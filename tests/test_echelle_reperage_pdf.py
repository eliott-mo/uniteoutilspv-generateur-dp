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

from dp_socle.planche import Planche
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


# ---------------------------------------------------------------------------
# Le fond du plan de repérage
# ---------------------------------------------------------------------------
#
# Il a été une image du Plan IGN v2 jusqu'au 26/09/2026, et deux tests
# mesuraient le seuil de résolution au-delà duquel ce service cesse de dessiner
# le parcellaire — 0,30 m/px, un piège de deux millièmes qui avait mordu. Ils
# n'ont plus d'objet : le parcellaire vient maintenant du WFS, en vectoriel,
# comme sur DP 1-3 et sur le plan de repérage de DP 4. Trois raisons, dans
# l'ordre où l'usage les a nommées le 26/09/2026 — la teinte jaune du Plan IGN
# noyait l'implantation, le seuil de résolution était à guetter, et un fond
# matriciel faisait partir toute la planche en image dans le `.pptx`.


def test_le_plan_de_reperage_ne_porte_aucun_fond_matriciel(planche):
    """Le fond est vectoriel, et c'est ce qui rend la planche nette dans le `.pptx`.

    Mesuré dans le SVG de la planche et non dans le PDF : c'est là que le raster
    se verrait, encodé en base64. La planche en porte d'autres — le logo du
    cartouche, et les photographies de la colonne de droite — et ce n'est pas
    d'eux qu'il s'agit : `preserveAspectRatio="none"` est la signature du seul
    `ajouter_fond_raster`, qui étire son image à une emprise terrain exacte.
    """
    svg = planche.planche.svg()

    assert 'preserveAspectRatio="none"' not in svg


def test_l_emprise_ne_couvre_pas_le_plan_d_un_aplat(planche):
    """Le voile saumon de `STYLE_EMPRISE` noyait l'implantation.

    Il vient de son remplissage à 15 % d'opacité, posé en dernier donc par-dessus
    tout le reste. Sur un plan de repérage, seul le trait subsiste — et seulement
    faute de contrat, la clôture étant sinon déjà dessinée par la palette.
    """
    from dp_socle.planche import STYLE_EMPRISE

    svg = planche.planche.svg()

    assert STYLE_EMPRISE.remplissage == "#d40000", "le style du socle a changé"
    assert f'fill="{STYLE_EMPRISE.remplissage}"' not in svg
    assert 'fill-opacity="0.15"' not in svg


@pytest.mark.reseau
def test_le_parcellaire_du_wfs_se_dessine_sous_le_reperage(tmp_path):
    """Le fond cadastral vient bien du service, et il est tracé.

    C'est le seul endroit qui dise si le WFS répond encore ce qu'on attend :
    des limites de parcelle en vectoriel, autour du site.
    """
    from shapely.geometry import box as _box

    from dp_socle.planche import STYLE_PARCELLE
    from dp_socle.planches.photographies import _poser_le_cadastre

    temoin = Planche(titre="T", numero="1", projet="essai", date="16/09/2026",
                     echelle=2500)
    # Saint-Cyr-en-Val : un site réel, dont le parcellaire est renseigné.
    centre = (622_974.0, 6_750_762.0)
    temoin.centrer_sur(centre)
    fenetre = _box(centre[0] - 200, centre[1] - 200, centre[0] + 200, centre[1] + 200)

    messages = []
    _poser_le_cadastre(temoin, fenetre, messages)

    assert messages == []
    svg = temoin.svg()
    assert svg.count(f'stroke="{STYLE_PARCELLE.trait}"') > 5, "trop peu de parcelles"
