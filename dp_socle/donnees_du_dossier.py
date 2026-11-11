"""Les données qui ont produit un dossier, rangées dans son `.pptx`.

POURQUOI
--------
Le serveur ne garde rien. À la fermeture de l'onglet, la fiche du projet — ce
qui a été saisi à l'écran : intitulés de légende retouchés, voiries, hauteurs
du PPRI, fondations, photomontages — et l'emprise déposée sont perdues. Le
contrat redescend dans l'archive (`contrat.archiver_le_contrat`), mais une
archive s'égare ; le `.pptx` finalisé, lui, est ce que l'agence garde. Les
premières demandes de compléments, le 11/11/2026 — les cotes du lot 10, sur des
dossiers déjà déposés —, ont montré ce que coûte cette perte : reconstituer
chaque saisie avec le chef de projet, sans certitude de retrouver l'indice du
plan qui a produit les planches.

Chaque `.pptx` emporte donc, invisible, de quoi régénérer ses planches : la
fiche, l'emprise et le contrat, avec la version de l'outil qui les a dessinées.
Une reprise ne demande plus que le fichier :

    lues = lire_les_donnees(Presentation("dossier.pptx"))
    deplie = deplier_les_donnees(lues, Path(tempfile.mkdtemp(prefix="reprise-")))
    generer_pptx(Projet.charger(deplie.fiche), dossier_sortie=deplie.sortie)

Ce module ne reprend rien lui-même : il n'y a ni bouton ni parcours. Les
reprises se font au cas par cas (décision du 11/11/2026), et ce sont ces
données qui les rendent sûres.

CE QUI N'Y EST PAS
------------------
- La notice DP 11 : elle est déjà dans le fichier, en pages, et pèserait plus
  que tout le reste. Le manifeste garde le nom du fichier. Elle ne suffit que
  tant que la reprise garde la pagination : ses pages portent leur numéro.
- L'image de couverture, l'export HelioScope, les photographies : l'application
  ne les dépose plus, et l'export HelioScope est en amont du contrat, qui est
  emporté et porte le calage. Ce qu'une saisie en tient — la longitude de
  calage et sa correction, que `Projet.valider` refuse sans l'export — part au
  manifeste avec sa valeur.
- Les fonds IGN, le cadastre et la BD TOPO, qu'une régénération recharge : ils
  ont pu changer depuis.

OÙ, ET SOUS QUELLE FORME
------------------------
Dans une partie « custom XML » du paquet (`customXml/itemN.xml`, reliée à la
présentation), la place que le format réserve aux données d'une application :
PowerPoint n'en montre rien. Pas dans `core_properties`, où vit l'identité du
lot 7 : 255 caractères par champ, quand la fiche seule en fait 3 000.

Le contenu est un ZIP, en base64 dans l'élément. Le GeoPackage s'y comprime :
les données de Sarnois — un GeoPackage de 745 Ko, son JSON de 21 Ko, la fiche
et l'emprise — ajoutent 96 Ko à un fichier de 10,5 Mo (mesuré le 11/11/2026).
Un ZIP plutôt que des éléments XML : ses sommes de contrôle disent si un
fichier est arrivé abîmé.

CE QUI A ÉTÉ MESURÉ, LE 11/11/2026
----------------------------------
Sur le `.pptx` réel de Sarnois IND10B, ses données rangées, puis ouvert par
PowerPoint pour Microsoft 365 (16.0, build 20527), une diapo supprimée, une
forme ajoutée, enregistré et exporté en PDF :

- les quatre fichiers emportés reviennent identiques à l'octet, et la fiche
  comme le contrat se rechargent ;
- PowerPoint a renuméroté la partie (`item9.xml` devenu `item3.xml`) et récrit
  sa déclaration XML : c'est pourquoi elle se cherche à son espace de noms ;
- le fichier portait déjà quatre parties « custom XML », posées par SharePoint
  quand le dossier y a été ouvert : un fichier réel n'a pas que les nôtres ;
- le PDF exporté n'en garde rien : ni l'espace de noms, ni une métadonnée ;
- l'inspecteur de document les trouve sous « Données XML personnalisées », et
  « Supprimer tout » les retire, avec celles de SharePoint : un fichier qui ne
  porte rien n'est donc pas forcément d'avant le 11/11/2026.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import io
import json
import tempfile
import uuid
import zipfile
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from pptx.opc.constants import CONTENT_TYPE as CT
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.opc.packuri import PackURI

from . import environnement
from .erreurs import ErreurDP, ErreurReprise
from .projet import Projet

#: Espace de noms de l'élément. C'est lui qui reconnaît nos données parmi les
#: autres parties « custom XML » qu'un fichier peut porter — celles qu'ajoute un
#: SharePoint, par exemple, quand le dossier y est ouvert.
ESPACE = "urn:generateur-dp:donnees-du-dossier"

#: Version de la forme des données. Une forme nouvelle se lira à côté de
#: celle-ci, jamais à sa place : les fichiers déjà déposés gardent la leur.
FORMAT = 1

NOM_MANIFESTE = "manifeste.json"
#: La fiche et son emprise. L'emprise a son sous-dossier : déposée sous le nom
#: `projet.json` — un GeoJSON peut s'appeler ainsi —, elle aurait écrasé la fiche.
DOSSIER_FICHE = "fiche"
SOUS_DOSSIER_EMPRISE = "emprise"
NOM_FICHE = "projet.json"
#: Le contrat, dans `contrat/{nom}/` : déplié, `contrat/` est le dossier de
#: sortie que `generer_pptx` attend, et `{nom}/` celui qu'il y lit.
DOSSIER_CONTRAT = "contrat"

#: Les fichiers d'un shapefile que l'application accepte au dépôt — la même
#: liste que `EXTENSIONS_SHAPEFILE` dans `app.py`, qui ne s'importe pas. Eux
#: seuls suivent le `.shp` : le dossier du projet range aussi le DXF du bureau
#: d'études et le tableau bilan, qu'un nom commun aurait emportés.
_EXTENSIONS_SHAPEFILE = (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qmd")

_ELEMENT = f"{{{ESPACE}}}donnees"
_ESPACE_DS = "http://schemas.openxmlformats.org/officeDocument/2006/customXml"
_FUSEAU = ZoneInfo("Europe/Paris")

#: Champs de la fiche qui désignent un fichier non emporté, et pourquoi.
_LAISSES = {
    "notice": "déjà dans le dossier, en pages",
    "image_garde": (
        "l'application ne la dépose plus : la couverture se pose dans le fichier"
    ),
    "helioscope": "en amont du contrat, qui est emporté et porte le calage",
}
_RAISON_PHOTOGRAPHIES = (
    "l'application ne les dépose plus : elles se posent dans le fichier"
)

#: Ce qui ne tient pas sans l'export HelioScope : `Projet.valider` refuse un
#: calage sans calepinage, et une correction sans calage.
_SUIVENT_L_EXPORT = ("longitude_calage", "correction_nord_sud_m")


@dataclass(frozen=True)
class DonneesEmportees:
    """Ce qu'un fichier emporte : son manifeste, et ses fichiers par leur nom."""

    manifeste: dict
    #: Nom dans l'archive (`fiche/projet.json`, `contrat/{nom}/geometries.gpkg`…)
    #: vers les octets du fichier, tels qu'ils étaient à la génération.
    fichiers: dict


