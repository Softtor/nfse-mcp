"""Mapper between internal domain models and SEFIN Nacional API formats.

Handles:
- Domain input → DPS XML
- GZip + Base64 encoding/decoding
- JSON response → domain result objects
"""

import base64
import gzip
from typing import Optional
from lxml import etree

from nfse_mcp.ports.service_invoice_provider import (
    CancelServiceInvoiceInput,
    CancelServiceInvoiceResult,
    IssueServiceInvoiceInput,
    IssueServiceInvoiceResult,
    QueryServiceInvoiceResult,
)
from nfse_mcp.ports.municipal_parameter_provider import (
    ContributorBenefitResult,
    ContributorRetentionResult,
    MunicipalAgreementResult,
    ServiceTaxParameterResult,
)
from nfse_mcp.nacional.dps_xml_builder import build_dps_xml
from nfse_mcp.nacional.evento_xml_builder import build_evento_cancelamento_xml
from nfse_mcp.errors import SefinNacionalError


# Regime especial ABRASF -> regEspTrib nacional. ABRASF 5 (MEI) e 6 (ME/EPP) não são regime especial
# no nacional: o enquadramento no Simples vai em opSimpNac.
_REG_ESP_TRIB_NACIONAL = {0: 0, 1: 3, 2: 2, 3: 6, 4: 1, 5: 0, 6: 0}


def op_simp_nac(simples_abrasf: int, regime_abrasf: int) -> int:
    """opSimpNac: 1=Não optante, 2=MEI, 3=ME/EPP (ABRASF: simples 1=sim, 2=não; regime 5=MEI)."""
    if simples_abrasf == 2:
        return 1
    return 2 if regime_abrasf == 5 else 3


def reg_esp_trib(regime_abrasf: int) -> int:
    """regEspTrib nacional a partir do RegimeEspecialTributacao ABRASF."""
    if regime_abrasf not in _REG_ESP_TRIB_NACIONAL:
        raise ValueError(f"Regime especial ABRASF sem equivalente nacional: {regime_abrasf}")
    return _REG_ESP_TRIB_NACIONAL[regime_abrasf]


def nfse_confere(xml_nfse: Optional[str], documento: str, valor: str, competencia: str) -> bool:
    """True se a NFS-e (XML) é do tomador, valor e competência informados."""
    if not xml_nfse:
        return False
    from decimal import Decimal, InvalidOperation

    root = etree.fromstring(xml_nfse.encode("utf-8"))
    def first(xpath):
        found = root.xpath(f"string(({xpath})[1])")
        return found.strip()
    try:
        mesmo_valor = Decimal(first("//*[local-name()='vServ']")) == Decimal(valor)
    except InvalidOperation:
        return False
    return (
        mesmo_valor
        and first("//*[local-name()='dCompet']") == competencia
        and first("//*[local-name()='toma']/*[local-name()='CNPJ' or local-name()='CPF']") == documento
    )


def encode_xml_for_api(xml_string: str) -> str:
    """Compress XML with GZip and encode to Base64 for API payload."""
    compressed = gzip.compress(xml_string.encode("utf-8"))
    return base64.b64encode(compressed).decode("ascii")


def decode_xml_from_api(base64_gzip_string: str) -> str:
    """Decode Base64 and decompress GZip to get XML string."""
    compressed = base64.b64decode(base64_gzip_string)
    return gzip.decompress(compressed).decode("utf-8")


def map_input_to_dps_xml(input: IssueServiceInvoiceInput) -> str:
    """Convert domain input to DPS XML string."""
    numero_dps = input.numero_dps or "1"
    return build_dps_xml(
        serie_dps=input.serie_dps,
        numero_dps=numero_dps,
        data_competencia=input.competencia,
        tipo_ambiente=input.tipo_ambiente,
        prestador_cnpj=input.prestador_cnpj,
        prestador_razao_social=input.prestador_razao_social,
        prestador_logradouro=input.prestador_endereco_logradouro,
        prestador_numero=input.prestador_endereco_numero,
        prestador_bairro=input.prestador_endereco_bairro,
        prestador_codigo_municipio=input.prestador_endereco_codigo_municipio,
        prestador_uf=input.prestador_endereco_uf,
        prestador_cep=input.prestador_endereco_cep,
        prestador_inscricao_municipal=input.prestador_inscricao_municipal,
        tomador_document=input.tomador_document,
        tomador_tipo_documento=input.tomador_tipo_documento,
        tomador_razao_social=input.tomador_razao_social,
        tomador_logradouro=input.tomador_endereco_logradouro,
        tomador_numero=input.tomador_endereco_numero,
        tomador_bairro=input.tomador_endereco_bairro,
        tomador_codigo_municipio=input.tomador_endereco_codigo_municipio,
        tomador_uf=input.tomador_endereco_uf,
        tomador_cep=input.tomador_endereco_cep,
        servico_codigo=input.servico_codigo,
        codigo_tributacao_municipio=input.codigo_tributacao_municipio,
        servico_discriminacao=input.servico_discriminacao,
        servico_valor=input.servico_valor,
        aliquota=input.aliquota,
        aliquota_simples=input.aliquota_simples,
        iss_retido=input.iss_retido,
        optante_simples_nacional=input.optante_simples_nacional,
        regime_especial_tributacao=input.regime_especial_tributacao,
        incentivo_fiscal=input.incentivo_fiscal,
        versao=input.versao,
    )


