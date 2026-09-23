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
        "3 bis. La carte : placer et viser les prises de vue",
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

    assert "_couches_de_la_carte(plan, regler_la_coupe)" in bloc
    assert "_style_carte(style)" in bloc
    assert "emprise_cadastrale" in bloc

    # Le choix des catégories vit dans la fonction qui les reprojette — elles
    # ne le sont qu'une fois par import, et non à chaque exécution du script.
    debut = source.index("def _couches_de_la_carte(plan, regler_la_coupe: bool):")
    fin = source.index(chr(10) + "def ", debut + 1)
    couches = source[debut:fin]

    assert "for categorie in ORDRE_DESSIN:" in couches
    # Et ce qui n'ira pas sur la planche en est écarté : les modules, qu'un plan
    # compte par milliers, et les catégories que `palette.EXCLUES` retire —
    # installations de chantier et contours d'étude. Les montrer laissait croire
    # qu'ils partiraient au dossier (retour d'usage du 17/09/2026).
    assert "CATEGORIES_HORS_CARTE" in couches

    # Les arbres existants sortent de la carte des prises de vue, et d'elle
    # seule : la coupe DP 3 les dessine à 8 m quand elle les traverse, et les
    # cacher au moment de tracer reviendrait à choisir à l'aveugle ce qui sera
    # dessiné (objection du 19/09/2026, vérifiée dans `_vegetation_sur_le_profil`).
    assert "CATEGORIES_HORS_CARTE_DES_VUES" in couches
    assert "regler_la_coupe=True" in source   # la carte de la coupe les garde
    assert "regler_la_coupe=False" in source  # celle des prises de vue, non


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

    assert 'if not regler_la_coupe and _geste_arme() == "translation_coupe":' in fonction
    # Le trait, le bouton et le rappel sont tous tenus par le même drapeau.
    assert "if regler_la_coupe and st.session_state.coupe_be is not None:" in fonction
    assert "elif regler_la_coupe and st.button(" in fonction
    assert "if regler_la_coupe and st.session_state.coupe_be is None:" in fonction


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


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_viser_pose_un_cone_qui_suit_la_souris(tmp_path, monkeypatch):
    """« Rien ne m'indique dans quelle direction je vise. »

    Retour d'usage du 22/09/2026. Le bandeau annonçait le geste, mais la carte
    ne montrait rien : ni le point concerné, ni la direction en cours. Le cône
    d'aperçu est ancré à la photographie et pivote vers la souris — comme le
    trait de la coupe, et pour la même raison : tout se passe dans Leaflet, et
    rien ne remonte à Streamlit avant le clic.
    """
    carte = _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(
        application, "DP 8", [("visite.jpg", _image_geolocalisee(), "image/jpeg")]
    )
    application = application.run()
    assert not _calques(carte["carte"], "ApercuDeVisee")

    _cliquer(application, "🎯 Viser")
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    assert len(_calques(carte["carte"], "ApercuDeVisee")) == 1
    # Et pas celui du placement : un seul geste à la fois.
    assert not _calques(carte["carte"], "ApercuDePlacement")

    _cliquer(application, "Annuler")
    application = application.run()
    assert not _calques(carte["carte"], "ApercuDeVisee")


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_placer_pose_un_repere_qui_suit_la_souris(tmp_path, monkeypatch):
    """Le pendant du cône pour le placement, sur une photo sans position.

    Un photomontage n'a pas d'EXIF : il reste à placer, et c'est le cas où le
    geste sert vraiment.
    """
    carte = _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(application, "DP 8", [("montage.png", _image_png(), "image/png")])
    application = application.run()

    _cliquer(application, "📍 Placer")
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    assert len(_calques(carte["carte"], "ApercuDePlacement")) == 1
    # Sans position, aucun cône : viser depuis nulle part ne veut rien dire.
    assert not _calques(carte["carte"], "ApercuDeVisee")


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
    bloc = source[source.index("### Le plan importé, et la ligne de coupe"):]

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


