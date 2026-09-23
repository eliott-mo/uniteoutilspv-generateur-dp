"""Import d'un export CAO HelioScope et calage en Lambert 93.

HelioScope exporte le calepinage en DXF sans aucune donnée de géolocalisation :
le dessin est dans un repère local, en mètres sol réels, orienté nord en haut.
Seule la position de l'origine est inconnue, et elle se reconstitue à partir de
l'entité IMAGE du fond de plan, dont la résolution encode le niveau de zoom de
la tuile Web Mercator et donc la latitude.

Ce module produit des géométries et des paramètres. Il ne dessine aucune
planche : le dessin relève du lot 4.

Mesures de référence, faites le 02/09/2026 sur les deux exports disponibles
(`helioscope_design_7676351`, Les Islettes 55 ; `helioscope_design_9281861`,
Bray-Saint-Aignan 45) et citées ici parce que plusieurs d'entre elles
contredisent ce que l'on suppose spontanément de ces fichiers.
"""

from __future__ import annotations

import io
import json
import math
import re
import statistics
import zipfile
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import Modelspace
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Polygon, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as transformer_geom
from shapely.ops import polygonize, unary_union

from .erreurs import ErreurCalage, ErreurHelioScope, ErreurModulesAbsents

#: Résolution Web Mercator au niveau de zoom 0, en mètres par pixel à
#: l'équateur. Constante des grilles de tuiles sphériques.
CONSTANTE_MERCATOR = 156543.03392804097

#: Rayon de la sphère Web Mercator (EPSG:3857), et demi-grand axe du WGS84.
RAYON_MERCATOR = 6378137.0

#: Première excentricité au carré de l'ellipsoïde WGS84.
EXCENTRICITE2_WGS84 = 0.00669437999014

#: Bornes du test d'intégrité sur la partie fractionnaire du zoom.
#: Cette partie fractionnaire vaut mathématiquement -log2(cos φ) ; pour la
#: France métropolitaine (41° à 52°) elle reste entre 0,40 et 0,72 et ne
#: s'approche donc jamais d'un entier. Hors de cette plage, le niveau de zoom
#: a été mal identifié et l'implantation sortirait à l'échelle fausse d'un
#: facteur 2, sans aucun signe visible sur la planche.
FRACTION_ZOOM_MIN = 0.40
FRACTION_ZOOM_MAX = 0.72

#: Dénivelé au-delà duquel un côté du module est tenu pour montant, en mètres.
#: Les côtés horizontaux du contour sont exactement à dz = 0 dans les fichiers
#: mesurés ; la tolérance ne sert qu'à absorber un arrondi d'export.
TOLERANCE_DENIVELE_M = 1e-6

#: Tolérance sur la composante horizontale du vecteur v de l'image. Une valeur
#: non nulle signifierait que le fond de plan est tourné, et donc que le DXF
#: n'est pas orienté nord en haut.
TOLERANCE_ROTATION_IMAGE = 1e-9

COUCHE_ZONE = "Field_Segments"
COUCHE_RECULS = "Field_Segment_Setback"
COUCHE_ZONES_EVITEES = "Keepouts"
COUCHE_MODULES = "Modules"

#: L'inclinaison est portée par le nom du bloc module, par exemple
#: `module_characterization_103712_25.0deg_portrait`.
MOTIF_INCLINAISON = re.compile(r"_(\d+(?:\.\d+)?)deg", re.IGNORECASE)

MESSAGE_MODULES_ABSENTS = (
    "L'export HelioScope ne contient aucun module : le calque « Modules » est "
    "déclaré mais vide. C'est la signature d'un export réalisé avant la "
    "finalisation de la section électrique — la zone, les reculs et les zones "
    "évitées sont bien présents, ce qui rend le fichier trompeur.\n"
    "Marche à suivre : rouvrir le design dans HelioScope, terminer la section "
    "électrique, faire « Save & Exit », puis réexporter le Layout CAD."
)


@dataclass
class Calage:
    """Paramètres de passage du repère DXF local au Web Mercator."""

    resolution_m_px: float
    zoom: int
    fraction_zoom: float
    #: Latitude entièrement déduite du fichier. C'est celle du centre de l'image
    #: de fond, et non de l'origine du DXF : voir `ordonnee_centre_image_m`.
    latitude_origine: float
    #: Facteur d'échelle sphérique 1/cos φ de la recette d'origine. Conservé
    #: comme témoin de la lecture du fichier ; le placement ne s'en sert pas,
    #: voir `_transformateur_local`.
    facteur_echelle: float
    #: Seule inconnue du modèle, fixée par le pré-positionnement puis validée
    #: par l'utilisateur. `None` tant que le calage n'a pas été fait.
    longitude_origine: float | None = None
    #: Correction nord-sud appliquée à la main, en mètres, comptée positivement
    #: vers le nord et à partir de la latitude déduite du fichier.
    #:
    #: Stockée comme un écart et non fondue dans `latitude_origine` : la latitude
    #: du fichier reste ainsi lisible, et toute correction saisie se voit.
    #: Depuis que `ordonnee_centre_image_m` rend compte des 11 m qui séparaient
    #: les deux designs des Islettes, ce n'est plus qu'un réglage fin : moins
    #: d'un mètre sur quatre des cinq exports mesurés le 23/09/2026.
    correction_nord_sud_m: float = 0.0
    #: Ordonnée du centre de l'image de fond dans le repère du DXF, en mètres.
    #:
    #: La latitude que la recette tire de la résolution du fond est celle du
    #: **centre de l'image**, pas celle de l'origine du DXF. Mesuré le 23/09/2026
    #: en corrélant le fond de cinq exports avec l'ortho IGN, sans correction
    #: nord-sud : le décalage à rattraper valait l'opposé de cette ordonnée à
    #: 0,7 m près sur quatre d'entre eux, à 4,1 m sur le cinquième.
    #:
    #:     Les Islettes, Export.zip        centre +2,51 m     décalage  −2,75 m
    #:     Les Islettes, Export_2.zip      centre −8,56 m     décalage  +8,50 m
    #:     Bray, export du 01/09/2026      centre −90,98 m    décalage +86,88 m
    #:     Gannay, design 10465241         centre +5,22 m     décalage  −5,58 m
    #:     Bray, design 10482797           centre −134,97 m   décalage +134,31 m
    #:
    #: Les 11 m entre les deux designs des Islettes étaient l'écart de leurs
    #: centres d'image (11,07 m) ; à Bray, les 134 m dépassaient la borne du
    #: réglage nord-sud, et le site ne se calait pas.
    ordonnee_centre_image_m: float = 0.0

    @property
    def latitude_corrigee(self) -> float:
        """Latitude de l'origine du DXF, tout compris. Pour affichage seulement.

        Le placement n'en passe pas par là : il applique le décalage du centre
        de l'image et la correction en mètres dans le repère métrique local, ce
        qui est exact et n'a pas à repasser par un angle.
        """
        return self.latitude_origine + (
            self.correction_nord_sud_m - self.ordonnee_centre_image_m
        ) / (math.pi / 180.0 * RAYON_MERCATOR)

    def exige_origine(self) -> float:
        if self.longitude_origine is None:
            raise ErreurCalage(
                "Le calage est-ouest n'a pas été fait : impossible de projeter "
                "les géométries. Appelez prepositionner() puis faites valider "
                "la superposition par l'utilisateur."
            )
        return self.longitude_origine


#: Suffixes de pose employés par HelioScope dans le nom du bloc module.
POSES = {"portrait": "portrait", "landscape": "paysage"}


@dataclass
class Module:
    """Dimensions et inclinaison d'un module, mesurées dans le bloc.

    Les deux côtés sont nommés par leur rôle et non par leur taille : selon la
    pose, c'est le grand ou le petit côté qui monte la pente.
    """

    #: Côté horizontal, perpendiculaire à la ligne de plus grande pente. Sa
    #: longueur est la même au sol et dans le plan du module.
    largeur_m: float
    #: Côté dans le plan incliné, le rampant. Ce n'est pas la hauteur de la bbox
    #: 2D du bloc, qui en est la projection au sol (rampant × cos i).
    longueur_m: float
    longueur_projetee_m: float
    #: Inclinaison lue dans le nom du bloc, recoupée avec la géométrie 3D.
    inclinaison_deg: float
    inclinaison_mesuree_deg: float
    #: « portrait » si le rampant est le grand côté, « paysage » sinon.
    pose: str
    nom_bloc: str

    @property
    def dimensions_hors_tout(self) -> tuple[float, float]:
        """Les deux dimensions vraies du panneau, du plus petit au plus grand."""
        return tuple(sorted((self.largeur_m, self.longueur_m)))


@dataclass
class Calepinage:
    """Paramètres du calepinage, extraits du DXF.

    Ils alimenteront la coupe DP 3 et le tableau de la notice DP 11 ; les lire
    dans le fichier plutôt que de les ressaisir garantit que le plan, la coupe
    et le texte disent la même chose.
    """

    nb_tables: int
    nb_modules_par_table: int
    nb_modules: int
    module: Module
    orientation_deg: float
    nb_rangees: int
    pas_rangees_m: float
    pas_tables_m: float
    nom_bloc_table: str


@dataclass
class ExportHelioScope:
    """Contenu utile d'un export HelioScope, une fois les ZIP ouverts."""

    identifiant_design: str
    dxf: bytes
    image_fond: bytes | None
    nom_dxf: str
    nom_image: str | None


@dataclass
class Implantation:
    """Résultat complet de l'import : géométries locales, calage, paramètres."""

    identifiant_design: str
    calage: Calage
    calepinage: Calepinage
    #: Géométries dans le repère DXF local, en mètres sol.
    zone_implantation: Polygon
    reculs: list[Polygon]
    zones_evitees: list[Polygon]
    tables: list[Polygon]
    #: Empreinte de chaque module, dans l'ordre des tables. C'est cette couche
    #: que dessine le plan de masse ; `tables` n'en est que le contour groupé.
    modules: list[Polygon]
    avertissements: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Ouverture de l'archive
