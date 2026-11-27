from lxml import etree
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import base64
import hashlib

from nfse_mcp.certificate import Certificate

DS_NS = "http://www.w3.org/2000/09/xmldsig#"
C14N_ALG = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"

# SHA-1 (legacy — required by ISS.net Brasilia)
SIG_ALG_SHA1 = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
DIGEST_ALG_SHA1 = "http://www.w3.org/2000/09/xmldsig#sha1"

# SHA-256 (SEFIN Nacional)
SIG_ALG_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
DIGEST_ALG_SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"

TRANSFORM_ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
TRANSFORM_C14N = C14N_ALG


def _ds_element(tag: str) -> str:
    """Return a tag in the XML-DSig namespace for searching."""
    return f"{{{DS_NS}}}{tag}"


class XmlSigner:
    """Signs XML documents using manual XML-DSig.

    Supports both SHA-1 (required by ISS.net Brasilia / ABRASF 2.04)
    and SHA-256 (used by SEFIN Nacional).
    """

    def __init__(self, cert: Certificate, use_sha256: bool = False):
        self.cert = cert
        self.use_sha256 = use_sha256
        self._sig_alg = SIG_ALG_SHA256 if use_sha256 else SIG_ALG_SHA1
        self._digest_alg = DIGEST_ALG_SHA256 if use_sha256 else DIGEST_ALG_SHA1
        self._hash_alg = hashes.SHA256() if use_sha256 else hashes.SHA1()

    def sign_xml(self, xml_string: str, reference_uri: str = "") -> str:
        root = etree.fromstring(xml_string.encode("utf-8"))

        # Remove existing Signature
        for sig in root.findall(_ds_element("Signature")):
            sig.getparent().remove(sig)
        for sig in root.findall(f".//{_ds_element('Signature')}"):
            sig.getparent().remove(sig)

        # 1. Canonicalize what the Reference points to: the whole document (URI="") or the element with that Id
        target = root
        if reference_uri.startswith("#"):
            found = root.xpath("//*[@Id=$id]", id=reference_uri[1:])
            if not found:
                raise ValueError(f"Elemento com Id {reference_uri[1:]} nao encontrado para assinar")
            # shortcut: c14n do libxml2 num trecho interno sai com xmlns="" indevido; canoniza uma cópia isolada.
            # Vale enquanto o elemento só depende do namespace padrão (caso da DPS); outros prefixos herdados se perdem.
            target = etree.fromstring(etree.tostring(found[0]))
        c14n_xml = etree.tostring(target, method="c14n", exclusive=False)
        digest_value = base64.b64encode(
            hashlib.sha256(c14n_xml).digest() if self.use_sha256 else hashlib.sha1(c14n_xml).digest()
        ).decode()

        # 2. Build SignedInfo as XML string for correct namespace handling
        # Compacto (sem quebra de linha/recuo): o fisco recusa caracteres de edição entre as tags.
        signed_info_xml = (
            f'<SignedInfo xmlns="{DS_NS}">'
            f'<CanonicalizationMethod Algorithm="{C14N_ALG}"/>'
            f'<SignatureMethod Algorithm="{self._sig_alg}"/>'
            f'<Reference URI="{reference_uri}">'
            f'<Transforms><Transform Algorithm="{TRANSFORM_ENVELOPED}"/><Transform Algorithm="{TRANSFORM_C14N}"/></Transforms>'
            f'<DigestMethod Algorithm="{self._digest_alg}"/>'
            f'<DigestValue>{digest_value}</DigestValue>'
            f'</Reference></SignedInfo>'
        )
        signed_info = etree.fromstring(signed_info_xml.encode("utf-8"))

        # 3. Canonicalize SignedInfo with exclusive C14N and sign it
        signed_info_c14n = etree.tostring(signed_info, method="c14n", exclusive=True)
        signature_bytes = self.cert.private_key.sign(
            signed_info_c14n,
            padding.PKCS1v15(),
            self._hash_alg,
        )
        signature_value = base64.b64encode(signature_bytes).decode()

        # 4. Build complete Signature element as XML string
        signature_xml = (
            f'<Signature xmlns="{DS_NS}">{etree.tostring(signed_info, encoding="unicode")}'
            f'<SignatureValue>{signature_value}</SignatureValue>'
            f'<KeyInfo><X509Data><X509Certificate>{self.cert.certificate_base64}</X509Certificate></X509Data></KeyInfo>'
            f'</Signature>'
        )
        sig_element = etree.fromstring(signature_xml.encode("utf-8"))

        # 5. Append Signature to root
        root.append(sig_element)

        # Always include UTF-8 XML declaration for SEFIN Nacional compatibility
        return etree.tostring(root, encoding="UTF-8", xml_declaration=True).decode("utf-8")

    def sign_rps(self, rps_xml: str) -> str:
        return self.sign_xml(rps_xml)

    def sign_lote(self, lote_xml: str, lote_id: str = "lote01") -> str:
        return self.sign_xml(lote_xml, reference_uri=f"#{lote_id}")
