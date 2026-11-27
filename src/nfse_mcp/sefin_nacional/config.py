"""Configuration for SEFIN Nacional NFS-e API."""

from dataclasses import dataclass
from pathlib import Path
import os


BASE_URLS = {
    "production": "https://sefin.nfse.gov.br/SefinNacional",
    "production_restricted": "https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional",
}
# DANFSe (PDF oficial) sai do ADN, não da SEFIN (lá o /danfse dá 501).
ADN_URLS = {
    "production": "https://adn.nfse.gov.br",
    "production_restricted": "https://adn.producaorestrita.nfse.gov.br",
}


@dataclass
class SefinNacionalConfig:
    environment: str
    base_url: str
    certificate_path: str
    certificate_password: str
    timeout: int
    max_retries: int
    debug: bool
    skip_xsd_validation: bool

    @property
    def tp_amb(self) -> int:
        """tpAmb da DPS e dos eventos: 1 só em produção; qualquer outro ambiente vai como 2 (produção restrita)."""
        return 1 if self.environment == "production" else 2


def load_sefin_config() -> SefinNacionalConfig:
    """Load SEFIN Nacional configuration from environment variables."""
    env = os.getenv("SEFIN_ENVIRONMENT", "production_restricted")
    base_url = BASE_URLS.get(env, BASE_URLS["production_restricted"])

    # Prefer SEFIN-specific vars, fall back to existing NFSE vars
    cert_path = os.getenv("SEFIN_CERTIFICATE_PATH") or os.getenv("NFSE_CERTIFICATE_PATH", "")
    cert_password = os.getenv("SEFIN_CERTIFICATE_PASSWORD") or os.getenv("NFSE_CERTIFICATE_PASSWORD", "")

    return SefinNacionalConfig(
        environment=env,
        base_url=base_url,
        certificate_path=cert_path,
        certificate_password=cert_password,
        timeout=int(os.getenv("SEFIN_TIMEOUT", "60")),
        max_retries=int(os.getenv("SEFIN_MAX_RETRIES", "3")),
        debug=os.getenv("SEFIN_DEBUG", "false").lower() == "true",
        skip_xsd_validation=os.getenv("SEFIN_SKIP_XSD_VALIDATION", "false").lower() == "true",
    )
