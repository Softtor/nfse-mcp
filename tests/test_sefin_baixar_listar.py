"""Baixar (XML + PDF do ADN quando houver) e listar NFS-e nacionais do log local."""

import pytest

from nfse_mcp.application.exceptions.application_error import InvoiceError
from nfse_mcp.application.services.sefin_nacional_service import nfse_nacionais
from nfse_mcp.ports.service_invoice_provider import QueryServiceInvoiceResult
from nfse_mcp.presentation.mcp.formatters import format_cancelamento_nacional, format_lista_nacional
from tests.test_sefin_emissao import Provider as _EmissaoProvider, _service

CHAVE = "53001082211222333000181000000000001626112150071927"


class Provider(_EmissaoProvider):
    def __init__(self, pdf=None):
        super().__init__()
        self.pdf = pdf

    def query_by_access_key(self, access_key):
        self.queried_keys.append(access_key)
        return QueryServiceInvoiceResult(success=True, chave_acesso=access_key, xml_nfse="<NFSe>16</NFSe>")

    def danfse_pdf(self, access_key):
        return self.pdf


def test_baixa_xml_com_nome_pelo_numero_e_devolve_link(tmp_path):
    r = _service(tmp_path, Provider()).baixar_nfse(CHAVE)
    xml = tmp_path / "xml" / f"NFSe-16-{CHAVE}.xml"
    assert xml.read_text() == "<NFSe>16</NFSe>"
    assert r == {"numero": "16", "xml": str(xml), "pdf": None, "link": "https://www.nfse.gov.br/consultapublica"}


def test_baixa_pdf_quando_o_adn_devolve(tmp_path):
    destino = tmp_path / "outra"
    r = _service(tmp_path, Provider(pdf=b"%PDF-1.4 x")).baixar_nfse(CHAVE, str(destino))
    assert (destino / f"NFSe-16-{CHAVE}.pdf").read_bytes() == b"%PDF-1.4 x"
    assert r["pdf"] == str(destino / f"NFSe-16-{CHAVE}.pdf")


@pytest.mark.parametrize("chave", ["../../etc/passwd", CHAVE[:-1], CHAVE + "0", CHAVE[:30] + "/" + CHAVE[31:]])
def test_chave_fora_do_formato_e_recusada_sem_rede(tmp_path, chave):
    provider = Provider()
    with pytest.raises(InvoiceError):
        _service(tmp_path, provider).baixar_nfse(chave)
    assert provider.queried_keys == []


def test_consulta_sem_xml_nao_grava(tmp_path):
    provider = Provider()
    for vazio in [QueryServiceInvoiceResult(success=False, errors=[{"codigo": "E1"}]),
                  QueryServiceInvoiceResult(success=True, chave_acesso=CHAVE, xml_nfse=None)]:
        provider.query_by_access_key = lambda k, r=vazio: r
        with pytest.raises(InvoiceError):
            _service(tmp_path, provider).baixar_nfse(CHAVE)
    assert not (tmp_path / "xml").exists()


def test_baixa_de_novo_em_pasta_aninhada(tmp_path):
    svc = _service(tmp_path, Provider())
    destino = tmp_path / "a" / "b"
    svc.baixar_nfse(CHAVE, str(destino))
    assert svc.baixar_nfse(CHAVE, str(destino))["xml"] == str(destino / f"NFSe-16-{CHAVE}.xml")


LOG = [
    {"provider": "abrasf", "date": "2026-11-04", "valor": "1.00"},
    {"provider": "sefin_nacional", "date": "2026-10-31", "numero_dps": "2", "status": "emitida"},
    {"provider": "sefin_nacional", "date": "2026-11-04", "numero_dps": "3", "status": "cancelada",
     "client_name": "TOMADOR TESTE", "valor": "8500.00", "chave_acesso": CHAVE},
    {"provider": "sefin_nacional", "date": "2026-11-05", "numero_dps": "4", "status": "pendente"},
]


