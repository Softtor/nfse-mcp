"""SEFIN Nacional provider implementation.

Implements ServiceInvoiceProvider and MunicipalParameterProvider.
"""

import logging
from typing import Optional

from nfse_mcp.certificate import Certificate
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
from nfse_mcp.sefin_nacional.client import SefinNacionalClient
from nfse_mcp.sefin_nacional.config import SefinNacionalConfig
from nfse_mcp.errors import (
    MunicipalityNotEnabledError,
    MunicipalityNotSupportedError,
    ProviderError,
    SefinNacionalError,
    ValidationError,
)
from nfse_mcp.sefin_nacional.mapper import (
    encode_xml_for_api,
    evento_cancela,
    map_cancel_input_to_evento_xml,
    map_input_to_dps_xml,
    map_json_to_benefits,
    map_json_to_cancel_result,
    map_json_to_issue_result,
    map_json_to_municipal_agreement,
    map_json_to_query_result,
    map_json_to_retentions,
    map_json_to_service_parameters,
)
from nfse_mcp.sefin_nacional.municipality_cache import MunicipalityCache
from nfse_mcp.sefin_nacional.municipality_data import MunicipalityDataLoader
from nfse_mcp.nacional.xsd_validator import XsdValidator
from nfse_mcp.xml_signer import XmlSigner
from nfse_mcp.nacional.dps_xml_builder import dps_id
from nfse_mcp.nacional.evento_xml_builder import CANCELAMENTO, evento_id

logger = logging.getLogger(__name__)


