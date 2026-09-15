"""Lecture d'une carte « photos-geoloc » déposée comme source de points de vue.

Le chef de projet qui a fait une visite de site en a déjà fait un rapport, et il
y a déjà placé chaque prise de vue et corrigé sa direction, à l'œil et sur fond
satellite. Ce module relit ce travail plutôt que de le lui faire refaire.

CE QUI FAIT FOI
---------------
Le bloc `<script id="donnees-carte" type="application/json">`, jamais le DOM. Une
carte réenregistrée depuis le navigateur est structurellement identique à une
carte fraîchement produite : il n'y a pas d'« original » à distinguer.

Les points en corbeille (`masque: true`) sont écartés — le chef de projet les a
mis de côté — et leur nombre est rapporté.

LE PIÈGE MESURÉ LE 15/09/2026 : LE CHAMP `cap` EST UN CACHE
------------------------------------------------------------
Le format documente `lat`, `lon` et `cap` comme des valeurs déduites, réécrites
à chaque enregistrement « pour que les lecteurs du fichier n'aient pas à refaire
le calcul ». C'est vrai, et c'est le contrat.

Mais la page, elle, ne les lit pas : `capEffectif()` recalcule depuis
`cap_manuel`, `cap_brut` et l'offset de calibration, et `positionEffective()`
depuis `lat_manuel` / `lat_brut`. **Ce que le chef de projet a vu à l'écran et
validé, ce sont donc ces valeurs recalculées**, pas le champ mis en cache. Les
deux ne peuvent diverger que sur un fichier abîmé ou édité à la main — mais
alors la planche porterait une direction que personne n'a jamais vue.

On rejoue donc la règle, et on croit la source plutôt que le cache. Quand les
deux diffèrent, le rapport de génération le dit : c'est le signe d'un fichier
retouché hors de l'outil.

Exception nécessaire aux cartes anciennes : avant la v3 il n'y a pas de
`cap_brut`, avant la v4 pas de `lat_brut`. Le cache est alors la seule valeur
disponible, et c'est exactement ce que la migration de `photos-geoloc` en
ferait. On le prend tel quel.

LA MÉMOIRE, QUI EST LE VRAI SUJET
----------------------------------
Une carte de quarante photos pèse une vingtaine de mégaoctets de base64, et
Streamlit **relit un fichier déposé à chaque exécution du script** : tout
décodage coûteux est payé à chaque interaction, pas une fois. Le dépôt voisin
s'est fait couper par l'hébergeur pour dépassement mémoire avant nous.

Trois précautions, dans cet ordre :

1. rester en **octets** de bout en bout — `json.loads` les accepte, et une
   chaîne Python a une largeur uniforme dictée par son caractère le plus large :
   un seul emoji dans un commentaire fait stocker tout le base64 sur 4 octets
   par caractère ;
2. **élaguer les images avant de parser**, par substitution sur les octets.

Une troisième précaution était prévue et s'est révélée fausse : chercher le
marqueur par la fin (`rfind`), au motif que le bloc serait écrit quasiment en fin
de document. Mesuré le 15/09/2026 sur un rapport réel de 17,8 Mo : le bloc est à
49 % du fichier, et le **script de réenregistrement de la page**, qui vient
après, porte le marqueur en toutes lettres dans une de ses chaînes. Un `rfind`
attrape donc cette mention et non le bloc. Le scan que l'optimisation voulait
éviter coûte 0,76 ms sur ce même fichier — rien qui vaille un piège pareil.

L'élagage est une optimisation, pas une condition de justesse : nous ne gardons
de toute façon que les métadonnées. S'il ne rend rien — format changé, base64
écrit autrement — la lecture reste correcte, seul le pic de mémoire est payé, et
le rapport le dit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from dp_socle.erreurs import ErreurCartePhotos
from dp_socle.points_de_vue import (
    ORIGINE_CARTE,
    VERSION_CARTE_MAX,
    PointDeVue,
    vers_l93,
)

_OUVERTURE = '<script id="donnees-carte" type="application/json">'
_FERMETURE = "</script>"

#: Le base64 d'une image, tel que le format l'écrit : `"image"` suivi d'une
#: chaîne sans autre caractère que l'alphabet base64. Aucune séquence échappée
#: ne peut donc s'y cacher, et un commentaire qui contiendrait ce texte verrait
#: ses guillemets échappés en `\"` — le motif ne peut viser qu'une vraie clé.
_MOTIF_IMAGE = rb'"image"\s*:\s*"[A-Za-z0-9+/=]*"'
_IMAGE_VIDE = b'"image":""'

#: Écart au-delà duquel un cap mis en cache est jugé en désaccord avec sa
#: source. Large à dessein : l'arrondi d'écriture ne doit pas déclencher
#: l'alerte, une retouche de fichier oui.
_TOLERANCE_CAP_DEG = 0.5
_TOLERANCE_POSITION_DEG = 1e-6  # ~0,1 m sous nos latitudes


@dataclass(frozen=True)
class PointDeCarte:
    """Un point lu dans la carte, avant toute affectation à une pièce.

    L'image n'y figure pas : elle reste dans le fichier et n'est décodée qu'à la
    demande, en vignette, au moment de la galerie.
    """

    identifiant: int
    nom: str
    #: Le numéro que ce point porte sur les marqueurs de la carte du rapport.
    #: C'est le seul repère commun entre les deux écrans — mesuré le 15/09/2026 :
    #: c'est le **rang** dans les points non masqués triés par `ordre`, et non la
    #: valeur du champ `ordre`.
    numero: int
    lat: float
    lon: float
    cap_deg: float | None = None
    #: Vrai si cette direction a été **touchée** dans le rapport : figée à la
    #: main, ou reprise par la calibration globale de la boussole. Un cap sorti
    #: brut de l'EXIF et jamais regardé ne l'est pas. Voir `lire_carte`.
    cap_confirme: bool = False
    precision_m: float | None = None
    commentaire: str = ""


@dataclass(frozen=True)
class CartePhotos:
    """Le contenu utile d'une carte déposée."""

    titre: str
    version: int
    points: tuple[PointDeCarte, ...]
    #: Périmètre du projet porté par le rapport, en WGS84, ou `None`. Absent des
    #: cartes antérieures à la v5, et facultatif de toute façon : l'emprise qui
    #: fait foi pour le dossier est la nôtre.
    emprise_wgs84: tuple | None = None
    #: Points écartés parce qu'ils sont en corbeille.
    masques: int = 0
    avertissements: tuple[str, ...] = ()


