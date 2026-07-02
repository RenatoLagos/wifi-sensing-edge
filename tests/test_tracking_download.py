from __future__ import annotations

import io
import logging

import pytest

from pc.tracking import _MODEL_SPECS, _download_model, _ensure_pose_model


class _FakeResponse:
    """Stands in for the urlopen response: chunked reads, optional failure."""

    def __init__(self, payload: bytes, *, fail_after_reads: int | None = None):
        self._stream = io.BytesIO(payload)
        self._fail_after_reads = fail_after_reads
        self._reads = 0

    def read(self, size: int = -1) -> bytes:
        if self._fail_after_reads is not None and self._reads >= self._fail_after_reads:
            raise TimeoutError("read timed out")
        self._reads += 1
        return self._stream.read(size)

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def test_download_model_success_is_atomic_and_logs(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="pc.tracking")
    target = tmp_path / "model.task"
    payload = b"x" * (200 * 1024)  # spans multiple chunks
    calls: list[tuple[str, float | None]] = []

    def fake_urlopen(url, timeout=None):
        calls.append((url, timeout))
        return _FakeResponse(payload)

    monkeypatch.setattr("pc.tracking.request.urlopen", fake_urlopen)
    _download_model("https://example.test/model.task", target, timeout_s=5.0)

    assert target.read_bytes() == payload
    assert not (tmp_path / "model.task.part").exists()
    assert calls == [("https://example.test/model.task", 5.0)]
    messages = [record.getMessage() for record in caplog.records]
    assert any("downloading pose model" in message for message in messages)
    assert any(f"({len(payload)} bytes)" in message for message in messages)


def test_download_model_read_failure_leaves_no_files_and_raises(
    tmp_path, monkeypatch
):
    target = tmp_path / "model.task"

    def fake_urlopen(url, timeout=None):
        return _FakeResponse(b"x" * 4096, fail_after_reads=0)

    monkeypatch.setattr("pc.tracking.request.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="example.test/model.task"):
        _download_model("https://example.test/model.task", target, timeout_s=5.0)

    assert list(tmp_path.iterdir()) == []


def test_download_model_connect_failure_leaves_no_files_and_raises(
    tmp_path, monkeypatch
):
    target = tmp_path / "model.task"

    def fake_urlopen(url, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr("pc.tracking.request.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="could not download pose model"):
        _download_model("https://example.test/model.task", target, timeout_s=5.0)

    assert list(tmp_path.iterdir()) == []


def test_download_model_empty_body_leaves_no_files_and_raises(tmp_path, monkeypatch):
    target = tmp_path / "model.task"

    def fake_urlopen(url, timeout=None):
        return _FakeResponse(b"")

    monkeypatch.setattr("pc.tracking.request.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="empty body"):
        _download_model("https://example.test/model.task", target, timeout_s=5.0)

    assert list(tmp_path.iterdir()) == []


def test_ensure_pose_model_redownloads_zero_byte_cached_file(tmp_path, monkeypatch):
    filename, url = _MODEL_SPECS[0]
    cached = tmp_path / filename
    cached.write_bytes(b"")
    requested: list[str] = []

    def fake_urlopen(request_url, timeout=None):
        requested.append(request_url)
        return _FakeResponse(b"model-bytes")

    monkeypatch.setattr("pc.tracking.request.urlopen", fake_urlopen)
    resolved = _ensure_pose_model(
        model_complexity=0, model_path=None, models_dir=tmp_path
    )

    assert resolved == cached
    assert cached.read_bytes() == b"model-bytes"
    assert requested == [url]


def test_ensure_pose_model_uses_valid_cache_without_network(tmp_path, monkeypatch):
    filename, _url = _MODEL_SPECS[0]
    cached = tmp_path / filename
    cached.write_bytes(b"cached-model")

    def fake_urlopen(url, timeout=None):
        raise AssertionError("urlopen must not be called for a valid cached model")

    monkeypatch.setattr("pc.tracking.request.urlopen", fake_urlopen)
    resolved = _ensure_pose_model(
        model_complexity=0, model_path=None, models_dir=tmp_path
    )

    assert resolved == cached
    assert cached.read_bytes() == b"cached-model"


def test_ensure_pose_model_passes_timeout_through(tmp_path, monkeypatch):
    _filename, url = _MODEL_SPECS[0]
    timeouts: list[float | None] = []

    def fake_urlopen(request_url, timeout=None):
        assert request_url == url
        timeouts.append(timeout)
        return _FakeResponse(b"model-bytes")

    monkeypatch.setattr("pc.tracking.request.urlopen", fake_urlopen)
    _ensure_pose_model(
        model_complexity=0,
        model_path=None,
        download_timeout_s=7.5,
        models_dir=tmp_path,
    )

    assert timeouts == [7.5]
