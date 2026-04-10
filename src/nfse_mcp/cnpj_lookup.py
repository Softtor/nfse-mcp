import requests
import re


# UF code to IBGE state code mapping
UF_TO_IBGE = {
    "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
    "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
    "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
    "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
    "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
    "SE": "28", "TO": "17",
}


def clean_document(doc: str) -> str:
    """Remove formatting from CNPJ/CPF."""
    return re.sub(r"[^0-9]", "", doc)


def lookup_cnpj(cnpj: str) -> dict | None:
    """
    Look up company data by CNPJ via BrasilAPI.

    Returns dict with keys:
        razao_social, nome_fantasia, logradouro, numero, complemento,
        bairro, municipio, uf, cep, telefone, email, codigo_municipio_ibge,
        cnae_fiscal, cnae_fiscal_descricao, situacao_cadastral

    Returns None if not found or error.
    """
    cnpj_clean = clean_document(cnpj)
    if len(cnpj_clean) != 14:
        return None

    try:
        resp = requests.get(
            f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_clean}",
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()

        # Build municipality IBGE code (7 digits)
        codigo_municipio = str(data.get("codigo_municipio_ibge", "") or data.get("codigo_municipio", ""))

        return {
            "cnpj": cnpj_clean,
            "razao_social": data.get("razao_social", ""),
            "nome_fantasia": data.get("nome_fantasia", ""),
            "logradouro": f"{data.get('descricao_tipo_de_logradouro', '')} {data.get('logradouro', '')}".strip(),
            "numero": data.get("numero", ""),
            "complemento": data.get("complemento", ""),
            "bairro": data.get("bairro", ""),
            "municipio": data.get("municipio", ""),
            "uf": data.get("uf", ""),
            "cep": clean_document(str(data.get("cep", ""))),
            "telefone": data.get("ddd_telefone_1", ""),
            "email": data.get("email", "") if data.get("email") else "",
            "codigo_municipio_ibge": codigo_municipio,
            "cnae_fiscal": str(data.get("cnae_fiscal", "")),
            "cnae_fiscal_descricao": data.get("cnae_fiscal_descricao", ""),
            "situacao_cadastral": data.get("descricao_situacao_cadastral", ""),
        }
    except Exception:
        return None
