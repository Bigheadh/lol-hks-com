from __future__ import annotations

import os


def game_running() -> bool:
    """Detect game launch by executable name, including when it is not foreground."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        return False
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        available = kernel32.Process32FirstW(handle, ctypes.byref(entry))
        while available:
            if entry.szExeFile.casefold() == "league of legends.exe":
                return True
            available = kernel32.Process32NextW(handle, ctypes.byref(entry))
        return False
    finally:
        kernel32.CloseHandle(handle)


def enable_dpi_awareness() -> None:
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass


def foreground_client_region() -> dict | None:
    """Read the visible League client bounds, without accessing game memory."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    hwnd = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return None
    try:
        path = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            return None
        if os.path.basename(path.value).casefold() not in {"leagueclientux.exe", "leagueclient.exe"}:
            return None
    finally:
        kernel32.CloseHandle(handle)
    rect, origin = wintypes.RECT(), wintypes.POINT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)) or not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    if rect.right < 600 or rect.bottom < 400:
        return None
    return dict(left=origin.x, top=origin.y, width=rect.right, height=rect.bottom)


def capture_screen(monitor: int = 1, region: dict | None = None):
    import mss
    from PIL import Image, ImageStat

    with mss.mss() as screen:
        if region is None:
            if monitor < 1 or monitor >= len(screen.monitors):
                raise ValueError(f"显示器 {monitor} 不存在，请重新选择。")
            region = screen.monitors[monitor]
        shot = screen.grab(region)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
    if max(ImageStat.Stat(image).stddev) < 2:
        raise ValueError("截图接近纯色，无法识别。可切换游戏为无边框窗口，或导入截图。")
    return image
