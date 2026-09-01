"""Tests de la conversion millimètres papier <-> mètres terrain."""

from __future__ import annotations

import pytest

from dp_socle.echelle import (
    TransformationL93,
    echelle_adaptative,
    formater_echelle,
    metres_vers_mm,
    mm_vers_metres,
)
from dp_socle.erreurs import ErreurEchelle

ZONE = (5.0, 5.0, 410.0, 268.0)
CENTRE = (652841.0, 6747711.0)


@pytest.mark.parametrize(
    "millimetres, denominateur, metres",
    [
        (1.0, 10000, 10.0),
        (100.0, 10000, 1000.0),
        (100.0, 5000, 500.0),
        (410.0, 1000, 410.0),
        (1.0, 200, 0.2),
    ],
)
def test_mm_vers_metres(millimetres, denominateur, metres):
    assert mm_vers_metres(millimetres, denominateur) == pytest.approx(metres)


def test_conversions_reciproques():
    for denominateur in (200, 500, 1000, 2000, 5000, 10000):
        assert metres_vers_mm(
            mm_vers_metres(123.45, denominateur), denominateur
        ) == pytest.approx(123.45)


def test_denominateur_invalide_refuse():
    for valeur in (0, -1000, None, "10000"):
        with pytest.raises(ErreurEchelle):
            mm_vers_metres(10.0, valeur)


def test_formatage():
    assert formater_echelle(10000) == "1:10 000"
    assert formater_echelle(500) == "1:500"


def test_emprise_terrain_correspond_a_la_zone():
    transformation = TransformationL93(ZONE, 10000, CENTRE)
    minx, miny, maxx, maxy = transformation.emprise
    assert maxx - minx == pytest.approx(mm_vers_metres(ZONE[2], 10000))
    assert maxy - miny == pytest.approx(mm_vers_metres(ZONE[3], 10000))
    assert (minx + maxx) / 2 == pytest.approx(CENTRE[0])
    assert (miny + maxy) / 2 == pytest.approx(CENTRE[1])


def test_transformation_coins():
    transformation = TransformationL93(ZONE, 10000, CENTRE)
    minx, miny, maxx, maxy = transformation.emprise
    x_mm, y_mm, largeur, hauteur = ZONE

    # Le nord (maxy) est en haut de la feuille : l'axe Y est retourné.
    assert transformation.point(minx, maxy) == pytest.approx((x_mm, y_mm))
    assert transformation.point(maxx, miny) == pytest.approx(
        (x_mm + largeur, y_mm + hauteur)
    )
    assert transformation.point(*CENTRE) == pytest.approx(
        (x_mm + largeur / 2, y_mm + hauteur / 2)
    )


def test_longueur_papier_d_un_segment_terrain():
    transformation = TransformationL93(ZONE, 10000, CENTRE)
    assert transformation.longueur(1000.0) == pytest.approx(100.0)


def test_echelle_adaptative_choisit_la_plus_grande():
    # 100 x 60 m + 20 % tiennent au 1:500 dans 410 x 268 mm.
    assert echelle_adaptative(100, 60, ZONE, valeurs=(500, 1000, 2000, 5000)) == 500
    # 400 x 300 m + 20 % ne tiennent qu'à partir du 1:2000 (hauteur limitante).
    assert echelle_adaptative(400, 300, ZONE, valeurs=(500, 1000, 2000, 5000)) == 2000


def test_echelle_adaptative_refuse_si_rien_ne_convient():
    with pytest.raises(ErreurEchelle):
        echelle_adaptative(50000, 40000, ZONE, valeurs=(500, 1000, 2000, 5000))


def test_echelle_adaptative_refuse_emprise_degeneree():
    with pytest.raises(ErreurEchelle):
        echelle_adaptative(0, 100, ZONE)
