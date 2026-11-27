"""Fake/mock implementations for SEFIN Nacional testing."""

from typing import Optional

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
from nfse_mcp.errors import SefinNacionalError


class FakeSefinNacionalProvider(ServiceInvoiceProvider, MunicipalParameterProvider):
    """In-memory fake provider for unit testing without real API calls."""

    def __init__(self, simulate_errors: Optional[dict] = None):
        self.issued: list[IssueServiceInvoiceInput] = []
        self.cancelled: list[CancelServiceInvoiceInput] = []
        self.queried_keys: list[str] = []
        self.simulate_errors = simulate_errors or {}

    def issue(self, input: IssueServiceInvoiceInput) -> IssueServiceInvoiceResult:
        if "issue" in self.simulate_errors:
            error = self.simulate_errors["issue"]
            if isinstance(error, Exception):
                raise error
            return IssueServiceInvoiceResult(success=False, errors=error)

        self.issued.append(input)
        # Generate fake access key
        chave = f"53001082{input.prestador_cnpj}{input.serie_dps.zfill(5)}{input.numero_dps or '1'.zfill(15)}0"
        chave = chave[:50].ljust(50, "0")
        return IssueServiceInvoiceResult(
            success=True,
            chave_acesso=chave,
            id_dps=f"{input.prestador_cnpj}{input.serie_dps.zfill(5)}{input.numero_dps or '1'.zfill(15)}",
            xml_nfse="<Nfse><Numero>1</Numero></Nfse>",
        )

    def query_by_access_key(self, access_key: str) -> QueryServiceInvoiceResult:
        if "query" in self.simulate_errors:
            error = self.simulate_errors["query"]
            if isinstance(error, Exception):
                raise error
            return QueryServiceInvoiceResult(success=False, errors=error)

        self.queried_keys.append(access_key)
        return QueryServiceInvoiceResult(
            success=True,
            chave_acesso=access_key,
            xml_nfse="<Nfse><Numero>1</Numero></Nfse>",
            status="autorizada",
        )

    def query_by_dps_id(self, dps_id: str) -> QueryServiceInvoiceResult:
        return self.query_by_access_key(f"FAKEKEY{dps_id}")

    def cancel(self, input: CancelServiceInvoiceInput) -> CancelServiceInvoiceResult:
        if "cancel" in self.simulate_errors:
            error = self.simulate_errors["cancel"]
            if isinstance(error, Exception):
                raise error
            return CancelServiceInvoiceResult(success=False, errors=error)

        self.cancelled.append(input)
        return CancelServiceInvoiceResult(success=True, xml_evento="<Evento></Evento>")

    def cancelamento_registrado(self, access_key: str) -> bool:
        return False

    def danfse_pdf(self, access_key: str) -> Optional[bytes]:
        return None

    def get_agreement_by_municipality(self, municipality_code: str) -> MunicipalAgreementResult:
        if "convenio" in self.simulate_errors:
            return MunicipalAgreementResult(conveniado=False)
        return MunicipalAgreementResult(
            conveniado=True,
            data_adesao="2025-01-01",
            emissores_publicos_habilitados=True,
        )

    def get_service_parameters(
        self, municipality_code: str, service_code: str
    ) -> ServiceTaxParameterResult:
        return ServiceTaxParameterResult(
            aliquotas=[{"valor": "2.00", "tipo": "padrao"}],
        )

    def get_contributor_retentions(
        self, municipality_code: str, document: str
    ) -> ContributorRetentionResult:
        return ContributorRetentionResult(retencoes=[])

    def get_contributor_benefits(
        self, municipality_code: str, document: str
    ) -> ContributorBenefitResult:
        return ContributorBenefitResult(beneficios=[])
