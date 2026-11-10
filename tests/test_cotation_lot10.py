"""Lot 10 — le calcul des cotes du plan de masse, sans PDF.

Les cotes se calculent dans `planches/cotation_plan_masse.py`, à part du dessin,
pour se vérifier ici sur des cas construits aux cotes connues : une clôture en
retrait de 6 m se cote 6,0 m, et non une valeur relue au même code. Les cas
suivent la liste « Comment le tester » du brief
(`_briefs/BRIEF_DP_lot10_cotation_plan_masse.md`), et chacun dit le piège mesuré
qu'il garde. Leur pose sur la DP 2, mesurée dans le PDF, est l'affaire des
étapes suivantes du lot.
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import LineString, Point, Polygon, box

from dp_socle.ign import Parcelle
from dp_socle.planches import cotation_plan_masse as cotation

from . import contrat_synthetique as synthese

X0, Y0 = synthese.ORIGINE_L93


def boite(x0, y0, x1, y1):
    """Un rectangle du site, en mètres depuis son coin sud-ouest."""
    return box(X0 + x0, Y0 + y0, X0 + x1, Y0 + y1)


def point(x, y):
    return (X0 + x, Y0 + y)


def parcelle(geometrie, numero="0001"):
    return Parcelle(
        geometrie=geometrie,
        idu=f"450000000ZA{numero}",
        section="ZA",
        numero=numero,
        contenance_m2=geometrie.area,
        commune="Essai",
    )


# ---------------------------------------------------------------------------
# D4 — la limite est celle des parcelles d'assiette, par la règle de la DP 1-3
# ---------------------------------------------------------------------------


def test_la_limite_entre_deux_parcelles_d_assiette_n_est_pas_une_limite():
    """L'union des parcelles d'assiette efface la limite qu'elles partagent.

    Elle n'est pas séparative : une cote qui s'y arrêterait mesurerait jusqu'au
    milieu du terrain. Et une parcelle que l'emprise n'entame qu'en écharde,
    sous `PART_MIN_ASSIETTE`, n'est pas du terrain d'assiette.
    """
    a = boite(0, 0, 100, 100)
    b = boite(100, 0, 200, 100)
    voisine = boite(0, 100, 200, 300)
    # L'emprise mord d'un mètre sur la voisine : 200 m² sur 40 000, 0,5 %.
    emprise = boite(0, 0, 200, 101)

    terrain = cotation.terrain_d_assiette(
        [parcelle(a, "0001"), parcelle(b, "0002"), parcelle(voisine, "0003")], emprise
    )

    assert terrain.area == pytest.approx(20_000.0)
    # Au milieu de la limite commune, la limite la plus proche est à 50 m.
    assert terrain.boundary.distance(Point(point(100, 50))) == pytest.approx(50.0)


def test_sans_parcelle_d_assiette_il_n_y_a_pas_de_terrain():
    voisine = boite(0, 100, 200, 300)
    assert cotation.terrain_d_assiette([parcelle(voisine)], boite(0, 0, 200, 101)) is None


# ---------------------------------------------------------------------------
# Les côtés de la clôture : ils groupent et orientent, ils ne mesurent pas
# ---------------------------------------------------------------------------


def _pans(cloture, rapport=None):
    rapport = [] if rapport is None else rapport
    return cotation.pans_de_la_cloture(cotation.enclos_de_la_cloture([cloture], rapport))


def _longueurs(pans):
    return sorted(round(pan.longueur_m, 1) for pan in pans)


def test_une_cloture_rectangulaire_a_quatre_cotes():
    pans = _pans(boite(0, 0, 200, 120))
    assert _longueurs(pans) == [120.0, 120.0, 200.0, 200.0]


def test_un_troncon_de_moins_de_vingt_metres_n_est_pas_un_cote():
    """Une encoche de 15 x 10 m dans le côté nord : ses trois tronçons ne comptent pas."""
    cloture = Polygon([
        point(0, 0), point(200, 0), point(200, 120), point(110, 120),
        point(110, 110), point(95, 110), point(95, 120), point(0, 120),
    ])
    pans = _pans(cloture)
    assert _longueurs(pans) == [90.0, 95.0, 120.0, 120.0, 200.0]


def test_un_cote_dessine_en_zigzag_fin_reste_un_seul_cote():
    """Le côté sud en vingt segments qui s'écartent de 0,5 m : la simplification à 1,5 m les redresse."""
    sud = [point(10 * k, 0.5 * (k % 2)) for k in range(21)]
    cloture = Polygon(sud + [point(200, 120), point(0, 120)])
    pans = _pans(cloture)
    assert _longueurs(pans) == [120.0, 120.0, 200.0, 200.0]


def test_une_courbe_douce_se_fond_en_un_seul_cote():
    """Un arc de 300 m de rayon tourne de moins de 25° d'un segment à l'autre.

    Le contour commence au milieu du côté sud : le premier et le dernier
    segment du tracé se rejoignent en un seul côté.
    """
    rayon = 300.0
    centre_y = 100.0 - math.sqrt(rayon**2 - 100.0**2)
    depart = math.atan2(100.0 - centre_y, 100.0)
    arc = [
        point(100.0 + rayon * math.cos(t), centre_y + rayon * math.sin(t))
        for t in (depart + k * (math.pi - 2 * depart) / 40 for k in range(41))
    ]
    cloture = Polygon([point(100, 0), point(200, 0)] + arc + [point(0, 0)])
    pans = _pans(cloture)
    longueurs = _longueurs(pans)
    assert len(longueurs) == 4
    assert longueurs[:3] == [100.0, 100.0, 200.0]
    # L'arc, simplifié en cordes : un peu moins que ses 203,4 m.
    assert longueurs[3] == pytest.approx(203.0, abs=1.0)


# ---------------------------------------------------------------------------
# C1 — tables → limite parcellaire, et clôture → limite parcellaire
# ---------------------------------------------------------------------------


def _site_c1():
    """Un terrain de 300 x 200 m ; la clôture en retrait de 6 m au sud, de 10 m
    à l'ouest et à l'est, sur la limite au nord ; cinq rangées de tables."""
    terrain = boite(0, 0, 300, 200)
    cloture = boite(10, 6, 290, 200)
    tables = [boite(35, 20 + 10 * k, 265, 24 + 10 * k) for k in range(5)]
    return terrain, cloture, tables


def _cotes_c1(terrain, cloture, tables, denominateur=2000):
    rapport = []
    resultats = cotation.cotes_tables_cloture_limite(
        _pans(cloture, rapport), tables, terrain, denominateur, rapport
    )
    return resultats, rapport


def test_la_cote_des_tables_traverse_la_cloture_jusqu_a_la_limite():
    """Les deux demandes visent la distance aux limites, pas à la clôture (08/11)."""
    resultats, _ = _cotes_c1(*_site_c1())

    assert sorted(r.tables_limite.valeur_m for r in resultats) == pytest.approx(
        [20.0, 35.0, 35.0]
    )
    sud = min(resultats, key=lambda r: r.tables_limite.valeur_m)
    assert sud.tables_limite.texte == "20,0 m (tables – limite parcellaire)"
    assert sud.tables_limite.famille == "C1"
    # Sa valeur se pose de préférence au-delà de la limite (D8).
    assert sud.tables_limite.vers_la_limite
    # De la table, à 20 m de la limite, à la limite : la clôture est traversée.
    assert sud.tables_limite.depart[1] == pytest.approx(Y0 + 20.0)
    assert sud.tables_limite.arrivee[1] == pytest.approx(Y0)


def test_un_cote_dont_les_tables_sont_a_plus_de_30_m_ne_se_cote_pas():
    resultats, rapport = _cotes_c1(*_site_c1())
    # Le côté nord : les tables en sont à 136 m.
    assert len(resultats) == 3
    assert any("136,0 m" in message for message in rapport)


def test_la_cloture_en_retrait_se_cote_a_la_limite_depuis_son_trace_reel():
    resultats, _ = _cotes_c1(*_site_c1())
    sud = min(resultats, key=lambda r: r.tables_limite.valeur_m)

    assert sud.places_cloture
    for place in sud.places_cloture:
        assert place.valeur_m == pytest.approx(6.0)
        assert place.texte == "6,0 m (clôture – limite parcellaire)"
        assert place.vers_la_limite
        # Perpendiculaire au côté, de la clôture à la limite.
        assert place.depart[1] == pytest.approx(Y0 + 6.0)
        assert place.arrivee[1] == pytest.approx(Y0)
        assert place.depart[0] == pytest.approx(place.arrivee[0])
        # À 20 mm de papier au moins de la première cote, soit 40 m au 1:2 000.
        assert place.ligne.distance(sud.tables_limite.ligne) >= 40.0


def test_la_cote_de_la_cloture_se_pose_la_ou_elle_gene_le_moins():
    """Au milieu du côté, elle tombait à Auzainvilliers parmi d'autres cotes (08/11)."""
    resultats, _ = _cotes_c1(*_site_c1())
    sud = min(resultats, key=lambda r: r.tables_limite.valeur_m)
    autre = cotation.CoteAPoser(
        famille="C6", depart=point(150, 30), arrivee=point(150, 2),
        texte="28,0 m (piste)", valeur_m=28.0,
    )

    choisie = cotation.choisir_la_place_cloture_limite(
        sud.places_cloture, [sud.tables_limite, autre]
    )

    # Parmi 35, 50, 65, 20 et 80 % du côté, la place la plus loin des deux
    # cotes : à 84 m de l'autre, et plus loin encore de la cote des tables.
    assert abs(choisie.depart[0] - (X0 + 150.0)) == pytest.approx(84.0)
    assert choisie.ligne.distance(sud.tables_limite.ligne) > 84.0


