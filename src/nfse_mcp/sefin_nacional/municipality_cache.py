"""Local JSON cache for municipality emission status.

Updated automatically when real API calls succeed or fail with known errors.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[3] / "data" / "municipality_cache.json"


@dataclass(frozen=True)
class MunicipalityCacheEntry:
    status: str  # "enabled", "not_enabled", "not_conveniado", "unknown"
    error_code: Optional[str] = None
    last_checked: Optional[str] = None
    source: Optional[str] = None  # "api_probe", "external_data", "manual"


class MunicipalityCache:
    """JSON-backed cache for municipality emission status."""

    def __init__(self, cache_path: Optional[Path | str] = None):
        self.cache_path = Path(cache_path or DEFAULT_CACHE_PATH)
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, municipality_code: str) -> Optional[MunicipalityCacheEntry]:
        """Return cached entry for a municipality, if any."""
        raw = self._data.get(str(municipality_code))
        if raw is None:
            return None
        return MunicipalityCacheEntry(
            status=raw.get("status", "unknown"),
            error_code=raw.get("error_code"),
            last_checked=raw.get("last_checked"),
            source=raw.get("source"),
        )

    def set(
        self,
        municipality_code: str,
        status: str,
        error_code: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        """Update cache entry for a municipality."""
        self._data[str(municipality_code)] = {
            "status": status,
            "error_code": error_code,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "source": source or "api_probe",
        }
        self._save()

    def is_enabled(self, municipality_code: str) -> Optional[bool]:
        """Return True/False if known, None if not cached."""
        entry = self.get(municipality_code)
        if entry is None:
            return None
        if entry.status == "enabled":
            return True
        if entry.status in ("not_enabled", "not_conveniado"):
            return False
        return None

    def clear(self) -> None:
        """Clear all cached entries."""
        self._data = {}
        self._save()
