"""ro menubar app.

a tiny macos menubar app that:
  - listens for a global hotkey (default: option+space)
  - records audio from the default mic
  - posts to /api/voice/loop
  - speaks ro's response via afplay
  - shows status in the menubar (idle / recording / thinking / speaking)
  - posts a notification with ro's reply text

permissions you'll be prompted for the first time:
  - Microphone (System Settings → Privacy & Security → Microphone)
  - Accessibility (for the global hotkey via pynput)
  - Notifications (optional, for the reply popup)

run:
  uv run python desktop/menubar.py
or as a launchd autostart, see infra/launchd/com.ro.menubar.plist
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import numpy as np
import rumps
import sounddevice as sd
import soundfile as sf
from pynput import keyboard

API_BASE = os.environ.get("RO_API_BASE", "http://127.0.0.1:8000")
HOTKEY = os.environ.get("RO_HOTKEY", "<alt>+<space>")  # pynput format
SAMPLE_RATE = 16000  # whisper sweet spot
MAX_SECONDS = 60     # cap; press hotkey again to stop


class RoMenubar(rumps.App):
    def __init__(self) -> None:
        super().__init__("ro", title="ro", quit_button=None)
        self._approvals_menu = rumps.MenuItem("Approvals (0)")
        self.menu = [
            rumps.MenuItem("Talk to ro", callback=self.menu_talk),
            rumps.MenuItem("Ask about my screen", callback=self.menu_screen),
            None,  # separator
            self._approvals_menu,
            rumps.MenuItem("Open web", callback=self.menu_open_web),
            rumps.MenuItem("Status: idle"),
            None,
            rumps.MenuItem("Quit", callback=self.menu_quit),
        ]
        self._status_item = self.menu["Status: idle"]
        self._recording = False
        self._audio_buf: list[np.ndarray] = []
        self._stop_event = threading.Event()
        self._listener: keyboard.GlobalHotKeys | None = None
        self._start_hotkey()
        self._approvals_timer = rumps.Timer(self._refresh_approvals, 20)
        self._approvals_timer.start()

    # ----- approvals: see + decide from the menubar -----

    def _refresh_approvals(self, _timer: rumps.Timer) -> None:
        threading.Thread(target=self._load_approvals, daemon=True).start()

    def _load_approvals(self) -> None:
        try:
            r = httpx.get(f"{API_BASE}/api/approvals", timeout=5)
            pending = r.json() if r.status_code == 200 else []
        except Exception:
            pending = []
        # rebuild the submenu on the main thread via rumps timer-safe calls
        self._approvals_menu.title = f"Approvals ({len(pending)})"
        # clear old entries
        for key in list(self._approvals_menu.keys()):
            del self._approvals_menu[key]
        if not pending:
            self._approvals_menu.add(rumps.MenuItem("nothing pending"))
            return
        for a in pending[:8]:
            desc = (a.get("description") or a.get("tool") or "?")[:70]
            item = rumps.MenuItem(desc)
            aid = a.get("id")
            item.add(rumps.MenuItem("Approve", callback=self._decide_cb(aid, "approved")))
            item.add(rumps.MenuItem("Reject", callback=self._decide_cb(aid, "rejected")))
            self._approvals_menu.add(item)

    def _decide_cb(self, action_id: str, decision: str):
        def _cb(_: rumps.MenuItem) -> None:
            def _post() -> None:
                try:
                    httpx.post(
                        f"{API_BASE}/api/approvals/{action_id}/decide",
                        json={"decision": decision}, timeout=30,
                    )
                except Exception:
                    pass
                self._load_approvals()
            threading.Thread(target=_post, daemon=True).start()
        return _cb

    # ----- screen sense: capture, ocr locally, ask ro -----

    def menu_screen(self, _: rumps.MenuItem) -> None:
        threading.Thread(target=self._screen_sense, daemon=True).start()

    def _screen_sense(self) -> None:
        """screenshot -> on-device ocr (apple vision, no cloud) -> ro.
        the pixels never leave the machine; only the recognized text goes to
        the supervisor, and the vault/airgap lanes still apply there."""
        import tempfile
        shot = os.path.join(tempfile.gettempdir(), "ro-screen.png")
        r = subprocess.run(["screencapture", "-x", shot], capture_output=True)
        if r.returncode != 0 or not os.path.exists(shot):
            rumps.notification("ro", "", "screen capture failed — grant Screen Recording permission")
            return
        try:
            text = self._ocr_local(shot)
        finally:
            try:
                os.unlink(shot)
            except OSError:
                pass
        if not text.strip():
            rumps.notification("ro", "", "could not read any text on screen")
            return

        window = rumps.Window(
            message="what do you want to know about what's on your screen?",
            title="ro · screen sense",
            default_text="what is this error and how do i fix it?",
            ok="ask", cancel="never mind", dimensions=(340, 60),
        )
        resp = window.run()
        if not resp.clicked or not resp.text.strip():
            return
        self._set_status("thinking about your screen…")
        try:
            answer = httpx.post(
                f"{API_BASE}/api/chat",
                json={"text": f"(context: text ocr'd from my screen, read-only)\n---\n{text[:6000]}\n---\n\n{resp.text.strip()}"},
                timeout=120,
            ).json().get("text", "(no reply)")
        except Exception as e:
            answer = f"api error: {e}"
        self._set_status("idle")
        subprocess.run(["pbcopy"], input=answer.encode(), check=False)
        rumps.Window(
            message=answer[:2000], title="ro says (also on your clipboard)",
            ok="thanks", dimensions=(0, 0),
        ).run()

    @staticmethod
    def _ocr_local(path: str) -> str:
        """apple vision framework, fully on-device."""
        try:
            import Quartz
            import Vision
        except ImportError:
            return ""
        data = open(path, "rb").read()
        provider = Quartz.CGDataProviderCreateWithData(None, data, len(data), None)
        image = Quartz.CGImageCreateWithPNGDataProvider(provider, None, False, Quartz.kCGRenderingIntentDefault)
        if image is None:
            return ""
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        ok, _err = handler.performRequests_error_([request], None)
        if not ok:
            return ""
        lines = []
        for obs in request.results() or []:
            candidates = obs.topCandidates_(1)
            if candidates and len(candidates):
                lines.append(str(candidates[0].string()))
        return "\n".join(lines)

    # ----- menu actions -----

    def menu_talk(self, _: rumps.MenuItem) -> None:
        self.toggle()

    def menu_open_web(self, _: rumps.MenuItem) -> None:
        subprocess.Popen(["open", "http://localhost:3000"])

    def menu_quit(self, _: rumps.MenuItem) -> None:
        try:
            if self._listener:
                self._listener.stop()
        finally:
            rumps.quit_application()

    # ----- hotkey -----

    def _start_hotkey(self) -> None:
        try:
            self._listener = keyboard.GlobalHotKeys({HOTKEY: self._on_hotkey})
            self._listener.start()
            self._set_status(f"idle ({HOTKEY})")
        except Exception as e:
            self._set_status(f"hotkey error: {e}")

    def _on_hotkey(self) -> None:
        # callback runs on the listener thread; bounce to main
        threading.Thread(target=self.toggle, daemon=True).start()

    # ----- core flow -----

    def toggle(self) -> None:
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self._recording = True
        self._audio_buf = []
        self.title = "● ro"        # red dot in menubar
        self._set_status("recording…")
        self._stop_event.clear()
        threading.Thread(target=self._record_loop, daemon=True).start()
        threading.Thread(target=self._auto_stop, daemon=True).start()

    def _stop_recording(self) -> None:
        if not self._recording:
            return
        self._recording = False
        self._stop_event.set()
        self.title = "ro"
        self._set_status("thinking…")
        threading.Thread(target=self._finish, daemon=True).start()

    def _record_loop(self) -> None:
        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=int(SAMPLE_RATE * 0.1),  # 100ms chunks
            ) as stream:
                while not self._stop_event.is_set():
                    chunk, _ = stream.read(int(SAMPLE_RATE * 0.1))
                    self._audio_buf.append(chunk.copy())
        except Exception as e:
            self._set_status(f"mic error: {e}")
            self._recording = False
            self.title = "ro"

    def _auto_stop(self) -> None:
        t0 = time.time()
        while self._recording and (time.time() - t0) < MAX_SECONDS:
            time.sleep(0.5)
        if self._recording:
            self._stop_recording()

    def _finish(self) -> None:
        # write audio to a tmp wav
        if not self._audio_buf:
            self._set_status("no audio")
            self.title = "ro"
            return
        audio = np.concatenate(self._audio_buf, axis=0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio, SAMPLE_RATE, subtype="PCM_16")
            wav_path = f.name

        try:
            transcript, response, mp3_path = self._roundtrip(wav_path)
        except Exception as e:
            self._set_status(f"error: {e}")
            self.title = "ro"
            return
        finally:
            try:
                Path(wav_path).unlink(missing_ok=True)
            except Exception:
                pass

        if not transcript:
            self._set_status("no speech detected")
            self.title = "ro"
            return

        self._set_status("speaking…")
        self.title = "♪ ro"
        try:
            rumps.notification(title="ro", subtitle=transcript[:80], message=response[:240] or "(no reply)")
        except Exception:
            pass

        if mp3_path:
            subprocess.run(["afplay", mp3_path], check=False)
            try:
                Path(mp3_path).unlink(missing_ok=True)
            except Exception:
                pass

        self.title = "ro"
        self._set_status(f"idle ({HOTKEY})")

    def _roundtrip(self, wav_path: str) -> tuple[str, str, str | None]:
        """upload wav -> /api/voice/loop, then fetch tts mp3."""
        with httpx.Client(timeout=120.0) as c, open(wav_path, "rb") as fp:
            files = {"audio": ("audio.wav", fp, "audio/wav")}
            r = c.post(f"{API_BASE}/api/voice/loop", files=files)
            r.raise_for_status()
            data = r.json()
            transcript = data.get("transcript", "")
            response = data.get("response", "")

        mp3_path: str | None = None
        if response:
            with httpx.Client(timeout=60.0) as c:
                rs = c.post(f"{API_BASE}/api/voice/speak", json={"text": response})
                if rs.status_code == 200 and rs.content:
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as out:
                        out.write(rs.content)
                        mp3_path = out.name
        return transcript, response, mp3_path

    # ----- ui helpers -----

    def _set_status(self, text: str) -> None:
        self._status_item.title = f"Status: {text}"


def main() -> None:
    RoMenubar().run()


if __name__ == "__main__":
    main()
