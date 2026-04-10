from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
import os

WEBSERVICE_URLS = {
    "production": "https://df.issnetonline.com.br/webservicenfse204/nfse.asmx",
    "homologation": "https://www.issnetonline.com.br/apresentacao/df/webservicenfse204/nfse.asmx",
    "homologation_fictitious": "https://www.issnetonline.com.br/homologaabrasf/webservicenfse204/nfse.asmx",
}


@dataclass
class ProviderConfig:
    cnpj: str
    im: str  # inscricao municipal
    razao_social: str
    simples_nacional: int  # 1=sim, 2=nao
    regime_tributacao: int  # 6=ME/EPP
    incentivo_fiscal: int  # 1=sim, 2=nao


@dataclass
class ServiceDefaults:
    cnae: str
    item_lista_servico: str
    codigo_tributacao_municipio: str
    aliquota: str
    municipio_ibge: str
    iss_retido: int  # 1=sim, 2=nao
    exigibilidade_iss: int


@dataclass
class Config:
    environment: str
    certificate_path: str
    certificate_password: str
    provider: ProviderConfig
    service_defaults: ServiceDefaults
    rps_serie: str
    webservice_url: str
    data_dir: Path  # path to data/ directory


def load_config() -> Config:
    # Load .env from project root
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(env_path)

    environment = os.getenv("NFSE_ENVIRONMENT", "production")

    provider = ProviderConfig(
        cnpj=os.getenv("NFSE_PROVIDER_CNPJ", ""),
        im=os.getenv("NFSE_PROVIDER_IM", ""),
        razao_social=os.getenv("NFSE_PROVIDER_RAZAO_SOCIAL", ""),
        simples_nacional=int(os.getenv("NFSE_PROVIDER_SIMPLES_NACIONAL", "1")),
        regime_tributacao=int(os.getenv("NFSE_PROVIDER_REGIME_TRIBUTACAO", "6")),
        incentivo_fiscal=int(os.getenv("NFSE_PROVIDER_INCENTIVO_FISCAL", "2")),
    )

    service_defaults = ServiceDefaults(
        cnae=os.getenv("NFSE_DEFAULT_CNAE", ""),
        item_lista_servico=os.getenv("NFSE_DEFAULT_ITEM_LISTA_SERVICO", ""),
        codigo_tributacao_municipio=os.getenv("NFSE_DEFAULT_CODIGO_TRIBUTACAO_MUNICIPIO", ""),
        aliquota=os.getenv("NFSE_DEFAULT_ALIQUOTA", "2.00"),
        municipio_ibge=os.getenv("NFSE_DEFAULT_MUNICIPIO_IBGE", "5300108"),
        iss_retido=int(os.getenv("NFSE_DEFAULT_ISS_RETIDO", "2")),
        exigibilidade_iss=int(os.getenv("NFSE_DEFAULT_EXIGIBILIDADE_ISS", "1")),
    )

    data_dir = Path(__file__).parent.parent.parent / "data"

    return Config(
        environment=environment,
        certificate_path=os.getenv("NFSE_CERTIFICATE_PATH", ""),
        certificate_password=os.getenv("NFSE_CERTIFICATE_PASSWORD", ""),
        provider=provider,
        service_defaults=service_defaults,
        rps_serie=os.getenv("NFSE_RPS_SERIE", "3"),
        webservice_url=WEBSERVICE_URLS.get(environment, WEBSERVICE_URLS["production"]),
        data_dir=data_dir,
    )
