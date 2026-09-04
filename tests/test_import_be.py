"""Tests de l'import du plan du bureau d'études (lot 2bis, étapes A et B).

Les valeurs attendues ont été relevées à la main sur les deux fichiers de
référence du projet Saint-Cyr-en-Val avant toute écriture de code.
"""

from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from dp_socle.erreurs import ErreurGeoreferencement, ErreurImportBE, ErreurTableauBilan
from dp_socle.import_be import azimut_tables, categorie_proposee, lire_plan_be, normaliser
from dp_socle.tableau_bilan import indice_depuis_nom, indices_disponibles, lire_tableau

REFERENCE = Path("exemples/saint-cyr-DXF")
DXF = REFERENCE / "20260903_SCV_IND06.dxf"
TABLEAU = REFERENCE / "20260825_SCV_Tableau_Bilan_V6.xlsx"


@pytest.fixture(scope="module")
def plan():
    return lire_plan_be(DXF)


@pytest.fixture(scope="module")
def tableau():
    return lire_tableau(TABLEAU, "IND06")


# ---------------------------------------------------------------------------
# Étape A — DXF
# ---------------------------------------------------------------------------


def test_unite_deduite_des_coordonnees_et_non_de_l_entete(plan):
    """$INSUNITS annonce des millimètres, les coordonnées sont en mètres.

    Un outil qui croirait l'en-tête diviserait tout le plan par mille.
    """
    document = ezdxf.readfile(str(DXF))
    assert document.header["$INSUNITS"] == 4  # 4 = millimètres
    assert plan.unite == "mètre"
    assert plan.facteur_unite == 1.0


def test_nombre_de_tables(plan):
    assert plan.nb_tables == 96


def test_surface_cloturee(plan):
    assert plan.surface_cloturee_m2 / 10_000 == pytest.approx(4.522, abs=0.002)


def test_lineaire_de_cloture(plan):
    assert plan.lineaire_cloture_m == pytest.approx(871.9, abs=0.5)


def test_nombre_de_portails(plan):
    """Trois portails, dessinés chacun en cinq entités jointives."""
    assert len(plan.geometries("portail")) == 15
    assert plan.nb_portails == 3


def test_azimut_des_tables(plan):
    """Rangées est-ouest sur le fichier de référence."""
    assert plan.azimut_tables_deg == pytest.approx(0.0, abs=1.0)


def test_les_tables_portent_une_altitude_reelle(plan):
    tables = plan.par_categorie("tables_pv")
    assert all(entite.z_reel for entite in tables)
    assert 90.0 < min(e.z_min for e in tables) < 110.0
    # La clôture est une polyligne 2D : son Z ne porte aucune altitude et le
    # lot 4 ne doit pas le confondre avec le terrain.
    assert not plan.par_categorie("cloture")[0].z_reel


def test_les_hatch_ne_doublent_pas_les_polylignes(plan):
    """Le DXF porte 13 HATCH qui redessinent des polylignes déjà importées."""
    document = ezdxf.readfile(str(DXF))
    assert sum(1 for e in document.modelspace() if e.dxftype() == "HATCH") == 13
    assert len(plan.par_categorie("pdl_ptr")) == 3  # 3 LWPOLYLINE, 3 HATCH ignorés


def test_les_bulges_des_polylignes_sont_discretises(plan):
    """Les plateformes portent des arcs en bulge, invisibles dans les sommets.

    Sans discrétisation, la plateforme du PDL sortirait à 133,8 m² au lieu de
    131,4 : c'est le genre d'écart qui ne se voit pas sur la planche.
    """
    plateformes = sorted(
        (e.geometrie.area for e in plan.par_categorie("plateforme")), reverse=True
    )
    assert plateformes[0] == pytest.approx(131.4, abs=0.5)


def test_les_calques_vides_sont_ignores_sans_message(plan):
    assert "PVcase PV Modules (full frames)" in plan.calques_vides
    assert "PVcase PV Modules (detailed)" in plan.calques_vides
    assert plan.avertissements == []


def test_correspondance_tolerante_aux_accents_et_separateurs():
    """L'apostrophe de « aire d'aspiration » est un tiret dans le fichier BE."""
    assert normaliser("UNI_Clôture") == normaliser("UNI_Cloture")
    assert normaliser("UNI_SDIS_Aire_d-aspiration") == normaliser(
        "UNI SDIS Aire d'aspiration"
    )
    assert categorie_proposee("UNI-CLOTURE") == "cloture"
    assert categorie_proposee("uni_sdis_aire d'aspiration") == "aire_aspiration"


CALQUE_TABLES = "PVcase PV Modules (optimised)"


def _ajouter_table(espace, origine) -> None:
    """Une table est-ouest : sans elle, l'azimut n'est pas calculable."""
    x, y = origine
    espace.add_lwpolyline(
        [(x, y), (x + 15, y), (x + 15, y + 4.6), (x, y + 4.6)],
        close=True,
        dxfattribs={"layer": CALQUE_TABLES},
    )


