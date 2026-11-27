# SEFIN Nacional NFS-e — Mapeamento Técnico

> Documento de pesquisa da API SEFIN Nacional NFS-e para o projeto `nfse-mcp`.  
> Data da pesquisa: 2026-05-06.  
> Fontes: documentação oficial do Portal NFS-e (gov.br), Manual do Contribuinte v1.2 (out/2025), bibliotecas de referência open source.

---

## 1. Resumo Executivo

A **SEFIN Nacional NFS-e** é a API REST do Emissor Público Nacional para o padrão nacional de Nota Fiscal de Serviço Eletrônica. Em vez de SOAP/ABRASF por prefeitura, o contribuinte envia uma **Declaração de Prestação de Serviços (DPS)** em XML, assinada digitalmente, compactada (GZip) e codificada (Base64), dentro de um body JSON. A API valida a DPS síncronamente e retorna a NFS-e autorizada (HTTP 201) ou uma lista de erros fiscais.

**Diferenças principais em relação ao ISS.net Brasília (ABRASF 2.04):**

| Aspecto | ISS.net Brasília | SEFIN Nacional |
|---------|------------------|----------------|
| Protocolo | SOAP | REST |
| Formato | XML puro | JSON envelope + XML DPS interno (GZip+Base64) |
| Autenticação | Certificado A1 (mTLS) | Certificado A1/A3 ICP-Brasil (mTLS) |
| Assinatura | SHA-1 (XML-DSig) | SHA-256 (XML-DSig presumido) |
| Emissão | `GerarNfse` (SOAP action) | `POST /nfse` (JSON body) |
| Consulta | SOAP methods | `GET /nfse/{chaveAcesso}` |
| Cancelamento | SOAP `CancelarNfse` | `POST /nfse/{chaveAcesso}/eventos` (evento XML) |
| Parâmetros municipais | Não disponível | `GET /parametros_municipais/...` |

---

## 2. Links Oficiais

| Recurso | URL |
|---------|-----|
| Portal oficial NFS-e | https://www.gov.br/nfse/pt-br |
| APIs Produção Restrita e Produção | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/apis-prod-restrita-e-producao |
| Swagger Produção Restrita | https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional/docs/index |
| Swagger Produção | https://sefin.nfse.gov.br/SefinNacional/docs/index |
| Documentação atual (PDFs) | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual |
| Manual Contribuinte v1.2 | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-emissor-publico-api-sistema-nacional-nfs-e-v1-2-out2025.pdf |
| Manual ADN v1.0 (fev/2026) | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-apis-adn-sistema-nacional-nfse.pdf |
| Guia Emissor Web v1.2 | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/guia-emissorpubliconacionalweb-snnfse-ern-v12.pdf |
| Schemas XSD | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual |

---

## 3. Ambientes

| Ambiente | Base URL | Finalidade |
|----------|----------|------------|
| **Produção Restrita** | `https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional` | Testes, homologação, validação técnica. Dados não têm validade fiscal (a menos que explicitado). |
| **Produção** | `https://sefin.nfse.gov.br/SefinNacional` | Emissão real de NFS-e com validade fiscal. |

---

## 4. Endpoints

### 4.1. API Sefin Nacional (Emissão e Consulta)

| Método | Endpoint | Descrição | Resposta |
|--------|----------|-----------|----------|
| `POST` | `/nfse` | Recepciona DPS e gera NFS-e síncrona. Body: `{"dpsXmlGZipB64": "..."}` | `201` = sucesso (JSON com `nfseXmlGZipB64`, `chaveAcesso`). `400/422` = erros de validação. |
| `GET` | `/nfse/{chaveAcesso}` | Consulta NFS-e pela chave de acesso (50 dígitos). | JSON com `nfseXmlGZipB64` ou erro. |
| `GET` | `/dps/{id}` | Consulta chave de acesso pelo identificador da DPS. | JSON com `chaveAcesso` (se certificado corresponder a prestador/tomador/intermediário). |
| `HEAD` | `/dps/{id}` | Verifica se a DPS já foi processada (virou NFS-e). | `200` se existir; `404` se não. |
| `POST` | `/nfse/{chaveAcesso}/eventos` | Registra evento na NFS-e (cancelamento, substituição, etc.). Body: `{"eventoXmlGZipB64": "..."}` | `201` = evento registrado. |
| `GET` | `/nfse/{chaveAcesso}/eventos` | Lista eventos vinculados à NFS-e. | JSON com lista de eventos. |
| `GET` | `/danfse/{chaveAcesso}` | Retorna PDF do DANFSe. | Binary PDF ou JSON erro. |

