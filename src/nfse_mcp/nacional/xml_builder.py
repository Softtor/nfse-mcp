from datetime import datetime, timezone, timedelta

from lxml import etree

from nfse_mcp.models import Client
from nfse_mcp.nacional.config import NacionalConfig
from nfse_mcp.nacional.constants import (
    EVENTO_CANCELAMENTO,
    EVENTO_CANCELAMENTO_DESC,
    NS,
    VER_APLIC,
)

NSMAP = {None: NS}
TZ_BRT = timezone(timedelta(hours=-3))


def _el(tag: str, **attribs: str) -> etree._Element:
    el = etree.Element(f"{{{NS}}}{tag}", nsmap=NSMAP)
    for k, v in attribs.items():
        el.set(k, v)
    return el


def _sub(parent: etree._Element, tag: str, text=None) -> etree._Element | None:
    if text is None or not str(text).strip():
        return None
    child = etree.SubElement(parent, f"{{{NS}}}{tag}")
    child.text = str(text).strip()
    return child


def _group(parent: etree._Element, tag: str) -> etree._Element:
    return etree.SubElement(parent, f"{{{NS}}}{tag}")


def _xml(root: etree._Element) -> str:
    return etree.tostring(root, xml_declaration=False, encoding="unicode")


def _digits(value: str) -> str:
    return "".join(c for c in (value or "") if c.isdigit())


def _c_trib_nac(raw: str) -> str:
    digits = _digits(raw)
    if len(digits) == 6:
        return digits
    if "." in (raw or ""):
        parts = raw.split(".")
        item = f"{int(parts[0]):02d}{int(parts[1]):02d}"
        return (item + "01")[:6]
    if len(digits) == 4:
        return digits + "01"
    if len(digits) == 3:
        return f"0{digits}01"
    return digits.zfill(6)[:6]


def pad_serie(serie: str) -> str:
    digits = _digits(serie) or "1"
    return digits.zfill(5)[:5]


def dps_id(cnpj: str, municipio: str, serie: str, numero: int) -> str:
    cnpj_d = _digits(cnpj).ljust(14, "0")[:14]
    mun = _digits(municipio).zfill(7)[:7]
    tipo = "2" if len(_digits(cnpj)) == 14 else "1"
    return f"DPS{mun}{tipo}{cnpj_d}{pad_serie(serie)}{str(numero).zfill(15)}"


def build_cabecalho(versao: str = "1.00") -> str:
    root = _el("cabecalho", versao=versao)
    _sub(root, "versaoDados", versao)
    return _xml(root)


