"""
Script controlado para teste em PRODUÇÃO SEFIN Nacional.
Emite 1 nota de R$ 1,00 e cancela imediatamente se bem-sucedida.
"""

import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from nfse_mcp.certificate import Certificate
from nfse_mcp.config import Config, ProviderConfig, ServiceDefaults
from nfse_mcp.sefin_nacional.config import SefinNacionalConfig
from nfse_mcp.sefin_nacional.provider import SefinNacionalProvider
from nfse_mcp.application.services.client_service import ClientApplicationService
from nfse_mcp.application.services.invoice_log_service import InvoiceLogService
from nfse_mcp.application.services.sefin_nacional_service import SefinNacionalApplicationService
from nfse_mcp.application.dto.commands import IssueInvoiceCommand
from nfse_mcp.client_store import ClientStore
from nfse_mcp.ports.service_invoice_provider import CancelServiceInvoiceInput


def main():
    load_dotenv(Path(__file__).parent.parent / ".env")

    cert_path = os.getenv("NFSE_CERTIFICATE_PATH")
    cert_pass = os.getenv("NFSE_CERTIFICATE_PASSWORD")
    cnpj = os.getenv("NFSE_PROVIDER_CNPJ")
    razao = os.getenv("NFSE_PROVIDER_RAZAO_SOCIAL")
    im = os.getenv("NFSE_PROVIDER_IM", "")

    print("=" * 60)
    print("  SEFIN NACIONAL — TESTE EM PRODUÇÃO")
    print("=" * 60)
    print(f"  Prestador: {razao}")
    print(f"  CNPJ: {cnpj}")
    print(f"  Certificado: {cert_path}")
    print(f"  Ambiente: PRODUÇÃO REAL")
    print("=" * 60)

    # Configuração de produção
    config = Config(
        environment="production",
        certificate_path=cert_path,
        certificate_password=cert_pass,
        provider=ProviderConfig(
            cnpj=cnpj,
            im=im,
            razao_social=razao,
            simples_nacional=int(os.getenv("NFSE_PROVIDER_SIMPLES_NACIONAL", "1")),
            regime_tributacao=int(os.getenv("NFSE_PROVIDER_REGIME_TRIBUTACAO", "6")),
            incentivo_fiscal=int(os.getenv("NFSE_PROVIDER_INCENTIVO_FISCAL", "2")),
        ),
        service_defaults=ServiceDefaults(
            cnae=os.getenv("NFSE_DEFAULT_CNAE", ""),
            item_lista_servico=os.getenv("NFSE_DEFAULT_ITEM_LISTA_SERVICO", "1.07"),
            codigo_tributacao_municipio=os.getenv("NFSE_DEFAULT_CODIGO_TRIBUTACAO_MUNICIPIO", ""),
            aliquota=os.getenv("NFSE_DEFAULT_ALIQUOTA", "2.00"),
            municipio_ibge="5300108",
            iss_retido=2,
            exigibilidade_iss=1,
        ),
        rps_serie="1",
        webservice_url="",
        data_dir=Path(__file__).parent.parent / "data",
    )

    sefin_config = SefinNacionalConfig(
        environment="production",
        base_url="https://sefin.nfse.gov.br/SefinNacional",
        certificate_path=cert_path,
        certificate_password=cert_pass,
        timeout=60,
        max_retries=2,
        debug=False,
        skip_xsd_validation=True,
    )

    cert = Certificate(cert_path, cert_pass)
    provider = SefinNacionalProvider(sefin_config, cert)

    store = ClientStore(config.data_dir)
    client_service = ClientApplicationService(store)
    log_service = InvoiceLogService(config.data_dir)
    sefin_service = SefinNacionalApplicationService(
        client_service=client_service,
        invoice_provider=provider,
        parameter_provider=provider,
        config=config,
        sefin_config=sefin_config,
        log_service=log_service,
    )

    # Use o próprio CNPJ da empresa como tomador para simplificar
    competencia = date.today().replace(day=1).isoformat()

    print(f"\n  --- ETAPA 1: EMISSÃO ---")
    print(f"  Valor: R$ 1,00")
    print(f"  Serviço: 1.07")
    print(f"  Competência: {competencia}")
    print(f"  Tomador: {cnpj} (própria empresa)")

    cmd = IssueInvoiceCommand(
        client_document=cnpj,
        valor="1.00",
        discriminacao="Servico de teste de integracao SEFIN Nacional - nfse-mcp",
        competencia=competencia,
        codigo_servico="1.07",
        aliquota="2.00",
        codigo_municipio="5300108",
    )

    try:
        result = sefin_service.issue_invoice(cmd)
    except Exception as e:
        print(f"\n  ❌ EMISSÃO FALHOU: {e}")
        if hasattr(e, 'raw_errors') and e.raw_errors:
            print(f"  Detalhes do erro:")
            for err in e.raw_errors:
                print(f"     [{err.get('codigo', 'N/A')}] {err.get('descricao', 'N/A')}")
        import traceback
        traceback.print_exc()
        return 1

    if not result.success:
        print(f"\n  ❌ EMISSÃO REJEITADA:")
        for err in result.errors:
            print(f"     [{err.get('codigo', 'N/A')}] {err.get('descricao', 'N/A')}")
        return 1

    print(f"\n  ✅ EMISSÃO BEM-SUCEDIDA!")
    print(f"     Chave de Acesso: {result.chave_acesso}")
    print(f"     idDPS: {result.id_dps}")
    print(f"     Data/Hora: {result.data_hora_processamento or 'N/A'}")

    # ETAPA 2: CANCELAMENTO
    print(f"\n  --- ETAPA 2: CANCELAMENTO ---")
    print(f"  Motivo: 1 - Erro na Emissao")

    try:
        cancel_input = CancelServiceInvoiceInput(
            chave_acesso=result.chave_acesso,
            motivo_codigo="1",
            motivo_descricao="Erro na Emissao",
            cnpj_autor=cnpj,
        )
        cancel_result = provider.cancel(cancel_input)
    except Exception as e:
        print(f"\n  ❌ CANCELAMENTO FALHOU: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n  ⚠️  NOTA EMITIDA E NÃO CANCELADA!")
        print(f"     Chave: {result.chave_acesso}")
        print(f"     Ação necessária: cancelar manualmente no portal")
        return 1

    if not cancel_result.success:
        print(f"\n  ❌ CANCELAMENTO REJEITADO:")
        for err in cancel_result.errors:
            print(f"     [{err.get('codigo', 'N/A')}] {err.get('descricao', 'N/A')}")
        print(f"\n  ⚠️  NOTA EMITIDA E NÃO CANCELADA!")
        print(f"     Chave: {result.chave_acesso}")
        return 1

    print(f"\n  ✅ CANCELAMENTO BEM-SUCEDIDO!")
    print(f"     Chave: {result.chave_acesso}")

    print("\n" + "=" * 60)
    print("  TESTE COMPLETO: EMISSÃO + CANCELAMENTO OK")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