# ---------------------------------------------------------------------------
# Les prises de vue des pièces photographiques (lot 6)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_une_photo_placee_et_visee_se_retrouve_dans_l_archive(tmp_path, monkeypatch):
    """Critère de validation n°6 du lot 6, sur le parcours complet.

    Déposer la photographie, la placer sur la carte, viser ce qu'elle regarde,
    générer, et retrouver la pièce dans le ZIP téléchargé : c'est ce que fait le
    chef de projet, et rien d'autre ne le vérifie de bout en bout.
    """
    import io as _io
    import zipfile

    carte = _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    # Deux photographies : DP 7 en porte exactement deux, et la seconde se
    # place seule par son EXIF. C'est la première que le parcours éprouve.
    _televerser(
        application,
        "DP 7",
        [
            ("vue-proche.jpg", _image_png(), "image/png"),
            (
                "vue-seconde.jpg",
                # Au bord du site de Saint-Cyr, dont le centre est à
                # 47,85273 / 1,97003 : un point de vue trop lointain ferait
                # refuser le plan de repérage, qui se cadre sur le site.
                _image_geolocalisee(lat=47.8540, lon=1.9670),
                "image/jpeg",
            ),
        ],
    )
    application = application.run()

    emprise = application.session_state["import_be"].plan.polygone_cloture
    centre = emprise.centroid

    # 📍 Placer : le clic dit où est la photographie.
    _cliquer(application, "📍 Placer")
    application = application.run()
    carte["point"] = (centre.x - 300.0, centre.y)
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    vue = application.session_state["vues_photo"]["DP 7"]["vue-proche.jpg"]
    assert vue["x"] == pytest.approx(centre.x - 300.0, abs=1.0)
    assert vue.get("cap_confirme") is not True

    # Le dépôt est réalimenté entre chaque geste : mesuré le 16/09/2026, un
    # `file_uploader` alimenté par `AppTest` perd sa valeur après un
    # `st.rerun()` programmatique, alors qu'un fichier déposé dans un navigateur
    # y survit. C'est une limite du harnais, pas du parcours — le même nom de
    # fichier conserve le point de vue déjà placé.
    carte["point"] = None
    # Deux photographies : DP 7 en porte exactement deux, et la seconde se
    # place seule par son EXIF. C'est la première que le parcours éprouve.
    _televerser(
        application,
        "DP 7",
        [
            ("vue-proche.jpg", _image_png(), "image/png"),
            (
                "vue-seconde.jpg",
                # Au bord du site de Saint-Cyr, dont le centre est à
                # 47,85273 / 1,97003 : un point de vue trop lointain ferait
                # refuser le plan de repérage, qui se cadre sur le site.
                _image_geolocalisee(lat=47.8540, lon=1.9670),
                "image/jpeg",
            ),
        ],
    )
    application = application.run()

    # 🎯 Viser : le second clic dit ce qu'elle regarde, et le cap s'en déduit.
    _cliquer(application, "🎯 Viser")
    application = application.run()
    carte["point"] = (centre.x, centre.y)
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    vue = application.session_state["vues_photo"]["DP 7"]["vue-proche.jpg"]
    assert vue["cap_confirme"] is True
    # La cible est plein est de la prise de vue : cap de 90°.
    assert vue["cap_deg"] == pytest.approx(90.0, abs=1.0)

    carte["point"] = None
    # Deux photographies : DP 7 en porte exactement deux, et la seconde se
    # place seule par son EXIF. C'est la première que le parcours éprouve.
    _televerser(
        application,
        "DP 7",
        [
            ("vue-proche.jpg", _image_png(), "image/png"),
            (
                "vue-seconde.jpg",
                # Au bord du site de Saint-Cyr, dont le centre est à
                # 47,85273 / 1,97003 : un point de vue trop lointain ferait
                # refuser le plan de repérage, qui se cadre sur le site.
                _image_geolocalisee(lat=47.8540, lon=1.9670),
                "image/jpeg",
            ),
        ],
    )
    application = application.run()
    _cliquer(application, "Générer le dossier")
    application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    genere = application.session_state["dossier_genere"]
    noms = zipfile.ZipFile(_io.BytesIO(genere["archive"])).namelist()
    assert "planches/DP_7_environnement_proche.pdf" in noms, (
        [m for m in genere["rapport"].avertissements if "DP 7" in m] or noms
    )
    assert "planches/DP_7_environnement_proche.pdf" in noms
    assert any(entree["numero"] == "DP 7" for entree in genere["rapport"].sommaire)


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_viser_avant_de_placer_est_refuse(tmp_path, monkeypatch):
    """Le cap se mesure depuis une position, pas depuis rien.

    Le bouton est désactivé tant que la photographie n'est pas placée : le test
    vérifie qu'il l'est, plutôt que d'éprouver un garde-fou que l'écran ne
    laisse pas atteindre.
    """
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(application, "DP 7", [("vue.jpg", _image_png(), "image/png")])
    application = application.run()

    viser = [b for b in application.button if "Viser" in b.label]
    assert viser, "le bouton de visée manque"
    assert viser[0].disabled


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_une_photo_remplacee_par_une_autre_oublie_son_point_de_vue(
    tmp_path, monkeypatch
):
    """Sinon la planche portait un repère pour une image qui n'est plus là.

    Le dépôt vide, lui, ne nettoie rien : il ne se distingue pas d'un dépôt
    momentanément vide, et `_photographies_du_projet` part de toute façon des
    fichiers déposés.
    """
    carte = _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(application, "DP 7", [("vue.jpg", _image_png(), "image/png")])
    application = application.run()
    _cliquer(application, "📍 Placer")
    application = application.run()
    emprise = application.session_state["import_be"].plan.polygone_cloture
    carte["point"] = (emprise.centroid.x, emprise.centroid.y)
    application = application.run()
    assert "vue.jpg" in application.session_state["vues_photo"]["DP 7"]

    carte["point"] = None
    _televerser(application, "DP 7", [("autre.jpg", _image_png(), "image/png")])
    application = application.run()
    assert "vue.jpg" not in application.session_state["vues_photo"]["DP 7"]


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_une_photo_geolocalisee_se_place_seule(tmp_path, monkeypatch):
    """L'EXIF d'une photographie de visite porte déjà sa position.

    La redemander au chef de projet serait lui faire saisir ce que le fichier
    contient. Le cap, lui, reste une proposition : aucun cône tant qu'il n'a pas
    été visé sur fond satellite.
    """
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(
        application,
        "DP 8",
        [("visite.jpg", _image_geolocalisee(cap=212.0), "image/jpeg")],
    )
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    vue = application.session_state["vues_photo"]["DP 8"]["visite.jpg"]
    assert vue["x"] is not None and vue["y"] is not None
    assert vue["origine_position"] == "exif"
    # Le cap est lu et proposé, mais il ne fait autorité pour personne.
    assert vue["cap_deg"] == pytest.approx(212.0, abs=0.5)
    assert vue["cap_confirme"] is False


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_une_photo_sans_exif_reste_a_placer(tmp_path, monkeypatch):
    """Un photomontage est un rendu : il n'a aucune position à livrer."""
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(application, "DP 8", [("montage.png", _image_png(), "image/png")])
    application = application.run()

    vue = application.session_state["vues_photo"]["DP 8"]["montage.png"]
    assert vue.get("x") is None
    assert vue["exif_lu"] is True


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_le_curseur_de_recadrage_se_retrouve_dans_le_projet(tmp_path, monkeypatch):
    """Ce que le chef de projet règle à l'écran doit atteindre la planche."""
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    # Deux rapports différents : l'emplacement prend leur médiane, et les deux
    # images doivent donc être rognées. Deux photographies de même rapport
    # n'auraient rien à rogner, et le curseur ne s'afficherait pas — c'est le
    # cas courant, celui d'un même appareil.
    _televerser(
        application,
        "DP 8",
        [
            ("visite.jpg", _image_geolocalisee(), "image/jpeg"),
            (
                "haute.jpg",
                _image_geolocalisee(taille=(160, 240)),
                "image/jpeg",
            ),
        ],
    )
    application = application.run()

    curseurs = [c for c in application.slider if "Recadrage" in c.label]
    assert curseurs, "le curseur de recadrage manque"
    curseurs[0].set_value(-30)
    application = application.run()
    assert application.session_state["vues_photo"]["DP 8"]["visite.jpg"][
        "cadrage"
    ] == pytest.approx(-0.30)


