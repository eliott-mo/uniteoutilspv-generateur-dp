"""Tests des contrôles croisés, de la ligne de coupe et du profil (lot 2bis).

Les tests qui interrogent le RGE ALTI sont marqués `reseau` : ils mesurent la
réponse réelle du service, seule chose qui dise si le point d'entrée et le
format n'ont pas changé.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import LineString, Point, Polygon, box

from dp_socle.coupe import (
    ECART_SUSPECT_DEG,
    ProfilTerrain,
    controler_coherence,
    corriger_ligne_coupe,
    coupe_enregistree,
    echantillonner,
    position_de_coupe,
    profil_terrain,
    reprendre_coupe,
    translater_ligne_coupe,
)
from dp_socle.erreurs import ErreurControleCroise, ErreurCoupe
from dp_socle.import_be import (
    AVERTISSEMENT,
    BLOQUANT,
    OK,
    controler,
    importer_be,
    lire_plan_be,
)
from dp_socle.tableau_bilan import lire_tableau

REFERENCE = Path("exemples/saint-cyr-DXF")
DXF = REFERENCE / "20260903_SCV_IND06.dxf"
TABLEAU = REFERENCE / "20260825_SCV_Tableau_Bilan_V6.xlsx"


@pytest.fixture(scope="module")
def plan():
    return lire_plan_be(DXF)


@pytest.fixture(scope="module")
def tableau():
    return lire_tableau(TABLEAU, "IND06")


def _statuts(controles):
    return {c.libelle: c.statut for c in controles}


# ---------------------------------------------------------------------------
# Étape C — contrôles croisés
# ---------------------------------------------------------------------------


def test_le_jeu_de_reference_passe_tous_les_controles(plan, tableau):
    controles = controler(plan, tableau, seuil_puissance_mwc=3.0)
    statuts = _statuts(controles)
    assert statuts["Nombre de tables"] == OK
    assert statuts["Nombre de portails"] == OK
    assert statuts["Surface clôturée"] == OK
    assert statuts["Linéaire de clôture"] == OK
    assert statuts["Surface projetée des modules"] == OK
    assert statuts["Inclinaison des rangées"] == OK
    assert statuts["Puissance du projet"] == OK
    # Sans emprise cadastrale, le contrôle d'inclusion ne peut pas être fait :
    # il est signalé, jamais tenu pour réussi.
    assert statuts["Clôture dans l'emprise cadastrale"] == AVERTISSEMENT


def test_nombre_de_tables_modifie_bloque(plan, tableau):
    """Le plan mis à jour sans le tableau est le scénario que ce lot attrape."""
    tableau_modifie = lire_tableau(TABLEAU, "IND06")
    tableau_modifie.structures["nb_tables"] = 95
    controles = controler(plan, tableau_modifie)
    controle = next(c for c in controles if c.libelle == "Nombre de tables")
    assert controle.statut == BLOQUANT
    assert "96 au plan contre 95 au tableau" in controle.message


def test_surface_cloturee_hors_tolerance_bloque(plan, tableau):
    tableau_modifie = lire_tableau(TABLEAU, "IND06")
    tableau_modifie.generalites["surface_cloturee_ha"] = 4.80  # +6 %
    controles = controler(plan, tableau_modifie)
    assert _statuts(controles)["Surface clôturée"] == BLOQUANT


def test_lineaire_hors_tolerance_avertit_sans_bloquer(plan, tableau):
    tableau_modifie = lire_tableau(TABLEAU, "IND06")
    tableau_modifie.generalites["lineaire_cloture_m"] = 950.0  # +9 %
    controles = controler(plan, tableau_modifie)
    assert _statuts(controles)["Linéaire de clôture"] == AVERTISSEMENT
    assert not [c for c in controles if c.bloquant]


def test_debordement_hors_emprise_cadastrale_avertit(plan, tableau):
    """Une emprise cadastrale trop petite doit se voir."""
    minx, miny, maxx, maxy = plan.polygone_cloture.bounds
    cadastre = box(minx, miny, maxx, maxy - 40.0)
    controle = next(
        c
        for c in controler(plan, tableau, emprise_cadastrale=cadastre)
        if c.libelle == "Clôture dans l'emprise cadastrale"
    )
    assert controle.statut == AVERTISSEMENT
    assert "déborde" in controle.message


def test_cloture_contenue_dans_le_cadastre(plan, tableau):
    cadastre = plan.polygone_cloture.buffer(20.0)
    controle = next(
        c
        for c in controler(plan, tableau, emprise_cadastrale=cadastre)
        if c.libelle == "Clôture dans l'emprise cadastrale"
    )
    assert controle.statut == OK


def test_puissance_au_dessus_du_seuil_saisi(plan, tableau):
    """Le seuil vient de l'utilisateur : aucune règle d'urbanisme n'est codée."""
    controle = next(
        c
        for c in controler(plan, tableau, seuil_puissance_mwc=1.0)
        if c.libelle == "Puissance du projet"
    )
    assert controle.statut == AVERTISSEMENT
    assert "AU-DESSUS" in controle.message


def test_sortie_refusee_tant_qu_un_controle_bloque(tmp_path):
    import_be = importer_be(DXF, TABLEAU, "IND05")  # indice qui ne va pas au DXF
    assert import_be.bloquants
    with pytest.raises(ErreurControleCroise) as erreur:
        import_be.ecrire(tmp_path)
    assert "Nombre de tables" in str(erreur.value)
    assert not list(tmp_path.iterdir())


# ---------------------------------------------------------------------------
# Étape D — ligne de coupe
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def emprise(plan):
    return plan.polygone_cloture


def test_trace_de_travers_ressort_strictement_nord_sud(plan, emprise):
    """Tables est-ouest, donc coupe nord-sud, quel que soit le tracé."""
    centre = emprise.centroid
    trace = LineString(
        [(centre.x - 40, centre.y - 28), (centre.x + 40, centre.y + 28)]
    )
    coupe = corriger_ligne_coupe(trace, plan.azimut_tables_deg, emprise)

    depart, arrivee = coupe.geometrie.coords[0], coupe.geometrie.coords[-1]
    assert depart[0] == pytest.approx(arrivee[0], abs=1e-6)  # même X : nord-sud
    assert coupe.azimut_coupe_deg == pytest.approx(90.0, abs=1e-6)


def test_point_milieu_du_trace_conserve(plan, emprise):
    """C'est le milieu qui exprime l'intention, pas la direction."""
    centre = emprise.centroid
    trace = LineString(
        [(centre.x - 40, centre.y - 28), (centre.x + 40, centre.y + 28)]
    )
    coupe = corriger_ligne_coupe(trace, plan.azimut_tables_deg, emprise)
    milieu = trace.interpolate(0.5, normalized=True)
    assert coupe.geometrie.distance(milieu) == pytest.approx(0.0, abs=1e-6)


def test_coupe_traverse_toute_l_emprise_avec_dix_metres_de_marge(plan, emprise):
    centre = emprise.centroid
    trace = LineString([(centre.x - 5, centre.y - 5), (centre.x + 5, centre.y + 5)])
    coupe = corriger_ligne_coupe(trace, plan.azimut_tables_deg, emprise)

    _, ymin, _, ymax = emprise.bounds
    ys = sorted(c[1] for c in coupe.geometrie.coords)
    assert ymin - ys[0] == pytest.approx(10.0, abs=0.01)
    assert ys[-1] - ymax == pytest.approx(10.0, abs=0.01)
    assert coupe.geometrie.intersects(emprise)


def test_trace_a_plus_de_45_degres_avertit_mais_corrige(plan, emprise):
    centre = emprise.centroid
    # Tracé est-ouest : parallèle aux rangées, l'utilisateur s'est trompé de sens.
    trace = LineString([(centre.x - 50, centre.y), (centre.x + 50, centre.y)])
    coupe = corriger_ligne_coupe(trace, plan.azimut_tables_deg, emprise)
    assert coupe.ecart_initial_deg > ECART_SUSPECT_DEG
    assert coupe.corrigee
    assert coupe.azimut_coupe_deg == pytest.approx(90.0, abs=1e-6)
    assert any("redressée" in m for m in coupe.avertissements)


def test_mode_manuel_conserve_la_direction_tracee_en_le_disant(plan, emprise):
    centre = emprise.centroid
    trace = LineString(
        [(centre.x - 40, centre.y - 28), (centre.x + 40, centre.y + 28)]
    )
    coupe = corriger_ligne_coupe(
        trace, plan.azimut_tables_deg, emprise, manuel=True
    )
    assert not coupe.corrigee
    assert coupe.azimut_coupe_deg == pytest.approx(35.0, abs=0.1)
    assert any("Mode manuel" in m for m in coupe.avertissements)


def test_emprise_allongee_en_biais_ne_donne_pas_une_coupe_deux_fois_trop_longue():
    """La longueur se calcule par projection, pas sur la diagonale de la bbox."""
    from shapely.affinity import rotate

    emprise_biaise = rotate(box(0, 0, 400, 60), 45, origin="centroid")
    trace = LineString([(-10, -10), (10, 10)])
    coupe = corriger_ligne_coupe(trace, 45.0, emprise_biaise)
    # Largeur réelle de la bande, perpendiculairement à son grand axe : 60 m.
    assert coupe.longueur_m == pytest.approx(60.0 + 20.0, abs=1.0)


def test_trace_reduit_a_un_point_refuse(emprise):
    with pytest.raises(ErreurCoupe):
        corriger_ligne_coupe(LineString([(0, 0), (0, 0)]), 0.0, emprise)


