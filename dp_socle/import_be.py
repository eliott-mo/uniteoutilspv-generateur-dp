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
from typing import Sequence

import ezdxf
from ezdxf import path as ezpath
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .erreurs import (
    ErreurControleCroise,
    ErreurGeoreferencement,
    ErreurImportBE,
)

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
    # Catégories que seul l'import HelioScope (lot 2) produit : le plan du BE
    # ne descend pas au module, et n'a ni zone d'implantation ni recul.
    # Ajoutées au contrat commun plutôt que laissées hors format, pour que le
    # lot 4 lise une seule structure et voie par l'absence de couche ce que la
    # source ne fournit pas. Aucune ne doit être confondue avec `cloture` :
    # `zone_implantation_pv` est un tracé à main levée qui ne suit pas le
    # parcellaire, et en tirer une surface clôturée ou un linéaire de clôture
    # donnerait des chiffres faux dans le dossier.
    "modules_pv",
    "zone_implantation_pv",
    "recul_implantation",
    "zone_evitee",
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
    # Distinguer la haie plantée de l'existante compte pour un dossier DP :
    # l'une est un aménagement, l'autre un état des lieux.
    "haie_existante",
    # Voirie dont le calque ne dit pas si elle est lourde ou légère. Le tableau
    # bilan sépare les deux et le lot 4 doit trancher, plutôt que de supposer.
    "voirie",
    # Portail interne d'exploitation, distinct du portail d'accès au site : le
    # tableau bilan ne compte que le second, et les confondre faisait échouer
    # le contrôle du nombre de portails sur les plans de Sarnois.
    "portail_exploitant",
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
    # Relevés sur les plans de Sarnois le 03/09/2026. La charte du BE n'est pas
    # figée : les mêmes objets y portent d'autres noms qu'à Saint-Cyr.
    "UNI_Local_Stockage": "local_technique",
    "UNI_Haies": "haie",
    "UNI_Haies existantes": "haie_existante",
    "UNI_VRD_Voirie": "voirie",
    # Poste de transformation. La légende du dossier de référence n'a qu'une
    # entrée « Poste de livraison/transformation » : les deux y sont dessinés
    # de la même façon, et le tableau bilan les compte séparément.
    "UNI_PDT": "pdl_ptr",
    # Ces trois-là ne se voient qu'une fois les blocs développés : elles sont
    # portées par le contenu des blocs, pas par leur insertion.
    "UNI_Portail exploitant": "portail_exploitant",
    "UNI_BESS_Batterie": "bess",
    "UNI_BESS_Rétention": "bac_retention",
}

#: Types d'entités traités. Les `HATCH` sont écartés : ce sont des remplissages
#: qui doublent une polyligne déjà présente sur le même calque (vérifié sur le
#: fichier de référence, aire identique au centième de m²). Les reprendre
#: dessinerait chaque élément deux fois.
TYPES_TRAITES = ("LWPOLYLINE", "POLYLINE", "LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE")

#: Profondeur maximale d'imbrication des blocs développés. Les blocs du BE sont
#: imbriqués sur deux niveaux au plus (une table est un bloc dont le contour est
#: une polyligne) ; la borne existe pour qu'un fichier construit en boucle
#: s'arrête en le disant plutôt que de tourner sans fin.
PROFONDEUR_BLOCS_MAX = 8

#: Types d'entités qui ne décrivent jamais un ouvrage : textes, cotations,
#: points, volumes. Ils sont écartés comme les autres types non traités, mais
#: **regroupés en une ligne** : un avertissement par calque portant une
#: étiquette produisait dix-neuf lignes sur le plan de Sarnois, et un écran
#: d'avertissements que personne ne lit ne protège de rien. Un type non traité
#: qui n'est pas dans cette liste garde son avertissement propre : c'est alors
#: une vraie surprise.
TYPES_ANNOTATION = frozenset(
    {
        "TEXT",
        "MTEXT",
        "ATTRIB",
        "ATTDEF",
        "DIMENSION",
        "LEADER",
        "MULTILEADER",
        "MLEADER",
        "POINT",
        "SOLID",
        "3DSOLID",
        "MESH",
        "BODY",
        "REGION",
        "IMAGE",
        "WIPEOUT",
    }
)

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

#: Écart admis entre les deux extrémités d'un contour de clôture avant de
#: signaler qu'il est ouvert, en mètres.
#:
#: Un contour ouvert est refermé pour calculer la surface, ce qui invente un
#: segment entre ses deux bouts. Sur Saint-Cyr la clôture porte le drapeau
#: « fermée » du DXF ; sur Sarnois elle est ouverte, et la surface qu'on en tire
#: dépend d'un segment que le BE n'a pas dessiné. Cela doit se dire.
ECART_FERMETURE_CLOTURE_M = 0.5

#: Écart admis, en degrés, entre l'inclinaison des rangées mesurée sur la
#: géométrie et celle déclarée au tableau bilan — comparées en valeur absolue,
#: voir `_azimut` pour pourquoi.
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


