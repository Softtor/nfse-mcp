"""MCP tool definitions.

All @mcp.tool() decorated functions live here. They delegate to Application Services
via the ServiceContainer and format results using MCP-specific formatters.
"""

from datetime import date

from nfse_mcp.cnpj_lookup import clean_document
from nfse_mcp.application.dto.commands import (
    IssueInvoiceCommand,
    CancelInvoiceCommand,
    ListInvoicesCommand,
    QueryParametersCommand,
    RegisterClientCommand,
)
from nfse_mcp.application.exceptions.application_error import ApplicationError, InvoiceError
from nfse_mcp.presentation.mcp.container import container
from nfse_mcp.presentation.mcp.formatters import (
    format_client,
    format_client_list,
    format_lookup_cnpj,
    format_issue_result_abrasf,
    format_issue_result_sefin,
    format_batch_result,
    format_cancel_result,
    format_nfse_links,
    format_list_invoices_result,
    format_cancelled_list,
    format_cadastral_data,
    format_query_sefin_result,
    format_parameters_result,
    format_municipality_not_enabled,
    format_baixar_nacional,
    format_cancelamento_nacional,
    format_lista_nacional,
)
from nfse_mcp.errors import MunicipalityNotEnabledError, ProviderError
from nfse_mcp.sefin_nacional.municipality_cache import MunicipalityCache
from nfse_mcp.sefin_nacional.municipality_data import MunicipalityDataLoader, EMISSOR_PROPRIO_SET

# The mcp instance is injected by server.py during registration
mcp = None  # type: ignore


def _today_str() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Client tools
# ---------------------------------------------------------------------------

def lookup_cnpj(cnpj: str) -> str:
    """Look up company data by CNPJ using BrasilAPI."""
    try:
        doc = clean_document(cnpj)
        if len(doc) != 14:
            return "Erro: CNPJ deve ter 14 digitos numericos."

        result = container.client_service().lookup_cnpj_data(doc)
        if result is None:
            return f"CNPJ {doc} nao encontrado ou erro na consulta."

        return format_lookup_cnpj(result, doc)
    except Exception as e:
        return f"Erro ao consultar CNPJ: {e}"


def register_client(
    document: str,
    razao_social: str = "",
    auto_lookup: bool = True,
) -> str:
    """Register a client (tomador) for NFS-e emission."""
    try:
        cmd = RegisterClientCommand(
            document=document,
            razao_social=razao_social,
            auto_lookup=auto_lookup,
        )
        service = container.client_service()
        doc_clean = clean_document(cmd.document)
        existing = service.find_by_document(doc_clean)
        is_new = existing is None

        client = service.register_client(
            document=cmd.document,
            razao_social=cmd.razao_social,
            auto_lookup=cmd.auto_lookup,
        )

        header = "=== Cliente Registrado ===" if is_new else "=== Cliente Existente ==="
        return f"{header}\n{format_client(client)}"
    except Exception as e:
        return f"Erro ao registrar cliente: {e}"


def list_clients() -> str:
    """List all registered clients (tomadores)."""
    try:
        clients = container.client_service().list_clients()
        return format_client_list(clients)
    except Exception as e:
        return f"Erro ao listar clientes: {e}"


# ---------------------------------------------------------------------------
# ABRASF tools
# ---------------------------------------------------------------------------

def emit_nfse(
    client_document: str,
    valor: str,
    discriminacao: str,
    competencia: str = "",
    cnae: str = "",
    aliquota: str = "",
    item_lista_servico: str = "",
    codigo_tributacao_municipio: str = "",
) -> str:
    """Emit a single NFS-e via ISS.net ABRASF 2.04."""
    try:
        cmd = IssueInvoiceCommand(
            client_document=client_document,
            valor=valor,
            discriminacao=discriminacao,
            competencia=competencia or None,
            cnae=cnae or None,
            aliquota=aliquota or None,
            item_lista_servico=item_lista_servico or None,
            codigo_tributacao_municipio=codigo_tributacao_municipio or None,
        )
        service = container.abrasf_service()
        result = service.issue_invoice(cmd)

        client = container.client_service().find_or_register_client(cmd.client_document)
        return format_issue_result_abrasf(
            result, client, cmd.valor, cmd.competencia or _today_str(), _today_str()
        )
    except ApplicationError as e:
        return f"Erro: {e.message}"
    except Exception as e:
        return f"Erro ao emitir NFS-e: {e}"


def emit_nfse_batch(csv_data: str) -> str:
    """Emit multiple NFS-e from CSV data in a single batch."""
    try:
        results = container.abrasf_service().issue_batch(csv_data)
        return format_batch_result(results)
    except ApplicationError as e:
        return f"Erro: {e.message}"
    except Exception as e:
        return f"Erro ao emitir lote: {e}"