def _dxf_minimal(chemin: Path, calque: str, origine=(622_900.0, 6_750_700.0)) -> Path:
    """DXF d'un rectangle de 10 x 4 m sur `calque`, plus une table, pour les cas d'erreur."""
    document = ezdxf.new(setup=True)
    document.layers.add(calque)
    espace = document.modelspace()
    x, y = origine
    espace.add_lwpolyline(
        [(x, y), (x + 10, y), (x + 10, y + 4), (x, y + 4)],
        close=True,
        dxfattribs={"layer": calque},
    )
    _ajouter_table(espace, (x, y + 20))
    document.saveas(str(chemin))
    return chemin


def test_dxf_hors_des_bornes_lambert_93_refuse(tmp_path):
    chemin = _dxf_minimal(
        tmp_path / "hors_bornes.dxf", "UNI_Clôture", origine=(1_200.0, 3_400.0)
    )
    with pytest.raises(ErreurGeoreferencement) as erreur:
        lire_plan_be(chemin)
    assert "Lambert 93" in str(erreur.value)


def test_calque_cloture_avec_variante_d_accentuation_reconnu(tmp_path):
    chemin = _dxf_minimal(tmp_path / "variante.dxf", "uni-cloture")
    plan_variante = lire_plan_be(chemin)
    assert plan_variante.correspondance["uni-cloture"] == "cloture"
    assert plan_variante.surface_cloturee_m2 == pytest.approx(40.0)


def test_calque_uniquement_en_hatch_signale(tmp_path):
    """Un élément qui n'existe qu'en remplissage serait perdu en silence."""
    document = ezdxf.new(setup=True)
    espace = document.modelspace()
    espace.add_lwpolyline(
        [(622_900, 6_750_700), (622_910, 6_750_700), (622_910, 6_750_704)],
        close=True,
        dxfattribs={"layer": "UNI_Clôture"},
    )
    remplissage = espace.add_hatch(dxfattribs={"layer": "UNI_VRD_Plateforme"})
    remplissage.paths.add_polyline_path(
        [(622_920, 6_750_700), (622_930, 6_750_700), (622_930, 6_750_710)], is_closed=True
    )
    _ajouter_table(espace, (622_900, 6_750_720))
    chemin = tmp_path / "hatch_seul.dxf"
    document.saveas(str(chemin))

    plan_hatch = lire_plan_be(chemin)
    messages = " ".join(plan_hatch.avertissements)
    assert "UNI_VRD_Plateforme" in messages and "HATCH" in messages
    assert plan_hatch.par_categorie("plateforme") == []


def test_sommets_dupliques_en_plan_dedoublonnes_dans_l_ordre(tmp_path):
    """Un `set()` détruirait la géométrie en perdant l'ordre du tracé."""
    document = ezdxf.new(setup=True)
    espace = document.modelspace()
    sommets = [
        (622_900, 6_750_700, 10.0),
        (622_910, 6_750_700, 11.0),
        (622_910, 6_750_700, 12.0),  # doublon en plan, extrusion 3D
        (622_910, 6_750_704, 12.0),
        (622_900, 6_750_704, 11.0),
    ]
    espace.add_polyline3d(
        sommets, close=True, dxfattribs={"layer": "PVcase PV Modules (optimised)"}
    )
    chemin = tmp_path / "doublons.dxf"
    document.saveas(str(chemin))

    plan_doublons = lire_plan_be(chemin)
    table = plan_doublons.tables[0]
    assert len(table.exterior.coords) == 5  # 4 sommets + fermeture
    assert table.area == pytest.approx(40.0)
    assert any("dupliqué" in m for m in plan_doublons.avertissements)


def test_azimut_robuste_au_repliement_a_90_degres():
    """Des rangées nord-sud ne doivent pas donner une médiane à 0°.

    Les angles voisins de ±90° tombent aux deux bouts de l'intervalle : une
    médiane naïve rendrait la direction perpendiculaire à la vraie.
    """
    from shapely.geometry import box
    from shapely.affinity import rotate

    tables = [
        rotate(box(0, 0, 15, 4.6), 90 + ecart, origin="centroid")
        for ecart in (-0.3, -0.1, 0.0, 0.1, 0.4)
    ]
    assert abs(azimut_tables(tables)) == pytest.approx(90.0, abs=0.5)


def test_calque_non_apparie_signale(tmp_path):
    chemin = _dxf_minimal(tmp_path / "inconnu.dxf", "UNI_Chose_Inconnue")
    plan_inconnu = lire_plan_be(chemin)
    assert plan_inconnu.calques_ignores == ["UNI_Chose_Inconnue"]
    assert any("non apparié" in m for m in plan_inconnu.avertissements)


def test_plan_sans_table_refuse(tmp_path):
    """Sans table, ni l'azimut ni la ligne de coupe n'ont de sens."""
    document = ezdxf.new(setup=True)
    document.modelspace().add_lwpolyline(
        [(622_900, 6_750_700), (622_910, 6_750_700), (622_910, 6_750_704)],
        close=True,
        dxfattribs={"layer": "UNI_Clôture"},
    )
    chemin = tmp_path / "sans_table.dxf"
    document.saveas(str(chemin))
    with pytest.raises(ErreurImportBE) as erreur:
        lire_plan_be(chemin)
    assert "Aucune table" in str(erreur.value)


# ---------------------------------------------------------------------------
# Étape B — tableau bilan
# ---------------------------------------------------------------------------


def test_indice_propose_depuis_le_nom_du_dxf():
    assert indice_depuis_nom("20260903_SCV_IND06.dxf") == "IND06"
    assert indice_depuis_nom("plan_sans_indice.dxf") is None


