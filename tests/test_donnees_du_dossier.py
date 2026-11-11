"""Les données qui ont produit un dossier, rangées dans son `.pptx`.

Le critère n'est pas qu'une partie s'ajoute au paquet, mais qu'un fichier
**enregistré** se relise en une fiche et un contrat que l'outil recharge : les
données sont donc écrites, le fichier enregistré puis rouvert, les données
dépliées et rechargées par `Projet.charger` et `charger_contrat`, ceux-là mêmes
que la génération appelle. La régénération d'un dossier entier à partir de ses
seules données est mesurée dans `test_sortie_pptx_lot8.py`, qui produit déjà ce
dossier une fois pour tout son module.
"""

from __future__ import annotations

import base64
import dataclasses
import io
import re
import zipfile
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.opc.constants import CONTENT_TYPE as CT
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI
from shapely.geometry import box

from dp_socle import ajout_notice
from dp_socle import donnees_du_dossier as donnees
from dp_socle.contrat import NOM_PARAMETRES, archiver_le_contrat, charger_contrat
from dp_socle.environnement import version_deployee
from dp_socle.erreurs import ErreurReprise
from dp_socle.geometrie import charger_emprise
from dp_socle.import_be import NOM_GEOPACKAGE
from dp_socle.projet import Projet

from . import contrat_synthetique as synthese

NOM = "PV-TÉMOIN"


def _emprise(dossier: Path, nom: str, pilote: str) -> Path:
    """L'emprise cadastrale du site de synthèse, élargie de 60 m, comme au lot 8."""
    import geopandas as gpd

    x0, y0 = synthese.ORIGINE_L93
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / nom
    gpd.GeoDataFrame(
        geometry=[
            box(
                x0 - 60, y0 - 60,
                x0 + synthese.LARGEUR_SITE_M + 60,
                y0 + synthese.HAUTEUR_SITE_M + 60,
            )
        ],
        crs="EPSG:2154",
    ).to_file(chemin, driver=pilote)
    return chemin


def _notice(chemin: Path) -> Path:
    from pypdf import PdfWriter

    chemin.parent.mkdir(parents=True, exist_ok=True)
    ecrivain = PdfWriter()
    ecrivain.add_blank_page(width=595, height=842)
    with open(chemin, "wb") as fichier:
        ecrivain.write(fichier)
    return chemin


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """Un projet rangé comme l'application le range.

    La fiche et ce qui a été déposé dans `projets/{nom}/`, la notice dans son
    sous-dossier `DP_11/` ; le contrat dans `sortie/{nom}/`. La fiche porte une
    valeur pour chaque saisie de l'écran : c'est ce qu'une reprise ne doit pas
    avoir à redemander.

    Écrit une fois pour le module : le contrat de synthèse coûte deux secondes,
    et aucun test ne modifie ce qu'il contient — ceux qui ajoutent un fichier à
    côté de l'emprise ne la remplacent pas.
    """
    tmp_path = tmp_path_factory.mktemp("donnees")
    dossier_projet = tmp_path / "projets" / NOM
    contrat = synthese.ecrire(tmp_path / "sortie" / NOM)
    projet = Projet(
        nom=NOM,
        commune="Témoin",
        code_postal="45000",
        date="2026-11-11",
        emprise=str(_emprise(dossier_projet, "emprise.geojson", "GeoJSON")),
        libelle="PV TÉMOIN IND02",
        voirie="piste_lourde",
        notice=str(_notice(dossier_projet / "DP_11" / "notice.pdf")),
        legendes={"cloture": "Clôture grillagée de 2 m"},
        surelevation_locaux_m=0.6,
        phec_locaux_m=0.4,
        fondation_longrines=True,
        nb_photomontages=2,
        zooms_photomontages=("proche", "eloigne"),
        mesures_paysageres=True,
    )
    projet.valider()
    return projet, contrat.dossier


