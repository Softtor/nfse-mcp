from xml.sax.saxutils import escape as xml_escape
import json
import os
import tempfile

from lxml import etree

from nfse_mcp.certificate import Certificate
from nfse_mcp.nacional.config import NacionalConfig
from nfse_mcp.nacional.constants import NS, SOAP_NS


class NacionalResponse:
    def __init__(self, raw_xml: str, method: str):
        self.raw_xml = raw_xml
        self.method = method
        self._parsed = None

    @property
    def xml_tree(self) -> etree._Element | None:
        if self._parsed is None and self.raw_xml:
            try:
                payload = self.raw_xml.encode("utf-8") if isinstance(self.raw_xml, str) else self.raw_xml
                self._parsed = etree.fromstring(payload)
            except Exception:
                pass
        return self._parsed

    def _findall(self, local: str):
        if self.xml_tree is None:
            return []
        return self.xml_tree.findall(f".//{{{NS}}}{local}") or self.xml_tree.findall(f".//{local}")

    def has_errors(self) -> bool:
        return bool(self._findall("MensagemRetorno"))

    def get_errors(self) -> list[dict]:
        if self.xml_tree is None:
            return [{"Codigo": "PARSE_ERROR", "Mensagem": "Could not parse response"}]
        errors = []
        for msg in self._findall("MensagemRetorno"):
            error = {}
            for tag in ("Codigo", "Mensagem", "Correcao"):
                el = msg.find(f"{{{NS}}}{tag}")
                if el is None:
                    el = msg.find(tag)
                if el is not None and el.text:
                    error[tag] = el.text
            if error:
                errors.append(error)
        return errors

    def get_nfse(self) -> dict:
        info: dict[str, str] = {}
        tree = self.xml_tree
        if tree is None:
            return info
        for tag in ("nNFSe", "nDFSe", "cStat", "dhProc", "nDPS", "serie", "chNFSe"):
            el = tree.find(f".//{{{NS}}}{tag}")
            if el is None:
                el = tree.find(f".//{tag}")
            if el is not None and el.text:
                info[tag] = el.text.strip()
        inf = tree.find(f".//{{{NS}}}infNFSe")
        if inf is None:
            inf = tree.find(".//infNFSe")
        if inf is not None and inf.get("Id"):
            info["Id"] = inf.get("Id")
        return info

    def get_next_dps(self) -> int | None:
        for tag in ("NumDPS", "nDPS"):
            els = self._findall(tag)
            if els and els[0].text:
                try:
                    return int("".join(c for c in els[0].text if c.isdigit()) or "0")
                except ValueError:
                    return None
        return None

    def to_json(self) -> str:
        if self.xml_tree is None:
            return json.dumps({"error": "No response", "raw": self.raw_xml})
        return json.dumps(self._element_to_dict(self.xml_tree), indent=2, ensure_ascii=False)

    def _element_to_dict(self, el) -> dict:
        result = {}
        for child in el:
            tag = child.tag.replace(f"{{{NS}}}", "").replace(f"{{{SOAP_NS}}}", "")
            if "}" in tag:
                tag = tag.split("}", 1)[1]
            value = self._element_to_dict(child) if len(child) else child.text
            if tag in result:
                if not isinstance(result[tag], list):
                    result[tag] = [result[tag]]
                result[tag].append(value)
            else:
                result[tag] = value
        return result


class NacionalSoapClient:
    def __init__(self, config: NacionalConfig, cert: Certificate):
        self.config = config
        self.cert = cert
        self._cert_files = None

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
        import requests as req

        soap_envelope = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            "<soap:Body>"
            f'<{method} xmlns="{SOAP_NS}">'
            f"<nfseCabecMsg>{xml_escape(header_xml)}</nfseCabecMsg>"
            f"<nfseDadosMsg>{xml_escape(data_xml)}</nfseDadosMsg>"
            f"</{method}>"
            "</soap:Body>"
            "</soap:Envelope>"
        )
        cert_path, key_path = self._get_cert_files()
        response = req.post(
            self.config.webservice_url,
            data=soap_envelope.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f"{SOAP_NS}/{method}",
            },
            cert=(cert_path, key_path),
            timeout=60,
        )
        try:
            tree = etree.fromstring(response.content)
            body = tree.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Body")
            if body is not None and len(body) > 0:
                return NacionalResponse(
                    raw_xml=etree.tostring(body[0], encoding="unicode"),
                    method=method,
                )
        except Exception:
            pass
        return NacionalResponse(raw_xml=response.text, method=method)

    def gerar_nfse(self, header_xml: str, data_xml: str) -> NacionalResponse:
        return self.call("GerarNfse", header_xml, data_xml)

    def consultar_nfse_dps(self, header_xml: str, data_xml: str) -> NacionalResponse:
        return self.call("ConsultarNfseDps", header_xml, data_xml)

    def cancelar_nfse(self, header_xml: str, data_xml: str) -> NacionalResponse:
        return self.call("CancelarNfse", header_xml, data_xml)

    def consultar_dps_disponivel(self, header_xml: str, data_xml: str) -> NacionalResponse:
        return self.call("ConsultarDpsDisponivel", header_xml, data_xml)

    def cleanup(self):
        if self._cert_files:
            for f in self._cert_files:
                try:
                    os.unlink(f)
                except OSError:
                    pass
            self._cert_files = None