#: Calques délibérément écartés, et pourquoi.
#:
#: Sans cette liste, le plan de Sarnois produisait 45 calques non appariés et
#: 71 avertissements : un écran d'avertissements que personne ne lit ne protège
#: de rien. Ceux-ci sont regroupés en une ligne, tandis qu'un calque vraiment
#: inconnu garde son avertissement propre et sa décision à prendre.
#:
#: Écarter n'est pas ignorer en silence : le regroupement est affiché, et tout
#: calque peut être apparié à la main à l'écran de correspondance.
CALQUES_ECARTES = {
    # Fond cadastral importé par le BE dans son plan. Le dossier prend son
    # cadastre du WFS IGN (lot 1), qui fait foi pour la planche DP 1-3 ; celui
    # du DXF est une copie de travail, sans garantie de fraîcheur.
    "prefixe:cad_": "fond cadastral du BE, remplacé par le WFS IGN",
    # Mobilier du dessin, propre à la mise en page du BE. « cosntruction » est
    # la faute de frappe du fichier réel : la normalisation efface les accents
    # et les séparateurs, pas les fautes.
    "UNI_Legende": "mobilier de dessin",
    "UNI_Echelle": "mobilier de dessin",
    "UNI_Traits de construction": "mobilier de dessin",
    "UNI_Traits de cosntruction": "mobilier de dessin",
    "Defpoints": "calque technique AutoCAD",
    # Couches de travail de PVcase. Les modules détaillés et les cadres pleins
    # doublent le contour déjà repris sur « (optimised) » ; le reste décrit la
    # construction de l'implantation, pas des ouvrages à dessiner.
    "PVcase PV Modules (detailed)": "doublon du contour de table",
    "PVcase PV Modules (full frames)": "doublon du contour de table",
    "PVcase Station": "couche de travail PVcase",
    "PVcase Offsets": "couche de travail PVcase",
    "PVcase AlignmentLine": "couche de travail PVcase",
    "PVcase Effective Area Hatch": "couche de travail PVcase",
    "PVcase PV Area": "couche de travail PVcase",
    "PVcase Trees": "couche de travail PVcase",
    # Le terrain est bien là — 1 898 points cotés et un maillage — mais le
    # profil de la coupe vient du RGE ALTI ou d'un relevé fourni. Le reprendre
    # d'ici demanderait de vérifier son référentiel altimétrique, ce qui n'est
    # pas fait.
    "PVcase Topographic Mesh": "maillage topographique, non exploité",
    "PVcase Topographic Mesh Polygon": "maillage topographique, non exploité",
    "PVcase Online Terrain": "points de terrain, non exploités",
    "-TopoNiveau": "points cotés du BE, non exploités",
    "PVcase Road Center Line": "couche de travail PVcase",
    # Étude d'ombrage portée au plan, pas un ouvrage à dessiner.
    "UNI_PDL-PDT_Zone_Ombre": "étude d'ombrage",
    # Contenu de blocs décoratifs : « GREY » vient d'une illustration, « Edges »
    # du bloc « Sheep rs », le mouton des plans agrivoltaïques. 1 594 et 195
    # entités qui noyaient la liste des calques inconnus.
    "GREY": "habillage décoratif d'un bloc",
    "Edges": "habillage décoratif d'un bloc",
}

_PREFIXES_ECARTES = tuple(
    (cle[len("prefixe:") :], motif)
    for cle, motif in CALQUES_ECARTES.items()
    if cle.startswith("prefixe:")
)
_ECARTES_NORMALISES = {
    normaliser(nom): motif
    for nom, motif in CALQUES_ECARTES.items()
    if not nom.startswith("prefixe:")
}


def motif_ecart(calque: str) -> str | None:
    """Raison pour laquelle un calque est délibérément écarté, ou None."""
    normalise = normaliser(calque)
    motif = _ECARTES_NORMALISES.get(normalise)
    if motif is not None:
        return motif
    for prefixe, motif_prefixe in _PREFIXES_ECARTES:
        if normalise.startswith(normaliser(prefixe)):
            return motif_prefixe
    return None


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



@dataclass(frozen=True)
class CalqueDXF:
    """Un calque du DXF, avec ce qu'il contient et la catégorie proposée."""

    nom: str
    nb_entites: int
    nb_hatch: int
    categorie_proposee: str | None


