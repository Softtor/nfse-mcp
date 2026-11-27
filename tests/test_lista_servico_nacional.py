"""Código de tributação nacional (cTribNac) conferido contra a lista oficial antes de gastar um número de DPS."""

import pytest

from nfse_mcp.application.exceptions.application_error import InvoiceError
from nfse_mcp.nacional.lista_servico import codigo_tributacao_nacional


@pytest.mark.parametrize("informado", ["01.07.01", "1.07.1", "010701"])
def test_codigo_existente_sai_com_seis_digitos(informado):
    assert codigo_tributacao_nacional(informado) == "010701"


@pytest.mark.parametrize("informado", ["1.07", "01.07", "01.07.00", "010700"])
def test_subitem_com_um_unico_desdobro_usa_esse_desdobro(informado):
    # 1.07 só tem o 01.07.01 na lista nacional; o 010700 é recusado pela SEFIN (E0310)
    assert codigo_tributacao_nacional(informado) == "010701"


@pytest.mark.parametrize("informado, na_mensagem", [
    ("01.03", ["01.03.01", "01.03.02"]),  # vários desdobros: não escolhe sozinho
    ("01.07.05", ["01.07.05", "01.07.01"]),  # desdobro inexistente: sugere o do subitem
])
def test_codigo_recusado_lista_as_opcoes_do_subitem(informado, na_mensagem):
    with pytest.raises(InvoiceError) as erro:
        codigo_tributacao_nacional(informado)
    assert all(trecho in erro.value.message for trecho in na_mensagem)


def test_subitem_inexistente_recusa():
    with pytest.raises(InvoiceError, match="01.99"):
        codigo_tributacao_nacional("01.99")


@pytest.mark.parametrize("informado", ["", "abc", "1.07.01.01"])
def test_formato_invalido_recusa(informado):
    with pytest.raises(InvoiceError):
        codigo_tributacao_nacional(informado)
