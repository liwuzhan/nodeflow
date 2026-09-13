"""Small in-memory SDK substitute used by node integration tests.

This intentionally models only the parameter and port operations exercised by
the tests. Runtime IPC behavior is covered by the software preflight instead.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SHANGHAI_CENTER = (31.2304, 121.4737)


class MockParameterStore:
    """Dictionary-like parameter store matching the SDK's get/set surface."""

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        self._values = dict(values or {})

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value


class MockPort:
    """In-memory latest-value port for deterministic integration tests."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._latest: Any = None

    def set_data(self, data: Any) -> None:
        self._latest = deepcopy(data)

    def recv_latest(self) -> Any:
        return deepcopy(self._latest)

    def send(self, data: Any) -> None:
        self._latest = deepcopy(data)

    def get_last_send_data(self) -> Any:
        return deepcopy(self._latest)


class MockNodeFlowSDK:
    """Minimal SDK facade shared by node integration tests."""

    def __init__(self, params: Mapping[str, Any] | None = None) -> None:
        self.params = MockParameterStore(params)
        self._ports: dict[tuple[str, str], MockPort] = {}

    def create_input_port(self, name: str) -> MockPort:
        return self._ports.setdefault(("input", name), MockPort(name))

    def create_output_port(self, name: str) -> MockPort:
        return self._ports.setdefault(("output", name), MockPort(name))

    def reset(self) -> None:
        self._ports.clear()
