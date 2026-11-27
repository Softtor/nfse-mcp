"""Cancelamento pelo Emissor Nacional: evento pelo XSD oficial, prévia sem envio e resposta perdida."""

import pytest
from lxml import etree

from nfse_mcp.errors import ValidationError
from nfse_mcp.nacional.evento_xml_builder import build_evento_cancelamento_xml
from nfse_mcp.nacional.xsd_validator import XsdValidator

CHAVE = "53001082211222333000181000000000000126116228598296"
MOTIVO = "Nota de teste emitida em producao restrita"


def _evento(tipo_ambiente=2, motivo="1", descricao=MOTIVO):
    return build_evento_cancelamento_xml(
        chave_acesso=CHAVE, motivo_codigo=motivo, motivo_descricao=descricao,
        cnpj_autor="11222333000181", tipo_ambiente=tipo_ambiente,
    )


@pytest.mark.parametrize("tipo_ambiente", [1, 2])
def test_evento_valida_no_xsd_oficial_do_leiaute(tipo_ambiente):
    xml = _evento(tipo_ambiente)
    assert XsdValidator().validate_evento(xml) == []
    doc = etree.fromstring(xml.encode())
    assert doc.xpath("string(//*[local-name()='infPedReg']/@Id)") == f"PRE{CHAVE}101101"
    assert doc.xpath("string(//*[local-name()='tpAmb'])") == str(tipo_ambiente)


def test_evento_fora_do_xsd_e_apontado():
    xml = _evento().replace("<cMotivo>1</cMotivo>", "<cMotivo>5</cMotivo>")
    assert XsdValidator().validate_evento(xml)


@pytest.mark.parametrize("descricao", ["x" * 15, "x" * 255])
def test_descricao_nos_limites_e_aceita(descricao):
    assert XsdValidator().validate_evento(_evento(descricao=descricao)) == []


@pytest.mark.parametrize("motivo,descricao", [("3", MOTIVO), ("1", "curto demais"), ("9", "x" * 256)])
def test_motivo_ou_descricao_fora_do_dominio_e_recusado_antes_de_montar(motivo, descricao):
    with pytest.raises(ValidationError):
        _evento(motivo=motivo, descricao=descricao)


# ---------------------------------------------------------------------------
# Serviço: prévia, envio único, resposta perdida
# ---------------------------------------------------------------------------

from nfse_mcp.application.exceptions.application_error import InvoiceError  # noqa: E402
from nfse_mcp.errors import SefinNacionalError  # noqa: E402
from tests.test_sefin_emissao import Provider as _EmissaoProvider, _service  # noqa: E402


class Provider(_EmissaoProvider):
    """Fake com erro de cancelamento e evento já registrado configuráveis."""

    def __init__(self, cancel_error=None, registrado=False):
        super().__init__()
        self.cancel_error = cancel_error
        self.registrado = registrado

    def cancel(self, input):
        if self.cancel_error:
            self.cancelled.append(input)
            raise self.cancel_error
        return super().cancel(input)

    def cancelamento_registrado(self, chave):
        return self.registrado


def _com_nota(tmp_path, provider, status="emitida"):
    svc = _service(tmp_path, provider)
    svc._log_service.append_nfse_log({
        "provider": "sefin_nacional", "date": "2026-11-04", "client_name": "TOMADOR TESTE LTDA",
        "valor": "8500.00", "competencia": "2026-11-01", "status": status, "chave_acesso": CHAVE,
    })
    return svc


def test_previa_nao_envia_e_mostra_a_nota(tmp_path):
    provider = Provider()
    previa = _com_nota(tmp_path, provider).cancel_invoice(CHAVE, "1", MOTIVO)
    assert provider.cancelled == []
    assert previa == {"enviado": False, "ambiente": "production", "numero": "1", "tomador": "TOMADOR TESTE LTDA",
                      "valor": "8500.00", "competencia": "2026-11-01", "chave_acesso": CHAVE}


def test_previa_ja_valida_motivo(tmp_path):
    with pytest.raises(ValidationError):
        _com_nota(tmp_path, Provider()).cancel_invoice(CHAVE, "1", "curto")


