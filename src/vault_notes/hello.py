"""Windows Hello (fingerprint / face / PIN) verification.

Calls UserConsentVerifier through its window interop interface, so the prompt
is attached to our window instead of appearing behind it. Uses plain ctypes,
so no extra packages are needed.
"""

import ctypes
import uuid
from ctypes import POINTER, byref, c_int32, c_uint32, c_void_p, wintypes

from PySide6.QtCore import QTimer

OK = "ok"
CANCELLED = "cancelled"
UNAVAILABLE = "unavailable"

CLASS_NAME = "Windows.Security.Credentials.UI.UserConsentVerifier"
IID_INTEROP = uuid.UUID("39E050C3-4E74-441A-8DC0-B81104DF949C")  # IUserConsentVerifierInterop
IID_ASYNC_INFO = uuid.UUID("00000036-0000-0000-C000-000000000046")  # IAsyncInfo
# IAsyncOperation<UserConsentVerificationResult>, from the Windows SDK's windows.security.credentials.ui.h
IID_ASYNC_OP = uuid.UUID("fd596ffd-2318-558f-9dbe-d21df43764a5")

# UserConsentVerificationResult values
VERIFIED = 0
NOT_AVAILABLE_RESULTS = {1, 2, 3}  # DeviceNotPresent, NotConfiguredForUser, DisabledByPolicy

# AsyncStatus values
STARTED = 0
COMPLETED = 1


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def of(cls, u: uuid.UUID) -> "GUID":
        return cls.from_buffer_copy(u.bytes_le)


combase = ctypes.windll.combase
combase.WindowsCreateString.argtypes = [wintypes.LPCWSTR, c_uint32, POINTER(c_void_p)]
combase.WindowsCreateString.restype = ctypes.HRESULT
combase.WindowsDeleteString.argtypes = [c_void_p]
combase.RoGetActivationFactory.argtypes = [c_void_p, POINTER(GUID), POINTER(c_void_p)]
combase.RoGetActivationFactory.restype = ctypes.HRESULT


def _method(ptr: c_void_p, index: int, *argtypes, restype=ctypes.HRESULT):
    """Returns the COM method at vtable slot `index`, bound to `ptr`."""
    vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtable[index])
    return lambda *args: fn(ptr, *args)


def _release(ptr: c_void_p) -> None:
    if ptr:
        _method(ptr, 2, restype=c_uint32)()


def _hstring(text: str) -> c_void_p:
    h = c_void_p()
    combase.WindowsCreateString(text, len(text), byref(h))
    return h


_pending: list["_Request"] = []


class _Request:
    def __init__(self, hwnd: int, message: str, on_done):
        self.on_done = on_done
        self.op = c_void_p()
        self.info = c_void_p()
        self.timer = QTimer(interval=100, timeout=self._poll)

        class_name = _hstring(CLASS_NAME)
        msg = _hstring(message)
        factory = c_void_p()
        try:
            combase.RoGetActivationFactory(class_name, byref(GUID.of(IID_INTEROP)), byref(factory))
            # IInspectable has 6 slots; RequestVerificationForWindowAsync is the first after them.
            request = _method(factory, 6, wintypes.HWND, c_void_p, POINTER(GUID), POINTER(c_void_p))
            request(hwnd, msg, byref(GUID.of(IID_ASYNC_OP)), byref(self.op))
            query = _method(self.op, 0, POINTER(GUID), POINTER(c_void_p))
            query(byref(GUID.of(IID_ASYNC_INFO)), byref(self.info))
        finally:
            _release(factory)
            combase.WindowsDeleteString(class_name)
            combase.WindowsDeleteString(msg)
        self.timer.start()

    def _poll(self):
        status = c_int32()
        try:
            _method(self.info, 7, POINTER(c_int32))(byref(status))  # IAsyncInfo.get_Status
            if status.value == STARTED:
                return
            result = None
            if status.value == COMPLETED:
                value = c_int32()
                _method(self.op, 8, POINTER(c_int32))(byref(value))  # IAsyncOperation.GetResults
                result = value.value
        except OSError:
            result = None
        self._finish(result)

    def _finish(self, result):
        self.timer.stop()
        _release(self.info)
        _release(self.op)
        self.info = self.op = None
        if self in _pending:
            _pending.remove(self)
        if result == VERIFIED:
            self.on_done(OK)
        elif result in NOT_AVAILABLE_RESULTS:
            self.on_done(UNAVAILABLE)
        else:
            self.on_done(CANCELLED)


def verify(hwnd: int, message: str, on_done) -> None:
    """Shows the Windows Hello prompt. Calls on_done(OK | CANCELLED | UNAVAILABLE)."""
    try:
        _pending.append(_Request(hwnd, message, on_done))
    except OSError:
        on_done(UNAVAILABLE)
