"""External municipality data loader.

Attempts to load the official Receita Federal spreadsheet of NFS-e adherent
municipalities. Falls back to an embedded snapshot if the download fails.

The official list is published at:
  https://www.gov.br/nfse/pt-br/municipios/municipios-aderentes

Note: the portal page changes frequently; if automatic download breaks, use
scripts/update_municipality_data.py to refresh the local snapshot manually.
"""

import csv
import json
import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DEFAULT_SNAPSHOT_PATH = DEFAULT_DATA_DIR / "municipality_snapshot.json"

# Known direct URLs (may break; manual refresh via script is the stable path)
KNOWN_SPREADSHEET_URLS = [
    "https://www.gov.br/nfse/pt-br/municipios/municipios-aderentes",
]


@dataclass(frozen=True)
class MunicipalityStatus:
    codigo_ibge: str
    nome: str
    uf: str
    conveniado: bool
    emissor_nacional: Optional[bool]  # True=uses national issuer, False=own issuer, None=unknown
    fonte: str
    data_atualizacao: Optional[str]


# Municipalities officially confirmed to maintain their own issuer (not national public issuers).
# Sources: official municipal communications, Seec/DF, etc.
# When a municipality is in this set, contributors must use the ABRASF/ISS.net provider,
# NOT the SEFIN Nacional (REST API) provider.
EMISSOR_PROPRIO_SET: set[str] = set()

# Municipalities where the contributor must issue through the national public issuers.
# Brasília/DF: desde a competência 11/2026 o ISS.net recusa RPS de optante do Simples Nacional
# (erro L120: "A emissão deve ser realizada no Emissor Nacional ... API do Ambiente Nacional").
EMISSOR_NACIONAL_SET: set[str] = {
    "5300108",
}

# Embedded minimal snapshot (can be expanded by the update script).
# This ensures the module works even when the portal is unreachable.
EMBEDDED_SNAPSHOT: dict[str, dict] = {
    # Example entry format; real data is loaded from snapshot file or downloaded.
    # "5300108": {
    #     "nome": "Brasilia",
    #     "uf": "DF",
    #     "conveniado": True,
    #     "emissor_nacional": False,
    #     "fonte": "embedded",
    #     "data_atualizacao": None,
    # }
}


def _normalize_ibge(code: str) -> str:
    return str(code).strip().lstrip("0").zfill(7)


