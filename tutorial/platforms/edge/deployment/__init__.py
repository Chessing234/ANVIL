"""Edge deployment helpers (Docker, device profiles)."""

from platforms.edge.deployment.device_profiles import DEVICE_PROFILES
from platforms.edge.deployment.docker_edge import (
    buildx_bake_edge_targets,
    edge_compose_fragment,
    edge_dockerfile,
)

__all__ = [
    "DEVICE_PROFILES",
    "buildx_bake_edge_targets",
    "edge_compose_fragment",
    "edge_dockerfile",
]
