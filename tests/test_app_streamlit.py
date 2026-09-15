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


def _notice_pdf(pages: int = 1) -> bytes:
    """Une notice de synthèse en A4 portrait, au texte vectoriel.

    Composée par cairo comme les planches : rien n'est déposé dans le dépôt, et
    le texte reste extractible du dossier assemblé — c'est ce qui distingue la
    fusion d'une rastérisation.
    """
    import io

    import cairosvg
    from pypdf import PdfReader, PdfWriter

    ecrivain = PdfWriter()
    for numero in range(1, pages + 1):
        svg = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<svg xmlns="http://www.w3.org/2000/svg" width="210mm" '
            'height="297mm" viewBox="0 0 210 297">'
            '<rect x="0" y="0" width="210" height="297" fill="#ffffff"/>'
            '<text x="20" y="40" font-family="sans-serif" font-size="4">'
            f"NOTICE DE SYNTHESE — page {numero}</text></svg>"
        ).encode("utf-8")
        ecrivain.add_page(PdfReader(io.BytesIO(cairosvg.svg2pdf(bytestring=svg))).pages[0])
    tampon = io.BytesIO()
    ecrivain.write(tampon)
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
        "3. Pièces fournies",
        "4. Génération",
    ]
    assert _bouton_present(application, "Générer le dossier")


def test_les_prerequis_sont_annonces_avant_toute_saisie(tmp_path, monkeypatch):
    """Le chef de projet sait ce qu'il doit rassembler avant de commencer."""
    application = _application(tmp_path, monkeypatch).run()

    annonce = "\n".join(information.value for information in application.info)
    assert "À rassembler avant de commencer" in annonce
    for attendu in (
        "Emprise cadastrale",
        "Plan du bureau d'études",
        "Tableau bilan",
        "Notice DP 11",
    ):
        assert attendu in annonce, attendu
    assert ".prj" in annonce, "le fichier qui manque le plus souvent"


@pytest.mark.skipif(not TABLEAU.exists(), reason="jeu de référence absent")
def test_le_tableau_sans_le_dxf_dit_ce_qui_manque(tmp_path, monkeypatch):
    """La section vide disait « validez l'import » et ne montrait rien à valider.

    Relevé le 15/09/2026 : tableau bilan et PDF déposés, DXF oublié. Tout le bloc
    d'import vit derrière « commune et DXF et tableau » — ni liste des indices, ni
    bouton, ni carte. L'écran enchaînait sur « Validez l'import ci-dessus pour
    continuer », qui désigne un import qui n'existe pas, et le chef de projet
    cherchait un bouton absent au lieu de déposer son plan.
    """
    application = _projet_cadre(tmp_path, monkeypatch)
    _televerser(
        application, "Tableau bilan", (TABLEAU.name, TABLEAU.read_bytes(), MIME_XLSX)
    )
    application = application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    assert not _bouton_present(application, "Importer et contrôler")
    manques = [avertissement.value for avertissement in application.warning]
    assert any("plan BE (DXF)" in manque for manque in manques), manques
    # Et il ne réclame que ce qui manque vraiment : le tableau est là.
    assert not any("tableau bilan" in manque.lower() for manque in manques), manques


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_la_section_du_plan_ne_reclame_rien_avant_le_premier_depot(
    tmp_path, monkeypatch
):
    """Réclamer les deux fichiers à l'ouverture, sous la liste des prérequis, est du bruit."""
    application = _projet_cadre(tmp_path, monkeypatch)

    manques = [avertissement.value for avertissement in application.warning]
    assert not any("Importer et contrôler" in manque for manque in manques), manques


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


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_le_bouton_arme_le_clic_et_s_annule(tmp_path, monkeypatch):
    """« Déplacer la coupe » arme la carte, annonce ce qu'elle attend, et se défait.

    Le clic lui-même n'est pas jouable ici — `AppTest` ne rend pas le contenu
    d'un composant `st_folium`, et la valeur qu'il renvoie est celle de ses
    défauts. Ce qui se mesure est l'armement : sans lui, aucun clic ne sera
    destiné à la coupe.
    """
    application = _plan_importe(tmp_path, monkeypatch)
    assert "geste_carte" not in application.session_state
    assert _bouton_present(application, "Déplacer la coupe")

    _cliquer(application, "Déplacer la coupe")
    application = application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    assert application.session_state["geste_carte"] == "translation_coupe"
    consignes = [info.value for info in application.info]
    assert any("Cliquez sur la carte" in consigne for consigne in consignes), consignes
    # La coupe proposée reste en place tant que rien n'a été cliqué.
    assert application.session_state["coupe_be"] is not None

    _cliquer(application, "Annuler le déplacement")
    application = application.run()

    assert application.session_state["geste_carte"] is None
    assert _bouton_present(application, "Déplacer la coupe")


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_un_clic_qui_ne_vient_pas_ne_deplace_rien(tmp_path, monkeypatch):
    """La carte armée sans clic laisse la coupe et le profil intacts.

    `last_clicked` persiste d'une exécution à la suivante : lu sans mémoire, il
    ferait rejouer le même clic à chaque interaction. Ici il vaut None, et la
    case du contournement se coche sans que la coupe bouge.
    """
    application = _plan_importe(tmp_path, monkeypatch)
    coupe_avant = application.session_state["coupe_be"].geometrie.wkt

    _cliquer(application, "Déplacer la coupe")
    application = application.run()
    for _ in range(2):
        application.checkbox[0].set_value(True)
        application = application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    assert application.session_state["coupe_be"].geometrie.wkt == coupe_avant
    assert application.session_state["origine_coupe"] == "defaut"