@pytest.mark.parametrize("outra", [{"provider": "sefin_nacional", "chave_acesso": "5" * 50, "status": "emitida"},
                                   {"provider": "abrasf", "chave_acesso": CHAVE, "status": "emitida"}])
def test_nota_fora_do_log_e_recusada(tmp_path, outra):
    provider = Provider()
    svc = _service(tmp_path, provider)
    svc._log_service.append_nfse_log(outra)
    with pytest.raises(InvoiceError, match="nao esta no log"):
        svc.cancel_invoice(CHAVE, "1", MOTIVO, confirmar=True)
    assert provider.cancelled == []


@pytest.mark.parametrize("status", ["pendente", "cancelada"])
def test_nota_nao_emitida_e_recusada(tmp_path, status):
    provider = Provider()
    with pytest.raises(InvoiceError, match=status):
        _com_nota(tmp_path, provider, status).cancel_invoice(CHAVE, "1", MOTIVO, confirmar=True)
    assert provider.cancelled == []


def test_confirmado_envia_uma_vez_com_tpamb_do_ambiente_e_marca_cancelada(tmp_path):
    provider = Provider()
    svc = _com_nota(tmp_path, provider)
    r = svc.cancel_invoice(CHAVE, "2", MOTIVO, confirmar=True)
    assert r["enviado"] is True and r["numero"] == "1" and r["tomador"] == "TOMADOR TESTE LTDA"
    [enviado] = provider.cancelled
    assert (enviado.chave_acesso, enviado.motivo_codigo, enviado.tipo_ambiente) == (CHAVE, "2", 1)
    assert enviado.cnpj_autor == "11222333000181"
    assert svc._log_service.load_nfse_log()[0]["status"] == "cancelada"
    [canc] = svc._log_service.load_cancel_log()
    assert canc == {"nfse_number": "1", "data_emissao": "2026-11-04", "data_cancelamento": svc._today_str(),
                    "valor": "8500.00", "motivo_descricao": MOTIVO, "client_name": "TOMADOR TESTE LTDA",
                    "chave_acesso": CHAVE, "provider": "sefin_nacional"}


def test_ja_cancelada_no_governo_marca_sem_reenviar(tmp_path):
    provider = Provider(registrado=True)
    svc = _com_nota(tmp_path, provider)
    assert svc.cancel_invoice(CHAVE, "1", MOTIVO, confirmar=True)["enviado"] is True
    assert provider.cancelled == []
    assert svc._log_service.load_nfse_log()[0]["status"] == "cancelada"


def test_recusa_sobe_com_complemento_e_nao_marca(tmp_path):
    erro = SefinNacionalError("Erro SEFIN Nacional (HTTP 400)", code="HTTP_400",
                              raw_errors=[{"codigo": "E1234", "descricao": "Campo X invalido"}])
    svc = _com_nota(tmp_path, Provider(cancel_error=erro))
    with pytest.raises(InvoiceError) as exc:
        svc.cancel_invoice(CHAVE, "1", MOTIVO, confirmar=True)
    assert exc.value.errors == [{"codigo": "E1234", "descricao": "Campo X invalido"}]
    assert svc._log_service.load_nfse_log()[0]["status"] == "emitida"


@pytest.mark.parametrize("registrado_depois,status", [(True, "cancelada"), (False, "emitida")])
def test_resposta_perdida_so_marca_se_o_governo_confirmar(tmp_path, registrado_depois, status):
    provider = Provider(cancel_error=SefinNacionalError("timeout", code="TIMEOUT"))
    provider.cancelamento_registrado = lambda chave: bool(provider.cancelled) and registrado_depois
    svc = _com_nota(tmp_path, provider)
    if registrado_depois:
        assert svc.cancel_invoice(CHAVE, "1", MOTIVO, confirmar=True)["enviado"] is True
    else:
        with pytest.raises(InvoiceError, match="conferir"):
            svc.cancel_invoice(CHAVE, "1", MOTIVO, confirmar=True)
    assert len(provider.cancelled) == 1
    assert svc._log_service.load_nfse_log()[0]["status"] == status


