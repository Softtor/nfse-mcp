from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
import pytest

from nfse_mcp.models import Client
from nfse_mcp.nacional.config import NacionalConfig
from nfse_mcp.nacional.constants import MUNICIPIO_IBGE_DF
from nfse_mcp.nacional.tools import reset_nacional_state


@pytest.fixture(autouse=True)
def _reset_nacional():
    reset_nacional_state()
    yield
    reset_nacional_state()


def make_pfx(path: Path, password: str = "test") -> Path:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Teste NFSe")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    blob = pkcs12.serialize_key_and_certificates(
        name=b"test",
        key=key,
        cert=cert,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
    )
    path.write_bytes(blob)
    return path


@pytest.fixture
def pfx_path(tmp_path: Path) -> Path:
    return make_pfx(tmp_path / "cert.p12")


@pytest.fixture
def nacional_cfg(tmp_path: Path, pfx_path: Path) -> NacionalConfig:
    return NacionalConfig(
        enabled=True,
        environment="homologation",
        webservice_url="https://nfse.issnetonline.com.br/wsnfsenacional/homologacao/nfse.asmx",
        wsdl_url="https://nfse.issnetonline.com.br/wsnfsenacional/homologacao/nfse.asmx?wsdl",
        certificate_path=str(pfx_path),
        certificate_password="test",
        provider_cnpj="33779923000142",
        provider_im="0791927900180",
        provider_razao_social="SOFTTOR SOLUCOES TRANSFORMADORAS LTDA",
        optante_simples=True,
        c_trib_nac="010701",
        c_trib_mun="107",
        aliquota="2.00",
        municipio_ibge=MUNICIPIO_IBGE_DF,
        dps_serie="1",
        layout_version="1.00",
        data_dir=tmp_path,
    )


@pytest.fixture
def tomador() -> Client:
    return Client(
        id="1",
        document="11222333000181",
        document_type="cnpj",
        razao_social="TOMADOR TESTE LTDA",
        endereco="SQN 1",
        numero="1",
        bairro="Asa Norte",
        codigo_municipio="5300108",
        uf="DF",
        cep="70000000",
    )
