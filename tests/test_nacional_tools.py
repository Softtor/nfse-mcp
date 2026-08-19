from unittest.mock import MagicMock, patch

from nfse_mcp.nacional.config import homolog_gate
from nfse_mcp.nacional.soap_client import NacionalResponse
from nfse_mcp.nacional.tools import (
    nacional_homolog_cancel_nfse,
    nacional_homolog_emit_nfse,
    nacional_homolog_query_nfse,
)


def test_gate_disabled(nacional_cfg):
    nacional_cfg.enabled = False
    msg = homolog_gate(nacional_cfg)
    assert "desligado" in msg
    assert "ABRASF 2.04" in msg


def test_gate_blocks_production(nacional_cfg):
    nacional_cfg.environment = "production"
    msg = homolog_gate(nacional_cfg)
    assert "homolog-only" in msg


def test_tools_refuse_when_disabled(nacional_cfg):
    nacional_cfg.enabled = False
    with patch("nfse_mcp.nacional.tools._get_cfg", return_value=nacional_cfg):
        out = nacional_homolog_emit_nfse("33779923000142", "10.00", "x")
    assert "NFSE_NACIONAL_ENABLED=1" in out


def test_emit_parses_mocked_soap(nacional_cfg, tomador):
    dps_resp = NacionalResponse(
        '<ConsultarDpsDisponivelResposta xmlns="http://www.sped.fazenda.gov.br/nfse">'
        "<ListaDpsDisponivel><DpsDisponivel><NumDPS>12</NumDPS></DpsDisponivel></ListaDpsDisponivel>"
        "</ConsultarDpsDisponivelResposta>",
        "ConsultarDpsDisponivel",
    )
    gerar_resp = NacionalResponse(
        '<GerarNfseResposta xmlns="http://www.sped.fazenda.gov.br/nfse">'
        "<ListaNfse><CompNfse><Nfse><infNFSe>"
        "<nNFSe>9001</nNFSe><chNFSe>CHAVE123</chNFSe><cStat>100</cStat>"
        "</infNFSe></Nfse></CompNfse></ListaNfse>"
        "</GerarNfseResposta>",
        "GerarNfse",
    )
    soap = MagicMock()
    soap.consultar_dps_disponivel.return_value = dps_resp
    soap.gerar_nfse.return_value = gerar_resp

    with (
        patch("nfse_mcp.nacional.tools._get_cfg", return_value=nacional_cfg),
        patch("nfse_mcp.nacional.tools._get_soap", return_value=soap),
        patch("nfse_mcp.nacional.tools._get_signer") as signer,
        patch("nfse_mcp.nacional.tools._find_or_register_client", return_value=tomador),
        patch("nfse_mcp.nacional.tools._ensure_client_address", return_value=tomador),
    ):
        signer.return_value.sign_by_id.side_effect = lambda xml, name: xml
        out = nacional_homolog_emit_nfse(tomador.document, "1000.00", "Suporte em TI")

    assert "NFS-e Nacional emitida" in out
    assert "9001" in out
    assert "CHAVE123" in out
    assert "homologacao" in out
    soap.gerar_nfse.assert_called_once()
    log = (nacional_cfg.data_dir / "nacional_nfse_log.json").read_text()
    assert "9001" in log


def test_query_mocked(nacional_cfg):
    resp = NacionalResponse(
        '<ConsultarNfseDpsResposta xmlns="http://www.sped.fazenda.gov.br/nfse">'
        "<CompNfse><Nfse><infNFSe><nNFSe>9001</nNFSe><nDPS>12</nDPS></infNFSe></Nfse></CompNfse>"
        "</ConsultarNfseDpsResposta>",
        "ConsultarNfseDps",
    )
    soap = MagicMock()
    soap.consultar_nfse_dps.return_value = resp
    with (
        patch("nfse_mcp.nacional.tools._get_cfg", return_value=nacional_cfg),
        patch("nfse_mcp.nacional.tools._get_soap", return_value=soap),
    ):
        out = nacional_homolog_query_nfse("12")
    assert "9001" in out
    assert "DPS: 12" in out or "12" in out


def test_cancel_mocked(nacional_cfg):
    resp = NacionalResponse(
        '<CancelarNfseResposta xmlns="http://www.sped.fazenda.gov.br/nfse"><evento/></CancelarNfseResposta>',
        "CancelarNfse",
    )
    soap = MagicMock()
    soap.cancelar_nfse.return_value = resp
    with (
        patch("nfse_mcp.nacional.tools._get_cfg", return_value=nacional_cfg),
        patch("nfse_mcp.nacional.tools._get_soap", return_value=soap),
        patch("nfse_mcp.nacional.tools._get_signer") as signer,
    ):
        signer.return_value.sign_by_id.side_effect = lambda xml, name: xml
        out = nacional_homolog_cancel_nfse("CHAVE123", "1")
    assert "Cancelamento Nacional enviado" in out
    soap.cancelar_nfse.assert_called_once()
