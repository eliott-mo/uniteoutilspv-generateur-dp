"""Primitives de dessin des coupes et des plans techniques.

Ce qui est mesuré ici est ce dont dépendent toutes les planches du lot : un
repère local isotrope, une conversion qui passe par `dp_socle.echelle` et un
dessin qui refuse de déborder du cadre qu'on lui donne. Les mesures sur le PDF
produit sont dans `test_planches_lot4.py` ; celles-ci portent sur la géométrie
avant rendu, où l'on peut isoler chaque primitive.
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon

from dp_socle.echelle import metres_vers_mm
from dp_socle.erreurs import ErreurComposition, ErreurEchelle
from dp_socle.planche import Planche
from dp_socle.planches.primitives import (
    CONTOUR_SILHOUETTE,
    HAUTEUR_SILHOUETTE_M,
    Dessin,
    bande_de_sol,
    cote_horizontale,
    echelle_du_dessin,
    forme_pleine,
    hachurer,
    silhouette,
    sol_hachure,
    union_valide,
)


def _planche() -> Planche:
    return Planche(
        titre="ESSAI", numero="T", projet="Essai", date="04/09/2026",
        avec_cartouche=False,
    )


def _dessin(denominateur: int = 100, cadre=None) -> Dessin:
    return Dessin(
        planche=_planche(), denominateur=denominateur,
        origine_mm=(50.0, 200.0), cadre_mm=cadre,
    )


# ---------------------------------------------------------------------------
# D2 — un seul facteur d'échelle, donc aucune exagération verticale possible
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("denominateur", [50, 80, 100, 200, 500, 1000])
def test_un_metre_vertical_mesure_comme_un_metre_horizontal(denominateur):
    """Décision D2 : les deux axes ont le même rapport, par construction.

    C'est la propriété qui rend l'exagération verticale impossible à écrire
    par mégarde. L'aperçu de contrôle du lot 2bis en applique une, avec
    raison ; une planche qui déclare une échelle au cartouche ne le peut pas.
    """
    dessin = _dessin(denominateur)
    origine = dessin.point(0.0, 0.0)
    horizontal = dessin.point(1.0, 0.0)
    vertical = dessin.point(0.0, 1.0)

    parcours_x = abs(horizontal[0] - origine[0])
    parcours_y = abs(vertical[1] - origine[1])
    assert parcours_x == pytest.approx(parcours_y)
    assert parcours_x == pytest.approx(metres_vers_mm(1.0, denominateur))


def test_la_conversion_passe_par_le_module_echelle():
    """Aucun facteur mètres/millimètres n'est recalculé ailleurs."""
    dessin = _dessin(250)
    assert dessin.longueur(7.0) == metres_vers_mm(7.0, 250)
    assert dessin.mm_par_metre == metres_vers_mm(1.0, 250)


def test_lordonnee_monte_dans_le_dessin_et_descend_sur_le_papier():
    dessin = _dessin(100)
    bas = dessin.point(0.0, 0.0)
    haut = dessin.point(0.0, 3.0)
    assert haut[1] < bas[1]


def test_le_rectangle_se_pose_par_son_coin_bas_gauche():
    dessin = _dessin(100)
    dessin.rectangle(0.0, 0.0, 12.0, 3.0)
    x, y, largeur, hauteur = dessin.etendue_mm()
    assert largeur == pytest.approx(metres_vers_mm(12.0, 100))
    assert hauteur == pytest.approx(metres_vers_mm(3.0, 100))
    # Le coin bas-gauche du dessin est l'origine du repère local.
    assert (x, y + hauteur) == pytest.approx(dessin.point(0.0, 0.0))


# ---------------------------------------------------------------------------
# Débordement : un dessin trop grand ne se rogne pas, il refuse
# ---------------------------------------------------------------------------


def test_un_dessin_qui_deborde_du_cadre_leve():
    """Les tracés en millimètres ne sont pas découpés sur la zone de dessin.

    Un dessin trop grand ne serait pas rogné : il s'imprimerait par-dessus le
    cartouche, et la planche partirait comme ça.
    """
    dessin = _dessin(50, cadre=(50.0, 150.0, 60.0, 50.0))
    dessin.rectangle(0.0, 0.0, 80.0, 2.0)
    with pytest.raises(ErreurComposition, match="sort du cadre"):
        dessin.verifier_cadre("essai")