def lire_carte(document: bytes | str) -> CartePhotos:
    """Relit le bloc de données d'une carte `photos-geoloc`.

    `document` est attendu en **octets** — c'est la voie que prend un fichier
    déposé dans Streamlit, et la seule qui ne matérialise jamais la carte en
    chaîne Python. Le texte est accepté pour les tests.
    """
    avertissements: list[str] = []
    document, elaguees = _elaguer_images(document)
    donnees = _bloc_de_donnees(document)

    version = donnees.get("version", 0)
    if not isinstance(version, int):
        raise ErreurCartePhotos(
            f"Carte illisible : sa version n'est pas un nombre ({version!r})."
        )
    if version > VERSION_CARTE_MAX:
        raise ErreurCartePhotos(
            f"Cette carte est au format {version}, plus récent que celui connu "
            f"ici ({VERSION_CARTE_MAX}). Elle n'est pas lue : un dossier ne se "
            "construit pas sur des données à demi comprises. Mettez le "
            "générateur à jour, ou réenregistrez la carte depuis une version "
            "antérieure de photos-geoloc."
        )

    bruts = donnees.get("points")
    if not isinstance(bruts, list):
        raise ErreurCartePhotos(
            "Carte abîmée : son bloc de données ne décrit pas une liste de photos."
        )

    if elaguees == 0 and bruts:
        avertissements.append(
            "Les images de la carte n'ont pas pu être écartées avant lecture : "
            "elle a été chargée en entier en mémoire. La lecture est correcte, "
            "mais le format d'écriture des images a probablement changé."
        )

    points, masques, messages = _points(bruts, donnees.get("offset", 0) or 0)
    avertissements.extend(messages)

    return CartePhotos(
        titre=str(donnees.get("titre") or "Rapport de visite"),
        version=version,
        points=points,
        emprise_wgs84=_emprise(donnees.get("emprise")),
        masques=masques,
        avertissements=tuple(avertissements),
    )


