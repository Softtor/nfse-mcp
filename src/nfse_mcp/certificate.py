from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption
from cryptography.x509 import Certificate as X509Certificate
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from pathlib import Path
import base64


class Certificate:
    """Handles PFX/PKCS12 certificate for XML digital signing."""

    def __init__(self, pfx_path: str, password: str):
        self._pfx_path = Path(pfx_path)
        if not self._pfx_path.exists():
            raise FileNotFoundError(f"Certificate file not found: {pfx_path}")

        pfx_data = self._pfx_path.read_bytes()
        private_key, certificate, chain = pkcs12.load_key_and_certificates(
            pfx_data, password.encode("utf-8")
        )

        if private_key is None or certificate is None:
            raise ValueError("Could not extract key/certificate from PFX file")

        self.private_key: RSAPrivateKey = private_key
        self.certificate: X509Certificate = certificate
        self.chain = chain or []

    @property
    def private_key_pem(self) -> bytes:
        return self.private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        )

    @property
    def certificate_pem(self) -> bytes:
        return self.certificate.public_bytes(Encoding.PEM)

    @property
    def certificate_der(self) -> bytes:
        return self.certificate.public_bytes(Encoding.DER)

    @property
    def certificate_base64(self) -> str:
        """X509 certificate in base64 (without PEM headers), for XML Signature."""
        pem = self.certificate_pem.decode("utf-8")
        # Remove PEM headers/footers and newlines
        b64 = pem.replace("-----BEGIN CERTIFICATE-----", "")
        b64 = b64.replace("-----END CERTIFICATE-----", "")
        b64 = b64.replace("\n", "").strip()
        return b64

    @property
    def cnpj(self) -> str | None:
        """Extract CNPJ from certificate subject if available."""
        for attr in self.certificate.subject:
            if "2.16.76.1.3.3" in attr.oid.dotted_string:
                return attr.value
        return None