**Nota sobre `/dps/{id}`:** O `id` da DPS é uma concatenação fixa de:
- Código IBGE do Município Emissor: 7 dígitos
- Tipo de Inscrição: 1 dígito (1=CPF, 2=CNPJ)
- Inscrição Federal: 14 dígitos (CPF preencher com zeros à esquerda)
- Série DPS: 5 dígitos
- Número DPS: 15 dígitos

Total: **42 dígitos**.

### 4.2. API Parâmetros Municipais

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/parametros_municipais/{codigoMunicipio}/convenio` | Consulta se o município é conveniado e seus parâmetros de convênio. |
| `GET` | `/parametros_municipais/{codigoMunicipio}/{codigoServico}` | Consulta alíquotas, regimes especiais, deduções/reduções por código de serviço. |
| `GET` | `/parametros_municipais/{codigoMunicipio}/{CPF/CNPJ}/retencoes` | Consulta retenções de ISSQN do contribuinte no município. |
| `GET` | `/parametros_municipais/{codigoMunicipio}/{CPF/CNPJ}/beneficios` | Consulta benefícios municipais do contribuinte. |

---

## 5. Autenticação

A API SEFIN Nacional exige **mTLS (Mutual TLS)**.

### 5.1. Requisitos do Certificado

- **Tipo:** A1 (arquivo `.pfx` / `.p12`) ou A3 (token/smartcard).
- **ICP-Brasil:** Obrigatório.
- **e-CNPJ preferencial:** O CNPJ do certificado deve corresponder ao CNPJ do prestador na DPS. A API valida o CNPJ Raiz.
- **OID 2.16.76.1.3.3:** Deve conter o CNPJ/CPF do titular no subject do certificado.

### 5.2. Como funciona

1. O cliente HTTP (ex: `requests` em Python) deve apresentar o certificado digital + chave privada no handshake TLS.
2. O servidor da SEFIN valida o certificado contra as CAs ICP-Brasil.
3. Não há token, API key, OAuth, ou senha adicional na requisição HTTP.
4. O corpo da requisição é JSON; o conteúdo fiscal está dentro do JSON (XML DPS comprimido).

### 5.3. Cadastro Prévio

- **Não é necessário cadastro prévio em portal** para consumir a API em si.
- O prestador precisa estar ativo no cadastro nacional de contribuintes NFS-e (implícito ao ter certificado válido e município conveniado).
- O município de atuação do prestador precisa estar **conveniado** ao Sistema Nacional NFS-e.

---

## 6. Payloads

### 6.1. Emissão — POST /nfse

**Request:**

```json
{
  "dpsXmlGZipB64": "H4sIAAAAAAAAA3WRQW7DMAxE75N3..."
}
```

Onde `dpsXmlGZipB64` é:
1. XML DPS assinado digitalmente (XML-DSig)
2. Compactado com GZip
3. Codificado em Base64

**Response de sucesso (HTTP 201):**

```json
{
  "tipoAmbiente": 1,
  "versaoAplicativo": "1.0.0",
  "dataHoraProcessamento": "2026-05-06T10:00:00-03:00",
  "chaveAcesso": "33045572238744743000149000000000001026029316934590",
  "idDPS": "530010821122233300018100000000000001",
  "nfseXmlGZipB64": "H4sIAAAAAAAAA3WRQW7D..."
}
```

**Response de erro (HTTP 400/422):**

```json
{
  "erros": [
    {
      "codigo": "E001",
      "descricao": "CPF/CNPJ do prestador inválido"
    }
  ]
}
```

### 6.2. Consulta NFS-e — GET /nfse/{chaveAcesso}

**Response de sucesso:**

```json
{
  "tipoAmbiente": 1,
  "versaoAplicativo": "1.0.0",
  "dataHoraProcessamento": "2026-05-06T10:00:00-03:00",
  "chaveAcesso": "33045572238744743000149000000000001026029316934590",
  "idDPS": "530010821122233300018100000000000001",
  "nfseXmlGZipB64": "H4sIAAAAAAAAA3WRQW7D..."
}
```

### 6.3. Evento — POST /nfse/{chaveAcesso}/eventos

**Request:**

```json
{
  "eventoXmlGZipB64": "H4sIAAAAAAAAA3WRQW7D..."
}
```

Onde `eventoXmlGZipB64` é o XML do evento (ex: `pedRegEvento` com `infPedReg` de cancelamento) assinado, GZip, Base64.

---

## 7. Certificados

| Aspecto | Detalhe |
|---------|---------|
| Tipo aceito | A1 (arquivo) ou A3 (token) |
| Formato arquivo | `.pfx` ou `.p12` (PKCS#12) |
| Algoritmo de assinatura XML | XML-DSig (presumido SHA-256) |
| Extração Python | `cryptography.hazmat.primitives.serialization.pkcs12` |
| Uso no `requests` | `cert=(cert_pem_path, key_pem_path)` |

O projeto `nfse-mcp` já possui a classe `Certificate` (`certificate.py`) que lê PFX e extrai private key + X509. Pode ser reaproveitada.

---

## 8. Requisitos de Cadastro / Portal

1. **Certificado digital ICP-Brasil válido** com CNPJ do prestador.
2. **Município conveniado** ao Sistema Nacional NFS-e (verificar via `/parametros_municipais/{codigoMunicipio}/convenio`).
3. Prestador deve estar ativo como contribuinte de ISSQN no município de atuação.
4. Para emissão via API, não é necessário acesso ao Portal Web (https://www.nfse.gov.br/EmissorNacional/Login), mas o portal pode ser usado para consultas manuais.

---

## 9. Fluxo Mínimo de Emissão

```
1. [OPCIONAL] Consultar /parametros_municipais/{codigoMunicipio}/convenio
   → Verificar se município é conveniado.

