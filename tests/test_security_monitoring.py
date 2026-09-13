import json

import pytest

from natureai_next.server.security_monitoring import (
    WazuhJsonlSink,
    verify_collected_package_integrity,
)


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []

    def emit_security_event(self, event: dict[str, str]) -> None:
        self.events.append(event)


def _verify(observed: str, sink: RecordingSink | WazuhJsonlSink | None = None) -> bool:
    return verify_collected_package_integrity(
        expected_sha256="a" * 64,
        observed_sha256=observed,
        request_id="req-001",
        package_id="pkg-001",
        broadcast_id="broadcast:req-001:aaaaaaaaaaaaaaaa",
        collector_id="fieldora-importer",
        signing_key_id="bastion-key-1",
        package_class="scientific-data",
        artifact_id="dataset-42",
        version="2026.09",
        provenance="approved-source",
        signature_verified=True,
        sink=sink,
    )


def test_matching_digest_is_accepted_without_security_alert() -> None:
    sink = RecordingSink()
    assert _verify("a" * 64, sink)
    assert sink.events == []


def test_digest_discrepancy_fails_closed_and_alerts_monitoring_sink() -> None:
    sink = RecordingSink()
    assert not _verify("b" * 64, sink)
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event["event_type"] == "package_integrity_mismatch"
    assert event["severity"] == "high"
    assert event["expected_sha256"] == "a" * 64
    assert event["observed_sha256"] == "b" * 64
    assert event["signing_key_id"] == "bastion-key-1"
    assert "path" not in event
    assert "content" not in event


def test_wazuh_sink_writes_single_line_bounded_json(tmp_path) -> None:
    log = tmp_path / "fieldora-security.jsonl"
    assert not _verify("b" * 64, WazuhJsonlSink(log))
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["fieldora"]["component"] == "trusted-side"
    assert event["fieldora"]["event_type"] == "package_integrity_mismatch"
    assert event["fieldora"]["expected_sha256"] == "a" * 64
    assert "path" not in event["fieldora"]
    assert "content" not in event["fieldora"]


def test_wazuh_sink_requires_precreated_event_directory(tmp_path) -> None:
    sink = WazuhJsonlSink(tmp_path / "missing" / "events.jsonl")
    with pytest.raises(FileNotFoundError):
        sink.emit_security_event({"event_type": "test"})
