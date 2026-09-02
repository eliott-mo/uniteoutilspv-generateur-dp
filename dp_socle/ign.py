"""Accès aux services de la Géoplateforme IGN, en Lambert 93 natif.

Choix d'architecture : WMS-R (et non WMTS) avec `CRS=EPSG:2154` et la BBOX
exacte de la zone de dessin. Le serveur renvoie directement une image à
l'emprise et à l'échelle voulues, ce qui évite à la fois le mosaïquage de tuiles
et la reprojection depuis le Web Mercator — deux sources d'erreur d'échelle.

Identifiants de couches et noms d'attributs **confirmés par GetCapabilities**
le 2026-09-01 :

Le WMS-R est réparti sur plusieurs nœuds, dont l'un répond par intermittence
`LayerNotDefined` sur une couche pourtant publiée (constaté le 2026-09-02) :
`telecharger_fond` redemande donc la même image un nombre borné de fois, et le
signale. Rien n'est substitué.

- WMS-R  https://data.geopf.fr/wms-r/wms   (WMS 1.3.0, MaxWidth/MaxHeight 5010)
    * GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2
    * ORTHOIMAGERY.ORTHOPHOTOS
- WFS    https://data.geopf.fr/wfs/ows     (WFS 2.0.0)
    * CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle
      attributs : idu, section, numero, feuille, contenance (m2),
                  code_insee, nom_com
    * CADASTRALPARCELS.PARCELLAIRE_EXPRESS:batiment
      attributs : type (« Bâtiment en dur », « Bâtiment léger »), code_insee
"""

from __future__ import annotations

import io
import time
import warnings
from dataclasses import dataclass

import requests
from PIL import Image
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from .erreurs import ErreurService

URL_WMS = "https://data.geopf.fr/wms-r/wms"
URL_WFS = "https://data.geopf.fr/wfs/ows"

COUCHE_PLAN = "GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"
COUCHE_ORTHO = "ORTHOIMAGERY.ORTHOPHOTOS"
COUCHE_PARCELLES = "CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle"
COUCHE_BATIMENTS = "CADASTRALPARCELS.PARCELLAIRE_EXPRESS:batiment"

#: Limite annoncée par le GetCapabilities du WMS-R.
TAILLE_MAX_PX = 5010

#: 200 dpi en A3 : 3228 x 2110 px sur la zone de dessin. Mesuré sur le dossier
#: de Bray-Saint-Aignan, la photographie aérienne pèse 10,6 Mo à 200 dpi contre
#: 16,2 Mo à 250, pour une lisibilité équivalente à l'impression.
DPI_DEFAUT = 200

_ENTETES = {"User-Agent": "generateur-dp-unite/1.0 (dossier DP photovoltaique)"}

#: Nombre de tentatives d'une requête GetMap, et attente entre deux essais.
#:
#: Le WMS-R est réparti sur plusieurs nœuds et l'un d'eux répond parfois
#: `LayerNotDefined` sur une couche pourtant présente dans le GetCapabilities.
#: Constaté le 02/09/2026 sur GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2 : la même
#: requête échoue en HTTP 400 puis passe à l'essai suivant. Sans reprise, un
#: aléa de quelques secondes fait échouer la génération complète du dossier.
#:
#: Ce n'est pas un repli : rien n'est substitué, on redemande la même chose, un
#: nombre borné de fois, et toute reprise est signalée.
TENTATIVES_WMS = 3
ATTENTE_REPRISE_S = 2.0


@dataclass
class FondRaster:
    """Image de fond, garantie à la bbox demandée."""

    image: Image.Image
    bbox: tuple[float, float, float, float]
    couche: str
    dpi: int
    format: str
    #: Nombre de requêtes qu'il a fallu pour obtenir l'image. Au-delà de 1, le
    #: service a flanché puis repris ; la planche est bonne, mais le fait est
    #: remonté au rapport de génération.
    tentatives: int = 1

    @property
    def taille_px(self) -> tuple[int, int]:
        return self.image.size


def dimensions_px(largeur_mm: float, hauteur_mm: float, dpi: int) -> tuple[int, int]:
    """Nombre de pixels pour une zone en millimètres à un DPI donné."""
    return (
        max(1, round(largeur_mm / 25.4 * dpi)),
        max(1, round(hauteur_mm / 25.4 * dpi)),
    )


