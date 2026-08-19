"""
MCP Server for NFS-e emission (Brasilia/DF - ISS.net ABRASF 2.04).

Provides tools for looking up CNPJs, managing clients, emitting/canceling
NFS-e invoices, and querying issued invoices via the ISS.net webservice.
"""

import csv
import io
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from nfse_mcp.certificate import Certificate
from nfse_mcp.client_store import ClientStore
from nfse_mcp.cnpj_lookup import clean_document
from nfse_mcp.cnpj_lookup import lookup_cnpj as _raw_lookup_cnpj
from nfse_mcp.config import Config, load_config
from nfse_mcp.models import Client, NfseResult, RpsData, ServiceData
from nfse_mcp.soap_client import SoapClient
from nfse_mcp.xml_builder import (
    build_cabecalho,
    build_cancelar_nfse_envio,
    build_consultar_dados_cadastrais_envio,
    build_consultar_nfse_servico_prestado_envio,
    build_consultar_url_nfse_envio,
    build_enviar_lote_rps_sincrono,
    build_gerar_nfse_envio,
    build_inf_declaracao_xml,
)
from nfse_mcp.xml_signer import XmlSigner
from nfse_mcp.nacional.tools import register_nacional_tools
from lxml import etree

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MCP app
# ---------------------------------------------------------------------------

mcp = FastMCP("nfse")

# ---------------------------------------------------------------------------
# Lazy-loaded global state
# ---------------------------------------------------------------------------

_config: Optional[Config] = None
_cert: Optional[Certificate] = None
_signer: Optional[XmlSigner] = None
_soap: Optional[SoapClient] = None
_store: Optional[ClientStore] = None


def _get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def _get_cert() -> Certificate:
    global _cert
    if _cert is None:
        cfg = _get_config()
        _cert = Certificate(cfg.certificate_path, cfg.certificate_password)
    return _cert


def _get_signer() -> XmlSigner:
    global _signer
    if _signer is None:
        _signer = XmlSigner(_get_cert())
    return _signer


def _get_soap() -> SoapClient:
    global _soap
    if _soap is None:
        _soap = SoapClient(_get_config(), _get_cert())
    return _soap


def _get_store() -> ClientStore:
    global _store
    if _store is None:
        _store = ClientStore(_get_config().data_dir)
    return _store


# ---------------------------------------------------------------------------
# RPS number (from webservice)
# ---------------------------------------------------------------------------

def _get_next_rps_number(config: Config, cert: Certificate, signer: XmlSigner) -> int:
    """Fetch next available RPS number from webservice."""
    NS = "http://www.abrasf.org.br/nfse.xsd"

    data_xml = (
        f'<ConsultarRpsDisponivelEnvio xmlns="{NS}">'
        f'<Pedido>'
        f'<Prestador>'
        f'<CpfCnpj><Cnpj>{config.provider.cnpj}</Cnpj></CpfCnpj>'
        f'<InscricaoMunicipal>{config.provider.im}</InscricaoMunicipal>'
        f'</Prestador>'
        f'<Pagina>1</Pagina>'
        f'</Pedido>'
        f'</ConsultarRpsDisponivelEnvio>'
    )

    signed = signer.sign_xml(data_xml)
    header = build_cabecalho()

    soap_client = SoapClient(config, cert)
    response = soap_client.consultar_rps_disponivel(header, signed)

    if response.xml_tree is not None:
        numeros = response.xml_tree.findall(f".//{{{NS}}}RpsDisponivel/{{{NS}}}Numero")
        if numeros:
            return int(numeros[0].text)

    raise Exception("Nao foi possivel obter numero de RPS disponivel")


# ---------------------------------------------------------------------------
# NFS-e log
# ---------------------------------------------------------------------------

def _nfse_log_path() -> Path:
    return _get_config().data_dir / "nfse_log.json"


def _load_nfse_log() -> list[dict]:
    path = _nfse_log_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return []
    return []


def _append_nfse_log(entry: dict) -> None:
    log = _load_nfse_log()
    log.append(entry)
    path = _nfse_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _today_str() -> str:
    return date.today().isoformat()


