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


def _image_geolocalisee(lat=47.9, lon=1.94, cap=None, taille=(240, 160)) -> bytes:
    """Un JPEG minuscule portant une position GPS, comme une photo de visite.

    `taille` porte le rapport de l'image. Il décide du rognage : l'emplacement
    de la planche prend le rapport **médian** des photographies d'une pièce, et
    des images de même rapport ne se rognent donc pas du tout.
    """
    import io

    from PIL import Image

    image = Image.new("RGB", taille, (150, 180, 150))
    exif = image.getexif()
    gps = exif.get_ifd(0x8825)
    gps.update({
        1: "N", 2: (float(int(lat)), (lat % 1) * 60.0, 0.0),
        3: "E", 4: (float(int(lon)), (lon % 1) * 60.0, 0.0),
    })
    if cap is not None:
        gps.update({16: "T", 17: float(cap)})
    tampon = io.BytesIO()
    image.save(tampon, format="JPEG", exif=exif)
    return tampon.getvalue()


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
    # Un poste qui a déplacé ses dossiers de travail ne doit pas faire écrire
    # les tests ailleurs que dans leur dossier jetable.
    monkeypatch.delenv("DP_DOSSIER_TRAVAIL", raising=False)
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


def _televerser(application, debut_du_libelle: str, fichiers, remplacer=False):
    """Dépose un fichier, ou plusieurs, dans le dépôt désigné.

    Un code de pièce — « DP 6 », « DP 7 », « DP 8 » — désigne depuis le
    25/09/2026 le dépôt unique des photographies, et l'affectation à la pièce
    se pose en session : c'est ce que fait le chef de projet dans le tableau,
    et le composant qui la reçoit n'est pas pilotable par `AppTest`.
    """
    if debut_du_libelle in ("DP 6", "DP 7", "DP 8"):
        depot = _televersement(application, "Photographies et photomontages")
        # Les dépôts s'accumulent : le dépôt est unique, et deux appels
        # successifs pour deux pièces différentes doivent tout garder. On
        # mémorise les triplets plutôt que de relire le widget, qui rend des
        # `UploadedFile` que `set_value` ne sait pas reprendre.
        deja = (
            []
            if remplacer
            else [
                triplet
                for triplet in getattr(application, "_photos_deposees", [])
                if triplet[0] not in {f[0] for f in fichiers}
            ]
        )
        tous = deja + list(fichiers)
        application._photos_deposees = tous
        try:
            choix = dict(application.session_state["piece_de_la_photo"])
        except KeyError:
            choix = {}
        for fichier in fichiers:
            choix[fichier[0]] = debut_du_libelle
        application.session_state["piece_de_la_photo"] = choix
        return depot.set_value(tous)
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


def _saisir(application, libelle: str, valeur: str):
    """Renseigne le champ texte dont le libellé est exactement celui-là.

    Par le libellé et non par le rang : `text_input[0]` liait les tests à l'ordre
    des champs à l'écran, et une colonne déplacée les faisait écrire la commune
    dans le code postal sans rien casser de visible.
    """
    for champ in application.text_input:
        if champ.label == libelle:
            return champ.set_value(valeur)
    raise AssertionError(
        f"Aucun champ « {libelle} » parmi : "
        + (", ".join(c.label for c in application.text_input) or "aucun")
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
    """Étape 1 : la commune et le code postal sont saisis, l'emprise déposée.

    Les deux champs se remplissent ici depuis que l'interface n'a plus de valeurs
    par défaut : elle portait la commune et le code postal de Bray-Saint-Aignan,
    restes du premier jeu d'essai, et les tests s'appuyaient sur eux sans le dire.
    Un test qui dépend d'une valeur préremplie cesse de mesurer le parcours réel.
    """
    application = _application(tmp_path, monkeypatch).run()
    _saisir(application, "Commune", "SAINT CYR")
    _saisir(application, "Code postal", "45460")
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
        "3. Génération",
    ]
    assert _bouton_present(application, "Générer le dossier à finaliser")


