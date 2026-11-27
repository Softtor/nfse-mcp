"""Cliente SOAP do padrão nacional NFS-e (ISS.net / Nota Control).

O mecanismo de transporte é o mesmo do ABRASF 2.04 — envelope montado à mão,
mTLS com PEM/KEY temporários — porque o WSDL confirma que as *parts* continuam
sendo ``nfseCabecMsg`` e ``nfseDadosMsg``. O que muda:

- namespace do método: ``http://www.sped.fazenda.gov.br/nfse``
- SOAPAction: ``http://www.sped.fazenda.gov.br/nfse/{Metodo}``
- ``verify=True``: ao contrário de ``df.issnetonline.com.br``, os hosts do
  padrão nacional servem cadeia TLS válida (verificado em 03/08/2026)

ponytail: o transporte é copiado de `nfse_mcp.abrasf.soap_client` de propósito.
Unificar exigiria ramificar o parser de resposta dentro do caminho que ainda
emite nota em produção. Reavaliar quando o ABRASF for aposentado.
"""

import os
import re
import tempfile
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

import requests
from lxml import etree

from nfse_mcp.certificate import Certificate


NS = "http://www.sped.fazenda.gov.br/nfse"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"

# O <soap:address> do WSDL aponta para um endereço genérico
# (https://nfse.issnetonline.com.br/nfse.asmx) que não é o de integração.
# Estas são as URLs informadas pela Nota Control no chamado #0540302.
WEBSERVICE_URLS = {
    "production": "https://nfse.fazenda.df.gov.br/wsnfsenacional/nfse.asmx",
    "homologation": "https://nfse.issnetonline.com.br/wsnfsenacional/homologacao/nfse.asmx",
}

_XML_DECL = re.compile(r"<\?xml[^?]*\?>\s*")


class NacionalResponse:
    """Resposta de uma chamada ao webservice nacional."""

    def __init__(self, raw_xml: str, method: str, http_status: int = 0):
        self.raw_xml = raw_xml
        self.method = method
        self.http_status = http_status

    def _root(self) -> Optional[etree._Element]:
        try:
            return etree.fromstring(self.raw_xml.encode("utf-8"))
        except etree.XMLSyntaxError:
            return None

    def get_errors(self) -> list[dict]:
        """Erros normalizados.

        O XSD modela a resposta como choice(<conteúdo> | ListaMensagemRetorno),
        com tcMensagemRetorno = Codigo + Mensagem + Correcao?.
        SOAP Faults são tratados à parte.
        """
        root = self._root()
        if root is None:
            return [{"Codigo": "PARSE", "Mensagem": self.raw_xml[:500]}]

        # `.//` não casa com a própria raiz, e o Fault chega desembrulhado.
        fault = (
            root
            if root.tag == f"{{{SOAP_NS}}}Fault"
            else root.find(f".//{{{SOAP_NS}}}Fault")
        )
        if fault is not None:
            code = fault.findtext("faultcode") or fault.findtext(f"{{{SOAP_NS}}}faultcode")
            msg = fault.findtext("faultstring") or fault.findtext(f"{{{SOAP_NS}}}faultstring")
            return [{"Codigo": code or "SOAP-Fault", "Mensagem": msg or "erro nao detalhado"}]

        errors = []
        for msg in root.iter(f"{{{NS}}}MensagemRetorno"):
            errors.append(
                {
                    "Codigo": msg.findtext(f"{{{NS}}}Codigo") or "",
                    "Mensagem": msg.findtext(f"{{{NS}}}Mensagem") or "",
                    "Correcao": msg.findtext(f"{{{NS}}}Correcao") or "",
                }
            )
        return errors

    def has_errors(self) -> bool:
        return bool(self.get_errors())

    def __repr__(self) -> str:
        return f"<NacionalResponse {self.method} http={self.http_status} len={len(self.raw_xml)}>"


def build_envelope(method: str, header_xml: str, data_xml: str) -> str:
    """Monta o envelope SOAP. Função pura — testável sem rede.

    Três detalhes que o servidor exige, todos descobertos empiricamente contra
    homologação (03/08/2026) e cada um capaz de derrubar a chamada sozinho:

    1. ``nfseCabecMsg``/``nfseDadosMsg`` vão **fora de namespace** (``xmlns=""``).
       O WSDL não declara ``elementFormDefault``, então o default é
       *unqualified*. Sem isso o servidor responde E183+E160 ("cabeçalho fora do
       padrão" + "arquivo em desacordo com o XML Schema") para **qualquer**
       conteúdo, inclusive vazio — ele nunca chega a ler o payload.
    2. O elemento do método precisa do ``xmlns`` **default**; declarar o
       namespace por prefixo, ainda que equivalente em XML, também dá E183.
    3. O conteúdo vai escapado por entidades. CDATA é rejeitado.

    A declaração XML é removida dos payloads — o ISS.net a rejeita ali dentro.
    """
    clean_data = _XML_DECL.sub("", data_xml)
    clean_header = _XML_DECL.sub("", header_xml)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<soap:Envelope xmlns:soap="{SOAP_NS}">\n'
        "  <soap:Body>\n"
        f'    <{method} xmlns="{NS}">\n'
        f'      <nfseCabecMsg xmlns="">{xml_escape(clean_header)}</nfseCabecMsg>\n'
        f'      <nfseDadosMsg xmlns="">{xml_escape(clean_data)}</nfseDadosMsg>\n'
        f"    </{method}>\n"
        "  </soap:Body>\n"
        "</soap:Envelope>"
    )