def _first_of_month() -> str:
    """Return the first day of the current month as YYYY-MM-DD."""
    today = date.today()
    return today.replace(day=1).isoformat()


def _last_of_month() -> str:
    """Return the last day of the current month as YYYY-MM-DD."""
    today = date.today()
    if today.month == 12:
        last = today.replace(year=today.year + 1, month=1, day=1)
    else:
        last = today.replace(month=today.month + 1, day=1)
    from datetime import timedelta
    last = last - timedelta(days=1)
    return last.isoformat()


def _format_client(client: Client) -> str:
    """Format a Client object as readable text."""
    lines = [
        f"Documento: {client.document} ({client.document_type.upper()})",
        f"Razao Social: {client.razao_social}",
    ]
    if client.nome_fantasia:
        lines.append(f"Nome Fantasia: {client.nome_fantasia}")
    if client.endereco:
        addr = client.endereco
        if client.numero:
            addr += f", {client.numero}"
        if client.complemento:
            addr += f" - {client.complemento}"
        lines.append(f"Endereco: {addr}")
    if client.bairro:
        lines.append(f"Bairro: {client.bairro}")
    if client.codigo_municipio:
        parts = []
        if client.uf:
            parts.append(client.uf)
        parts.append(f"IBGE: {client.codigo_municipio}")
        lines.append(f"Municipio: {' / '.join(parts)}")
    if client.cep:
        lines.append(f"CEP: {client.cep}")
    if client.telefone:
        lines.append(f"Telefone: {client.telefone}")
    if client.email:
        lines.append(f"Email: {client.email}")
    return "\n".join(lines)


def _parse_nfse_response(response, rps_number: int | None = None) -> NfseResult:
    """Parse an NfseResponse into an NfseResult."""
    if response.has_errors():
        errors = response.get_errors()
        error_msgs = []
        for e in errors:
            msg = e.get("Mensagem", "Erro desconhecido")
            cod = e.get("Codigo", "")
            correcao = e.get("Correcao", "")
            entry = f"[{cod}] {msg}"
            if correcao:
                entry += f" (Correcao: {correcao})"
            error_msgs.append(entry)
        return NfseResult(
            success=False,
            numero_rps=rps_number,
            errors=error_msgs,
        )

    nfse_list = response.get_nfse_list()
    if not nfse_list:
        return NfseResult(
            success=False,
            numero_rps=rps_number,
            errors=["Nenhuma NFS-e retornada na resposta"],
            mensagem=response.raw_xml[:500] if response.raw_xml else None,
        )

    nfse_data = nfse_list[0]
    return NfseResult(
        success=True,
        numero_nfse=nfse_data.get("Numero"),
        numero_rps=rps_number,
        codigo_verificacao=nfse_data.get("CodigoVerificacao"),
        data_emissao=nfse_data.get("DataEmissao"),
    )


def _find_or_register_client(document: str) -> Client:
    """Find existing client or auto-register by document."""
    store = _get_store()
    doc_clean = clean_document(document)
    client = store.find_by_document(doc_clean)
    if client is None:
        client = store.register(doc_clean, auto_lookup=True)
    return client


def _ensure_client_address(client: Client) -> Client:
    """Ensure client has all required address fields for NFS-e emission.

    If fields are missing, try BrasilAPI lookup. If still missing, fill defaults.
    """
    required = [client.endereco, client.numero, client.bairro,
                client.codigo_municipio, client.uf, client.cep]

    if all(required):
        return client

    # Try BrasilAPI lookup if CNPJ
    if client.document_type == "cnpj" and len(client.document) == 14:
        from nfse_mcp.cnpj_lookup import lookup_cnpj
        result = lookup_cnpj(client.document)
        if result:
            if not client.endereco:
                client.endereco = result.get("logradouro") or None
            if not client.numero:
                client.numero = result.get("numero") or None
            if not client.bairro:
                client.bairro = result.get("bairro") or None
            if not client.codigo_municipio:
                client.codigo_municipio = result.get("codigo_municipio_ibge") or None
            if not client.uf:
                client.uf = result.get("uf") or None
            if not client.cep:
                client.cep = result.get("cep") or None

    # Fill remaining gaps with defaults
    if not client.endereco:
        client.endereco = "Rua Nao Informada"
    if not client.numero:
        client.numero = "SN"
    if not client.bairro:
        client.bairro = "Nao Informado"
    if not client.codigo_municipio:
        client.codigo_municipio = "5300108"  # Brasilia
    if not client.uf:
        client.uf = "DF"
    if not client.cep:
        client.cep = "70000000"

    # Persist updates
    store = _get_store()
    store.update(
        client.id,
        endereco=client.endereco,
        numero=client.numero,
        bairro=client.bairro,
        codigo_municipio=client.codigo_municipio,
        uf=client.uf,
        cep=client.cep,
    )

    return client