def test_les_prerequis_sont_annonces_avant_toute_saisie(tmp_path, monkeypatch):
    """Le chef de projet sait ce qu'il doit rassembler avant de commencer.

    Replié depuis le 24/09/2026 : qui connaît l'outil n'a pas à le relire à
    chaque ouverture, et qui ne le connaît pas le déplie. Le contenu, lui,
    ne change pas — c'est lui qu'on mesure ici.
    """
    application = _application(tmp_path, monkeypatch).run()

    annonce = "\n".join(bloc.value for bloc in application.get("markdown"))
    titres = "".join(bloc.label for bloc in application.get("expander"))
    assert "À rassembler avant de commencer" in titres, titres
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


def _gestes_de_l_app():
    """`GESTES_CARTE` et `_signaler_le_geste` tirés du source de `app.py`.

    `app.py` est un script Streamlit : il ne s'importe pas. Le bloc des gestes
    ne dépend que de folium, et s'exécute donc seul.
    """
    import folium

    source = (RACINE / "app.py").read_text(encoding="utf-8")
    bloc = source[source.index("GESTES_CARTE = {") : source.index("def _armer_geste")]
    espace = {"folium": folium}
    exec(bloc, espace)  # noqa: S102 — code du dépôt, pas une entrée
    return espace


def test_un_geste_arme_se_voit_sur_la_carte_et_pas_seulement_au_dessus():
    """Retour d'usage du 19/09/2026 : « c'est toujours une main qui apparaît ».

    Le bandeau disait quel geste était armé, mais la carte gardait le curseur de
    déplacement de Leaflet et rien ne l'entourait : on ne voyait pas qu'elle
    attendait un clic. Le style s'injecte dans le document de la carte — le
    composant vit dans un cadre isolé qu'aucune feuille de style de Streamlit
    n'atteint.
    """
    import folium

    espace = _gestes_de_l_app()
    for geste, (_bouton, _bandeau, couleur) in espace["GESTES_CARTE"].items():
        carte = folium.Map(tiles=None)
        espace["_signaler_le_geste"](carte, geste)
        html = carte._repr_html_()
        assert "cursor:crosshair" in html, geste
        # Les trois classes de Leaflet, sans quoi la main revient dès que la
        # souris passe sur une table ou sur la clôture.
        for classe in (".leaflet-container", ".leaflet-grab", ".leaflet-interactive"):
            assert classe in html, (geste, classe)
        assert couleur in html, geste

    # Et la carte n'est signalée que lorsqu'un geste est armé : hors geste, elle
    # se déplace à la main comme n'importe quelle carte.
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    assert "if _geste_arme() is not None:\n        _signaler_le_geste(" in source


