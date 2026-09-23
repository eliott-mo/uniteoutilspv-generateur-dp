"""Lecture de la position, de la date et du cap dans l'EXIF d'une photographie.

Repris de `photos-geoloc/lecture_exif.py`, qui l'a éprouvé sur des photos
réelles de visite de site, avec deux écarts que la règle de ce dépôt impose.

ÉCART 1 — AUCUN REPLI SILENCIEUX
--------------------------------
L'original avale les champs abîmés par `except Exception: pass` : un cap
illisible y devient une absence de cap, et rien ne le dit. C'est tenable pour un
rapport de visite qu'on relit à l'écran ; ça ne l'est pas pour une planche qui
part à l'instruction, où une direction manquante et une direction perdue ne se
distinguent plus. Chaque champ illisible laisse donc ici une phrase dans
`avertissements`.

ÉCART 2 — LE HEIC SE DIT, IL NE SE DEVINE PAS
---------------------------------------------
Comme l'original, ce module enregistre le décodeur `pillow-heif` avant tout
`Image.open` : le HEIC est le format par défaut des iPhone, et un chef de projet
qui dépose une photo de visite en dépose un sans le savoir.

Mais l'original avale l'échec d'import dans un `except Exception` et laisse
l'application tourner sans le dire à l'utilisateur. Ici l'indisponibilité est un
**état d'environnement**, sur le patron de `environnement.etat_cairo()` : elle
s'annonce au démarrage, et un HEIC déposé lève un message qui désigne la vraie
cause. Sans cela, Pillow dirait seulement qu'il ne reconnaît pas le fichier —
exactement le diagnostic qui a fait accuser la police alors que cairo manquait.

Le piège est réel et mesuré le 15/09/2026 : `pillow-heif` était installé sur le
poste de développement sans figurer dans `requirements.txt`. Un HEIC s'y lisait
donc, et aurait été refusé en production sans que rien ne l'explique.

Le cap `GPSImgDirection` n'est pas écrit par GPS Map Camera : il ne se lit que si
le chef de projet a utilisé une autre application (iPhone, Open Camera,
Solocator). Son absence est le cas courant, pas une anomalie.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dp_socle.erreurs import ErreurPhotoIllisible
from dp_socle.points_de_vue import MetadonneesPhoto

# Identifiants des sous-répertoires EXIF (constantes du standard).
_IFD_GPS = 0x8825
_IFD_EXIF = 0x8769

# Codes des champs utilisés.
_GPS_LAT_REF, _GPS_LAT = 1, 2
_GPS_LON_REF, _GPS_LON = 3, 4
_GPS_DIR_REF, _GPS_DIR = 16, 17
_GPS_PRECISION = 31  # GPSHPositioningError : incertitude horizontale, en mètres
_DATE_ORIGINALE = 36867  # DateTimeOriginal, préféré à DateTime (306)
_DATE_FICHIER = 306

#: Extensions que Pillow ne sait ouvrir qu'avec `pillow-heif` enregistré.
EXTENSIONS_HEIC = (".heic", ".heif", ".heics", ".heifs", ".hif")

#: Ce qui reconnaît, parmi les avertissements, le seul qu'un placement à la main
#: rend caduc. Les autres — cap magnétique, date illisible, incertitude GPS
#: illisible — restent vrais quoi qu'on fasse ensuite.
#:
#: L'écran de saisie affichait tout le lot tant que la photographie vivait :
#: « placez son point de vue sur la carte » se lisait sous une ligne annonçant
#: « placée sur la carte, visée 215° » (retour d'usage du 24/09/2026).
MARQUE_SANS_POSITION = "n'est pas géolocalisée"


@dataclass(frozen=True)
class EtatHeic:
    """Disponibilité du décodeur HEIC, à annoncer au démarrage."""

    disponible: bool
    message: str


def _enregistrer_heic() -> EtatHeic:
    """Enregistre le décodeur HEIC auprès de Pillow, une fois, à l'import.

    Mesuré le 15/09/2026 : l'enregistrement ajoute les cinq extensions HEIF et ne
    retire ni ne remplace aucun format existant — un JPEG et un PNG restent lus
    par leur décodeur habituel.
    """
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError as erreur:
        return EtatHeic(
            False,
            "Le module « pillow-heif » n'est pas installé : les photos HEIC "
            "(format par défaut des iPhone) ne pourront pas être lues. Installez "
            f"les dépendances de requirements.txt. ({erreur})",
        )
    except OSError as erreur:
        # La roue embarque libheif : un échec ici est un binaire inutilisable,
        # pas une absence. Le distinguer évite de renvoyer vers une installation
        # qui a déjà eu lieu.
        return EtatHeic(
            False,
            "Le module « pillow-heif » est installé mais son décodeur ne "
            f"s'initialise pas ({erreur}). Réinstallez-le : « pip install "
            "--force-reinstall pillow-heif ».",
        )
    return EtatHeic(True, "Photos HEIC (iPhone) lisibles.")


ETAT_HEIC = _enregistrer_heic()


def etat_heic() -> EtatHeic:
    """L'état du décodeur HEIC, pour l'annoncer au démarrage de l'application."""
    return ETAT_HEIC


def _dms_vers_degres(dms, reference: str) -> float:
    """Coordonnée EXIF (degrés, minutes, secondes) en degrés décimaux."""
    degres, minutes, secondes = [float(valeur) for valeur in dms]
    decimal = degres + minutes / 60.0 + secondes / 3600.0
    return -decimal if reference in ("S", "W") else decimal