def test_la_cote_de_la_cloture_s_ecarte_aussi_de_la_ligne_de_coupe():
    """Confondue avec la ligne de coupe, sa valeur n'avait plus de place (09/11/2026).

    Sur le site synthétique de la DP 2, la coupe nord-sud passe au milieu du
    côté sud, là où la cote clôture → limite s'essaie d'abord : sa ligne se
    confondait avec le trait d'axe, et sa valeur, qui ne doit pas couper la
    ligne de coupe (D8), a été posée au mieux. Pour le choix de la place, la
    ligne de coupe compte comme une autre cote.
    """
    resultats, _ = _cotes_c1(*_site_c1())
    sud = min(resultats, key=lambda r: r.tables_limite.valeur_m)
    seule = cotation.choisir_la_place_cloture_limite(sud.places_cloture, [sud.tables_limite])
    # La coupe passe là où la cote se serait posée sans elle.
    x = seule.depart[0]
    coupe = LineString([(x, Y0 - 50.0), (x, Y0 + 250.0)])

    choisie = cotation.choisir_la_place_cloture_limite(
        sud.places_cloture, [sud.tables_limite], traits=[coupe]
    )

    def eloignement(place):
        return min(place.ligne.distance(sud.tables_limite.ligne), place.ligne.distance(coupe))

    assert choisie.ligne.distance(coupe) > 0.0
    assert eloignement(choisie) == max(eloignement(p) for p in sud.places_cloture)
    assert cotation.choisir_les_places_cloture_limite(
        [sud], [sud.tables_limite], traits=[coupe]
    ) == [choisie]


def test_les_cotes_de_cloture_deja_choisies_comptent_pour_les_suivantes():
    """Choisie la première, la cote d'un côté écarte celle du côté voisin.

    C'est le choix de la maquette (v7, 09/11/2026) : chaque cote choisie
    rejoint les cotes posées avant le choix suivant. Choisies chacune pour soi,
    deux cotes de part et d'autre d'un angle peuvent tomber au pied l'une de
    l'autre.
    """
    # Deux tables, l'une au sud-est, l'autre au nord-ouest : la cote des
    # tables de chaque côté tombe à un bout, et la place la plus libre de
    # chaque côté, à l'autre bout — au sud-ouest pour les côtés sud et ouest,
    # au nord-est pour les côtés nord et est.
    terrain = boite(0, 0, 300, 300)
    cloture = boite(10, 10, 290, 290)
    tables = [boite(250, 25, 270, 29), boite(25, 250, 29, 270)]
    resultats, _ = _cotes_c1(terrain, cloture, tables)
    assert len(resultats) == 4

    choisies = cotation.choisir_les_places_cloture_limite(
        resultats, [r.tables_limite for r in resultats]
    )

    assert len(choisies) == 4
    # Choisies chacune pour soi, les deux d'un même angle seraient à 79 m
    # l'une de l'autre ; la seconde s'écarte de la première, à 113 m.
    ecarts = [a.ligne.distance(b.ligne) for k, a in enumerate(choisies) for b in choisies[k + 1:]]
    assert min(ecarts) == pytest.approx(math.hypot(56.0, 98.0))


def test_une_cloture_sur_la_limite_tracee_en_arrondis_n_a_pas_de_seconde_cote():
    """Mesurée depuis le tracé simplifié, elle valait 0,9 et 1,0 m à Saint-Cyr (08/11).

    Au nord, la limite ondule de 1,2 m autour d'une droite, et la clôture la
    suit au point près. Simplifiée à 1,5 m, la clôture devient cette droite, et
    s'écarte de la limite jusqu'à 1,2 m aux endroits essayés : l'écart doit se
    prendre sur la clôture réelle, où il est nul, et la cote ne pas se poser.
    """
    # L'onde est nulle aux deux bouts : la corde qui la redresse est horizontale.
    onde = [point(x, 150.0 + 1.2 * math.sin(2 * math.pi * x / 50.0)) for x in range(300, -1, -1)]
    terrain = Polygon([point(0, 0), point(300, 0)] + onde)
    cloture = terrain.intersection(boite(0, 5, 300, 1000))
    tables = [boite(35, 20 + 10 * k, 265, 24 + 10 * k) for k in range(13)]

    resultats, rapport = _cotes_c1(terrain, cloture, tables)

    (arrondi,) = [r for r in resultats if r.pan.trace.centroid.y > Y0 + 140.0]
    # Le côté est bien redressé par la simplification : c'est le piège.
    assert len(arrondi.pan.trace.coords) == 2
    assert arrondi.tables_limite.valeur_m > 0.0
    assert arrondi.places_cloture == []
    assert any("sur la limite" in message for message in rapport)
    # Le côté sud, en retrait de 5 m, garde la sienne.
    (sud,) = [r for r in resultats if r.pan.trace.centroid.y < Y0 + 10.0]
    assert sud.places_cloture[0].valeur_m == pytest.approx(5.0)


def test_la_cote_de_la_cloture_part_de_la_cloture_reelle_et_non_du_cote_simplifie():
    """Une clôture qui ondule de 1,2 m autour de 6 m de retrait.

    Le côté simplifié est la droite à 6 m. Une cote qui en partirait vaudrait
    6,0 m partout et commencerait dans le vide, à côté du trait de la clôture :
    juste en apparence, fausse sur le fond.
    """
    # Nulle aux deux bouts, comme plus haut : le côté simplifié est horizontal.
    onde = [point(x, 6.0 + 1.2 * math.sin(2 * math.pi * x / 50.0)) for x in range(25, 276)]
    cloture = Polygon(onde + [point(275, 200), point(25, 200)])
    terrain = boite(0, 0, 300, 200)
    tables = [boite(35, 20 + 10 * k, 265, 24 + 10 * k) for k in range(5)]

    resultats, _ = _cotes_c1(terrain, cloture, tables)

    (sud,) = [r for r in resultats if r.pan.trace.centroid.y < Y0 + 10.0]
    assert len(sud.pan.trace.coords) == 2
    assert sud.places_cloture
    for place in sud.places_cloture:
        assert Point(place.depart).distance(cloture.exterior) < 1e-6
        assert place.valeur_m == pytest.approx(place.depart[1] - Y0)
    assert max(abs(p.valeur_m - 6.0) for p in sud.places_cloture) > 0.5


def test_un_cote_trop_court_pour_deux_cotes_n_en_recoit_qu_une():
    """Deux côtés de 30 m au 1:2 000 : les 20 mm d'écart y feraient 40 m."""
    terrain = boite(0, 0, 80, 100)
    cloture = boite(10, 10, 40, 90)
    tables = [boite(15, 20, 35, 80)]

    resultats, rapport = _cotes_c1(terrain, cloture, tables)

    courts = [r for r in resultats if r.pan.longueur_m == pytest.approx(30.0)]
    assert len(courts) == 2
    for court in courts:
        assert court.tables_limite.valeur_m == pytest.approx(20.0)
        assert court.places_cloture == []
    assert sum("trop près" in message for message in rapport) == 2
    # Les côtés de 80 m, eux, ont la place.
    longs = [r for r in resultats if r.pan.longueur_m == pytest.approx(80.0)]
    assert sorted(r.places_cloture[0].valeur_m for r in longs) == pytest.approx([10.0, 40.0])


def test_une_cloture_sans_cote_exploitable_se_dit():
    """Une clôture restée ouverte n'a pas d'enclos, donc pas de côté : C1 ne
    disparaît pas sans un mot."""
    terrain, _, tables = _site_c1()
    ouverte = LineString([point(10, 6), point(290, 6), point(290, 200)])

    resultats, rapport = _cotes_c1(terrain, ouverte, tables)

    assert resultats == []
    assert any("aucun côté" in m for m in rapport)
    # Ses deux bouts sont à 340,6 m l'un de l'autre : ce n'est pas un jeu de tracé.
    assert any("340,6 m" in m for m in rapport)


def test_une_table_hors_du_terrain_ne_se_cote_pas_a_la_limite():
    """Partie de l'extérieur, la cote mesurerait l'entrée dans le terrain, pas sa limite."""
    terrain = boite(0, 0, 300, 200)
    # La clôture et les tables débordent du terrain par le sud : le plan sort
    # de l'emprise.
    cloture = boite(10, -15, 290, 200)
    tables = [boite(35, -10, 265, 24)]

    resultats, rapport = _cotes_c1(terrain, cloture, tables)

    assert all(r.tables_limite.depart[1] > Y0 for r in resultats)
    assert any("hors du terrain d'assiette" in message for message in rapport)


# ---------------------------------------------------------------------------
# D2 et D3 — les ouvrages permanents, mesurés sur leur corps
# ---------------------------------------------------------------------------