@pytest.mark.parametrize("inicio,fim,dps", [("", "", ["2", "3", "4"]), ("2026-11-01", "", ["3", "4"]),
                                            ("", "2026-11-04", ["2", "3"]), ("2026-11-04", "2026-11-04", ["3"])])
def test_lista_so_nacionais_no_periodo(inicio, fim, dps):
    assert [e["numero_dps"] for e in nfse_nacionais(LOG, inicio, fim)] == dps


def test_lista_formatada_mostra_status_e_chave_e_o_limite():
    texto = format_lista_nacional(nfse_nacionais(LOG, "2026-11-04", "2026-11-04"))
    assert "cancelada" in texto and CHAVE in texto and "TOMADOR TESTE" in texto and "8500.00" in texto
    assert "emitidas por esta ferramenta" in texto
    assert "Nenhuma" in format_lista_nacional([])


@pytest.mark.parametrize("enviado,frase", [(False, "confirmar=True"), (True, "CANCELADA")])
def test_resposta_do_cancelamento_repete_numero_tomador_valor_e_ambiente(enviado, frase):
    texto = format_cancelamento_nacional({"enviado": enviado, "ambiente": "production", "numero": "16",
                                          "tomador": "TOMADOR TESTE", "valor": "8500.00", "competencia": "2026-11-01",
                                          "chave_acesso": CHAVE})
    assert all(p in texto for p in [frase, "16", "TOMADOR TESTE", "8500.00", "production", CHAVE])


# ---------------------------------------------------------------------------
# Provider/cliente: DANFSe vem do ADN; qualquer coisa que não seja PDF vira None
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock  # noqa: E402

import requests  # noqa: E402

from nfse_mcp.errors import SefinNacionalError  # noqa: E402
from nfse_mcp.sefin_nacional.client import SefinNacionalClient  # noqa: E402
from nfse_mcp.sefin_nacional.provider import SefinNacionalProvider  # noqa: E402


@pytest.mark.parametrize("resposta,esperado", [(b"%PDF-1.7", b"%PDF-1.7"), (b"<html>", None),
                                               (SefinNacionalError("503", code="HTTP_503"), None)])
def test_danfse_pdf_so_devolve_pdf(resposta, esperado):
    client = MagicMock()
    client.get_danfse.side_effect = [resposta]
    provider = SefinNacionalProvider(MagicMock(), cert=MagicMock(), signer=MagicMock(), client=client)
    assert provider.danfse_pdf(CHAVE) == esperado


@pytest.mark.parametrize("ambiente,url", [("production", "https://adn.nfse.gov.br/danfse/"),
                                          ("production_restricted", "https://adn.producaorestrita.nfse.gov.br/danfse/")])
def test_danfse_e_pedido_ao_adn_do_ambiente(monkeypatch, ambiente, url):
    config = MagicMock(environment=ambiente, base_url="https://sefin.invalid", timeout=1)
    c = SefinNacionalClient(config, cert=None)
    monkeypatch.setattr(c, "_get_cert_files", lambda: ("c.pem", "k.pem"))
    pedido = {}

    def fake_get(u, **kw):
        pedido.update(url=u, accept=kw["headers"]["Accept"])
        return MagicMock(status_code=200, content=b"%PDF")

    monkeypatch.setattr(requests, "get", fake_get)
    assert c.get_danfse(CHAVE) == b"%PDF"
    assert pedido == {"url": url + CHAVE, "accept": "application/pdf"}


# ---------------------------------------------------------------------------
# Tools MCP
# ---------------------------------------------------------------------------

from nfse_mcp.presentation.mcp import tools  # noqa: E402


@pytest.fixture
def svc(tmp_path, monkeypatch):
    s = _service(tmp_path, Provider())
    s._log_service.append_nfse_log({**LOG[2], "status": "emitida", "competencia": "2026-11-01"})
    monkeypatch.setattr(tools.container, "sefin_service", lambda: s)
    return s