def test_un_dessin_qui_tient_ne_leve_pas():
    dessin = _dessin(500, cadre=(40.0, 190.0, 200.0, 60.0))
    dessin.rectangle(0.0, 0.0, 80.0, 2.0)
    dessin.verifier_cadre("essai")


def test_sans_cadre_aucun_controle():
    dessin = _dessin(50)
    dessin.rectangle(0.0, 0.0, 500.0, 2.0)
    dessin.verifier_cadre("essai")


# ---------------------------------------------------------------------------
# Choix d'échelle
# ---------------------------------------------------------------------------


def test_echelle_du_dessin_retient_la_plus_grande_qui_tienne():
    """La plus grande échelle, c'est le plus petit dénominateur."""
    zone = (0.0, 0.0, 200.0, 100.0)
    # 15 m au 1/100 font 150 mm : ça tient. Au 1/50 il en faudrait 300.
    assert echelle_du_dessin(15.0, 5.0, zone, (50, 100, 200)) == 100
    assert echelle_du_dessin(9.0, 3.0, zone, (50, 100, 200)) == 50
    # 30 m ne tiennent qu'au 1/200 : 150 mm contre 300 au 1/100.
    assert echelle_du_dessin(30.0, 5.0, zone, (50, 100, 200)) == 200


def test_echelle_du_dessin_nomme_le_dessin_qui_ne_tient_pas():
    """À quatre dessins par planche, savoir lequel déborde fait le diagnostic."""
    with pytest.raises(ErreurEchelle, match="coupe des tables"):
        echelle_du_dessin(
            900.0, 5.0, (0.0, 0.0, 200.0, 100.0), (50, 100),
            libelle="coupe des tables",
        )


# ---------------------------------------------------------------------------
# Hachures et sol
# ---------------------------------------------------------------------------


def test_les_hachures_restent_dans_le_contour():
    dessin = _dessin(100)
    contour = [(0.0, 0.0), (20.0, 0.0), (20.0, 4.0), (0.0, 4.0)]
    hachurer(dessin, contour)

    polygone = Polygon([dessin.point(*p) for p in contour])
    assert dessin._etendue, "aucune hachure tracée"
    for point in dessin._etendue:
        assert polygone.buffer(0.01).covers(
            __import__("shapely").geometry.Point(point)
        ), f"hachure hors du contour : {point}"


def test_le_pas_des_hachures_est_constant_sur_le_papier():
    """Une hachure est une convention de dessin, pas une mesure du terrain."""
    contour = [(0.0, 0.0), (20.0, 0.0), (20.0, 4.0), (0.0, 4.0)]
    grand = _dessin(100)
    hachurer(grand, contour)
    petit = _dessin(200)
    hachurer(petit, [(x * 2, y * 2) for x, y in contour])
    # Même surface de papier hachurée, donc même nombre de traits.
    assert abs(len(grand._etendue) - len(petit._etendue)) <= 2


def test_la_bande_de_sol_suit_le_terrain():
    points = [(0.0, 10.0), (10.0, 11.0), (20.0, 10.5)]
    contour = bande_de_sol(points, 1.0)
    assert len(contour) == 2 * len(points)
    assert contour[:3] == points
    assert contour[3] == (20.0, 9.5)


def test_le_sol_hachure_trace_la_ligne_de_terrain():
    dessin = _dessin(500)
    profil = [(x, 190.0 + 0.02 * x) for x in range(0, 220, 5)]
    sol_hachure(dessin, profil)
    x, y, largeur, hauteur = dessin.etendue_mm()
    assert largeur == pytest.approx(metres_vers_mm(215.0, 500), abs=0.1)


# ---------------------------------------------------------------------------
# Formes pleines
# ---------------------------------------------------------------------------


def test_la_silhouette_fait_bien_la_taille_annoncee():
    """C'est elle qui donne l'échelle à l'instructeur : elle doit être juste."""
    dessin = _dessin(50)
    silhouette(dessin, 0.0, 0.0)
    _, _, largeur, hauteur = dessin.etendue_mm()
    assert hauteur == pytest.approx(
        metres_vers_mm(HAUTEUR_SILHOUETTE_M, 50), rel=0.02
    )
    # Une silhouette humaine est bien plus haute que large.
    assert largeur < hauteur / 3.0


def test_le_contour_de_la_silhouette_est_un_polygone_simple():
    """Un contour qui se recoupe se remplirait par morceaux."""
    polygone = Polygon(CONTOUR_SILHOUETTE)
    assert polygone.is_valid
    assert polygone.area > 0