@dataclass(frozen=True)
class DossierDeplie:
    """Où les données se sont dépliées, sous les noms que la génération attend."""

    #: Le `projet.json`, que `Projet.charger` relit.
    fiche: Path
    #: Le dossier de sortie à donner à `generer_pptx`, qui y lit le contrat dans
    #: `{nom}/`. Toujours là, même vide : sans plan importé, la régénération doit
    #: y trouver « aucun plan », et non le contrat qu'un autre passage du même
    #: projet aurait laissé dans le `sortie/` par défaut.
    sortie: Path


# ---------------------------------------------------------------------------
# À la génération
# ---------------------------------------------------------------------------


def emporter_les_donnees(presentation, projet: Projet, contrat: bytes | None) -> list[str]:
    """Range dans le fichier la fiche, l'emprise et le contrat qui l'ont produit.

    `contrat` est l'archive de `contrat.archiver_le_contrat`, prise au moment où
    la génération a lu le contrat — `None` sans plan importé. Les données déjà
    rangées dans le fichier sont **remplacées** : après une reprise, les
    planches transplantées ne sont plus celles qu'elles décrivaient.

    Rend les messages du rapport, vide quand tout est rangé. Un échec n'arrête
    pas la génération — le dossier est juste, il se reprendra seulement comme
    ceux d'avant le 11/11/2026 —, mais il se dit.
    """
    try:
        archive = _archive(projet, contrat)
    except (OSError, ErreurDP) as exc:
        return [
            "Le dossier n'emporte pas les données qui l'ont produit "
            f"({exc}) : une reprise demandera de reconstituer la fiche, "
            "l'emprise et le contrat."
        ]
    _retirer(presentation)
    _poser(presentation, archive)
    return []


