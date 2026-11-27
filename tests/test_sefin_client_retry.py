"""O envio da DPS (POST) não pode ser repetido sozinho: a 1ª tentativa pode ter virado nota."""

import pytest
import requests

from nfse_mcp.errors import SefinNacionalError
from nfse_mcp.sefin_nacional.client import SefinNacionalClient
from nfse_mcp.sefin_nacional.config import SefinNacionalConfig


@pytest.fixture
def client(monkeypatch):
    config = SefinNacionalConfig(
        environment="production_restricted", base_url="https://example.invalid", certificate_path="",
        certificate_password="", timeout=1, max_retries=3, debug=False, skip_xsd_validation=True,
    )
    c = SefinNacionalClient(config, cert=None)
    monkeypatch.setattr(c, "_get_cert_files", lambda: ("c.pem", "k.pem"))
    monkeypatch.setattr("time.sleep", lambda s: None)
    calls = []

    def fake_request(method, url, **kw):
        calls.append(method)
        raise requests.exceptions.Timeout("sem resposta")

    monkeypatch.setattr(requests, "request", fake_request)
    return c, calls


def test_post_com_timeout_nao_reenvia(client):
    c, calls = client
    with pytest.raises(SefinNacionalError) as exc:
        c.post_nfse("payload")
    assert exc.value.code == "TIMEOUT"
    assert calls == ["POST"]


def test_consulta_com_timeout_continua_repetindo(client):
    c, calls = client
    with pytest.raises(SefinNacionalError):
        c.get_dps("DPS123")
    assert calls == ["GET", "GET", "GET"]


def test_recusa_traz_o_complemento_do_erro(monkeypatch):
    config = SefinNacionalConfig(
        environment="production_restricted", base_url="https://example.invalid", certificate_path="",
        certificate_password="", timeout=1, max_retries=3, debug=False, skip_xsd_validation=True,
    )
    c = SefinNacionalClient(config, cert=None)
    monkeypatch.setattr(c, "_get_cert_files", lambda: ("c.pem", "k.pem"))

    class Resp:
        status_code = 400
        headers = {"Content-Type": "application/json; charset=utf-8"}
        text = "x"

        def json(self):
            return {"erros": [{"Codigo": "E1235", "Descricao": "Falha no esquema XML do DF-e.",
                               "Complemento": "invalid child element 'cLocEmi'"}]}

    monkeypatch.setattr(requests, "request", lambda *a, **k: Resp())
    with pytest.raises(SefinNacionalError) as exc:
        c.post_nfse("payload")
    assert exc.value.raw_errors == [{"codigo": "E1235",
                                     "descricao": "Falha no esquema XML do DF-e. invalid child element 'cLocEmi'"}]


def test_queda_de_conexao_em_consulta_repete_e_vira_connection_error(client, monkeypatch):
    c, calls = client

    def fake_request(method, url, **kw):
        calls.append(method)
        raise requests.exceptions.ConnectionError("caiu")

    monkeypatch.setattr(requests, "request", fake_request)
    with pytest.raises(SefinNacionalError) as exc:
        c.get_dps("DPS123")
    assert exc.value.code == "CONNECTION_ERROR"
    assert calls == ["GET", "GET", "GET"]


def _client_respondendo(monkeypatch, resp):
    config = SefinNacionalConfig(
        environment="production_restricted", base_url="https://example.invalid", certificate_path="",
        certificate_password="", timeout=1, max_retries=3, debug=False, skip_xsd_validation=True,
    )
    c = SefinNacionalClient(config, cert=None)
    monkeypatch.setattr(c, "_get_cert_files", lambda: ("c.pem", "k.pem"))
    monkeypatch.setattr(requests, "request", resp)
    return c


def test_erro_sem_json_nao_quebra_e_mantem_o_status(monkeypatch):
    class Resp:
        status_code = 500
        headers = {"Content-Type": "text/html"}
        text = "<html>erro</html>"

        def json(self):
            raise ValueError("nao e json")

    c = _client_respondendo(monkeypatch, lambda *a, **k: Resp())
    with pytest.raises(SefinNacionalError) as exc:
        c.get_dps("DPS1")
    assert (exc.value.code, exc.value.raw_errors) == ("HTTP_500", [])


def test_lista_de_erros_com_chave_em_ingles(monkeypatch):
    class Resp:
        status_code = 400
        headers = {"Content-Type": "application/json"}
        text = "x"

        def json(self):
            return {"errors": [{"codigo": "E1", "descricao": "d"}]}

    c = _client_respondendo(monkeypatch, lambda *a, **k: Resp())
    with pytest.raises(SefinNacionalError) as exc:
        c.get_dps("DPS1")
    assert exc.value.raw_errors == [{"codigo": "E1", "descricao": "d"}]


def test_falha_de_certificado_nao_repete(monkeypatch):
    from nfse_mcp.errors import CertificateError
    calls = []

    def ssl(*a, **k):
        calls.append(1)
        raise requests.exceptions.SSLError("handshake")

    c = _client_respondendo(monkeypatch, ssl)
    with pytest.raises(CertificateError):
        c.get_dps("DPS1")
    assert calls == [1]


def test_evento_vai_no_campo_do_swagger_oficial(client, monkeypatch):
    c, _ = client
    sent = {}

    class Resp:
        status_code, text, headers = 201, "", {"Content-Type": "application/json"}

    def fake_request(method, url, json=None, **kw):
        sent.update(method=method, url=url, json=json)
        return Resp()

    monkeypatch.setattr(requests, "request", fake_request)
    c.post_evento("CHAVE", "B64")
    assert sent == {"method": "POST", "url": "https://example.invalid/nfse/CHAVE/eventos",
                    "json": {"pedidoRegistroEventoXmlGZipB64": "B64"}}