# ---------------------------------------------------------------------------
# Reprendre un rapport de visite photos-geoloc
# ---------------------------------------------------------------------------


def _affectations(application):
    """Les listes déroulantes de la galerie du rapport, dans l'ordre."""
    return [b for b in application.selectbox if b.label == "Affectation"]


def _carte_photos(points) -> bytes:
    """Une carte photos-geoloc minimale, avec de vraies images en base64."""
    import base64
    import io
    import json

    from PIL import Image

    def _image_base64(teinte):
        tampon = io.BytesIO()
        Image.new("RGB", (120, 80), teinte).save(tampon, format="JPEG")
        return base64.b64encode(tampon.getvalue()).decode("ascii")

    ecrits = []
    for rang, (nom, lat, lon, cap, manuel) in enumerate(points):
        point = {
            "id": rang, "nom": nom, "ordre": rang,
            "lat_brut": lat, "lon_brut": lon,
            "lat_manuel": None, "lon_manuel": None, "lat": lat, "lon": lon,
            "cap_brut": cap, "cap_manuel": cap if manuel else None,
            "cap": cap, "precision_m": None, "masque": False, "commentaire": "",
            "image": _image_base64((160 + 20 * rang, 180, 150)),
        }
        ecrits.append(point)
    donnees = {
        "version": 5, "titre": "Visite de site", "offset": 0.0,
        "emprise": None, "points": ecrits,
    }
    return (
        "<html><body>"
        + '<script id="donnees-carte" type="application/json">'
        + json.dumps(donnees, ensure_ascii=False)
        + "</script></body></html>"
    ).encode("utf-8")


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_un_rapport_de_visite_se_reprend_avec_ses_points_de_vue(tmp_path, monkeypatch):
    """L'entrée de premier choix du lot : le travail déjà fait ne se refait pas.

    Une direction **figée à la main** dans le rapport part confirmée ; elle fera
    donc dessiner un cône sans qu'on ait à viser de nouveau.
    """
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    # Saint-Cyr : un point tout près du site, un autre à plus d'un kilomètre.
    carte = _carte_photos([
        ("proche.jpeg", 47.85268, 1.96650, 212.0, True),
        ("lointaine.jpeg", 47.85793, 1.94968, None, False),
    ])
    _televerser(application, "Carte du rapport", ("rapport.htm", carte, "text/html"))
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    # Rien n'est retenu tant que le chef de projet n'a pas choisi : le bouton
    # reste hors d'atteinte, et c'est tout l'objet du défaut « Ne pas retenir ».
    reprendre = [b for b in application.button if "au projet" in b.label]
    assert reprendre and reprendre[0].disabled

    # Les widgets sont reconstruits à chaque exécution : la liste se relit à
    # chaque tour, sinon la seconde référence pointe sur un objet périmé et son
    # choix se perd en silence.
    for rang, piece_voulue in enumerate(("DP 7", "DP 8")):
        _affectations(application)[rang].set_value(piece_voulue)
        application = application.run()

    _cliquer(application, "Ajouter ces")
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    reprises = application.session_state["photos_reprises"]
    retenues = {nom for par_nom in reprises.values() for nom in par_nom}
    assert retenues == {"proche.jpg", "lointaine.jpg"}, reprises

    # La direction figée dans le rapport fait autorité, et rien d'autre.
    vues = application.session_state["vues_photo"]
    confirmes = [
        vue for par_nom in vues.values() for vue in par_nom.values()
        if vue.get("cap_confirme")
    ]
    assert len(confirmes) == 1
    assert confirmes[0]["cap_deg"] == pytest.approx(212.0, abs=0.5)


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_la_piece_proposee_suit_la_distance_au_site(tmp_path, monkeypatch):
    """La pièce est suggérée, jamais choisie d'office.

    DP 7 est l'environnement proche, DP 8 le paysage lointain.

    Chaque point se range donc seul, et le chef de projet ne corrige que ce qui
    n'est pas évident. Positions calculées le 16/09/2026 sur les bornes réelles
    de Saint-Cyr : 90 m du site pour la première, 1 396 m pour la seconde.
    """
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    carte = _carte_photos([
        ("proche.jpeg", 47.85268, 1.96650, None, False),
        ("lointaine.jpeg", 47.85793, 1.94968, None, False),
    ])
    _televerser(application, "Carte du rapport", ("rapport.htm", carte, "text/html"))
    application = application.run()

    # Rien n'est choisi d'avance : une visite de vingt-cinq photographies ne
    # doit pas en verser vingt-cinq au dossier parce que personne n'a rien dit.
    assert [boite.value for boite in _affectations(application)] == [
        "Ne pas retenir",
        "Ne pas retenir",
    ]
    # La distance au site est en revanche affichée, pour n'avoir à corriger que
    # ce qui n'est pas évident.
    suggestions = [c.value for c in application.caption if "suggère" in c.value]
    assert "**DP 7**" in suggestions[0] and "**DP 8**" in suggestions[1], suggestions


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_une_carte_illisible_est_refusee_sans_bloquer_l_ecran(tmp_path, monkeypatch):
    """Le chef de projet doit pouvoir corriger, pas se retrouver devant un mur."""
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(
        application, "Carte du rapport",
        ("pas-une-carte.htm", b"<html><body>bonjour</body></html>", "text/html"),
    )
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]
    assert any(
        "n'est pas une carte" in erreur.value for erreur in application.error
    ), [e.value for e in application.error]


