"""Ports (interfaces) for fiscal service invoice providers."""

from nfse_mcp.ports.service_invoice_provider import (
    CancelServiceInvoiceInput,
    CancelServiceInvoiceResult,
    IssueServiceInvoiceInput,
    IssueServiceInvoiceResult,
    QueryServiceInvoiceResult,
    ServiceInvoiceProvider,
)
from nfse_mcp.ports.municipal_parameter_provider import (
    ContributorBenefitResult,
    ContributorRetentionResult,
    MunicipalAgreementResult,
    MunicipalParameterProvider,
    ServiceTaxParameterResult,
)

__all__ = [
    "CancelServiceInvoiceInput",
    "CancelServiceInvoiceResult",
    "IssueServiceInvoiceInput",
    "IssueServiceInvoiceResult",
    "QueryServiceInvoiceResult",
    "ServiceInvoiceProvider",
    "ContributorBenefitResult",
    "ContributorRetentionResult",
    "MunicipalAgreementResult",
    "MunicipalParameterProvider",
    "ServiceTaxParameterResult",
]
