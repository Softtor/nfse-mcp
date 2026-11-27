"""SEFIN Nacional NFS-e REST API integration (ACL layer)."""

from nfse_mcp.sefin_nacional.config import SefinNacionalConfig, load_sefin_config
from nfse_mcp.sefin_nacional.client import SefinNacionalClient
from nfse_mcp.sefin_nacional.provider import SefinNacionalProvider
from nfse_mcp.errors import (
    ProviderError,
    SefinNacionalError,
    ValidationError,
    CertificateError,
    MunicipalityNotSupportedError,
)

__all__ = [
    "SefinNacionalConfig",
    "load_sefin_config",
    "SefinNacionalClient",
    "SefinNacionalProvider",
    "ProviderError",
    "SefinNacionalError",
    "ValidationError",
    "CertificateError",
    "MunicipalityNotSupportedError",
]
