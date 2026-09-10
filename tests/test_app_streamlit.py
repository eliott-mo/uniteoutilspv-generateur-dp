"""L'application elle-même, jouée de bout en bout sans navigateur.

`AppTest` exécute `app.py` comme Streamlit le fait — de haut en bas, à chaque
interaction — et rend les exceptions plutôt que de les afficher en rouge dans le
navigateur du chef de projet. C'est le seul contrôle qui voit ce que voit
l'utilisateur : les tests des modules, eux, n'exécutent jamais le script.

Écrit après la `NameError` du 09/09/2026 : la réorganisation des sections avait
laissé `nom` composé en section 4 et lu en section 2, et le dépôt du DXF levait
avant qu'aucune planche ne soit dessinée. Aucun des 410 tests d'alors ne
touchait `app.py`.

Les sections apparaissent maintenant au fur et à mesure, et les tests suivent
le même chemin que le chef de projet : nommer et cadrer le projet, importer le
plan, valider l'import, puis générer. Un relevé altimétrique de synthèse est
déposé à chaque fois, pour que le profil du terrain se lise dans un fichier et
non sur le RGE ALTI : ces tests ne demandent aucun service en ligne.
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
EMPRISE = REFERENCE / "phu_45590_saint-cyr-en-val-geoperso-1-24_10_2025_17_11"

#: Lecture du DXF de Saint-Cyr et du classeur de 7 Mo comprise.
DELAI_S = 300

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Bornes de la clôture de Saint-Cyr, relevées sur le DXF le 10/09/2026, avec
#: une marge : le relevé de synthèse doit couvrir toute la coupe, sinon ses
#: extrémités sont prolongées et le profil porte un avertissement de plus.
BORNES = (622_800.0, 6_750_550.0, 623_120.0, 6_750_970.0)


# ---------------------------------------------------------------------------
# Utilitaires de dépôt
# ---------------------------------------------------------------------------


def _image_png(couleur=(120, 140, 160)) -> bytes:
    """Une image minuscule mais valide : `st.image` refuse des octets factices."""
    import io

    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (8, 6), couleur).save(tampon, format="PNG")
    return tampon.getvalue()


def _releve_altimetrique() -> bytes:
    """Un relevé « X Y Z » de synthèse couvrant le site, en pente douce.

    Déposé pour que `profil_terrain` lise un fichier au lieu d'interroger le
    RGE ALTI : ces tests n'ont alors besoin d'aucun service en ligne, et le
    profil est le même à chaque exécution.

    Le pas en x vaut 2 m, la largeur du demi-couloir que `_couloir_de_coupe`
    retient autour de la ligne : plus large, aucun point du relevé ne tombe
    dans le couloir de la coupe — qui court nord-sud — et le profil est refusé.
    """
    ouest, sud, est, nord = BORNES
    lignes = ["# X Y Z — relevé de synthèse, Lambert 93"]
    x = ouest
    while x <= est:
        y = sud
        while y <= nord:
            lignes.append(f"{x:.2f} {y:.2f} {100.0 + 0.02 * (y - sud):.2f}")
            y += 5.0
        x += 2.0
    return "\n".join(lignes).encode("utf-8")


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


def _televersement(application, debut_du_libelle: str):
    """Le dépôt dont le libellé commence par ce texte."""
    for televersement in application.get("file_uploader"):
        if televersement.label.lower().startswith(debut_du_libelle.lower()):
            return televersement
    raise AssertionError(
        f"Aucun dépôt « {debut_du_libelle} » parmi : "
        + (", ".join(t.label for t in application.get("file_uploader")) or "aucun")
    )


def _televerser(application, debut_du_libelle: str, fichiers):
    """Dépose un fichier, ou plusieurs, dans le dépôt désigné."""
    return _televersement(application, debut_du_libelle).set_value(fichiers)


def _cliquer(application, libelle_partiel: str):
    """Clique le bouton dont le libellé porte ce texte."""
    for bouton in application.button:
        if libelle_partiel.lower() in bouton.label.lower():
            return bouton.click()
    raise AssertionError(
        f"Aucun bouton « {libelle_partiel} » parmi : "
        + (", ".join(b.label for b in application.button) or "aucun")
    )


def _bouton_present(application, libelle_partiel: str) -> bool:
    return any(
        libelle_partiel.lower() in bouton.label.lower() for bouton in application.button
    )


def _boite_indice(application):
    """La liste déroulante de choix de l'indice du tableau bilan."""
    for boite in application.selectbox:
        if "tableau bilan" in boite.label.lower():
            return boite
    raise AssertionError("la liste de choix de l'indice n'est pas affichée")


