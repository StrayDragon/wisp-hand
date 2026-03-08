from __future__ import annotations

import os
import shutil
import socket
import struct
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from wisp_hand.command import CommandResult, CommandRunner
from wisp_hand.errors import WispHandError
from wisp_hand.models import PointerButton
from wisp_hand.policy import normalize_key_name

_BUTTON_CODES: dict[PointerButton, int] = {
    "left": 0x110,
    "right": 0x111,
    "middle": 0x112,
}
_VERTICAL_AXIS = 0
_HORIZONTAL_AXIS = 1


class InputBackend(Protocol):
    def move_pointer(self, *, x: int, y: int, desktop_bounds: dict[str, int]) -> None: ...

    def click_pointer(
        self,
        *,
        x: int,
        y: int,
        button: PointerButton,
        desktop_bounds: dict[str, int],
    ) -> None: ...

    def drag_pointer(
        self,
        *,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: PointerButton,
        desktop_bounds: dict[str, int],
    ) -> None: ...

    def scroll_pointer(
        self,
        *,
        x: int,
        y: int,
        delta_x: int,
        delta_y: int,
        desktop_bounds: dict[str, int],
    ) -> None: ...

    def type_text(self, *, text: str) -> None: ...

    def press_keys(self, *, keys: Sequence[str]) -> None: ...


class WaylandInputBackend:
    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        binary_resolver: Callable[[str], str | None] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._pointer = WlrVirtualPointerBackend(env=env)
        self._keyboard = WtypeKeyboardBackend(
            runner=runner,
            binary_resolver=binary_resolver,
        )

    def move_pointer(self, *, x: int, y: int, desktop_bounds: dict[str, int]) -> None:
        self._pointer.move_pointer(x=x, y=y, desktop_bounds=desktop_bounds)

    def click_pointer(
        self,
        *,
        x: int,
        y: int,
        button: PointerButton,
        desktop_bounds: dict[str, int],
    ) -> None:
        self._pointer.click_pointer(x=x, y=y, button=button, desktop_bounds=desktop_bounds)

    def drag_pointer(
        self,
        *,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: PointerButton,
        desktop_bounds: dict[str, int],
    ) -> None:
        self._pointer.drag_pointer(
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
            button=button,
            desktop_bounds=desktop_bounds,
        )

    def scroll_pointer(
        self,
        *,
        x: int,
        y: int,
        delta_x: int,
        delta_y: int,
        desktop_bounds: dict[str, int],
    ) -> None:
        self._pointer.scroll_pointer(
            x=x,
            y=y,
            delta_x=delta_x,
            delta_y=delta_y,
            desktop_bounds=desktop_bounds,
        )

    def type_text(self, *, text: str) -> None:
        self._keyboard.type_text(text=text)

    def press_keys(self, *, keys: Sequence[str]) -> None:
        self._keyboard.press_keys(keys=keys)


