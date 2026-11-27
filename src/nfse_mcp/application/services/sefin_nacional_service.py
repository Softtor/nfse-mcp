"""SEFIN Nacional application service.

Orchestrates client lookup, input building, provider calls, and logging
for SEFIN Nacional NFS-e operations.
"""

import json
import re
from datetime import date
from pathlib import Path
from nfse_mcp.application.dto.commands import (
    IssueInvoiceCommand,
    QueryInvoiceCommand,
    QueryParametersCommand,
)
from nfse_mcp.application.services.client_service import ClientApplicationService
from nfse_mcp.application.services.invoice_log_service import InvoiceLogService
from nfse_mcp.application.exceptions.application_error import InvoiceError, ParameterError
from nfse_mcp.errors import (
    CertificateError,
    MunicipalityNotEnabledError,
    ProviderError,
    SefinNacionalError,
    ValidationError,
)
from nfse_mcp.nacional.dps_xml_builder import dps_id
from nfse_mcp.nacional.evento_xml_builder import validar_cancelamento
from nfse_mcp.ports.service_invoice_provider import (
    CancelServiceInvoiceInput,
    IssueServiceInvoiceInput,
    IssueServiceInvoiceResult,
    ServiceInvoiceProvider,
)
from nfse_mcp.ports.municipal_parameter_provider import MunicipalParameterProvider
from nfse_mcp.nacional.lista_servico import codigo_tributacao_nacional
from nfse_mcp.config import Config
from nfse_mcp.sefin_nacional.config import SefinNacionalConfig
from nfse_mcp.sefin_nacional.mapper import nfse_confere, op_simp_nac, reg_esp_trib
from nfse_mcp.sefin_nacional.municipality_data import MunicipalityDataLoader

SERIE_DPS = "1"
CONSULTA_PUBLICA = "https://www.nfse.gov.br/consultapublica"
CHAVE_NFSE = re.compile(r"[0-9]{6}[0-9A-Z]{14}[0-9]{30}")  # TSChaveNFSe do XSD oficial


def nfse_nacionais(log: list[dict], inicio: str = "", fim: str = "") -> list[dict]:
    """Entradas do Emissor Nacional no log local com data entre inicio e fim (AAAA-MM-DD; vazio = sem limite)."""
    return [e for e in log if e.get("provider") == "sefin_nacional"
            and (not inicio or e.get("date", "") >= inicio) and (not fim or e.get("date", "") <= fim)]


def next_numero_dps(log: list[dict]) -> int:
    """Próximo nDPS a partir do log: maior numero_dps já usado no nacional + 1."""
    usados = [int(e["numero_dps"]) for e in log if e.get("provider") == "sefin_nacional" and e.get("numero_dps")]
    return max(usados, default=0) + 1


def numero_nfse(chave_acesso: str) -> str:
    """nNFSe: os 13 dígitos da chave depois de município (7), ambiente (1), tipo de inscrição (1) e CNPJ (14)."""
    return chave_acesso[23:36].lstrip("0") or "0"


def _servidor_recusou(exc: ProviderError) -> bool:
    """True quando a SEFIN respondeu recusando (a DPS não foi aceita), e não quando a resposta se perdeu."""
    return isinstance(exc, MunicipalityNotEnabledError) or exc.code.startswith("HTTP_4")