def _contrat(site) -> bytes:
    """Le contrat tel que la génération le met de côté, au moment de le lire."""
    _, dossier_contrat = site
    return archiver_le_contrat(dossier_contrat, NOM)


def _enregistre(presentation) -> Presentation:
    """Le fichier tel qu'il quitte le serveur, puis tel qu'on le rouvre."""
    tampon = io.BytesIO()
    presentation.save(tampon)
    return Presentation(io.BytesIO(tampon.getvalue()))


def _emporte(site, projet=None) -> Presentation:
    presentation = Presentation()
    messages = donnees.emporter_les_donnees(
        presentation, projet or site[0], _contrat(site)
    )
    assert messages == []
    return _enregistre(presentation)


# ---------------------------------------------------------------------------
# Ce que le fichier emporte
# ---------------------------------------------------------------------------


def test_le_fichier_enregistre_emporte_l_emprise_et_le_contrat_a_l_octet(site):
    """Les fichiers mêmes, et non une relecture : un contrat relu puis récrit
    pourrait différer de celui qui a produit les planches sans que rien ne le
    montre."""
    projet, dossier_contrat = site

    lues = donnees.lire_les_donnees(_emporte(site))

    assert lues is not None
    assert (
        lues.fichiers["fiche/emprise/emprise.geojson"]
        == projet.chemin_emprise.read_bytes()
    )
    for nom in (NOM_GEOPACKAGE, NOM_PARAMETRES):
        assert (
            lues.fichiers[f"contrat/{NOM}/{nom}"]
            == (dossier_contrat / nom).read_bytes()
        ), nom


def test_la_fiche_depliee_se_recharge_avec_chaque_saisie(site, tmp_path):
    """Tout ce que le chef de projet a saisi revient, sauf les chemins.

    L'emprise est la copie emportée, et la notice n'est pas suivie : elle est
    déjà dans le fichier, en pages, et pèserait plus que tout le reste.

    La référence est la fiche que l'application écrit elle-même, relue : un
    `projet.json` rend ses n-uplets en listes, et c'est cette forme-là qu'une
    régénération a toujours reçue.
    """
    projet, _ = site
    reference = Projet.charger(projet.ecrire(tmp_path / "temoin" / "projet.json"))

    deplie = donnees.deplier_les_donnees(
        donnees.lire_les_donnees(_emporte(site)), tmp_path / "reprise"
    )
    relu = Projet.charger(deplie.fiche)

    attendu = dataclasses.asdict(reference)
    obtenu = dataclasses.asdict(relu)
    for champ in ("emprise", "notice"):
        attendu.pop(champ)
        obtenu.pop(champ)
    assert obtenu == attendu
    assert relu.notice is None
    assert Path(relu.emprise).read_bytes() == projet.chemin_emprise.read_bytes()
    assert Path(relu.emprise).is_relative_to((tmp_path / "reprise").resolve())


def test_le_contrat_deplie_se_recharge_la_ou_la_generation_le_cherche(site, tmp_path):
    """`generer_pptx` lit le contrat dans `{sortie}/{nom}/` : c'est là qu'il se
    déplie, pour qu'une reprise n'ait rien à déplacer."""
    projet, dossier_contrat = site

    deplie = donnees.deplier_les_donnees(
        donnees.lire_les_donnees(_emporte(site)), tmp_path / "reprise"
    )

    original = charger_contrat(dossier_contrat, voirie=projet.voirie)
    repris = charger_contrat(deplie.sortie / NOM, voirie=projet.voirie)
    assert repris.donnees == original.donnees
    assert {nom: len(objets) for nom, objets in repris.couches.items()} == {
        nom: len(objets) for nom, objets in original.couches.items()
    }