def test_la_carte_porte_toutes_les_categories_de_la_planche():
    """La carte dessine le plan aux couleurs de la légende DP, pas deux calques.

    Elle ne montrait que `tables_pv` et `cloture`, en dur : ni les pistes, ni les
    postes, ni la citerne, ni l'emprise cadastrale. Le contrôle se fait à la
    source — le contenu d'un composant `st_folium` n'est pas lisible depuis
    `AppTest`.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    debut = source.index("### Le plan importé, et la ligne de coupe")
    # La carte vit dans _carte_du_plan : la borne est la fin de cette fonction.
    fin = source.index(chr(10) + "def ", debut)
    bloc = source[debut:fin]

    assert "_couches_de_la_carte(plan)" in bloc
    assert "_style_carte(style, trait)" in bloc
    assert "emprise_cadastrale" in bloc

    # Le choix des catégories vit dans la fonction qui les reprojette — elles
    # ne le sont qu'une fois par import, et non à chaque exécution du script.
    debut = source.index("def _couches_de_la_carte(plan):")
    fin = source.index(chr(10) + "def ", debut + 1)
    couches = source[debut:fin]

    assert "for categorie in ORDRE_DESSIN:" in couches
    # Et ce qui n'ira pas sur la planche en est écarté : les modules, qu'un plan
    # compte par milliers, et les catégories que `palette.EXCLUES` retire —
    # installations de chantier et contours d'étude. Les montrer laissait croire
    # qu'ils partiraient au dossier (retour d'usage du 17/09/2026).
    assert "CATEGORIES_HORS_CARTE" in couches

    # Les arbres existants, eux, restent : la coupe DP 3 les dessine à 8 m quand
    # elle les traverse, et les cacher au moment de tracer reviendrait à choisir
    # à l'aveugle ce qui sera dessiné (objection du 19/09/2026, vérifiée dans
    # `_vegetation_sur_le_profil`). Ils étaient écartés de la carte des prises de
    # vue, qui n'existe plus depuis le 26/09/2026 : une seule carte, une seule
    # liste de couches.
    assert "CATEGORIES_HORS_CARTE_DES_VUES" not in couches
    assert "arbre_existant" not in couches


def test_un_axe_a_aplat_se_trace_en_trait_sur_la_carte():
    """Une haie du plan PDF est un axe : la carte la trace, elle ne la remplit pas.

    Remplie, elle colorait l'aire entre son tracé et sa corde — le navigateur
    ferme implicitement un chemin SVG rempli —, et l'axe n'avait que
    l'épaisseur du filet. Même règle que `palette.style_de` pour les planches :
    un linéaire d'une catégorie à aplat se trace dans la teinte de l'aplat.
    """
    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))
    from dp_socle.apercu_be import STYLES
    from dp_socle.planches.palette import EXCLUES

    source = (RACINE / "app.py").read_text(encoding="utf-8")
    espace = {"EXCLUES": EXCLUES}
    exec(  # noqa: S102 — la fonction est extraite du script, qui ne s'importe pas
        source[
            source.index("OPACITE_CARTE = ") : source.index(
                "#: Ce qui relève du fonctionnement normal de l'import"
            )
        ],
        espace,
    )
    style_carte, teinte = espace["_style_carte"], espace["_teinte"]

    def entite(type_geometrie, coordonnees):
        return {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": type_geometrie, "coordinates": coordonnees},
        }

    haie = STYLES["haie"]
    assert haie.remplissage is not None
    for axe in (
        entite("LineString", [[2.35, 47.84], [2.36, 47.85]]),
        entite("MultiLineString", [[[2.35, 47.84], [2.36, 47.85]]]),
    ):
        dessin = style_carte(haie, axe)
        assert dessin["fill"] is False
        assert dessin["color"] == teinte(haie.remplissage)
        assert dessin["weight"] >= espace["EPAISSEUR_AXE_CARTE_PX"]

    # Une surface garde le style de sa catégorie, inchangé.
    surface = entite("Polygon", [[[2.35, 47.84], [2.36, 47.84], [2.36, 47.85], [2.35, 47.84]]])
    assert style_carte(haie, surface) == {
        "color": teinte(haie.filet),
        "weight": max(haie.epaisseur, 1),
        "fill": True,
        "fillColor": teinte(haie.remplissage),
        "fillOpacity": espace["OPACITE_CARTE"],
    }
    assert style_carte(haie, surface) == style_carte(haie)
    # Un linéaire par nature, sans aplat — la clôture — garde le sien.
    cloture = STYLES["cloture"]
    assert style_carte(cloture, entite("LineString", [[2.35, 47.84], [2.36, 47.85]])) == (
        style_carte(cloture)
    )


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_la_coupe_quitte_l_ecran_une_fois_l_import_valide(tmp_path, monkeypatch):
    """« Une fois qu'on a validé, on ne parle plus de la coupe. »

    Retour d'usage du 22/09/2026 : le bouton « Déplacer la coupe » survivait à
    la validation et « venait polluer le reste du process ». La carte qui reste
    à l'écran ne sert plus qu'aux photographies — la coupe est figée, son
    bouton, son trait et ses consignes s'en vont avec elle.
    """
    _carte_cliquable(monkeypatch)
    avant = _plan_importe(tmp_path, monkeypatch)
    assert _bouton_present(avant, "Déplacer la coupe")

    apres = _import_valide(tmp_path, monkeypatch)
    assert not apres.exception, [str(e.value) for e in apres.exception]
    assert not _bouton_present(apres, "Déplacer la coupe")
    # La coupe est bien retenue : ce n'est pas qu'elle a disparu du dossier.
    assert apres.session_state["coupe_be"] is not None

    # Et plus une consigne à son sujet sur la carte des prises de vue.
    textes = [element.value for element in apres.get("markdown")]
    assert not any("Déplacer la coupe" in texte for texte in textes), [
        texte for texte in textes if "coupe" in texte
    ]


def test_un_geste_de_coupe_arme_ne_survit_pas_a_la_validation():
    """Armé avant de valider, il n'aurait plus de bouton pour l'annuler.

    Sa bannière réclamerait un clic que plus rien n'attend — le cas exact qui
    avait motivé la relance du script à l'armement.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    debut = source.index("def _carte_du_plan(")
    fin = source.index(chr(10) + "def ", debut + 1)
    fonction = source[debut:fin]

    assert 'if not avec_la_coupe and _geste_arme() == "translation_coupe":' in fonction
    # Le bouton et le rappel sont tenus par le même drapeau. Le trait de la coupe,
    # lui, ne l'est plus : il reste dessiné après la validation, où la carte sert
    # à vérifier le plan — et par où passe la coupe décide de la planche DP 3.
    assert 'if _geste_arme() == "translation_coupe" and avec_la_coupe:' in fonction
    assert "elif avec_la_coupe and st.button(" in fonction
    assert "if avec_la_coupe and st.session_state.coupe_be is None:" in fonction


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
    ferait rejouer le même clic à chaque interaction. Ici il vaut None, et le
    script se rejoue sans que la coupe bouge.
    """
    application = _plan_importe(tmp_path, monkeypatch)
    coupe_avant = application.session_state["coupe_be"].geometrie.wkt

    _cliquer(application, "Déplacer la coupe")
    application = application.run()
    # Streamlit rejoue le script à chaque interaction : deux tours suffisent à
    # faire ressortir un clic qui serait relu à chaque fois.
    for _ in range(2):
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


def test_le_cone_d_apercu_se_fige_au_clic_et_dit_ce_qu_il_attend():
    """Au clic, Streamlit met une à deux secondes à redessiner.

    « Quand on clique pour valider, on a l'impression que tout plante l'espace
    d'une seconde. » Le cône se fige donc dans sa position, prend sa couleur
    pleine, et la carte annonce ce qu'elle fait — exactement ce que le trait de
    la coupe fait depuis le 15/09/2026.
    """
    import folium

    from dp_socle.apercu_be import apercu_de_placement, apercu_de_visee

    for calque in (
        apercu_de_visee(47.9, 1.94, 50.0, 60.0, "#d81b8c"),
        apercu_de_placement("#d81b8c"),
    ):
        carte = folium.Map(tiles=None)
        calque.add_to(carte)
        html = carte._repr_html_()
        assert "fige = true" in html
        assert "cursor = " in html and "progress" in html
        # Le survol ne remonte jamais à Streamlit : c'est tout l'intérêt.
        assert "mousemove" in html
        assert "return_on_hover" not in html


def test_le_cone_d_apercu_pointe_vers_le_curseur_depuis_la_photographie():
    """Son sommet est la prise de vue, et lui seul : c'est ce qu'il montre."""
    import folium

    from dp_socle.apercu_be import SEGMENTS_CONE_APERCU, apercu_de_visee

    carte = folium.Map(tiles=None)
    apercu_de_visee(47.9, 1.94, 50.0, 60.0, "#d81b8c").add_to(carte)
    html = carte._repr_html_()

    assert "47.9" in html and "1.94" in html
    assert f"var n = {SEGMENTS_CONE_APERCU};" in html
    # La demi-ouverture est en radians, pas en degrés : 50° donne 0,436 rad.
    assert "0.436" in html


def test_le_clic_ne_remonte_pas_la_carte():
    """La carte garde sa clé après une translation, donc son zoom.

    Ce que les deux tests du clic ne peuvent pas voir : le composant y est
    remplacé, et il ignore la clé qu'on lui passe. La clé portait un compteur
    tant que le tracé polyligne existait, pour chasser le trait Leaflet résiduel
    qui se superposait à la coupe redressée. Le tracé retiré le 17/09/2026, ce
    trait n'existe plus : la clé est stable, et le zoom du chef de projet avec.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    debut = source.index("if _geste_arme() is None:")
    # La carte vit dans _carte_du_plan : la borne est la fin de cette fonction.
    fin = source.index(chr(10) + "def ", debut)
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
    fin = source.index("clic = _clic_neuf(resultat_carte)", debut)
    appel = source[debut:fin]

    assert "returned_objects=" in appel
    assert '"last_clicked"' in appel
    # Le tracé retiré, les dessins n'ont plus à revenir : les laisser passer
    # relancerait le script sans que rien ne les lise.
    for inutile in (
        "bounds", "zoom", "last_object_clicked", "selected_layers",
        "all_drawings", "last_active_drawing",
    ):
        assert f'"{inutile}"' not in appel, inutile