def dpi_utilisable(largeur_mm: float, hauteur_mm: float, dpi: int) -> int:
    """DPI réellement demandable sans dépasser la limite de taille du serveur."""
    largeur_px, hauteur_px = dimensions_px(largeur_mm, hauteur_mm, dpi)
    depassement = max(largeur_px, hauteur_px) / TAILLE_MAX_PX
    if depassement <= 1.0:
        return dpi
    return int(dpi / depassement)


def telecharger_fond(
    couche: str,
    bbox: tuple[float, float, float, float],
    largeur_mm: float,
    hauteur_mm: float,
    dpi: int = DPI_DEFAUT,
    format_image: str = "image/jpeg",
    timeout: int = 120,
) -> FondRaster:
    """GetMap WMS-R à la bbox exacte, sans recadrage ultérieur.

    Recadrer une image demandée plus large réintroduirait une erreur d'échelle :
    on demande donc précisément la zone de dessin.
    """
    minx, miny, maxx, maxy = bbox
    if maxx <= minx or maxy <= miny:
        raise ErreurService(f"BBOX dégénérée transmise au WMS : {bbox}")

    dpi_reel = dpi_utilisable(largeur_mm, hauteur_mm, dpi)
    largeur_px, hauteur_px = dimensions_px(largeur_mm, hauteur_mm, dpi_reel)
    tentatives = 0

    parametres = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS": couche,
        "STYLES": "",
        "CRS": "EPSG:2154",
        "BBOX": ",".join(f"{v:.3f}" for v in (minx, miny, maxx, maxy)),
        "WIDTH": str(largeur_px),
        "HEIGHT": str(hauteur_px),
        "FORMAT": format_image,
        "TRANSPARENT": "FALSE",
    }
    while True:
        tentatives += 1
        try:
            reponse = requests.get(
                URL_WMS, params=parametres, headers=_ENTETES, timeout=timeout
            )
        except requests.RequestException as exc:
            echec = (
                f"Couche WMS « {couche} » injoignable : {exc}. "
                "Pas de fond blanc de remplacement : la planche n'est pas produite."
            )
            reponse = None
        else:
            type_contenu = (reponse.headers.get("content-type") or "").lower()
            if reponse.status_code == 200 and type_contenu.startswith("image/"):
                break
            lisible = "xml" in type_contenu or "text" in type_contenu
            extrait = reponse.text[:400] if lisible else ""
            echec = (
                f"Couche WMS « {couche} » : réponse HTTP {reponse.status_code}, "
                f"type {type_contenu or 'inconnu'}. {extrait}"
            )

        if tentatives >= TENTATIVES_WMS:
            raise ErreurService(
                f"{echec} Échec après {tentatives} tentatives."
            )
        warnings.warn(
            f"Couche WMS « {couche} » : échec de la tentative {tentatives} sur "
            f"{TENTATIVES_WMS}, nouvelle tentative dans {ATTENTE_REPRISE_S:.0f} s. "
            f"{echec}",
            RuntimeWarning,
            stacklevel=2,
        )
        time.sleep(ATTENTE_REPRISE_S)

    try:
        image = Image.open(io.BytesIO(reponse.content))
        image.load()
    except Exception as exc:
        raise ErreurService(f"Image WMS « {couche} » illisible : {exc}") from exc

    if image.size != (largeur_px, hauteur_px):
        raise ErreurService(
            f"Le WMS a renvoyé une image {image.size} au lieu de "
            f"{(largeur_px, hauteur_px)} pour la couche « {couche} » : "
            "l'échelle de la planche ne serait pas garantie."
        )

    # .convert("RGB") systématique : critique pour la mémoire et pour l'export PDF.
    image = image.convert("RGB")
    return FondRaster(
        image=image,
        bbox=(minx, miny, maxx, maxy),
        couche=couche,
        dpi=dpi_reel,
        format=format_image,
        tentatives=tentatives,
    )


@dataclass
class Parcelle:
    """Parcelle cadastrale issue du Parcellaire Express."""

    geometrie: BaseGeometry
    idu: str
    section: str
    numero: str
    contenance_m2: float
    commune: str

    @property
    def designation(self) -> str:
        return f"{self.section} {self.numero}"


