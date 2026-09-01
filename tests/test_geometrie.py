"""Tests du chargement d'emprise : ZIP, CRS, multi-polygones."""

from __future__ import annotations

import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from dp_socle.erreurs import ErreurCRS, ErreurEmprise
from dp_socle.geometrie import charger_emprise

CENTRE = (652841.0, 6747711.0)


def _carre(cx, cy, cote):
    demi = cote / 2.0
    return Polygon(
        [
            (cx - demi, cy - demi),
            (cx + demi, cy - demi),
            (cx + demi, cy + demi),
            (cx - demi, cy + demi),
        ]
    )


def _ecrire_shapefile(dossier, geometries, crs):
    gdf = gpd.GeoDataFrame({"id": range(len(geometries))}, geometry=geometries, crs=crs)
    chemin = dossier / "emprise.shp"
    gdf.to_file(chemin)
    return chemin


def test_lecture_shapefile_lambert93(tmp_path):
    cx, cy = CENTRE
    _ecrire_shapefile(tmp_path, [_carre(cx, cy, 200)], "EPSG:2154")
    emprise = charger_emprise(tmp_path / "emprise.shp")

    assert emprise.reprojetee is False
    assert emprise.nb_polygones == 1
    assert emprise.surface_m2 == pytest.approx(40000.0)
    assert emprise.centre == pytest.approx(CENTRE)


def test_union_de_plusieurs_polygones(tmp_path):
    """Deux polygones disjoints : c'est l'union qui compte, pas le premier."""
    cx, cy = CENTRE
    _ecrire_shapefile(
        tmp_path, [_carre(cx - 300, cy, 100), _carre(cx + 300, cy, 100)], "EPSG:2154"
    )
    emprise = charger_emprise(tmp_path / "emprise.shp")

    assert emprise.nb_polygones == 2
    assert emprise.surface_m2 == pytest.approx(20000.0)
    largeur, _ = emprise.dimensions_m
    assert largeur == pytest.approx(700.0)


def test_reprojection_depuis_wgs84(tmp_path):
    cx, cy = CENTRE
    gdf = gpd.GeoDataFrame(
        {"id": [0]}, geometry=[_carre(cx, cy, 200)], crs="EPSG:2154"
    ).to_crs("EPSG:4326")
    gdf.to_file(tmp_path / "emprise.shp")

    emprise = charger_emprise(tmp_path / "emprise.shp")
    assert emprise.reprojetee is True
    assert emprise.centre[0] == pytest.approx(cx, abs=0.5)
    assert emprise.centre[1] == pytest.approx(cy, abs=0.5)


def test_lecture_depuis_un_zip(tmp_path):
    cx, cy = CENTRE
    source = tmp_path / "src"
    source.mkdir()
    _ecrire_shapefile(source, [_carre(cx, cy, 200)], "EPSG:2154")

    archive = tmp_path / "emprise.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for fichier in source.iterdir():
            zf.write(fichier, fichier.name)

    emprise = charger_emprise(archive)
    assert emprise.surface_m2 == pytest.approx(40000.0)


def test_prj_absent_refuse(tmp_path):
    """Sans .prj, le CRS est inconnu : on refuse au lieu de supposer 2154."""
    cx, cy = CENTRE
    chemin = _ecrire_shapefile(tmp_path, [_carre(cx, cy, 200)], "EPSG:2154")
    chemin.with_suffix(".prj").unlink()

    with pytest.raises(ErreurCRS):
        charger_emprise(chemin)


def test_prj_absent_dans_le_zip_refuse(tmp_path):
    cx, cy = CENTRE
    source = tmp_path / "src"
    source.mkdir()
    chemin = _ecrire_shapefile(source, [_carre(cx, cy, 200)], "EPSG:2154")
    chemin.with_suffix(".prj").unlink()

    archive = tmp_path / "emprise.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for fichier in source.iterdir():
            zf.write(fichier, fichier.name)

    with pytest.raises(ErreurCRS):
        charger_emprise(archive)


def test_fichier_absent(tmp_path):
    with pytest.raises(ErreurEmprise):
        charger_emprise(tmp_path / "inexistant.shp")


def test_zip_sans_shapefile(tmp_path):
    archive = tmp_path / "vide.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("lisezmoi.txt", "rien ici")
    with pytest.raises(ErreurEmprise):
        charger_emprise(archive)
