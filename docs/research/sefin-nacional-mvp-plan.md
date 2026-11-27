# SEFIN Nacional NFS-e — Plano do MVP

> Este documento detalha o escopo, estrutura, interfaces, estratégias e plano de testes para a primeira integração da camada ACL SEFIN Nacional no `nfse-mcp`.

---

## 1. Escopo do MVP

### 1.1. Dentro do Escopo

1. **Camada ACL isolada** em `src/nfse_mcp/sefin_nacional/` com interfaces/ports (`ServiceInvoiceProvider`, `MunicipalParameterProvider`).
2. **Client HTTP mTLS** (`SefinNacionalClient`) usando `requests` + certificado A1 local.
3. **Builder de DPS XML v1.00** com campos mínimos obrigatórios para teste.
4. **Validação XSD local** antes do envio (carregar schemas em `schemas/sefin_nacional/`).
5. **Assinatura XML-DSig** (adaptar `XmlSigner` para suportar SHA-256).
6. **Compressão GZip + Base64** do XML para envio e decodificação da resposta.
7. **Mapper** entre dados internos (`IssueServiceInvoiceInput`) e XML DPS / resposta JSON.
8. **Provider implementando as interfaces** (`SefinNacionalProvider`).
9. **Erros normalizados** (`SefinNacionalError`, `ValidationError`, etc.) que não vazam detalhes da API fiscal para o domínio.
10. **MCP Tools** para emissão, consulta por chave e por DPS, e consulta de parâmetros municipais.
11. **Mock/Fake provider** para testes unitários sem dependência da API real.
12. **Configuração por ambiente** (Produção Restrita / Produção) via variáveis de ambiente.
13. **Documentação técnica** completa (`sefin-nacional-map.md` e `sefin-nacional-mvp-plan.md`).

### 1.2. Fora do Escopo

- Suporte a DPS v1.01 / campos IBSCBS (Reforma Tributária).
- Emissão de NFS-e de decisão administrativa/judicial (bypass).
- Substituição de NFS-e (evento complexo).
- Distribuição de DF-e por NSU (APIs ADN).
- Cache persistente de parâmetros municipais.
- Webhooks.
- Emissão em lote (a API SEFIN é síncrona e unitária).
- Suporte a múltiplos provedores municipais não-nacionais.
- Painel administrativo ou UI.
- Emissão em produção real (esta etapa é apenas validação técnica em Produção Restrita).

---

## 2. Estrutura de Pastas

```
src/nfse_mcp/
  __init__.py
  server.py                    # MCP server — adicionar novas tools
  config.py                    # Config loader (.env)
  models.py                    # Dataclasses de domínio
  certificate.py               # PFX loader (reuso)
  xml_signer.py                # XML-DSig com suporte a SHA-1 e SHA-256
  cnpj_lookup.py               # BrasilAPI (reuso)
  client_store.py              # CRUD de clientes (reuso)
  # --- ABRASF 2.04 (movido) ---
  abrasf/
    __init__.py
    xml_builder.py             # XMLs ABRASF 2.04
    soap_client.py             # Cliente SOAP ISS.net
  # --- SEFIN Nacional (novo) ---
  sefin_nacional/
    __init__.py
    config.py                  # Base URLs por ambiente
    client.py                  # HTTP client mTLS
    provider.py                # Implementação das interfaces
    mapper.py                  # Mapeamento input ↔ DPS ↔ resposta
    dps_xml_builder.py         # Builder XML DPS v1.00
    evento_xml_builder.py      # Builder XML de eventos (cancelamento)
    xsd_validator.py           # Validação contra schemas XSD
    errors.py                  # Exceções normalizadas
    types.py                   # TypedDicts / dataclasses internos
  # --- Ports/Interfaces (novo) ---
  ports/
    __init__.py
    service_invoice_provider.py
    municipal_parameter_provider.py
schemas/
  schema_v204.xsd              # XSD ABRASF 2.04 (existente)
  sefin_nacional/              # XSDs da SEFIN Nacional (a baixar do portal)
docs/research/
  sefin-nacional-map.md        # Resumo técnico completo
  sefin-nacional-mvp-plan.md   # Este documento
tests/
  test_sefin_nacional_provider.py
  test_sefin_nacional_client.py
  test_dps_xml_builder.py
  fakes.py                     # Mock/Fake providers
```

---

## 3. Interfaces / Ports

### 3.1. ServiceInvoiceProvider

```python
class ServiceInvoiceProvider(ABC):
    @abstractmethod
    def issue(self, input: IssueServiceInvoiceInput) -> IssueServiceInvoiceResult: ...

    @abstractmethod
    def query_by_access_key(self, access_key: str) -> QueryServiceInvoiceResult: ...

    @abstractmethod
    def query_by_dps_id(self, dps_id: str) -> QueryServiceInvoiceResult: ...

    @abstractmethod
    def cancel(self, input: CancelServiceInvoiceInput) -> CancelServiceInvoiceResult: ...
```

