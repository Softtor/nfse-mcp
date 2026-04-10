"""
XML builder for ISS.net NFS-e webservice (ABRASF 2.04 standard - Brasilia/DF).

Rules enforced:
- Compact XML (no whitespace/formatting between tags)
- Omit tags with null/empty values
- No leading zeros in numeric fields
- Dates: YYYY-MM-DD
- Decimals: dot separator, no thousands separator (e.g. "1000.50")
- Percentages: decimal form (e.g. "2.00" for 2%)
"""

from lxml import etree

from nfse_mcp.config import Config
from nfse_mcp.models import Client, RpsData, ServiceData

NS = "http://www.abrasf.org.br/nfse.xsd"
NSMAP = {None: NS}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _el(tag: str, **attribs: str) -> etree._Element:
    """Create a root element in the ABRASF namespace."""
    el = etree.Element(f"{{{NS}}}{tag}", nsmap=NSMAP)
    for k, v in attribs.items():
        el.set(k, v)
    return el


def _sub(parent: etree._Element, tag: str, text=None) -> etree._Element | None:
    """Add a subelement only when *text* is not None/empty."""
    if text is not None and str(text).strip():
        child = etree.SubElement(parent, f"{{{NS}}}{tag}")
        child.text = str(text).strip()
        return child
    return None


def _sub_group(parent: etree._Element, tag: str) -> etree._Element:
    """Add a group (container) subelement unconditionally."""
    return etree.SubElement(parent, f"{{{NS}}}{tag}")


def _to_xml(root: etree._Element) -> str:
    """Serialize an element tree to a compact XML string (no declaration)."""
    return etree.tostring(root, xml_declaration=False, encoding="unicode")


def _strip_leading_zeros(value: str) -> str:
    """Remove leading zeros from a numeric string, preserving at least one digit."""
    if not value:
        return value
    stripped = value.lstrip("0") or "0"
    return stripped


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------

def _build_prestador(parent: etree._Element, config: Config) -> None:
    """Append <Prestador> with provider identification."""
    prestador = _sub_group(parent, "Prestador")
    cpf_cnpj = _sub_group(prestador, "CpfCnpj")
    _sub(cpf_cnpj, "Cnpj", config.provider.cnpj)
    _sub(prestador, "InscricaoMunicipal", config.provider.im)


def _build_cpf_cnpj(parent: etree._Element, document: str, document_type: str) -> None:
    """Append <CpfCnpj> choosing <Cnpj> or <Cpf> based on document_type."""
    cpf_cnpj = _sub_group(parent, "CpfCnpj")
    if document_type == "cnpj":
        _sub(cpf_cnpj, "Cnpj", document)
    else:
        _sub(cpf_cnpj, "Cpf", document)


def _build_tomador(parent: etree._Element, client: Client) -> None:
    """Append <TomadorServico> with client data."""
    tomador = _sub_group(parent, "TomadorServico")

    # IdentificacaoTomador
    ident = _sub_group(tomador, "IdentificacaoTomador")
    _build_cpf_cnpj(ident, client.document, client.document_type)

    _sub(tomador, "RazaoSocial", client.razao_social)

    # Endereco - only if required fields are present (Endereco, Numero, Bairro are required by XSD)
    has_required_address = all([
        client.endereco, client.numero, client.bairro,
        client.codigo_municipio, client.uf, client.cep,
    ])
    if has_required_address:
        endereco = _sub_group(tomador, "Endereco")
        _sub(endereco, "Endereco", client.endereco)
        _sub(endereco, "Numero", client.numero)
        _sub(endereco, "Complemento", client.complemento)
        _sub(endereco, "Bairro", client.bairro)
        _sub(endereco, "CodigoMunicipio", client.codigo_municipio)
        _sub(endereco, "Uf", client.uf)
        _sub(endereco, "Cep", client.cep)

    # Contato - only if at least one contact field is present
    has_contact = any([client.telefone, client.email])
    if has_contact:
        contato = _sub_group(tomador, "Contato")
        _sub(contato, "Telefone", client.telefone)
        _sub(contato, "Email", client.email)


def _build_servico(parent: etree._Element, service: ServiceData, config: Config) -> None:
    """Append <Servico> block with service data, falling back to config defaults."""
    servico = _sub_group(parent, "Servico")

    # Valores
    valores = _sub_group(servico, "Valores")
    _sub(valores, "ValorServicos", service.valor_servicos)
    aliquota = service.aliquota or config.service_defaults.aliquota
    _sub(valores, "Aliquota", aliquota)

    iss_retido = service.iss_retido if service.iss_retido else config.service_defaults.iss_retido
    _sub(servico, "IssRetido", str(iss_retido))

    item = service.item_lista_servico or config.service_defaults.item_lista_servico
    # ItemListaServico must keep format NN.NN (e.g. "01.07") — pad with zero if needed
    if item and "." in item:
        parts = item.split(".")
        item = f"{int(parts[0]):02d}.{int(parts[1]):02d}"
    _sub(servico, "ItemListaServico", item)

    cnae = service.cnae or config.service_defaults.cnae
    _sub(servico, "CodigoCnae", _strip_leading_zeros(cnae) if cnae else None)

    cod_trib = service.codigo_tributacao_municipio or config.service_defaults.codigo_tributacao_municipio
    _sub(servico, "CodigoTributacaoMunicipio", cod_trib)

    _sub(servico, "Discriminacao", service.discriminacao)

    municipio = service.municipio_prestacao or config.service_defaults.municipio_ibge
    _sub(servico, "CodigoMunicipio", _strip_leading_zeros(municipio) if municipio else None)

    exig = service.exigibilidade_iss if service.exigibilidade_iss else config.service_defaults.exigibilidade_iss
    _sub(servico, "ExigibilidadeISS", str(exig))

    _sub(servico, "MunicipioIncidencia", _strip_leading_zeros(service.municipio_incidencia) if service.municipio_incidencia else None)


def _build_inf_declaracao(
    parent: etree._Element,
    config: Config,
    rps: RpsData,
    service: ServiceData,
    client: Client,
    competencia: str,
) -> None:
    """Build <InfDeclaracaoPrestacaoServico> inside *parent*.

    This is the shared core used by both GerarNfseEnvio (single) and
    EnviarLoteRpsSincronoEnvio (batch).
    """
    inf = _sub_group(parent, "InfDeclaracaoPrestacaoServico")

    # Rps identification
    rps_el = _sub_group(inf, "Rps")
    ident = _sub_group(rps_el, "IdentificacaoRps")
    _sub(ident, "Numero", str(rps.numero))
    _sub(ident, "Serie", rps.serie or config.rps_serie)
    _sub(ident, "Tipo", str(rps.tipo))
    _sub(rps_el, "DataEmissao", rps.data_emissao)
    _sub(rps_el, "Status", str(rps.status))

    # Competencia
    _sub(inf, "Competencia", competencia)

    # Servico
    _build_servico(inf, service, config)

    # Prestador
    _build_prestador(inf, config)

    # Tomador
    _build_tomador(inf, client)

    # Tributacao flags
    _sub(inf, "RegimeEspecialTributacao", str(config.provider.regime_tributacao))
    _sub(inf, "OptanteSimplesNacional", str(config.provider.simples_nacional))
    _sub(inf, "IncentivoFiscal", str(config.provider.incentivo_fiscal))


# ---------------------------------------------------------------------------
# Public builder functions
# ---------------------------------------------------------------------------

def build_cabecalho() -> str:
    """Build the SOAP header XML (cabecalho).

    Returns compact XML string.
    """
    root = _el("cabecalho", versao="1.00")
    _sub(root, "versaoDados", "2.04")
    return _to_xml(root)


def build_inf_declaracao_xml(
    config: Config,
    rps: RpsData,
    service: ServiceData,
    client: Client,
    competencia: str,
) -> str:
    """Build standalone <InfDeclaracaoPrestacaoServico> XML for signing.

    This is used by the emission flow so the signature can be placed
    inside <Rps> as a sibling of <InfDeclaracaoPrestacaoServico>.

    Returns compact XML string of the InfDeclaracaoPrestacaoServico element.
    """
    root = _el("InfDeclaracaoPrestacaoServico")

    # Rps identification
    rps_el = _sub_group(root, "Rps")
    ident = _sub_group(rps_el, "IdentificacaoRps")
    _sub(ident, "Numero", str(rps.numero))
    _sub(ident, "Serie", rps.serie or config.rps_serie)
    _sub(ident, "Tipo", str(rps.tipo))
    _sub(rps_el, "DataEmissao", rps.data_emissao)
    _sub(rps_el, "Status", str(rps.status))

    # Competencia
    _sub(root, "Competencia", competencia)

    # Servico
    _build_servico(root, service, config)

    # Prestador
    _build_prestador(root, config)

    # Tomador
    _build_tomador(root, client)

    # Tributacao flags
    _sub(root, "RegimeEspecialTributacao", str(config.provider.regime_tributacao))
    _sub(root, "OptanteSimplesNacional", str(config.provider.simples_nacional))
    _sub(root, "IncentivoFiscal", str(config.provider.incentivo_fiscal))

    return _to_xml(root)


def build_gerar_nfse_envio(
    config: Config,
    rps: RpsData,
    service: ServiceData,
    client: Client,
    competencia: str,
) -> str:
    """Build <GerarNfseEnvio> for a single NFS-e emission.

    Args:
        config: Provider/environment configuration.
        rps: RPS identification data.
        service: Service description and tax data.
        client: Client (tomador) data.
        competencia: Competence date (YYYY-MM-DD).

    Returns compact XML string.
    """
    root = _el("GerarNfseEnvio")
    rps_wrapper = _sub_group(root, "Rps")
    _build_inf_declaracao(rps_wrapper, config, rps, service, client, competencia)
    return _to_xml(root)


