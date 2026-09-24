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

import http.cookiejar
import io
import ssl
import time
import warnings
from dataclasses import dataclass
from functools import lru_cache

import requests
from PIL import Image
from pyproj import Transformer
from requests.adapters import HTTPAdapter
from requests.utils import DEFAULT_CA_BUNDLE_PATH
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from .erreurs import ErreurAltimetrie, ErreurService

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


class _AdaptateurTLS(HTTPAdapter):
    """Un adaptateur HTTPS dont le contexte TLS porte déjà ses autorités.

    requests 2.33 confie à urllib3 2.6 le chemin du magasin de certificats de
    certifi, et urllib3 le recharge à chaque nouvelle connexion : de 0,3 à 4 s
    sur un poste Windows, mesuré le 24/09/2026 — jusqu'au tiers du calage sur
    l'ortho. Une session seule n'y suffit pas : la Géoplateforme ferme une
    connexion inactive en moins de 15 s, et deux clics sont d'ordinaire plus
    espacés. Ce contexte-ci est chargé une fois, des mêmes autorités que
    requests, et garde la même exigence : certificat et nom d'hôte vérifiés.
    """

    def __init__(self):
        # Avant `super().__init__`, qui crée déjà le gestionnaire de connexions.
        self._contexte = ssl.create_default_context(cafile=DEFAULT_CA_BUNDLE_PATH)
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        kwargs["ssl_context"] = self._contexte
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        # Derrière un proxy aussi : sans lui, urllib3 prendrait le magasin du
        # système, en silence, puisque le chemin de certifi ne lui est plus
        # transmis.
        proxy_kwargs["ssl_context"] = self._contexte
        return super().proxy_manager_for(proxy, **proxy_kwargs)

    def cert_verify(self, conn, url, verify, cert):
        super().cert_verify(conn, url, verify, cert)
        # Laissé au pool, le chemin des autorités les ferait recharger par
        # urllib3 à chaque connexion : elles sont déjà dans le contexte.
        conn.ca_certs = None
        conn.ca_cert_dir = None


@lru_cache(maxsize=1)
def _session() -> requests.Session:
    """La session de toutes les requêtes à la Géoplateforme.

    Créée au premier appel et non à l'import : charger les certificats ne coûte
    qu'à qui interroge un service. Elle réutilise aussi la connexion ouverte
    pour les requêtes qui se suivent à moins de quelques secondes — pages du
    cadastre, paquets du RGE ALTI, fonds d'un même dossier. Partagée par toutes
    les sessions de l'application, elle ne garde aucun cookie.
    """
    session = requests.Session()
    session.mount("https://", _AdaptateurTLS())
    session.cookies.set_policy(http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))
    return session


