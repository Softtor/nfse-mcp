"""Command DTOs for application services.

These are protocol-agnostic input objects used by Application Services.
They can be created from MCP tool arguments, HTTP request bodies, or CLI flags.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class IssueInvoiceCommand:
    """Command to issue a service invoice."""

    client_document: str
    valor: str
    discriminacao: str
    competencia: Optional[str] = None
    cnae: Optional[str] = None
    codigo_servico: Optional[str] = None
    aliquota: Optional[str] = None
    codigo_municipio: Optional[str] = "5300108"
    item_lista_servico: Optional[str] = None
    codigo_tributacao_municipio: Optional[str] = None


@dataclass
class CancelInvoiceCommand:
    """Command to cancel an issued invoice."""

    nfse_number: str
    motivo: str = "1"  # 1=Erro na Emissao, 2=Servico nao Prestado, 9=Outros


@dataclass
class QueryInvoiceCommand:
    """Command to query an invoice."""

    chave_acesso: Optional[str] = None
    dps_id: Optional[str] = None


@dataclass
class ListInvoicesCommand:
    """Command to list invoices in a period."""

    data_inicial: Optional[str] = None
    data_final: Optional[str] = None


@dataclass
class QueryParametersCommand:
    """Command to query municipal parameters."""

    codigo_municipio: str
    codigo_servico: Optional[str] = None


@dataclass
class RegisterClientCommand:
    """Command to register a client."""

    document: str
    razao_social: str = ""
    auto_lookup: bool = True