def test_indices_disponibles():
    assert indices_disponibles(TABLEAU) == ["IND05", "IND06"]


def test_indice_absent_refuse():
    with pytest.raises(ErreurTableauBilan) as erreur:
        lire_tableau(TABLEAU, "IND09")
    assert "IND05, IND06" in str(erreur.value)


def test_parametres_de_l_indice_06(tableau):
    assert tableau.generalites["phase"] == "APS"
    assert tableau.generalites["date"].isoformat() == "2026-08-25"
    assert tableau.generalites["surface_cloturee_ha"] == pytest.approx(4.52)
    assert tableau.generalites["lineaire_cloture_m"] == pytest.approx(875.0)
    assert tableau.generalites["nb_portails"] == 3
    assert tableau.structures["nb_tables"] == 96
    assert tableau.structures["inclinaison_deg"] == pytest.approx(15.0)
    assert tableau.structures["point_bas_m"] == pytest.approx(2.5)
    assert tableau.structures["point_haut_m"] == pytest.approx(4.0)
    assert tableau.modules["nb_modules"] == 4628
    assert tableau.modules["puissance_mwc"] == pytest.approx(2.93878)


def test_les_colonnes_d_indice_ne_sont_pas_confondues():
    """IND05 et IND06 diffèrent : lire la mauvaise colonne serait invisible."""
    ind05 = lire_tableau(TABLEAU, "IND05")
    assert ind05.structures["nb_tables"] == 126
    assert ind05.modules["puissance_mwc"] == pytest.approx(3.99399)


def test_azimut_avec_symbole_degre(tableau):
    """La cellule vaut la chaîne « 0° », pas le nombre 0."""
    assert tableau.structures["azimut_deg"] == pytest.approx(0.0)


def test_valeur_composite_rendue_en_couple(tableau):
    assert tableau.structures["nb_modules_longueur"] == (13, 26)
    assert tableau.structures["nb_modules_table"] == (26, 52)


def test_cotes_normalisees_avec_leur_ordre_de_lecture(tableau):
    """L'ordre des cotes change d'une section à l'autre et doit être conservé."""
    par_ouvrage = {c.ouvrage: c for c in tableau.cotes}
    ptr = par_ouvrage["Poste de transformation - PTR"]
    pdl_ptr = par_ouvrage["Poste de livraison et de transformation - PDL/PTR"]
    assert ptr.dimensions == "10 x 3 x 3m"
    assert ptr.ordre_cotes == "largeur x longueur x hauteur"
    assert pdl_ptr.dimensions == "12 x 3 x 3m"
    assert pdl_ptr.ordre_cotes == "longueur x largeur x hauteur"
    assert par_ouvrage["Aire d'aspiration"].surface_m2 == pytest.approx(32.0)
    assert par_ouvrage["Aire de charge (BESS) — Conteneurs"].dimensions == "6 x 3 x 3m"


def test_standards_du_type_de_projet(tableau):
    assert tableau.standards["Format modules"] == "G12R"
    assert tableau.standards["Inclinaison"] == 15


def test_paramètre_absent_leve_plutot_que_de_rendre_une_valeur_par_defaut(tmp_path):
    """Un tableau dont la mise en page a changé doit échouer, pas deviner."""
    import openpyxl

    classeur = openpyxl.Workbook()
    feuille = classeur.active
    feuille.title = "2. Caractéristiques du projet"
    feuille["A1"] = "Projet incomplet"
    feuille["B1"] = "IND06"
    feuille["A2"] = "Phase "
    feuille["B2"] = "APS"
    chemin = tmp_path / "incomplet.xlsx"
    classeur.save(chemin)

    with pytest.raises(ErreurTableauBilan) as erreur:
        lire_tableau(chemin, "IND06")
    assert "introuvable" in str(erreur.value)


# ---------------------------------------------------------------------------
# Références de bloc — révélées par les plans de Sarnois
# ---------------------------------------------------------------------------


class _NamespaceSansCalque:
    """Espace de noms DXF dont `layer` lève, comme celui d'un GEOMAPIMAGE."""

    @property
    def layer(self):
        raise ezdxf.DXFAttributeError(
            'Invalid DXF attribute "layer" for entity GEOMAPIMAGE'
        )


class _EntiteSansCalque:
    """Entité DXF sans attribut de calque.

    Une doublure plutôt qu'un vrai GEOMAPIMAGE : ezdxf n'offre pas de fabrique
    pour cette entité, et le plan de Sarnois qui en porte un pèse 47 Mo, trop
    lourd pour l'historique du dépôt.
    """

    def __init__(self):
        self.dxf = _NamespaceSansCalque()

    def dxftype(self):
        return "GEOMAPIMAGE"


def test_calque_absent_ne_leve_pas_d_exception_nue():
    """Toutes les entités DXF ne portent pas d'attribut de calque.

    Le plan de Sarnois contient un `GEOMAPIMAGE`, l'image géoréférencée du fond
    de plan, qui n'en a pas. Y accéder levait une `DXFAttributeError` nue,
    remontée jusqu'à l'écran en trace brute.
    """
    from dp_socle.import_be import _calque_de

    assert _calque_de(_EntiteSansCalque()) is None