# ---------------------------------------------------------------------------
# Le dépôt des fichiers, qui se rejoue à chaque interaction
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_un_fichier_inchange_n_est_pas_reecrit_a_chaque_interaction(
    tmp_path, monkeypatch
):
    """Signalé en usage réel le 16/09/2026, sur un PermissionError de OneDrive.

    `_deposer` vit dans le flux principal : il se rejouait donc à chaque clic, et
    réécrivait le DXF et le classeur — plusieurs dizaines de mégaoctets — pour
    rien. Dans un dossier synchronisé, le service tenait le fichier ouvert
    pendant son téléversement et l'écriture échouait.
    """
    _carte_cliquable(monkeypatch)
    application = _plan_importe(tmp_path, monkeypatch)
    depose = tmp_path / "projets" / "PV-SAINT-CYR" / DXF.name
    assert depose.exists(), "le DXF déposé est introuvable"

    ecrit_le = depose.stat().st_mtime_ns
    # Une interaction quelconque : le script se rejoue en entier.
    _cliquer(application, "Déplacer la coupe")
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]
    assert depose.stat().st_mtime_ns == ecrit_le, (
        "le DXF a été réécrit alors qu'il n'avait pas changé"
    )


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_un_fichier_efface_du_disque_est_reecrit(tmp_path, monkeypatch):
    """L'existence se vérifie, et pas seulement la mémoire de session.

    Sans cela, un fichier effacé entre deux exécutions n'était jamais réécrit, et
    la génération échouait plus tard sur un chemin qui ne mène nulle part.
    """
    _carte_cliquable(monkeypatch)
    application = _plan_importe(tmp_path, monkeypatch)
    depose = tmp_path / "projets" / "PV-SAINT-CYR" / DXF.name
    depose.unlink()

    _cliquer(application, "Déplacer la coupe")
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]
    assert depose.exists(), "le DXF effacé n'a pas été réécrit"