# ---------------------------------------------------------------------------
# Étape D bis — déplacer la coupe au lieu de la retracer
# ---------------------------------------------------------------------------
#
# La coupe proposée à l'import annonçait que le chef de projet « la déplace
# seulement si elle lui déplaît », et il n'existait aucun moyen de la déplacer :
# retracer un segment appelait `corriger_ligne_coupe(..., tables=…)`, qui
# recalcule la position et repose la coupe exactement où elle était. Ces tests
# mesurent la combinaison qui manquait — direction imposée, position choisie.


def _perpendiculaire(plan) -> float:
    return plan.azimut_tables_deg + 90.0


def _ecart_a_la_perpendiculaire(coupe, plan) -> float:
    """Écart absolu, en degrés, entre la coupe et la perpendiculaire aux rangées."""
    from dp_socle.coupe import _dans_demi_tour

    return abs(_dans_demi_tour(coupe.azimut_coupe_deg - _perpendiculaire(plan)))


def test_la_coupe_deplacee_passe_par_le_point_designe(plan, emprise):
    """Le point cliqué est sur la ligne, à la tolérance de reprojection près."""
    auto, _, _ = position_de_coupe(plan.azimut_tables_deg, emprise, plan.tables)
    # Franchement à l'ouest de la position automatique : 80 m, quand la reprise
    # d'une coupe se juge identique en deçà de 10 cm.
    point = Point(auto.x - 80.0, auto.y + 25.0)

    coupe = translater_ligne_coupe(point, plan.azimut_tables_deg, emprise)

    assert coupe.geometrie.distance(point) == pytest.approx(0.0, abs=1e-6)
    assert coupe.position_choisie


def test_la_coupe_deplacee_ne_fait_aucun_angle_avec_la_perpendiculaire(plan, emprise):
    """Écart nul : c'est ce qui distingue ce geste du mode manuel.

    Le seul contournement qui imposait une position — « Conserver la direction
    tracée » — conservait aussi la direction, donc l'oblique du tracé à main
    levée, qui allonge toutes les distances lues sur la planche de 1/cos θ.
    """
    centre = emprise.centroid
    point = Point(centre.x - 60.0, centre.y - 40.0)

    deplacee = translater_ligne_coupe(point, plan.azimut_tables_deg, emprise)
    assert _ecart_a_la_perpendiculaire(deplacee, plan) == pytest.approx(0.0, abs=1e-9)
    assert deplacee.ecart_initial_deg == 0.0
    assert deplacee.corrigee

    # Le même point atteint par le seul moyen qui existait avant : de travers.
    trace = LineString([(point.x - 40, point.y - 28), (point.x + 40, point.y + 28)])
    manuelle = corriger_ligne_coupe(
        trace, plan.azimut_tables_deg, emprise, manuel=True
    )
    assert _ecart_a_la_perpendiculaire(manuelle, plan) > 30.0


def test_deplacer_la_coupe_la_deplace_vraiment(plan, emprise):
    """Le geste vide d'avant, et celui qui le remplace, mesurés côte à côte."""
    auto, _, _ = position_de_coupe(plan.azimut_tables_deg, emprise, plan.tables)
    point = Point(auto.x - 80.0, auto.y)
    trace = LineString([(point.x, point.y - 30), (point.x, point.y + 30)])

    # Retracer : le tracé n'est qu'un déclencheur, la coupe repose où elle était.
    retracee = corriger_ligne_coupe(
        trace, plan.azimut_tables_deg, emprise, tables=plan.tables
    )
    assert retracee.geometrie.distance(point) == pytest.approx(80.0, abs=1.0)

    # Cliquer : elle y va.
    deplacee = translater_ligne_coupe(point, plan.azimut_tables_deg, emprise)
    assert deplacee.geometrie.distance(point) == pytest.approx(0.0, abs=1e-6)


def test_la_coupe_deplacee_traverse_toute_l_emprise_avec_la_marge(plan, emprise):
    centre = emprise.centroid
    coupe = translater_ligne_coupe(
        Point(centre.x + 45.0, centre.y), plan.azimut_tables_deg, emprise
    )

    _, ymin, _, ymax = emprise.bounds
    ys = sorted(c[1] for c in coupe.geometrie.coords)
    assert ymin - ys[0] == pytest.approx(10.0, abs=0.01)
    assert ys[-1] - ymax == pytest.approx(10.0, abs=0.01)
    assert coupe.geometrie.intersects(emprise)


def test_clic_trop_loin_du_site_refuse_en_disant_de_combien(plan, emprise):
    """Aucun repli silencieux : un clic hors de portée lève, avec la distance."""
    loin = Point(emprise.centroid.x + 4_000.0, emprise.centroid.y)
    with pytest.raises(ErreurCoupe) as leve:
        translater_ligne_coupe(loin, plan.azimut_tables_deg, emprise)

    message = str(leve.value)
    assert "ne traverse pas l'emprise clôturée" in message
    # La distance annoncée est celle du point au bord de l'emprise, et non au
    # centre : c'est la portée qui manque. Son séparateur de milliers doit être
    # l'espace — celui du format `,.0f` de Python est une virgule, qui se lirait
    # ici comme une décimale.
    entiers = round(loin.distance(emprise))
    assert f"{entiers // 1000} {entiers % 1000:03d} m" in message
    assert "," not in message.split(" m.")[0]


def test_deplacer_sans_point_refuse(plan, emprise):
    with pytest.raises(ErreurCoupe):
        translater_ligne_coupe(None, plan.azimut_tables_deg, emprise)
    with pytest.raises(ErreurCoupe):
        translater_ligne_coupe(Point(), plan.azimut_tables_deg, emprise)


def test_la_position_choisie_se_rejoue_et_ne_se_recalcule_pas(plan, tableau, emprise):
    """Une régénération conserve la position déplacée à la main.

    C'est le piège de ce chantier, mesuré le 15/09/2026 : la sortie ne gardait
    que le tracé, et la reprise le repassait par `corriger_ligne_coupe` avec les
    tables — ce qui recalculait la position et reposait la coupe automatique. Le
    choix du chef de projet était perdu, et l'écran l'annonçait comme un
    déplacement dû au plan.
    """
    from dp_socle.import_be import parametres_json

    auto, _, _ = position_de_coupe(plan.azimut_tables_deg, emprise, plan.tables)
    point = Point(auto.x - 80.0, auto.y)
    deplacee = translater_ligne_coupe(point, plan.azimut_tables_deg, emprise)

    donnees = parametres_json(
        plan, tableau, controler(plan, tableau), ligne_coupe=deplacee
    )
    assert donnees["ligne_coupe"]["position_choisie"] is True

    enregistree = coupe_enregistree(donnees)
    assert enregistree.position_choisie
    rejouee, profil_reutilisable = reprendre_coupe(
        enregistree, plan.azimut_tables_deg, emprise, tables=plan.tables
    )

    assert rejouee.geometrie.distance(point) == pytest.approx(0.0, abs=1e-6)
    assert profil_reutilisable
    assert _ecart_a_la_perpendiculaire(rejouee, plan) == pytest.approx(0.0, abs=1e-9)
    assert any("Position de coupe reprise" in m for m in rejouee.avertissements)

    # Et sans cette distinction, la reprise aurait ramené la coupe automatique.
    recalculee = corriger_ligne_coupe(
        enregistree.trace_initial,
        plan.azimut_tables_deg,
        emprise,
        tables=plan.tables,
    )
    assert recalculee.geometrie.distance(point) == pytest.approx(80.0, abs=1.0)


def _releve_en_pente_vers_l_est(emprise, chemin: Path, pente: float = 0.05) -> Path:
    """Un relevé de synthèse dont l'altitude ne dépend que de l'abscisse est.

    Les rangées de Saint-Cyr sont est-ouest, donc la coupe est nord-sud et
    déplacer la coupe la fait glisser en x. Un terrain qui ne penche qu'en x rend
    un profil plat, à une altitude qui dit **où** la coupe est passée : c'est ce
    qui permet de mesurer que le profil suit la coupe, et non l'inverse.
    """
    minx, miny, maxx, maxy = emprise.bounds
    lignes = []
    x = minx - 15.0
    while x <= maxx + 15.0:
        y = miny - 15.0
        while y <= maxy + 15.0:
            lignes.append(f"{x:.2f} {y:.2f} {100.0 + pente * (x - minx):.3f}")
            y += 5.0
        x += 1.0
    chemin.write_text("\n".join(lignes), encoding="utf-8")
    return chemin


def test_le_profil_et_les_controles_suivent_la_coupe_deplacee(tmp_path, plan, emprise):
    """Déplacer la coupe relève le terrain ailleurs, et rejoue la cohérence.

    Une coupe déplacée sous le profil de la précédente donnerait une planche DP 3
    fausse et d'apparence parfaitement normale : les altitudes seraient celles
    d'une autre ligne, à quelques mètres près, sans que rien ne le signale.
    """
    releve = _releve_en_pente_vers_l_est(emprise, tmp_path / "releve.txt")
    minx = emprise.bounds[0]
    auto, _, _ = position_de_coupe(plan.azimut_tables_deg, emprise, plan.tables)

    altitudes_par_position = {}
    for decalage in (-80.0, 0.0, 60.0):
        coupe = translater_ligne_coupe(
            Point(auto.x + decalage, auto.y), plan.azimut_tables_deg, emprise
        )
        profil = profil_terrain(coupe, fichier_altimetrie=releve)
        # Terrain qui ne penche qu'en x, coupe à x constant : le profil est plat,
        # à l'altitude du x où la coupe est passée.
        attendue = 100.0 + 0.05 * (auto.x + decalage - minx)
        assert min(profil.altitudes_m) == pytest.approx(attendue, abs=0.15)
        assert max(profil.altitudes_m) == pytest.approx(attendue, abs=0.15)
        altitudes_par_position[decalage] = attendue

        # Et les contrôles de cohérence se rejouent sur cette ligne-là.
        coherence = controler_coherence(profil, coupe, plan.tables)
        assert coherence.nb_tables_comparees > 0

    # Les trois positions ne rendent pas le même profil : la mesure discrimine.
    assert len(set(round(a, 1) for a in altitudes_par_position.values())) == 3