def depuis_carte(point: PointDeCarte) -> PointDeVue:
    """Point de vue issu d'une carte `photos-geoloc`, en Lambert 93.

    Une direction **corrigée dans le rapport** part confirmée : le chef de projet
    l'a réglée sur fond satellite, ce qui est la bonne façon de le faire, et le
    lui redemander ici serait lui faire refaire sur un fond moins lisible un
    travail déjà fait au bon endroit.

    Une direction **jamais touchée**, non. Écart à la décision D0 du brief, qui
    tenait le dépôt d'un rapport pour une validation de ses directions. Mesuré le
    15/09/2026 sur « Rapport Photo SARNOIS » : 25 points, calibration nulle,
    aucune direction figée — le chef de projet avait produit son rapport sans
    toucher aux caps. Les traiter comme confirmés aurait dessiné 25 cônes issus
    d'une boussole de téléphone, dont l'un que le dépôt `photomontage` a mesuré
    faux de 15°. C'est la règle du dépôt qui tranche : le cap ne se croit pas.

    Une position replacée à la main dans le rapport vaut une position mesurée :
    le choix est assumé (décision du 10/09/2026), et rien ne la distingue ici.
    """
    x, y = vers_l93(point.lat, point.lon)
    return PointDeVue(
        nom=point.nom,
        x=x,
        y=y,
        cap_deg=point.cap_deg,
        origine_position=ORIGINE_CARTE,
        origine_cap=ORIGINE_CARTE if point.cap_deg is not None else None,
        cap_confirme=point.cap_deg is not None and point.cap_confirme,
        precision_m=point.precision_m,
        ordre_rapport=point.numero,
    )


# ---------------------------------------------------------------------------
# Découpage du fichier
# ---------------------------------------------------------------------------


def _elaguer_images(document: bytes | str) -> tuple[bytes | str, int]:
    """Vide les images du document sans le décoder. Rend le document et le compte."""
    if isinstance(document, bytes):
        return re.subn(_MOTIF_IMAGE, _IMAGE_VIDE, document)
    motif = _MOTIF_IMAGE.decode("ascii")
    return re.subn(motif, _IMAGE_VIDE.decode("ascii"), document)


def _bloc_de_donnees(document: bytes | str) -> dict:
    """Extrait et parse le bloc JSON, sans analyse HTML.

    Le découpage est sûr : l'écriture échappe les « < » en `\\u003c`, aucun « < »
    littéral ne peut donc figurer dans le JSON et le premier `</script>` qui suit
    la balise ouvrante en est bien le terminateur.
    """
    ouverture, fermeture = (
        (_OUVERTURE.encode("utf-8"), _FERMETURE.encode("utf-8"))
        if isinstance(document, bytes)
        else (_OUVERTURE, _FERMETURE)
    )
    debut, fin = _bornes(document, ouverture, fermeture)

    try:
        donnees = json.loads(document[debut:fin])
    except UnicodeDecodeError as erreur:
        raise ErreurCartePhotos(
            "Carte abîmée : son bloc de données n'est pas du texte lisible. Le "
            "fichier a probablement été altéré en cours de transfert."
        ) from erreur
    except json.JSONDecodeError as erreur:
        raise ErreurCartePhotos(
            f"Carte abîmée : son bloc de données n'est pas lisible "
            f"({erreur.msg}, caractère {erreur.pos})."
        ) from erreur

    if not isinstance(donnees, dict):
        raise ErreurCartePhotos(
            "Carte abîmée : son bloc de données ne décrit pas une carte."
        )
    return donnees


