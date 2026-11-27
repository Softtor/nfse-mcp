# CLAUDE.md

Guia para o Claude Code ao trabalhar neste projeto.

## Visão Geral

MCP Server em Python para emitir NFS-e (Nota Fiscal de Serviço Eletrônica) em Brasília/DF através do webservice ISS.net (padrão ABRASF 2.04). Permite emissão, consulta, cancelamento e gerenciamento de clientes via prompt do Claude Code ou CSV.

**Prestador:** Prestador Exemplo LTDA
- CNPJ: 11.222.333/0001-81
- Inscrição Municipal: 1234567
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

## Tools MCP Disponíveis (18)

| Tool | Descrição |
|------|-----------|
| `lookup_cnpj` | Consulta dados de empresa via BrasilAPI |
| `register_client` | Cadastra tomador (auto-preenche via CNPJ) |
| `list_clients` | Lista clientes cadastrados |
| `emit_nfse` | Emite NFS-e via ABRASF/ISS.net (para municípios com emissor próprio) |
| `emit_nfse_batch` | Emite lote via CSV (sequencial, uma por uma) |
| `get_nfse_link` | Retorna URLs de visualização/autenticidade |
| `cancel_nfse` | Cancela NFS-e emitida |
| `list_nfse` | Lista NFS-e por período com valores |
| `list_cancelled_nfse` | Lista NFS-e canceladas (log local `data/cancel_log.json`) |
| `query_cadastral_data` | Dados cadastrais do prestador no webservice |
| `emit_nfse_nacional` | Emite NFS-e via SEFIN Nacional (apenas para municípios com emissor nacional) |
| `emit_nfse_unificado` | Emite escolhendo o provider automaticamente (SEFIN ou ABRASF) via `NfseRouterService` |
| `consultar_nfse_nacional` | Consulta NFS-e pela chave de acesso (SEFIN Nacional) |
| `consultar_parametros_municipais` | Consulta convênio, alíquotas e regimes (SEFIN Nacional) |
| `verificar_habilitacao_municipio` | Verifica se o município usa emissor próprio ou nacional |
| `list_nfse_nacional` | Lista as NFS-e nacionais do log local (só as emitidas por esta ferramenta) |
| `baixar_nfse_nacional` | Grava o XML da NFS-e nacional (e o PDF se o ADN devolver) e dá o link da Consulta Pública |
| `cancelar_nfse_nacional` | Cancela NFS-e nacional `emitida` no log; sem `confirmar=True` só mostra a prévia |

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
Tipo: ICP-Brasil AC SOLUTI Multipla v5 (para o prestador).

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

# Prestador (exemplo)
NFSE_PROVIDER_CNPJ=11222333000181
NFSE_PROVIDER_IM=1234567
NFSE_PROVIDER_RAZAO_SOCIAL=PRESTADOR EXEMPLO LTDA
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

O Claude Code lê a configuração de MCP de `~/.claude.json` (escopo user/global) ou de um
`.mcp.json` na raiz do projeto (escopo project). **Não existe mais `~/.claude/mcp.json`.**

### Registro (recomendado: escopo user)

Assim o servidor fica disponível em qualquer sessão, não só dentro deste repositório:

```bash
claude mcp add nfse -s user -- uv --directory /caminho/absoluto/para/nfse-mcp run nfse-mcp
```

Verificar o registro:

```bash
claude mcp list
claude mcp get nfse
```

### Alternativa: escopo project (`.mcp.json` na raiz)

Só carrega quando o cwd da sessão é este repositório — útil para versionar a config:

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

### ⚠️ Armadilhas do registro

- **Tools MCP só carregam no início da sessão.** Depois de registrar, reinicie a sessão
  (ou use `/mcp` para reconectar) — caso contrário as tools `mcp__nfse__*` não aparecem.
- **Primeiro start é lento.** Não é necessário rodar `uv sync` antes: o `uv run` resolve as
  dependências sozinho na primeira invocação, mas isso pode levar o handshake inicial a
  estourar o timeout uma vez. Se falhar, rode `uv sync` manualmente e reinicie.
- **Use caminho absoluto** em `--directory`. O servidor é iniciado a partir do cwd da
  sessão, que raramente é o diretório do projeto.
- **O `.env` é lido do diretório do projeto**, não do cwd da sessão — por isso o
  `--directory` é obrigatório.

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
| L003 | Código de tributação não pertence ao contribuinte | Usar `CodigoTributacaoMunicipio` registrado para o prestador (ex: 107) |
| L016 | Data competência fora da vigência | Verificar período de vigência da atividade |

## SEFIN Nacional NFS-e (Nova Camada ACL)

A partir de maio/2026, o projeto suporta também a **SEFIN Nacional NFS-e** (padrão nacional) como segundo provider, além do ISS.net de Brasília.

### Arquitetura

