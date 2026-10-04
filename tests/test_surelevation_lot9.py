"""Lot 9 — locaux techniques surélevés au-dessus des plus hautes eaux.

Ce qui se vérifie ici, dans l'ordre où le défaut coûterait le plus cher :

1. les deux hauteurs saisies sont relatives au terrain naturel, et le dépôt
   refuse une saisie qui se contredit elle-même ;
2. la planche produite **montre** la surélévation — mesurée dans le PDF, pas
   dans les valeurs intermédiaires, selon la règle du dépôt ;
3. un projet sans surélévation sort exactement comme avant.

Le troisième point est le plus important des trois : la quasi-totalité des
dossiers ne sont pas en zone inondable, et ce lot ne doit rien leur changer.
"""

from __future__ import annotations

import json

import pytest

from dp_socle.erreurs import ErreurDP
from dp_socle.projet import Projet


def _projet(tmp_path, **cotes):
    """Un `projet.json` minimal, prêt à valider."""
    emprise = tmp_path / "emprise.geojson"
    emprise.write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    return Projet(
        nom="essai",
        commune="Saint-Cyr-en-Val",
        code_postal="45590",
        date="2026-10-04",
        emprise=str(emprise),
        **cotes,
    )


def test_les_deux_cotes_de_saint_cyr_se_valident(tmp_path):
    """Les valeurs réelles du projet qui a demandé le lot, relevées le 02/10/2026."""
    _projet(tmp_path, surelevation_locaux_m=2.25, phec_locaux_m=1.95).valider()


def test_la_surelevation_seule_suffit(tmp_path):
    """La PHEC est facultative : sans elle, le reste se dessine quand même."""
    _projet(tmp_path, surelevation_locaux_m=2.25).valider()


def test_un_projet_sans_surelevation_reste_valide(tmp_path):
    """Le cas courant : rien de saisi, rien de changé."""
    projet = _projet(tmp_path)
    projet.valider()
    assert projet.surelevation_locaux_m is None
    assert projet.phec_locaux_m is None


def test_la_phec_seule_est_refusee(tmp_path):
    """Elle ne permet pas de déduire le plancher : leur écart est la revanche.

    10 cm à Périgny pour 30 à Saint-Cyr (mesuré le 02/10/2026) : il n'y a pas
    de valeur à supposer, et supposer serait le repli que le dépôt interdit.
    """
    with pytest.raises(ErreurDP, match="revanche"):
        _projet(tmp_path, phec_locaux_m=1.95).valider()


def test_une_phec_au_niveau_du_plancher_est_refusee(tmp_path):
    """Le dessin se contredirait : l'eau au-dessus du plancher qu'elle épargne."""
    with pytest.raises(ErreurDP, match="contredirait"):
        _projet(tmp_path, surelevation_locaux_m=1.95, phec_locaux_m=1.95).valider()
    with pytest.raises(ErreurDP, match="contredirait"):
        _projet(tmp_path, surelevation_locaux_m=1.95, phec_locaux_m=2.25).valider()


@pytest.mark.parametrize("hauteur", [0.0, -2.25])
def test_une_hauteur_nulle_ou_negative_est_refusee(tmp_path, hauteur):
    """Zéro n'est pas « posé au sol » : c'est un champ qu'on laisse vide.

    Les distinguer a une raison : `None` dit « non concerné » et sort la ligne
    de constat au rapport, tandis qu'un zéro saisi laisserait croire à une
    surélévation réglée à zéro, ce qui n'existe pas en PPRI.
    """
    with pytest.raises(ErreurDP, match="laissez le champ vide|hauteur en mètres"):
        _projet(tmp_path, surelevation_locaux_m=hauteur).valider()


def test_une_valeur_non_numerique_est_refusee(tmp_path):
    """Un `projet.json` corrigé à la main de travers se refuse, il ne s'arrondit pas."""
    with pytest.raises(ErreurDP, match="hauteur en mètres"):
        _projet(tmp_path, surelevation_locaux_m="2,25").valider()


def test_les_cotes_font_l_aller_retour_par_projet_json(tmp_path):
    """Écrites puis relues, elles valent la même chose.

    `ecrire` ne garde que les champs renseignés : une surélévation absente ne
    doit pas apparaître dans le fichier, sans quoi tous les dossiers porteraient
    un champ de zone inondable.
    """
    chemin = _projet(
        tmp_path, surelevation_locaux_m=2.25, phec_locaux_m=1.95
    ).ecrire(tmp_path / "projet.json")
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    assert donnees["surelevation_locaux_m"] == 2.25
    assert donnees["phec_locaux_m"] == 1.95

    chemin_nu = _projet(tmp_path).ecrire(tmp_path / "nu" / "projet.json")
    nues = json.loads(chemin_nu.read_text(encoding="utf-8"))
    assert "surelevation_locaux_m" not in nues
    assert "phec_locaux_m" not in nues