def test_un_shapefile_emporte_ses_compagnons_et_eux_seuls(site, tmp_path):
    """Le `.shp` seul ne se lit pas : ses `.shx`, `.dbf` et `.prj` vont avec.

    C'est la forme que l'application garde quand le chef de projet dépose les
    fichiers un à un plutôt qu'en ZIP (`_enregistrer_fichiers`). Mais elle range
    au même endroit le DXF du bureau d'études et le tableau bilan : un fichier
    qui porte le même nom sans être d'un shapefile reste derrière.
    """
    projet, _ = site
    dossier_projet = tmp_path / "projets" / NOM
    shapefile = dataclasses.replace(
        projet,
        emprise=str(_emprise(dossier_projet, "parcelles.shp", "ESRI Shapefile")),
    )
    (dossier_projet / "parcelles.dxf").write_bytes(b"0\nEOF\n")

    lues = donnees.lire_les_donnees(_emporte(site, shapefile))
    deplie = donnees.deplier_les_donnees(lues, tmp_path / "reprise")
    relu = Projet.charger(deplie.fiche)

    emportes = {Path(nom).suffix for nom in lues.fichiers if "/parcelles." in nom}
    assert {".shp", ".shx", ".dbf", ".prj"} <= emportes
    assert ".dxf" not in emportes
    assert (
        charger_emprise(relu.emprise).geometrie.area
        == pytest.approx(charger_emprise(shapefile.emprise).geometrie.area)
    )


def test_une_emprise_rangee_en_dossier_est_emportee(site, tmp_path):
    """`charger_emprise` lit un dossier qui porte un seul `.shp` ; un
    `projet.json` écrit à la main peut en désigner un."""
    projet, _ = site
    dossier = tmp_path / "parcellaire"
    _emprise(dossier, "parcelles.shp", "ESRI Shapefile")
    en_dossier = dataclasses.replace(projet, emprise=str(dossier))

    deplie = donnees.deplier_les_donnees(
        donnees.lire_les_donnees(_emporte(site, en_dossier)), tmp_path / "reprise"
    )
    relu = Projet.charger(deplie.fiche)

    assert Path(relu.emprise).is_dir()
    assert (
        charger_emprise(relu.emprise).geometrie.area
        == pytest.approx(charger_emprise(dossier).geometrie.area)
    )


def test_le_manifeste_dit_l_outil_qui_a_produit_et_ce_qui_n_est_pas_suivi(site):
    """Ce qui permettra de savoir, des mois après le dépôt, ce que le dossier
    contient — s'il a déjà ses cotes, par exemple — et ce qui est resté derrière.

    La version est celle du code **chargé**, et non celle du disque : c'est lui
    qui a dessiné les planches, et les deux divergent le temps d'un
    redémarrage (voir `environnement`).
    """
    manifeste = donnees.lire_les_donnees(_emporte(site)).manifeste

    assert manifeste["format"] == donnees.FORMAT
    assert manifeste["nom"] == NOM
    assert re.fullmatch(r"\d\d/\d\d/\d{4} à \d\d:\d\d", manifeste["outil"]["version"])
    assert manifeste["outil"]["commit"] == version_deployee().commit
    assert manifeste["outil"]["en_retard"] is False
    assert manifeste["non_emportes"]["notice"]["fichiers"] == ["notice.pdf"]


def test_un_projet_sans_plan_se_reprend_sans_plan(site, tmp_path):
    """Un dossier d'étude amont, réduit aux pièces DP 1, n'a pas de contrat.

    Sa reprise doit trouver « aucun plan », comme sa génération l'avait
    trouvé — et non le contrat qui se trouverait à ce moment dans le
    `sortie/` par défaut, celui d'un autre passage du même projet.
    """
    from dp_socle.sortie_pptx import _contrat_eventuel

    projet, _ = site
    presentation = Presentation()
    assert donnees.emporter_les_donnees(presentation, projet, None) == []

    lues = donnees.lire_les_donnees(_enregistre(presentation))
    deplie = donnees.deplier_les_donnees(lues, tmp_path / "reprise")
    contrat, message = _contrat_eventuel(deplie.sortie / NOM, Projet.charger(deplie.fiche))

    assert lues.manifeste["contrat"] is None
    assert contrat is None
    assert "Aucun plan importé" in message


