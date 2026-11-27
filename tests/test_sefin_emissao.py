"""Emissão pelo Emissor Nacional: numeração da DPS, recuperação de resposta perdida e nota pendente."""

import json
from pathlib import Path

import pytest

from nfse_mcp.application.dto.commands import IssueInvoiceCommand
from nfse_mcp.application.exceptions.application_error import InvoiceError
from nfse_mcp.application.services.client_service import ClientApplicationService
from nfse_mcp.application.services.invoice_log_service import InvoiceLogService
from nfse_mcp.application.services.sefin_nacional_service import SefinNacionalApplicationService
from nfse_mcp.client_store import ClientStore
from nfse_mcp.config import Config, ProviderConfig, ServiceDefaults
from nfse_mcp.errors import SefinNacionalError
from nfse_mcp.ports.service_invoice_provider import QueryServiceInvoiceResult
from nfse_mcp.sefin_nacional.config import SefinNacionalConfig
from tests.fakes import FakeSefinNacionalProvider

TOMADOR = "11444777000161"


def _nfse_xml(documento=TOMADOR, valor="8500.00", competencia="2026-11-01"):
    return (
        '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"><infNFSe><DPS><infDPS>'
        f"<dCompet>{competencia}</dCompet><toma><CNPJ>{documento}</CNPJ></toma>"
        f"<valores><vServPrest><vServ>{valor}</vServ></vServPrest></valores>"
        "</infDPS></DPS></infNFSe></NFSe>"
    )


class Provider(FakeSefinNacionalProvider):
    """Fake com erro de emissão e resposta de consulta por DPS configuráveis."""

    def __init__(self, issue_error=None, query=None):
        super().__init__()
        self.issue_error = issue_error
        self.query = query
        self.queried_dps: list[str] = []

    def issue(self, input):
        if self.issue_error:
            self.issued.append(input)
            raise self.issue_error
        return super().issue(input)

    def query_by_dps_id(self, dps_id):
        self.queried_dps.append(dps_id)
        if isinstance(self.query, Exception):
            raise self.query
        return self.query


def _service(tmp_path: Path, provider, aliquota_simples="6.00") -> SefinNacionalApplicationService:
    config = Config(
        environment="production",
        certificate_path="",
        certificate_password="",
        provider=ProviderConfig(
            cnpj="11222333000181", im="1234567", razao_social="PRESTADOR TESTE",
            simples_nacional=1, regime_tributacao=6, incentivo_fiscal=2, aliquota_simples=aliquota_simples,
        ),
        service_defaults=ServiceDefaults(
            cnae="", item_lista_servico="1.07", codigo_tributacao_municipio="107",
            aliquota="2.00", municipio_ibge="5300108", iss_retido=2, exigibilidade_iss=1,
        ),
        rps_serie="3",
        webservice_url="",
        data_dir=tmp_path,
    )
    sefin_config = SefinNacionalConfig(
        environment="production", base_url="https://example.com", certificate_path="",
        certificate_password="", timeout=60, max_retries=3, debug=False, skip_xsd_validation=True,
    )
    client_service = ClientApplicationService(ClientStore(tmp_path))
    client_service.register_client(TOMADOR, "TOMADOR TESTE LTDA")
    return SefinNacionalApplicationService(
        client_service=client_service, invoice_provider=provider, parameter_provider=provider,
        config=config, sefin_config=sefin_config, log_service=InvoiceLogService(tmp_path),
    )


def _cmd(**kw):
    base = dict(
        client_document=TOMADOR, valor="8500.00", discriminacao="Desenvolvimento de software",
        competencia="2026-11-01", codigo_servico="01.04.01", codigo_tributacao_municipio="104",
        codigo_municipio="5300108",
    )
    base.update(kw)
    return IssueInvoiceCommand(**base)


def _log(tmp_path):
    return json.loads((tmp_path / "nfse_log.json").read_text())


def test_dps_sai_com_regime_nacional_e_codigo_municipal(tmp_path):
    provider = Provider()
    _service(tmp_path, provider).issue_invoice(_cmd())
    sent = provider.issued[0]
    assert (sent.optante_simples_nacional, sent.regime_especial_tributacao) == (3, 0)
    assert sent.codigo_tributacao_municipio == "104"
    assert sent.tipo_ambiente == 1
    assert sent.prestador_inscricao_municipal is None  # E0120: CNC do DF sem complemento para a IM


