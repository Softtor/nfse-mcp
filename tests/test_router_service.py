"""Tests for NfseRouterService fallback logic."""

from unittest.mock import MagicMock

import pytest

from nfse_mcp.application.dto.commands import IssueInvoiceCommand
from nfse_mcp.application.exceptions.application_error import InvoiceError
from nfse_mcp.application.services.router_service import (
    NfseRouterService,
    SUPPORTED_ABRASF_MUNICIPALITIES,
)
from nfse_mcp.errors import (
    MunicipalityNotEnabledError,
    MunicipalityNotSupportedError,
    SefinNacionalError,
)


def _make_cmd(codigo_municipio: str = "5300108") -> IssueInvoiceCommand:
    return IssueInvoiceCommand(
        client_document="12345678000195",
        valor="1000.00",
        discriminacao="Servico de teste",
        codigo_municipio=codigo_municipio,
    )


@pytest.fixture
def router():
    sefin = MagicMock()
    abrasf = MagicMock()
    data_loader = MagicMock()
    config = MagicMock()
    config.service_defaults.municipio_ibge = "5300108"
    return NfseRouterService(sefin, abrasf, data_loader, config)


class TestKnownOwnIssuer:
    """Municipality is known to maintain its own issuer."""

    def test_abrasf_supported(self, router: NfseRouterService):
        router._data_loader.is_emissor_proprio.return_value = True
        router._data_loader.is_emissor_nacional.return_value = False
        router._abrasf_service.issue_invoice.return_value = MagicMock(success=True)

        cmd = _make_cmd("5300108")
        result = router.issue_invoice(cmd)

        router._abrasf_service.issue_invoice.assert_called_once_with(cmd)
        router._sefin_service.issue_invoice.assert_not_called()
        assert result.success is True

    def test_abrasf_not_supported(self, router: NfseRouterService):
        router._data_loader.is_emissor_proprio.return_value = True
        router._data_loader.is_emissor_nacional.return_value = False

        cmd = _make_cmd("9999999")  # Not in SUPPORTED_ABRASF_MUNICIPALITIES
        with pytest.raises(InvoiceError, match="ainda nao esta disponivel"):
            router.issue_invoice(cmd)


class TestKnownNationalIssuer:
    """Municipality is known to use national public issuers."""

    def test_goes_to_sefin(self, router: NfseRouterService):
        router._data_loader.is_emissor_proprio.return_value = False
        router._data_loader.is_emissor_nacional.return_value = True
        router._sefin_service.issue_invoice.return_value = MagicMock(success=True)

        cmd = _make_cmd("3106200")
        result = router.issue_invoice(cmd)

        router._sefin_service.issue_invoice.assert_called_once_with(cmd)
        router._abrasf_service.issue_invoice.assert_not_called()
        assert result.success is True


class TestUnknownMunicipalityFallback:
    """Municipality is unknown — try SEFIN first, fallback to ABRASF on errors."""

    def test_sefin_success(self, router: NfseRouterService):
        router._data_loader.is_emissor_proprio.return_value = False
        router._data_loader.is_emissor_nacional.return_value = False
        router._sefin_service.issue_invoice.return_value = MagicMock(success=True)

        cmd = _make_cmd("3106200")
        result = router.issue_invoice(cmd)

        router._sefin_service.issue_invoice.assert_called_once_with(cmd)
        router._abrasf_service.issue_invoice.assert_not_called()
        assert result.success is True

    def test_e0039_fallback_to_abrasf(self, router: NfseRouterService):
        router._data_loader.is_emissor_proprio.return_value = False
        router._data_loader.is_emissor_nacional.return_value = False
        router._sefin_service.issue_invoice.side_effect = MunicipalityNotEnabledError("5300108")
        router._abrasf_service.issue_invoice.return_value = MagicMock(success=True)

        cmd = _make_cmd("5300108")
        result = router.issue_invoice(cmd)

        router._sefin_service.issue_invoice.assert_called_once_with(cmd)
        router._abrasf_service.issue_invoice.assert_called_once_with(cmd)
        assert result.success is True

    def test_e0039_no_abrasf_support(self, router: NfseRouterService):
        router._data_loader.is_emissor_proprio.return_value = False
        router._data_loader.is_emissor_nacional.return_value = False
        router._sefin_service.issue_invoice.side_effect = MunicipalityNotEnabledError("9999999")

        cmd = _make_cmd("9999999")
        with pytest.raises(InvoiceError, match="ainda nao esta disponivel"):
            router.issue_invoice(cmd)

    def test_not_supported_fallback_to_abrasf(self, router: NfseRouterService):
        router._data_loader.is_emissor_proprio.return_value = False
        router._data_loader.is_emissor_nacional.return_value = False
        router._sefin_service.issue_invoice.side_effect = MunicipalityNotSupportedError("5300108")
        router._abrasf_service.issue_invoice.return_value = MagicMock(success=True)

        cmd = _make_cmd("5300108")
        result = router.issue_invoice(cmd)

        router._abrasf_service.issue_invoice.assert_called_once_with(cmd)
        assert result.success is True

    def test_not_supported_no_abrasf_support(self, router: NfseRouterService):
        router._data_loader.is_emissor_proprio.return_value = False
        router._data_loader.is_emissor_nacional.return_value = False
        router._sefin_service.issue_invoice.side_effect = MunicipalityNotSupportedError("9999999")

        cmd = _make_cmd("9999999")
        with pytest.raises(InvoiceError, match="nao aderiu ao Sistema Nacional NFS-e"):
            router.issue_invoice(cmd)

    def test_other_sefin_error_fallback_to_abrasf(self, router: NfseRouterService):
        router._data_loader.is_emissor_proprio.return_value = False
        router._data_loader.is_emissor_nacional.return_value = False
        router._sefin_service.issue_invoice.side_effect = SefinNacionalError("Timeout", code="TIMEOUT")
        router._abrasf_service.issue_invoice.return_value = MagicMock(success=True)

        cmd = _make_cmd("5300108")
        result = router.issue_invoice(cmd)

        router._abrasf_service.issue_invoice.assert_called_once_with(cmd)
        assert result.success is True

    def test_other_sefin_error_no_abrasf_support(self, router: NfseRouterService):
        router._data_loader.is_emissor_proprio.return_value = False
        router._data_loader.is_emissor_nacional.return_value = False
        router._sefin_service.issue_invoice.side_effect = SefinNacionalError("Timeout", code="TIMEOUT")

        cmd = _make_cmd("9999999")
        with pytest.raises(InvoiceError, match="Erro no SEFIN Nacional"):
            router.issue_invoice(cmd)


class TestSupportedAbrasfSet:
    """Verify the hard-coded ABRASF support set."""

    def test_brasilia_is_supported(self):
        assert "5300108" in SUPPORTED_ABRASF_MUNICIPALITIES

    def test_random_municipality_not_supported(self):
        assert "9999999" not in SUPPORTED_ABRASF_MUNICIPALITIES


def test_container_nao_monta_o_abrasf_quando_o_roteador_escolhe_a_sefin(monkeypatch):
    from nfse_mcp.presentation.mcp.container import ServiceContainer

    c = ServiceContainer()
    montou_abrasf = []
    monkeypatch.setattr(c, "abrasf_service", lambda: montou_abrasf.append(1))
    monkeypatch.setattr(c, "sefin_service", lambda: object())
    monkeypatch.setattr(c, "config", lambda: object())
    c.router_service()
    assert montou_abrasf == []  # sem NFSE_CERTIFICATE_PATH, só a SEFIN continua emitindo
