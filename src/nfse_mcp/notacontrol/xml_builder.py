"""Builders de XML do padrão nacional NFS-e (ISS.net / Nota Control).

Diferenças relevantes frente ao ABRASF 2.04 (`nfse_mcp.abrasf.xml_builder`),
todas confirmadas contra `schemas/nacional/schema_v101.xsd`:

- namespace ``http://www.sped.fazenda.gov.br/nfse`` (era ``.../abrasf.org.br/nfse.xsd``)
- o wrapper ``<Pedido>`` **deixou de existir**: ``Prestador`` vai direto no envio
- o prestador usa ``<CNPJ>`` direto, sem o wrapper ``<CpfCnpj>`` do ABRASF
- ``<Pagina>`` é obrigatório nas consultas (50 registros por página)
- ``versao``/``versaoDados`` do cabeçalho passam a ``1.01``
"""

from typing import Optional

from lxml import etree

from nfse_mcp.config import Config


NS = "http://www.sped.fazenda.gov.br/nfse"
NSMAP = {None: NS}

VERSAO = "1.01"

# Máximo de registros por página nas consultas (manual §7.2.7).
PAGE_SIZE = 50


def _el(tag: str, **attribs: str) -> etree._Element:
    return etree.Element(f"{{{NS}}}{tag}", nsmap=NSMAP, **attribs)


def _sub(parent: etree._Element, tag: str, text: Optional[str]) -> Optional[etree._Element]:
    """Cria o filho apenas se houver conteúdo — tags nulas devem ser omitidas."""
    if text is None or text == "":
        return None
    child = etree.SubElement(parent, f"{{{NS}}}{tag}")
    child.text = str(text)
    return child


def _group(parent: etree._Element, tag: str) -> etree._Element:
    return etree.SubElement(parent, f"{{{NS}}}{tag}")


def _to_xml(root: etree._Element) -> str:
    return etree.tostring(root, encoding="unicode", xml_declaration=False)


def _build_prestador(parent: etree._Element, config: Config) -> etree._Element:
    """<Prestador> do tipo tcIdentificacaoPessoaEmpresaComIM: choice(CNPJ|CPF) + IM."""
    prestador = _group(parent, "Prestador")
    _sub(prestador, "CNPJ", config.provider.cnpj)
    _sub(prestador, "IM", config.provider.im)
    return prestador


def build_cabecalho(versao_dados: str = VERSAO) -> str:
    """<cabecalho versao="1.01"><versaoDados>1.01</versaoDados></cabecalho>.

    No ABRASF os dois eixos eram independentes (versao="1.00" com
    versaoDados="2.04"); aqui o XSD tipa ambos como TVerNFSe.
    """
    root = _el("cabecalho", versao=VERSAO)
    _sub(root, "versaoDados", versao_dados)
    return _to_xml(root)


def build_consultar_dados_cadastrais_envio(config: Config) -> str:
    """<ConsultarDadosCadastraisEnvio> — o menor payload do padrão."""
    root = _el("ConsultarDadosCadastraisEnvio")
    _build_prestador(root, config)
    return _to_xml(root)


def build_consultar_nfse_servico_prestado_envio(
    config: Config,
    data_inicial: str,
    data_final: str,
    pagina: int = 1,
) -> str:
    """<ConsultarNfseServicoPrestadoEnvio> por período de emissão.

    A ordem do XSD é sequence[Prestador, choice(...), Tomador?, Intermediario?, Pagina].
    """
    root = _el("ConsultarNfseServicoPrestadoEnvio")
    _build_prestador(root, config)

    periodo = _group(root, "PeriodoEmissao")
    _sub(periodo, "DataInicial", data_inicial)
    _sub(periodo, "DataFinal", data_final)

    _sub(root, "Pagina", str(pagina))
    return _to_xml(root)


def build_gerar_nfse_envio(dps_assinado_xml: str) -> str:
    """<GerarNfseEnvio> envolvendo um DPS **já assinado**.

    O XSD define GerarNfseEnvio > DPS (TCDPS), e TCDPS é
    sequence[infDPS, dsig:Signature] — a assinatura é irmã de infDPS.
    """
    root = _el("GerarNfseEnvio")
    dps = etree.fromstring(dps_assinado_xml.encode("utf-8"))
    root.append(dps)
    return _to_xml(root)
