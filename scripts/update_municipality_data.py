#!/usr/bin/env python3
"""Script to update the local municipality snapshot from official sources.

Usage:
    python scripts/update_municipality_data.py [path/to/downloaded.csv]

If no CSV path is provided, the script attempts to download the latest list
from the official Receita Federal portal. If that fails, it prints instructions
for manual download.
"""

import argparse
import sys
from pathlib import Path

# Add src to path so we can import nfse_mcp
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from nfse_mcp.sefin_nacional.municipality_data import MunicipalityDataLoader

OFFICIAL_URL = "https://www.gov.br/nfse/pt-br/municipios/municipios-aderentes"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update municipality snapshot for NFS-e national system",
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        help="Path to a manually-downloaded CSV from the official portal",
    )
    args = parser.parse_args()

    loader = MunicipalityDataLoader()

    if args.csv_file:
        csv_path = Path(args.csv_file)
        if not csv_path.exists():
            print(f"ERROR: File not found: {csv_path}", file=sys.stderr)
            return 1
        loader.refresh_from_csv(csv_path)
        print(f"Updated snapshot with {len(loader._data)} municipalities from {csv_path}")
        return 0

    # Attempt auto-download (best-effort; gov.br blocks scraping sometimes)
    print("Attempting auto-download from official portal...")
    print(f"URL: {OFFICIAL_URL}")
    print()
    print("If automatic download fails, follow these steps:")
    print(f"1. Open {OFFICIAL_URL} in your browser")
    print("2. Click the link to download the spreadsheet (usually Excel or CSV)")
    print("3. If the file is Excel, save/export it as CSV with columns:")
    print("   codigo_ibge, nome, uf, conveniado, emissor_nacional")
    print("4. Run: python scripts/update_municipality_data.py /path/to/file.csv")
    print()
    print("Current snapshot size:", len(loader._data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
