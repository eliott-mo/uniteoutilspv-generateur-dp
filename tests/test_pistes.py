"""Pistes du plan projet PDF : du tracé du plan à la piste d'un vrai plan (lot 2ter).

Ce qui se mesure ici est la bande produite : sa largeur, le rayon de son bord
intérieur dans les virages, l'angle vif qu'elle ne doit plus avoir, la boucle
qu'elle ferme ou non, et ce que le rapport dit de ce qui n'a pas tenu.
Instruction du chef de projet du 23/09/2026 : 5 m de large, 11 m de rayon au
bord intérieur des virages. Les tracés sont construits à la main, aux
dimensions de ceux de Gannay et de Bray.
"""

from __future__ import annotations

import pytest
from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from dp_socle.pistes import (
    LARGEUR_PISTE_M,
    RAYON_AXE_M,
    RAYON_INTERIEUR_M,
    AxePiste,
    dessiner_pistes,
)


def _pistes(*traces):
    return dessiner_pistes([AxePiste(c, l, LineString(p)) for c, l, p in traces])


def test_les_valeurs_sont_celles_de_l_instruction():
    assert LARGEUR_PISTE_M == 5.0
    assert RAYON_INTERIEUR_M == 11.0
    assert RAYON_AXE_M == 13.5


def test_une_piste_droite_a_5_m_de_large():
    (piste,), notes = _pistes(("piste_lourde_a_creer", "A", [(0, 0), (100, 0)]))
    assert piste.surface.area == pytest.approx(500.0, rel=1e-6)
    assert not notes


def test_un_coude_s_arrondit_a_11_m_au_bord_interieur():
    """Un virage à angle droit : le bord intérieur suit un arc de 11 m, l'extérieur de 16 m.

    Le centre de l'arc est à 13,5 m de chacun des deux alignements. La bande
    n'entre pas dans le cercle de 11 m, et elle le touche ; l'angle vif
    qu'aurait fait la bande sans arrondi n'en fait plus partie.
    """
    (piste,), notes = _pistes(("piste_lourde_a_creer", "A", [(0, 0), (100, 0), (100, 100)]))
    centre = Point(100.0 - RAYON_AXE_M, RAYON_AXE_M)
    assert piste.surface.distance(centre) == pytest.approx(RAYON_INTERIEUR_M, abs=0.02)
    # L'angle vif extérieur, et la pointe de la bande qui l'aurait suivi.
    assert not piste.surface.contains(Point(101.8, -1.8))
    assert not piste.surface.contains(Point(98.5, 1.5))
    # Dans le virage, le bord extérieur est à 16 m du centre.
    virage = [c for c in piste.surface.exterior.coords if c[0] > 86.5 and c[1] < 13.5]
    assert max(centre.distance(Point(c)) for c in virage) == pytest.approx(16.0, abs=0.05)
    assert piste.rayons_axe_m == [13.5]
    assert not notes


def test_un_decrochement_du_trait_s_efface_et_le_rapport_le_dit():
    """À Bray, le trait longe un décrochement de la clôture de 0,8 m.

    Un segment si court entre deux alignements presque parallèles est le reste
    d'un raccord mal ajusté dans PowerPoint : ses deux sommets se fondent.
    """
    (piste,), notes = _pistes(
        ("piste_lourde_existante", "A", [(0, 0), (100, 0), (100.3, 0.8), (200, 0.8)])
    )
    assert len(piste.axe.coords) < 10
    assert piste.surface.area == pytest.approx(piste.axe.length * LARGEUR_PISTE_M, rel=0.001)
    assert any("décrochement" in n for n in notes)


def test_deux_traces_mis_bout_a_bout_ferment_une_boucle_arrondie():
    """La boucle de Gannay : une piste existante, une piste à créer, deux raccords.

    Leurs extrémités sont à 2 m l'une de l'autre : ce sont deux traits mis
    bout à bout. Chaque coin est arrondi, raccords compris, et chaque morceau
    garde sa catégorie.
    """
    pistes, _ = _pistes(
        ("piste_lourde_a_creer", "à créer", [(0, 2), (0, 100), (100, 100)]),
        ("piste_lourde_existante", "existante", [(100, 98), (100, 0), (2, 0)]),
    )
    assert {p.categorie for p in pistes} == {"piste_lourde_a_creer", "piste_lourde_existante"}
    union = unary_union([p.surface for p in pistes])
    assert union.geom_type == "Polygon"
    assert len(union.interiors) == 1
    for coin, centre in (
        ((0, 0), (RAYON_AXE_M, RAYON_AXE_M)),
        ((0, 100), (RAYON_AXE_M, 100 - RAYON_AXE_M)),
        ((100, 100), (100 - RAYON_AXE_M, 100 - RAYON_AXE_M)),
        ((100, 0), (100 - RAYON_AXE_M, RAYON_AXE_M)),
    ):
        assert union.distance(Point(centre)) == pytest.approx(RAYON_INTERIEUR_M, abs=0.02), coin