def _build_signed_gerar_nfse(
    config: Config,
    signer: XmlSigner,
    rps: RpsData,
    service: ServiceData,
    client: Client,
    competencia: str,
) -> str:
    """Build a signed GerarNfseEnvio XML ready for SOAP submission.

    Signs InfDeclaracaoPrestacaoServico, then moves the Signature to be
    a sibling inside <Rps>, then wraps in <GerarNfseEnvio>.
    """
    NS = "http://www.abrasf.org.br/nfse.xsd"
    DS = "http://www.w3.org/2000/09/xmldsig#"

    # 1. Build InfDeclaracaoPrestacaoServico XML
    inf_xml = build_inf_declaracao_xml(config, rps, service, client, competencia)

    # 2. Sign it (enveloped - signature goes inside the element)
    signed_xml = signer.sign_xml(inf_xml)

    # 3. Parse and extract signature
    signed_el = etree.fromstring(signed_xml.encode("utf-8"))
    sig_el = signed_el.find(f"{{{DS}}}Signature")
    if sig_el is not None:
        signed_el.remove(sig_el)

    # 4. Build final structure: GerarNfseEnvio > Rps > [InfDeclaracaoPrestacaoServico, Signature]
    root = etree.Element(f"{{{NS}}}GerarNfseEnvio", nsmap={None: NS})
    rps_el = etree.SubElement(root, f"{{{NS}}}Rps")
    rps_el.append(signed_el)
    if sig_el is not None:
        rps_el.append(sig_el)

    return etree.tostring(root, encoding="unicode", xml_declaration=False)


def _try_get_url(nfse_number: str) -> str | None:
    """Attempt to get the NFS-e visualization URL. Returns None on failure."""
    try:
        cfg = _get_config()
        header = build_cabecalho()
        data_xml = build_consultar_url_nfse_envio(cfg, numero_nfse=nfse_number)
        signed = _get_signer().sign_xml(data_xml)
        resp = _get_soap().consultar_url_nfse(header, signed)
        if not resp.has_errors():
            links = resp.get_links()
            if links:
                # Return first URL found
                for link in links:
                    for key, val in link.items():
                        if isinstance(val, str) and val.startswith("http"):
                            return val
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def lookup_cnpj(cnpj: str) -> str:
    """Look up company data by CNPJ using BrasilAPI. Returns company info including razao social, address, CNAE, and registration status."""
    try:
        doc = clean_document(cnpj)
        if len(doc) != 14:
            return "Erro: CNPJ deve ter 14 digitos numericos."

        result = _raw_lookup_cnpj(doc)
        if result is None:
            return f"CNPJ {doc} nao encontrado ou erro na consulta."

        lines = [
            f"=== Dados do CNPJ {doc} ===",
            f"Razao Social: {result['razao_social']}",
            f"Nome Fantasia: {result['nome_fantasia'] or '-'}",
            f"Situacao: {result['situacao_cadastral']}",
            f"CNAE: {result['cnae_fiscal']} - {result['cnae_fiscal_descricao']}",
            f"Endereco: {result['logradouro']}, {result['numero']}",
        ]
        if result["complemento"]:
            lines.append(f"Complemento: {result['complemento']}")
        lines.extend([
            f"Bairro: {result['bairro']}",
            f"Municipio: {result['municipio']} / {result['uf']}",
            f"CEP: {result['cep']}",
            f"Codigo IBGE: {result['codigo_municipio_ibge']}",
            f"Telefone: {result['telefone'] or '-'}",
            f"Email: {result['email'] or '-'}",
        ])
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao consultar CNPJ: {e}"