def _carte_cliquable(monkeypatch):
    """Remplace le composant de carte, seule pièce de l'écran qu'`AppTest` ne joue pas.

    `st_folium` renvoie ses valeurs par défaut sous `AppTest`, `last_clicked` à
    None : aucun clic n'y arrive jamais. Le remplacer par un composant qui rend le
    clic qu'on lui dicte laisse jouer tout le reste du chemin réel — l'armement,
    la consommation du clic, la translation, le relevé du profil et les contrôles.

    Rend un dictionnaire sur lequel poser `point`, en (x, y) Lambert 93 ; None
    pour une carte sur laquelle personne n'a cliqué. La carte reçue est retenue
    sous `carte` : c'est le seul endroit d'où lire ce qui a été posé dessus.
    """
    import streamlit_folium
    from pyproj import Transformer

    vers_wgs84 = Transformer.from_crs(2154, 4326, always_xy=True)
    dicte = {"point": None, "carte": None}

    def _composant(carte=None, *_args, **_kwargs):
        dicte["carte"] = carte
        valeurs = {
            "last_clicked": None,
            "all_drawings": None,
            "last_active_drawing": None,
        }
        if dicte["point"] is not None:
            longitude, latitude = vers_wgs84.transform(*dicte["point"])
            valeurs["last_clicked"] = {"lat": latitude, "lng": longitude}
        return valeurs

    monkeypatch.setattr(streamlit_folium, "st_folium", _composant)
    return dicte


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_un_clic_deplace_la_coupe_et_releve_le_profil(tmp_path, monkeypatch):
    """Le geste entier, de l'armement au profil : la coupe passe par le clic.

    Les rangées de Saint-Cyr sont est-ouest, donc la coupe est nord-sud et la
    déplacer la fait glisser en x. Le clic est posé 60 m à l'ouest de la coupe
    proposée, dans l'emprise du relevé altimétrique déposé.
    """
    carte = _carte_cliquable(monkeypatch)
    application = _plan_importe(tmp_path, monkeypatch)
    avant = application.session_state["coupe_be"].geometrie
    profil_avant = application.session_state["profil_be"]

    _cliquer(application, "Déplacer la coupe")
    application = application.run()

    milieu = avant.interpolate(0.5, normalized=True)
    carte["point"] = (milieu.x - 60.0, milieu.y)
    application = application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    coupe = application.session_state["coupe_be"]
    from shapely.geometry import Point

    assert coupe.geometrie.distance(Point(*carte["point"])) == pytest.approx(
        0.0, abs=1e-6
    )
    # Direction inchangée, position déplacée de 60 m : le geste qui manquait.
    # Rangées est-ouest, donc coupe strictement nord-sud, avant comme après.
    depart, arrivee = coupe.geometrie.coords[0], coupe.geometrie.coords[-1]
    assert depart[0] == pytest.approx(arrivee[0], abs=1e-6)
    assert coupe.geometrie.distance(milieu) == pytest.approx(60.0, abs=0.01)
    assert coupe.position_choisie
    assert application.session_state["origine_coupe"] == "deplacee"

    # Le geste est désarmé, le profil relevé sur la nouvelle ligne.
    assert application.session_state["geste_carte"] is None
    profil = application.session_state["profil_be"]
    assert profil is not None and profil is not profil_avant
    assert len(profil.abscisses_m) >= 2
    annonces = [succes.value for succes in application.success]
    assert any("Coupe déplacée" in annonce for annonce in annonces), annonces


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_un_clic_hors_du_site_refuse_et_garde_la_coupe(tmp_path, monkeypatch):
    """Aucun repli silencieux, et aucune perte : la coupe d'avant reste en place.

    Le tracé, lui, efface la coupe retenue quand il échoue. Un clic mal placé ne
    doit pas coûter la coupe qui était bonne.
    """
    carte = _carte_cliquable(monkeypatch)
    application = _plan_importe(tmp_path, monkeypatch)
    avant = application.session_state["coupe_be"].geometrie.wkt

    _cliquer(application, "Déplacer la coupe")
    application = application.run()

    milieu = application.session_state["coupe_be"].geometrie.interpolate(
        0.5, normalized=True
    )
    carte["point"] = (milieu.x + 4_000.0, milieu.y)
    application = application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    erreurs = [erreur.value for erreur in application.error]
    assert any("ne traverse pas l'emprise clôturée" in e for e in erreurs), erreurs
    assert application.session_state["coupe_be"].geometrie.wkt == avant
    assert application.session_state["origine_coupe"] == "defaut"