def test_entites_sans_calque_ecartees_et_comptees(tmp_path):
    from dp_socle.import_be import _developper

    anomalies: dict = {}
    entites = [_EntiteSansCalque(), _EntiteSansCalque()]
    assert list(_developper(entites, None, 0, anomalies)) == []
    assert anomalies["sans_calque"] == {"GEOMAPIMAGE": 2}


def _dxf_avec_bloc(chemin: Path, calque_contenu: str, rotation: float = 0.0) -> Path:
    """DXF dont la table est une référence de bloc, comme chez le BE.

    Sur Sarnois, les 85 tables, les 4 portails et la citerne sont des `INSERT` :
    dessinés à plat, ils seraient invisibles à l'import.
    """
    document = ezdxf.new(setup=True)
    bloc = document.blocks.new("TABLE_PV")
    bloc.add_lwpolyline(
        [(0, 0), (15, 0), (15, 4.6), (0, 4.6)],
        close=True,
        dxfattribs={"layer": calque_contenu},
    )
    espace = document.modelspace()
    espace.add_blockref(
        "TABLE_PV",
        (622_900, 6_750_700),
        dxfattribs={"layer": CALQUE_TABLES, "rotation": rotation},
    )
    espace.add_lwpolyline(
        [(622_880, 6_750_680), (622_960, 6_750_680), (622_960, 6_750_760)],
        close=True,
        dxfattribs={"layer": "UNI_Clôture"},
    )
    document.saveas(str(chemin))
    return chemin


def test_table_en_reference_de_bloc_importee(tmp_path):
    chemin = _dxf_avec_bloc(tmp_path / "bloc.dxf", "PVcase PV Modules (optimised)")
    plan_bloc = lire_plan_be(chemin)
    assert plan_bloc.nb_tables == 1
    assert plan_bloc.tables[0].area == pytest.approx(69.0, abs=0.1)


def test_calque_zero_dans_un_bloc_herite_de_l_insertion(tmp_path):
    """Convention AutoCAD qu'ezdxf 1.4.4 n'applique pas de lui-même.

    Vérifié le 03/09/2026 : `virtual_entities()` rend une sous-entité déclarée
    sur « 0 » toujours sur « 0 ». Sans cette règle, tout le contenu des blocs
    dessinés sur le calque 0 tomberait dans un fourre-tout et serait perdu.
    """
    chemin = _dxf_avec_bloc(tmp_path / "herite.dxf", "0")
    plan_herite = lire_plan_be(chemin)
    assert plan_herite.nb_tables == 1
    assert plan_herite.par_categorie("tables_pv")[0].calque == CALQUE_TABLES


def test_rotation_de_la_reference_de_bloc_appliquee(tmp_path):
    """`virtual_entities()` applique la transformation de l'insertion.

    Les 85 tables de Sarnois sont posées à 245,5° : sans cette résolution,
    elles ressortiraient toutes parallèles à l'axe du dessin.
    """
    from dp_socle.import_be import azimut_tables

    droit = lire_plan_be(_dxf_avec_bloc(tmp_path / "droit.dxf", "0", rotation=0.0))
    tourne = lire_plan_be(_dxf_avec_bloc(tmp_path / "tourne.dxf", "0", rotation=24.5))
    assert azimut_tables(droit.tables) == pytest.approx(0.0, abs=0.01)
    assert azimut_tables(tourne.tables) == pytest.approx(24.5, abs=0.01)


def test_blocs_imbriques_developpes(tmp_path):
    document = ezdxf.new(setup=True)
    interieur = document.blocks.new("CONTOUR")
    interieur.add_lwpolyline(
        [(0, 0), (15, 0), (15, 4.6), (0, 4.6)], close=True, dxfattribs={"layer": "0"}
    )
    exterieur = document.blocks.new("TABLE")
    exterieur.add_blockref("CONTOUR", (0, 0), dxfattribs={"layer": "0"})
    espace = document.modelspace()
    espace.add_blockref("TABLE", (622_900, 6_750_700), dxfattribs={"layer": CALQUE_TABLES})
    espace.add_lwpolyline(
        [(622_880, 6_750_680), (622_960, 6_750_680), (622_960, 6_750_760)],
        close=True,
        dxfattribs={"layer": "UNI_Clôture"},
    )
    chemin = tmp_path / "imbrique.dxf"
    document.saveas(str(chemin))

    plan_imbrique = lire_plan_be(chemin)
    assert plan_imbrique.nb_tables == 1
    assert plan_imbrique.tables[0].area == pytest.approx(69.0, abs=0.1)


def test_cloture_ouverte_signalee(tmp_path):
    """Refermer un contour ouvert invente un segment que le BE n'a pas dessiné.

    Le drapeau `closed` du DXF ne suffit pas à trancher : sur Sarnois la
    clôture l'a à faux alors que son tracé revient sur son point de départ. Ce
    qui compte est la distance entre les deux extrémités, pas le drapeau.
    """
    document = ezdxf.new(setup=True)
    espace = document.modelspace()
    espace.add_lwpolyline(
        [
            (622_900, 6_750_700),
            (622_980, 6_750_700),
            (622_980, 6_750_780),
            (622_900, 6_750_760),
        ],
        close=False,
        dxfattribs={"layer": "UNI_Clôture"},
    )
    _ajouter_table(espace, (622_910, 6_750_710))
    chemin = tmp_path / "cloture_ouverte.dxf"
    document.saveas(str(chemin))

    plan_ouvert = lire_plan_be(chemin)
    messages = " ".join(plan_ouvert.avertissements)
    assert "contour de clôture" in messages and "ouvert" in messages
    assert "60.0 m" in messages  # écart entre les deux extrémités


