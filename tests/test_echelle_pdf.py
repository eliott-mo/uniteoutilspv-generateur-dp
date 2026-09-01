"""Critère de validation n°1 : l'échelle est vraie dans le PDF produit.

Le test ne porte pas sur des valeurs intermédiaires du générateur : il génère
une planche au 1:10 000 contenant un segment de longueur terrain connue, puis
mesure ce segment dans le fichier PDF de sortie. Écart admis : 0,5 %.
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import LineString

from dp_socle.planche import HAUTEUR_MM, LARGEUR_MM, Planche, Style

from .mesure_pdf import format_page, longueur, segments_obliques

pytest.importorskip(
    "cairosvg", reason="CairoSVG et libcairo sont nécessaires pour produire le PDF"
)

CENTRE = (652841.0, 6747711.0)
DENOMINATEUR = 10000

#: Segment oblique, pour se distinguer sans ambiguïté du cadre et du fond.
DELTA_X_M = 1000.0
DELTA_Y_M = 600.0
LONGUEUR_TERRAIN_M = math.hypot(DELTA_X_M, DELTA_Y_M)

MM_PAR_PT = 25.4 / 72.0
ECART_ADMIS = 0.005


def _planche_temoin(chemin):
    planche = Planche(
        titre="TÉMOIN D'ÉCHELLE",
        numero="TEST",
        projet="Contrôle métrologique",
        date="01/09/2026",
        echelle=DENOMINATEUR,
        avec_cartouche=False,
    )
    planche.centrer_sur(CENTRE)
    cx, cy = CENTRE
    planche.ajouter_geometrie(
        LineString(
            [
                (cx - DELTA_X_M / 2, cy - DELTA_Y_M / 2),
                (cx + DELTA_X_M / 2, cy + DELTA_Y_M / 2),
            ]
        ),
        Style(trait="#000000", epaisseur_mm=0.2, remplissage="none"),
    )
    return planche.rendre_pdf(chemin)


def test_page_est_un_a3_paysage(tmp_path):
    chemin = _planche_temoin(tmp_path / "temoin.pdf")
    largeur_pt, hauteur_pt = format_page(chemin)
    assert largeur_pt * MM_PAR_PT == pytest.approx(LARGEUR_MM, abs=0.2)
    assert hauteur_pt * MM_PAR_PT == pytest.approx(HAUTEUR_MM, abs=0.2)


def test_echelle_vraie_a_moins_de_0_5_pourcent(tmp_path):
    chemin = _planche_temoin(tmp_path / "temoin.pdf")

    obliques = segments_obliques(chemin)
    assert obliques, "aucun segment oblique trouvé dans le PDF produit"
    mesure_pt = max(longueur(segment) for segment in obliques)
    mesure_mm = mesure_pt * MM_PAR_PT

    attendu_mm = LONGUEUR_TERRAIN_M * 1000.0 / DENOMINATEUR
    ecart = abs(mesure_mm - attendu_mm) / attendu_mm

    assert ecart < ECART_ADMIS, (
        f"segment mesuré {mesure_mm:.3f} mm dans le PDF, attendu {attendu_mm:.3f} mm "
        f"pour {LONGUEUR_TERRAIN_M:.1f} m au 1:{DENOMINATEUR} — écart {ecart:.3%}"
    )


def test_echelle_vraie_au_1_5000(tmp_path):
    """Même contrôle à une autre échelle, pour écarter une compensation fortuite."""
    planche = Planche(
        titre="TÉMOIN D'ÉCHELLE",
        numero="TEST",
        projet="Contrôle métrologique",
        date="01/09/2026",
        echelle=5000,
        avec_cartouche=False,
    )
    planche.centrer_sur(CENTRE)
    cx, cy = CENTRE
    planche.ajouter_geometrie(
        LineString([(cx - 250, cy - 150), (cx + 250, cy + 150)]),
        Style(trait="#000000", epaisseur_mm=0.2, remplissage="none"),
    )
    chemin = planche.rendre_pdf(tmp_path / "temoin_5000.pdf")

    mesure_mm = max(
        longueur(segment) for segment in segments_obliques(chemin)
    ) * MM_PAR_PT
    attendu_mm = math.hypot(500.0, 300.0) * 1000.0 / 5000
    assert abs(mesure_mm - attendu_mm) / attendu_mm < ECART_ADMIS
