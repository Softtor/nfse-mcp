"""Municipal parameter application service.

Wraps the MunicipalParameterProvider port with application-level conveniences.
"""

from nfse_mcp.ports.municipal_parameter_provider import MunicipalParameterProvider


class MunicipalParameterApplicationService:
    """Application service for municipal parameter queries."""

    def __init__(self, provider: MunicipalParameterProvider):
        self._provider = provider

    def check_agreement(self, municipality_code: str):
        """Check if a municipality is integrated with the national system."""
        return self._provider.get_agreement_by_municipality(municipality_code)

    def get_service_parameters(self, municipality_code: str, service_code: str):
        """Get tax parameters for a specific service in a municipality."""
        return self._provider.get_service_parameters(municipality_code, service_code)

    def get_contributor_retentions(self, municipality_code: str, document: str):
        """Get ISSQN retentions for a contributor."""
        return self._provider.get_contributor_retentions(municipality_code, document)

    def get_contributor_benefits(self, municipality_code: str, document: str):
        """Get municipal benefits for a contributor."""
        return self._provider.get_contributor_benefits(municipality_code, document)