def calques_du_dxf(chemin: str | Path) -> list[CalqueDXF]:
    """Liste les calques peuplés du DXF, pour l'écran de correspondance.

    Lu avant l'import complet : la correspondance des calques est soumise à
    confirmation, et l'utilisateur doit voir ce qu'il apparie. Les calques sans
    entité sont écartés — le fichier de référence en porte cinq, ce n'est pas
    une anomalie.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise ErreurImportBE(f"DXF du plan BE introuvable : {chemin}")
    try:
        document = ezdxf.readfile(str(chemin))
    except (OSError, ezdxf.DXFError) as exc:
        raise ErreurImportBE(f"DXF illisible ({chemin.name}) : {exc}") from exc

    entites: dict[str, int] = {}
    hatchs: dict[str, int] = {}
    # Le même développement des blocs que `lire_plan_be`, et pour la même
    # raison : sans lui, les tables et les portails de Sarnois n'apparaissaient
    # pas à l'écran de correspondance alors que l'import les trouvait. L'écran
    # où l'on confirme l'appariement doit montrer ce qui sera apparié.
    for calque, entite in _developper(document.modelspace(), None, 0, {}):
        type_dxf = entite.dxftype()
        cible = hatchs if type_dxf == "HATCH" else entites
        if type_dxf != "HATCH" and type_dxf not in TYPES_TRAITES:
            continue
        cible[calque] = cible.get(calque, 0) + 1

    return [
        CalqueDXF(
            nom=nom,
            nb_entites=entites.get(nom, 0),
            nb_hatch=hatchs.get(nom, 0),
            categorie_proposee=categorie_proposee(nom),
        )
        for nom in sorted(set(entites) | set(hatchs))
    ]

# ---------------------------------------------------------------------------
# Étape A — lecture du DXF
# ---------------------------------------------------------------------------


def _calque_de(entite) -> str | None:
    """Calque d'une entité, ou None si elle n'en porte pas.

    Toutes les entités DXF n'ont pas d'attribut `layer` : le plan de Sarnois
    porte un `GEOMAPIMAGE`, l'image géoréférencée du fond de plan, qui n'en a
    pas. Y accéder directement levait une `DXFAttributeError` nue, remontée
    jusqu'à l'écran en trace brute au lieu d'une erreur nommée.
    """
    try:
        return entite.dxf.layer
    except ezdxf.DXFError:
        return None


def _developper(entites, calque_insert: str | None, profondeur: int, anomalies: dict):
    """Parcourt les entités en résolvant les références de bloc.

    Les éléments du plan ne sont pas tous dessinés à plat. Sur Sarnois, les
    85 tables, les 4 portails et la citerne sont des `INSERT`, c'est-à-dire des
    références de bloc avec leur propre rotation et leur propre échelle :
    `virtual_entities()` applique ces transformations, qu'un lecteur écrit à la
    main devrait réimplémenter.

    Le calque retenu est celui de la sous-entité, **sauf s'il vaut « 0 »**,
    auquel cas elle hérite du calque de l'INSERT — c'est la convention AutoCAD,
    et ezdxf 1.4.4 ne l'applique pas de lui-même (vérifié le 03/09/2026 : une
    sous-entité déclarée sur « 0 » ressort sur « 0 »). Sans cette règle, le
    contenu des blocs dessinés sur le calque 0 se retrouverait tout entier dans
    un fourre-tout, et l'élément serait perdu.
    """
    for entite in entites:
        calque = _calque_de(entite)
        type_dxf = entite.dxftype()

        if calque is None:
            anomalies.setdefault("sans_calque", {})
            anomalies["sans_calque"][type_dxf] = (
                anomalies["sans_calque"].get(type_dxf, 0) + 1
            )
            continue

        # Convention AutoCAD : le calque « 0 » dans un bloc signifie « celui de
        # l'insertion ».
        if calque_insert is not None and calque == "0":
            calque = calque_insert

        if type_dxf != "INSERT":
            yield calque, entite
            continue

        if profondeur >= PROFONDEUR_BLOCS_MAX:
            anomalies.setdefault("blocs_trop_imbriques", set()).add(calque)
            continue
        try:
            sous_entites = list(entite.virtual_entities())
        except Exception as exc:  # noqa: BLE001 - remonté en erreur nommée
            raise ErreurImportBE(
                f"Bloc « {entite.dxf.get('name', '?')} » du calque « {calque} » "
                f"impossible à développer : {exc}"
            ) from exc
        yield from _developper(sous_entites, calque, profondeur + 1, anomalies)

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
    annotations: dict[str, int] = {}
    anomalies: dict = {}
    for calque, entite in _developper(modelspace, None, 0, anomalies):
        type_dxf = entite.dxftype()
        if type_dxf == "HATCH":
            hatch_par_calque[calque] = hatch_par_calque.get(calque, 0) + 1
            continue
        if type_dxf in TYPES_ANNOTATION:
            annotations.setdefault(type_dxf, 0)
            annotations[type_dxf] += 1
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

    if annotations:
        detail = ", ".join(f"{n} {typ}" for typ, n in sorted(annotations.items()))
        avertissements.append(
            f"{sum(annotations.values())} annotation(s) écartée(s) ({detail}) : "
            "textes, cotations, points et volumes ne décrivent aucun ouvrage."
        )

    # Les entités sans calque ne sont rattachables à aucune catégorie. Elles sont
    # écartées, mais comptées et dites : c'est la seule façon de savoir qu'un
    # élément a été laissé de côté.
    sans_calque = anomalies.get("sans_calque")
    if sans_calque:
        detail = ", ".join(f"{n} {typ}" for typ, n in sorted(sans_calque.items()))
        avertissements.append(
            f"{sum(sans_calque.values())} entité(s) sans calque écartée(s) "
            f"({detail}). Ces types ne portent pas d'attribut de calque et ne "
            "peuvent être rattachés à aucune catégorie."
        )
    trop_imbriques = anomalies.get("blocs_trop_imbriques")
    if trop_imbriques:
        avertissements.append(
            f"Blocs imbriqués au-delà de {PROFONDEUR_BLOCS_MAX} niveaux sur les "
            f"calques {', '.join(sorted(trop_imbriques))} : leur contenu n'est "
            "pas importé."
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
    ecartes: dict[str, list[str]] = {}
    for calque in calques_ignores:
        motif = motif_ecart(calque)
        if motif is not None:
            ecartes.setdefault(motif, []).append(calque)
            continue
        avertissements.append(
            f"Calque « {calque} » non apparié ({len(entites_par_calque[calque])} "
            "entités) : son contenu n'est pas importé. Appariez-le à une "
            "catégorie si l'élément doit figurer sur les planches."
        )
    for motif, calques in sorted(ecartes.items()):
        avertissements.append(
            f"{len(calques)} calque(s) écarté(s) — {motif} : "
            f"{', '.join(sorted(calques))}. Appariez-en un à l'écran de "
            "correspondance si son contenu doit figurer sur les planches."
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

    for entite in entites:
        if entite.categorie != "cloture" or entite.geometrie.geom_type != "LineString":
            continue
        sommets = list(entite.geometrie.coords)
        ecart = hypot(
            sommets[0][0] - sommets[-1][0], sommets[0][1] - sommets[-1][1]
        )
        if ecart > ECART_FERMETURE_CLOTURE_M:
            avertissements.append(
                f"Le contour de clôture du calque « {entite.calque} » est ouvert : "
                f"{ecart:.1f} m séparent ses deux extrémités. Il est refermé pour "
                "calculer la surface clôturée, ce qui invente un segment que le BE "
                "n'a pas dessiné — vérifiez la surface annoncée."
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


# ---------------------------------------------------------------------------
# Étape C — contrôles croisés
# ---------------------------------------------------------------------------

#: Tolérances des contrôles croisés, en fraction de la valeur du tableau.
TOLERANCE_SURFACE_CLOTURE = 0.02
TOLERANCE_LINEAIRE_CLOTURE = 0.02
TOLERANCE_SURFACE_MODULES = 0.05

#: Débordement de la clôture hors de l'emprise cadastrale en deçà duquel on ne
#: dit rien, en m². Absorbe l'imprécision de numérisation du parcellaire ; un
#: vrai débordement se compte en dizaines de m².
DEBORDEMENT_NEGLIGEABLE_M2 = 1.0

OK = "ok"
AVERTISSEMENT = "avertissement"
BLOQUANT = "bloquant"
#: Contrôle que la source ne permet pas de faire — pas un contrôle réussi.
#: L'import HelioScope n'a qu'une source, là où l'import BE en recoupe deux :
#: la plupart des recoupements n'y ont simplement pas d'objet. Les afficher en
#: vert laisserait croire à une vérification qui n'a pas eu lieu.
IMPOSSIBLE = "impossible"


@dataclass
class Controle:
    """Résultat d'un recoupement entre le DXF, le tableau bilan et l'emprise.

    Le scénario redouté n'est pas le fichier corrompu, c'est le plan mis à jour
    sans le tableau : ces contrôles sont la seule chose qui l'attrape avant le
    dépôt du dossier. Ils ne s'assouplissent pas pour faire passer une entrée.
    """

    libelle: str
    valeur_dxf: float | int | None
    valeur_tableau: float | int | None
    unite: str
    statut: str
    message: str
    tolerance: str = ""

    @property
    def ecart_relatif(self) -> float | None:
        if not self.valeur_tableau or self.valeur_dxf is None:
            return None
        return (self.valeur_dxf - self.valeur_tableau) / self.valeur_tableau

    @property
    def bloquant(self) -> bool:
        return self.statut == BLOQUANT


def controler(
    plan: PlanBE,
    tableau,
    emprise_cadastrale: BaseGeometry | None = None,
    seuil_puissance_mwc: float | None = None,
) -> list[Controle]:
    """Recoupe le plan, le tableau bilan et l'emprise cadastrale.

    `tableau` est un `TableauBilan` de `dp_socle.tableau_bilan` — importé au
    seul titre du typage, d'où l'absence d'annotation : le module des tableaux
    dépend déjà de celui-ci pour la normalisation des libellés.

    `seuil_puissance_mwc` est le seuil de recevabilité en déclaration
    préalable : il vient de l'utilisateur et n'est pas codé en dur, une règle
    d'urbanisme n'ayant pas sa place ici.
    """
    generalites = tableau.generalites
    structures = tableau.structures
    modules = tableau.modules
    controles: list[Controle] = []

    controles.append(
        _egalite_stricte(
            "Nombre de tables",
            plan.nb_tables,
            structures["nb_tables"],
            "tables",
            "Le plan et le tableau ne décrivent pas la même implantation : l'un "
            "des deux n'a pas été mis à jour.",
        )
    )
    controles.append(
        _egalite_stricte(
            "Nombre de portails",
            plan.nb_portails,
            generalites["nb_portails"],
            "portails",
            "Les entités du calque portail sont regroupées par contact ; un "
            "écart signale un portail ajouté ou retiré d'un seul côté.",
        )
    )

    surface_tableau_m2 = generalites["surface_cloturee_ha"] * 10_000.0
    surface_dxf = plan.surface_cloturee_m2
    if surface_dxf is None:
        controles.append(
            Controle(
                "Surface clôturée",
                None,
                surface_tableau_m2,
                "m²",
                BLOQUANT,
                "Aucun contour de clôture dans le DXF : la surface clôturée ne "
                "peut pas être recoupée avec le tableau.",
                "2 %",
            )
        )
    else:
        controles.append(
            _ecart_relatif(
                "Surface clôturée",
                surface_dxf,
                surface_tableau_m2,
                "m²",
                TOLERANCE_SURFACE_CLOTURE,
                BLOQUANT,
                "La surface clôturée du plan et celle du tableau divergent.",
            )
        )

    lineaire_dxf = plan.lineaire_cloture_m
    if lineaire_dxf is None:
        controles.append(
            Controle(
                "Linéaire de clôture",
                None,
                generalites["lineaire_cloture_m"],
                "m",
                AVERTISSEMENT,
                "Aucun contour de clôture dans le DXF : linéaire non contrôlé.",
                "2 %",
            )
        )
    else:
        controles.append(
            _ecart_relatif(
                "Linéaire de clôture",
                lineaire_dxf,
                generalites["lineaire_cloture_m"],
                "m",
                TOLERANCE_LINEAIRE_CLOTURE,
                AVERTISSEMENT,
                "Le tableau arrondit souvent le linéaire ; au-delà de 2 % c'est "
                "le tracé qui a changé.",
            )
        )

    controles.append(
        _ecart_relatif(
            "Surface projetée des modules",
            plan.surface_tables_m2,
            modules["surface_projetee_m2"],
            "m²",
            TOLERANCE_SURFACE_MODULES,
            AVERTISSEMENT,
            "La somme des aires de tables du plan englobe les jeux entre modules "
            "d'une même table ; quelques pour cent d'écart sont normaux.",
        )
    )

    controles.append(
        _azimut(
            plan.azimut_tables_deg,
            structures["azimut_deg"],
            structures["azimut_brut"],
        )
    )
    controles.append(_emprise(plan, emprise_cadastrale))
    controles.append(_puissance(modules["puissance_mwc"], seuil_puissance_mwc))
    return controles


def _egalite_stricte(
    libelle: str, valeur_dxf, valeur_tableau, unite: str, explication: str
) -> Controle:
    conforme = valeur_dxf == valeur_tableau
    return Controle(
        libelle=libelle,
        valeur_dxf=valeur_dxf,
        valeur_tableau=valeur_tableau,
        unite=unite,
        statut=OK if conforme else BLOQUANT,
        tolerance="égalité stricte",
        message=(
            f"{valeur_dxf} au plan comme au tableau."
            if conforme
            else f"{valeur_dxf} au plan contre {valeur_tableau} au tableau. "
            + explication
        ),
    )


def _ecart_relatif(
    libelle: str,
    valeur_dxf: float,
    valeur_tableau: float,
    unite: str,
    tolerance: float,
    statut_echec: str,
    explication: str,
) -> Controle:
    if not valeur_tableau:
        return Controle(
            libelle,
            valeur_dxf,
            valeur_tableau,
            unite,
            statut_echec,
            f"La valeur du tableau est nulle : l'écart avec le plan "
            f"({valeur_dxf:.1f} {unite}) n'est pas calculable.",
            f"{tolerance:.0%}",
        )
    ecart = abs(valeur_dxf - valeur_tableau) / abs(valeur_tableau)
    conforme = ecart <= tolerance
    return Controle(
        libelle=libelle,
        valeur_dxf=valeur_dxf,
        valeur_tableau=valeur_tableau,
        unite=unite,
        statut=OK if conforme else statut_echec,
        tolerance=f"{tolerance:.0%}",
        message=(
            f"Écart de {ecart:.1%} entre le plan et le tableau."
            if conforme
            else f"Écart de {ecart:.1%}, au-delà des {tolerance:.0%} admis. "
            + explication
        ),
    )


def _azimut(azimut_dxf: float, azimut_tableau: float, azimut_brut: str) -> Controle:
    """Recoupe l'inclinaison des rangées mesurée sur les tables avec le tableau.

    **Seules les valeurs absolues sont comparées, et c'est délibéré.** Le champ
    « Azimut (°) » du tableau bilan n'a pas de convention stable d'un projet à
    l'autre — relevé le 03/09/2026 sur trois dossiers : « 0° » pour un champ
    plein sud, donc 0 = sud ; « 41° SE » avec la direction en toutes lettres ;
    et « -24,5 » sans direction et de signe contraire pour une orientation de la
    même famille. Ailleurs encore, le sud est noté 180, en azimut compas.

    Les ramener toutes dans ]-90, 90] absorbe l'origine (0 ou 180 pour le sud),
    et la valeur absolue absorbe le sens de comptage. Ce qui subsiste — de
    combien les rangées s'écartent de l'est-ouest — est la seule grandeur que
    les trois écritures expriment de la même façon.

    Ce que ce contrôle ne voit donc pas : un plan monté en miroir, tables à -41°
    là où le tableau décrit +41°. Il faudrait une convention écrite au tableau
    pour l'attraper, et il n'y en a pas. La cellule est affichée telle quelle à
    côté de la mesure, pour que la lecture reste possible à l'œil.

    Il avertit sans bloquer : c'est toujours la géométrie qui oriente la coupe
    A-A', jamais cette valeur.
    """
    mesure = abs(_dans_demi_tour(azimut_dxf))
    declare = abs(_dans_demi_tour(azimut_tableau))
    ecart = abs(mesure - declare)
    conforme = ecart <= TOLERANCE_AZIMUT_DEG
    return Controle(
        libelle="Inclinaison des rangées",
        valeur_dxf=mesure,
        valeur_tableau=declare,
        unite="° depuis l'est-ouest",
        statut=OK if conforme else AVERTISSEMENT,
        tolerance=f"{TOLERANCE_AZIMUT_DEG:g}°, en valeur absolue",
        message=(
            f"Rangées mesurées à {mesure:.2f}° de l'est-ouest, pour « "
            f"{azimut_brut} » au tableau : écart de {ecart:.2f}°. Seule la "
            "valeur absolue est comparée, le champ du tableau n'ayant pas de "
            "convention stable d'un projet à l'autre — un plan monté en miroir "
            "ne serait donc pas vu ici."
            if conforme
            else f"Rangées mesurées à {mesure:.2f}° de l'est-ouest, pour « "
            f"{azimut_brut} » au tableau : écart de {ecart:.2f}°, au-delà des "
            f"{TOLERANCE_AZIMUT_DEG:g}° admis. Le plan et le tableau ne "
            "décrivent pas la même orientation de rangées. C'est la géométrie "
            "qui oriente la coupe A-A'."
        ),
    )


def _emprise(plan: PlanBE, emprise_cadastrale: BaseGeometry | None) -> Controle:
    polygone = plan.polygone_cloture
    if emprise_cadastrale is None:
        return Controle(
            "Clôture dans l'emprise cadastrale",
            None,
            None,
            "",
            AVERTISSEMENT,
            "Emprise cadastrale non fournie : un débordement de la clôture hors "
            "des parcelles du projet n'aurait pas été vu.",
        )
    if polygone is None:
        return Controle(
            "Clôture dans l'emprise cadastrale",
            None,
            None,
            "",
            AVERTISSEMENT,
            "Aucun contour de clôture dans le DXF : contrôle impossible.",
        )
    surface = float(polygone.difference(emprise_cadastrale).area)
    if surface <= DEBORDEMENT_NEGLIGEABLE_M2:
        return Controle(
            "Clôture dans l'emprise cadastrale",
            0.0,
            None,
            "m²",
            OK,
            "L'emprise clôturée est contenue dans l'emprise cadastrale fournie.",
        )
    return Controle(
        "Clôture dans l'emprise cadastrale",
        surface,
        None,
        "m²",
        AVERTISSEMENT,
        f"L'emprise clôturée déborde de {surface:.0f} m² hors de l'emprise "
        "cadastrale fournie. Vérifiez la maîtrise foncière avant le dépôt.",
    )


def _puissance(puissance_mwc: float, seuil_mwc: float | None) -> Controle:
    """Rappelle la puissance du projet face au seuil de recevabilité en DP.

    Le seuil n'est pas codé en dur : c'est une règle d'urbanisme, qui change, et
    la figer ici reviendrait à faire dire au générateur ce qu'il n'a pas à dire.
    L'outil affiche la puissance en évidence et la compare au seuil saisi.
    """
    if seuil_mwc is None:
        return Controle(
            "Puissance du projet",
            puissance_mwc,
            None,
            "MWc",
            AVERTISSEMENT,
            f"Puissance du projet : {puissance_mwc:.5f} MWc. Aucun seuil de "
            "recevabilité en déclaration préalable n'a été saisi ; contrôlez la "
            "recevabilité du dossier avant le dépôt.",
        )
    conforme = puissance_mwc <= seuil_mwc
    return Controle(
        libelle="Puissance du projet",
        valeur_dxf=puissance_mwc,
        valeur_tableau=seuil_mwc,
        unite="MWc",
        statut=OK if conforme else AVERTISSEMENT,
        tolerance=f"≤ {seuil_mwc:g} MWc",
        message=(
            f"Puissance du projet : {puissance_mwc:.5f} MWc, sous le seuil de "
            f"{seuil_mwc:g} MWc saisi."
            if conforme
            else f"Puissance du projet : {puissance_mwc:.5f} MWc, AU-DESSUS du "
            f"seuil de {seuil_mwc:g} MWc saisi. Le dossier n'est peut-être pas "
            "recevable en déclaration préalable."
        ),
    )


def controles_bloquants(controles: list[Controle]) -> list[Controle]:
    return [c for c in controles if c.bloquant]


# ---------------------------------------------------------------------------
# Sorties — contrat d'interface avec le lot 4
# ---------------------------------------------------------------------------

#: Noms des deux fichiers produits. Le GeoPackage plutôt que du GeoJSON : la
#: spécification GeoJSON impose le WGS84, et y écrire du Lambert 93 est non
#: conforme — cela se paie tôt ou tard par une reprojection silencieuse chez le
#: lecteur. Le GeoPackage porte son système de coordonnées explicitement.
NOM_GEOPACKAGE = "geometries.gpkg"
NOM_PARAMETRES = "projet.json"

#: Producteurs reconnus du contrat. Le champ `origine` du `projet.json` les
#: distingue, et distingue surtout ces sorties du `projet.json` du lot 1, qui
#: porte le même nom dans `projets/`.
ORIGINE_IMPORT_BE = "import_be"
ORIGINE_HELIOSCOPE = "helioscope"
ORIGINES = (ORIGINE_IMPORT_BE, ORIGINE_HELIOSCOPE)

#: Version du contrat de sortie. Elle permet au lot 4 de refuser une sortie
#: qu'il ne sait pas lire, plutôt que de dessiner une planche fausse.
#:
#: Version 2, le 03/09/2026 : alignement du lot 2 (import HelioScope) sur ce
#: contrat. Le schéma gagne quatre couches — `modules_pv`,
#: `zone_implantation_pv`, `recul_implantation`, `zone_evitee` — et le champ
#: `origine` peut désormais valoir « helioscope ». Les sorties en version 1
#: restent lisibles ; l'inverse ne l'est pas, d'où la montée de version.
VERSION_CONTRAT = 2


def ecrire_geopackage(
    source: "PlanBE | Sequence[EntiteBE]",
    dossier: str | Path,
    ligne_coupe=None,
) -> Path:
    """Écrit les géométries en GeoPackage, une couche par catégorie.

    La coordonnée Z est conservée telle que le DXF la porte ; la colonne
    `z_reel` dit si elle décrit le terrain (les tables) ou seulement l'élévation
    d'une polyligne 2D (tout le reste sur le fichier de référence).

    `source` accepte un `PlanBE` ou une simple liste d'`EntiteBE` : l'import
    HelioScope produit des entités du même contrat sans avoir de plan BE, et
    `PlanBE` porte `unite`, `facteur_unite`, `calques_ignores`, qui ne veulent
    rien dire pour lui. Fabriquer un faux `PlanBE` pour satisfaire la signature
    reviendrait à inventer ces valeurs.
    """
    import geopandas as gpd

    entites = list(source.entites if isinstance(source, PlanBE) else source)
    par_categorie: dict[str, list[EntiteBE]] = {}
    for entite in entites:
        par_categorie.setdefault(entite.categorie, []).append(entite)

    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / NOM_GEOPACKAGE
    # Une écriture par-dessus un GeoPackage existant y empilerait les couches
    # d'un import précédent : on repart d'un fichier neuf.
    if chemin.exists():
        chemin.unlink()

    couches = 0
    for categorie in CATEGORIES:
        lot = par_categorie.get(categorie)
        if not lot:
            continue
        gdf = gpd.GeoDataFrame(
            {
                "calque": [e.calque for e in lot],
                "categorie": [e.categorie for e in lot],
                "z_reel": [e.z_reel for e in lot],
                "z_min": [e.z_min for e in lot],
                "z_max": [e.z_max for e in lot],
            },
            geometry=[e.geometrie for e in lot],
            crs=CRS_PROJET,
        )
        gdf.to_file(chemin, layer=categorie, driver="GPKG")
        couches += 1

    if ligne_coupe is not None:
        gdf = gpd.GeoDataFrame(
            {
                "role": ["coupe_AA"],
                "corrigee": [ligne_coupe.corrigee],
                "azimut_tables_deg": [ligne_coupe.azimut_tables_deg],
                "ecart_initial_deg": [ligne_coupe.ecart_initial_deg],
                "longueur_m": [ligne_coupe.longueur_m],
            },
            geometry=[ligne_coupe.geometrie],
            crs=CRS_PROJET,
        )
        gdf.to_file(chemin, layer="ligne_coupe", driver="GPKG")
        couches += 1

    if not couches:
        raise ErreurImportBE(
            "Aucune couche à écrire : le plan importé est vide."
        )
    inconnues = sorted(set(par_categorie) - set(CATEGORIES))
    if inconnues:
        raise ErreurImportBE(
            f"Catégories hors contrat, non écrites : {', '.join(inconnues)}. "
            f"Attendu parmi : {', '.join(CATEGORIES)}."
        )
    return chemin


def parametres_json(
    plan: PlanBE,
    tableau,
    controles: list[Controle],
    ligne_coupe=None,
    profil=None,
    coherence=None,
    seuil_puissance_mwc: float | None = None,
) -> dict:
    """Paramètres techniques, azimut et profil, prêts à être écrits en JSON."""
    import datetime as _dt

    def _lisible(valeur):
        if isinstance(valeur, (_dt.date, _dt.datetime)):
            return valeur.isoformat()
        if isinstance(valeur, tuple):
            return list(valeur)
        return valeur

    donnees = {
        "version_contrat": VERSION_CONTRAT,
        "origine": ORIGINE_IMPORT_BE,
        "sources": {
            "dxf": plan.source,
            "tableau_bilan": tableau.source,
            "indice": tableau.indice,
        },
        "projet": {
            "nom": tableau.nom_projet,
            "phase": _lisible(tableau.generalites.get("phase")),
            "date_tableau": _lisible(tableau.generalites.get("date")),
        },
        "plan": {
            "unite_dxf": plan.unite,
            "azimut_tables_deg": plan.azimut_tables_deg,
            "nb_tables": plan.nb_tables,
            "nb_portails": plan.nb_portails,
            "surface_cloturee_m2": plan.surface_cloturee_m2,
            "lineaire_cloture_m": plan.lineaire_cloture_m,
            "surface_tables_m2": plan.surface_tables_m2,
            "correspondance_calques": plan.correspondance,
            "calques_ignores": plan.calques_ignores,
            "avertissements": plan.avertissements,
        },
        "parametres": {
            groupe: {cle: _lisible(valeur) for cle, valeur in valeurs.items()}
            for groupe, valeurs in (
                ("generalites", tableau.generalites),
                ("structures", tableau.structures),
                ("modules", tableau.modules),
                ("postes", tableau.postes),
            )
        },
        "cotes_normalisees": [
            {
                "ouvrage": cote.ouvrage,
                "dimensions": cote.dimensions,
                "ordre_cotes": cote.ordre_cotes,
                "surface_m2": cote.surface_m2,
                "surface_plateforme_m2": cote.surface_plateforme_m2,
            }
            for cote in tableau.cotes
        ],
        "standards_unite": {
            cle: _lisible(valeur) for cle, valeur in tableau.standards.items()
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
        "seuil_puissance_dp_mwc": seuil_puissance_mwc,
        "avertissements_tableau": tableau.avertissements,
    }

    if ligne_coupe is not None:
        donnees["ligne_coupe"] = {
            "corrigee": ligne_coupe.corrigee,
            "azimut_tables_deg": ligne_coupe.azimut_tables_deg,
            "azimut_coupe_deg": ligne_coupe.azimut_coupe_deg,
            "ecart_initial_deg": ligne_coupe.ecart_initial_deg,
            "longueur_m": ligne_coupe.longueur_m,
            # Les deux tracés sont conservés : la régénération ne redemande
            # jamais le tracé, et l'écran de validation doit pouvoir remontrer
            # ce qui a été redressé.
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
            # Abscisse curviligne depuis A et altitude NGF, dans l'ordre du
            # parcours de la ligne de coupe.
            "points": [
                [round(s, 3), round(z, 3)]
                for s, z in zip(profil.abscisses_m, profil.altitudes_m)
            ],
            "avertissements": profil.avertissements,
        }

    if coherence is not None:
        donnees["coherence_altimetrique"] = {
            "nb_tables_comparees": coherence.nb_tables_comparees,
            "ecart_median_m": coherence.ecart_median_m,
            "ecart_min_m": coherence.ecart_min_m,
            "ecart_max_m": coherence.ecart_max_m,
            "conforme": coherence.conforme,
            "message": coherence.message,
        }

    return donnees


def ecrire_parametres(donnees: dict, dossier: str | Path) -> Path:
    """Écrit `projet.json` dans le dossier de sortie de l'import BE.

    À ne pas confondre avec le `projet.json` du lot 1, qui vit dans
    `projets/{nom}/` et décrit les métadonnées du dossier : celui-ci est la
    sortie de l'import BE, dans `sortie/{nom}/`, et alimente le lot 4. Le champ
    `origine` les distingue à la lecture.
    """
    import json

    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / NOM_PARAMETRES
    chemin.write_text(
        json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return chemin


def lire_parametres(dossier: str | Path) -> dict | None:
    """Relit le `projet.json` d'un import précédent, ou None s'il n'y en a pas.

    Sert à ne jamais redemander le tracé de la coupe : rouvrir un dossier
    reprend ce que le chef de projet avait tracé. L'absence de fichier est un
    cas normal — c'est le premier import — et rend None. Un fichier présent mais
    illisible lève : le reprendre à moitié serait pire que de le rejeter.
    """
    import json

    chemin = Path(dossier) / NOM_PARAMETRES
    if not chemin.exists():
        return None
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ErreurImportBE(
            f"{chemin} est présent mais illisible : {exc}. Supprimez-le pour "
            "repartir d'un import neuf."
        ) from exc

    if not isinstance(donnees, dict):
        raise ErreurImportBE(f"{chemin} ne contient pas un objet JSON.")

    origine = donnees.get("origine")
    if origine not in ORIGINES:
        # Le `projet.json` du lot 1, dans projets/{nom}/, porte le même nom. Y
        # chercher une ligne de coupe ne rendrait rien de bon. On accepte les
        # deux producteurs du contrat et on continue de refuser tout le reste.
        raise ErreurImportBE(
            f"{chemin} n'est pas une sortie du contrat (origine « {origine} », "
            f"attendu parmi : {', '.join(sorted(ORIGINES))}). Le projet.json du "
            "lot 1 vit dans projets/, pas dans sortie/."
        )

    version = donnees.get("version_contrat")
    if not isinstance(version, int) or version > VERSION_CONTRAT:
        raise ErreurImportBE(
            f"{chemin} annonce la version de contrat {version!r}, alors que cet "
            f"outil lit jusqu'à la version {VERSION_CONTRAT}. Régénérez la "
            "sortie avec une version plus récente de l'outil."
        )
    return donnees

@dataclass
class ImportBE:
    """Résultat complet d'un import : plan, tableau, contrôles, coupe, profil."""

    plan: PlanBE
    tableau: object
    controles: list[Controle]
    ligne_coupe: object | None = None
    profil: object | None = None
    coherence: object | None = None
    seuil_puissance_mwc: float | None = None

    @property
    def bloquants(self) -> list[Controle]:
        return controles_bloquants(self.controles)

    @property
    def avertissements(self) -> list[str]:
        messages = list(self.plan.avertissements) + list(self.tableau.avertissements)
        for controle in self.controles:
            if controle.statut == AVERTISSEMENT:
                messages.append(f"{controle.libelle} : {controle.message}")
        if self.ligne_coupe is not None:
            messages.extend(self.ligne_coupe.avertissements)
        if self.profil is not None:
            messages.extend(self.profil.avertissements)
        if self.coherence is not None and not self.coherence.conforme:
            messages.append(self.coherence.message)
        return messages

    def ecrire(self, dossier: str | Path) -> tuple[Path, Path]:
        """Écrit le GeoPackage et `projet.json`, après refus des bloquants.

        L'écriture est refusée tant qu'un contrôle bloquant subsiste : produire
        le contrat d'interface du lot 4 à partir d'entrées qui se contredisent
        reviendrait à fabriquer un dossier plausible et faux.
        """
        bloquants = self.bloquants
        if bloquants:
            raise ErreurControleCroise(
                "Contrôles croisés bloquants, sortie non écrite :\n"
                + "\n".join(f"— {c.libelle} : {c.message}" for c in bloquants)
            )
        gpkg = ecrire_geopackage(self.plan, dossier, self.ligne_coupe)
        parametres = ecrire_parametres(
            parametres_json(
                self.plan,
                self.tableau,
                self.controles,
                self.ligne_coupe,
                self.profil,
                self.coherence,
                self.seuil_puissance_mwc,
            ),
            dossier,
        )
        return gpkg, parametres


def importer_be(
    chemin_dxf: str | Path,
    chemin_tableau: str | Path,
    indice: str,
    correspondance: dict[str, str] | None = None,
    emprise_cadastrale: BaseGeometry | None = None,
    seuil_puissance_mwc: float | None = None,
) -> ImportBE:
    """Lit les deux fichiers du BE et les recoupe. Ne trace pas la coupe A-A'.

    La ligne de coupe demande un tracé de l'utilisateur : elle s'ajoute ensuite
    au résultat, avec le profil du terrain.
    """
    from .tableau_bilan import lire_tableau

    plan = lire_plan_be(chemin_dxf, correspondance)
    tableau = lire_tableau(chemin_tableau, indice)
    controles = controler(plan, tableau, emprise_cadastrale, seuil_puissance_mwc)
    return ImportBE(
        plan=plan,
        tableau=tableau,
        controles=controles,
        seuil_puissance_mwc=seuil_puissance_mwc,
    )