```
src/nfse_mcp/
  ports/                     # Interfaces abstratas (domínio)
    service_invoice_provider.py
    municipal_parameter_provider.py
  abrasf/                    # Provider ISS.net/ABRASF 2.04 (SOAP)
    xml_builder.py
    soap_client.py
  sefin_nacional/            # Provider SEFIN Nacional (REST + mTLS)
    config.py
    client.py                # HTTP client mTLS
    provider.py              # Implementação das interfaces
    mapper.py                # Domain ↔ DPS XML ↔ JSON
    dps_xml_builder.py       # XML DPS v1.00
    evento_xml_builder.py    # XML de eventos
    xsd_validator.py         # Validação local com schemas
    errors.py                # Erros normalizados
```

### ⚠️ Diferença Crítica: Aderido ao Sistema vs Emissor Público Nacional

Um município pode estar **aderido ao Sistema Nacional NFS-e** (compartilhando dados no ADN) mas **não ter habilitado os emissores públicos nacionais** (Web, Mobile, API). Neste caso, o município mantém seu **emissor próprio** (ex: ISS.net, Betha, IPM) e o contribuinte deve continuar usando o webservice municipal.

**Brasília/DF (5300108) — desde a competência 11/2026 emite pelo Emissor Nacional.**
O ISS.net recusa RPS de optante do Simples com competência >= 01/11/2026 (erro L120). O prestador
(ME/EPP) emite pelo `emit_nfse_nacional`; o DF está em `EMISSOR_NACIONAL_SET` (`municipality_data.py`).
Competência anterior a 11/2026 ainda é ISS.net (`emit_nfse`).

**Armadilhas SEFIN Nacional (provadas em 04/11/2026):**
- Produção e produção restrita rodam leiautes diferentes: `LEIAUTE_POR_TPAMB` (`nacional/dps_xml_builder.py`) liga cada tpAmb ao XSD oficial em `schemas/nacional/oficial-*`. Produção restrita exige `finNFSe`; produção ainda o recusa. Quando a produção mudar, troque a entrada 1.
- A recusa vem com `Complemento` (diz o campo exato); o cliente junta na descrição.
- Assinatura: `Reference URI="#<Id do infDPS>"` (URI vazia é recusada) e c14n de cópia isolada do infDPS (o c14n do libxml2 num trecho interno põe `xmlns=""` e dá E0714). SHA-1 é aceito.
- Regras do DF/ME-EPP: sem `cTribMun` (o 104/107 do ISS.net dá E0314), sem `IM` (E0120), `pTotTribSN` = `NFSE_PROVIDER_ALIQUOTA_SIMPLES` em vez de `indTotTrib` (E0712), sem `tribFed`. `opSimpNac`/`regEspTrib` são traduzidos do padrão ABRASF em `sefin_nacional/mapper.py`.
- nDPS é reservado em `data/dps_counter.json` antes do envio; POST não repete sozinho. Resposta perdida (timeout, 5xx) vira entrada `pendente` no log e bloqueia nova nota do mesmo tomador até a consulta por DPS resolver.
- Teste sem valor fiscal: `SEFIN_ENVIRONMENT=production_restricted` no comando sobrepõe o `.env` (load_dotenv não sobrescreve).
- Consulta de parâmetros municipais usa o código com pontos (`01.04.01.000`).
- `cTribNac` é conferido antes de reservar o nDPS contra `nacional/lista_servico_nacional.json` (Anexo B v1.01, 22/01/2026); código fora dela a SEFIN recusa com E0310. Nova versão do Anexo B: regerar o JSON a partir da aba LISTA.SERV.NAC.

**Armadilhas do evento de cancelamento (provadas em produção restrita, 04/11/2026):**
- O corpo do POST `/nfse/{chave}/eventos` é `{"pedidoRegistroEventoXmlGZipB64": ...}`; com outro nome a SEFIN dá HTTP 500 genérico ("An error has occurred."). Swagger: `{base_url}/swagger/docs/v1` (com mTLS).
- `pedRegEvento` segue o XSD (`tiposEventos_v1.01.xsd`, igual nos dois leiautes), não o texto do manual: `infPedReg@Id` = `PRE` + chave + `101101`, assinatura com `Reference URI="#<Id>"`, `versao`/`verAplic` 1.00, tpAmb de `SefinNacionalConfig.tp_amb`.
- `GET /nfse/{chave}/eventos` dá 405. Use `GET /nfse/{chave}/eventos/101101/1`: 404 (JSON) = sem cancelamento; 200 traz `eventos[]` com `chaveAcesso`/`tipoEvento`.
- PDF: `GET {SEFIN}/danfse` dá 501; `GET {ADN}/danfse/{chave}` deu 503/404 (NT 008/2026). O `baixar_nfse_nacional` tenta uma vez e segue só com XML + link.