def _bornes(document, ouverture, fermeture) -> tuple[int, int]:
    """Bornes du premier bloc de données qui en soit vraiment un.

    Le marqueur apparaît deux fois dans une carte : le bloc lui-même, et la
    chaîne du script qui réécrit la page à l'enregistrement. On retient donc la
    première occurrence dont le contenu **commence par une accolade** — la
    mention du script est suivie d'une concaténation, jamais de JSON.

    Ce contrôle rend le découpage insensible à l'ordre des deux, et donc à une
    réorganisation du gabarit chez le voisin.
    """
    accolade = b"{" if isinstance(document, bytes) else "{"
    depart = 0
    while True:
        debut = document.find(ouverture, depart)
        if debut == -1:
            break
        debut += len(ouverture)
        fin = document.find(fermeture, debut)
        if fin == -1:
            raise ErreurCartePhotos(
                "Carte abîmée : son bloc de données n'est pas refermé."
            )
        if document[debut:fin].lstrip()[:1] == accolade:
            return debut, fin
        depart = fin

    raise ErreurCartePhotos(
        "Ce fichier n'est pas une carte produite par photos-geoloc : son bloc de "
        "données est introuvable. Déposez le fichier HTML produit par l'outil, ou "
        "réenregistré depuis la carte."
    )


# ---------------------------------------------------------------------------
# Les points, et les deux règles jumelles de photos-geoloc
# ---------------------------------------------------------------------------


def _points(bruts: list, offset: float) -> tuple[tuple[PointDeCarte, ...], int, list]:
    """Les points visibles, numérotés comme la carte les numérote.

    Mesuré le 15/09/2026 dans `generation_html.py` : `rendreMarqueurs()` numérote
    par `i + 1` sur `pointsVisibles()`, qui filtre les masqués **puis** trie par
    `ordre`. Le numéro d'un marqueur est donc un rang dans cette liste, jamais la
    valeur du champ `ordre`. Écart au brief du lot, qui annonçait un numéro
    calculé sur la liste complète : la corbeille décale bien la numérotation.
    """
    avertissements: list[str] = []
    visibles = [point for point in bruts if isinstance(point, dict) and not point.get("masque")]
    masques = len(bruts) - len(visibles)
    visibles.sort(key=lambda point: point.get("ordre", 0))

    points: list[PointDeCarte] = []
    for rang, brut in enumerate(visibles, start=1):
        lat, lon = _position_effective(brut, avertissements)
        if lat is None or lon is None:
            avertissements.append(
                f"Point {rang} de la carte (« {brut.get('nom', '?')} ») sans "
                "position : il est ignoré."
            )
            continue
        cap_deg, cap_confirme = _cap_effectif(brut, offset, avertissements)
        points.append(
            PointDeCarte(
                identifiant=brut.get("id", rang),
                nom=str(brut.get("nom") or f"Photo {rang}"),
                numero=rang,
                lat=lat,
                lon=lon,
                cap_deg=cap_deg,
                cap_confirme=cap_confirme,
                precision_m=_nombre(brut.get("precision_m")),
                commentaire=str(brut.get("commentaire") or ""),
            )
        )

    bruts_non_regardes = sum(
        1 for point in points if point.cap_deg is not None and not point.cap_confirme
    )
    if bruts_non_regardes:
        avertissements.append(
            f"{bruts_non_regardes} direction(s) de ce rapport sortent de la "
            "boussole du téléphone sans avoir été corrigées : ni calibration "
            "globale, ni visée point par point. Elles sont reprises comme des "
            "propositions — visez-les sur la carte pour qu'un cône soit dessiné."
        )
    return tuple(points), masques, avertissements


