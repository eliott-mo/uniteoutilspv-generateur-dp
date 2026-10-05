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


def test_une_piste_qui_longe_la_cloture_se_reporte_a_un_demi_metre_d_elle():
    """Demande du chef de projet du 23/09/2026 : plus près de la clôture, sans la toucher.

    Un tracé en U à 2 m de la clôture d'un carré : la piste de 5 m menée
    dessus la chevaucherait. Serrée, son axe court à 3 m de la clôture — la
    demi-largeur et le jeu —, sur les mêmes trois côtés, et sa bande passe à
    0,5 m d'elle.
    """
    from shapely.geometry import Polygon

    from dp_socle.pistes import JEU_CLOTURE_M, serrer_contre

    enceinte = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    trace = LineString([(2, 98), (2, 2), (98, 2), (98, 98)])
    serre = serrer_contre(trace, enceinte)
    assert serre is not None
    decalage = LARGEUR_PISTE_M / 2.0 + JEU_CLOTURE_M
    assert serre.hausdorff_distance(
        LineString([(decalage, 98), (decalage, decalage), (100 - decalage, decalage), (100 - decalage, 98)])
    ) < decalage
    (piste,), _ = _pistes(("piste_lourde_a_creer", "U", list(serre.coords)))
    assert piste.surface.distance(enceinte.exterior) == pytest.approx(JEU_CLOTURE_M, abs=0.01)
    # Une piste qui traverse l'enceinte ne longe pas la clôture : rien à serrer.
    assert serrer_contre(LineString([(50, 0), (50, 100)]), enceinte) is None


def test_un_raccord_sur_un_alignement_n_est_pas_un_virage():
    """Deux tracés mis bout à bout sur une même droite, près d'un angle.

    Le raccord tombe à 4 m de l'angle : l'arc de 13,5 m de l'angle doit le
    franchir. Gardé comme sommet, il se prenait pour un décrochement, et
    l'angle se déplaçait (mesuré à Gannay le 23/09/2026).
    """
    pistes, notes = _pistes(
        ("piste_lourde_existante", "existante", [(0, 100), (0, 0), (4, 0)]),
        ("piste_lourde_a_creer", "à créer", [(4, 0), (100, 0)]),
    )
    assert not any("décrochement" in n or "fondus" in n for n in notes)
    union = unary_union([p.surface for p in pistes])
    centre = Point(RAYON_AXE_M, RAYON_AXE_M)
    assert union.distance(centre) == pytest.approx(RAYON_INTERIEUR_M, abs=0.02)
    assert {p.libelle: p.rayons_axe_m for p in pistes} == {
        "existante": [13.5],
        "à créer": [13.5],
    }


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


# ---------------------------------------------------------------------------
# Les tracés dégénérés du plan (Saint-Aubin-sur-Loire, 01/10/2026)
# ---------------------------------------------------------------------------


def test_un_trace_reduit_a_un_point_ne_fait_pas_tomber_l_import():
    """Un tracé d'un seul sommet n'arrête pas les autres pistes.

    Relevé sur le plan de Saint-Aubin-sur-Loire : l'import s'arrêtait sur
    `GEOSException: point array must contain 0 or >1 elements`, une trace
    Python qui ne disait ni le tracé fautif ni quoi en faire.
    """
    pistes, notes = _pistes(
        ("piste_lourde_a_creer", "A", [(0, 0), (100, 0)]),
        ("piste_lourde_a_creer", "Point", [(300, 300), (300, 300)]),
    )
    assert [piste.libelle for piste in pistes] == ["A"]
    assert any("réduits à un point" in note for note in notes)


