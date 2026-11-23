"""Asynchronous client for a direct Heiman Wi-Fi switch."""

from dataclasses import dataclass
import json
import re
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout
from yarl import URL

_SCHEMA = "heiman_wifi_v1"
_SWITCH_TYPES = {"sw", "switch", "smart_switch"}
_TIMEOUT = ClientTimeout(total=5)
_MAC_PATTERN = re.compile(r"[0-9a-f]{12}")


class HeimanError(Exception):
    """A request failed or the switch returned an invalid response."""


class UnsupportedDevice(HeimanError):
    """The endpoint does not identify a supported Heiman switch."""


def _mac(value: Any) -> str | None:
    if isinstance(value, str):
        compact = value.strip().lower().replace(":", "").replace("-", "")
        if _MAC_PATTERN.fullmatch(compact) and compact != "000000000000":
            return compact
    return None


def _text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        if isinstance(value := data.get(key), str) and value.strip():
            return value.strip()
    return None


@dataclass(frozen=True, slots=True)
class SwitchInfo:
    """Identity and metadata advertised by the switch."""

    mac: str
    name: str
    model: str | None
    firmware: str | None
    endpoint_id: str | None


class HeimanSwitchClient:
    """Read and control one switch using an injected HTTP session."""

    def __init__(self, session: ClientSession, host: str, port: int) -> None:
        """Store the local HTTP address and session."""
        self._session = session
        self._url = URL.build(scheme="http", host=host, port=port)

    async def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with self._session.request(
                method,
                self._url / path,
                json=payload,
                timeout=_TIMEOUT,
                allow_redirects=False,
            ) as response:
                if not 200 <= response.status < 300:
                    raise HeimanError(f"/{path} returned HTTP {response.status}")
                body = await response.read()
        except (ClientError, TimeoutError) as err:
            raise HeimanError(f"Request to /{path} failed") from err

        if method == "POST" and not body.strip():
            return {}

        try:
            data = json.loads(body)
        except (ValueError, RecursionError) as err:
            raise HeimanError(f"/{path} returned invalid JSON") from err
        if not isinstance(data, dict):
            raise HeimanError(f"/{path} must return a JSON object")
        return data

    async def get_info(self) -> SwitchInfo:
        """Read the switch identity and check the protocol version."""
        data = await self._request("GET", "info")
        mac = _mac(data.get("mac")) or _mac(data.get("macAddress"))
        device_type = _text(data, "deviceType", "type", "typeCode")
        if (
            data.get("schema") != _SCHEMA
            or mac is None
            or device_type is None
            or device_type.lower() not in _SWITCH_TYPES
        ):
            raise UnsupportedDevice("Expected a heiman_wifi_v1 switch with a MAC")

        model = _text(data, "model", "productModel")
        return SwitchInfo(
            mac=mac,
            name=_text(data, "name", "deviceName") or model or "Heiman Wi-Fi Switch",
            model=model,
            firmware=_text(data, "firmwareVersion", "version"),
            endpoint_id=_text(data, "id", "device_id"),
        )

    async def get_power(self, info: SwitchInfo) -> bool:
        """Read the root switch's Boolean power state."""
        data = await self._request("GET", "state")
        properties = data.get("properties", data)
        if isinstance(properties, dict) and isinstance(
            power := properties.get("power"), bool
        ):
            return power

        devices = data.get("devices")
        if isinstance(devices, list):
            for device in devices:
                if not isinstance(device, dict):
                    continue
                endpoint = _text(device, "id", "device_id", "mac")
                if endpoint is None or (
                    endpoint != info.endpoint_id and _mac(endpoint) != info.mac
                ):
                    continue
                properties = device.get("properties")
                if isinstance(properties, dict) and isinstance(
                    power := properties.get("power"), bool
                ):
                    return power

        raise HeimanError("/state has no Boolean power value for the root switch")

    async def set_power(self, is_on: bool) -> None:
        """Send an explicit Boolean power command to the direct switch."""
        result = await self._request(
            "POST", "control", {"property": "power", "value": is_on}
        )
        if result.get("ok") is False or result.get("success") is False:
            raise HeimanError("The switch rejected the power command")