def test_une_saisie_qui_depend_d_un_fichier_laisse_suit_son_fichier(site, tmp_path):
    """L'export HelioScope du lot 2 n'est pas emporté : le contrat qui en est
    issu l'est, et c'est lui qui porte le calage. Sa longitude ne peut pas
    rester seule — `Projet.valider` refuse un calage sans calepinage —, elle
    part au manifeste avec sa valeur."""
    projet, _ = site
    export = tmp_path / "calepinage.dxf"
    export.write_bytes(b"0\nEOF\n")
    cale = dataclasses.replace(
        projet, helioscope=str(export), longitude_calage=2.31, correction_nord_sud_m=1.5
    )

    lues = donnees.lire_les_donnees(_emporte(site, cale))
    relu = Projet.charger(donnees.deplier_les_donnees(lues, tmp_path / "reprise").fiche)

    assert (relu.helioscope, relu.longitude_calage, relu.correction_nord_sud_m) == (
        None, None, None,
    )
    assert lues.manifeste["non_emportes"]["helioscope"]["fichiers"] == ["calepinage.dxf"]
    assert lues.manifeste["valeurs_retirees"] == {
        "longitude_calage": 2.31,
        "correction_nord_sud_m": 1.5,
    }


def test_un_echec_se_dit_et_le_fichier_s_ecrit_quand_meme(site, tmp_path):
    """La règle des pièces manquantes : le rapport le dit, la génération va au
    bout. Le dossier est juste, il se reprendra seulement comme ceux d'avant."""
    projet, _ = site
    disparue = tmp_path / "emprise.geojson"
    disparue.write_bytes(projet.chemin_emprise.read_bytes())
    sans_emprise = dataclasses.replace(projet, emprise=str(disparue))
    disparue.unlink()
    presentation = Presentation()

    messages = donnees.emporter_les_donnees(presentation, sans_emprise, _contrat(site))

    assert len(messages) == 1
    assert "n'emporte pas" in messages[0] and "contrat" in messages[0]
    assert donnees.lire_les_donnees(_enregistre(presentation)) is None


# ---------------------------------------------------------------------------
# Ce que le fichier montre : rien de plus
# ---------------------------------------------------------------------------


def test_rien_ne_change_de_ce_que_le_fichier_montre(site):
    """Ni diapo, ni forme, ni l'identité du lot 7 : les données ne se voient pas."""
    projet, _ = site
    presentation = Presentation()
    diapo = presentation.slides.add_slide(presentation.slide_layouts[6])
    diapo.shapes.add_textbox(0, 0, 100, 100).text_frame.text = "repère"
    ajout_notice.ecrire_identite(presentation, projet)
    avant = _enregistre(presentation)

    assert donnees.emporter_les_donnees(presentation, projet, _contrat(site)) == []
    apres = _enregistre(presentation)

    assert donnees.lire_les_donnees(apres) is not None
    assert len(apres.slides) == len(avant.slides) == 1
    assert [f.name for f in apres.slides[0].shapes] == [
        f.name for f in avant.slides[0].shapes
    ]
    assert ajout_notice.lire_identite(apres) == ajout_notice.lire_identite(avant)
    assert apres.core_properties.title == avant.core_properties.title


def test_le_contrat_s_y_comprime(site):
    """Le GeoPackage se comprime de sept fois environ : les données de Sarnois,
    766 Ko de contrat brut, ajoutent 96 Ko au fichier (mesuré le 11/11/2026). Le
    fichier ne doit pas grossir du contrat brut, augmenté du tiers de la
    base64."""
    projet, dossier_contrat = site
    sans = io.BytesIO()
    Presentation().save(sans)
    avec = io.BytesIO()
    presentation = Presentation()
    assert donnees.emporter_les_donnees(presentation, projet, _contrat(site)) == []
    presentation.save(avec)

    assert donnees.lire_les_donnees(Presentation(io.BytesIO(avec.getvalue()))) is not None
    brut = sum(
        (dossier_contrat / nom).stat().st_size for nom in (NOM_GEOPACKAGE, NOM_PARAMETRES)
    )
    assert len(avec.getvalue()) - len(sans.getvalue()) < brut


