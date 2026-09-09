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


def _image_png(couleur=(120, 140, 160)) -> bytes:
    """Une image minuscule mais valide : `st.image` refuse des octets factices."""
    import io

    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (8, 6), couleur).save(tampon, format="PNG")
    return tampon.getvalue()


def _deposer_photos(application, code: str, fichiers):
    """Dépose plusieurs fichiers dans la ligne d'une pièce photographique."""
    for televersement in application.get("file_uploader"):
        if televersement.label.startswith(code):
            return televersement.set_value(list(fichiers))
    raise AssertionError(
        f"Aucune ligne « {code} » parmi : "
        + ", ".join(t.label for t in application.get("file_uploader"))
    )


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


def test_generer_sans_emprise_le_dit(tmp_path, monkeypatch):
    """Le clic sans emprise cadastrale produit une erreur, pas un silence.

    Relevé le 09/09/2026 : `_enregistrer_fichiers` rendait `None` sans un mot
    quand aucun fichier n'était déposé, `_construire_projet` rendait `None` à
    son tour, et le clic n'avait strictement aucun effet à l'écran. Un chef de
    projet ne peut pas deviner ce qui manque devant un écran inchangé.
    """
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("SAINT CYR")
    application.run()

    _cliquer(application, "Générer le dossier")
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    refus = [erreur.value for erreur in application.error]
    assert any("emprise cadastrale" in message.lower() for message in refus), refus
    assert not (tmp_path / "sortie").exists()


@pytest.mark.skipif(not DXF.exists(), reason="DXF de référence absent")
def test_les_avertissements_de_l_import_s_affichent(tmp_path, monkeypatch):
    """Les avertissements passent bien par le conteneur réservé plus haut.

    Ils sont rendus à l'emplacement des contrôles croisés mais remplis après le
    bloc de coupe, faute de quoi ceux de la coupe, du profil et du terrain
    arrivaient avec une exécution de retard. Ce test garde surtout contre le
    risque inverse : qu'en déplaçant leur écriture on les perde tous.
    """
    application = _plan_depose(tmp_path, monkeypatch)
    _cliquer(application, "Importer et contrôler")
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    messages = [avertissement.value for avertissement in application.warning]
    assert any("emprise cadastrale" in message.lower() for message in messages), messages


@pytest.mark.skipif(not DXF.exists(), reason="DXF de référence absent")
def test_le_cadre_de_l_apercu_est_refait_a_chaque_import(tmp_path, monkeypatch):
    """Un nouvel import repart d'un cadre neuf, pas de celui du projet d'avant.

    Le cadre n'était calculé que lorsqu'il valait `None`, et rien ne l'y
    remettait : le second projet importé dans une même session se dessinait
    dans le cadre et sur l'ortho du premier — un aperçu faux, à l'endroit
    précis où le chef de projet vérifie que l'import a lu son plan.

    Faute d'un second jeu réel dans le dépôt, le rejeu de deux projets n'est pas
    possible ici : on contrôle que le cadre est bien produit, puis que le
    gestionnaire d'import l'invalide avec les autres états dérivés.
    """
    application = _plan_depose(tmp_path, monkeypatch)
    _cliquer(application, "Importer et contrôler")
    application.run()
    assert application.session_state["cadre_apercu_be"] is not None

    source = (RACINE / "app.py").read_text(encoding="utf-8")
    debut = source.index('if st.button("Importer et contrôler"')
    fin = source.index("import_be_courant = st.session_state.import_be")
    gestionnaire = source[debut:fin]
    for cle in ("coupe_be", "profil_be", "cadre_apercu_be"):
        assert f"st.session_state.{cle} = None" in gestionnaire, cle


@pytest.mark.skipif(not DXF.exists(), reason="DXF de référence absent")
def test_importer_sans_commune_est_refuse(tmp_path, monkeypatch):
    """Sans commune, le plan n'est pas déposé : il n'a pas de dossier à lui.

    `_nom_depot` se rabattait sur « projet » : les plans de tous les projets
    encore sans nom atterrissaient dans `projets/projet/`, où les fichiers de
    même nom s'écrasaient l'un l'autre sans un mot. Un repli silencieux, ce que
    le dépôt interdit.
    """
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("")
    _televerser(application, "Plan BE", DXF, "application/dxf")
    _televerser(
        application,
        "Tableau bilan",
        TABLEAU,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    refus = [erreur.value for erreur in application.error]
    assert any("commune" in message.lower() for message in refus), refus
    assert not (tmp_path / "projets" / "projet").exists()
    assert not (tmp_path / "projets").exists()


def test_deux_photos_de_meme_nom_sont_refusees(tmp_path, monkeypatch):
    """Deux fichiers de même nom dans une pièce s'écraseraient : on refuse.

    Le dossier de la pièce nomme sa cible d'après le nom du fichier déposé. Deux
    « vue.png » dans DP 7, et le second remplaçait le premier sur le disque sans
    que rien ne le dise ; le dossier partait avec une vue de moins.
    """
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("SAINT CYR")
    _deposer_photos(
        application,
        "DP 7",
        [
            ("vue.png", _image_png((200, 120, 90)), "image/png"),
            ("vue.png", _image_png((90, 120, 200)), "image/png"),
        ],
    )
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    refus = [erreur.value for erreur in application.error]
    assert any("même nom" in message and "DP 7" in message for message in refus), refus

    _cliquer(application, "Générer le dossier")
    application.run()
    assert any(
        "même nom" in erreur.value for erreur in application.error
    ), [e.value for e in application.error]
    assert not (tmp_path / "sortie").exists()


def test_une_insertion_paysagere_en_pdf_le_dit(tmp_path, monkeypatch):
    """Un PDF déposé en DP 6 ne peut pas monter en page de garde, et on le dit.

    Le dépôt accepte le PDF — c'est un format normal pour la pièce — mais la
    page de garde attend une image. Sans message, le chef de projet croyait sa
    couverture fournie et recevait le cadre tireté.
    """
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("SAINT CYR")
    _deposer_photos(
        application,
        "DP 6",
        [("insertion.pdf", b"%PDF-1.4 factice", "application/pdf")],
    )
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    messages = [avertissement.value for avertissement in application.warning]
    assert any("PDF" in message and "page de garde" in message for message in messages), (
        messages
    )


def test_la_couverture_se_reconnait_a_l_objet_et_non_au_nom():
    """La page de garde prend l'insertion retenue, pas son homonyme d'une autre pièce.

    `_enregistrer_photos` comparait les noms de fichiers, sur les trois pièces à
    la fois : une photo de DP 7 appelée comme l'insertion retenue prenait sa
    place en couverture, et le dossier partait avec une vue de l'existant au
    lieu du projet fini.

    Exercer la fonction demanderait une génération complète — emprise, fonds
    IGN, contrat sur le disque. On contrôle donc la règle à la source : la
    comparaison se fait sur l'objet déposé.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    debut = source.index("def _enregistrer_photos(")
    fin = source.index("def _enregistrer_fichiers(")
    corps = source[debut:fin]
    assert "if fichier is retenu:" in corps
    assert "retenu.name" not in corps
