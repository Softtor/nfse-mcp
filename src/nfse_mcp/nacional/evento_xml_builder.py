"""Pedido de registro do evento de cancelamento (e101101), pelo XSD oficial pedRegEvento_v1.01.

A ordem e os nomes seguem tiposEventos_v1.01.xsd (igual nos dois leiautes), não o texto da documentação.
"""

from datetime import datetime, timezone
from lxml import etree

from nfse_mcp.errors import ValidationError

NS_EVENTO = "http://www.sped.fazenda.gov.br/nfse"
CANCELAMENTO = "101101"
MOTIVOS_CANCELAMENTO = {"1": "Erro na emissao", "2": "Servico nao prestado", "9": "Outros"}


def evento_id(chave_acesso: str) -> str:
    """Id do infPedReg: "PRE" + chave (50) + tipo do evento (6)."""
    return f"PRE{chave_acesso}{CANCELAMENTO}"


def validar_cancelamento(motivo_codigo: str, motivo_descricao: str) -> None:
    """cMotivo 1|2|9 e xMotivo de 15 a 255 caracteres (TSCodJustCanc, TSMotivo)."""
    if motivo_codigo not in MOTIVOS_CANCELAMENTO:
        raise ValidationError(f"Motivo de cancelamento invalido: {motivo_codigo} (use 1, 2 ou 9)")
    if not 15 <= len(motivo_descricao.strip()) <= 255:
        raise ValidationError("A descricao do cancelamento precisa ter de 15 a 255 caracteres")


def build_evento_cancelamento_xml(
    chave_acesso: str,
    motivo_codigo: str,
    motivo_descricao: str,
    cnpj_autor: str,
    tipo_ambiente: int = 2,
    data_hora_evento: str | None = None,
    versao: str = "1.00",
) -> str:
    """XML compacto do pedRegEvento, pronto para assinar (Reference no Id do infPedReg)."""
    validar_cancelamento(motivo_codigo, motivo_descricao)
    if data_hora_evento is None:
        data_hora_evento = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    root = etree.Element(f"{{{NS_EVENTO}}}pedRegEvento", nsmap={None: NS_EVENTO}, versao=versao)
    inf = etree.SubElement(root, f"{{{NS_EVENTO}}}infPedReg", Id=evento_id(chave_acesso))
    for tag, valor in [("tpAmb", tipo_ambiente), ("verAplic", versao), ("dhEvento", data_hora_evento),
                       ("CNPJAutor", cnpj_autor), ("chNFSe", chave_acesso)]:
        etree.SubElement(inf, f"{{{NS_EVENTO}}}{tag}").text = str(valor)
    evento = etree.SubElement(inf, f"{{{NS_EVENTO}}}e{CANCELAMENTO}")
    for tag, valor in [("xDesc", "Cancelamento de NFS-e"), ("cMotivo", motivo_codigo),
                       ("xMotivo", motivo_descricao.strip())]:
        etree.SubElement(evento, f"{{{NS_EVENTO}}}{tag}").text = valor
    return etree.tostring(root, encoding="unicode")
