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


def _modules_importes(chemins) -> set:
    """Les modules tiers importés par ces fichiers.

    Lus dans l'arbre syntaxique et non à l'exécution : un import fait au fond
    d'une fonction, pour ne le payer qu'à l'usage, ne s'exécute pas forcément
    pendant les tests — et c'est précisément un import de ce genre qui a manqué
    en ligne.
    """
    modules = set()
    for chemin in chemins:
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in noeud.names)
            elif isinstance(noeud, ast.ImportFrom) and noeud.level == 0 and noeud.module:
                modules.add(noeud.module.split(".")[0])
    return {
        module
        for module in modules
        if module not in sys.stdlib_module_names
        and module not in ("dp_socle", "tests")
    }


def _paquets_declares(*fichiers) -> set:
    """Les paquets épinglés dans ces fichiers de dépendances.

    Les lignes de renvoi (« -r requirements.txt ») sont ignorées : le fichier
    renvoyé est passé explicitement par l'appelant, qui sait ce qu'il exige.
    """
    declares = set()
    for fichier in fichiers:
        for ligne in (RACINE / fichier).read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith(("#", "-")):
                continue
            declares.add(_normaliser(ligne.split("==")[0]))
    return declares


def _exiger_declares(chemins, fichiers, ou: str) -> None:
    """Refuse tout module importé qu'aucun de ces fichiers ne déclare."""
    declares = _paquets_declares(*fichiers)
    distributions = packages_distributions()

    manquants = []
    for module in sorted(_modules_importes(chemins)):
        fournisseurs = {_normaliser(nom) for nom in distributions.get(module, [])}
        if not fournisseurs:
            manquants.append(f"{module} : aucun paquet installé ne le fournit")
        elif not fournisseurs & declares:
            manquants.append(f"{module} : fourni par {', '.join(sorted(fournisseurs))}")

    assert not manquants, f"Modules importés, absents de {ou} :\n" + "\n".join(
        f"  - {ligne}" for ligne in manquants
    )


def test_tout_module_importe_par_le_socle_est_declare():
    """Ce que le socle et l'application importent doit figurer dans `requirements.txt`.

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
    _exiger_declares(
        [*RACINE.glob("dp_socle/**/*.py"), RACINE / "app.py"],
        ["requirements.txt"],
        "requirements.txt",
    )


def test_un_test_non_marque_ne_peut_pas_joindre_un_service():
    """Le garde-fou qui rend la marque `reseau` vraie, verifie sur lui-meme.

    Sans lui, un test qui sort sans le declarer passe tant que le service
    repond. C'est arrive : le 28/09/2026 la CI est tombee deux fois de suite
    sur du code sain, parce que `test_sortie_pptx_lot8.py` interrogeait la
    Geoplateforme en croyant employer une doublure. Voir `tests/sans_reseau.py`.

    Ce test-ci ne porte pas la marque : la coupure doit donc l'atteindre.
    """
    import socket

    from .sans_reseau import ReseauCoupe

    with pytest.raises(ReseauCoupe, match="marque `reseau`"):
        socket.create_connection(("data.geopf.fr", 443), timeout=1)

    with pytest.raises(ReseauCoupe, match="data.geopf.fr:443"):
        socket.socket().connect(("data.geopf.fr", 443))


def test_tout_module_importe_par_les_tests_est_declare():
    """Les tests ont le droit d'en importer plus, pas d'en importer sans le dire.

    Ce contrôle-ci manquait : posé le 26/09/2026 sur le socle seul, il laissait
    deux `import fiona` dans `test_contrat_helioscope.py`. Ils passaient sur le
    poste, où fiona est installée, et l'intégration continue les a fait tomber
    sur sa toute première exécution — ce pour quoi elle est là.

    `requirements-dev.txt` fait foi, qui reprend `requirements.txt` et y ajoute
    de quoi jouer la suite.
    """
    _exiger_declares(
        sorted(RACINE.glob("tests/**/*.py")),
        ["requirements.txt", "requirements-dev.txt"],
        "requirements.txt et requirements-dev.txt",
    )
