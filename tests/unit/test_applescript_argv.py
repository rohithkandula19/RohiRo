"""applescript injection defense: handle and text ride argv, never the script.

a quote-bearing handle or body must never end up interpolated into the
osascript source. we assert the subprocess argv shape directly.
"""

from __future__ import annotations

from unittest.mock import patch


HOSTILE_HANDLE = '" of targetService\nset x to do shell script "id" -- '
HOSTILE_TEXT = 'hi" & (do shell script "touch /tmp/pwned") & "'


def test_imessage_send_passes_argv() -> None:
    from api.integrations import imessage as imsg

    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        ok = imsg._send_message(HOSTILE_HANDLE, HOSTILE_TEXT)
        assert ok
        argv = run.call_args[0][0]
        # script source is a fixed constant; hostile strings appear only as argv items
        assert argv[0] == "osascript"
        assert argv[1] == "-e"
        assert HOSTILE_HANDLE not in argv[2]
        assert HOSTILE_TEXT not in argv[2]
        assert argv[3] == HOSTILE_HANDLE
        assert argv[4] == HOSTILE_TEXT


def test_notify_passes_argv() -> None:
    from api.scheduler import engine

    with patch("api.scheduler.engine.subprocess.run") as run:
        engine._notify(title='evil" with title "x', message='m"sg\nline2')
        argv = run.call_args[0][0]
        assert argv[0] == "osascript"
        assert 'evil' not in argv[2]  # not in the script source
        assert argv[3].startswith('evil')
        assert "\n" not in argv[4]  # newlines flattened for notification
