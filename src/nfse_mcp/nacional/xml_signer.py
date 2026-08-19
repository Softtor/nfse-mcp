import base64
import hashlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from lxml import etree

from nfse_mcp.certificate import Certificate
from nfse_mcp.nacional.constants import DS_NS

C14N_ALG = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
SIG_ALG = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
DIGEST_ALG = "http://www.w3.org/2000/09/xmldsig#sha1"
TRANSFORM_ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"


class NacionalXmlSigner:
    def __init__(self, cert: Certificate):
        self.cert = cert

    def sign_by_id(self, xml_string: str, element_local_name: str) -> str:
        root = etree.fromstring(xml_string.encode("utf-8"))
        for sig in root.findall(f".//{{{DS_NS}}}Signature"):
            sig.getparent().remove(sig)

        target = None
        for el in root.iter():
            if el.tag.endswith(f"}}{element_local_name}") or el.tag == element_local_name:
                if el.get("Id"):
                    target = el
                    break
        if target is None:
            raise ValueError(f"Elemento {element_local_name} com atributo Id nao encontrado")

        element_id = target.get("Id")
        c14n_xml = etree.tostring(target, method="c14n", exclusive=False)
        digest_value = base64.b64encode(hashlib.sha1(c14n_xml).digest()).decode()
        signed_info = self._build_signed_info(digest_value, f"#{element_id}")
        signed_info_c14n = etree.tostring(signed_info, method="c14n", exclusive=False)
        signature_bytes = self.cert.private_key.sign(
            signed_info_c14n,
            padding.PKCS1v15(),
            hashes.SHA1(),
        )
        signature_value = base64.b64encode(signature_bytes).decode()
        sig_element = self._build_signature(signed_info, signature_value)
        parent = target.getparent()
        if parent is None:
            root.append(sig_element)
        else:
            parent.append(sig_element)
        return etree.tostring(root, encoding="unicode", xml_declaration=False)

    def _build_signed_info(self, digest_value: str, reference_uri: str) -> etree._Element:
        si = etree.Element(f"{{{DS_NS}}}SignedInfo")
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
        t2.set("Algorithm", C14N_ALG)
        dm = etree.SubElement(ref, f"{{{DS_NS}}}DigestMethod")
        dm.set("Algorithm", DIGEST_ALG)
        dv = etree.SubElement(ref, f"{{{DS_NS}}}DigestValue")
        dv.text = digest_value
        return si

    def _build_signature(self, signed_info: etree._Element, signature_value: str) -> etree._Element:
        sig = etree.Element(f"{{{DS_NS}}}Signature")
        sig.append(signed_info)
        sv = etree.SubElement(sig, f"{{{DS_NS}}}SignatureValue")
        sv.text = signature_value
        ki = etree.SubElement(sig, f"{{{DS_NS}}}KeyInfo")
        x509 = etree.SubElement(ki, f"{{{DS_NS}}}X509Data")
        x509cert = etree.SubElement(x509, f"{{{DS_NS}}}X509Certificate")
        x509cert.text = self.cert.certificate_base64
        return sig
