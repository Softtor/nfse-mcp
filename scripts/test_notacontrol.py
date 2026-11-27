"""Smoke test do webservice NFS-e padrão nacional (ISS.net / Nota Control).

Precisa de rede e do cadastro no ambiente de homologação:
    http://www.issnetonline.com.br/homologacao/online/Login/Login.aspx
    -> "Solicitação de Cadastro Ambiente de Homologação"

Uso:
    uv run python scripts/test_notacontrol.py [homologation|production]

Parâmetros do ambiente de homologação (chamado Nota Control #0540302):
    série da DPS = 8 | município = 5002704 (Campo Grande/MS)
    cTribMun: 7->3%  6->5%  4->2,5%  1->2%
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nfse_mcp.certificate import Certificate  # noqa: E402
from nfse_mcp.config import load_config  # noqa: E402
from nfse_mcp.notacontrol import xml_builder as xb  # noqa: E402
from nfse_mcp.notacontrol.soap_client import (  # noqa: E402
    WEBSERVICE_URLS,
    NotaControlSoapClient,
)


def divider(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main() -> int:
    env = sys.argv[1] if len(sys.argv) > 1 else "homologation"
    cfg = load_config()
    cert = Certificate(cfg.certificate_path, cfg.certificate_password)
    soap = NotaControlSoapClient(cert, environment=env)
    header = xb.build_cabecalho()

    print(f"ambiente : {env}")
    print(f"url      : {WEBSERVICE_URLS[env]}")
    print(f"CNPJ     : {cfg.provider.cnpj}")
    print(f"IM       : {cfg.provider.im}")

    ok = True

    divider("1. ConsultarDadosCadastrais  (prova de vida do transporte)")
    data = xb.build_consultar_dados_cadastrais_envio(cfg)
    print("envio:", data)
    resp = soap.consultar_dados_cadastrais(header, data)
    print(f"HTTP {resp.http_status}")
    print("resposta:", resp.raw_xml[:1500])
    if resp.has_errors():
        ok = False
        for e in resp.get_errors():
            print("  ERRO:", e)
    else:
        print("  OK — transporte, mTLS, envelope e cabeçalho 1.01 validados")

    divider("2. ConsultarNfseServicoPrestado  (a consulta que quebrou no ABRASF)")
    data = xb.build_consultar_nfse_servico_prestado_envio(
        cfg, "2026-07-01", "2026-07-31", pagina=1
    )
    resp = soap.consultar_nfse_servico_prestado(header, data)
    print(f"HTTP {resp.http_status}")
    print("resposta:", resp.raw_xml[:2000])
    for e in resp.get_errors():
        print("  ERRO:", e)

    soap.cleanup()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
