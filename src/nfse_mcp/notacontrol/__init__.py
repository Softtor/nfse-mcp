"""Transporte SOAP do padrão nacional NFS-e (ISS.net / Nota Control).

Substitui o padrão ABRASF 2.04 em `nfse_mcp.abrasf`. Mantém o envelope SOAP e a
assinatura SHA-1 do padrão antigo, mas troca o modelo de dados de RPS para DPS
(layout em `nfse_mcp.nacional`).
"""
