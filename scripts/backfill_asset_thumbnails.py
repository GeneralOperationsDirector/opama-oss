"""
Backfill thumbnails for existing CustomAsset images that predate thumbnail generation.

Run inside the backend container:
    docker exec -it opama-backend python /app/scripts/backfill_asset_thumbnails.py

Or from the host with the DB reachable:
    python scripts/backfill_asset_thumbnails.py
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

# Allow imports from the project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")

from PIL import Image
from sqlmodel import Session, create_engine, select

from services.custom_assets.models import CustomAsset

_ROOT = Path(__file__).resolve().parents[1]
UPLOADS = Path(os.environ.get("ASSET_UPLOADS_PATH", str(_ROOT / "uploads/assets")))
THUMB_WIDTH = 300
DATABASE_URL = os.environ["DATABASE_URL"]

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


def make_thumbnail(src: Path) -> bytes:
    img = Image.open(src).convert("RGB")
    ratio = THUMB_WIDTH / img.width
    img = img.resize((THUMB_WIDTH, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return buf.getvalue()


def backfill() -> None:
    engine = create_engine(DATABASE_URL)
    updated = skipped = missing = errors = 0

    with Session(engine) as session:
        assets = session.exec(select(CustomAsset)).all()
        print(f"Found {len(assets)} assets total.")

        for asset in assets:
            changed = False

            for url_field, thumb_field, glob_pattern, thumb_name in [
                ("image_url",      "image_thumb_url",      f"{asset.id}.*",      f"{asset.id}_thumb.jpg"),
                ("back_image_url", "back_image_thumb_url", f"{asset.id}_back.*", f"{asset.id}_back_thumb.jpg"),
            ]:
                url = getattr(asset, url_field)
                if not url or not url.startswith("/uploads/"):
                    continue

                # Skip if thumbnail already exists and is recorded
                if getattr(asset, thumb_field):
                    skipped += 1
                    continue

                # Find the full-resolution file on disk
                candidates = list(UPLOADS.glob(glob_pattern.split("/")[-1]))
                if not candidates:
                    print(f"  [MISSING] asset {asset.id} {url_field}: file not found on disk")
                    missing += 1
                    continue

                src = candidates[0]
                thumb_path = UPLOADS / thumb_name
                try:
                    thumb_path.write_bytes(make_thumbnail(src))
                    setattr(asset, thumb_field, f"/uploads/assets/{thumb_name}")
                    changed = True
                    print(f"  [OK] asset {asset.id} {thumb_field} → {thumb_name}")
                    updated += 1
                except Exception as exc:
                    print(f"  [ERROR] asset {asset.id} {url_field}: {exc}")
                    errors += 1

            if changed:
                session.add(asset)

        session.commit()

    print(f"\nDone. updated={updated}  skipped={skipped}  missing={missing}  errors={errors}")


if __name__ == "__main__":
    backfill()
