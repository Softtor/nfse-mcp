# CLAUDE.md

Guia para o Claude Code ao trabalhar neste projeto.

## Visão Geral

MCP Server em Python para emitir NFS-e (Nota Fiscal de Serviço Eletrônica) em Brasília/DF através do webservice ISS.net (padrão ABRASF 2.04). Permite emissão, consulta, cancelamento e gerenciamento de clientes via prompt do Claude Code ou CSV.

**Prestador:** Softtor Soluções Transformadoras LTDA
- CNPJ: 33.779.923/0001-42
- Inscrição Municipal: 0791927900180
- Regime: Simples Nacional ME/EPP (regime 6)
- Serviço: Suporte em TI (CNAE 6209-1/00, Item LC116: 1.07)

## Arquitetura

```
nfse-mcp/
├── .env                    # Configuração (cert path, dados prestador, defaults)
├── pyproject.toml          # Dependências Python
├── src/nfse_mcp/
│   ├── server.py           # MCP server + 9 tools (entrypoint)
│   ├── config.py           # Carrega .env → Config dataclass
│   ├── models.py           # Dataclasses: Client, RpsData, ServiceData, NfseResult
│   ├── certificate.py      # Lê PFX/PKCS12 → private_key + x509 cert
│   ├── xml_signer.py       # XML-DSig padrão (SHA-1) com lxml + cryptography
│   ├── xml_builder.py      # Monta XMLs ABRASF 2.04 (GerarNfse, Cancelar, etc.)
│   ├── soap_client.py      # Cliente SOAP raw (sem zeep/suds)
│   ├── cnpj_lookup.py      # BrasilAPI para auto-preencher clientes
│   └── client_store.py     # CRUD de clientes em data/clients.json
├── data/
│   ├── clients.json        # Tomadores cadastrados
│   └── nfse_log.json       # Log local de emissões
└── schemas/
    └── schema_v204.xsd     # XSD ABRASF 2.04 (referência)
```

## Tools MCP Disponíveis (9)

| Tool | Descrição |
|------|-----------|
| `lookup_cnpj` | Consulta dados de empresa via BrasilAPI |
| `register_client` | Cadastra tomador (auto-preenche via CNPJ) |
| `list_clients` | Lista clientes cadastrados |
| `emit_nfse` | Emite NFS-e individual |
| `emit_nfse_batch` | Emite lote via CSV (sequencial, uma por uma) |
| `get_nfse_link` | Retorna URLs de visualização/autenticidade |
| `cancel_nfse` | Cancela NFS-e emitida |
| `list_nfse` | Lista NFS-e por período com valores |
| `query_cadastral_data` | Dados cadastrais do prestador no webservice |

## Webservice ISS.net Brasília

**URL produção:** `https://df.issnetonline.com.br/webservicenfse204/nfse.asmx`
**Namespace SOAP:** `http://nfse.abrasf.org.br`
**Namespace dados:** `http://www.abrasf.org.br/nfse.xsd`

### Métodos que FUNCIONAM
- `GerarNfse` — emissão individual (método principal)
- `CancelarNfse` — cancelamento
- `ConsultarUrlNfse` — links das notas
- `ConsultarRpsDisponivel` — próximos números de RPS
- `ConsultarDadosCadastrais` — dados do prestador
- `ConsultarNfseServicoPrestado` — listagem com valores (período máx ~1 mês)

### Métodos com PROBLEMAS
- `RecepcionarLoteRpsSincrono` — aceita XML mas valida assinatura de RPS individual de forma não-documentada. O `emit_nfse_batch` **não usa** este método — emite uma nota por vez via `GerarNfse`.

## ⚠️ Armadilhas Importantes (Aprendido na Raça)

### 1. Wrapper `<Pedido>` nos XMLs de consulta
Os métodos `ConsultarDadosCadastrais`, `ConsultarNfseServicoPrestado`, `ConsultarNfsePorFaixa` **exigem** que o conteúdo esteja dentro de `<Pedido>`:
```xml
<ConsultarDadosCadastraisEnvio xmlns="...">
  <Pedido>  <!-- OBRIGATÓRIO -->
    <Prestador>...</Prestador>
  </Pedido>
</ConsultarDadosCadastraisEnvio>
```
Sem o `<Pedido>`, o servidor retorna HTTP 500 genérico ("Error"). Esta é a diferença principal do padrão ABRASF puro.

### 2. Cabeçalho: versão 1.00 (não 2.04)
```xml
<cabecalho versao="1.00" xmlns="http://www.abrasf.org.br/nfse.xsd">
  <versaoDados>2.04</versaoDados>
</cabecalho>
```
Usar `versao="2.04"` causa erro E183.

