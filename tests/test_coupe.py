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
