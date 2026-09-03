"""Import du plan final du bureau d'études interne (lot 2bis).

Le BE fournit un DXF déjà géoréférencé en Lambert 93 et un tableau bilan Excel.
Il n'y a donc ni calage à faire ni élément technique à saisir : le travail est
de lire, normaliser et **recouper** ces deux fichiers avant de les transmettre
au dessin des planches (lot 4).

Ce module ne dessine rien.

Le scénario d'erreur réaliste n'est pas le fichier corrompu : c'est le plan mis
à jour sans le tableau, ou l'inverse. Personne ne s'en aperçoit avant
l'instruction du dossier. Les contrôles croisés de l'étape C sont donc la
véritable valeur de ce lot, et ne doivent jamais être assouplis pour faire
passer une entrée.

Vérifications faites sur le jeu de référence Saint-Cyr-en-Val
(`20260903_SCV_IND06.dxf`, `20260825_SCV_Tableau_Bilan_V6.xlsx`) le 03/09/2026.
"""

from __future__ import annotations

import statistics
import unicodedata
from dataclasses import dataclass, field
from math import atan2, degrees, hypot
from pathlib import Path

import ezdxf
from ezdxf import path as ezpath
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .erreurs import ErreurGeoreferencement, ErreurImportBE

CRS_PROJET = "EPSG:2154"

#: Bornes du Lambert 93 pour la France métropolitaine, Corse comprise. Un plan
#: qui en sort n'est pas géoréférencé — ou l'est dans un autre système — et le
#: générateur refuse plutôt que de produire un dossier situé ailleurs.
X_MIN_L93, X_MAX_L93 = 100_000.0, 1_300_000.0
Y_MIN_L93, Y_MAX_L93 = 6_000_000.0, 7_200_000.0

#: Facteurs d'unité essayés pour ramener les coordonnées du DXF en mètres.
#: `$INSUNITS` n'est jamais consulté : sur le fichier de référence il annonce
#: des millimètres (valeur 4) alors que les coordonnées sont en mètres. Un
#: outil qui croirait l'en-tête diviserait tout le plan par mille.
FACTEURS_UNITE = {
    "mètre": 1.0,
    "millimètre": 0.001,
    "centimètre": 0.01,
    "pied": 0.3048,
}

#: Catégories du contrat d'interface avec le lot 4. Toute géométrie importée
#: porte l'une d'elles ; les calques non appariés sont écartés en le disant.
CATEGORIES = (
    "tables_pv",
    "cloture",
    "portail",
    "pdl_ptr",
    "plateforme",
    "piste_lourde_existante",
    "piste_lourde_a_creer",
    "bache_incendie",
    "aire_aspiration",
    "local_technique",
    "bess",
    "bac_retention",
    "haie",
    "ligne_coupe",
)

#: Correspondance calque → catégorie proposée par défaut, d'après la charte de
#: nommage `UNI_` du BE. Elle est soumise à confirmation de l'utilisateur : la
#: charte n'est pas figée et un calque mal apparié fait disparaître un élément
#: du plan sans erreur visible.
CORRESPONDANCE_DEFAUT = {
    "PVcase PV Modules (optimised)": "tables_pv",
    "UNI_Clôture": "cloture",
    "UNI_portail": "portail",
    "UNI_PDL": "pdl_ptr",
    "UNI_VRD_Plateforme": "plateforme",
    "UNI_VRD_Piste_lourde_existante": "piste_lourde_existante",
    "UNI_VRD_Piste_lourde_à_créer": "piste_lourde_a_creer",
    "UNI_SDIS_Bache_incendie": "bache_incendie",
    "UNI_SDIS_Aire_d-aspiration": "aire_aspiration",
    "UNI_Local_technique": "local_technique",
    "UNI_BESS": "bess",
    "UNI_Bac_de_retention": "bac_retention",
    "UNI_Haie": "haie",
}

#: Types d'entités traités. Les `HATCH` sont écartés : ce sont des remplissages
#: qui doublent une polyligne déjà présente sur le même calque (vérifié sur le
#: fichier de référence, aire identique au centième de m²). Les reprendre
#: dessinerait chaque élément deux fois.
TYPES_TRAITES = ("LWPOLYLINE", "POLYLINE", "LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE")