**Regra de ouro:**
- Se o município mantém emissor próprio → use **`emit_nfse`** (ABRASF/ISS.net via SOAP)
- Se o município habilitou emissores públicos nacionais → use **`emit_nfse_nacional`** (SEFIN Nacional REST API)
- Use **`verificar_habilitacao_municipio(codigo_ibge)`** para descobrir qual provider usar

### Principais Diferenças Técnicas (ABRASF vs SEFIN Nacional)

| Aspecto | ISS.net Brasília (emissor próprio) | SEFIN Nacional (emissor público) |
|---------|-----------------------------------|----------------------------------|
| Protocolo | SOAP | REST |
| Formato | XML puro | JSON envelope + XML DPS (GZip+Base64) |
| Assinatura | SHA-1 | SHA-256 |
| Emissão | `GerarNfse` | `POST /nfse` |
| Consulta | SOAP methods | `GET /nfse/{chaveAcesso}` |
| Cancelamento | SOAP `CancelarNfse` | `POST /nfse/{chaveAcesso}/eventos` |
| Parâmetros municipais | Não disponível | `GET /parametros_municipais/...` |

### Ambientes

- **Produção Restrita:** `https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional`
- **Produção:** `https://sefin.nfse.gov.br/SefinNacional`

### Autenticação

- mTLS com certificado digital ICP-Brasil (A1 ou A3, e-CNPJ preferencial).
- Sem token adicional. O CNPJ do certificado deve corresponder ao CNPJ do prestador.

### MCP Tools SEFIN Nacional

| Tool | Descrição |
|------|-----------|
| `emit_nfse_nacional` | Emite NFS-e via SEFIN Nacional (apenas municípios com emissor público) |
| `emit_nfse_unificado` | Emite NFS-e usando o provider correto automaticamente (SEFIN ou ABRASF) |
| `consultar_nfse_nacional` | Consulta NFS-e pela chave de acesso |
| `consultar_parametros_municipais` | Consulta convênio, alíquotas e regimes |
| `verificar_habilitacao_municipio` | Verifica se o município usa emissor próprio ou nacional, e sugere o provider correto |
| `list_nfse_nacional` | Lista NFS-e nacionais do log local (DPS, data, tomador, valor, status, chave) |
| `baixar_nfse_nacional` | XML em `data/xml/NFSe-<n>-<chave>.xml` + PDF do ADN quando houver + link da Consulta Pública |
| `cancelar_nfse_nacional` | Evento e101101; prévia por padrão, envio só com `confirmar=True` depois do ok do usuário |

### NfseRouterService (Fallback Inteligente)

O `NfseRouterService` orquestra a emissão automaticamente entre SEFIN Nacional e ABRASF/ISS.net:

```
Recebe requisição de emissão
    │
    ├──► Município conhecido como emissor próprio
    │    ├──► ABRASF suporta? → Emite via ABRASF ✅
    │    └──► ABRASF NÃO suporta → "Integração indisponível" ❌
    │
    ├──► Município conhecido como emissor nacional
    │    └──► Emite via SEFIN Nacional ✅
    │
    └──► Município desconhecido
         ├──► Tenta SEFIN Nacional
         │    ├──► Sucesso → Emite ✅
         │    ├──► E0039 → Fallback para ABRASF (se suportado) ✅
         │    ├──► Não conveniado → Fallback para ABRASF (se suportado) ✅
         │    └──► Outro erro → Fallback para ABRASF (se suportado) ✅
         │
         └──► SEFIN falhou e ABRASF não suporta → Erro informativo ❌
```

**Uso recomendado para API unificada:**
```python
from nfse_mcp.application.services.router_service import NfseRouterService
result = router.issue_invoice(command)
```

**Municípios suportados por ABRASF atualmente:** `{ "5300108" }` (Brasília/DF). Expandir conforme novas integrações forem implementadas.

### Configuração (.env)

```env
SEFIN_ENVIRONMENT=production_restricted
SEFIN_CERTIFICATE_PATH=/caminho/certificado.p12  # ou reutilizar NFSE_CERTIFICATE_PATH
SEFIN_CERTIFICATE_PASSWORD=senha
SEFIN_DEBUG=false
SEFIN_SKIP_XSD_VALIDATION=false
```

### Testes

```bash
uv run pytest tests/ -v
```

### Documentação

- `docs/research/sefin-nacional-map.md` — Mapeamento técnico completo da API
- `docs/research/sefin-nacional-mvp-plan.md` — Plano do MVP, escopo, DTOs, testes

---

## Referências

- **Manual de integração:** Manual ABRASF 2.04 + guia ISS Brasília (portal `df.issnetonline.com.br`)
- **Schemas XSD:** pasta `schemas/` deste repositório + documentação ABRASF em `abrasf.org.br/nfse.xsd`
- **Planilha CNAE x LS x Atividade:** disponível no Manual de Orientação ao Contribuinte v2.04 do portal ISS Brasília
- **SEFIN Nacional:** https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual
