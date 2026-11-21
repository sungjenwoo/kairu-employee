"""The device monitor: notices a USB or other plugged-in device this PC has never seen. Read-only.

Each round it lists the devices present (Windows: SetupAPI, the list Device Manager shows, for the
USB, USB storage and HID buses; Linux: /sys/bus/usb). The first look learns every device already
known; after that, a device never seen before gives one alert, listing what was plugged in:

  new_device    any new device (a USB drive, a phone, a mouse)
  new_keyboard  a new keyboard: high, because a gadget that pretends to be a keyboard can type
                commands faster than anyone can see

It never blocks, ejects or changes a device. Unplugging is never an alert.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

from kairu.protect.store import Finding, ProtectStore, iso, now_utc

ENUMERATORS = ("USB", "USBSTOR", "HID")
KNOWN = "devices:known"  # in protection.db settings: device ids already seen, one per line


@dataclass(frozen=True)
class Device:
    id: str  # Windows instance id, e.g. USB\VID_0781&PID_5567\4C530001; stable for a device with a serial number
    name: str
    kind: str  # Windows device class: DiskDrive, Keyboard, Mouse, WPD, ...; "" if unknown


def present() -> list[Device]:
    if sys.platform == "win32":
        return _windows()
    return _linux()


class DeviceMonitor:
    name = "devices"

    def __init__(self, store: ProtectStore, listing=present):
        self.store, self.listing = store, listing

    def check(self) -> tuple[list[Finding], str]:
        devices = self.listing()
        known = set((self.store.setting(KNOWN) or "").splitlines())
        ids = {device.id.upper(): device for device in devices}
        first = self.store.setting(KNOWN) is None
        new = [device for key, device in sorted(ids.items()) if key not in known]
        self.store.set_setting(KNOWN, "\n".join(sorted(known | set(ids))))
        note = f"{len(ids)} connected, {len(known | set(ids))} known"
        if first or not new:
            return [], note
        return [self._finding(new)], note

    def _finding(self, new: list[Device]) -> Finding:
        keyboards = [device for device in new if device.kind.lower() == "keyboard"]
        named = sorted({device.name for device in new if device.name}) or ["a device with no name"]
        lines = [("Devices", "; ".join(named[:6]) + (f" and {len(named) - 6} more" if len(named) > 6 else "")),
                 ("Seen at", now_utc().astimezone().strftime("%a %d %b %Y, %H:%M"))]
        lines += [("Device id", device.id[:120]) for device in new[:3]]
        if keyboards:
            return Finding(key=f"devices:{iso(now_utc())}", source="devices", kind="new_keyboard", severity="high",
                           classification="Confirmed fact", title=f"New keyboard connected: {keyboards[0].name or 'unnamed'}",
                           lines=lines, why=["a keyboard this PC has never seen was connected",
                                             "a gadget that pretends to be a keyboard (such as a fake USB stick) can "
                                             "type commands by itself"],
                           not_checked=["whether it is a real keyboard"],
                           you_can="If you just plugged in a keyboard yourself, nothing to do. If not, unplug it now "
                                   "and press Ctrl+Alt+K. Kairu changed nothing.")
        return Finding(key=f"devices:{iso(now_utc())}", source="devices", kind="new_device", severity="warning",
                       classification="Confirmed fact", title=f"New device connected: {named[0]}", lines=lines,
                       why=["a device this PC has never seen was connected"], not_checked=["what is on it"],
                       you_can="If you plugged it in yourself, nothing to do. If not, unplug it. Kairu changed nothing.")


# --- Windows: SetupAPI through ctypes ----------------------------------------------------------------

def _windows() -> list[Device]:
    import ctypes
    from ctypes import wintypes

    class DevInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", ctypes.c_byte * 16), ("DevInst", wintypes.DWORD),
                    ("Reserved", ctypes.c_size_t)]

    api = ctypes.WinDLL("setupapi", use_last_error=True)
    api.SetupDiGetClassDevsW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD)
    api.SetupDiGetClassDevsW.restype = ctypes.c_void_p
    api.SetupDiEnumDeviceInfo.argtypes = (ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DevInfo))
    api.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
    api.SetupDiGetDeviceInstanceIdW.argtypes = (ctypes.c_void_p, ctypes.POINTER(DevInfo), wintypes.LPWSTR, wintypes.DWORD,
                                                ctypes.POINTER(wintypes.DWORD))
    api.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
    api.SetupDiGetDeviceRegistryPropertyW.argtypes = (ctypes.c_void_p, ctypes.POINTER(DevInfo), wintypes.DWORD,
                                                      ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p, wintypes.DWORD,
                                                      ctypes.POINTER(wintypes.DWORD))
    api.SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL
    api.SetupDiDestroyDeviceInfoList.argtypes = (ctypes.c_void_p,)
    invalid = ctypes.c_void_p(-1).value
    present_only, all_classes = 0x2, 0x4
    friendly, description, device_class = 0xC, 0x0, 0x7

    def text(handle, info, prop) -> str:
        buffer = ctypes.create_unicode_buffer(512)
        if api.SetupDiGetDeviceRegistryPropertyW(handle, ctypes.byref(info), prop, None, buffer, ctypes.sizeof(buffer), None):
            return buffer.value
        return ""

    found = []
    for enumerator in ENUMERATORS:
        handle = api.SetupDiGetClassDevsW(None, enumerator, None, present_only | all_classes)
        if handle in (None, invalid):
            continue
        try:
            index, info = 0, DevInfo(cbSize=ctypes.sizeof(DevInfo))
            while api.SetupDiEnumDeviceInfo(handle, index, ctypes.byref(info)):
                index += 1
                ident = ctypes.create_unicode_buffer(512)
                if not api.SetupDiGetDeviceInstanceIdW(handle, ctypes.byref(info), ident, 512, None):
                    continue
                name = text(handle, info, friendly) or text(handle, info, description)
                found.append(Device(ident.value, name, text(handle, info, device_class)))
        finally:
            api.SetupDiDestroyDeviceInfoList(handle)
    return found


# --- Linux: /sys/bus/usb ---------------------------------------------------------------------------

def _linux() -> list[Device]:
    found = []
    for folder in sorted(Path("/sys/bus/usb/devices").glob("*")):
        try:
            vendor = (folder / "idVendor").read_text().strip()
            product = (folder / "idProduct").read_text().strip()
        except OSError:
            continue  # an interface, not a device
        serial = _read(folder / "serial") or folder.name
        name = " ".join(part for part in (_read(folder / "manufacturer"), _read(folder / "product")) if part)
        keyboard = any(_read(face / "bInterfaceClass") == "03" and _read(face / "bInterfaceProtocol") == "01"
                       for face in folder.glob(f"{folder.name}:*"))
        found.append(Device(f"USB\\VID_{vendor}&PID_{product}\\{serial}".upper(), name, "Keyboard" if keyboard else ""))
    return found


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""
