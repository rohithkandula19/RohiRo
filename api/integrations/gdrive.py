"""google drive client.

reads from the shared google token written by setup_google_oauth.py. read-only:
ro can list, search, and pull file content into chat as context, but doesn't
write to drive.

verbs:
- configured()
- list_recent_files(limit=20)                       -> list[DriveFile]
- search_files(query, limit=15)                     -> list[DriveFile]
- get_file_text(file_id)                            -> str

PDFs are extracted via pypdfium2 (text layer). when the text layer is empty or
nearly so (scanned PDFs), pages are rendered to PNG and run through claude
vision in OCR mode.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from typing import Any, Optional

from api.integrations import google_auth, vision
from api.observability.logging import log

# mime types we know how to read as plain text
_TEXT_MIMES = {
    "text/plain", "text/markdown", "text/html", "application/json",
    "application/xml", "text/csv", "text/tab-separated-values",
}
# google native formats: export to plain text or markdown
_GOOGLE_EXPORTS = {
    "application/vnd.google-apps.document": ("text/plain", "txt"),
    "application/vnd.google-apps.spreadsheet": ("text/csv", "csv"),
    "application/vnd.google-apps.presentation": ("text/plain", "txt"),
}


@dataclass
class DriveFile:
    file_id: str
    name: str
    mime_type: str
    modified_at: str
    owner: str = ""
    size: int = 0
    parents: list[str] | None = None
    starred: bool = False
    web_view: str = ""


def configured() -> bool:
    return google_auth.configured()


def _service():
    return google_auth.service("drive", "v3")


async def _run(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


# ----- list / search -----


_FIELDS = "files(id,name,mimeType,modifiedTime,size,owners,starred,parents,webViewLink)"


def _to_file(x: dict[str, Any]) -> DriveFile:
    owners = x.get("owners") or []
    owner_name = owners[0].get("displayName", "") if owners else ""
    return DriveFile(
        file_id=x["id"],
        name=x.get("name", "(unnamed)"),
        mime_type=x.get("mimeType", ""),
        modified_at=x.get("modifiedTime", ""),
        owner=owner_name,
        size=int(x.get("size") or 0),
        parents=x.get("parents") or [],
        starred=bool(x.get("starred", False)),
        web_view=x.get("webViewLink", ""),
    )


async def list_recent_files(limit: int = 20) -> list[DriveFile]:
    if not configured():
        return []
    svc = _service()

    def _do():
        resp = (
            svc.files()
            .list(
                pageSize=limit,
                orderBy="modifiedTime desc",
                q="trashed = false",
                fields=_FIELDS,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        return [_to_file(f) for f in resp.get("files", [])]

    return await _run(_do)


async def search_files(query: str, limit: int = 15) -> list[DriveFile]:
    if not configured() or not query.strip():
        return []
    svc = _service()
    # quote the user's query for the drive query language
    safe = query.replace("'", "\\'")
    q = f"name contains '{safe}' or fullText contains '{safe}' and trashed = false"

    def _do():
        resp = (
            svc.files()
            .list(
                pageSize=limit,
                q=q,
                orderBy="modifiedTime desc",
                fields=_FIELDS,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        return [_to_file(f) for f in resp.get("files", [])]

    return await _run(_do)


# ----- read content -----


async def get_file_text(file_id: str, *, max_chars: int = 16000) -> str:
    """fetch file content as plain text. google native -> exported; binary -> empty.

    PDFs: text layer first; if sparse, OCR via claude vision on each page (capped).
    """
    svc = _service()

    def _meta_and_bytes() -> tuple[str, str, bytes | None]:
        meta = svc.files().get(fileId=file_id, fields="id,name,mimeType,size").execute()
        mime = meta.get("mimeType", "")
        if mime in _GOOGLE_EXPORTS:
            export_mime, _ = _GOOGLE_EXPORTS[mime]
            data = svc.files().export(fileId=file_id, mimeType=export_mime).execute()
            text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
            return mime, text, None
        if mime in _TEXT_MIMES or mime.startswith("text/"):
            data = svc.files().get_media(fileId=file_id).execute()
            text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
            return mime, text, None
        if mime == "application/pdf":
            data = svc.files().get_media(fileId=file_id).execute()
            return mime, "", data if isinstance(data, (bytes, bytearray)) else None
        return mime, f"[binary file, mimeType={mime}, not extracted]", None

    mime, text, pdf_bytes = await _run(_meta_and_bytes)

    if mime == "application/pdf" and pdf_bytes:
        text = await _extract_pdf(pdf_bytes, max_chars=max_chars)

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n…[truncated at {max_chars} chars]"
    return text


# ----- pdf -----


async def _extract_pdf(pdf_bytes: bytes, *, max_chars: int = 16000, ocr_page_cap: int = 6) -> str:
    """text layer first; OCR up to `ocr_page_cap` pages with vision if it's a scan."""
    def _text_layer() -> tuple[str, int]:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(pdf_bytes)
        pages = []
        n = len(pdf)
        for i in range(n):
            page = pdf[i]
            textpage = page.get_textpage()
            try:
                pages.append(textpage.get_text_range() or "")
            finally:
                textpage.close()
                page.close()
        pdf.close()
        return "\n\n".join(pages), n

    text, n_pages = await _run(_text_layer)
    avg = (len(text) / max(1, n_pages)) if n_pages else 0
    if text.strip() and avg >= 60:
        return text

    # scanned/empty layer: OCR via vision
    log.info("pdf text layer sparse, falling back to vision OCR", chars=len(text), pages=n_pages)
    ocr_chunks: list[str] = []
    pages_to_ocr = min(n_pages, ocr_page_cap)
    images = await _run(_render_pdf_pages, pdf_bytes, pages_to_ocr)
    for i, png in enumerate(images, start=1):
        try:
            page_text = await vision.ocr(png)
        except Exception as e:
            page_text = f"(vision OCR failed on page {i}: {e})"
        ocr_chunks.append(f"=== page {i} ===\n{page_text}")
    head = "\n\n".join(ocr_chunks)
    if n_pages > pages_to_ocr:
        head += f"\n\n[...{n_pages - pages_to_ocr} more pages skipped to keep cost down]"
    return head


def _render_pdf_pages(pdf_bytes: bytes, max_pages: int, scale: float = 1.5) -> list[bytes]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_bytes)
    out: list[bytes] = []
    try:
        for i in range(min(len(pdf), max_pages)):
            page = pdf[i]
            bitmap = page.render(scale=scale)
            pil = bitmap.to_pil()
            buf = io.BytesIO()
            pil.save(buf, format="PNG", optimize=True)
            out.append(buf.getvalue())
            page.close()
    finally:
        pdf.close()
    return out