### 3.2. MunicipalParameterProvider

```python
class MunicipalParameterProvider(ABC):
    @abstractmethod
    def get_agreement_by_municipality(self, municipality_code: str) -> MunicipalAgreementResult: ...

    @abstractmethod
    def get_service_parameters(self, municipality_code: str, service_code: str) -> ServiceTaxParameterResult: ...

    @abstractmethod
    def get_contributor_retentions(self, municipality_code: str, document: str) -> ContributorRetentionResult: ...

    @abstractmethod
    def get_contributor_benefits(self, municipality_code: str, document: str) -> ContributorBenefitResult: ...
```

---

## 4. DTOs Internos (Contratos)

### 4.1. Input para Emissão

```python
@dataclass
class IssueServiceInvoiceInput:
    # Dados do prestador (obrigatórios)
    prestador_cnpj: str
    prestador_razao_social: str
    prestador_endereco_logradouro: str
    prestador_endereco_numero: str
    prestador_endereco_bairro: str
    prestador_endereco_codigo_municipio: str
    prestador_endereco_uf: str
    prestador_endereco_cep: str
    prestador_inscricao_municipal: Optional[str] = None

    # Dados do tomador (obrigatórios)
    tomador_document: str              # CPF ou CNPJ (somente números)
    tomador_razao_social: str
    tomador_endereco_logradouro: str
    tomador_endereco_numero: str
    tomador_endereco_bairro: str
    tomador_endereco_codigo_municipio: str
    tomador_endereco_uf: str
    tomador_endereco_cep: str
    tomador_tipo_documento: str = "cnpj"  # "cpf" ou "cnpj"

    # Dados do serviço (obrigatórios)
    servico_codigo: str                # Código da lista de serviços nacional
    servico_discriminacao: str
    servico_valor: str                 # Decimal string (ex: "1000.00")
    competencia: str                   # YYYY-MM-DD

    # Dados tributários (obrigatórios — exigem confirmação humana)
    optante_simples_nacional: int = 1  # 1=Não, 2=MEI, 3=ME/EPP
    regime_especial_tributacao: int = 0  # 0=Nenhum
    incentivo_fiscal: int = 2          # 1=Sim, 2=Não
    aliquota: Optional[str] = None
    iss_retido: int = 2                # 2=Não

    # Dados da DPS
    serie_dps: str = "1"
    numero_dps: Optional[str] = None
    tipo_ambiente: int = 2             # 2=Produção Restrita, 1=Produção
    versao: str = "1.00"
```

### 4.2. Output para Emissão

```python
@dataclass
class IssueServiceInvoiceResult:
    success: bool
    chave_acesso: Optional[str] = None       # 50 dígitos
    id_dps: Optional[str] = None
    numero_nfse: Optional[str] = None
    data_emissao: Optional[str] = None
    xml_nfse: Optional[str] = None           # XML decodificado (gzip+base64)
    data_hora_processamento: Optional[str] = None
    errors: list[dict] = field(default_factory=list)
```

### 4.3. Input para Cancelamento

```python
@dataclass
class CancelServiceInvoiceInput:
    chave_acesso: str
    motivo_codigo: str       # "1"=Erro na emissão, "2"=Serviço não prestado
    motivo_descricao: str
    cnpj_autor: str
    data_hora_evento: Optional[str] = None   # ISO 8601; default = agora
```

### 4.4. Output para Cancelamento

```python
@dataclass
class CancelServiceInvoiceResult:
    success: bool
    xml_evento: Optional[str] = None
    errors: list[dict] = field(default_factory=list)
```

### 4.5. Output para Consulta

```python
@dataclass
class QueryServiceInvoiceResult:
    success: bool
    chave_acesso: Optional[str] = None
    xml_nfse: Optional[str] = None
    status: Optional[str] = None
    errors: list[dict] = field(default_factory=list)
```

---

## 5. Estratégia de Validação XML/XSD

1. **Schemas XSD** são carregados de `schemas/sefin_nacional/` no momento da inicialização do `XsdValidator`.
2. Antes de assinar, o XML DPS é validado contra `DPS_v1.00.xsd`.
3. Antes de enviar um evento, o XML do evento é validado contra `pedRegEvento_v1.00.xsd`.
4. Em caso de erro de validação, uma `ValidationError` é levantada com a lista de mensagens de erro do parser `lxml`.
5. Em Produção Restrita, a validação pode ser desabilitada via flag `SEFIN_SKIP_XSD_VALIDATION=true` para testes exploratórios.

---

## 6. Estratégia de Certificado

