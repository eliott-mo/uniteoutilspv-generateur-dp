"""Trame des modules à l'intérieur des tables.

Le plan du bureau d'études ne descend pas au module : la trame se reconstruit
depuis le tableau bilan et la géométrie des tables. Ce qui est mesuré ici, c'est
qu'elle retombe sur les formats déclarés — et qu'elle refuse de se dessiner
quand elle n'y retombe pas, plutôt que de diviser une rangée en dix-sept
modules là où il y en a treize.
"""

from __future__ import annotations

import math

import pytest
from shapely.geometry import Polygon

from dp_socle.contrat import charger_contrat
from dp_socle.planches.modules import (
    LARGEUR_MODULE_MAX_M,
    LARGEUR_MODULE_MIN_M,
    controler_trame,
    diviser_table,
    rectangle_oriente,
    trame_du_projet,
)

from . import contrat_synthetique as synthese

#: Un module G12R, le format courant des projets UNITe.
LONGUEUR_G12R_M = 2.384
LARGEUR_G12R_M = 1.134


def _table(longueur_m: float, largeur_m: float, angle_deg: float = 20.0) -> Polygon:
    """Table rectangulaire quelconque, tournée : rien n'est parallèle aux axes."""
    angle = math.radians(angle_deg)
    x0, y0 = synthese.ORIGINE_L93
    coins = []
    for long, trav in (
        (0.0, 0.0), (longueur_m, 0.0), (longueur_m, largeur_m), (0.0, largeur_m)
    ):
        coins.append(
            (
                x0 + long * math.cos(angle) - trav * math.sin(angle),
                y0 + long * math.sin(angle) + trav * math.cos(angle),
            )
        )
    return Polygon(coins)


# ---------------------------------------------------------------------------
# Le repère d'une table
# ---------------------------------------------------------------------------


def test_le_repere_dune_table_retrouve_ses_deux_cotes():
    """La trame se pose sur une table tournée comme sur une table droite."""
    repere = rectangle_oriente(_table(15.0, 4.6, angle_deg=37.0))
    assert repere is not None
    _, _, _, longueur, largeur = repere
    assert longueur == pytest.approx(15.0, abs=0.01)
    assert largeur == pytest.approx(4.6, abs=0.01)


def test_le_grand_cote_est_toujours_la_longueur():
    repere = rectangle_oriente(_table(4.6, 15.0))
    _, _, _, longueur, largeur = repere
    assert longueur > largeur


# ---------------------------------------------------------------------------
# La largeur du module se mesure sur le plan, pas sur les hauteurs déclarées
# ---------------------------------------------------------------------------


def test_la_largeur_du_module_vient_des_tables_dessinees(tmp_path):
    """Mesuré sur Saint-Cyr : les hauteurs déclarées faussent le calcul.

    2,50 et 4,00 m à 15° donnent un rampant de 5,80 m, donc un module de
    0,93 m de large. La largeur des tables dessinées, elle, donne 4,78 m de
    rampant et un module de 1,13 m — un G12R, que le tableau nomme par
    ailleurs. Ce sont les hauteurs qui sont des bornes d'enveloppe.
    """
    synthese.ecrire(tmp_path, inclinaison_deg=15.0, point_bas_m=2.5, point_haut_m=4.0)
    contrat = charger_contrat(tmp_path)
    contrat.donnees["parametres"]["modules"]["surface_unitaire_m2"] = (
        LONGUEUR_G12R_M * LARGEUR_G12R_M
    )
    # Deux modules sur le rampant, incliné à 15° : la table mesure au sol
    # 2 x 2,384 x cos(15°) = 4,606 m de large.
    largeur_table = 2 * LONGUEUR_G12R_M * math.cos(math.radians(15.0))
    tables = [_table(15.0, largeur_table)]

    rampant_declare = (4.0 - 2.5) / math.sin(math.radians(15.0))
    trame, raison = trame_du_projet(contrat, tables, rampant_declare)
    assert trame is not None, raison
    assert trame.largeur_module_m == pytest.approx(LARGEUR_G12R_M, abs=0.02)
    assert "mesuré sur la largeur des tables" in trame.origine


def test_sans_tables_la_trame_retombe_sur_les_hauteurs(tmp_path):
    """Dernier recours, et il est nommé dans l'origine de la trame."""
    synthese.ecrire(tmp_path)
    contrat = charger_contrat(tmp_path)
    trame, raison = trame_du_projet(contrat, [], rampant_declare_m=4.784)
    assert trame is not None, raison
    assert "hauteurs déclarées" in trame.origine


def test_une_largeur_de_module_absurde_refuse_la_trame(tmp_path):
    """Mieux vaut pas de trame qu'une trame fausse."""
    synthese.ecrire(tmp_path)
    contrat = charger_contrat(tmp_path)
    trame, raison = trame_du_projet(contrat, [], rampant_declare_m=40.0)
    assert trame is None
    assert "hors de la fourchette" in raison
    assert str(int(LARGEUR_MODULE_MIN_M * 100)) or LARGEUR_MODULE_MAX_M


def test_le_calepinage_helioscope_donne_les_deux_cotes(tmp_path):
    """Le lot 2 mesure le module : rien à déduire."""
    synthese.ecrire(tmp_path)
    contrat = charger_contrat(tmp_path)
    contrat.donnees["parametres"]["modules"]["largeur_m"] = LARGEUR_G12R_M
    trame, _ = trame_du_projet(contrat, [], None)
    assert trame.largeur_module_m == LARGEUR_G12R_M
    assert "calepinage" in trame.origine