def map_cancel_input_to_evento_xml(input: CancelServiceInvoiceInput) -> str:
    """Convert cancel input to evento XML string."""
    return build_evento_cancelamento_xml(
        chave_acesso=input.chave_acesso,
        motivo_codigo=input.motivo_codigo,
        motivo_descricao=input.motivo_descricao,
        cnpj_autor=input.cnpj_autor,
        tipo_ambiente=input.tipo_ambiente,
        data_hora_evento=input.data_hora_evento,
    )


def evento_cancela(json_data: dict, chave_acesso: str) -> bool:
    """True se o GET /nfse/{chave}/eventos/101101/1 lista o cancelamento desta chave.

    A resposta traz `eventos: [{chaveAcesso, tipoEvento: 101101, arquivoXml, ...}]` (provado em 04/11/2026)."""
    return any(e.get("chaveAcesso") == chave_acesso and e.get("tipoEvento") == 101101
               for e in json_data.get("eventos") or [])


def map_json_to_issue_result(json_data: dict, status_code: int) -> IssueServiceInvoiceResult:
    """Map SEFIN JSON response to domain issue result."""
    if status_code >= 400:
        raw_errors = json_data.get("erros") or json_data.get("errors") or []
        errors = []
        for e in raw_errors if isinstance(raw_errors, list) else []:
            errors.append({
                "codigo": e.get("codigo") or e.get("Codigo") or "UNKNOWN",
                "descricao": e.get("descricao") or e.get("Descricao") or str(e),
            })
        return IssueServiceInvoiceResult(success=False, errors=errors)

    nfse_xml = None
    raw_nfse = json_data.get("nfseXmlGZipB64")
    if raw_nfse:
        try:
            nfse_xml = decode_xml_from_api(raw_nfse)
        except Exception:
            pass

    return IssueServiceInvoiceResult(
        success=True,
        chave_acesso=json_data.get("chaveAcesso"),
        id_dps=json_data.get("idDPS"),
        data_hora_processamento=json_data.get("dataHoraProcessamento"),
        xml_nfse=nfse_xml,
        errors=[],
    )


def map_json_to_query_result(json_data: dict, status_code: int) -> QueryServiceInvoiceResult:
    """Map SEFIN JSON response to domain query result."""
    if status_code >= 400:
        raw_errors = json_data.get("erros") or json_data.get("errors") or []
        errors = []
        for e in raw_errors if isinstance(raw_errors, list) else []:
            errors.append({
                "codigo": e.get("codigo") or e.get("Codigo") or "UNKNOWN",
                "descricao": e.get("descricao") or e.get("Descricao") or str(e),
            })
        return QueryServiceInvoiceResult(success=False, errors=errors)

    nfse_xml = None
    raw_nfse = json_data.get("nfseXmlGZipB64")
    if raw_nfse:
        try:
            nfse_xml = decode_xml_from_api(raw_nfse)
        except Exception:
            pass

    return QueryServiceInvoiceResult(
        success=True,
        chave_acesso=json_data.get("chaveAcesso"),
        xml_nfse=nfse_xml,
        status="autorizada",  # inferred from successful query
        errors=[],
    )


def map_json_to_cancel_result(json_data: dict, status_code: int) -> CancelServiceInvoiceResult:
    """Map SEFIN JSON response to domain cancel result."""
    if status_code >= 400:
        raw_errors = json_data.get("erros") or json_data.get("errors") or []
        errors = []
        for e in raw_errors if isinstance(raw_errors, list) else []:
            errors.append({
                "codigo": e.get("codigo") or e.get("Codigo") or "UNKNOWN",
                "descricao": e.get("descricao") or e.get("Descricao") or str(e),
            })
        return CancelServiceInvoiceResult(success=False, errors=errors)

    evento_xml = None
    raw_evento = json_data.get("eventoXmlGZipB64")
    if raw_evento:
        try:
            evento_xml = decode_xml_from_api(raw_evento)
        except Exception:
            pass

    return CancelServiceInvoiceResult(success=True, xml_evento=evento_xml, errors=[])


def map_json_to_municipal_agreement(json_data: dict) -> MunicipalAgreementResult:
    """Map SEFIN JSON to municipal agreement result."""
    conveniado = json_data.get("conveniado", False)
    if isinstance(conveniado, str):
        conveniado = conveniado.lower() in ("true", "1", "sim", "s")
    return MunicipalAgreementResult(
        conveniado=conveniado,
        data_adesao=json_data.get("dataAdesao"),
        regras_especiais=json_data.get("regrasEspeciais") or [],
    )


def map_json_to_service_parameters(json_data: dict) -> ServiceTaxParameterResult:
    """Map SEFIN JSON to service tax parameter result."""
    return ServiceTaxParameterResult(
        aliquotas=json_data.get("aliquotas") or [],
        regimes_especiais=json_data.get("regimesEspeciais") or [],
        deducoes=json_data.get("deducoes") or [],
    )


def map_json_to_retentions(json_data: dict) -> ContributorRetentionResult:
    """Map SEFIN JSON to contributor retention result."""
    return ContributorRetentionResult(
        retencoes=json_data.get("retencoes") or [],
    )


def map_json_to_benefits(json_data: dict) -> ContributorBenefitResult:
    """Map SEFIN JSON to contributor benefit result."""
    return ContributorBenefitResult(
        beneficios=json_data.get("beneficios") or [],
    )
