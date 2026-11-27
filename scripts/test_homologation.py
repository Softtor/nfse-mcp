"""
Script de teste de homologação para ABRASF e SEFIN Nacional.

Executa consultas read-only e, se bem-sucedidas, emite notas de teste.

Usage:
    uv run python scripts/test_homologation.py [--abrasf] [--sefin] [--all]
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nfse_mcp.certificate import Certificate
from nfse_mcp.config import Config, ProviderConfig, ServiceDefaults
from nfse_mcp.xml_signer import XmlSigner
from nfse_mcp.abrasf.soap_client import SoapClient
from nfse_mcp.abrasf.xml_builder import build_cabecalho, build_consultar_dados_cadastrais_envio
from nfse_mcp.sefin_nacional import SefinNacionalConfig, SefinNacionalProvider, load_sefin_config
from nfse_mcp.application.services.client_service import ClientApplicationService
from nfse_mcp.application.services.invoice_log_service import InvoiceLogService
from nfse_mcp.application.services.abrasf_service import AbrasfApplicationService
from nfse_mcp.application.services.sefin_nacional_service import SefinNacionalApplicationService
from nfse_mcp.application.dto.commands import IssueInvoiceCommand, QueryParametersCommand
from nfse_mcp.client_store import ClientStore
from dotenv import load_dotenv


def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def divider(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def ok(msg: str):
    print(f"  [OK] {msg}")


def fail(msg: str):
    print(f"  [FAIL] {msg}")


def warn(msg: str):
    print(f"  [WARN] {msg}")


# ---------------------------------------------------------------------------
# ABRASF Homologation Tests
# ---------------------------------------------------------------------------

def test_abrasf_homologation():
    divider("ABRASF - Homologação")

    load_env()
    cert_path = os.getenv("NFSE_CERTIFICATE_PATH", "")
    cert_password = os.getenv("NFSE_CERTIFICATE_PASSWORD", "")
    cnpj = os.getenv("NFSE_PROVIDER_CNPJ", "")
    im = os.getenv("NFSE_PROVIDER_IM", "")
    razao = os.getenv("NFSE_PROVIDER_RAZAO_SOCIAL", "")

    if not cert_path or not Path(cert_path).exists():
        fail(f"Certificado não encontrado: {cert_path}")
        return False

    if not cnpj or cnpj == "00000000000000":
        fail("CNPJ do prestador não configurado no .env")
        return False

    ok(f"Certificado encontrado: {cert_path}")
    ok(f"CNPJ Prestador: {cnpj}")

    # Build homologation config manually
    config = Config(
        environment="homologation",
        certificate_path=cert_path,
        certificate_password=cert_password,
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
            item_lista_servico=os.getenv("NFSE_DEFAULT_ITEM_LISTA_SERVICO", ""),
            codigo_tributacao_municipio=os.getenv("NFSE_DEFAULT_CODIGO_TRIBUTACAO_MUNICIPIO", ""),
            aliquota=os.getenv("NFSE_DEFAULT_ALIQUOTA", "2.00"),
            municipio_ibge=os.getenv("NFSE_DEFAULT_MUNICIPIO_IBGE", "5300108"),
            iss_retido=int(os.getenv("NFSE_DEFAULT_ISS_RETIDO", "2")),
            exigibilidade_iss=int(os.getenv("NFSE_DEFAULT_EXIGIBILIDADE_ISS", "1")),
        ),
        rps_serie="8",  # homologation series
        webservice_url="https://www.issnetonline.com.br/apresentacao/df/webservicenfse204/nfse.asmx",
        data_dir=Path(__file__).parent.parent / "data",
    )

    try:
        cert = Certificate(config.certificate_path, config.certificate_password)
        ok("Certificado carregado com sucesso")
    except Exception as e:
        fail(f"Erro ao carregar certificado: {e}")
        return False

    signer = XmlSigner(cert)
    soap = SoapClient(config, cert)

    # Test 1: Consultar dados cadastrais
    print("\n  --- Teste 1: Consultar Dados Cadastrais ---")
    try:
        header = build_cabecalho()
        data_xml = build_consultar_dados_cadastrais_envio(config)
        signed = signer.sign_xml(data_xml)
        response = soap.consultar_dados_cadastrais(header, signed)

        if response.has_errors():
            errors = response.get_errors()
            for e in errors:
                fail(f"[{e.get('Codigo', '')}] {e.get('Mensagem', '')}")
        else:
            ok("Consulta cadastral bem-sucedida")
            # Show some provider data
            json_str = response.to_json()
            import json
            data = json.loads(json_str)
            if isinstance(data, dict) and "ConsultarDadosCadastraisResposta" in data:
                resp = data["ConsultarDadosCadastraisResposta"]
                if "DadosCadastrais" in resp:
                    dc = resp["DadosCadastrais"]
                    print(f"       Razão Social: {dc.get('RazaoSocial', 'N/A')}")
                    print(f"       Situação: {dc.get('Situacao', 'N/A')}")
    except Exception as e:
        fail(f"Erro na consulta cadastral: {e}")
        return False

    # Test 2: Consultar RPS disponível
    print("\n  --- Teste 2: Consultar RPS Disponível ---")
    try:
        NS = "http://www.abrasf.org.br/nfse.xsd"
        rps_xml = (
            f'<ConsultarRpsDisponivelEnvio xmlns="{NS}">'
            f'<Pedido>'
            f'<Prestador>'
            f'<CpfCnpj><Cnpj>{config.provider.cnpj}</Cnpj></CpfCnpj>'
            f'<InscricaoMunicipal>{config.provider.im}</InscricaoMunicipal>'
            f'</Prestador>'
            f'<Pagina>1</Pagina>'
            f'</Pedido>'
            f'</ConsultarRpsDisponivelEnvio>'
        )
        signed = signer.sign_xml(rps_xml)
        header = build_cabecalho()
        resp = soap.consultar_rps_disponivel(header, signed)

        if resp.has_errors():
            errors = resp.get_errors()
            for e in errors:
                fail(f"[{e.get('Codigo', '')}] {e.get('Mensagem', '')}")
        else:
            if resp.xml_tree is not None:
                numeros = resp.xml_tree.findall(f".//{{{NS}}}RpsDisponivel/{{{NS}}}Numero")
                if numeros:
                    ok(f"RPS disponível encontrado: {numeros[0].text}")
                else:
                    warn("Nenhum RPS disponível retornado (pode ser normal em homologação)")
            else:
                warn("Resposta sem XML parseável")
    except Exception as e:
        fail(f"Erro ao consultar RPS: {e}")

    # Test 3: Emitir nota de teste
    print("\n  --- Teste 3: Emitir NFS-e de Teste ---")
    print("       [PULADO - emissão requer confirmação manual para evitar consumo de RPS]")
    warn("Para emitir uma nota de teste ABRASF, execute manualmente via MCP ou API")

    return True


# ---------------------------------------------------------------------------
# SEFIN Nacional Production Restricted Tests
# ---------------------------------------------------------------------------

def test_sefin_homologation():
    divider("SEFIN Nacional - Produção Restrita (Homologação)")

    load_env()
    cert_path = os.getenv("SEFIN_CERTIFICATE_PATH") or os.getenv("NFSE_CERTIFICATE_PATH", "")
    cert_password = os.getenv("SEFIN_CERTIFICATE_PASSWORD") or os.getenv("NFSE_CERTIFICATE_PASSWORD", "")
    cnpj = os.getenv("NFSE_PROVIDER_CNPJ", "")
    razao = os.getenv("NFSE_PROVIDER_RAZAO_SOCIAL", "")

    if not cert_path or not Path(cert_path).exists():
        fail(f"Certificado não encontrado: {cert_path}")
        return False

    if not cnpj or cnpj == "00000000000000":
        fail("CNPJ do prestador não configurado no .env")
        return False

    ok(f"Certificado encontrado: {cert_path}")
    ok(f"CNPJ Prestador: {cnpj}")

    sefin_config = SefinNacionalConfig(
        environment="production_restricted",
        base_url="https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional",
        certificate_path=cert_path,
        certificate_password=cert_password,
        timeout=60,
        max_retries=3,
        debug=False,
        skip_xsd_validation=True,
    )

    try:
        cert = Certificate(sefin_config.certificate_path, sefin_config.certificate_password)
        ok("Certificado carregado com sucesso")
    except Exception as e:
        fail(f"Erro ao carregar certificado: {e}")
        return False

    provider = SefinNacionalProvider(sefin_config, cert)
    ok("Provider SEFIN Nacional inicializado")

    # Test 1: Consultar convênio Brasília
    print("\n  --- Teste 1: Consultar Convênio (Brasília/5300108) ---")
    try:
        result = provider.get_agreement_by_municipality("5300108")
        if result.conveniado:
            ok(f"Brasília é conveniada. Adesão: {result.data_adesao or 'N/A'}")
        else:
            warn("Brasília NÃO está conveniada no SEFIN Nacional")
    except Exception as e:
        fail(f"Erro ao consultar convênio: {e}")
        return False

    # Test 2: Consultar parâmetros de serviço
    print("\n  --- Teste 2: Consultar Parâmetros do Serviço 1.07 ---")
    try:
        params = provider.get_service_parameters("5300108", "1.07")
        ok(f"Parâmetros obtidos: {len(params.aliquotas)} alíquota(s)")
        for a in params.aliquotas:
            print(f"       - {a}")
    except Exception as e:
        fail(f"Erro ao consultar parâmetros: {e}")

    # Test 3: Consultar retenções e benefícios
    print("\n  --- Teste 3: Consultar Retenções/Benefícios ---")
    try:
        ret = provider.get_contributor_retentions("5300108", cnpj)
        ok(f"Retenções: {len(ret.retencoes)} registro(s)")
    except Exception as e:
        warn(f"Erro ao consultar retenções: {e}")

    try:
        ben = provider.get_contributor_benefits("5300108", cnpj)
        ok(f"Benefícios: {len(ben.beneficios)} registro(s)")
    except Exception as e:
        warn(f"Erro ao consultar benefícios: {e}")

    # Test 4: Emitir nota de teste
    print("\n  --- Teste 4: Emitir NFS-e de Teste ---")
    try:
        # Setup application service
        config = Config(
            environment="homologation",
            certificate_path=cert_path,
            certificate_password=cert_password,
            provider=ProviderConfig(
                cnpj=cnpj,
                im=os.getenv("NFSE_PROVIDER_IM", ""),
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
            rps_serie="8",
            webservice_url="",
            data_dir=Path(__file__).parent.parent / "data",
        )

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

        # Use a test client (the provider's own CNPJ as tomador for simplicity)
        cmd = IssueInvoiceCommand(
            client_document=cnpj,
            valor="1.00",
            discriminacao="Servico de teste em ambiente de homologacao - nfse-mcp",
            competencia=date.today().replace(day=1).isoformat(),
            codigo_servico="1.07",
            aliquota="2.00",
            codigo_municipio="5300108",
        )

        result = sefin_service.issue_invoice(cmd)
        if result.success:
            ok(f"NFS-e emitida com sucesso!")
            print(f"       Chave de Acesso: {result.chave_acesso}")
            print(f"       idDPS: {result.id_dps}")
            print(f"       Data/Hora: {result.data_hora_processamento or 'N/A'}")

            # Test 5: Query by access key
            print("\n  --- Teste 5: Consultar NFS-e pela Chave de Acesso ---")
            query_result = sefin_service.query_by_access_key(result.chave_acesso)
            if query_result.success:
                ok("Consulta bem-sucedida")
                print(f"       Status: {query_result.status or 'N/A'}")
                print(f"       XML length: {len(query_result.xml_nfse or '')} chars")
            else:
                warn("Consulta retornou erro (pode ser normal em Produção Restrita)")
        else:
            fail(f"Emissão falhou: {result.errors}")
            return False

    except Exception as e:
        fail(f"Erro ao emitir NFS-e de teste: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Testes de homologação nfse-mcp")
    parser.add_argument("--abrasf", action="store_true", help="Testar ABRASF homologação")
    parser.add_argument("--sefin", action="store_true", help="Testar SEFIN Produção Restrita")
    parser.add_argument("--all", action="store_true", help="Testar ambos")
    args = parser.parse_args()

    if not any([args.abrasf, args.sefin, args.all]):
        args.all = True

    results = []

    if args.abrasf or args.all:
        results.append(("ABRASF", test_abrasf_homologation()))

    if args.sefin or args.all:
        results.append(("SEFIN", test_sefin_homologation()))

    divider("RESUMO")
    for name, success in results:
        status = "✅ SUCESSO" if success else "❌ FALHA"
        print(f"  {name}: {status}")

    sys.exit(0 if all(r[1] for r in results) else 1)


if __name__ == "__main__":
    main()