def test_cloture_fermee_sans_drapeau_ne_declenche_rien(tmp_path):
    """Le cas réel de Sarnois : drapeau à faux, tracé refermé à la main."""
    document = ezdxf.new(setup=True)
    espace = document.modelspace()
    espace.add_lwpolyline(
        [
            (622_900, 6_750_700),
            (622_980, 6_750_700),
            (622_980, 6_750_780),
            (622_900, 6_750_700),
        ],
        close=False,
        dxfattribs={"layer": "UNI_Clôture"},
    )
    _ajouter_table(espace, (622_910, 6_750_710))
    chemin = tmp_path / "cloture_refermee.dxf"
    document.saveas(str(chemin))

    plan_ferme = lire_plan_be(chemin)
    assert not any("ouvert" in m for m in plan_ferme.avertissements)
    assert plan_ferme.surface_cloturee_m2 == pytest.approx(3200.0, abs=1.0)


# ---------------------------------------------------------------------------
# Tableau bilan V10 — révélé par Sarnois
# ---------------------------------------------------------------------------

TABLEAU_V10 = Path("exemples/sarnois-1-DXF/20260827_Sarnois_Tableau_Bilan_V10.xlsx")


def test_onglet_renomme_entre_les_versions_du_tableau():
    """« 2. Caractéristiques du projet » en V6, « Projet » en V10."""
    import openpyxl

    from dp_socle.tableau_bilan import ONGLETS_CARACTERISTIQUES

    v10 = openpyxl.load_workbook(TABLEAU_V10, read_only=True).sheetnames
    assert "2. Caractéristiques du projet" not in v10
    assert "Projet" in v10
    assert set(ONGLETS_CARACTERISTIQUES) >= {"2. Caractéristiques du projet", "Projet"}

    assert indices_disponibles(TABLEAU_V10) == [
        "IND06",
        "IND07",
        "IND08",
        "IND09",
        "IND10A",
        "IND10B",
    ]
    assert indices_disponibles(TABLEAU) == ["IND05", "IND06"]


def test_onglet_inconnu_refuse_en_listant_les_onglets(tmp_path):
    import openpyxl

    classeur = openpyxl.Workbook()
    classeur.active.title = "Autre chose"
    chemin = tmp_path / "inconnu.xlsx"
    classeur.save(chemin)

    with pytest.raises(ErreurTableauBilan) as erreur:
        indices_disponibles(chemin)
    assert "Autre chose" in str(erreur.value)


def test_valeur_composite_au_perluete_sommee():
    """Un projet à deux formats de table décrit son parc en deux nombres.

    « 269 & 27 » vaut 296 tables. La chaîne d'origine reste lisible à côté :
    la décomposition ne doit pas disparaître dans la somme.
    """
    tableau_v10 = lire_tableau(TABLEAU_V10, "IND09")
    assert tableau_v10.structures["nb_tables"] == 296
    assert tableau_v10.structures["nb_tables_brut"] == "269 & 27"
    assert tableau_v10.structures["nb_modules_longueur"] == (13, 26)


def test_valeur_explicitement_non_renseignee_admise_sur_le_gcr():
    """Le tableau met « / » là où le GCR n'a pas été calculé.

    Admis parce qu'aucun contrôle n'en dépend. Ailleurs, une case illisible
    reste une erreur — rendre None en silence masquerait le problème.
    """
    from dp_socle.tableau_bilan import _nombre, _nombre_ou_absent

    assert lire_tableau(TABLEAU_V10, "IND09").modules["gcr"] is None
    assert lire_tableau(TABLEAU_V10, "IND06").modules["gcr"] == pytest.approx(0.4214, abs=1e-4)
    assert _nombre_ou_absent("/", "GCR (%)") is None
    with pytest.raises(ErreurTableauBilan):
        _nombre("/", "GCR (%)")


def test_azimut_negatif_du_tableau_v10():
    """Le projet SE dont le tableau écrit « -24.5 » sans direction."""
    tableau_v10 = lire_tableau(TABLEAU_V10, "IND09")
    assert tableau_v10.structures["azimut_deg"] == pytest.approx(-24.5)
    assert tableau_v10.structures["azimut_brut"] == "-24.5"


def test_indice_a_suffixe_alphabetique_reconnu():
    """`IND10A` et `IND10B` étaient écartés de l'en-tête **sans rien dire**.

    Le motif n'acceptait qu'un nombre. Les deux colonnes de Sarnois, deux
    réductions du projet sous les 3 MWc, disparaissaient de la liste des
    indices, et l'outil laissait croire que le plan était en avance sur le
    tableau alors que les colonnes étaient là.
    """
    assert indice_depuis_nom("2026_08_025-IMP-DEV-Fixe-IND10a.dxf") == "IND10A"
    assert indice_depuis_nom("2026_08_27-IMP-DEV-Fixe-IND10b.dxf") == "IND10B"
    assert indice_depuis_nom("20260903_SCV_IND06.dxf") == "IND06"