#: Les gabarits UNITe, tels que le tableau bilan les porte : relevés au contrat
#: d'Auzainvilliers IND03 le 09/11/2026, et réduits à ce que les cas emploient.
#: L'ordre des cotes change d'un ouvrage à l'autre, comme au tableau.
CATALOGUE = [
    {"ouvrage": "Poste de transformation - PTR", "dimensions": "10 x 3 x 3m",
     "ordre_cotes": "largeur x longueur x hauteur", "surface_m2": 30.0,
     "surface_plateforme_m2": 115.0},
    {"ouvrage": "Poste de livraison et de transformation - PDL/PTR",
     "dimensions": "12 x 3 x 3m", "ordre_cotes": "largeur x longueur x hauteur",
     "surface_m2": 36.0, "surface_plateforme_m2": 132.0},
    {"ouvrage": "Local de stockage matériel — P<=5MWc",
     "dimensions": "1 conteneur 20 pieds 6 x 3 x 3m",
     "ordre_cotes": "largeur x longueur x hauteur", "surface_m2": 18.0,
     "surface_plateforme_m2": None},
    {"ouvrage": "Local de stockage matériel — P>5MWc",
     "dimensions": "1 conteneur 40 pieds 12 x 3 x 3m",
     "ordre_cotes": "largeur x longueur x hauteur", "surface_m2": 36.0,
     "surface_plateforme_m2": None},
    {"ouvrage": "Aire de charge (BESS) — Conteneurs", "dimensions": "6 x 3 x 3m",
     "ordre_cotes": "longueur x largeur x hauteur", "surface_m2": 18.0,
     "surface_plateforme_m2": 50.0},
    {"ouvrage": "Aire de charge (BESS) — Citerne de refroidissement",
     "dimensions": "11,7 x 9,3 x 1 m", "ordre_cotes": "longueur x largeur x hauteur",
     "surface_m2": 104.0, "surface_plateforme_m2": None},
    {"ouvrage": "Aire de charge (BESS) — Bac de rétention",
     "dimensions": "17,5 x 3 x 2,3 m", "ordre_cotes": "longueur x largeur x hauteur",
     "surface_m2": 55.0, "surface_plateforme_m2": None},
    {"ouvrage": "Aire de charge (BESS) — Zone de remise", "dimensions": "12 x 3 x 3m",
     "ordre_cotes": "longueur x largeur x hauteur", "surface_m2": 36.0,
     "surface_plateforme_m2": None},
    {"ouvrage": "Citerne incendie — 30", "dimensions": "7,95 x 4,44 x 1,3 m",
     "ordre_cotes": "longueur x largeur x hauteur", "surface_m2": None,
     "surface_plateforme_m2": 35.0},
    {"ouvrage": "Citerne incendie — 120", "dimensions": "11,7 x 9,3 x 1 m",
     "ordre_cotes": "longueur x largeur x hauteur", "surface_m2": None,
     "surface_plateforme_m2": 104.0},
]


def _contrat(dossier, calques: dict, structures=None, catalogue=None):
    """Un contrat qui ne porte que `calques`, `{catégorie: géométries}`.

    Écrit par les producteurs réels, `ecrire_geopackage` et `ecrire_parametres`,
    et relu par `charger_contrat` : c'est le chemin de la génération.
    """
    from dp_socle.contrat import charger_contrat
    from dp_socle.import_be import EntiteBE, ecrire_geopackage, ecrire_parametres

    lot = [
        EntiteBE(categorie=categorie, calque="ESSAI", geometrie=g, z_reel=False)
        for categorie, geometries in calques.items()
        for g in geometries
    ]
    ecrire_geopackage(lot, dossier, None)
    donnees = synthese.parametres()
    donnees["cotes_normalisees"] = CATALOGUE if catalogue is None else catalogue
    donnees["parametres"]["structures"].update(structures or {})
    ecrire_parametres(donnees, dossier)
    return charger_contrat(dossier)


def _ouvrages_du_contrat(contrat):
    from dp_socle.planches.palette import objets_a_dessiner

    rapport = []
    ouvrages = cotation.ouvrages_permanents(contrat, objets_a_dessiner(contrat, []), rapport)
    return ouvrages, rapport


def test_un_ouvrage_se_mesure_sur_son_corps_et_non_sur_ce_qui_l_entoure(tmp_path):
    """À Auzainvilliers, la cote prise sur le conteneur s'arrêtait au milieu de l'orange.

    Chaque BESS de 6 x 3 m y est posé sur un aplat de 6,0 x 8,1 m, et le poste
    de Saint-Cyr est bordé de deux bandes de terre remise : le corps est l'objet
    aux cotes du catalogue, que la palette sépare (D3).
    """
    contrat = _contrat(tmp_path, {
        "pdl_ptr": [boite(100, 100, 112, 103), boite(100, 103, 112, 104.5),
                    boite(100, 98.5, 112, 100)],
        "bess": [boite(150, 99, 158.06, 105), boite(151, 100, 157.06, 103)],
    })

    ouvrages, _ = _ouvrages_du_contrat(contrat)

    assert sorted((o.categorie, round(o.geometrie.area, 2)) for o in ouvrages) == [
        ("bess", 18.18), ("pdl_ptr", 36.0),
    ]


def test_les_ouvrages_temporaires_et_les_sols_ne_se_cotent_pas(tmp_path):
    """D2 : la base vie et le stockage de chantier sont temporaires, le bac
    d'équarrissage et la contention relèvent du pâturage, l'aire d'aspiration
    et la plateforme sont des sols. Le bac de rétention et la zone de remise,
    eux, sont des constructions (04/11/2026)."""
    contrat = _contrat(tmp_path, {
        "base_vie": [boite(10, 10, 22, 13)],
        "stockage_chantier": [boite(30, 10, 60, 40)],
        "bac_equarrissage": [boite(70, 10, 72, 12)],
        "zone_contention": [boite(80, 10, 90, 20)],
        "aire_aspiration": [boite(100, 10, 108, 14)],
        "plateforme": [boite(120, 10, 140, 25)],
        "bac_retention": [boite(150, 10, 166.9, 13)],
        "zone_remise": [boite(170, 10, 182.01, 13)],
    })

    ouvrages, _ = _ouvrages_du_contrat(contrat)

    assert sorted(o.categorie for o in ouvrages) == ["bac_retention", "zone_remise"]


def test_deux_corps_qui_se_touchent_font_un_seul_ouvrage(tmp_path):
    """À 2,5 cm près ; deux conteneurs écartés de 4 cm en sont deux."""
    contrat = _contrat(tmp_path, {
        "local_technique": [
            boite(100, 100, 106, 103), boite(106.02, 100, 112.02, 103),
            boite(112.06, 100, 118.06, 103),
        ],
    })

    ouvrages, _ = _ouvrages_du_contrat(contrat)

    assert sorted(round(o.geometrie.area, 1) for o in ouvrages) == [18.0, 36.0]
    (double,) = [o for o in ouvrages if o.geometrie.area > 20]
    assert len(double.corps) == 2


def test_un_ouvrage_sans_objet_aux_cotes_du_catalogue_se_mesure_sur_tout_son_dessin(tmp_path):
    """Une citerne de 15 x 15 m : aucune variante du catalogue n'en a la surface."""
    contrat = _contrat(tmp_path, {"bache_incendie": [boite(100, 100, 115, 115)]})

    ouvrages, rapport = _ouvrages_du_contrat(contrat)

    (citerne,) = ouvrages
    assert citerne.geometrie.area == pytest.approx(225.0)
    assert any("bache_incendie" in m and "toutes ses surfaces" in m for m in rapport)


def test_une_citerne_arrivee_en_collection_de_geometries_se_mesure(tmp_path):
    """Le contour auto-intersectant d'Auzainvilliers : `make_valid` en fait une
    collection, et une version de la maquette la sortait des cotes sans un mot."""
    noeud = Polygon([point(100, 100), point(111.7, 100), point(111.7, 109.3),
                     point(105, 109.3), point(105, 112), point(105, 109.3),
                     point(100, 109.3)])
    contrat = _contrat(tmp_path, {"citerne_refroidissement": [noeud]})
    assert contrat.geometries("citerne_refroidissement")[0].geom_type == "GeometryCollection"

    ouvrages, _ = _ouvrages_du_contrat(contrat)

    (citerne,) = ouvrages
    assert citerne.geometrie.area == pytest.approx(11.7 * 9.3)


def test_un_ouvrage_sans_surface_a_mesurer_se_dit(tmp_path):
    """Un contour resté ouvert ne se mesure pas : il se dit, il ne disparaît pas."""
    ouvert = LineString([point(100, 100), point(117.5, 100), point(117.5, 103)])
    contrat = _contrat(tmp_path, {"bac_retention": [ouvert]})

    ouvrages, rapport = _ouvrages_du_contrat(contrat)

    assert ouvrages == []
    assert any("bac_retention" in m and "aucune surface" in m for m in rapport)


# ---------------------------------------------------------------------------
# C3 — un ouvrage → ses voisins directs, et → la limite parcellaire
# ---------------------------------------------------------------------------


def ouvrage(categorie, geometrie):
    return cotation.Ouvrage(categorie=categorie, geometrie=geometrie, corps=(geometrie,))


LIMITE = boite(0, 0, 300, 200).boundary


def _paires(cotes):
    return sorted(tuple(sorted(c.ouvrages)) for c in cotes if len(c.ouvrages) == 2)


def _a_la_limite(cotes, ouvrages):
    return {
        ouvrages[c.ouvrages[0]].categorie: c for c in cotes if len(c.ouvrages) == 1
    }


def test_trois_conteneurs_alignes_ne_se_cotent_pas_du_premier_au_troisieme():
    """Sans la règle de la paire séparée, la cote du premier au troisième
    traverserait le deuxième."""
    conteneurs = [
        ouvrage("bess", boite(100 + 11 * k, 100, 106 + 11 * k, 103)) for k in range(3)
    ]
    rapport = []

    cotes = cotation.cotes_entre_ouvrages(conteneurs, LIMITE, rapport)

    assert _paires(cotes) == [(0, 1), (1, 2)]
    # Et la paire écartée se dit : une cote qu'une règle écarte n'est pas
    # retirée en silence (D9).
    assert any("16,0 m" in m and "posé sur le segment" in m for m in rapport)
    entre = [c for c in cotes if len(c.ouvrages) == 2]
    assert [c.texte for c in entre] == ["5,0 m", "5,0 m"]
    assert all(c.famille == "C3" and not c.vers_la_limite for c in entre)


def test_une_paire_qu_un_troisieme_ouvrage_situe_deja_ne_se_cote_pas():
    """Le voisinage relatif : à Auzainvilliers, 9 cotes au lieu de 24 paires (10/11)."""
    ouvrages = [
        ouvrage("ptr", boite(100, 100, 110, 103)),
        ouvrage("bess", boite(130, 100, 136.06, 103)),
        ouvrage("pdl_ptr", boite(112, 110, 124, 113)),
    ]
    rapport = []

    cotes = cotation.cotes_entre_ouvrages(ouvrages, LIMITE, rapport)

    # ptr — bess, à 20 m : le PDL/PTR est plus près de chacun des deux.
    assert _paires(cotes) == [(0, 2), (1, 2)]
    assert any("« ptr »" in m and "« bess »" in m and "« pdl_ptr »" in m
               and "plus proche" in m for m in rapport)


def test_un_ouvrage_se_cote_a_la_limite_en_deca_de_30_m():
    ouvrages = [
        ouvrage("ptr", boite(100, 12, 110, 15)),
        ouvrage("pdl_ptr", boite(200, 35, 212, 38)),
    ]
    rapport = []

    cotes = cotation.cotes_entre_ouvrages(ouvrages, LIMITE, rapport)

    limites = _a_la_limite(cotes, ouvrages)
    assert set(limites) == {"ptr"}
    assert limites["ptr"].texte == "12,0 m (limite parcellaire)"
    assert limites["ptr"].vers_la_limite
    assert any("« pdl_ptr »" in m and "35,0 m" in m for m in rapport)


def test_sans_limite_connue_les_ouvrages_ne_se_cotent_pas_a_la_limite_et_le_rapport_le_dit():
    ouvrages = [ouvrage("bess", boite(150, 30.9, 156.06, 33.9))]
    rapport = []

    cotes = cotation.cotes_entre_ouvrages(ouvrages, None, rapport)

    assert cotes == []
    assert any("pas de limite" in m for m in rapport)


def test_les_batteries_et_le_local_de_stockage_se_cotent_toujours_a_la_limite():
    """Sans seuil, et même par-dessus un autre ouvrage : c'est eux que
    l'instructeur nomme (04/11/2026). Le rapport dit la règle franchie."""
    ouvrages = [
        ouvrage("bess", boite(150, 30.9, 156.06, 33.9)),
        ouvrage("local_technique", boite(50, 20, 56, 23)),
        ouvrage("pdl_ptr", boite(47, 10, 59, 13)),
        ouvrage("ptr", boite(250, 20, 260, 23)),
        ouvrage("bac_retention", boite(246, 10, 263.5, 13)),
    ]
    rapport = []

    cotes = cotation.cotes_entre_ouvrages(ouvrages, LIMITE, rapport)

    limites = _a_la_limite(cotes, ouvrages)
    assert {k: round(c.valeur_m, 1) for k, c in limites.items()} == {
        "bess": 30.9, "local_technique": 20.0, "pdl_ptr": 10.0, "bac_retention": 10.0,
    }
    assert any("« bess »" in m and "au-delà de 30 m" in m for m in rapport)
    assert any("« local_technique »" in m and "par-dessus" in m and "« pdl_ptr »" in m
               for m in rapport)
    # Le PTR, derrière le bac, n'est pas de ceux qu'on cote toujours.
    assert any("« ptr »" in m and "« bac_retention »" in m for m in rapport)


# ---------------------------------------------------------------------------
# C7 — batteries et citernes → la table la plus proche
# ---------------------------------------------------------------------------

TABLES_C7 = [boite(0, 50, 100, 54)]


def test_deux_bess_seul_le_plus_proche_des_tables_se_cote():
    """Le BESS nord d'Auzainvilliers, à 28,3 m quand le sud en est à 8,3 m :
    « pas utile » (09/11). Il est nommé au rapport, avec la distance du coté."""
    ouvrages = [
        ouvrage("bess", boite(40, 62.26, 46.06, 65.26)),
        ouvrage("bess", boite(60, 82.29, 66.06, 85.29)),
    ]
    rapport = []

    cotes = cotation.cotes_vers_les_tables(ouvrages, TABLES_C7, rapport)

    (cote,) = cotes
    assert cote.texte == "8,3 m (table la plus proche)"
    assert cote.famille == "C7" and cote.ouvrages == (0,)
    assert any("28,29 m" in m and "8,26 m" in m for m in rapport)


def test_un_bess_dont_la_table_est_derriere_un_autre_ouvrage_ne_se_cote_pas():
    """L'ouvrage qui s'intercale porte déjà la distance qui compte."""
    ouvrages = [
        ouvrage("bess", boite(40, 70, 46.06, 73)),
        ouvrage("citerne_refroidissement", boite(37, 58, 48.7, 67.3)),
    ]
    rapport = []

    cotes = cotation.cotes_vers_les_tables(ouvrages, TABLES_C7, rapport)

    assert [ouvrages[c.ouvrages[0]].categorie for c in cotes] == ["citerne_refroidissement"]
    assert cotes[0].valeur_m == pytest.approx(4.0)
    assert any("« bess »" in m and "s'intercale" in m for m in rapport)


def test_chaque_famille_a_sa_cote_vers_les_tables_et_les_postes_n_en_ont_pas():
    ouvrages = [
        ouvrage("bess", boite(10, 60, 16.06, 63)),
        ouvrage("citerne_refroidissement", boite(30, 60, 41.7, 69.3)),
        ouvrage("bache_incendie", boite(60, 62, 71.7, 71.3)),
        ouvrage("ptr", boite(80, 60, 90, 63)),
    ]

    cotes = cotation.cotes_vers_les_tables(ouvrages, TABLES_C7, [])

    assert sorted(ouvrages[c.ouvrages[0]].categorie for c in cotes) == [
        "bache_incendie", "bess", "citerne_refroidissement",
    ]


# ---------------------------------------------------------------------------
# C5 — l'écartement entre deux rangées, à la valeur de la coupe
# ---------------------------------------------------------------------------


def _rangees(ecart, nombre=6, largeur=4.0, longueur=100.0):
    """Des rangées est-ouest, larges de `largeur`, séparées de `ecart`."""
    pas = largeur + ecart
    return [boite(0, k * pas, longueur, k * pas + largeur) for k in range(nombre)]


def test_l_inter_rangee_se_cote_une_fois_sur_un_ecart_qui_vaut_la_coupe():
    """Au plus près du centre du champ, perpendiculairement aux rangées (D6)."""
    rapport = []

    cote = cotation.cote_inter_rangee(_rangees(4.5), 4.5, rapport)

    assert cote.texte == "4,5 m entre rangées"
    assert cote.famille == "C5"
    assert cote.longueur_m == pytest.approx(4.5)
    # Entre la troisième et la quatrième rangée, au milieu du champ.
    assert sorted((cote.depart[1] - Y0, cote.arrivee[1] - Y0)) == pytest.approx([21.0, 25.5])
    assert cote.depart[0] == pytest.approx(cote.arrivee[0])


def test_l_inter_rangee_dit_le_nombre_de_la_coupe():
    """Un écart de 4,6 m au plan pour 4,55 m à la coupe : la cote dit 4,55,
    comme la DP 3. Les deux planches ne disent qu'un nombre."""
    cote = cotation.cote_inter_rangee(_rangees(4.6), 4.55, [])

    assert cote.texte == "4,55 m entre rangées"


def test_sans_ecart_qui_vaille_la_coupe_l_inter_rangee_ne_se_cote_pas():
    """Plaquer 4,5 m sur un écart de 4,9 m, ce serait la planche fausse qui
    s'affiche correctement. À Saint-Cyr, IND06 et IND07 ont 4,9 et 4,5 m."""
    rapport = []

    assert cotation.cote_inter_rangee(_rangees(4.9), 4.5, rapport) is None
    assert any("4,5 m" in m and "4,9" in m for m in rapport)


def test_l_ecart_entre_deux_tables_d_une_meme_rangee_n_est_pas_un_inter_rangee():
    """Deux tables bout à bout, à 4,5 m l'une de l'autre, dans des rangées à 6 m."""
    tables = []
    for rangee in _rangees(6.0):
        x0, y0, x1, y1 = rangee.bounds
        tables += [box(x0, y0, x0 + 40.0, y1), box(x0 + 44.5, y0, x1, y1)]

    assert cotation.cote_inter_rangee(tables, 4.5, []) is None


def test_une_coupe_qui_ne_se_calcule_pas_se_dit(tmp_path):
    """Sans coupe, pas de valeur de référence pour l'inter-rangée : on le dit."""
    contrat = _contrat(tmp_path, {"tables_pv": _rangees(4.5)},
                       structures={"inclinaison_deg": 95.0})
    rapport = []

    assert cotation.table_de_la_coupe(contrat, rapport) is None
    assert any("95" in m for m in rapport)


# ---------------------------------------------------------------------------
# C6 — la largeur de chaque piste, prise en travers
# ---------------------------------------------------------------------------


def _l_de_piste(x, y, largeur):
    """Une piste en L, de 60 et 40 m de bras."""
    return boite(x, y, x + 60, y + largeur).union(boite(x, y, x + largeur, y + 40))


def test_la_largeur_d_une_piste_se_prend_en_travers_meme_quand_elle_tourne():
    rapport = []

    cotes = cotation.cotes_de_largeur_de_piste(
        [("piste_lourde", [_l_de_piste(0, 0, 5.0)])], [], rapport
    )

    (cote,) = cotes
    assert cote.texte == "5,0 m (piste)"
    assert cote.famille == "C6"
    assert cote.longueur_m == pytest.approx(5.0, abs=0.01)


def test_une_cote_par_largeur_et_par_type_de_piste():
    """Au demi-mètre près : 5,0 et 5,2 m sont une seule largeur, cotée une fois,
    sur la plus grande des deux pistes — c'est sur elle qu'elle se lit le mieux."""
    objets = [
        ("piste_lourde", [_l_de_piste(0, 0, 5.0), _l_de_piste(100, 0, 5.2),
                          _l_de_piste(200, 0, 6.0)]),
        ("piste_legere", [_l_de_piste(0, 100, 3.5), _l_de_piste(100, 100, 3.5)]),
    ]
    rapport = []

    cotes = cotation.cotes_de_largeur_de_piste(objets, [], rapport)

    assert sorted(round(c.valeur_m * 2) / 2 for c in cotes) == [3.5, 5.0, 6.0]
    assert sum("déjà cotée" in m for m in rapport) == 2


def test_ni_une_plateforme_ni_une_aire_ni_une_laniere_ne_sont_des_pistes():
    """La maquette cotait 4,2 m sous un poste (03/11/2026)."""
    poste = ouvrage("pdl_ptr", boite(4, 4, 16, 7))
    objets = [
        # Sous le poste : sa plateforme.
        ("piste_lourde", [boite(0, 0, 20, 11)]),
        # 12 x 10 m : une aire, moins de trois fois le carré de sa largeur.
        ("piste_legere", [boite(100, 0, 112, 10), boite(200, 0, 260, 1.5)]),
        # L'aire de grutage n'est pas une piste, quelle que soit sa forme.
        ("aire_grutage", [boite(300, 0, 360, 5)]),
    ]
    rapport = []

    assert cotation.cotes_de_largeur_de_piste(objets, [poste], rapport) == []
    assert any("plateforme" in m for m in rapport)
    assert any("une aire" in m for m in rapport)
    assert any("lanière" in m for m in rapport)


# ---------------------------------------------------------------------------
# C4 — clôture → habitation la plus proche
# ---------------------------------------------------------------------------

CLOTURE_C4 = [boite(0, 0, 200, 120)]


def test_un_hangar_plus_proche_qu_une_maison_ne_la_remplace_pas():
    """Sarnois : le bâtiment le plus proche au cadastre est un hangar, à 103 m ;
    l'habitation est à 166 m. Le cadastre ne dit pas l'usage, la BD TOPO si."""
    batiments = [
        (boite(250, 0, 260, 20), {"usage_1": "Agricole"}),
        (boite(280, 0, 290, 10), {"usage_1": "Indifférencié"}),
        (boite(320, 0, 330, 10), {"usage_1": "Résidentiel"}),
    ]
    rapport = []

    cote = cotation.cote_habitation(CLOTURE_C4, batiments, rapport)

    assert cote.texte == "120 m (habitation la plus proche)"
    assert cote.famille == "C4"
    assert cote.depart == pytest.approx(point(200, cote.depart[1] - Y0))
    assert cote.arrivee[0] == pytest.approx(X0 + 320.0)
    # L'indifférencié plus proche se dit, il ne remplace pas l'habitation.
    assert any("indifférencié" in m and "80 m" in m for m in rapport)


def test_sans_habitation_a_moins_de_1000_m_la_cote_ne_se_pose_pas():
    rapport = []
    batiments = [(boite(1300, 0, 1310, 10), {"usage_1": "Résidentiel"})]

    assert cotation.cote_habitation(CLOTURE_C4, batiments, rapport) is None
    assert any("aucune habitation" in m for m in rapport)


def _du_cadastre(geometrie, genre="Bâtiment en dur"):
    """Un bâtiment du cadastre, tel que `ign.telecharger_batiments` le rend."""
    from dp_socle.ign import Batiment

    return Batiment(geometrie=geometrie, type=genre)


def _parcelle(geometrie, section, numero):
    from dp_socle.ign import Parcelle

    return Parcelle(geometrie=geometrie, idu=f"00000000{section}{numero}", section=section,
                    numero=numero, contenance_m2=geometrie.area, commune="00000")


def test_un_batiment_du_cadastre_que_la_bd_topo_ignore_se_dit_au_rapport():
    """Saint-Cyr : 40 m² à 26 m de la clôture et 935 m² à 90 m, au cadastre et
    absents de la BD TOPO, quand l'habitation qu'elle donne est à 119 m (10/11/2026).

    Rien ne dit s'ils sont habités : le rapport les nomme, avec leur parcelle,
    pour qu'on aille voir. La cote reste sur l'habitation de la BD TOPO. Un
    bâtiment que la BD TOPO recouvre, ou plus loin que l'habitation, ne se dit
    pas.
    """
    serre = boite(250, 0, 260, 20)
    maison = boite(320, 0, 330, 10)
    inconnu = boite(230, 30, 238, 35)
    lointain = boite(400, 0, 410, 10)
    cadastre = [_du_cadastre(g) for g in (serre, maison, inconnu, lointain)]
    parcelles = [_parcelle(boite(220, 20, 300, 60), "AB", "0100")]
    rapport = []

    cote = cotation.cote_habitation(
        CLOTURE_C4,
        [(serre, {"usage_1": "Agricole"}), (maison, {"usage_1": "Résidentiel"})],
        rapport, cadastre=cadastre, parcelles=parcelles,
    )

    assert cote.texte == "120 m (habitation la plus proche)"
    (message,) = [m for m in rapport if "cadastre" in m]
    assert "1 bâtiment(s) du cadastre" in message, message
    assert "40 m² à 30 m (AB 0100)" in message, message
    assert "410" not in message and "200 m" not in message, message


def test_sans_habitation_un_batiment_du_cadastre_que_la_bd_topo_ignore_se_dit():
    """La légende dira « aucune habitation à moins de 1 000 m (BD TOPO) » : le
    rapport dit ce que le cadastre connaît plus près, et que la BD TOPO ignore."""
    rapport = []

    assert cotation.cote_habitation(
        CLOTURE_C4, [], rapport, cadastre=[_du_cadastre(boite(600, 0, 610, 10))]
    ) is None

    assert any("aucune habitation" in m for m in rapport)
    assert any("1 bâtiment(s) du cadastre" in m and "100 m² à 400 m" in m for m in rapport), rapport


def test_un_batiment_que_la_bd_topo_recouvre_en_partie_est_connu_d_elle():
    """Les contours du cadastre et de la BD TOPO ne coïncident pas : à Saint-Cyr,
    la maison est recouverte à 81 %, une remise à 58 %. Mesuré sur les trois
    sites le 10/11/2026 : un bâtiment du cadastre l'est à 50 % ou plus, ou pas
    du tout."""
    maison = boite(320, 0, 330, 10)
    remise = boite(290, 0, 300, 10)
    cadastre = [_du_cadastre(boite(316, 0, 330, 10)), _du_cadastre(boite(290, 0, 300, 17))]
    rapport = []

    cotation.cote_habitation(
        CLOTURE_C4,
        [(maison, {"usage_1": "Résidentiel"}), (remise, {"usage_1": "Annexe"})],
        rapport, cadastre=cadastre,
    )

    assert not any("cadastre" in m for m in rapport), rapport


# ---------------------------------------------------------------------------
# C2 et C8 — les voies publiques, cotées à leur axe ou à leur extrémité
# ---------------------------------------------------------------------------


def troncon(*points_m, **proprietes):
    proprietes.setdefault("nature", "Route à 1 chaussée")
    return (LineString([point(*p) for p in points_m]), proprietes)


def _site_du_poste():
    """Un poste de livraison près du nord-est de la clôture, et trois voies.

    Un chemin dans la clôture à 5,2 m, un chemin sur la parcelle voisine à
    7,5 m, la D18 hors de toute parcelle à 12,2 m : c'est Saint-Cyr pour les
    deux premiers, Auzainvilliers pour la troisième (07/11/2026).
    """
    enclos = boite(0, 0, 160, 120)
    poste = ouvrage("pdl_ptr", boite(140, 112, 152, 115))
    # La parcelle du site, celle du nord ; la D18 passe entre elles et la parcelle est.
    cadastre = unary_union_de([boite(0, 0, 160, 120), boite(0, 120, 160, 300),
                               boite(170, -100, 400, 300)])
    voies = [
        troncon((20, 106.8), (158, 106.8), nature="Chemin"),
        troncon((20, 122.5), (158, 122.5), nature="Chemin"),
        troncon((164.2, -100), (164.2, 300), cpx_numero="D18"),
    ]
    return enclos, poste, cadastre, voies


def unary_union_de(geometries):
    from shapely.ops import unary_union

    return unary_union(geometries)


def test_une_voie_dans_la_cloture_ou_sur_une_parcelle_n_est_pas_publique():
    """La BD TOPO ne dit pas à qui est une voie, le cadastre si : le domaine
    public n'est pas cadastré. Et la BD TOPO porte aussi les chemins du site."""
    enclos, poste, cadastre, voies = _site_du_poste()

    classees = cotation.classer_les_voies(voies, poste.geometrie, cadastre, enclos)

    assert [(round(v.distance_m, 1), v.publique) for v in classees] == [
        (5.2, False), (7.5, False), (12.2, True),
    ]
    assert classees[0].part_dans_cloture == pytest.approx(1.0)
    assert classees[1].part_hors_parcelles == pytest.approx(0.0)