# ---------------------------------------------------------------------------


def ouvrir_export(chemin: str | Path) -> ExportHelioScope:
    """Extrait le DXF de calepinage et son image de fond de l'export HelioScope.

    L'export est un ZIP qui contient lui-même le ZIP « Layout CAD ». Il porte
    aussi, selon les projets, un rendu PNG et le schéma unifilaire ; ce dernier
    est un DXF qu'il ne faut surtout pas confondre avec le calepinage, d'où la
    sélection par le préfixe `helioscope_design_`.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise ErreurHelioScope(f"Export HelioScope introuvable : {chemin}")

    try:
        with zipfile.ZipFile(chemin) as archive:
            noms = archive.namelist()
            interne = [n for n in noms if n.lower().endswith(".zip")]
            if len(interne) == 1:
                contenu = archive.read(interne[0])
                source = interne[0]
            elif not interne:
                # Certains chefs de projet transmettent directement le Layout CAD.
                contenu = chemin.read_bytes()
                source = chemin.name
            else:
                raise ErreurHelioScope(
                    f"{chemin.name} contient plusieurs archives "
                    f"({', '.join(interne)}) : impossible de savoir laquelle est "
                    "le Layout CAD. Ne transmettez que l'export d'un seul design."
                )
    except zipfile.BadZipFile as exc:
        raise ErreurHelioScope(
            f"{chemin.name} n'est pas une archive ZIP lisible : {exc}"
        ) from exc

    try:
        interne_zip = zipfile.ZipFile(io.BytesIO(contenu))
    except zipfile.BadZipFile as exc:
        raise ErreurHelioScope(
            f"L'archive interne {source} est illisible : {exc}"
        ) from exc

    with interne_zip as cad:
        noms_cad = cad.namelist()
        dxf = [
            n
            for n in noms_cad
            if n.lower().endswith(".dxf")
            and Path(n).name.lower().startswith("helioscope_design_")
        ]
        if not dxf:
            raise ErreurHelioScope(
                f"Aucun DXF de calepinage dans {source} (contenu : "
                f"{', '.join(noms_cad) or 'vide'}). Le fichier attendu s'appelle "
                "helioscope_design_<identifiant>.dxf ; un fichier "
                "« Single-Line Diagram » est le schéma unifilaire, pas le calepinage."
            )
        if len(dxf) > 1:
            raise ErreurHelioScope(
                f"{source} contient plusieurs calepinages ({', '.join(dxf)}). "
                "Ne transmettez qu'un design à la fois."
            )
        nom_dxf = dxf[0]
        octets_dxf = cad.read(nom_dxf)

        images = [n for n in noms_cad if n.lower().endswith((".jpg", ".jpeg", ".png"))]
        nom_image = images[0] if len(images) == 1 else None
        octets_image = cad.read(nom_image) if nom_image else None

    identifiant = Path(nom_dxf).stem.replace("helioscope_design_", "")
    return ExportHelioScope(
        identifiant_design=identifiant,
        dxf=octets_dxf,
        image_fond=octets_image,
        nom_dxf=nom_dxf,
        nom_image=nom_image,
    )


def lire_dxf(octets: bytes) -> Drawing:
    """Charge un DXF depuis des octets."""
    try:
        texte = octets.decode("utf-8")
    except UnicodeDecodeError:
        # Les DXF anciens sont en cp1252 ; HelioScope écrit de l'UTF-8, mais on
        # ne veut pas échouer sur un fichier repassé par un logiciel de CAO.
        texte = octets.decode("cp1252", errors="replace")
    try:
        return ezdxf.read(io.StringIO(texte))
    except (ezdxf.DXFError, OSError) as exc:
        raise ErreurHelioScope(f"DXF illisible : {exc}") from exc


# ---------------------------------------------------------------------------
# Recette de calage
# ---------------------------------------------------------------------------


def _entite_image(msp: Modelspace):
    images = msp.query("IMAGE")
    if not images:
        raise ErreurCalage(
            "Le DXF ne contient pas d'entité IMAGE. Le calage repose entièrement "
            "sur la résolution du fond de plan : sans elle, le calepinage ne peut "
            "pas être géoréférencé. Réexportez le Layout CAD depuis HelioScope en "
            "conservant l'image de fond."
        )
    if len(images) > 1:
        raise ErreurCalage(
            f"Le DXF contient {len(images)} entités IMAGE ; une seule est attendue."
        )
    return images[0]


def calculer_calage(resolution_m_px: float) -> Calage:
    """Applique la recette de recalage validée sur les exports de référence.

    La séquence est reprise telle quelle, sans réécriture : chaque terme a été
    établi empiriquement.

        1. res      = image.u_pixel.x                 (m/px au sol)
        2. z        = floor(log2(K / res))
        3. lat      = acos(res * 2**z / K)
        4. k        = 1 / cos(lat)
        5. Mercator = origine + coordonnées DXF * k
    """
    if not resolution_m_px > 0:
        raise ErreurCalage(
            f"Résolution du fond de plan nulle ou négative ({resolution_m_px}) : "
            "le DXF ne suit pas le modèle HelioScope."
        )

    rapport = math.log2(CONSTANTE_MERCATOR / resolution_m_px)
    zoom = math.floor(rapport)
    fraction = rapport - zoom

    if not FRACTION_ZOOM_MIN <= fraction <= FRACTION_ZOOM_MAX:
        raise ErreurCalage(
            f"Test d'intégrité du zoom en échec : la partie fractionnaire de "
            f"log2(K/res) vaut {fraction:.4f}, hors de la plage attendue "
            f"[{FRACTION_ZOOM_MIN} ; {FRACTION_ZOOM_MAX}] pour la France "
            f"métropolitaine (résolution lue : {resolution_m_px} m/px, "
            f"zoom déduit : {zoom}).\n"
            "Le niveau de zoom n'a donc pas été identifié correctement, et "
            "l'implantation sortirait à une échelle fausse d'un facteur 2 sans "
            "que rien ne le laisse voir sur la planche. Le fichier est refusé."
        )

    cosinus = resolution_m_px * 2**zoom / CONSTANTE_MERCATOR
    if not -1.0 <= cosinus <= 1.0:
        raise ErreurCalage(
            f"Cosinus de latitude hors domaine ({cosinus}) : le DXF ne suit pas "
            "le modèle HelioScope."
        )
    latitude = math.degrees(math.acos(cosinus))
    facteur = 1.0 / cosinus

    return Calage(
        resolution_m_px=resolution_m_px,
        zoom=zoom,
        fraction_zoom=fraction,
        latitude_origine=latitude,
        facteur_echelle=facteur,
    )


def ordonnee_centre_image(image) -> float:
    """Ordonnée du centre de l'image de fond, dans le repère du DXF.

    C'est là, et non à l'origine du DXF, que vaut la latitude déduite de la
    résolution du fond (voir `Calage.ordonnee_centre_image_m`).
    """
    return float(image.dxf.insert.y + image.dxf.image_size.y * image.dxf.v_pixel.y / 2.0)


def _controler_image(image) -> float:
    """Vérifie l'orientation du fond de plan et renvoie sa résolution."""
    v_x = image.dxf.v_pixel.x
    if abs(v_x) > TOLERANCE_ROTATION_IMAGE:
        raise ErreurCalage(
            f"Le fond de plan est tourné (v_pixel.x = {v_x:.3e}, tolérance "
            f"{TOLERANCE_ROTATION_IMAGE:.0e}). La recette de calage suppose un "
            "dessin orienté nord en haut ; ce fichier ne l'est pas et est refusé."
        )
    u = image.dxf.u_pixel
    if abs(u.y) > TOLERANCE_ROTATION_IMAGE:
        raise ErreurCalage(
            f"Le fond de plan est tourné (u_pixel.y = {u.y:.3e}) : dessin non "
            "orienté nord en haut, fichier refusé."
        )
    return float(u.x)


# ---------------------------------------------------------------------------
# Lecture des contours
# ---------------------------------------------------------------------------


def contour(polyligne) -> list[tuple[float, float]]:
    """Ramène une polyligne HelioScope à son anneau (x, y).

    Deux pièges, tous deux mesurés le 02/09/2026 sur le design 7676351 :

    - `Field_Segments` et `Keepouts` sont exportés en polyface mesh, pas en
      polyligne simple. Les derniers sommets sont des *enregistrements de face*
      (drapeau 128 sans le bit 64) tous situés en (0, 0, 0) : les garder ajoute
      un sommet parasite à l'origine, qui crée une pointe et fausse la surface.
      Sur la zone d'implantation des Islettes, 0,719 ha au lieu de 0,887 ha.
    - Les sommets restants sont ceux d'un mur extrudé : chaque coin apparaît
      deux fois, en Z=0 et en Z=hauteur. On dédoublonne sur (x, y) en
      préservant l'ordre — un `set()` casserait la géométrie.

    Les polylignes de `Field_Segment_Setback` sont, elles, des polylignes 2D
    simples sans doublon : la même règle s'y applique sans effet.
    """
    points: list[tuple[float, float]] = []
    for sommet in polyligne.vertices:
        drapeaux = sommet.dxf.flags
        if drapeaux & 128 and not drapeaux & 64:
            continue
        points.append((float(sommet.dxf.location.x), float(sommet.dxf.location.y)))
    return list(dict.fromkeys(points))


#: Surface en deçà de laquelle un anneau reconstitué est écarté, en m². Le
#: noduage des murs laisse des échardes de quelques centimètres carrés aux
#: jonctions ; elles sont signalées, jamais supprimées en silence.
SURFACE_ECHARDE_M2 = 1.0