def lire_metadonnees(source, nom: str | None = None) -> MetadonneesPhoto:
    """Ce que l'EXIF de la photographie livre, et ce qu'il n'a pas livré.

    `source` est un chemin, ou un fichier déjà ouvert — celui que Streamlit rend
    d'un dépôt, qui n'a jamais touché le disque. Lire l'EXIF sans écrire un
    fichier temporaire évite de recopier plusieurs mégaoctets à chaque exécution
    du script, et Streamlit en relance une à chaque interaction.

    `nom` prend le pas sur le nom du fichier quand l'appelant en a un meilleur —
    une photo déposée vit sous un nom temporaire qui ne dirait rien au chef de
    projet dans le rapport de génération. Il est **obligatoire** pour un fichier
    ouvert, dont l'extension est le seul moyen de reconnaître un HEIC.

    Une photo sans position n'est pas une erreur ici : elle rend des
    métadonnées sans `lat`/`lon`, et c'est à l'appelant d'en faire un placement
    à la main. Seul un fichier qui ne s'ouvre pas du tout lève.
    """
    from PIL import Image

    chemin = Path(source) if isinstance(source, (str, Path)) else None
    nom = nom or (chemin.name if chemin is not None else None)
    if nom is None:
        raise ErreurPhotoIllisible(
            "Photographie ouverte sans nom : son extension est le seul moyen de "
            "reconnaître un HEIC, et son nom le seul repère du rapport."
        )
    avertissements: list[str] = []

    if Path(nom).suffix.lower() in EXTENSIONS_HEIC and not ETAT_HEIC.disponible:
        # Sans cette vérification, Pillow dirait seulement qu'il ne reconnaît pas
        # le fichier, et le chef de projet croirait sa photo abîmée.
        raise ErreurPhotoIllisible(
            f"« {nom} » est au format HEIC, que cette installation ne sait pas "
            f"ouvrir. {ETAT_HEIC.message}"
        )

    try:
        with Image.open(chemin if chemin is not None else source) as image:
            exif = image.getexif()
            gps = exif.get_ifd(_IFD_GPS)
            bloc_exif = exif.get_ifd(_IFD_EXIF)
    except OSError as erreur:
        raise ErreurPhotoIllisible(
            f"« {nom} » ne s'ouvre pas comme une image ({erreur})."
        ) from erreur

    precision_m = None
    if gps and gps.get(_GPS_PRECISION) is not None:
        # Lue avant les coordonnées : le champ existe indépendamment d'elles.
        try:
            precision_m = float(gps[_GPS_PRECISION])
        except (TypeError, ValueError):
            avertissements.append(
                f"« {nom} » : l'incertitude GPS annoncée est illisible "
                f"({gps[_GPS_PRECISION]!r}). La position est lue quand même, sans "
                "que sa fiabilité puisse être contrôlée."
            )

    cap_deg = None
    if gps and _GPS_DIR in gps:
        try:
            cap_deg = round(float(gps[_GPS_DIR]) % 360.0, 1)
        except (TypeError, ValueError):
            avertissements.append(
                f"« {nom} » : le cap EXIF est illisible ({gps[_GPS_DIR]!r}). Le "
                "point de vue se place sans direction ; visez-la sur la carte."
            )
        else:
            if gps.get(_GPS_DIR_REF) == "M":
                # La déclinaison magnétique vaut 1 à 2° en France, négligeable
                # devant les ±10 à 20° d'une boussole de téléphone. On ne corrige
                # donc pas — mais on ne le tait pas non plus.
                avertissements.append(
                    f"« {nom} » : cap donné par rapport au nord magnétique, repris "
                    "tel quel. L'écart au nord géographique est de 1 à 2° en "
                    "France, sous la précision d'une boussole de téléphone."
                )

    date = None
    brut = bloc_exif.get(_DATE_ORIGINALE) if bloc_exif else None
    brut = brut or exif.get(_DATE_FICHIER)
    if brut:
        try:
            date = datetime.strptime(str(brut), "%Y:%m:%d %H:%M:%S")
        except ValueError:
            avertissements.append(
                f"« {nom} » : la date de prise de vue est illisible ({brut!r})."
            )

    if not gps or _GPS_LAT not in gps or _GPS_LON not in gps:
        avertissements.append(
            f"« {nom} » {MARQUE_SANS_POSITION} : placez son point de vue sur la "
            "carte."
        )
        return MetadonneesPhoto(
            nom=nom,
            cap_deg=cap_deg,
            precision_m=precision_m,
            date=date,
            avertissements=tuple(avertissements),
        )

    try:
        lat = _dms_vers_degres(gps[_GPS_LAT], gps.get(_GPS_LAT_REF, "N"))
        lon = _dms_vers_degres(gps[_GPS_LON], gps.get(_GPS_LON_REF, "E"))
    except (TypeError, ValueError) as erreur:
        avertissements.append(
            f"« {nom} » : coordonnées GPS illisibles ({erreur}). Placez son point "
            "de vue sur la carte."
        )
        return MetadonneesPhoto(
            nom=nom,
            cap_deg=cap_deg,
            precision_m=precision_m,
            date=date,
            avertissements=tuple(avertissements),
        )

    return MetadonneesPhoto(
        nom=nom,
        lat=lat,
        lon=lon,
        cap_deg=cap_deg,
        precision_m=precision_m,
        date=date,
        avertissements=tuple(avertissements),
    )