def test_une_sortie_ecrite_avant_le_geste_rejoue_la_correction(plan, emprise):
    """Les sorties d'avant n'ont pas de position choisie : rien ne la suppose."""
    trace = LineString(
        [(emprise.centroid.x, emprise.centroid.y - 30),
         (emprise.centroid.x, emprise.centroid.y + 30)]
    )
    ancienne = corriger_ligne_coupe(trace, plan.azimut_tables_deg, emprise)
    donnees = {
        "ligne_coupe": {
            "corrigee": True,
            "azimut_tables_deg": plan.azimut_tables_deg,
            "coordonnees_l93": [list(c) for c in ancienne.geometrie.coords],
            "trace_initial_l93": [list(c) for c in ancienne.trace_initial.coords],
        }
    }
    enregistree = coupe_enregistree(donnees)
    assert enregistree.position_choisie is False

    rejouee, _ = reprendre_coupe(enregistree, plan.azimut_tables_deg, emprise)
    assert any("Tracé de coupe repris" in m for m in rejouee.avertissements)


# ---------------------------------------------------------------------------
# Étape E — profil altimétrique
# ---------------------------------------------------------------------------


def test_echantillonnage_tous_les_cinq_metres():
    abscisses, points = echantillonner(LineString([(0, 0), (0, 22)]), pas_m=5.0)
    assert abscisses == [0.0, 5.0, 10.0, 15.0, 20.0, 22.0]
    assert points[-1] == pytest.approx((0.0, 22.0))


def test_interpolation_du_profil():
    profil = ProfilTerrain([0.0, 10.0, 20.0], [100.0, 110.0, 105.0], "test", 10.0)
    assert profil.altitude_a(5.0) == pytest.approx(105.0)
    assert profil.altitude_a(-3.0) == pytest.approx(100.0)  # avant A
    assert profil.altitude_a(99.0) == pytest.approx(105.0)  # après A'
    assert profil.denivelee_m == pytest.approx(10.0)


def test_fichier_altimetrie_xyz_prend_le_pas_sur_le_service(tmp_path):
    """Le repli manuel doit être annoncé, jamais silencieux."""
    fichier = tmp_path / "releve.txt"
    fichier.write_text(
        "X;Y;Z\n"
        "0,0;0,0;100,00\n"
        "0,0;50,0;102,00\n"
        "0,0;100,0;101,00\n",
        encoding="utf-8",
    )
    ligne = LineString([(0, 0), (0, 100)])
    profil = profil_terrain(ligne, pas_m=25.0, fichier_altimetrie=fichier)
    assert profil.altitudes_m == pytest.approx([100.0, 101.0, 102.0, 101.5, 101.0])
    assert "releve.txt" in profil.origine
    assert any("prend le pas" in m for m in profil.avertissements)


def test_fichier_altimetrie_de_format_inattendu_refuse(tmp_path):
    fichier = tmp_path / "mauvais.txt"
    fichier.write_text("0 0 100 42\n0 50 102 43\n", encoding="utf-8")
    with pytest.raises(ErreurCoupe) as erreur:
        profil_terrain(LineString([(0, 0), (0, 100)]), fichier_altimetrie=fichier)
    assert "colonnes" in str(erreur.value)


def test_coherence_detecte_un_referentiel_altimetrique_decale():
    """Un décalage de référentiel se compte en dizaines de mètres."""
    ligne = LineString([(0, 0), (0, 100)])
    profil = ProfilTerrain([0.0, 100.0], [100.0, 100.0], "test", 5.0)
    tables = [
        Polygon(
            [(-2, y, 148.0), (2, y, 148.0), (2, y + 4, 149.2), (-2, y + 4, 149.2)]
        )
        for y in (10, 30, 50)
    ]
    coherence = controler_coherence(profil, ligne, tables)
    assert coherence.nb_tables_comparees == 3
    assert not coherence.conforme
    assert "référentiel" in coherence.message


def test_coherence_admet_la_garde_au_sol_de_la_structure():
    ligne = LineString([(0, 0), (0, 100)])
    profil = ProfilTerrain([0.0, 100.0], [100.0, 100.0], "test", 5.0)
    tables = [
        Polygon([(-2, y, 101.7), (2, y, 101.7), (2, y + 4, 102.9), (-2, y + 4, 102.9)])
        for y in (10, 30, 50)
    ]
    coherence = controler_coherence(profil, ligne, tables)
    assert coherence.conforme
    assert coherence.ecart_median_m == pytest.approx(1.7)


# ---------------------------------------------------------------------------
# Sorties — contrat d'interface avec le lot 4
# ---------------------------------------------------------------------------


def test_geopackage_relu_avec_son_systeme_de_coordonnees(tmp_path, plan, emprise):
    import geopandas as gpd

    import_be = importer_be(DXF, TABLEAU, "IND06", seuil_puissance_mwc=3.0)
    centre = emprise.centroid
    import_be.ligne_coupe = corriger_ligne_coupe(
        LineString([(centre.x - 20, centre.y - 20), (centre.x + 20, centre.y + 20)]),
        import_be.plan.azimut_tables_deg,
        emprise,
    )
    gpkg, parametres = import_be.ecrire(tmp_path)

    tables = gpd.read_file(gpkg, layer="tables_pv")
    assert tables.crs.to_epsg() == 2154
    assert len(tables) == 96
    assert tables.geometry.iloc[0].has_z
    assert bool(tables["z_reel"].iloc[0])

    coupe = gpd.read_file(gpkg, layer="ligne_coupe")
    assert coupe.crs.to_epsg() == 2154
    assert len(coupe) == 1

    import json

    donnees = json.loads(parametres.read_text(encoding="utf-8"))
    assert donnees["origine"] == "import_be"
    assert donnees["plan"]["nb_tables"] == 96
    assert donnees["parametres"]["modules"]["puissance_mwc"] == pytest.approx(2.93878)
    assert donnees["ligne_coupe"]["azimut_coupe_deg"] == pytest.approx(90.0)


def test_reecriture_ne_empile_pas_les_couches(tmp_path, emprise):
    """Un second import dans le même dossier repart d'un GeoPackage neuf."""
    import pyogrio

    import_be = importer_be(DXF, TABLEAU, "IND06")
    import_be.ecrire(tmp_path)
    premier = len(pyogrio.list_layers(tmp_path / "geometries.gpkg"))
    import_be.ecrire(tmp_path)
    assert len(pyogrio.list_layers(tmp_path / "geometries.gpkg")) == premier


# ---------------------------------------------------------------------------
# Service altimétrique — mesuré sur la réponse réelle
# ---------------------------------------------------------------------------


@pytest.mark.reseau
def test_profil_recupere_en_une_requete_et_concorde_avec_les_z_du_dxf(plan, emprise):
    """Critère 7 du brief, mesuré de bout en bout sur le fichier de référence."""
    from dp_socle.ign import POINTS_PAR_REQUETE

    centre = emprise.centroid
    coupe = corriger_ligne_coupe(
        LineString([(centre.x - 20, centre.y - 20), (centre.x + 20, centre.y + 20)]),
        plan.azimut_tables_deg,
        emprise,
    )
    abscisses, points = echantillonner(coupe.geometrie)
    assert len(points) <= 2 * POINTS_PAR_REQUETE  # une ou deux requêtes

    profil = profil_terrain(coupe)
    assert len(profil.abscisses_m) == len(abscisses)
    assert 80.0 < profil.altitude_min_m < 120.0  # NGF plausible à Saint-Cyr

    coherence = controler_coherence(profil, coupe, plan.tables)
    assert coherence.nb_tables_comparees > 0
    assert coherence.conforme
    assert abs(coherence.ecart_median_m) <= 2.0


class _ReponseFeinte:
    """Ce que `requests.get` rend, réduit à ce que le module en lit."""

    def __init__(self, status_code: int, altitudes=None, text: str = ""):
        self.status_code = status_code
        self.text = text
        self._altitudes = altitudes

    def json(self):
        return {"elevations": list(self._altitudes)}


def _service_altimetrique_feint(monkeypatch, reponses):
    """Remplace le transport du service. Rend la liste des appels effectués."""
    import dp_socle.ign as ign

    appels = []
    restantes = list(reponses)

    def faux_get(url, params=None, headers=None, timeout=None):
        appels.append(params)
        reponse = restantes.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    monkeypatch.setattr(ign.requests, "get", faux_get)
    # Sans cela, trois tentatives feraient attendre le test quatre secondes.
    monkeypatch.setattr(ign.time, "sleep", lambda _: None)
    return appels


