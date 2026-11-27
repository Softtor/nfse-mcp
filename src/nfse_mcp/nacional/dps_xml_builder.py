"""Builder for SEFIN Nacional DPS XML (v1.00).

Generates XML conforming to the official SEFIN Nacional layout.
Validated against DPS_v1.00.xsd schema.
"""

from datetime import datetime, timezone
from lxml import etree

# Namespace for DPS v1.00
NS_DPS = "http://www.sped.fazenda.gov.br/nfse"
NSMAP = {None: NS_DPS}


def _el(tag: str, **attribs) -> etree._Element:
    """Create a DPS element in the SEFIN namespace."""
    el = etree.Element(f"{{{NS_DPS}}}{tag}", nsmap=NSMAP)
    for k, v in attribs.items():
        if v is not None:
            el.set(k, str(v))
    return el


def _sub(parent: etree._Element, tag: str, text=None) -> etree._Element | None:
    """Add a subelement only when text is not None/empty."""
    if text is not None and str(text).strip():
        child = etree.SubElement(parent, f"{{{NS_DPS}}}{tag}")
        child.text = str(text).strip()
        return child
    return None


def _format_timezone(dt: datetime) -> str:
    """Format datetime with colon in timezone (e.g., -03:00)."""
    tz = dt.strftime("%z")
    if len(tz) == 5 and tz[0] in "+-":
        tz = tz[:3] + ":" + tz[3:]
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + tz


def _format_c_trib_nac(codigo: str) -> str:
    """Convert service code to 6-digit cTribNac format.

    Examples:
        '1.07'   -> '010700'
        '1.07.1' -> '010701'
        '010700' -> '010700'
    """
    parts = codigo.replace("-", ".").split(".")
    digits = "".join(p.zfill(2) for p in parts if p)
    return digits[:6].ljust(6, "0")


# Leiaute (pasta do XSD oficial em schemas/nacional/) em vigor em cada ambiente (tpAmb).
# Em 04/11/2026 a produção ainda recusa finNFSe (leiaute de 09/02/2026); a produção restrita já o exige.
LEIAUTE_POR_TPAMB = {1: "oficial-20260209", 2: "oficial-20261020"}


def dps_id(codigo_municipio: str, cnpj: str, serie: str, numero: str) -> str:
    """Id da DPS: DPS + IBGE(7) + tipoInsc(1, 2=CNPJ) + inscricao(14) + serie(5) + numero(15)."""
    return f"DPS{codigo_municipio}2{cnpj}{serie.zfill(5)}{numero.zfill(15)}"


def build_dps_xml(
    serie_dps: str,
    numero_dps: str,
    data_competencia: str,
    tipo_ambiente: int,
    prestador_cnpj: str,
    prestador_razao_social: str,
    prestador_logradouro: str,
    prestador_numero: str,
    prestador_bairro: str,
    prestador_codigo_municipio: str,
    prestador_uf: str,
    prestador_cep: str,
    prestador_inscricao_municipal: str | None = None,
    tomador_document: str = "",
    tomador_tipo_documento: str = "cnpj",
    tomador_razao_social: str = "",
    tomador_logradouro: str = "",
    tomador_numero: str = "",
    tomador_bairro: str = "",
    tomador_codigo_municipio: str = "",
    tomador_uf: str = "",
    tomador_cep: str = "",
    servico_codigo: str = "",
    codigo_tributacao_municipio: str = "",
    servico_discriminacao: str = "",
    servico_valor: str = "0.00",
    aliquota: str | None = None,
    aliquota_simples: str | None = None,
    iss_retido: int = 2,
    optante_simples_nacional: int = 1,
    regime_especial_tributacao: int = 0,
    incentivo_fiscal: int = 2,
    versao: str = "1.00",
) -> str:
    """Build a DPS XML string for SEFIN Nacional.

    Returns compact XML (no declaration) ready for signing.
    """
    # Root: DPS
    dps = _el("DPS", versao=versao)

    # infDPS
    inf = etree.SubElement(dps, f"{{{NS_DPS}}}infDPS")
    inf.set("Id", dps_id(prestador_codigo_municipio, prestador_cnpj, serie_dps, numero_dps))

    # Header
    _sub(inf, "tpAmb", str(tipo_ambiente))
    _sub(inf, "dhEmi", _format_timezone(datetime.now(timezone.utc).astimezone()))
    _sub(inf, "verAplic", versao)
    _sub(inf, "serie", serie_dps)
    _sub(inf, "nDPS", numero_dps)
    _sub(inf, "dCompet", data_competencia)
    _sub(inf, "tpEmit", "1")  # 1 = Prestador é o emitente
    if LEIAUTE_POR_TPAMB[tipo_ambiente] == "oficial-20261020":
        _sub(inf, "finNFSe", "0")  # 0 = NFS-e regular (obrigatório no leiaute de 20/10/2026)
    _sub(inf, "cLocEmi", prestador_codigo_municipio)

    # Prestador
    prest = etree.SubElement(inf, f"{{{NS_DPS}}}prest")
    _sub(prest, "CNPJ", prestador_cnpj)
    if prestador_inscricao_municipal:
        _sub(prest, "IM", prestador_inscricao_municipal)

    reg_trib_prest = etree.SubElement(prest, f"{{{NS_DPS}}}regTrib")
    _sub(reg_trib_prest, "opSimpNac", str(optante_simples_nacional))
    # regApTribSN: obrigatório quando opSimpNac=3 (Optante ME/EPP)
    if optante_simples_nacional == 3:
        _sub(reg_trib_prest, "regApTribSN", "1")  # 1=tributos federais e municipal apurados pelo SN
    _sub(reg_trib_prest, "regEspTrib", str(regime_especial_tributacao))

    # Tomador
    if tomador_document:
        toma = etree.SubElement(inf, f"{{{NS_DPS}}}toma")
        if tomador_tipo_documento == "cnpj":
            _sub(toma, "CNPJ", tomador_document)
        else:
            _sub(toma, "CPF", tomador_document)
        _sub(toma, "xNome", tomador_razao_social)

        end_toma = etree.SubElement(toma, f"{{{NS_DPS}}}end")
        end_nac_toma = etree.SubElement(end_toma, f"{{{NS_DPS}}}endNac")
        _sub(end_nac_toma, "cMun", tomador_codigo_municipio)
        _sub(end_nac_toma, "CEP", tomador_cep)
        _sub(end_toma, "xLgr", tomador_logradouro)
        _sub(end_toma, "nro", tomador_numero)
        _sub(end_toma, "xBairro", tomador_bairro)

    # Serviço
    if servico_codigo or servico_discriminacao:
        _add_serv(inf, prestador_codigo_municipio, servico_codigo, codigo_tributacao_municipio, servico_discriminacao)

    # Valores e Tributação
    valores = etree.SubElement(inf, f"{{{NS_DPS}}}valores")
    v_serv_prest = etree.SubElement(valores, f"{{{NS_DPS}}}vServPrest")
    _sub(v_serv_prest, "vServ", servico_valor)
    _add_trib(valores, servico_valor, aliquota, aliquota_simples, iss_retido, optante_simples_nacional)

    # Serialize with UTF-8 XML declaration
    return etree.tostring(dps, encoding="UTF-8", xml_declaration=True).decode("utf-8")