def test_resposta_perdida_e_consulta_falhando_nao_marca(tmp_path):
    provider = Provider(cancel_error=SefinNacionalError("timeout", code="TIMEOUT"))
    svc = _com_nota(tmp_path, provider)
    provider.cancelamento_registrado = lambda chave: (_ for _ in ()).throw(SefinNacionalError("x", code="TIMEOUT")) \
        if provider.cancelled else False
    with pytest.raises(InvoiceError, match="conferir"):
        svc.cancel_invoice(CHAVE, "1", MOTIVO, confirmar=True)
    assert svc._log_service.load_nfse_log()[0]["status"] == "emitida"


# ---------------------------------------------------------------------------
# Provider: assinatura e consulta do evento (respostas reais da produção restrita, 04/11/2026)
# ---------------------------------------------------------------------------

import json  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from nfse_mcp.ports.service_invoice_provider import CancelServiceInvoiceInput  # noqa: E402
from nfse_mcp.sefin_nacional.provider import SefinNacionalProvider  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _provider(get_evento=None):
    client = MagicMock()
    client.get_evento.side_effect = get_evento
    client.post_evento.return_value = {}
    signer = MagicMock()
    signer.sign_xml.return_value = "<pedRegEvento/>"
    config = MagicMock(skip_xsd_validation=False)
    return SefinNacionalProvider(config, cert=MagicMock(), signer=signer, client=client), client, signer


def test_cancel_assina_apontando_o_id_do_pedido():
    provider, client, signer = _provider()
    provider.cancel(CancelServiceInvoiceInput(CHAVE, "1", MOTIVO, "11222333000181", tipo_ambiente=2))
    assert signer.sign_xml.call_args.kwargs == {"reference_uri": f"#PRE{CHAVE}101101"}
    assert client.post_evento.call_args.args[0] == CHAVE


def test_cancelamento_registrado_le_a_resposta_real():
    resposta = json.loads((FIXTURES / "sefin_evento_101101_cancelada.json").read_text())
    provider, client, _ = _provider(get_evento=lambda *a: resposta)
    assert provider.cancelamento_registrado(CHAVE) is True
    assert client.get_evento.call_args.args == (CHAVE, "101101")
    assert provider.cancelamento_registrado("5" * 50) is False


def test_sem_evento_o_governo_responde_404_e_vale_false():
    corpo = json.loads((FIXTURES / "sefin_evento_101101_404.json").read_text())

    def nao_tem(*a):
        raise SefinNacionalError("Erro SEFIN Nacional (HTTP 404)", code="HTTP_404", raw_errors=[corpo])

    assert _provider(get_evento=nao_tem)[0].cancelamento_registrado(CHAVE) is False


def test_outro_erro_na_consulta_do_evento_sobe():
    def fora(*a):
        raise SefinNacionalError("timeout", code="TIMEOUT")

    with pytest.raises(SefinNacionalError):
        _provider(get_evento=fora)[0].cancelamento_registrado(CHAVE)


def test_evento_fora_do_xsd_nao_e_enviado():
    provider, client, _ = _provider()
    provider.validator = MagicMock()
    provider.validator.validate_evento.return_value = ["erro"]
    with pytest.raises(ValidationError):
        provider.cancel(CancelServiceInvoiceInput(CHAVE, "1", MOTIVO, "11222333000181"))
    client.post_evento.assert_not_called()


def test_resultado_sem_sucesso_nao_marca(tmp_path):
    provider = Provider()
    provider.simulate_errors = {"cancel": [{"codigo": "E1", "descricao": "recusa"}]}
    svc = _com_nota(tmp_path, provider)
    with pytest.raises(InvoiceError) as exc:
        svc.cancel_invoice(CHAVE, "1", MOTIVO, confirmar=True)
    assert exc.value.errors == [{"codigo": "E1", "descricao": "recusa"}]
    assert svc._log_service.load_nfse_log()[0]["status"] == "emitida"