def test_la_coupe_ne_se_trace_plus_a_la_main():
    """Le tracé polyligne a été retiré le 17/09/2026, le clic l'a remplacé.

    Il n'était déjà plus qu'un déclencheur : en automatique, la position était
    recalculée sur le nombre de rangées et le tracé jeté. Son seul emploi
    restant — imposer une direction oblique — allongeait toutes les distances
    lues sur la planche, et le déplacement au clic tient la perpendiculaire.

    Ce qui disparaît avec lui : l'outil de dessin de la carte, le compteur qui la
    remontait pour chasser le trait résiduel, et le mode manuel.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    debut = source.index("### Le plan importé, et la ligne de coupe")
    # Jusqu'à la fin de _carte_du_plan, et pas jusqu'au bout du fichier : la
    # suite porte du dessin d'image qui n'a rien à voir avec la carte.
    bloc = source[debut : source.index(chr(10) + "def ", debut)]

    for disparu in ("Draw(", "trace_l93", "tour_carte", "manuel="):
        assert disparu not in bloc, disparu
    assert "trace_initial" not in bloc
    assert 'key="carte_coupe_be"' in bloc


# ---------------------------------------------------------------------------
# Les refus
# ---------------------------------------------------------------------------


def test_sans_emprise_la_generation_est_hors_de_portee(tmp_path, monkeypatch):
    """On ne peut plus lancer une génération que l'emprise ne cadrerait pas.

    Le clic était auparavant absorbé sans rien produire : ni planche, ni erreur,
    l'écran inchangé. La section n'existe plus, et l'écran dit ce qu'il attend.
    """
    application = _application(tmp_path, monkeypatch).run()
    _saisir(application, "Commune", "SAINT CYR")
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
    _saisir(application, "Commune", "")
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
    assert "3. Génération" in _titres(application)
    assert _bouton_present(application, "Générer le dossier")


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

    Le dossier sort, sans la pièce DP 11, et le rapport dit qu'il manque. C'est
    le seul endroit où le chef de projet peut s'en apercevoir avant de déposer.
    Mesuré sur la sortie PowerPoint depuis le 26/09/2026 : c'est la seule que
    l'interface produise.
    """
    application = _import_valide(tmp_path, monkeypatch)
    _cliquer(application, "Générer le dossier à finaliser")
    application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    rapport = application.session_state["pptx_genere"]["rapport"]
    assert rapport.notice is None
    assert any(
        "Aucune notice DP 11" in message for message in rapport.avertissements
    ), rapport.avertissements
    assert "DP 11" not in [entree["numero"] for entree in rapport.sommaire]


