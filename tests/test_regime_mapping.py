"""Tradução dos códigos de regime do padrão ABRASF para o padrão nacional (DPS)."""

import pytest

from nfse_mcp.sefin_nacional.mapper import op_simp_nac, reg_esp_trib


@pytest.mark.parametrize("simples, regime, esperado", [
    (1, 6, 3),  # optante ME/EPP
    (1, 5, 2),  # MEI
    (2, 6, 1),  # não optante
    (2, 0, 1),
])
def test_op_simp_nac(simples, regime, esperado):
    assert op_simp_nac(simples, regime) == esperado


@pytest.mark.parametrize("regime, esperado", [(6, 0), (5, 0), (0, 0), (1, 3), (2, 2), (3, 6), (4, 1)])
def test_reg_esp_trib(regime, esperado):
    assert reg_esp_trib(regime) == esperado


def test_reg_esp_trib_desconhecido_falha():
    with pytest.raises(ValueError):
        reg_esp_trib(9)


def test_nfse_confere_casos_de_borda():
    from nfse_mcp.sefin_nacional.mapper import nfse_confere
    xml = ('<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"><DPS><infDPS><dCompet>2026-11-01</dCompet>'
           '<toma><CPF>12345678901</CPF></toma><vServ>{v}</vServ></infDPS></DPS></NFSe>')
    assert nfse_confere(None, "12345678901", "10.00", "2026-11-01") is False
    assert nfse_confere(xml.format(v="abc"), "12345678901", "10.00", "2026-11-01") is False
    assert nfse_confere(xml.format(v="10.0"), "12345678901", "10.00", "2026-11-01") is True
    assert nfse_confere(xml.format(v="10.00"), "12345678901", "10.00", "2026-12-01") is False