def test_une_panne_passagere_du_rge_alti_est_rejouee(monkeypatch):
    """Un 503 suivi d'un 200 rend les altitudes, et la reprise se dit.

    La coupe d'un dossier tient en une ou deux requêtes : sans reprise, un aléa
    de quelques secondes du service faisait perdre la coupe entière, et c'est ce
    qui faisait échouer le contrôle croisé par intermittence (17/09/2026).
    """
    from dp_socle.ign import telecharger_altitudes

    appels = _service_altimetrique_feint(
        monkeypatch,
        [
            _ReponseFeinte(503, text="Service Unavailable"),
            _ReponseFeinte(200, altitudes=[101.0, 102.0]),
        ],
    )
    with pytest.warns(RuntimeWarning, match="tentative 1 sur 3"):
        altitudes = telecharger_altitudes([(650000.0, 6750000.0), (650005.0, 6750000.0)])

    assert altitudes == [101.0, 102.0]
    assert len(appels) == 2
    # Ce sont bien les mêmes points qui sont redemandés, rien n'est substitué.
    assert appels[0] == appels[1]


def test_une_requete_refusee_par_sa_forme_n_est_pas_rejouee(monkeypatch):
    """Un 414 vient de l'URL, pas du service : le rejouer perdrait du temps."""
    from dp_socle.erreurs import ErreurAltimetrie
    from dp_socle.ign import telecharger_altitudes

    appels = _service_altimetrique_feint(
        monkeypatch, [_ReponseFeinte(414, text="Request-URI Too Long")]
    )
    with pytest.raises(ErreurAltimetrie, match="même requête donnerait le même"):
        telecharger_altitudes([(650000.0, 6750000.0)])

    assert len(appels) == 1


def test_un_service_durablement_injoignable_finit_par_lever(monkeypatch):
    """Trois échecs de transport : le message compte les tentatives et oriente."""
    import requests

    from dp_socle.erreurs import ErreurAltimetrie
    from dp_socle.ign import telecharger_altitudes

    appels = _service_altimetrique_feint(
        monkeypatch, [requests.ConnectionError("coupure") for _ in range(3)]
    )
    with pytest.warns(RuntimeWarning):
        with pytest.raises(ErreurAltimetrie) as leve:
            telecharger_altitudes([(650000.0, 6750000.0)])

    assert "après 3 tentatives" in str(leve.value)
    assert "fichier d'altimétrie en repli" in str(leve.value)
    assert len(appels) == 3


def test_virgule_decimale_et_virgule_separatrice_ne_sont_pas_confondues(tmp_path):
    """« 0,0;0,0;100,00 » compte trois colonnes, pas six."""
    fichier = tmp_path / "csv_francais.txt"
    fichier.write_text("0,0;0,0;100,00\n0,0;100,0;104,00\n", encoding="utf-8")
    profil = profil_terrain(
        LineString([(0, 0), (0, 100)]), pas_m=50.0, fichier_altimetrie=fichier
    )
    assert profil.altitudes_m == pytest.approx([100.0, 102.0, 104.0])
    assert any("point-virgule" in m for m in profil.avertissements)


def test_csv_a_la_virgule_avec_decimale_au_point(tmp_path):
    fichier = tmp_path / "csv_anglais.txt"
    fichier.write_text("0.0,0.0,100.0\n0.0,100.0,104.0\n", encoding="utf-8")
    profil = profil_terrain(
        LineString([(0, 0), (0, 100)]), pas_m=50.0, fichier_altimetrie=fichier
    )
    assert profil.altitudes_m == pytest.approx([100.0, 102.0, 104.0])
    assert any("virgule" in m for m in profil.avertissements)


# ---------------------------------------------------------------------------
# Carte interactive du tracé (étape F)
# ---------------------------------------------------------------------------


def test_geojson_de_la_carte_est_une_featurecollection(plan):
    """Régression : folium ne sait pas cadrer sur une `GeometryCollection`.

    Sa descente de l'arbre des couches lève `KeyError: 'coordinates'` et la
    carte de tracé ne s'affiche pas du tout — donc plus de ligne de coupe.
    """
    import folium

    from dp_socle.apercu_be import URL_TUILES_ORTHO, en_wgs84

    collection = en_wgs84(plan.geometries("tables_pv"))
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 96

    carte = folium.Map(tiles=None)
    folium.TileLayer(tiles=URL_TUILES_ORTHO, attr="IGN").add_to(carte)
    folium.GeoJson(collection).add_to(carte)
    sud, ouest, nord, est = [c for paire in carte.get_bounds() for c in paire]
    assert 47.8 < sud < nord < 47.9  # Saint-Cyr-en-Val
    assert 1.9 < ouest < est < 2.0


def test_trace_de_la_carte_revient_en_lambert_93(plan):
    """Le tracé arrive en WGS84 ; tout ce qui est mesuré reste en L93."""
    from dp_socle.apercu_be import bornes_wgs84, trace_l93

    sud, ouest, nord, est = bornes_wgs84(plan.polygone_cloture)
    trace = trace_l93(
        {
            "last_active_drawing": {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[ouest, sud], [est, nord]],
                }
            }
        }
    )
    assert trace is not None
    minx, miny, maxx, maxy = plan.polygone_cloture.bounds
    assert trace.coords[0] == pytest.approx((minx, miny), abs=0.5)
    assert trace.coords[-1] == pytest.approx((maxx, maxy), abs=0.5)


def test_carte_sans_trace_ne_renvoie_rien():
    from dp_socle.apercu_be import trace_l93

    assert trace_l93(None) is None
    assert trace_l93({}) is None
    assert trace_l93({"all_drawings": []}) is None
    # Un polygone dessiné par erreur n'est pas une ligne de coupe.
    assert (
        trace_l93(
            {
                "last_active_drawing": {
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]}
                }
            }
        )
        is None
    )


def test_deplacer_la_coupe_la_translate_en_bloc(plan, emprise):
    """Le segment glisse sans tourner ni changer de longueur.

    C'est la propriété sur laquelle repose le trait d'aperçu qui suit la souris :
    il peut être le segment de référence translaté, plutôt qu'une coupe
    recalculée à chaque mouvement. `_etendre` projette les sommets de l'emprise
    sur la direction de coupe *relativement au point de passage* ; déplacer ce
    point perpendiculairement à la coupe ne change aucune de ces projections.
    """
    base = translater_ligne_coupe(
        emprise.centroid, plan.azimut_tables_deg, emprise
    ).geometrie
    depart, arrivee = base.coords[0], base.coords[-1]

    for decalage in (-90.0, -30.0, 45.0, 95.0):
        # Le décalage porte sur l'axe des rangées (est-ouest à Saint-Cyr), plus
        # un déplacement le long de la coupe, qui ne doit rien changer du tout.
        glissee = translater_ligne_coupe(
            Point(emprise.centroid.x + decalage, emprise.centroid.y + 40.0),
            plan.azimut_tables_deg,
            emprise,
        ).geometrie
        a2, b2 = glissee.coords[0], glissee.coords[-1]
        # Les deux extrémités subissent la même translation, au bit près.
        assert a2[0] - depart[0] == pytest.approx(b2[0] - arrivee[0], abs=1e-9)
        assert a2[1] - depart[1] == pytest.approx(b2[1] - arrivee[1], abs=1e-9)
        assert glissee.length == pytest.approx(base.length, abs=1e-9)


def test_le_trait_d_apercu_ne_ment_pas_sur_l_endroit_de_la_coupe(plan, emprise):
    """L'aperçu dessiné dans le navigateur tombe sur la coupe que Python calculera.

    Leaflet translate le segment dans le plan de la carte, en pixels Web Mercator,
    quand la coupe est calculée en Lambert 93. Le Web Mercator est conforme, donc
    le trait reste parallèle ; reste à mesurer ce que coûte le changement de
    projection. Ce test refait le calcul du navigateur et le compare au tracé
    réel : un aperçu qui mentirait d'un mètre ferait cliquer à côté.
    """
    from pyproj import Transformer

    vers_merc = Transformer.from_crs(2154, 3857, always_xy=True)
    vers_l93 = Transformer.from_crs(3857, 2154, always_xy=True)
    base = translater_ligne_coupe(
        emprise.centroid, plan.azimut_tables_deg, emprise
    ).geometrie
    depart, arrivee = base.coords[0][:2], base.coords[-1][:2]

    pire = 0.0
    for dx in (-100.0, -40.0, 0.0, 55.0, 100.0):
        for dy in (-180.0, 0.0, 180.0):
            curseur = (emprise.centroid.x + dx, emprise.centroid.y + dy)
            vraie = translater_ligne_coupe(
                Point(*curseur), plan.azimut_tables_deg, emprise
            ).geometrie

            # Le calcul que fait le navigateur, à l'identique.
            a, b, c = (vers_merc.transform(*p) for p in (depart, arrivee, curseur))
            ux, uy = b[0] - a[0], b[1] - a[1]
            norme = (ux * ux + uy * uy) ** 0.5
            ux, uy = ux / norme, uy / norme
            vx, vy = c[0] - a[0], c[1] - a[1]
            projete = vx * ux + vy * uy
            wx, wy = vx - projete * ux, vy - projete * uy
            apercu = [
                Point(*vers_l93.transform(a[0] + wx, a[1] + wy)),
                Point(*vers_l93.transform(b[0] + wx, b[1] + wy)),
            ]
            pire = max(pire, max(vraie.distance(bout) for bout in apercu))

    # Mesuré à 1,3 cm sur Saint-Cyr le 15/09/2026. Le seuil est à 10 cm : bien
    # au-dessus de la mesure, et bien en dessous du pixel de carte au zoom 18,
    # qui vaut 45 cm. Le chef de projet ne peut pas cliquer plus fin que ça.
    assert pire < 0.10, f"le trait d'aperçu s'écarte de {pire * 100:.1f} cm"


