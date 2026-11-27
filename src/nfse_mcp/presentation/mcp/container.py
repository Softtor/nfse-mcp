"""Dependency injection container for MCP layer.

Encapsulates lazy initialization of all application services and infrastructure.
This can be reused by a future FastAPI layer by creating a similar container.
"""

from typing import Optional

from nfse_mcp.certificate import Certificate
from nfse_mcp.client_store import ClientStore
from nfse_mcp.config import Config, load_config
from nfse_mcp.xml_signer import XmlSigner
from nfse_mcp.abrasf.soap_client import SoapClient
from nfse_mcp.sefin_nacional import SefinNacionalConfig, SefinNacionalProvider, load_sefin_config

from nfse_mcp.application.services.client_service import ClientApplicationService
from nfse_mcp.application.services.invoice_log_service import InvoiceLogService
from nfse_mcp.application.services.abrasf_service import AbrasfApplicationService
from nfse_mcp.application.services.sefin_nacional_service import SefinNacionalApplicationService
from nfse_mcp.application.services.router_service import NfseRouterService


class ServiceContainer:
    """Lazy-initialized service container."""

    def __init__(self):
        self._config: Optional[Config] = None
        self._cert: Optional[Certificate] = None
        self._signer: Optional[XmlSigner] = None
        self._soap: Optional[SoapClient] = None
        self._store: Optional[ClientStore] = None
        self._log_service: Optional[InvoiceLogService] = None
        self._client_service: Optional[ClientApplicationService] = None
        self._abrasf_service: Optional[AbrasfApplicationService] = None

        self._sefin_config: Optional[SefinNacionalConfig] = None
        self._sefin_cert: Optional[Certificate] = None
        self._sefin_provider: Optional[SefinNacionalProvider] = None
        self._sefin_service: Optional[SefinNacionalApplicationService] = None
        self._router_service: Optional[NfseRouterService] = None

    # ------------------------------------------------------------------
    # Shared infrastructure
    # ------------------------------------------------------------------

    def config(self) -> Config:
        if self._config is None:
            self._config = load_config()
        return self._config

    def cert(self) -> Certificate:
        if self._cert is None:
            self._cert = Certificate(self.config().certificate_path, self.config().certificate_password)
        return self._cert

    def signer(self) -> XmlSigner:
        if self._signer is None:
            self._signer = XmlSigner(self.cert())
        return self._signer

    def soap(self) -> SoapClient:
        if self._soap is None:
            self._soap = SoapClient(self.config(), self.cert())
        return self._soap

    def store(self) -> ClientStore:
        if self._store is None:
            self._store = ClientStore(self.config().data_dir)
        return self._store

    def log_service(self) -> InvoiceLogService:
        if self._log_service is None:
            self._log_service = InvoiceLogService(self.config().data_dir)
        return self._log_service

    # ------------------------------------------------------------------
    # Application services
    # ------------------------------------------------------------------

    def client_service(self) -> ClientApplicationService:
        if self._client_service is None:
            self._client_service = ClientApplicationService(self.store())
        return self._client_service

    def abrasf_service(self) -> AbrasfApplicationService:
        if self._abrasf_service is None:
            self._abrasf_service = AbrasfApplicationService(
                client_service=self.client_service(),
                config=self.config(),
                cert=self.cert(),
                signer=self.signer(),
                soap=self.soap(),
                log_service=self.log_service(),
            )
        return self._abrasf_service

    # ------------------------------------------------------------------
    # SEFIN Nacional
    # ------------------------------------------------------------------

    def sefin_config(self) -> SefinNacionalConfig:
        if self._sefin_config is None:
            self._sefin_config = load_sefin_config()
        return self._sefin_config

    def sefin_cert(self) -> Certificate:
        if self._sefin_cert is None:
            self._sefin_cert = Certificate(
                self.sefin_config().certificate_path,
                self.sefin_config().certificate_password,
            )
        return self._sefin_cert

    def sefin_provider(self) -> SefinNacionalProvider:
        if self._sefin_provider is None:
            self._sefin_provider = SefinNacionalProvider(
                self.sefin_config(),
                self.sefin_cert(),
            )
        return self._sefin_provider

    def sefin_service(self) -> SefinNacionalApplicationService:
        if self._sefin_service is None:
            self._sefin_service = SefinNacionalApplicationService(
                client_service=self.client_service(),
                invoice_provider=self.sefin_provider(),
                parameter_provider=self.sefin_provider(),
                config=self.config(),
                sefin_config=self.sefin_config(),
                log_service=self.log_service(),
            )
        return self._sefin_service

    def router_service(self) -> NfseRouterService:
        if self._router_service is None:
            from nfse_mcp.sefin_nacional.municipality_data import MunicipalityDataLoader
            self._router_service = NfseRouterService(
                sefin_service=self.sefin_service(),
                abrasf_service=self.abrasf_service(),
                data_loader=MunicipalityDataLoader(),
                config=self.config(),
            )
        return self._router_service


# Global singleton container (appropriate for MCP stdio single-process model)
container = ServiceContainer()