def _interroger_wfs(
    typename: str,
    bbox: tuple[float, float, float, float],
    timeout: int,
    taille_page: int,
    maximum: int,
    libelle: str,
) -> list:
    """GetFeature paginé, en EPSG:2154, sur une couche du Parcellaire Express."""
    minx, miny, maxx, maxy = bbox
    if maxx <= minx or maxy <= miny:
        raise ErreurService(f"BBOX dégénérée transmise au WFS : {bbox}")

    entites: list = []
    index = 0
    while index < maximum:
        parametres = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "TYPENAMES": typename,
            "SRSNAME": "EPSG:2154",
            "BBOX": f"{minx:.3f},{miny:.3f},{maxx:.3f},{maxy:.3f},EPSG:2154",
            "OUTPUTFORMAT": "application/json",
            "COUNT": str(taille_page),
            "STARTINDEX": str(index),
        }
        try:
            reponse = requests.get(
                URL_WFS, params=parametres, headers=_ENTETES, timeout=timeout
            )
        except requests.RequestException as exc:
            raise ErreurService(
                f"Service WFS ({libelle}) injoignable : {exc}. "
                "La planche n'est pas produite plutôt que d'être incomplète."
            ) from exc

        if reponse.status_code != 200:
            raise ErreurService(
                f"Service WFS ({libelle}) : réponse HTTP {reponse.status_code}. "
                f"{reponse.text[:400]}"
            )
        try:
            donnees = reponse.json()
        except ValueError as exc:
            raise ErreurService(
                f"Réponse WFS ({libelle}) illisible, du GeoJSON était attendu : "
                f"{reponse.text[:400]}"
            ) from exc

        page = donnees.get("features") or []
        entites.extend(page)
        if len(page) < taille_page:
            break
        index += taille_page
    return entites


def telecharger_parcelles(
    bbox: tuple[float, float, float, float],
    timeout: int = 120,
    taille_page: int = 1000,
    maximum: int = 5000,
) -> list[Parcelle]:
    """Parcelles cadastrales intersectant la bbox, en Lambert 93."""
    entites = _interroger_wfs(
        COUCHE_PARCELLES, bbox, timeout, taille_page, maximum, "cadastre"
    )
    resultats = []
    for entite in entites:
        geometrie = entite.get("geometry")
        if not geometrie:
            continue
        proprietes = entite.get("properties") or {}
        resultats.append(
            Parcelle(
                geometrie=shape(geometrie),
                idu=str(proprietes.get("idu", "")),
                section=str(proprietes.get("section", "")),
                numero=str(proprietes.get("numero", "")),
                contenance_m2=float(proprietes.get("contenance") or 0.0),
                commune=str(proprietes.get("nom_com", "")),
            )
        )

    if not resultats:
        raise ErreurService(
            f"Aucune parcelle cadastrale renvoyée par le WFS pour la bbox {bbox}. "
            "Vérifiez que l'emprise est bien en France métropolitaine et couverte "
            "par le Parcellaire Express."
        )
    return resultats


def verifier_couches(couches=(COUCHE_PLAN, COUCHE_ORTHO), timeout: int = 120) -> dict:
    """Confronte les identifiants câblés au GetCapabilities du WMS-R."""
    try:
        reponse = requests.get(
            URL_WMS,
            params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetCapabilities"},
            headers=_ENTETES,
            timeout=timeout,
        )
        reponse.raise_for_status()
    except requests.RequestException as exc:
        raise ErreurService(f"GetCapabilities WMS-R inaccessible : {exc}") from exc
    texte = reponse.text
    return {couche: f"<Name>{couche}</Name>" in texte for couche in couches}


@dataclass
class Batiment:
    """Emprise bâtie issue du Parcellaire Express."""

    geometrie: BaseGeometry
    type: str


def telecharger_batiments(
    bbox: tuple[float, float, float, float],
    timeout: int = 120,
    taille_page: int = 1000,
    maximum: int = 5000,
) -> list[Batiment]:
    """Bâtiments cadastraux intersectant la bbox, en Lambert 93.

    Une bbox sans bâtiment renvoie une liste vide : en secteur agricole c'est
    un résultat, pas une anomalie. C'est l'appelant qui en rend compte.
    """
    entites = _interroger_wfs(COUCHE_BATIMENTS, bbox, timeout, taille_page, maximum,
                              "bâtiments")
    return [
        Batiment(geometrie=shape(e["geometry"]), type=str((e.get("properties") or {}).get("type", "")))
        for e in entites
        if e.get("geometry")
    ]
