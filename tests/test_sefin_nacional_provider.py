"""Unit tests for SefinNacionalProvider."""

import pytest
from unittest.mock import MagicMock

from nfse_mcp.ports.service_invoice_provider import (
    CancelServiceInvoiceInput,
    IssueServiceInvoiceInput,
)
from nfse_mcp.errors import (
    MunicipalityNotEnabledError,
    MunicipalityNotSupportedError,
    SefinNacionalError,
    ValidationError,
)
from nfse_mcp.sefin_nacional.provider import SefinNacionalProvider
from tests.fakes import FakeSefinNacionalProvider


def _make_input() -> IssueServiceInvoiceInput:
    return IssueServiceInvoiceInput(
        prestador_cnpj="11222333000181",
        prestador_razao_social="PRESTADOR TESTE LTDA",
        prestador_endereco_logradouro="Rua Exemplo",
        prestador_endereco_numero="123",
        prestador_endereco_bairro="Centro",
        prestador_endereco_codigo_municipio="5300108",
        prestador_endereco_uf="DF",
        prestador_endereco_cep="70000000",
        tomador_document="12345678000190",
        tomador_razao_social="CLIENTE TOMADOR LTDA",
        tomador_endereco_logradouro="Av Cliente",
        tomador_endereco_numero="456",
        tomador_endereco_bairro="Bairro Cliente",
        tomador_endereco_codigo_municipio="5300108",
        tomador_endereco_uf="DF",
        tomador_endereco_cep="70000000",
        servico_codigo="1.07",
        servico_discriminacao="Consultoria em TI",
        servico_valor="5000.00",
        competencia="2026-05-01",
    )


class TestFakeProvider:
    """Tests using the in-memory fake provider."""

    def test_issue_success(self):
        provider = FakeSefinNacionalProvider()
        input_data = _make_input()
        result = provider.issue(input_data)

        assert result.success is True
        assert result.chave_acesso is not None
        assert len(result.chave_acesso) == 50
        assert result.xml_nfse is not None
        assert len(provider.issued) == 1

    def test_issue_error(self):
        provider = FakeSefinNacionalProvider(simulate_errors={
            "issue": [{"codigo": "E001", "descricao": "Erro fiscal"}]
        })
        result = provider.issue(_make_input())

        assert result.success is False
        assert any(e["codigo"] == "E001" for e in result.errors)

    def test_query_by_access_key_success(self):
        provider = FakeSefinNacionalProvider()
        result = provider.query_by_access_key("12345")

        assert result.success is True
        assert result.chave_acesso == "12345"
        assert result.status == "autorizada"

    def test_cancel_success(self):
        provider = FakeSefinNacionalProvider()
        input_data = CancelServiceInvoiceInput(
            chave_acesso="12345",
            motivo_codigo="1",
            motivo_descricao="Erro na emissao",
            cnpj_autor="11222333000181",
        )
        result = provider.cancel(input_data)

        assert result.success is True
        assert result.xml_evento is not None

    def test_convenio_supported(self):
        provider = FakeSefinNacionalProvider()
        result = provider.get_agreement_by_municipality("5300108")
        assert result.conveniado is True

    def test_convenio_not_supported(self):
        provider = FakeSefinNacionalProvider(simulate_errors={"convenio": True})
        result = provider.get_agreement_by_municipality("9999999")
        assert result.conveniado is False


class TestSefinNacionalProviderValidation:
    """Tests for validation logic in the real provider (with mocked client)."""

    def test_issue_with_validation_error(self):
        config = MagicMock()
        config.skip_xsd_validation = False
        cert = MagicMock()

        validator = MagicMock()
        validator.validate_dps.return_value = ["Element 'nDPS' is missing"]

        provider = SefinNacionalProvider(
            config=config,
            cert=cert,
            validator=validator,
            client=MagicMock(),
            signer=MagicMock(),
        )

        with pytest.raises(ValidationError) as exc_info:
            provider.issue(_make_input())

        assert "XML DPS invalido" in str(exc_info.value)
        assert "Element 'nDPS' is missing" in exc_info.value.validation_errors

    def test_municipality_not_supported(self):
        config = MagicMock()
        cert = MagicMock()

        client = MagicMock()
        client.get_convenio.return_value = {"conveniado": False}

        provider = SefinNacionalProvider(
            config=config,
            cert=cert,
            client=client,
        )

        with pytest.raises(MunicipalityNotSupportedError) as exc_info:
            provider.get_agreement_by_municipality("9999999")

        assert "9999999" in str(exc_info.value)

    def test_issue_e0039_raises_municipality_not_enabled(self):
        config = MagicMock()
        config.skip_xsd_validation = True
        cert = MagicMock()

        client = MagicMock()
        exc = SefinNacionalError(
            "Erro SEFIN Nacional (HTTP 422)",
            code="HTTP_422",
            raw_errors=[{"codigo": "E0039", "descricao": "Municipio nao habilitado"}],
        )
        client.post_nfse.side_effect = exc

        cache = MagicMock()

        signer = MagicMock()
        signer.sign_xml.return_value = "<DPS></DPS>"

        provider = SefinNacionalProvider(
            config=config,
            cert=cert,
            client=client,
            signer=signer,
            cache=cache,
        )

        with pytest.raises(MunicipalityNotEnabledError) as exc_info:
            provider.issue(_make_input())

        assert "5300108" in str(exc_info.value)
        cache.set.assert_called_once_with(
            "5300108",
            status="not_enabled",
            error_code="E0039",
            source="api_probe",
        )

    def test_get_agreement_with_external_data(self):
        config = MagicMock()
        cert = MagicMock()

        client = MagicMock()
        client.get_convenio.return_value = {"conveniado": True, "dataAdesao": "2025-01-01"}

        data_loader = MagicMock()
        data_loader.get_status.return_value = MagicMock(
            emissor_nacional=True,
        )

        cache = MagicMock()

        provider = SefinNacionalProvider(
            config=config,
            cert=cert,
            client=client,
            data_loader=data_loader,
            cache=cache,
        )

        result = provider.get_agreement_by_municipality("5300108")

        assert result.conveniado is True
        assert result.emissores_publicos_habilitados is True
        cache.set.assert_called_once_with(
            "5300108",
            status="enabled",
            source="external_data",
        )


def test_issue_assina_referenciando_o_id_do_infdps():
    # XSD oficial: Reference URI tem minLength 2 — URI="" é recusada (E1235)
    config = MagicMock()
    config.skip_xsd_validation = True
    client = MagicMock()
    client.post_nfse.return_value = {"chaveAcesso": "C" * 50}
    signer = MagicMock()
    signer.sign_xml.return_value = "<DPS/>"
    provider = SefinNacionalProvider(config=config, cert=MagicMock(), client=client, signer=signer, cache=MagicMock())
    data = _make_input()
    data.numero_dps = "7"
    provider.issue(data)
    assert signer.sign_xml.call_args.kwargs["reference_uri"] == "#DPS530010821122233300018100001000000000000007"