def test_le_trait_d_apercu_part_dans_le_script_de_la_carte(plan, emprise):
    """Sans ce JS dans le script envoyé au navigateur, le trait n'existe pas.

    Vérifié le 15/09/2026 dans `streamlit-folium` 0.27.2 : son
    `generate_leaflet_string` appelle `_template.module.script` sur chaque enfant
    de la carte (`__init__.py:517`), donc un `MacroElement` est bien exécuté.
    """
    import folium
    from streamlit_folium import _get_map_string

    from dp_socle.apercu_be import apercu_au_survol

    coupe = translater_ligne_coupe(
        emprise.centroid, plan.azimut_tables_deg, emprise
    ).geometrie
    carte = folium.Map(tiles=None)
    apercu_au_survol(coupe).add_to(carte)
    script = _get_map_string(carte)

    assert 'carte.on("mousemove"' in script
    assert 'carte.on("mouseout"' in script
    # La carte est renommée `map_div` par le composant : sans cette substitution
    # le JS s'accrocherait à une variable qui n'existe pas côté navigateur.
    assert "var carte = map_div;" in script
    # Le trait ne doit pas intercepter le clic qui suit, sinon il n'arrive jamais.
    assert "interactive: false" in script
    # Et il part invisible : il n'apparaît qu'au premier mouvement de souris.
    assert "opacity: 0," in script


def test_le_trait_se_fige_au_clic_et_annonce_le_travail(plan, emprise):
    """Sans cela, le clic semblait ne pas avoir pris.

    Relevé le 15/09/2026 par le chef de projet : Streamlit met une à deux
    secondes à rejouer le script — relevé du profil et contrôles de cohérence
    compris — et pendant ce temps le trait continuait de suivre la souris sur la
    carte encore affichée. Le geste paraissait perdu, et recliquer n'arrangeait
    rien : le second point était ignoré, le geste étant déjà désarmé.

    Leaflet, lui, voit le clic tout de suite. Le trait se fige donc à l'instant
    du clic, prend l'aspect d'une coupe retenue, et un bandeau dit ce qui se
    passe. Vérifié dans un navigateur le même jour : après le clic, ni un survol
    lointain ni un second clic ne le déplacent.
    """
    import folium
    from streamlit_folium import _get_map_string

    from dp_socle.apercu_be import apercu_au_survol

    coupe = translater_ligne_coupe(
        emprise.centroid, plan.azimut_tables_deg, emprise
    ).geometrie
    carte = folium.Map(tiles=None)
    apercu_au_survol(coupe).add_to(carte)
    script = _get_map_string(carte)

    assert 'carte.on("click"' in script
    assert "var fige = false;" in script
    # Le survol et la sortie de carte cessent tous deux d'agir une fois figé.
    assert "if (!fige) { placer(e.latlng); }" in script
    assert "if (!fige) { apercu.setStyle({opacity: 0}); }" in script
    # Le trait figé n'est plus un aperçu : plein, opaque, épaisseur de la coupe.
    assert "dashArray: null" in script
    # Et l'écran dit pourquoi il attend.
    assert "relevé du profil du terrain" in script
    assert 'cursor = "progress"' in script


def test_clic_de_la_carte_revient_en_lambert_93(plan):
    """Le clic arrive en WGS84 ; tout ce qui est mesuré reste en L93."""
    from dp_socle.apercu_be import bornes_wgs84, clic_l93

    sud, ouest, nord, est = bornes_wgs84(plan.polygone_cloture)
    clic = clic_l93({"last_clicked": {"lat": sud, "lng": ouest}})

    assert clic is not None
    minx, miny, _, _ = plan.polygone_cloture.bounds
    assert (clic.x, clic.y) == pytest.approx((minx, miny), abs=0.5)


def test_carte_sans_clic_ne_renvoie_rien():
    """La carte rend `last_clicked` à None tant que personne n'a cliqué."""
    from dp_socle.apercu_be import clic_l93

    assert clic_l93(None) is None
    assert clic_l93({}) is None
    assert clic_l93({"last_clicked": None}) is None
    # Et une charge tronquée ne passe pas pour un clic à l'équateur.
    assert clic_l93({"last_clicked": {"lat": 47.86}}) is None


def test_apercu_du_plan_sur_fond_ortho(plan, emprise):
    """L'aperçu se compose sans planter, avec la coupe superposée."""
    from dp_socle.apercu_be import apercu_plan, cadre_apercu, legende_presente

    class _FondFactice:
        """Ortho remplacée par une image unie : ce test mesure le dessin des
        géométries, pas la disponibilité du WMS."""

        def __init__(self, taille):
            from PIL import Image

            self.image = Image.new("RGB", taille, (120, 120, 120))

    centre = emprise.centroid
    coupe = corriger_ligne_coupe(
        LineString([(centre.x - 30, centre.y - 30), (centre.x + 30, centre.y + 30)]),
        plan.azimut_tables_deg,
        emprise,
    )
    cadre = cadre_apercu(plan)
    minx, miny, maxx, maxy = cadre
    largeur = 900
    fond = _FondFactice((largeur, round(largeur * (maxy - miny) / (maxx - minx))))

    image = apercu_plan(plan, ligne_coupe=coupe, fond=fond, cadre=cadre, largeur_px=450)
    assert image.size[0] == 450
    categories = {categorie for categorie, _, _ in legende_presente(plan)}
    assert "tables_pv" in categories and "cloture" in categories


# ---------------------------------------------------------------------------
# Nuage de points de l'outil topographique interne
# ---------------------------------------------------------------------------

NUAGE = Path(
    "exemples/rosnay-lhopital-topo/"
    "sco_rosnay-lhopital-flottant-parcelles-topo-sc-30_06_2026_12_43_1m_interpole.txt"
)

#: Coupe nord-sud entièrement contenue dans le nuage de Rosnay-l'Hôpital.
COUPE_NUAGE = LineString([(809_500.0, 6_815_600.0), (809_500.0, 6_816_000.0)])


def _couloir_de_reference(demi_largeur_m: float = 0.75) -> dict[int, float]:
    """Profil de contrôle, calculé à la main, hors du code testé."""
    x0 = COUPE_NUAGE.coords[0][0]
    y0, y1 = COUPE_NUAGE.coords[0][1], COUPE_NUAGE.coords[-1][1]
    par_abscisse: dict[int, list[float]] = {}
    with NUAGE.open(encoding="utf-8") as fichier:
        next(fichier)  # ligne d'en-tête « _MULTIPLE _POINT »
        for ligne in fichier:
            x, y, z = (float(v) for v in ligne.split(","))
            if abs(x - x0) <= demi_largeur_m and y0 <= y <= y1:
                par_abscisse.setdefault(round(y - y0), []).append(z)
    return {s: sum(zs) / len(zs) for s, zs in par_abscisse.items()}


def test_nuage_de_points_lu_dans_un_couloir_et_non_projete_en_entier():
    """Le relevé de l'outil topo est un nuage, pas un profil.

    202 399 points sur une grille au mètre couvrant 605 × 494 m. Les projeter
    tous sur la coupe puis trier par abscisse donnait un profil *plausible* et
    faux : jusqu'à 2,57 m d'écart, d'amplitude 3,14 m, pour un relief réel de
    3,50 m. Rien ne le signalait.
    """
    profil = profil_terrain(COUPE_NUAGE, pas_m=5.0, fichier_altimetrie=NUAGE)
    reference = _couloir_de_reference()

    ecarts = [
        z - reference[round(s)]
        for s, z in zip(profil.abscisses_m, profil.altitudes_m)
        if round(s) in reference
    ]
    assert len(ecarts) > 50
    assert max(abs(e) for e in ecarts) < 0.20
    assert profil.denivelee_m == pytest.approx(
        max(reference.values()) - min(reference.values()), abs=0.05
    )
    assert any("couloir" in m for m in profil.avertissements)


def test_entete_non_numerique_du_nuage_saute():
    """La première ligne du fichier est « _MULTIPLE _POINT »."""
    assert NUAGE.read_text(encoding="utf-8").splitlines()[0] == "_MULTIPLE _POINT"
    profil = profil_terrain(COUPE_NUAGE, pas_m=25.0, fichier_altimetrie=NUAGE)
    assert all(100.0 < z < 130.0 for z in profil.altitudes_m)
    assert any("virgule" in m for m in profil.avertissements)


def test_coupe_en_diagonale_trouve_des_points_sur_une_grille_au_metre():
    """Cas le plus défavorable : en diagonale, la grille au mètre espace de 1,41 m."""
    diagonale = LineString(
        [(809_400.0, 6_815_700.0), (809_600.0, 6_815_900.0)]
    )
    profil = profil_terrain(diagonale, pas_m=5.0, fichier_altimetrie=NUAGE)
    assert len(profil.altitudes_m) > 50
    assert all(100.0 < z < 130.0 for z in profil.altitudes_m)


def test_coupe_hors_du_nuage_leve_au_lieu_de_rendre_un_profil():
    hors = LineString([(800_000.0, 6_810_000.0), (800_000.0, 6_810_400.0)])
    with pytest.raises(ErreurCoupe) as erreur:
        profil_terrain(hors, pas_m=5.0, fichier_altimetrie=NUAGE)
    assert "ne couvre pas cette coupe" in str(erreur.value)


