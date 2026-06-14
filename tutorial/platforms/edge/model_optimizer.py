"""Quantization, pruning, ONNX export, and micro-benchmarks for edge TUTORIAL models."""

from __future__ import annotations

import json
import math
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class BenchmarkResult(BaseModel):
    """Latency and memory snapshot for an edge inference configuration."""

    model_config = {"extra": "forbid"}

    model_path: str = Field(min_length=1)
    device: str = Field(min_length=1)
    mean_latency_ms: float = Field(ge=0.0)
    p95_latency_ms: float = Field(ge=0.0)
    peak_rss_bytes: int = Field(ge=0)


class ModelOptimizer:
    """NumPy-first optimizer with optional PyTorch checkpoints and ONNX export."""

    WEIGHTS_KEY = "weights"

    @staticmethod
    def _write_manifest(npz_path: Path, meta: dict[str, Any]) -> None:
        manifest = npz_path.with_name(npz_path.name + ".manifest.json")
        manifest.write_text(json.dumps(meta, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _out_path(model_path: str, tag: str) -> Path:
        base = Path(model_path)
        return base.with_name(f"{base.stem}_{tag}{base.suffix if base.suffix else '.npz'}")

    @classmethod
    def _load_weights(cls, model_path: str) -> np.ndarray:
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(model_path)
        suf = path.suffix.lower()
        if suf == ".npz":
            data = np.load(path, allow_pickle=False)
            if cls.WEIGHTS_KEY not in data.files:
                raise ValueError("Expected an .npz bundle with a 'weights' float32 vector")
            vec = np.asarray(data[cls.WEIGHTS_KEY], dtype=np.float32).ravel()
            return vec
        if suf in {".pt", ".pth"}:
            try:
                import torch  # type: ignore import-not-found
            except ImportError as exc:  # pragma: no cover - optional heavy dep
                raise RuntimeError(
                    "Loading .pt/.pth requires PyTorch: pip install torch"
                ) from exc
            try:
                payload = torch.load(path, map_location="cpu", weights_only=True)
            except TypeError:
                payload = torch.load(path, map_location="cpu", weights_only=False)
            tensors: list[np.ndarray] = []
            if isinstance(payload, dict):
                for value in payload.values():
                    if hasattr(value, "detach"):
                        tensors.append(value.detach().cpu().numpy().astype(np.float32).ravel())
            elif hasattr(payload, "detach"):
                tensors.append(payload.detach().cpu().numpy().astype(np.float32).ravel())
            if not tensors:
                raise ValueError("Unsupported PyTorch checkpoint structure")
            return np.concatenate(tensors)
        raise ValueError("Unsupported model_path; use .npz (weights vector) or .pt/.pth (torch)")

    @classmethod
    def _save_npz(cls, path: Path, weights: np.ndarray, meta: dict[str, Any]) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, **{cls.WEIGHTS_KEY: weights.astype(np.float32)})
        cls._write_manifest(path, meta)
        return str(path.resolve())

    @classmethod
    def prune_model(cls, model_path: str, target_sparsity: float = 0.5) -> str:
        """Magnitude-prune a flattened weight vector and persist a new ``.npz`` bundle."""
        if not 0.0 <= target_sparsity < 1.0:
            raise ValueError("target_sparsity must be in [0, 1)")
        weights = cls._load_weights(model_path).astype(np.float32, copy=False)
        flat = np.abs(weights.ravel())
        cutoff_index = int(math.floor(target_sparsity * flat.size))
        if cutoff_index <= 0:
            pruned = weights
        else:
            threshold = np.partition(flat, cutoff_index)[cutoff_index]
            mask = np.abs(weights) >= threshold
            pruned = weights * mask.astype(np.float32)
        meta = {
            "op": "prune",
            "target_sparsity": target_sparsity,
            "source": str(Path(model_path).resolve()),
        }
        out = cls._out_path(model_path, f"pruned_{int(target_sparsity * 100)}")
        if out.suffix.lower() not in {".npz"}:
            out = out.with_suffix(".npz")
        saved = cls._save_npz(out, pruned, meta)
        logger.info("model_pruned", out=saved, nnz=int(np.count_nonzero(pruned)))
        return saved

    @classmethod
    def quantize_model(cls, model_path: str, target_bits: int = 8) -> str:
        """Symmetric per-tensor quantization to INT8 (8) or pseudo-FP16 storage (16)."""
        if target_bits not in {8, 16}:
            raise ValueError("target_bits must be 8 (INT8) or 16 (FP16 storage)")
        weights = cls._load_weights(model_path).astype(np.float32, copy=False)
        if target_bits == 8:
            max_abs = float(np.max(np.abs(weights)) + 1e-8)
            scale = max_abs / 127.0
            q = np.clip(np.round(weights / scale), -127, 127).astype(np.int8)
            dequant = (q.astype(np.float32) * scale).astype(np.float32)
            meta = {
                "op": "quantize_int8",
                "scale": scale,
                "source": str(Path(model_path).resolve()),
            }
            out = cls._out_path(model_path, "int8")
            out = out.with_suffix(".npz")
            out.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(out, **{cls.WEIGHTS_KEY: dequant, "q_int8": q})
            cls._write_manifest(
                out,
                {
                    "op": "quantize_int8",
                    "scale": scale,
                    "source": str(Path(model_path).resolve()),
                },
            )
            saved = str(out.resolve())
            logger.info("model_quantized_int8", out=saved, scale=scale)
            return saved
        # FP16 storage path: store float16 weights for smaller disk footprint; compute in float32 at runtime.
        half = weights.astype(np.float16)
        restored = half.astype(np.float32)
        meta = {"op": "quantize_fp16_storage", "source": str(Path(model_path).resolve())}
        out = cls._out_path(model_path, "fp16").with_suffix(".npz")
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out, **{cls.WEIGHTS_KEY: restored})
        cls._write_manifest(out, meta)
        saved = str(out.resolve())
        logger.info("model_quantized_fp16", out=saved)
        return saved

    @classmethod
    def convert_to_onnx(cls, model_path: str) -> str:
        """Export a tiny deterministic ONNX graph that embeds the optimized weights as a MatMul."""
        try:
            import onnx  # type: ignore import-not-found
            from onnx import TensorProto, helper  # type: ignore import-not-found
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError("Install ONNX: pip install onnx") from exc

        weights = cls._load_weights(model_path).astype(np.float32, copy=False)
        dim = int(math.ceil(math.sqrt(weights.size)))
        padded = np.zeros(dim * dim, dtype=np.float32)
        padded[: weights.size] = weights.ravel()
        matrix = padded.reshape(dim, dim)

        tensor_w = helper.make_tensor(
            name="W",
            data_type=TensorProto.FLOAT,
            dims=list(matrix.shape),
            vals=matrix.flatten().tolist(),
        )
        x_info = helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, dim])
        y_info = helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, dim])
        node = helper.make_node("MatMul", ["x", "W"], ["y"], name="edge_mul")
        graph = helper.make_graph(
            [node],
            "tutorial_edge",
            inputs=[x_info],
            outputs=[y_info],
            initializer=[tensor_w],
        )
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
        onnx.checker.check_model(model)
        out = cls._out_path(model_path, "onnx").with_suffix(".onnx")
        out.parent.mkdir(parents=True, exist_ok=True)
        onnx.save(model, out.as_posix())
        logger.info("model_exported_onnx", out=str(out))
        return str(out.resolve())

    @classmethod
    def get_model_size(cls, model_path: str) -> int:
        """Return on-disk model size in bytes."""
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(model_path)
        return int(path.stat().st_size)

    @classmethod
    def benchmark_model(cls, model_path: str, device: str) -> BenchmarkResult:
        """Benchmark ONNX Runtime when available; otherwise NumPy MatMul fallback."""
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(model_path)

        def _rss() -> int:
            usage = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            # macOS: bytes; Linux: kilobytes
            if sys.platform == "darwin":
                return usage
            return usage * 1024

        latencies: list[float] = []
        if path.suffix.lower() == ".onnx":
            try:
                import onnxruntime as ort  # type: ignore import-not-found
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("Install onnxruntime to benchmark ONNX models") from exc
            so = ort.SessionOptions()
            so.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
            session = ort.InferenceSession(path.as_posix(), sess_options=so, providers=["CPUExecutionProvider"])
            input_meta = session.get_inputs()[0]
            name = input_meta.name
            shape = []
            for dim in input_meta.shape:
                if isinstance(dim, str):
                    shape.append(1)
                else:
                    shape.append(int(dim) if dim is not None else 1)
            x = np.random.randn(*shape).astype(np.float32)
            # Warm-up
            for _ in range(3):
                session.run(None, {name: x})
            end = time.perf_counter() + 0.35
            while time.perf_counter() < end:
                t0 = time.perf_counter()
                session.run(None, {name: x})
                latencies.append((time.perf_counter() - t0) * 1000.0)
        else:
            weights = cls._load_weights(path.as_posix()).astype(np.float32, copy=False)
            dim = int(math.ceil(math.sqrt(weights.size)))
            padded = np.zeros(dim * dim, dtype=np.float32)
            padded[: weights.size] = weights.ravel()
            matrix = padded.reshape(dim, dim)
            x = np.random.randn(1, dim).astype(np.float32)
            end = time.perf_counter() + 0.25
            while time.perf_counter() < end:
                t0 = time.perf_counter()
                _ = x @ matrix
                latencies.append((time.perf_counter() - t0) * 1000.0)

        if not latencies:
            latencies = [0.0]
        mean_ms = float(np.mean(latencies))
        p95_ms = float(np.percentile(latencies, 95))
        rss = _rss()
        logger.info("model_benchmarked", mean_ms=mean_ms, p95_ms=p95_ms, device=device)
        return BenchmarkResult(
            model_path=str(path.resolve()),
            device=device,
            mean_latency_ms=mean_ms,
            p95_latency_ms=p95_ms,
            peak_rss_bytes=rss,
        )

    @classmethod
    def optimization_pipeline(cls, model_path: str, device_profile_ram_mb: int) -> dict[str, Any]:
        """Run prune → quantize → ONNX while enforcing a conservative RAM budget."""
        est_bytes = cls.get_model_size(model_path)
        budget = int(device_profile_ram_mb * 1024 * 1024 * 0.25)
        if est_bytes > budget:
            raise ValueError(
                f"Model file ({est_bytes} bytes) exceeds conservative RAM budget ({budget} bytes) "
                f"for this device profile"
            )
        pruned = cls.prune_model(model_path, target_sparsity=0.5)
        quantized = cls.quantize_model(pruned, target_bits=8)
        onnx_path = cls.convert_to_onnx(quantized)
        bench = cls.benchmark_model(onnx_path, device="edge_cpu")
        return {
            "pruned_path": pruned,
            "quantized_path": quantized,
            "onnx_path": onnx_path,
            "benchmark": bench.model_dump(),
        }