2. Montar XML DPS com dados da prestação de serviço.
   → Campos: prestador, tomador, serviço, valores, tributação, série/número DPS.

3. Assinar digitalmente o XML DPS (XML-DSig no nó raiz).

4. Validar XML assinado contra schema XSD local (DPS_v1.00.xsd).

5. Compactar XML com GZip → codificar em Base64.

6. Montar JSON body: {"dpsXmlGZipB64": "<base64>"}

7. Enviar POST /nfse com mTLS (certificado A1/A3).

8. Receber resposta:
   a) HTTP 201 → decodificar nfseXmlGZipB64 → extrair XML NFS-e → retornar chaveAcesso.
   b) HTTP 4xx → extrair lista de erros (codigo/descricao) → retornar erro normalizado.

9. [OPCIONAL] Consultar GET /danfse/{chaveAcesso} para obter PDF.
```

---

## 10. Fluxo de Consulta

```
1. Consultar por chave de acesso:
   GET /nfse/{chaveAcesso}
   → Retorna JSON com nfseXmlGZipB64 (decodificar para obter XML).

2. Consultar por identificador da DPS:
   GET /dps/{idDPS}
   → Retorna chaveAcesso da NFS-e correspondente (se permissão do certificado).

3. Verificar se DPS foi processada (sem obter chave):
   HEAD /dps/{idDPS}
   → HTTP 200 = processada; 404 = não encontrada/pendente.
```

---

## 11. Fluxo de Eventos (Cancelamento)

```
1. Montar XML de evento (pedRegEvento v1.00):
   → Tipo evento: e101101 (cancelamento)
   → Campos: chave NFSe, motivo, CNPJ autor, data/hora do evento.

2. Assinar digitalmente o nó infPedReg.

3. Compactar com GZip → Base64.

4. POST /nfse/{chaveAcesso}/eventos
   → Body: {"eventoXmlGZipB64": "..."}

