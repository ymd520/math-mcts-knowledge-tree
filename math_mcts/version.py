"""Runtime accessor for the single version value stored in the catalog manifest."""
import json
from pathlib import Path

_MANIFEST_PATH = Path(__file__).with_name("data") / "curated" / "manifest.json"


def _read_catalog_version() -> str:
    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError(f"Missing catalog version in {_MANIFEST_PATH}")
    return version


CATALOG_VERSION = _read_catalog_version()
