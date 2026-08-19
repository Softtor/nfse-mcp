# nfse-mcp

MCP Server Python para emissão de NFS-e (Nota Fiscal de Serviço Eletrônica) em **Brasília/DF**. O caminho de **produção** é o webservice ISS.net no padrão **ABRASF 2.04**. Existe um SKU separado, **homolog-only**, para o **Padrão Nacional** do DF — ele não substitui o ABRASF 2.04 e não emite em produção.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/protocol-MCP-purple.svg)](https://modelcontextprotocol.io)

## O que é

Permite que um LLM (via Model Context Protocol) emita, consulte, cancele e gerencie notas fiscais de serviço diretamente no webservice da prefeitura de Brasília. Expõe **9 tools MCP** para fluxo completo de faturamento — incluindo cadastro automático de tomadores via BrasilAPI, emissão individual, emissão em lote via CSV e consulta de URLs de autenticidade.

Desenvolvido originalmente para o uso interno da **Softtor Soluções Transformadoras LTDA** e disponibilizado como open source para outras empresas prestadoras de serviço em Brasília/DF que enfrentam os mesmos desafios de integração com o ISS.net.

## Status

Em **produção** para a Softtor desde 2025 via **ABRASF 2.04** (`df.issnetonline.com.br/webservicenfse204`). O Padrão Nacional do DF está disponível apenas como adapter de **homologação** neste repositório; cutover de produção exige decisão humana explícita.

## Requisitos

- **Python 3.11+**
- **[uv](https://github.com/astral-sh/uv)** (gerenciador de pacotes recomendado)
- **Certificado digital A1** (PFX/PKCS12) ICP-Brasil da empresa prestadora
- **Cadastro ativo** na prefeitura de Brasília como prestador de serviços
- **CNAE e Item da LC 116** compatíveis com sua atividade (ver "Configuração")

## Instalação

```bash
git clone https://github.com/Softtor/nfse-mcp.git
cd nfse-mcp
uv sync
```

## Configuração

Copie o arquivo de exemplo e preencha com os dados do seu prestador:

```bash
cp .env.example .env
$EDITOR .env
```

Campos essenciais:

| Variável | Descrição |
|---|---|
| `NFSE_ENVIRONMENT` | `production` ou `homologation` |
| `NFSE_CERTIFICATE_PATH` | Caminho absoluto para o `.p12` |
| `NFSE_CERTIFICATE_PASSWORD` | Senha do certificado |
| `NFSE_PROVIDER_CNPJ` | CNPJ do prestador (14 dígitos) |
| `NFSE_PROVIDER_IM` | Inscrição Municipal |
| `NFSE_PROVIDER_RAZAO_SOCIAL` | Razão social |
| `NFSE_DEFAULT_CNAE` | CNAE principal (ex.: `6209100`) |
| `NFSE_DEFAULT_ITEM_LISTA_SERVICO` | Item LC 116 (ex.: `1.07`) |
| `NFSE_DEFAULT_CODIGO_TRIBUTACAO_MUNICIPIO` | Código municipal de tributação (obrigatório em Brasília) |
| `NFSE_DEFAULT_ALIQUOTA` | Alíquota ISS (ex.: `2.00`) |
| `NFSE_RPS_SERIE` | Série do RPS (`3` produção, `8` homologação) |

> ⚠️ **Nunca commite** `.env`, arquivos de certificado (`*.p12`, `*.pfx`) ou conteúdo de `data/` — o `.gitignore` já protege esses arquivos, mas vale o aviso.

## Tools MCP disponíveis

| Tool | Descrição |
|---|---|
| `lookup_cnpj` | Consulta dados de empresa via BrasilAPI |
| `register_client` | Cadastra tomador (auto-preenche via CNPJ) |
| `list_clients` | Lista clientes cadastrados |
| `emit_nfse` | Emite NFS-e individual |
| `emit_nfse_batch` | Emite lote via CSV (sequencial, uma por uma) |
| `get_nfse_link` | Retorna URLs de visualização/autenticidade |
| `cancel_nfse` | Cancela NFS-e emitida |
| `list_nfse` | Lista NFS-e por período com valores |
| `query_cadastral_data` | Dados cadastrais do prestador no webservice |

### Padrão Nacional DF (homologação apenas)

SKU novo, separado das 9 tools ABRASF 2.04. **Não emite em produção.** Só responde depois de `NFSE_NACIONAL_ENABLED=1` e `NFSE_NACIONAL_ENVIRONMENT=homologation`.

| Tool | Descrição |
|---|---|
| `nacional_homolog_emit_nfse` | Emite uma NFS-e no Padrão Nacional contra o WS de homologação |
| `nacional_homolog_query_nfse` | Consulta NFS-e por número de DPS |
| `nacional_homolog_cancel_nfse` | Envia pedido de cancelamento (evento e101103) |

## Padrão Nacional DF — como apontar para homologação

O ABRASF 2.04 **permanece** o caminho de produção. O Nacional é um módulo irmão (`src/nfse_mcp/nacional/`) e só fala com homologação.

1. Use o **mesmo certificado A1** ICP-Brasil (PFX/PKCS12) já configurado em `NFSE_CERTIFICATE_PATH` / `NFSE_CERTIFICATE_PASSWORD`. O WS Nacional exige esse A1 em mTLS; sem ele o asmx/WSDL responde **403**.
2. No `.env`, **não** mude `NFSE_ENVIRONMENT` para o Nacional. Mantenha produção ABRASF como está e ligue só o SKU novo:

```env
NFSE_NACIONAL_ENABLED=1
NFSE_NACIONAL_ENVIRONMENT=homologation
NFSE_NACIONAL_C_TRIB_NAC=010701
NFSE_NACIONAL_C_TRIB_MUN=107
NFSE_NACIONAL_DPS_SERIE=1
```

3. Endpoint **fixo** neste SKU (não há chave de produção): `https://nfse.issnetonline.com.br/wsnfsenacional/homologacao/nfse.asmx`
4. Um humano precisa ligar `NFSE_NACIONAL_ENABLED=1`. Com o flag em `0` (padrão), as três tools existem mas recusam a chamada.

Fora de escopo neste V1: cutover de produção, multi-CNPJ, lote, portal nacional, e qualquer API de cálculo tributário extra.

Cronograma público da SEEC/DF (Ato Conjunto RFB/CGIBS nº 4, 2026-07-30): ABRASF 2.04 aceito até 2026-09-30; Padrão Nacional obrigatório a partir de 2026-10-01. Este repositório **não** troca o caminho de produção automaticamente nessa data.

## Integração com Claude Code

Adicione ao `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "nfse": {
      "command": "uv",
      "args": [
        "--directory",
        "/caminho/absoluto/para/nfse-mcp",
        "run",
        "nfse-mcp"
      ],
      "env": {}
    }
  }
}
```

Após registrar, basta pedir ao Claude coisas como:
- *"Emita uma NFS-e de R$ 5.000 para o CNPJ 00.000.000/0001-00 com descrição 'Consultoria em TI — abril/2026'"*
- *"Liste todas as NFS-e emitidas em março"*
- *"Cancele a nota 2026/1234"*

## Desenvolvimento

```bash
# Rodar o server (stdio — para testar o protocolo MCP)
uv run nfse-mcp

# Sanity check de importação
uv run python -c "from nfse_mcp.server import main; print('OK')"

# Testes (SOAP Nacional mockado; sem certificado A1 no CI)
uv sync --extra dev
uv run pytest
```

Estrutura do projeto:

```
nfse-mcp/
├── src/nfse_mcp/
│   ├── server.py         # MCP server + 9 tools ABRASF 2.04 + registro das 3 tools Nacional
│   ├── config.py         # Carrega .env → Config ABRASF 2.04
│   ├── models.py         # Dataclasses de domínio
│   ├── certificate.py    # Lê PFX/PKCS12
│   ├── xml_signer.py     # XML-DSig SHA-1 ABRASF 2.04
│   ├── xml_builder.py    # Monta XMLs ABRASF 2.04
│   ├── soap_client.py    # Cliente SOAP ABRASF 2.04
│   ├── cnpj_lookup.py    # BrasilAPI
│   ├── client_store.py   # CRUD de clientes
│   └── nacional/         # Adapter DF Padrão Nacional (homolog-only, SKU separado)
│       ├── config.py
│       ├── xml_builder.py
│       ├── xml_signer.py
│       ├── soap_client.py
│       └── tools.py      # emit / query / cancel
├── tests/                # pytest; SOAP Nacional mockado
├── data/                 # Runtime (clients.json, nfse_log.json — gitignored)
└── schemas/
    └── schema_v204.xsd   # XSD ABRASF 2.04 (referência)
```

Para detalhes técnicos, armadilhas do webservice e fluxo de assinatura XML, veja [CLAUDE.md](CLAUDE.md) — o guia interno que documenta as decisões de design e as peculiaridades do webservice ISS.net de Brasília.

## Limitações conhecidas

- **Escopo geográfico:** funciona apenas com o webservice ISS.net de **Brasília/DF**. Outras prefeituras usam endpoints e variações do padrão ABRASF diferentes.
- **Padrão em produção:** ABRASF 2.04. O Padrão Nacional DF neste repo é **homolog-only** (três tools `nacional_homolog_*`).
- **Método de emissão ABRASF:** `GerarNfse` individual. O `emit_nfse_batch` emite uma nota por vez (não usa `RecepcionarLoteRpsSincrono`, que apresenta problemas de validação não documentados no webservice de Brasília).
- **Nacional V1 não implementa:** produção, lote, multi-CNPJ, portal nacional, consulta por faixa/período, substituição.
- **WSDL Nacional:** `https://nfse.issnetonline.com.br/wsnfsenacional/homologacao/nfse.asmx?wsdl` exige certificado A1 (mTLS). Sem A1 a URL devolve HTTP 403; o CI não chama homologação ao vivo.

## Contribuindo

Issues e Pull Requests são bem-vindos. Por favor:

1. Rode suas alterações em **homologação** (`NFSE_ENVIRONMENT=homologation`, `NFSE_RPS_SERIE=8`) antes de abrir PR.
2. Não commite nenhum dado real de cliente ou certificado.
3. Se adicionar suporte a outras prefeituras, considere extrair uma camada de abstração por município.

## Licença

[MIT](LICENSE) — © 2026 Softtor Soluções Transformadoras LTDA