def _add_serv(inf, codigo_municipio, servico_codigo, codigo_tributacao_municipio, discriminacao) -> None:
    serv = etree.SubElement(inf, f"{{{NS_DPS}}}serv")
    loc_prest = etree.SubElement(serv, f"{{{NS_DPS}}}locPrest")
    _sub(loc_prest, "cLocPrestacao", codigo_municipio)

    c_serv = etree.SubElement(serv, f"{{{NS_DPS}}}cServ")
    if servico_codigo:
        _sub(c_serv, "cTribNac", _format_c_trib_nac(servico_codigo))
    _sub(c_serv, "cTribMun", codigo_tributacao_municipio)
    if discriminacao:
        _sub(c_serv, "xDescServ", discriminacao)


def _add_trib(valores, servico_valor, aliquota, aliquota_simples, iss_retido, optante_simples_nacional) -> None:
    trib = etree.SubElement(valores, f"{{{NS_DPS}}}trib")
    trib_mun = etree.SubElement(trib, f"{{{NS_DPS}}}tribMun")
    # Schema v1.01 order: tribISSQN -> cPaisResult -> tpImunidade -> exigSusp -> BM -> tpRetISSQN -> pAliq
    _sub(trib_mun, "tribISSQN", "1")  # 1 = Operação tributável
    _sub(trib_mun, "tpRetISSQN", "1" if iss_retido == 2 else "2")
    # pAliq is not allowed when the provider has special taxation regime
    # (e.g., Simples Nacional). Only include when not optante.
    if aliquota and optante_simples_nacional not in (1, 3):
        _sub(trib_mun, "pAliq", aliquota)

    # Optante do Simples (2=MEI, 3=ME/EPP) recolhe PIS/COFINS no DAS: tribFed é opcional e fica de fora.
    if optante_simples_nacional not in (2, 3):
        trib_fed = etree.SubElement(trib, f"{{{NS_DPS}}}tribFed")
        pis_cofins = etree.SubElement(trib_fed, f"{{{NS_DPS}}}piscofins")
        # Schema order: CST -> vBCPisCofins -> pAliqPis -> pAliqCofins -> vPis -> vCofins -> tpRetPisCofins
        _sub(pis_cofins, "CST", "01")
        _sub(pis_cofins, "vBCPisCofins", servico_valor)
        _sub(pis_cofins, "pAliqPis", "0.00")
        _sub(pis_cofins, "pAliqCofins", "0.00")
        _sub(pis_cofins, "vPis", "0.00")
        _sub(pis_cofins, "vCofins", "0.00")

    tot_trib = etree.SubElement(trib, f"{{{NS_DPS}}}totTrib")
    # E0712: ME/EPP não pode usar indTotTrib; informa o % aproximado de tributos do Simples.
    if optante_simples_nacional in (2, 3) and aliquota_simples:
        _sub(tot_trib, "pTotTribSN", aliquota_simples)
    else:
        _sub(tot_trib, "indTotTrib", "0")
