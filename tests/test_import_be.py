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
