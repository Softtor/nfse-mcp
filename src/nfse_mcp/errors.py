"""Normalized errors for the SEFIN Nacional ACL layer.

All exceptions inherit from ProviderError so the domain layer can catch them
without knowing SEFIN-specific details.
"""


class ProviderError(Exception):
    """Base exception for all provider errors."""

    def __init__(self, message: str, code: str = "PROVIDER_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class SefinNacionalError(ProviderError):
    """Generic SEFIN Nacional API error."""

    def __init__(self, message: str, code: str = "SEFIN_ERROR", raw_errors: list[dict] | None = None):
        self.raw_errors = raw_errors or []
        super().__init__(message, code)


class ValidationError(ProviderError):
    """XML/XSD validation error before sending."""

    def __init__(self, message: str, validation_errors: list[str] | None = None):
        self.validation_errors = validation_errors or []
        super().__init__(message, "VALIDATION_ERROR")


class CertificateError(ProviderError):
    """Certificate or mTLS connection error."""

    def __init__(self, message: str):
        super().__init__(message, "CERTIFICATE_ERROR")


class MunicipalityNotSupportedError(ProviderError):
    """The municipality is not integrated with the national system."""

    def __init__(self, municipality_code: str):
        self.municipality_code = municipality_code
        super().__init__(
            f"Municipio {municipality_code} nao conveniado ao Sistema Nacional NFS-e.",
            "MUNICIPALITY_NOT_SUPPORTED",
        )


class MunicipalityNotEnabledError(ProviderError):
    """The municipality is integrated but has not enabled national public issuers."""

    def __init__(self, municipality_code: str):
        self.municipality_code = municipality_code
        super().__init__(
            f"Municipio {municipality_code} esta conveniado ao Sistema Nacional NFS-e, "
            f"mas nao habilitou os emissores publicos nacionais (Web, Mobile, API). "
            f"Este municipio pode ter optado por manter seu emissor proprio (ISS.net/ABRASF). "
            f"Se voce emite pelo sistema municipal, continue usando a funcao 'emit_nfse' "
            f"em vez de 'emit_nfse_nacional'. "
            f"Mais info: https://www.gov.br/nfse/pt-br/municipios/monitoramento-adesoes",
            "MUNICIPALITY_NOT_ENABLED",
        )
