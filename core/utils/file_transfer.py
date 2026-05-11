import ctypes
from ctypes import wintypes
import os
import shutil
import platform
from pathlib import Path
from .platform import is_windows


# Read the Windows FILETIME values for CreationTime, AccessTime, and ModifyTime.
def read_windows_file_times(path: Path):
    if not is_windows():
        return None

    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    handle = kernel32.CreateFileW(
        str(path),
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002 | 0x00000004,  # share flags
        None,
        3,  # OPEN_EXISTING
        0x00000080,  # FILE_ATTRIBUTE_NORMAL
        None,
    )

    if handle == wintypes.HANDLE(-1).value:
        return None

    try:
        created = FILETIME()
        accessed = FILETIME()
        written = FILETIME()

        if not kernel32.GetFileTime(
            handle,
            ctypes.byref(created),
            ctypes.byref(accessed),
            ctypes.byref(written),
        ):
            return None

        return (
            (created.dwLowDateTime, created.dwHighDateTime),
            (accessed.dwLowDateTime, accessed.dwHighDateTime),
            (written.dwLowDateTime, written.dwHighDateTime),
        )
    finally:
        kernel32.CloseHandle(handle)


# Apply the given Windows FILETIME values to the specified path. This is 
# necessary when moving files across drives since CreationTime isn't preserved by default.
def apply_windows_file_times(path: Path, file_times):
    if not is_windows() or file_times is None:
        return

    try:
        import pywintypes
        import win32file
        import win32con
    except ImportError:
        return

    handle = win32file.CreateFile(
        str(path),
        win32con.GENERIC_WRITE,
        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
        None,
        win32con.OPEN_EXISTING,
        win32con.FILE_ATTRIBUTE_NORMAL,
        None,
    )

    if handle == win32file.INVALID_HANDLE_VALUE:
        return

    try:
        c_low, c_high = file_times[0]
        a_low, a_high = file_times[1]
        w_low, w_high = file_times[2]

        # FILETIME → 64bit int → pywintypes.Time
        def to_time(low, high):
            ft = (high << 32) | low
            return pywintypes.Time(ft / 10_000_000 - 11644473600)

        win32file.SetFileTime(
            handle,
            to_time(c_low, c_high),
            to_time(a_low, a_high),
            to_time(w_low, w_high),
        )
    finally:
        handle.close()


def transfer_file_safe(src: Path, dst: Path, mode: str):
    src = Path(src)
    dst = Path(dst)

    if not src.exists():
        raise FileNotFoundError(f"Source file does not exist: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    file_times = None
    try:
        file_times = read_windows_file_times(src)
    except OSError:
        file_times = None

    try:
        if mode == "copy":
            shutil.copy2(src, dst)
        elif mode == "move":
            same_drive = (
                os.path.splitdrive(str(src))[0].lower()
                == os.path.splitdrive(str(dst))[0].lower()
            )
            shutil.move(str(src), str(dst))

            if same_drive:
                return
        else:
            raise ValueError(f"Unsupported transfer mode: {mode}")

    except PermissionError as exc:
        raise PermissionError(
            f"File is locked or permission denied: {src}"
        ) from exc

    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Temporary file disappeared during transfer: {src}"
        ) from exc

    try:
        apply_windows_file_times(dst, file_times)
    except OSError:
        pass


def move_to_system_recycle(path: Path) -> bool:
    if not is_windows() or not path.exists():
        return False

    shell32 = ctypes.windll.shell32
    from_path = str(path.resolve()) + "\0\0"

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    file_operation = SHFILEOPSTRUCTW()
    file_operation.hwnd = None
    file_operation.wFunc = 0x0003  # FO_DELETE
    file_operation.pFrom = from_path
    file_operation.pTo = None
    file_operation.fFlags = 0x0040 | 0x0010 | 0x0400  # FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI

    result = shell32.SHFileOperationW(ctypes.byref(file_operation))
    return result == 0 and not file_operation.fAnyOperationsAborted
