import platform

# This module provides a cross-platform file transfer function that preserves timestamps.
def is_windows():
    return platform.system() == "Windows"

# This module provides platform-specific utilities for file operations, 
# such as checking if the current OS is Windows and if the pywin32 library is available.
def has_pywin32():
    if not is_windows():
        return False
    try:
        import win32file, win32con, pywintypes
        return True
    except ImportError:
        return False