1. **Reaproveitar** a classe `Certificate` existente (`certificate.py`) que lê PFX/PKCS12 e extrai `private_key` + `x509_certificate`.
2. O `SefinNacionalClient` converte o certificado e a chave para arquivos temporários PEM (igual ao `SoapClient` atual) e passa para o `requests` via parâmetro `cert=(cert_path, key_path)`.
3. As variáveis de ambiente podem ser reutilizadas do config atual (`NFSE_CERTIFICATE_PATH`, `NFSE_CERTIFICATE_PASSWORD`) ou específicas da SEFIN (`SEFIN_CERTIFICATE_PATH`, `SEFIN_CERTIFICATE_PASSWORD`).
4. O certificado é carregado uma única vez e mantido em memória (lazy singleton no `server.py`).
5. **Nunca logar** a senha do certificado. **Nunca versionar** arquivos `.pfx`/`.p12`.

---

## 7. Estratégia de Logs / Auditoria

1. **Log de requisição:** método HTTP, endpoint, status code, duração (ms).
2. **Log de erro:** código do erro fiscal + descrição (sem expor XML completo).
3. **Log de sucesso:** chave de acesso gerada, idDPS, data/hora de processamento.
4. **Nunca logar** em produção:
   - XML completo da DPS/NFS-e
   - CPF/CNPJ completos (mascarar: `337.***.***/0001-42`)
   - Valores monetários (mascarar: `R$ ****.**`)
   - Chaves de acesso completas (mascarar: `33************...`)
5. Em modo debug (`SEFIN_DEBUG=true`), permitir logar XML completo para diagnóstico.
6. **Histórico local:** armazenar em `data/sefin_nacional_log.json` com estrutura similar ao `nfse_log.json` existente.

---

## 8. Plano de Testes

### 8.1. Cenários de Sucesso

| # | Cenário | Como testar |
|---|---------|-------------|
| 1 | Emissão bem-sucedida | Mock `SefinNacionalClient` retornando HTTP 201 com `nfseXmlGZipB64`. Verificar `IssueServiceInvoiceResult.success=True` e `chaveAcesso` presente. |
| 2 | Consulta por chave de acesso | Mock retornando JSON com `nfseXmlGZipB64`. Verificar decodificação correta. |
| 3 | Consulta por idDPS | Mock retornando chave de acesso. Verificar mapeamento. |
| 4 | Consulta de parâmetros municipais | Mock retornando JSON de convênio. Verificar `conveniado=True`. |

### 8.2. Cenários de Erro

| # | Cenário | Como testar |
|---|---------|-------------|
| 5 | Rejeição fiscal (dados inválidos) | Mock retornando HTTP 422 com lista de `erros`. Verificar `success=False` e erros normalizados. |
| 6 | Certificado inválido / mTLS falha | Simular `requests.exceptions.SSLError`. Verificar `CertificateError` normalizada. |
| 7 | Município não conveniado | Mock `/convenio` retornando `conveniado=False`. Verificar `MunicipalityNotSupportedError`. |
| 8 | XML inválido (falha de XSD) | Criar XML DPS com campo obrigatório faltante. Verificar `ValidationError` antes do envio. |
| 9 | Duplicidade de DPS | Mock retornando erro específico de DPS já informada. Verificar `success=False` e mensagem clara. |
| 10 | Timeout / indisponibilidade | Simular `requests.exceptions.Timeout`. Verificar retry (3 tentativas com backoff) e erro final normalizado. |

### 8.3. Testes de Integração (requer certificado real)

| # | Cenário | Ambiente |
|---|---------|----------|
| 11 | Emissão de DPS de teste em Produção Restrita | Produção Restrita |
| 12 | Consulta da NFS-e gerada no teste #11 | Produção Restrita |
| 13 | Consulta de parâmetros do município de Brasília | Produção Restrita |

---

## 9. Variáveis de Ambiente

```env
# Escolha do provider padrão (abrasf | sefin_nacional)
DEFAULT_PROVIDER=sefin_nacional

# Ambiente da SEFIN (production | production_restricted)
SEFIN_ENVIRONMENT=production_restricted

# Certificado (pode reutilizar NFSE_CERTIFICATE_PATH ou usar específico)
SEFIN_CERTIFICATE_PATH=/caminho/para/certificado.p12
SEFIN_CERTIFICATE_PASSWORD=senha-do-certificado

# Debug
SEFIN_DEBUG=false
SEFIN_SKIP_XSD_VALIDATION=false

# Timeouts
SEFIN_TIMEOUT=60
SEFIN_MAX_RETRIES=3
```

---

## 10. Critérios de Aceite do MVP

1. [ ] É possível emitir uma DPS de teste em Produção Restrita (ou ao menos construir o XML, validar XSD, e simular o envio com mock).
2. [ ] O domínio não conhece detalhes da SEFIN Nacional (só trabalha com `IssueServiceInvoiceInput`/`Result`).
3. [ ] A ACL retorna erros normalizados e legíveis.
4. [ ] A documentação técnica cobre todos os endpoints, autenticação, payloads e riscos.
5. [ ] O mock provider cobre os cenários de sucesso e erro principais.
6. [ ] O código ABRASF existente continua funcionando sem regressão.
