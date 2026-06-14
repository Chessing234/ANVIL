"""Tests for QVAC Edge AI integration (optimizer, runtime, sync, deployment helpers)."""

from __future__ import annotations

import httpx
import numpy as np
import pytest
import respx

from platforms.edge import (
    DEVICE_PROFILES,
    BenchmarkResult,
    DeviceProfile,
    EdgeRuntime,
    LocalSync,
    ModelOptimizer,
    buildx_bake_edge_targets,
    edge_compose_fragment,
    edge_dockerfile,
)


def test_device_profiles_contains_expected_hardware() -> None:
    assert "raspberry_pi_4" in DEVICE_PROFILES
    assert DEVICE_PROFILES["nvidia_jetson_nano"]["gpu"] == "128-core Maxwell"
    assert DEVICE_PROFILES["intel_nuc"]["ram_mb"] == 16384


def test_docker_edge_templates() -> None:
    df = edge_dockerfile()
    assert "linux/arm64" in buildx_bake_edge_targets()
    assert "HEALTHCHECK" in df
    comp = edge_compose_fragment()
    assert "deploy:" in comp
    assert "resources:" in comp


def test_model_optimizer_sizes_and_prune(tmp_path) -> None:
    weights = np.random.randn(512).astype(np.float32)
    src = tmp_path / "base.npz"
    np.savez_compressed(src, weights=weights)
    pruned_path = ModelOptimizer.prune_model(str(src), target_sparsity=0.5)
    q8 = ModelOptimizer.quantize_model(pruned_path, target_bits=8)
    onnx_path = ModelOptimizer.convert_to_onnx(q8)
    assert ModelOptimizer.get_model_size(onnx_path) > 0
    bench = ModelOptimizer.benchmark_model(onnx_path, device="cpu_test")
    assert isinstance(bench, BenchmarkResult)
    assert bench.mean_latency_ms < 2000.0
    assert bench.p95_latency_ms < 2000.0


def test_model_optimizer_pipeline_respects_ram_budget(tmp_path) -> None:
    w = (np.random.randn(128).astype(np.float32) * 0.01).astype(np.float32)
    src = tmp_path / "tiny.npz"
    np.savez_compressed(src, weights=w)
    summary = ModelOptimizer.optimization_pipeline(str(src), device_profile_ram_mb=4096)
    assert "onnx_path" in summary
    assert summary["benchmark"]["mean_latency_ms"] < 2000.0


@pytest.mark.asyncio
async def test_edge_runtime_local_first(tmp_path) -> None:
    db = tmp_path / "edge.sqlite3"
    rt = EdgeRuntime(db_path=str(db))
    profile = DeviceProfile.from_key("raspberry_pi_4")
    await rt.initialize(profile)
    out = await rt.run_agent("triage", {"severity": "LOW"})
    assert out["backend"] == "local_rules"
    incident = await rt.process_incident_local({"id": "inc-1", "severity": "HIGH"})
    assert incident["incident_id"] == "inc-1"
    status = await rt.get_local_status()
    assert status.pending_sync >= 1


@pytest.mark.asyncio
@respx.mock
async def test_edge_runtime_sync_with_central(tmp_path) -> None:
    base = "http://edge-central.test"
    respx.get(base + "/health").mock(return_value=httpx.Response(200, json={"ok": True}))
    respx.post(base + "/edge/ingest").mock(return_value=httpx.Response(200, json={"ok": True}))

    db = tmp_path / "edge2.sqlite3"
    rt = EdgeRuntime(db_path=str(db), central_url=base)
    await rt.initialize(DeviceProfile.from_key("intel_nuc"))
    await rt.process_incident_local({"id": "inc-2", "severity": "MEDIUM"})
    await rt.sync_with_central()
    status = await rt.get_local_status()
    assert status.pending_sync == 0


@pytest.mark.asyncio
async def test_local_sync_conflict_rules() -> None:
    sync = LocalSync(db_path=":memory:")
    merged = await sync.resolve_conflicts(
        {"payload": {"content_title": "local", "progress_score": 10}},
        {"payload": {"content_title": "remote", "progress_score": 99}},
    )
    assert merged["payload"]["content_title"] == "remote"
    assert merged["payload"]["progress_score"] == 10


@pytest.mark.asyncio
@respx.mock
async def test_local_sync_channels(tmp_path) -> None:
    base = "http://sync.test"
    respx.post(base + "/sync/kg").mock(return_value=httpx.Response(200, json={"content_x": 1}))
    respx.post(base + "/sync/lessons").mock(return_value=httpx.Response(200, json={"title": "remote"}))
    respx.post(base + "/sync/progress").mock(return_value=httpx.Response(200, json={}))
    respx.get(base + "/health").mock(return_value=httpx.Response(200))

    db = tmp_path / "sync.sqlite3"
    sync = LocalSync(db_path=str(db), central_url=base)
    await sync.enqueue_knowledge_delta({"content_a": 1, "meta": "x"})
    await sync.upsert_lesson("lesson-1", {"content_body": "hello"})
    await sync.upsert_progress("student-1", {"progress_points": 3})

    kg = await sync.sync_knowledge_graph()
    assert kg.pushed == 1
    lessons = await sync.sync_lessons()
    assert lessons.pushed == 1
    prog = await sync.sync_student_progress()
    assert prog.pushed == 1

    st = await sync.get_sync_status()
    assert st.pending_knowledge == 0
    assert st.pending_lessons == 0
    assert st.pending_progress == 0


def test_edge_package_exports() -> None:
    import platforms.edge as edge

    assert hasattr(edge, "ModelOptimizer")
    assert hasattr(edge, "EdgeRuntime")
    assert hasattr(edge, "LocalSync")
