from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from wisp_hand.audit import AuditLogger
from wisp_hand.capture import CaptureArtifactStore, CaptureDiffEngine
from wisp_hand.config import load_runtime_config
from wisp_hand.errors import WispHandError
from wisp_hand.runtime import WispHandRuntime


def write_config(path: Path, contents: str) -> Path:
    path.write_text(contents.strip() + "\n", encoding="utf-8")
    return path


def write_capture_pair(store: CaptureArtifactStore, *, created_at: datetime) -> str:
    capture_id, image_path, metadata_path = store.allocate()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(image_path, format="PNG")
    store.write_metadata(
        metadata_path=metadata_path,
        payload={
            "capture_id": capture_id,
            "path": str(image_path),
            "created_at": created_at.isoformat(),
        },
    )
    return capture_id


def test_capture_retention_deletes_png_json_as_pair(tmp_path: Path) -> None:
    store = CaptureArtifactStore(base_dir=tmp_path)
    capture_id = write_capture_pair(store, created_at=datetime.now(UTC) - timedelta(days=10))

    summary = store.enforce_retention(
        max_age_seconds=1,
        max_total_bytes=None,
        now=datetime.now(UTC),
    )
    assert capture_id in summary["removed_ids"]
    assert not (tmp_path / f"{capture_id}.png").exists()
    assert not (tmp_path / f"{capture_id}.json").exists()


def test_capture_diff_errors_after_artifact_cleanup(tmp_path: Path) -> None:
    store = CaptureArtifactStore(base_dir=tmp_path)
    capture_id = write_capture_pair(store, created_at=datetime.now(UTC))

    # Simulate retention cleanup removing the capture pair.
    (tmp_path / f"{capture_id}.png").unlink()
    (tmp_path / f"{capture_id}.json").unlink()

    engine = CaptureDiffEngine(artifact_store=store)
    with pytest.raises(WispHandError) as exc:
        engine.diff(left_capture_id=capture_id, right_capture_id=capture_id)
    assert exc.value.code == "capability_unavailable"


def test_audit_log_rotation_keeps_bounded_files(tmp_path: Path) -> None:
    audit_file = tmp_path / "audit.jsonl"
    audit_file.write_text("x" * 256, encoding="utf-8")

    logger = AuditLogger(audit_file=audit_file, max_bytes=64, backup_count=2)
    logger.record(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "tool_name": "wisp_hand.capabilities",
            "status": "ok",
            "latency_ms": 0,
        }
    )

    assert audit_file.exists()
    assert (tmp_path / "audit.jsonl.1").exists()


def test_restart_old_session_is_not_accepted(tmp_path: Path) -> None:
    config = load_runtime_config(
        write_config(
            tmp_path / "config.toml",
            """
[server]
transport = "stdio"

[paths]
state_dir = "./state"
audit_file = "./state/audit.jsonl"
runtime_log_file = "./state/runtime.jsonl"

[dependencies]
required_binaries = []
optional_binaries = []
""",
        )
    )

    runtime1 = WispHandRuntime(config=config)
    session = runtime1.open_session(scope_type="desktop", scope_target=None, armed=False, dry_run=True, ttl_seconds=60)

    runtime2 = WispHandRuntime(config=config)
    with pytest.raises(WispHandError) as exc:
        runtime2.wait(session_id=session["session_id"], duration_ms=0)
    assert exc.value.code == "session_not_found"