class MunicipalityDataLoader:
    """Loads and queries municipality adherence data.

    Usage:
        loader = MunicipalityDataLoader()
        status = loader.get_status("5300108")
        if status and status.emissor_nacional is True:
            print("Habilitado para emissores públicos nacionais")
    """

    def __init__(
        self,
        snapshot_path: Optional[Path | str] = None,
    ):
        self.snapshot_path = Path(snapshot_path or DEFAULT_SNAPSHOT_PATH)
        self._data: dict[str, MunicipalityStatus] = {}
        self._load()

    def _load(self) -> None:
        # 1. Try local snapshot file
        if self.snapshot_path.exists():
            try:
                with open(self.snapshot_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for code, entry in raw.items():
                    self._data[_normalize_ibge(code)] = MunicipalityStatus(
                        codigo_ibge=_normalize_ibge(code),
                        nome=entry.get("nome", ""),
                        uf=entry.get("uf", ""),
                        conveniado=entry.get("conveniado", False),
                        emissor_nacional=entry.get("emissor_nacional"),
                        fonte=entry.get("fonte", "snapshot"),
                        data_atualizacao=entry.get("data_atualizacao"),
                    )
                logger.info("Loaded %d municipalities from snapshot", len(self._data))
                return
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load snapshot: %s", exc)

        # 2. Fall back to embedded snapshot
        for code, entry in EMBEDDED_SNAPSHOT.items():
            self._data[_normalize_ibge(code)] = MunicipalityStatus(
                codigo_ibge=_normalize_ibge(code),
                nome=entry.get("nome", ""),
                uf=entry.get("uf", ""),
                conveniado=entry.get("conveniado", False),
                emissor_nacional=entry.get("emissor_nacional"),
                fonte=entry.get("fonte", "embedded"),
                data_atualizacao=entry.get("data_atualizacao"),
            )
        logger.info("Loaded %d municipalities from embedded snapshot", len(self._data))

    def get_status(self, municipality_code: str) -> Optional[MunicipalityStatus]:
        """Return status for a municipality, or None if not in dataset."""
        return self._data.get(_normalize_ibge(municipality_code))

    def is_emissor_nacional(self, municipality_code: str) -> bool:
        """Return True if the municipality uses national public issuers.

        This is a strong signal that SEFIN Nacional (REST API) is the
        correct provider for this municipality.
        """
        if _normalize_ibge(municipality_code) in EMISSOR_NACIONAL_SET:
            return True
        status = self.get_status(municipality_code)
        if status is not None and status.emissor_nacional is True:
            return True
        return False

    def is_emissor_proprio(self, municipality_code: str) -> bool:
        """Return True if the municipality maintains its own issuer.

        This is a stronger signal than `is_emissor_nacional == False`:
        a municipality may be in transition or simply not have enabled
        national issuers yet. When this returns True, the contributor
        should use the ABRASF/ISS.net provider.
        """
        code = _normalize_ibge(municipality_code)
        if code in EMISSOR_PROPRIO_SET:
            return True
        status = self.get_status(municipality_code)
        if status is not None and status.emissor_nacional is False:
            return True
        return False

    def determine_best_provider(self, municipality_code: str) -> str | None:
        """Return the best provider for a municipality, or None if unknown.

        Returns:
            "abrasf" — municipality maintains its own issuer (ISS.net, Betha, IPM, etc.)
            "sefin"  — municipality uses national public issuers
            None     — not enough information to decide
        """
        if self.is_emissor_proprio(municipality_code):
            return "abrasf"
        if self.is_emissor_nacional(municipality_code):
            return "sefin"
        return None

    def refresh_from_csv(self, csv_path: Path | str) -> None:
        """Reload data from a local CSV file (e.g. downloaded manually)."""
        new_data: dict[str, MunicipalityStatus] = {}
        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = _normalize_ibge(row.get("codigo_ibge", row.get("IBGE", "")))
                if not code:
                    continue
                # Heuristic: if the CSV has an "emissor_nacional" column use it,
                # otherwise infer from "tipo_adesao" or similar.
                emissor_nacional: Optional[bool] = None
                emissor_raw = row.get("emissor_nacional", "").strip().lower()
                if emissor_raw in ("sim", "true", "1", "s"):
                    emissor_nacional = True
                elif emissor_raw in ("nao", "false", "0", "n"):
                    emissor_nacional = False

                conveniado = True
                conveniado_raw = row.get("conveniado", "").strip().lower()
                if conveniado_raw in ("nao", "false", "0", "n"):
                    conveniado = False

                new_data[code] = MunicipalityStatus(
                    codigo_ibge=code,
                    nome=row.get("nome", row.get("municipio", "")).strip(),
                    uf=row.get("uf", row.get("UF", "")).strip(),
                    conveniado=conveniado,
                    emissor_nacional=emissor_nacional,
                    fonte="csv_manual",
                    data_atualizacao=datetime.now(timezone.utc).isoformat(),
                )

        self._data = new_data
        self._persist()
        logger.info("Refreshed %d municipalities from CSV", len(self._data))

    def _persist(self) -> None:
        """Write current in-memory data to the snapshot JSON file."""
        raw: dict[str, dict] = {}
        for code, status in self._data.items():
            raw[code] = {
                "nome": status.nome,
                "uf": status.uf,
                "conveniado": status.conveniado,
                "emissor_nacional": status.emissor_nacional,
                "fonte": status.fonte,
                "data_atualizacao": status.data_atualizacao,
            }
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.snapshot_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