def unwrap_output(response_bytes: bytes, method: str) -> str:
    """Extrai o XML útil de dentro de ``soap:Body > {Metodo}Response > outputXML``.

    O WSDL tipa ``outputXML`` como ``xsd:string``, mas servidores .asmx às vezes
    devolvem o conteúdo como elementos embutidos em vez de texto escapado.
    Tratamos os dois casos. SOAP Fault e corpos ilegíveis voltam crus, para o
    chamador decidir — nunca inventar formato de erro.
    """
    try:
        tree = etree.fromstring(response_bytes)
    except etree.XMLSyntaxError:
        return response_bytes.decode("utf-8", errors="replace")

    body = tree.find(f".//{{{SOAP_NS}}}Body")
    if body is None or len(body) == 0:
        return etree.tostring(tree, encoding="unicode")

    method_resp = body[0]

    # SOAP Fault: devolve como veio, get_errors() sabe lê-lo.
    if method_resp.tag == f"{{{SOAP_NS}}}Fault":
        return etree.tostring(method_resp, encoding="unicode")

    for out in method_resp.iter():
        if etree.QName(out).localname != "outputXML":
            continue
        if len(out):  # conteúdo veio como elementos
            return etree.tostring(out[0], encoding="unicode")
        if out.text and out.text.strip():  # conteúdo veio escapado
            return out.text.strip()

    return etree.tostring(method_resp, encoding="unicode")


class NotaControlSoapClient:
    """Cliente SOAP do webservice NFS-e padrão nacional."""

    def __init__(
        self,
        cert: Certificate,
        environment: str = "homologation",
        url: Optional[str] = None,
        verify: bool = True,
        timeout: int = 60,
    ):
        self.cert = cert
        self.url = url or WEBSERVICE_URLS.get(
            environment, WEBSERVICE_URLS["homologation"]
        )
        self.verify = verify
        self.timeout = timeout
        self._cert_files: Optional[tuple[str, str]] = None

    def _get_cert_files(self) -> tuple[str, str]:
        if self._cert_files is None:
            cert_fd, cert_path = tempfile.mkstemp(suffix=".pem")
            key_fd, key_path = tempfile.mkstemp(suffix=".key")
            os.write(cert_fd, self.cert.certificate_pem)
            os.close(cert_fd)
            os.write(key_fd, self.cert.private_key_pem)
            os.close(key_fd)
            self._cert_files = (cert_path, key_path)
        return self._cert_files

    def call(self, method: str, header_xml: str, data_xml: str) -> NacionalResponse:
        envelope = build_envelope(method, header_xml, data_xml)
        cert_path, key_path = self._get_cert_files()

        response = requests.post(
            self.url,
            data=envelope.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f"{NS}/{method}",
            },
            cert=(cert_path, key_path),
            verify=self.verify,
            timeout=self.timeout,
        )
        return NacionalResponse(
            raw_xml=unwrap_output(response.content, method),
            method=method,
            http_status=response.status_code,
        )

    # --- operações (nomes conforme o WSDL, que diverge do manual em dois casos)

    def gerar_nfse(self, header: str, data: str) -> NacionalResponse:
        return self.call("GerarNfse", header, data)

    def cancelar_nfse(self, header: str, data: str) -> NacionalResponse:
        return self.call("CancelarNfse", header, data)

    def consultar_dados_cadastrais(self, header: str, data: str) -> NacionalResponse:
        return self.call("ConsultarDadosCadastrais", header, data)

    def consultar_nfse_servico_prestado(self, header: str, data: str) -> NacionalResponse:
        return self.call("ConsultarNfseServicoPrestado", header, data)

    def consultar_url_nfse(self, header: str, data: str) -> NacionalResponse:
        return self.call("ConsultarUrlNfse", header, data)

    def consultar_dps_disponivel(self, header: str, data: str) -> NacionalResponse:
        return self.call("ConsultarDpsDisponivel", header, data)

    def consultar_nfse_dps(self, header: str, data: str) -> NacionalResponse:
        return self.call("ConsultarNfseDps", header, data)

    def validar_xml(self, header: str, data: str) -> NacionalResponse:
        """Operação presente no WSDL mas ausente do manual — valida server-side."""
        return self.call("ValidarXml", header, data)

    def cleanup(self) -> None:
        if self._cert_files:
            for path in self._cert_files:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            self._cert_files = None