#: Flèche maximale de discrétisation des arcs, en mètres. Les portails sont
#: dessinés avec des arcs de 3,5 m de rayon et les plateformes portent des
#: bulges : au centimètre, l'écart de surface mesuré sur le fichier de
#: référence est de 1,8 % sur une plateforme de 133 m², invisible à l'échelle
#: des planches DP.
FLECHE_DISCRETISATION_M = 0.01

#: Distance en deçà de laquelle deux entités d'un même calque sont tenues pour
#: appartenant au même ouvrage, au moment de compter les portails. Un portail
#: est dessiné en cinq entités jointives (deux vantaux, leur débattement en
#: arcs, et l'ouverture) ; les portails d'un même site sont distants de
#: plusieurs dizaines de mètres.
TOLERANCE_REGROUPEMENT_M = 0.05

#: Écart admis entre l'azimut calculé sur la géométrie et celui déclaré au
#: tableau bilan, en degrés.
TOLERANCE_AZIMUT_DEG = 2.0


# ---------------------------------------------------------------------------
# Normalisation tolérante des libellés
# ---------------------------------------------------------------------------

#: Caractères effacés avant comparaison. Les noms de calque du BE contiennent
#: des accents et des caractères substitués : l'apostrophe de « aire
#: d'aspiration » est devenue un tiret dans le fichier de référence. Comparer
#: des chaînes brutes ferait perdre le calque en silence.
_SEPARATEURS = "-_ '’` ‑–—."


def normaliser(texte: object) -> str:
    """Forme comparable d'un libellé : sans accent, sans casse, sans séparateur.

    Sert aussi bien aux noms de calque du DXF qu'aux libellés du tableau bilan.
    """
    if texte is None:
        return ""
    decompose = unicodedata.normalize("NFKD", str(texte))
    sans_accent = "".join(c for c in decompose if not unicodedata.combining(c))
    return "".join(
        c for c in sans_accent.casefold() if c not in _SEPARATEURS
    ).strip()


_CORRESPONDANCE_NORMALISEE = {
    normaliser(calque): categorie for calque, categorie in CORRESPONDANCE_DEFAUT.items()
}


def categorie_proposee(calque: str) -> str | None:
    """Catégorie proposée pour un nom de calque, ou None s'il est inconnu."""
    return _CORRESPONDANCE_NORMALISEE.get(normaliser(calque))


# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntiteBE:
    """Une géométrie du plan BE, en Lambert 93, rattachée à une catégorie."""

    categorie: str
    calque: str
    geometrie: BaseGeometry
    #: Vrai quand la coordonnée Z du DXF porte une altitude de terrain plutôt
    #: qu'un zéro d'élévation de polyligne. Seules les tables en portent une sur
    #: le fichier de référence ; le lot 4 s'en sert pour recouper le MNT.
    z_reel: bool

    @property
    def z_min(self) -> float | None:
        return _borne_z(self.geometrie, min)

    @property
    def z_max(self) -> float | None:
        return _borne_z(self.geometrie, max)


@dataclass
class PlanBE:
    """Contenu normalisé du DXF du bureau d'études."""

    entites: list[EntiteBE]
    azimut_tables_deg: float
    correspondance: dict[str, str]
    unite: str
    facteur_unite: float
    calques_ignores: list[str]
    calques_vides: list[str]
    source: str
    avertissements: list[str] = field(default_factory=list)

    def par_categorie(self, categorie: str) -> list[EntiteBE]:
        return [e for e in self.entites if e.categorie == categorie]

    def geometries(self, categorie: str) -> list[BaseGeometry]:
        return [e.geometrie for e in self.par_categorie(categorie)]

    @property
    def tables(self) -> list[BaseGeometry]:
        return [g for g in self.geometries("tables_pv") if g.geom_type == "Polygon"]

    @property
    def nb_tables(self) -> int:
        return len(self.tables)

    @property
    def surface_tables_m2(self) -> float:
        return float(sum(g.area for g in self.tables))

    @property
    def cloture(self) -> BaseGeometry | None:
        """Contour clôturé, en un seul anneau. None si le calque est absent."""
        geometries = self.geometries("cloture")
        if not geometries:
            return None
        if len(geometries) > 1:
            # Plusieurs anneaux : c'est possible (site en deux parties), mais on
            # ne les fusionne pas en silence — l'union sert aux mesures, et le
            # nombre d'anneaux est rappelé à l'écran de validation.
            return unary_union(geometries)
        return geometries[0]

    @property
    def polygone_cloture(self) -> Polygon | None:
        """Emprise clôturée sous forme de polygone, quel que soit le tracé source."""
        geometrie = self.cloture
        if geometrie is None:
            return None
        return _polygoniser(geometrie)

    @property
    def surface_cloturee_m2(self) -> float | None:
        polygone = self.polygone_cloture
        return None if polygone is None else float(polygone.area)

    @property
    def lineaire_cloture_m(self) -> float | None:
        geometrie = self.cloture
        if geometrie is None:
            return None
        return float(sum(_perimetre(g) for g in _parties(geometrie)))

    @property
    def nb_portails(self) -> int:
        return _compter_ouvrages(self.geometries("portail"))