# ---------------------------------------------------------------------------
# Les fichiers réels : d'autres parties, d'autres numéros
# ---------------------------------------------------------------------------


def _partie_de_sharepoint(presentation) -> None:
    """Une partie « custom XML » comme SharePoint en pose à l'ouverture.

    Relevé le 11/11/2026 : le `.pptx` de Sarnois en portait quatre, dont
    celle-ci, et la nôtre y prenait le numéro 9. Une lecture qui prendrait la
    première partie venue, ou la relation unique, lirait celle-ci.
    """
    paquet = presentation.part.package
    partie = Part(
        PackURI("/customXml/item1.xml"),
        CT.XML,
        paquet,
        b'<?mso-contentType?><FormTemplates xmlns="http://schemas.microsoft.com/'
        b'sharepoint/v3/contenttype/forms"><Display>DocumentLibraryForm</Display>'
        b"</FormTemplates>",
    )
    presentation.part.relate_to(partie, RT.CUSTOM_XML)
    partie.relate_to(
        Part(
            PackURI("/customXml/itemProps1.xml"),
            CT.OFC_CUSTOM_XML_PROPERTIES,
            paquet,
            b'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            b'<ds:datastoreItem ds:itemID="{6E1E2B4D-0000-4000-8000-000000000001}" '
            b'xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml">'
            b"<ds:schemaRefs/></ds:datastoreItem>",
        ),
        RT.CUSTOM_XML_PROPS,
    )


def test_les_parties_de_sharepoint_ne_trompent_pas_la_lecture(site):
    projet, _ = site
    presentation = Presentation()
    _partie_de_sharepoint(presentation)
    assert donnees.emporter_les_donnees(presentation, projet, _contrat(site)) == []

    tampon = io.BytesIO()
    presentation.save(tampon)
    with zipfile.ZipFile(io.BytesIO(tampon.getvalue())) as lu:
        noms = sorted(n for n in lu.namelist() if re.fullmatch(r"customXml/item\d+\.xml", n))
        assert donnees.ESPACE.encode() not in lu.read("customXml/item1.xml")
    lues = donnees.lire_les_donnees(Presentation(io.BytesIO(tampon.getvalue())))

    assert len(noms) == 2
    assert lues is not None and lues.manifeste["nom"] == NOM


def test_un_second_rangement_remplace_le_premier(site):
    """Après une reprise, les planches transplantées ne sont plus celles que
    décrivent les données : les ranger à nouveau doit les remplacer, et non en
    ajouter un second jeu que la lecture refuserait."""
    projet, _ = site
    presentation = Presentation()
    donnees.emporter_les_donnees(presentation, projet, _contrat(site))
    repris = dataclasses.replace(projet, libelle="PV TÉMOIN IND03")

    assert donnees.emporter_les_donnees(presentation, repris, _contrat(site)) == []
    lues = donnees.lire_les_donnees(_enregistre(presentation))

    assert '"libelle": "PV TÉMOIN IND03"' in lues.fichiers["fiche/projet.json"].decode()


# ---------------------------------------------------------------------------
# Ce que la lecture refuse
# ---------------------------------------------------------------------------


def test_un_dossier_d_avant_ne_porte_pas_de_donnees():
    assert donnees.lire_les_donnees(_enregistre(Presentation())) is None