def test_les_sentiers_les_escaliers_et_les_pistes_cyclables_sont_ecartes_d_office():
    enclos, poste, cadastre, _ = _site_du_poste()
    voies = [troncon((164.2, -100), (164.2, 300), nature=n)
             for n in ("Sentier", "Escalier", "Piste cyclable")]

    assert cotation.classer_les_voies(voies, poste.geometrie, cadastre, enclos) == []


def test_le_poste_de_livraison_se_cote_jusqu_a_l_axe_de_la_voie_publique():
    enclos, poste, cadastre, voies = _site_du_poste()
    rapport = []

    (resultat,) = cotation.cotes_poste_de_livraison(
        [poste], voies, cadastre, enclos, [], 1000, None, rapport
    )

    cote = resultat.cote
    assert cote.texte == "12,2 m (axe de la D18)"
    assert cote.famille == "C8" and cote.ouvrages == (0,)
    assert resultat.genre == "axe"
    # Perpendiculaire à l'axe, et ses flèches le touchent.
    assert cote.arrivee[0] == pytest.approx(X0 + 164.2)
    assert cote.depart[1] == pytest.approx(cote.arrivee[1])
    # L'axe se dessine sur 25 m de part et d'autre du pied de la cote.
    assert resultat.axe.length == pytest.approx(50.0)
    assert resultat.axe.distance(Point(cote.arrivee)) < 1e-6
    # Ce qui était plus proche et n'est pas public se dit.
    assert any("5,2 m" in m and "dans la clôture" in m and "7,5 m" in m
               and "sur des parcelles" in m for m in rapport)


def test_un_poste_sans_voie_publique_a_moins_de_30_m_ne_se_cote_pas():
    """Saint-Cyr : la première voie publique est à 108 m du PDL/PTR (07/11)."""
    enclos, poste, _, voies = _site_du_poste()
    cadastre = unary_union_de([boite(0, 0, 160, 120), boite(0, 120, 160, 300)])
    loin = [voies[0], voies[1], troncon((260, -100), (260, 300))]
    rapport = []

    assert cotation.cotes_poste_de_livraison(
        [poste], loin, cadastre, enclos, [], 1000, None, rapport
    ) == []
    assert any("108 m" in m and "pdl_ptr" in m for m in rapport)


def test_la_cote_a_l_axe_se_decale_le_long_de_la_face_plutot_que_de_se_superposer():
    """À Auzainvilliers, la cote de la D18 partait du même point, dans la même
    direction, que la cote de la citerne à la limite : elle se décale jusqu'à
    4 mm de papier de toute cote parallèle, et le rapport dit la distance perdue."""
    citerne = ouvrage("bache_incendie", boite(100, 5, 111.7, 14.3))
    route = troncon((0, -10), (300, -16), cpx_numero="D18")
    a_la_limite = cotation.CoteAPoser(
        famille="C3", depart=point(100, 5), arrivee=point(100, 0),
        texte="5,0 m (limite parcellaire)", valeur_m=5.0, vers_la_limite=True,
        ouvrages=(0,),
    )
    rapport = []

    resultat = cotation.cote_vers_la_voie_publique(
        [], [citerne], [route], boite(0, 0, 300, 200), boite(0, 3, 300, 200),
        [a_la_limite], 1000, rapport,
    )

    cote = resultat.cote
    assert cote.famille == "C2"
    # 4 mm au 1:1 000 : 4 m.
    assert cote.ligne.distance(a_la_limite.ligne) >= 4.0 - 1e-6
    assert route[0].distance(Point(cote.arrivee)) < 1e-6
    dx, dy = cote.arrivee[0] - cote.depart[0], cote.arrivee[1] - cote.depart[1]
    assert abs(dx * 300.0 + dy * -6.0) / math.hypot(dx, dy) / math.hypot(300, 6) < 1e-3
    assert any("décalée" in m for m in rapport)


def test_une_voie_publique_qui_s_arrete_avant_le_site_se_cote_a_son_extremite():
    """Saint-Cyr : la route empierrée publique finit à l'angle nord-ouest du
    site, « 23,3 m (extrémité de la route) » (08/11/2026)."""
    tables = [boite(50, 50, 150, 100)]
    route = troncon((-100, 120), (20, 120), nature="Route empierrée")
    rapport = []

    resultat = cotation.cote_vers_la_voie_publique(
        tables, [], [route], boite(0, 0, 200, 110), boite(40, 40, 160, 110),
        [], 2000, rapport,
    )

    assert resultat.genre == "extrémité"
    assert resultat.cote.texte == "36,1 m (extrémité de la route)"
    assert resultat.cote.arrivee == pytest.approx(point(20, 120))


def test_les_troncons_d_une_route_se_fondent_avant_la_mesure():
    """La BD TOPO coupe une route à chaque carrefour : le bout d'un tronçon
    n'est pas le bout de la route, et l'axe se dessine par-delà la coupure."""
    citerne = ouvrage("bache_incendie", boite(110, 5, 121.7, 14.3))
    route = [troncon((0, -10), (100, -10)), troncon((100, -10), (300, -10))]

    resultat = cotation.cote_vers_la_voie_publique(
        [], [citerne], route, boite(0, 0, 300, 200), boite(0, 3, 300, 200),
        [], 1000, [],
    )

    assert resultat.genre == "axe"
    assert resultat.cote.valeur_m == pytest.approx(15.0)
    assert resultat.axe.length == pytest.approx(50.0)


def test_sans_voie_publique_la_cote_vers_la_voie_ne_se_pose_pas():
    rapport = []
    chemin = troncon((0, -10), (300, -10), nature="Chemin")

    # Le chemin est sur la parcelle voisine.
    assert cotation.cote_vers_la_voie_publique(
        [boite(50, 50, 150, 100)], [], [chemin],
        unary_union_de([boite(0, 0, 300, 200), boite(0, -50, 300, 0)]),
        boite(40, 40, 160, 110), [], 2000, rapport,
    ) is None
    assert any("aucune voie publique" in m for m in rapport)


def test_le_poste_le_plus_proche_de_la_voie_reprend_la_cote_de_c2_pour_sa_zone():
    """Quand C2 part du poste vers la voie de C8, C8 est la même cote, et suit la zone du poste.

    Sarnois : le poste de livraison est la construction la plus proche du
    chemin, à 3,0 m, soit 1,5 mm sur la DP 2 au 1:2 000 ; sa zone partait sur
    la DP 2 bis sans cette cote, que seule C2 portait. La planche de détail la
    reprend (chef de projet, 10/11/2026). Sur une même planche, elle ne se pose
    qu'une fois : c'est la DP 2 qui choisit laquelle.
    """
    enclos, poste, cadastre, voies = _site_du_poste()
    rapport = []
    c2 = cotation.cote_vers_la_voie_publique(
        [], [poste], voies, cadastre, enclos, [], 1000, rapport
    )

    (c8,) = cotation.cotes_poste_de_livraison(
        [poste], voies, cadastre, enclos, [c2.cote], 1000, c2, rapport
    )

    assert c8.confondue_avec is c2.cote
    assert c8.cote.ligne.equals(c2.cote.ligne) and c8.cote.texte == c2.cote.texte
    assert c8.cote.famille == "C8" and c8.cote.ouvrages == (0,)
    assert c8.axe.equals(c2.axe) and c8.genre == c2.genre
    assert c2.confondue_avec is None
    assert any("confondue" in m and "zone" in m for m in rapport), rapport


# ---------------------------------------------------------------------------
# D12 — les trois dimensions, en légende
# ---------------------------------------------------------------------------


#: Un contrat ne s'écrit pas vide.
SEULE_CLOTURE = {"cloture": [boite(0, 0, 200, 120)]}


def _dimensions(tmp_path, calques, table=None):
    from dp_socle.planches.palette import objets_a_dessiner

    contrat = _contrat(tmp_path, calques)
    rapport = []
    ouvrages = cotation.ouvrages_permanents(contrat, objets_a_dessiner(contrat, []), [])
    return cotation.dimensions_en_legende(contrat, ouvrages, table, rapport), rapport


def test_chaque_construction_porte_les_cotes_et_la_hauteur_du_catalogue(tmp_path):
    """« Coté dans les trois dimensions » (Auzainvilliers, art. R. 431-36 b) :
    la hauteur n'est pas cotée sur le plan, elle est dans la légende, avec
    l'emprise. Ce sont les cotes du catalogue, celles des élévations de la
    DP 4 : le bac dessiné à 16,9 m reste un bac de 17,5 m."""
    dimensions, _ = _dimensions(tmp_path, {
        "pdl_ptr": [boite(100, 100, 112, 103)],
        "bac_retention": [boite(150, 100, 166.9, 103)],
    })

    assert dimensions["pdl_ptr"] == "(12 × 3 m, h 3 m)"
    assert dimensions["bac_retention"] == "(17,5 × 3 m, h 2,3 m)"


def test_la_variante_d_une_famille_se_choisit_sur_la_surface_du_corps(tmp_path):
    petite, _ = _dimensions(tmp_path / "30", {"bache_incendie": [boite(100, 100, 107.95, 104.44)]})
    grande, _ = _dimensions(tmp_path / "120", {"bache_incendie": [boite(100, 100, 111.7, 109.3)]})

    assert petite["bache_incendie"] == "(7,95 × 4,44 m, h 1,3 m)"
    assert grande["bache_incendie"] == "(11,7 × 9,3 m, h 1 m)"


