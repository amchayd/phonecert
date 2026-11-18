from phonecert.device.reader import _error_message

LOG = ("2026-11-10 19:35:05 Mac.local pymobiledevice3.__main__[47208] ERROR Device is not connected.\n"
       "2026-11-10 19:35:05 Mac.local pymobiledevice3.__main__[47208] INFO Run again with -v for the full traceback")


def test_error_message_keeps_the_error_line():
    assert _error_message(LOG) == "Device is not connected."
    assert _error_message("plain failure") == "plain failure"
    assert _error_message("") == "unknown error"
