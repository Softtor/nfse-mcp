"""Tests for MunicipalityDataLoader."""

from pathlib import Path

import pytest

from nfse_mcp.sefin_nacional.municipality_data import MunicipalityDataLoader


@pytest.fixture
def loader(tmp_path: Path):
    return MunicipalityDataLoader(snapshot_path=tmp_path / "municipality_snapshot.json")


class TestMunicipalityDataLoader:
    def test_get_status_missing_returns_none(self, loader: MunicipalityDataLoader):
        assert loader.get_status("5300108") is None

    def test_is_emissor_nacional_missing_returns_false(self, loader: MunicipalityDataLoader):
        assert loader.is_emissor_nacional("9999999") is False

    def test_refresh_from_csv(self, tmp_path: Path):
        csv_path = tmp_path / "municipios.csv"
        csv_path.write_text(
            "codigo_ibge,nome,uf,conveniado,emissor_nacional\n"
            "5300108,Brasilia,DF,True,False\n"
            "3550308,Sao Paulo,SP,True,True\n",
            encoding="utf-8",
        )
        loader = MunicipalityDataLoader(snapshot_path=tmp_path / "snap.json")
        loader.refresh_from_csv(csv_path)

        sp = loader.get_status("3550308")
        assert sp is not None
        assert sp.nome == "Sao Paulo"
        assert sp.uf == "SP"
        assert sp.conveniado is True
        assert sp.emissor_nacional is True

        df = loader.get_status("5300108")
        assert df is not None
        assert df.emissor_nacional is False

        # Persistence
        loader2 = MunicipalityDataLoader(snapshot_path=tmp_path / "snap.json")
        assert loader2.get_status("3550308") is not None

    def test_brasilia_emite_pelo_nacional(self, loader: MunicipalityDataLoader):
        # Desde 11/2026 o ISS.net recusa optante do Simples (L120): Brasília vai pelo nacional
        assert loader.is_emissor_nacional("5300108") is True
        assert loader.is_emissor_nacional("005300108") is True  # zero-padded
        assert loader.is_emissor_proprio("5300108") is False
        assert loader.determine_best_provider("5300108") == "sefin"

    def test_is_emissor_proprio_from_external_data(self, tmp_path: Path):
        csv_path = tmp_path / "municipios.csv"
        csv_path.write_text(
            "codigo_ibge,nome,uf,conveniado,emissor_nacional\n"
            "3106200,Belo Horizonte,MG,True,False\n",
            encoding="utf-8",
        )
        loader = MunicipalityDataLoader(snapshot_path=tmp_path / "snap.json")
        loader.refresh_from_csv(csv_path)
        assert loader.is_emissor_proprio("3106200") is True

    def test_is_emissor_proprio_unknown(self, loader: MunicipalityDataLoader):
        assert loader.is_emissor_proprio("9999999") is False


def test_emissor_nacional_pelos_dados_externos(tmp_path):
    csv_path = tmp_path / "municipios.csv"
    csv_path.write_text(
        "codigo_ibge,nome,uf,conveniado,emissor_nacional\n3550308,Sao Paulo,SP,True,True\n",
        encoding="utf-8",
    )
    loader = MunicipalityDataLoader(snapshot_path=tmp_path / "snap.json")
    loader.refresh_from_csv(csv_path)
    assert loader.is_emissor_nacional("3550308") is True
    assert loader.is_emissor_nacional("9999999") is False