def test_deux_variantes_d_une_meme_famille_se_disent_au_rapport(tmp_path):
    """La légende n'a qu'une entrée par famille : elle ne choisit pas entre deux."""
    dimensions, rapport = _dimensions(tmp_path, {
        "bache_incendie": [boite(100, 100, 107.95, 104.44), boite(150, 100, 161.7, 109.3)],
    })

    assert "bache_incendie" not in dimensions
    assert any("bache_incendie" in m and "variantes" in m for m in rapport)


def test_les_tables_portent_leur_hauteur_maximale_et_a_defaut_celle_dessinee(tmp_path):
    from dp_socle.planches.dp3_coupes import GeometrieTable

    table = GeometrieTable(
        point_bas_m=1.5, point_haut_m=3.53, inclinaison_deg=25.0, inter_table_m=6.0,
        pas_m=10.0, rampant_m=4.8, projection_m=4.35, nb_modules_rampant=2,
        point_haut_max_m=4.0,
    )
    sans_maximum = GeometrieTable(**{**table.__dict__, "point_haut_max_m": None})

    avec, _ = _dimensions(tmp_path / "a", SEULE_CLOTURE, table)
    sans, _ = _dimensions(tmp_path / "b", SEULE_CLOTURE, sans_maximum)

    assert avec["tables_pv"] == "(hauteur maximale 4 m)"
    assert sans["tables_pv"] == "(hauteur maximale 3,53 m)"


def test_la_cloture_et_le_portail_portent_les_hauteurs_de_leurs_elevations(tmp_path, monkeypatch):
    """Le contrat n'en porte aucune : ce sont les constantes UNITe que les
    élévations de la DP 4 cotent (09/11/2026), lues là et non recopiées."""
    from dp_socle.planches import standards

    monkeypatch.setattr(standards, "HAUTEUR_CLOTURE_M", 1.8)
    monkeypatch.setattr(standards, "HAUTEUR_PORTAIL_M", 2.2)

    dimensions, _ = _dimensions(tmp_path, SEULE_CLOTURE)

    assert dimensions["cloture"] == "(h 1,8 m)"
    assert dimensions["portail"] == "(h 2,2 m)"


# ---------------------------------------------------------------------------
# Ce que la relecture du module a montré (09/11/2026)
# ---------------------------------------------------------------------------


def test_deux_habitations_a_egale_distance_ne_font_pas_tomber_la_cote():
    """Deux maisons mitoyennes dont l'angle commun est au plus près de la
    clôture : le tri comparait alors les bâtiments eux-mêmes, et levait — à la
    génération, une fois tous les fonds téléchargés."""
    batiments = [
        (boite(320, 0, 330, 10), {"usage_1": "Résidentiel"}),
        (boite(320, -10, 330, 0), {"usage_1": "Résidentiel"}),
    ]

    cote = cotation.cote_habitation(CLOTURE_C4, batiments, [])

    assert cote.texte == "120 m (habitation la plus proche)"


def test_les_valeurs_que_la_coupe_substitue_se_disent_sur_le_plan_de_masse(tmp_path):
    """Sans profil de terrain, la DP 3 n'est pas produite, ni ses avertissements :
    une hauteur de tables prise aux standards arrivait en légende sans un mot."""
    contrat = _contrat(tmp_path, {"tables_pv": _rangees(4.5)},
                       structures={"point_haut_m": None})
    rapport = []

    table = cotation.table_de_la_coupe(contrat, rapport)

    assert table is not None
    assert any("point_haut_m" in m and "standard" in m for m in rapport)


def test_un_ouvrage_pose_sur_la_limite_n_a_pas_de_cote_a_la_limite():
    """Le lot 2ter pose les postes de livraison sur la limite : une cote de
    longueur nulle ne porte pas de flèches. Le dessin le montre, et le rapport
    le dit — batteries comprises."""
    ouvrages = [
        ouvrage("pdl_ptr", boite(100, -1, 112, 2)),
        ouvrage("bess", boite(150, 0.02, 156.06, 3.02)),
    ]
    rapport = []

    cotes = cotation.cotes_entre_ouvrages(ouvrages, LIMITE, rapport)

    assert _a_la_limite(cotes, ouvrages) == {}
    assert sum("sur la limite" in m for m in rapport) == 2


def test_la_cote_vers_la_voie_ne_quitte_pas_la_construction_la_plus_proche():
    """Décalée « le long de la face », elle pouvait sauter sur une autre
    construction : au 1:2 000, un BESS à 15 m de la D18 cédait la cote à une
    table à 54,5 m. Faute de place sur sa face, elle reste, et le dit."""
    bess = ouvrage("bess", boite(100, 0.5, 106.06, 3.5))
    tables = [boite(50, 40, 150, 44)]
    route = troncon((0, -14.5), (300, -14.5), cpx_numero="D18")
    a_la_limite = cotation.CoteAPoser(
        famille="C3", depart=point(103, 0.5), arrivee=point(103, 0),
        texte="0,5 m (limite parcellaire)", valeur_m=0.5, vers_la_limite=True,
        ouvrages=(0,),
    )
    rapport = []

    resultat = cotation.cote_vers_la_voie_publique(
        tables, [bess], [route], boite(0, 0, 300, 200), boite(0, 0.2, 300, 200),
        [a_la_limite], 2000, rapport,
    )

    assert resultat.cote.valeur_m == pytest.approx(15.0)
    assert bess.geometrie.distance(Point(resultat.cote.depart)) < 1e-6
    assert any("superposée" in m for m in rapport)
    assert not any("décalée" in m for m in rapport)


def test_une_cloture_dont_les_bouts_se_manquent_de_9_mm_se_referme_et_le_dit():
    """Bédarieux : 747,6 m de clôture dont les bouts se manquent de 9 mm, fermée
    pour qui la regarde, ouverte pour `is_closed` (02/10/2026). L'import la
    tient pour fermée à 10 cm près ; ses côtés aussi."""
    presque = LineString([point(0, 0), point(200, 0), point(200, 120), point(0, 120),
                          point(0, 0.009)])
    rapport = []

    pans = _pans(presque, rapport)

    assert _longueurs(pans) == [120.0, 120.0, 200.0, 200.0]
    assert any("9 mm" in m for m in rapport)


def test_une_cloture_en_morceaux_jointifs_se_recoud():
    """Le lot 2ter rend la clôture en lignes quand elle ne se ferme pas d'un tenant."""
    morceaux = [
        LineString([point(0, 0), point(200, 0)]), LineString([point(200, 0), point(200, 120)]),
        LineString([point(200, 120), point(0, 120)]), LineString([point(0, 120), point(0, 0)]),
    ]

    pans = cotation.pans_de_la_cloture(cotation.enclos_de_la_cloture(morceaux, []))

    assert _longueurs(pans) == [120.0, 120.0, 200.0, 200.0]


def test_les_cotes_d_un_enclos_partent_de_ses_propres_tables():
    """Deux enclos à 8 m l'un de l'autre : les tables du premier étaient « les
    plus proches » d'un côté du second, sans table."""
    terrain = boite(0, 0, 400, 200)
    rapport = []
    enclos = cotation.enclos_de_la_cloture(
        [boite(10, 10, 190, 190), boite(198, 10, 390, 190)], rapport
    )
    tables = [boite(30, 30, 185, 34)]

    resultats = cotation.cotes_tables_cloture_limite(
        cotation.pans_de_la_cloture(enclos), tables, terrain, 2000, rapport
    )

    assert resultats
    assert all(r.pan.trace.centroid.x < X0 + 195.0 for r in resultats)
    assert any("sans table" in m for m in rapport)


def test_une_route_en_boucle_n_a_pas_d_extremite():
    """Le départ d'une boucle n'est pas le bout de la route, et son axe se
    dessine des deux côtés de ce départ."""
    citerne = ouvrage("bache_incendie", boite(0, 0, 11.7, 9.3))
    boucle = troncon((-20, -20), (-120, -20), (-120, -120), (-20, -120), (-20, -20))

    resultat = cotation.cote_vers_la_voie_publique(
        [], [citerne], [boucle], boite(-5, -5, 300, 200), boite(-5, -5, 300, 200),
        [], 1000, [],
    )

    assert resultat.genre == "axe"
    assert resultat.cote.texte == "28,3 m (axe de la route)"
    assert resultat.axe.length == pytest.approx(50.0)


def test_l_axe_d_une_voie_numerotee_se_dessine_par_dela_un_carrefour():
    """La D18 coupée par un chemin : l'axe s'arrêtait au carrefour. Il se
    dessine sur la D18, de part et d'autre du pied, et pas sur le chemin."""
    citerne = ouvrage("bache_incendie", boite(102, 5, 113.7, 14.3))
    voies = [
        troncon((0, -10), (100, -10), cpx_numero="D18"),
        troncon((100, -10), (300, -10), cpx_numero="D18"),
        troncon((100, -10), (100, -200), nature="Chemin"),
    ]

    resultat = cotation.cote_vers_la_voie_publique(
        [], [citerne], voies, boite(0, 0, 300, 200), boite(0, 3, 300, 200), [], 1000, [],
    )

    assert resultat.cote.texte == "15,0 m (axe de la D18)"
    assert resultat.axe.length == pytest.approx(50.0)
    assert resultat.axe.distance(Point(point(100, -30))) > 1.0


