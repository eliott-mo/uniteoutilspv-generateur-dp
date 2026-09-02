"""Tests de la découverte de cairo et du diagnostic qui en découle.

Le 03/09/2026, un lancement de `streamlit run app.py` sans avoir exporté
`DP_CAIRO_DLL_DIR` produisait deux messages trompeurs : la police Aptos était
déclarée « non utilisée » alors qu'elle était installée, et le dossier échouait
au tout dernier moment, après le téléchargement de tous les fonds IGN, sur une
trace CairoSVG. Ces tests figent le comportement corrigé.
"""

from __future__ import annotations

import sys

import pytest

from dp_socle import environnement
from dp_socle.environnement import NOM_DLL, VARIABLE, EtatCairo, etat_cairo

windows_seulement = pytest.mark.skipif(
    not sys.platform.startswith("win"),
    reason="la découverte de DLL ne concerne que Windows",
)


def test_cairo_se_charge_reellement():
    """Le contrôle passe par cairocffi, pas par la présence d'un fichier.

    Une DLL présente mais privée de ses dépendances passerait un simple test
    d'existence et échouerait au rendu.
    """
    etat = etat_cairo()
    assert etat.disponible, etat.message
    assert "cairo" in etat.message.lower()


@windows_seulement
def test_decouverte_sans_variable(monkeypatch):
    """Sans `DP_CAIRO_DLL_DIR`, les dossiers connus sont fouillés."""
    monkeypatch.delenv(VARIABLE, raising=False)
    monkeypatch.setattr(environnement, "_prepare", False)

    dossier = environnement.preparer_cairo()
    if dossier is None:
        pytest.skip(f"aucun {NOM_DLL} dans les dossiers connus de ce poste")
    assert (dossier / NOM_DLL).is_file()


@windows_seulement
def test_variable_invalide_leve(monkeypatch, tmp_path):
    """Une variable explicitement fournie et fausse est une erreur, pas un appel
    à chercher ailleurs : la corriger vaut mieux que la contourner."""
    monkeypatch.setattr(environnement, "_prepare", False)

    monkeypatch.setenv(VARIABLE, str(tmp_path / "absent"))
    with pytest.raises(FileNotFoundError, match="dossier inexistant"):
        environnement.preparer_cairo()

    monkeypatch.setattr(environnement, "_prepare", False)
    monkeypatch.setenv(VARIABLE, str(tmp_path))
    with pytest.raises(FileNotFoundError, match=NOM_DLL):
        environnement.preparer_cairo()


def test_le_diagnostic_de_police_ne_blame_pas_la_police_sans_cairo(monkeypatch):
    """Sans cairo, le message doit désigner cairo — pas Aptos.

    Toutes les mesures de police passent par cairo : quand il manque, chaque
    contrôle typographique échoue et le diagnostic concluait « installez
    Aptos », sur un poste où Aptos était installée.
    """
    from dp_socle import polices

    monkeypatch.setattr(
        environnement,
        "etat_cairo",
        lambda: EtatCairo(
            disponible=False,
            dossier=None,
            message="Bibliothèque cairo indisponible : simulation de test.",
        ),
    )
    polices.etat_polices.cache_clear()
    try:
        etat = polices.etat_polices(installer=False)
    finally:
        polices.etat_polices.cache_clear()

    assert not etat.disponible
    assert "cairo" in etat.message.lower()
    assert "installez Aptos" not in etat.message
    # Et surtout : ne pas annoncer une substitution par la police elle-même.
    assert "composées en « Aptos »" not in etat.message