def test_trou_dans_le_couloir_signale(tmp_path):
    """Un profil interpolé en ligne droite sur 100 m doit se dire."""
    fichier = tmp_path / "nuage_troue.txt"
    lignes = ["_MULTIPLE _POINT"]
    for y in list(range(0, 40)) + list(range(140, 200)):
        for x in (-1, 0, 1):
            lignes.append(f"{x}.00,{y}.00,{100 + y * 0.01:.2f}")
    fichier.write_text("\n".join(lignes) + "\n", encoding="utf-8")

    profil = profil_terrain(
        LineString([(0, 0), (0, 199)]), pas_m=10.0, fichier_altimetrie=fichier
    )
    assert any("trou de" in m for m in profil.avertissements)


@pytest.mark.reseau
def test_le_nuage_du_be_concorde_avec_le_rge_alti():
    """Contrôle croisé de deux sources indépendantes sur le même segment.

    Elles s'accordent à ±0,10 m, écart-type 0,02 m : l'outil topographique
    interne rééchantillonne le RGE ALTI, il n'apporte pas une mesure de terrain
    plus fine. C'est donc un repli quand le service est indisponible, pas une
    source à préférer.
    """
    nuage = profil_terrain(COUPE_NUAGE, pas_m=5.0, fichier_altimetrie=NUAGE)
    ign = profil_terrain(COUPE_NUAGE, pas_m=5.0)
    ecarts = [a - b for a, b in zip(nuage.altitudes_m, ign.altitudes_m)]
    assert max(abs(e) for e in ecarts) < 0.30
    assert nuage.denivelee_m == pytest.approx(ign.denivelee_m, abs=0.15)


# ---------------------------------------------------------------------------
# Azimut : trois écritures, aucune convention
# ---------------------------------------------------------------------------


def _controle_azimut(plan, azimut_dxf, ecrit_au_tableau):
    """Rejoue le contrôle d'orientation avec une valeur d'azimut donnée."""
    from dataclasses import replace

    from dp_socle.tableau_bilan import _angle, _texte

    tableau = lire_tableau(TABLEAU, "IND06")
    tableau.structures["azimut_deg"] = _angle(ecrit_au_tableau, "Azimut (°)")
    tableau.structures["azimut_brut"] = _texte(ecrit_au_tableau, "Azimut (°)")
    plan_oriente = replace(plan, azimut_tables_deg=azimut_dxf)
    return next(
        c
        for c in controler(plan_oriente, tableau)
        if c.libelle == "Inclinaison des rangées"
    )


@pytest.mark.parametrize(
    ("azimut_dxf", "ecrit_au_tableau"),
    [
        # Saint-Cyr : rangées est-ouest, « 0° » au tableau, 0 valant le sud.
        (0.0, "0°"),
        # Le même champ plein sud écrit en azimut compas ailleurs.
        (0.0, "180"),
        # Un projet sud-est, direction en toutes lettres.
        (-41.0, "41° SE"),
        (41.0, "41° SE"),
        # Un autre projet sud-est, sans direction et de signe contraire.
        (24.5, "-24,5"),
        (-24.5, "-24,5"),
    ],
)
def test_orientation_reconnue_quelle_que_soit_l_ecriture(
    plan, azimut_dxf, ecrit_au_tableau
):
    """Les trois écritures relevées chez le BE décrivent la même grandeur.

    Ramener dans ]-90, 90] absorbe l'origine (0 ou 180 pour le sud), la valeur
    absolue absorbe le sens de comptage.
    """
    controle = _controle_azimut(plan, azimut_dxf, ecrit_au_tableau)
    assert controle.statut == OK
    # La cellule est montrée telle qu'écrite : le « SE » n'est pas avalé.
    assert str(ecrit_au_tableau) in controle.message


def test_orientation_franchement_differente_avertit(plan):
    """Rangées est-ouest alors que le tableau annonce un champ à 41°."""
    controle = _controle_azimut(plan, 0.0, "41° SE")
    assert controle.statut == AVERTISSEMENT
    assert "41.00°" in controle.message


def test_plan_en_miroir_non_detecte_et_c_est_documente(plan):
    """Limite assumée, faute de convention écrite au tableau.

    Ce test existe pour que la limite soit visible et se casse si quelqu'un
    croit un jour l'avoir corrigée sans avoir obtenu la convention.
    """
    assert _controle_azimut(plan, 41.0, "41° SE").statut == OK
    assert _controle_azimut(plan, -41.0, "41° SE").statut == OK


def test_direction_ecrite_conservee_dans_le_tableau_lu():
    """Le convertisseur numérique avalait « SE » sans rien dire."""
    from dp_socle.tableau_bilan import _angle, _texte

    assert _angle("41° SE", "Azimut (°)") == pytest.approx(41.0)
    assert _texte("41° SE", "Azimut (°)") == "41° SE"

    tableau = lire_tableau(TABLEAU, "IND06")
    assert tableau.structures["azimut_deg"] == pytest.approx(0.0)
    assert tableau.structures["azimut_brut"] == "0°"


# ---------------------------------------------------------------------------
# Reprise d'un import précédent — « une régénération ne redemande jamais
# le tracé » (brief, étape D, critère 4)
# ---------------------------------------------------------------------------


def _sortie_avec_coupe(dossier: Path, emprise, plan, azimut=None):
    """Écrit une sortie d'import complète, coupe et profil compris."""
    import_be = importer_be(DXF, TABLEAU, "IND06", seuil_puissance_mwc=3.0)
    centre = emprise.centroid
    coupe = corriger_ligne_coupe(
        LineString([(centre.x - 40, centre.y - 28), (centre.x + 40, centre.y + 28)]),
        plan.azimut_tables_deg if azimut is None else azimut,
        emprise,
    )
    import_be.ligne_coupe = coupe
    import_be.profil = ProfilTerrain(
        [0.0, coupe.longueur_m], [100.0, 103.0], "profil de test", 5.0
    )
    import_be.ecrire(dossier)
    return coupe


def test_le_trace_est_repris_sans_etre_redemande(tmp_path, plan, emprise):
    from dp_socle.coupe import coupe_enregistree, reprendre_coupe
    from dp_socle.import_be import lire_parametres

    origine = _sortie_avec_coupe(tmp_path, emprise, plan)

    enregistree = coupe_enregistree(lire_parametres(tmp_path))
    assert enregistree is not None
    assert not enregistree.manuel
    assert enregistree.profil is not None

    reprise, profil_reutilisable = reprendre_coupe(
        enregistree, plan.azimut_tables_deg, emprise
    )
    assert profil_reutilisable
    assert reprise.geometrie.hausdorff_distance(origine.geometrie) < 0.01
    assert reprise.trace_initial.equals_exact(origine.trace_initial, tolerance=1e-6)
    assert any("repris de l'import précédent" in m for m in reprise.avertissements)


def test_reprise_rejoue_la_correction_sur_le_plan_du_jour(tmp_path, plan, emprise):
    """Un nouvel indice qui tourne les tables doit tourner la coupe avec.

    Recharger la ligne corrigée telle quelle la figerait sur un plan qui
    n'existe plus, et la coupe ne serait plus perpendiculaire aux rangées.
    """
    from shapely.affinity import rotate

    from dp_socle.coupe import coupe_enregistree, reprendre_coupe
    from dp_socle.import_be import lire_parametres

    _sortie_avec_coupe(tmp_path, emprise, plan)
    enregistree = coupe_enregistree(lire_parametres(tmp_path))

    pivot = emprise.centroid
    emprise_tournee = rotate(emprise, 20.0, origin=pivot)
    reprise, profil_reutilisable = reprendre_coupe(
        enregistree, 20.0, emprise_tournee
    )

    # Toujours perpendiculaire aux rangées, sur leur nouvelle orientation.
    assert (reprise.azimut_coupe_deg - 20.0) % 180.0 == pytest.approx(90.0, abs=1e-6)
    # Le profil ne peut pas être réutilisé sous une ligne qui a bougé.
    assert not profil_reutilisable
    assert any("s'est déplacée" in m for m in reprise.avertissements)


def test_mode_manuel_repris_tel_quel(tmp_path, plan, emprise):
    from dp_socle.coupe import coupe_enregistree, reprendre_coupe
    from dp_socle.import_be import lire_parametres

    import_be = importer_be(DXF, TABLEAU, "IND06")
    centre = emprise.centroid
    import_be.ligne_coupe = corriger_ligne_coupe(
        LineString([(centre.x - 40, centre.y - 28), (centre.x + 40, centre.y + 28)]),
        plan.azimut_tables_deg,
        emprise,
        manuel=True,
    )
    import_be.ecrire(tmp_path)

    enregistree = coupe_enregistree(lire_parametres(tmp_path))
    assert enregistree.manuel
    reprise, _ = reprendre_coupe(enregistree, plan.azimut_tables_deg, emprise)
    assert not reprise.corrigee
    assert reprise.azimut_coupe_deg == pytest.approx(35.0, abs=0.1)


def test_premier_import_sans_sortie_precedente(tmp_path):
    """L'absence de fichier est le cas normal, pas une erreur."""
    from dp_socle.coupe import coupe_enregistree
    from dp_socle.import_be import lire_parametres

    assert lire_parametres(tmp_path) is None
    assert coupe_enregistree(None) is None


