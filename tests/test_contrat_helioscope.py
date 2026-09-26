"""Tests de l'alignement du lot 2 sur le contrat de sortie du lot 2bis.

Le test qui compte ici est `test_les_trois_producteurs_ecrivent_le_meme_schema` :
c'est lui qui empêche les producteurs du contrat — le plan du BE, l'export
HelioScope, le plan PDF — de repartir chacun de leur côté. Les autres figent
les décisions prises le 03/09/2026, chacune contre une mesure.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from shapely.geometry import LineString
from shapely.ops import unary_union

from dp_socle.erreurs import ErreurHelioScope, ErreurImportBE
from dp_socle.geometrie import charger_emprise
from dp_socle.helioscope import (
    CORRESPONDANCE_CONTRAT,
    azimut_rangees,
    corriger_nord_sud,
    ecrire_sortie,
    entites_contrat,
    importer,
    ligne_coupe_helioscope,
    limites_helioscope,
    prepositionner,
    rangees,
)
from dp_socle.import_be import (
    CATEGORIES,
    CRS_PROJET,
    IMPOSSIBLE,
    NOM_GEOPACKAGE,
    ORIGINE_HELIOSCOPE,
    ORIGINE_IMPORT_BE,
    ORIGINE_PLAN_PDF,
    VERSION_CONTRAT,
    azimut_tables,
    ecrire_geopackage,
    lire_parametres,
    lire_plan_be,
)

EXEMPLES = Path(__file__).resolve().parent.parent / "exemples"

ISLETTES = EXEMPLES / "les-islettes-PDF"
EXPORT = ISLETTES / "HelioScope ABO_55_Les Islettes Export.zip"
EMPRISE = ISLETTES / "abo_55_les-islettes-geoperso-1-02_09_2026_13_35.zip"

#: Jeu de référence du lot 2bis, pour la comparaison de schéma.
DXF_BE = EXEMPLES / "saint-cyr-DXF" / "20260903_SCV_IND06.dxf"

#: Colonnes attribuaires du contrat. Elles ne dépendent pas de la provenance :
#: un schéma qui changerait selon la source obligerait le lot 4 à savoir d'où
#: vient le fichier avant de le lire.
COLONNES = {"calque", "categorie", "z_reel", "z_min", "z_max", "geometry"}

#: La ligne de coupe est une couche à part, et ses colonnes le sont aussi. Elle
#: est comparée séparément mais elle l'est : c'est celle dont les deux
#: producteurs pourraient le plus facilement diverger, puisque chacun la
#: construit depuis sa propre emprise.
COLONNES_COUPE = {
    "role",
    "corrigee",
    "azimut_tables_deg",
    "ecart_initial_deg",
    "longueur_m",
    "geometry",
}

besoin_export = pytest.mark.skipif(
    not EXPORT.exists(), reason=f"export de référence absent : {EXPORT}"
)
besoin_dxf_be = pytest.mark.skipif(
    not DXF_BE.exists(), reason=f"DXF de référence absent : {DXF_BE}"
)


@pytest.fixture(scope="module")
def implantation():
    """Implantation des Islettes, calée comme au terme de la validation."""
    emprise = charger_emprise(EMPRISE)
    resultat = importer(EXPORT)
    diagnostic = prepositionner(resultat, emprise.geometrie)
    corriger_nord_sud(resultat.calage, -diagnostic.ecart_nord_sud_m)
    return resultat


@pytest.fixture(scope="module")
def emprise_cadastrale():
    return charger_emprise(EMPRISE).geometrie


@pytest.fixture(scope="module")
def sortie_lot2(tmp_path_factory, implantation, emprise_cadastrale):
    dossier = tmp_path_factory.mktemp("lot2")
    gpkg, params, controles = ecrire_sortie(
        implantation, dossier, emprise_cadastrale=emprise_cadastrale
    )
    return dossier, gpkg, params, controles


def _implantation_pour_schema():
    """Implantation calée, indépendante de la fixture de module."""
    emprise = charger_emprise(EMPRISE)
    resultat = importer(EXPORT)
    diagnostic = prepositionner(resultat, emprise.geometrie)
    corriger_nord_sud(resultat.calage, -diagnostic.ecart_nord_sud_m)
    return resultat


def _schema(chemin: Path) -> dict[str, set[str]]:
    """Couches du GeoPackage et colonnes de chacune, CRS vérifié au passage.

    Par pyogrio, comme `contrat._lire_couches` : fiona n'est pas déclarée, et
    ces deux tests-ci sont ce qui restait d'elle après le 26/09/2026 — ils
    passaient sur le poste, où elle est installée, et tombaient en intégration
    continue, où elle ne l'est pas.
    """
    import geopandas as gpd
    from pyogrio import list_layers

    schema = {}
    for couche, _type_geometrique in list_layers(chemin):
        gdf = gpd.read_file(chemin, layer=couche)
        assert gdf.crs is not None, f"couche « {couche} » sans CRS"
        assert gdf.crs.to_string() == CRS_PROJET, (
            f"couche « {couche} » en {gdf.crs.to_string()} au lieu de {CRS_PROJET}"
        )
        schema[couche] = set(gdf.columns)
    return schema


# ---------------------------------------------------------------------------
# Le garde-fou : les trois producteurs écrivent le même schéma
# ---------------------------------------------------------------------------

#: Troisième producteur, depuis le 23/09/2026 : le plan PDF de Gannay calé sur
#: son export HelioScope (lot 2ter).
besoin_plan_pdf = pytest.mark.skipif(
    not (EXEMPLES / "gannay-PDF" / "Annexe5_CasXCas_PlanProjet_2026-09-21.pdf").exists(),
    reason="plan PDF de Gannay absent",
)

#: Clés du `projet.json` que le lot 2bis écrit toujours, et que les deux autres
#: producteurs doivent donc écrire aussi : le lot 4 les lit sans savoir d'où
#: vient le fichier. Chacun peut en ajouter — le calage pour le lot 2, le calage
#: du plan pour le lot 2ter —, aucun ne peut en retirer.
CLES_PARAMETRES = {
    "version_contrat",
    "origine",
    "sources",
    "projet",
    "plan",
    "parametres",
    "cotes_normalisees",
    "standards_unite",
    "controles",
    "seuil_puissance_dp_mwc",
    "avertissements_tableau",
}
CLES_PLAN = {
    "unite_dxf",
    "azimut_tables_deg",
    "nb_tables",
    "nb_portails",
    "surface_cloturee_m2",
    "lineaire_cloture_m",
    "surface_tables_m2",
    "correspondance_calques",
    "calques_ignores",
    "avertissements",
}


def _sortie_plan_pdf(dossier: Path):
    """Le plan de Gannay, calé et écrit par le lot 2ter, coupe comprise."""
    from dp_socle.coupe import coupe_par_defaut
    from dp_socle.plan_pdf import ChoixDuPlan, importer_plan_pdf
    from tests.jeux_plan_pdf import (
        EXPORT_GANNAY,
        LONGITUDE_GANNAY,
        NORD_SUD_GANNAY_M,
        PLAN_GANNAY,
    )

    dossier.mkdir(parents=True, exist_ok=True)
    resultat = importer_plan_pdf(
        PLAN_GANNAY,
        EXPORT_GANNAY,
        longitude_origine=LONGITUDE_GANNAY,
        correction_nord_sud_m=NORD_SUD_GANNAY_M,
        choix=ChoixDuPlan(volume_citerne_m3=120, largeur_portail_m=7.0),
    )
    plan = resultat.plan
    resultat.ligne_coupe = coupe_par_defaut(
        plan.azimut_tables_deg, plan.polygone_cloture, plan.tables
    )
    return resultat.ecrire(dossier / "sortie")


@besoin_export
@besoin_dxf_be
@besoin_plan_pdf
def test_les_trois_producteurs_ecrivent_le_meme_schema(sortie_lot2, tmp_path):
    """Un GeoPackage du lot 2, du lot 2bis et du lot 2ter se lisent pareil.

    C'est ce test qui empêche les formats de diverger : toute couche nouvelle,
    toute colonne renommée d'un côté et pas des autres le fait échouer. Les
    couches ne sont pas les mêmes — chaque source apporte ce qu'elle a — mais
    elles viennent toutes du contrat, et leurs colonnes sont identiques. Le
    `projet.json` est comparé de même, sur les clés que le lot 4 peut lire.

    Deux producteurs jusqu'au 23/09/2026, trois depuis le plan PDF (lot 2ter,
    décision D6 de son brief).
    """
    from dp_socle.coupe import corriger_ligne_coupe
    from dp_socle.import_be import parametres_json
    from dp_socle.tableau_bilan import lire_tableau

    dossier_lot2, _, _, _ = sortie_lot2
    implantation_lot2 = _implantation_pour_schema()
    emprise = charger_emprise(EMPRISE).geometrie

    # Les deux sorties portent une ligne de coupe : c'est la couche dont les
    # deux producteurs pourraient le plus facilement diverger, chacun la
    # construisant depuis sa propre emprise.
    centre = unary_union(rangees(implantation_lot2)).centroid
    coupe_lot2 = ligne_coupe_helioscope(
        implantation_lot2,
        LineString([(centre.x - 40, centre.y - 60), (centre.x + 25, centre.y + 55)]),
        emprise,
    )
    gpkg_lot2 = ecrire_geopackage(
        entites_contrat(implantation_lot2),
        tmp_path / "lot2",
        ligne_coupe=coupe_lot2,
    )

    plan = lire_plan_be(DXF_BE)
    centre_be = plan.polygone_cloture.centroid
    coupe_lot2bis = corriger_ligne_coupe(
        LineString(
            [
                (centre_be.x - 30, centre_be.y - 40),
                (centre_be.x + 20, centre_be.y + 35),
            ]
        ),
        azimut_tables(plan.tables),
        plan.polygone_cloture,
    )
    gpkg_lot2bis = ecrire_geopackage(
        plan, tmp_path / "lot2bis", ligne_coupe=coupe_lot2bis
    )

    gpkg_lot2ter, json_lot2ter = _sortie_plan_pdf(tmp_path / "lot2ter")

    schemas = {
        "lot 2": _schema(gpkg_lot2),
        "lot 2bis": _schema(gpkg_lot2bis),
        "lot 2ter": _schema(gpkg_lot2ter),
    }

    connues = set(CATEGORIES) | {"ligne_coupe"}
    for etiquette, schema in schemas.items():
        hors = sorted(set(schema) - connues)
        assert not hors, f"couches hors contrat côté {etiquette} : {hors}"
        assert "tables_pv" in schema, etiquette
        assert "ligne_coupe" in schema, etiquette
        for nom, colonnes in schema.items():
            attendu = COLONNES_COUPE if nom == "ligne_coupe" else COLONNES
            assert colonnes == attendu, (
                f"couche « {nom} » côté {etiquette} : colonnes {sorted(colonnes)}"
            )

    # Et les couches communes se lisent pareil des trois côtés.
    for couche in ("tables_pv", "ligne_coupe"):
        assert len({frozenset(s[couche]) for s in schemas.values()}) == 1, couche
    # Le lot 2ter porte ce que le lot 2 ne pouvait pas donner : le reste du plan.
    assert {"cloture", "portail", "pdl_ptr"} <= set(schemas["lot 2ter"])

    # Le `projet.json`, sur les clés que le lot 4 peut lire.
    parametres = {
        "lot 2": json.loads((dossier_lot2 / "projet.json").read_text(encoding="utf-8")),
        "lot 2bis": parametres_json(
            plan,
            lire_tableau(EXEMPLES / "saint-cyr-DXF" / "20260825_SCV_Tableau_Bilan_V6.xlsx", "IND06"),
            [],
        ),
        "lot 2ter": json.loads(json_lot2ter.read_text(encoding="utf-8")),
    }
    for etiquette, donnees in parametres.items():
        manquantes = sorted(CLES_PARAMETRES - set(donnees))
        assert not manquantes, f"projet.json côté {etiquette} : il manque {manquantes}"
        manquantes = sorted(CLES_PLAN - set(donnees["plan"]))
        assert not manquantes, f"« plan » côté {etiquette} : il manque {manquantes}"
        assert donnees["version_contrat"] == VERSION_CONTRAT, etiquette


@besoin_export
def test_couches_ecrites_par_le_lot_2(sortie_lot2):
    from pyogrio import list_layers

    _, gpkg, _, _ = sortie_lot2
    assert {couche for couche, _type in list_layers(gpkg)} == {
        "tables_pv",
        "modules_pv",
        "zone_implantation_pv",
        "recul_implantation",
        "zone_evitee",
    }


@besoin_export
def test_les_deux_fichiers_du_contrat_sont_ecrits(sortie_lot2):
    dossier, gpkg, params, _ = sortie_lot2
    assert gpkg == dossier / NOM_GEOPACKAGE
    assert params == dossier / "projet.json"
    assert gpkg.exists() and params.exists()


# ---------------------------------------------------------------------------
# L'orientation : le piège du brief
# ---------------------------------------------------------------------------


@besoin_export
def test_les_rangees_et_non_les_tables_brutes_alimentent_tables_pv(implantation):
    """Sur les tables brutes, `azimut_tables()` se trompe de 90°.

    Une « table » HelioScope est une colonne de 3 modules dont le grand côté est
    en travers de la rangée. Brancher la ligne de coupe dessus donnerait une
    coupe parallèle aux rangées au lieu de perpendiculaire, sans anomalie
    visible sur la planche.
    """
    from dp_socle.helioscope import geometries_l93

    brutes = geometries_l93(implantation)["tables"]
    lignes = rangees(implantation)

    assert azimut_tables(brutes) == pytest.approx(-88.105, abs=0.01)
    assert azimut_tables(lignes) == pytest.approx(1.895, abs=0.01)
    # 90° d'écart exactement : c'est bien la même direction, lue sur l'autre côté.
    ecart = abs(((azimut_tables(brutes) - azimut_tables(lignes)) + 90) % 180 - 90)
    assert ecart == pytest.approx(90.0, abs=0.01) or ecart == pytest.approx(
        0.0, abs=0.01
    )

    entites = entites_contrat(implantation)
    tables_pv = [e.geometrie for e in entites if e.categorie == "tables_pv"]
    assert len(tables_pv) == len(lignes) == implantation.calepinage.nb_rangees
    assert azimut_tables(tables_pv) == pytest.approx(1.895, abs=0.01)


@pytest.fixture(scope="module")
def implantation_gannay():
    """Le design 10465241 de Gannay-sur-Loire, où rien ne se touche."""
    from tests.jeux_plan_pdf import EXPORT_GANNAY

    return importer(EXPORT_GANNAY)


@pytest.mark.skipif(
    not (EXEMPLES / "gannay-PDF" / "helioscope_design_10465241.dxf").exists(),
    reason="DXF de Gannay absent",
)
def test_des_tables_qui_ne_se_touchent_pas_forment_quand_meme_des_rangees(
    implantation_gannay,
):
    """Tables espacées de 0,49 m, modules séparés de 1,2 cm : l'union ne suffit pas.

    Mesuré le 23/09/2026 : l'union des tables contiguës rendait 4 752
    « rangées » — les modules eux-mêmes —, dont le grand côté est nord-sud, et
    l'azimut sortait à 90° au lieu de 0°. La coupe A-A' se serait posée
    parallèle aux rangées, sans rien de visible sur la planche.
    """
    from dp_socle.helioscope import grouper_en_rangees, rangees_locales

    union_seule = grouper_en_rangees(implantation_gannay.tables)
    assert len(union_seule) == implantation_gannay.calepinage.nb_modules == 4752
    assert azimut_tables(union_seule) == pytest.approx(90.0, abs=0.01)

    lignes, jeu = rangees_locales(implantation_gannay)
    assert len(lignes) == implantation_gannay.calepinage.nb_rangees == 16
    assert jeu == pytest.approx(0.50, abs=0.02)
    assert azimut_tables(lignes) == pytest.approx(0.0, abs=0.01)
    # Chaque rangée est d'un seul tenant, et ne déborde pas de ses tables de
    # plus que les jeux qu'elle referme.
    surface_tables = sum(t.area for t in implantation_gannay.tables)
    surface_rangees = sum(l.area for l in lignes)
    assert 1.0 < surface_rangees / surface_tables < 1.10


@besoin_export
def test_l_ecart_a_orientation_deg_est_la_convergence_des_meridiens(implantation):
    """`orientation_deg` se rapporte au nord géographique, pas à celui de la grille.

    Le brief donnait cet écart de 1,45° comme inexpliqué. Il vaut exactement la
    convergence des méridiens du Lambert 93 au droit du site : c'est ce qui
    interdit d'utiliser `orientation_deg` pour orienter une coupe tracée en L93.
    """
    import pyproj

    azimut = azimut_rangees(implantation)
    orientation = (implantation.calepinage.orientation_deg + 90.0) % 180.0 - 90.0

    centre = unary_union(rangees(implantation)).centroid
    lon, lat = pyproj.Transformer.from_crs(2154, 4326, always_xy=True).transform(
        centre.x, centre.y
    )
    convergence = pyproj.Proj(2154).get_factors(lon, lat).meridian_convergence

    assert convergence == pytest.approx(1.4507, abs=1e-3)
    assert azimut - orientation == pytest.approx(convergence, abs=1e-3)


@besoin_export
def test_ligne_de_coupe_perpendiculaire_aux_rangees(
    implantation, emprise_cadastrale
):
    """Mesuré sur la géométrie rendue, pas sur la valeur déclarée."""
    azimut = azimut_rangees(implantation)
    centre = unary_union(rangees(implantation)).centroid
    # Tracé volontairement de travers : la correction doit le redresser.
    trace = LineString(
        [(centre.x - 40, centre.y - 60), (centre.x + 25, centre.y + 55)]
    )
    ligne = ligne_coupe_helioscope(implantation, trace, emprise_cadastrale)

    (x1, y1), (x2, y2) = ligne.geometrie.coords[0][:2], ligne.geometrie.coords[-1][:2]
    mesure = math.degrees(math.atan2(y2 - y1, x2 - x1))
    ecart = abs(((mesure - azimut - 90.0) + 90.0) % 180.0 - 90.0)
    assert ecart < 1.0
    assert mesure == pytest.approx(91.895, abs=0.01)
    assert ligne.corrigee


@besoin_export
def test_coupe_refusee_sans_emprise_cadastrale(implantation):
    """La coupe du lot 2 s'étend sur le cadastre, faute de clôture.

    La zone HelioScope n'est pas un candidat : tracée à main levée, elle ne suit
    pas le parcellaire.
    """
    trace = LineString([(846000, 6891900), (846050, 6891950)])
    with pytest.raises(ErreurHelioScope, match="[Ee]mprise cadastrale absente"):
        ligne_coupe_helioscope(implantation, trace, None)


# ---------------------------------------------------------------------------
# Ce que le lot 2 ne peut pas fournir
# ---------------------------------------------------------------------------


@besoin_export
def test_les_controles_impossibles_ne_passent_pas_pour_reussis(sortie_lot2):
    """Une source unique ne se recoupe pas avec elle-même."""
    _, _, _, controles = sortie_lot2
    impossibles = [c for c in controles if c.statut == IMPOSSIBLE]
    assert len(impossibles) == 3
    libelles = " ".join(c.libelle for c in impossibles)
    assert "tableau bilan" in libelles
    assert "altimétrique" in libelles
    assert "clôture" in libelles
    for controle in impossibles:
        assert controle.statut != "ok"
        assert not controle.bloquant


@besoin_export
def test_debordement_hors_emprise_reste_calculable(implantation, emprise_cadastrale):
    """Le seul recoupement qui survit : le calepinage contre le parcellaire."""
    controles = limites_helioscope(implantation, emprise_cadastrale)
    emprise_absente = limites_helioscope(implantation, None)

    debordement = [c for c in controles if "emprise cadastrale" in c.libelle]
    assert len(debordement) == 1
    assert debordement[0].statut == "ok"

    sans = [c for c in emprise_absente if "emprise cadastrale" in c.libelle]
    assert sans[0].statut == "avertissement"


@besoin_export
def test_aucune_altitude_dans_le_geopackage(sortie_lot2):
    """Le DXF HelioScope est plat : les colonnes Z restent nulles, pas absentes."""
    import geopandas as gpd

    _, gpkg, _, _ = sortie_lot2
    gdf = gpd.read_file(gpkg, layer="tables_pv")
    assert set(gdf["z_reel"]) == {False}
    assert gdf["z_min"].isna().all()
    assert gdf["z_max"].isna().all()


# ---------------------------------------------------------------------------
# `projet.json` de sortie
# ---------------------------------------------------------------------------


@besoin_export
def test_parametres_relus_par_le_lecteur_du_lot_2bis(sortie_lot2, implantation):
    dossier, _, _, _ = sortie_lot2
    donnees = lire_parametres(dossier)
    assert donnees is not None
    assert donnees["origine"] == ORIGINE_HELIOSCOPE
    assert donnees["version_contrat"] == VERSION_CONTRAT
    assert donnees["plan"]["azimut_tables_deg"] == pytest.approx(1.895, abs=0.01)
    assert donnees["plan"]["nb_tables"] == implantation.calepinage.nb_rangees
    # Les valeurs que HelioScope ne donne pas restent nulles et nommées.
    assert donnees["plan"]["surface_cloturee_m2"] is None
    assert donnees["plan"]["lineaire_cloture_m"] is None
    assert donnees["sources"]["tableau_bilan"] is None
    # Et la clé de cohérence altimétrique est absente plutôt que remplie de nulls.
    assert "coherence_altimetrique" not in donnees


@besoin_export
def test_le_projet_json_du_lot_1_reste_refuse(tmp_path):
    """Les deux fichiers portent le même nom ; l'origine les distingue."""
    (tmp_path / "projet.json").write_text(
        json.dumps({"nom": "essai", "commune": "Les Islettes"}), encoding="utf-8"
    )
    with pytest.raises(ErreurImportBE, match="n'est pas une sortie du contrat"):
        lire_parametres(tmp_path)