def test_indice_ambigu_ne_rend_rien_plutot_qu_au_hasard():
    """Sans garde, « IND06final » rendrait l'indice « IND06F »."""
    assert indice_depuis_nom("truc_IND06final.dxf") is None
    assert indice_depuis_nom("plan_sans_indice.dxf") is None


def test_variantes_d_un_meme_indice_lues_separement():
    """Les deux réductions de Sarnois diffèrent, et les confondre serait invisible."""
    a = lire_tableau(TABLEAU_V10, "IND10A")
    b = lire_tableau(TABLEAU_V10, "IND10B")

    assert a.structures["nb_tables"] == 85 and a.structures["nb_tables_brut"] == "84 & 1"
    assert b.structures["nb_tables"] == 90 and b.structures["nb_tables_brut"] == "79 & 11"
    assert a.generalites["surface_cloturee_ha"] == pytest.approx(4.87)
    assert b.generalites["surface_cloturee_ha"] == pytest.approx(3.48)
    assert a.generalites["lineaire_cloture_m"] == pytest.approx(949.0)
    assert b.generalites["lineaire_cloture_m"] == pytest.approx(738.0)
    # Deux variantes calibrées pour passer sous le seuil de 3 MWc.
    for variante in (a, b):
        assert variante.modules["puissance_mwc"] == pytest.approx(2.98792)
        assert variante.generalites["nb_portails"] == 1
        assert variante.structures["azimut_deg"] == pytest.approx(-24.5)


# ---------------------------------------------------------------------------
# Charte des calques — élargie sur les plans de Sarnois
# ---------------------------------------------------------------------------


def test_ecran_de_correspondance_voit_ce_que_l_import_apparie(tmp_path):
    """Les deux lectures doivent voir les mêmes calques.

    `calques_du_dxf` ne développait pas les blocs : les tables et les portails
    de Sarnois n'apparaissaient donc pas à l'écran où l'on confirme
    l'appariement, alors que l'import les trouvait.
    """
    from dp_socle.import_be import calques_du_dxf

    chemin = _dxf_avec_bloc(tmp_path / "ecran.dxf", "PVcase PV Modules (optimised)")
    vus = {c.nom for c in calques_du_dxf(chemin)}
    apparies = set(lire_plan_be(chemin).correspondance)
    assert apparies <= vus
    assert "PVcase PV Modules (optimised)" in vus


def test_calques_ecartes_regroupes_en_une_ligne(tmp_path):
    """45 calques non appariés faisaient 71 avertissements, donc aucun lu."""
    from dp_socle.import_be import motif_ecart

    document = ezdxf.new(setup=True)
    espace = document.modelspace()
    _ajouter_table(espace, (622_900, 6_750_700))
    for calque in ("CAD_1PARCELLE", "CAD_3BATIDUR", "UNI_Legende", "UNI_Echelle"):
        espace.add_lwpolyline(
            [(622_800, 6_750_600), (622_810, 6_750_600), (622_810, 6_750_610)],
            close=True,
            dxfattribs={"layer": calque},
        )
    chemin = tmp_path / "ecartes.dxf"
    document.saveas(str(chemin))

    plan_ecarte = lire_plan_be(chemin)
    groupes = [m for m in plan_ecarte.avertissements if "calque(s) écarté(s)" in m]
    assert len(groupes) == 2  # fond cadastral, mobilier de dessin
    assert not [m for m in plan_ecarte.avertissements if "non apparié" in m]
    assert motif_ecart("CAD_1PARCELLE") == "fond cadastral du BE, remplacé par le WFS IGN"
    assert motif_ecart("UNI_Clôture") is None


def test_calque_vraiment_inconnu_garde_son_avertissement(tmp_path):
    """Écarter en groupe ne doit pas noyer ce qui demande une décision."""
    chemin = _dxf_minimal(tmp_path / "inconnu.dxf", "UNI_Chose_Inconnue")
    plan_inconnu = lire_plan_be(chemin)
    assert any(
        "UNI_Chose_Inconnue" in m and "non apparié" in m
        for m in plan_inconnu.avertissements
    )


def test_annotations_regroupees(tmp_path):
    """Textes et cotations produisaient un avertissement par calque."""
    document = ezdxf.new(setup=True)
    espace = document.modelspace()
    _ajouter_table(espace, (622_900, 6_750_700))
    for indice, calque in enumerate(("UNI_Clôture", "UNI_PDL", "UNI_VRD_Plateforme")):
        espace.add_text(
            f"étiquette {indice}", dxfattribs={"layer": calque}
        ).set_placement((622_800 + indice, 6_750_600))
    chemin = tmp_path / "annotations.dxf"
    document.saveas(str(chemin))

    plan_annote = lire_plan_be(chemin)
    groupes = [m for m in plan_annote.avertissements if "annotation(s) écartée(s)" in m]
    assert len(groupes) == 1
    assert "3 TEXT" in groupes[0]