def _titres(application) -> list:
    return [titre.value for titre in application.subheader]


# ---------------------------------------------------------------------------
# Les étapes du parcours, chacune s'appuyant sur la précédente
# ---------------------------------------------------------------------------


def _projet_cadre(tmp_path, monkeypatch):
    """Étape 1 : la commune est saisie et l'emprise cadastrale déposée."""
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("SAINT CYR")
    _televerser(
        application,
        "Emprise cadastrale",
        [
            (chemin.name, chemin.read_bytes(), "application/octet-stream")
            for chemin in sorted(EMPRISE.iterdir())
            if chemin.suffix.lower() in (".shp", ".shx", ".dbf", ".prj")
        ],
    )
    return application.run()


def _plan_depose(tmp_path, monkeypatch):
    """Étape 2 : le DXF, le tableau bilan et le relevé altimétrique sont déposés."""
    application = _projet_cadre(tmp_path, monkeypatch)
    _televerser(application, "Plan BE (DXF", (DXF.name, DXF.read_bytes(), "application/dxf"))
    _televerser(application, "Tableau bilan", (TABLEAU.name, TABLEAU.read_bytes(), MIME_XLSX))
    _televerser(
        application,
        "Relevé altimétrique",
        ("releve.txt", _releve_altimetrique(), "text/plain"),
    )
    return application.run()


def _plan_importe(tmp_path, monkeypatch):
    """Étape 3 : l'import est fait, et la coupe par défaut avec lui."""
    application = _plan_depose(tmp_path, monkeypatch)
    _cliquer(application, "Importer et contrôler")
    return application.run()


def _import_valide(tmp_path, monkeypatch):
    """Étape 4 : le contrat est écrit, les sections 3 et 4 s'ouvrent."""
    application = _plan_importe(tmp_path, monkeypatch)
    _cliquer(application, "Valider l'import")
    return application.run()


# ---------------------------------------------------------------------------
# Le parcours, section après section
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_les_sections_apparaissent_au_fur_et_a_mesure(tmp_path, monkeypatch):
    """Chaque section attend que la précédente soit satisfaite.

    Une page entière offrait le bouton « Générer le dossier » dès l'ouverture :
    cliqué avant l'import, il produisait un PDF de 17 Mo à quatre planches sur
    neuf, d'apparence complète. La section n'existe plus tant que le plan n'est
    pas validé.
    """
    application = _application(tmp_path, monkeypatch).run()
    assert _titres(application) == ["1. Métadonnées du projet"]
    assert not _bouton_present(application, "Générer le dossier")

    application = _projet_cadre(tmp_path, monkeypatch)
    assert _titres(application) == [
        "1. Métadonnées du projet",
        "2. Plan du bureau d'études",
    ]
    assert not _bouton_present(application, "Générer le dossier")

    application = _import_valide(tmp_path, monkeypatch)
    assert not application.exception, [str(e.value) for e in application.exception]
    assert _titres(application) == [
        "1. Métadonnées du projet",
        "2. Plan du bureau d'études",
        "3. Photographies et photomontages",
        "4. Génération",
    ]
    assert _bouton_present(application, "Générer le dossier")