def _archive(projet: Projet, contrat: bytes | None) -> bytes:
    """Le ZIP des données : le manifeste, la fiche et son emprise, le contrat."""
    fichiers, non_emportes, retirees = _fiche(projet)
    if contrat is not None:
        # Le contrat tel que l'archive du téléchargement le porte : les mêmes
        # fichiers, sous les mêmes noms, et non une relecture qui pourrait
        # différer de celui qui a produit les planches.
        with zipfile.ZipFile(io.BytesIO(contrat)) as lu:
            for membre in lu.namelist():
                fichiers[f"{DOSSIER_CONTRAT}/{membre}"] = lu.read(membre)
    manifeste = {
        "format": FORMAT,
        "nom": projet.nom,
        "produit_le": datetime.now(_FUSEAU).isoformat(timespec="seconds"),
        # La version de l'outil dit ce que les planches contiennent — si le
        # dossier a déjà ses cotes, par exemple —, sans avoir à les relire.
        "outil": _version_de_l_outil(),
        "fiche": f"{DOSSIER_FICHE}/{NOM_FICHE}",
        "contrat": f"{DOSSIER_CONTRAT}/{projet.nom}" if contrat is not None else None,
        "non_emportes": non_emportes,
        "valeurs_retirees": retirees,
    }
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            NOM_MANIFESTE, json.dumps(manifeste, ensure_ascii=False, indent=2)
        )
        for nom, octets in fichiers.items():
            archive.writestr(nom, octets)
    return tampon.getvalue()


def _version_de_l_outil() -> dict:
    """La version du code **chargé**, celui qui a dessiné les planches.

    `version_deployee` date le disque, et le disque devance la mémoire le temps
    d'un redémarrage : c'est l'écart qui a coûté l'aller-retour du 09/10/2026
    (voir `environnement`). Le commit, lui, ne se lit que sur le disque ;
    `en_retard` dit s'il peut être plus récent que le code qui a tourné.
    """
    version = environnement.version_deployee()
    horodatage = environnement.HORODATAGE_AU_DEMARRAGE
    return {
        "version": (
            datetime.fromtimestamp(horodatage, _FUSEAU).strftime("%d/%m/%Y à %H:%M")
            if horodatage
            else "inconnue"
        ),
        "commit": version.commit,
        "en_retard": version.en_retard,
    }


def _fiche(projet: Projet) -> tuple[dict, dict, dict]:
    """La fiche telle que l'application l'écrit, et l'emprise à côté d'elle.

    Écrite par `Projet.ecrire`, comme l'application l'écrit : ses chemins sont
    relatifs au `projet.json`, ce qui laisse la fiche se déplier n'importe où et
    se relire par `Projet.charger`.
    """
    non_emportes, retirees, changements = {}, {}, {}
    for champ, raison in _LAISSES.items():
        valeur = getattr(projet, champ)
        if valeur:
            non_emportes[champ] = {"fichiers": [Path(valeur).name], "raison": raison}
            changements[champ] = None
    if projet.photographies:
        non_emportes["photographies"] = {
            "fichiers": sorted(
                {
                    Path(image).name
                    for prises in projet.photographies.values()
                    for prise in prises
                    for image in prise.get("images") or []
                    if image
                }
            ),
            "raison": _RAISON_PHOTOGRAPHIES,
        }
        changements["photographies"] = None
    if projet.helioscope:
        for champ in _SUIVENT_L_EXPORT:
            valeur = getattr(projet, champ)
            if valeur is not None:
                retirees[champ] = valeur
                changements[champ] = None

    with tempfile.TemporaryDirectory(prefix="donnees-") as travail:
        base = Path(travail)
        emprise = base / SOUS_DOSSIER_EMPRISE
        # Une emprise en dossier se range en dossier, sous son nom : c'est le
        # dossier que `charger_emprise` relira.
        destination = emprise / projet.chemin_emprise.name if projet.chemin_emprise.is_dir() else emprise
        destination.mkdir(parents=True)
        for source in _fichiers_de_l_emprise(projet.chemin_emprise):
            (destination / source.name).write_bytes(source.read_bytes())
        changements["emprise"] = str(emprise / projet.chemin_emprise.name)
        dataclasses.replace(projet, **changements).ecrire(base / NOM_FICHE)
        fichiers = {
            f"{DOSSIER_FICHE}/{chemin.relative_to(base).as_posix()}": chemin.read_bytes()
            for chemin in sorted(base.rglob("*"))
            if chemin.is_file()
        }
    return fichiers, non_emportes, retirees