def test_portail_d_exploitation_distinct_du_portail_d_acces():
    """Le tableau ne compte que les portails d'accès.

    Les confondre donnait 4 portails au plan contre 1 au tableau sur Sarnois,
    et faisait échouer un contrôle qui avait raison de se plaindre.
    """
    from dp_socle.import_be import CATEGORIES, categorie_proposee

    assert categorie_proposee("UNI_portail") == "portail"
    assert categorie_proposee("UNI_Portail exploitant") == "portail_exploitant"
    assert "portail_exploitant" in CATEGORIES


def test_noms_de_calque_de_sarnois_apparies():
    """La charte du BE n'est pas figée d'un projet à l'autre."""
    from dp_socle.import_be import categorie_proposee

    attendus = {
        "UNI_Cloture": "cloture",
        "UNI_Haies": "haie",
        "UNI_Haies existantes": "haie_existante",
        "UNI_Local_Stockage": "local_technique",
        "UNI_VRD_Voirie": "voirie",
        "UNI_PDT": "ptr",
        "UNI_BESS_Batterie": "bess",
        "UNI_BESS_Rétention": "bac_retention",
    }
    for calque, categorie in attendus.items():
        assert categorie_proposee(calque) == categorie, calque


def test_saint_cyr_reste_sans_avertissement(plan):
    """La charte élargie ne doit rien changer au jeu de référence."""
    assert plan.avertissements == []
    assert len(plan.correspondance) == 9


def test_categories_de_chantier_agri_et_bess():
    """Vocabulaire élargi aux objets réellement présents chez le BE."""
    from dp_socle.import_be import CATEGORIES, categorie_proposee

    attendus = {
        "UNI_VRD_Base_vie": "base_vie",
        "UNI_VRD_Stockage_Logistique": "stockage_chantier",
        "UNI_Limite paddock": "limite_paddock",
        "UNI_Bac d'équarissage": "bac_equarrissage",
        "ESPACE VERT": "espace_vert",
        "UNI_BESS_Refroidissement": "citerne_refroidissement",
        "UNI_BESS_Zone_remise": "zone_remise",
    }
    for calque, categorie in attendus.items():
        assert categorie_proposee(calque) == categorie, calque
        assert categorie in CATEGORIES


def test_zone_d_implantation_potentielle_ecartee():
    """Seule la clôture délimite le projet au dossier."""
    from dp_socle.import_be import categorie_proposee, motif_ecart

    assert categorie_proposee("UNI_ZIP") is None
    assert "clôture" in motif_ecart("UNI_ZIP")


def test_remplissage_doublon_des_plateformes_ecarte():
    """« VAL-PDL » redouble « UNI_VRD_Plateforme ».

    Mesuré sur Sarnois : ses deux boucles ont le même centre et la même aire
    que celles des plateformes, à 1 m² près (81,8 contre 82,9 m² et 94,4 contre
    95,5 m²). Les importer dessinerait chaque plateforme deux fois.
    """
    from dp_socle.import_be import motif_ecart

    assert motif_ecart("VAL-PDL") == "doublon du remplissage des plateformes"


def test_calque_ecarte_ne_produit_pas_d_avertissement_de_hatch(tmp_path):
    """Un calque écarté l'est pour toutes ses formes, remplissages compris."""
    document = ezdxf.new(setup=True)
    espace = document.modelspace()
    _ajouter_table(espace, (622_900, 6_750_700))
    remplissage = espace.add_hatch(dxfattribs={"layer": "VAL-PDL"})
    remplissage.paths.add_polyline_path(
        [(622_920, 6_750_700), (622_930, 6_750_700), (622_930, 6_750_710)],
        is_closed=True,
    )
    chemin = tmp_path / "ecarte_hatch.dxf"
    document.saveas(str(chemin))

    plan_ecarte = lire_plan_be(chemin)
    assert not any("VAL-PDL" in m and "HATCH" in m for m in plan_ecarte.avertissements)
    assert any("VAL-PDL" in m and "écarté" in m for m in plan_ecarte.avertissements)


def test_toutes_les_categories_ont_un_style_et_un_rang_de_dessin():
    """Le contrat et l'aperçu doivent rester alignés.

    Une catégorie sans style ne se verrait pas sur l'écran de validation, et
    c'est justement là qu'un appariement fautif doit sauter aux yeux.
    """
    from dp_socle.apercu_be import ORDRE_DESSIN, STYLES
    from dp_socle.import_be import CATEGORIES

    assert set(CATEGORIES) == set(STYLES)
    assert set(CATEGORIES) - {"ligne_coupe"} == set(ORDRE_DESSIN)


def test_calque_par_defaut_ecarte_mais_appariable(tmp_path):
    """Le calque 0 est le calque de travail du BE, censé être vide à l'export.

    Ce qui s'y trouve y est par oubli : sur l'indice A de Sarnois une zone de
    contention de 70 m², sur l'indice B des traits de construction. Il est donc
    écarté d'office — mais reste appariable à la main, ce qui permet de
    récupérer l'ouvrage égaré sans faire rééditer le fichier au BE.
    """
    from dp_socle.import_be import motif_ecart

    document = ezdxf.new(setup=True)
    espace = document.modelspace()
    _ajouter_table(espace, (622_900, 6_750_700))
    espace.add_lwpolyline(
        [(622_940, 6_750_700), (622_948, 6_750_700), (622_948, 6_750_710)],
        close=True,
        dxfattribs={"layer": "0"},
    )
    chemin = tmp_path / "calque_zero.dxf"
    document.saveas(str(chemin))

    assert "calque de travail" in motif_ecart("0")
    plan_ecarte = lire_plan_be(chemin)
    assert not plan_ecarte.par_categorie("zone_contention")
    assert any("0" in m and "écarté" in m for m in plan_ecarte.avertissements)

    # Rattrapage manuel, sans que le BE ait à rééditer son export.
    plan_rattrape = lire_plan_be(
        chemin,
        correspondance={CALQUE_TABLES: "tables_pv", "0": "zone_contention"},
    )
    recuperees = plan_rattrape.par_categorie("zone_contention")
    assert len(recuperees) == 1
    assert recuperees[0].geometrie.area == pytest.approx(40.0)