def _calques(carte, nom: str) -> list:
    """Les enfants de la carte folium portant ce nom d'élément."""
    if carte is None:
        return []
    return [
        enfant
        for enfant in carte._children.values()
        if getattr(enfant, "_name", None) == nom
    ]


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_le_trait_d_apercu_n_apparait_qu_une_fois_le_geste_arme(tmp_path, monkeypatch):
    """Un trait qui suivrait la souris en permanence serait du bruit.

    Il est posé sur la carte à l'armement et retiré à l'annulation, puisque la
    carte est recomposée à chaque exécution du script. Ce qui se passe ensuite —
    le trait qui suit la souris — est du JavaScript Leaflet, et ne remonte jamais
    à Streamlit : c'est tout l'intérêt, et c'est mesuré côté module.
    """
    carte = _carte_cliquable(monkeypatch)
    application = _plan_importe(tmp_path, monkeypatch)
    assert not _calques(carte["carte"], "ApercuCoupeAuSurvol")

    _cliquer(application, "Déplacer la coupe")
    application = application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    assert len(_calques(carte["carte"], "ApercuCoupeAuSurvol")) == 1

    _cliquer(application, "Annuler le déplacement")
    application = application.run()

    assert not _calques(carte["carte"], "ApercuCoupeAuSurvol")