def _fichiers_de_l_emprise(chemin: Path) -> list[Path]:
    """Le fichier d'emprise, et ses compagnons quand c'est un shapefile.

    Le `.shp` seul ne se lit pas : l'index est dans le `.shx`, les attributs dans
    le `.dbf`, la projection dans le `.prj`. L'application les range côte à côte
    quand ils sont déposés un à un (`_enregistrer_fichiers`) : ce sont ceux qui
    portent le même nom. Un dossier, que `charger_emprise` accepte quand il ne
    porte qu'un `.shp`, donne les fichiers de shapefile qu'il contient.
    """
    if chemin.is_dir():
        return sorted(
            fichier
            for fichier in chemin.iterdir()
            if fichier.is_file() and fichier.suffix.lower() in _EXTENSIONS_SHAPEFILE
        )
    if chemin.suffix.lower() != ".shp":
        return [chemin]
    return sorted(
        voisin
        for voisin in chemin.parent.iterdir()
        if voisin.is_file()
        and voisin.stem.lower() == chemin.stem.lower()
        and voisin.suffix.lower() in _EXTENSIONS_SHAPEFILE
    )


def _retirer(presentation) -> None:
    """Détache les données déjà rangées : une partie que rien ne relie plus
    n'est pas enregistrée.

    Reconnues à leur espace de noms seul, sans les lire : une partie abîmée se
    remplace comme une autre.
    """
    for rId, relation in list(presentation.part.rels.items()):
        if relation.reltype == RT.CUSTOM_XML and _nomme_notre_espace(
            relation.target_part.blob
        ):
            presentation.part.drop_rel(rId)


def _poser(presentation, archive: bytes) -> None:
    """La partie de données, reliée à la présentation, et ses propriétés.

    Le couple `itemN.xml` / `itemPropsN.xml` est celui qu'Office écrit lui-même :
    les propriétés donnent à la partie un identifiant et le schéma qu'elle suit.
    L'XML s'écrit à la main : la base64 ne porte aucun caractère à échapper, et
    l'élément n'a qu'un attribut.
    """
    paquet = presentation.part.package
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<donnees xmlns="{ESPACE}" format="{FORMAT}">'
        f"{base64.b64encode(archive).decode('ascii')}</donnees>"
    ).encode("utf-8")
    identifiant = "{" + str(uuid.uuid4()).upper() + "}"
    proprietes = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f'<ds:datastoreItem ds:itemID="{identifiant}" xmlns:ds="{_ESPACE_DS}">'
        f'<ds:schemaRefs><ds:schemaRef ds:uri="{ESPACE}"/></ds:schemaRefs>'
        "</ds:datastoreItem>"
    ).encode("utf-8")

    # Le premier numéro libre pour les deux noms à la fois. `next_partname`
    # cherche par préfixe, et « /customXml/item » compte aussi les `itemProps` :
    # il rendait `item9` sur un fichier qui en portait quatre de chaque, sans
    # rien garantir du nom des propriétés (mesuré sur Sarnois, 11/11/2026).
    pris = {str(partie.partname).lower() for partie in paquet.iter_parts()}
    numero = 1
    while (
        f"/customxml/item{numero}.xml" in pris
        or f"/customxml/itemprops{numero}.xml" in pris
    ):
        numero += 1
    partie = Part(PackURI(f"/customXml/item{numero}.xml"), CT.XML, paquet, xml)
    presentation.part.relate_to(partie, RT.CUSTOM_XML)
    partie.relate_to(
        Part(
            PackURI(f"/customXml/itemProps{numero}.xml"),
            CT.OFC_CUSTOM_XML_PROPERTIES,
            paquet,
            proprietes,
        ),
        RT.CUSTOM_XML_PROPS,
    )


# ---------------------------------------------------------------------------
# À la reprise
# ---------------------------------------------------------------------------