def _cap_effectif(
    point: dict, offset: float, avertissements: list
) -> tuple[float | None, bool]:
    """La règle du cap, jumelle de `capEffectif()` dans la page, et sa confiance.

    Une direction figée à la main l'emporte et ne suit pas la calibration ; sinon
    la direction d'origine reçoit l'offset ; sinon il n'y a pas de cône.

    Le second terme dit si cette direction a été **regardée**. Une direction
    figée à la main l'a été, une par une ; une calibration globale non nulle l'a
    été aussi, puisqu'elle se règle en voyant les cônes pointer les bons éléments
    du paysage, et qu'un téléphone mal calibré décale tout du même angle. Un cap
    sorti brut de l'EXIF, sur un rapport où rien n'a été touché, ne l'a pas été.
    """
    cache = _nombre(point.get("cap"))
    calibre = abs(offset) > 1e-9
    if point.get("cap_manuel") is not None:
        return _confronter(point, _nombre(point["cap_manuel"]), cache, avertissements), True
    if point.get("cap_brut") is None:
        # Carte antérieure à la v3 : pas de `cap_brut`, le cache est la seule
        # valeur, et c'est ce que la migration en ferait.
        return cache, calibre
    brut = _nombre(point["cap_brut"])
    valeur = None if brut is None else (brut + offset) % 360.0
    return _confronter(point, valeur, cache, avertissements), calibre


def _confronter(
    point: dict, valeur: float | None, cache: float | None, avertissements: list
) -> float | None:
    """Retient la valeur recalculée, et signale un cache qui ne la suit plus."""

    if (
        valeur is not None
        and cache is not None
        and abs(((valeur - cache + 180.0) % 360.0) - 180.0) > _TOLERANCE_CAP_DEG
    ):
        avertissements.append(
            f"« {point.get('nom', '?')} » : la direction enregistrée ({cache:.0f}°) "
            f"ne correspond pas à celle que la carte affiche ({valeur:.0f}°). "
            "C'est celle de la carte qui est retenue — le fichier a été retouché "
            "hors de l'outil."
        )
    return valeur


def _position_effective(point: dict, avertissements: list) -> tuple:
    """La règle de la position, jumelle de `positionEffective()` dans la page.

    Une position replacée à la main l'emporte ; sinon c'est celle d'origine.
    """
    cache = (_nombre(point.get("lat")), _nombre(point.get("lon")))
    if point.get("lat_manuel") is not None and point.get("lon_manuel") is not None:
        valeur = (_nombre(point["lat_manuel"]), _nombre(point["lon_manuel"]))
    elif point.get("lat_brut") is None:
        # Carte antérieure à la v4 : pas de `lat_brut`.
        return cache
    else:
        valeur = (_nombre(point.get("lat_brut")), _nombre(point.get("lon_brut")))

    if all(v is not None for v in valeur) and all(v is not None for v in cache):
        if (
            abs(valeur[0] - cache[0]) > _TOLERANCE_POSITION_DEG
            or abs(valeur[1] - cache[1]) > _TOLERANCE_POSITION_DEG
        ):
            avertissements.append(
                f"« {point.get('nom', '?')} » : la position enregistrée ne "
                "correspond pas à celle que la carte affiche. C'est celle de la "
                "carte qui est retenue — le fichier a été retouché hors de l'outil."
            )
    return valeur


def _emprise(brut) -> tuple | None:
    """Les poches du périmètre porté par le rapport, en WGS84, ou `None`."""
    if not isinstance(brut, dict):
        return None
    poches = brut.get("poches")
    if not isinstance(poches, list) or not poches:
        return None
    return tuple(
        tuple((float(lat), float(lon)) for lat, lon in poche)
        for poche in poches
        if isinstance(poche, list) and poche
    ) or None


def _nombre(valeur) -> float | None:
    """Un flottant, ou `None` si la valeur n'en est pas un. Jamais d'exception."""
    if valeur is None or isinstance(valeur, bool):
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None
