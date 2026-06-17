"""Provisioner drivers — the only thing that differs between local and cloud."""
from control_plane.provisioner.base import (
    InstanceHandle,
    InstanceStatus,
    Provisioner,
    ProvisioningError,
)


def make_provisioner() -> Provisioner:
    """Construct the configured provisioner driver (CONTROL_PLANE_PROVISIONER).

    The single seam the webhook/CLI go through so neither knows whether it's
    talking to local Docker or Fly. FlyProvisioner slots in here at M5."""
    from control_plane.config import settings

    kind = settings.provisioner_kind
    if kind == "docker":
        from control_plane.provisioner.docker import DockerProvisioner

        return DockerProvisioner()
    raise ProvisioningError(f"unknown provisioner '{kind}' (set CONTROL_PLANE_PROVISIONER)")


__all__ = [
    "Provisioner",
    "InstanceHandle",
    "InstanceStatus",
    "ProvisioningError",
    "make_provisioner",
]