def test_les_prerequis_sont_annonces_avant_toute_saisie(tmp_path, monkeypatch):
    """Le chef de projet sait ce qu'il doit rassembler avant de commencer."""
    application = _application(tmp_path, monkeypatch).run()

    annonce = "\n".join(information.value for information in application.info)
    assert "À rassembler avant de commencer" in annonce
    for attendu in ("Emprise cadastrale", "Plan du bureau d'études", "Tableau bilan"):
        assert attendu in annonce, attendu
    assert ".prj" in annonce, "le fichier qui manque le plus souvent"


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_le_depot_du_plan_ne_leve_pas(tmp_path, monkeypatch):
    """Déposer le DXF et le tableau bilan ne lève plus de `NameError`.

    C'est la panne du 09/09/2026, reproduite : commune saisie, plan et tableau
    déposés, rien d'autre. Le script allait alors chercher `nom`, composé six
    cents lignes plus bas, et s'arrêtait sur `name 'nom' is not defined`.
    """
    application = _plan_depose(tmp_path, monkeypatch)

    assert not application.exception, [str(e.value) for e in application.exception]
    # Le dépôt a bien eu lieu, sous le nom de la commune et sans indice : c'est
    # le tableau déposé là qui donne la liste des indices.
    assert (tmp_path / "projets" / "PV-SAINT-CYR" / DXF.name).exists()
    assert (tmp_path / "projets" / "PV-SAINT-CYR" / TABLEAU.name).exists()


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_la_coupe_est_proposee_des_l_import(tmp_path, monkeypatch):
    """L'import place la coupe : le chef de projet n'a plus rien à tracer.

    Le tracé n'apportait que l'intention — la direction vient de l'azimut des
    tables, la position du nombre de rangées traversées. Celui qui trouve la
    proposition bien placée peut valider dans la foulée.
    """
    application = _plan_importe(tmp_path, monkeypatch)

    assert not application.exception, [str(e.value) for e in application.exception]
    assert application.session_state["coupe_be"] is not None
    assert application.session_state["origine_coupe"] == "defaut"
    assert application.session_state["profil_be"] is not None

    annonces = [succes.value for succes in application.success]
    assert any("Coupe par défaut" in annonce for annonce in annonces), annonces
    # Et l'écriture de la sortie est offerte sans avoir rien tracé.
    assert _bouton_present(application, "Valider l'import")


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_le_profil_du_terrain_n_est_plus_dessine(tmp_path, monkeypatch):
    """La figure du profil ne trompe plus sur la forme du terrain.

    Elle était tracée sans respecter le rapport entre abscisses et altitudes —
    350 m de long pour quelques mètres de dénivelée — et donnait à lire une
    colline là où le terrain est plat. Ce qui compte, la cohérence de la pente
    et le contrôle des altitudes du DXF, remonte en avertissement quand il
    cloche ; le reste n'engageait rien.
    """
    application = _plan_importe(tmp_path, monkeypatch)

    # Une seule image dans la section 2 : l'aperçu des géométries.
    assert len(application.get("imgs")) <= 1
    intitules = [metrique.label for metrique in application.get("metric")]
    for absent in ("Dénivelée totale", "Altitude mini", "Longueur de la coupe"):
        assert absent not in intitules, intitules


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_l_indice_ne_nomme_le_dossier_qu_une_fois_importe(tmp_path, monkeypatch):
    """Le dossier porte l'indice de l'import, pas celui que la liste affiche."""
    application = _plan_depose(tmp_path, monkeypatch)

    assert _boite_indice(application).value == "IND06"
    assert "indice_tableau_bilan" not in application.session_state

    application = _import_valide(tmp_path, monkeypatch)

    assert not application.exception, [str(e.value) for e in application.exception]
    assert application.session_state["indice_tableau_bilan"] == "IND06"
    annonces = [texte.value for texte in application.markdown]
    assert any(
        "PV SAINT CYR IND06" in annonce
        for annonce in annonces
    ), annonces


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_changer_d_indice_sans_reimporter_refuse_d_ecrire(tmp_path, monkeypatch):
    """Déplacer la liste après l'import ne déplace pas la cible de l'écriture.

    Relevé le 09/09/2026 : la liste déroulante nommait le dossier de sortie
    alors que l'import en mémoire était celui de l'indice précédent. Écrire
    déposait la géométrie d'IND06 dans `sortie/…-IND05/`, en supprimant le
    GeoPackage qui s'y trouvait — l'écrasement même que l'indice au nom devait
    empêcher, et sous une étiquette fausse.
    """
    application = _plan_importe(tmp_path, monkeypatch)
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
    assert not _bouton_present(application, "Valider l'import")


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_les_avertissements_de_l_import_s_affichent(tmp_path, monkeypatch):
    """Les avertissements passent bien par le conteneur réservé plus haut.

    Ils sont rendus à l'emplacement des contrôles croisés mais remplis après le
    bloc de coupe, faute de quoi ceux de la coupe, du profil et du terrain
    arrivaient avec une exécution de retard. Ce test garde surtout contre le
    risque inverse : qu'en déplaçant leur écriture on les perde tous.
    """
    application = _plan_importe(tmp_path, monkeypatch)

    assert not application.exception, [str(e.value) for e in application.exception]
    messages = [avertissement.value for avertissement in application.warning]
    assert any("RGE ALTI" in message for message in messages), messages


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_le_plan_importe_ne_s_affiche_qu_une_fois(tmp_path, monkeypatch):
    """La coupe se trace sur le plan lui-même, et non à côté d'un aperçu.

    L'écran portait deux vues presque identiques : une carte à tracer, qui ne
    montrait que les tables et la clôture, puis un aperçu statique de tout le
    plan. Le chef de projet traçait donc sa coupe sans voir ce qu'elle allait
    couper, et procédait par essai-erreur — tracer, corriger, descendre lire
    l'aperçu, remonter.
    """
    application = _plan_importe(tmp_path, monkeypatch)

    assert not application.exception, [str(e.value) for e in application.exception]
    # Plus aucune image dans la section 2 : la carte porte tout.
    assert not application.get("imgs")