def test_un_moignon_contre_une_piste_ne_fait_pas_tomber_l_import():
    """Un tracé de 2 cm le long d'une piste s'écarte, et se dit.

    Ses deux bouts sont libres et à portée de raccord : chacun est mené
    jusqu'à l'axe voisin, et ils y tombent au même endroit. Le chemin sort
    alors sans aucun segment, et `_arrondir` s'y arrêtait sur un `IndexError`
    qui ne nommait ni le tracé fautif ni quoi en faire.
    """
    pistes, notes = _pistes(
        ("piste_lourde_a_creer", "A", [(0, 0), (100, 0)]),
        ("piste_lourde_a_creer", "Moignon", [(50, 0.3), (50, 0.32)]),
    )
    assert [piste.libelle for piste in pistes] == ["A"]
    assert any("sans longueur" in note and "Moignon" in note for note in notes)
    # La bande de la piste qui reste est intacte : le moignon ne l'a pas élargie.
    assert pistes[0].surface.area == pytest.approx(500.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Le raccord sur une piste courbe (Gannay, 01/10/2026)
# ---------------------------------------------------------------------------


def test_un_raccord_sur_une_piste_courbe_ne_part_pas_en_aiguille():
    """L'évasement reste dans le creux de l'angle, sur une piste qui tourne.

    Remonté par le chef de projet le 01/10/2026 sur la boucle de Gannay : le
    raccord sortait deux aiguilles de 20 m de long pour 2 à 3 m de large, de
    part et d'autre de la bretelle, bien au-delà du bitume. L'arc qui comblait
    l'angle était posé sur la **tangente** de la piste rejointe ; sur une piste
    de 40 m de rayon, la tangente s'écarte de la bande de plusieurs mètres en
    quelques dizaines, et l'évasement s'en allait avec elle.

    Ce qui se mesure ici est la propriété que l'aiguille viole : ce qu'on
    ajoute au raccord ne dépasse pas de ce qu'une bille du rayon intérieur peut
    atteindre, c'est-à-dire de la fermeture des deux bandes. Sur ce tracé,
    l'ancien dessin en mettait 23,7 m² dehors.
    """
    import math

    rayon_boucle = 40.0
    boucle = [
        (
            rayon_boucle * math.cos(math.radians(angle)),
            rayon_boucle * math.sin(math.radians(angle)),
        )
        for angle in range(-90, 91, 5)
    ]
    bretelle = [(rayon_boucle + 0.3, 0.0), (rayon_boucle + 60.0, 0.0)]
    pistes, _ = _pistes(
        ("piste_lourde_existante", "boucle", boucle),
        ("piste_lourde_a_creer", "bretelle", bretelle),
    )

    union = unary_union([piste.surface for piste in pistes])
    bandes = unary_union(
        [
            piste.axe.buffer(LARGEUR_PISTE_M / 2.0, cap_style="flat", join_style="round")
            for piste in pistes
        ]
    )
    # Le lissage ôte le liseré que les arrondis de `buffer` laissent le long
    # des bandes : ce qui reste est l'évasement, et lui seul.
    ajout = union.difference(bandes).buffer(-0.01).buffer(0.01)
    assert ajout.area > 10.0, "le raccord doit bien combler quelque chose"

    fermeture = bandes.buffer(RAYON_INTERIEUR_M, join_style="round").buffer(
        -RAYON_INTERIEUR_M, join_style="round"
    )
    assert ajout.difference(fermeture.buffer(0.05)).area == pytest.approx(0.0, abs=0.5)


# ---------------------------------------------------------------------------
# Les pistes écartées des tables (demande du 02/10/2026)
# ---------------------------------------------------------------------------


def test_une_piste_qui_mord_sur_une_rangee_s_en_ecarte_du_minimum():
    """« Des tables viennent se superposer à la piste », et il y a la place.

    La correction qui serre les pistes contre la clôture ne traite que celles
    qui la longent : une piste dessinée en plein champ au travers d'une rangée
    n'avait rien. Elle s'écarte maintenant du plus petit décalage qui dégage
    les tables, et pas d'un centimètre de plus — c'est une correction du plan,
    et une correction se tient au minimum.
    """
    from shapely.geometry import LineString, box

    from dp_socle.plan_pdf import _pistes_hors_des_tables

    rangee = box(0.0, 0.0, 100.0, 2.0)
    # Bande de 5 m centrée sur y = 4 : elle déborde de 0,5 m sur la rangée.
    axe = AxePiste(
        "piste_lourde_a_creer", "Piste", LineString([(0.0, 4.0), (100.0, 4.0)])
    )
    pistes, _ = dessiner_pistes([axe])
    assert pistes[0].surface.intersection(rangee).area == pytest.approx(50.0, abs=1.0)

    correction, ecartes, note = _pistes_hors_des_tables([axe], pistes, [rangee], None)
    assert correction is not None and note is None
    assert correction.retrait_m == pytest.approx(0.5, abs=0.05)

    apres, _ = dessiner_pistes(ecartes)
    assert apres[0].surface.intersection(rangee).area == pytest.approx(0.0, abs=0.05)


def test_une_piste_dessinee_au_travers_d_une_rangee_le_dit_au_lieu_de_se_taire():
    """Chercher et renoncer n'est pas la même chose que ne rien voir.

    Une piste dont l'axe passe dans la rangée demanderait plus de trois mètres
    de décalage — `DECALAGE_PISTE_MAX_M`, au-delà duquel le bout de la piste
    quitte le tracé voisin auquel il se raccorde. Rien n'est proposé, et c'est
    dit : sans cela le chef de projet croirait que l'outil n'a rien vu.
    """
    from shapely.geometry import LineString, box

    from dp_socle.plan_pdf import _pistes_hors_des_tables

    rangee = box(0.0, 0.0, 100.0, 2.0)
    axe = AxePiste(
        "piste_lourde_a_creer", "Piste", LineString([(0.0, 1.0), (100.0, 1.0)])
    )
    pistes, _ = dessiner_pistes([axe])

    correction, ecartes, note = _pistes_hors_des_tables([axe], pistes, [rangee], None)
    assert correction is None
    assert ecartes == [axe], "le tracé du plan reste tel quel"
    assert "au travers d'une rangée" in note and "3 m" in note


def test_une_piste_a_l_ecart_des_tables_ne_declenche_rien():
    """Pas de correction sans objet, et pas de message sans objet non plus."""
    from shapely.geometry import LineString, box

    from dp_socle.plan_pdf import _pistes_hors_des_tables

    rangee = box(0.0, 0.0, 100.0, 2.0)
    axe = AxePiste(
        "piste_lourde_a_creer", "Piste", LineString([(0.0, 20.0), (100.0, 20.0)])
    )
    pistes, _ = dessiner_pistes([axe])

    correction, ecartes, note = _pistes_hors_des_tables([axe], pistes, [rangee], None)
    assert correction is None and note is None and ecartes == [axe]


# ---------------------------------------------------------------------------
# La largeur annoncée en légende prend le pas sur les 5 m (05/10/2026)
# ---------------------------------------------------------------------------


def test_une_piste_porte_la_largeur_de_sa_legende():
    """« Piste à créer (4 m de large) » se dessine à 4 m, pas à 5.

    Décision du chef de projet du 05/10/2026 : le plan sait ce qu'il dessine,
    et l'élargir le contredit. À La Chapelle-sous-Aubenas ce mètre de trop
    faisait passer le poste de livraison, à 2,30 m de l'axe, au-dedans de la
    bande — donc hors de portée de la correction qui cale les ouvrages, dont
    la règle du centre protège ce qui est dessiné sur la piste.
    """
    from dp_socle.pistes import AxePiste, dessiner_pistes

    trace = LineString([(0.0, 0.0), (120.0, 0.0)])
    etroite, _ = dessiner_pistes([AxePiste("piste_lourde_a_creer", "p", trace, 4.0)])
    large, _ = dessiner_pistes([AxePiste("piste_lourde_a_creer", "p", trace)])

    assert etroite[0].largeur_m == 4.0
    assert large[0].largeur_m == 5.0
    # Mesuré sur la bande produite, et non sur la valeur déclarée.
    assert etroite[0].surface.area / trace.length == pytest.approx(4.0, rel=1e-3)
    assert large[0].surface.area / trace.length == pytest.approx(5.0, rel=1e-3)


def test_le_rayon_de_l_axe_suit_la_largeur():
    """Le rayon imposé est celui du bord intérieur : sur l'axe, il suit la largeur.

    11 m au bord intérieur font 13 m sur l'axe d'une piste de 4 m, 13,5 m sur
    celui d'une piste de 5 m. Arrondir une piste de 4 m à 13,5 m lui donnerait
    un bord intérieur de 11,5 m — pas faux, mais ce n'est plus la règle ; et
    l'inverse, 13 m sur une piste de 5 m, descendrait son bord à 10,5 m, en
    deçà de la « voie engins ».
    """
    from dp_socle.pistes import RAYON_INTERIEUR_M, rayon_axe

    assert rayon_axe(4.0) == pytest.approx(13.0)
    assert rayon_axe(5.0) == pytest.approx(13.5)
    assert rayon_axe(4.0) - 4.0 / 2.0 == pytest.approx(RAYON_INTERIEUR_M)


def test_la_piste_serree_contre_la_cloture_garde_sa_largeur():
    """Serrer une piste de 4 m ne doit pas la reporter comme une piste de 5 m.

    L'axe est reporté sur la clôture décalée de la demi-largeur et du jeu : à
    5 m supposés, une piste de 4 m se serait retrouvée à 1 m de la clôture au
    lieu de 0,5, et sa bande aurait laissé un mètre de perdu le long d'elle.
    """
    from shapely.geometry import Polygon

    from dp_socle.pistes import JEU_CLOTURE_M, serrer_contre

    enceinte = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    trace = LineString([(2.0, 2.0), (2.0, 98.0)])
    for largeur in (4.0, 5.0):
        axe = serrer_contre(trace, enceinte, largeur_m=largeur)
        assert axe is not None, largeur
        bande = axe.buffer(largeur / 2.0, cap_style="flat", join_style="round")
        assert bande.distance(enceinte.exterior) == pytest.approx(
            JEU_CLOTURE_M, abs=0.05
        ), largeur