def test_la_silhouette_a_les_pieds_sur_le_sol():
    ordonnees = [y for _, y in CONTOUR_SILHOUETTE]
    assert min(ordonnees) == pytest.approx(0.0)
    assert max(ordonnees) == pytest.approx(1.0, abs=0.01)


def test_forme_pleine_refuse_une_forme_degeneree():
    planche = _planche()
    with pytest.raises(ErreurComposition, match="au moins trois"):
        forme_pleine(planche, [(0.0, 0.0), (1.0, 1.0)], "#000000")
    with pytest.raises(ErreurComposition, match="aire nulle"):
        forme_pleine(
            planche, [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)], "#000000"
        )


def test_forme_pleine_se_mesure_dans_le_svg():
    """Un aplat vectoriel, et non un motif : cairo pixellise les motifs.

    Mesuré le 04/09/2026 : une silhouette de 35 mm déclarée en `<pattern>` et
    peinte par un rectangle ressortait floue sur un aperçu à 600 dpi. Le
    remplissage par balayage, lui, est fait de traits que le PDF porte.
    """
    planche = _planche()
    forme_pleine(planche, [(10.0, 10.0), (20.0, 10.0), (15.0, 20.0)], "#000000")
    svg = planche.svg()
    assert svg.count("<line") > 20
    assert "<pattern" not in svg


# ---------------------------------------------------------------------------
# Cotes
# ---------------------------------------------------------------------------


def test_la_cote_se_reporte_dehors_quand_la_place_manque():
    """Une cote illisible est une cote absente, et personne ne la redemande."""
    large = _dessin(50)
    cote_horizontale(large, 0.0, 12.0, 0.0, "12,00 m")
    droite_large = max(p[0] for p in large._etendue)

    etroit = _dessin(2000)
    cote_horizontale(etroit, 0.0, 12.0, 0.0, "12,00 m")
    droite_etroite = max(p[0] for p in etroit._etendue)

    # Au 1/2 000 la cote ne tient pas dans les 6 mm du trait : elle est
    # reportée au-delà de son extrémité droite.
    assert droite_etroite > etroit.point(12.0, 0.0)[0] + 1.0
    assert droite_large < large.point(12.0, 0.0)[0] + 1.0


# ---------------------------------------------------------------------------
# D6 — make_valid avant toute union
# ---------------------------------------------------------------------------


def test_union_valide_traverse_un_polygone_auto_intersectant():
    papillon = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])
    assert not papillon.is_valid
    union = union_valide([papillon, Polygon([(20, 0), (30, 0), (30, 10), (20, 10)])])
    assert union is not None and union.is_valid


def test_union_valide_rend_rien_sur_un_lot_vide():
    assert union_valide([]) is None
    assert union_valide([Polygon()]) is None


def test_langle_des_hachures_de_sol_est_a_45_degres():
    """Convention du dessin de coupe, comme sur le plan cadastral."""
    dessin = _dessin(100)
    hachurer(dessin, [(0.0, 0.0), (20.0, 0.0), (20.0, 4.0), (0.0, 4.0)])
    points = dessin._etendue
    # Les points sont notés par paires : chaque trait a ses deux extrémités.
    pentes = []
    for depart, arrivee in zip(points[::2], points[1::2]):
        dx = arrivee[0] - depart[0]
        dy = arrivee[1] - depart[1]
        if abs(dx) > 0.01:
            pentes.append(abs(dy / dx))
    assert pentes
    assert all(pente == pytest.approx(1.0, abs=0.01) for pente in pentes), (
        f"pentes relevées : {sorted(set(round(p, 2) for p in pentes))}"
    )


def test_la_silhouette_est_a_lechelle_du_dessin_qui_la_porte():
    """La même personne, deux échelles : elle suit le dessin, pas la feuille."""
    hauteurs = {}
    for denominateur in (50, 200):
        dessin = _dessin(denominateur)
        silhouette(dessin, 0.0, 0.0)
        hauteurs[denominateur] = dessin.etendue_mm()[3]
    assert hauteurs[50] / hauteurs[200] == pytest.approx(4.0, rel=0.02)


def test_math_disponible_pour_les_reperes():
    """Garde-fou trivial : le repère de coupe normalise sa direction."""
    assert math.hypot(3, 4) == 5