def test_un_fichier_verrouille_designe_la_vraie_cause(tmp_path, monkeypatch):
    """Un PermissionError brut est une trace que le chef de projet ne lit pas.

    Sous Windows la cause est presque toujours un autre programme qui tient le
    fichier — OneDrive, un antivirus, ou le logiciel qui l'a produit.
    """
    import sys

    sys.path.insert(0, str(RACINE)) if str(RACINE) not in sys.path else None
    from dp_socle.erreurs import ErreurDepot

    import app as application_module

    cible = tmp_path / "verrouille.dxf"

    def _refuser(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "write_bytes", _refuser)
    with pytest.raises(ErreurDepot, match="tient ouvert"):
        application_module._ecrire_depose(cible, b"peu importe")


# ---------------------------------------------------------------------------
# Le bruit des avertissements, et les photographies reprises
# ---------------------------------------------------------------------------


def test_les_messages_de_routine_se_replient():
    """Un avertissement qu'on ne lit plus ne protège plus de rien.

    Mesuré le 17/09/2026 sur le plan de Sarnois : vingt-deux messages, dont onze
    qui disaient seulement quels calques de travail avaient été écartés. Ils
    noyaient les quatre qui demandaient une action, dont deux écarts de surface
    de 100 %.
    """
    import sys

    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    espace = {}
    exec(  # noqa: S102 — la fonction est extraite du script, qui ne s'importe pas
        source[
            source.index("MOTIFS_DE_ROUTINE = (") : source.index(
                "def _tableau_controles("
            )
        ],
        espace,
    )
    trier = espace["_trier_les_avertissements"]

    _, a_lire, routine = trier([
        "16 calque(s) écarté(s) — fond cadastral du BE, remplacé par le WFS IGN : CAD_1",
        "10533 annotation(s) écartée(s) (4394 3DSOLID) : textes et cotations",
        "1 entité(s) sans calque écartée(s) (1 GEOMAPIMAGE).",
        "Surface de voie lourde : Écart de 100.0%, au-delà des 5% admis.",
        "Calque « ESPACE VERT » : 1 géométrie(s) invalide(s).",
    ])
    assert len(routine) == 3
    assert a_lire == [
        "Surface de voie lourde : Écart de 100.0%, au-delà des 5% admis.",
        "Calque « ESPACE VERT » : 1 géométrie(s) invalide(s).",
    ]