def test_la_carte_porte_toutes_les_categories_de_la_planche():
    """La carte dessine le plan aux couleurs de la légende DP, pas deux calques.

    Elle ne montrait que `tables_pv` et `cloture`, en dur : ni les pistes, ni les
    postes, ni la citerne, ni l'emprise cadastrale. Le contrôle se fait à la
    source — le contenu d'un composant `st_folium` n'est pas lisible depuis
    `AppTest`.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    debut = source.index("### Le plan importé, et la ligne de coupe")
    fin = source.index("if trace is not None and st.button")
    bloc = source[debut:fin]

    assert "for categorie in ORDRE_DESSIN:" in bloc
    assert "_style_carte(style)" in bloc
    assert "emprise_cadastrale" in bloc
    # Et les modules en sont écartés : un plan en compte des milliers.
    assert "CATEGORIES_HORS_CARTE" in bloc


def test_seule_la_coupe_redressee_est_montree():
    """Le tracé d'origine ne s'affiche plus à côté de la coupe corrigée.

    Relevé le 10/09/2026 par le chef de projet : tracer volontairement de
    travers, corriger, et voir son trait oblique persister sur la carte donnait
    à croire que rien n'avait été redressé. La carte remonte aussi à neuf après
    chaque correction, faute de quoi Leaflet gardait le trait dessiné à la main
    par-dessus la ligne retenue.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    debut = source.index("### Le plan importé, et la ligne de coupe")
    fin = source.index("with emplacement_avertissements:")
    bloc = source[debut:fin]

    assert "trace_initial" not in bloc
    assert 'st.session_state["tour_carte"]' in bloc
    assert "key=f\"carte_coupe_be_{st.session_state.get('tour_carte', 0)}\"" in bloc


# ---------------------------------------------------------------------------
# Les refus
# ---------------------------------------------------------------------------


def test_sans_emprise_la_generation_est_hors_de_portee(tmp_path, monkeypatch):
    """On ne peut plus lancer une génération que l'emprise ne cadrerait pas.

    Le clic était auparavant absorbé sans rien produire : ni planche, ni erreur,
    l'écran inchangé. La section n'existe plus, et l'écran dit ce qu'il attend.
    """
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("SAINT CYR")
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    assert not _bouton_present(application, "Générer le dossier")
    attentes = "\n".join(information.value for information in application.info)
    assert "emprise cadastrale" in attentes.lower(), attentes
    assert not (tmp_path / "sortie").exists()


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_importer_sans_commune_est_hors_de_portee(tmp_path, monkeypatch):
    """Sans commune, le plan n'a pas de dossier à lui : on ne le dépose pas.

    `_nom_depot` se rabattait sur « projet » : les plans de tous les projets
    encore sans nom atterrissaient dans `projets/projet/`, où les fichiers de
    même nom s'écrasaient l'un l'autre sans un mot.
    """
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("")
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    assert _titres(application) == ["1. Métadonnées du projet"]
    attentes = "\n".join(information.value for information in application.info)
    assert "commune" in attentes.lower(), attentes
    assert not (tmp_path / "projets").exists()


