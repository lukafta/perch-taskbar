"""The few Win32 calls Qt doesn't cover, via ctypes.

Each function returns None/False instead of failing when not on Windows, so
callers don't need their own platform checks. Global hotkeys
(RegisterHotKey / WM_HOTKEY) will live here too.
"""

from __future__ import annotations

import ctypes
import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from ctypes import wintypes

    # Private WinDLL instances so setting argtypes/restype here can't clash
    # with other code that uses the shared ctypes.windll objects.
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    class _APPBARDATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uCallbackMessage", wintypes.UINT),
            ("uEdge", wintypes.UINT),
            ("rc", wintypes.RECT),
            ("lParam", wintypes.LPARAM),
        ]

    _shell32.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(_APPBARDATA)]
    _shell32.SHAppBarMessage.restype = ctypes.c_size_t

    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    _user32.AttachThreadInput.restype = wintypes.BOOL
    _user32.BringWindowToTop.argtypes = [wintypes.HWND]
    _user32.BringWindowToTop.restype = wintypes.BOOL
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _kernel32.GetCurrentThreadId.argtypes = []
    _kernel32.GetCurrentThreadId.restype = wintypes.DWORD

_ABM_GETTASKBARPOS = 0x05
_ABE_LEFT, _ABE_RIGHT = 0, 2


def taskbar_position() -> tuple[int, int] | None:
    """Edge and thickness of the primary taskbar, straight from the shell.

    Returns ``(edge, thickness)`` where ``edge`` is an ABE_* value
    (0 left, 1 top, 2 right, 3 bottom) and ``thickness`` is in physical pixels.
    Unlike the screen's work area, this still answers when the taskbar is set
    to auto-hide.
    """
    if not IS_WINDOWS:
        return None
    data = _APPBARDATA(cbSize=ctypes.sizeof(_APPBARDATA))
    if not _shell32.SHAppBarMessage(_ABM_GETTASKBARPOS, ctypes.byref(data)):
        return None
    rc = data.rc
    if data.uEdge in (_ABE_LEFT, _ABE_RIGHT):
        thickness = rc.right - rc.left
    else:
        thickness = rc.bottom - rc.top
    return data.uEdge, thickness


def force_foreground(hwnd: int) -> bool:
    """Make ``hwnd`` the foreground window when a plain request was refused.

    Windows only lets the process that owns the current foreground window move
    the foreground elsewhere. Briefly attaching this thread's input queue to
    that window's thread makes us count as its owner for the call.
    Returns True if the window ended up in the foreground.
    """
    if not IS_WINDOWS:
        return False
    foreground_thread = _user32.GetWindowThreadProcessId(_user32.GetForegroundWindow(), None)
    our_thread = _kernel32.GetCurrentThreadId()
    attached = foreground_thread not in (0, our_thread) and bool(
        _user32.AttachThreadInput(our_thread, foreground_thread, True)
    )
    try:
        _user32.BringWindowToTop(hwnd)
        return bool(_user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            _user32.AttachThreadInput(our_thread, foreground_thread, False)
