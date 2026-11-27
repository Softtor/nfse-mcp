"""Tests for Application Services."""

import pytest
from pathlib import Path

from nfse_mcp.models import Client
from nfse_mcp.client_store import ClientStore
from nfse_mcp.application.services.client_service import ClientApplicationService
from nfse_mcp.application.services.invoice_log_service import InvoiceLogService
from nfse_mcp.application.services.sefin_nacional_service import SefinNacionalApplicationService
from nfse_mcp.application.dto.commands import IssueInvoiceCommand, QueryParametersCommand
from nfse_mcp.config import Config, ProviderConfig, ServiceDefaults
from nfse_mcp.sefin_nacional.config import SefinNacionalConfig
from tests.fakes import FakeSefinNacionalProvider


# ---------------------------------------------------------------------------
# ClientApplicationService tests
# ---------------------------------------------------------------------------

@pytest.fixture
def client_service(tmp_path: Path):
    store = ClientStore(tmp_path)
    return ClientApplicationService(store)


class TestClientApplicationService:
    def test_register_client(self, client_service: ClientApplicationService):
        client = client_service.register_client("12345678000195", "Empresa Teste")
        assert client.document == "12345678000195"
        assert client.razao_social == "Empresa Teste"
        assert client.document_type == "cnpj"

    def test_find_or_register_client_new(self, client_service: ClientApplicationService):
        client = client_service.find_or_register_client("12345678000195")
        assert client.document == "12345678000195"

    def test_find_or_register_client_existing(self, client_service: ClientApplicationService):
        client_service.register_client("12345678000195", "Empresa Teste")
        client2 = client_service.find_or_register_client("12345678000195")
        assert client2.razao_social == "Empresa Teste"

    def test_ensure_complete_address_fills_defaults(self, client_service: ClientApplicationService):
        # Use CPF (11 digits) to avoid BrasilAPI lookup
        client = client_service.register_client("12345678901", "Pessoa Teste")
        # Clear address fields
        client.endereco = None
        client.numero = None
        client.bairro = None
        client.codigo_municipio = None
        client.uf = None
        client.cep = None

        updated = client_service.ensure_complete_address(client)
        assert updated.endereco == "Rua Nao Informada"
        assert updated.numero == "SN"
        assert updated.bairro == "Nao Informado"
        assert updated.codigo_municipio == "5300108"
        assert updated.uf == "DF"
        assert updated.cep == "70000000"

    def test_list_clients(self, client_service: ClientApplicationService):
        assert client_service.list_clients() == []
        client_service.register_client("12345678000195", "Empresa A")
        client_service.register_client("98765432000100", "Empresa B")
        clients = client_service.list_clients()
        assert len(clients) == 2
        assert {c.razao_social for c in clients} == {"Empresa A", "Empresa B"}

    def test_lookup_cnpj_data_invalid_length(self, client_service: ClientApplicationService):
        result = client_service.lookup_cnpj_data("123")
        assert result is None


# ---------------------------------------------------------------------------
# InvoiceLogService tests
# ---------------------------------------------------------------------------

@pytest.fixture
def log_service(tmp_path: Path):
    return InvoiceLogService(tmp_path)


class TestInvoiceLogService:
    def test_append_and_load_nfse_log(self, log_service: InvoiceLogService):
        log_service.append_nfse_log({"nfse_number": "1", "valor": "100.00"})
        log_service.append_nfse_log({"nfse_number": "2", "valor": "200.00"})
        logs = log_service.load_nfse_log()
        assert len(logs) == 2
        assert logs[0]["nfse_number"] == "1"
        assert logs[1]["valor"] == "200.00"

    def test_append_and_load_cancel_log(self, log_service: InvoiceLogService):
        log_service.append_cancel_log({"nfse_number": "1", "motivo": "Erro"})
        logs = log_service.load_cancel_log()
        assert len(logs) == 1
        assert logs[0]["motivo"] == "Erro"

    def test_load_empty_log(self, log_service: InvoiceLogService):
        assert log_service.load_nfse_log() == []
        assert log_service.load_cancel_log() == []


# ---------------------------------------------------------------------------
# SefinNacionalApplicationService tests
# ---------------------------------------------------------------------------

