"""Unified NFS-e emission router with intelligent fallback.

Orchestrates between SEFIN Nacional (REST API) and ABRASF/ISS.net (SOAP)
based on municipality characteristics and availability.
"""

from nfse_mcp.application.dto.commands import IssueInvoiceCommand
from nfse_mcp.application.exceptions.application_error import InvoiceError
from nfse_mcp.application.services.abrasf_service import AbrasfApplicationService
from nfse_mcp.application.services.sefin_nacional_service import SefinNacionalApplicationService
from nfse_mcp.config import Config
from nfse_mcp.errors import (
    MunicipalityNotEnabledError,
    MunicipalityNotSupportedError,
    SefinNacionalError,
)
from nfse_mcp.sefin_nacional.municipality_data import MunicipalityDataLoader

# Municipalities currently supported by the ABRASF/ISS.net integration.
# Expand this set as new municipality integrations are implemented.
SUPPORTED_ABRASF_MUNICIPALITIES: set[str] = {
    "5300108",  # Brasília/DF — ISS.net ABRASF 2.04
}


class NfseRouterService:
    """Routes NFS-e emission requests to the correct provider.

    Usage:
        router = NfseRouterService(sefin_service, abrasf_service, data_loader, config)
        result = router.issue_invoice(command)
    """

    def __init__(
        self,
        sefin_service: SefinNacionalApplicationService,
        abrasf_service: AbrasfApplicationService,
        data_loader: MunicipalityDataLoader,
        config: Config,
    ):
        self._sefin_service = sefin_service
        self._abrasf_service = abrasf_service
        self._data_loader = data_loader
        self._config = config

    def _is_abrasf_supported(self, municipality_code: str) -> bool:
        """Return True if we have an ABRASF integration for this municipality."""
        from nfse_mcp.sefin_nacional.municipality_data import _normalize_ibge
        return _normalize_ibge(municipality_code) in SUPPORTED_ABRASF_MUNICIPALITIES

    def _try_sefin(self, command: IssueInvoiceCommand):
        """Attempt emission via SEFIN Nacional."""
        return self._sefin_service.issue_invoice(command)

    def _try_abrasf(self, command: IssueInvoiceCommand):
        """Attempt emission via ABRASF/ISS.net."""
        return self._abrasf_service.issue_invoice(command)

    def issue_invoice(self, command: IssueInvoiceCommand):
        """Emit a service invoice using the best available provider.

        Returns the result from either SEFIN Nacional or ABRASF/ISS.net.
        Raises InvoiceError with a clear message when neither provider is available.
        """
        muni = command.codigo_municipio or self._config.service_defaults.municipio_ibge or "5300108"

        # 1. Known own-issuer municipality → go straight to ABRASF
        if self._data_loader.is_emissor_proprio(muni):
            if self._is_abrasf_supported(muni):
                return self._try_abrasf(command)
            raise InvoiceError(
                f"Municipio {muni} mantem emissor proprio (ISS.net/ABRASF), "
                f"mas a integracao ABRASF para este municipio ainda nao esta disponivel. "
                f"Entre em contato com o suporte para verificar quando sera implementada."
            )

        # 2. Known national-issuer municipality → go straight to SEFIN
        if self._data_loader.is_emissor_nacional(muni):
            return self._try_sefin(command)

        # 3. Unknown → try SEFIN first, fallback to ABRASF on specific errors
        return self._try_sefin_with_abrasf_fallback(command, muni)

    def _try_sefin_with_abrasf_fallback(self, command: IssueInvoiceCommand, municipality_code: str):
        """Try SEFIN Nacional first; fallback to ABRASF on known errors."""
        try:
            return self._try_sefin(command)
        except MunicipalityNotEnabledError:
            # Municipality is integrated but hasn't enabled national public issuers.
            # It likely maintains its own issuer.
            if self._is_abrasf_supported(municipality_code):
                return self._try_abrasf(command)
            raise InvoiceError(
                f"Municipio {municipality_code} nao habilitou os emissores publicos nacionais "
                f"(erro E0039) e a integracao ABRASF/ISS.net para este municipio ainda nao "
                f"esta disponivel. O municipio pode manter emissor proprio. "
                f"Entre em contato com o suporte para verificar quando sera implementada."
            )
        except MunicipalityNotSupportedError:
            # Municipality is not integrated with the national system at all.
            if self._is_abrasf_supported(municipality_code):
                return self._try_abrasf(command)
            raise InvoiceError(
                f"Municipio {municipality_code} nao aderiu ao Sistema Nacional NFS-e "
                f"e a integracao ABRASF para este municipio nao esta disponivel. "
                f"Entre em contato com o suporte."
            )
        except SefinNacionalError as exc:
            # Any other SEFIN error (connection, certificate, validation, etc.)
            # Try ABRASF as a last resort if supported.
            if self._is_abrasf_supported(municipality_code):
                return self._try_abrasf(command)
            # Re-raise as InvoiceError with context
            raise InvoiceError(
                f"Erro no SEFIN Nacional para municipio {municipality_code}: {exc.message}. "
                f"Integracao ABRASF tambem nao esta disponivel para este municipio."
            )