def build_dps_xml(
    cfg: NacionalConfig,
    client: Client,
    numero_dps: int,
    valor: str,
    discriminacao: str,
    competencia: str,
    dh_emi: datetime | None = None,
) -> str:
    now = dh_emi or datetime.now(TZ_BRT)
    serie = pad_serie(cfg.dps_serie)
    inf_id = dps_id(cfg.provider_cnpj, cfg.municipio_ibge, serie, numero_dps)

    root = _el("DPS", versao=cfg.layout_version)
    inf = _group(root, "infDPS")
    inf.set("Id", inf_id)

    _sub(inf, "tpAmb", "2")
    _sub(inf, "dhEmi", now.strftime("%Y-%m-%dT%H:%M:%S-03:00"))
    _sub(inf, "verAplic", VER_APLIC)
    _sub(inf, "serie", serie)
    _sub(inf, "nDPS", str(numero_dps))
    _sub(inf, "dCompet", competencia)
    _sub(inf, "tpEmit", "1")
    _sub(inf, "cLocEmi", _digits(cfg.municipio_ibge)[:7])

    prest = _group(inf, "prest")
    _sub(prest, "CNPJ", _digits(cfg.provider_cnpj))
    _sub(prest, "IM", _digits(cfg.provider_im))
    reg = _group(prest, "regTrib")
    if cfg.optante_simples:
        _sub(reg, "opSimpNac", "3")
        _sub(reg, "regApTribSN", "1")
    else:
        _sub(reg, "opSimpNac", "1")
    _sub(reg, "regEspTrib", "0")

    toma = _group(inf, "toma")
    doc = _digits(client.document)
    if client.document_type == "cpf" or len(doc) == 11:
        _sub(toma, "CPF", doc)
    else:
        _sub(toma, "CNPJ", doc)
    _sub(toma, "xNome", client.razao_social)
    if client.codigo_municipio and client.cep and client.endereco and client.numero:
        end = _group(toma, "end")
        end_nac = _group(end, "endNac")
        _sub(end_nac, "cMun", _digits(client.codigo_municipio)[:7])
        _sub(end_nac, "CEP", _digits(client.cep).zfill(8)[:8])
        _sub(end, "xLgr", client.endereco)
        _sub(end, "nro", client.numero)
        _sub(end, "xCpl", client.complemento)
        _sub(end, "xBairro", client.bairro)

    serv = _group(inf, "serv")
    loc = _group(serv, "locPrest")
    _sub(loc, "cLocPrestacao", _digits(cfg.municipio_ibge)[:7])
    c_serv = _group(serv, "cServ")
    _sub(c_serv, "cTribNac", _c_trib_nac(cfg.c_trib_nac))
    _sub(c_serv, "cTribMun", _digits(cfg.c_trib_mun) or _c_trib_nac(cfg.c_trib_nac))
    _sub(c_serv, "xDescServ", discriminacao)

    valores = _group(inf, "valores")
    v_serv = _group(valores, "vServPrest")
    _sub(v_serv, "vServ", valor)
    trib = _group(valores, "trib")
    trib_mun = _group(trib, "tribMun")
    _sub(trib_mun, "tribISSQN", "1")
    _sub(trib_mun, "tpRetISSQN", "1")
    _sub(trib_mun, "pAliq", cfg.aliquota)
    tot = _group(trib, "totTrib")
    if cfg.optante_simples:
        _sub(tot, "pTotTribSN", cfg.aliquota)
    else:
        _sub(tot, "indTotTrib", "0")

    return _xml(root)


def wrap_gerar_nfse_envio(signed_dps_xml: str) -> str:
    dps = etree.fromstring(signed_dps_xml.encode("utf-8"))
    root = _el("GerarNfseEnvio")
    root.append(dps)
    return _xml(root)


def build_consultar_nfse_dps_envio(
    cfg: NacionalConfig, numero_dps: str, serie: str | None = None
) -> str:
    root = _el("ConsultarNfseDpsEnvio")
    ident = _group(root, "IdentificacaoDps")
    _sub(ident, "NumDPS", str(numero_dps))
    _sub(ident, "SerieDPS", pad_serie(serie or cfg.dps_serie))
    prest = _group(root, "Prestador")
    _sub(prest, "CNPJ", _digits(cfg.provider_cnpj))
    _sub(prest, "IM", _digits(cfg.provider_im))
    return _xml(root)


def build_consultar_dps_disponivel_envio(cfg: NacionalConfig, pagina: int = 1) -> str:
    root = _el("ConsultarDpsDisponivelEnvio")
    prest = _group(root, "Prestador")
    _sub(prest, "CNPJ", _digits(cfg.provider_cnpj))
    _sub(prest, "IM", _digits(cfg.provider_im))
    _sub(root, "Pagina", str(pagina))
    return _xml(root)


def build_cancelar_nfse_envio(
    cfg: NacionalConfig,
    chave_nfse: str,
    codigo_motivo: str,
    x_motivo: str,
    dh_evento: datetime | None = None,
) -> str:
    now = dh_evento or datetime.now(TZ_BRT)
    chave = "".join(chave_nfse.split())
    inf_id = f"PRE{chave}{EVENTO_CANCELAMENTO}"
    root = _el("CancelarNfseEnvio")
    ped = _group(root, "pedRegEvento")
    ped.set("versao", cfg.layout_version)
    inf = _group(ped, "infPedReg")
    inf.set("Id", inf_id)
    _sub(inf, "tpAmb", "2")
    _sub(inf, "verAplic", VER_APLIC)
    _sub(inf, "dhEvento", now.strftime("%Y-%m-%dT%H:%M:%S-03:00"))
    _sub(inf, "CNPJAutor", _digits(cfg.provider_cnpj))
    _sub(inf, "chNFSe", chave)
    ev = _group(inf, "e101103")
    _sub(ev, "xDesc", EVENTO_CANCELAMENTO_DESC)
    _sub(ev, "cMotivo", codigo_motivo)
    _sub(ev, "xMotivo", x_motivo)
    return _xml(root)
