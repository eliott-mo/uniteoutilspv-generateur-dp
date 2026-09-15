"""Points de vue des photographies DP 6, DP 7 et DP 8 (lot 6).

Une pièce photographique porte, à côté de ses images, un **plan de repérage**
qui dit d'où la photo a été prise et, quand on le sait, ce qu'elle regarde. Ce
module ne dessine rien : il établit ces points de vue à partir des deux sources
que le lot accepte, et rien d'autre.

DEUX ENTRÉES, PAS DEUX TRAITEMENTS
----------------------------------
1. Une **carte HTML de `photos-geoloc`**, l'outil de rapport de visite des chefs
   de projet. C'est l'entrée de premier choix : le chef de projet y a déjà placé
   chaque prise de vue et corrigé sa direction, à l'œil et sur fond satellite —
   précisément le geste que nous lui demanderions de refaire.
2. Une **photographie déposée seule**, dont on lit l'EXIF. C'est le chemin des
   photomontages, qui ne sont allés sur aucun terrain, et des vues qui ne
   viennent pas d'une visite outillée.

Les deux produisent le même `PointDeVue`. La suite du lot ne sait pas d'où il
vient, sauf pour le dire au rapport de génération.

CE QU'ON CROIT, ET CE QU'ON NE CROIT PAS
----------------------------------------
La **position** GPS se lit : elle n'a jamais été prise en défaut sur les deux
dépôts. L'incertitude que l'appareil annonce se lit avec elle, et au-delà de
`SEUIL_PRECISION_M` la photo est signalée — jamais écartée, c'est au chef de
projet de juger.

Le **cap** ne se croit pas. Mesuré des deux côtés : la boussole d'un téléphone
donne ±10 à 20°, et mal calibrée elle décale toutes les directions du même angle
(30 à 40° couramment). Une validation du dépôt `photomontage` a relevé 15°
d'erreur sur un cap annoncé, établis par recoupement sur deux éoliennes
identifiées dans OpenStreetMap. Un cap EXIF **propose** donc une orientation ;
il ne fait autorité qu'une fois confirmé sur fond satellite — ce qui est déjà le
cas d'un cap venu d'une carte `photos-geoloc`.

Sans cap confirmé, la planche porte le repère numéroté **sans cône**. Ce n'est
pas un manque : c'est le cas normal d'une vue de drone, et `photos-geoloc` le
traite déjà ainsi. Aucun cap n'est inventé, et le rapport de génération dit
lesquels manquent.

PIÈGE — DEUX CONVENTIONS D'ANGLE COHABITENT DANS CE DÉPÔT
----------------------------------------------------------
Le cap d'un point de vue est un **azimut géographique** : 0° au nord, sens
horaire, comme l'EXIF `GPSImgDirection` et comme `photos-geoloc`.

Le reste du dépôt travaille en **angle mathématique** : 0° à l'est, sens
trigonométrique — c'est le cas de `azimut_tables_deg` et de tout ce que
`coupe.py` calcule par `atan2(dy, dx)`. Mélanger les deux donne un cône qui
pointe ailleurs sans que rien ne le signale, exactement le genre de planche
fausse d'aspect correct que ce dépôt refuse. La conversion est isolée dans
`PointDeVue.cap_trigonometrique_deg` et ne doit être refaite nulle part.

Vérifié le 15/09/2026 : `dp_socle/coupe.py:298` calcule bien sa direction par
`degrees(atan2(dy, dx))`, donc depuis l'est.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from dp_socle.erreurs import ErreurPhotoIllisible

#: Version du format de carte `photos-geoloc` que ce module sait lire.
#:
#: Relevé le 15/09/2026 dans `photos-geoloc/generation_html.py` : `VERSION_CARTE`
#: y vaut 5. Les versions antérieures se lisent sans migration — les champs dont
#: nous avons besoin (`lat`, `lon`, `cap`, déduits et réécrits à chaque
#: enregistrement) existent depuis la v2 ; seule l'emprise du site, apparue en
#: v5, manque aux plus anciennes, et nous avons la nôtre.
#:
#: Une version PLUS RÉCENTE est refusée, et non lue au mieux : c'est la règle du
#: contrat d'entrée du lot 4. `photos-geoloc` la lit quand même avec un
#: avertissement, ce qui convient à un rapport interne ; un dossier qui part à
#: l'instruction ne se contente pas d'un « des informations peuvent être
#: perdues ».
VERSION_CARTE_MAX = 5

#: Au-delà de cette incertitude annoncée par l'appareil, la position est
#: signalée. Valeur reprise de `photos-geoloc`, calée sur l'usage : à l'échelle
#: d'une visite de site, 100 m ne veulent plus rien dire — on change de
#: parcelle. Un téléphone en bonne réception annonce environ 5 m.
SEUIL_PRECISION_M = 20.0

#: Provenances d'une position ou d'un cap, pour le rapport de génération.
ORIGINE_EXIF = "exif"
ORIGINE_CARTE = "carte"
ORIGINE_MAIN = "main"

#: Demi-côté long du film 35 mm, en millimètres : 36 / 2. C'est la référence de
#: `FocalLengthIn35mmFilm`, et donc du champ de vue qu'on en déduit.
_DEMI_COTE_LONG_MM = 18.0


def demi_angle_vue_deg(
    focale_35mm: float | None, largeur_px: int | None, hauteur_px: int | None
) -> float | None:
    """Demi-champ horizontal d'une photo, en degrés, ou `None` s'il est inconnu.

    C'est l'ouverture du cône de visée porté par le plan de repérage. Elle se
    calcule sur le **côté long** de l'image, tenu pour les 36 mm du film 35 mm,
    l'autre côté s'en déduisant par le rapport d'image.

    PIÈGE — LE ROGNAGE (D6), mesuré le 15/09/2026 sur les photos de validation
    -------------------------------------------------------------------------
    GPS Map Camera peut rendre une photo en 9:16 quand le capteur sort du 3:4 :
    `20260618_083511660_iOS.jpg` fait 2247 x 4032, soit un rapport de 0,557. La
    règle courante « le côté court vaut 24 mm » y donnerait un champ trop large
    d'un cinquième, puisque c'est justement ce côté-là qui a été rogné. Calculer
    sur le côté long, qui n'est jamais celui que ces rognages retirent, traite
    le cas sans avoir à le détecter.

    L'incertitude qui reste — la convention exacte de `FocalLengthIn35mmFilm`
    varie d'un fabricant à l'autre, largeur ou diagonale — est de l'ordre de
    10 %. C'est petit devant les 10 à 20° d'erreur d'une boussole de téléphone,
    et le cône est un repère de lecture, pas une mesure.

    Toutes les photos ne portent pas la focale : `20231004_172552.jpg` n'en a
    aucune. On ne l'invente pas, et la planche porte alors l'axe de visée seul.
    """
    if not focale_35mm or focale_35mm <= 0:
        return None
    if not largeur_px or not hauteur_px or largeur_px <= 0 or hauteur_px <= 0:
        return None
    from math import atan, degrees

    if largeur_px >= hauteur_px:
        demi_mm = _DEMI_COTE_LONG_MM
    else:
        demi_mm = _DEMI_COTE_LONG_MM * largeur_px / hauteur_px
    return degrees(atan(demi_mm / float(focale_35mm)))


# ---------------------------------------------------------------------------
# Le point de vue, et ce qui le décrit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PointDeVue:
    """Une prise de vue reportée sur un plan de repérage, en Lambert 93.

    `cap_deg` est l'azimut géographique de la visée, ou `None` si la direction
    n'est pas connue. `cap_confirme` dit si cette valeur fait autorité : un cap
    EXIF seul ne la fait pas, un cap venu d'une carte `photos-geoloc` ou visé
    sur la carte de l'application la font. C'est `dessine_un_cone` qui tranche,
    et lui seul — comparer `cap_deg is not None` ailleurs ferait ressortir un
    cap non confirmé sur la planche.
    """

    nom: str
    x: float
    y: float
    cap_deg: float | None = None
    origine_position: str = ORIGINE_MAIN
    origine_cap: str | None = None
    cap_confirme: bool = False
    precision_m: float | None = None
    #: Demi-champ horizontal de la photo, en degrés, ou `None` s'il est inconnu.
    #: Voir `demi_angle_vue_deg` : il ne s'invente pas.
    demi_angle_deg: float | None = None
    #: Rang du point sur la carte du rapport, quand il en vient. Sert à parler la
    #: même langue que le chef de projet, qui a ce numéro sous les yeux — jamais
    #: à numéroter la pièce, qui repart de 1 par pièce.
    ordre_rapport: int | None = None

    @property
    def point(self):
        """La position en géométrie shapely, pour le dessin et les mesures."""
        from shapely.geometry import Point

        return Point(self.x, self.y)

    @property
    def dessine_une_visee(self) -> bool:
        """Vrai si la planche doit montrer ce que ce point regarde.

        Direction connue **et** confirmée : c'est la seule condition. Sans elle,
        le repère est posé seul, ce qui est le cas normal d'une vue de drone.
        """
        return self.cap_deg is not None and self.cap_confirme

    @property
    def dessine_un_cone(self) -> bool:
        """Vrai si cette visée peut s'ouvrir en cône, et pas seulement en axe.

        Il y faut le champ de vue, que toutes les photos ne portent pas — un
        photomontage n'a aucun EXIF, et une photo sur cinq du jeu de validation
        n'annonce pas sa focale. On ne l'invente pas : la planche porte alors
        l'axe de visée seul, ce qui dit la direction sans prétendre à une
        ouverture. Lecture de D6, qui interdit d'inventer un champ de vue et non
        de montrer une direction vérifiée.
        """
        return self.dessine_une_visee and self.demi_angle_deg is not None

    @property
    def cap_trigonometrique_deg(self) -> float | None:
        """Le cap en angle mathématique : 0° à l'est, sens trigonométrique.

        Seule conversion admise entre l'azimut géographique de ce module et la
        convention du reste du dépôt. Voir le piège en tête de fichier.
        """
        if self.cap_deg is None:
            return None
        return (90.0 - self.cap_deg) % 360.0

    @property
    def position_peu_fiable(self) -> bool:
        """Vrai si l'appareil a annoncé une incertitude au-delà du seuil.

        `None` signifie « incertitude inconnue », surtout pas « mauvaise » : la
        plupart des applications photo n'écrivent pas ce champ.
        """
        return self.precision_m is not None and self.precision_m > SEUIL_PRECISION_M


@dataclass(frozen=True)
class MetadonneesPhoto:
    """Ce que l'EXIF d'une photographie a livré, et ce qu'il n'a pas livré.

    `avertissements` n'est jamais décoratif : chaque champ illisible y laisse une
    phrase. Un `pass` silencieux sur un champ EXIF abîmé ferait dessiner une
    planche muette sur ce qu'elle ignore.
    """

    nom: str
    lat: float | None = None
    lon: float | None = None
    cap_deg: float | None = None
    precision_m: float | None = None
    date: datetime | None = None
    #: Équivalent 35 mm de la focale (`FocalLengthIn35mmFilm`), et dimensions de
    #: l'image : ensemble, ils donnent le champ de vue. Voir `demi_angle_vue_deg`.
    focale_35mm: float | None = None
    largeur_px: int | None = None
    hauteur_px: int | None = None
    avertissements: tuple[str, ...] = ()

    @property
    def demi_angle_deg(self) -> float | None:
        return demi_angle_vue_deg(self.focale_35mm, self.largeur_px, self.hauteur_px)

    @property
    def geolocalisee(self) -> bool:
        return self.lat is not None and self.lon is not None


# ---------------------------------------------------------------------------
# Constructeurs — la règle de confirmation du cap est ici, et nulle part ailleurs
# ---------------------------------------------------------------------------


def depuis_exif(metadonnees: MetadonneesPhoto) -> PointDeVue:
    """Point de vue issu de l'EXIF d'une photographie déposée seule.

    Le cap lu **n'est pas confirmé** : il propose une orientation, que le chef de
    projet valide en visant sur la carte. Tant qu'il ne l'a pas fait, la planche
    porte le repère sans cône.

    Lève si la photo n'est pas géolocalisée : c'est à l'appelant de proposer
    alors le placement à la main, pas à ce constructeur d'inventer une position.
    """
    if not metadonnees.geolocalisee:
        raise ErreurPhotoIllisible(
            f"« {metadonnees.nom} » ne porte pas de position GPS : son point de "
            "vue doit être placé sur la carte."
        )
    x, y = vers_l93(metadonnees.lat, metadonnees.lon)
    return PointDeVue(
        nom=metadonnees.nom,
        x=x,
        y=y,
        cap_deg=metadonnees.cap_deg,
        origine_position=ORIGINE_EXIF,
        origine_cap=ORIGINE_EXIF if metadonnees.cap_deg is not None else None,
        cap_confirme=False,
        precision_m=metadonnees.precision_m,
        demi_angle_deg=metadonnees.demi_angle_deg,
    )


def place_a_la_main(
    nom: str,
    x: float,
    y: float,
    cap_deg: float | None = None,
    demi_angle_deg: float | None = None,
) -> PointDeVue:
    """Point de vue posé sur la carte de l'application, et visé s'il y a lieu.

    Le cap est confirmé dès qu'il existe : le chef de projet vient de désigner ce
    que la photo regarde, sur le plan du bureau d'études et sur fond IGN. C'est
    le geste « Viser » de `photos-geoloc`, au même sens.
    """
    return PointDeVue(
        nom=nom,
        x=float(x),
        y=float(y),
        cap_deg=None if cap_deg is None else float(cap_deg) % 360.0,
        origine_position=ORIGINE_MAIN,
        origine_cap=None if cap_deg is None else ORIGINE_MAIN,
        cap_confirme=cap_deg is not None,
        demi_angle_deg=demi_angle_deg,
    )


# ---------------------------------------------------------------------------
# Géométrie — les deux seules conversions du module
# ---------------------------------------------------------------------------


def cap_vers(
    x_origine: float, y_origine: float, x_cible: float, y_cible: float
) -> float:
    """Azimut géographique, en Lambert 93, de l'origine vers la cible.

    Transposition de `capVers()` de `photos-geoloc`, où viser consiste à cliquer
    ce que la photo regarde plutôt qu'à saisir un angle. `atan2(dx, dy)` et non
    `atan2(dy, dx)` : le résultat est un azimut depuis le nord, pas un angle
    depuis l'est. Voir le piège en tête de fichier.

    Le Lambert 93 n'est pas conforme au nord géographique partout — la
    convergence des méridiens atteint 3° aux bords de la France. C'est sans
    conséquence ici : le cap sert à orienter un cône sur une planche, et
    l'incertitude d'une boussole de téléphone vaut cinq fois cet écart.
    """
    from math import atan2, degrees

    return degrees(atan2(x_cible - x_origine, y_cible - y_origine)) % 360.0


def vers_l93(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 en Lambert 93. Tout le traitement géométrique du dépôt y vit."""
    from pyproj import Transformer

    transformateur = Transformer.from_crs(4326, 2154, always_xy=True)
    return transformateur.transform(float(lon), float(lat))
