"""Tests des contrôles croisés, de la ligne de coupe et du profil (lot 2bis).

Les tests qui interrogent le RGE ALTI sont marqués `reseau` : ils mesurent la
réponse réelle du service, seule chose qui dise si le point d'entrée et le
format n'ont pas changé.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import LineString, Polygon, box

from dp_socle.coupe import (
    ECART_SUSPECT_DEG,
    ProfilTerrain,
    controler_coherence,
    corriger_ligne_coupe,
    echantillonner,
    profil_terrain,
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
    assert statuts["Azimut des tables"] == OK
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
