"""Device-specific resource profiles for QVAC Edge AI deployments."""

from __future__ import annotations

from typing import Any, TypedDict


class DeviceProfileDict(TypedDict, total=False):
    """Typed structure for entries in ``DEVICE_PROFILES``."""

    ram_mb: int
    cpu_cores: int
    gpu: str | None
    model_variant: str
    max_concurrent_agents: int
    inference_batch_size: int


DEVICE_PROFILES: dict[str, dict[str, Any]] = {
    "raspberry_pi_4": {
        "ram_mb": 4096,
        "cpu_cores": 4,
        "gpu": None,
        "model_variant": "tiny",
        "max_concurrent_agents": 2,
        "inference_batch_size": 1,
    },
    "nvidia_jetson_nano": {
        "ram_mb": 4096,
        "cpu_cores": 4,
        "gpu": "128-core Maxwell",
        "model_variant": "small",
        "max_concurrent_agents": 3,
        "inference_batch_size": 4,
    },
    "intel_nuc": {
        "ram_mb": 16384,
        "cpu_cores": 4,
        "gpu": "Intel UHD",
        "model_variant": "medium",
        "max_concurrent_agents": 5,
        "inference_batch_size": 8,
    },
    "generic_arm64": {
        "ram_mb": 8192,
        "cpu_cores": 4,
        "gpu": None,
        "model_variant": "small",
        "max_concurrent_agents": 3,
        "inference_batch_size": 2,
    },
}