5. Resposta HTTP 201 = evento registrado com sucesso.
```

---

## 12. Códigos de Erro / Rejeição Mais Comuns

> Nota: A documentação oficial não publica uma lista única e completa de códigos. Os códigos abaixo são inferidos de bibliotecas de referência e manuais.

| Código | Significado | Ação |
|--------|-------------|------|
| `E001` | CPF/CNPJ do prestador inválido | Verificar dados do prestador na DPS |
| `E002` | Certificado digital não corresponde ao CNPJ/CPF do prestador | Usar certificado correto (e-CNPJ) |
| `E003` | Município não conveniado | Consultar `/convenio` antes de emitir |
| `E004` | XML fora do schema / estrutura inválida | Validar XSD localmente antes de enviar |
| `E005` | DPS já informada (duplicidade) | Verificar se DPS já foi emitida; não reenviar |
| `E006` | Alíquota inválida para o serviço/município | Consultar parâmetros municipais |
| `E007` | Campos obrigatórios não informados | Verificar preenchimento de todos os campos obrigatórios |
| `E008` | Data de competência inválida | Usar data no formato correto (YYYY-MM-DD) |
| `E009` | Tomador com dados incompletos | Completar endereço do tomador |
| `E010` | Valor do serviço inválido | Usar valor decimal positivo |

---

## 13. XSDs para Validação Local

Os schemas devem ser baixados do portal oficial e colocados em `schemas/sefin_nacional/`:

| Schema | Arquivo | Uso |
|--------|---------|-----|
| DPS v1.00 | `DPS_v1.00.xsd` | Validar XML DPS antes do envio |
| DPS v1.01 | `DPS_v1.01.xsd` | Para emissões com campos IBSCBS (futuro) |
| NFSe v1.00 | `NFSe_v1.00.xsd` | Validar XML da NFSe retornada |
| Evento v1.00 | `evento_v1.00.xsd` | Validar XML de eventos |
| Pedido Registro Evento v1.00 | `pedRegEvento_v1.00.xsd` | Validar XML de pedido de evento |
| Tipos Simples | `tiposSimples_v1.00.xsd` | Tipos auxiliares |
| Tipos Complexos | `tiposComplexos_v1.00.xsd` | Tipos auxiliares |
| XML-DSig | `xmldsig-core-schema.xsd` | Assinatura digital |

---

## 14. Campos Mínimos para DPS de Teste

Para uma DPS mínima válida em ambiente de Produção Restrita:

### 14.1. Prestador

| Campo | Exemplo | Obrigatório |
|-------|---------|-------------|
| CNPJ | `11222333000181` | Sim |
| Inscrição Municipal | `1234567` | Sim (depende do município) |
| Razão Social | `PRESTADOR TESTE LTDA` | Sim |
| Endereço completo | Logradouro, número, bairro, município IBGE, UF, CEP | Sim |

### 14.2. Tomador

| Campo | Exemplo | Obrigatório |
|-------|---------|-------------|
| CPF ou CNPJ | `12345678000190` | Sim |
| Razão Social | `CLIENTE TOMADOR LTDA` | Sim |
| Endereço completo | Logradouro, número, bairro, município IBGE, UF, CEP | Sim |

### 14.3. Serviço

| Campo | Exemplo | Obrigatório |
|-------|---------|-------------|
| Código do serviço (Lista Nacional) | `1.07` ou código NBS | Sim |
| Discriminação | `Consultoria em TI` | Sim |
| Valor do serviço | `5000.00` | Sim |
| Alíquota | `2.00` | Sim (ou consultar parâmetros) |
| ISS Retido | `2` (Não) | Sim |

### 14.4. DPS

| Campo | Exemplo | Obrigatório |
|-------|---------|-------------|
| Série DPS | `1` | Sim |
| Número DPS | `1` | Sim |
| Data de competência | `2026-05-01` | Sim |
| Tipo de ambiente | `2` (Produção Restrita) | Sim |

---

## 15. Dados Fiscais no Cadastro do Prestador

- CNPJ / CPF
- Inscrição Municipal (se exigida pelo município)
- Razão Social / Nome
- Endereço completo
- Optante pelo Simples Nacional (1=Não, 2=MEI, 3=ME/EPP)
- Regime Especial de Tributação (0=Nenhum, 1=Ato Cooperado, 2=Estimativa, 3=Microempresa Municipal, 4=Notário ou Registrador)
- Incentivo Fiscal (1=Sim, 2=Não)

---

## 16. Dados Fiscais no Cadastro do Tomador

- CNPJ / CPF
- Razão Social / Nome
- Endereço completo (logradouro, número, bairro, município IBGE, UF, CEP)
- Inscrição Municipal (opcional, depende do município)

---

## 17. Dados Fiscais no Cadastro do Serviço

- Código do serviço conforme Lista de Serviços Nacional (ou NBS, se aplicável)
- Discriminação do serviço
- Valor do serviço
- Alíquota de ISSQN
- Indicador de ISS retido
- Regime especial de tributação (se aplicável)
- Deduções / reduções (se aplicável)
- Benefícios municipais (se aplicável)

---

## 18. Campos que NÃO devem ser inferidos pela IA sem confirmação humana

| Campo | Motivo |
|-------|--------|
| Alíquota de ISS | Pode variar por município, serviço e regime do prestador. Erro gera rejeição fiscal. |
| Código do serviço (Lista Nacional / NBS) | Define a tributação. Erro pode classificar o serviço incorretamente. |
| Regime especial de tributação | Afeta cálculo do imposto. Só o contribuinte ou contador sabe o regime correto. |
| Optante Simples Nacional | Dado cadastral do prestador. A IA pode sugerir, mas precisa de confirmação. |
| ISS Retido | Depende do contrato e da legislação municipal. |
| Deduções / reduções / benefícios | Requer conhecimento específico da legislação municipal. |
| Valor do serviço | Pode ser inferido a partir da descrição do usuário, mas exige confirmação. |
| Data de competência | Pode ser inferida como 1º do mês atual, mas o usuário deve confirmar. |

**Campos que a IA pode inferir com baixo risco:**
- Endereço do tomador (via BrasilAPI por CNPJ)
- Razão social do tomador (via BrasilAPI)
- Código IBGE do município (via BrasilAPI ou tabela)
- UF e CEP (via BrasilAPI)

---

## 19. Riscos Fiscais e Técnicos

| Risco | Severidade | Mitigação |
|-------|------------|-----------|
| Emissão duplicada (mesma DPS) | Alta | Implementar idempotência por `idDPS`; armazenar estado local; não reenviar em caso de erro de duplicidade. |
| Município não conveniado | Alta | Sempre consultar `/parametros_municipais/{codigoMunicipio}/convenio` antes de emitir. |
| Certificado expirado | Alta | Monitorar validade do certificado; alertar 30 dias antes. |
| XML inválido / rejeição fiscal | Média | Validar XSD localmente antes de transmitir; testar em Produção Restrita primeiro. |
| Dados do tomador incompletos | Média | Validar campos obrigatórios antes de montar DPS; usar BrasilAPI como fallback. |
| IA inferir dados tributários incorretamente | Alta | Sempre pedir confirmação humana para alíquota, código de serviço, regime, etc. |
| Vazamento de dados em logs | Alta | Nunca logar XML completo em produção; mascarar CPF/CNPJ, valores, chaves de acesso. |
| Rate limit / indisponibilidade da API | Média | Implementar retry com backoff exponencial; não retry em erros fiscais (4xx). |
| Cancelamento indevido | Alta | Exigir confirmação dupla do usuário antes de cancelar; registrar motivo. |

---

## 20. Dúvidas em Aberto

1. **Qual algoritmo de hash exato para assinatura XML na SEFIN Nacional?** O manual v1.2 cita XML-DSig mas não especifica SHA-1 vs SHA-256. A biblioteca de referência `gildonei/nfse-nacional` (PHP) usa SHA-256. Precisa ser validado empiricamente em Produção Restrita.
2. **O schema DPS v1.01 é obrigatório desde 01/01/2026?** A documentação menciona que versões 1.0 e 1.01 são válidas, mas v1.01 é necessária para campos IBSCBS (Reforma Tributária). Para MVP, usar v1.00.
3. **O endpoint de eventos requer assinatura de qual nó exatamente?** Presume-se `infPedReg` dentro do `pedRegEvento`, mas precisa confirmar contra schema `pedRegEvento_v1.00.xsd`.
4. **Qual é o limite de rate limit da API?** Não documentado explicitamente no manual do contribuinte.
5. **A SEFIN Nacional aceita CPF como prestador (pessoa física)?** O manual menciona CPF/CNPJ, mas a maioria dos exemplos usa CNPJ. Precisa confirmar.
6. **Como funciona exatamente o número da DPS (nDPS)?** É sequencial por prestador? Precisa buscar disponível? Ou o emissor define livremente? Não há endpoint equivalente ao `ConsultarRpsDisponivel` do ISS.net.
7. **A SEFIN Nacional retorna o número da NFS-e em algum campo separado?** O manual mostra `chaveAcesso` e `idDPS`, mas não explicita se há um campo `numeroNfse` no JSON de resposta. O número pode estar dentro do XML NFSe retornado.

---

## 21. Referências

- Manual do Contribuinte – Emissor Público API v1.2 (out/2025). SEFIN Nacional NFS-e.
- Guia do Painel Administrativo Municipal NFS-e v1.2 (out/2025).
- Manual Municípios APIs ADN – Sistema Nacional NFS-e v1.2 (out/2025).
- Nota Técnica SE/CGNFS-e nº 004/2025 (Reforma Tributária – layout IBSCBS).
- Nota Técnica SE/CGNFS-e nº 008/2026 (DANFSe).
- Biblioteca de referência (PHP): https://github.com/gildonei/nfse-nacional
- Biblioteca de referência (PHP): https://github.com/pedrocasado/nfse-php
- Artigo técnico: https://notagateway.com.br/blog/api-nfse-nacional/
