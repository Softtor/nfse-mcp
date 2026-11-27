"""Client (tomador) application service.

Handles client registration, lookup, address completion, and listing.
Independent of transport layer (MCP, HTTP, CLI).
"""

from nfse_mcp.models import Client
from nfse_mcp.client_store import ClientStore
from nfse_mcp.cnpj_lookup import lookup_cnpj, clean_document


class ClientApplicationService:
    """Application service for client management."""

    def __init__(self, store: ClientStore):
        self._store = store

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def lookup_cnpj_data(self, cnpj: str) -> dict | None:
        """Look up company data by CNPJ via BrasilAPI."""
        doc = clean_document(cnpj)
        if len(doc) != 14:
            return None
        return lookup_cnpj(doc)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_client(
        self,
        document: str,
        razao_social: str = "",
        auto_lookup: bool = True,
    ) -> Client:
        """Register a client. If already exists, returns existing."""
        doc = clean_document(document)
        return self._store.register(
            document=doc,
            razao_social=razao_social or None,
            auto_lookup=auto_lookup,
        )

    def find_or_register_client(self, document: str) -> Client:
        """Find existing client or auto-register by document."""
        doc_clean = clean_document(document)
        client = self._store.find_by_document(doc_clean)
        if client is None:
            client = self._store.register(doc_clean, auto_lookup=True)
        return client

    # ------------------------------------------------------------------
    # Address completion
    # ------------------------------------------------------------------

    def ensure_complete_address(self, client: Client) -> Client:
        """Ensure client has all required address fields.

        If fields are missing, tries BrasilAPI lookup (CNPJ only).
        Falls back to defaults for remaining gaps and persists updates.
        """
        required = [
            client.endereco,
            client.numero,
            client.bairro,
            client.codigo_municipio,
            client.uf,
            client.cep,
        ]

        if all(required):
            return client

        # Try BrasilAPI lookup if CNPJ
        if client.document_type == "cnpj" and len(client.document) == 14:
            result = lookup_cnpj(client.document)
            if result:
                if not client.endereco:
                    client.endereco = result.get("logradouro") or None
                if not client.numero:
                    client.numero = result.get("numero") or None
                if not client.bairro:
                    client.bairro = result.get("bairro") or None
                if not client.codigo_municipio:
                    client.codigo_municipio = result.get("codigo_municipio_ibge") or None
                if not client.uf:
                    client.uf = result.get("uf") or None
                if not client.cep:
                    client.cep = result.get("cep") or None

        # Fill remaining gaps with defaults
        if not client.endereco:
            client.endereco = "Rua Nao Informada"
        if not client.numero:
            client.numero = "SN"
        if not client.bairro:
            client.bairro = "Nao Informado"
        if not client.codigo_municipio:
            client.codigo_municipio = "5300108"  # Brasilia
        if not client.uf:
            client.uf = "DF"
        if not client.cep:
            client.cep = "70000000"

        # Persist updates
        self._store.update(
            client.id,
            endereco=client.endereco,
            numero=client.numero,
            bairro=client.bairro,
            codigo_municipio=client.codigo_municipio,
            uf=client.uf,
            cep=client.cep,
        )

        return client

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_clients(self) -> list[Client]:
        """List all registered clients."""
        return self._store.list_all()

    def find_by_document(self, document: str) -> Client | None:
        """Find a client by document number."""
        return self._store.find_by_document(clean_document(document))
