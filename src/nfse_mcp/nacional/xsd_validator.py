"""Validação XSD de documentos do padrão nacional NFS-e (DPS e eventos)."""

from pathlib import Path
from typing import Optional

from lxml import etree

from nfse_mcp.nacional.dps_xml_builder import LEIAUTE_POR_TPAMB



# Schemas versionados no repositório (schemas/nacional/).
# Path relativo ao pacote — nunca absoluto de máquina de dev.
DEFAULT_SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "schemas" / "nacional"
# Esquemas oficiais da Receita, um por leiaute (tpAmb), em schemas/nacional/oficial-*:
# oficial-20261020 = esquemas_prod_restrita_20261020.zip, sem alteração.
# oficial-20260209 = nfse-esquemas_xsd-v1-01-20260209.zip (pasta 1.01) com ^/$ tirados dos patterns:
# em XSD eles são literais e o lxml recusaria toda série/data; o servidor (.NET) os trata como âncoras.


class XsdValidator:
    """Valida DPS e pedidos de evento contra o esquema oficial do leiaute do tpAmb do documento."""

    def __init__(self, schemas_dir: Optional[Path] = None):
        self.schemas_dir = schemas_dir or DEFAULT_SCHEMAS_DIR
        self._schemas: dict[Path, etree.XMLSchema] = {}

    def _validate_oficial(self, xml_string: str, arquivo: str) -> list[str]:
        try:
            doc = etree.fromstring(xml_string.encode("utf-8"))
        except etree.XMLSyntaxError as exc:
            return [f"XML syntax error: {exc}"]
        tp_amb = int(doc.xpath("string(//*[local-name()='tpAmb'])") or 2)
        path = self.schemas_dir / LEIAUTE_POR_TPAMB[tp_amb] / arquivo
        if path not in self._schemas:
            self._schemas[path] = etree.XMLSchema(etree.parse(str(path)))
        schema = self._schemas[path]
        if schema.validate(doc):
            return []
        return [str(e) for e in schema.error_log]

    def validate_dps(self, xml_string: str) -> list[str]:
        """Valida um DPS. Retorna lista de erros (vazia se válido)."""
        return self._validate_oficial(xml_string, "DPS_v1.01.xsd")

    def validate_evento(self, xml_string: str) -> list[str]:
        """Valida um pedido de registro de evento. Retorna lista de erros."""
        return self._validate_oficial(xml_string, "pedRegEvento_v1.01.xsd")