def test_les_trois_types_de_poste_sont_distincts():
    """PDL seul, PTR seul, PDL/PTR combiné : trois légendes au dossier.

    Le tableau bilan les compte séparément et leur donne des cotes distinctes —
    9 x 3 m pour le PDL, 10 x 3 m pour le PTR, 12 x 3 m pour le combiné. Les
    confondre dans une seule catégorie interdisait au lot 4 de les dessiner
    différemment.
    """
    from dp_socle.import_be import CATEGORIES, categorie_proposee

    assert {"pdl", "ptr", "pdl_ptr"} <= set(CATEGORIES)
    assert categorie_proposee("UNI_PDT") == "ptr"
    # Le poste de transformation de l'aire de charge BESS est un PTR.
    assert categorie_proposee("UNI_BESS_PTR") == "ptr"


def test_le_calque_pdl_porte_en_fait_un_poste_combine():
    """Le nom du calque dit « PDL », le tableau dit « PDL/PTR ».

    Sur Saint-Cyr comme sur Sarnois : 1 PDL/PTR, 0 PDL, 0 PTR. C'est le tableau
    qui tranche, pas le nom du calque — et un projet portant un PDL seul
    demandera de corriger l'appariement à l'écran.
    """
    from dp_socle.import_be import categorie_proposee

    assert categorie_proposee("UNI_PDL") == "pdl_ptr"
    tableau_scv = lire_tableau(TABLEAU, "IND06")
    assert tableau_scv.postes["nb_pdl_ptr"] == 1
    assert tableau_scv.postes["nb_pdl"] == 0
    assert tableau_scv.postes["nb_ptr"] == 0


def test_zone_de_contention_avec_les_elements_agrivoltaiques():
    from dp_socle.import_be import categorie_proposee

    assert categorie_proposee("UNI_Zone de contention") == "zone_contention"
    assert categorie_proposee("UNI_Limite paddock") == "limite_paddock"


# ---------------------------------------------------------------------------
# Exports triés du BE — livrés le 04/09/2026
# ---------------------------------------------------------------------------


def test_pistes_lourdes_et_legeres_distinguees():
    """Le BE sépare désormais ce que la légende du dossier sépare.

    Sans cette distinction, le lot 4 ne pouvait pas donner aux deux les deux
    gris de la légende de référence. Les intitulés retenus sont ceux du plan du
    BE : « voie lourde » et « piste légère ».
    """
    from dp_socle.import_be import CATEGORIES, categorie_proposee

    assert categorie_proposee("UNI_VRD_Pistes lourdes") == "piste_lourde"
    assert categorie_proposee("UNI_VRD_Pistes légères") == "piste_legere"
    assert categorie_proposee("UNI_VRD_Aire de grutage") == "aire_grutage"
    assert {"piste_lourde", "piste_legere", "aire_grutage"} <= set(CATEGORIES)


def test_arbres_existants_importes_et_non_ecartes():
    """« Arbres existant » figure à la légende du BE : c'est de la végétation
    en place, qui a sa place au dossier au même titre que les haies."""
    from dp_socle.import_be import categorie_proposee, motif_ecart

    assert categorie_proposee("PVcase Trees") == "arbre_existant"
    assert motif_ecart("PVcase Trees") is None


def test_maillage_3d_rendu_par_son_emprise_en_plan(tmp_path):
    """`ezdxf.path` refuse les maillages, et l'import échouait dessus.

    Les arbres du BE en sont. Ce qui se dessine d'un arbre sur un plan de masse
    est son houppier vu du dessus : l'enveloppe convexe des sommets le donne.
    Attention aux enregistrements de face, qui n'encodent que des indices —
    les compter comme des points donnait des houppiers de plusieurs millions
    de mètres carrés.
    """
    document = ezdxf.new(setup=True)
    espace = document.modelspace()
    _ajouter_table(espace, (622_900, 6_750_700))
    maillage = espace.add_polyface(dxfattribs={"layer": "PVcase Trees"})
    maillage.append_face(
        [
            (622_950, 6_750_700, 0),
            (622_954, 6_750_700, 0),
            (622_954, 6_750_704, 3),
            (622_950, 6_750_704, 3),
        ]
    )
    chemin = tmp_path / "arbre.dxf"
    document.saveas(str(chemin))

    plan_arbre = lire_plan_be(chemin)
    arbres = plan_arbre.par_categorie("arbre_existant")
    assert len(arbres) == 1
    assert arbres[0].geometrie.geom_type == "Polygon"
    assert arbres[0].geometrie.area == pytest.approx(16.0, abs=0.1)