@pytest.mark.reseau
@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_la_notice_deposee_se_retrouve_dans_le_pptx(tmp_path, monkeypatch):
    """Critère de validation n°8 du lot 5, repris sur la sortie PowerPoint.

    Déposer la notice, générer, et la retrouver dans le fichier téléchargé :
    c'est ce que fait le chef de projet, et rien d'autre ne le vérifie.

    Ce que ce test ne peut plus affirmer, et qui est une perte assumée : que le
    texte de la notice reste du texte. Le `.pptx` la rastérise page par page
    (décision D6 du lot 8), et `tests/test_notice_lot5.py` continue de mesurer
    le texte dans le PDF de la pièce.
    """
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(
        application, "DP 11", ("notice.pdf", _notice_pdf(pages=2), "application/pdf")
    )
    application = application.run()
    _cliquer(application, "Générer le dossier à finaliser")
    application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    rapport = application.session_state["pptx_genere"]["rapport"]
    assert rapport.notice["pages"] == 2
    # La notice ferme le dossier, sur ses deux pages, et le sommaire l'annonce
    # une fois, à sa première page.
    assert rapport.sommaire[-1]["numero"] == "DP 11"
    notice = [diapo for diapo in rapport.diapos if diapo.code == "DP 11"]
    assert len(notice) == 2
    assert [d.numero for d in notice] == [
        rapport.sommaire[-1]["page"], rapport.sommaire[-1]["page"] + 1,
    ]
    assert rapport.fichier.exists()


