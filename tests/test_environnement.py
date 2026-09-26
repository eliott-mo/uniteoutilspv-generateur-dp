"""Tests de la découverte de cairo et du diagnostic qui en découle.

Le 03/09/2026, un lancement de `streamlit run app.py` sans avoir exporté
`DP_CAIRO_DLL_DIR` produisait deux messages trompeurs : la police Aptos était
déclarée « non utilisée » alors qu'elle était installée, et le dossier échouait
au tout dernier moment, après le téléchargement de tous les fonds IGN, sur une
trace CairoSVG. Ces tests figent le comportement corrigé.
"""

from __future__ import annotations

import ast
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

from dp_socle import environnement
from dp_socle.environnement import NOM_DLL, VARIABLE, EtatCairo, etat_cairo

RACINE = Path(__file__).resolve().parent.parent

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


# ---------------------------------------------------------------------------
# Ce que le code importe, le déploiement doit le déclarer
# ---------------------------------------------------------------------------


def _normaliser(nom: str) -> str:
    """Nom de paquet comparable : pip ignore la casse et confond « - » et « _ »."""
    return nom.strip().lower().replace("_", "-")


def _modules_importes() -> set:
    """Les modules tiers importés par le socle et par l'application.

    Lus dans l'arbre syntaxique et non à l'exécution : un import fait au fond
    d'une fonction, pour ne le payer qu'à l'usage, ne s'exécute pas pendant les
    tests — et c'est précisément un import de ce genre qui a manqué en ligne.
    """
    modules = set()
    for chemin in [*RACINE.glob("dp_socle/**/*.py"), RACINE / "app.py"]:
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in noeud.names)
            elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
                modules.add(noeud.module.split(".")[0])
    return {
        module
        for module in modules
        if module not in sys.stdlib_module_names and module != "dp_socle"
    }


def _paquets_declares() -> set:
    lignes = (RACINE / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return {
        _normaliser(ligne.split("==")[0])
        for ligne in lignes
        if ligne.strip() and not ligne.lstrip().startswith("#")
    }


def test_tout_module_importe_est_declare_dans_requirements():
    """Ce que le code importe doit figurer dans `requirements.txt`.

    Le piège s'est refermé trois fois : pillow-heif, puis PyMuPDF, puis fiona —
    installés sur le poste de développement, absents du conteneur. Les deux
    premiers se sont vus en relisant le code ; le troisième a arrêté la
    génération d'un chef de projet, en ligne, sur un `ModuleNotFoundError`
    (26/09/2026).

    « Une autre dépendance l'apporte » ne suffit pas : geopandas 1.x a cessé
    d'apporter fiona, et rien ne l'avait dit. Le nom du paquet qui fournit un
    module est demandé à l'environnement (`packages_distributions`) plutôt
    qu'écrit dans une table — `PIL` vient de Pillow, `pptx` de python-pptx, et
    une table aurait vieilli sans prévenir.
    """
    declares = _paquets_declares()
    distributions = packages_distributions()

    manquants = []
    for module in sorted(_modules_importes()):
        fournisseurs = {_normaliser(nom) for nom in distributions.get(module, [])}
        if not fournisseurs:
            manquants.append(f"{module} : aucun paquet installé ne le fournit")
        elif not fournisseurs & declares:
            manquants.append(f"{module} : fourni par {', '.join(sorted(fournisseurs))}")

    assert not manquants, "Modules importés mais non déclarés :\n" + "\n".join(
        f"  - {ligne}" for ligne in manquants
    )