def get_nfse_link(
    nfse_number: str = "",
    periodo_inicio: str = "",
    periodo_fim: str = "",
) -> str:
    """Get the visualization URL for NFS-e(s)."""
    try:
        links = container.abrasf_service().get_nfse_link(nfse_number, periodo_inicio, periodo_fim)
        return format_nfse_links(links)
    except ApplicationError as e:
        return f"Erro: {e.message}"
    except Exception as e:
        return f"Erro ao consultar link: {e}"


def cancel_nfse(nfse_number: str, motivo: str = "1") -> str:
    """Cancel an issued NFS-e."""
    try:
        cmd = CancelInvoiceCommand(nfse_number=nfse_number, motivo=motivo)
        result = container.abrasf_service().cancel_invoice(cmd)
        return format_cancel_result(result, _today_str())
    except InvoiceError as e:
        if e.errors:
            detalhes = "; ".join(f"[{d.get('codigo')}] {d.get('descricao')}" for d in e.errors)
            return f"Erro: {e.message} — {detalhes}"
        return f"Erro: {e.message}"
    except ApplicationError as e:
        return f"Erro: {e.message}"
    except Exception as e:
        return f"Erro ao cancelar NFS-e: {e}"


def list_nfse(data_inicial: str = "", data_final: str = "") -> str:
    """List NFS-e invoices issued in a period."""
    try:
        cmd = ListInvoicesCommand(
            data_inicial=data_inicial or None,
            data_final=data_final or None,
        )
        data = container.abrasf_service().list_invoices(cmd)
        return format_list_invoices_result(data)
    except ApplicationError as e:
        return f"Erro: {e.message}"
    except Exception as e:
        return f"Erro ao listar NFS-e: {e}"


def list_cancelled_nfse() -> str:
    """List all NFS-e invoices that have been cancelled (from local log)."""
    try:
        log = container.abrasf_service().list_cancelled_invoices()
        return format_cancelled_list(log)
    except Exception as e:
        return f"Erro ao listar cancelamentos: {e}"


def query_cadastral_data() -> str:
    """Query the provider's cadastral data from the ISS.net webservice."""
    try:
        data = container.abrasf_service().query_cadastral_data()
        return format_cadastral_data(data)
    except ApplicationError as e:
        return f"Erro: {e.message}"
    except Exception as e:
        return f"Erro ao consultar dados cadastrais: {e}"


# ---------------------------------------------------------------------------
# SEFIN Nacional tools
# ---------------------------------------------------------------------------

def emit_nfse_nacional(
    client_document: str,
    valor: str,
    discriminacao: str,
    competencia: str = "",
    codigo_servico: str = "",
    aliquota: str = "",
    codigo_municipio: str = "5300108",
    codigo_tributacao_municipio: str = "",
) -> str:
    """Emit a NFS-e via SEFIN Nacional (REST API with mTLS)."""
    try:
        # Pre-check: known own-issuer municipalities should use ABRASF/ISS.net
        loader = MunicipalityDataLoader()
        if loader.is_emissor_proprio(codigo_municipio):
            return (
                f"=== Emissor Próprio Detectado ===\n\n"
                f"O município {codigo_municipio} mantém emissor próprio (ISS.net/ABRASF) "
                f"e não utiliza os emissores públicos nacionais.\n\n"
                f"Para emitir NFS-e neste município, use a função 'emit_nfse' "
                f"(ABRASF 2.04 / ISS.net via SOAP) em vez de 'emit_nfse_nacional'.\n\n"
                f"Dica: use 'verificar_habilitacao_municipio({codigo_municipio})' "
                f"para mais detalhes."
            )

        cmd = IssueInvoiceCommand(
            client_document=client_document,
            valor=valor,
            discriminacao=discriminacao,
            competencia=competencia or None,
            codigo_servico=codigo_servico or None,
            aliquota=aliquota or None,
            codigo_municipio=codigo_municipio,
            codigo_tributacao_municipio=codigo_tributacao_municipio,
        )
        result = container.sefin_service().issue_invoice(cmd)
        client = container.client_service().find_or_register_client(cmd.client_document)
        return format_issue_result_sefin(result, client, cmd.valor, cmd.competencia or _today_str())
    except MunicipalityNotEnabledError as e:
        return format_municipality_not_enabled(e.municipality_code)
    except ApplicationError as e:
        return f"Erro: {e.message}"
    except Exception as e:
        return _erro(e)


