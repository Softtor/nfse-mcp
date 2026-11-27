"""Unit tests for DPS XML builder."""

import pytest
from lxml import etree

from nfse_mcp.nacional.dps_xml_builder import build_dps_xml


def test_build_dps_xml_minimal():
    xml = build_dps_xml(
        serie_dps="1",
        numero_dps="1",
        data_competencia="2026-05-01",
        tipo_ambiente=2,
        prestador_cnpj="11222333000181",
        prestador_razao_social="PRESTADOR TESTE LTDA",
        prestador_logradouro="Rua Exemplo",
        prestador_numero="123",
        prestador_bairro="Centro",
        prestador_codigo_municipio="5300108",
        prestador_uf="DF",
        prestador_cep="70000000",
    )

    assert "DPS" in xml
    assert "infDPS" in xml
    assert "11222333000181" in xml
    assert "2026-05-01" in xml
    assert "<nDPS>1</nDPS>" in xml or "nDPS>1</nDPS>" in xml


def test_build_dps_xml_with_tomador_and_service():
    xml = build_dps_xml(
        serie_dps="1",
        numero_dps="42",
        data_competencia="2026-05-01",
        tipo_ambiente=2,
        prestador_cnpj="11222333000181",
        prestador_razao_social="PRESTADOR TESTE LTDA",
        prestador_logradouro="Rua Exemplo",
        prestador_numero="123",
        prestador_bairro="Centro",
        prestador_codigo_municipio="5300108",
        prestador_uf="DF",
        prestador_cep="70000000",
        tomador_document="12345678000190",
        tomador_tipo_documento="cnpj",
        tomador_razao_social="CLIENTE LTDA",
        tomador_logradouro="Av Cliente",
        tomador_numero="456",
        tomador_bairro="Bairro",
        tomador_codigo_municipio="5300108",
        tomador_uf="DF",
        tomador_cep="70000000",
        servico_codigo="1.07",
        servico_discriminacao="Consultoria em TI",
        servico_valor="5000.00",
        aliquota="2.00",
    )

    assert "12345678000190" in xml
    assert "010700" in xml
    assert "5000.00" in xml
    # Aliquota is omitted when optante_simples_nacional=1 (default)
    assert "<pAliq>" not in xml
    assert "<prest>" in xml
    assert "<toma>" in xml
    assert "<valores>" in xml


def test_build_dps_xml_with_aliquota_when_not_simples():
    xml = build_dps_xml(
        serie_dps="1",
        numero_dps="42",
        data_competencia="2026-05-01",
        tipo_ambiente=2,
        prestador_cnpj="11222333000181",
        prestador_razao_social="PRESTADOR TESTE LTDA",
        prestador_logradouro="Rua Exemplo",
        prestador_numero="123",
        prestador_bairro="Centro",
        prestador_codigo_municipio="5300108",
        prestador_uf="DF",
        prestador_cep="70000000",
        servico_codigo="1.07",
        servico_discriminacao="Consultoria em TI",
        servico_valor="5000.00",
        aliquota="2.00",
        optante_simples_nacional=0,  # Not Simples Nacional
    )

    assert "<pAliq>2.00</pAliq>" in xml


def test_build_dps_xml_well_formed():
    xml = build_dps_xml(
        serie_dps="1",
        numero_dps="1",
        data_competencia="2026-05-01",
        tipo_ambiente=2,
        prestador_cnpj="11222333000181",
        prestador_razao_social="PRESTADOR TESTE LTDA",
        prestador_logradouro="Rua Exemplo",
        prestador_numero="123",
        prestador_bairro="Centro",
        prestador_codigo_municipio="5300108",
        prestador_uf="DF",
        prestador_cep="70000000",
    )

    # Should be valid XML
    root = etree.fromstring(xml.encode("utf-8"))
    assert root.tag.endswith("DPS")


def _dps_softtor(**overrides):
    params = dict(
        serie_dps="1",
        numero_dps="7",
        data_competencia="2026-11-01",
        tipo_ambiente=2,
        prestador_cnpj="11222333000181",
        prestador_razao_social="PRESTADOR TESTE LTDA",
        prestador_logradouro="Rua Exemplo",
        prestador_numero="123",
        prestador_bairro="Centro",
        prestador_codigo_municipio="5300108",
        prestador_uf="DF",
        prestador_cep="70000000",
        prestador_inscricao_municipal="1234567",
        tomador_document="11444777000161",
        tomador_razao_social="TOMADOR TESTE LTDA",
        tomador_logradouro="Rua X",
        tomador_numero="1",
        tomador_bairro="Centro",
        tomador_codigo_municipio="5300108",
        tomador_uf="DF",
        tomador_cep="70000000",
        servico_codigo="01.04.01",
        codigo_tributacao_municipio="104",
        servico_discriminacao="Desenvolvimento de software",
        servico_valor="8500.00",
        optante_simples_nacional=3,
        regime_especial_tributacao=0,
    )
    params.update(overrides)
    return build_dps_xml(**params)


def test_ctribmun_vem_logo_apos_ctribnac():
    xml = _dps_softtor()
    assert "<cTribNac>010401</cTribNac><cTribMun>104</cTribMun><xDescServ>" in xml


def test_optante_simples_nao_informa_pis_cofins():
    assert "tribFed" not in _dps_softtor(optante_simples_nacional=3)
    assert "tribFed" not in _dps_softtor(optante_simples_nacional=2)
    assert "<CST>01</CST>" in _dps_softtor(optante_simples_nacional=1)


def test_dps_softtor_valida_no_xsd():
    from nfse_mcp.nacional.xsd_validator import XsdValidator
    assert XsdValidator().validate_dps(_dps_softtor()) == []


def test_dps_id_e_o_id_do_infdps():
    from nfse_mcp.nacional.dps_xml_builder import dps_id
    expected = dps_id("5300108", "11222333000181", "1", "7")
    assert expected == "DPS530010821122233300018100001000000000000007"
    assert f'Id="{expected}"' in _dps_softtor()


def test_finnfse_regular_logo_apos_tpemit():
    # Leiaute de 20/10/2026 (SefinNacional 1.6): finNFSe obrigatório entre tpEmit e cLocEmi
    assert "<tpEmit>1</tpEmit><finNFSe>0</finNFSe><cLocEmi>" in _dps_softtor()


def test_me_epp_informa_percentual_do_simples_no_total_de_tributos():
    # E0712: ME/EPP não pode usar indTotTrib; informa pTotTribSN
    assert "<totTrib><pTotTribSN>6.00</pTotTribSN></totTrib>" in _dps_softtor(aliquota_simples="6.00")
    assert "<totTrib><indTotTrib>0</indTotTrib></totTrib>" in _dps_softtor(optante_simples_nacional=1)


def test_regime_de_apuracao_so_para_me_epp():
    assert "<regApTribSN>1</regApTribSN>" in _dps_softtor(optante_simples_nacional=3)
    assert "regApTribSN" not in _dps_softtor(optante_simples_nacional=1)


def test_servico_so_com_descricao_ainda_gera_o_grupo():
    xml = _dps_softtor(servico_codigo="")
    assert "<xDescServ>Desenvolvimento de software</xDescServ>" in xml
    assert "cTribNac" not in xml


def test_declaracao_xml_e_iss_retido():
    xml = _dps_softtor(iss_retido=1)
    assert xml.startswith("<?xml")
    assert "<tpRetISSQN>2</tpRetISSQN>" in xml
