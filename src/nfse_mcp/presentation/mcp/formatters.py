"""MCP-specific string formatters.

Convert domain/application results into human-readable strings for MCP tool responses.
"""

from nfse_mcp.models import Client, NfseResult


def format_client(client: Client) -> str:
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


def format_client_list(clients: list[Client]) -> str:
    """Format a list of clients as a table."""
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


def format_lookup_cnpj(result: dict, cnpj: str) -> str:
    """Format CNPJ lookup result."""
    lines = [
        f"=== Dados do CNPJ {cnpj} ===",
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


def format_issue_result_abrasf(
    result: NfseResult,
    client: Client,
    valor: str,
    competencia: str,
    today_str: str,
) -> str:
    """Format successful ABRASF issuance result."""
    if not result.success:
        errors = "\n".join(f"  - {e}" for e in result.errors)
        return (
            f"=== Erro na Emissao ===\n"
            f"RPS: {result.numero_rps}\n"
            f"Cliente: {client.razao_social}\n"
            f"Valor: R$ {valor}\n"
            f"Erros:\n{errors}"
        )

    lines = [
        "=== NFS-e Emitida com Sucesso ===",
        f"NFS-e Numero: {result.numero_nfse}",
        f"RPS Numero: {result.numero_rps}",
        f"Data Emissao: {result.data_emissao or today_str}",
        f"Cliente: {client.razao_social} ({client.document})",
        f"Valor: R$ {valor}",
        f"Competencia: {competencia}",
    ]
    if result.codigo_verificacao:
        lines.append(f"Codigo Verificacao: {result.codigo_verificacao}")
    if result.url_visualizacao:
        lines.append(f"Link: {result.url_visualizacao}")
    return "\n".join(lines)


def format_batch_result(results: list[dict]) -> str:
    """Format batch issuance results."""
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = len(results) - success_count

    lines = [
        f"=== Emissao em Lote ({len(results)} notas) ===",
        "",
    ]

    for r in results:
        line_num = r.get("line", 0)
        if r.get("status") == "error":
            lines.append(f"Linha {line_num}: ERRO - {r.get('message', '')}")
        else:
            msg = (
                f"Linha {line_num}: OK - NFS-e #{r.get('nfse_number')} | "
                f"RPS #{r.get('rps_number')} | {r.get('client_name')} | R$ {r.get('valor')}"
            )
            lines.append(msg)
            if r.get("url"):
                lines.append(f"  Link: {r['url']}")

    lines.extend(["", f"Resumo: {success_count} emitidas, {error_count} erros"])
    return "\n".join(lines)


def format_cancel_result(result: dict, today_str: str) -> str:
    """Format successful cancellation result."""
    return (
        f"=== NFS-e Cancelada com Sucesso ===\n"
        f"NFS-e Numero: {result['nfse_number']}\n"
        f"Motivo: {result['motivo']} - {result['motivo_descricao']}\n"
        f"Data: {today_str}"
    )


def format_nfse_links(links: list[dict]) -> str:
    """Format NFS-e link query result."""
    if not links:
        return "Nenhum link encontrado para os parametros informados."

    lines = ["=== Links NFS-e ===", ""]
    for i, link in enumerate(links, 1):
        lines.append(f"--- Link #{i} ---")
        for key, val in link.items():
            lines.append(f"  {key}: {val}")
        lines.append("")
    return "\n".join(lines)


def format_list_invoices_result(data: dict) -> str:
    """Format invoice listing result."""
    notas = data.get("notas", [])
    if not notas:
        return f"Nenhuma NFS-e encontrada no periodo {data['periodo_inicial']} a {data['periodo_final']}."

    canceladas = data.get("total_canceladas", 0)
    resumo = f"Total: {data['total']} nota(s)"
    if canceladas:
        resumo += f" — {data.get('total_ativas', 0)} ativa(s), {canceladas} cancelada(s)"

    lines = [
        f"=== NFS-e Emitidas ({data['periodo_inicial']} a {data['periodo_final']}) ===",
        resumo,
        "",
        f"{'NFS-e':<8} {'Status':<11} {'Data':<22} {'Valor':>14} {'Tomador':<40}",
        "-" * 98,
    ]

    for nfse in notas:
        numero = nfse.get("numero", "-")
        data_emissao = nfse.get("data_emissao", "-")
        valor = nfse.get("valor", 0.0)
        tomador = nfse.get("tomador", "-")
        status = nfse.get("status", "Ativa")
        valor_fmt = f"R$ {valor:,.2f}"
        lines.append(
            f"{numero:<8} {status:<11} {data_emissao[:22]:<22} "
            f"{valor_fmt:>14} {(tomador or '-')[:40]:<40}"
        )

    lines.append("-" * 98)
    if canceladas:
        lines.append(
            f"{'Total (somente ativas)':>55} R$ {data.get('valor_total', 0.0):,.2f}"
        )
    else:
        lines.append(f"{'Total':>55} R$ {data.get('valor_total', 0.0):,.2f}")
    return "\n".join(lines)


def format_cancelled_list(log: list[dict]) -> str:
    """Format cancelled invoices log."""
    if not log:
        return "Nenhuma NFS-e cancelada registrada na base local."

    lines = [
        f"=== {len(log)} NFS-e(s) Cancelada(s) ===",
        "",
        f"{'NFS-e':<8} {'Data Emissao':<12} {'Data Canc.':<12} {'Valor':>12} {'Motivo':<25} {'Cliente':<35}",
        "-" * 110,
    ]

    total_valor = 0.0
    for entry in log:
        numero = entry.get("nfse_number", "-")
        data_emissao = entry.get("data_emissao", "-")
        data_cancel = entry.get("data_cancelamento", "-")
        valor_str = entry.get("valor", "0")
        motivo = entry.get("motivo_descricao", "-")
        cliente = entry.get("client_name", "-")

        try:
            valor_num = float(valor_str)
            total_valor += valor_num
            valor_fmt = f"R$ {valor_num:,.2f}"
        except (ValueError, TypeError):
            valor_fmt = f"R$ {valor_str}"

        lines.append(
            f"{numero:<8} {data_emissao:<12} {data_cancel:<12} {valor_fmt:>12} {motivo[:25]:<25} {(cliente or '-')[:35]:<35}"
        )

    lines.extend([
        "-" * 110,
        f"{'Total':>53} R$ {total_valor:,.2f}",
    ])
    return "\n".join(lines)


def format_cadastral_data(data: dict) -> str:
    """Format cadastral data query result."""
    lines = [
        "=== Dados Cadastrais do Prestador ===",
        f"CNPJ: {data['provider_cnpj']}",
        f"Inscricao Municipal: {data['provider_im']}",
        f"Razao Social: {data['provider_razao_social']}",
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

    lines.extend(_flatten(data["dados"]))
    return "\n".join(lines)


def format_issue_result_sefin(result, client, valor: str, competencia: str) -> str:
    """Format successful SEFIN Nacional issuance result."""
    if not result.success:
        errors = "\n".join(
            f"  [{e.get('codigo', '')}] {e.get('descricao', '')}" for e in result.errors
        )
        return (
            f"=== Erro na Emissao SEFIN Nacional ===\n"
            f"Cliente: {client.razao_social}\n"
            f"Valor: R$ {valor}\n"
            f"Erros:\n{errors}"
        )

    lines = [
        "=== NFS-e Emitida com Sucesso (SEFIN Nacional) ===",
        f"Chave de Acesso: {result.chave_acesso}",
        f"idDPS: {result.id_dps}",
        f"Cliente: {client.razao_social} ({client.document})",
        f"Valor: R$ {valor}",
        f"Competencia: {competencia}",
    ]
    if result.data_hora_processamento:
        lines.append(f"Data/Hora Processamento: {result.data_hora_processamento}")
    return "\n".join(lines)


def format_municipality_not_enabled(municipality_code: str) -> str:
    """Format MunicipalityNotEnabledError for MCP output."""
    lines = [
        f"=== Erro E0039 — Município Não Habilitado ===",
        f"Código IBGE: {municipality_code}",
        "",
        "O município está conveniado ao Sistema Nacional NFS-e, mas NÃO habilitou",
        "os emissores públicos nacionais (Web, Mobile, API).",
        "",
        "Possíveis causas:",
        "  • O gestor municipal ainda não ativou essa opção no painel administrativo.",
        "  • O município optou por manter seu emissor próprio (ISS.net/ABRASF) e apenas",
        "    compartilha os dados com o Ambiente Nacional de Dados (ADN).",
        "",
        "Próximos passos:",
        "  1. Verifique se o município mantém emissor próprio usando a função",
        "     'verificar_habilitacao_municipio'.",
        "  2. Se o município mantém emissor próprio, use a função 'emit_nfse' (ABRASF/ISS.net)",
        "     em vez de 'emit_nfse_nacional' (SEFIN Nacional).",
        "  3. Se o município deveria usar emissores públicos nacionais, entre em contato",
        "     com a administração tributária municipal para verificar a parametrização.",
        "  4. Consulte a lista oficial de municípios aderentes em:",
        "     https://www.gov.br/nfse/pt-br/municipios/monitoramento-adesoes",
    ]
    return "\n".join(lines)


def format_query_sefin_result(result) -> str:
    """Format SEFIN Nacional query result."""
    if not result.success:
        errors = "\n".join(
            f"  [{e.get('codigo', '')}] {e.get('descricao', '')}" for e in result.errors
        )
        return f"=== Erro na Consulta ===\nErros:\n{errors}"

    lines = [
        "=== NFS-e Consultada (SEFIN Nacional) ===",
        f"Chave de Acesso: {result.chave_acesso}",
        f"Status: {result.status or 'autorizada'}",
    ]
    if result.xml_nfse:
        lines.append(f"XML NFSe: {len(result.xml_nfse)} caracteres")
    return "\n".join(lines)


def format_parameters_result(data: dict) -> str:
    """Format municipal parameters query result."""
    convenio = data["convenio"]
    lines = [
        f"=== Parametros Municipais ===",
        f"Conveniado: {'Sim' if convenio.conveniado else 'Nao'}",
    ]
    if convenio.data_adesao:
        lines.append(f"Data Adesao: {convenio.data_adesao}")

    if convenio.emissores_publicos_habilitados is True:
        lines.append("Emissores Publicos Nacionais: Habilitado ✅")
    elif convenio.emissores_publicos_habilitados is False:
        lines.append("Emissores Publicos Nacionais: NAO HABILITADO ❌")
        lines.append("  -> O município está conveniado, mas ainda não habilitou os emissores públicos nacionais.")
        lines.append("  -> Entre em contato com a administração tributária municipal para verificar a parametrização.")
    else:
        lines.append("Emissores Publicos Nacionais: Não verificável via API ⚠️")
        lines.append("  -> 'Conveniado' não significa que os emissores públicos nacionais estejam habilitados.")
        lines.append("  -> A única forma definitiva de confirmar é tentar emitir uma nota real.")
        lines.append("  -> Se receber erro E0039, o município ainda não habilitou essa opção.")

    if "service_params" in data:
        params = data["service_params"]
        lines.append(f"\n--- Servico ---")
        if params.aliquotas:
            lines.append(f"Aliquotas: {len(params.aliquotas)} registros")
        if params.regimes_especiais:
            lines.append(f"Regimes Especiais: {len(params.regimes_especiais)} registros")
        if params.deducoes:
            lines.append(f"Deduções: {len(params.deducoes)} registros")

    return "\n".join(lines)


def format_lista_nacional(entries: list[dict]) -> str:
    """NFS-e do Emissor Nacional no log local."""
    if not entries:
        return "Nenhuma NFS-e nacional no log local para o periodo."
    lines = [f"=== {len(entries)} NFS-e nacional(is) (log local) ===", ""]
    for e in entries:
        lines.append(
            f"DPS {e.get('numero_dps', '-')} | {e.get('date', '-')} | {e.get('client_name', '-')} | "
            f"R$ {e.get('valor', '-')} | {e.get('status', '-')} | chave {e.get('chave_acesso', '-')}"
        )
    lines += ["", "Limite: so notas emitidas por esta ferramenta (a API nacional nao lista as notas do emitente)."]
    return "\n".join(lines)


def format_baixar_nacional(r: dict, chave_acesso: str) -> str:
    """Arquivos gravados e link da consulta pública."""
    pdf = r["pdf"] or "nao gerado: o governo nao esta devolvendo o PDF (DANFSe) pelo ADN"
    return "\n".join([
        f"=== NFS-e {r['numero']} baixada ===",
        f"XML: {r['xml']}",
        f"PDF: {pdf}",
        f"Consulta publica (visualizar/baixar o PDF): {r['link']}",
        f"Chave para colar na consulta: {chave_acesso}",
    ])


def format_cancelamento_nacional(r: dict) -> str:
    """Prévia (nada enviado) ou confirmação do cancelamento, sempre com os dados da nota."""
    titulo = ("=== NFS-e CANCELADA ===" if r["enviado"]
              else "=== Previa do cancelamento (NADA FOI ENVIADO) ===")
    lines = [
        titulo,
        f"Ambiente: {r['ambiente']}",
        f"NFS-e: {r['numero']}",
        f"Tomador: {r['tomador']}",
        f"Valor: R$ {r['valor']}",
        f"Competencia: {r['competencia']}",
        f"Chave: {r['chave_acesso']}",
    ]
    if not r["enviado"]:
        lines += ["", "Confira com o usuario. So depois da confirmacao por escrito, chame de novo com confirmar=True."]
    return "\n".join(lines)