def emit_nfse_unificado(
    client_document: str,
    valor: str,
    discriminacao: str,
    competencia: str = "",
    codigo_servico: str = "",
    aliquota: str = "",
    codigo_municipio: str = "5300108",
    codigo_tributacao_municipio: str = "",
) -> str:
    """Emit a NFS-e using the best available provider (SEFIN Nacional or ABRASF/ISS.net).

    This function automatically selects the correct provider based on the municipality:
    - SEFIN Nacional for municipalities with national public issuers
    - ABRASF/ISS.net for municipalities that maintain their own issuer
    - Intelligent fallback if the provider is unknown
    """
    try:
        cmd = IssueInvoiceCommand(
            client_document=client_document,
            valor=valor,
            discriminacao=discriminacao,
            competencia=competencia or None,
            codigo_servico=codigo_servico or None,
            aliquota=aliquota or None,
            codigo_municipio=codigo_municipio,
            codigo_tributacao_municipio=codigo_tributacao_municipio,
        )
        result = container.router_service().issue_invoice(cmd)
        client = container.client_service().find_or_register_client(cmd.client_document)
        # Determine which provider was actually used by checking the result type
        # Both return similar structures, but we can infer from the provider used
        if hasattr(result, 'chave_acesso') and result.chave_acesso:
            # SEFIN Nacional result
            return format_issue_result_sefin(result, client, cmd.valor, cmd.competencia or _today_str())
        else:
            # ABRASF result
            return format_issue_result_abrasf(
                result, client, cmd.valor, cmd.competencia or _today_str(), _today_str()
            )
    except ApplicationError as e:
        return f"Erro: {e.message}"
    except Exception as e:
        return _erro(e)


def consultar_nfse_nacional(chave_acesso: str) -> str:
    """Query a NFS-e by access key via SEFIN Nacional."""
    try:
        result = container.sefin_service().query_by_access_key(chave_acesso)
        return format_query_sefin_result(result)
    except Exception as e:
        return f"Erro ao consultar NFS-e: {e}"


def _erro(e: Exception) -> str:
    """Mensagem de erro da tool, com os detalhes (Complemento) que a SEFIN devolveu."""
    detalhes = getattr(e, "errors", None) or getattr(e, "raw_errors", None) or getattr(e, "validation_errors", None)
    texto = f"Erro: {getattr(e, 'message', e)}"
    if detalhes:
        texto += " — " + "; ".join(f"[{d.get('codigo')}] {d.get('descricao')}" if isinstance(d, dict) else str(d)
                                   for d in detalhes)
    return texto


def list_nfse_nacional(data_inicial: str = "", data_final: str = "") -> str:
    """Lista as NFS-e do Emissor Nacional emitidas por esta ferramenta (log local), com DPS, data, tomador,
    valor, status (emitida/pendente/nao_emitida/cancelada) e chave de acesso. Datas AAAA-MM-DD, opcionais."""
    return format_lista_nacional(container.sefin_service().list_invoices(data_inicial, data_final))


def baixar_nfse_nacional(chave_acesso: str, pasta: str = "") -> str:
    """Baixa a NFS-e nacional pela chave de acesso: grava o XML (e o PDF, se o governo devolver) em
    <pasta>/NFSe-<numero>-<chave>.xml (padrão data/xml/) e devolve o link da Consulta Pública."""
    try:
        return format_baixar_nacional(container.sefin_service().baixar_nfse(chave_acesso, pasta), chave_acesso)
    except (ApplicationError, ProviderError) as e:
        return _erro(e)


def cancelar_nfse_nacional(chave_acesso: str, motivo: str = "1", descricao: str = "", confirmar: bool = False) -> str:
    """Cancela uma NFS-e do Emissor Nacional emitida por esta ferramenta (status emitida no log local).

    motivo: 1=Erro na emissão, 2=Serviço não prestado, 9=Outros. descricao: 15 a 255 caracteres.
    Sem confirmar (padrão) NADA é enviado: devolve a prévia (ambiente, nº NFS-e, tomador, valor, competência).
    Mostre a prévia ao usuário e só chame com confirmar=True depois que ele confirmar por escrito.
    Cancelamento é irreversível."""
    try:
        r = container.sefin_service().cancel_invoice(chave_acesso, motivo, descricao, confirmar)
        return format_cancelamento_nacional(r)
    except (ApplicationError, ProviderError) as e:
        return _erro(e)


def consultar_parametros_municipais(codigo_municipio: str, codigo_servico: str = "") -> str:
    """Query municipal parameters (convenio, aliquotas, regimes) via SEFIN Nacional."""
    try:
        cmd = QueryParametersCommand(
            codigo_municipio=codigo_municipio,
            codigo_servico=codigo_servico or None,
        )
        data = container.sefin_service().query_parameters(cmd)
        return format_parameters_result(data)
    except ApplicationError as e:
        return f"Erro: {e.message}"
    except Exception as e:
        return f"Erro ao consultar parametros municipais: {e}"


