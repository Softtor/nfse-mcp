"""Lookup de alíquota de ISS pela tabela oficial de Brasília.

Fonte: Relacionamento - CNAE x LS x Atividade (ISS Brasília / ABRASF 2.04)
Chave: (XML_CodigoCnae, XML_CodigoTributacaoMunicipio) → alíquota percentual (ex: "2.00")
"""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

_NS = {"ns": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# Resolved once at module level; None means not yet loaded.
_TABLE: dict[tuple[str, str], str] | None = None


def _col_index(ref: str) -> int:
    """Convert Excel column letter(s) to 0-based index (A=0, B=1, ...)."""
    col = ""
    for ch in ref:
        if ch.isalpha():
            col += ch
        else:
            break
    result = 0
    for ch in col.upper():
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result - 1


def _load_table(xlsx_path: Path) -> dict[tuple[str, str], str]:
    table: dict[tuple[str, str], str] = {}

    with zipfile.ZipFile(xlsx_path) as z:
        # Load shared strings
        shared: list[str] = []
        ss_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in ss_root.findall("ns:si", _NS):
            t = si.find("ns:t", _NS)
            if t is not None:
                shared.append(t.text or "")
            else:
                parts = [
                    r.find("ns:t", _NS).text or ""
                    for r in si.findall("ns:r", _NS)
                    if r.find("ns:t", _NS) is not None
                ]
                shared.append("".join(parts))

        # Parse sheet1 — columns: A=cnae, E=cod_trib, G=aliquota
        ws_root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        for row in ws_root.findall(".//ns:row", _NS):
            cells: dict[int, str] = {}
            for c in row.findall("ns:c", _NS):
                ref = c.get("r", "")
                idx = _col_index(ref)
                t_attr = c.get("t")
                v_el = c.find("ns:v", _NS)
                if v_el is None:
                    cells[idx] = ""
                    continue
                if t_attr == "s":
                    cells[idx] = shared[int(v_el.text)]
                else:
                    cells[idx] = v_el.text or ""

            cnae = cells.get(0, "").strip()      # col A
            cod_trib = cells.get(4, "").strip()  # col E
            aliq_raw = cells.get(6, "").strip()  # col G

            if not cnae or not cod_trib or not aliq_raw or cnae == "XML_CodigoCnae":
                continue  # skip header and incomplete rows

            try:
                aliq_pct = float(aliq_raw) * 100
                table[(cnae, cod_trib)] = f"{aliq_pct:.2f}"
            except ValueError:
                pass

    return table


def _get_table() -> dict[tuple[str, str], str]:
    global _TABLE
    if _TABLE is None:
        # Look for the XLSX at the project root (2 levels above src/nfse_mcp/)
        xlsx_name = "Relacionamento - CNAE x LS x Atividade_v.6 (30032023).xlsx"
        candidates = [
            Path(__file__).parent.parent.parent / xlsx_name,
            Path.cwd() / xlsx_name,
        ]
        for path in candidates:
            if path.exists():
                _TABLE = _load_table(path)
                break
        else:
            _TABLE = {}  # file not found — use empty table (fallback to config)
    return _TABLE


def lookup_aliquota(cnae: str, cod_trib: str) -> str | None:
    """Return ISS aliquota as percentage string (e.g. '2.00') or None if not found.

    Args:
        cnae: CNAE code without mask (e.g. '6209100').
        cod_trib: CodigoTributacaoMunicipio (e.g. '107').
    """
    return _get_table().get((cnae.strip(), cod_trib.strip()))