def _borne_z(geometrie: BaseGeometry, choix) -> float | None:
    if not geometrie.has_z:
        return None
    zs = [c[2] for g in _parties(geometrie) for c in _coordonnees(g)]
    return choix(zs) if zs else None


def _parties(geometrie: BaseGeometry):
    if hasattr(geometrie, "geoms"):
        for partie in geometrie.geoms:
            yield from _parties(partie)
    else:
        yield geometrie


def _coordonnees(geometrie: BaseGeometry):
    if geometrie.geom_type == "Polygon":
        return list(geometrie.exterior.coords)
    return list(geometrie.coords)


def _perimetre(geometrie: BaseGeometry) -> float:
    if geometrie.geom_type == "Polygon":
        return float(geometrie.exterior.length)
    return float(geometrie.length)


def _polygoniser(geometrie: BaseGeometry) -> Polygon | None:
    """Polygone d'un contour, qu'il arrive en polygone ou en ligne fermée."""
    morceaux = []
    for partie in _parties(geometrie):
        if partie.geom_type == "Polygon":
            morceaux.append(partie)
        elif partie.geom_type == "LineString" and len(partie.coords) >= 4:
            morceaux.append(Polygon([(x, y) for x, y, *_ in partie.coords]))
    if not morceaux:
        return None
    union = unary_union(morceaux)
    return union if union.geom_type in ("Polygon", "MultiPolygon") else None


def _compter_ouvrages(geometries: list[BaseGeometry]) -> int:
    """Nombre d'ouvrages distincts dans un lot de géométries jointives.

    Un portail arrive en cinq entités qui se touchent ; deux portails du même
    site sont distants de dizaines de mètres. Le regroupement se fait donc par
    contact, pas par comptage d'entités.
    """
    if not geometries:
        return 0
    tampon = unary_union(geometries).buffer(TOLERANCE_REGROUPEMENT_M)
    return len(tampon.geoms) if hasattr(tampon, "geoms") else 1


# ---------------------------------------------------------------------------
# Étape A — lecture du DXF
# ---------------------------------------------------------------------------


