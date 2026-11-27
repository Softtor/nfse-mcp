# nfse-mcp

MCP Server Python para emissão de NFS-e (Nota Fiscal de Serviço Eletrônica) em **Brasília/DF** através do webservice ISS.net, padrão **ABRASF 2.04**.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/protocol-MCP-purple.svg)](https://modelcontextprotocol.io)

## O que é

Permite que um LLM (via Model Context Protocol) emita, consulte, cancele e gerencie notas fiscais de serviço diretamente no webservice da prefeitura de Brasília. Expõe **9 tools MCP** para fluxo completo de faturamento — incluindo cadastro automático de tomadores via BrasilAPI, emissão individual, emissão em lote via CSV e consulta de URLs de autenticidade.

Desenvolvido originalmente para o uso interno da **Softtor Soluções Transformadoras LTDA** e disponibilizado como open source para outras empresas prestadoras de serviço em Brasília/DF que enfrentam os mesmos desafios de integração com o ISS.net.

## Status

Em **produção** para a Softtor desde 2025. Testado contra o webservice oficial `df.issnetonline.com.br`. Adapta-se a qualquer prestador com certificado digital A1 e cadastro ativo na prefeitura de Brasília.

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
```

### Como testar

```bash
uv sync
uv run pytest tests/ -v
```

Os testes usam dados fictícios (CNPJs de exemplo, certificado e servidor simulados) e não enviam nada à prefeitura nem à SEFIN. Para provar uma emissão de verdade, use o ambiente de homologação com um certificado seu (`SEFIN_ENVIRONMENT=production_restricted`) e os scripts de `scripts/`.

Estrutura do projeto:

```
nfse-mcp/
├── src/nfse_mcp/
│   ├── server.py         # MCP server + 9 tools (entrypoint)
│   ├── config.py         # Carrega .env → Config dataclass
│   ├── models.py         # Dataclasses de domínio
│   ├── certificate.py    # Lê PFX/PKCS12
│   ├── xml_signer.py     # XML-DSig SHA-1 manual
│   ├── xml_builder.py    # Monta XMLs ABRASF 2.04
│   ├── soap_client.py    # Cliente SOAP raw (sem zeep)
│   ├── cnpj_lookup.py    # BrasilAPI
│   └── client_store.py   # CRUD de clientes
├── data/                 # Runtime (clients.json, nfse_log.json — gitignored)
└── schemas/
    └── schema_v204.xsd   # XSD ABRASF 2.04 (referência)
```

Para detalhes técnicos, armadilhas do webservice e fluxo de assinatura XML, veja [CLAUDE.md](CLAUDE.md) — o guia interno que documenta as decisões de design e as peculiaridades do webservice ISS.net de Brasília.

## Limitações conhecidas

- **Escopo geográfico:** funciona apenas com o webservice ISS.net de **Brasília/DF**. Outras prefeituras usam endpoints e variações do padrão ABRASF diferentes.
- **Padrão:** ABRASF 2.04 apenas. Prefeituras em versões anteriores (1.00, 2.00) não são suportadas.
- **Método de emissão:** `GerarNfse` individual. O `emit_nfse_batch` emite uma nota por vez (não usa `RecepcionarLoteRpsSincrono`, que apresenta problemas de validação não documentados no webservice de Brasília).
- **Testes:** a suíte automatizada (`tests/`) roda sem rede, sem certificado e sem `.env`. A emissão real só foi provada em produção.

## Contribuindo

Issues e Pull Requests são bem-vindos. Por favor:

1. Rode suas alterações em **homologação** (`NFSE_ENVIRONMENT=homologation`, `NFSE_RPS_SERIE=8`) antes de abrir PR.
2. Não commite nenhum dado real de cliente ou certificado.
3. Se adicionar suporte a outras prefeituras, considere extrair uma camada de abstração por município.

## Licença

[MIT](LICENSE) — © 2026 Softtor Soluções Transformadoras LTDA
