"""A recusa da SEFIN chega a quem chamou a tool com o código e o motivo, não só "HTTP 400"."""

from types import SimpleNamespace

import pytest

from nfse_mcp.errors import SefinNacionalError
from nfse_mcp.presentation.mcp import tools

RECUSA = SefinNacionalError(
    "Erro SEFIN Nacional (HTTP 400)", code="HTTP_400",
    raw_errors=[{"codigo": "E0310", "descricao": "O código de tributação nacional informado não existe"}],
)


def _recusa(_cmd):
    raise RECUSA


@pytest.mark.parametrize("tool, servico", [
    (tools.emit_nfse_nacional, "sefin_service"),
    (tools.emit_nfse_unificado, "router_service"),
])
def test_emissao_recusada_mostra_codigo_e_motivo(monkeypatch, tool, servico):
    monkeypatch.setattr(tools.container, servico, lambda: SimpleNamespace(issue_invoice=_recusa))
    saida = tool(client_document="45997418000153", valor="1500.00", discriminacao="Suporte em TI")
    assert "[E0310]" in saida and "não existe" in saida


from nfse_mcp.application.exceptions.application_error import InvoiceError  # noqa: E402
from nfse_mcp.errors import MunicipalityNotEnabledError  # noqa: E402

CLIENTE = SimpleNamespace(razao_social="PESSOA TESTE", document="45997418000153")
TOOLS = [(tools.emit_nfse_nacional, "sefin_service"), (tools.emit_nfse_unificado, "router_service")]


def _servico(monkeypatch, servico, issue_invoice):
    monkeypatch.setattr(tools.container, servico, lambda: SimpleNamespace(issue_invoice=issue_invoice))
    monkeypatch.setattr(tools.container, "client_service",
                        lambda: SimpleNamespace(find_or_register_client=lambda _doc: CLIENTE))


def _emite(tool):
    return tool(client_document="45997418000153", valor="1500.00", discriminacao="Suporte em TI",
                competencia="2026-11-01")


def _levanta(erro):
    def issue_invoice(_cmd):
        raise erro
    return issue_invoice


@pytest.mark.parametrize("tool, servico", TOOLS)
def test_codigo_recusado_antes_do_envio_diz_qual_usar(monkeypatch, tool, servico):
    _servico(monkeypatch, servico, _levanta(InvoiceError("Opcoes do subitem 01.07: 01.07.01 (Suporte técnico)")))
    assert _emite(tool) == "Erro: Opcoes do subitem 01.07: 01.07.01 (Suporte técnico)"


@pytest.mark.parametrize("tool, servico", TOOLS)
def test_nota_nacional_emitida_mostra_a_chave(monkeypatch, tool, servico):
    resultado = SimpleNamespace(success=True, chave_acesso="5300108", id_dps="DPS1", data_hora_processamento=None)
    _servico(monkeypatch, servico, lambda _cmd: resultado)
    assert "Chave de Acesso: 5300108" in _emite(tool)


def test_unificado_mostra_nota_do_iss_net(monkeypatch):
    resultado = SimpleNamespace(success=True, chave_acesso=None, numero_nfse="106", numero_rps="95",
                                data_emissao="2026-10-01", url_visualizacao=None, codigo_verificacao=None)
    _servico(monkeypatch, "router_service", lambda _cmd: resultado)
    assert "NFS-e Numero: 106" in _emite(tools.emit_nfse_unificado)


def test_nacional_em_municipio_sem_emissor_nacional(monkeypatch):
    _servico(monkeypatch, "sefin_service", _levanta(MunicipalityNotEnabledError("5300108")))
    assert "E0039" in _emite(tools.emit_nfse_nacional)


def test_nacional_em_municipio_com_emissor_proprio_aponta_o_emit_nfse(monkeypatch):
    monkeypatch.setattr(tools, "MunicipalityDataLoader", lambda: SimpleNamespace(is_emissor_proprio=lambda _c: True))
    assert "emit_nfse'" in _emite(tools.emit_nfse_nacional)
