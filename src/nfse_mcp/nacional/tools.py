from datetime import date
from pathlib import Path
import json

from nfse_mcp.certificate import Certificate
from nfse_mcp.client_store import ClientStore
from nfse_mcp.cnpj_lookup import clean_document, lookup_cnpj
from nfse_mcp.models import Client
from nfse_mcp.nacional.config import NacionalConfig, homolog_gate, load_nacional_config
from nfse_mcp.nacional.soap_client import NacionalResponse, NacionalSoapClient
from nfse_mcp.nacional.xml_builder import (
    build_cabecalho,
    build_cancelar_nfse_envio,
    build_consultar_dps_disponivel_envio,
    build_consultar_nfse_dps_envio,
    build_dps_xml,
    wrap_gerar_nfse_envio,
)
from nfse_mcp.nacional.xml_signer import NacionalXmlSigner

MOTIVO_DESC = {
    "1": "Erro na Emissao",
    "2": "Servico nao Prestado",
    "9": "Outros",
}

_cfg: NacionalConfig | None = None
_cert: Certificate | None = None
_signer: NacionalXmlSigner | None = None
_soap: NacionalSoapClient | None = None
_store: ClientStore | None = None


def reset_nacional_state() -> None:
    global _cfg, _cert, _signer, _soap, _store
    _cfg = None
    _cert = None
    _signer = None
    _soap = None
    _store = None


def _get_cfg() -> NacionalConfig:
    global _cfg
    if _cfg is None:
        _cfg = load_nacional_config()
    return _cfg


def _get_cert() -> Certificate:
    global _cert
    if _cert is None:
        cfg = _get_cfg()
        _cert = Certificate(cfg.certificate_path, cfg.certificate_password)
    return _cert


def _get_signer() -> NacionalXmlSigner:
    global _signer
    if _signer is None:
        _signer = NacionalXmlSigner(_get_cert())
    return _signer


def _get_soap() -> NacionalSoapClient:
    global _soap
    if _soap is None:
        _soap = NacionalSoapClient(_get_cfg(), _get_cert())
    return _soap


def _get_store() -> ClientStore:
    global _store
    if _store is None:
        _store = ClientStore(_get_cfg().data_dir)
    return _store


def _log_path() -> Path:
    return _get_cfg().data_dir / "nacional_nfse_log.json"


def _append_log(entry: dict) -> None:
    path = _log_path()
    log = []
    if path.exists():
        try:
            log = json.loads(path.read_text())
        except Exception:
            log = []
    log.append(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2, ensure_ascii=False))


def _find_or_register_client(document: str) -> Client:
    store = _get_store()
    doc_clean = clean_document(document)
    client = store.find_by_document(doc_clean)
    if client is None:
        client = store.register(doc_clean, auto_lookup=True)
    return client


def _ensure_client_address(client: Client) -> Client:
    required = [
        client.endereco,
        client.numero,
        client.bairro,
        client.codigo_municipio,
        client.cep,
    ]
    if all(required):
        return client
    if client.document_type == "cnpj" and len(client.document) == 14:
        result = lookup_cnpj(client.document)
        if result:
            client.endereco = client.endereco or result.get("logradouro") or None
            client.numero = client.numero or result.get("numero") or None
            client.bairro = client.bairro or result.get("bairro") or None
            client.codigo_municipio = client.codigo_municipio or result.get("codigo_municipio_ibge") or None
            client.uf = client.uf or result.get("uf") or None
            client.cep = client.cep or result.get("cep") or None
    client.endereco = client.endereco or "Rua Nao Informada"
    client.numero = client.numero or "SN"
    client.bairro = client.bairro or "Nao Informado"
    client.codigo_municipio = client.codigo_municipio or "5300108"
    client.uf = client.uf or "DF"
    client.cep = client.cep or "70000000"
    _get_store().update(
        client.id,
        endereco=client.endereco,
        numero=client.numero,
        bairro=client.bairro,
        codigo_municipio=client.codigo_municipio,
        uf=client.uf,
        cep=client.cep,
    )
    return client


