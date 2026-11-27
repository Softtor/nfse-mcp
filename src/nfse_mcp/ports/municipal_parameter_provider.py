"""Port interface for municipal parameter providers.

Allows querying tax parameters, agreements, retentions and benefits per municipality.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MunicipalAgreementResult:
    conveniado: bool = False
    data_adesao: Optional[str] = None
    regras_especiais: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    emissores_publicos_habilitados: Optional[bool] = None


@dataclass
class ServiceTaxParameterResult:
    aliquotas: list[dict] = field(default_factory=list)
    regimes_especiais: list[dict] = field(default_factory=list)
    deducoes: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


@dataclass
class ContributorRetentionResult:
    retencoes: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


@dataclass
class ContributorBenefitResult:
    beneficios: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


class MunicipalParameterProvider(ABC):
    """Abstract provider for municipal tax parameters."""

    @abstractmethod
    def get_agreement_by_municipality(self, municipality_code: str) -> MunicipalAgreementResult:
        """Check if a municipality is integrated with the national system."""
        ...

    @abstractmethod
    def get_service_parameters(
        self, municipality_code: str, service_code: str
    ) -> ServiceTaxParameterResult:
        """Get tax parameters for a specific service in a municipality."""
        ...

    @abstractmethod
    def get_contributor_retentions(
        self, municipality_code: str, document: str
    ) -> ContributorRetentionResult:
        """Get ISSQN retentions for a contributor in a municipality."""
        ...

    @abstractmethod
    def get_contributor_benefits(
        self, municipality_code: str, document: str
    ) -> ContributorBenefitResult:
        """Get municipal benefits for a contributor."""
        ...
