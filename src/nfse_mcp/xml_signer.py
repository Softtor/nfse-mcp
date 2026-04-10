from lxml import etree
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import base64
import hashlib

from nfse_mcp.certificate import Certificate

DS_NS = "http://www.w3.org/2000/09/xmldsig#"
C14N_ALG = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
SIG_ALG = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
DIGEST_ALG = "http://www.w3.org/2000/09/xmldsig#sha1"
TRANSFORM_ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
TRANSFORM_C14N = C14N_ALG


class XmlSigner:
    """Signs XML documents for NFS-e ABRASF 2.04 using manual XML-DSig (SHA1 required by webservice)."""

    def __init__(self, cert: Certificate):
        self.cert = cert

    def sign_xml(self, xml_string: str, reference_uri: str = "") -> str:
        root = etree.fromstring(xml_string.encode("utf-8"))

        # Remove existing Signature
        for sig in root.findall(f"{{{DS_NS}}}Signature"):
            sig.getparent().remove(sig)
        for sig in root.findall(f".//{{{DS_NS}}}Signature"):
            sig.getparent().remove(sig)

        # 1. Canonicalize the document (without Signature) for DigestValue
        c14n_xml = etree.tostring(root, method="c14n", exclusive=False)
        digest_value = base64.b64encode(hashlib.sha1(c14n_xml).digest()).decode()

        # 2. Build SignedInfo
        signed_info = self._build_signed_info(digest_value, reference_uri)

        # 3. Canonicalize SignedInfo and sign it
        signed_info_c14n = etree.tostring(signed_info, method="c14n", exclusive=False)
        signature_bytes = self.cert.private_key.sign(
            signed_info_c14n,
            padding.PKCS1v15(),
            hashes.SHA1(),
        )
        signature_value = base64.b64encode(signature_bytes).decode()

        # 4. Build complete Signature element
        sig_element = self._build_signature(signed_info, signature_value)

        # 5. Append Signature to root
        root.append(sig_element)

        return etree.tostring(root, encoding="unicode", xml_declaration=False)

    def _build_signed_info(self, digest_value: str, reference_uri: str) -> etree._Element:
        si = etree.Element(f"{{{DS_NS}}}SignedInfo", nsmap={"ds": DS_NS})
        si.tag = f"{{{DS_NS}}}SignedInfo"

        c14n = etree.SubElement(si, f"{{{DS_NS}}}CanonicalizationMethod")
        c14n.set("Algorithm", C14N_ALG)

        sig_method = etree.SubElement(si, f"{{{DS_NS}}}SignatureMethod")
        sig_method.set("Algorithm", SIG_ALG)

        ref = etree.SubElement(si, f"{{{DS_NS}}}Reference")
        ref.set("URI", reference_uri)

        transforms = etree.SubElement(ref, f"{{{DS_NS}}}Transforms")
        t1 = etree.SubElement(transforms, f"{{{DS_NS}}}Transform")
        t1.set("Algorithm", TRANSFORM_ENVELOPED)
        t2 = etree.SubElement(transforms, f"{{{DS_NS}}}Transform")
        t2.set("Algorithm", TRANSFORM_C14N)

        dm = etree.SubElement(ref, f"{{{DS_NS}}}DigestMethod")
        dm.set("Algorithm", DIGEST_ALG)

        dv = etree.SubElement(ref, f"{{{DS_NS}}}DigestValue")
        dv.text = digest_value

        return si

    def _build_signature(self, signed_info: etree._Element, signature_value: str) -> etree._Element:
        sig = etree.Element(f"{{{DS_NS}}}Signature", nsmap={"ds": DS_NS})
        # Re-tag without prefix for clean output
        sig.tag = f"{{{DS_NS}}}Signature"

        sig.append(signed_info)

        sv = etree.SubElement(sig, f"{{{DS_NS}}}SignatureValue")
        sv.text = signature_value

        ki = etree.SubElement(sig, f"{{{DS_NS}}}KeyInfo")
        x509 = etree.SubElement(ki, f"{{{DS_NS}}}X509Data")
        x509cert = etree.SubElement(x509, f"{{{DS_NS}}}X509Certificate")
        x509cert.text = self.cert.certificate_base64

        return sig

    def sign_rps(self, rps_xml: str) -> str:
        return self.sign_xml(rps_xml)

    def sign_lote(self, lote_xml: str, lote_id: str = "lote01") -> str:
        return self.sign_xml(lote_xml, reference_uri=f"#{lote_id}")