def _connexion_neuve() -> None:
    """Ferme les connexions ouvertes de la session : la suivante sera neuve.

    Pour les reprises. Avant la session partagée, chaque tentative ouvrait sa
    propre connexion, et c'est ainsi qu'une reprise passait là où un nœud du
    WMS-R répondait `LayerNotDefined` (constaté le 02/09/2026). Sur une même
    connexion, le 24/09/2026, les trois tentatives ont échoué de même. Le
    contexte TLS reste chargé : la connexion neuve ne recharge rien.
    """
    _session().close()


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
            reponse = _session().get(
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
        _connexion_neuve()
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
            reponse = _session().get(
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
        reponse = _session().get(
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


# ---------------------------------------------------------------------------
# Service altimétrique (RGE ALTI)
# ---------------------------------------------------------------------------

#: Point d'entrée du calcul altimétrique de la Géoplateforme, et ressource
#: RGE ALTI. Vérifiés en réponse réelle le 03/09/2026 : le service répond en
#: GET, `{"elevations": [z, ...]}` avec `zonly=true`, altitudes en NGF.
URL_ALTIMETRIE = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"
RESSOURCE_ALTIMETRIE = "ign_rge_alti_wld"

#: Nombre de points par requête.
#:
#: Le brief annonçait un plafond « de l'ordre de 2 000 points ». Mesuré le
#: 03/09/2026, ce n'est pas le nombre de points qui limite mais la longueur de
#: l'URL : 200 points passent (URL de 4 736 caractères), 500 sont refusés en
#: HTTP 414 (11 636 caractères). Le POST, essayé sous ses deux formes,
#: répond 500 ou 400 : seul le GET fonctionne.
#:
#: Une coupe de site échantillonnée tous les 5 m tient donc en une ou deux
#: requêtes.
POINTS_PAR_REQUETE = 200

#: Attente entre deux requêtes successives, en secondes. Le service annonce une
#: limitation de l'ordre de 5 requêtes par seconde ; les requêtes ne sont pas
#: parallélisées.
ATTENTE_ALTIMETRIE_S = 0.25

#: Nombre de tentatives d'une requête altimétrique, sur le patron du WMS.
#:
#: Constaté le 17/09/2026 : le contrôle croisé du nuage du BE contre le RGE ALTI
#: échouait par intermittence quand la suite de tests enchaînait les appels au
#: service, et passait relancé seul. La requête altimétrique était la seule du
#: module sans reprise, alors que le WMS en a depuis le 02/09/2026 pour le même
#: motif — et elle porte davantage : un aléa de quelques secondes fait perdre la
#: coupe entière au chef de projet, qui doit tout recommencer.
#:
#: Ce n'est pas un repli : rien n'est substitué, on redemande les mêmes points,
#: un nombre borné de fois, et toute reprise est signalée.
TENTATIVES_ALTIMETRIE = 3

#: Codes HTTP qu'il vaut la peine de rejouer : surcharge passagère (429) et
#: panne d'un nœud (5xx). Un 400 ou un 414 viennent de la requête elle-même —
#: mesuré le 03/09/2026, 500 points la font dépasser la longueur d'URL admise —
#: et se reproduiraient à l'identique.
CODES_ALTIMETRIE_TRANSITOIRES = (429, 500, 502, 503, 504)

_VERS_WGS84 = Transformer.from_crs(2154, 4326, always_xy=True)


def telecharger_altitudes(
    points_l93: list[tuple[float, float]], timeout: int = 60
) -> list[float]:
    """Altitudes NGF du RGE ALTI aux points donnés en Lambert 93.

    Les points sont interrogés dans l'ordre reçu, par paquets, sans
    parallélisation. Une altitude manquante ou hors service lève plutôt que de
    trouer le profil : une coupe avec un point à zéro se dessinerait sans que
    personne ne le voie.
    """
    if not points_l93:
        raise ErreurAltimetrie(
            "Aucun point transmis au service altimétrique : la ligne de coupe "
            "est vide."
        )

    altitudes: list[float] = []
    for debut in range(0, len(points_l93), POINTS_PAR_REQUETE):
        paquet = points_l93[debut : debut + POINTS_PAR_REQUETE]
        if debut:
            time.sleep(ATTENTE_ALTIMETRIE_S)
        altitudes.extend(_paquet_altitudes(paquet, timeout))

    if len(altitudes) != len(points_l93):
        raise ErreurAltimetrie(
            f"Le service altimétrique a renvoyé {len(altitudes)} altitudes pour "
            f"{len(points_l93)} points demandés."
        )
    return altitudes


def _reponse_altimetrie(parametres: dict, timeout: int, points: int):
    """La réponse du service, en rejouant ce qui mérite de l'être.

    Rend la réponse HTTP 200 ; lève `ErreurAltimetrie` dès qu'un échec ne se
    rejoue pas, ou une fois les tentatives épuisées.
    """
    tentatives = 0
    while True:
        tentatives += 1
        rejouable = True
        try:
            reponse = _session().get(
                URL_ALTIMETRIE, params=parametres, headers=_ENTETES, timeout=timeout
            )
        except requests.RequestException as exc:
            echec = (
                f"Service altimétrique de la Géoplateforme injoignable : {exc}."
            )
        else:
            if reponse.status_code == 200:
                return reponse
            rejouable = reponse.status_code in CODES_ALTIMETRIE_TRANSITOIRES
            echec = (
                f"Service altimétrique : HTTP {reponse.status_code} sur "
                f"{points} points. {reponse.text[:200]}"
            )

        if not rejouable:
            raise ErreurAltimetrie(
                f"{echec} Cette réponse ne vient pas d'un aléa du service : "
                "la même requête donnerait le même résultat."
            )
        if tentatives >= TENTATIVES_ALTIMETRIE:
            raise ErreurAltimetrie(
                f"{echec} Échec après {tentatives} tentatives. Fournissez un "
                "fichier d'altimétrie en repli."
            )
        warnings.warn(
            f"Service altimétrique : échec de la tentative {tentatives} sur "
            f"{TENTATIVES_ALTIMETRIE}, nouvelle tentative dans "
            f"{ATTENTE_REPRISE_S:.0f} s. {echec}",
            RuntimeWarning,
            stacklevel=2,
        )
        _connexion_neuve()
        time.sleep(ATTENTE_REPRISE_S)


def _paquet_altitudes(paquet: list[tuple[float, float]], timeout: int) -> list[float]:
    lons, lats = _VERS_WGS84.transform([p[0] for p in paquet], [p[1] for p in paquet])
    parametres = {
        "lon": "|".join(f"{v:.6f}" for v in lons),
        "lat": "|".join(f"{v:.6f}" for v in lats),
        "resource": RESSOURCE_ALTIMETRIE,
        "delimiter": "|",
        "zonly": "true",
        "indent": "false",
    }
    reponse = _reponse_altimetrie(parametres, timeout, len(paquet))
    try:
        donnees = reponse.json()
    except ValueError as exc:
        raise ErreurAltimetrie(
            f"Réponse du service altimétrique illisible : {reponse.text[:200]}"
        ) from exc

    brutes = donnees.get("elevations")
    if not isinstance(brutes, list) or len(brutes) != len(paquet):
        raise ErreurAltimetrie(
            f"Réponse altimétrique inattendue : {len(brutes) if isinstance(brutes, list) else 'aucune'} "
            f"altitude(s) pour {len(paquet)} points demandés."
        )

    altitudes = []
    for indice, valeur in enumerate(brutes):
        # Avec `zonly=true` la réponse est une liste de nombres ; le format
        # complet renvoie des objets. Les deux sont acceptés, la valeur
        # sentinelle du service (-99999) est refusée plutôt que dessinée.
        if isinstance(valeur, dict):
            valeur = valeur.get("z")
        try:
            altitude = float(valeur)
        except (TypeError, ValueError) as exc:
            raise ErreurAltimetrie(
                f"Altitude illisible au point {indice + 1} : {valeur!r}."
            ) from exc
        if altitude < -1000.0:
            raise ErreurAltimetrie(
                f"Le RGE ALTI ne couvre pas le point {indice + 1} de la coupe "
                f"(altitude {altitude:g}). Fournissez un fichier d'altimétrie "
                "en repli."
            )
        altitudes.append(altitude)
    return altitudes