def test_un_message_de_forme_inconnue_reste_visible():
    """Le repli est sûr : ce qui n'est pas reconnu s'affiche.

    Le classement se fait sur le texte, ce qui est fragile. Un message dont la
    formulation change doit redevenir visible, jamais se replier en silence.
    """
    import sys

    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    espace = {}
    exec(  # noqa: S102
        source[
            source.index("MOTIFS_DE_ROUTINE = (") : source.index(
                "def _tableau_controles("
            )
        ],
        espace,
    )
    _, a_lire, routine = espace["_trier_les_avertissements"](
        ["Trois calques ont été laissés de côté"]
    )
    assert a_lire and not routine


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_une_vue_dp6_a_une_seule_image_est_signalee_avant_de_generer(
    tmp_path, monkeypatch
):
    """« DP 6 n'est pas dedans, j'avais pourtant choisi une image brute. »

    Retour d'usage du 22/09/2026. Le refus était juste — une insertion
    paysagère compare l'état actuel et le projet, une image seule ne compare
    rien — mais il tombait à la génération, au bout du parcours, dans le
    rapport. Il se dit maintenant là où le photomontage peut encore être
    déposé.
    """
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(
        application, "DP 6", [("brute.jpg", _image_geolocalisee(), "image/jpeg")]
    )
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    # L'EXIF l'a placée : elle compte, et il en manque donc une.
    assert application.session_state["vues_photo"]["DP 6"]["brute.jpg"]["x"]
    alertes = [a.value for a in application.warning]
    assert any("une seule photographie placée" in a for a in alertes), alertes
    assert any("photomontage" in a for a in alertes), alertes


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_une_vue_dp6_complete_ne_se_fait_rien_reprocher(tmp_path, monkeypatch):
    """Deux volets sur la même vue : la planche sortira, rien à signaler."""
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(
        application,
        "DP 6",
        [
            ("brute.jpg", _image_geolocalisee(), "image/jpeg"),
            ("montage.jpg", _image_geolocalisee(lat=47.9001), "image/jpeg"),
        ],
    )
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    # Les deux sont sur la vue A par défaut : c'est la même prise de vue.
    alertes = [a.value for a in application.warning]
    assert not any("une seule photographie placée" in a for a in alertes), alertes