### 3. Assinatura dentro de `<Rps>` (para GerarNfse)
O schema exige:
```xml
<GerarNfseEnvio>
  <Rps>
    <InfDeclaracaoPrestacaoServico>...</InfDeclaracaoPrestacaoServico>
    <Signature>...</Signature>  <!-- sibling, não dentro de InfDeclaracao -->
  </Rps>
</GerarNfseEnvio>
```
Fluxo: sign `InfDeclaracaoPrestacaoServico` (enveloped) → extrai `<Signature>` → coloca como irmã dentro de `<Rps>`.

### 4. ItemListaServico formato `NN.NN`
Deve ser `"01.07"` com zero à esquerda. `"1.07"` é rejeitado pelo XSD (enumeration).

### 5. CodigoTributacaoMunicipio é OBRIGATÓRIO
O webservice de Brasília exige este campo (mesmo sendo opcional no XSD). Para suporte em TI (CNAE 6209-1/00, Item 01.07, alíquota 2%), use `107`. Códigos disponíveis na planilha "Relacionamento CNAE x LS x Atividade" do Manual de Orientação ao Contribuinte v2.04 (ISS Brasília).

### 6. Endereço do tomador com campos obrigatórios
O XSD requer `Endereco` (logradouro), `Numero`, `Bairro`, `CodigoMunicipio`, `Uf`, `Cep`. Se faltar qualquer um, o webservice retorna erros E056/E059/E113/E114/E115/E116/E199. O `_ensure_client_address()` preenche defaults ("Rua Nao Informada", "SN") quando dados estão incompletos.

### 7. SOAP com entity escaping (não CDATA)
```python
from xml.sax.saxutils import escape
# CERTO:
body = f"<nfseDadosMsg>{escape(xml)}</nfseDadosMsg>"
# ERRADO:
body = f"<nfseDadosMsg><![CDATA[{xml}]]></nfseDadosMsg>"  # servidor rejeita
```

### 8. Zeep NÃO é confiável para este webservice
O `zeep` infere namespace errado do WSDL. Usar SOAP raw via `requests` com envelope construído manualmente. O cliente SOAP (`soap_client.py`) usa apenas `requests`.

### 9. Certificado A1 PFX
Configurar caminho no `.env` via `NFSE_CERTIFICATE_PATH` (certificado ICP-Brasil, renovado anualmente).
Senha: configurar via `NFSE_CERTIFICATE_PASSWORD` no `.env` local (nunca commitar).
Tipo: ICP-Brasil AC SOLUTI Multipla v5 (para o prestador Softtor).

### 10. RPS Auto-numbering via ConsultarRpsDisponivel
Nunca incrementar RPS localmente. Sempre buscar o próximo disponível no webservice:
```python
rps_num = _get_next_rps_number(cfg, cert, signer)  # consulta webservice
```

### 11. Série RPS = 3 (produção)
Definida no `.env`: `NFSE_RPS_SERIE=3`. Homologação usa série 8.

## Assinatura XML

**Não usar `signxml`** — bloqueia SHA-1 por padrão (webservice exige SHA-1).
Implementação manual em `xml_signer.py`:
1. Canonicalize XML (C14N exclusive OFF)
2. `DigestValue = base64(sha1(c14n_xml))`
3. Build `<SignedInfo>` com Reference URI
4. Canonicalize `SignedInfo`
5. `SignatureValue = base64(rsa_pkcs1v15_sha1(c14n_signedinfo, private_key))`
6. Append `<Signature>` ao root do documento

## Fluxo de Emissão de Nota

1. **Localizar/cadastrar cliente**
   - Busca em `clients.json` por CNPJ
   - Se não existe: chama `lookup_cnpj` (BrasilAPI) e salva
2. **Preencher endereço obrigatório**
   - `_ensure_client_address()` completa campos faltantes com defaults
3. **Obter próximo RPS**
   - `_get_next_rps_number()` via `ConsultarRpsDisponivel`
4. **Montar XML + assinar**
   - `build_inf_declaracao_xml()` → `sign_xml()` → mover signature para dentro de `<Rps>` → wrap em `<GerarNfseEnvio>`
5. **Enviar via SOAP**
   - `SoapClient.gerar_nfse(header, signed_xml)`
6. **Processar resposta**
   - Extrair `<Numero>`, `<CodigoVerificacao>`, `<DataEmissao>`
7. **Obter link**
   - `ConsultarUrlNfse` com o número da nota