def test_sortie_ecrite_sans_coupe_ne_rend_pas_de_trace(tmp_path):
    from dp_socle.coupe import coupe_enregistree
    from dp_socle.import_be import lire_parametres

    importer_be(DXF, TABLEAU, "IND06").ecrire(tmp_path)
    donnees = lire_parametres(tmp_path)
    assert donnees is not None and "ligne_coupe" not in donnees
    assert coupe_enregistree(donnees) is None


def test_projet_json_du_lot_1_refuse(tmp_path):
    """Les deux fichiers portent le même nom, dans deux dossiers différents."""
    import json

    from dp_socle.erreurs import ErreurImportBE
    from dp_socle.import_be import lire_parametres

    (tmp_path / "projet.json").write_text(
        json.dumps({"nom": "ALR_45", "commune": "Bray-Saint-Aignan"}),
        encoding="utf-8",
    )
    with pytest.raises(ErreurImportBE) as erreur:
        lire_parametres(tmp_path)
    assert "lot 1" in str(erreur.value)


def test_contrat_de_version_plus_recent_refuse(tmp_path):
    import json

    from dp_socle.erreurs import ErreurImportBE
    from dp_socle.import_be import VERSION_CONTRAT, lire_parametres

    (tmp_path / "projet.json").write_text(
        json.dumps({"origine": "import_be", "version_contrat": VERSION_CONTRAT + 1}),
        encoding="utf-8",
    )
    with pytest.raises(ErreurImportBE) as erreur:
        lire_parametres(tmp_path)
    assert "version" in str(erreur.value)


# ---------------------------------------------------------------------------
# Emprise cadastrale réelle
# ---------------------------------------------------------------------------

EMPRISE_CADASTRALE = REFERENCE / "phu_45590_saint-cyr-en-val-geoperso-1-24_10_2025_17_11"


@pytest.fixture(scope="module")
def cadastre():
    from dp_socle.geometrie import charger_emprise

    return charger_emprise(EMPRISE_CADASTRALE).geometrie


def test_export_geoperso_porte_deux_fois_le_meme_polygone():
    """Relevé le 03/09/2026 sur l'export réel, et traité par l'union.

    Les deux entités sont géométriquement identiques : 4,5259 ha chacune,
    distance de Hausdorff nulle. `charger_emprise` en fait l'union et rend un
    seul polygone — c'est ce qui évite de compter la surface deux fois.
    """
    import geopandas as gpd

    from dp_socle.geometrie import charger_emprise

    brut = gpd.read_file(EMPRISE_CADASTRALE)
    assert len(brut) == 2
    assert brut.geometry.iloc[0].equals(brut.geometry.iloc[1])
    assert brut.geometry.area.sum() / 10_000 == pytest.approx(9.052, abs=0.002)

    emprise = charger_emprise(EMPRISE_CADASTRALE)
    assert emprise.nb_polygones == 1
    assert emprise.surface_m2 / 10_000 == pytest.approx(4.526, abs=0.002)


def test_cloture_reelle_tenue_pour_contenue_dans_le_cadastre(plan, tableau, cadastre):
    """Le seuil de 1 m² éprouvé sur du réel, non plus sur un polygone fabriqué.

    La clôture dépasse de 0,53 m² de l'emprise cadastrale : de l'imprécision de
    numérisation, pas un débordement. Un vrai débordement se compte en dizaines
    de m² — celui du test synthétique voisin en fait plusieurs milliers.
    """
    from dp_socle.import_be import DEBORDEMENT_NEGLIGEABLE_M2

    debordement = plan.polygone_cloture.difference(cadastre).area
    assert 0.0 < debordement < DEBORDEMENT_NEGLIGEABLE_M2

    controle = next(
        c
        for c in controler(plan, tableau, emprise_cadastrale=cadastre)
        if c.libelle == "Clôture dans l'emprise cadastrale"
    )
    assert controle.statut == OK


def test_import_complet_avec_emprise_reelle_ne_leve_aucun_bloquant(cadastre):
    """Le jeu Saint-Cyr au complet : DXF, tableau et parcellaire réels."""
    import_be = importer_be(
        DXF,
        TABLEAU,
        "IND06",
        emprise_cadastrale=cadastre,
        seuil_puissance_mwc=3.0,
    )
    assert import_be.bloquants == []
    assert all(c.statut == OK for c in import_be.controles)
    # Plus aucun avertissement de contrôle : c'est le seul jeu où toutes les
    # pièces d'entrée sont présentes.
    assert import_be.avertissements == []


# ---------------------------------------------------------------------------
# Contrôle du profil par les altitudes embarquées dans le DXF
# ---------------------------------------------------------------------------


def _points_autour(ligne, decalage_m, bruit_m=0.0, pas_m=5.0, altitude=100.0):
    """Points d'altitude le long d'une ligne, décalés d'une constante."""
    import random

    alea = random.Random(0)
    longueur = ligne.length
    points = []
    s = 0.0
    while s <= longueur:
        p = ligne.interpolate(s)
        secousse = alea.uniform(-bruit_m, bruit_m) if bruit_m else 0.0
        points.append((p.x, p.y, altitude + decalage_m + secousse))
        s += pas_m
    return points


def test_terrain_du_dxf_concordant_ne_declenche_rien():
    from dp_socle.coupe import controler_terrain_embarque

    ligne = LineString([(0, 0), (0, 200)])
    profil = ProfilTerrain([0.0, 200.0], [100.0, 100.0], "RGE ALTI", 5.0)
    resultats = controler_terrain_embarque(
        profil,
        ligne,
        {"-TopoNiveau": _points_autour(ligne, -0.13, bruit_m=0.10)},
        {"-TopoNiveau": "points cotés du géomètre"},
    )
    assert len(resultats) == 1
    assert resultats[0].conforme
    assert "même terrain" in resultats[0].message


def test_decalage_de_referentiel_distingue_du_bruit():
    """Une dispersion faible autour d'une médiane non nulle n'est pas du bruit.

    Mesuré sur Sarnois : « PVcase Online Terrain » se tient 0,80 m sous le RGE
    ALTI avec une dispersion de 0,04 m — la même forme de terrain, dans un
    autre référentiel altimétrique. Le nom du calque dit probablement
    pourquoi : un modèle téléchargé, pas un relevé.
    """
    from dp_socle.coupe import controler_terrain_embarque

    ligne = LineString([(0, 0), (0, 200)])
    profil = ProfilTerrain([0.0, 200.0], [100.0, 100.0], "RGE ALTI", 5.0)

    decale = controler_terrain_embarque(
        profil, ligne, {"PVcase Online Terrain": _points_autour(ligne, -0.80, 0.04)}
    )[0]
    assert not decale.conforme
    assert decale.ecart_median_m == pytest.approx(-0.80, abs=0.05)
    assert "décalage constant" in decale.message

    bruyant = controler_terrain_embarque(
        profil, ligne, {"Relevé bruyant": _points_autour(ligne, -0.80, 1.50)}
    )[0]
    assert not bruyant.conforme
    assert "terrains différents" in bruyant.message


def test_chaque_source_du_dxf_est_jugee_separement():
    """Les fusionner masquerait leur désaccord, et c'est lui qu'on veut voir."""
    from dp_socle.coupe import controler_terrain_embarque

    ligne = LineString([(0, 0), (0, 200)])
    profil = ProfilTerrain([0.0, 200.0], [100.0, 100.0], "RGE ALTI", 5.0)
    resultats = controler_terrain_embarque(
        profil,
        ligne,
        {
            "-TopoNiveau": _points_autour(ligne, -0.13, 0.10),
            "PVcase Online Terrain": _points_autour(ligne, -0.80, 0.04),
        },
    )
    par_source = {r.source: r.conforme for r in resultats}
    assert par_source == {"-TopoNiveau": True, "PVcase Online Terrain": False}


def test_points_hors_du_couloir_ignores():
    """Comparer des points éloignés reviendrait à comparer deux endroits."""
    from dp_socle.coupe import controler_terrain_embarque

    ligne = LineString([(0, 0), (0, 200)])
    profil = ProfilTerrain([0.0, 200.0], [100.0, 100.0], "RGE ALTI", 5.0)
    loin = [(500.0, y, 130.0) for y in range(0, 200, 5)]
    assert controler_terrain_embarque(profil, ligne, {"Ailleurs": loin}) == []


def test_dxf_sans_altitude_ne_produit_aucun_controle():
    """Saint-Cyr ne porte pas de calque de terrain, et ce n'est pas une anomalie."""
    from dp_socle.coupe import controler_terrain_embarque

    plan_sans_terrain = lire_plan_be(DXF)
    assert plan_sans_terrain.points_terrain == {}
    ligne = LineString([(0, 0), (0, 200)])
    profil = ProfilTerrain([0.0, 200.0], [100.0, 100.0], "RGE ALTI", 5.0)
    assert controler_terrain_embarque(profil, ligne, {}) == []


def test_coupe_qui_manque_le_site_refusee(plan, emprise):
    """Une coupe qui ne rencontre pas le site n'est pas une coupe de ce site.

    Le cas se produit à la reprise : le dossier de sortie garde le tracé du
    projet d'avant. Rejoué sur un autre plan, il donnait une ligne à 185 km de
    là — avec un profil du terrain d'apparence parfaitement normale, relevé
    quelque part entre les deux sites, et un simple avertissement.
    """
    minx, miny, _, _ = emprise.bounds
    ailleurs = LineString(
        [(minx - 200_000, miny - 200_000), (minx - 199_900, miny - 199_800)]
    )
    with pytest.raises(ErreurCoupe) as erreur:
        corriger_ligne_coupe(ailleurs, plan.azimut_tables_deg, emprise)
    assert "ne traverse pas l'emprise clôturée" in str(erreur.value)
    assert "autre site" in str(erreur.value)


