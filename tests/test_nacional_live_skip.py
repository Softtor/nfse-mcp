import os

import pytest
import requests

from nfse_mcp.nacional.constants import HOMOLOG_URL, HOMOLOG_WSDL_URL


@pytest.mark.skipif(
    not os.getenv("NFSE_NACIONAL_LIVE"),
    reason=(
        "Chamada live de homologacao exige certificado A1 ICP-Brasil do contribuinte "
        "(mTLS). Sem A1 o WSDL/asmx responde 403. Nao roda no CI."
    ),
)
def test_live_homolog_wsdl_with_client_cert():
    cert_path = os.getenv("NFSE_CERTIFICATE_PATH")
    password = os.getenv("NFSE_CERTIFICATE_PASSWORD")
    if not cert_path or not password:
        pytest.skip("NFSE_CERTIFICATE_PATH/PASSWORD ausentes")
    pytest.skip("Live homolog depende de PEM extraido do A1; use o adapter localmente")


def test_homolog_wsdl_forbidden_without_client_cert():
    try:
        resp = requests.get(HOMOLOG_WSDL_URL, timeout=20)
        resp_asmx = requests.get(HOMOLOG_URL, timeout=20)
    except requests.RequestException as exc:
        pytest.skip(f"Sem acesso de rede ao homolog ISS.net: {exc}")
    assert resp.status_code == 403
    assert resp_asmx.status_code == 403
