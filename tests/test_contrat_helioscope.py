"""Tests de l'alignement du lot 2 sur le contrat de sortie du lot 2bis.

Le test qui compte ici est `test_les_deux_lots_ecrivent_le_meme_schema` : c'est
lui qui empêche les deux producteurs de repartir chacun de leur côté. Les
autres figent les décisions prises le 03/09/2026, chacune contre une mesure.
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
    """Couches du GeoPackage et colonnes de chacune, CRS vérifié au passage."""
    import fiona
    import geopandas as gpd

    schema = {}
    for couche in fiona.listlayers(chemin):
        gdf = gpd.read_file(chemin, layer=couche)
        assert gdf.crs is not None, f"couche « {couche} » sans CRS"
        assert gdf.crs.to_string() == CRS_PROJET, (
            f"couche « {couche} » en {gdf.crs.to_string()} au lieu de {CRS_PROJET}"
        )
        schema[couche] = set(gdf.columns)
    return schema


# ---------------------------------------------------------------------------
# Le garde-fou : les deux lots écrivent le même schéma
# ---------------------------------------------------------------------------


@besoin_export
@besoin_dxf_be
def test_les_deux_lots_ecrivent_le_meme_schema(sortie_lot2, tmp_path):
    """Un GeoPackage du lot 2 et un du lot 2bis se lisent de la même façon.

    C'est ce test qui empêche les deux formats de diverger : toute couche
    nouvelle, toute colonne renommée d'un côté et pas de l'autre le fait échouer.
    Les couches ne sont pas les mêmes — chaque source apporte ce qu'elle a — mais
    elles viennent toutes du contrat, et leurs colonnes sont identiques.
    """
    from dp_socle.coupe import corriger_ligne_coupe

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

    schema_lot2 = _schema(gpkg_lot2)
    schema_lot2bis = _schema(gpkg_lot2bis)

    connues = set(CATEGORIES) | {"ligne_coupe"}
    for etiquette, schema in (("lot 2", schema_lot2), ("lot 2bis", schema_lot2bis)):
        hors = sorted(set(schema) - connues)
        assert not hors, f"couches hors contrat côté {etiquette} : {hors}"
        assert "tables_pv" in schema, etiquette
        assert "ligne_coupe" in schema, etiquette

    for nom, colonnes in {**schema_lot2bis, **schema_lot2}.items():
        attendu = COLONNES_COUPE if nom == "ligne_coupe" else COLONNES
        assert colonnes == attendu, f"couche « {nom} » : colonnes {sorted(colonnes)}"

    # Et la couche commune se lit pareil des deux côtés.
    assert schema_lot2["tables_pv"] == schema_lot2bis["tables_pv"]
    assert schema_lot2["ligne_coupe"] == schema_lot2bis["ligne_coupe"]


@besoin_export
def test_couches_ecrites_par_le_lot_2(sortie_lot2):
    import fiona

    _, gpkg, _, _ = sortie_lot2
    assert set(fiona.listlayers(gpkg)) == {
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


def test_les_deux_origines_du_contrat_sont_reconnues(tmp_path):
    for origine in (ORIGINE_IMPORT_BE, ORIGINE_HELIOSCOPE):
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