def test_deux_jeux_de_donnees_levent_plutot_que_d_en_choisir_un(site):
    """Ce que l'outil n'écrit jamais — il remplace —, mais qu'un fichier peut
    porter : rien ne dirait lequel croire."""
    projet, _ = site
    presentation = Presentation()
    archive = donnees._archive(projet, _contrat(site))
    donnees._poser(presentation, archive)
    donnees._poser(presentation, archive)

    with pytest.raises(ErreurReprise, match="2 jeux de données"):
        donnees.lire_les_donnees(_enregistre(presentation))


def _recrit(presentation, remplacer) -> Presentation:
    """Le fichier enregistré, sa partie de données passée par `remplacer`.

    Par le ZIP et non par l'objet `python-pptx` : c'est ce que ferait un fichier
    abîmé, ou venu d'une autre version de l'outil.
    """
    tampon = io.BytesIO()
    presentation.save(tampon)
    sortie = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(tampon.getvalue())) as lu,
        zipfile.ZipFile(sortie, "w", zipfile.ZIP_DEFLATED) as ecrit,
    ):
        for membre in lu.infolist():
            contenu = lu.read(membre)
            if re.fullmatch(r"customXml/item\d+\.xml", membre.filename) and (
                donnees.ESPACE.encode() in contenu
            ):
                contenu = remplacer(contenu)
            ecrit.writestr(membre, contenu)
    return Presentation(io.BytesIO(sortie.getvalue()))


def _emporte_sans_enregistrer(site) -> Presentation:
    presentation = Presentation()
    donnees.emporter_les_donnees(presentation, site[0], _contrat(site))
    return presentation


def test_un_format_inconnu_leve_en_nommant_les_deux(site):
    abime = _recrit(
        _emporte_sans_enregistrer(site),
        lambda xml: xml.replace(b'format="1"', b'format="9"'),
    )

    with pytest.raises(ErreurReprise, match="format 9.*format 1"):
        donnees.lire_les_donnees(abime)


def test_des_donnees_tronquees_levent_au_lieu_de_disparaitre(site):
    """Une partie abîmée n'est pas une partie absente : rendre `None` ferait
    passer le dossier pour un dossier d'avant."""
    abime = _recrit(_emporte_sans_enregistrer(site), lambda xml: xml[: len(xml) // 2])

    with pytest.raises(ErreurReprise, match="illisibles"):
        donnees.lire_les_donnees(abime)


def test_un_flux_compresse_abime_leve_aussi(site):
    """Une base64 valide peut porter un flux qui ne se décompresse plus : c'est
    `zlib` qui lève alors, et non le ZIP.

    Un octet changé au hasard ne suffit pas à le montrer — il casse le plus
    souvent la somme de contrôle, que le ZIP signale lui-même (mesuré le
    11/11/2026). L'en-tête du premier bloc du manifeste reçoit donc le type
    réservé `11`, que tout décompresseur refuse.
    """
    import struct

    def alterer(xml: bytes) -> bytes:
        debut = xml.index(b">", xml.index(b"<donnees")) + 1
        fin = xml.index(b"</donnees>")
        archive = bytearray(base64.b64decode(xml[debut:fin]))
        longueur_nom, longueur_extra = struct.unpack("<HH", archive[26:30])
        archive[30 + longueur_nom + longueur_extra] |= 0b110
        return xml[:debut] + base64.b64encode(bytes(archive)) + xml[fin:]

    abime = _recrit(_emporte_sans_enregistrer(site), alterer)

    with pytest.raises(ErreurReprise, match="illisibles"):
        donnees.lire_les_donnees(abime)


def test_un_dossier_de_reprise_deja_occupe_est_refuse(site, tmp_path):
    """Les restes d'un dépliage précédent se mêleraient aux nouvelles données —
    un contrat d'hier sous un dossier qui n'en a pas."""
    lues = donnees.lire_les_donnees(_emporte(site))
    donnees.deplier_les_donnees(lues, tmp_path / "reprise")

    with pytest.raises(ErreurReprise, match="pas vide"):
        donnees.deplier_les_donnees(lues, tmp_path / "reprise")
