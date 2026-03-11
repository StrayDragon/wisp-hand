from __future__ import annotations

import asyncio
import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from wisp_hand.capture import CaptureArtifactStore
from wisp_hand.config import load_runtime_config
from wisp_hand.errors import WispHandError
from wisp_hand.runtime import WispHandRuntime
from wisp_hand.server import WispHandServer


class FakeOllamaTransport:
    def __init__(self, response: dict[str, Any] | None = None, *, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response = response or {"response": "default"}
        self.error = error

    def __call__(self, *, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.calls.append({"url": url, "payload": payload, "timeout": timeout})
        if self.error is not None:
            raise self.error
        return self.response


def write_config(
    path: Path,
    *,
    vision_mode: str,
    max_image_edge: int = 1024,
) -> None:
    path.write_text(
        f"""
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"
capture_dir = "./state/captures"

[vision]
mode = "{vision_mode}"
model = "llava"
base_url = "http://127.0.0.1:11434"
timeout_seconds = 2.5
max_image_edge = {max_image_edge}
max_tokens = 128
max_concurrency = 1
""".strip(),
        encoding="utf-8",
    )


def build_runtime(
    tmp_path: Path,
    *,
    vision_mode: str = "assist",
    transport: FakeOllamaTransport | None = None,
    max_image_edge: int = 1024,
) -> tuple[WispHandRuntime, FakeOllamaTransport]:
    write_config(tmp_path / "config.toml", vision_mode=vision_mode, max_image_edge=max_image_edge)
    fake_transport = transport or FakeOllamaTransport()
    runtime = WispHandRuntime(
        config=load_runtime_config(tmp_path / "config.toml"),
        ollama_transport=fake_transport,
    )
    return runtime, fake_transport


def encode_png(width: int, height: int, *, color: tuple[int, int, int]) -> str:
    image = Image.new("RGB", (width, height), color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def write_capture(capture_dir: Path, *, capture_id: str, width: int, height: int, color: tuple[int, int, int]) -> None:
    image_path = capture_dir / f"{capture_id}.png"
    metadata_path = capture_dir / f"{capture_id}.json"
    Image.new("RGB", (width, height), color=color).save(image_path, format="PNG")
    CaptureArtifactStore(base_dir=capture_dir).write_metadata(
        metadata_path=metadata_path,
        payload={
            "capture_id": capture_id,
            "scope": {
                "type": "region",
                "target": {"x": 0, "y": 0, "width": width, "height": height},
                "coordinate_space": {"origin": "scope", "units": "px", "relative_to": "region"},
                "constraints": {"input_relative": True},
            },
            "target": "scope",
            "width": width,
            "height": height,
            "mime_type": "image/png",
            "created_at": "2026-03-09T00:00:00+00:00",
            "source_bounds": {"x": 0, "y": 0, "width": width, "height": height},
            "source_coordinate_space": "layout_px",
            "image_coordinate_space": "image_px",
            "pixel_ratio_x": 1.0,
            "pixel_ratio_y": 1.0,
            "mapping": {"kind": "single", "monitors": []},
            "downscale": None,
        },
    )


def test_vision_disabled_mode_returns_structured_error(tmp_path: Path) -> None:
    runtime, _ = build_runtime(tmp_path, vision_mode="disabled")
    server = WispHandServer(runtime)

    async def run_test() -> None:
        result = await server.mcp.call_tool(
            "wisp_hand.vision.describe",
            {"inline_image": encode_png(4, 4, color=(1, 2, 3))},
        )
        assert result.isError is True
        assert result.structuredContent["code"] == "capability_unavailable"

    asyncio.run(run_test())


def test_vision_provider_unavailable_and_timeout_are_degraded(tmp_path: Path) -> None:
    runtime, _ = build_runtime(tmp_path, transport=FakeOllamaTransport(error=OSError("connection refused")))
    with pytest.raises(WispHandError) as unavailable_exc:
        runtime.vision_describe(inline_image=encode_png(4, 4, color=(1, 2, 3)))
    assert unavailable_exc.value.code == "capability_unavailable"

    runtime, _ = build_runtime(tmp_path, transport=FakeOllamaTransport(error=TimeoutError("timed out")))
    with pytest.raises(WispHandError) as timeout_exc:
        runtime.vision_describe(inline_image=encode_png(4, 4, color=(1, 2, 3)))
    assert timeout_exc.value.code == "capability_unavailable"


def test_vision_preprocesses_large_images_and_returns_describe_payload(tmp_path: Path) -> None:
    transport = FakeOllamaTransport(response={"response": "A large red banner"})
    runtime, fake_transport = build_runtime(tmp_path, transport=transport, max_image_edge=1000)

    result = runtime.vision_describe(
        inline_image=encode_png(2000, 1000, color=(255, 0, 0)),
        prompt="Describe it.",
    )

    assert result["answer"] == "A large red banner"
    assert result["input_source"] == "inline"
    assert result["image_width"] == 2000
    assert result["image_height"] == 1000
    assert result["processed_width"] == 1000
    assert result["processed_height"] == 500

    payload = fake_transport.calls[0]["payload"]
    sent_image = Image.open(BytesIO(base64.b64decode(payload["images"][0])))
    assert sent_image.size == (1000, 500)


def test_vision_locate_uses_capture_artifacts_and_records_audit_fields(tmp_path: Path) -> None:
    transport = FakeOllamaTransport(
        response={
            "response": json.dumps(
                {
                    "candidates": [
                        {
                            "x": 10,
                            "y": 20,
                            "width": 30,
                            "height": 40,
                            "confidence": 0.8,
                            "reason": "matches the button label",
                        }
                    ]
                }
            )
        }
    )
    runtime, _ = build_runtime(tmp_path, transport=transport)
    write_capture(runtime.config.paths.capture_dir, capture_id="cap-1", width=100, height=80, color=(0, 0, 0))

    locate = runtime.vision_locate(capture_id="cap-1", target="submit button")
    assert locate["capture_id"] == "cap-1"
    assert locate["target"] == "submit button"
    expected_candidates = [
        {
            "x": 10,
            "y": 20,
            "width": 30,
            "height": 40,
            "confidence": 0.8,
            "reason": "matches the button label",
        }
    ]
    assert locate["candidates_scope"] == expected_candidates
    assert "candidates_image" not in locate

    locate_both = runtime.vision_locate(capture_id="cap-1", target="submit button", space="both")
    assert locate_both["candidates_image"] == expected_candidates
    assert locate_both["candidates_scope"] == expected_candidates

    audit_path = runtime.config.paths.audit_file
    assert audit_path is not None and audit_path.exists()
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    locate_entry = next(entry for entry in entries if entry["tool_name"] == "wisp_hand.vision.locate")
    assert locate_entry["input_source"] == "capture"
    assert locate_entry["capture_id"] == "cap-1"
    assert locate_entry["provider"] == "ollama"
    assert locate_entry["model"] == "llava"


def test_vision_locate_limits_candidates_by_default(tmp_path: Path) -> None:
    transport = FakeOllamaTransport(
        response={
            "response": json.dumps(
                {
                    "candidates": [
                        {"x": 1, "y": 2, "width": 3, "height": 4, "confidence": 0.9, "reason": "a"},
                        {"x": 5, "y": 6, "width": 7, "height": 8, "confidence": 0.8, "reason": "b"},
                        {"x": 9, "y": 10, "width": 11, "height": 12, "confidence": 0.7, "reason": "c"},
                        {"x": 13, "y": 14, "width": 15, "height": 16, "confidence": 0.6, "reason": "d"},
                        {"x": 17, "y": 18, "width": 19, "height": 20, "confidence": 0.5, "reason": "e"},
                    ]
                }
            )
        }
    )
    runtime, _ = build_runtime(tmp_path, transport=transport)
    write_capture(runtime.config.paths.capture_dir, capture_id="cap-limit", width=100, height=80, color=(0, 0, 0))

    default_limited = runtime.vision_locate(capture_id="cap-limit", target="target")
    assert len(default_limited["candidates_scope"]) == 3

    explicit = runtime.vision_locate(capture_id="cap-limit", target="target", limit=5)
    assert len(explicit["candidates_scope"]) == 5


def test_vision_describe_supports_capture_and_inline_sources(tmp_path: Path) -> None:
    transport = FakeOllamaTransport(response={"response": "A compact UI screenshot"})
    runtime, _ = build_runtime(tmp_path, transport=transport)
    write_capture(runtime.config.paths.capture_dir, capture_id="cap-2", width=32, height=24, color=(10, 20, 30))

    from_capture = runtime.vision_describe(capture_id="cap-2")
    from_inline = runtime.vision_describe(inline_image=encode_png(16, 12, color=(30, 20, 10)))

    assert from_capture["input_source"] == "capture"
    assert from_capture["capture_id"] == "cap-2"
    assert from_inline["input_source"] == "inline"
    assert from_inline["capture_id"] is None