def _anneau(polyligne, couche: str) -> Polygon | None:
    """Polygone d'une polyligne fermée, quand elle porte l'anneau complet."""
    sommets = contour(polyligne)
    if len(sommets) < 3:
        return None
    polygone = Polygon(sommets)
    if not polygone.is_valid:
        polygone = polygone.buffer(0)
        if polygone.is_empty or polygone.geom_type != "Polygon":
            raise ErreurHelioScope(
                f"Une polyligne du calque « {couche} » forme un contour invalide "
                "que la correction topologique ne rattrape pas. Reprenez le tracé "
                "dans HelioScope."
            )
    return polygone


def _assembler(polylignes, couche: str) -> tuple[list[Polygon], list[str]]:
    """Reconstitue les anneaux d'un calque, selon la façon dont il est écrit.

    HelioScope emploie deux représentations, et la distinction se lit dans le
    DXF plutôt que dans le nom du calque (mesuré le 02/09/2026) :

    - `AcDbPolyFaceMesh` : un mur extrudé. Une zone peut tenir dans un seul
      maillage — la zone évitée des Islettes — ou être éclatée en panneaux d'une
      seule face — les 29 entités de Bray-Saint-Aignan, dont 23 n'ont que deux
      sommets distincts. Prendre chaque entité pour un polygone en perdrait 23
      sur 29 ; on rassemble donc les arêtes de tout le calque et on referme les
      anneaux avec `polygonize`, ce qui rend les 5 zones évitées réelles.
    - `AcDb3dPolyline` : une polyligne fermée qui porte déjà l'anneau entier.
      Les reculs arrivent ainsi, et ils se recouvrent largement : les passer
      dans `polygonize` les découperait en 121 morceaux au lieu de 30.
    """
    anneaux: list[Polygon] = []
    aretes: list[LineString] = []
    for entite in polylignes:
        if entite.get_mode() == "AcDbPolyFaceMesh":
            sommets = [
                (round(x, 3), round(y, 3)) for x, y in contour(entite)
            ]
            if len(sommets) < 2:
                continue
            if len(sommets) >= 3:
                sommets.append(sommets[0])
            aretes.append(LineString(sommets))
        else:
            polygone = _anneau(entite, couche)
            if polygone is not None:
                anneaux.append(polygone)

    avertissements: list[str] = []
    if aretes:
        reconstitues = list(polygonize(unary_union(aretes)))
        echardes = [p for p in reconstitues if p.area < SURFACE_ECHARDE_M2]
        anneaux.extend(p for p in reconstitues if p.area >= SURFACE_ECHARDE_M2)
        if not reconstitues:
            raise ErreurHelioScope(
                f"Le calque « {couche} » porte {len(aretes)} tronçons de mur qui "
                "ne referment aucun contour. La géométrie exportée est "
                "incohérente ; réexportez le Layout CAD depuis HelioScope."
            )
        if echardes:
            avertissements.append(
                f"{len(echardes)} écharde(s) de moins de {SURFACE_ECHARDE_M2:.0f} m² "
                f"écartée(s) à l'assemblage du calque « {couche} » "
                f"(la plus grande {max(p.area for p in echardes):.2f} m²) : "
                "sous-produits du recollement des murs, sans objet sur la planche."
            )
    return anneaux, avertissements


def extraire_geometries(
    msp: Modelspace,
) -> tuple[Polygon, list[Polygon], list[Polygon], list[str]]:
    """Lit la zone d'implantation, les reculs et les zones évitées."""
    avertissements: list[str] = []

    zones, avert = _assembler(
        msp.query(f'POLYLINE[layer=="{COUCHE_ZONE}"]'), COUCHE_ZONE
    )
    avertissements.extend(avert)
    if not zones:
        raise ErreurHelioScope(
            f"Aucune zone d'implantation sur le calque « {COUCHE_ZONE} ». "
            "Le calage et la surface du projet en dépendent."
        )
    if len(zones) > 1:
        union = unary_union(zones)
        if union.geom_type != "Polygon":
            raise ErreurHelioScope(
                f"Le calque « {COUCHE_ZONE} » porte {len(zones)} polygones "
                "disjoints. Le générateur ne traite qu'une zone d'implantation "
                "d'un seul tenant."
            )
        zone = union
    else:
        zone = zones[0]

    reculs, avert = _assembler(
        msp.query(f'POLYLINE[layer=="{COUCHE_RECULS}"]'), COUCHE_RECULS
    )
    avertissements.extend(avert)
    evitees, avert = _assembler(
        msp.query(f'POLYLINE[layer=="{COUCHE_ZONES_EVITEES}"]'), COUCHE_ZONES_EVITEES
    )
    avertissements.extend(avert)
    return zone, reculs, evitees, avertissements


# ---------------------------------------------------------------------------
# Calepinage
# ---------------------------------------------------------------------------


def _feuilles(entite, profondeur: int = 0):
    """Descend récursivement les INSERT jusqu'aux entités dessinées."""
    if entite.dxftype() == "INSERT":
        if profondeur >= 4:
            raise ErreurHelioScope(
                "Imbrication de blocs trop profonde dans le calque "
                f"« {COUCHE_MODULES} » : structure inattendue."
            )
        for sous in entite.virtual_entities():
            yield from _feuilles(sous, profondeur + 1)
    else:
        yield entite


def _mesurer_module(bloc, nom_bloc: str) -> tuple[float, float, float, float, str]:
    """Mesure le module dans son bloc : largeur, rampant, projection, inclinaison.

    Le contour est un rectangle **3D incliné**, et c'est le côté qui prend de la
    hauteur qui porte l'inclinaison — pas forcément le plus long. Mesuré le
    02/09/2026 sur les deux designs des Islettes :

        portrait (7676351)  (0,0,0) → (1,303, 0, 0) → (1,303, -2,1606, -1,0075)
        paysage  (8102502)  (0,0,0) → (2,384, 0, 0) → (2,384, -1,1809, -0,5507)

    Même panneau de 1,303 × 2,384 m à 25° dans les deux cas, mais en paysage le
    rampant est le petit côté. Prendre le côté le plus long pour le rampant, ce
    qui marche en portrait, donne 0° d'inclinaison en paysage. On identifie donc
    le rampant par son dénivelé.

    Dans les deux cas la bbox 2D du bloc donne la projection au sol, jamais les
    dimensions vraies du panneau.
    """
    contours = [e for e in bloc if e.dxftype() == "POLYLINE"]
    if len(contours) != 1:
        raise ErreurHelioScope(
            f"Le bloc module « {nom_bloc} » contient {len(contours)} contours ; "
            "un seul rectangle est attendu."
        )
    sommets = [
        (float(v.dxf.location.x), float(v.dxf.location.y), float(v.dxf.location.z))
        for v in contours[0].vertices
        if not (v.dxf.flags & 128 and not v.dxf.flags & 64)
    ]
    if len(sommets) != 4:
        raise ErreurHelioScope(
            f"Le contour du bloc module « {nom_bloc} » a {len(sommets)} sommets ; "
            "un rectangle de 4 sommets est attendu."
        )

    cotes = [
        (math.dist(a, b), math.dist(a[:2], b[:2]), abs(b[2] - a[2]))
        for a, b in zip(sommets, sommets[1:] + sommets[:1])
    ]
    montants = [c for c in cotes if c[2] > TOLERANCE_DENIVELE_M]
    plats = [c for c in cotes if c[2] <= TOLERANCE_DENIVELE_M]
    if len(montants) != 2 or len(plats) != 2:
        raise ErreurHelioScope(
            f"Le bloc module « {nom_bloc} » n'est pas un rectangle incliné selon "
            f"une seule direction : {len(montants)} côtés dénivelés sur 4. "
            "Le générateur refuse d'en déduire une inclinaison."
        )

    rampant, projetee, _ = montants[0]
    largeur = plats[0][0]
    if projetee <= 0 or projetee > rampant:
        raise ErreurHelioScope(
            f"Géométrie du bloc module « {nom_bloc} » incohérente : projection au "
            f"sol {projetee:.3f} m pour un rampant de {rampant:.3f} m."
        )
    inclinaison = math.degrees(math.acos(projetee / rampant))
    pose = "portrait" if rampant >= largeur else "paysage"
    return largeur, rampant, projetee, inclinaison, pose


def _pose_du_nom(nom_bloc: str, nom_bloc_minuscule: str | None = None) -> str | None:
    """Pose annoncée par le suffixe du nom de bloc, si elle y figure."""
    minuscule = (nom_bloc_minuscule or nom_bloc).lower()
    for suffixe, pose in POSES.items():
        if minuscule.endswith(suffixe):
            return pose
    return None


def _inclinaison_du_nom(nom_bloc: str) -> float:
    correspondance = MOTIF_INCLINAISON.search(nom_bloc)
    if correspondance is None:
        raise ErreurHelioScope(
            f"L'inclinaison ne se lit pas dans le nom du bloc module "
            f"« {nom_bloc} » : le motif attendu est « _<valeur>deg », par exemple "
            "module_characterization_103712_25.0deg_portrait. Le générateur "
            "refuse de retenir une inclinaison par défaut, qui produirait une "
            "coupe DP 3 et une notice DP 11 fausses sans que cela se voie."
        )
    return float(correspondance.group(1))


