"""L'application elle-même, jouée de bout en bout sans navigateur.

`AppTest` exécute `app.py` comme Streamlit le fait — de haut en bas, à chaque
interaction — et rend les exceptions plutôt que de les afficher en rouge dans le
navigateur du chef de projet. C'est le seul contrôle qui voit ce que voit
l'utilisateur : les tests des modules, eux, n'exécutent jamais le script.

Écrit après la `NameError` du 09/09/2026 : la réorganisation des sections avait
laissé `nom` composé en section 4 et lu en section 2, et le dépôt du DXF levait
avant qu'aucune planche ne soit dessinée. Aucun des 410 tests d'alors ne
touchait `app.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
APP = RACINE / "app.py"
REFERENCE = RACINE / "exemples" / "saint-cyr-DXF"
DXF = REFERENCE / "20260903_SCV_IND06.dxf"
TABLEAU = REFERENCE / "20260825_SCV_Tableau_Bilan_V6.xlsx"

#: Lecture du DXF de Saint-Cyr et du classeur de 7 Mo comprise.
DELAI_S = 300


def _application(tmp_path, monkeypatch):
    """Une application prête à jouer, qui écrit dans un dossier jetable.

    `DOSSIER_PROJETS` et `DOSSIER_SORTIE` sont relatifs : se placer dans un
    dossier temporaire suffit à ce que le test n'écrive rien dans le dépôt.
    """
    from streamlit.testing.v1 import AppTest

    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))
    monkeypatch.chdir(tmp_path)
    return AppTest.from_file(str(APP), default_timeout=DELAI_S)


def _televerser(application, libelle_partiel: str, chemin: Path, mime: str):
    """Dépose un fichier dans le téléversement dont le libellé porte ce texte."""
    for televersement in application.get("file_uploader"):
        if libelle_partiel.lower() in televersement.label.lower():
            televersement.set_value((chemin.name, chemin.read_bytes(), mime))
            return televersement
    raise AssertionError(
        f"Aucun téléversement « {libelle_partiel} » parmi : "
        + ", ".join(t.label for t in application.get("file_uploader"))
    )


def test_le_script_se_deroule_en_entier(tmp_path, monkeypatch):
    """Les quatre sections s'affichent, dans l'ordre, sans exception."""
    application = _application(tmp_path, monkeypatch).run()

    assert not application.exception, [str(e.value) for e in application.exception]
    assert [titre.value for titre in application.subheader] == [
        "1. Métadonnées du projet",
        "2. Plan du bureau d'études",
        "3. Photographies et photomontages",
        "4. Génération",
    ]


@pytest.mark.skipif(not DXF.exists(), reason="DXF de référence absent")
def test_le_depot_du_plan_ne_leve_pas(tmp_path, monkeypatch):
    """Déposer le DXF et le tableau bilan ne lève plus de `NameError`.

    C'est la panne du 09/09/2026, reproduite : commune saisie, plan et tableau
    déposés, rien d'autre. Le script allait alors chercher `nom`, composé six
    cents lignes plus bas, et s'arrêtait sur `name 'nom' is not defined`.
    """
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("SAINT CYR")
    _televerser(application, "Plan BE", DXF, "application/dxf")
    _televerser(
        application,
        "Tableau bilan",
        TABLEAU,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    # Le dépôt a bien eu lieu, sous le nom de la commune et sans indice : c'est
    # le tableau déposé là qui donne la liste des indices.
    assert (tmp_path / "projets" / "PV-SAINT-CYR" / DXF.name).exists()
    assert (tmp_path / "projets" / "PV-SAINT-CYR" / TABLEAU.name).exists()


@pytest.mark.skipif(not DXF.exists(), reason="DXF de référence absent")
def test_l_indice_du_tableau_entre_dans_le_nom_du_dossier(tmp_path, monkeypatch):
    """Le dossier annoncé en section 4 porte l'indice choisi en section 2.

    Sans lui, deux indices d'un même projet écrivaient dans le même dossier et
    le second écrasait le premier — Sarnois en a deux.
    """
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("SAINT CYR")
    _televerser(application, "Plan BE", DXF, "application/dxf")
    _televerser(
        application,
        "Tableau bilan",
        TABLEAU,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    application.run()

    indices = [
        boite
        for boite in application.selectbox
        if "tableau bilan" in boite.label.lower()
    ]
    assert indices, "la boîte de choix de l'indice doit être affichée"
    assert application.session_state["indice_tableau_bilan"] == "IND06"

    annonces = [texte.value for texte in application.markdown]
    assert any(
        "PV SAINT CYR IND06" in annonce and "sortie/PV-SAINT-CYR-IND06/" in annonce
        for annonce in annonces
    ), [a for a in annonces if "sortie/" in a]
