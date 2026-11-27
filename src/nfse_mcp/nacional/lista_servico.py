"""Código de tributação nacional (cTribNac) conferido contra a lista oficial do Sistema Nacional NFS-e.

A lista vem da aba LISTA.SERV.NAC. do Anexo B (anexo_b-nbs2-lista_servico_nacional-snnfse-v1-01-20260122.xlsx,
gov.br/nfse > documentação técnica > documentação atual). Código fora dela a SEFIN recusa com E0310,
depois de o número da DPS já ter sido gasto.
"""

import json
import re
from pathlib import Path

from nfse_mcp.application.exceptions.application_error import InvoiceError

LISTA = json.loads((Path(__file__).with_name("lista_servico_nacional.json")).read_text(encoding="utf-8"))
_FORMATO = re.compile(r"^\d{1,2}\.\d{1,2}(\.\d{1,2})?$|^\d{4}(\d{2})?$")


def _pontuado(codigo: str) -> str:
    return ".".join(codigo[i:i + 2] for i in range(0, len(codigo), 2))


def _opcoes(subitem: str) -> list[str]:
    return [c for c in LISTA if c.startswith(subitem)]


def _descrever(codigos: list[str]) -> str:
    return "; ".join(f"{_pontuado(c)} ({LISTA[c][:80]})" for c in codigos)


def codigo_tributacao_nacional(informado: str) -> str:
    """Devolve o cTribNac de 6 dígitos da lista nacional, ou InvoiceError dizendo qual usar.

    Item.subitem sem desdobro (ou desdobro 00) vira o único desdobro do subitem, quando só há um.
    """
    texto = (informado or "").strip()
    if not _FORMATO.match(texto):
        raise InvoiceError(f"Codigo de servico '{informado}' fora do formato item.subitem.desdobro (ex.: 01.07.01).")
    digitos = "".join(p.zfill(2) for p in texto.split(".")) if "." in texto else texto
    if digitos in LISTA:
        return digitos
    subitem = digitos[:4]
    opcoes = _opcoes(subitem)
    if not opcoes:
        raise InvoiceError(f"O subitem {_pontuado(subitem)} nao existe na lista de servicos nacional.")
    if digitos[4:] in ("", "00") and len(opcoes) == 1:
        return opcoes[0]
    raise InvoiceError(
        f"O codigo de servico {_pontuado(digitos)} nao existe na lista de servicos nacional. "
        f"Opcoes do subitem {_pontuado(subitem)}: {_descrever(opcoes)}."
    )
