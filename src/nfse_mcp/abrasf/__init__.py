"""ABRASF 2.04 SOAP integration for ISS.net (Brasilia/DF)."""

from nfse_mcp.abrasf.xml_builder import (
    build_cabecalho,
    build_cancelar_nfse_envio,
    wrap_cancelar_nfse_envio,
    build_consultar_dados_cadastrais_envio,
    build_consultar_nfse_servico_prestado_envio,
    build_consultar_url_nfse_envio,
    build_enviar_lote_rps_sincrono,
    build_gerar_nfse_envio,
    build_inf_declaracao_xml,
)
from nfse_mcp.abrasf.soap_client import NfseResponse, SoapClient

__all__ = [
    "build_cabecalho",
    "build_cancelar_nfse_envio",
    "wrap_cancelar_nfse_envio",
    "build_consultar_dados_cadastrais_envio",
    "build_consultar_nfse_servico_prestado_envio",
    "build_consultar_url_nfse_envio",
    "build_enviar_lote_rps_sincrono",
    "build_gerar_nfse_envio",
    "build_inf_declaracao_xml",
    "NfseResponse",
    "SoapClient",
]
