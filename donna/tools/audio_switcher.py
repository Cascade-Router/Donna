"""Toggle Windows default audio endpoint between wired and Bluetooth devices."""

from __future__ import annotations

from ctypes import HRESULT, c_int, c_wchar_p
from typing import Any

from comtypes import CLSCTX_ALL, COMMETHOD, CoCreateInstance, GUID, IUnknown


# Undocumented PolicyConfig COM interface used to set the default endpoint.
class IPolicyConfig(IUnknown):
    _iid_ = GUID("{f8679f50-850a-41cf-9c72-430f290290c8}")
    _methods_ = (
        COMMETHOD([], HRESULT, "Unused1"),
        COMMETHOD([], HRESULT, "Unused2"),
        COMMETHOD([], HRESULT, "Unused3"),
        COMMETHOD([], HRESULT, "Unused4"),
        COMMETHOD([], HRESULT, "Unused5"),
        COMMETHOD([], HRESULT, "Unused6"),
        COMMETHOD([], HRESULT, "Unused7"),
        COMMETHOD([], HRESULT, "Unused8"),
        COMMETHOD([], HRESULT, "Unused9"),
        COMMETHOD([], HRESULT, "Unused10"),
        COMMETHOD(
            [],
            HRESULT,
            "SetDefaultEndpoint",
            (["in"], c_wchar_p, "deviceId"),
            (["in"], c_int, "role"),
        ),
    )


_CLSID_POLICY_CONFIG = GUID("{870af99c-171d-4f9e-af0d-e63df40c2bc9}")

_BLUETOOTH_HINTS = ("bluetooth", "bt ", "airpods", "headset", "buds")
_WIRED_HINTS = ("wired", "realtek", "speakers", "headphone", "earphone", "usb audio")


def _friendly_name(device: Any) -> str:
    try:
        return str(getattr(device, "FriendlyName", "") or "")
    except Exception:  # noqa: BLE001
        return ""


def _device_id(device: Any) -> str:
    for attr in ("id", "Id", "dev_id"):
        try:
            val = getattr(device, attr, None)
            if val:
                return str(val)
        except Exception:  # noqa: BLE001
            continue
    return ""


def _matches_target(name: str, target_type: str) -> bool:
    lower = (name or "").lower()
    if target_type == "bluetooth":
        return any(h in lower for h in _BLUETOOTH_HINTS)
    if target_type == "wired":
        if any(h in lower for h in _BLUETOOTH_HINTS):
            return False
        return any(h in lower for h in _WIRED_HINTS) or bool(lower)
    return False


def toggle_audio_endpoint(target_type: str) -> str:
    """Set the default multimedia playback device to a wired or Bluetooth endpoint.

    Args:
        target_type: ``\"bluetooth\"`` or ``\"wired\"``.

    Returns:
        Status string for the ReAct observation path.
    """
    kind = str(target_type or "").strip().lower()
    if kind not in ("bluetooth", "wired"):
        return "ERROR: target_type must be 'bluetooth' or 'wired'"

    try:
        from pycaw.pycaw import AudioUtilities
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: pycaw unavailable ({exc})"

    try:
        chosen_id: str | None = None
        chosen_name = ""
        for device in AudioUtilities.GetAllDevices():
            name = _friendly_name(device)
            if not name or not _matches_target(name, kind):
                continue
            device_id = _device_id(device)
            if not device_id:
                continue
            chosen_id = device_id
            chosen_name = name
            break

        if not chosen_id:
            return f"ERROR: no active {kind} audio endpoint found"

        # Initialize IMMDeviceEnumerator path via pycaw, then set default via IPolicyConfig.
        _ = AudioUtilities.GetDeviceEnumerator()
        policy = CoCreateInstance(
            _CLSID_POLICY_CONFIG,
            IPolicyConfig,
            CLSCTX_ALL,
        )
        # eConsole=0, eMultimedia=1, eCommunications=2
        for role in (0, 1, 2):
            policy.SetDefaultEndpoint(chosen_id, role)
        return f"OK: default audio endpoint set to {kind} device '{chosen_name}'"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: toggle_audio_endpoint failed ({exc})"
