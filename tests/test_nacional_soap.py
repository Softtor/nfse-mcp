from unittest.mock import MagicMock, patch

from nfse_mcp.certificate import Certificate
from nfse_mcp.nacional.soap_client import NacionalSoapClient
from nfse_mcp.nacional.xml_builder import build_cabecalho


SUCCESS_GERAR = """
<GerarNfseResposta xmlns="http://www.sped.fazenda.gov.br/nfse">
  <ListaNfse>
    <CompNfse>
      <Nfse versao="1.00">
        <infNFSe Id="NFS5300108ABC">
          <nNFSe>9001</nNFSe>
          <nDFSe>9001</nDFSe>
          <cStat>100</cStat>
          <dhProc>2026-08-19T12:00:00-03:00</dhProc>
          <chNFSe>53001081234567890123456789012345678901234567890</chNFSe>
          <DPS versao="1.00">
            <infDPS Id="DPS1">
              <nDPS>12</nDPS>
              <serie>00001</serie>
            </infDPS>
          </DPS>
        </infNFSe>
      </Nfse>
    </CompNfse>
  </ListaNfse>
</GerarNfseResposta>
""".strip()

ERROR_GERAR = """
<GerarNfseResposta xmlns="http://www.sped.fazenda.gov.br/nfse">
  <ListaMensagemRetorno>
    <MensagemRetorno>
      <Codigo>E160</Codigo>
      <Mensagem>Arquivo em desacordo com o XML Schema</Mensagem>
      <Correcao>Verificar estrutura</Correcao>
    </MensagemRetorno>
  </ListaMensagemRetorno>
</GerarNfseResposta>
""".strip()

SOAP_WRAP = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>{inner}</soap:Body>
</soap:Envelope>
"""


def _soap(inner: str) -> bytes:
    return SOAP_WRAP.format(inner=inner).encode("utf-8")


def test_gerar_nfse_envelope_namespace(nacional_cfg, pfx_path):
    cert = Certificate(str(pfx_path), "test")
    client = NacionalSoapClient(nacional_cfg, cert)
    captured = {}

    def fake_post(url, data=None, headers=None, cert=None, timeout=None):
        captured["url"] = url
        captured["data"] = data.decode() if isinstance(data, bytes) else data
        captured["headers"] = headers
        resp = MagicMock()
        resp.content = _soap(SUCCESS_GERAR)
        resp.text = SUCCESS_GERAR
        return resp

    with patch("requests.post", side_effect=fake_post):
        resp = client.gerar_nfse(build_cabecalho(), "<GerarNfseEnvio/>")

    assert captured["url"].endswith("/wsnfsenacional/homologacao/nfse.asmx")
    assert captured["headers"]["SOAPAction"] == "http://www.sped.fazenda.gov.br/nfse/GerarNfse"
    assert 'xmlns="http://www.sped.fazenda.gov.br/nfse"' in captured["data"]
    assert "<GerarNfse " in captured["data"] or "<GerarNfse xmlns=" in captured["data"]
    assert "&lt;GerarNfseEnvio/&gt;" in captured["data"]
    assert "<![CDATA[" not in captured["data"]
    assert resp.get_nfse()["nNFSe"] == "9001"
    assert resp.get_nfse()["chNFSe"].startswith("5300108")
    assert not resp.has_errors()


def test_parse_errors():
    from nfse_mcp.nacional.soap_client import NacionalResponse

    resp = NacionalResponse(ERROR_GERAR, "GerarNfse")
    assert resp.has_errors()
    errors = resp.get_errors()
    assert errors[0]["Codigo"] == "E160"


def test_consultar_and_cancel_actions(nacional_cfg, pfx_path):
    cert = Certificate(str(pfx_path), "test")
    client = NacionalSoapClient(nacional_cfg, cert)
    actions = []

    def fake_post(url, data=None, headers=None, cert=None, timeout=None):
        actions.append(headers["SOAPAction"])
        resp = MagicMock()
        resp.content = _soap("<ok/>")
        resp.text = "<ok/>"
        return resp

    with patch("requests.post", side_effect=fake_post):
        client.consultar_nfse_dps(build_cabecalho(), "<x/>")
        client.cancelar_nfse(build_cabecalho(), "<x/>")
        client.consultar_dps_disponivel(build_cabecalho(), "<x/>")

    assert actions == [
        "http://www.sped.fazenda.gov.br/nfse/ConsultarNfseDps",
        "http://www.sped.fazenda.gov.br/nfse/CancelarNfse",
        "http://www.sped.fazenda.gov.br/nfse/ConsultarDpsDisponivel",
    ]
