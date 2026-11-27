"""ABRASF application service.

Orchestrates SOAP/XML-based NFS-e operations for ISS.net ABRASF 2.04.
"""

import csv
import io
import json
from datetime import date, datetime, timedelta
from typing import Optional

from lxml import etree

from nfse_mcp.application.dto.commands import (
    IssueInvoiceCommand,
    CancelInvoiceCommand,
    ListInvoicesCommand,
)
from nfse_mcp.application.services.client_service import ClientApplicationService
from nfse_mcp.application.services.invoice_log_service import InvoiceLogService
from nfse_mcp.application.exceptions.application_error import InvoiceError
from nfse_mcp.config import Config
from nfse_mcp.certificate import Certificate
from nfse_mcp.xml_signer import XmlSigner
from nfse_mcp.abrasf.soap_client import SoapClient
from nfse_mcp.abrasf.xml_builder import (
    build_cabecalho,
    build_cancelar_nfse_envio,
    wrap_cancelar_nfse_envio,
    build_consultar_dados_cadastrais_envio,
    build_consultar_nfse_servico_prestado_envio,
    build_consultar_url_nfse_envio,
    build_inf_declaracao_xml,
)
from nfse_mcp.models import Client, NfseResult, RpsData, ServiceData


class AbrasfApplicationService:
    """Application service for ABRASF NFS-e operations."""

    def __init__(
        self,
        client_service: ClientApplicationService,
        config: Config,
        cert: Certificate,
        signer: XmlSigner,
        soap: SoapClient,
        log_service: InvoiceLogService,
    ):
        self._client_service = client_service
        self._config = config
        self._cert = cert
        self._signer = signer
        self._soap = soap
        self._log_service = log_service

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _today_str(self) -> str:
        return date.today().isoformat()

    def _first_of_month(self) -> str:
        return date.today().replace(day=1).isoformat()

    def _last_of_month(self) -> str:
        today = date.today()
        if today.month == 12:
            last = today.replace(year=today.year + 1, month=1, day=1)
        else:
            last = today.replace(month=today.month + 1, day=1)
        last = last - timedelta(days=1)
        return last.isoformat()

    def _get_next_rps_number(self) -> int:
        """Fetch next available RPS number from webservice."""
        NS = "http://www.abrasf.org.br/nfse.xsd"
        config = self._config
        cert = self._cert
        signer = self._signer

        data_xml = (
            f'<ConsultarRpsDisponivelEnvio xmlns="{NS}">'
            f'<Pedido>'
            f'<Prestador>'
            f'<CpfCnpj><Cnpj>{config.provider.cnpj}</Cnpj></CpfCnpj>'
            f'<InscricaoMunicipal>{config.provider.im}</InscricaoMunicipal>'
            f'</Prestador>'
            f'<Pagina>1</Pagina>'
            f'</Pedido>'
            f'</ConsultarRpsDisponivelEnvio>'
        )

        signed = signer.sign_xml(data_xml)
        header = build_cabecalho()

        soap_client = SoapClient(config, cert)
        response = soap_client.consultar_rps_disponivel(header, signed)

        if response.xml_tree is not None:
            numeros = response.xml_tree.findall(f".//{{{NS}}}RpsDisponivel/{{{NS}}}Numero")
            if numeros:
                return int(numeros[0].text)

        raise InvoiceError("Nao foi possivel obter numero de RPS disponivel")

    def _build_signed_gerar_nfse(
        self,
        rps: RpsData,
        service: ServiceData,
        client: Client,
        competencia: str,
    ) -> str:
        """Build a signed GerarNfseEnvio XML ready for SOAP submission."""
        NS = "http://www.abrasf.org.br/nfse.xsd"
        DS = "http://www.w3.org/2000/09/xmldsig#"

        inf_xml = build_inf_declaracao_xml(self._config, rps, service, client, competencia)
        signed_xml = self._signer.sign_xml(inf_xml)

        signed_el = etree.fromstring(signed_xml.encode("utf-8"))
        sig_el = signed_el.find(f"{{{DS}}}Signature")
        if sig_el is not None:
            signed_el.remove(sig_el)

        root = etree.Element(f"{{{NS}}}GerarNfseEnvio", nsmap={None: NS})
        rps_el = etree.SubElement(root, f"{{{NS}}}Rps")
        rps_el.append(signed_el)
        if sig_el is not None:
            rps_el.append(sig_el)

        return etree.tostring(root, encoding="unicode", xml_declaration=False)

    def _parse_nfse_response(self, response, rps_number: Optional[int] = None) -> NfseResult:
        """Parse an NfseResponse into an NfseResult."""
        if response.has_errors():
            errors = response.get_errors()
            error_msgs = []
            for e in errors:
                msg = e.get("Mensagem", "Erro desconhecido")
                cod = e.get("Codigo", "")
                correcao = e.get("Correcao", "")
                entry = f"[{cod}] {msg}"
                if correcao:
                    entry += f" (Correcao: {correcao})"
                error_msgs.append(entry)
            return NfseResult(
                success=False,
                numero_rps=rps_number,
                errors=error_msgs,
            )

        nfse_list = response.get_nfse_list()
        if not nfse_list:
            return NfseResult(
                success=False,
                numero_rps=rps_number,
                errors=["Nenhuma NFS-e retornada na resposta"],
                mensagem=response.raw_xml[:500] if response.raw_xml else None,
            )

        nfse_data = nfse_list[0]
        return NfseResult(
            success=True,
            numero_nfse=nfse_data.get("Numero"),
            numero_rps=rps_number,
            codigo_verificacao=nfse_data.get("CodigoVerificacao"),
            data_emissao=nfse_data.get("DataEmissao"),
        )

    def _try_get_url(self, nfse_number: str) -> Optional[str]:
        """Attempt to get the NFS-e visualization URL."""
        try:
            cfg = self._config
            header = build_cabecalho()
            data_xml = build_consultar_url_nfse_envio(cfg, numero_nfse=nfse_number)
            signed = self._signer.sign_xml(data_xml)
            resp = self._soap.consultar_url_nfse(header, signed)
            if not resp.has_errors():
                links = resp.get_links()
                if links:
                    for link in links:
                        for key, val in link.items():
                            if isinstance(val, str) and val.startswith("http"):
                                return val
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Issue single
    # ------------------------------------------------------------------

    def issue_invoice(self, command: IssueInvoiceCommand) -> NfseResult:
        """Issue a single NFS-e via ABRASF."""
        client = self._client_service.find_or_register_client(command.client_document)
        if not client.razao_social:
            raise InvoiceError(
                f"Cliente com documento {command.client_document} "
                "nao possui razao social. Registre o cliente primeiro."
            )

        client = self._client_service.ensure_complete_address(client)

        rps_num = self._get_next_rps_number()

        comp = command.competencia or self._first_of_month()
        rps = RpsData(
            numero=rps_num,
            serie=self._config.rps_serie,
            tipo=1,
            data_emissao=self._today_str(),
            status=1,
        )
        service = ServiceData(
            valor_servicos=command.valor,
            discriminacao=command.discriminacao,
            cnae=command.cnae or "",
            aliquota=command.aliquota or "",
            item_lista_servico=command.item_lista_servico or "",
            codigo_tributacao_municipio=command.codigo_tributacao_municipio or "",
        )

        signed_xml = self._build_signed_gerar_nfse(rps, service, client, comp)
        header_xml = build_cabecalho()
        response = self._soap.gerar_nfse(header_xml, signed_xml)

        result = self._parse_nfse_response(response, rps_number=rps_num)

        if result.success:
            url = None
            if result.numero_nfse:
                url = self._try_get_url(result.numero_nfse)
                result.url_visualizacao = url

            self._log_service.append_nfse_log({
                "provider": "abrasf",
                "rps_number": rps_num,
                "nfse_number": result.numero_nfse,
                "date": self._today_str(),
                "client_cnpj": client.document,
                "client_name": client.razao_social,
                "valor": command.valor,
                "discriminacao": command.discriminacao,
                "cnae": command.cnae or self._config.service_defaults.cnae,
                "item_lista_servico": command.item_lista_servico or self._config.service_defaults.item_lista_servico,
                "codigo_tributacao_municipio": command.codigo_tributacao_municipio or self._config.service_defaults.codigo_tributacao_municipio,
                "aliquota": command.aliquota or self._config.service_defaults.aliquota,
                "competencia": comp,
                "url": url,
            })

        return result

    # ------------------------------------------------------------------
    # Issue batch
    # ------------------------------------------------------------------

    def issue_batch(self, csv_data: str) -> list[dict]:
        """Emit multiple NFS-e from CSV data.

        Returns a list of result dicts with 'status', 'line', 'message', 'nfse_number', etc.
        """
        reader = csv.reader(io.StringIO(csv_data.strip()))
        rows = list(reader)
        if not rows:
            raise InvoiceError("CSV vazio.")

        first = rows[0]
        if first and first[0].lower().strip() in ("cnpj", "document", "documento"):
            rows = rows[1:]

        if not rows:
            raise InvoiceError("Nenhuma linha de dados no CSV.")

        results = []
        for i, row in enumerate(rows):
            line_num = i + 1
            if len(row) < 3:
                results.append({
                    "status": "error",
                    "line": line_num,
                    "message": "precisa de pelo menos 3 colunas (cnpj, valor, discriminacao)",
                })
                continue

            doc = row[0].strip()
            valor = row[1].strip()
            discriminacao = row[2].strip()
            comp = row[3].strip() if len(row) > 3 and row[3].strip() else self._first_of_month()

            try:
                client = self._client_service.find_or_register_client(doc)
                if not client.razao_social:
                    results.append({
                        "status": "error",
                        "line": line_num,
                        "message": f"cliente {doc} sem razao social",
                    })
                    continue

                self._client_service.ensure_complete_address(client)

                rps_num = self._get_next_rps_number()
                rps = RpsData(
                    numero=rps_num,
                    serie=self._config.rps_serie,
                    tipo=1,
                    data_emissao=self._today_str(),
                    status=1,
                )
                service = ServiceData(
                    valor_servicos=valor,
                    discriminacao=discriminacao,
                )

                signed_xml = self._build_signed_gerar_nfse(rps, service, client, comp)
                header_xml = build_cabecalho()
                response = self._soap.gerar_nfse(header_xml, signed_xml)

                if response.has_errors():
                    errors = response.get_errors()
                    error_msgs = "; ".join(
                        f"[{e.get('Codigo', '')}] {e.get('Mensagem', '')}" for e in errors
                    )
                    results.append({
                        "status": "error",
                        "line": line_num,
                        "message": f"{client.razao_social}: {error_msgs}",
                    })
                    continue

                nfse_list = response.get_nfse_list()
                nfse_data = nfse_list[0] if nfse_list else {}
                nfse_number = nfse_data.get("Numero", "?")
                url = None
                if nfse_number and nfse_number != "?":
                    url = self._try_get_url(nfse_number)

                self._log_service.append_nfse_log({
                    "provider": "abrasf",
                    "rps_number": rps_num,
                    "nfse_number": nfse_number,
                    "date": self._today_str(),
                    "client_cnpj": doc,
                    "client_name": client.razao_social,
                    "valor": valor,
                    "discriminacao": discriminacao,
                    "cnae": self._config.service_defaults.cnae,
                    "item_lista_servico": self._config.service_defaults.item_lista_servico,
                    "codigo_tributacao_municipio": self._config.service_defaults.codigo_tributacao_municipio,
                    "aliquota": self._config.service_defaults.aliquota,
                    "competencia": comp,
                    "url": url,
                })

                results.append({
                    "status": "success",
                    "line": line_num,
                    "nfse_number": nfse_number,
                    "rps_number": rps_num,
                    "client_name": client.razao_social,
                    "valor": valor,
                    "url": url,
                })

            except Exception as e:
                results.append({
                    "status": "error",
                    "line": line_num,
                    "message": str(e),
                })

        return results

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel_invoice(self, command: CancelInvoiceCommand) -> dict:
        """Cancel an issued NFS-e.

        Returns dict with 'success', 'nfse_number', 'motivo', etc.
        """
        # ponytail: valores conforme tsCodigoCancelamentoNfse do XSD ABRASF 2.04
        # (schemas/schema_v204.xsd) — o mapa anterior (1/2/9) nao batia com o
        # schema real (1-5) e causava SOAP Fault generico ao usar "9".
        motivo_desc = {
            "1": "Erro na Emissao",
            "2": "Servico nao Prestado",
            "3": "Erro de Assinatura",
            "4": "Duplicidade da Nota",
            "5": "Erro de Processamento",
        }

        if command.motivo not in motivo_desc:
            raise InvoiceError(f"motivo invalido '{command.motivo}'. Use 1 a 5.")

        pedido_xml = build_cancelar_nfse_envio(self._config, command.nfse_number, command.motivo)
        signed_pedido = self._signer.sign_xml(pedido_xml)
        data_xml = wrap_cancelar_nfse_envio(signed_pedido)

        header = build_cabecalho()
        response = self._soap.cancelar_nfse(header, data_xml)

        if response.has_errors():
            errors = response.get_errors()
            error_msgs = [f"[{e.get('Codigo', '')}] {e.get('Mensagem', '')}" for e in errors]
            raise InvoiceError(
                f"Erro no cancelamento da NFS-e {command.nfse_number}",
                errors=[{"codigo": e.get("Codigo"), "descricao": e.get("Mensagem")} for e in errors],
            )

        # Build cancel log entry
        nfse_log = self._log_service.load_nfse_log()
        original = None
        for entry in nfse_log:
            if str(entry.get("nfse_number")) == str(command.nfse_number):
                original = entry
                break

        cancel_entry = {
            "nfse_number": str(command.nfse_number),
            "motivo_codigo": command.motivo,
            "motivo_descricao": motivo_desc[command.motivo],
            "data_cancelamento": self._today_str(),
            "hora_cancelamento": datetime.now().isoformat(),
        }

        if original:
            cancel_entry.update({
                "rps_number": original.get("rps_number"),
                "client_cnpj": original.get("client_cnpj"),
                "client_name": original.get("client_name"),
                "valor": original.get("valor"),
                "discriminacao": original.get("discriminacao"),
                "cnae": original.get("cnae"),
                "item_lista_servico": original.get("item_lista_servico"),
                "codigo_tributacao_municipio": original.get("codigo_tributacao_municipio"),
                "aliquota": original.get("aliquota"),
                "competencia": original.get("competencia"),
                "data_emissao": original.get("date"),
                "url": original.get("url"),
            })

        self._log_service.append_cancel_log(cancel_entry)

        return {
            "success": True,
            "nfse_number": command.nfse_number,
            "motivo": command.motivo,
            "motivo_descricao": motivo_desc[command.motivo],
        }

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_nfse_link(self, nfse_number: str = "", periodo_inicio: str = "", periodo_fim: str = "") -> list[dict]:
        """Get visualization URLs for NFS-e(s)."""
        cfg = self._config
        header = build_cabecalho()

        if nfse_number:
            data_xml = build_consultar_url_nfse_envio(cfg, numero_nfse=nfse_number)
        elif periodo_inicio and periodo_fim:
            data_xml = build_consultar_url_nfse_envio(
                cfg, data_inicial=periodo_inicio, data_final=periodo_fim
            )
        else:
            raise InvoiceError("Informe nfse_number ou periodo_inicio + periodo_fim.")

        signed = self._signer.sign_xml(data_xml)
        response = self._soap.consultar_url_nfse(header, signed)

        if response.has_errors():
            errors = response.get_errors()
            raise InvoiceError(
                "Erro na consulta de URL",
                errors=[{"codigo": e.get("Codigo"), "descricao": e.get("Mensagem")} for e in errors],
            )

        return response.get_links()

    def list_invoices(self, command: ListInvoicesCommand) -> dict:
        """List NFS-e invoices issued in a period.

        Returns dict with 'periodo', 'total', 'notas' (list), 'valor_total'.
        """
        d_ini = command.data_inicial or self._first_of_month()
        # O webservice rejeita data final no futuro (E133), e o fim do mês
        # corrente quase sempre está no futuro — daí o clamp para hoje.
        d_fim = command.data_final or min(self._last_of_month(), self._today_str())

        header = build_cabecalho()
        data_xml = build_consultar_nfse_servico_prestado_envio(self._config, d_ini, d_fim)
        signed = self._signer.sign_xml(data_xml)
        response = self._soap.consultar_nfse_servico_prestado(header, signed)

        if response.has_errors():
            errors = response.get_errors()
            # E212 ("NFS-e não encontrada") é período vazio, não falha: o
            # webservice usa erro para dizer "nenhum resultado".
            if all(e.get("Codigo") == "E212" for e in errors):
                return {
                    "periodo_inicial": d_ini,
                    "periodo_final": d_fim,
                    "total": 0,
                    "notas": [],
                    "valor_total": 0.0,
                }
            raise InvoiceError(
                f"Erro na consulta de {d_ini} a {d_fim}",
                errors=[{"codigo": e.get("Codigo"), "descricao": e.get("Mensagem")} for e in errors],
            )

        nfse_list = response.get_nfse_list()
        notas = []
        total_valor = 0.0
        total_canceladas = 0

        for nfse in nfse_list:
            numero = nfse.get("Numero", "-")
            data_emissao = nfse.get("DataEmissao", "-")
            valor_str = nfse.get("ValorServicos", "0")
            tomador = nfse.get("TomadorRazaoSocial", "-")
            cancelada = bool(nfse.get("Cancelada"))

            try:
                valor_num = float(valor_str)
            except (ValueError, TypeError):
                valor_num = 0.0

            # Nota cancelada não entra no faturamento.
            if cancelada:
                total_canceladas += 1
            else:
                total_valor += valor_num

            notas.append({
                "numero": numero,
                "data_emissao": data_emissao,
                "valor": valor_num,
                "tomador": tomador,
                "cancelada": cancelada,
                "status": "CANCELADA" if cancelada else "Ativa",
                "data_cancelamento": nfse.get("DataCancelamento"),
            })

        return {
            "periodo_inicial": d_ini,
            "periodo_final": d_fim,
            "total": len(notas),
            "total_ativas": len(notas) - total_canceladas,
            "total_canceladas": total_canceladas,
            "notas": notas,
            # Soma apenas as ativas — é o valor que vale para faturamento.
            "valor_total": total_valor,
        }

    def list_cancelled_invoices(self) -> list[dict]:
        """List all cancelled invoices from local log."""
        return self._log_service.load_cancel_log()

    def query_cadastral_data(self) -> dict:
        """Query provider cadastral data from webservice."""
        cfg = self._config
        header = build_cabecalho()
        data_xml = build_consultar_dados_cadastrais_envio(cfg)
        signed = self._signer.sign_xml(data_xml)
        response = self._soap.consultar_dados_cadastrais(header, signed)

        if response.has_errors():
            errors = response.get_errors()
            raise InvoiceError(
                "Erro na consulta cadastral",
                errors=[{"codigo": e.get("Codigo"), "descricao": e.get("Mensagem")} for e in errors],
            )

        json_str = response.to_json()
        data = json.loads(json_str)
        return {
            "provider_cnpj": cfg.provider.cnpj,
            "provider_im": cfg.provider.im,
            "provider_razao_social": cfg.provider.razao_social,
            "dados": data,
        }
