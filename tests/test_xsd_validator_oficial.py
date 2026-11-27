"""A DPS é validada contra o esquema oficial publicado pela Receita (leiaute de 20/10/2026)."""

from nfse_mcp.nacional.xsd_validator import XsdValidator
from tests.test_dps_xml_builder import _dps_softtor


def test_dps_sem_finnfse_e_recusada_como_no_servidor():
    xml = _dps_softtor().replace("<finNFSe>0</finNFSe>", "")
    erros = XsdValidator().validate_dps(xml)
    assert any("cLocEmi" in e and "finNFSe" in e for e in erros)


def test_ctribmun_e_opcional_no_esquema_oficial():
    assert XsdValidator().validate_dps(_dps_softtor(codigo_tributacao_municipio="")) == []


def test_producao_segue_o_leiaute_de_fevereiro_sem_finnfse():
    # Produção (tpAmb=1) recusou finNFSe em 04/11/2026; produção restrita (tpAmb=2) exige
    xml = _dps_softtor(tipo_ambiente=1)
    assert "finNFSe" not in xml
    assert XsdValidator().validate_dps(xml) == []
    com_fin = xml.replace("<tpEmit>1</tpEmit>", "<tpEmit>1</tpEmit><finNFSe>0</finNFSe>")
    assert any("finNFSe" in e for e in XsdValidator().validate_dps(com_fin))
