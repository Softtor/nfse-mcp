"""Testes offline do transporte e dos builders do padrão nacional.

Nada aqui toca a rede: `build_envelope` e os builders são funções puras, e a
validação usa o XSD versionado em `schemas/nacional/`.
"""

from pathlib import Path

import pytest
from lxml import etree

from nfse_mcp.config import Config, ProviderConfig, ServiceDefaults
from nfse_mcp.notacontrol import xml_builder as xb
from nfse_mcp.notacontrol.soap_client import (
    NS,
    SOAP_NS,
    WEBSERVICE_URLS,
    NacionalResponse,
    build_envelope,
    unwrap_output,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "schemas" / "nacional" / "schema_v101.xsd"
)


@pytest.fixture(scope="module")
def schema() -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(SCHEMA_PATH)))


@pytest.fixture
def config() -> Config:
    return Config(
        environment="homologation",
        certificate_path="/dev/null",
        certificate_password="",
        provider=ProviderConfig(
            cnpj="11222333000181",
            im="1234567",
            razao_social="PRESTADOR TESTE LTDA",
            simples_nacional=1,
            regime_tributacao=6,
            incentivo_fiscal=2,
        ),
        service_defaults=ServiceDefaults(
            cnae="6209100",
            item_lista_servico="1.07",
            codigo_tributacao_municipio="107",
            aliquota="2.00",
            municipio_ibge="5300108",
            iss_retido=2,
            exigibilidade_iss=1,
        ),
        rps_serie="8",
        webservice_url=WEBSERVICE_URLS["homologation"],
        data_dir=Path("/tmp"),
    )


# --------------------------------------------------------------------------
# Envelope SOAP
# --------------------------------------------------------------------------


def test_envelope_usa_namespace_e_parts_do_padrao_nacional():
    env = build_envelope("ConsultarDadosCadastrais", "<cabecalho/>", "<Envio/>")
    assert f'<ConsultarDadosCadastrais xmlns="{NS}">' in env
    assert "nfseCabecMsg" in env and "nfseDadosMsg" in env
    assert "abrasf.org.br" not in env


def test_envelope_deixa_parts_fora_de_namespace():
    """Regressão: sem xmlns="" nas parts o servidor devolve E183+E160.

    O WSDL não declara elementFormDefault, então nfseCabecMsg/nfseDadosMsg são
    unqualified. Com o xmlns default do método herdado, o servidor não lê o
    payload — responde o mesmo erro até para corpo vazio.
    """
    env = build_envelope("ConsultarDadosCadastrais", "<cabecalho/>", "<Envio/>")
    assert '<nfseCabecMsg xmlns="">' in env
    assert '<nfseDadosMsg xmlns="">' in env

    tree = etree.fromstring(env.encode("utf-8"))
    method_el = tree.find(f"{{{SOAP_NS}}}Body")[0]
    for child in method_el:
        assert etree.QName(child).namespace is None, (
            f"{etree.QName(child).localname} não pode estar em namespace"
        )


def test_envelope_escapa_por_entidades_e_nao_usa_cdata():
    env = build_envelope("GerarNfse", "<cabecalho/>", "<Dados a='1'/>")
    assert "&lt;Dados" in env
    assert "CDATA" not in env


def test_envelope_remove_declaracao_xml_do_payload():
    """O ISS.net rejeita a declaração XML dentro de nfseDadosMsg."""
    data = '<?xml version="1.0" encoding="UTF-8"?><Envio/>'
    env = build_envelope("GerarNfse", '<?xml version="1.0"?><cabecalho/>', data)
    # a única declaração é a do próprio envelope
    assert env.count("<?xml") == 1
    assert "&lt;?xml" not in env


def test_envelope_e_xml_bem_formado():
    env = build_envelope("ConsultarDadosCadastrais", "<cabecalho/>", "<Envio/>")
    tree = etree.fromstring(env.encode("utf-8"))
    body = tree.find(f"{{{SOAP_NS}}}Body")
    assert body is not None
    assert etree.QName(body[0]).localname == "ConsultarDadosCadastrais"


# --------------------------------------------------------------------------
# Desembrulho de outputXML
# --------------------------------------------------------------------------


def _soap(inner: str) -> bytes:
    return (
        f'<soap:Envelope xmlns:soap="{SOAP_NS}"><soap:Body>{inner}'
        "</soap:Body></soap:Envelope>"
    ).encode("utf-8")