@mcp.tool()
def register_client(
    document: str,
    razao_social: str = "",
    auto_lookup: bool = True,
) -> str:
    """Register a client (tomador) for NFS-e emission. If auto_lookup=True and document is CNPJ, automatically fills data from BrasilAPI. If the client already exists, returns existing data."""
    try:
        doc = clean_document(document)
        if not doc:
            return "Erro: documento vazio."

        store = _get_store()
        client = store.register(
            document=doc,
            razao_social=razao_social or None,
            auto_lookup=auto_lookup,
        )

        existing = store.find_by_document(doc)
        is_new = existing and existing.id == client.id

        header = "=== Cliente Registrado ===" if is_new else "=== Cliente Existente ==="
        return f"{header}\n{_format_client(client)}"
    except Exception as e:
        return f"Erro ao registrar cliente: {e}"


@mcp.tool()
def list_clients() -> str:
    """List all registered clients (tomadores). Returns a formatted table with document, name, and location."""
    try:
        store = _get_store()
        clients = store.list_all()

        if not clients:
            return "Nenhum cliente registrado."

        lines = [
            f"=== {len(clients)} Cliente(s) Registrado(s) ===",
            "",
            f"{'Documento':<20} {'Tipo':<6} {'Razao Social':<50} {'UF':<4} {'Municipio IBGE':<15}",
            "-" * 95,
        ]
        for c in clients:
            lines.append(
                f"{c.document:<20} {c.document_type.upper():<6} "
                f"{(c.razao_social or '-')[:50]:<50} "
                f"{(c.uf or '-'):<4} {(c.codigo_municipio or '-'):<15}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao listar clientes: {e}"


@mcp.tool()
def emit_nfse(
    client_document: str,
    valor: str,
    discriminacao: str,
    competencia: str = "",
    cnae: str = "",
    aliquota: str = "",
) -> str:
    """Emit a single NFS-e (electronic service invoice).

    Args:
        client_document: CNPJ or CPF of the service taker (tomador).
        valor: Service value as decimal string (e.g. "1000.00").
        discriminacao: Detailed service description.
        competencia: Competence date in YYYY-MM-DD format (defaults to 1st of current month).
        cnae: CNAE code override (uses config default if empty).
        aliquota: ISS tax rate override (uses config default if empty).

    Returns formatted result with NFS-e number, RPS number, and link.
    """
    try:
        cfg = _get_config()
        cert = _get_cert()
        signer = _get_signer()

        # 1. Find or auto-register client
        client = _find_or_register_client(client_document)
        if not client.razao_social:
            return (
                f"Erro: Cliente com documento {clean_document(client_document)} "
                "nao possui razao social. Registre o cliente primeiro com register_client."
            )

        # 2. Ensure client has complete address
        client = _ensure_client_address(client)

        # 3. Get next RPS number from webservice
        try:
            rps_num = _get_next_rps_number(cfg, cert, signer)
        except Exception as e:
            return f"Erro ao obter numero de RPS disponivel: {e}"

        # 4. Build data
        comp = competencia or _first_of_month()
        rps = RpsData(
            numero=rps_num,
            serie=cfg.rps_serie,
            tipo=1,
            data_emissao=_today_str(),
            status=1,
        )
        service = ServiceData(
            valor_servicos=valor,
            discriminacao=discriminacao,
            cnae=cnae,
            aliquota=aliquota,
        )

        # 5. Build signed XML (sign InfDeclaracaoPrestacaoServico, move sig into Rps)
        signed_xml = _build_signed_gerar_nfse(cfg, signer, rps, service, client, comp)

        # 6. Send via SOAP
        header_xml = build_cabecalho()
        response = _get_soap().gerar_nfse(header_xml, signed_xml)

        # 7. Parse response
        result = _parse_nfse_response(response, rps_number=rps_num)

        if not result.success:
            errors = "\n".join(f"  - {e}" for e in result.errors)
            return (
                f"=== Erro na Emissao ===\n"
                f"RPS: {rps_num}\n"
                f"Cliente: {client.razao_social}\n"
                f"Valor: R$ {valor}\n"
                f"Erros:\n{errors}"
            )

        # 8. Try to get URL
        url = None
        if result.numero_nfse:
            url = _try_get_url(result.numero_nfse)
            result.url_visualizacao = url

        # 9. Log result
        _append_nfse_log({
            "rps_number": rps_num,
            "nfse_number": result.numero_nfse,
            "date": _today_str(),
            "client_cnpj": client.document,
            "client_name": client.razao_social,
            "valor": valor,
            "url": url,
        })

        # 10. Format output
        lines = [
            "=== NFS-e Emitida com Sucesso ===",
            f"NFS-e Numero: {result.numero_nfse}",
            f"RPS Numero: {rps_num}",
            f"Data Emissao: {result.data_emissao or _today_str()}",
            f"Cliente: {client.razao_social} ({client.document})",
            f"Valor: R$ {valor}",
            f"Competencia: {comp}",
        ]
        if result.codigo_verificacao:
            lines.append(f"Codigo Verificacao: {result.codigo_verificacao}")
        if url:
            lines.append(f"Link: {url}")
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao emitir NFS-e: {e}"


@mcp.tool()
def emit_nfse_batch(csv_data: str) -> str:
    """Emit multiple NFS-e from CSV data in a single batch.

    CSV format (one row per invoice, header optional):
        cnpj,valor,discriminacao,competencia

    The competencia column is optional (defaults to 1st of current month).
    Each client is auto-registered if not already known.

    Returns results for each invoice in the batch.
    """
    try:
        cfg = _get_config()
        cert = _get_cert()
        signer = _get_signer()

        # Parse CSV
        reader = csv.reader(io.StringIO(csv_data.strip()))
        rows = list(reader)
        if not rows:
            return "Erro: CSV vazio."

        # Skip header if first row looks like a header
        first = rows[0]
        if first and first[0].lower().strip() in ("cnpj", "document", "documento"):
            rows = rows[1:]

        if not rows:
            return "Erro: Nenhuma linha de dados no CSV."

        result_lines = [f"=== Emissao em Lote ({len(rows)} notas) ===", ""]
        success_count = 0
        error_count = 0

        for i, row in enumerate(rows):
            if len(row) < 3:
                result_lines.append(f"Linha {i + 1}: ERRO - precisa de pelo menos 3 colunas (cnpj, valor, discriminacao)")
                error_count += 1
                continue

            doc = row[0].strip()
            valor = row[1].strip()
            discriminacao = row[2].strip()
            comp = row[3].strip() if len(row) > 3 and row[3].strip() else _first_of_month()

            try:
                client = _find_or_register_client(doc)
                if not client.razao_social:
                    result_lines.append(f"Linha {i + 1}: ERRO - cliente {doc} sem razao social")
                    error_count += 1
                    continue

                _ensure_client_address(client)

                rps_num = _get_next_rps_number(cfg, cert, signer)
                rps = RpsData(
                    numero=rps_num,
                    serie=cfg.rps_serie,
                    tipo=1,
                    data_emissao=_today_str(),
                    status=1,
                )
                service = ServiceData(
                    valor_servicos=valor,
                    discriminacao=discriminacao,
                )

                # Build signed XML and send via GerarNfse
                signed_xml = _build_signed_gerar_nfse(cfg, signer, rps, service, client, comp)
                header_xml = build_cabecalho()
                response = _get_soap().gerar_nfse(header_xml, signed_xml)

                if response.has_errors():
                    errors = response.get_errors()
                    error_msgs = "; ".join(f"[{e.get('Codigo','')}] {e.get('Mensagem','')}" for e in errors)
                    result_lines.append(f"Linha {i + 1}: ERRO - {client.razao_social}: {error_msgs}")
                    error_count += 1
                    continue

                # Parse success
                nfse_list = response.get_nfse_list()
                nfse_data = nfse_list[0] if nfse_list else {}
                nfse_number = nfse_data.get("Numero", "?")
                url = None
                if nfse_number and nfse_number != "?":
                    url = _try_get_url(nfse_number)

                _append_nfse_log({
                    "rps_number": rps_num,
                    "nfse_number": nfse_number,
                    "date": _today_str(),
                    "client_cnpj": doc,
                    "client_name": client.razao_social,
                    "valor": valor,
                    "url": url,
                })

                result_lines.append(f"Linha {i + 1}: OK - NFS-e #{nfse_number} | RPS #{rps_num} | {client.razao_social} | R$ {valor}")
                if url:
                    result_lines.append(f"  Link: {url}")
                success_count += 1

            except Exception as e:
                result_lines.append(f"Linha {i + 1}: ERRO - {doc}: {e}")
                error_count += 1

        result_lines.append("")
        result_lines.append(f"Resumo: {success_count} emitidas, {error_count} erros")

        return "\n".join(result_lines)
    except Exception as e:
        return f"Erro ao emitir lote: {e}"


@mcp.tool()
def get_nfse_link(
    nfse_number: str = "",
    periodo_inicio: str = "",
    periodo_fim: str = "",
) -> str:
    """Get the visualization URL for NFS-e(s). Query by invoice number or by emission period (YYYY-MM-DD).

    Args:
        nfse_number: Specific NFS-e number to get the link for.
        periodo_inicio: Start date for period query (YYYY-MM-DD).
        periodo_fim: End date for period query (YYYY-MM-DD).
    """
    try:
        cfg = _get_config()
        header = build_cabecalho()

        if nfse_number:
            data_xml = build_consultar_url_nfse_envio(cfg, numero_nfse=nfse_number)
        elif periodo_inicio and periodo_fim:
            data_xml = build_consultar_url_nfse_envio(
                cfg,
                data_inicial=periodo_inicio,
                data_final=periodo_fim,
            )
        else:
            return "Erro: informe nfse_number ou periodo_inicio + periodo_fim."

        signed = _get_signer().sign_xml(data_xml)
        response = _get_soap().consultar_url_nfse(header, signed)

        if response.has_errors():
            errors = response.get_errors()
            error_lines = [f"  [{e.get('Codigo', '')}] {e.get('Mensagem', '')}" for e in errors]
            return "=== Erro na Consulta ===\n" + "\n".join(error_lines)

        links = response.get_links()
        if not links:
            return "Nenhum link encontrado para os parametros informados."

        lines = ["=== Links NFS-e ===", ""]
        for i, link in enumerate(links, 1):
            lines.append(f"--- Link #{i} ---")
            for key, val in link.items():
                lines.append(f"  {key}: {val}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao consultar link: {e}"


@mcp.tool()
def cancel_nfse(nfse_number: str, motivo: str = "1") -> str:
    """Cancel an issued NFS-e.

    Args:
        nfse_number: Number of the NFS-e to cancel.
        motivo: Cancellation reason code. 1=Erro na Emissao, 2=Servico nao Prestado, 9=Outros.
    """
    try:
        cfg = _get_config()

        motivo_desc = {
            "1": "Erro na Emissao",
            "2": "Servico nao Prestado",
            "9": "Outros",
        }

        if motivo not in motivo_desc:
            return f"Erro: motivo invalido '{motivo}'. Use 1, 2 ou 9."

        # Build cancel XML
        data_xml = build_cancelar_nfse_envio(cfg, nfse_number, motivo)

        # Sign
        signed = _get_signer().sign_xml(data_xml)

        # Send
        header = build_cabecalho()
        response = _get_soap().cancelar_nfse(header, signed)

        if response.has_errors():
            errors = response.get_errors()
            error_lines = [f"  [{e.get('Codigo', '')}] {e.get('Mensagem', '')}" for e in errors]
            return (
                f"=== Erro no Cancelamento ===\n"
                f"NFS-e: {nfse_number}\n"
                f"Motivo: {motivo} - {motivo_desc[motivo]}\n"
                f"Erros:\n" + "\n".join(error_lines)
            )

        return (
            f"=== NFS-e Cancelada com Sucesso ===\n"
            f"NFS-e Numero: {nfse_number}\n"
            f"Motivo: {motivo} - {motivo_desc[motivo]}\n"
            f"Data: {_today_str()}"
        )
    except Exception as e:
        return f"Erro ao cancelar NFS-e: {e}"


@mcp.tool()
def list_nfse(data_inicial: str = "", data_final: str = "") -> str:
    """List NFS-e invoices issued in a period. Queries the webservice directly.

    Args:
        data_inicial: Start date (YYYY-MM-DD). Defaults to 1st of current month.
        data_final: End date (YYYY-MM-DD). Defaults to last day of current month.
    """
    try:
        cfg = _get_config()

        d_ini = data_inicial or _first_of_month()
        d_fim = data_final or _last_of_month()

        header = build_cabecalho()
        data_xml = build_consultar_nfse_servico_prestado_envio(cfg, d_ini, d_fim)
        signed = _get_signer().sign_xml(data_xml)
        response = _get_soap().consultar_nfse_servico_prestado(header, signed)

        if response.has_errors():
            errors = response.get_errors()
            error_lines = [f"  [{e.get('Codigo', '')}] {e.get('Mensagem', '')}" for e in errors]
            return (
                f"=== Erro na Consulta ===\n"
                f"Periodo: {d_ini} a {d_fim}\n"
                f"Erros:\n" + "\n".join(error_lines)
            )

        nfse_list = response.get_nfse_list()
        if not nfse_list:
            return f"Nenhuma NFS-e encontrada no periodo {d_ini} a {d_fim}."

        lines = [
            f"=== NFS-e Emitidas ({d_ini} a {d_fim}) ===",
            f"Total: {len(nfse_list)} nota(s)",
            "",
            f"{'NFS-e':<10} {'Data':<22} {'Valor':>14} {'Tomador':<40}",
            "-" * 88,
        ]

        total_valor = 0.0
        for nfse in nfse_list:
            numero = nfse.get("Numero", "-")
            data_emissao = nfse.get("DataEmissao", "-")
            valor_str = nfse.get("ValorServicos", "0")
            tomador = nfse.get("TomadorRazaoSocial", "-")

            try:
                valor_num = float(valor_str)
                total_valor += valor_num
                valor_fmt = f"R$ {valor_num:,.2f}"
            except (ValueError, TypeError):
                valor_fmt = f"R$ {valor_str}"

            lines.append(
                f"{numero:<10} {data_emissao[:22]:<22} {valor_fmt:>14} {(tomador or '-')[:40]:<40}"
            )

        lines.extend([
            "-" * 88,
            f"{'Total':>46} R$ {total_valor:,.2f}",
        ])
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao listar NFS-e: {e}"


@mcp.tool()
def query_cadastral_data() -> str:
    """Query the provider's cadastral data from the ISS.net webservice. Useful for verifying registration status and provider information."""
    try:
        cfg = _get_config()
        header = build_cabecalho()
        data_xml = build_consultar_dados_cadastrais_envio(cfg)
        signed = _get_signer().sign_xml(data_xml)
        response = _get_soap().consultar_dados_cadastrais(header, signed)

        if response.has_errors():
            errors = response.get_errors()
            error_lines = [f"  [{e.get('Codigo', '')}] {e.get('Mensagem', '')}" for e in errors]
            return "=== Erro na Consulta Cadastral ===\n" + "\n".join(error_lines)

        # Parse the JSON representation for display
        json_str = response.to_json()
        data = json.loads(json_str)

        lines = [
            "=== Dados Cadastrais do Prestador ===",
            f"CNPJ: {cfg.provider.cnpj}",
            f"Inscricao Municipal: {cfg.provider.im}",
            f"Razao Social: {cfg.provider.razao_social}",
            "",
            "--- Dados do Webservice ---",
        ]

        def _flatten(d: dict, prefix: str = "") -> list[str]:
            items = []
            for k, v in d.items():
                full_key = f"{prefix}{k}" if not prefix else f"{prefix}.{k}"
                if isinstance(v, dict):
                    items.extend(_flatten(v, full_key))
                elif isinstance(v, list):
                    for i, item in enumerate(v):
                        if isinstance(item, dict):
                            items.extend(_flatten(item, f"{full_key}[{i}]"))
                        else:
                            items.append(f"{full_key}[{i}]: {item}")
                else:
                    items.append(f"{full_key}: {v}")
            return items

        lines.extend(_flatten(data))
        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao consultar dados cadastrais: {e}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

register_nacional_tools(mcp)


def main():
    """Run the NFS-e MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
