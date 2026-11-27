from lxml import etree
from nfse_mcp.certificate import Certificate
from nfse_mcp.config import Config
import json
import tempfile
import os


class NfseResponse:
    """Parsed response from the NFS-e webservice."""

    def __init__(self, raw_xml: str, method: str):
        self.raw_xml = raw_xml
        self.method = method
        self._parsed = None

    @property
    def xml_tree(self) -> etree._Element | None:
        if self._parsed is None and self.raw_xml:
            try:
                self._parsed = etree.fromstring(self.raw_xml.encode("utf-8") if isinstance(self.raw_xml, str) else self.raw_xml)
            except Exception:
                pass
        return self._parsed

    def has_errors(self) -> bool:
        if self.xml_tree is None:
            return True
        # Check for SOAP Fault
        for el in self.xml_tree.iter():
            if el.tag == "{http://schemas.xmlsoap.org/soap/envelope/}Fault":
                return True
        # Check for ListaMensagemRetorno with error codes
        errors = self.xml_tree.findall(".//{http://www.abrasf.org.br/nfse.xsd}MensagemRetorno")
        return len(errors) > 0

    def get_errors(self) -> list[dict]:
        if self.xml_tree is None:
            return [{"Codigo": "PARSE_ERROR", "Mensagem": "Could not parse response"}]
        errors = []
        # Check for SOAP Fault first
        for fault in self.xml_tree.iter():
            if fault.tag == "{http://schemas.xmlsoap.org/soap/envelope/}Fault":
                faultcode = fault.find("faultcode")
                faultstring = fault.find("faultstring")
                detail = fault.find("detail")
                error = {
                    "Codigo": faultcode.text if faultcode is not None else "SOAP_FAULT",
                    "Mensagem": faultstring.text if faultstring is not None else "Unknown SOAP error",
                }
                if detail is not None and detail.text:
                    error["Correcao"] = detail.text
                errors.append(error)
                return errors
        ns = "{http://www.abrasf.org.br/nfse.xsd}"
        for msg in self.xml_tree.findall(f".//{ns}MensagemRetorno"):
            error = {}
            codigo = msg.find(f"{ns}Codigo")
            mensagem = msg.find(f"{ns}Mensagem")
            correcao = msg.find(f"{ns}Correcao")
            if codigo is not None:
                error["Codigo"] = codigo.text
            if mensagem is not None:
                error["Mensagem"] = mensagem.text
            if correcao is not None and correcao.text:
                error["Correcao"] = correcao.text
            errors.append(error)
        return errors

    def get_nfse_list(self) -> list[dict]:
        """Extract NFS-e data from CompNfse elements."""
        if self.xml_tree is None:
            return []
        ns = "{http://www.abrasf.org.br/nfse.xsd}"
        nfse_list = []
        for comp in self.xml_tree.findall(f".//{ns}CompNfse"):
            nfse = comp.find(f".//{ns}Nfse")
            if nfse is None:
                nfse = comp.find(f".//{ns}NfseFinal") or comp

            info = {}
            # Try to extract key fields
            for tag in ["Numero", "CodigoVerificacao", "DataEmissao"]:
                el = nfse.find(f".//{ns}{tag}")
                if el is not None and el.text:
                    info[tag] = el.text

            # Get service value
            valor = nfse.find(f".//{ns}ValorServicos")
            if valor is not None:
                info["ValorServicos"] = valor.text

            # Get tomador info
            razao = nfse.find(f".//{ns}TomadorServico/{ns}RazaoSocial")
            if razao is None:
                razao = nfse.find(f".//{ns}RazaoSocial")
            if razao is not None:
                info["TomadorRazaoSocial"] = razao.text

            # Cancelamento vem como <NfseCancelamento>, irmão de <Nfse> dentro
            # de <CompNfse> — nunca como campo de status dentro da própria nota.
            cancelamento = comp.find(f"{ns}NfseCancelamento")
            info["Cancelada"] = cancelamento is not None
            if cancelamento is not None:
                data_canc = cancelamento.find(f".//{ns}DataHora")
                if data_canc is not None and data_canc.text:
                    info["DataCancelamento"] = data_canc.text

            nfse_list.append(info)
        return nfse_list

    def get_links(self) -> list[dict]:
        """Extract URL links from ConsultarUrlNfseResposta."""
        if self.xml_tree is None:
            return []
        ns = "{http://www.abrasf.org.br/nfse.xsd}"
        links = []
        for link_el in self.xml_tree.findall(f".//{ns}Links"):
            link = {}
            for child in link_el:
                tag = child.tag.replace(ns, "")
                if child.text and not isinstance(child.text, type(None)):
                    link[tag] = child.text
                else:
                    # Nested element
                    for sub in child:
                        subtag = sub.tag.replace(ns, "")
                        if sub.text:
                            link[f"{tag}_{subtag}"] = sub.text
            links.append(link)
        return links

    def to_json(self) -> str:
        """Convert the XML response to a JSON string for display."""
        if self.xml_tree is None:
            return json.dumps({"error": "No response", "raw": self.raw_xml})
        return json.dumps(self._element_to_dict(self.xml_tree), indent=2, ensure_ascii=False)

    def _element_to_dict(self, el) -> dict:
        ns = "{http://www.abrasf.org.br/nfse.xsd}"
        result = {}
        for child in el:
            tag = child.tag.replace(ns, "").replace("{http://www.w3.org/2000/09/xmldsig#}", "ds:")
            if len(child) > 0:
                value = self._element_to_dict(child)
            else:
                value = child.text
            if tag in result:
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(value)
            else:
                result[tag] = value
        return result