def test_sem_codigo_municipal_nao_usa_o_padrao_do_iss_net(tmp_path):
    # O 107/104 do ISS.net não existe no Emissor Nacional do DF (E0314); cTribMun é opcional
    provider = Provider()
    _service(tmp_path, provider).issue_invoice(_cmd(codigo_tributacao_municipio=None))
    assert provider.issued[0].codigo_tributacao_municipio == ""


def test_numeracao_continua_do_log_e_avanca_mesmo_com_falha(tmp_path):
    (tmp_path / "nfse_log.json").write_text(json.dumps([
        {"provider": "abrasf", "rps_number": 90, "numero_dps": "99"},  # só o nacional conta
        {"provider": "sefin_nacional", "numero_dps": "4"},
    ]))
    provider = Provider(issue_error=SefinNacionalError("recusada", code="HTTP_400"),
                        query=SefinNacionalError("nao achou", code="HTTP_404"))
    service = _service(tmp_path, provider)
    with pytest.raises(SefinNacionalError, match="recusada"):
        service.issue_invoice(_cmd())
    provider.issue_error = None
    service.issue_invoice(_cmd())
    assert [i.numero_dps for i in provider.issued] == ["5", "6"]
    assert _log(tmp_path)[-1]["numero_dps"] == "6"


def test_contador_ilegivel_nao_volta_para_um(tmp_path):
    (tmp_path / "dps_counter.json").write_text("{quebrado")
    provider = Provider()
    with pytest.raises(Exception):
        _service(tmp_path, provider).issue_invoice(_cmd())
    assert provider.issued == []


def test_resposta_perdida_com_nota_igual_vira_sucesso(tmp_path):
    provider = Provider(
        issue_error=SefinNacionalError("timeout", code="TIMEOUT"),
        query=QueryServiceInvoiceResult(success=True, chave_acesso="C" * 50, xml_nfse=_nfse_xml()),
    )
    result = _service(tmp_path, provider).issue_invoice(_cmd())
    assert (result.success, result.chave_acesso) == (True, "C" * 50)
    assert provider.queried_dps == ["DPS530010821122233300018100001000000000000001"]
    assert _log(tmp_path)[-1]["chave_acesso"] == "C" * 50


def test_recusa_do_servidor_sem_nota_relanca_erro_original_sem_pendente(tmp_path):
    provider = Provider(issue_error=SefinNacionalError("E0312 recusada", code="HTTP_400"),
                        query=SefinNacionalError("nao achou", code="HTTP_404"))
    with pytest.raises(SefinNacionalError, match="E0312"):
        _service(tmp_path, provider).issue_invoice(_cmd())
    assert [e["status"] for e in _log(tmp_path)] == ["nao_emitida"]  # não bloqueia a próxima nota