def test_tools_novas_registradas():
    nomes = {f.__name__ for f in tools.TOOL_REGISTRY}
    assert {"baixar_nfse_nacional", "list_nfse_nacional", "cancelar_nfse_nacional"} <= nomes


def test_tool_cancelar_sem_confirmar_so_mostra_previa(svc):
    texto = tools.cancelar_nfse_nacional(CHAVE, "1", "Nota emitida com valor errado")
    assert "NADA FOI ENVIADO" in texto and "TOMADOR TESTE" in texto
    assert svc._log_service.load_nfse_log()[0]["status"] == "emitida"


def test_tool_cancelar_mostra_erro_com_detalhe(svc):
    assert tools.cancelar_nfse_nacional(CHAVE, "1", "curto").startswith("Erro:")
    assert "nao esta no log" in tools.cancelar_nfse_nacional("5" * 50, "1", "Nota emitida com valor errado")


def test_tools_listar_e_baixar(svc, tmp_path):
    assert CHAVE in tools.list_nfse_nacional("2026-11-01", "2026-11-30")
    texto = tools.baixar_nfse_nacional(CHAVE)
    assert "NFS-e 16 baixada" in texto and "nao gerado" in texto
    assert tools.baixar_nfse_nacional("../x").startswith("Erro:")


@pytest.mark.parametrize("status", [400, 503])
def test_danfse_com_erro_http_sobe_como_erro_da_sefin(monkeypatch, status):
    c = SefinNacionalClient(MagicMock(environment="production", timeout=1), cert=None)
    monkeypatch.setattr(c, "_get_cert_files", lambda: ("c.pem", "k.pem"))
    monkeypatch.setattr(requests, "get", lambda u, **kw: MagicMock(status_code=status, content=b""))
    with pytest.raises(SefinNacionalError, match=str(status)):
        c.get_danfse(CHAVE)


def test_get_evento_pede_o_primeiro_evento_do_tipo(monkeypatch):
    c = SefinNacionalClient(MagicMock(base_url="https://sefin.invalid"), cert=None)
    pedidos = []
    monkeypatch.setattr(c, "_request", lambda m, path, **kw: pedidos.append((m, path)) or {})
    c.get_evento(CHAVE, "101101")
    assert pedidos == [("GET", f"/nfse/{CHAVE}/eventos/101101/1")]


from nfse_mcp.application.exceptions.application_error import InvoiceError as _IE  # noqa: E402
from nfse_mcp.errors import ValidationError  # noqa: E402


@pytest.mark.parametrize("erro,trecho", [
    (_IE("recusado", errors=[{"codigo": "E1234", "descricao": "Campo X"}]), "Erro: recusado — [E1234] Campo X"),
    (SefinNacionalError("http", code="HTTP_400", raw_errors=[{"codigo": "E9", "descricao": "Y"}]), "Erro: http — [E9] Y"),
    (ValidationError("xsd", validation_errors=["linha 1"]), "Erro: xsd — linha 1"),
    (_IE("sem detalhe"), "Erro: sem detalhe"),
])
def test_erro_da_tool_traz_o_detalhe_do_governo(erro, trecho):
    assert tools._erro(erro) == trecho


def test_pdf_com_erro_de_rede_vira_erro_do_provider_e_nao_excecao_crua(monkeypatch):
    c = SefinNacionalClient(MagicMock(environment="production", base_url="https://sefin.invalid", timeout=1), cert=None)
    monkeypatch.setattr(c, "_get_cert_files", lambda: ("c.pem", "k.pem"))

    def cai(*args, **kwargs):
        raise requests.ConnectionError("sem rede")

    monkeypatch.setattr(requests, "get", cai)
    with pytest.raises(SefinNacionalError, match="ConnectionError") as erro:
        c.get_danfse(CHAVE)
    assert erro.value.code == "TRANSPORT"
    provider = SefinNacionalProvider.__new__(SefinNacionalProvider)
    provider.client = MagicMock(get_danfse=MagicMock(side_effect=erro.value))
    assert provider.danfse_pdf(CHAVE) is None  # o download segue só com XML + link
