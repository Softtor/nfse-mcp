"""Assinatura com Reference URI="#Id" (exigida pelo XSD oficial da DPS) deve resumir o elemento referenciado."""

import base64
import hashlib

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from lxml import etree

from nfse_mcp.xml_signer import XmlSigner

DS = "{http://www.w3.org/2000/09/xmldsig#}"
DPS = (
    '<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">'
    '<infDPS Id="DPS1"><nDPS>1</nDPS><prest><CNPJ>1</CNPJ></prest></infDPS></DPS>'
)


class FakeCert:
    def __init__(self):
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.certificate_base64 = "Q0VSVA=="


@pytest.mark.parametrize("sha256", [False, True])
def test_reference_por_id_resume_o_elemento_e_assinatura_confere(sha256):
    cert = FakeCert()
    signed = XmlSigner(cert, use_sha256=sha256).sign_xml(DPS, reference_uri="#DPS1")
    root = etree.fromstring(signed.encode())
    inf = root.find("{http://www.sped.fazenda.gov.br/nfse}infDPS")
    algo = hashlib.sha256 if sha256 else hashlib.sha1
    # c14n do libxml2 num trecho dentro do documento sai com xmlns="" indevido; o fisco (.NET) não.
    canonical = etree.tostring(etree.fromstring(etree.tostring(inf)), method="c14n")
    assert b'xmlns=""' not in canonical
    expected = base64.b64encode(algo(canonical).digest()).decode()
    assert root.find(f".//{DS}DigestValue").text == expected

    # lxml põe xmlns="" indevido ao canonizar um trecho que redefine o namespace padrão; isola o SignedInfo.
    signed_info = etree.fromstring(etree.tostring(root.find(f".//{DS}SignedInfo")))
    cert.private_key.public_key().verify(
        base64.b64decode(root.find(f".//{DS}SignatureValue").text),
        etree.tostring(signed_info, method="c14n"),
        padding.PKCS1v15(),
        hashes.SHA256() if sha256 else hashes.SHA1(),
    )
    assert "\n" not in signed.split("?>", 1)[1].lstrip("\n")  # fisco recusa caracteres de edição entre as tags


def test_reference_para_id_inexistente_falha():
    with pytest.raises(ValueError, match="nao encontrado"):
        XmlSigner(FakeCert()).sign_xml(DPS, reference_uri="#NAOEXISTE")