def build_enviar_lote_rps_sincrono(
    config: Config,
    lote_number: int,
    rps_list: list[tuple[RpsData, ServiceData, Client, str]],
) -> str:
    """Build <EnviarLoteRpsSincronoEnvio> for synchronous batch submission.

    Args:
        config: Provider/environment configuration.
        lote_number: Batch (lote) number.
        rps_list: List of tuples (rps, service, client, competencia).

    Returns compact XML string.
    """
    root = _el("EnviarLoteRpsSincronoEnvio")
    lote = _sub_group(root, "LoteRps")
    lote.set("Id", f"lote{lote_number}")
    lote.set("versao", "2.04")

    _sub(lote, "NumeroLote", str(lote_number))

    # Prestador at lote level
    _build_prestador(lote, config)

    _sub(lote, "QuantidadeRps", str(len(rps_list)))

    lista = _sub_group(lote, "ListaRps")
    for rps, service, client, competencia in rps_list:
        rps_wrapper = _sub_group(lista, "Rps")
        _build_inf_declaracao(rps_wrapper, config, rps, service, client, competencia)

    return _to_xml(root)


def build_cancelar_nfse_envio(
    config: Config,
    nfse_number: str,
    codigo_cancelamento: str,
    codigo_municipio: str = "5300108",
) -> str:
    """Build <CancelarNfseEnvio> to cancel an issued NFS-e.

    Args:
        config: Provider/environment configuration.
        nfse_number: Number of the NFS-e to cancel.
        codigo_cancelamento: Cancellation reason code.
        codigo_municipio: IBGE municipality code (defaults to Brasilia).

    Returns compact XML string.
    """
    root = _el("CancelarNfseEnvio")
    pedido = _sub_group(root, "Pedido")
    inf = _sub_group(pedido, "InfPedidoCancelamento")

    ident = _sub_group(inf, "IdentificacaoNfse")
    _sub(ident, "Numero", _strip_leading_zeros(nfse_number))
    _build_cpf_cnpj(ident, config.provider.cnpj, "cnpj")
    _sub(ident, "InscricaoMunicipal", config.provider.im)
    _sub(ident, "CodigoMunicipio", _strip_leading_zeros(codigo_municipio))

    _sub(inf, "CodigoCancelamento", codigo_cancelamento)

    return _to_xml(root)


def build_consultar_url_nfse_envio(
    config: Config,
    numero_nfse: str | None = None,
    data_inicial: str | None = None,
    data_final: str | None = None,
    rps_numero: int | None = None,
    rps_serie: str | None = None,
    rps_tipo: int | None = None,
    pagina: int = 1,
) -> str:
    """Build <ConsultarUrlNfseEnvio> to query the visualization URL.

    Provide exactly one of: numero_nfse, period (data_inicial+data_final),
    or RPS identification (rps_numero+rps_serie+rps_tipo).

    Returns compact XML string.
    """
    root = _el("ConsultarUrlNfseEnvio")
    pedido = _sub_group(root, "Pedido")

    _build_prestador(pedido, config)

    if numero_nfse:
        _sub(pedido, "NumeroNfse", _strip_leading_zeros(numero_nfse))
    elif data_inicial and data_final:
        periodo = _sub_group(pedido, "PeriodoEmissao")
        _sub(periodo, "DataInicial", data_inicial)
        _sub(periodo, "DataFinal", data_final)
    elif rps_numero is not None:
        ident = _sub_group(pedido, "IdentificacaoRps")
        _sub(ident, "Numero", str(rps_numero))
        _sub(ident, "Serie", rps_serie or config.rps_serie)
        _sub(ident, "Tipo", str(rps_tipo or 1))

    _sub(pedido, "Pagina", str(pagina))

    return _to_xml(root)


def build_consultar_nfse_servico_prestado_envio(
    config: Config,
    data_inicial: str,
    data_final: str,
    pagina: int = 1,
) -> str:
    """Build <ConsultarNfseServicoPrestadoEnvio> to query issued invoices.

    Args:
        config: Provider/environment configuration.
        data_inicial: Start date (YYYY-MM-DD).
        data_final: End date (YYYY-MM-DD).
        pagina: Page number for pagination.

    Returns compact XML string.
    """
    root = _el("ConsultarNfseServicoPrestadoEnvio")
    pedido = _sub_group(root, "Pedido")

    _build_prestador(pedido, config)

    periodo = _sub_group(pedido, "PeriodoEmissao")
    _sub(periodo, "DataInicial", data_inicial)
    _sub(periodo, "DataFinal", data_final)

    _sub(pedido, "Pagina", str(pagina))

    return _to_xml(root)


def build_consultar_dados_cadastrais_envio(config: Config) -> str:
    """Build <ConsultarDadosCadastraisEnvio> to query cadastral data.

    Returns compact XML string.
    """
    root = _el("ConsultarDadosCadastraisEnvio")
    pedido = _sub_group(root, "Pedido")
    _build_prestador(pedido, config)
    return _to_xml(root)
