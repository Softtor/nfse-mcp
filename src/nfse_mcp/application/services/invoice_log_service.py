"""Invoice and cancel log service.

Encapsulates reading/writing of local JSON logs for issued and cancelled invoices.
"""

import json
from datetime import date
from pathlib import Path


class InvoiceLogService:
    """Manages local JSON logs for NFS-e operations."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._nfse_log_path = data_dir / "nfse_log.json"
        self._cancel_log_path = data_dir / "cancel_log.json"

    def _today_str(self) -> str:
        return date.today().isoformat()

    def _load_json(self, path: Path) -> list[dict]:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                return []
        return []

    def _append_json(self, path: Path, entry: dict) -> None:
        data = self._load_json(path)
        data.append(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # ------------------------------------------------------------------
    # NFS-e log
    # ------------------------------------------------------------------

    def append_nfse_log(self, entry: dict) -> None:
        """Append an entry to the NFS-e issuance log."""
        self._append_json(self._nfse_log_path, entry)

    def save_nfse_log(self, entries: list[dict]) -> None:
        """Rewrite the NFS-e issuance log (used to update a pending entry in place)."""
        self._nfse_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._nfse_log_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False))

    def load_nfse_log(self) -> list[dict]:
        """Load the full NFS-e issuance log."""
        return self._load_json(self._nfse_log_path)

    # ------------------------------------------------------------------
    # Cancel log
    # ------------------------------------------------------------------

    def append_cancel_log(self, entry: dict) -> None:
        """Append an entry to the cancellation log."""
        self._append_json(self._cancel_log_path, entry)

    def load_cancel_log(self) -> list[dict]:
        """Load the full cancellation log."""
        return self._load_json(self._cancel_log_path)