def _format_errors(resp: NacionalResponse) -> str:
    lines = []
    for e in resp.get_errors():
        entry = f"[{e.get('Codigo', '')}] {e.get('Mensagem', 'Erro desconhecido')}"
        if e.get("Correcao"):
            entry += f" (Correcao: {e['Correcao']})"
        lines.append(f"  - {entry}")
    if not lines:
        lines.append(f"  - {resp.raw_xml[:500] if resp.raw_xml else 'sem detalhe'}")
    return "\n".join(lines)


def _next_dps_number(cfg: NacionalConfig) -> int:
    header = build_cabecalho(cfg.layout_version)
    data_xml = build_consultar_dps_disponivel_envio(cfg)
    resp = _get_soap().consultar_dps_disponivel(header, data_xml)
    n = resp.get_next_dps()
    if n:
        return n
    raise Exception("Nao foi possivel obter numero de DPS disponivel no webservice de homologacao")


def _gate() -> str | None:
    return homolog_gate(_get_cfg())


def nacional_homolog_emit_nfse(
    client_document: str,
    valor: str,
    discriminacao: str,
    competencia: str = "",
) -> str:
    """Emit a single DF NFS-e Padrão Nacional invoice against the homologation webservice only.

    Args:
        client_document: CNPJ or CPF of the service taker (tomador).
        valor: Service value as decimal string (e.g. "1000.00").
        discriminacao: Detailed service description.
        competencia: Competence date in YYYY-MM-DD (defaults to 1st of current month).
    """
    blocked = _gate()
    if blocked:
        return blocked
    try:
        cfg = _get_cfg()
        client = _find_or_register_client(client_document)
        if not client.razao_social:
            return (
                f"Erro: Cliente com documento {clean_document(client_document)} "
                "nao possui razao social. Use register_client primeiro."
            )
        client = _ensure_client_address(client)
        try:
            n_dps = _next_dps_number(cfg)
        except Exception as e:
            return f"Erro ao obter numero de DPS disponivel: {e}"
        today = date.today()
        comp = competencia or today.replace(day=1).isoformat()
        dps_xml = build_dps_xml(cfg, client, n_dps, valor, discriminacao, comp)
        signed_dps = _get_signer().sign_by_id(dps_xml, "infDPS")
        data_xml = wrap_gerar_nfse_envio(signed_dps)
        header = build_cabecalho(cfg.layout_version)
        resp = _get_soap().gerar_nfse(header, data_xml)
        if resp.has_errors():
            return (
                f"=== Erro na Emissao Nacional (homolog) ===\n"
                f"DPS: {n_dps}\n"
                f"Cliente: {client.razao_social}\n"
                f"Valor: R$ {valor}\n"
                f"Erros:\n{_format_errors(resp)}"
            )
        nfse = resp.get_nfse()
        if not nfse.get("nNFSe") and not nfse.get("nDFSe"):
            return (
                f"=== Erro na Emissao Nacional (homolog) ===\n"
                f"DPS: {n_dps}\n"
                f"Nenhuma NFS-e retornada.\n{_format_errors(resp)}"
            )
        numero = nfse.get("nNFSe") or nfse.get("nDFSe")
        _append_log({
            "dps_number": n_dps,
            "nfse_number": numero,
            "chave": nfse.get("chNFSe") or nfse.get("Id"),
            "date": today.isoformat(),
            "client_cnpj": client.document,
            "client_name": client.razao_social,
            "valor": valor,
            "ambiente": "homologation",
        })
        lines = [
            "=== NFS-e Nacional emitida (homologacao DF) ===",
            f"NFS-e Numero: {numero}",
            f"DPS Numero: {n_dps}",
            f"Cliente: {client.razao_social} ({client.document})",
            f"Valor: R$ {valor}",
            f"Competencia: {comp}",
            "Ambiente: homologacao (nao e producao)",
        ]
        if nfse.get("chNFSe"):
            lines.append(f"Chave: {nfse['chNFSe']}")
        if nfse.get("cStat"):
            lines.append(f"cStat: {nfse['cStat']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao emitir NFS-e Nacional (homolog): {e}"


def nacional_homolog_query_nfse(dps_number: str, dps_serie: str = "") -> str:
    """Query a DF NFS-e Padrão Nacional invoice on homologation by DPS number.

    Args:
        dps_number: DPS number returned at emission.
        dps_serie: DPS series override (defaults to NFSE_NACIONAL_DPS_SERIE).
    """
    blocked = _gate()
    if blocked:
        return blocked
    try:
        cfg = _get_cfg()
        if not dps_number.strip():
            return "Erro: informe dps_number."
        header = build_cabecalho(cfg.layout_version)
        data_xml = build_consultar_nfse_dps_envio(cfg, dps_number.strip(), dps_serie or None)
        resp = _get_soap().consultar_nfse_dps(header, data_xml)
        if resp.has_errors():
            return (
                f"=== Erro na Consulta Nacional (homolog) ===\n"
                f"DPS: {dps_number}\n"
                f"Erros:\n{_format_errors(resp)}"
            )
        nfse = resp.get_nfse()
        if not nfse:
            return f"Nenhuma NFS-e encontrada para DPS {dps_number} (homologacao)."
        lines = ["=== NFS-e Nacional (homologacao DF) ==="]
        labels = {
            "nNFSe": "NFS-e Numero",
            "nDFSe": "nDFSe",
            "nDPS": "DPS",
            "serie": "Serie DPS",
            "chNFSe": "Chave",
            "cStat": "cStat",
            "dhProc": "Processamento",
            "Id": "Id",
        }
        for key, label in labels.items():
            if nfse.get(key):
                lines.append(f"{label}: {nfse[key]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao consultar NFS-e Nacional (homolog): {e}"


def nacional_homolog_cancel_nfse(chave_nfse: str, motivo: str = "1") -> str:
    """Cancel a DF NFS-e Padrão Nacional invoice on homologation.

    Args:
        chave_nfse: Access key (chNFSe) returned at emission.
        motivo: Cancellation reason. 1=Erro na Emissao, 2=Servico nao Prestado, 9=Outros.
    """
    blocked = _gate()
    if blocked:
        return blocked
    try:
        cfg = _get_cfg()
        if motivo not in MOTIVO_DESC:
            return f"Erro: motivo invalido '{motivo}'. Use 1, 2 ou 9."
        chave = "".join(chave_nfse.split())
        if not chave:
            return "Erro: informe chave_nfse (chNFSe retornada na emissao)."
        data_xml = build_cancelar_nfse_envio(cfg, chave, motivo, MOTIVO_DESC[motivo])
        signed = _get_signer().sign_by_id(data_xml, "infPedReg")
        header = build_cabecalho(cfg.layout_version)
        resp = _get_soap().cancelar_nfse(header, signed)
        if resp.has_errors():
            return (
                f"=== Erro no Cancelamento Nacional (homolog) ===\n"
                f"Chave: {chave}\n"
                f"Motivo: {motivo} - {MOTIVO_DESC[motivo]}\n"
                f"Erros:\n{_format_errors(resp)}"
            )
        return (
            f"=== Cancelamento Nacional enviado (homologacao DF) ===\n"
            f"Chave: {chave}\n"
            f"Motivo: {motivo} - {MOTIVO_DESC[motivo]}\n"
            f"Data: {date.today().isoformat()}\n"
            "O DF trata o cancelamento como pedido de analise fiscal (evento e101103)."
        )
    except Exception as e:
        return f"Erro ao cancelar NFS-e Nacional (homolog): {e}"


def register_nacional_tools(mcp) -> None:
    mcp.tool()(nacional_homolog_emit_nfse)
    mcp.tool()(nacional_homolog_query_nfse)
    mcp.tool()(nacional_homolog_cancel_nfse)