@pytest.mark.reseau
@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_le_dossier_reste_telechargeable_apres_un_premier_clic(
    tmp_path, monkeypatch
):
    """Le compte rendu et son bouton survivent à la réexécution du script.

    Tout clic sur un bouton de téléchargement rejoue le script : `lancer_pptx`
    retombe à faux et le bloc `if lancer_pptx:` disparaît, bouton compris. Le
    chef de projet devait alors relancer une génération complète — fonds IGN
    compris — pour réessayer.

    Le rejeu est ici obtenu par un `run()` de plus, ce qu'est exactement une
    réexécution provoquée par un clic.
    """
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(
        application, "DP 11", ("notice.pdf", _notice_pdf(), "application/pdf")
    )
    application = application.run()
    _cliquer(application, "Générer le dossier à finaliser")
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    intitules = [bouton.label for bouton in application.get("download_button")]
    assert any("PowerPoint" in intitule for intitule in intitules), intitules

    # La réexécution que provoquerait un clic dessus.
    application.run()
    assert not application.exception, [str(e.value) for e in application.exception]
    survivants = [bouton.label for bouton in application.get("download_button")]
    assert any("PowerPoint" in intitule for intitule in survivants), survivants


def test_les_intitules_de_legende_se_corrigent_avant_de_generer(tmp_path, monkeypatch):
    """La légende est dessinée dans la planche : elle se retouche avant, ou jamais.

    La décision D1 du lot 8 la voulait éditable dans le `.pptx` ; elle ne l'est
    pas, et ne le sera pas sans redessiner les planches sans elle. Le recours est
    donc ici, à l'étape où le chef de projet vérifie le plan.

    Un champ par **intitulé** et non par catégorie : « Voie lourde » couvre la
    piste lourde et l'aire de grutage, et la planche n'en fait qu'une ligne.
    """
    application = _import_valide(tmp_path, monkeypatch)

    champs = {
        champ.label: champ
        for champ in application.text_input
        if "objet(s)" in champ.label
    }
    assert champs, [c.label for c in application.text_input]
    # L'intitulé par défaut est celui du dossier de référence, et il est proposé
    # tel quel : le chef de projet corrige, il ne saisit pas tout.
    for libelle, champ in champs.items():
        assert champ.value == libelle.split(" — ")[0]

    premier = next(iter(champs.values()))
    premier.set_value("Emprise du parc solaire")
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    # La clé porte le nom du dépôt : une correction faite sur un projet ne suit
    # pas le chef de projet quand il en ouvre un autre.
    assert application.session_state[premier.key] == "Emprise du parc solaire"
    assert premier.key.startswith("legende_")
    assert "SAINT-CYR" in premier.key.upper()


