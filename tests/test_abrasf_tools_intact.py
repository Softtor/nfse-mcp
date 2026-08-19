from nfse_mcp.server import mcp


ABRASF_TOOLS = {
    "lookup_cnpj",
    "register_client",
    "list_clients",
    "emit_nfse",
    "emit_nfse_batch",
    "get_nfse_link",
    "cancel_nfse",
    "list_nfse",
    "query_cadastral_data",
}

NACIONAL_TOOLS = {
    "nacional_homolog_emit_nfse",
    "nacional_homolog_query_nfse",
    "nacional_homolog_cancel_nfse",
}


def _tool_names() -> set[str]:
    manager = getattr(mcp, "_tool_manager", None)
    assert manager is not None
    tools = getattr(manager, "_tools", None)
    if tools is None:
        tools = getattr(manager, "tools", None)
    assert tools is not None
    return set(tools)


def test_abrasf_tools_still_registered():
    names = _tool_names()
    missing = ABRASF_TOOLS - names
    assert not missing, f"Tools ABRASF 2.04 ausentes: {missing}"


def test_nacional_homolog_tools_registered():
    names = _tool_names()
    missing = NACIONAL_TOOLS - names
    assert not missing, f"Tools Nacional ausentes: {missing}"


def test_abrasf_tool_names_unchanged():
    names = _tool_names()
    renamed = {"emit_nfse_nacional", "emit_nfse_v2", "gerar_nfse"}
    assert ABRASF_TOOLS <= names
    assert not (renamed & ABRASF_TOOLS)
