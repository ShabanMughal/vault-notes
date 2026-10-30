"""Windows integration: global hotkey, lock-on-Windows-lock, start with Windows."""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter

user32 = ctypes.windll.user32
wtsapi32 = ctypes.windll.wtsapi32

WM_HOTKEY = 0x0312
WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000

HOTKEY_ID = 0xB17E

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "VaultNotes"


class NativeFilter(QAbstractNativeEventFilter):
    """Receives the global hotkey and the Windows session-lock message."""

    def __init__(self, on_hotkey, on_session_lock):
        super().__init__()
        self.on_hotkey = on_hotkey
        self.on_session_lock = on_session_lock

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                self.on_hotkey()
                return True, 0
            if msg.message == WM_WTSSESSION_CHANGE and msg.wParam == WTS_SESSION_LOCK:
                self.on_session_lock()
        return False, 0


def register_hotkey(key: str = "N") -> bool:
    """Ctrl+Alt+<key>, delivered to this thread's message queue."""
    return bool(user32.RegisterHotKey(None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord(key)))


def unregister_hotkey() -> None:
    user32.UnregisterHotKey(None, HOTKEY_ID)


def register_session_notifications(hwnd: int) -> None:
    wtsapi32.WTSRegisterSessionNotification(wintypes.HWND(hwnd), 0)


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw}" -m vault_notes --tray'


def autostart_enabled() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except OSError:
                pass
