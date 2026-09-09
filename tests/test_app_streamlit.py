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


def _cliquer(application, libelle_partiel: str):
    """Clique le bouton dont le libellé porte ce texte."""
    for bouton in application.button:
        if libelle_partiel.lower() in bouton.label.lower():
            return bouton.click()
    raise AssertionError(
        f"Aucun bouton « {libelle_partiel} » parmi : "
        + ", ".join(b.label for b in application.button)
    )


def _boite_indice(application):
    """La liste déroulante de choix de l'indice du tableau bilan."""
    for boite in application.selectbox:
        if "tableau bilan" in boite.label.lower():
            return boite
    raise AssertionError("la liste de choix de l'indice n'est pas affichée")


def _plan_depose(tmp_path, monkeypatch):
    """Une application avec la commune saisie et le plan de Saint-Cyr déposé."""
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("SAINT CYR")
    _televerser(application, "Plan BE", DXF, "application/dxf")
    _televerser(
        application,
        "Tableau bilan",
        TABLEAU,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    return application.run()


@pytest.mark.skipif(not DXF.exists(), reason="DXF de référence absent")
def test_l_indice_ne_nomme_le_dossier_qu_une_fois_importe(tmp_path, monkeypatch):
    """Le dossier porte l'indice de l'import, pas celui que la liste affiche.

    Tant qu'on n'a pas importé, la liste n'est qu'une proposition : le dossier
    ne porte pas encore d'indice, et la section 4 le dit.
    """
    application = _plan_depose(tmp_path, monkeypatch)

    assert _boite_indice(application).value == "IND06"
    assert "indice_tableau_bilan" not in application.session_state
    assert any(
        "n'a pas été importé" in legende.value for legende in application.caption
    )

    _cliquer(application, "Importer et contrôler")
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    assert application.session_state["indice_tableau_bilan"] == "IND06"
    annonces = [texte.value for texte in application.markdown]
    assert any(
        "PV SAINT CYR IND06" in annonce and "sortie/PV-SAINT-CYR-IND06/" in annonce
        for annonce in annonces
    ), [a for a in annonces if "sortie/" in a]


@pytest.mark.skipif(not DXF.exists(), reason="DXF de référence absent")
def test_changer_d_indice_sans_reimporter_refuse_d_ecrire(tmp_path, monkeypatch):
    """Déplacer la liste après l'import ne déplace pas la cible de l'écriture.

    Relevé le 09/09/2026 : la liste déroulante nommait le dossier de sortie
    alors que l'import en mémoire était celui de l'indice précédent. Écrire
    déposait la géométrie d'IND06 dans `sortie/…-IND05/`, en supprimant le
    GeoPackage qui s'y trouvait — l'écrasement même que l'indice au nom devait
    empêcher, et sous une étiquette fausse.
    """
    application = _plan_depose(tmp_path, monkeypatch)
    _cliquer(application, "Importer et contrôler")
    application.run()
    assert application.session_state["indice_tableau_bilan"] == "IND06"

    _boite_indice(application).set_value("IND05")
    application.run()

    # Le dossier reste celui de l'import : la liste ne le renomme pas.
    assert application.session_state["indice_tableau_bilan"] == "IND06"
    refus = [erreur.value for erreur in application.error]
    assert any(
        "IND05" in message and "IND06" in message and "Importer et contrôler" in message
        for message in refus
    ), refus
    # Et la section 4 continue de nommer le dossier de l'import, pas celui de
    # la liste : c'est là que le chef de projet lit ce qu'il va produire.
    annonces = [texte.value for texte in application.markdown]
    assert any("sortie/PV-SAINT-CYR-IND06/" in annonce for annonce in annonces)
    assert not any("sortie/PV-SAINT-CYR-IND05/" in annonce for annonce in annonces)
