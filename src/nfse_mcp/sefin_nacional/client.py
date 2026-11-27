"""HTTP client for SEFIN Nacional REST API with mTLS authentication."""

import json
import os
import tempfile
import time
from typing import Optional

import requests

from nfse_mcp.certificate import Certificate
from nfse_mcp.sefin_nacional.config import ADN_URLS, SefinNacionalConfig
from nfse_mcp.errors import CertificateError, SefinNacionalError


class SefinNacionalClient:
    """Low-level REST client for SEFIN Nacional.

    Handles mTLS, JSON payloads, GZip+Base64 XMLs, and retries.
    """

    def __init__(self, config: SefinNacionalConfig, cert: Certificate):
        self.config = config
        self.cert = cert
        self._cert_files: Optional[tuple[str, str]] = None

    def _get_cert_files(self) -> tuple[str, str]:
        """Write cert and key to temp PEM files for requests SSL."""
        if self._cert_files is None:
            cert_fd, cert_path = tempfile.mkstemp(suffix=".pem")
            key_fd, key_path = tempfile.mkstemp(suffix=".key")
            os.write(cert_fd, self.cert.certificate_pem)
            os.close(cert_fd)
            os.write(key_fd, self.cert.private_key_pem)
            os.close(key_fd)
            self._cert_files = (cert_path, key_path)
        return self._cert_files

    def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
        expect_json: bool = True,
    ) -> dict:
        """Make an HTTP request with mTLS, retries and normalized error handling."""
        url = f"{self.config.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        response = self._send(method, url, json_body, headers)

        if expect_json and response.headers.get("Content-Type", "").startswith("application/json"):
            body = response.json() if response.text else {}
        else:
            body = {"raw": response.text}

        if response.status_code >= 400:
            raise SefinNacionalError(
                f"Erro SEFIN Nacional (HTTP {response.status_code})",
                code=f"HTTP_{response.status_code}",
                raw_errors=_error_list(body),
            )

        return body

    def _send(self, method: str, url: str, json_body: Optional[dict], headers: dict) -> requests.Response:
        """Envia com mTLS. GET repete com espera; POST (emissão, evento) vai uma vez só: se a resposta
        se perdeu, quem chamou consulta antes de reenviar."""
        cert = self._get_cert_files()
        attempts = 1 if method == "POST" else self.config.max_retries
        for attempt in range(1, attempts + 1):
            try:
                return requests.request(
                    method, url, json=json_body, headers=headers, cert=cert, timeout=self.config.timeout,
                )
            except requests.exceptions.SSLError as exc:
                raise CertificateError(f"Falha na autenticacao mTLS: {exc}")
            except requests.exceptions.RequestException as exc:
                if attempt < attempts:
                    time.sleep(2 ** attempt)  # exponential backoff
                    continue
                if isinstance(exc, requests.exceptions.Timeout):
                    raise SefinNacionalError(f"Timeout apos {attempts} tentativa(s): {exc}", code="TIMEOUT")
                raise SefinNacionalError(
                    f"Erro de conexao apos {attempts} tentativa(s): {exc}", code="CONNECTION_ERROR",
                )
        raise AssertionError("inalcançável: o laço sempre devolve ou lança")

    def post_nfse(self, dps_xml_gzip_b64: str) -> dict:
        """POST /nfse — issue a DPS."""
        return self._request("POST", "/nfse", json_body={"dpsXmlGZipB64": dps_xml_gzip_b64})

    def get_nfse(self, chave_acesso: str) -> dict:
        """GET /nfse/{chaveAcesso} — query NFS-e by access key."""
        return self._request("GET", f"/nfse/{chave_acesso}")

    def get_dps(self, dps_id: str) -> dict:
        """GET /dps/{id} — query access key by DPS identifier."""
        return self._request("GET", f"/dps/{dps_id}")

    def head_dps(self, dps_id: str) -> bool:
        """HEAD /dps/{id} — check if DPS was processed. Returns True if exists."""
        try:
            self._request("HEAD", f"/dps/{dps_id}", expect_json=False)
            return True
        except SefinNacionalError as exc:
            if exc.code == "HTTP_404":
                return False
            raise

    def post_evento(self, chave_acesso: str, evento_xml_gzip_b64: str) -> dict:
        """POST /nfse/{chaveAcesso}/eventos — register an event."""
        return self._request(
            "POST",
            f"/nfse/{chave_acesso}/eventos",
            json_body={"pedidoRegistroEventoXmlGZipB64": evento_xml_gzip_b64},  # nome do swagger /swagger/docs/v1
        )

    def get_evento(self, chave_acesso: str, tipo_evento: str, numero: int = 1) -> dict:
        """GET /nfse/{chave}/eventos/{tipoEvento}/{nSeq}: um evento (GET em /eventos sem tipo dá 405)."""
        return self._request("GET", f"/nfse/{chave_acesso}/eventos/{tipo_evento}/{numero}")

    def get_danfse(self, chave_acesso: str) -> bytes:
        """GET {ADN}/danfse/{chaveAcesso}: PDF oficial. Em 04/11/2026 o ADN devolve 503/404 (NT 008/2026)."""
        adn = ADN_URLS.get(self.config.environment, ADN_URLS["production_restricted"])
        response = requests.get(
            f"{adn}/danfse/{chave_acesso}",
            cert=self._get_cert_files(),
            headers={"Accept": "application/pdf"},
            timeout=self.config.timeout,
        )
        if response.status_code >= 400:
            raise SefinNacionalError(
                f"Erro ao baixar DANFSe (HTTP {response.status_code})",
                code=f"HTTP_{response.status_code}",
            )
        return response.content

    def get_convenio(self, codigo_municipio: str) -> dict:
        """GET /parametros_municipais/{codigoMunicipio}/convenio"""
        return self._request("GET", f"/parametros_municipais/{codigo_municipio}/convenio")

    def get_service_parameters(self, codigo_municipio: str, codigo_servico: str) -> dict:
        """GET /parametros_municipais/{codigoMunicipio}/{codigoServico}"""
        return self._request("GET", f"/parametros_municipais/{codigo_municipio}/{codigo_servico}")

    def get_retencoes(self, codigo_municipio: str, documento: str) -> dict:
        """GET /parametros_municipais/{codigoMunicipio}/{documento}/retencoes"""
        return self._request("GET", f"/parametros_municipais/{codigo_municipio}/{documento}/retencoes")

    def get_beneficios(self, codigo_municipio: str, documento: str) -> dict:
        """GET /parametros_municipais/{codigoMunicipio}/{documento}/beneficios"""
        return self._request("GET", f"/parametros_municipais/{codigo_municipio}/{documento}/beneficios")

    def cleanup(self) -> None:
        """Remove temporary PEM files."""
        if self._cert_files:
            for f in self._cert_files:
                try:
                    os.unlink(f)
                except OSError:
                    pass
            self._cert_files = None


def _error_list(body: dict) -> list[dict]:
    """Erros da resposta da SEFIN, com o Complemento (é ele que diz o campo recusado)."""
    raw_errors = body.get("erros") or body.get("errors") or []
    error_list = []
    for e in raw_errors if isinstance(raw_errors, list) else []:
        desc = _campo(e, "descricao") or str(e)
        complemento = _campo(e, "complemento")
        if complemento:
            desc = f"{desc} {complemento}"
        error_list.append({"codigo": _campo(e, "codigo") or "UNKNOWN", "descricao": desc})
    return error_list


def _campo(erro: dict, nome: str):
    """A SEFIN devolve os campos ora em minúscula, ora com inicial maiúscula."""
    return erro.get(nome) or erro.get(nome.capitalize())