class WtypeKeyboardBackend:
    _MODIFIER_KEYS = {"alt", "ctrl", "shift", "super"}

    def __init__(
        self,
        *,
        runner: CommandRunner | None = None,
        binary_resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        self._runner = runner or CommandRunner()
        self._binary_resolver = binary_resolver or shutil.which

    def type_text(self, *, text: str) -> None:
        self._ensure_binary_available()
        self._run(["wtype", text])

    def press_keys(self, *, keys: Sequence[str]) -> None:
        self._ensure_binary_available()

        modifiers: list[str] = []
        regular_keys: list[str] = []
        for raw_key in keys:
            key = normalize_key_name(raw_key)
            if key in self._MODIFIER_KEYS:
                modifiers.append(key)
            else:
                regular_keys.append(key)

        if not regular_keys and not modifiers:
            raise WispHandError("invalid_parameters", "keys must include at least one key")

        command = ["wtype"]
        for modifier in modifiers:
            command.extend(["-M", modifier])
        for key in regular_keys:
            command.extend(["-k", key])
        for modifier in reversed(modifiers):
            command.extend(["-m", modifier])

        self._run(command)

    def _ensure_binary_available(self) -> None:
        if self._binary_resolver("wtype") is None:
            raise WispHandError(
                "dependency_missing",
                "Required binary is missing",
                {"binary": "wtype"},
            )

    def _run(self, args: list[str]) -> None:
        try:
            result = self._runner(args)
        except FileNotFoundError as exc:  # pragma: no cover - defensive wrapper
            raise WispHandError(
                "dependency_missing",
                "Required binary is missing",
                {"binary": args[0]},
            ) from exc

        _ensure_command_succeeded(result)


class WlrVirtualPointerBackend:
    def __init__(self, *, env: Mapping[str, str] | None = None) -> None:
        self._env = env if env is not None else os.environ

    def move_pointer(self, *, x: int, y: int, desktop_bounds: dict[str, int]) -> None:
        with _VirtualPointerSession(env=self._env) as session:
            session.move(x=x, y=y, desktop_bounds=desktop_bounds)

    def click_pointer(
        self,
        *,
        x: int,
        y: int,
        button: PointerButton,
        desktop_bounds: dict[str, int],
    ) -> None:
        with _VirtualPointerSession(env=self._env) as session:
            session.click(x=x, y=y, button=button, desktop_bounds=desktop_bounds)

    def drag_pointer(
        self,
        *,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: PointerButton,
        desktop_bounds: dict[str, int],
    ) -> None:
        with _VirtualPointerSession(env=self._env) as session:
            session.drag(
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
                button=button,
                desktop_bounds=desktop_bounds,
            )

    def scroll_pointer(
        self,
        *,
        x: int,
        y: int,
        delta_x: int,
        delta_y: int,
        desktop_bounds: dict[str, int],
    ) -> None:
        with _VirtualPointerSession(env=self._env) as session:
            session.scroll(
                x=x,
                y=y,
                delta_x=delta_x,
                delta_y=delta_y,
                desktop_bounds=desktop_bounds,
            )


class _VirtualPointerSession:
    def __init__(self, *, env: Mapping[str, str]) -> None:
        self._env = env
        self._sock: socket.socket | None = None
        self._wl_registry_id = 2
        self._callback_id = 3
        self._manager_id = 4
        self._pointer_id = 5
        self._manager_bound = False

    def __enter__(self) -> _VirtualPointerSession:
        self._sock = self._connect()
        self._send_message(1, 1, struct.pack("<I", self._wl_registry_id))
        self._send_message(1, 0, struct.pack("<I", self._callback_id))
        self._drain_events()
        if not self._manager_bound:
            raise WispHandError(
                "capability_unavailable",
                "zwlr virtual pointer protocol is unavailable",
                {},
            )
        self._send_message(self._manager_id, 0, struct.pack("<II", 0, self._pointer_id))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def move(self, *, x: int, y: int, desktop_bounds: dict[str, int]) -> None:
        self._motion_absolute(x=x, y=y, desktop_bounds=desktop_bounds)
        self._sync()

    def click(
        self,
        *,
        x: int,
        y: int,
        button: PointerButton,
        desktop_bounds: dict[str, int],
    ) -> None:
        self._motion_absolute(x=x, y=y, desktop_bounds=desktop_bounds)
        self._button(button=button, pressed=True)
        self._button(button=button, pressed=False)
        self._sync()

    def drag(
        self,
        *,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        button: PointerButton,
        desktop_bounds: dict[str, int],
    ) -> None:
        self._motion_absolute(x=start_x, y=start_y, desktop_bounds=desktop_bounds)
        self._button(button=button, pressed=True)

        steps = 20
        for index in range(1, steps + 1):
            x = round(start_x + (end_x - start_x) * index / steps)
            y = round(start_y + (end_y - start_y) * index / steps)
            self._motion_absolute(x=x, y=y, desktop_bounds=desktop_bounds)
            time.sleep(0.01)

        self._button(button=button, pressed=False)
        self._sync()

    def scroll(
        self,
        *,
        x: int,
        y: int,
        delta_x: int,
        delta_y: int,
        desktop_bounds: dict[str, int],
    ) -> None:
        self._motion_absolute(x=x, y=y, desktop_bounds=desktop_bounds)
        if delta_x:
            self._axis(axis=_HORIZONTAL_AXIS, steps=delta_x)
        if delta_y:
            self._axis(axis=_VERTICAL_AXIS, steps=delta_y)
        self._frame()
        self._sync()

    def _connect(self) -> socket.socket:
        runtime_dir = self._env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        wayland_display = self._env.get("WAYLAND_DISPLAY", "wayland-0")
        socket_path = os.path.join(runtime_dir, wayland_display)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(socket_path)
        except OSError as exc:
            sock.close()
            raise WispHandError(
                "capability_unavailable",
                "Failed to connect to Wayland display",
                {"socket_path": socket_path, "reason": str(exc)},
            ) from exc
        return sock

    def _motion_absolute(self, *, x: int, y: int, desktop_bounds: dict[str, int]) -> None:
        normalized_x = x - desktop_bounds["x"]
        normalized_y = y - desktop_bounds["y"]
        payload = struct.pack(
            "<IIIII",
            _millis(),
            normalized_x,
            normalized_y,
            desktop_bounds["width"],
            desktop_bounds["height"],
        )
        self._send_message(self._pointer_id, 1, payload)
        self._frame()

    def _button(self, *, button: PointerButton, pressed: bool) -> None:
        payload = struct.pack(
            "<III",
            _millis(),
            _BUTTON_CODES[button],
            1 if pressed else 0,
        )
        self._send_message(self._pointer_id, 2, payload)
        self._frame()

    def _axis(self, *, axis: int, steps: int) -> None:
        payload = struct.pack(
            "<IIi",
            _millis(),
            axis,
            _to_fixed(steps * 15.0),
        )
        self._send_message(self._pointer_id, 3, payload)

    def _frame(self) -> None:
        self._send_message(self._pointer_id, 4, b"")

    def _sync(self) -> None:
        self._send_message(1, 0, struct.pack("<I", self._callback_id))
        self._drain_events()

    def _drain_events(self) -> None:
        assert self._sock is not None
        self._sock.setblocking(False)
        callback_done = False
        try:
            while True:
                try:
                    header = _recv_exactly(self._sock, 8)
                except BlockingIOError:
                    if callback_done:
                        break
                    time.sleep(0.001)
                    continue

                if len(header) < 8:
                    break

                object_id, size_and_opcode = struct.unpack("<II", header)
                size = (size_and_opcode >> 16) & 0xFFFF
                opcode = size_and_opcode & 0xFFFF
                payload = _recv_exactly(self._sock, size - 8)
                if len(payload) < size - 8:
                    break

                if object_id == self._wl_registry_id and opcode == 0:
                    global_name = struct.unpack("<I", payload[:4])[0]
                    string_size = struct.unpack("<I", payload[4:8])[0]
                    interface_name = payload[8 : 8 + string_size - 1].decode("utf-8")
                    version = struct.unpack("<I", payload[-4:])[0]
                    if interface_name == "zwlr_virtual_pointer_manager_v1":
                        bind_payload = (
                            struct.pack("<I", global_name)
                            + _encode_wayland_string(interface_name)
                            + struct.pack("<II", version, self._manager_id)
                        )
                        self._send_message(self._wl_registry_id, 0, bind_payload)
                        self._manager_bound = True
                elif object_id == self._callback_id and opcode == 0:
                    callback_done = True
        finally:
            self._sock.setblocking(True)

    def _send_message(self, object_id: int, opcode: int, payload: bytes) -> None:
        if self._sock is None:
            raise WispHandError("internal_error", "Virtual pointer session is not connected", {})
        message = struct.pack("<IHH", object_id, opcode, 8 + len(payload)) + payload
        try:
            self._sock.sendall(message)
        except OSError as exc:
            raise WispHandError(
                "capability_unavailable",
                "Wayland virtual pointer dispatch failed",
                {"reason": str(exc)},
            ) from exc


def _ensure_command_succeeded(result: CommandResult) -> None:
    if result.returncode == 0:
        return
    raise WispHandError(
        "capability_unavailable",
        "Command execution failed",
        {
            "command": result.args,
            "stderr": result.stderr,
            "returncode": result.returncode,
        },
    )


def _encode_wayland_string(value: str) -> bytes:
    raw = value.encode("utf-8") + b"\x00"
    padding = b"\x00" * ((4 - (len(raw) % 4)) % 4)
    return struct.pack("<I", len(raw)) + raw + padding


def _millis() -> int:
    return int(time.time() * 1000) & 0xFFFFFFFF


def _to_fixed(value: float) -> int:
    return int(round(value * 256))


def _recv_exactly(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        try:
            chunk = sock.recv(remaining)
        except BlockingIOError:
            time.sleep(0.001)
            continue
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