@pytest.mark.skipif(not DXF.exists(), reason="jeu de référence absent")
def test_une_photo_reprise_du_rapport_se_place_et_se_recadre(tmp_path, monkeypatch):
    """Elle compte autant qu'une photographie déposée à la main.

    Signalé à l'usage le 17/09/2026 : le bloc ne comptait que les dépôts, et
    sortait en annonçant « aucune photographie » à un chef de projet qui venait
    d'en reprendre douze d'un rapport. Ni bouton pour les placer, ni curseur pour
    les recadrer — alors qu'elles s'affichaient bien sur la carte.
    """
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    carte = _carte_photos([("proche.jpeg", 47.85268, 1.96650, 212.0, True)])
    _televerser(application, "Carte du rapport", ("rapport.htm", carte, "text/html"))
    application = application.run()
    _affectations(application)[0].set_value("DP 7")
    application = application.run()
    _cliquer(application, "Ajouter ces")
    application = application.run()
    assert not application.exception, [str(e.value) for e in application.exception]

    assert _bouton_present(application, "📍 Placer"), [
        b.label for b in application.button
    ]
    assert _bouton_present(application, "🎯 Viser")
    # Son image du rapport a déjà le rapport de son emplacement : il n'y a rien
    # à rogner, et c'est ce que la ligne dit à la place du curseur. L'un ou
    # l'autre prouve que la photographie reprise est bien rendue.
    legendes = [c.value for c in application.get("caption")]
    curseurs = [c for c in application.slider if "Recadrage" in c.label]
    assert curseurs or any("Rien à rogner" in legende for legende in legendes), (
        legendes
    )


def test_un_curseur_de_recadrage_ne_s_affiche_que_s_il_peut_rogner(
    tmp_path, monkeypatch
):
    """« Le recadrage ne fonctionne pas, je bouge le curseur et il ne se passe
    rien. » Retour d'usage du 22/09/2026 — et pour cause.

    L'emplacement de la planche prend le rapport **médian** des photographies
    d'une pièce. Quand elles viennent toutes du même appareil, elles ont toutes
    ce rapport : il n'y a rien à retirer, et le curseur n'a rien à déplacer.
    Un curseur qui ne peut rien faire doit le dire.
    """
    _carte_cliquable(monkeypatch)
    application = _import_valide(tmp_path, monkeypatch)
    _televerser(
        application, "DP 8", [("visite.jpg", _image_geolocalisee(), "image/jpeg")]
    )
    application = application.run()

    assert not [c for c in application.slider if "Recadrage" in c.label]
    legendes = [c.value for c in application.get("caption")]
    assert any("Rien à rogner" in legende for legende in legendes), legendes


def test_les_demandes_au_bureau_d_etudes_sont_rassemblees():
    """« Comme je ne serai pas toujours là pour vérifier les plans. »

    Un chef de projet qui reçoit un plan incomplet doit savoir exactement quoi
    redemander, sans trier lui-même une vingtaine de remarques ni connaître le
    DXF. La demande est recopiable telle quelle, et nomme ce qu'elle concerne.
    """
    import sys

    if str(RACINE) not in sys.path:
        sys.path.insert(0, str(RACINE))
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    espace = {}
    exec(  # noqa: S102
        source[
            source.index("MOTIFS_DE_ROUTINE = (") : source.index(
                "def _trancher_les_voiries("
            )
        ],
        espace,
    )
    au_be, a_lire, routine = espace["_trier_les_avertissements"]([
        "Calque « PVcase Road » : 13 remplissage(s) HATCH et aucune polyligne. "
        "L'élément serait perdu — à demander au bureau d'études : le contour de "
        "cet élément, en polyligne fermée.",
        "16 calque(s) écarté(s) — fond cadastral du BE : CAD_1",
        "Calque « UNI_Cloture » : 1 sommet(s) dupliqué(s).",
    ])
    assert len(au_be) == 1 and len(routine) == 1 and len(a_lire) == 1
    # La demande porte ce qu'elle concerne : « le contour de cet élément » seul
    # ne dirait pas de quel élément il s'agit.
    demande = espace["_demande_au_be"](au_be[0])
    assert demande.startswith("Calque « PVcase Road » —")
    assert "polyligne fermée" in demande
    assert "HATCH" not in demande