def test_reprise_d_un_trace_d_un_autre_projet_refusee(tmp_path, plan, emprise):
    """Deux projets sous le même identifiant de dossier partagent la sortie."""
    from dp_socle.coupe import coupe_enregistree, reprendre_coupe
    from dp_socle.import_be import lire_parametres

    _sortie_avec_coupe(tmp_path, emprise, plan)
    enregistree = coupe_enregistree(lire_parametres(tmp_path))

    from shapely.affinity import translate

    autre_site = translate(emprise, xoff=200_000, yoff=150_000)
    with pytest.raises(ErreurCoupe):
        reprendre_coupe(enregistree, plan.azimut_tables_deg, autre_site)


# ---------------------------------------------------------------------------
# Format du relevé altimétrique : trois colonnes, et rien d'autre
# ---------------------------------------------------------------------------


def test_fichier_a_deux_colonnes_refuse(tmp_path):
    """La forme « abscisse ; altitude » avait été écrite sans exemple à la main.

    Aucun outil du parc n'en produit, et le lecteur ne devinait le format que
    sur le nombre de colonnes. Un export « matricule ; altitude », que tout
    géomètre peut fournir, était lu comme un profil : altitudes justes, placées
    à des abscisses de 11 700 m sur une coupe de 250 m, donc toutes hors de la
    coupe et rabattues sur la première valeur. Un profil plat, crédible, faux.
    """
    fichier = tmp_path / "matricule.txt"
    fichier.write_text(
        "\n".join(f"{11_700 + i};192.{i:02d}" for i in range(0, 40, 4)),
        encoding="utf-8",
    )
    with pytest.raises(ErreurCoupe) as erreur:
        profil_terrain(
            LineString([(621_765, 6_954_200), (621_765, 6_954_450)]),
            pas_m=50.0,
            fichier_altimetrie=fichier,
        )
    assert "3 colonnes" in str(erreur.value)


def test_export_sans_altitude_refuse(tmp_path):
    """Un fichier « X Y » a deux colonnes, comme un profil en avait."""
    fichier = tmp_path / "sans_altitude.txt"
    fichier.write_text(
        "\n".join(f"621765.00;{6_954_200 + i}.00" for i in range(0, 250, 10)),
        encoding="utf-8",
    )
    with pytest.raises(ErreurCoupe):
        profil_terrain(
            LineString([(621_765, 6_954_200), (621_765, 6_954_450)]),
            pas_m=50.0,
            fichier_altimetrie=fichier,
        )


def test_troisieme_colonne_qui_n_est_pas_une_altitude_refusee(tmp_path):
    """Trois colonnes ne suffisent pas : encore faut-il que la dernière soit une cote.

    Rien dans un fichier de nombres ne dit ce que chaque colonne signifie. Le
    seul garde-fou possible est l'ordre de grandeur.
    """
    from dp_socle.coupe import ALTITUDE_MAX_PLAUSIBLE_M

    fichier = tmp_path / "xy_matricule.txt"
    fichier.write_text(
        "\n".join(
            f"621765.0;{6_954_200 + i}.0;{11_700 + i}" for i in range(0, 250, 5)
        ),
        encoding="utf-8",
    )
    with pytest.raises(ErreurCoupe) as erreur:
        profil_terrain(
            LineString([(621_765, 6_954_200), (621_765, 6_954_450)]),
            pas_m=50.0,
            fichier_altimetrie=fichier,
        )
    assert "pas une altitude" in str(erreur.value)
    assert f"{ALTITUDE_MAX_PLAUSIBLE_M:.0f}" in str(erreur.value)


def test_altitudes_metropolitaines_acceptees(tmp_path):
    """La fourchette est large : elle refuse un non-sens, pas un relevé."""
    from dp_socle.coupe import _verifier_altitudes

    # Du polder du Nord au mont Blanc.
    _verifier_altitudes([(0.0, 0.0, -4.0), (0.0, 0.0, 4_809.0)], tmp_path / "x.txt")
    with pytest.raises(ErreurCoupe):
        _verifier_altitudes([(0.0, 0.0, 6_954_200.0)], tmp_path / "x.txt")


def test_le_nuage_reel_reste_lu(tmp_path):
    """Le format de l'outil interne n'est pas affecté par ce durcissement."""
    profil = profil_terrain(COUPE_NUAGE, pas_m=25.0, fichier_altimetrie=NUAGE)
    assert len(profil.altitudes_m) > 10
    assert all(100.0 < z < 130.0 for z in profil.altitudes_m)


# ---------------------------------------------------------------------------
# Surfaces de piste
# ---------------------------------------------------------------------------


def test_surfaces_de_piste_du_jeu_de_reference(plan, tableau):
    """Saint-Cyr : 3 362 m² dessinés pour 3 365 déclarés, soit 0,1 %."""
    controle = next(
        c
        for c in controler(plan, tableau)
        if c.libelle == "Surface de voie lourde"
    )
    assert controle.statut == OK
    assert controle.valeur_dxf == pytest.approx(3362.0, abs=5.0)
    assert controle.valeur_tableau == pytest.approx(3365.0)


def test_aucune_piste_legere_ni_au_plan_ni_au_tableau(plan, tableau):
    """Un contrôle sans objet ne vaut pas mieux qu'un contrôle absent.

    Saint-Cyr ne dessine aucune piste légère et le tableau n'en déclare pas.
    """
    assert not [
        c for c in controler(plan, tableau) if c.libelle == "Surface de piste légère"
    ]


def test_piste_dessinee_hors_tolerance_avertit(plan, tableau):
    tableau_modifie = lire_tableau(TABLEAU, "IND06")
    tableau_modifie.pistes["surface_piste_lourde_m2"] = 5000.0  # +49 %
    controle = next(
        c
        for c in controler(plan, tableau_modifie)
        if c.libelle == "Surface de voie lourde"
    )
    assert controle.statut == AVERTISSEMENT
    assert not controle.bloquant


def test_recouvrement_de_pistes_compte_une_seule_fois(tmp_path):
    """La comparaison porte sur l'union des polygones, pas sur leur somme.

    Deux polygones qui se chevauchent — une aire de grutage posée sur la voie
    qu'elle élargit, par exemple — ne doivent pas compter deux fois leur partie
    commune.
    """
    import ezdxf

    from dp_socle.import_be import CATEGORIES_VOIE_LOURDE, _surface_dessinee

    document = ezdxf.new(setup=True)
    espace = document.modelspace()
    espace.add_lwpolyline(
        [(622_900, 6_750_800), (622_915, 6_750_800), (622_915, 6_750_804.6)],
        close=True,
        dxfattribs={"layer": "PVcase PV Modules (optimised)"},
    )
    for calque in ("UNI_VRD_Pistes lourdes", "UNI_VRD_Aire de grutage"):
        espace.add_lwpolyline(
            [
                (622_900, 6_750_700),
                (622_910, 6_750_700),
                (622_910, 6_750_710),
                (622_900, 6_750_710),
            ],
            close=True,
            dxfattribs={"layer": calque},
        )
    chemin = tmp_path / "recouvrement.dxf"
    document.saveas(str(chemin))

    plan_recouvert = lire_plan_be(chemin)
    # Deux carrés de 100 m² exactement superposés : 100 m², pas 200.
    assert _surface_dessinee(plan_recouvert, CATEGORIES_VOIE_LOURDE) == pytest.approx(
        100.0
    )


def test_la_coupe_par_defaut_est_perpendiculaire_et_bien_placee():
    """L'outil propose une coupe d'emblée, sans qu'on ait rien tracé.

    Le tracé du chef de projet n'apportait que l'intention : la direction vient
    de l'azimut des tables, la position du nombre de rangées traversées. Celui
    qui trouve la proposition bien placée n'a plus rien à faire.
    """
    from dp_socle.coupe import coupe_par_defaut

    # Vingt rangées est-ouest, mais aucune table entre x = 60 et x = 140 :
    # la coupe par défaut doit éviter ce couloir vide.
    rangees = [
        geom
        for index in range(20)
        for geom in (
            box(0.0, index * 10.0, 60.0, index * 10.0 + 4.0),
            box(140.0, index * 10.0, 200.0, index * 10.0 + 4.0),
        )
    ]
    emprise = box(0.0, -10.0, 200.0, 210.0)

    coupe = coupe_par_defaut(0.0, emprise, rangees)

    # Perpendiculaire aux rangées, qui courent d'est en ouest.
    assert abs(abs(coupe.azimut_coupe_deg) - 90.0) < 1e-6
    assert coupe.ecart_initial_deg == 0.0
    assert coupe.corrigee
    # Elle traverse le site sur toute sa hauteur, marge comprise.
    assert coupe.geometrie.intersects(emprise)
    assert coupe.longueur_m == pytest.approx(220.0 + 2 * 10.0, abs=0.5)
    # Et elle dit où elle s'est posée : rien de muet.
    assert coupe.avertissements
    assert "Coupe par défaut" in coupe.avertissements[0]


def test_la_coupe_par_defaut_refuse_un_plan_sans_table():
    """Sans rangée, la position ne peut pas se choisir : on le dit."""
    from dp_socle.coupe import coupe_par_defaut

    with pytest.raises(ErreurCoupe, match="Aucune table"):
        coupe_par_defaut(0.0, box(0.0, 0.0, 100.0, 100.0), [])
