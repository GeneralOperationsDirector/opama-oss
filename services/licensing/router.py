from fastapi import APIRouter
from pydantic import BaseModel

from app.license import get_license

router = APIRouter()


class LicenseStatus(BaseModel):
    valid: bool
    tier: str
    modules: list[str] | str
    customer: str | None
    expires_at: str | None
    message: str


@router.get("", response_model=LicenseStatus)
def license_status() -> LicenseStatus:
    """Return the current license status for this deployment."""
    info = get_license()
    return LicenseStatus(
        valid=info.valid,
        tier=info.tier,
        modules=info.modules,
        customer=info.customer or None,
        expires_at=info.expires_at.isoformat() if info.expires_at else None,
        message=info.message,
    )
