"""OS authentication before revealing a stored credential. Never log credentials."""
import sys


def authenticate_windows():
    import ctypes as c
    from ctypes import wintypes as w
    import getpass

    class Info(c.Structure):
        _fields_ = [('size', w.DWORD), ('parent', w.HWND), ('message', w.LPCWSTR), ('caption', w.LPCWSTR), ('banner', w.HBITMAP)]
    info = Info(c.sizeof(Info), None, 'Verify your Windows account to reveal the bot token', 'LiKeWatch', None)
    package, size, save = w.ULONG(), w.ULONG(), w.BOOL()
    output = c.c_void_p()
    cred = c.WinDLL('credui')
    cred.CredUIPromptForWindowsCredentialsW.argtypes = [c.POINTER(Info),w.DWORD,c.POINTER(w.ULONG),c.c_void_p,w.ULONG,c.POINTER(c.c_void_p),c.POINTER(w.ULONG),c.POINTER(w.BOOL),w.DWORD]
    if cred.CredUIPromptForWindowsCredentialsW(c.byref(info),0,c.byref(package),None,0,c.byref(output),c.byref(size),c.byref(save),1):
        return False
    user, domain, password = (c.create_unicode_buffer(512) for _ in range(3))
    lengths = [w.DWORD(512) for _ in range(3)]
    handle = w.HANDLE()
    try:
        cred.CredUnPackAuthenticationBufferW.argtypes = [w.DWORD,c.c_void_p,w.DWORD,w.LPWSTR,c.POINTER(w.DWORD),w.LPWSTR,c.POINTER(w.DWORD),w.LPWSTR,c.POINTER(w.DWORD)]
        if not cred.CredUnPackAuthenticationBufferW(0,output,size,user,c.byref(lengths[0]),domain,c.byref(lengths[1]),password,c.byref(lengths[2])):
            return False
        if user.value.split('\\')[-1].casefold() != getpass.getuser().casefold():
            return False
        adv = c.WinDLL('advapi32')
        adv.LogonUserW.argtypes=[w.LPCWSTR,w.LPCWSTR,w.LPCWSTR,w.DWORD,w.DWORD,c.POINTER(w.HANDLE)]
        return bool(adv.LogonUserW(user,domain,password,3,0,c.byref(handle)))
    finally:
        if handle:
            c.windll.kernel32.CloseHandle(handle)
        c.memset(password,0,c.sizeof(password))
        c.memset(output,0,size.value)
        c.windll.ole32.CoTaskMemFree.argtypes=[c.c_void_p]
        c.windll.ole32.CoTaskMemFree(output)


def authentication_command():
    from .ocr import resource_path
    if sys.platform == 'darwin':
        helper = resource_path('assets', 'native-auth')
        if helper.is_file():
            return [str(helper)]
        return ['/usr/bin/swift', str(resource_path('assets','authenticate.swift'))]
    return None

from PySide6.QtCore import QThread, Signal


class Authentication(QThread):
    verified = Signal(bool)

    def run(self):
        try:
            if sys.platform == 'win32':
                allowed = authenticate_windows()
            else:
                import subprocess
                command = authentication_command()
                allowed = bool(command) and subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120).returncode == 0
        except Exception:
            allowed = False
        self.verified.emit(allowed)