def extraire_calepinage(doc: Drawing, msp: Modelspace) -> tuple[Calepinage, list[str]]:
    """Extrait les paramètres du calepinage et les empreintes de table."""
    inserts = msp.query(f'INSERT[layer=="{COUCHE_MODULES}"]')
    if not inserts:
        raise ErreurModulesAbsents(MESSAGE_MODULES_ABSENTS)

    avertissements: list[str] = []

    noms_table = {e.dxf.name for e in inserts}
    if len(noms_table) > 1:
        raise ErreurHelioScope(
            f"Le calque « {COUCHE_MODULES} » référence {len(noms_table)} blocs "
            f"table différents ({', '.join(sorted(noms_table))}). Le générateur "
            "ne traite qu'un type de table."
        )
    nom_table = noms_table.pop()
    bloc_table = doc.blocks.get(nom_table)
    if bloc_table is None:
        raise ErreurHelioScope(f"Bloc table « {nom_table} » introuvable dans le DXF.")

    modules_du_bloc = [e for e in bloc_table if e.dxftype() == "INSERT"]
    if not modules_du_bloc:
        raise ErreurModulesAbsents(MESSAGE_MODULES_ABSENTS)
    noms_module = {e.dxf.name for e in modules_du_bloc}
    if len(noms_module) > 1:
        raise ErreurHelioScope(
            f"La table « {nom_table} » mélange {len(noms_module)} modules "
            f"différents ({', '.join(sorted(noms_module))})."
        )
    nom_module = noms_module.pop()
    bloc_module = doc.blocks.get(nom_module)
    if bloc_module is None:
        raise ErreurHelioScope(f"Bloc module « {nom_module} » introuvable dans le DXF.")

    largeur, longueur, projetee, inclinaison_mesuree, pose = _mesurer_module(
        bloc_module, nom_module
    )
    inclinaison = _inclinaison_du_nom(nom_module)
    if abs(inclinaison - inclinaison_mesuree) > 0.5:
        raise ErreurHelioScope(
            f"Incohérence sur l'inclinaison du bloc « {nom_module} » : le nom "
            f"annonce {inclinaison}°, la géométrie 3D en mesure "
            f"{inclinaison_mesuree:.2f}°. L'une des deux sources est fausse ; le "
            "générateur refuse d'arbitrer."
        )
    pose_annoncee = _pose_du_nom(nom_module)
    if pose_annoncee is not None and pose_annoncee != pose:
        raise ErreurHelioScope(
            f"Incohérence sur la pose du bloc « {nom_module} » : le nom annonce "
            f"« {pose_annoncee} », la géométrie montre un rampant de "
            f"{longueur:.3f} m pour une largeur de {largeur:.3f} m, soit "
            f"« {pose} ». Le générateur refuse d'arbitrer."
        )

    rotations = {round(e.dxf.rotation, 4) for e in inserts}
    if len(rotations) > 1:
        raise ErreurHelioScope(
            f"Les tables ont {len(rotations)} orientations différentes "
            f"({', '.join(str(r) for r in sorted(rotations))}). Le générateur ne "
            "traite qu'un calepinage d'orientation unique."
        )
    orientation = rotations.pop()

    positions = [(float(e.dxf.insert.x), float(e.dxf.insert.y)) for e in inserts]
    nb_rangees, pas_rangees, pas_tables = _rangees_et_pas(positions, orientation)

    nb_par_table = len(modules_du_bloc)
    calepinage = Calepinage(
        nb_tables=len(inserts),
        nb_modules_par_table=nb_par_table,
        nb_modules=len(inserts) * nb_par_table,
        module=Module(
            largeur_m=largeur,
            longueur_m=longueur,
            longueur_projetee_m=projetee,
            inclinaison_deg=inclinaison,
            inclinaison_mesuree_deg=inclinaison_mesuree,
            pose=pose,
            nom_bloc=nom_module,
        ),
        orientation_deg=orientation,
        nb_rangees=nb_rangees,
        pas_rangees_m=pas_rangees,
        pas_tables_m=pas_tables,
        nom_bloc_table=nom_table,
    )
    return calepinage, avertissements


