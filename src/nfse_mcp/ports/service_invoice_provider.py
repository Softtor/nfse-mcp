"""Port interface for service invoice providers (SEFIN Nacional, ABRASF, etc.).

The domain layer depends on these abstractions, not on concrete providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IssueServiceInvoiceInput:
    """Minimal data required to issue a service invoice.

    Fields that the AI may suggest but MUST require human confirmation:
      - optante_simples_nacional
      - regime_especial_tributacao
      - incentivo_fiscal
      - aliquota
      - iss_retido
      - servico_codigo
    """

    # Prestador (issuer) — all required first
    prestador_cnpj: str
    prestador_razao_social: str
    prestador_endereco_logradouro: str
    prestador_endereco_numero: str
    prestador_endereco_bairro: str
    prestador_endereco_codigo_municipio: str  # IBGE
    prestador_endereco_uf: str
    prestador_endereco_cep: str

    # Tomador (service taker) — all required
    tomador_document: str  # CPF or CNPJ (numbers only)
    tomador_razao_social: str
    tomador_endereco_logradouro: str
    tomador_endereco_numero: str
    tomador_endereco_bairro: str
    tomador_endereco_codigo_municipio: str
    tomador_endereco_uf: str
    tomador_endereco_cep: str

    # Serviço — required
    servico_codigo: str  # National service list code
    servico_discriminacao: str
    servico_valor: str  # Decimal string
    competencia: str  # YYYY-MM-DD

    # Optional / with defaults
    prestador_inscricao_municipal: Optional[str] = None
    codigo_tributacao_municipio: str = ""  # cTribMun (ex.: 104 em Brasília)
    tomador_tipo_documento: str = "cnpj"  # "cpf" | "cnpj"
    optante_simples_nacional: int = 1  # 1=Não, 2=MEI, 3=ME/EPP
    regime_especial_tributacao: int = 0  # 0=Nenhum
    incentivo_fiscal: int = 2  # 1=Sim, 2=Não
    aliquota: Optional[str] = None
    aliquota_simples: Optional[str] = None  # pTotTribSN (% tributos do Simples), obrigatório para ME/EPP
    iss_retido: int = 2  # 2=Não
    serie_dps: str = "1"
    numero_dps: Optional[str] = None
    tipo_ambiente: int = 2  # 1=Produção, 2=Produção Restrita
    versao: str = "1.00"


@dataclass
class IssueServiceInvoiceResult:
    success: bool
    chave_acesso: Optional[str] = None  # 50 digits
    id_dps: Optional[str] = None
    numero_nfse: Optional[str] = None
    data_emissao: Optional[str] = None
    xml_nfse: Optional[str] = None  # decoded XML
    data_hora_processamento: Optional[str] = None
    errors: list[dict] = field(default_factory=list)


@dataclass
class CancelServiceInvoiceInput:
    chave_acesso: str
    motivo_codigo: str  # "1"=Erro na emissão, "2"=Serviço não prestado
    motivo_descricao: str
    cnpj_autor: str
    data_hora_evento: Optional[str] = None
    tipo_ambiente: int = 2  # 1=Produção, 2=Produção Restrita


@dataclass
class CancelServiceInvoiceResult:
    success: bool
    xml_evento: Optional[str] = None
    errors: list[dict] = field(default_factory=list)


@dataclass
class QueryServiceInvoiceResult:
    success: bool
    chave_acesso: Optional[str] = None
    xml_nfse: Optional[str] = None
    status: Optional[str] = None
    errors: list[dict] = field(default_factory=list)


class ServiceInvoiceProvider(ABC):
    """Abstract provider for issuing, querying and cancelling service invoices."""

    @abstractmethod
    def issue(self, input: IssueServiceInvoiceInput) -> IssueServiceInvoiceResult:
        """Issue a new service invoice."""
        ...

    @abstractmethod
    def query_by_access_key(self, access_key: str) -> QueryServiceInvoiceResult:
        """Query an invoice by its access key (50 digits)."""
        ...

    @abstractmethod
    def query_by_dps_id(self, dps_id: str) -> QueryServiceInvoiceResult:
        """Query an invoice by its DPS identifier (42 digits)."""
        ...

    @abstractmethod
    def cancel(self, input: CancelServiceInvoiceInput) -> CancelServiceInvoiceResult:
        """Cancel an issued invoice."""
        ...

    @abstractmethod
    def cancelamento_registrado(self, access_key: str) -> bool:
        """True se o governo já registrou o evento de cancelamento desta chave."""
        ...

    @abstractmethod
    def danfse_pdf(self, access_key: str) -> Optional[bytes]:
        """PDF oficial (DANFSe) da nota, ou None se o governo não o devolver."""
        ...