def lire_les_donnees(presentation) -> DonneesEmportees | None:
    """Les données que le fichier emporte, ou None s'il n'en porte pas.

    None ne dit pas à lui seul que le dossier est d'avant le 11/11/2026 :
    l'inspecteur de document de PowerPoint retire ces données si l'on supprime
    les « Données XML personnalisées » (mesuré le 11/11/2026). Une partie qui
    porte notre espace de noms mais ne se lit plus lève au contraire : un
    fichier abîmé ne passe pas pour un fichier d'avant.

    Cherchées dans tout le paquet, et reconnues à leur espace de noms plutôt
    qu'au nom de leur partie : PowerPoint renumérote les parties qu'il
    réenregistre.
    """
    elements = [
        element
        for partie in presentation.part.package.iter_parts()
        if (element := _element_de(partie)) is not None
    ]
    if not elements:
        return None
    if len(elements) > 1:
        raise ErreurReprise(
            f"Le fichier porte {len(elements)} jeux de données du dossier, là où "
            "il n'en faut qu'un : rien ne dit lequel croire."
        )
    element = elements[0]
    forme = element.get("format")
    if forme != str(FORMAT):
        raise ErreurReprise(
            f"Données du dossier au format {forme} : cet outil lit le format "
            f"{FORMAT}."
        )
    try:
        archive = base64.b64decode("".join((element.text or "").split()), validate=True)
        with zipfile.ZipFile(io.BytesIO(archive)) as lu:
            fichiers = {
                nom: lu.read(nom) for nom in lu.namelist() if not nom.endswith("/")
            }
        manifeste = json.loads(fichiers.pop(NOM_MANIFESTE).decode("utf-8"))
        if not isinstance(manifeste, dict) or "nom" not in manifeste:
            raise ValueError("manifeste sans nom de projet")
    except (
        binascii.Error, zipfile.BadZipFile, zlib.error, EOFError, KeyError, ValueError,
    ) as exc:
        raise ErreurReprise(f"Les données du dossier sont illisibles : {exc}") from exc
    return DonneesEmportees(manifeste=manifeste, fichiers=fichiers)


def _element_de(partie):
    """L'élément de données d'une partie, ou None si la partie n'est pas la nôtre.

    Sont examinées les parties en `application/xml` et toutes celles rangées
    sous `customXml/`, quel que soit le type que leur aurait donné un autre
    logiciel. Une partie qui nomme notre espace mais ne se lit plus n'est pas
    « pas la nôtre » : la taire ferait passer un fichier abîmé pour un fichier
    d'avant.
    """
    if partie.content_type != CT.XML and not str(partie.partname).lower().startswith(
        "/customxml/"
    ):
        return None
    try:
        element = ElementTree.fromstring(partie.blob)
    except ElementTree.ParseError as exc:
        if _nomme_notre_espace(partie.blob):
            raise ErreurReprise(
                f"Les données du dossier sont illisibles : {exc}"
            ) from exc
        return None
    return element if element.tag == _ELEMENT else None


def _nomme_notre_espace(octets: bytes) -> bool:
    """Vrai si les octets nomment notre espace, en UTF-8 ou en UTF-16."""
    return any(
        ESPACE.encode(codage) in octets for codage in ("utf-8", "utf-16-le", "utf-16-be")
    )


def deplier_les_donnees(donnees: DonneesEmportees, cible) -> DossierDeplie:
    """Écrit la fiche, l'emprise et le contrat dans `cible`, prêts à régénérer.

    `cible` doit être neuf : les restes d'un dépliage précédent — un contrat
    d'hier sous un dossier qui n'en a pas — se mêleraient aux données. Les
    chemins rendus se déduisent de la forme des données et non du manifeste,
    qui ne fait que les annoncer.
    """
    racine = Path(cible).resolve()
    if racine.exists() and any(racine.iterdir()):
        raise ErreurReprise(
            f"Le dossier de reprise {racine} n'est pas vide : dépliez dans un "
            "dossier neuf, pour qu'aucun reste d'une reprise précédente ne se "
            "mêle à ces données."
        )
    fiche = f"{DOSSIER_FICHE}/{NOM_FICHE}"
    if fiche not in donnees.fichiers:
        raise ErreurReprise("Les données du dossier ne portent pas de fiche.")
    if donnees.manifeste.get("contrat") and not any(
        nom.startswith(f"{DOSSIER_CONTRAT}/") for nom in donnees.fichiers
    ):
        raise ErreurReprise(
            "Le manifeste annonce un contrat que les données ne portent pas."
        )
    for nom, octets in donnees.fichiers.items():
        chemin = (racine / nom).resolve()
        if not chemin.is_relative_to(racine):
            raise ErreurReprise(
                f"« {nom} » s'écrirait hors du dossier de reprise : ces données "
                "ne viennent pas de l'outil."
            )
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(octets)
    sortie = racine / DOSSIER_CONTRAT
    sortie.mkdir(parents=True, exist_ok=True)
    return DossierDeplie(fiche=racine / fiche, sortie=sortie)