def test_queda_do_processo_no_envio_deixa_a_dps_pendente_no_log(tmp_path):
    # Se o processo cai depois da SEFIN aceitar, só o log guarda a DPS: a próxima emissão a consulta.
    provider = Provider(issue_error=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        _service(tmp_path, provider).issue_invoice(_cmd())
    [entrada] = _log(tmp_path)
    assert (entrada["status"], entrada["numero_dps"]) == ("pendente", "1")

    provider.issue_error = None
    provider.query = QueryServiceInvoiceResult(success=True, chave_acesso="C" * 50, xml_nfse=_nfse_xml())
    with pytest.raises(InvoiceError, match="foi emitida"):
        _service(tmp_path, provider).issue_invoice(_cmd())  # acha a nota pela DPS e não emite outra
    assert provider.queried_dps == ["DPS530010821122233300018100001000000000000001"]
    assert [i.numero_dps for i in provider.issued] == ["1"]
    assert _log(tmp_path)[0]["status"] == "emitida"


def test_nota_recuperada_de_outro_pedido_nao_conta(tmp_path):
    provider = Provider(
        issue_error=SefinNacionalError("timeout", code="TIMEOUT"),
        query=QueryServiceInvoiceResult(success=True, chave_acesso="C" * 50,
                                        xml_nfse=_nfse_xml(valor="800.00")),
    )
    with pytest.raises(InvoiceError, match="pendente"):
        _service(tmp_path, provider).issue_invoice(_cmd())
    assert _log(tmp_path)[-1]["status"] == "pendente"


def test_resposta_perdida_sem_nota_fica_pendente_e_bloqueia_nova_emissao(tmp_path):
    provider = Provider(issue_error=SefinNacionalError("timeout", code="TIMEOUT"),
                        query=SefinNacionalError("nao achou", code="HTTP_404"))
    service = _service(tmp_path, provider)
    with pytest.raises(InvoiceError, match="pendente"):
        service.issue_invoice(_cmd())
    pend = _log(tmp_path)[-1]
    assert (pend["status"], pend["numero_dps"]) == ("pendente", "1")

    # Nova tentativa: consulta a pendente primeiro; ela apareceu, então não emite outra.
    provider.issue_error = None
    provider.query = QueryServiceInvoiceResult(success=True, chave_acesso="P" * 50, xml_nfse=_nfse_xml())
    with pytest.raises(InvoiceError, match="P" * 50):
        service.issue_invoice(_cmd())
    assert len(provider.issued) == 1
    assert _log(tmp_path)[-1]["status"] == "emitida"


def test_pendente_que_nao_existe_e_liberada(tmp_path):
    provider = Provider(issue_error=SefinNacionalError("timeout", code="TIMEOUT"),
                        query=SefinNacionalError("nao achou", code="HTTP_404"))
    service = _service(tmp_path, provider)
    with pytest.raises(InvoiceError):
        service.issue_invoice(_cmd())
    provider.issue_error = None
    result = service.issue_invoice(_cmd())
    assert result.success
    assert [e["status"] for e in _log(tmp_path)] == ["nao_emitida", "emitida"]
    assert [i.numero_dps for i in provider.issued] == ["1", "2"]


def test_pendente_com_consulta_fora_do_ar_continua_bloqueando(tmp_path):
    provider = Provider(issue_error=SefinNacionalError("timeout", code="TIMEOUT"),
                        query=SefinNacionalError("timeout", code="TIMEOUT"))
    service = _service(tmp_path, provider)
    with pytest.raises(InvoiceError):
        service.issue_invoice(_cmd())
    provider.issue_error = None
    with pytest.raises(InvoiceError, match="pendente"):
        service.issue_invoice(_cmd())
    assert len(provider.issued) == 1


def test_percentual_do_simples_vai_na_dps(tmp_path):
    provider = Provider()
    _service(tmp_path, provider).issue_invoice(_cmd())
    assert provider.issued[0].aliquota_simples == "6.00"


def test_optante_sem_percentual_configurado_nao_envia(tmp_path):
    provider = Provider()
    with pytest.raises(InvoiceError, match="NFSE_PROVIDER_ALIQUOTA_SIMPLES"):
        _service(tmp_path, provider, aliquota_simples="").issue_invoice(_cmd())
    assert provider.issued == []


def test_padroes_quando_o_pedido_nao_informa(tmp_path):
    from datetime import date
    provider = Provider()
    _service(tmp_path, provider).issue_invoice(
        _cmd(codigo_municipio=None, codigo_servico=None, competencia=None, aliquota=None)
    )
    sent = provider.issued[0]
    assert sent.prestador_endereco_codigo_municipio == "5300108"
    assert sent.servico_codigo == "010701"  # o 1.07 do ISS.net vira o único desdobro nacional
    assert sent.competencia == date.today().replace(day=1).isoformat()
    assert sent.aliquota == "2.00"


def test_nota_ja_emitida_nao_e_tratada_como_pendente(tmp_path):
    provider = Provider()
    service = _service(tmp_path, provider)
    service.issue_invoice(_cmd())
    service.issue_invoice(_cmd(valor="100.00"))
    assert provider.queried_dps == []
    assert [i.numero_dps for i in provider.issued] == ["1", "2"]


def test_codigo_de_servico_inexistente_nao_gasta_numero_de_dps(tmp_path):
    provider = Provider()
    service = _service(tmp_path, provider)
    with pytest.raises(InvoiceError, match="01.07.01"):
        service.issue_invoice(_cmd(codigo_servico="01.07.05"))
    assert provider.issued == []
    assert not (tmp_path / "dps_counter.json").exists()