class SoapClient:
    """SOAP client for ISS.net NFS-e webservice."""

    def __init__(self, config: Config, cert: Certificate):
        self.config = config
        self.cert = cert
        self._cert_files = None

    def _get_cert_files(self) -> tuple[str, str]:
        """Write cert and key to temp files for requests SSL."""
        if self._cert_files is None:
            cert_fd, cert_path = tempfile.mkstemp(suffix=".pem")
            key_fd, key_path = tempfile.mkstemp(suffix=".key")
            os.write(cert_fd, self.cert.certificate_pem)
            os.close(cert_fd)
            os.write(key_fd, self.cert.private_key_pem)
            os.close(key_fd)
            self._cert_files = (cert_path, key_path)
        return self._cert_files

    def _call(self, method: str, header_xml: str, data_xml: str) -> NfseResponse:
        """Call a SOAP method with header and data XML strings."""
        # Use raw SOAP directly — zeep infers wrong namespace from WSDL
        return self._call_raw(method, header_xml, data_xml)

    def _call_raw(self, method: str, header_xml: str, data_xml: str) -> NfseResponse:
        """Send raw SOAP envelope via requests."""
        import requests as req
        import re
        from xml.sax.saxutils import escape as xml_escape

        # Strip XML declaration from data_xml — ISS.net rejects it inside nfseDadosMsg
        clean_data = re.sub(r"<\?xml[^?]*\?>\s*", "", data_xml)

        soap_envelope = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <{method} xmlns="http://nfse.abrasf.org.br">
      <nfseCabecMsg>{xml_escape(header_xml)}</nfseCabecMsg>
      <nfseDadosMsg>{xml_escape(clean_data)}</nfseDadosMsg>
    </{method}>
  </soap:Body>
</soap:Envelope>'''

        cert_path, key_path = self._get_cert_files()

        response = req.post(
            self.config.webservice_url,
            data=soap_envelope.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f"http://nfse.abrasf.org.br/{method}",
            },
            cert=(cert_path, key_path),
            # ponytail: df.issnetonline.com.br manda a cadeia TLS com o certificado
            # raiz self-signed no meio (erro OpenSSL 19), rejeitado mesmo com a CA
            # GoDaddy correta instalada — bug do lado do webservice da prefeitura.
            # Verificado com curl/openssl s_client fora deste código. Reavaliar se
            # a prefeitura corrigir a cadeia servida.
            verify=False,
            timeout=60,
        )

        # Extract response from SOAP envelope
        try:
            tree = etree.fromstring(response.content)
            body = tree.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Body")
            if body is not None and len(body) > 0:
                # Get the first child of Body (the method response)
                method_resp = body[0]
                return NfseResponse(
                    raw_xml=etree.tostring(method_resp, encoding="unicode"),
                    method=method,
                )
        except Exception:
            pass

        return NfseResponse(raw_xml=response.text, method=method)

    def gerar_nfse(self, header_xml: str, data_xml: str) -> NfseResponse:
        return self._call("GerarNfse", header_xml, data_xml)

    def enviar_lote_rps_sincrono(self, header_xml: str, data_xml: str) -> NfseResponse:
        return self._call("RecepcionarLoteRpsSincrono", header_xml, data_xml)

    def cancelar_nfse(self, header_xml: str, data_xml: str) -> NfseResponse:
        return self._call("CancelarNfse", header_xml, data_xml)

    def consultar_url_nfse(self, header_xml: str, data_xml: str) -> NfseResponse:
        return self._call("ConsultarUrlNfse", header_xml, data_xml)

    def consultar_nfse_servico_prestado(self, header_xml: str, data_xml: str) -> NfseResponse:
        return self._call("ConsultarNfseServicoPrestado", header_xml, data_xml)

    def consultar_dados_cadastrais(self, header_xml: str, data_xml: str) -> NfseResponse:
        return self._call("ConsultarDadosCadastrais", header_xml, data_xml)

    def consultar_rps_disponivel(self, header_xml: str, data_xml: str) -> NfseResponse:
        return self._call("ConsultarRpsDisponivel", header_xml, data_xml)

    def cleanup(self):
        """Remove temp cert files."""
        if self._cert_files:
            for f in self._cert_files:
                try:
                    os.unlink(f)
                except OSError:
                    pass
            self._cert_files = None