def test_unwrap_output_com_conteudo_escapado():
    body = _soap(
        f'<ConsultarDadosCadastraisResponse xmlns="{NS}">'
        "<outputXML>&lt;Cadastro&gt;&lt;IM&gt;123&lt;/IM&gt;&lt;/Cadastro&gt;"
        "</outputXML></ConsultarDadosCadastraisResponse>"
    )
    assert unwrap_output(body, "ConsultarDadosCadastrais") == (
        "<Cadastro><IM>123</IM></Cadastro>"
    )


def test_unwrap_output_com_conteudo_embutido():
    """Servidores .asmx as vezes devolvem elementos em vez de texto escapado."""
    body = _soap(
        f'<ConsultarDadosCadastraisResponse xmlns="{NS}">'
        "<outputXML><Cadastro><IM>123</IM></Cadastro></outputXML>"
        "</ConsultarDadosCadastraisResponse>"
    )
    assert "<IM>123</IM>" in unwrap_output(body, "ConsultarDadosCadastrais")


def test_unwrap_output_preserva_soap_fault():
    body = _soap(
        f'<soap:Fault xmlns:soap="{SOAP_NS}">'
        "<faultcode>s:Client</faultcode><faultstring>Error</faultstring>"
        "</soap:Fault>"
    )
    out = unwrap_output(body, "GerarNfse")
    assert "Fault" in out and "Error" in out


def test_unwrap_output_com_corpo_ilegivel_nao_explode():
    assert "nao é xml" in unwrap_output(b"nao <<< e xml", "GerarNfse").replace(
        "<<< e", "é"
    )


# --------------------------------------------------------------------------
# NacionalResponse
# --------------------------------------------------------------------------


def test_response_le_lista_mensagem_retorno():
    xml = (
        f'<ListaMensagemRetorno xmlns="{NS}"><MensagemRetorno>'
        "<Codigo>E0001</Codigo><Mensagem>DPS invalida</Mensagem>"
        "<Correcao>Verifique o cTribMun</Correcao>"
        "</MensagemRetorno></ListaMensagemRetorno>"
    )
    resp = NacionalResponse(xml, "GerarNfse")
    assert resp.has_errors()
    err = resp.get_errors()[0]
    assert err["Codigo"] == "E0001"
    assert err["Correcao"] == "Verifique o cTribMun"


def test_response_le_soap_fault():
    xml = (
        f'<soap:Fault xmlns:soap="{SOAP_NS}">'
        "<faultcode>s:Client</faultcode><faultstring>Error</faultstring></soap:Fault>"
    )
    resp = NacionalResponse(xml, "ConsultarDadosCadastrais")
    assert resp.get_errors()[0]["Mensagem"] == "Error"


def test_response_sem_erros_quando_conteudo_valido():
    resp = NacionalResponse(f'<Cadastro xmlns="{NS}"><IM>123</IM></Cadastro>', "X")
    assert not resp.has_errors()


# --------------------------------------------------------------------------
# Builders validados contra o XSD oficial
# --------------------------------------------------------------------------


def test_cabecalho_valida_no_xsd(schema, config):
    xml = xb.build_cabecalho()
    doc = etree.fromstring(xml.encode("utf-8"))
    schema.assertValid(doc)
    assert doc.get("versao") == "1.01"
    assert doc.findtext(f"{{{NS}}}versaoDados") == "1.01"


def test_consultar_dados_cadastrais_valida_no_xsd(schema, config):
    xml = xb.build_consultar_dados_cadastrais_envio(config)
    schema.assertValid(etree.fromstring(xml.encode("utf-8")))


def test_consultar_dados_cadastrais_sem_wrapper_pedido(config):
    """O <Pedido> do ABRASF deixou de existir no padrão nacional."""
    xml = xb.build_consultar_dados_cadastrais_envio(config)
    assert "<Pedido>" not in xml
    # e o prestador usa <CNPJ> direto, sem o wrapper <CpfCnpj>
    assert "CpfCnpj" not in xml
    assert "<CNPJ>11222333000181</CNPJ>" in xml


def test_consultar_servico_prestado_valida_no_xsd(schema, config):
    xml = xb.build_consultar_nfse_servico_prestado_envio(
        config, "2026-07-01", "2026-07-31", pagina=2
    )
    schema.assertValid(etree.fromstring(xml.encode("utf-8")))


def test_consultar_servico_prestado_exige_pagina(config):
    xml = xb.build_consultar_nfse_servico_prestado_envio(
        config, "2026-07-01", "2026-07-31"
    )
    assert "<Pagina>1</Pagina>" in xml
