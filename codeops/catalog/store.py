"""Local catalog cache (.codeops/catalog/models.json)."""

from __future__ import annotations

import json
from pathlib import Path

from codeops.catalog.types import CatalogModel

DEFAULT_CATALOG_DIR = Path(".codeops/catalog")
MODELS_FILE = "models.json"


def catalog_path(base: Path | None = None) -> Path:
    root = base or Path.cwd()
    return root / DEFAULT_CATALOG_DIR / MODELS_FILE


def load_models(base: Path | None = None) -> list[CatalogModel]:
    path = catalog_path(base)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    items = data if isinstance(data, list) else data.get("models", [])
    return [CatalogModel.from_dict(m) for m in items if isinstance(m, dict) and m.get("id")]


def save_models(models: list[CatalogModel], base: Path | None = None) -> Path:
    path = catalog_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "models": [m.to_dict() for m in models],
        "count": len(models),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