def test_des_modules_au_contrat_ne_se_doublent_pas_d_une_trame(tmp_path):
    """Les modules du contrat se dessinent tels quels : pas de trame par-dessus.

    Posée en pas régulier sur toute la rangée, la trame doublait les modules
    d'un calepinage HelioScope, qui s'arrêtent à chaque table. À Gannay, où les
    tables sont séparées de 0,5 m, les deux grilles se décalaient d'une table à
    l'autre (relevé le 23/09/2026). Rien n'est à signaler pour autant : ce
    n'est pas une trame manquante.
    """
    synthese.ecrire(tmp_path)
    contrat = charger_contrat(tmp_path)
    contrat.donnees["parametres"]["modules"]["largeur_m"] = LARGEUR_G12R_M
    contrat.couches["modules_pv"] = contrat.couches["tables_pv"]
    assert trame_du_projet(contrat, contrat.geometries("tables_pv"), None) == (None, None)


# ---------------------------------------------------------------------------
# Ce sont les formats déclarés qui commandent le découpage
# ---------------------------------------------------------------------------


def test_les_formats_declares_commandent_le_nombre_de_modules(tmp_path):
    """Le contour d'une rangée déborde de ses modules ; l'arrondi se trompe.

    Une table de 30,0 m divisée par un module de 1,129 m tombe sur 27 modules,
    alors que le tableau bilan en déclare 26 : c'est le cadre et le jeu de pose
    qui font la différence. Le format déclaré fait foi.
    """
    synthese.ecrire(tmp_path)
    contrat = charger_contrat(tmp_path)
    contrat.donnees["parametres"]["structures"]["nb_modules_longueur"] = [13, 26]
    contrat.donnees["parametres"]["modules"]["surface_unitaire_m2"] = (
        LONGUEUR_G12R_M * LARGEUR_G12R_M
    )
    largeur_table = 2 * LONGUEUR_G12R_M * math.cos(math.radians(25.0))
    tables = [_table(30.0, largeur_table), _table(15.0, largeur_table)]

    trame, raison = trame_du_projet(contrat, tables, None)
    assert trame is not None, raison
    comptes = [diviser_table(t, trame)[1] for t in tables]
    assert sorted(comptes) == [13, 26]


def test_sans_format_declare_le_nombre_sarrondit(tmp_path):
    synthese.ecrire(tmp_path)
    contrat = charger_contrat(tmp_path)
    contrat.donnees["parametres"]["structures"].pop("nb_modules_longueur", None)
    contrat.donnees["parametres"]["modules"]["surface_unitaire_m2"] = (
        LONGUEUR_G12R_M * LARGEUR_G12R_M
    )
    largeur_table = 2 * LONGUEUR_G12R_M * math.cos(math.radians(25.0))
    table = _table(LARGEUR_G12R_M * 12, largeur_table)
    trame, _ = trame_du_projet(contrat, [table], None)
    assert diviser_table(table, trame)[1] == 12


def test_la_trame_divise_aussi_le_rampant(tmp_path):
    """2V : deux modules empilés sur la pente, donc un trait en travers."""
    synthese.ecrire(tmp_path)
    contrat = charger_contrat(tmp_path)
    contrat.donnees["parametres"]["structures"]["nb_modules_longueur"] = [10]
    contrat.donnees["parametres"]["modules"]["surface_unitaire_m2"] = (
        LONGUEUR_G12R_M * LARGEUR_G12R_M
    )
    largeur_table = 2 * LONGUEUR_G12R_M * math.cos(math.radians(25.0))
    table = _table(LARGEUR_G12R_M * 10, largeur_table)
    trame, _ = trame_du_projet(contrat, [table], None)
    lignes, nombre = diviser_table(table, trame)
    # Neuf traits dans la longueur pour dix modules, plus un dans l'autre sens.
    assert nombre == 10
    assert len(lignes) == 9 + (trame.nb_rampant - 1)


def test_une_table_qui_ne_tombe_pas_juste_nest_pas_divisee(tmp_path):
    """Une rangée hors format n'est pas tramée au petit bonheur."""
    synthese.ecrire(tmp_path)
    contrat = charger_contrat(tmp_path)
    contrat.donnees["parametres"]["structures"]["nb_modules_longueur"] = [13]
    contrat.donnees["parametres"]["modules"]["surface_unitaire_m2"] = (
        LONGUEUR_G12R_M * LARGEUR_G12R_M
    )
    largeur_table = 2 * LONGUEUR_G12R_M * math.cos(math.radians(25.0))
    trame, _ = trame_du_projet(contrat, [_table(15.0, largeur_table)], None)
    # Une table deux fois trop longue pour le seul format déclaré.
    assert diviser_table(_table(40.0, largeur_table), trame) is None


# ---------------------------------------------------------------------------
# Le recoupement avec le tableau bilan
# ---------------------------------------------------------------------------


def test_le_controle_accepte_les_formats_declares():
    assert controler_trame({"nb_modules_longueur": [13, 26]}, [13, 26, 13]) is None


def test_le_controle_signale_un_format_inattendu():
    message = controler_trame({"nb_modules_longueur": [13, 26]}, [13, 27])
    assert message and "27" in message


def test_le_controle_se_tait_sans_declaration():
    assert controler_trame({}, [13, 26]) is None
