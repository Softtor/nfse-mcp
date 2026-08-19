from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

from nfse_mcp.nacional.constants import (
    HOMOLOG_URL,
    HOMOLOG_WSDL_URL,
    LAYOUT_VERSION,
    MUNICIPIO_IBGE_DF,
)


@dataclass
class NacionalConfig:
    enabled: bool
    environment: str
    webservice_url: str
    wsdl_url: str
    certificate_path: str
    certificate_password: str
    provider_cnpj: str
    provider_im: str
    provider_razao_social: str
    optante_simples: bool
    c_trib_nac: str
    c_trib_mun: str
    aliquota: str
    municipio_ibge: str
    dps_serie: str
    layout_version: str
    data_dir: Path


def load_nacional_config() -> NacionalConfig:
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    load_dotenv(env_path)

    environment = os.getenv("NFSE_NACIONAL_ENVIRONMENT", "homologation").strip().lower()
    enabled = os.getenv("NFSE_NACIONAL_ENABLED", "0").strip() in ("1", "true", "True", "yes")
    data_dir = Path(__file__).parent.parent.parent.parent / "data"
    simples = os.getenv("NFSE_PROVIDER_SIMPLES_NACIONAL", "1").strip() == "1"

    return NacionalConfig(
        enabled=enabled,
        environment=environment,
        webservice_url=HOMOLOG_URL,
        wsdl_url=HOMOLOG_WSDL_URL,
        certificate_path=os.getenv("NFSE_CERTIFICATE_PATH", ""),
        certificate_password=os.getenv("NFSE_CERTIFICATE_PASSWORD", ""),
        provider_cnpj=os.getenv("NFSE_PROVIDER_CNPJ", ""),
        provider_im=os.getenv("NFSE_PROVIDER_IM", ""),
        provider_razao_social=os.getenv("NFSE_PROVIDER_RAZAO_SOCIAL", ""),
        optante_simples=simples,
        c_trib_nac=os.getenv("NFSE_NACIONAL_C_TRIB_NAC", "010701"),
        c_trib_mun=os.getenv("NFSE_NACIONAL_C_TRIB_MUN")
        or os.getenv("NFSE_DEFAULT_CODIGO_TRIBUTACAO_MUNICIPIO", "107"),
        aliquota=os.getenv("NFSE_DEFAULT_ALIQUOTA", "2.00"),
        municipio_ibge=os.getenv("NFSE_DEFAULT_MUNICIPIO_IBGE", MUNICIPIO_IBGE_DF),
        dps_serie=os.getenv("NFSE_NACIONAL_DPS_SERIE", "1"),
        layout_version=LAYOUT_VERSION,
        data_dir=data_dir,
    )


def homolog_gate(cfg: NacionalConfig) -> str | None:
    if not cfg.enabled:
        return (
            "NFS-e Padrão Nacional (DF) está desligado. "
            "Defina NFSE_NACIONAL_ENABLED=1 no .env para usar as tools de homologação. "
            "O caminho de produção continua sendo ABRASF 2.04."
        )
    if cfg.environment not in ("homologation", "homologacao", "homolog"):
        return (
            "NFS-e Padrão Nacional (DF) é homolog-only. "
            "NFSE_NACIONAL_ENVIRONMENT deve ser homologation. "
            "A URL de produção DF Nacional não é usada."
        )
    return None
