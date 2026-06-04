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
        self.menu = [
            rumps.MenuItem("Talk to ro", callback=self.menu_talk),
            None,  # separator
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