def test_un_raccord_en_t_s_evase_au_rayon_interieur():
    """Une piste qui en rejoint une autre : ses deux angles rentrants s'arrondissent à 11 m."""
    pistes, notes = _pistes(
        ("piste_lourde_existante", "principale", [(0, 0), (200, 0)]),
        ("piste_lourde_a_creer", "bretelle", [(100, 0.3), (100, 50)]),
    )
    bretelle = next(p for p in pistes if p.libelle == "bretelle")
    assert bretelle.rayons_raccords_m == [11.0, 11.0]
    # Le bout est mené jusqu'à l'axe qu'il rejoint.
    assert min(abs(c[1]) for c in bretelle.axe.coords) < 1e-6
    union = unary_union([p.surface for p in pistes])
    # L'angle rentrant est comblé près du coin, et l'arc de 11 m le borne.
    assert union.contains(Point(104.0, 4.0))
    assert not union.contains(Point(110.0, 10.0))
    centre = Point(102.5 + RAYON_INTERIEUR_M, 2.5 + RAYON_INTERIEUR_M)
    assert union.distance(centre) == pytest.approx(RAYON_INTERIEUR_M, abs=0.05)
    assert not notes


def test_une_bretelle_courte_s_evase_au_rayon_qui_tient_et_le_dit():
    """La bretelle du portail de Gannay : 11,4 m entre deux pistes.

    Il n'y a pas la place d'arcs de 11 m : chaque angle rentrant prend la
    moitié de ce qui reste à découvert, et le rapport le dit.
    """
    pistes, notes = _pistes(
        ("piste_lourde_existante", "haut", [(0, 0), (200, 0)]),
        ("piste_lourde_existante", "bas", [(0, -11.4), (200, -11.4)]),
        ("piste_lourde_existante", "bretelle", [(100, -0.3), (100, -11.1)]),
    )
    bretelle = next(p for p in pistes if p.libelle == "bretelle")
    assert bretelle.rayons_raccords_m == pytest.approx([3.2] * 4, abs=0.05)
    assert len([n for n in notes if "faute de place" in n]) == 2


def test_deux_virages_rapproches_se_fondent_en_un_seul():
    """Deux virages de 45° à 3 m l'un de l'autre n'ont pas la place d'arcs de 13,5 m.

    Ils se fondent au sommet commun des deux alignements qui les encadrent :
    le virage à angle droit qu'un projeteur tracerait, arrondi au rayon voulu.
    """
    (piste,), notes = _pistes(
        ("piste_legere", "A", [(0, 0), (100, 0), (102.12, 2.12), (102.12, 100)])
    )
    assert piste.rayons_axe_m == [13.5]
    assert any("fondus en un seul" in n for n in notes)
    sommet = (102.12 + 0.0, 0.0)
    centre = Point(sommet[0] - RAYON_AXE_M, RAYON_AXE_M)
    assert piste.surface.distance(centre) == pytest.approx(RAYON_INTERIEUR_M, abs=0.05)


def test_un_virage_sans_place_se_resserre_et_le_rapport_le_dit():
    """Un demi-tour sur 10 m ne s'arrondit pas à 13,5 m : il se resserre, et c'est dit."""
    (piste,), notes = _pistes(("piste_legere", "A", [(0, 0), (100, 0), (100, 10), (0, 10)]))
    assert piste.rayons_axe_m == [5.0, 5.0]
    assert any("5.0 m de rayon" in n and "en deçà" in n for n in notes)


def test_deux_bouts_proches_sans_raccord_le_disent():
    """À Bray, deux pistes finissent au local technique à 3,6 m l'une de l'autre.

    Trop loin pour deux traits mis bout à bout : ce sont deux accès. On ne les
    raccorde pas, mais on le dit, pour que le plan tranche.
    """
    pistes, notes = _pistes(
        ("piste_lourde_existante", "existante", [(100, 100), (0, 0)]),
        ("piste_lourde_a_creer", "à créer", [(-100, 100), (-2.55, 2.55)]),
    )
    assert sum(p.rayons_axe_m == [] for p in pistes) == 2
    assert any("laissées sans raccord" in n for n in notes)