class SefinNacionalApplicationService:
    """Application service for SEFIN Nacional NFS-e operations."""

    def __init__(
        self,
        client_service: ClientApplicationService,
        invoice_provider: ServiceInvoiceProvider,
        parameter_provider: MunicipalParameterProvider,
        config: Config,
        sefin_config: SefinNacionalConfig,
        log_service: InvoiceLogService,
    ):
        self._client_service = client_service
        self._invoice_provider = invoice_provider
        self._parameter_provider = parameter_provider
        self._config = config
        self._sefin_config = sefin_config
        self._log_service = log_service

    def _today_str(self) -> str:
        return date.today().isoformat()

    def _first_of_month(self) -> str:
        today = date.today()
        return today.replace(day=1).isoformat()

    # ------------------------------------------------------------------
    # Issue
    # ------------------------------------------------------------------

    def issue_invoice(self, command: IssueInvoiceCommand):
        """Issue a service invoice via SEFIN Nacional.

        Returns IssueServiceInvoiceResult.
        Raises InvoiceError on failure.
        """
        codigo_municipio = command.codigo_municipio or "5300108"
        loader = MunicipalityDataLoader()
        if loader.is_emissor_proprio(codigo_municipio):
            raise InvoiceError(
                f"Municipio {codigo_municipio} mantem emissor proprio (ISS.net/ABRASF). "
                f"Use o servico ABRASF (emit_nfse) em vez de SEFIN Nacional (emit_nfse_nacional)."
            )

        # Antes de reservar o nDPS: código fora da lista nacional gastaria o número (E0310).
        codigo_servico = codigo_tributacao_nacional(
            command.codigo_servico or self._config.service_defaults.item_lista_servico
        )
        client = self._load_client(command.client_document)
        optante = self._optante_simples()
        self._resolve_pending(client.document)
        numero_dps = self._reserve_numero_dps()
        input_data = self._dps_input(command, client, optante, numero_dps, codigo_servico)
        entry = self._log_entry(input_data, client)
        # Grava antes de enviar: se o processo cair depois da SEFIN aceitar, a próxima emissão
        # acha esta DPS pendente e consulta, em vez de mandar outro nDPS (nota duplicada).
        self._log_service.append_nfse_log({**entry, "status": "pendente", "erro": "envio em andamento"})

        try:
            result = self._invoice_provider.issue(input_data)
        except (ValidationError, CertificateError):
            self._atualizar_entrada(entry["id_dps"], status="nao_emitida", erro="nada chegou a SEFIN")
            raise
        except ProviderError as exc:
            result = self._recover(entry, exc)

        if result.success:
            self._atualizar_entrada(entry["id_dps"], status="emitida", chave_acesso=result.chave_acesso, erro=None)

        return result

    def _atualizar_entrada(self, id_dps: str, **campos) -> None:
        """Atualiza no log a entrada da DPS; campo None é removido."""
        log = self._log_service.load_nfse_log()
        for entrada in log:
            if entrada.get("provider") == "sefin_nacional" and entrada.get("id_dps") == id_dps:
                entrada.update(campos)
                for chave in [c for c, v in campos.items() if v is None]:
                    entrada.pop(chave, None)
        self._log_service.save_nfse_log(log)

    def _load_client(self, document: str):
        client = self._client_service.find_or_register_client(document)
        if not client.razao_social:
            raise InvoiceError(
                f"Cliente com documento {document} "
                "nao possui razao social. Registre o cliente primeiro."
            )
        return self._client_service.ensure_complete_address(client)

    def _optante_simples(self) -> int:
        """opSimpNac do prestador; optante sem % de tributos do Simples configurado não emite (E0712)."""
        provider = self._config.provider
        optante = op_simp_nac(provider.simples_nacional, provider.regime_tributacao)
        if optante in (2, 3) and not provider.aliquota_simples:
            raise InvoiceError(
                "Optante do Simples precisa do % aproximado de tributos na NFS-e nacional (E0712): "
                "configure NFSE_PROVIDER_ALIQUOTA_SIMPLES no .env."
            )
        return optante

    def _dps_input(
        self, command: IssueInvoiceCommand, client, optante: int, numero_dps: str, codigo_servico: str
    ) -> IssueServiceInvoiceInput:
        provider = self._config.provider
        defaults = self._config.service_defaults
        municipio = command.codigo_municipio or "5300108"
        # Endereço do tomador já vem completo de ensure_complete_address.
        return IssueServiceInvoiceInput(
            prestador_cnpj=provider.cnpj,
            prestador_razao_social=provider.razao_social,
            prestador_endereco_logradouro="Rua Nao Informada",
            prestador_endereco_numero="SN",
            prestador_endereco_bairro="Nao Informado",
            prestador_endereco_codigo_municipio=municipio,
            prestador_endereco_uf="DF",
            prestador_endereco_cep="70000000",
            # Sem IM: a SEFIN recusa (E0120) quando o CNC do município não tem complemento cadastrado.
            prestador_inscricao_municipal=None,
            tomador_document=client.document,
            tomador_tipo_documento=client.document_type,
            tomador_razao_social=client.razao_social,
            tomador_endereco_logradouro=client.endereco,
            tomador_endereco_numero=client.numero,
            tomador_endereco_bairro=client.bairro,
            tomador_endereco_codigo_municipio=client.codigo_municipio,
            tomador_endereco_uf=client.uf,
            tomador_endereco_cep=client.cep,
            servico_codigo=codigo_servico,
            servico_discriminacao=command.discriminacao,
            servico_valor=command.valor,
            competencia=command.competencia or self._first_of_month(),
            # Só o informado: o padrão da config é código do ISS.net e não existe no nacional (E0314).
            codigo_tributacao_municipio=command.codigo_tributacao_municipio or "",
            optante_simples_nacional=optante,
            aliquota_simples=provider.aliquota_simples or None,
            regime_especial_tributacao=reg_esp_trib(provider.regime_tributacao),
            incentivo_fiscal=provider.incentivo_fiscal,
            aliquota=command.aliquota or defaults.aliquota,
            iss_retido=defaults.iss_retido,
            tipo_ambiente=self._sefin_config.tp_amb,
            serie_dps=SERIE_DPS,
            numero_dps=numero_dps,
        )

    def _log_entry(self, input_data: IssueServiceInvoiceInput, client) -> dict:
        return {
            "provider": "sefin_nacional",
            "id_dps": dps_id(input_data.prestador_endereco_codigo_municipio, input_data.prestador_cnpj,
                             input_data.serie_dps, input_data.numero_dps),
            "serie_dps": input_data.serie_dps,
            "numero_dps": input_data.numero_dps,
            "date": self._today_str(),
            "client_cnpj": client.document,
            "client_name": client.razao_social,
            "valor": input_data.servico_valor,
            "discriminacao": input_data.servico_discriminacao,
            "codigo_servico": input_data.servico_codigo,
            "codigo_tributacao_municipio": input_data.codigo_tributacao_municipio,
            "aliquota": input_data.aliquota,
            "competencia": input_data.competencia,
        }

    # ------------------------------------------------------------------
    # Numeração e DPS sem resposta
    # ------------------------------------------------------------------

    def _reserve_numero_dps(self) -> str:
        """Reserva o nDPS antes do envio, para que nenhum número seja usado duas vezes."""
        path = self._config.data_dir / "dps_counter.json"
        if path.exists():
            numero = json.loads(path.read_text())["next"]  # ilegível → erro, nunca recomeça do 1
        else:
            numero = next_numero_dps(self._log_service.load_nfse_log())
        path.write_text(json.dumps({"next": numero + 1}))
        return str(numero)

    def _lookup(self, entry: dict):
        """NFS-e gerada pela DPS da entrada; None se a SEFIN diz que não existe. ProviderError se não der para saber."""
        try:
            found = self._invoice_provider.query_by_dps_id(entry["id_dps"])
        except SefinNacionalError as exc:
            if exc.code == "HTTP_404":
                return None
            raise
        if not found.success:
            raise SefinNacionalError(f"Consulta da DPS {entry['id_dps']} sem chave de acesso")
        return found

    def _matches(self, found, entry: dict) -> bool:
        return nfse_confere(found.xml_nfse, entry["client_cnpj"], entry["valor"], entry["competencia"])

    def _recover(self, entry: dict, exc: ProviderError) -> IssueServiceInvoiceResult:
        """Envio sem resposta clara: confirma pela consulta da DPS antes de dizer que falhou."""
        try:
            found = self._lookup(entry)
        except ProviderError:
            found = False  # não deu para saber
        if found is None and _servidor_recusou(exc):
            self._atualizar_entrada(entry["id_dps"], status="nao_emitida", erro=exc.message)
            raise exc
        if found and self._matches(found, entry):
            return IssueServiceInvoiceResult(
                success=True, chave_acesso=found.chave_acesso, id_dps=entry["id_dps"], xml_nfse=found.xml_nfse,
            )
        self._atualizar_entrada(entry["id_dps"], status="pendente", erro=exc.message)
        raise InvoiceError(
            f"NFS-e pendente: a DPS {entry['id_dps']} foi enviada e nao foi possivel confirmar se virou nota "
            f"({exc.message}). Nenhuma outra nota sera emitida para {entry['client_name']} ate a consulta resolver."
        )

    def _resolve_pending(self, document: str) -> None:
        """Antes de emitir, resolve DPS pendente do mesmo tomador: emitida bloqueia, inexistente libera."""
        log = self._log_service.load_nfse_log()
        for entry in log:
            if entry.get("provider") != "sefin_nacional" or entry.get("status") != "pendente":
                continue
            if entry.get("client_cnpj") != document:
                continue
            try:
                found = self._lookup(entry)
            except ProviderError as exc:
                raise InvoiceError(
                    f"NFS-e pendente da DPS {entry['id_dps']} ainda sem confirmacao ({exc.message}). Nao emiti outra."
                )
            if found is None:
                entry["status"] = "nao_emitida"
                self._log_service.save_nfse_log(log)
                continue
            if not self._matches(found, entry):
                raise InvoiceError(
                    f"NFS-e pendente da DPS {entry['id_dps']}: a nota {found.chave_acesso} nao confere com o pedido. "
                    f"Conferir manualmente antes de emitir outra."
                )
            entry.update(status="emitida", chave_acesso=found.chave_acesso)
            self._log_service.save_nfse_log(log)
            raise InvoiceError(
                f"A NFS-e pendente da DPS {entry['id_dps']} foi emitida (chave {found.chave_acesso}). Nao emiti outra."
            )

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    def cancel_invoice(self, chave_acesso: str, motivo: str, descricao: str, confirmar: bool = False) -> dict:
        """Sem confirmar, só devolve a nota para conferência. Confirmado, envia o evento uma vez.

        Só cancela nota emitida por esta ferramenta (entrada `emitida` no log local)."""
        validar_cancelamento(motivo, descricao)
        log = self._log_service.load_nfse_log()
        entry = self._nota_emitida(log, chave_acesso)
        resumo = {
            "enviado": confirmar, "ambiente": self._sefin_config.environment, "numero": numero_nfse(chave_acesso),
            "tomador": entry.get("client_name"), "valor": entry.get("valor"),
            "competencia": entry.get("competencia"), "chave_acesso": chave_acesso,
        }
        if confirmar:
            if not self._invoice_provider.cancelamento_registrado(chave_acesso):
                self._enviar_cancelamento(chave_acesso, motivo, descricao)
            self._marcar_cancelada(log, entry, resumo, descricao)
        return resumo

    def _nota_emitida(self, log: list[dict], chave_acesso: str) -> dict:
        nacionais = (e for e in log if e.get("provider") == "sefin_nacional")
        entry = next((e for e in nacionais if e.get("chave_acesso") == chave_acesso), None)
        if entry is None:
            raise InvoiceError(f"A chave {chave_acesso} nao esta no log local: so cancelo nota emitida por esta ferramenta.")
        if entry.get("status") != "emitida":
            raise InvoiceError(f"A nota {chave_acesso} esta com status {entry.get('status')} no log, nao emitida.")
        return entry

    def _enviar_cancelamento(self, chave_acesso: str, motivo: str, descricao: str) -> None:
        """POST do evento, uma vez. Recusa sobe com o Complemento; resposta perdida só passa se o governo confirmar."""
        input_data = CancelServiceInvoiceInput(
            chave_acesso=chave_acesso, motivo_codigo=motivo, motivo_descricao=descricao,
            cnpj_autor=self._config.provider.cnpj, tipo_ambiente=self._sefin_config.tp_amb,
        )
        try:
            result = self._invoice_provider.cancel(input_data)
        except (ValidationError, CertificateError):
            raise  # nada chegou à SEFIN
        except ProviderError as exc:
            if _servidor_recusou(exc):
                raise InvoiceError(f"Cancelamento recusado: {exc.message}", errors=getattr(exc, "raw_errors", []))
            erro = exc
        else:
            if not result.success:
                raise InvoiceError("Cancelamento recusado pela SEFIN", errors=result.errors)
            return
        try:
            if self._invoice_provider.cancelamento_registrado(chave_acesso):
                return
        except ProviderError:
            pass  # não deu para saber: cai no aviso abaixo
        raise InvoiceError(
            f"Cancelamento da nota {chave_acesso} enviado sem resposta clara ({erro.message}). "
            "Nao marquei como cancelada: conferir na consulta antes de reenviar."
        )

    def _marcar_cancelada(self, log: list[dict], entry: dict, resumo: dict, descricao: str) -> None:
        entry["status"] = "cancelada"
        self._log_service.save_nfse_log(log)
        self._log_service.append_cancel_log({
            "nfse_number": resumo["numero"], "data_emissao": entry.get("date"),
            "data_cancelamento": self._today_str(), "valor": entry.get("valor"), "motivo_descricao": descricao,
            "client_name": entry.get("client_name"), "chave_acesso": resumo["chave_acesso"],
            "provider": "sefin_nacional",
        })

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_invoices(self, data_inicial: str = "", data_final: str = "") -> list[dict]:
        """NFS-e nacionais emitidas por esta ferramenta (log local) no período."""
        return nfse_nacionais(self._log_service.load_nfse_log(), data_inicial, data_final)

    def baixar_nfse(self, chave_acesso: str, pasta: str = "") -> dict:
        """Grava o XML da NFS-e (e o PDF, se o ADN devolver) em <pasta>/NFSe-<nNFSe>-<chave>.*"""
        if not CHAVE_NFSE.fullmatch(chave_acesso):
            raise InvoiceError(f"Chave de acesso fora do formato oficial (50 caracteres): {chave_acesso!r}")
        result = self._invoice_provider.query_by_access_key(chave_acesso)
        if not result.success or not result.xml_nfse:
            raise InvoiceError(f"A SEFIN nao devolveu o XML da chave {chave_acesso}", errors=result.errors)
        destino = Path(pasta) if pasta else self._config.data_dir / "xml"
        destino.mkdir(parents=True, exist_ok=True)
        numero = numero_nfse(chave_acesso)
        xml = destino / f"NFSe-{numero}-{chave_acesso}.xml"
        xml.write_text(result.xml_nfse)
        pdf_bytes = self._invoice_provider.danfse_pdf(chave_acesso)
        pdf = None
        if pdf_bytes:
            pdf = xml.with_suffix(".pdf")
            pdf.write_bytes(pdf_bytes)
        return {"numero": numero, "xml": str(xml), "pdf": pdf and str(pdf), "link": CONSULTA_PUBLICA}

    def query_by_access_key(self, chave_acesso: str):
        """Query an invoice by access key."""
        return self._invoice_provider.query_by_access_key(chave_acesso)

    def query_by_dps_id(self, dps_id: str):
        """Query an invoice by DPS identifier."""
        return self._invoice_provider.query_by_dps_id(dps_id)

    # ------------------------------------------------------------------
    # Municipal parameters
    # ------------------------------------------------------------------

    def get_agreement(self, codigo_municipio: str):
        """Get municipal agreement info."""
        return self._parameter_provider.get_agreement_by_municipality(codigo_municipio)

    def get_service_parameters(self, codigo_municipio: str, codigo_servico: str):
        """Get service tax parameters for a municipality."""
        return self._parameter_provider.get_service_parameters(codigo_municipio, codigo_servico)

    def query_parameters(self, command: QueryParametersCommand):
        """Query municipal parameters (convenio + optional service params).

        Returns dict with 'convenio' and optional 'service_params'.
        Raises ParameterError on failure.
        """
        try:
            convenio = self._parameter_provider.get_agreement_by_municipality(
                command.codigo_municipio
            )
            result = {"convenio": convenio}

            if command.codigo_servico:
                params = self._parameter_provider.get_service_parameters(
                    command.codigo_municipio, command.codigo_servico
                )
                result["service_params"] = params

            return result
        except Exception as e:
            raise ParameterError(f"Erro ao consultar parametros municipais: {e}")
