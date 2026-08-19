# NFS-e Padrão Nacional DF (homologação)

Adapter SOAP irmão do ABRASF 2.04. Homolog-only. A URL de produção
`https://nfse.fazenda.df.gov.br/wsnfsenacional/nfse.asmx` está no código
como constante documentada e **não é usada**.

## Gate

- `NFSE_NACIONAL_ENABLED=1`
- `NFSE_NACIONAL_ENVIRONMENT=homologation`
- Certificado A1 ICP-Brasil em `NFSE_CERTIFICATE_PATH` (mTLS + assinatura)
- Sem A1, asmx/WSDL devolve HTTP 403

Endpoint: `https://nfse.issnetonline.com.br/wsnfsenacional/homologacao/nfse.asmx`

## Contrato V1

Namespace: `http://www.sped.fazenda.gov.br/nfse`

| Operação MCP | SOAP | XML |
|---|---|---|
| emit | `GerarNfse` | `GerarNfseEnvio` / `DPS` |
| query | `ConsultarNfseDps` | `ConsultarNfseDpsEnvio` |
| cancel | `CancelarNfse` | `pedRegEvento` / `e101103` |

Cabeçalho: `versao="1.00"` / `versaoDados=1.00`.

## Risco: `GerarNfse` pode não existir no WSDL real

V1 usa `GerarNfse` porque o Manual Nota Control v1.01 (DF) e o mapeamento
Unimake `BrasiliaDF.xml` listam esse método para emissão individual.

O WSDL homolog não foi lido aqui: GET sem A1 retorna 403. Em outro município
ISS.net (`wsnfsenacional`), o WSDL obtido com mTLS **não expôs** `GerarNfse`;
a emissão que funcionou foi `RecepcionarLoteDpsSincrono` com uma DPS.

Se a homologação Softtor devolver SOAP fault de método inexistente, o próximo
passo é `RecepcionarLoteDpsSincrono`. **Não está implementado.**
