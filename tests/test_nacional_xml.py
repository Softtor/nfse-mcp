from lxml import etree

from nfse_mcp.certificate import Certificate
from nfse_mcp.nacional.constants import NS
from nfse_mcp.nacional.xml_builder import (
    build_cabecalho,
    build_cancelar_nfse_envio,
    build_consultar_nfse_dps_envio,
    build_dps_xml,
    dps_id,
    pad_serie,
    wrap_gerar_nfse_envio,
)
from nfse_mcp.nacional.xml_signer import NacionalXmlSigner


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def test_dps_id_format():
    ident = dps_id("33779923000142", "5300108", "1", 12)
    assert ident.startswith("DPS53001082")
    assert ident.endswith("000000000000012")
    assert len(ident) == 3 + 7 + 1 + 14 + 5 + 15


def test_pad_serie():
    assert pad_serie("1") == "00001"
    assert pad_serie("3") == "00003"


def test_cabecalho_layout_100():
    xml = build_cabecalho("1.00")
    root = etree.fromstring(xml.encode())
    assert root.get("versao") == "1.00"
    assert root[0].text == "1.00"
    assert NS in (root.nsmap.get(None) or "")


def test_dps_minimal_structure(nacional_cfg, tomador):
    xml = build_dps_xml(nacional_cfg, tomador, 1, "1000.00", "Suporte em TI", "2026-08-01")
    root = etree.fromstring(xml.encode())
    assert _local(root.tag) == "DPS"
    assert root.get("versao") == "1.00"
    inf = root[0]
    assert inf.get("Id").startswith("DPS5300108")
    tags = [_local(c.tag) for c in inf]
    assert tags == ["tpAmb", "dhEmi", "verAplic", "serie", "nDPS", "dCompet", "tpEmit", "cLocEmi", "prest", "toma", "serv", "valores"]
    assert inf.find(f"{{{NS}}}tpAmb").text == "2"
    c_trib = inf.find(f".//{{{NS}}}cTribNac")
    assert c_trib.text == "010701"
    assert inf.find(f".//{{{NS}}}cTribMun").text == "107"
    assert b"IBSCBS" not in xml.encode()
    assert root.find(f"{{{NS}}}IBSCBS") is None


def test_gerar_nfse_envio_wraps_signed_dps(nacional_cfg, tomador, pfx_path):
    dps = build_dps_xml(nacional_cfg, tomador, 7, "250.00", "Suporte", "2026-08-01")
    signed = NacionalXmlSigner(Certificate(str(pfx_path), "test")).sign_by_id(dps, "infDPS")
    envio = wrap_gerar_nfse_envio(signed)
    root = etree.fromstring(envio.encode())
    assert _local(root.tag) == "GerarNfseEnvio"
    dps_el = root[0]
    assert _local(dps_el.tag) == "DPS"
    locals_ = [_local(c.tag) for c in dps_el]
    assert "infDPS" in locals_
    assert "Signature" in locals_


def test_consultar_dps_envio(nacional_cfg):
    xml = build_consultar_nfse_dps_envio(nacional_cfg, "12")
    root = etree.fromstring(xml.encode())
    assert _local(root.tag) == "ConsultarNfseDpsEnvio"
    assert root.find(f".//{{{NS}}}NumDPS").text == "12"
    assert root.find(f".//{{{NS}}}SerieDPS").text == "00001"
    assert root.find(f".//{{{NS}}}Signature") is None


def test_cancelar_evento_e101103(nacional_cfg):
    xml = build_cancelar_nfse_envio(
        nacional_cfg,
        "NFS" + "0" * 47,
        "1",
        "Erro na Emissao",
    )
    root = etree.fromstring(xml.encode())
    inf = root.find(f".//{{{NS}}}infPedReg")
    assert inf.get("Id").startswith("PRE")
    assert inf.get("Id").endswith("101103")
    ev = inf.find(f"{{{NS}}}e101103")
    assert ev is not None
    assert ev.find(f"{{{NS}}}cMotivo").text == "1"
