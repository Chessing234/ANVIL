"""QVAC Edge AI integration (quantization, on-device runtime, local sync, deployment helpers)."""

from platforms.edge.deployment import (
    DEVICE_PROFILES,
    buildx_bake_edge_targets,
    edge_compose_fragment,
    edge_dockerfile,
)
from platforms.edge.edge_runtime import DeviceProfile, DeviceStatus, EdgeRuntime
from platforms.edge.local_sync import LocalSync, SyncResult, SyncStatus
from platforms.edge.model_optimizer import BenchmarkResult, ModelOptimizer

__all__ = [
    "BenchmarkResult",
    "DEVICE_PROFILES",
    "DeviceProfile",
    "DeviceStatus",
    "EdgeRuntime",
    "LocalSync",
    "ModelOptimizer",
    "SyncResult",
    "SyncStatus",
    "buildx_bake_edge_targets",
    "edge_compose_fragment",
    "edge_dockerfile",
]