def test_l_inter_rangee_se_mesure_dans_deux_champs_d_orientations_differentes():
    """Un champ à 0°, un autre à 30° : rapportés à un seul axe, aucun écart ne
    passait le filtre de 10°, et le rapport accusait le plan et la coupe."""
    from shapely import affinity

    oblique = [
        affinity.rotate(affinity.translate(r, 0.0, 200.0), 30.0, origin=point(50, 223))
        for r in _rangees(4.5)
    ]

    cote = cotation.cote_inter_rangee(_rangees(4.5) + oblique, 4.5, [])

    assert cote is not None
    assert cote.longueur_m == pytest.approx(4.5, abs=0.01)


def test_un_ecart_en_travers_d_une_seule_de_ses_deux_tables_n_est_pas_un_inter_rangee():
    """À la jonction de deux champs, une table à 0° et une à 30° : leur écart de
    4,5 m est en travers de la première seulement, et ne mesure aucune rangée."""
    from shapely import affinity

    a_zero = boite(0, 0, 100, 4)
    a_trente = affinity.translate(
        affinity.rotate(box(0, 0, 60, 4), 30.0, origin=(0, 0)), X0 + 50.0, Y0 + 8.5
    )

    assert cotation.cote_inter_rangee([a_zero, a_trente], 4.5, []) is None


def test_une_meme_largeur_se_cote_pour_chaque_type_de_piste():
    """Auzainvilliers : 3,5 m de piste existante, 3,5 m de piste à créer."""
    objets = [
        ("piste_lourde_existante", [_l_de_piste(0, 0, 3.5)]),
        ("piste_lourde_a_creer", [_l_de_piste(100, 0, 3.5)]),
    ]

    assert len(cotation.cotes_de_largeur_de_piste(objets, [], [])) == 2


def test_deux_largeurs_a_moins_d_un_demi_metre_l_une_de_l_autre_n_en_font_qu_une():
    """5,2 et 5,3 m tombaient dans deux cases d'arrondi, 5,0 et 5,5 m."""
    objets = [("piste_lourde", [_l_de_piste(0, 0, 5.3), _l_de_piste(100, 0, 5.2)])]

    assert len(cotation.cotes_de_largeur_de_piste(objets, [], [])) == 1


def test_une_piste_que_les_ouvrages_couvrent_est_leur_sol():
    """Sous deux grands ouvrages, sans porter la moitié d'aucun."""
    grands = [ouvrage("bac_retention", boite(-5, -10, 20, 20)),
              ouvrage("zone_remise", boite(20, -10, 45, 20))]
    rapport = []

    assert cotation.cotes_de_largeur_de_piste(
        [("piste_lourde", [boite(0, 0, 40, 4)])], grands, rapport
    ) == []
    assert any("les ouvrages la couvrent" in m for m in rapport)


def test_une_piste_dessinee_en_axe_se_dit_sans_largeur():
    """Une piste du plan PDF n'a que son axe (lot 2ter) : dessinée en trait,
    elle n'a pas de largeur à mesurer, et cela se dit."""
    rapport = []

    assert cotation.cotes_de_largeur_de_piste(
        [("piste_legere", [LineString([point(0, 0), point(100, 0)])])], [], rapport
    ) == []
    assert any("piste_legere" in m and "axe" in m for m in rapport)


def test_le_numero_d_une_voie_s_elide_devant_une_voyelle():
    enclos, poste, cadastre, _ = _site_du_poste()
    voies = [troncon((164.2, -100), (164.2, 300), cpx_numero="A6", nature="Type autoroutier")]

    (resultat,) = cotation.cotes_poste_de_livraison(
        [poste], voies, cadastre, enclos, [], 1000, None, []
    )

    assert resultat.cote.texte == "12,2 m (axe de l'A6)"


def test_sans_parcellaire_autour_on_ne_sait_pas_quelles_voies_sont_publiques():
    """Le domaine public se lit au cadastre : sans lui, toute voie passerait
    pour publique. Pas de cote, et le rapport le dit."""
    enclos, poste, _, voies = _site_du_poste()
    rapport = []

    assert cotation.cote_vers_la_voie_publique(
        [], [poste], voies, None, enclos, [], 1000, rapport
    ) is None
    assert cotation.cotes_poste_de_livraison(
        [poste], voies, None, enclos, [], 1000, None, rapport
    ) == []
    assert sum("parcellaire" in m for m in rapport) == 2


def test_sans_enclos_la_part_dans_la_cloture_ne_se_verifie_pas_et_cela_se_dit():
    _, poste, cadastre, voies = _site_du_poste()
    rapport = []

    resultat = cotation.cote_vers_la_voie_publique(
        [], [poste], voies, cadastre, None, [], 1000, rapport
    )

    assert resultat is not None
    assert any("clôture" in m and "pas vérifiée" in m for m in rapport)


def test_sans_tables_les_cotes_qui_s_y_rapportent_se_disent():
    rapport = []

    assert cotation.cotes_vers_les_tables(
        [ouvrage("bess", boite(10, 60, 16.06, 63))], [], rapport
    ) == []
    assert cotation.cote_inter_rangee([boite(0, 0, 100, 4)], 4.5, rapport) is None
    assert len(rapport) == 2


def test_un_ouvrage_sans_cote_au_catalogue_le_dit_sans_accuser_le_dessin(tmp_path):
    """Le dessin n'y est pour rien quand c'est le catalogue du contrat qui manque."""
    sans_citerne = [c for c in CATALOGUE if not c["ouvrage"].startswith("Citerne incendie")]
    contrat = _contrat(tmp_path, {"bache_incendie": [boite(100, 100, 111.7, 109.3)]},
                       catalogue=sans_citerne)

    ouvrages, rapport = _ouvrages_du_contrat(contrat)

    assert len(ouvrages) == 1
    assert any("bache_incendie" in m and "catalogue du contrat" in m for m in rapport)


def test_choisir_parmi_aucune_place_ne_choisit_rien():
    assert cotation.choisir_la_place_cloture_limite([], []) is None


# ---------------------------------------------------------------------------
# D7 — les zones techniques, et ce qui les envoie sur une planche de détail
# ---------------------------------------------------------------------------


def _cote(famille, a, b, ouvrages=(), texte=None):
    longueur = math.dist(point(*a), point(*b))
    return cotation.CoteAPoser(
        famille=famille, depart=point(*a), arrivee=point(*b),
        texte=texte or f"{longueur:.1f} m", valeur_m=longueur, ouvrages=ouvrages,
    )


def test_une_zone_reunit_les_ouvrages_que_des_cotes_c3_relient():
    """Les cotes C3 entre ouvrages font les zones ; C3 à la limite, C7 et C8 les suivent (D7).

    Trois ouvrages reliés deux à deux font une zone ; un poste qui n'a que sa
    cote vers la voie en fait une à lui seul ; un ouvrage sans cote n'en fait
    pas. Les cotes qui ne partent d'aucun ouvrage — C1, C2, C4, C5, C6 —
    n'appartiennent à aucune zone : elles restent sur la DP 2.
    """
    ab = _cote("C3", (0, 0), (10, 0), (0, 1))
    bc = _cote("C3", (10, 0), (20, 0), (1, 2))
    a_limite = _cote("C3", (0, 0), (0, -8), (0,))
    c_tables = _cote("C7", (20, 0), (20, 15), (2,))
    poste_voie = _cote("C8", (60, 0), (60, -12), (4,))
    c1 = _cote("C1", (30, 20), (30, -10))
    c2 = _cote("C2", (20, 0), (20, -30))

    zones = cotation.zones_techniques([ab, c1, bc, a_limite, c_tables, poste_voie, c2])

    assert [zone.ouvrages for zone in zones] == [(0, 1, 2), (4,)]
    assert zones[0].cotes == (ab, bc, a_limite, c_tables)
    assert zones[1].cotes == (poste_voie,)


class _Gene:
    """Ce que la pose rend d'une cote qui se lit mal, réduit à ce qu'on en lit."""

    def __init__(self, cote, raison):
        self.cote, self.texte, self.raison = cote, cote.texte, raison


def test_une_zone_part_en_detail_par_sa_cote_de_deux_millimetres():
    """2 m entre deux conteneurs : 2 mm au 1:1 000, sous les 3 mm lisibles (D7, 04/11).

    Au 1:500, la même cote fait 4 mm : la zone reste sur la DP 2.
    """
    courte = _cote("C3", (0, 0), (2, 0), (0, 1), texte="2,0 m")
    zone = cotation.zones_techniques([courte])[0]

    raisons = cotation.raisons_du_detail(zone, 1000, [])
    assert len(raisons) == 1 and "« 2,0 m »" in raisons[0] and "2,0 mm" in raisons[0]
    assert cotation.raisons_du_detail(zone, 500, []) == []


def test_une_zone_part_en_detail_par_sa_valeur_posee_sur_un_ouvrage():
    """Une valeur posée sur un ouvrage le cache : sa zone part (D7) ; une autre zone reste."""
    genee = _cote("C3", (0, 0), (12, 0), (0, 1), texte="12,0 m")
    voisine = _cote("C3", (100, 0), (112, 0), (2, 3), texte="12,0 m")
    zones = cotation.zones_techniques([genee, voisine])
    genes = [_Gene(genee, "valeur posée sur « Conteneurs BESS »")]

    raisons = cotation.raisons_du_detail(zones[0], 1000, genes)
    assert raisons == ["« 12,0 m » : valeur posée sur « Conteneurs BESS »"]
    assert cotation.raisons_du_detail(zones[1], 1000, genes) == []