@pytest.fixture
def sefin_service(tmp_path: Path):
    store = ClientStore(tmp_path)
    client_service = ClientApplicationService(store)
    fake_provider = FakeSefinNacionalProvider()
    config = Config(
        environment="homologation",
        certificate_path="",
        certificate_password="",
        provider=ProviderConfig(
            cnpj="12345678000195",
            im="123456",
            razao_social="Prestador Teste",
            simples_nacional=1,
            regime_tributacao=6,
            incentivo_fiscal=2,
            aliquota_simples="6.00",
        ),
        service_defaults=ServiceDefaults(
            cnae="",
            item_lista_servico="1.07",
            codigo_tributacao_municipio="",
            aliquota="2.00",
            municipio_ibge="5300108",
            iss_retido=2,
            exigibilidade_iss=1,
        ),
        rps_serie="3",
        webservice_url="",
        data_dir=tmp_path,
    )
    sefin_config = SefinNacionalConfig(
        environment="homologation",
        base_url="https://example.com",
        certificate_path="",
        certificate_password="",
        timeout=60,
        max_retries=3,
        debug=False,
        skip_xsd_validation=True,
    )
    log_service = InvoiceLogService(tmp_path)
    service = SefinNacionalApplicationService(
        client_service=client_service,
        invoice_provider=fake_provider,
        parameter_provider=fake_provider,
        config=config,
        sefin_config=sefin_config,
        log_service=log_service,
    )
    return service


class TestSefinNacionalApplicationService:
    def test_issue_invoice_success(self, sefin_service: SefinNacionalApplicationService):
        # Pre-register client to avoid BrasilAPI flakiness
        # Use a non-own-issuer municipality to avoid the emissor-proprio block
        sefin_service._client_service.register_client("12345678000195", "Empresa Teste")
        cmd = IssueInvoiceCommand(
            client_document="12345678000195",
            valor="1000.00",
            discriminacao="Servico de teste",
            competencia="2026-05-01",
            codigo_municipio="3106200",  # Belo Horizonte (not in EMISSOR_PROPRIO_SET)
        )
        result = sefin_service.issue_invoice(cmd)
        assert result.success is True
        assert result.chave_acesso is not None
        assert len(result.chave_acesso) == 50

    def test_issue_invoice_client_without_razao_social(self, sefin_service: SefinNacionalApplicationService):
        # Register client without razao_social (use CPF to avoid auto-lookup)
        # Use a non-own-issuer municipality to avoid the emissor-proprio block
        sefin_service._client_service.register_client("12345678901", "")
        cmd = IssueInvoiceCommand(
            client_document="12345678901",
            valor="1000.00",
            discriminacao="Servico de teste",
            codigo_municipio="3106200",  # Belo Horizonte (not in EMISSOR_PROPRIO_SET)
        )
        from nfse_mcp.application.exceptions.application_error import InvoiceError
        with pytest.raises(InvoiceError, match="nao possui razao social"):
            sefin_service.issue_invoice(cmd)

    def test_query_by_access_key(self, sefin_service: SefinNacionalApplicationService):
        result = sefin_service.query_by_access_key("12345678901234567890123456789012345678901234567890")
        assert result.success is True
        assert result.status == "autorizada"

    def test_query_parameters(self, sefin_service: SefinNacionalApplicationService):
        cmd = QueryParametersCommand(codigo_municipio="5300108", codigo_servico="1.07")
        result = sefin_service.query_parameters(cmd)
        assert "convenio" in result
        assert result["convenio"].conveniado is True
        assert "service_params" in result
        assert len(result["service_params"].aliquotas) == 1

    def test_get_agreement(self, sefin_service: SefinNacionalApplicationService):
        result = sefin_service.get_agreement("5300108")
        assert result.conveniado is True

    def test_get_agreement_emissores_habilitados(self, sefin_service: SefinNacionalApplicationService):
        result = sefin_service.get_agreement("5300108")
        assert result.conveniado is True
        assert result.emissores_publicos_habilitados is True

    def test_issue_invoice_brasilia_pelo_nacional(self, sefin_service: SefinNacionalApplicationService):
        # Brasília (5300108) emite pelo nacional desde 11/2026 (ISS.net recusa optante do Simples)
        sefin_service._client_service.register_client("12345678000195", "Empresa Teste")
        cmd = IssueInvoiceCommand(
            client_document="12345678000195",
            valor="1000.00",
            discriminacao="Servico de teste",
            competencia="2026-11-01",
            codigo_municipio="5300108",
        )
        assert sefin_service.issue_invoice(cmd).success is True