def test_le_clic_ne_remonte_pas_la_carte():
    """La carte garde sa clé après une translation, donc son zoom.

    Ce que les deux tests du clic ne peuvent pas voir : le composant y est
    remplacé, et il ignore la clé qu'on lui passe. La clé porte un compteur qui
    change à chaque coupe retenue par un *tracé*, pour chasser le trait Leaflet
    résiduel qui se superposait sinon à la coupe redressée. Un clic ne laisse
    aucun trait résiduel : la remonter ferait perdre son zoom au chef de projet
    pour rien.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    debut = source.index("if _geste_arme() is None:")
    fin = source.index('if trace is not None and st.button("Corriger')
    bloc = source[debut:fin]

    assert "translater_ligne_coupe(" in bloc
    assert "_retenir_clic(clic)" in bloc
    assert "_desarmer_geste()" in bloc
    # La coupe retenue n'est pas effacée par un clic refusé, contrairement au
    # tracé : c'est le seul endroit où les deux chemins diffèrent.
    assert "coupe_be = None" not in bloc
    assert "tour_carte" not in bloc


def test_la_carte_ne_relance_plus_le_script_pour_un_zoom():
    """`returned_objects` restreint la carte à ce que cet écran lit vraiment.

    Vérifié le 15/09/2026 dans le bundle de `streamlit-folium` 0.27.2 : la charge
    renvoyée est filtrée sur cette liste, puis comparée à la précédente, et
    `setComponentValue` n'est appelé que si elle a changé. Laisser passer le
    cadrage et le zoom relançait le script au moindre déplacement de la carte.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    debut = source.index("resultat_carte = st_folium(")
    fin = source.index("trace = trace_l93(resultat_carte)")
    appel = source[debut:fin]

    assert "returned_objects=" in appel
    for lu in ("last_clicked", "all_drawings", "last_active_drawing"):
        assert f'"{lu}"' in appel, lu
    for inutile in ("bounds", "zoom", "last_object_clicked", "selected_layers"):
        assert f'"{inutile}"' not in appel, inutile


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


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_la_notice_se_depose_en_section_3(tmp_path, monkeypatch):
    """La section 3 est devenue l'endroit où l'on dépose ce que l'outil ne dessine pas.

    Déposer la notice n'y lève pas : la génération, elle, est mesurée par le
    test réseau qui suit, parce qu'elle télécharge les fonds IGN.
    """
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(
        application, "DP 11", ("notice.pdf", _notice_pdf(), "application/pdf")
    )
    application = application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    assert _televersement(application, "DP 11").label.startswith("DP 11 — Notice")
    # Déposée, elle ne fait plus l'objet du rappel.
    rappels = [avertissement.value for avertissement in application.warning]
    assert not any("Aucune notice DP 11" in m for m in rappels), rappels


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_l_absence_de_notice_avertit_sans_bloquer(tmp_path, monkeypatch):
    """Le dépôt est en mise au point : rien ne bloque sur une pièce manquante.

    L'avertissement est le seul garde-fou, et il doit donc être là — sans lui,
    un dossier partirait incomplet sans que rien ne l'ait dit. Le bouton de
    génération, lui, reste offert.
    """
    application = _import_valide(tmp_path, monkeypatch)

    assert not application.exception, [str(e.value) for e in application.exception]
    rappels = [avertissement.value for avertissement in application.warning]
    assert any("Aucune notice DP 11" in message for message in rappels), rappels
    assert not [
        erreur.value for erreur in application.error if "notice" in erreur.value
    ]
    assert _bouton_present(application, "Générer le dossier")


@pytest.mark.reseau
@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_un_dossier_sans_notice_se_produit_quand_meme(tmp_path, monkeypatch):
    """Critère de validation n°6 du lot 5, sur le parcours complet.

    Le dossier sort, sans la pièce DP 11, et le rapport dit qu'il est incomplet
    pour le dépôt. C'est le seul endroit où le chef de projet peut s'en
    apercevoir avant de déposer.
    """
    application = _import_valide(tmp_path, monkeypatch)
    _cliquer(application, "Générer le dossier")
    application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    rapport = application.session_state["dossier_genere"]["rapport"]
    assert rapport.notice is None
    assert any(
        "incomplet pour le dépôt" in message for message in rapport.avertissements
    ), rapport.avertissements
    assert "DP 11" not in [entree["numero"] for entree in rapport.sommaire]


@pytest.mark.reseau
@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_la_notice_deposee_se_retrouve_dans_l_archive(tmp_path, monkeypatch):
    """Critère de validation n°8 du lot 5, sur le parcours complet.

    Déposer la notice, générer, et la retrouver dans le ZIP téléchargé : c'est
    ce que fait le chef de projet, et rien d'autre ne le vérifie.
    """
    import io
    import zipfile

    from pypdf import PdfReader

    application = _import_valide(tmp_path, monkeypatch)
    _televerser(
        application, "DP 11", ("notice.pdf", _notice_pdf(pages=2), "application/pdf")
    )
    application = application.run()
    _cliquer(application, "Générer le dossier")
    application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    genere = application.session_state["dossier_genere"]
    noms = zipfile.ZipFile(io.BytesIO(genere["archive"])).namelist()
    assert "planches/DP_11_notice.pdf" in noms, noms

    # La notice ferme le dossier, sur ses deux pages, et le sommaire les
    # annonce ensemble.
    rapport = genere["rapport"]
    assert rapport.notice["pages"] == 2
    assert rapport.sommaire[-1]["numero"] == "DP 11"
    assemble = PdfReader(str(rapport.assemblage))
    assert len(assemble.pages) == rapport.sommaire[-1]["page"] + 1

    # Le texte de la notice est encore du texte dans le dossier assemblé.
    derniere = assemble.pages[-1].extract_text()
    assert "NOTICE DE SYNTHESE" in derniere, derniere


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
    # Une notice est déposée pour que le dossier produit soit complet : ce
    # test-ci porte sur les boutons de téléchargement, pas sur ce qui manque.
    _televerser(
        application, "DP 11", ("notice.pdf", _notice_pdf(), "application/pdf")
    )
    application = application.run()
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
