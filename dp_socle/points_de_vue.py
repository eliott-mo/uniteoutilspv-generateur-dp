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

from dp_socle.erreurs import ErreurPhotoIllisible, ErreurPointDeVue

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
    def dessine_un_cone(self) -> bool:
        """Vrai si la planche doit montrer ce que ce point regarde.

        Direction connue **et** confirmée : c'est la seule condition. Sans elle,
        le repère est posé seul, ce qui est le cas normal d'une vue de drone.

        Le cône porté par la planche est un **symbole d'orientation** de taille
        fixe, comme celui des marqueurs de `photos-geoloc` : il dit d'où l'on
        regarde et vers où, pas jusqu'où ni sur quelle largeur. Le champ de vue
        réel de la photographie n'entre donc pas dans la condition — décision du
        16/09/2026, qui écarte du même coup le calcul de focale que D6 prescrivait
        et les erreurs de rognage qui allaient avec.
        """
        return self.cap_deg is not None and self.cap_confirme

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
    avertissements: tuple[str, ...] = ()

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
    )


def place_a_la_main(
    nom: str,
    x: float,
    y: float,
    cap_deg: float | None = None,
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


# ---------------------------------------------------------------------------
# Ce qui survit à un rechargement de page
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PriseDeVue:
    """Un point de vue et les images qu'il donne, pour une pièce du dossier.

    Une prise de DP 7 ou DP 8 porte une photographie ; une prise de DP 6 en
    porte deux ou trois — les volets d'une même vue, qui partagent forcément le
    même point de vue puisque c'est la même prise (D3 du brief : un photomontage
    est un rendu, sa position est celle de la photographie d'origine).
    """

    point_de_vue: PointDeVue
    images: tuple[str, ...]
    #: Décalage de rognage de chaque image, dans l'ordre. Voir
    #: `planches.photographies.ImagePlanche.cadrage`.
    cadrages: tuple[tuple[float, float], ...] = ()

    def cadrage_de(self, rang: int) -> tuple[float, float]:
        """Le cadrage de l'image de ce rang, centré par défaut."""
        if rang < len(self.cadrages):
            return tuple(self.cadrages[rang])
        return (0.0, 0.0)


def point_de_vue_en_json(vue: PointDeVue) -> dict:
    """Le point de vue tel qu'il s'écrit dans `projet.json`.

    Les champs déduits ne sont pas écrits : `dessine_un_cone` se recalcule, et
    l'écrire permettrait à un fichier retouché de faire dessiner un cône que la
    règle refuse. Le fichier ne porte que ce qui a été décidé.
    """
    return {
        "nom": vue.nom,
        "x": vue.x,
        "y": vue.y,
        "cap_deg": vue.cap_deg,
        "origine_position": vue.origine_position,
        "origine_cap": vue.origine_cap,
        "cap_confirme": vue.cap_confirme,
        "precision_m": vue.precision_m,
        "ordre_rapport": vue.ordre_rapport,
    }


def point_de_vue_depuis_json(donnees: dict) -> PointDeVue:
    """Relit un point de vue écrit par `point_de_vue_en_json`.

    Les champs absents prennent leur valeur par défaut, sauf la position, sans
    laquelle il n'y a pas de point de vue du tout.
    """
    for champ in ("x", "y"):
        if donnees.get(champ) is None:
            raise ErreurPointDeVue(
                f"Point de vue sans « {champ} » dans projet.json : une prise de "
                "vue sans position ne se reporte sur aucun plan."
            )
    return PointDeVue(
        nom=str(donnees.get("nom") or "prise de vue"),
        x=float(donnees["x"]),
        y=float(donnees["y"]),
        cap_deg=None if donnees.get("cap_deg") is None else float(donnees["cap_deg"]),
        origine_position=str(donnees.get("origine_position") or ORIGINE_MAIN),
        origine_cap=donnees.get("origine_cap"),
        cap_confirme=bool(donnees.get("cap_confirme", False)),
        precision_m=(
            None if donnees.get("precision_m") is None
            else float(donnees["precision_m"])
        ),
        ordre_rapport=(
            None if donnees.get("ordre_rapport") is None
            else int(donnees["ordre_rapport"])
        ),
    )


def prise_en_json(prise: PriseDeVue) -> dict:
    return {
        "point_de_vue": point_de_vue_en_json(prise.point_de_vue),
        "images": list(prise.images),
        "cadrages": [list(cadrage) for cadrage in prise.cadrages],
    }


def prise_depuis_json(donnees: dict) -> PriseDeVue:
    images = donnees.get("images") or []
    if not images:
        raise ErreurPointDeVue(
            "Prise de vue sans image dans projet.json : il n'y a rien à poser "
            "sur la planche."
        )
    return PriseDeVue(
        point_de_vue=point_de_vue_depuis_json(donnees.get("point_de_vue") or {}),
        images=tuple(str(image) for image in images),
        cadrages=tuple(
            (float(cadrage[0]), float(cadrage[1]))
            for cadrage in donnees.get("cadrages") or []
        ),
    )