def test_le_dossier_reduit_se_demande_explicitement(tmp_path, monkeypatch):
    """Les seules pièces DP 1 restent possibles, mais elles se demandent.

    Un dossier sans plan de masse ni coupes est un dossier d'étude amont, pas un
    dossier déposable. Il était produit par simple inadvertance ; il faut
    maintenant cocher la case qui dit ce qu'on renonce à obtenir.
    """
    application = _projet_cadre(tmp_path, monkeypatch)
    assert not _bouton_present(application, "Générer le dossier")

    cases = [
        case
        for case in application.checkbox
        if "seulement les pièces DP 1" in case.label
    ]
    assert cases, [case.label for case in application.checkbox]
    cases[0].set_value(True)
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    assert "4. Génération" in _titres(application)
    assert _bouton_present(application, "Générer le dossier")


def test_deux_photos_de_meme_nom_sont_refusees(tmp_path, monkeypatch):
    """Deux fichiers de même nom dans une pièce s'écraseraient : on refuse.

    Le dossier de la pièce nomme sa cible d'après le nom du fichier déposé. Deux
    « vue.png » dans DP 7, et le second remplaçait le premier sur le disque sans
    que rien ne le dise ; le dossier partait avec une vue de moins.
    """
    application = _projet_cadre(tmp_path, monkeypatch)
    [c for c in application.checkbox if "seulement les pièces DP 1" in c.label][
        0
    ].set_value(True)
    application.run()

    _televerser(
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
    assert any("même nom" in erreur.value for erreur in application.error), [
        e.value for e in application.error
    ]
    assert not (tmp_path / "sortie").exists()


def test_une_insertion_paysagere_en_pdf_le_dit(tmp_path, monkeypatch):
    """Un PDF déposé en DP 6 ne peut pas monter en page de garde, et on le dit.

    Le dépôt accepte le PDF — c'est un format normal pour la pièce — mais la
    page de garde attend une image. Sans message, le chef de projet croyait sa
    couverture fournie et recevait le cadre tireté.
    """
    application = _projet_cadre(tmp_path, monkeypatch)
    [c for c in application.checkbox if "seulement les pièces DP 1" in c.label][
        0
    ].set_value(True)
    application.run()

    _televerser(
        application, "DP 6", [("insertion.pdf", b"%PDF-1.4 factice", "application/pdf")]
    )
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    messages = [avertissement.value for avertissement in application.warning]
    assert any(
        "PDF" in message and "page de garde" in message for message in messages
    ), messages


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


@pytest.mark.reseau
@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_le_dossier_reste_telechargeable_apres_un_premier_clic(
    tmp_path, monkeypatch
):
    """Le compte rendu et ses boutons survivent à la réexécution du script.

    Tout clic sur un bouton de téléchargement rejoue le script : `lancer`
    retombe à faux et le bloc `if lancer:` disparaît, boutons compris. Le chef
    de projet ne pouvait donc emporter qu'un seul fichier, puis devait relancer
    une génération complète — fonds IGN compris — pour obtenir l'autre.

    Le rejeu est ici obtenu par un `run()` de plus, ce qu'est exactement une
    réexécution provoquée par un clic.
    """
    application = _import_valide(tmp_path, monkeypatch)
    _cliquer(application, "Générer le dossier")
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    telechargements = application.get("download_button")
    intitules = [bouton.label for bouton in telechargements]
    assert any("dossier complet" in intitule for intitule in intitules), intitules
    assert any("PDF assemblé" in intitule for intitule in intitules), intitules

    # La réexécution que provoquerait un clic sur l'un d'eux.
    application.run()
    assert not application.exception, [str(e.value) for e in application.exception]
    survivants = [bouton.label for bouton in application.get("download_button")]
    assert any("dossier complet" in intitule for intitule in survivants), survivants
    assert any("PDF assemblé" in intitule for intitule in survivants), survivants
