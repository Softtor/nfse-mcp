import json
import uuid
from pathlib import Path
from nfse_mcp.models import Client
from nfse_mcp.cnpj_lookup import lookup_cnpj, clean_document


class ClientStore:
    """Manages client (tomador) data in a local JSON file."""

    def __init__(self, data_dir: Path):
        self._file = data_dir / "clients.json"
        self._ensure_file()

    def _ensure_file(self):
        if not self._file.exists():
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text("[]")

    def _load(self) -> list[dict]:
        return json.loads(self._file.read_text())

    def _save(self, clients: list[dict]):
        self._file.write_text(json.dumps(clients, indent=2, ensure_ascii=False))

    def list_all(self) -> list[Client]:
        data = self._load()
        return [Client(**c) for c in data]

    def find_by_document(self, document: str) -> Client | None:
        doc_clean = clean_document(document)
        for c in self._load():
            if clean_document(c["document"]) == doc_clean:
                return Client(**c)
        return None

    def find_by_id(self, client_id: str) -> Client | None:
        for c in self._load():
            if c["id"] == client_id:
                return Client(**c)
        return None

    def register(
        self,
        document: str,
        razao_social: str | None = None,
        auto_lookup: bool = True,
        **kwargs,
    ) -> Client:
        """
        Register a client. If auto_lookup=True and document is CNPJ,
        will fetch data from BrasilAPI automatically.
        """
        doc_clean = clean_document(document)

        # Check if already exists
        existing = self.find_by_document(doc_clean)
        if existing:
            return existing

        doc_type = "cnpj" if len(doc_clean) == 14 else "cpf"

        # Auto-lookup CNPJ data
        lookup_data = {}
        if auto_lookup and doc_type == "cnpj":
            result = lookup_cnpj(doc_clean)
            if result:
                lookup_data = {
                    "razao_social": result["razao_social"],
                    "nome_fantasia": result["nome_fantasia"],
                    "endereco": result["logradouro"],
                    "numero": result["numero"],
                    "complemento": result["complemento"],
                    "bairro": result["bairro"],
                    "codigo_municipio": result["codigo_municipio_ibge"],
                    "uf": result["uf"],
                    "cep": result["cep"],
                    "telefone": result["telefone"],
                    "email": result["email"],
                }

        # Merge: explicit kwargs override lookup data
        client_data = {
            "id": str(uuid.uuid4()),
            "document": doc_clean,
            "document_type": doc_type,
            "razao_social": razao_social or lookup_data.get("razao_social", ""),
            **{k: v for k, v in lookup_data.items() if k != "razao_social"},
            **{k: v for k, v in kwargs.items() if v is not None},
        }

        client = Client(**client_data)

        clients = self._load()
        clients.append(vars(client))
        self._save(clients)

        return client

    def update(self, client_id: str, **kwargs) -> Client | None:
        clients = self._load()
        for i, c in enumerate(clients):
            if c["id"] == client_id:
                c.update({k: v for k, v in kwargs.items() if v is not None})
                clients[i] = c
                self._save(clients)
                return Client(**c)
        return None

    def delete(self, client_id: str) -> bool:
        clients = self._load()
        new_clients = [c for c in clients if c["id"] != client_id]
        if len(new_clients) == len(clients):
            return False
        self._save(new_clients)
        return True
