from dataclasses import dataclass, field
from typing import Optional
from datetime import date


@dataclass
class Client:
    id: str  # UUID
    document: str  # CNPJ or CPF (numbers only)
    document_type: str  # "cnpj" or "cpf"
    razao_social: str
    nome_fantasia: Optional[str] = None
    inscricao_municipal: Optional[str] = None
    endereco: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    codigo_municipio: Optional[str] = None  # IBGE code
    uf: Optional[str] = None
    cep: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[str] = None


@dataclass
class RpsData:
    numero: int
    serie: str
    tipo: int = 1  # 1 = RPS
    data_emissao: str = ""  # YYYY-MM-DD
    status: int = 1  # 1 = Normal


@dataclass
class ServiceData:
    valor_servicos: str  # decimal string e.g. "1000.00"
    discriminacao: str
    cnae: str = ""
    item_lista_servico: str = ""
    codigo_tributacao_municipio: str = ""
    aliquota: str = ""
    municipio_prestacao: str = "5300108"  # Brasilia
    iss_retido: int = 2  # 2 = Nao
    exigibilidade_iss: int = 1  # 1 = Exigivel
    municipio_incidencia: str = "5300108"


@dataclass
class NfseResult:
    success: bool
    numero_nfse: Optional[str] = None
    numero_rps: Optional[int] = None
    url_visualizacao: Optional[str] = None
    url_autenticidade: Optional[str] = None
    codigo_verificacao: Optional[str] = None
    data_emissao: Optional[str] = None
    mensagem: Optional[str] = None
    errors: list[str] = field(default_factory=list)