8. **Registrar no log**
   - Append em `data/nfse_log.json`

## Configuração (.env)

```env
NFSE_ENVIRONMENT=production
NFSE_CERTIFICATE_PATH=/caminho/local/para/certificado.p12
NFSE_CERTIFICATE_PASSWORD=sua-senha-do-certificado

# Prestador (Softtor)
NFSE_PROVIDER_CNPJ=33779923000142
NFSE_PROVIDER_IM=0791927900180
NFSE_PROVIDER_RAZAO_SOCIAL=SOFTTOR SOLUCOES TRANSFORMADORAS LTDA
NFSE_PROVIDER_SIMPLES_NACIONAL=1       # 1=Sim, 2=Não
NFSE_PROVIDER_REGIME_TRIBUTACAO=6      # 6=ME/EPP
NFSE_PROVIDER_INCENTIVO_FISCAL=2       # 2=Não

# Defaults do serviço
NFSE_DEFAULT_CNAE=6209100
NFSE_DEFAULT_ITEM_LISTA_SERVICO=1.07
NFSE_DEFAULT_CODIGO_TRIBUTACAO_MUNICIPIO=107    # CRÍTICO - obrigatório!
NFSE_DEFAULT_ALIQUOTA=2.00
NFSE_DEFAULT_MUNICIPIO_IBGE=5300108    # Brasília
NFSE_DEFAULT_ISS_RETIDO=2              # 2=Não retido
NFSE_DEFAULT_EXIGIBILIDADE_ISS=1       # 1=Exigível

NFSE_RPS_SERIE=3
```

## Comandos de Desenvolvimento

```bash
# Instalar dependências
uv sync

# Rodar server (stdio para testar protocolo MCP)
uv run nfse-mcp

# Testar importação
uv run python -c "from nfse_mcp.server import main; print('OK')"

# Debug de uma chamada SOAP diretamente
uv run python -c "
from nfse_mcp.config import load_config
from nfse_mcp.certificate import Certificate
from nfse_mcp.xml_signer import XmlSigner
# ... construir XML, assinar, enviar ...
"
```

## Dependências

```toml
mcp[cli]>=1.0.0       # MCP server SDK
lxml>=5.0.0           # Manipulação XML
cryptography>=42.0.0  # PKCS12, RSA, SHA-1
requests>=2.31.0      # HTTP (SOAP + BrasilAPI)
python-dotenv>=1.0.0  # .env
```

**Importante:** `zeep` e `signxml` são incompatíveis com este webservice (zeep infere namespace errado do WSDL; signxml bloqueia SHA-1 por padrão). Não adicionar.

## Integração com Claude Code

Registro em `~/.claude/mcp.json`:
```json
{
  "mcpServers": {
    "nfse": {
      "command": "uv",
      "args": ["--directory", "/caminho/absoluto/para/nfse-mcp", "run", "nfse-mcp"],
      "env": {}
    }
  }
}
```

## Códigos de Erro Comuns do Webservice

| Código | Significado | Solução |
|--------|-------------|---------|
| E010 | RPS já informado | Usar número disponível via `ConsultarRpsDisponivel` |
| E056/E059/E113/E114/E115/E199 | Endereço tomador incompleto | Completar campos do endereço |
| E116 | UF do tomador incorreta | Usar sigla 2 letras válida |
| E133 | Data final > hoje | Ajustar `data_final` |
| E135 | Período consultado > permitido | Dividir consulta em períodos menores |
| E160 | XML fora do schema | Verificar estrutura contra XSD |
| E174 | RPS não assinado | Problema na assinatura — usar GerarNfse ao invés de lote |
| E183 | Cabeçalho fora do padrão | Usar `versao="1.00"` no cabecalho |
| E190 | Certificado digital inválido | Verificar PFX e senha |
| E215 | Item incompatível com código tributação | Usar combinação correta da planilha CNAE x LS |
| L003 | Código de tributação não pertence ao contribuinte | Usar `CodigoTributacaoMunicipio` registrado para a Softtor (ex: 107) |
| L016 | Data competência fora da vigência | Verificar período de vigência da atividade |

## Referências

- **Manual de integração:** Manual ABRASF 2.04 + guia ISS Brasília (portal `df.issnetonline.com.br`)
- **Schemas XSD:** pasta `schemas/` deste repositório + documentação ABRASF em `abrasf.org.br/nfse.xsd`
- **Planilha CNAE x LS x Atividade:** disponível no Manual de Orientação ao Contribuinte v2.04 do portal ISS Brasília