def lire_plan_be(
    chemin: str | Path,
    correspondance: dict[str, str] | None = None,
) -> PlanBE:
    """Lit le DXF du BE et renvoie ses géométries normalisées en Lambert 93.

    `correspondance` associe un nom de calque à une catégorie ; laissée à None,
    la correspondance par défaut est appliquée et les calques inconnus sont
    signalés plutôt qu'écartés en silence.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise ErreurImportBE(f"DXF du plan BE introuvable : {chemin}")
    try:
        document = ezdxf.readfile(str(chemin))
    except (OSError, ezdxf.DXFError) as exc:
        raise ErreurImportBE(f"DXF illisible ({chemin.name}) : {exc}") from exc

    modelspace = document.modelspace()
    avertissements: list[str] = []

    entites_par_calque: dict[str, list] = {}
    hatch_par_calque: dict[str, int] = {}
    types_ecartes: dict[str, set[str]] = {}
    for entite in modelspace:
        calque = entite.dxf.layer
        type_dxf = entite.dxftype()
        if type_dxf == "HATCH":
            hatch_par_calque[calque] = hatch_par_calque.get(calque, 0) + 1
            continue
        if type_dxf not in TYPES_TRAITES:
            types_ecartes.setdefault(calque, set()).add(type_dxf)
            continue
        entites_par_calque.setdefault(calque, []).append(entite)

    if not entites_par_calque:
        raise ErreurImportBE(
            f"{chemin.name} ne contient aucune entité exploitable dans l'espace objet "
            f"(types attendus : {', '.join(TYPES_TRAITES)})."
        )

    unite, facteur = _detecter_unite(entites_par_calque, chemin.name)
    if facteur != 1.0:
        avertissements.append(
            f"Coordonnées lues en {unite}s et converties en mètres (facteur "
            f"{facteur}). L'en-tête $INSUNITS du fichier n'a pas été consulté : "
            "l'unité est déduite de l'ordre de grandeur des coordonnées."
        )

    for calque, types in sorted(types_ecartes.items()):
        avertissements.append(
            f"Calque « {calque} » : entités de type {', '.join(sorted(types))} "
            "non traitées et absentes du plan importé."
        )

    # Un calque qui n'existe qu'en remplissage perdrait son élément : les HATCH
    # sont écartés partout, donc un calque qui n'a que ça ne produit rien.
    for calque, nombre in sorted(hatch_par_calque.items()):
        if calque not in entites_par_calque:
            avertissements.append(
                f"Calque « {calque} » : {nombre} remplissage(s) HATCH et aucune "
                "polyligne. L'élément serait perdu — demandez au BE de fournir "
                "son contour."
            )

    # Les calques déclarés mais sans entité sont ignorés sans message : le
    # fichier de référence en porte trois (« PVcase PV Modules (full frames) »,
    # « (detailed) », « PVcase Station ») et ce n'est pas une anomalie.
    calques_vides = sorted(
        couche.dxf.name
        for couche in document.layers
        if couche.dxf.name not in entites_par_calque
        and couche.dxf.name not in hatch_par_calque
    )

    if correspondance is None:
        correspondance = {}
        for calque in sorted(entites_par_calque):
            categorie = categorie_proposee(calque)
            if categorie is not None:
                correspondance[calque] = categorie

    inconnues = sorted(set(correspondance.values()) - set(CATEGORIES))
    if inconnues:
        raise ErreurImportBE(
            f"Catégories inconnues dans la correspondance des calques : "
            f"{', '.join(inconnues)}. Attendu parmi : {', '.join(CATEGORIES)}."
        )

    calques_ignores = sorted(set(entites_par_calque) - set(correspondance))
    for calque in calques_ignores:
        avertissements.append(
            f"Calque « {calque} » non apparié ({len(entites_par_calque[calque])} "
            "entités) : son contenu n'est pas importé. Appariez-le à une "
            "catégorie si l'élément doit figurer sur les planches."
        )

    entites: list[EntiteBE] = []
    sommets_perdus: dict[str, int] = {}
    for calque, categorie in correspondance.items():
        if calque not in entites_par_calque:
            avertissements.append(
                f"Calque « {calque} » apparié à « {categorie} » mais absent du "
                "fichier ou vide : aucune géométrie importée pour cette catégorie."
            )
            continue
        for entite in entites_par_calque[calque]:
            geometrie, perdus = _geometrie_de(entite, facteur, chemin.name)
            if geometrie is None:
                continue
            sommets_perdus[calque] = sommets_perdus.get(calque, 0) + perdus
            entites.append(
                EntiteBE(
                    categorie=categorie,
                    calque=calque,
                    geometrie=geometrie,
                    z_reel=_z_varie(geometrie),
                )
            )

    for calque, perdus in sorted(sommets_perdus.items()):
        if perdus:
            avertissements.append(
                f"Calque « {calque} » : {perdus} sommet(s) dupliqué(s) en plan "
                "supprimé(s), tracé conservé dans l'ordre. Signe habituel d'une "
                "polyligne extrudée en 3D."
            )

    if not entites:
        raise ErreurImportBE(
            f"Aucune géométrie importée depuis {chemin.name} : la correspondance "
            "des calques n'apparie rien. Calques présents : "
            f"{', '.join(sorted(entites_par_calque))}."
        )

    tables = [
        e.geometrie
        for e in entites
        if e.categorie == "tables_pv" and e.geometrie.geom_type == "Polygon"
    ]
    azimut = azimut_tables(tables)

    return PlanBE(
        entites=entites,
        azimut_tables_deg=azimut,
        correspondance=dict(correspondance),
        unite=unite,
        facteur_unite=facteur,
        calques_ignores=calques_ignores,
        calques_vides=calques_vides,
        source=chemin.name,
        avertissements=avertissements,
    )


def _detecter_unite(entites_par_calque: dict[str, list], nom: str) -> tuple[str, float]:
    """Unité du dessin, déduite de l'ordre de grandeur des coordonnées.

    `$INSUNITS` n'est volontairement pas lu : sur le fichier de référence il
    vaut 4 (millimètres) alors que les coordonnées sont en mètres.
    """
    xs: list[float] = []
    ys: list[float] = []
    for entites in entites_par_calque.values():
        for entite in entites:
            try:
                boite = ezpath.make_path(entite).bbox()
            except Exception:  # noqa: BLE001 - type d'entité inattendu, signalé plus bas
                continue
            if boite.has_data:
                xs.extend((boite.extmin.x, boite.extmax.x))
                ys.extend((boite.extmin.y, boite.extmax.y))
    if not xs:
        raise ErreurImportBE(
            f"{nom} : aucune coordonnée exploitable, impossible de déterminer l'unité."
        )

    centre_x = (min(xs) + max(xs)) / 2.0
    centre_y = (min(ys) + max(ys)) / 2.0
    candidats = [
        (nom_unite, facteur)
        for nom_unite, facteur in FACTEURS_UNITE.items()
        if X_MIN_L93 <= centre_x * facteur <= X_MAX_L93
        and Y_MIN_L93 <= centre_y * facteur <= Y_MAX_L93
    ]
    if not candidats:
        raise ErreurGeoreferencement(
            f"{nom} : les coordonnées ne tombent dans les bornes du Lambert 93 "
            f"métropolitain pour aucune unité usuelle. Centre du dessin lu à "
            f"X={centre_x:.1f} Y={centre_y:.1f} (attendu X entre "
            f"{X_MIN_L93:,.0f} et {X_MAX_L93:,.0f}, Y entre {Y_MIN_L93:,.0f} et "
            f"{Y_MAX_L93:,.0f}). Le plan ne semble pas géoréférencé en Lambert 93 ; "
            "demandez au BE un export en EPSG:2154."
            .replace(",", " ")
        )
    if len(candidats) > 1:
        raise ErreurGeoreferencement(
            f"{nom} : l'unité du dessin est ambiguë, {len(candidats)} facteurs "
            f"placent le plan en Lambert 93 ({', '.join(c[0] for c in candidats)}). "
            "Le générateur refuse de choisir."
        )
    return candidats[0]


def _geometrie_de(
    entite, facteur: float, nom_fichier: str
) -> tuple[BaseGeometry | None, int]:
    """Géométrie shapely d'une entité DXF, arcs discrétisés, Z conservé.

    Renvoie aussi le nombre de sommets dupliqués en plan qui ont été retirés.
    `ezdxf.path` traite d'une seule main les polylignes 2D à bulge, les
    polylignes 3D, les lignes et les arcs : réimplémenter la discrétisation des
    bulges à la main était le piège à éviter (les plateformes du fichier de
    référence en portent quatre, invisibles dans la liste des sommets).
    """
    try:
        trace = ezpath.make_path(entite)
    except Exception as exc:  # noqa: BLE001 - remonté en erreur nommée
        raise ErreurImportBE(
            f"{nom_fichier} : entité {entite.dxftype()} du calque "
            f"« {entite.dxf.layer} » non convertible ({exc})."
        ) from exc

    sommets = [
        (v.x * facteur, v.y * facteur, v.z * facteur)
        for v in trace.flattening(distance=FLECHE_DISCRETISATION_M / max(facteur, 1e-12))
    ]
    if len(sommets) < 2:
        return None, 0

    ferme = hypot(sommets[0][0] - sommets[-1][0], sommets[0][1] - sommets[-1][1]) <= 1e-6
    corps = sommets[:-1] if ferme else sommets

    # Dédoublonnage sur (x, y) en préservant l'ordre : les polylignes extrudées
    # en 3D portent des sommets superposés en plan. Un `set()` détruirait la
    # géométrie en perdant l'ordre du tracé.
    vus: set[tuple[float, float]] = set()
    uniques = []
    for x, y, z in corps:
        cle = (round(x, 6), round(y, 6))
        if cle in vus:
            continue
        vus.add(cle)
        uniques.append((x, y, z))
    perdus = len(corps) - len(uniques)

    if ferme and len(uniques) >= 3:
        return Polygon(uniques), perdus
    if len(uniques) < 2:
        return None, perdus
    return LineString(uniques), perdus


def _z_varie(geometrie: BaseGeometry) -> bool:
    """Vrai si la coordonnée Z porte une information, faux si elle est constante.

    Une polyligne 2D ressort avec Z figé à son élévation, le plus souvent zéro :
    la distinguer d'une table qui suit le terrain évite au lot 4 de recouper le
    MNT avec des zéros.
    """
    if not geometrie.has_z:
        return False
    zs = [c[2] for c in _coordonnees(geometrie)]
    return bool(zs) and (max(zs) - min(zs)) > 1e-6


# ---------------------------------------------------------------------------
# Azimut des tables
# ---------------------------------------------------------------------------


def azimut_tables(tables: list[BaseGeometry]) -> float:
    """Direction du grand côté des tables, en degrés depuis l'est, dans ]-90, 90].

    Calculé sur la géométrie et non sur le tableau bilan : c'est la seule
    valeur dont on soit sûr qu'elle décrit le plan qu'on va dessiner. Sur le
    fichier de référence elle vaut 0°, c'est-à-dire des rangées est-ouest.
    """
    if not tables:
        raise ErreurImportBE(
            "Aucune table de modules dans le plan : l'azimut ne peut pas être "
            "calculé, et la ligne de coupe A-A' ne peut pas être orientée."
        )
    angles = [_angle_grand_cote(table) for table in tables]
    return _mediane_axiale(angles)


def _angle_grand_cote(polygone: BaseGeometry) -> float:
    """Angle du grand côté du rectangle englobant orienté, en degrés depuis l'est."""
    rectangle = polygone.minimum_rotated_rectangle
    if rectangle.geom_type != "Polygon":
        raise ErreurImportBE(
            f"Table dégénérée : son rectangle englobant est un "
            f"{rectangle.geom_type}, pas un polygone."
        )
    sommets = list(rectangle.exterior.coords)[:-1]
    meilleur, longueur_max = 0.0, -1.0
    for (x1, y1, *_), (x2, y2, *_) in zip(sommets, sommets[1:] + sommets[:1]):
        longueur = hypot(x2 - x1, y2 - y1)
        if longueur > longueur_max:
            longueur_max, meilleur = longueur, degrees(atan2(y2 - y1, x2 - x1))
    return meilleur


def _mediane_axiale(angles: list[float]) -> float:
    """Médiane d'un lot de directions non orientées, dans ]-90, 90].

    Une direction et son opposée décrivent la même rangée : la médiane naïve
    d'angles ramenés dans ]-90, 90] casserait sur un lot proche de ±90°, où des
    valeurs voisines sur le terrain se retrouveraient aux deux bouts de
    l'intervalle. On recale donc d'abord sur la moyenne axiale (moyenne des
    angles doublés, convention usuelle pour les directions), puis on prend la
    médiane dans la demi-tour centrée sur elle.
    """
    from math import cos, radians, sin

    moyenne_x = sum(cos(2 * radians(a)) for a in angles)
    moyenne_y = sum(sin(2 * radians(a)) for a in angles)
    centre = degrees(atan2(moyenne_y, moyenne_x)) / 2.0
    recales = [centre + _dans_demi_tour(a - centre) for a in angles]
    return _dans_demi_tour(statistics.median(recales))


def _dans_demi_tour(angle: float) -> float:
    """Ramène un angle dans ]-90, 90] : une rangée n'a pas de sens de parcours."""
    angle = (angle + 90.0) % 180.0 - 90.0
    return 90.0 if angle == -90.0 else angle
