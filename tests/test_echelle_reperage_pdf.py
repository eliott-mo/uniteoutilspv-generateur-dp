"""Critère de validation n°1 du lot 6 : l'échelle du plan de repérage est vraie.

Mesurée dans le flux de contenu du **PDF produit**, et non sur des valeurs
intermédiaires du générateur : c'est le fichier qui part à l'instruction, et lui
seul, qui doit porter la bonne échelle.

Deux mesures, sur la même planche DP 7 :

- la largeur de l'emprise, dont on connaît la dimension terrain exactement ;
- la distance entre les deux repères de prise de vue, qui est ce que le brief
  demande de vérifier.

Les prises de vue sont posées **sans direction confirmée**, pour qu'aucun cône
ne vienne mêler ses arcs à ceux des disques de repère : la mesure doit porter
sur les repères, et on ne la rend pas fragile pour la rendre exhaustive.
"""

from __future__ import annotations

import math

import pytest
from PIL import Image
from shapely.geometry import box

from dp_socle.planches import dp7_environnement_proche
from dp_socle.points_de_vue import place_a_la_main
from dp_socle.projet import Projet

from .mesure_pdf import longueur, segments

pytest.importorskip(
    "cairosvg", reason="CairoSVG et libcairo sont nécessaires pour produire le PDF"
)

MM_PAR_PT = 25.4 / 72.0
ECART_ADMIS = 0.005

X0, Y0 = 622_000.0, 6_954_000.0
LARGEUR_EMPRISE_M = 330.0
HAUTEUR_EMPRISE_M = 260.0
EMPRISE = box(X0, Y0, X0 + LARGEUR_EMPRISE_M, Y0 + HAUTEUR_EMPRISE_M)

#: Les deux prises de vue, de part et d'autre du site.
PRISE_1 = (X0 - 260.0, Y0 + 60.0)
PRISE_2 = (X0 + 520.0, Y0 + 300.0)
DISTANCE_TERRAIN_M = math.dist(PRISE_1, PRISE_2)


@pytest.fixture(scope="module")
def planche(tmp_path_factory):
    """La planche DP 7 produite, et l'échelle que son repérage a retenue."""
    dossier = tmp_path_factory.mktemp("dp7")
    photos = []
    for rang in (1, 2):
        chemin = dossier / f"photo{rang}.jpg"
        Image.new("RGB", (2400, 1600), (200, 210, 190)).save(chemin)
        photos.append(chemin)

    projet = Projet(nom="essai", commune="Sarnois", code_postal="60210",
                    date="2026-09-16", emprise="x")
    prises = [
        (place_a_la_main("p1", *PRISE_1), photos[0]),
        (place_a_la_main("p2", *PRISE_2), photos[1]),
    ]
    sortie = dp7_environnement_proche.generer(
        projet, prises, EMPRISE, dossier, numero="14", fond_ign=False
    )
    return sortie


def _segments_pdf(chemin):
    return segments(chemin)


def test_l_emprise_mesure_sa_dimension_terrain_dans_le_pdf(planche):
    """L'échelle inscrite au cadre est celle que le dessin porte réellement.

    Un plan de repérage dont l'échelle annoncée ne serait pas la vraie est
    exactement la planche fausse d'aspect correct que ce dépôt refuse : elle
    s'imprime sans broncher et se mesure faux à la règle.
    """
    denominateur = planche.echelle
    attendu_mm = LARGEUR_EMPRISE_M * 1000.0 / denominateur

    horizontaux = [
        segment for segment in _segments_pdf(planche.chemin)
        if abs(segment[0][1] - segment[1][1]) < 0.3
        and abs(longueur(segment) * MM_PAR_PT - attendu_mm) / attendu_mm < 0.02
    ]
    assert horizontaux, (
        f"aucun segment horizontal de {attendu_mm:.1f} mm dans le PDF : "
        f"l'emprise de {LARGEUR_EMPRISE_M:.0f} m au 1/{denominateur} devrait en "
        "porter deux."
    )
    mesure_mm = longueur(horizontaux[0]) * MM_PAR_PT
    terrain_m = mesure_mm * denominateur / 1000.0
    assert abs(terrain_m - LARGEUR_EMPRISE_M) / LARGEUR_EMPRISE_M < ECART_ADMIS


def test_la_distance_entre_les_deux_prises_de_vue_est_vraie(planche):
    """Ce que le brief demande de mesurer, sur le fichier de sortie.

    Les repères sont des disques : leurs arcs sont les seuls segments très
    courts du flux, les prises de vue étant posées sans direction confirmée.
    On les regroupe en deux amas et on mesure entre leurs centres.
    """
    denominateur = planche.echelle
    rayon_pt = 2.4 / MM_PAR_PT

    courts = [
        segment for segment in _segments_pdf(planche.chemin)
        if 0.05 < longueur(segment) < rayon_pt / 2.0
    ]
    assert courts, "aucun arc de repère dans le PDF"

    # Un disque est approché par seize segments par quadrant : son amas compte
    # plus de cent points. Les amas d'une poignée de points viennent d'ailleurs
    # — un coin arrondi de cadre, une amorce de tracé — et ne sont pas des
    # repères.
    amas = [
        groupe
        for groupe in _regrouper(
            [point for segment in courts for point in segment], rayon_pt * 3.0
        )
        if len(groupe) >= 20
    ]
    assert len(amas) == 2, (
        f"{len(amas)} amas denses de petits segments au lieu des deux repères "
        "attendus"
    )
    centres = [_centre(amas[0]), _centre(amas[1])]
    mesure_mm = math.dist(centres[0], centres[1]) * MM_PAR_PT
    terrain_m = mesure_mm * denominateur / 1000.0
    assert abs(terrain_m - DISTANCE_TERRAIN_M) / DISTANCE_TERRAIN_M < ECART_ADMIS


def _regrouper(points, distance_max: float) -> list:
    """Amas de points séparés d'au plus `distance_max`, par agrégation simple."""
    amas = []
    for point in points:
        for groupe in amas:
            if math.dist(point, groupe[0]) <= distance_max:
                groupe.append(point)
                break
        else:
            amas.append([point])
    return amas


def _centre(points) -> tuple:
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )
