"""Tests de l'import HelioScope, mesurés sur les deux exports de référence.

Les valeurs attendues ne sont pas recopiées d'un brief : elles ont été mesurées
le 02/09/2026 dans les fichiers eux-mêmes, et recoupées entre elles (la surface
des modules contre celle du bloc, l'inclinaison du nom de bloc contre celle de
la géométrie 3D, la latitude déduite contre la position réelle de la commune).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import Polygon

from dp_socle.erreurs import ErreurCalage, ErreurHelioScope, ErreurModulesAbsents
from dp_socle.geometrie import charger_emprise
from dp_socle.helioscope import (
    FRACTION_ZOOM_MAX,
    FRACTION_ZOOM_MIN,
    calculer_calage,
    extraire_geometries,
    lire_dxf,
    ecrire_geojson,
    importer,
    ouvrir_export,
    parametres_json,
    prepositionner,
    projeter,
)

EXEMPLES = Path(__file__).resolve().parent.parent / "exemples"

#: Design complet : Les Islettes (55), section électrique terminée.
EXPORT_COMPLET = EXEMPLES / "les-islettes" / "HelioScope ABO_55_Les Islettes Export.zip"
EMPRISE_ISLETTES = (
    EXEMPLES / "les-islettes" / "abo_55_les-islettes-geoperso-1-02_09_2026_13_35.zip"
)
#: Second design du même projet, en pose paysage : sert à confronter les deux
#: latitudes déduites, et à couvrir le cas où le rampant est le petit côté.
EXPORT_COMPLET_2 = (
    EXEMPLES / "les-islettes" / "HelioScope ABO_55_Les Islettes Export_2.zip"
)
#: Design exporté avant la fin de la section électrique : aucun module, alors
#: que la zone, les reculs et les zones évitées sont bien là.
EXPORT_SANS_MODULES = EXEMPLES / "bray-saint-aignan" / "helioscope_export.zip"

besoin_export_complet = pytest.mark.skipif(
    not EXPORT_COMPLET.exists(), reason=f"export de référence absent : {EXPORT_COMPLET}"
)
besoin_export_complet_2 = pytest.mark.skipif(
    not EXPORT_COMPLET_2.exists(),
    reason=f"export de référence absent : {EXPORT_COMPLET_2}",
)
besoin_export_sans_modules = pytest.mark.skipif(
    not EXPORT_SANS_MODULES.exists(),
    reason=f"export de référence absent : {EXPORT_SANS_MODULES}",
)


@pytest.fixture(scope="module")
def implantation():
    return importer(EXPORT_COMPLET)


@pytest.fixture(scope="module")
def implantation_paysage():
    return importer(EXPORT_COMPLET_2)


# ---------------------------------------------------------------------------
# Ouverture de l'archive
# ---------------------------------------------------------------------------


@besoin_export_complet
def test_ouverture_archive_imbriquee():
    """Le calepinage est choisi, pas le schéma unifilaire qui est aussi un DXF."""
    export = ouvrir_export(EXPORT_COMPLET)
    assert export.identifiant_design == "7676351"
    assert Path(export.nom_dxf).name == "helioscope_design_7676351.dxf"
    assert export.image_fond is not None


def test_export_introuvable(tmp_path):
    with pytest.raises(ErreurHelioScope, match="introuvable"):
        ouvrir_export(tmp_path / "absent.zip")


# ---------------------------------------------------------------------------
# Recette de calage et test d'intégrité
# ---------------------------------------------------------------------------


@besoin_export_complet
def test_latitude_deduite_du_fichier(implantation):
    """Les Islettes (55) est à 49,11° N : la recette retrouve la commune."""
    calage = implantation.calage
    assert calage.zoom == 19
    assert calage.latitude_origine == pytest.approx(49.110690, abs=1e-6)
    assert calage.facteur_echelle == pytest.approx(
        1 / math.cos(math.radians(calage.latitude_origine)), rel=1e-12
    )


@besoin_export_complet
def test_fraction_zoom_dans_la_plage(implantation):
    assert FRACTION_ZOOM_MIN <= implantation.calage.fraction_zoom <= FRACTION_ZOOM_MAX


@pytest.mark.parametrize("facteur", [1.5, 1.3, 0.75, 1.2])
def test_integrite_refuse_une_resolution_hors_modele(facteur):
    """Une résolution qui ne colle pas au modèle sort de la plage et est refusée."""
    with pytest.raises(ErreurCalage, match="intégrité"):
        calculer_calage(0.1954518020063469 * facteur)


@pytest.mark.parametrize("facteur", [0.95, 1.05, 1.1])
def test_integrite_aveugle_aux_petits_ecarts(facteur):
    """La plage fait 0,32 de large : une erreur modérée sur `res` y reste.

    Pour le design 7676351 (fraction 0,6113), le test ne se déclenche qu'en
    dessous de -7,3 % ou au-dessus de +15,8 % sur `res`. Il garantit que le
    niveau de zoom est identifié sans ambiguïté, pas que la résolution est
    exacte : c'est le pré-positionnement sur l'ortho qui joue ce rôle-là.
    """
    calculer_calage(0.1954518020063469 * facteur)


@pytest.mark.parametrize("facteur", [0.25, 0.5, 2, 4])
def test_le_facteur_deux_est_absorbe_par_le_zoom(facteur):
    """Doubler `res` ne peut pas déclencher le test, et n'a pas à le déclencher.

    La partie fractionnaire de log2(K/res) est invariante quand `res` est
    multiplié par une puissance de 2 : le niveau de zoom absorbe exactement le
    facteur, et la latitude comme le facteur d'échelle sortent inchangés. Ce que
    le test d'intégrité garantit, ce n'est donc pas l'absence d'erreur d'un
    facteur 2 sur `res` — elle est sans effet — mais que le `floor` du niveau de
    zoom soit sans ambiguïté : rester à distance des entiers est ce qui empêche
    z de basculer d'une unité, et là, l'échelle serait bien fausse d'un facteur 2.
    """
    reference = calculer_calage(0.1954518020063469)
    decale = calculer_calage(0.1954518020063469 * facteur)
    assert decale.fraction_zoom == pytest.approx(reference.fraction_zoom, abs=1e-12)
    assert decale.latitude_origine == pytest.approx(
        reference.latitude_origine, abs=1e-12
    )
    assert decale.facteur_echelle == pytest.approx(
        reference.facteur_echelle, rel=1e-12
    )
    assert decale.zoom == reference.zoom - round(math.log2(facteur))


def test_resolution_nulle_refusee():
    with pytest.raises(ErreurCalage, match="nulle ou négative"):
        calculer_calage(0.0)


# ---------------------------------------------------------------------------
# Contrôles à l'import
# ---------------------------------------------------------------------------


@besoin_export_sans_modules
def test_export_sans_modules_refuse_avec_la_marche_a_suivre():
    """Le cas le plus fréquent et le plus piégeux : l'export prématuré."""
    with pytest.raises(ErreurModulesAbsents) as erreur:
        importer(EXPORT_SANS_MODULES)
    message = str(erreur.value)
    assert "section électrique" in message
    assert "Save & Exit" in message
    assert "réexporter" in message


@besoin_export_sans_modules
def test_export_sans_modules_porte_pourtant_ses_contours():
    """C'est ce qui rend le fichier trompeur : tout le reste est présent."""
    doc = lire_dxf(ouvrir_export(EXPORT_SANS_MODULES).dxf)
    zone, reculs, evitees, _ = extraire_geometries(doc.modelspace())
    # 24,95 ha, et non les 25,05 ha que donne un dédoublonnage naïf : l'écart
    # est précisément le sommet parasite en (0, 0) laissé par les
    # enregistrements de face du polyface mesh.
    assert zone.area / 1e4 == pytest.approx(24.953, abs=0.01)
    assert len(reculs) == 30


@besoin_export_sans_modules
def test_zones_evitees_eclatees_en_panneaux_de_mur():
    """Bray-Saint-Aignan exporte ses zones évitées en tronçons, pas en anneaux.

    29 entités polyface, dont 23 n'ont que deux sommets distincts : les prendre
    une par une pour des polygones en perdrait 23 sur 29, c'est-à-dire des
    bâtiments et des bassins absents du plan de masse. L'assemblage en rend 7 :
    cinq zones de 750 à 2 900 m², et deux petites de 18 et 3 m² qui sont peut-être
    des annexes — rien ne permet de les traiter en artefacts, elles sont donc
    gardées.
    """
    from dp_socle.helioscope import COUCHE_ZONES_EVITEES

    doc = lire_dxf(ouvrir_export(EXPORT_SANS_MODULES).dxf)
    msp = doc.modelspace()
    assert len(msp.query(f'POLYLINE[layer=="{COUCHE_ZONES_EVITEES}"]')) == 29

    _, _, evitees, avertissements = extraire_geometries(msp)
    assert len(evitees) == 7
    assert sum(p.area for p in evitees) / 1e4 == pytest.approx(1.045, abs=0.01)
    assert sum(1 for p in evitees if p.area > 500) == 5
    # Les échardes du recollement sont écartées, mais dites.
    assert any("écharde" in a for a in avertissements)


@besoin_export_sans_modules
def test_reculs_non_decoupes_par_l_assemblage():
    """Les reculs se recouvrent : les polygoniser en ferait 121 au lieu de 30."""
    doc = lire_dxf(ouvrir_export(EXPORT_SANS_MODULES).dxf)
    _, reculs, _, _ = extraire_geometries(doc.modelspace())
    assert len(reculs) == 30


# ---------------------------------------------------------------------------
# Lecture des contours
# ---------------------------------------------------------------------------


@besoin_export_complet
def test_zone_implantation_sans_sommet_parasite(implantation):
    """Les enregistrements de face du polyface mesh sont écartés.

    Les garder ajouterait un sommet en (0, 0), qui ramènerait la surface de
    0,887 ha à 0,719 ha — une erreur de 19 % passée inaperçue.
    """
    zone = implantation.zone_implantation
    assert len(zone.exterior.coords) - 1 == 8
    assert (0.0, 0.0) not in list(zone.exterior.coords)
    assert zone.area / 1e4 == pytest.approx(0.8874, abs=0.001)


@besoin_export_complet
def test_couches_de_contours(implantation):
    assert len(implantation.reculs) == 2
    assert len(implantation.zones_evitees) == 1
    assert implantation.zones_evitees[0].area == pytest.approx(275.9, abs=0.5)


# ---------------------------------------------------------------------------
# Paramètres du calepinage
# ---------------------------------------------------------------------------


@besoin_export_complet
def test_comptage_des_modules(implantation):
    calepinage = implantation.calepinage
    assert calepinage.nb_tables == 530
    assert calepinage.nb_modules_par_table == 3
    assert calepinage.nb_modules == 1590


@besoin_export_complet
def test_dimensions_et_inclinaison_du_module(implantation):
    """La longueur retenue est la longueur vraie, pas la projection au sol."""
    module = implantation.calepinage.module
    assert module.pose == "portrait"
    assert module.largeur_m == pytest.approx(1.303, abs=1e-3)
    assert module.longueur_m == pytest.approx(2.384, abs=1e-3)
    assert module.longueur_projetee_m == pytest.approx(2.1606, abs=1e-3)
    assert module.inclinaison_deg == 25.0
    assert module.inclinaison_mesuree_deg == pytest.approx(25.0, abs=1e-3)
    # La projection au sol doit bien être la longueur vraie fois le cosinus.
    assert module.longueur_projetee_m == pytest.approx(
        module.longueur_m * math.cos(math.radians(module.inclinaison_deg)), rel=1e-9
    )


@besoin_export_complet
def test_rangees_mesurees_dans_le_repere_du_calepinage(implantation):
    """Le calepinage est à 0,44° hors axe : compter les Y bruts donnerait 530."""
    calepinage = implantation.calepinage
    assert calepinage.orientation_deg == pytest.approx(-179.5559, abs=1e-4)
    assert calepinage.nb_rangees == 8
    assert calepinage.pas_rangees_m == pytest.approx(9.482, abs=0.01)
    assert calepinage.pas_tables_m == pytest.approx(1.303, abs=0.01)


def test_inclinaison_absente_du_nom_de_bloc():
    from dp_socle.helioscope import _inclinaison_du_nom

    assert _inclinaison_du_nom("module_characterization_103712_25.0deg_portrait") == 25.0
    with pytest.raises(ErreurHelioScope, match="refuse de retenir"):
        _inclinaison_du_nom("module_characterization_103712_portrait")


# ---------------------------------------------------------------------------
# Empreintes de table
# ---------------------------------------------------------------------------


@besoin_export_complet
def test_une_empreinte_par_table(implantation):
    """L'accroche au millimètre recolle les modules d'une même table.

    Sans elle, `unary_union` laissait 1 178 fragments pour 530 tables, de façon
    instable d'une exécution à l'autre.
    """
    assert len(implantation.tables) == implantation.calepinage.nb_tables
    assert {g.geom_type for g in implantation.tables} == {"Polygon"}
    module = implantation.calepinage.module
    attendue = 3 * module.largeur_m * module.longueur_projetee_m
    assert implantation.tables[0].area == pytest.approx(attendue, rel=2e-3)


# ---------------------------------------------------------------------------
# Calage et projection
# ---------------------------------------------------------------------------


@besoin_export_complet
def test_projection_refusee_avant_calage(implantation):
    from dp_socle.helioscope import Calage

    calage = Calage(
        resolution_m_px=implantation.calage.resolution_m_px,
        zoom=implantation.calage.zoom,
        fraction_zoom=implantation.calage.fraction_zoom,
        latitude_origine=implantation.calage.latitude_origine,
        facteur_echelle=implantation.calage.facteur_echelle,
    )
    with pytest.raises(ErreurCalage, match="calage est-ouest n'a pas été fait"):
        projeter(Polygon([(0, 0), (1, 0), (1, 1)]), calage)


@besoin_export_complet
def test_prepositionnement_tombe_sur_la_commune(implantation):
    """Le calage doit poser le calepinage sur Les Islettes, pas ailleurs."""
    emprise = charger_emprise(EMPRISE_ISLETTES)
    diagnostic = prepositionner(implantation, emprise.geometrie)

    assert diagnostic.longitude == pytest.approx(4.9994, abs=1e-3)
    assert diagnostic.recouvrement > 0.75
    # La latitude étant verrouillée par le fichier, l'écart nord-sud n'est pas
    # corrigé : on le mesure. Au-delà de quelques dizaines de mètres, c'est le
    # modèle de calage qu'il faudrait remettre en cause.
    assert abs(diagnostic.ecart_nord_sud_m) < 20.0
    assert diagnostic.surface_zone_ha == pytest.approx(0.887, abs=0.01)


def test_echelle_vraie_sur_le_terrain(implantation):
    """Une longueur du DXF doit se retrouver identique en distance géodésique.

    C'est le point qui compte : une erreur de facteur d'échelle produirait une
    implantation d'aspect parfaitement normal mais aux mauvaises dimensions, que
    personne ne verrait avant l'instruction du dossier.

    Le placement de la recette d'origine (`Mercator = origine + DXF * k`, avec
    k = 1/cos φ) ne passe pas ce test : mesuré le 02/09/2026, il étire de
    +1918 ppm en est-ouest et raccourcit de -976 ppm en nord-sud, parce que le
    facteur sphérique de Web Mercator ignore que les rayons de courbure N et M
    de l'ellipsoïde diffèrent. Le placement retenu tombe à 0 ppm dans les deux
    directions.
    """
    from pyproj import Geod
    from shapely.geometry import Point

    emprise = charger_emprise(EMPRISE_ISLETTES)
    prepositionner(implantation, emprise.geometrie)
    geod = Geod(ellps="WGS84")
    vers_wgs84 = Transformer.from_crs(2154, 4326, always_xy=True)

    def au_sol(a, b):
        pa = projeter(Point(*a), implantation.calage)
        pb = projeter(Point(*b), implantation.calage)
        lon1, lat1 = vers_wgs84.transform(pa.x, pa.y)
        lon2, lat2 = vers_wgs84.transform(pb.x, pb.y)
        return geod.inv(lon1, lat1, lon2, lat2)[2]

    for nom, (a, b) in {
        "est-ouest": ((0.0, 0.0), (700.0, 0.0)),
        "nord-sud": ((0.0, 0.0), (0.0, 700.0)),
        "diagonale": ((0.0, 0.0), (494.97474683058324, 494.97474683058324)),
    }.items():
        assert au_sol(a, b) == pytest.approx(math.dist(a, b), rel=1e-5), nom


@besoin_export_complet
def test_dimensions_de_table_conservees_apres_projection(implantation):
    """Le contrôle précédent, sur l'objet dessiné plutôt que sur un segment."""
    from pyproj import Geod
    from shapely.geometry import Point

    emprise = charger_emprise(EMPRISE_ISLETTES)
    prepositionner(implantation, emprise.geometrie)
    geod = Geod(ellps="WGS84")
    vers_wgs84 = Transformer.from_crs(2154, 4326, always_xy=True)

    # On compare des sommets homologues, pas des boîtes englobantes : le nord
    # de la grille Lambert 93 n'est pas le nord géographique, et la bbox d'un
    # polygone tourné n'est pas conservée.
    table = implantation.tables[0]
    projetee = projeter(table, implantation.calage)
    locaux = list(table.exterior.coords)
    projetes = list(projetee.exterior.coords)
    assert len(locaux) == len(projetes)

    for (ax, ay), (bx, by), pa, pb in zip(
        locaux[:-1], locaux[1:], projetes[:-1], projetes[1:]
    ):
        lon1, lat1 = vers_wgs84.transform(*pa)
        lon2, lat2 = vers_wgs84.transform(*pb)
        assert geod.inv(lon1, lat1, lon2, lat2)[2] == pytest.approx(
            math.dist((ax, ay), (bx, by)), abs=1e-4
        )


# ---------------------------------------------------------------------------
# Sorties
# ---------------------------------------------------------------------------


@besoin_export_complet
def test_geojson_en_lambert93(implantation, tmp_path):
    import json

    emprise = charger_emprise(EMPRISE_ISLETTES)
    prepositionner(implantation, emprise.geometrie)
    fichiers = ecrire_geojson(implantation, tmp_path)
    assert {f.stem for f in fichiers} == {
        "tables",
        "modules",
        "zone_implantation",
        "reculs",
        "zones_evitees",
    }

    tables = json.loads((tmp_path / "tables.geojson").read_text(encoding="utf-8"))
    assert tables["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::2154"
    assert len(tables["features"]) == 530
    x, y = tables["features"][0]["geometry"]["coordinates"][0][0]
    # Des mètres Lambert 93, pas des degrés : le contrôle attrape une sortie
    # laissée par mégarde en WGS84.
    assert 840_000 < x < 852_000
    assert 6_885_000 < y < 6_898_000


@besoin_export_complet
def test_parametres_serialisables(implantation):
    import json

    emprise = charger_emprise(EMPRISE_ISLETTES)
    prepositionner(implantation, emprise.geometrie)
    donnees = parametres_json(implantation)
    json.dumps(donnees)  # doit passer sans convertisseur maison
    assert donnees["design"] == "7676351"
    assert donnees["calepinage"]["nb_modules"] == 1590
    assert donnees["calage"]["longitude_origine"] == pytest.approx(4.9994, abs=1e-3)


# ---------------------------------------------------------------------------
# Réglage et persistance du calage
# ---------------------------------------------------------------------------


@besoin_export_complet
def test_decalage_est_ouest_ne_touche_pas_a_la_latitude(implantation):
    """Le seul réglage offert déplace en est-ouest, et rien d'autre."""
    from shapely.geometry import Point

    from dp_socle.helioscope import decaler_longitude

    emprise = charger_emprise(EMPRISE_ISLETTES)
    prepositionner(implantation, emprise.geometrie)
    latitude = implantation.calage.latitude_origine
    avant = projeter(Point(0.0, 0.0), implantation.calage)

    decaler_longitude(implantation.calage, 37.5)
    apres = projeter(Point(0.0, 0.0), implantation.calage)

    assert implantation.calage.latitude_origine == latitude
    vers_wgs84 = Transformer.from_crs(2154, 4326, always_xy=True)
    _, lat_avant = vers_wgs84.transform(avant.x, avant.y)
    lon_apres, lat_apres = vers_wgs84.transform(apres.x, apres.y)
    assert lat_apres == pytest.approx(lat_avant, abs=1e-9)

    from pyproj import Geod

    lon_avant, _ = vers_wgs84.transform(avant.x, avant.y)
    assert Geod(ellps="WGS84").inv(lon_avant, lat_avant, lon_apres, lat_apres)[
        2
    ] == pytest.approx(37.5, abs=0.01)

    decaler_longitude(implantation.calage, -37.5)


def test_projet_json_conserve_le_calage(tmp_path):
    """Un dossier régénéré ne doit jamais redemander le calage."""
    import geopandas as gpd
    from shapely.geometry import Polygon as ShapelyPolygon

    from dp_socle.projet import Projet

    emprise = tmp_path / "emprise.shp"
    gpd.GeoDataFrame(
        {"id": [0]},
        geometry=[ShapelyPolygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:2154",
    ).to_file(emprise)
    export = tmp_path / "export.zip"
    # Seule l'existence du fichier est vérifiée à ce stade.
    export.write_bytes(b"contenu sans importance")

    projet = Projet(
        nom="essai",
        commune="Les Islettes",
        code_postal="55120",
        date="2026-09-02",
        emprise=str(emprise),
        helioscope=str(export),
        longitude_calage=4.99935612,
    )
    chemin = projet.ecrire(tmp_path / "projet.json")
    relu = Projet.charger(chemin)
    assert relu.cale
    assert relu.longitude_calage == pytest.approx(4.99935612, abs=1e-9)


def test_longitude_hors_de_france_refusee(tmp_path):
    import geopandas as gpd
    from shapely.geometry import Polygon as ShapelyPolygon

    from dp_socle.erreurs import ErreurDP
    from dp_socle.projet import Projet

    emprise = tmp_path / "emprise.shp"
    gpd.GeoDataFrame(
        {"id": [0]},
        geometry=[ShapelyPolygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:2154",
    ).to_file(emprise)
    export = tmp_path / "export.zip"
    export.write_bytes(b"x")

    projet = Projet(
        nom="essai",
        commune="Ailleurs",
        code_postal="00000",
        date="2026-09-02",
        emprise=str(emprise),
        helioscope=str(export),
        longitude_calage=-73.5,
    )
    with pytest.raises(ErreurDP, match="hors de la France"):
        projet.valider()


# ---------------------------------------------------------------------------
# Second design du même projet
# ---------------------------------------------------------------------------


@besoin_export_complet_2
def test_pose_paysage_mesuree_sur_le_cote_montant(implantation_paysage):
    """En paysage, le rampant est le petit côté : le mesurer au plus long donne 0°.

    Même panneau que le design portrait — 1,303 × 2,384 m à 25° — mais posé à
    plat. Chercher l'inclinaison sur le côté le plus long y renvoyait 0°, ce que
    le recoupement avec le nom du bloc a fait échouer bruyamment plutôt que de
    laisser passer une coupe DP 3 fausse.
    """
    module = implantation_paysage.calepinage.module
    assert module.pose == "paysage"
    assert module.largeur_m == pytest.approx(2.384, abs=1e-3)
    assert module.longueur_m == pytest.approx(1.303, abs=1e-3)
    assert module.longueur_projetee_m == pytest.approx(1.1809, abs=1e-3)
    assert module.inclinaison_deg == 25.0
    assert module.inclinaison_mesuree_deg == pytest.approx(25.0, abs=1e-3)
    # Le panneau est physiquement le même dans les deux designs.
    assert module.dimensions_hors_tout == pytest.approx((1.303, 2.384), abs=1e-3)


@besoin_export_complet_2
def test_calepinage_du_design_paysage(implantation_paysage):
    calepinage = implantation_paysage.calepinage
    assert calepinage.nb_tables == 378
    assert calepinage.nb_modules == 1134
    assert calepinage.orientation_deg == 0
    assert calepinage.nb_rangees == 13
    assert calepinage.pas_rangees_m == pytest.approx(6.543, abs=0.01)
    assert calepinage.pas_tables_m == pytest.approx(2.384, abs=0.01)


@besoin_export_complet
@besoin_export_complet_2
def test_les_deux_designs_ne_donnent_pas_la_meme_latitude(
    implantation, implantation_paysage
):
    """Mesure de la précision réelle de la latitude déduite : environ ±10 m.

    Le brief annonçait deux designs d'un même projet concordant à 1e-6 degré.
    Mesuré le 02/09/2026 sur les deux designs des Islettes, ils diffèrent de
    9,9e-5 degré, soit 11 m nord-sud : `res` n'est pas quantifiée sur la rangée
    de tuiles, elle est calculée au point de référence de chaque design, et ces
    points diffèrent.

    Ce test fige la limite constatée plutôt que l'affirmation du brief. La
    latitude reste utilement contrainte — elle place le projet à une dizaine de
    mètres près — mais elle n'est pas exacte, et un écart nord-sud résiduel de
    cet ordre au pré-positionnement est normal, pas suspect.
    """
    ecart = abs(
        implantation.calage.latitude_origine
        - implantation_paysage.calage.latitude_origine
    )
    assert ecart > 1e-6, "les deux designs concorderaient : revoir ce constat"
    assert ecart == pytest.approx(9.94e-5, rel=0.05)
    # En mètres sur le terrain, pour que l'ordre de grandeur soit lisible.
    assert ecart * 111_320 == pytest.approx(11.0, abs=1.0)


# ---------------------------------------------------------------------------
# Rendu : azimut et couche des modules
# ---------------------------------------------------------------------------


def _azimuts(polygone) -> set[float]:
    """Azimuts des côtés, ramenés modulo 90° et arrondis.

    Modulo 90° parce qu'un rectangle a deux directions perpendiculaires et que
    seule compte leur commune orientation par rapport au repère du calepinage.
    La fusion des modules laisse des sommets alignés sur les grands côtés : on
    compare donc des directions, jamais « le plus long côté ».
    """
    sommets = list(polygone.exterior.coords)
    return {
        round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90.0, 3)
        for a, b in zip(sommets[:-1], sommets[1:])
        if math.dist(a, b) > 1e-6
    }


@besoin_export_complet
def test_azimut_unique_sur_toutes_les_tables(implantation):
    """Toutes les tables partagent exactement le même azimut.

    L'accroche appliquée avant fusion des modules déforme les contours si son
    pas est trop grossier. Au millimètre, essayé d'abord, l'azimut oscillait de
    ±0,027° et le design 7676351 sortait deux angles au lieu d'un ; au
    micromètre, la valeur est unique. Ce n'est pas cosmétique : un calepinage
    dont chaque table part de travers se lit comme un azimut mal appliqué.
    """
    attendu = round(implantation.calepinage.orientation_deg % 90.0, 3)
    angles = set()
    for table in implantation.tables:
        angles |= _azimuts(table)
    assert angles == {attendu}


@besoin_export_complet
def test_couche_des_modules(implantation):
    """Le plan de masse se dessine module par module, pas table par table."""
    calepinage = implantation.calepinage
    assert len(implantation.modules) == calepinage.nb_modules
    assert {m.geom_type for m in implantation.modules} == {"Polygon"}

    module = calepinage.module
    attendue = module.largeur_m * module.longueur_projetee_m
    for empreinte in implantation.modules[:20]:
        assert empreinte.area == pytest.approx(attendue, rel=1e-3)

    attendu = round(calepinage.orientation_deg % 90.0, 3)
    angles = set()
    for empreinte in implantation.modules:
        angles |= _azimuts(empreinte)
    assert angles == {attendu}


@besoin_export_complet_2
def test_azimut_nul_du_design_paysage(implantation_paysage):
    """Le design 2 est aligné sur l'axe : ses rangées sont exactement horizontales."""
    assert implantation_paysage.calepinage.orientation_deg == 0
    angles = set()
    for table in implantation_paysage.tables:
        angles |= _azimuts(table)
    assert angles == {0.0}


# ---------------------------------------------------------------------------
# Correction nord-sud
# ---------------------------------------------------------------------------


@besoin_export_complet
def test_correction_nord_sud_deplace_bien_vers_le_nord(implantation):
    """Une correction de N mètres déplace de N mètres, et seulement en latitude."""
    from pyproj import Geod
    from shapely.geometry import Point

    from dp_socle.helioscope import corriger_nord_sud

    emprise = charger_emprise(EMPRISE_ISLETTES)
    prepositionner(implantation, emprise.geometrie)
    corriger_nord_sud(implantation.calage, 0.0)
    avant = projeter(Point(0.0, 0.0), implantation.calage)

    corriger_nord_sud(implantation.calage, 12.5)
    apres = projeter(Point(0.0, 0.0), implantation.calage)

    vers_wgs84 = Transformer.from_crs(2154, 4326, always_xy=True)
    lon_avant, lat_avant = vers_wgs84.transform(avant.x, avant.y)
    lon_apres, lat_apres = vers_wgs84.transform(apres.x, apres.y)

    assert lat_apres > lat_avant
    assert lon_apres == pytest.approx(lon_avant, abs=1e-9)
    assert Geod(ellps="WGS84").inv(lon_avant, lat_avant, lon_apres, lat_apres)[
        2
    ] == pytest.approx(12.5, abs=0.01)

    corriger_nord_sud(implantation.calage, 0.0)


@besoin_export_complet
def test_correction_nord_sud_ne_touche_pas_a_la_latitude_du_fichier(implantation):
    """La latitude déduite reste lisible : la retouche est stockée à côté."""
    from dp_socle.helioscope import corriger_nord_sud

    emprise = charger_emprise(EMPRISE_ISLETTES)
    prepositionner(implantation, emprise.geometrie)
    du_fichier = implantation.calage.latitude_origine

    corriger_nord_sud(implantation.calage, -8.55)
    assert implantation.calage.latitude_origine == du_fichier
    assert implantation.calage.correction_nord_sud_m == pytest.approx(-8.55)
    assert implantation.calage.latitude_corrigee < du_fichier

    corriger_nord_sud(implantation.calage, 0.0)


@besoin_export_complet
def test_correction_nord_sud_annule_l_ecart_residuel(implantation):
    """Appliquer la correction annoncée par le diagnostic recale l'implantation."""
    from dp_socle.helioscope import corriger_nord_sud

    emprise = charger_emprise(EMPRISE_ISLETTES)
    corriger_nord_sud(implantation.calage, 0.0)
    avant = prepositionner(implantation, emprise.geometrie)
    assert avant.ecart_nord_sud_m == pytest.approx(8.55, abs=0.5)

    corriger_nord_sud(implantation.calage, -avant.ecart_nord_sud_m)
    apres = prepositionner(implantation, emprise.geometrie)
    assert apres.ecart_nord_sud_m == pytest.approx(0.0, abs=0.05)
    # Le recouvrement gagne ce que la latitude du fichier lui coûtait.
    assert apres.recouvrement > avant.recouvrement + 0.05

    corriger_nord_sud(implantation.calage, 0.0)


@besoin_export_complet
@pytest.mark.parametrize("metres", [31.0, -45.0, 200.0])
def test_correction_nord_sud_bornee(implantation, metres):
    """Au-delà de ±30 m, ce n'est plus une retouche mais un calage faux."""
    from dp_socle.helioscope import corriger_nord_sud

    with pytest.raises(ErreurCalage, match="hors de la plage admise"):
        corriger_nord_sud(implantation.calage, metres)


def test_projet_json_conserve_la_correction_nord_sud(tmp_path):
    import geopandas as gpd
    from shapely.geometry import Polygon as ShapelyPolygon

    from dp_socle.erreurs import ErreurDP
    from dp_socle.projet import Projet

    emprise = tmp_path / "emprise.shp"
    gpd.GeoDataFrame(
        {"id": [0]},
        geometry=[ShapelyPolygon([(0, 0), (100, 0), (100, 100), (0, 100)])],
        crs="EPSG:2154",
    ).to_file(emprise)
    export = tmp_path / "export.zip"
    export.write_bytes(b"contenu sans importance")

    projet = Projet(
        nom="essai",
        commune="Les Islettes",
        code_postal="55120",
        date="2026-09-02",
        emprise=str(emprise),
        helioscope=str(export),
        longitude_calage=4.99935612,
        correction_nord_sud_m=-8.55,
    )
    relu = Projet.charger(projet.ecrire(tmp_path / "projet.json"))
    assert relu.correction_nord_sud_m == pytest.approx(-8.55)

    projet.correction_nord_sud_m = -80.0
    with pytest.raises(ErreurDP, match="au-delà des"):
        projet.valider()

    projet.correction_nord_sud_m = -8.55
    projet.longitude_calage = None
    with pytest.raises(ErreurDP, match="sans calage est-ouest"):
        projet.valider()