def verificar_habilitacao_municipio(codigo_municipio: str) -> str:
    """Verify if a municipality is enabled for national public NFS-e issuers.

    Checks in order:
    1. Local cache of previous attempts
    2. External data (official Receita Federal spreadsheet snapshot)
    3. SEFIN Nacional API (convenio endpoint)
    """
    try:
        lines = [
            f"=== Verificação de Habilitação — Município {codigo_municipio} ===",
            "",
        ]

        cache = MunicipalityCache()
        cached = cache.get(codigo_municipio)
        if cached:
            lines.append(f"[Cache local] Status: {cached.status}")
            if cached.last_checked:
                lines.append(f"[Cache local] Verificado em: {cached.last_checked}")
            if cached.source:
                lines.append(f"[Cache local] Fonte: {cached.source}")
            lines.append("")

        loader = MunicipalityDataLoader()
        external = loader.get_status(codigo_municipio)
        if external:
            lines.append(f"[Dados externos] Nome: {external.nome} / {external.uf}")
            lines.append(f"[Dados externos] Conveniado: {'Sim' if external.conveniado else 'Não'}")
            if external.emissor_nacional is True:
                lines.append("[Dados externos] Emissores públicos nacionais: HABILITADO ✅")
            elif external.emissor_nacional is False:
                lines.append("[Dados externos] Emissores públicos nacionais: NÃO HABILITADO ❌")
            else:
                lines.append("[Dados externos] Emissores públicos nacionais: Não informado")
            if external.data_atualizacao:
                lines.append(f"[Dados externos] Atualizado em: {external.data_atualizacao}")
            lines.append("")

        # Strong signal: known own-issuer municipality
        if loader.is_emissor_proprio(codigo_municipio):
            lines.append("⚠️  ATENÇÃO: Este município mantém EMISSOR PRÓPRIO (ISS.net/ABRASF).")
            lines.append("    → Para emitir NFS-e, use a função 'emit_nfse' (ABRASF/ISS.net via SOAP).")
            lines.append("    → NÃO use 'emit_nfse_nacional' (SEFIN Nacional REST API).")
            lines.append("")

        # Fallback to API
        sefin_service = container.sefin_service()
        try:
            convenio = sefin_service.get_agreement(codigo_municipio)
            lines.append(f"[API SEFIN] Conveniado: {'Sim' if convenio.conveniado else 'Não'}")
            if convenio.data_adesao:
                lines.append(f"[API SEFIN] Data de adesão: {convenio.data_adesao}")
            if convenio.emissores_publicos_habilitados is True:
                lines.append("[API SEFIN] Emissores públicos nacionais: HABILITADO ✅")
            elif convenio.emissores_publicos_habilitados is False:
                lines.append("[API SEFIN] Emissores públicos nacionais: NÃO HABILITADO ❌")
            else:
                lines.append("[API SEFIN] Emissores públicos nacionais: NÃO VERIFICÁVEL VIA API ⚠️")
        except Exception as api_exc:
            lines.append(f"[API SEFIN] Erro ao consultar convênio: {api_exc}")

        lines.extend([
            "",
            "---",
            "",
            "⚠️ IMPORTANTE:",
            "  • 'Conveniado' ≠ 'Habilitado para emissores públicos nacionais'",
            "  • Um município pode ser conveniado mas manter seu emissor próprio (ADN apenas).",
            "  • A única forma DEFINITIVA de confirmar é tentar emitir uma nota real.",
            "  • Se receber erro E0039, o município ainda não habilitou os emissores públicos.",
            "",
            "Links úteis:",
            "  • Monitoramento de adesões: https://www.gov.br/nfse/pt-br/municipios/monitoramento-adesoes",
            "  • Lista de municípios aderentes: https://www.gov.br/nfse/pt-br/municipios/municipios-aderentes",
        ])

        return "\n".join(lines)
    except Exception as e:
        return f"Erro ao verificar habilitação do município: {e}"


# ---------------------------------------------------------------------------
# Tool registration mapping
# ---------------------------------------------------------------------------

TOOL_REGISTRY = [
    lookup_cnpj,
    register_client,
    list_clients,
    emit_nfse,
    emit_nfse_batch,
    get_nfse_link,
    cancel_nfse,
    list_nfse,
    list_cancelled_nfse,
    query_cadastral_data,
    emit_nfse_nacional,
    emit_nfse_unificado,
    consultar_nfse_nacional,
    consultar_parametros_municipais,
    verificar_habilitacao_municipio,
    list_nfse_nacional,
    baixar_nfse_nacional,
    cancelar_nfse_nacional,
]


def register_tools(mcp_instance):
    """Register all tools on the given FastMCP instance."""
    global mcp
    mcp = mcp_instance
    for tool_fn in TOOL_REGISTRY:
        mcp_instance.tool()(tool_fn)