class SefinNacionalProvider(ServiceInvoiceProvider, MunicipalParameterProvider):
    """ACL provider for SEFIN Nacional NFS-e API."""

    def __init__(
        self,
        config: SefinNacionalConfig,
        cert: Certificate,
        signer: Optional[XmlSigner] = None,
        validator: Optional[XsdValidator] = None,
        client: Optional[SefinNacionalClient] = None,
        cache: Optional[MunicipalityCache] = None,
        data_loader: Optional[MunicipalityDataLoader] = None,
    ):
        self.config = config
        self.cert = cert
        self.signer = signer or XmlSigner(cert, use_sha256=False)
        self.validator = validator or XsdValidator()
        self.client = client or SefinNacionalClient(config, cert)
        self.cache = cache or MunicipalityCache()
        self.data_loader = data_loader or MunicipalityDataLoader()

    def issue(self, input: IssueServiceInvoiceInput) -> IssueServiceInvoiceResult:
        """Issue a service invoice via SEFIN Nacional."""
        try:
            # 1. Build DPS XML
            dps_xml = map_input_to_dps_xml(input)

            # 2. Validate XSD (optional)
            if not self.config.skip_xsd_validation:
                errors = self.validator.validate_dps(dps_xml)
                if errors:
                    raise ValidationError(
                        "XML DPS invalido segundo schema XSD",
                        validation_errors=errors,
                    )

            # 3. Sign XML: Reference aponta o Id do infDPS (o XSD oficial recusa URI vazia)
            id_dps = dps_id(input.prestador_endereco_codigo_municipio, input.prestador_cnpj,
                            input.serie_dps, input.numero_dps or "1")
            signed_xml = self.signer.sign_xml(dps_xml, reference_uri=f"#{id_dps}")

            # 4. Encode for API
            payload = encode_xml_for_api(signed_xml)

            # 5. Send
            response = self.client.post_nfse(payload)

            # 6. Map result
            return map_json_to_issue_result(response, 201)

        except SefinNacionalError as exc:
            self._raise_if_not_enabled(exc, input.prestador_endereco_codigo_municipio)
            raise
        except ProviderError:
            raise
        except Exception as exc:
            logger.exception("Erro inesperado na emissao SEFIN Nacional")
            raise SefinNacionalError(f"Erro inesperado: {exc}")

    def _raise_if_not_enabled(self, exc: SefinNacionalError, muni: str) -> None:
        """E0039 (município sem emissor público nacional) vira erro amigável e fica no cache."""
        if any(err.get("codigo") == "E0039" for err in exc.raw_errors):
            self.cache.set(muni, status="not_enabled", error_code="E0039", source="api_probe")
            raise MunicipalityNotEnabledError(muni) from exc

    def query_by_access_key(self, access_key: str) -> QueryServiceInvoiceResult:
        """Query an invoice by its access key."""
        try:
            response = self.client.get_nfse(access_key)
            return map_json_to_query_result(response, 200)
        except ProviderError:
            raise
        except Exception as exc:
            logger.exception("Erro na consulta por chave de acesso")
            raise SefinNacionalError(f"Erro na consulta: {exc}")

    def query_by_dps_id(self, dps_id: str) -> QueryServiceInvoiceResult:
        """Query an invoice by its DPS identifier."""
        try:
            response = self.client.get_dps(dps_id)
            # The response contains chaveAcesso; we then query the NFSe
            chave = response.get("chaveAcesso")
            if chave:
                return self.query_by_access_key(chave)
            return QueryServiceInvoiceResult(
                success=False,
                errors=[{"codigo": "NO_ACCESS_KEY", "descricao": "Chave de acesso nao disponivel para esta DPS"}],
            )
        except ProviderError:
            raise
        except Exception as exc:
            logger.exception("Erro na consulta por idDPS")
            raise SefinNacionalError(f"Erro na consulta: {exc}")

    def cancel(self, input: CancelServiceInvoiceInput) -> CancelServiceInvoiceResult:
        """Cancel an issued invoice."""
        try:
            evento_xml = map_cancel_input_to_evento_xml(input)

            if not self.config.skip_xsd_validation:
                errors = self.validator.validate_evento(evento_xml)
                if errors:
                    raise ValidationError(
                        "XML de evento invalido segundo schema XSD",
                        validation_errors=errors,
                    )

            signed_evento = self.signer.sign_xml(evento_xml, reference_uri=f"#{evento_id(input.chave_acesso)}")
            payload = encode_xml_for_api(signed_evento)

            response = self.client.post_evento(input.chave_acesso, payload)
            return map_json_to_cancel_result(response, 201)

        except ProviderError:
            raise
        except Exception as exc:
            logger.exception("Erro no cancelamento SEFIN Nacional")
            raise SefinNacionalError(f"Erro no cancelamento: {exc}")

    def cancelamento_registrado(self, access_key: str) -> bool:
        """Consulta o evento e101101 da chave; 404 = não há cancelamento."""
        try:
            response = self.client.get_evento(access_key, CANCELAMENTO)
        except SefinNacionalError as exc:
            if exc.code == "HTTP_404":
                return False
            raise
        return evento_cancela(response, access_key)

    def danfse_pdf(self, access_key: str) -> Optional[bytes]:
        """PDF do ADN, uma tentativa; erro ou conteúdo que não é PDF = None (o governo não está gerando)."""
        try:
            conteudo = self.client.get_danfse(access_key)
        except ProviderError:
            return None
        return conteudo if conteudo.startswith(b"%PDF") else None

    def get_agreement_by_municipality(self, municipality_code: str) -> MunicipalAgreementResult:
        """Check if a municipality is integrated."""
        try:
            response = self.client.get_convenio(municipality_code)
            result = map_json_to_municipal_agreement(response)

            # Enrich with external data if available
            external = self.data_loader.get_status(municipality_code)
            if external is not None:
                result.emissores_publicos_habilitados = external.emissor_nacional

            if not result.conveniado:
                self.cache.set(
                    municipality_code,
                    status="not_conveniado",
                    source="api_convenio",
                )
                raise MunicipalityNotSupportedError(municipality_code)

            # Update cache when we learn something new
            if result.emissores_publicos_habilitados is True:
                self.cache.set(
                    municipality_code,
                    status="enabled",
                    source="external_data",
                )
            elif result.emissores_publicos_habilitados is False:
                self.cache.set(
                    municipality_code,
                    status="not_enabled",
                    source="external_data",
                )

            return result
        except ProviderError:
            raise
        except Exception as exc:
            logger.exception("Erro ao consultar convenio municipal")
            raise SefinNacionalError(f"Erro ao consultar convenio: {exc}")

    def get_service_parameters(
        self, municipality_code: str, service_code: str
    ) -> ServiceTaxParameterResult:
        """Get tax parameters for a service."""
        try:
            response = self.client.get_service_parameters(municipality_code, service_code)
            return map_json_to_service_parameters(response)
        except ProviderError:
            raise
        except Exception as exc:
            logger.exception("Erro ao consultar parametros do servico")
            raise SefinNacionalError(f"Erro ao consultar parametros: {exc}")

    def get_contributor_retentions(
        self, municipality_code: str, document: str
    ) -> ContributorRetentionResult:
        """Get contributor retentions."""
        try:
            response = self.client.get_retencoes(municipality_code, document)
            return map_json_to_retentions(response)
        except ProviderError:
            raise
        except Exception as exc:
            logger.exception("Erro ao consultar retencoes")
            raise SefinNacionalError(f"Erro ao consultar retencoes: {exc}")

    def get_contributor_benefits(
        self, municipality_code: str, document: str
    ) -> ContributorBenefitResult:
        """Get contributor benefits."""
        try:
            response = self.client.get_beneficios(municipality_code, document)
            return map_json_to_benefits(response)
        except ProviderError:
            raise
        except Exception as exc:
            logger.exception("Erro ao consultar beneficios")
            raise SefinNacionalError(f"Erro ao consultar beneficios: {exc}")