def test_origine_inconnue_refusee(tmp_path):
    (tmp_path / "projet.json").write_text(
        json.dumps({"origine": "pvcase", "version_contrat": VERSION_CONTRAT}),
        encoding="utf-8",
    )
    with pytest.raises(ErreurImportBE, match="pvcase"):
        lire_parametres(tmp_path)


def test_les_trois_origines_du_contrat_sont_reconnues(tmp_path):
    for origine in (ORIGINE_IMPORT_BE, ORIGINE_HELIOSCOPE, ORIGINE_PLAN_PDF):
        dossier = tmp_path / origine
        dossier.mkdir()
        (dossier / "projet.json").write_text(
            json.dumps({"origine": origine, "version_contrat": VERSION_CONTRAT}),
            encoding="utf-8",
        )
        assert lire_parametres(dossier)["origine"] == origine


# ---------------------------------------------------------------------------
# Correspondance des couches
# ---------------------------------------------------------------------------


def test_toute_categorie_de_la_correspondance_est_au_contrat():
    """Une catégorie hors `CATEGORIES` ne serait jamais écrite, en silence."""
    assert set(CORRESPONDANCE_CONTRAT) <= set(CATEGORIES)


def test_la_zone_helioscope_n_est_pas_appariee_a_la_cloture():
    """Le piège à ne pas tomber dedans : la surface clôturée en dépendrait.

    La zone d'implantation HelioScope est tracée à main levée et ne suit pas le
    parcellaire — 25,05 ha contre 27,99 ha pour le cadastre sur
    Bray-Saint-Aignan. L'apparier à `cloture` donnerait une surface clôturée et
    un linéaire de clôture faux dans le dossier déposé.
    """
    assert "cloture" not in CORRESPONDANCE_CONTRAT
    assert "portail" not in CORRESPONDANCE_CONTRAT
    assert CORRESPONDANCE_CONTRAT["zone_implantation_pv"] == "Field_Segments"


def test_toute_categorie_dessinable_a_un_style_et_une_place():
    """Une catégorie sans style ferait planter l'aperçu ; sans place, elle
    disparaîtrait du dessin sans erreur visible."""
    from dp_socle.apercu_be import ORDRE_DESSIN, STYLES

    for categorie in CATEGORIES:
        assert categorie in STYLES, categorie
        if categorie != "ligne_coupe":
            assert categorie in ORDRE_DESSIN, categorie