def test_la_seule_sortie_offerte_est_le_pptx_a_finaliser(tmp_path, monkeypatch):
    """Un seul bouton de génération, et c'est celui du `.pptx`.

    Le bouton du PDF assemblé a été retiré le 26/09/2026 avec le dépôt des
    photographies. Ce n'est pas un renoncement à la voie PDF, qui reste sous
    tests : c'est qu'elle ne peut plus être juste depuis ici, faute de
    photographies pour DP 6, DP 7 et DP 8. Elle sortirait un dossier amputé de
    trois pièces, d'apparence complète.
    """
    application = _import_valide(tmp_path, monkeypatch)

    libelles = [bouton.label for bouton in application.button]
    generations = [l for l in libelles if l.startswith("Générer")]
    assert generations == ["Générer le dossier à finaliser (PowerPoint)"], libelles


@pytest.mark.reseau
@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_la_sortie_powerpoint_se_telecharge_sans_photographie(tmp_path, monkeypatch):
    """La raison d'être du lot 8 : un dossier téléchargeable sans les photos.

    Aucune prise de vue n'est déposée, et les pièces photographiques sortent
    quand même — cadres vides, plan de repérage imprimé, repères à poser. Le
    compte rendu dit ce qui n'est plus vérifié.
    """
    from dp_socle.sortie_pptx import AVERTISSEMENTS_DE_PRINCIPE

    application = _import_valide(tmp_path, monkeypatch)
    _cliquer(application, "Générer le dossier à finaliser")
    application.run()

    assert not application.exception, [str(e.value) for e in application.exception]
    rapport = application.session_state["pptx_genere"]["rapport"]
    assert rapport.fichier.name.endswith("_DP_a_finaliser.pptx")
    assert {"DP 6", "DP 7", "DP 8"} <= {diapo.code for diapo in rapport.diapos}
    for phrase in AVERTISSEMENTS_DE_PRINCIPE:
        assert phrase in rapport.avertissements

    intitules = [bouton.label for bouton in application.get("download_button")]
    assert any("PowerPoint" in intitule for intitule in intitules), intitules


@pytest.mark.reseau
@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_un_intitule_corrige_se_retrouve_dans_le_projet(tmp_path, monkeypatch):
    """La retouche de légende part au `projet.json`, et donc aux planches.

    Conservée plutôt que consommée : une régénération ne redemande pas au chef de
    projet de récrire ce qu'il a déjà écrit.
    """
    import json

    application = _import_valide(tmp_path, monkeypatch)
    champ = next(c for c in application.text_input if "objet(s)" in c.label)
    intitule = champ.label.split(" — ")[0]
    champ.set_value("Voie de desserte")
    application = application.run()

    _cliquer(application, "Générer le dossier à finaliser")
    application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    nom = application.session_state["pptx_genere"]["nom"]
    donnees = json.loads(
        (tmp_path / "projets" / nom / "projet.json").read_text(encoding="utf-8")
    )
    assert "Voie de desserte" in donnees["legendes"].values(), donnees["legendes"]
    # L'intitulé d'origine, lui, n'est pas retenu : une correction qui ne corrige
    # rien n'a pas à encombrer le fichier.
    assert intitule not in donnees["legendes"].values()


# ---------------------------------------------------------------------------
# Ce que le retrait du volet photographique laisse derrière lui
# ---------------------------------------------------------------------------
#
# Un millier de lignes de tests vivaient ici : le dépôt des photographies par
# deux portes, la reprise d'un rapport `photos-geoloc`, le placement et la visée
# sur la carte, le cadrage au clic, et le bruit des avertissements qui les
# accompagnait. Les sections qu'ils mesuraient ont été retirées de l'interface
# le 26/09/2026 : le volet photographique se traite dans le `.pptx` du lot 8.
#
# Ce qui les remplace n'est pas rien, et n'est pas ici : `tests/test_sortie_pptx_lot8.py`
# mesure les cadres vides, leurs intitulés et les repères de vue dans le fichier
# produit, et `tests/test_photographies_lot6.py` continue de mesurer les planches
# DP 6 à DP 8 elles-mêmes. Ce qui n'est plus mesuré nulle part, parce que plus
# personne ne le fait, c'est le contrôle de la position d'un cône contre l'EXIF
# de sa photographie.