def _rangees_et_pas(
    positions: list[tuple[float, float]], orientation_deg: float
) -> tuple[int, float, float]:
    """Compte les rangées et mesure les pas, dans le repère du calepinage.

    Compter les valeurs distinctes en Y des points d'insertion ne marche que si
    les rangées sont parallèles à l'axe X. Ce n'est pas le cas général : sur le
    design 7676351, l'orientation vaut -179,5559°, soit 0,444° hors axe, et le
    comptage brut donne 530 « rangées » pour 530 tables. On repasse donc dans le
    repère du calepinage par rotation inverse avant de regrouper — mesuré le
    02/09/2026, 8 rangées et un pas de 9,48 m sur ce design.
    """
    if len(positions) < 2:
        raise ErreurHelioScope(
            "Moins de deux tables dans le calepinage : les pas ne peuvent pas "
            "être mesurés."
        )

    angle = math.radians(-orientation_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    locaux = [(x * cos_a - y * sin_a, x * sin_a + y * cos_a) for x, y in positions]

    # Seuil de regroupement : la moitié de la plus petite longueur de table
    # plausible. 0,5 m sépare sans ambiguïté deux rangées (pas de plusieurs
    # mètres) sans éclater une rangée sur le bruit de position (quelques mm).
    seuil = 0.5
    rangees: list[list[tuple[float, float]]] = []
    for point in sorted(locaux, key=lambda p: p[1]):
        if rangees and point[1] - rangees[-1][-1][1] < seuil:
            rangees[-1].append(point)
        else:
            rangees.append([point])

    centres = [statistics.mean(p[1] for p in r) for r in rangees]
    ecarts_y = [b - a for a, b in zip(centres, centres[1:])]
    if not ecarts_y:
        raise ErreurHelioScope(
            "Le calepinage ne comporte qu'une seule rangée : le pas "
            "inter-rangées ne peut pas être mesuré."
        )

    ecarts_x: list[float] = []
    for rangee in rangees:
        xs = sorted(p[0] for p in rangee)
        ecarts_x.extend(b - a for a, b in zip(xs, xs[1:]))
    if not ecarts_x:
        raise ErreurHelioScope(
            "Aucune rangée ne comporte deux tables : le pas inter-table ne peut "
            "pas être mesuré."
        )

    return len(rangees), statistics.median(ecarts_y), statistics.median(ecarts_x)


#: Pas de grille appliqué aux sommets des modules avant fusion en table, en
#: mètres. Les modules d'une même table partagent une arête, mais les
#: transformations de blocs imbriqués laissent des écarts de l'ordre de 1e-12 m
#: qui empêchent `unary_union` de recoller : sans cette accroche, le design
#: 7676351 sortait 1 178 fragments pour 530 tables, de façon instable d'une
#: exécution à l'autre.
#:
#: Le micromètre suffit à recoller et ne déforme rien. Un pas au millimètre,
#: essayé d'abord, recollait aussi mais faisait osciller l'azimut des tables de
#: ±0,027° d'une table à l'autre — sur le design 7676351, deux valeurs d'angle
#: au lieu d'une. Invisible en position, mais c'est exactement le genre de bruit
#: qui se voit sur un plan de masse une fois les modules dessinés.
GRILLE_FUSION_M = 1e-6


def empreintes_tables(
    msp: Modelspace,
) -> tuple[list[BaseGeometry], list[Polygon], list[str]]:
    """Empreintes au sol des tables et des modules, blocs imbriqués résolus.

    Rend une entrée par table, dans l'ordre des INSERT, et à part l'empreinte de
    chaque module. Ce sont les modules qu'il faut pour dessiner un plan de masse
    lisible : le dossier de référence les trace un par un, la table n'étant que
    leur contour d'ensemble.
    """
    empreintes: list[BaseGeometry] = []
    modules: list[Polygon] = []
    morcelees = 0
    for insert in msp.query(f'INSERT[layer=="{COUCHE_MODULES}"]'):
        morceaux = []
        for entite in _feuilles(insert):
            if entite.dxftype() != "POLYLINE":
                continue
            anneau = contour(entite)
            if len(anneau) >= 3:
                accroche = [
                    (
                        round(x / GRILLE_FUSION_M) * GRILLE_FUSION_M,
                        round(y / GRILLE_FUSION_M) * GRILLE_FUSION_M,
                    )
                    for x, y in anneau
                ]
                morceaux.append(Polygon(accroche))
        if not morceaux:
            raise ErreurHelioScope(
                "Une table du calque « Modules » ne contient aucun contour "
                "exploitable après résolution des blocs."
            )
        modules.extend(morceaux)
        union = unary_union(morceaux)
        if union.geom_type == "MultiPolygon":
            # Table dont les modules ne se touchent pas : c'est possible, mais
            # assez rare pour être signalé plutôt que passé sous silence.
            morcelees += 1
        empreintes.append(union)

    avertissements: list[str] = []
    if morcelees:
        avertissements.append(
            f"{morcelees} table(s) sur {len(empreintes)} ont des modules "
            "disjoints : leur empreinte est rendue en plusieurs morceaux. "
            "Vérifiez le calepinage dans HelioScope si ce n'est pas voulu."
        )
    return empreintes, modules, avertissements


# ---------------------------------------------------------------------------
# Contrôles à l'import
# ---------------------------------------------------------------------------


def controler(doc: Drawing, msp: Modelspace) -> list[str]:
    """Contrôles non bloquants ; les cas bloquants lèvent ailleurs."""
    avertissements: list[str] = []

    unites = doc.header.get("$INSUNITS")
    if unites != 6:
        avertissements.append(
            f"$INSUNITS vaut {unites} au lieu de 6 (mètres). Le générateur "
            "interprète malgré tout les coordonnées comme des mètres, "
            "conformément au modèle HelioScope : vérifiez les dimensions "
            "obtenues avant de valider le calage."
        )

    return avertissements


def importer(chemin_export: str | Path) -> Implantation:
    """Lit un export HelioScope de bout en bout, sans le caler."""
    export = ouvrir_export(chemin_export)
    doc = lire_dxf(export.dxf)
    msp = doc.modelspace()

    avertissements = controler(doc, msp)

    image = _entite_image(msp)
    calage = calculer_calage(_controler_image(image))
    calage.ordonnee_centre_image_m = ordonnee_centre_image(image)

    zone, reculs, evitees, avert_geom = extraire_geometries(msp)
    avertissements.extend(avert_geom)
    calepinage, avert_calepinage = extraire_calepinage(doc, msp)
    avertissements.extend(avert_calepinage)
    tables, modules, avert_tables = empreintes_tables(msp)
    avertissements.extend(avert_tables)
    avertissements.append(
        f"{len(evitees)} zone(s) évitée(s) reconstituée(s) sur le calque "
        f"« {COUCHE_ZONES_EVITEES} » ; l'absence de zone évitée est normale sur "
        "un terrain sans bâtiment ni bassin."
    )
    if len(tables) != calepinage.nb_tables:
        raise ErreurHelioScope(
            f"{len(tables)} empreintes de table pour {calepinage.nb_tables} "
            "INSERT : la résolution des blocs a perdu ou dupliqué des tables."
        )

    return Implantation(
        identifiant_design=export.identifiant_design,
        calage=calage,
        calepinage=calepinage,
        zone_implantation=zone,
        reculs=reculs,
        zones_evitees=evitees,
        tables=tables,
        modules=modules,
        avertissements=avertissements,
    )


# ---------------------------------------------------------------------------
# Projection et pré-positionnement
# ---------------------------------------------------------------------------

_VERS_L93 = Transformer.from_crs(3857, 2154, always_xy=True)
_VERS_MERCATOR = Transformer.from_crs(2154, 3857, always_xy=True)
_VERS_WGS84 = Transformer.from_crs(2154, 4326, always_xy=True)


@lru_cache(maxsize=8)
def _transformateur_local(latitude: float, longitude: float) -> Transformer:
    """Transformateur du repère DXF vers le Lambert 93.

    Le repère DXF est déjà un repère métrique local, en mètres sol vrais,
    orienté nord en haut et centré sur son origine : c'est très exactement ce
    qu'est une projection transverse Mercator de facteur d'échelle 1 centrée sur
    cette origine. Le passage du DXF vers ce système est donc l'identité, et il
    ne reste qu'à reprojeter en Lambert 93.

    Pourquoi ne pas passer par le Web Mercator comme le fait la recette d'origine
    (`Mercator = origine + DXF * k`, avec k = 1/cos φ) : ce facteur est celui de
    la *sphère* Web Mercator, alors qu'un mètre sol vaut a/(N cos φ) en abscisse
    de Mercator et a/M en ordonnée, sur l'ellipsoïde. Comme N ≠ M, aucun facteur
    isotrope ne convient. Mesuré le 02/09/2026 sur le design 7676351, distances
    géodésiques vraies contre distances DXF :

        recette Web Mercator   est-ouest +1918 ppm   nord-sud  -976 ppm
        transverse Mercator    est-ouest     0 ppm   nord-sud     0 ppm

    Soit, à l'échelle du site de Bray-Saint-Aignan (700 m), 1,34 m d'étirement
    est-ouest — une erreur d'échelle systématique, invisible sur la planche, que
    la règle « l'échelle doit être vraie à l'impression » interdit. Les étapes 1
    à 4 de la recette, qui déduisent le zoom et la latitude, sont conservées mot
    pour mot : c'est uniquement le placement, l'étape 5, qui est corrigé ici.
    """
    local = CRS.from_proj4(
        f"+proj=tmerc +lat_0={latitude!r} +lon_0={longitude!r} +k=1 "
        "+x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
    )
    return Transformer.from_crs(local, CRS.from_epsg(2154), always_xy=True)


def projeter(geometrie: BaseGeometry, calage: Calage) -> BaseGeometry:
    """Passe une géométrie du repère DXF local au Lambert 93."""
    longitude = calage.exige_origine()
    transformateur = _transformateur_local(calage.latitude_origine, longitude)

    decalage = calage.correction_nord_sud_m - calage.ordonnee_centre_image_m

    def _vers_l93(x, y, z=None):
        # Le repère métrique local est centré sur la latitude du fichier, qui
        # est celle du centre de l'image de fond : on y ramène ce centre, puis
        # on ajoute la correction nord-sud. Le repère est orienté nord à
        # l'origine, une translation en y est donc exactement un déplacement
        # vers le nord.
        return transformateur.transform(x, y + decalage)

    return transformer_geom(_vers_l93, geometrie)


@dataclass
class Prepositionnement:
    """Diagnostic du pré-positionnement automatique, à montrer à l'utilisateur."""

    longitude: float
    recouvrement: float
    ecart_nord_sud_m: float
    surface_zone_ha: float
    surface_emprise_ha: float
    iterations: int

    @property
    def message(self) -> str:
        return (
            f"Pré-positionnement : recouvrement {self.recouvrement:.0%} avec "
            f"l'emprise, écart nord-sud résiduel {self.ecart_nord_sud_m:+.1f} m "
            f"(correction à saisir pour l'annuler : "
            f"{-self.ecart_nord_sud_m:+.1f} m). "
            f"Zone HelioScope {self.surface_zone_ha:.2f} ha contre "
            f"{self.surface_emprise_ha:.2f} ha pour l'emprise fournie. "
            "Résultat indicatif : la zone est tracée à la main dans HelioScope "
            "et ne suit pas le parcellaire. À valider à l'œil sur l'ortho IGN."
        )


#: Convergence du calage est-ouest, en mètres sur le terrain.
TOLERANCE_CALAGE_M = 1e-3
ITERATIONS_CALAGE_MAX = 12


def prepositionner(
    implantation: Implantation, emprise_l93: BaseGeometry
) -> Prepositionnement:
    """Cale la zone d'implantation sur l'emprise, en est-ouest seulement.

    La latitude est entièrement déterminée par la résolution du fond de plan :
    le seul degré de liberté est la longitude de l'origine. On aligne donc les
    centroïdes en X, et on rend compte de l'écart nord-sud résiduel au lieu de
    le corriger — c'est lui qui révèle un calage douteux.

    La longitude étant le paramètre de la projection locale, l'alignement se
    fait par points fixes : deux ou trois passes suffisent, et l'absence de
    convergence lève plutôt que de rendre un calage approximatif en silence.
    """
    zone = implantation.zone_implantation
    calage = implantation.calage
    centre_emprise = emprise_l93.centroid

    metres_par_degre = metres_par_degre_longitude(calage.latitude_origine)
    lon_emprise, _ = _VERS_WGS84.transform(centre_emprise.x, centre_emprise.y)
    calage.longitude_origine = lon_emprise - zone.centroid.x / metres_par_degre

    for iteration in range(1, ITERATIONS_CALAGE_MAX + 1):
        ecart_x = centre_emprise.x - projeter(zone, calage).centroid.x
        calage.longitude_origine += ecart_x / metres_par_degre
        if abs(ecart_x) < TOLERANCE_CALAGE_M:
            break
    else:
        raise ErreurCalage(
            f"Le calage est-ouest n'a pas convergé en {ITERATIONS_CALAGE_MAX} "
            f"passes (écart résiduel {ecart_x:.3f} m). Vérifiez que l'emprise "
            "fournie est bien celle du projet."
        )

    zone_l93 = projeter(zone, calage)
    union = zone_l93.union(emprise_l93).area
    recouvrement = zone_l93.intersection(emprise_l93).area / union if union else 0.0

    return Prepositionnement(
        longitude=calage.longitude_origine,
        recouvrement=recouvrement,
        ecart_nord_sud_m=zone_l93.centroid.y - centre_emprise.y,
        surface_zone_ha=zone_l93.area / 1e4,
        surface_emprise_ha=emprise_l93.area / 1e4,
        iterations=iteration,
    )


# ---------------------------------------------------------------------------
# Sorties
# ---------------------------------------------------------------------------

def geometries_l93(implantation: Implantation) -> dict[str, list[BaseGeometry]]:
    """Toutes les couches, projetées en Lambert 93."""
    calage = implantation.calage
    return {
        "tables": [projeter(g, calage) for g in implantation.tables],
        "modules": [projeter(g, calage) for g in implantation.modules],
        "zone_implantation": [projeter(implantation.zone_implantation, calage)],
        "reculs": [projeter(g, calage) for g in implantation.reculs],
        "zones_evitees": [projeter(g, calage) for g in implantation.zones_evitees],
    }


# ---------------------------------------------------------------------------
# Contrat de sortie commun avec le lot 2bis
# ---------------------------------------------------------------------------

#: Correspondance couche HelioScope → catégorie du contrat, décidée le
#: 03/09/2026, mesures à l'appui :
#:
#: - `tables_pv` reçoit les **rangées**, pas les tables brutes du DXF. Une
#:   « table » HelioScope est une colonne de 3 modules, 1,30 × 6,48 m, dont le
#:   grand côté est *en travers* de la rangée : `azimut_tables()` y répond
#:   -88,105° au lieu de +1,895°, et la ligne de coupe sortirait parallèle aux
#:   rangées au lieu de perpendiculaire, sans rien de visible sur la planche.
#:   Mettre les rangées dans `tables_pv` fait que le calcul juste est celui
#:   qu'on obtient sans rien savoir de la provenance du fichier.
#: - `modules_pv` reçoit le détail que le plan du BE ne donne pas. Conservé
#:   plutôt qu'écarté : c'est cette trame qui rend un plan de masse lisible.
#: - `zone_implantation_pv`, `recul_implantation`, `zone_evitee` n'ont pas
#:   d'équivalent BE non plus. Aucune n'est appariée à `cloture` : la zone
#:   HelioScope est tracée à main levée, ne suit pas le parcellaire, et en tirer
#:   une surface clôturée ou un linéaire de clôture donnerait des chiffres faux
#:   dans le dossier.
CORRESPONDANCE_CONTRAT = {
    "tables_pv": COUCHE_MODULES,
    "modules_pv": COUCHE_MODULES,
    "zone_implantation_pv": COUCHE_ZONE,
    "recul_implantation": COUCHE_RECULS,
    "zone_evitee": COUCHE_ZONES_EVITEES,
}


def grouper_en_rangees(tables: list[BaseGeometry]) -> list[Polygon]:
    """Fusionne des tables contiguës en rangées, sans les reprojeter.

    Séparé de `rangees()` pour l'aperçu de calage, qui a déjà ses tables
    projetées sous la main : repasser par `geometries_l93` y ajouterait 0,9 s à
    chaque cran de curseur, sur 1,4 s de redessin.
    """
    return list(polygones_ou_vide(unary_union(tables)))


#: Seuil de regroupement des tables en rangées, en mètres, sur leur ordonnée
#: dans le repère du calepinage. Le même que celui de `_rangees_et_pas`, qui
#: mesure le pas sur les points d'insertion : deux rangées sont à plusieurs
#: mètres l'une de l'autre, deux tables d'une même rangée au millimètre.
SEUIL_RANGEE_M = 0.5

#: Marge ajoutée au demi-jeu entre tables pour refermer une rangée, en mètres.
#: Elle referme aussi les joints entre modules d'une même table, qui se
#: comptent en millimètres : 1,2 cm sur le design 10465241 de Gannay.
MARGE_FERMETURE_RANGEE_M = 0.01


def _dans_le_repere_du_calepinage(implantation: Implantation):
    """Bornes de chaque table dans le repère du calepinage, rotation annulée."""
    angle = math.radians(-implantation.calepinage.orientation_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    bornes = []
    for table in implantation.tables:
        xs, ys = [], []
        for polygone in polygones_ou_vide(table):
            for x, y in polygone.exterior.coords:
                xs.append(x * cos_a - y * sin_a)
                ys.append(x * sin_a + y * cos_a)
        bornes.append((min(xs), min(ys), max(xs), max(ys)))
    return bornes


def rangees_locales(implantation: Implantation) -> tuple[list[Polygon], float]:
    """Rangées de tables dans le repère du DXF, et le jeu mesuré entre tables.

    Les tables se regroupent **par leur ordonnée dans le repère du
    calepinage**, comme `_rangees_et_pas` le fait pour mesurer le pas, et non
    par contact. L'union des tables contiguës suffisait sur les deux designs
    des Islettes, où tous les écarts entre tables valent exactement une largeur
    de module (mesuré le 02/09/2026). Elle ne suffit pas au design 10465241 de
    Gannay-sur-Loire (mesuré le 23/09/2026) : ses tables sont espacées de
    0,49 m et ses modules séparés par des joints de 1,2 cm. Rien ne s'y touche,
    et l'union rendait 4 752 « rangées » — les modules — dont `azimut_tables`
    lisait le grand côté, nord-sud : 90° au lieu de 0°, et une coupe A-A'
    parallèle aux rangées sans rien de visible sur la planche.

    Chaque rangée est ensuite refermée sur le **jeu mesuré** entre ses tables
    (fermeture morphologique de rayon demi-jeu, à angles vifs) : un vide plus
    large — une rangée interrompue par une zone évitée — reste un vide, et la
    rangée sort en deux morceaux.
    """
    bornes = _dans_le_repere_du_calepinage(implantation)
    ordre = sorted(range(len(bornes)), key=lambda i: (bornes[i][1] + bornes[i][3]) / 2)
    groupes: list[list[int]] = []
    derniere = None
    for indice in ordre:
        milieu = (bornes[indice][1] + bornes[indice][3]) / 2
        if groupes and milieu - derniere < SEUIL_RANGEE_M:
            groupes[-1].append(indice)
        else:
            groupes.append([indice])
        derniere = milieu

    jeux = []
    for groupe in groupes:
        suite = sorted(groupe, key=lambda i: bornes[i][0])
        jeux.extend(
            bornes[b][0] - bornes[a][2]
            for a, b in zip(suite, suite[1:])
            if bornes[b][0] - bornes[a][2] > 0
        )
    jeu = statistics.median(jeux) if jeux else 0.0
    rayon = jeu / 2.0 + MARGE_FERMETURE_RANGEE_M

    lignes: list[Polygon] = []
    for groupe in groupes:
        union = unary_union([implantation.tables[i] for i in groupe])
        refermee = union.buffer(rayon, join_style="mitre").buffer(
            -rayon, join_style="mitre"
        )
        lignes.extend(polygones_ou_vide(refermee))
    return lignes, jeu


def rangees(implantation: Implantation) -> list[Polygon]:
    """Rangées de tables, en Lambert 93 : une par ligne du calepinage.

    HelioScope n'encode aucun groupement en structures : la rangée est le seul
    regroupement que le fichier permette de reconstituer, et c'est aussi celui
    que l'aperçu de calage cerne de noir. Voir `rangees_locales` pour la façon
    de la reconstituer quand les tables ne se touchent pas.
    """
    calage = implantation.calage
    return [projeter(ligne, calage) for ligne in rangees_locales(implantation)[0]]


def azimut_rangees(implantation: Implantation) -> float:
    """Azimut des rangées en Lambert 93, dans ]-90, 90], pour orienter la coupe.

    **Ne pas utiliser `calepinage.orientation_deg` à sa place.** Les deux
    diffèrent, et l'écart n'est pas du bruit : mesuré le 03/09/2026 sur le
    design 7676351, les rangées sont à +1,895° quand `orientation_deg` ramené
    dans ]-90, 90] vaut +0,444°, soit 1,4507° d'écart. C'est **exactement** la
    convergence des méridiens du Lambert 93 au droit du site, que pyproj donne à
    +1,4507° : résidu nul.

    Autrement dit, `orientation_deg` est la rotation des INSERT dans le repère
    du DXF, rapportée au **nord géographique**, tandis que la ligne de coupe se
    trace en Lambert 93, rapporté au **nord de la grille**. La convergence est
    nulle sur le méridien 3° E et atteint 3° aux bords de la France
    métropolitaine : y brancher `orientation_deg` inclinerait la coupe d'autant,
    sans que rien ne le signale.

    On mesure donc sur la géométrie projetée, comme le fait le lot 2bis.
    """
    lignes = rangees(implantation)
    if not lignes:
        raise ErreurHelioScope(
            "Aucune rangée reconstituée : l'azimut ne peut pas être calculé, et "
            "la ligne de coupe A-A' ne peut pas être orientée."
        )
    from .import_be import azimut_tables

    return azimut_tables(lignes)


def entites_contrat(implantation: Implantation) -> list:
    """Géométries de l'implantation, dans le vocabulaire du contrat commun.

    `z_reel` est faux partout et les bornes Z restent nulles : le DXF HelioScope
    est plat, vérifié sur les deux exports des Islettes. Les colonnes sont
    conservées quand même — un schéma qui changerait selon la provenance
    obligerait le lot 4 à savoir d'où vient le fichier avant de le lire.
    """
    from .import_be import EntiteBE

    couches = geometries_l93(implantation)
    contenu = {
        "tables_pv": rangees(implantation),
        "modules_pv": couches["modules"],
        "zone_implantation_pv": couches["zone_implantation"],
        "recul_implantation": couches["reculs"],
        "zone_evitee": couches["zones_evitees"],
    }
    return [
        EntiteBE(
            categorie=categorie,
            calque=CORRESPONDANCE_CONTRAT[categorie],
            geometrie=geometrie,
            z_reel=False,
        )
        for categorie, geometries in contenu.items()
        for geometrie in geometries
    ]


def limites_helioscope(
    implantation: Implantation,
    emprise_cadastrale: BaseGeometry | None = None,
) -> list:
    """Ce que l'import HelioScope ne permet pas de contrôler, dit comme tel.

    Le lot 2bis tire sa valeur d'avoir deux sources qui peuvent se contredire :
    le plan du BE et son tableau bilan. L'import HelioScope n'en a qu'une. La
    plupart des recoupements n'y ont donc pas d'objet — et les rendre
    « conformes » ferait croire à une vérification qui n'a pas eu lieu. Un
    statut à part le dit.

    Seul le débordement hors de l'emprise cadastrale reste calculable, parce
    qu'il confronte le calepinage à une source extérieure : le parcellaire.
    """
    from .import_be import (
        AVERTISSEMENT,
        DEBORDEMENT_NEGLIGEABLE_M2,
        IMPOSSIBLE,
        OK,
        Controle,
    )

    controles = [
        Controle(
            "Recoupement avec le tableau bilan",
            None,
            None,
            "",
            IMPOSSIBLE,
            "L'export HelioScope est la seule source : il n'y a pas de tableau "
            "bilan à confronter au plan. Nombre de modules, puissance, "
            "inclinaison et azimut ne sont donc pas recoupés — ils sont lus une "
            "fois, et rien ne les contredit.",
        ),
        Controle(
            "Cohérence altimétrique des tables",
            None,
            None,
            "",
            IMPOSSIBLE,
            "Le DXF HelioScope est plat : les tables ne portent aucune altitude. "
            "Le profil du terrain reste disponible par le RGE ALTI, mais sans "
            "recoupement possible avec l'implantation.",
        ),
        Controle(
            "Surface clôturée et linéaire de clôture",
            None,
            None,
            "",
            IMPOSSIBLE,
            "HelioScope ne donne aucune clôture. La zone d'implantation est un "
            "tracé d'étude à main levée qui ne suit pas le parcellaire : en "
            "tirer une surface clôturée serait faux. À relever sur le plan du BE.",
        ),
    ]

    if emprise_cadastrale is None or emprise_cadastrale.is_empty:
        controles.append(
            Controle(
                "Implantation dans l'emprise cadastrale",
                None,
                None,
                "",
                AVERTISSEMENT,
                "Emprise cadastrale non fournie : un débordement des tables hors "
                "des parcelles du projet n'aurait pas été vu.",
            )
        )
        return controles

    lignes = rangees(implantation)
    debordement = (
        float(unary_union(lignes).difference(emprise_cadastrale).area)
        if lignes
        else 0.0
    )
    if debordement <= DEBORDEMENT_NEGLIGEABLE_M2:
        controles.append(
            Controle(
                "Implantation dans l'emprise cadastrale",
                0.0,
                None,
                "m²",
                OK,
                "Les rangées sont contenues dans l'emprise cadastrale fournie.",
            )
        )
    else:
        controles.append(
            Controle(
                "Implantation dans l'emprise cadastrale",
                debordement,
                None,
                "m²",
                AVERTISSEMENT,
                f"Les rangées débordent de {debordement:.0f} m² hors de "
                "l'emprise cadastrale fournie. Vérifiez la maîtrise foncière, "
                "ou le calage est-ouest, avant le dépôt.",
            )
        )
    return controles


def parametres_contrat(
    implantation: Implantation,
    controles: list,
    projet=None,
    ligne_coupe=None,
    profil=None,
) -> dict:
    """`projet.json` de sortie, au même format que celui du lot 2bis.

    À ne pas confondre avec le `projet.json` du lot 1, qui vit dans
    `projets/{nom}/` et décrit les métadonnées du dossier : celui-ci est la
    sortie de l'import, dans `sortie/{nom}/`, et alimente le lot 4. Le champ
    `origine` les distingue à la lecture.
    """
    from .import_be import ORIGINE_HELIOSCOPE, VERSION_CONTRAT

    calage = implantation.calage
    calepinage = implantation.calepinage
    module = calepinage.module
    lignes = rangees(implantation)

    donnees = {
        "version_contrat": VERSION_CONTRAT,
        "origine": ORIGINE_HELIOSCOPE,
        "sources": {
            "export_helioscope": (
                str(projet.helioscope) if projet is not None else None
            ),
            "design": implantation.identifiant_design,
            "tableau_bilan": None,
        },
        "projet": {
            "nom": projet.nom if projet is not None else None,
            "phase": "DP",
            "date_tableau": None,
        },
        "plan": {
            "unite_dxf": "mètre",
            "azimut_tables_deg": azimut_rangees(implantation),
            "nb_tables": len(lignes),
            "nb_portails": 0,
            "surface_cloturee_m2": None,
            "lineaire_cloture_m": None,
            "surface_tables_m2": float(sum(g.area for g in lignes)),
            "correspondance_calques": dict(CORRESPONDANCE_CONTRAT),
            "calques_ignores": [],
            "avertissements": list(implantation.avertissements),
        },
        # Le lot 2bis met ici les valeurs du tableau bilan ; le lot 2 met celles
        # qu'il lit dans le DXF, seule source dont il dispose.
        "parametres": {
            "generalites": {
                "azimut_rangees_l93_deg": azimut_rangees(implantation),
                "orientation_insert_dxf_deg": calepinage.orientation_deg,
                "nb_rangees": calepinage.nb_rangees,
                "pas_rangees_m": calepinage.pas_rangees_m,
                "pas_tables_m": calepinage.pas_tables_m,
            },
            "structures": {
                "nb_tables_dxf": calepinage.nb_tables,
                "nb_modules_par_table": calepinage.nb_modules_par_table,
                "nom_bloc_table": calepinage.nom_bloc_table,
            },
            "modules": {
                "nb_modules": calepinage.nb_modules,
                "largeur_m": module.largeur_m,
                "longueur_m": module.longueur_m,
                "longueur_projetee_m": module.longueur_projetee_m,
                "inclinaison_deg": module.inclinaison_deg,
                "inclinaison_mesuree_deg": module.inclinaison_mesuree_deg,
                "pose": module.pose,
                "nom_bloc": module.nom_bloc,
            },
            "postes": {},
        },
        "cotes_normalisees": [],
        "standards_unite": {},
        "calage": {
            "resolution_m_px": calage.resolution_m_px,
            "zoom": calage.zoom,
            "latitude_origine": calage.latitude_origine,
            "longitude_origine": calage.longitude_origine,
            "correction_nord_sud_m": calage.correction_nord_sud_m,
            "ordonnee_centre_image_m": calage.ordonnee_centre_image_m,
            "facteur_echelle": calage.facteur_echelle,
        },
        "controles": [
            {
                "libelle": c.libelle,
                "statut": c.statut,
                "valeur_dxf": c.valeur_dxf,
                "valeur_tableau": c.valeur_tableau,
                "unite": c.unite,
                "tolerance": c.tolerance,
                "message": c.message,
            }
            for c in controles
        ],
        "seuil_puissance_dp_mwc": None,
        "avertissements_tableau": [],
    }

    if ligne_coupe is not None:
        donnees["ligne_coupe"] = {
            "corrigee": ligne_coupe.corrigee,
            # Le geste, et non seulement son résultat : une position choisie à la
            # main se rejoue par une translation, pas par une correction, qui la
            # recalculerait. Voir `coupe.reprendre_coupe`.
            "position_choisie": ligne_coupe.position_choisie,
            "azimut_tables_deg": ligne_coupe.azimut_tables_deg,
            "azimut_coupe_deg": ligne_coupe.azimut_coupe_deg,
            "ecart_initial_deg": ligne_coupe.ecart_initial_deg,
            "longueur_m": ligne_coupe.longueur_m,
            "coordonnees_l93": [list(c[:2]) for c in ligne_coupe.geometrie.coords],
            "trace_initial_l93": [
                list(c[:2]) for c in ligne_coupe.trace_initial.coords
            ],
            "avertissements": ligne_coupe.avertissements,
        }

    if profil is not None:
        donnees["profil_terrain"] = {
            "origine": profil.origine,
            "pas_m": profil.pas_m,
            "denivelee_m": profil.denivelee_m,
            "altitude_min_m": profil.altitude_min_m,
            "altitude_max_m": profil.altitude_max_m,
            "points": [
                [round(s, 3), round(z, 3)]
                for s, z in zip(profil.abscisses_m, profil.altitudes_m)
            ],
            "avertissements": profil.avertissements,
        }

    # Aucune cohérence altimétrique : le DXF est plat, c'est dit dans les
    # contrôles, et la clé reste absente plutôt que remplie de valeurs nulles.
    return donnees


def ligne_coupe_helioscope(
    implantation: Implantation,
    trace,
    emprise_cadastrale: BaseGeometry,
    manuel: bool = False,
):
    """Ligne A-A' d'un projet HelioScope, orientée et étendue comme il faut.

    Simple façade sur `coupe.corriger_ligne_coupe`, mais elle fige les deux
    choix par lesquels on se trompe :

    - l'azimut vient de `azimut_rangees()`, mesuré en Lambert 93 sur les
      rangées. Ni les tables brutes, dont le grand côté est en travers de la
      rangée, ni `orientation_deg`, qui se rapporte au nord géographique et non
      au nord de la grille ;
    - l'étendue vient de l'**emprise cadastrale** du lot 1. Le lot 2bis étend sa
      coupe à l'emprise clôturée ; HelioScope n'a pas de clôture, et sa zone
      d'implantation est un tracé d'étude à main levée qui ne suit pas le
      parcellaire. Le cadastre est la seule limite dont on réponde.

    Écart assumé avec le lot 2bis : la coupe n'y est pas replacée sur le nombre
    de rangées traversées. `implantation.tables` est en repère DXF local, quand
    le tracé et l'emprise sont en Lambert 93 ; les confronter demanderait de
    reprojeter les tables, ce qui est un travail de calage et non de coupe. Le
    point milieu du tracé est donc conservé ici.
    """
    from .coupe import corriger_ligne_coupe

    if emprise_cadastrale is None or emprise_cadastrale.is_empty:
        raise ErreurHelioScope(
            "Emprise cadastrale absente : la ligne de coupe d'un projet "
            "HelioScope s'étend sur elle, faute de clôture dans l'export. "
            "Fournissez le shapefile d'emprise du lot 1."
        )
    return corriger_ligne_coupe(
        trace,
        azimut_rangees(implantation),
        emprise_cadastrale,
        manuel=manuel,
    )


def ecrire_sortie(
    implantation: Implantation,
    dossier: str | Path,
    emprise_cadastrale: BaseGeometry | None = None,
    projet=None,
    ligne_coupe=None,
    profil=None,
) -> tuple[Path, Path, list]:
    """Écrit le GeoPackage et le `projet.json` du contrat, comme le lot 2bis.

    Rend les deux chemins et la liste des contrôles, dont ceux que l'absence de
    tableau bilan rend impossibles : l'appelant doit les montrer.
    """
    from .import_be import ecrire_geopackage, ecrire_parametres

    controles = limites_helioscope(implantation, emprise_cadastrale)
    chemin_gpkg = ecrire_geopackage(
        entites_contrat(implantation), dossier, ligne_coupe=ligne_coupe
    )
    chemin_json = ecrire_parametres(
        parametres_contrat(
            implantation,
            controles,
            projet=projet,
            ligne_coupe=ligne_coupe,
            profil=profil,
        ),
        dossier,
    )
    return chemin_gpkg, chemin_json, controles

# ---------------------------------------------------------------------------
# Aperçu de contrôle
# ---------------------------------------------------------------------------

def metres_par_degre_longitude(latitude: float) -> float:
    """Longueur d'un degré de longitude au sol, en mètres, sur l'ellipsoïde.

    Le facteur naïf `a·cos φ` est celui de la sphère : il donne 1 914 ppm de
    trop à cette latitude, soit 7 cm sur un décalage de 37 m demandé — assez
    pour que le curseur de réglage ne rende pas la valeur qu'il affiche. Le
    rayon de courbure en première verticale N remet les deux d'accord.
    """
    phi = math.radians(latitude)
    grande_normale = RAYON_MERCATOR / math.sqrt(
        1 - EXCENTRICITE2_WGS84 * math.sin(phi) ** 2
    )
    return math.pi / 180.0 * grande_normale * math.cos(phi)


#: Correction nord-sud admise, en mètres. Les deux designs des Islettes
#: donnaient deux latitudes distantes de 11 m ; c'était l'écart de leurs centres
#: d'image, dont le calage tient compte depuis le 23/09/2026
#: (`Calage.ordonnee_centre_image_m`). La latitude est depuis bonne au mètre
#: près sur quatre des cinq exports mesurés, à 4 m sur le cinquième : la borne
#: garde une marge large. Au-delà, ce n'est plus un ajustement mais le signe
#: que le modèle de calage ne tient pas sur ce fichier, et le corriger à la
#: main masquerait le problème au lieu de le montrer.
CORRECTION_NORD_SUD_MAX_M = 30.0


def corriger_nord_sud(calage: "Calage", metres: float) -> None:
    """Fixe la correction nord-sud, comptée positivement vers le nord.

    Second et dernier degré de liberté, ouvert parce que la latitude déduite du
    fichier n'est bonne qu'à quelques mètres. Il reste séparé du réglage
    est-ouest, et non fondu dans un glissement libre en deux dimensions : deux
    curseurs indépendants se règlent chacun sur un critère visuel simple, là où
    un déplacement libre laisse compenser une erreur d'un axe par l'autre.
    """
    if not -CORRECTION_NORD_SUD_MAX_M <= metres <= CORRECTION_NORD_SUD_MAX_M:
        raise ErreurCalage(
            f"Correction nord-sud de {metres:+.1f} m demandée, hors de la plage "
            f"admise (±{CORRECTION_NORD_SUD_MAX_M:.0f} m). La latitude déduite du "
            "fichier est bonne à quelques mètres près ; un écart de cet ordre "
            "signale que le calage lui-même est faux — mauvais export, mauvaise "
            "emprise — et non qu'il faut le rattraper à la main."
        )
    calage.correction_nord_sud_m = float(metres)


def decaler_longitude(calage: "Calage", metres: float) -> None:
    """Déplace l'origine de `metres` vers l'est, en gardant la latitude.

    Le seul réglage offert à l'utilisateur. Un déplacement libre en deux
    dimensions serait plus facile à rater : la latitude étant verrouillée par le
    fichier, la laisser bouger reviendrait à masquer un calage faux.
    """
    calage.longitude_origine = calage.exige_origine() + metres / metres_par_degre_longitude(
        calage.latitude_origine
    )


def polygones_ou_vide(geometrie: BaseGeometry):
    """Itère les polygones d'une géométrie simple ou multiple."""
    if geometrie.is_empty:
        return
    if geometrie.geom_type == "Polygon":
        yield geometrie
    elif geometrie.geom_type == "MultiPolygon":
        yield from geometrie.geoms
    else:
        raise ErreurHelioScope(
            f"Type de géométrie inattendu à l'aperçu : {geometrie.geom_type}"
        )


#: Palette reprise du dossier de référence HOCH « Les Islettes » du 25/04/2024,
#: relevée sur la planche DP 2 : modules en bleu-vert pâle cernés de bleu franc,
#: table cernée de noir. L'aperçu n'est pas une planche, mais s'en rapprocher
#: permet de juger le calage sur ce qu'on verra au lot 4.
COULEUR_MODULE = (151, 202, 202)
COULEUR_FILET_MODULE = (0, 0, 255)
COULEUR_FILET_TABLE = (0, 0, 0)
COULEUR_EMPRISE = (255, 214, 0)
COULEUR_ZONE = (255, 45, 45)

#: Facteur de suréchantillonnage du rendu.
#:
#: `ImageDraw` ne fait pas d'anticrénelage : une rangée à 0,44° de l'horizontale
#: se rastérise en marches d'escalier, ce qui donne à lire un calepinage aligné
#: nord-sud et décalé rangée par rangée, alors que l'azimut est correctement
#: appliqué à la géométrie. On dessine donc trois fois plus grand puis on réduit.
SURECHANTILLONNAGE = 3


#: Jeu laissé autour du cadre de l'aperçu, en mètres, pour que l'implantation
#: reste visible pendant qu'on la déplace aux curseurs.
JEU_CADRE_M = 40.0


def cadre_apercu(
    implantation: Implantation,
    emprise_l93: BaseGeometry,
    marge: float = 0.12,
) -> tuple[float, float, float, float]:
    """Emprise géographique de l'aperçu, **fixe pendant tout le réglage**.

    Le cadre est calculé une fois, sur la position issue du pré-positionnement,
    puis ne bouge plus : c'est ce qui permet de ne télécharger l'ortho qu'une
    fois et de ne redessiner que la surcouche à chaque mouvement de curseur.
    Un cadre recalculé à chaque fois obligerait à redemander l'image au WMS, et
    l'aperçu disparaîtrait puis reviendrait à chaque cran — impossible de juger
    un déplacement dans ces conditions.

    Corollaire assumé : poussé loin, le calepinage sort du cadre. C'est un signal
    utile, pas une gêne — le pré-positionnement est bon à quelques mètres, un
    déplacement de cette ampleur veut dire qu'on corrige autre chose qu'un calage.
    """
    zone = projeter(implantation.zone_implantation, implantation.calage)
    minx, miny, maxx, maxy = unary_union([zone, emprise_l93]).bounds
    tampon = marge * max(maxx - minx, maxy - miny) + JEU_CADRE_M
    return (minx - tampon, miny - tampon, maxx + tampon, maxy + tampon)


def fond_apercu(
    cadre: tuple[float, float, float, float],
    largeur_px: int = 1100,
    dpi: int = 150,
):
    """Ortho IGN du cadre, suréchantillonnée, à ne télécharger qu'une fois."""
    from .ign import COUCHE_ORTHO, telecharger_fond

    minx, miny, maxx, maxy = cadre
    largeur_px = largeur_px * SURECHANTILLONNAGE
    hauteur_px = max(1, round(largeur_px * (maxy - miny) / (maxx - minx)))
    return telecharger_fond(
        COUCHE_ORTHO,
        cadre,
        largeur_px / dpi * 25.4,
        hauteur_px / dpi * 25.4,
        dpi=dpi,
    )


def apercu_calage(
    implantation: Implantation,
    emprise_l93: BaseGeometry,
    fond=None,
    cadre: tuple[float, float, float, float] | None = None,
    largeur_px: int = 1100,
    dpi: int = 150,
):
    """Superposition du calepinage recalé sur l'ortho IGN, pour validation.

    Image de contrôle destinée à l'écran, pas une planche : le dessin du dossier
    relève du lot 4. Elle existe parce que la validation du calage par
    l'utilisateur est obligatoire et ne peut pas se faire sur des chiffres.

    `fond` et `cadre` se fournissent ensemble pour rejouer l'aperçu sans
    retélécharger l'ortho, ce que fait l'interface à chaque mouvement de curseur.
    """
    from PIL import Image, ImageDraw

    if cadre is None:
        cadre = cadre_apercu(implantation, emprise_l93)
    if fond is None:
        fond = fond_apercu(cadre, largeur_px=largeur_px, dpi=dpi)

    minx, miny, maxx, maxy = cadre
    largeur_m, hauteur_m = maxx - minx, maxy - miny

    couches = geometries_l93(implantation)
    zone = couches["zone_implantation"][0]

    image = fond.image.copy()
    px_largeur, px_hauteur = image.size
    dessin = ImageDraw.Draw(image, "RGBA")

    def en_pixels(geometrie):
        anneaux = []
        for polygone in (
            geometrie.geoms if geometrie.geom_type == "MultiPolygon" else [geometrie]
        ):
            anneaux.append(
                [
                    (
                        (x - minx) / largeur_m * px_largeur,
                        (maxy - y) / hauteur_m * px_hauteur,
                    )
                    for x, y in polygone.exterior.coords
                ]
            )
        return anneaux

    # Les filets sont dimensionnés dans l'image suréchantillonnée : ils
    # retrouvent leur épaisseur nominale après réduction.
    filet = max(1, round(px_largeur / largeur_px))
    # Remplissage et filet sont tracés séparément : `ImageDraw.polygon` avec un
    # `width` supérieur à 1 met 9,6 s pour les 1 590 modules du design 7676351,
    # contre 0,03 s pour le même contour en `line` (Pillow 12, mesuré le
    # 03/09/2026). C'est ce qui rendait le réglage aux curseurs inutilisable.
    for module in couches["modules"]:
        for anneau in en_pixels(module):
            dessin.polygon(anneau, fill=COULEUR_MODULE + (235,))
            dessin.line(anneau, fill=COULEUR_FILET_MODULE, width=filet)
    # Le contour noir cerne la rangée, pas chaque table. HelioScope n'encode
    # aucun groupement en structures — sur les deux designs des Islettes, tous
    # les écarts entre tables valent exactement une largeur de module — et
    # cerner les 530 colonnes une par une noie la trame bleue des modules.
    for silhouette in grouper_en_rangees(couches["tables"]):
        for anneau in en_pixels(silhouette):
            dessin.line(anneau, fill=COULEUR_FILET_TABLE, width=filet, joint="curve")
    for anneau in en_pixels(emprise_l93):
        dessin.line(anneau, fill=COULEUR_EMPRISE, width=filet * 4, joint="curve")
    for anneau in en_pixels(zone):
        dessin.line(anneau, fill=COULEUR_ZONE, width=filet * 4, joint="curve")

    hauteur_cible = max(1, round(largeur_px * px_hauteur / px_largeur))
    return image.resize((largeur_px, hauteur_cible), Image.LANCZOS)
