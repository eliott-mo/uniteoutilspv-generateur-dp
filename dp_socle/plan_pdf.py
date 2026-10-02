"""Import d'un plan projet PDF, calé sur les tables d'un export HelioScope (lot 2ter).

Certains projets n'ont ni plan du bureau d'études ni DXF complet : le chef de
projet dispose d'un export HelioScope qui ne porte **que les tables**, et d'un
plan PDF — l'annexe 5 d'une demande d'examen au cas par cas, montée dans
PowerPoint sur une copie d'écran HelioScope — qui porte tout le reste :
clôture, portail, haies, pistes, postes, local technique, réserve incendie. Le
cas est arrivé à Gannay-sur-Loire (03) en septembre 2026.

Ce module lit ce plan, le cale sur les tables que le lot 2 a posées, et en
tire les géométries du contrat commun. Il ne dessine rien.

Trois constats, mesurés le 23/09/2026 sur les plans de Gannay et de
Bray-Saint-Aignan, ont décidé de sa forme :

- **le plan est vectoriel.** PowerPoint exporte ses formes en tracés, avec
  leur couleur exacte ; seule la copie d'écran HelioScope — et avec elle les
  tables — est une image. On lit donc les tracés, et l'image pour les tables
  seulement. Le prototype rendait la page à 300 dpi et relevait les couleurs
  au pixel : il trouvait huit locaux techniques et quatre BESS là où le plan
  de Gannay en dessine un de chaque, et manquait le poste de livraison ;
- **deux exports, deux écritures du même trait.** Le plan de Gannay garde ses
  traits en traits et sa clôture en points ; celui de Bray les écrit en
  contours remplis, un trait épais y devenant une capsule. On lit donc l'axe
  d'une forme, pas la forme ;
- **les couleurs changent d'un plan à l'autre** : la clôture est un pointillé
  magenta à Gannay, un trait rouge à Bray, dont le local technique est rouge.
  Rien n'est écrit en dur : chaque couleur se relève sur la pastille de la
  légende qui précède son libellé (décision D1).

Tout le traitement se fait en **points PDF, ordonnée vers le haut**, puis dans
le repère local du DXF HelioScope — mètres au sol, nord en haut — où le plan se
cale sur les tables ; le passage en Lambert 93 est celui du lot 2.
"""

from __future__ import annotations

import ctypes
import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

from .erreurs import (
    ErreurEchelleIncoherente,
    ErreurLegendeIntrouvable,
    ErreurPlanPDF,
    ErreurRecouvrementInsuffisant,
)
from .import_be import normaliser
from .pistes import (
    JEU_CLOTURE_M,
    LARGEUR_PISTE_M,
    RAYON_AXE_M,
    RAYON_INTERIEUR_M,
    AxePiste,
    dessiner_pistes,
    serrer_contre,
)

# ---------------------------------------------------------------------------
# Vocabulaire de la légende
# ---------------------------------------------------------------------------

#: Libellés de légende connus, et la catégorie du contrat qu'on leur propose.
#:
#: Relevés le 23/09/2026 sur les deux plans d'essai, tirés du même modèle
#: PowerPoint d'annexe 5 mais pas de la même version : les mêmes objets y
#: portent d'autres noms, comme les calques du BE d'un projet à l'autre. La
#: comparaison passe par `import_be.normaliser` — accents, casse et séparateurs
#: effacés — et un libellé inconnu n'est rattaché à rien : il est signalé, et
#: s'apparie à la main.
CORRESPONDANCE_LEGENDE = {
    "Clôture": "cloture",
    "Portail": "portail",
    "Haie à créer": "haie",
    # Faute du modèle, relevée à Gannay : la normalisation efface les accents
    # et les séparateurs, pas les fautes.
    "Haie à crée": "haie",
    # Une haie qu'on complète n'est ni une plantation neuve ni un simple état
    # des lieux : elle a sa catégorie depuis le 30/09/2026. Les deux allaient
    # à `haie`, et le dossier s'engageait sur une plantation là où le plan du
    # bureau d'études distingue « à crée » (noir) de « à renforcer » (bleu
    # clair) — relevé sur Gannay.
    "Haie à renforcer": "haie_a_renforcer",
    "Haie existante": "haie_existante",
    # Végétation en place, ajoutée au plan de Bray le 24/09/2026 : une surface
    # dont l'étendue dessinée est l'information. Elle rejoint les houppiers du
    # plan du BE (« PVcase Trees »), que le dossier légende « Arbres existants »
    # et que la coupe DP 3 dessine à hauteur d'arbre.
    "Zone boisée": "arbre_existant",
    "Zone boisée existante": "arbre_existant",
    "Boisement existant": "arbre_existant",
    "Arbres existants": "arbre_existant",
    "Poste combiné de Livraison/transformation": "pdl_ptr",
    "Poste de Livraison/transfo": "pdl_ptr",
    # Relevé sur Lachapelle-sous-Aubenas le 30/09/2026 : le poste n'était pas
    # importé du tout, faute de cette graphie. « Local de stockage BESS », de
    # la même légende, reste à trancher — il peut désigner le conteneur de
    # batteries comme l'abri qui le couvre, et l'écran de correspondance est
    # là pour ça.
    "Poste de Livraison/Transformation": "pdl_ptr",
    "Poste de livraison et de transformation": "pdl_ptr",
    "Poste de livraison": "pdl",
    "Poste de transformation": "ptr",
    "Réserve incendie": "bache_incendie",
    "Citerne incendie": "bache_incendie",
    "Citerne de refroidissement": "citerne_refroidissement",
    "Local technique": "local_technique",
    "BESS": "bess",
    "Batterie de stockage": "bess",
    "Bac de rétention": "bac_retention",
    "Bac de rétention des eaux": "bac_retention",
    "Bac de récupération des eaux": "bac_retention",
    # Le béton en place, quand la légende du plan PDF le nomme. Traçé et
    # élargi comme une piste : c'est une voie, dont le plan donne le fil.
    "Chemin existant": "chemin_existant",
    "Piste lourde existante": "piste_lourde_existante",
    "Piste lourde à créer": "piste_lourde_a_creer",
    "Piste légère": "piste_legere",
    # Instruction du chef de projet du 24/09/2026 : la plateforme existante se
    # matérialise comme de la piste lourde. À Bray, trois de ses formes sont des
    # bandes de piste, la quatrième une surface de 2 331 m², gardée telle que
    # dessinée (voir `EPAISSEUR_SURFACE_M`).
    "Plateforme existante": "piste_lourde_existante",
}

#: Libellés dont on sait qu'ils ne se rattachent à rien sans décision : ils ne
#: disent pas si la piste est lourde ou légère, comme le calque
#: « UNI_VRD_Voirie » du BE. Relevés sur le plan de Bray-Saint-Aignan.
LIBELLES_A_TRANCHER = {
    "Piste existante": "le libellé ne dit pas si la piste est lourde ou légère",
    "Piste à créer": "le libellé ne dit pas si la piste est lourde ou légère",
}

_CORRESPONDANCE_NORMALISEE = {
    normaliser(libelle): categorie for libelle, categorie in CORRESPONDANCE_LEGENDE.items()
}
_A_TRANCHER_NORMALISES = {
    normaliser(libelle): motif for libelle, motif in LIBELLES_A_TRANCHER.items()
}

#: Catégories dont la géométrie du plan est signifiante : on garde le tracé
#: (décision D2). À Gannay la clôture fait 180 points pour 684 m.
CATEGORIES_TRACEES = (
    "cloture",
    "haie",
    "haie_existante",
    "haie_a_renforcer",
    "chemin_existant",
    "piste_lourde_existante",
    "piste_lourde_a_creer",
    "piste_lourde",
    "piste_legere",
    "voirie",
)

#: Catégories tracées qui sont des pistes : le plan en donne le tracé et le
#: type, et `pistes.py` en fait une piste de 5 m aux virages arrondis
#: (instruction du chef de projet du 23/09/2026).
CATEGORIES_PISTES = (
    "chemin_existant",
    "piste_lourde_existante",
    "piste_lourde_a_creer",
    "piste_lourde",
    "piste_legere",
)

#: Catégories dont le plan ne donne que la position et l'orientation : leurs
#: formes ne sont pas à l'échelle (instruction du chef de projet du 21/09/2026,
#: décision D2), et leurs dimensions viennent des gabarits UNITe.
CATEGORIES_OUVRAGES = (
    "portail",
    "pdl_ptr",
    "ptr",
    "pdl",
    "bache_incendie",
    "citerne_refroidissement",
    "local_technique",
    "bess",
    "bac_retention",
)

#: Épaisseur moyenne — deux fois l'aire sur le périmètre — au delà de laquelle
#: une forme de piste est une surface, gardée telle que dessinée, et non un
#: trait dont on tire l'axe : réduite à un axe, elle deviendrait une bande de
#: 5 m. Mesuré le 24/09/2026 à Bray : les pistes et trois des plateformes
#: existantes font 4,3 m d'épaisseur, la quatrième plateforme 99 × 39 m.
EPAISSEUR_SURFACE_M = 1.5 * LARGEUR_PISTE_M

#: Catégories dont le plan donne la surface telle qu'elle est dessinée : de la
#: végétation en place, dont l'étendue est l'information — ni un trait dont on
#: garde l'axe, ni un ouvrage aux cotes du catalogue. Le bois de Bray est ainsi
#: tracé à main levée sur la copie d'écran HelioScope (plan du 24/09/2026).
CATEGORIES_SURFACES = ("arbre_existant", "espace_vert")

#: Ce qu'un plan PDF sait importer. Une autre catégorie du contrat, appariée à
#: la main, ne sortirait pas du plan : la zone boisée de Bray, appariée aux
#: arbres existants avant qu'ils ne s'importent, disparaissait ainsi sans un
#: mot (24/09/2026). L'application ne propose donc que celles-ci, et
#: `construire` dit ce qu'il laisse de côté si on lui en passe une autre.
CATEGORIES_IMPORTABLES = CATEGORIES_TRACEES + CATEGORIES_OUVRAGES + CATEGORIES_SURFACES

#: Ce que la légende doit porter pour que le plan serve à quelque chose. Sans
#: clôture, le plan ne délimite pas le projet : la version du 28/08/2026 du
#: plan de Gannay est dans ce cas, et c'est bien une version antérieure, pas
#: un plan à lire tel quel.
CATEGORIES_ATTENDUES = ("cloture",)


#: Une cote écrite dans un libellé de légende. Instruction du chef de projet du
#: 23/09/2026 : le volume d'une réserve incendie et la largeur d'un portail se
#: portent en légende — « Réserve incendie 120 m³ », « Portail 7 m » —, et le
#: plan les donne alors lui-même. Un volume s'écrit en m³ ou m3, une largeur en
#: m ; un « m² » n'est ni l'un ni l'autre.
_COTE_EN_LEGENDE = re.compile(
    r"\s*[(\-–—:,]?\s*(?:(?:de|l\s*=)\s*)?(\d+(?:[.,]\d+)?)\s*(m\s*[3³]|m)(?![\w²])\s*\)?",
    re.IGNORECASE,
)


def _sans_cote(libelle: str) -> tuple[float | None, str | None, str]:
    """La cote qu'un libellé porte, son unité (« m3 » ou « m »), et le libellé sans elle."""
    trouve = _COTE_EN_LEGENDE.search(libelle)
    if trouve is None:
        return None, None, libelle
    valeur = float(trouve.group(1).replace(",", "."))
    unite = "m" if trouve.group(2).lower() == "m" else "m3"
    reste = (libelle[: trouve.start()] + " " + libelle[trouve.end() :]).strip(" -–—:,")
    return valeur, unite, " ".join(reste.split())


def categorie_proposee(libelle: str) -> str | None:
    """Catégorie proposée pour un libellé de légende, ou None s'il est inconnu.

    La cote qu'il porte n'y entre pas : « Réserve incendie 120 m³ » est une
    réserve incendie.
    """
    return _CORRESPONDANCE_NORMALISEE.get(normaliser(_sans_cote(libelle)[2]))


def motif_a_trancher(libelle: str) -> str | None:
    """Raison pour laquelle un libellé connu ne se rattache à rien d'office."""
    return _A_TRANCHER_NORMALISES.get(normaliser(_sans_cote(libelle)[2]))


def cote_lue(libelle: str, categorie: str | None) -> dict:
    """Ce qu'un libellé de légende dit des dimensions de son ouvrage.

    Un volume pour une réserve incendie, une largeur pour un portail : ce sont
    les deux dimensions que les gabarits UNITe ne tranchent pas.
    """
    valeur, unite, _ = _sans_cote(libelle)
    if valeur is None:
        return {}
    if categorie == "bache_incendie" and unite == "m3":
        return {"volume_citerne_m3": int(valeur) if valeur.is_integer() else valeur}
    if categorie == "portail" and unite == "m":
        return {"largeur_portail_m": valeur}
    return {}


# ---------------------------------------------------------------------------
# Constantes de lecture, toutes mesurées le 23/09/2026 sur Gannay et Bray
# ---------------------------------------------------------------------------

#: Résolution de référence du brief, pour dire l'échelle du plan dans son
#: unité : le prototype rendait la page à 300 dpi et y mesurait 0,1531 m/px.
DPI_REFERENCE = 300.0

#: Distance maximale entre une pastille et le libellé qu'elle précède, en pt :
#: 8,8 à Gannay, de 5 à 10 à Bray.
ECART_PASTILLE_LIBELLE_PT = 20.0

#: Plus grande dimension d'une pastille, en pt. La plus grande mesurée est le
#: trait de clôture de Bray, 25,6 pt.
TAILLE_PASTILLE_MAX_PT = 40.0

#: Distance de couleur — euclidienne, sur les composantes RGB de 0 à 255 — au
#: delà de laquelle un tracé n'est rattaché à aucune pastille. Le plan ne
#: reprend pas toujours la couleur exacte de sa légende : l'orangé des pistes à
#: créer de Gannay est (237, 125, 49) sur la carte et (244, 99, 34) sur la
#: pastille, soit 30,8.
ECART_COULEUR_MAX = 60.0

#: Le plus proche doit l'être nettement plus que le suivant. À Bray, le local
#: technique (255, 0, 0) est à 46,9 de la clôture (231, 18, 36) : seule la
#: couleur exacte les sépare, et un rapport de 0,6 laisse passer l'orangé de
#: Gannay (30,8 contre plus de 200 pour le suivant).
RAPPORT_COULEUR_MAX = 0.6

#: Deux pastilles plus proches que ceci d'un tracé sont à égalité de couleur,
#: et ce sont le liseré et le motif qui les départagent. À Bray, la citerne
#: incendie et la citerne de refroidissement portent le même cyan
#: (0, 176, 240) : seul le liseré noir de la seconde les distingue. À Gannay, la
#: clôture et le portail portent le même magenta, en points pour l'une, en
#: ellipse cernée pour l'autre.
EGALITE_COULEUR = 12.0

#: Allongement — grand côté sur petit côté du rectangle minimal — à partir
#: duquel une pastille figure un trait, et une forme de la carte en est un.
#: Une pastille est une icône courte : la barre de « Piste existante » de Bray
#: est à 2,9, la tache de « Plateforme existante » à 1,0. Sur la carte, les
#: bandes de piste passent 50, la plateforme de 99 × 39 m reste à 2,5.
ALLONGEMENT_PASTILLE_TRAIT = 2.0
ALLONGEMENT_FORME_TRAIT = 4.0

#: Recouvrement au delà duquel deux tracés superposés sont une même forme —
#: un remplissage et son liseré, que PowerPoint écrit l'un après l'autre.
RECOUVREMENT_LISERE = 0.6

#: Nombre de points par segment de Bézier aplati. Les courbes du plan sont des
#: ellipses de pastille, des bouts de capsule et des cercles de piste : douze
#: points suffisent à les suivre au dixième de point.
POINTS_PAR_BEZIER = 12

#: Teinte des tables sur une copie d'écran HelioScope, en degrés. Mesurée sur
#: l'image intégrée des deux plans : 237 à 246° à Gannay (5e et 95e centiles),
#: 230 à 250° à Bray — le bleu-violet des modules HelioScope. Le logo UNITe,
#: pris dans la même image, est à 203° : il en sort. C'est la couleur d'un
#: logiciel, pas celle d'une légende, et aucune pastille ne la porte.
TEINTE_TABLES_DEG = (225.0, 262.0)
SATURATION_TABLES_MIN = 0.25
VALEUR_TABLES_MIN = 0.20

#: Recouvrement des tables attendu d'une copie d'écran fine (décision D7).
#: Mesuré à Gannay : 88,3 % sur le rendu à 300 dpi du prototype. En deçà, le
#: calage n'est plus refusé mais signalé : voir `ECART_RANGEES_MAX`.
RECOUVREMENT_MIN = 0.70

#: Écart admis entre le nombre de rangées du plan et celui du DXF.
#:
#: C'est **ce compte-là** qui dit qu'un plan a bien été dressé sur ce
#: calepinage, et non le recouvrement : mesuré le 29/09/2026, 16 rangées
#: contre 16 à Gannay, 35 contre 35 à Saint-Aubin-sur-Loire. Le recouvrement
#: de Jaccard, lui, dépend de la finesse de la copie d'écran : sur des barres
#: de quatre pixels, un demi-pixel de décalage coûte un quart de l'union, et
#: Saint-Aubin plafonnait à 52 % avec un calage juste et 35 rangées sur 35.
#: Un seuil de recouvrement refusait donc un plan correct parce que sa copie
#: d'écran était grossière.
#:
#: 1 : une rangée d'un bout peut passer sous la légende ou sortir du cadre.
#: Au-delà, ce n'est plus le même calepinage.
ECART_RANGEES_MAX = 1

#: Plancher de recouvrement, sous lequel la direction est peut-être bonne mais
#: la place ne l'est pas. Il ne juge plus la finesse de l'image, seulement
#: l'aberration : un calage posé à côté tombe à quelques pour cent.
RECOUVREMENT_PLANCHER = 0.25

#: Part minimale des tables du plan qui doivent tomber sur une table du DXF,
#: à un pixel près.
#:
#: C'est la mesure qui dit qu'un plan a bien été dressé sur ce calepinage, là
#: où le recouvrement de Jaccard n'y arrive pas. Mesuré le 30/09/2026 sur
#: trois cas :
#:
#: | cas                              | Jaccard | cette mesure |
#: |----------------------------------|---------|--------------|
#: | Gannay, plan et DXF concordants  |  95,4 % |      100,0 % |
#: | Saint-Aubin, copie d'écran fruste |  52,2 % |       92,5 % |
#: | Gannay, une table sur deux ôtée   |  52,1 % |       56,8 % |
#:
#: Le Jaccard ne sépare pas les deux derniers — 52,2 contre 52,1 — parce
#: qu'il compte l'épaisseur des barres autant que leur place : sur une copie
#: d'écran où les rangées font quatre pixels, un demi-pixel de débord coûte un
#: quart de l'union. La tolérance d'un pixel absorbe ce débord et ne comble
#: pas l'absence d'une table entière, qui fait dix pixels.
FIDELITE_MIN = 0.75

#: Écart admis entre l'échelle mesurée sur le pas des rangées et celle qu'implique
#: l'emprise des tables, dans chacune des deux directions (décision D7). Une
#: copie d'écran étirée d'un seul côté dans PowerPoint donne un plan
#: anisotrope, que le pas seul ne verrait pas.
TOLERANCE_ECHELLE = 0.02

#: Densité minimale d'une case du profil pour que l'emprise du plan s'y arrête,
#: en part de la case médiane.
#:
#: 5 % : mesuré le 01/10/2026 sur Lachapelle-sous-Aubenas, dont la photo
#: aérienne porte du terrain nu à la teinte des tables — 142 pixels épars sur
#: 442 103, en traînée de 4,4 m au bout des rangées. Pris au minimum et au
#: maximum, ils allongeaient l'emprise de 3,1 % et faisaient refuser un plan
#: juste, calé à 99,9 % sur 17 rangées contre 17. Les cases du champ en portent
#: 40 et plus, la traînée 3 à 4 : l'écart tombe à 0,2 %. À 10 % le champ même
#: est rogné (+5,4 % à Lachapelle), à 20 % Gannay se perd (+7,6 %) ; à 5 %,
#: Gannay ne bouge pas (+0,19 % contre +0,04 %).
PART_BORD_MIN = 0.05

#: Nombre de cases sur lesquelles le profil est lissé avant d'y chercher le
#: bord du champ : une table fait au moins un demi-mètre de profondeur, cinq
#: pixels à 300 dpi, et du bruit n'en fait pas.
LARGEUR_LISSAGE_BORD = 5


# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Trace:
    """Un chemin vectoriel de la page, en points PDF, ordonnée vers le haut."""

    rang: int
    #: Couleurs RGB 0-255 du remplissage et du trait, ou None si le chemin
    #: n'est pas rempli, ou pas tracé. PDFium rend la couleur de l'état
    #: graphique même quand elle ne sert pas : seul le mode de dessin fait foi.
    remplissage: tuple | None
    trait: tuple | None
    epaisseur_pt: float
    #: Sous-chemins aplatis, chacun une suite de points, et s'il est fermé.
    sous_chemins: tuple
    fermes: tuple
    courbe: bool

    @property
    def bornes(self) -> tuple[float, float, float, float]:
        xs = [x for chemin in self.sous_chemins for x, _ in chemin]
        ys = [y for chemin in self.sous_chemins for _, y in chemin]
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class Objet:
    """Une forme du plan : un tracé, et son liseré quand il en a un."""

    traces: list
    #: Couleur qui fait la forme : le remplissage s'il y en a un, sinon le trait.
    couleur: tuple
    #: « aplat » pour une forme remplie, « trait » pour un chemin seulement tracé.
    nature: str
    #: Couleur du liseré qui cerne un aplat, ou None.
    lisere: tuple | None
    #: « pointille » quand l'aplat est fait de petites formes répétées — les
    #: points de la clôture de Gannay —, « plein » sinon.
    motif: str

    @property
    def bornes(self) -> tuple[float, float, float, float]:
        tous = [t.bornes for t in self.traces]
        return (
            min(b[0] for b in tous),
            min(b[1] for b in tous),
            max(b[2] for b in tous),
            max(b[3] for b in tous),
        )

    @property
    def principal(self) -> Trace:
        return self.traces[0]


@dataclass(frozen=True)
class LigneTexte:
    """Une ligne de texte de la page, fragments recollés."""

    texte: str
    bornes: tuple[float, float, float, float]

    @property
    def hauteur(self) -> float:
        return self.bornes[3] - self.bornes[1]

    @property
    def milieu_y(self) -> float:
        return (self.bornes[1] + self.bornes[3]) / 2


@dataclass
class EntreeLegende:
    """Une entrée de la légende : un libellé, et la pastille qui le précède."""

    libelle: str
    pastille: Objet
    categorie: str | None
    #: Pourquoi le libellé ne se rattache à rien d'office, quand il est connu.
    a_trancher: str | None = None

    @property
    def couleur(self) -> tuple:
        return self.pastille.couleur


@dataclass
class ElementPlan:
    """Une forme de la carte, rattachée à une entrée de la légende."""

    entree: EntreeLegende
    objet: Objet

    @property
    def categorie(self) -> str | None:
        return self.entree.categorie


@dataclass
class ImageDeFond:
    """La copie d'écran HelioScope : ses pixels, et où elle est posée."""

    pixels: np.ndarray
    #: Matrice PDF de l'image (a, b, c, d, e, f) : le carré unité de l'image
    #: vers la page, la première ligne de pixels en haut.
    matrice: tuple

    @property
    def taille(self) -> tuple[int, int]:
        return self.pixels.shape[1], self.pixels.shape[0]

    def vers_page(self, colonnes, lignes):
        """Centres de pixels (colonne, ligne) vers la page, en points."""
        largeur, hauteur = self.taille
        a, b, c, d, e, f = self.matrice
        u = (np.asarray(colonnes, float) + 0.5) / largeur
        v = 1.0 - (np.asarray(lignes, float) + 0.5) / hauteur
        return a * u + c * v + e, b * u + d * v + f

    def vers_pixels(self, x, y):
        """Points de la page vers l'image, en pixels (colonne, ligne) continus."""
        largeur, hauteur = self.taille
        a, b, c, d, e, f = self.matrice
        determinant = a * d - b * c
        dx, dy = np.asarray(x, float) - e, np.asarray(y, float) - f
        u = (d * dx - c * dy) / determinant
        v = (-b * dx + a * dy) / determinant
        return u * largeur, (1.0 - v) * hauteur

    @property
    def cadre(self) -> tuple[float, float, float, float]:
        largeur, hauteur = self.taille
        xs, ys = self.vers_page([-0.5, largeur - 0.5, -0.5, largeur - 0.5],
                                [-0.5, -0.5, hauteur - 0.5, hauteur - 0.5])
        return (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))


@dataclass
class PlanPDF:
    """Ce que le plan PDF dit, en points de la page. Rien n'y est encore calé."""

    source: str
    #: Rang de la page lue, à partir de 1 comme l'affiche une visionneuse.
    page: int
    legende: list
    elements: list
    fond: ImageDeFond
    #: Formes de la carte qu'aucune pastille n'explique : signalées, jamais
    #: rangées au hasard.
    non_reconnus: list = field(default_factory=list)
    avertissements: list = field(default_factory=list)
    #: Ce que le tableau d'informations du plan déclare, quand il en porte un :
    #: clé de `INFORMATIONS_DU_PLAN` → valeur, et le texte d'où elle vient.
    informations: dict = field(default_factory=dict)

    def entree(self, categorie: str) -> list:
        return [e for e in self.legende if e.categorie == categorie]

    def elements_de(self, categorie: str) -> list:
        return [e for e in self.elements if e.categorie == categorie]

    @property
    def correspondance(self) -> dict:
        """Libellé de légende → catégorie retenue, pour le contrat."""
        return {e.libelle: e.categorie for e in self.legende}


# ---------------------------------------------------------------------------
# Lecture de la page
# ---------------------------------------------------------------------------


def _pdfium():
    """PDFium, importé à la demande : le reste du générateur n'en a pas besoin."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as brut

    return pdfium, brut


def _ouvrir(chemin: Path):
    pdfium, _ = _pdfium()
    if not chemin.exists():
        raise ErreurPlanPDF(f"Plan PDF introuvable : {chemin}")
    try:
        return pdfium.PdfDocument(str(chemin))
    except Exception as exc:  # noqa: BLE001 - remonté en erreur nommée
        raise ErreurPlanPDF(
            f"« {chemin.name} » n'est pas un PDF lisible ({exc}). S'il est "
            "protégé par un mot de passe, exportez-le à nouveau sans protection."
        ) from exc


def _matrice(objet) -> tuple:
    """Matrice complète d'un objet de page, formulaires englobants compris."""
    m = objet.get_matrix().get()
    conteneur = objet.container
    while conteneur is not None:
        a1, b1, c1, d1, e1, f1 = m
        a2, b2, c2, d2, e2, f2 = conteneur.get_matrix().get()
        m = (
            a1 * a2 + b1 * c2,
            a1 * b2 + b1 * d2,
            c1 * a2 + d1 * c2,
            c1 * b2 + d1 * d2,
            e1 * a2 + f1 * c2 + e2,
            e1 * b2 + f1 * d2 + f2,
        )
        conteneur = conteneur.container
    return m


def _appliquer(m: tuple, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = m
    return (a * x + c * y + e, b * x + d * y + f)


def _couleur(fonction, objet_brut) -> tuple | None:
    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    if not fonction(objet_brut, r, g, b, a):
        return None
    if a.value == 0:
        # Une couleur entièrement transparente ne dessine rien.
        return None
    return (r.value, g.value, b.value)


def _bezier(p0, p1, p2, p3, n: int = POINTS_PAR_BEZIER):
    points = []
    for i in range(1, n + 1):
        t = i / n
        u = 1.0 - t
        points.append(
            (
                u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
            )
        )
    return points


def _trace(objet, rang: int) -> Trace | None:
    """Un chemin de la page, aplati et ramené en points de la page."""
    _, brut = _pdfium()
    raw = objet.raw
    mode, trace_actif = ctypes.c_int(), ctypes.c_int()
    if not brut.FPDFPath_GetDrawMode(raw, mode, trace_actif):
        return None
    remplissage = (
        _couleur(brut.FPDFPageObj_GetFillColor, raw) if mode.value != 0 else None
    )
    trait = (
        _couleur(brut.FPDFPageObj_GetStrokeColor, raw) if trace_actif.value else None
    )
    if remplissage is None and trait is None:
        return None
    epaisseur = ctypes.c_float(0.0)
    brut.FPDFPageObj_GetStrokeWidth(raw, epaisseur)
    matrice = _matrice(objet)

    chemins, fermes = [], []
    courant: list = []
    ferme = False
    bezier: list = []
    courbe = False
    x, y = ctypes.c_float(), ctypes.c_float()
    for indice in range(brut.FPDFPath_CountSegments(raw)):
        segment = brut.FPDFPath_GetPathSegment(raw, indice)
        brut.FPDFPathSegment_GetPoint(segment, x, y)
        point = _appliquer(matrice, x.value, y.value)
        nature = brut.FPDFPathSegment_GetType(segment)
        if nature == brut.FPDF_SEGMENT_MOVETO:
            if len(courant) >= 2:
                chemins.append(tuple(courant))
                fermes.append(ferme)
            courant, ferme, bezier = [point], False, []
        elif nature == brut.FPDF_SEGMENT_BEZIERTO:
            courbe = True
            bezier.append(point)
            if len(bezier) == 3:
                depart = courant[-1] if courant else point
                courant.extend(_bezier(depart, *bezier))
                bezier = []
        else:
            courant.append(point)
        if brut.FPDFPathSegment_GetClose(segment):
            ferme = True
    if len(courant) >= 2:
        chemins.append(tuple(courant))
        fermes.append(ferme)
    if not chemins:
        return None
    # Un contour fermé dont le dernier point retombe sur le premier est fermé,
    # que l'export l'ait marqué ou non.
    fermes = [
        f or math.dist(c[0], c[-1]) < 1e-3 for c, f in zip(chemins, fermes)
    ]
    return Trace(
        rang=rang,
        remplissage=remplissage,
        trait=trait,
        epaisseur_pt=float(epaisseur.value) * _facteur_lineaire(matrice),
        sous_chemins=tuple(chemins),
        fermes=tuple(fermes),
        courbe=courbe,
    )


def _facteur_lineaire(m: tuple) -> float:
    a, b, c, d, _, _ = m
    return math.sqrt(abs(a * d - b * c))


def _objets_de_page(page):
    """Chemins et images d'une page, formulaires compris, en points de page."""
    _, brut = _pdfium()
    traces, images = [], []
    for rang, objet in enumerate(page.get_objects()):
        if objet.type == brut.FPDF_PAGEOBJ_PATH:
            trace = _trace(objet, rang)
            if trace is not None:
                traces.append(trace)
        elif objet.type == brut.FPDF_PAGEOBJ_IMAGE:
            images.append(objet)
    return traces, images


def _lignes_de_texte(page) -> list[LigneTexte]:
    """Lignes de texte de la page, fragments d'une même ligne recollés.

    PDFium rend le texte par fragments, et un même libellé en fait plusieurs :
    sur le plan de Bray « Portai » et « l », « Citerne » et « Incendie »,
    « Citerne de refroidissemen » et « t ». Deux fragments sont d'une même
    ligne quand ils sont sur la même hauteur et se touchent presque.

    Les fragments se regroupent d'abord par hauteur, puis se lisent de gauche à
    droite. Les trier sur leur seule hauteur mettait « de Transformation »,
    posé 0,1 pt plus haut, devant « Poste » : le libellé sortait coupé en deux.
    """
    textes = page.get_textpage()
    fragments = []
    for indice in range(textes.count_rects()):
        gauche, bas, droite, haut = textes.get_rect(indice)
        texte = textes.get_text_bounded(gauche, bas, droite, haut)
        if texte.strip():
            fragments.append((texte, (gauche, bas, droite, haut)))
    fragments.sort(key=lambda f: -(f[1][1] + f[1][3]) / 2)

    rangs: list[list] = []
    for fragment in fragments:
        bornes = fragment[1]
        milieu = (bornes[1] + bornes[3]) / 2
        if rangs:
            premier = rangs[-1][0][1]
            h = max(bornes[3] - bornes[1], premier[3] - premier[1])
            if abs(milieu - (premier[1] + premier[3]) / 2) < 0.35 * h:
                rangs[-1].append(fragment)
                continue
        rangs.append([fragment])

    lignes: list[list] = []
    for rang in rangs:
        rang.sort(key=lambda f: f[1][0])
        lignes.append([rang[0]])
        for texte, bornes in rang[1:]:
            dernier = lignes[-1][-1][1]
            h = max(bornes[3] - bornes[1], dernier[3] - dernier[1])
            if -0.5 * h <= bornes[0] - dernier[2] < 1.0 * h:
                lignes[-1].append((texte, bornes))
            else:
                lignes.append([(texte, bornes)])

    resultat = []
    for ligne in lignes:
        morceaux = [ligne[0][0]]
        for (_, precedent), (texte, bornes) in zip(ligne, ligne[1:]):
            h = bornes[3] - bornes[1]
            colle = bornes[0] - precedent[2] < 0.25 * h
            morceaux.append(texte if colle else " " + texte)
        resultat.append(
            LigneTexte(
                texte=" ".join("".join(morceaux).split()),
                bornes=(
                    min(b[0] for _, b in ligne),
                    min(b[1] for _, b in ligne),
                    max(b[2] for _, b in ligne),
                    max(b[3] for _, b in ligne),
                ),
            )
        )
    return resultat


# ---------------------------------------------------------------------------
# Formes : regrouper, caractériser, comparer
# ---------------------------------------------------------------------------


def _surface_bornes(b) -> float:
    return max(b[2] - b[0], 0.0) * max(b[3] - b[1], 0.0)


def _recouvrement(b1, b2) -> float:
    """Intersection sur la plus petite des deux boîtes, entre 0 et 1."""
    inter = (
        max(0.0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
        * max(0.0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
    )
    petite = min(_surface_bornes(b1), _surface_bornes(b2))
    if petite <= 0:
        # Une forme plate — un trait horizontal — n'a pas de surface : on la
        # compare sur sa longueur.
        return 1.0 if inter > 0 or _contient(b1, b2) or _contient(b2, b1) else 0.0
    return inter / petite


def _contient(grande, petite, jeu: float = 1.0) -> bool:
    return (
        grande[0] - jeu <= petite[0]
        and grande[1] - jeu <= petite[1]
        and petite[2] <= grande[2] + jeu
        and petite[3] <= grande[3] + jeu
    )


def _motif(trace: Trace) -> str:
    """« pointille » quand l'aplat est fait de petites formes répétées."""
    fermes = [c for c, f in zip(trace.sous_chemins, trace.fermes) if f]
    if trace.remplissage is None or len(fermes) < 2:
        return "plein"
    tailles = [
        max(max(x for x, _ in c) - min(x for x, _ in c), max(y for _, y in c) - min(y for _, y in c))
        for c in fermes
    ]
    b = trace.bornes
    etendue = max(b[2] - b[0], b[3] - b[1])
    return "pointille" if max(tailles) < 0.5 * etendue else "plein"


def _grouper_en_objets(traces: list[Trace]) -> list[Objet]:
    """Rassemble un remplissage et le liseré qui le cerne en une seule forme.

    PowerPoint écrit une forme cernée en deux chemins consécutifs : l'aplat,
    puis son contour. Les comparer séparément à la légende confondrait la
    citerne incendie de Bray, cyan, avec sa citerne de refroidissement, cyan
    cernée de noir.
    """
    objets: list[Objet] = []
    pris = set()
    for i, trace in enumerate(traces):
        if i in pris:
            continue
        pris.add(i)
        lisere = None
        membres = [trace]
        if trace.remplissage is not None:
            if trace.trait is not None and trace.trait != trace.remplissage:
                lisere = trace.trait
            for j in (i + 1, i + 2):
                if j >= len(traces) or j in pris:
                    continue
                suivant = traces[j]
                if (
                    suivant.remplissage is None
                    and suivant.trait is not None
                    and _recouvrement(trace.bornes, suivant.bornes) >= RECOUVREMENT_LISERE
                    and _contient(suivant.bornes, trace.bornes, jeu=suivant.epaisseur_pt + 1.0)
                ):
                    membres.append(suivant)
                    pris.add(j)
                    if suivant.trait != trace.remplissage:
                        lisere = suivant.trait
                    break
            objets.append(Objet(membres, trace.remplissage, "aplat", lisere, _motif(trace)))
        else:
            objets.append(Objet(membres, trace.trait, "trait", None, "plein"))
    return objets


def _distance(c1: tuple, c2: tuple) -> float:
    return math.dist(c1, c2)


# ---------------------------------------------------------------------------
# Légende
# ---------------------------------------------------------------------------


def _legende(objets: list[Objet], lignes: list[LigneTexte]) -> list[EntreeLegende]:
    """Les entrées de la légende : chaque pastille, et le libellé qui la suit.

    La pastille se reconnaît à sa place, pas à sa forme : une petite forme dont
    un texte commence juste à droite, à sa hauteur. Un libellé sur deux lignes
    — « Poste combiné de » et « Livraison/transformation » à Gannay — se
    recolle : chaque ligne va à la pastille la plus proche en hauteur, et la
    pastille de ce poste est centrée entre ses deux lignes.
    """
    candidates = []
    for objet in objets:
        b = objet.bornes
        if max(b[2] - b[0], b[3] - b[1]) > TAILLE_PASTILLE_MAX_PT:
            continue
        milieu = (b[1] + b[3]) / 2
        voisines = [
            ligne
            for ligne in lignes
            if 0.0 <= ligne.bornes[0] - b[2] <= ECART_PASTILLE_LIBELLE_PT
            and abs(ligne.milieu_y - milieu) <= max(ligne.hauteur, b[3] - b[1])
        ]
        if voisines:
            candidates.append(objet)

    # Chaque ligne va à la pastille la plus proche en hauteur, parmi celles
    # qu'elle suit de près : c'est ce qui recolle un libellé sur deux lignes.
    attributions: dict[int, list] = {}
    for ligne in lignes:
        meilleure, ecart = None, None
        for rang, objet in enumerate(candidates):
            b = objet.bornes
            if not 0.0 <= ligne.bornes[0] - b[2] <= ECART_PASTILLE_LIBELLE_PT:
                continue
            d = abs(ligne.milieu_y - (b[1] + b[3]) / 2)
            if d <= 1.2 * ligne.hauteur and (ecart is None or d < ecart):
                meilleure, ecart = rang, d
        if meilleure is not None:
            attributions.setdefault(meilleure, []).append(ligne)

    entrees = []
    for rang, objet in enumerate(candidates):
        lignes_de_l_entree = sorted(
            attributions.get(rang, []), key=lambda l: -l.milieu_y
        )
        if not lignes_de_l_entree:
            continue
        libelle = " ".join(" ".join(l.texte for l in lignes_de_l_entree).split())
        entrees.append(
            EntreeLegende(
                libelle=libelle,
                pastille=objet,
                categorie=categorie_proposee(libelle),
                a_trancher=motif_a_trancher(libelle),
            )
        )
    return entrees


def _rattacher(objet: Objet, legende: list[EntreeLegende]) -> tuple[EntreeLegende | None, str]:
    """L'entrée de légende dont cette forme porte la couleur, ou None et pourquoi.

    La couleur décide ; le liseré et le motif départagent deux pastilles de
    même couleur ; une forme qui hésite entre deux couleurs n'est rangée nulle
    part.

    Une forme se range parmi les pastilles de sa nature, aplat ou trait. Si
    aucune n'a sa couleur, elle peut rejoindre une catégorie tracée de l'autre
    nature — clôture, haie, piste —, dont on ne garde que l'axe : PowerPoint
    exporte un même trait en contour rempli ou en trait selon l'outil qui l'a
    dessiné. Le segment qui fermait la clôture de Bray (plan du 24/09/2026),
    une droite, était un trait quand le reste était rempli : refusé, il
    laissait l'enceinte ouverte. Le repli rend alors, en second, ce qu'il faut
    en dire.
    """
    meme_nature = [e for e in legende if e.pastille.nature == objet.nature]
    if any(_distance(objet.couleur, e.pastille.couleur) <= ECART_COULEUR_MAX for e in meme_nature):
        return _choisir(objet, meme_nature)
    tracees = [
        e for e in legende if e.pastille.nature != objet.nature and e.categorie in CATEGORIES_TRACEES
    ]
    repli, _ = _choisir(objet, tracees)
    if repli is not None:
        return repli, (
            f"un {objet.nature} de sa couleur, là où sa pastille est un "
            f"{repli.pastille.nature}, lui est rattaché : on n'en garde que l'axe"
        )
    # La raison d'origine : aucune pastille de sa nature, ou aucune assez proche.
    return _choisir(objet, meme_nature)


def _figure_un_trait(objet: Objet, seuil: float) -> bool:
    """Un trait, ou une forme assez allongée pour en figurer un."""
    if objet.nature == "trait":
        return True
    forme = _polygone_de(objet.principal)
    if forme is None:
        return True
    _, _, longueur, largeur = _rectangle_minimal(forme)
    return largeur <= 0 or longueur / largeur >= seuil


def _pastilles_de_meme_couleur(entrees) -> list[str]:
    """Ce qu'il y a à dire quand deux pastilles portent la même couleur.

    Deux pastilles de la même couleur rendent la carte indéchiffrable : une
    forme qui la porte peut venir de l'une comme de l'autre, et `_choisir` ne
    peut plus trancher que sur l'allure — trait ou aplat. Il se trompe alors
    dès qu'un tracé coude, un morceau de clôture à angle droit ayant une boîte
    englobante carrée.

    Relevé le 30/09/2026 sur Lachapelle-sous-Aubenas, dont la légende donne le
    même orangé à « Clôture » et à « Poste de transformation » : dix-huit
    morceaux de grillage sont sortis en postes de transformation, posés au
    gabarit et éparpillés le long de l'enceinte.

    `entrees` est une suite de (libellé, couleur, catégorie) : la fonction ne
    lit rien d'autre de la légende, et le dire ici permet de la mesurer sans
    fabriquer de fausse pastille.
    """
    par_couleur: dict = {}
    for libelle, couleur, categorie in entrees:
        if categorie is not None:
            par_couleur.setdefault(couleur, []).append(libelle)
    messages = []
    for couleur, libelles in sorted(par_couleur.items()):
        if len(libelles) > 1:
            messages.append(
                f"La légende donne la même couleur {couleur} à "
                f"{len(libelles)} entrées — "
                + " ; ".join(f"« {n} »" for n in sorted(libelles))
                + ". Une forme de la carte qui la porte peut venir de n'importe "
                "laquelle : le rattachement se fait alors sur la seule allure, et "
                "il se trompe dès qu'un tracé coude. Donnez-leur des couleurs "
                "distinctes sur le plan, et refaites l'import."
            )
    return messages


def _conseils_des_libelles_non_rattaches(entrees) -> list[str]:
    """Ce qu'on dit d'un libellé que rien ne rattache, et qui soit praticable.

    « Appariez-le à la main » ne vaut que si la couleur de l'entrée n'appartient
    qu'à elle : les formes de la carte se rattachent par la couleur, et deux
    entrées de la même teinte ne se départagent plus.

    Mesuré le 01/10/2026 sur Saint-Aubin-sur-Loire : trois entrées — « Clôture »,
    « PDL /PTR » et « Portail d'accès » — portent le même rouge, et les deux
    dernières ne sont rattachées à rien. Suivi, le conseil aurait donné au poste
    de livraison les morceaux de clôture : le défaut même qui avait sorti
    dix-huit bouts de grillage en postes de transformation à Lachapelle.

    `entrees` est une suite de (libellé, couleur, catégorie, à trancher) : la
    fonction ne lit rien d'autre de la légende, et le dire ici permet de la
    mesurer sans fabriquer de fausse pastille.
    """
    messages = []
    for libelle, couleur, categorie, a_trancher in entrees:
        if categorie is not None:
            continue
        voisines = sorted(
            autre
            for autre, teinte, _, _ in entrees
            if autre != libelle and teinte == couleur
        )
        if voisines:
            messages.append(
                f"Libellé de légende « {libelle} » non rattaché, et sa couleur "
                f"{couleur} est aussi celle de "
                + " ; ".join(f"« {n} »" for n in voisines)
                + ". L'apparier à la main ne suffirait pas — les formes se "
                "rattachent par la couleur, et l'outil ne saurait pas de "
                "laquelle elles viennent. Donnez-lui une couleur propre sur le "
                "plan, et refaites l'import."
            )
            continue
        messages.append(
            f"Libellé de légende « {libelle} » "
            + (
                f"non rattaché : {a_trancher}. Appariez-le à la main."
                if a_trancher
                else "inconnu : ses formes ne sont pas importées. "
                "Appariez-le à la main s'il désigne un ouvrage du projet."
            )
        )
    return messages


def _choisir(objet: Objet, legende: list[EntreeLegende]) -> tuple[EntreeLegende | None, str]:
    """Parmi ces entrées, celle dont la forme porte la couleur, ou None et pourquoi."""
    candidates = [(_distance(objet.couleur, e.pastille.couleur), e) for e in legende]
    if not candidates:
        return None, "aucune pastille de même nature (aplat ou trait)"
    candidates.sort(key=lambda c: c[0])
    meilleure = candidates[0][0]
    if meilleure > ECART_COULEUR_MAX:
        return None, (
            f"couleur {objet.couleur} à {meilleure:.0f} de la plus proche pastille "
            f"(« {candidates[0][1].libelle} ») ; au delà de {ECART_COULEUR_MAX:.0f}, "
            "elle n'est rattachée à rien"
        )
    egales = [e for d, e in candidates if d - meilleure <= EGALITE_COULEUR]
    suivantes = [d for d, _ in candidates if d - meilleure > EGALITE_COULEUR]
    if suivantes and meilleure > RAPPORT_COULEUR_MAX * suivantes[0]:
        return None, (
            f"couleur {objet.couleur} entre deux pastilles, à {meilleure:.0f} et "
            f"{suivantes[0]:.0f} : elle n'est rangée ni dans l'une ni dans l'autre"
        )
    if len(egales) == 1:
        return egales[0], ""

    def desaccord(entree: EntreeLegende) -> int:
        pastille = entree.pastille
        ecarts = 0
        if (pastille.lisere is None) != (objet.lisere is None):
            ecarts += 1
        elif pastille.lisere is not None and _distance(pastille.lisere, objet.lisere) > ECART_COULEUR_MAX:
            ecarts += 1
        if pastille.motif != objet.motif:
            ecarts += 1
        # Une bande n'est pas une surface, et cela pèse plus qu'un liseré, qui
        # s'oublie : à Bray, la piste existante est dessinée sans le liseré
        # gris de sa pastille, et ses bandes allaient à « Plateforme
        # existante », de même vert, sans liseré mais figurée d'une tache.
        if _figure_un_trait(pastille, ALLONGEMENT_PASTILLE_TRAIT) != _figure_un_trait(
            objet, ALLONGEMENT_FORME_TRAIT
        ):
            ecarts += 2
        return ecarts

    notes = sorted((desaccord(e), e.libelle, e) for e in egales)
    if notes[0][0] == notes[1][0]:
        return None, (
            f"même couleur, même liseré et même motif que les pastilles "
            f"« {notes[0][1]} » et « {notes[1][1]} » : impossible de choisir"
        )
    return notes[0][2], ""


# ---------------------------------------------------------------------------
# Image de fond et tables
# ---------------------------------------------------------------------------


def _image_de_fond(images, page_numero: int, source: str) -> ImageDeFond:
    """La plus grande image de la page : la copie d'écran qui porte les tables."""
    if not images:
        raise ErreurPlanPDF(
            f"La page {page_numero} de « {source} » ne porte aucune image : les "
            "tables se relèvent sur la copie d'écran HelioScope, et sans elles "
            "il n'y a pas d'échelle à mesurer (décision D3)."
        )

    def aire(objet) -> float:
        m = _matrice(objet)
        return abs(m[0] * m[3] - m[1] * m[2])

    objet = max(images, key=aire)
    try:
        pixels = np.asarray(objet.get_bitmap(render=False).to_pil().convert("RGB"))
    except Exception as exc:  # noqa: BLE001 - remonté en erreur nommée
        raise ErreurPlanPDF(
            f"L'image de fond de « {source} » ne se décode pas ({exc})."
        ) from exc
    return ImageDeFond(pixels=pixels, matrice=_matrice(objet))


def masque_des_tables(fond: ImageDeFond) -> np.ndarray:
    """Pixels de l'image qui portent la teinte des tables HelioScope.

    Une ouverture enlève les pixels isolés ; une fermeture referme les joints
    sombres entre modules, qui passent sous le seuil de saturation.
    """
    from PIL import Image, ImageFilter

    teinte = np.asarray(Image.fromarray(fond.pixels).convert("HSV")).astype(float)
    h = teinte[..., 0] * 360.0 / 255.0
    s = teinte[..., 1] / 255.0
    v = teinte[..., 2] / 255.0
    brut = (
        (h >= TEINTE_TABLES_DEG[0])
        & (h <= TEINTE_TABLES_DEG[1])
        & (s >= SATURATION_TABLES_MIN)
        & (v >= VALEUR_TABLES_MIN)
    )
    image = Image.fromarray((brut * 255).astype(np.uint8))
    image = image.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    image = image.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    return np.asarray(image) > 127


# ---------------------------------------------------------------------------
# Lecture complète
# ---------------------------------------------------------------------------


#: Libellés du tableau d'informations d'un plan, et ce qu'on en lit.
#:
#: Relevés le 23/09/2026 sur le plan de Bray-Saint-Aignan, dont le cartouche
#: porte un tableau en deux colonnes, libellé à gauche et valeur à droite sur
#: la même ligne : « Hauteur point bas | 1.1 mètres min », « Hauteur point haut
#: | 3 mètres max ». Le plan de Gannay n'en a pas. Instruction du chef de
#: projet du même jour : la hauteur des tables se prend au plan quand il la
#: donne, au standard UNITe sinon ; les modules se prennent à l'export
#: HelioScope — le cartouche de Bray en annonce 5 296, l'export en porte 4 590.
#: Le nombre de modules et l'inclinaison ne sont donc lus que pour être
#: recoupés.
INFORMATIONS_DU_PLAN = {
    "point_bas_m": ("Hauteur point bas", "Hauteur du point bas"),
    "point_haut_m": ("Hauteur point haut", "Hauteur du point haut"),
    "nb_modules": ("Nombre de modules",),
    "inclinaison_deg": ("Inclinaison",),
}

#: Forme de la valeur attendue pour chaque information : une longueur en
#: mètres, un entier, un angle en degrés.
_VALEURS_DU_PLAN = {
    "point_bas_m": r"(\d+(?:[.,]\d+)?)\s*(?:m\b|mètres?\b|metres?\b)",
    "point_haut_m": r"(\d+(?:[.,]\d+)?)\s*(?:m\b|mètres?\b|metres?\b)",
    "nb_modules": r"(\d[\d\u00a0\u202f ]*)\s*$",
    "inclinaison_deg": r"(\d+(?:[.,]\d+)?)\s*°",
}


def _informations(lignes: list[LigneTexte]) -> dict:
    """Ce que le tableau d'informations du plan déclare, libellé par libellé.

    La valeur se cherche sur la ligne du libellé, puis sur les lignes posées à
    sa droite à la même hauteur : une cellule de tableau PowerPoint est un
    texte à part, que rien ne relie à son libellé que sa place.
    """
    resultat: dict = {}
    for ligne in lignes:
        texte_normalise = normaliser(ligne.texte)
        for cle, libelles in INFORMATIONS_DU_PLAN.items():
            if cle in resultat or not any(
                texte_normalise.startswith(normaliser(libelle)) for libelle in libelles
            ):
                continue
            hauteur = ligne.hauteur
            voisines = sorted(
                (
                    autre
                    for autre in lignes
                    if autre is not ligne
                    and autre.bornes[0] >= ligne.bornes[2] - 1.0
                    and abs(autre.milieu_y - ligne.milieu_y) < 0.5 * max(hauteur, autre.hauteur)
                ),
                key=lambda autre: autre.bornes[0],
            )
            for source in [ligne] + voisines:
                trouve = re.search(_VALEURS_DU_PLAN[cle], source.texte.strip(), re.IGNORECASE)
                if trouve is None:
                    continue
                brut = re.sub(r"[\s\u00a0\u202f]", "", trouve.group(1)).replace(",", ".")
                resultat[cle] = {
                    "valeur": int(brut) if cle == "nb_modules" else float(brut),
                    "texte": ligne.texte if source is ligne else f"{ligne.texte} | {source.texte}",
                }
                break
    return resultat


def lire_legende(chemin: str | Path) -> list[EntreeLegende]:
    """Les entrées de la légende seules, pour en faire confirmer la correspondance.

    Rien n'y est encore exigé : un plan dont la clôture porte un nom que la
    correspondance ne connaît pas doit pouvoir montrer sa légende, pour qu'on
    l'apparie à la main avant l'import.
    """
    return _page_du_plan(Path(chemin))[1]


def _page_du_plan(chemin: Path):
    """La page qui porte la légende : son rang, sa légende, ses formes, ses images, son texte."""
    document = _ouvrir(chemin)
    pages_lues = []
    for indice in range(len(document)):
        page = document[indice]
        lignes = _lignes_de_texte(page)
        traces, images = _objets_de_page(page)
        objets = _grouper_en_objets(traces)
        legende = _legende(objets, lignes)
        connues = [e for e in legende if e.categorie or e.a_trancher]
        if connues:
            pages_lues.append((indice, legende, objets, images, lignes))

    if not pages_lues:
        raise ErreurLegendeIntrouvable(
            f"Aucune page de « {chemin.name} » ne porte de légende reconnue : "
            "pas de pastille suivie d'un libellé connu, comme « Clôture » ou "
            "« Poste de transformation ». Libellés connus : "
            f"{', '.join(CORRESPONDANCE_LEGENDE)}."
        )
    if len(pages_lues) > 1:
        raise ErreurPlanPDF(
            f"Plusieurs pages de « {chemin.name} » portent une légende "
            f"(pages {', '.join(str(p[0] + 1) for p in pages_lues)}) : impossible "
            "de savoir laquelle est le plan. Ne transmettez que la page du plan."
        )
    return pages_lues[0]


def lire_plan_pdf(
    chemin: str | Path, correspondance: dict[str, str | None] | None = None
) -> PlanPDF:
    """Lit la légende, les formes de la carte et l'image des tables d'un plan PDF.

    `correspondance` remplace, libellé par libellé, la catégorie proposée par
    `CORRESPONDANCE_LEGENDE` : un libellé peut ainsi être apparié à la main, ou
    écarté en lui donnant None.
    """
    chemin = Path(chemin)
    indice, legende, objets, images, lignes = _page_du_plan(chemin)
    avertissements: list[str] = []

    if correspondance:
        normalisee = {normaliser(k): v for k, v in correspondance.items()}
        for entree in legende:
            cle = normaliser(entree.libelle)
            if cle in normalisee:
                entree.categorie = normalisee[cle]
                entree.a_trancher = None

    for categorie in CATEGORIES_ATTENDUES:
        if not any(e.categorie == categorie for e in legende):
            raise ErreurLegendeIntrouvable(
                f"La légende de « {chemin.name} » ne porte pas de clôture "
                f"(catégorie « {categorie} ») : libellés lus — "
                f"{', '.join(e.libelle for e in legende) or 'aucun'}. Sans "
                "clôture, le plan ne délimite pas le projet ; c'est souvent la "
                "marque d'une version antérieure du plan."
            )
    avertissements.extend(
        _pastilles_de_meme_couleur(
            [(e.libelle, e.pastille.couleur, e.categorie) for e in legende]
        )
    )

    avertissements.extend(
        _conseils_des_libelles_non_rattaches(
            [(e.libelle, e.pastille.couleur, e.categorie, e.a_trancher) for e in legende]
        )
    )

    fond = _image_de_fond(images, indice + 1, chemin.name)
    cadre = fond.cadre
    surface_cadre = _surface_bornes(cadre)
    pastilles = {id(e.pastille) for e in legende}

    elements, non_reconnus = [], []
    replis: dict = {}
    for objet in objets:
        if id(objet) in pastilles:
            continue
        b = objet.bornes
        milieu = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
        if not (cadre[0] <= milieu[0] <= cadre[2] and cadre[1] <= milieu[1] <= cadre[3]):
            continue
        if _surface_bornes(b) > 0.5 * surface_cadre:
            # Le cadre de la carte, ou un fond qui la couvre : ni l'un ni
            # l'autre n'est un ouvrage. À Gannay, le cadre porte le vert des
            # pistes existantes.
            continue
        entree, raison = _rattacher(objet, legende)
        if entree is None:
            non_reconnus.append((objet, raison))
            continue
        if raison:
            replis.setdefault((entree.libelle, raison), []).append(
                ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            )
        elements.append(ElementPlan(entree=entree, objet=objet))

    # Un même repli vaut pour toutes les formes qu'il concerne : le dire une
    # fois par forme noyait le reste du rapport. Mesuré le 02/10/2026 sur
    # La Chapelle-sous-Aubenas : onze lignes identiques pour la clôture sur
    # vingt-trois messages, et le chef de projet « n'a plus envie de les lire ».
    # Les positions restent, elles : c'est par elles qu'on retrouve la forme
    # sur le plan.
    for (libelle, raison), positions in replis.items():
        lieux = " ; ".join(f"({x:.0f}, {y:.0f})" for x, y in positions[:3])
        reste = len(positions) - 3
        avertissements.append(
            f"« {libelle} » : {raison} — "
            + (
                f"{len(positions)} fois, vers {lieux} pt"
                + (f" et {reste} autre{'s' if reste > 1 else ''}" if reste > 0 else "")
                if len(positions) > 1
                else f"vers {lieux} pt"
            )
            + "."
        )

    if non_reconnus:
        detail = "; ".join(
            f"{o.nature} {o.couleur} vers ({(o.bornes[0] + o.bornes[2]) / 2:.0f}, "
            f"{(o.bornes[1] + o.bornes[3]) / 2:.0f}) pt — {r}"
            for o, r in non_reconnus[:6]
        )
        avertissements.append(
            f"{len(non_reconnus)} forme(s) de la carte ne se rattachent à aucune "
            f"entrée de la légende et ne sont pas importées : {detail}"
            + (" ; …" if len(non_reconnus) > 6 else "")
        )

    # Une entrée de légende sans rien sur la carte est une anomalie, pas un
    # résultat (décision D7) : ou la couleur du plan s'est écartée de sa
    # pastille, ou l'ouvrage a été retiré sans retirer sa légende.
    for entree in legende:
        if entree.categorie and not any(e.entree is entree for e in elements):
            avertissements.append(
                f"« {entree.libelle} » figure à la légende, mais aucune forme de "
                f"la carte ne porte sa couleur {entree.couleur} : la couche "
                f"« {entree.categorie} » sort vide. Vérifiez que l'ouvrage a bien "
                "été retiré du projet, et pas seulement redessiné d'une autre "
                "couleur."
            )

    return PlanPDF(
        source=chemin.name,
        page=indice + 1,
        legende=legende,
        elements=elements,
        fond=fond,
        non_reconnus=[o for o, _ in non_reconnus],
        avertissements=avertissements,
        informations=_informations(lignes),
    )


# ---------------------------------------------------------------------------
# Géométrie des formes, en points de la page
# ---------------------------------------------------------------------------

#: Remplissage minimal de son rectangle minimal pour qu'une forme remplie soit
#: le trait épais d'une capsule, donc un axe droit.
RECTITUDE_MIN = 0.8

#: Seuil de changement de direction, en degrés, au delà duquel un sommet du
#: tracé est un angle à retrouver plutôt qu'un point de passage.
ANGLE_MIN_DEG = 10.0


def _polygone_de(trace: Trace) -> Polygon | None:
    morceaux = [
        Polygon(c)
        for c, f in zip(trace.sous_chemins, trace.fermes)
        if f and len(c) >= 3
    ]
    morceaux = [m if m.is_valid else m.buffer(0) for m in morceaux]
    morceaux = [m for m in morceaux if not m.is_empty and m.area > 0]
    if not morceaux:
        return None
    union = unary_union(morceaux)
    return union if union.geom_type in ("Polygon", "MultiPolygon") else None


def _rectangle_minimal(geometrie: BaseGeometry):
    """Centre, direction du grand côté (degrés), grand côté et petit côté."""
    rectangle = geometrie.minimum_rotated_rectangle
    sommets = list(rectangle.exterior.coords)[:4]
    cotes = [
        (math.dist(sommets[i], sommets[(i + 1) % 4]), sommets[i], sommets[(i + 1) % 4])
        for i in range(4)
    ]
    grand = max(cotes, key=lambda c: c[0])
    petit = min(c[0] for c in cotes)
    direction = math.degrees(
        math.atan2(grand[2][1] - grand[1][1], grand[2][0] - grand[1][0])
    )
    centre = rectangle.centroid
    return (centre.x, centre.y), _dans_demi_tour(direction), grand[0], petit


def _dans_demi_tour(angle: float) -> float:
    """Direction d'un axe ramenée dans ]-90, 90]."""
    angle = (angle + 90.0) % 180.0 - 90.0
    return 90.0 if angle == -90.0 else angle


def _points_du_pointille(trace: Trace) -> list[tuple[float, float]]:
    """Centres des points d'un pointillé, dans l'ordre où l'export les écrit."""
    centres = []
    for chemin, ferme in zip(trace.sous_chemins, trace.fermes):
        if not ferme:
            continue
        sommets = chemin[:-1] if math.dist(chemin[0], chemin[-1]) < 1e-3 else chemin
        centres.append(
            (
                sum(x for x, _ in sommets) / len(sommets),
                sum(y for _, y in sommets) / len(sommets),
            )
        )
    return centres


def _morceaux_de_trace(objet: Objet) -> tuple[list[LineString], float, list[str]]:
    """Axes d'une forme de tracé, et la largeur typique du trait, en points.

    Trois écritures du même trait coexistent, relevées le 23/09/2026 : un
    chemin tracé (les pistes et les haies de Gannay), dont l'axe est le chemin
    lui-même ; un pointillé de petits carrés remplis (la clôture de Gannay,
    180 points), dont l'axe passe par leurs centres ; un contour rempli en
    capsule (tout le plan de Bray), dont l'axe est le grand axe du rectangle
    minimal, raccourci des deux demi-cercles d'extrémité.
    """
    trace = objet.principal
    remarques: list[str] = []
    if objet.nature == "trait":
        morceaux = [
            LineString(list(c) + ([c[0]] if f and c[0] != c[-1] else []))
            for c, f in zip(trace.sous_chemins, trace.fermes)
            if len(c) >= 2
        ]
        return morceaux, trace.epaisseur_pt, remarques

    if objet.motif == "pointille":
        centres = _points_du_pointille(trace)
        if len(centres) < 2:
            return [], 0.0, remarques
        return [LineString(centres)], 0.0, remarques

    polygone = _polygone_de(trace)
    if polygone is None:
        return [], 0.0, remarques
    (cx, cy), direction, longueur, largeur = _rectangle_minimal(polygone)
    rectitude = polygone.area / (longueur * largeur) if longueur * largeur else 0.0
    if rectitude < RECTITUDE_MIN:
        remarques.append(
            f"un trait vers ({cx:.0f}, {cy:.0f}) pt n'est pas rectiligne "
            f"(il remplit {rectitude:.0%} de son rectangle minimal) : son axe est "
            "approché par son grand côté"
        )
    # Les bouts arrondis d'une capsule dépassent l'extrémité du trait d'un
    # demi-diamètre ; un bout carré s'arrête au trait.
    demi = max((longueur - (largeur if trace.courbe else 0.0)) / 2.0, 0.0)
    ux, uy = math.cos(math.radians(direction)), math.sin(math.radians(direction))
    return (
        [LineString([(cx - ux * demi, cy - uy * demi), (cx + ux * demi, cy + uy * demi)])],
        largeur,
        remarques,
    )


def _relier(morceaux: list[LineString], jeu: float) -> list[LineString]:
    """Recoud des morceaux de trait bout à bout, quand leurs bouts se touchent.

    Un trait de PowerPoint arrive en morceaux : 32 pans de points pour la
    clôture de Gannay, dans un ordre qui ne suit pas le tour, neuf capsules
    pour celle de Bray. Chaque morceau est prolongé par celui dont un bout est
    le plus proche, à moins de `jeu`, jusqu'à ce qu'il n'y en ait plus ; un
    tracé dont les deux bouts se rejoignent est refermé.
    """
    restants = [list(m.coords) for m in morceaux if len(m.coords) >= 2]
    lignes = []
    while restants:
        chaine = restants.pop(0)
        if len(chaine) > 3 and math.dist(chaine[0], chaine[-1]) < 1e-6:
            lignes.append(LineString(chaine))
            continue
        while restants:
            meilleur = None
            for indice, morceau in enumerate(restants):
                for bout_chaine in (0, -1):
                    for bout_morceau in (0, -1):
                        d = math.dist(chaine[bout_chaine], morceau[bout_morceau])
                        if d <= jeu and (meilleur is None or d < meilleur[0]):
                            meilleur = (d, indice, bout_chaine, bout_morceau)
            if meilleur is None:
                break
            _, indice, bout_chaine, bout_morceau = meilleur
            morceau = restants.pop(indice)
            if bout_chaine == -1:
                chaine = chaine + (morceau if bout_morceau == 0 else morceau[::-1])
            else:
                chaine = (morceau[::-1] if bout_morceau == 0 else morceau) + chaine
        if len(chaine) > 3 and 1e-9 <= math.dist(chaine[0], chaine[-1]) <= jeu:
            chaine = chaine + [chaine[0]]
        lignes.append(LineString(chaine))
    return lignes


def _intersection_des_droites(a1, a2, b1, b2):
    """Intersection des droites (a1 a2) et (b1 b2), ou None si parallèles."""
    dxa, dya = a2[0] - a1[0], a2[1] - a1[1]
    dxb, dyb = b2[0] - b1[0], b2[1] - b1[1]
    denominateur = dxa * dyb - dya * dxb
    if abs(denominateur) < 1e-12:
        return None
    t = ((b1[0] - a1[0]) * dyb - (b1[1] - a1[1]) * dxb) / denominateur
    return (a1[0] + t * dxa, a1[1] + t * dya)


def _retrouver_les_angles(ligne: LineString, jeu: float, tolerance: float) -> LineString:
    """Rend à un tracé les angles que ses morceaux n'atteignaient pas.

    Les points d'un pointillé s'arrêtent avant l'angle, et deux pans se
    rejoignent par un court biais qui le coupe. Relié tel quel, le tracé de la
    clôture de Gannay fait 682,3 m ; ses quatre côtés, prolongés jusqu'à se
    couper, en font 684,5 (mesuré le 23/09/2026). Un biais plus court que
    `jeu`, entre deux côtés plus longs que lui qui font un angle franc, est
    donc remplacé par l'intersection de ces deux côtés.
    """
    # Fermé se juge aux extrémités, et non par `is_ring`, qui exige aussi un
    # tracé sans recoupement : à la jonction de deux pans de points, un pas en
    # arrière de 0,6 pt suffit à le recouper, et l'angle de départ restait coupé.
    coords = list(ligne.coords)
    ferme = len(coords) > 3 and math.dist(coords[0], coords[-1]) < 1e-9
    points = list(ligne.simplify(tolerance, preserve_topology=False).coords)
    if ferme:
        points = points[:-1]
    if len(points) < 4:
        return ligne

    change = True
    while change and len(points) >= 4:
        change = False
        n = len(points)
        indices = range(n) if ferme else range(1, n - 2)
        for i in indices:
            a, b = points[i - 1], points[i]
            c, d = points[(i + 1) % n], points[(i + 2) % n]
            biais = math.dist(b, c)
            if biais > jeu or math.dist(a, b) <= biais or math.dist(c, d) <= biais:
                continue
            angle = abs(
                _dans_demi_tour(
                    math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
                    - math.degrees(math.atan2(d[1] - c[1], d[0] - c[0]))
                )
            )
            if angle < ANGLE_MIN_DEG:
                continue
            coin = _intersection_des_droites(a, b, c, d)
            if coin is None or math.dist(coin, ((b[0] + c[0]) / 2, (b[1] + c[1]) / 2)) > jeu:
                continue
            points[i] = coin
            del points[(i + 1) % n]
            change = True
            break
    if ferme:
        points.append(points[0])
    return LineString(points)


@dataclass(frozen=True)
class TracePlan:
    """Un tracé du plan, en points de la page, avec le libellé qui l'a nommé."""

    categorie: str
    libelle: str
    ligne: LineString

    @property
    def ferme(self) -> bool:
        coords = list(self.ligne.coords)
        return len(coords) > 3 and math.dist(coords[0], coords[-1]) < 1e-9


def traces(
    plan: PlanPDF, categorie: str, ecarter: frozenset = frozenset()
) -> tuple[list[TracePlan], list[str]]:
    """Tracés d'une catégorie linéaire, en points de la page, morceaux recousus.

    `ecarter` porte les `id` des formes qui ne sont pas des tracés : les
    surfaces d'une catégorie de piste, gardées telles que dessinées.

    Les morceaux se recousent **par entrée de légende**, et non par catégorie :
    à Gannay la haie à créer et la haie à renforcer vont toutes deux à `haie`
    et se touchent bout à bout — recousues ensemble, elles ne faisaient plus
    qu'un tracé, et le libellé de l'une disparaissait.

    Rend aussi ce qu'il faut en dire : un morceau de trait qui n'est pas droit.
    """
    resultat, remarques = [], []
    for entree in plan.entree(categorie):
        morceaux, largeurs, espacements = [], [], []
        for element in plan.elements:
            if element.entree is not entree or id(element.objet) in ecarter:
                continue
            axes, largeur, notes = _morceaux_de_trace(element.objet)
            morceaux.extend(axes)
            remarques.extend(f"« {entree.libelle} » : {n}" for n in notes)
            if largeur:
                largeurs.append(largeur)
            if element.objet.motif == "pointille":
                for axe in axes:
                    coords = list(axe.coords)
                    espacements.extend(math.dist(p, q) for p, q in zip(coords, coords[1:]))
        if not morceaux:
            continue
        # Le jeu admis entre deux bouts : deux pas de pointillé, ou deux largeurs
        # de trait. Mesuré sur la clôture de Gannay, les pans de points se
        # rejoignent à 6,2 pt au plus, pour un pas de 6,0.
        jeu = max(
            2.0 * statistics.median(espacements) if espacements else 0.0,
            2.0 * statistics.median(largeurs) if largeurs else 0.0,
            2.0,
        )
        tolerance = max(0.1, 0.1 * statistics.median(largeurs)) if largeurs else 0.1
        for ligne in _relier(morceaux, jeu):
            resultat.append(
                TracePlan(
                    categorie=categorie,
                    libelle=entree.libelle,
                    ligne=_retrouver_les_angles(ligne, jeu, tolerance),
                )
            )
    return resultat, remarques


@dataclass(frozen=True)
class Repere:
    """Un ouvrage tel que le plan le situe : position et orientation, rien d'autre.

    Le plan n'est pas à l'échelle pour les ouvrages (instruction du chef de
    projet du 21/09/2026, décision D2) : la taille dessinée est gardée pour le
    rapport, jamais pour la géométrie.
    """

    categorie: str
    libelle: str
    centre: tuple[float, float]
    #: Direction du grand côté dessiné, en degrés dans ]-90, 90].
    direction_deg: float
    longueur_dessinee: float
    largeur_dessinee: float

    @property
    def orientation_ambigue(self) -> bool:
        """Vrai quand le repère dessiné est carré : son grand côté ne dit rien."""
        return (
            self.largeur_dessinee <= 0
            or self.longueur_dessinee / self.largeur_dessinee < 1.15
        )


def reperes(plan: PlanPDF, categorie: str) -> list[Repere]:
    """Position et orientation de chaque ouvrage d'une catégorie, en points."""
    resultat = []
    for element in plan.elements_de(categorie):
        principal = element.objet.principal
        forme = _polygone_de(principal)
        if forme is None:
            forme = MultiPoint(
                [p for c in principal.sous_chemins for p in c]
            ).minimum_rotated_rectangle
        _, direction, longueur, largeur = _rectangle_minimal(forme)
        centre = forme.centroid
        resultat.append(
            Repere(
                categorie=categorie,
                libelle=element.entree.libelle,
                centre=(centre.x, centre.y),
                direction_deg=direction,
                longueur_dessinee=longueur,
                largeur_dessinee=largeur,
            )
        )
    return resultat


# ---------------------------------------------------------------------------
# Calage sur les tables du lot 2
# ---------------------------------------------------------------------------


@dataclass
class RangeesDuPlan:
    """Les rangées de tables relevées sur la copie d'écran, en points de page."""

    #: Direction des rangées, en degrés dans ]-90, 90], ordonnée vers le haut.
    direction_deg: float
    pas_pt: float
    dispersion_pt: float
    #: Position de chaque rangée sur la normale, du bas vers le haut.
    centres: list
    #: Points des tables, en points de page, restreints aux rangées reconnues.
    points: np.ndarray
    #: Pixels de l'image retenus comme tables, restreints aux rangées.
    masque: np.ndarray
    #: Pixels à la teinte des tables écartés comme étrangers au champ.
    isolats_ecartes: int = 0


#: Part des pixels de table sous laquelle un groupe isolé n'est pas le champ.
PART_ISOLAT_MAX = 0.01

#: Écart, en pixels, au-delà duquel deux groupes de tables ne se touchent plus.
ECART_ISOLAT_PX = 20.0


def _sans_les_isolats(points, retenus, direction: float, pas: float):
    """Écarte les taches à la teinte des tables qui ne sont pas le champ.

    Relevé le 30/09/2026 sur Lachapelle-sous-Aubenas : la page porte sept
    taches de la teinte HelioScope hors du champ — pastille de légende, flèche
    du nord, échelle — de 76 à 1 131 pixels pour un champ de 489 034. Elles ne
    changent rien aux rangées, qui se mesurent sur des bandes de vingt points
    au moins, mais l'emprise se prend au minimum et au maximum : elles la
    faisaient passer de 976 à 1 976 pixels, soit le facteur deux exact qui
    faisait échouer le recoupement d'échelle (« -50,6 % » pour 2 % tolérés).

    Le champ pèse 99 % des pixels : ce qui pèse moins d'un centième **et** se
    tient à plus de vingt pixels du reste n'en fait pas partie. Les deux
    conditions comptent — un projet en plusieurs zones, comme
    Saint-Aubin-sur-Loire, a des groupes éloignés qui pèsent chacun leur part.
    """
    if not retenus.any():
        return retenus, 0
    angle = math.radians(direction)
    le_long = points[:, 0] * math.cos(angle) + points[:, 1] * math.sin(angle)
    ordre = np.argsort(le_long[retenus])
    indices = np.nonzero(retenus)[0][ordre]
    valeurs = le_long[indices]

    coupures = np.nonzero(np.diff(valeurs) > ECART_ISOLAT_PX * pas)[0]
    groupes = np.split(indices, coupures + 1)
    minimum = PART_ISOLAT_MAX * len(indices)
    gardes = [groupe for groupe in groupes if len(groupe) >= minimum]
    if len(gardes) == len(groupes):
        return retenus, 0

    filtre = np.zeros_like(retenus)
    for groupe in gardes:
        filtre[groupe] = True
    return filtre, int(retenus.sum() - filtre.sum())


def _pas_pixel(fond: ImageDeFond) -> float:
    largeur, hauteur = fond.taille
    a, b, c, d, _, _ = fond.matrice
    return math.sqrt(abs(a * d - b * c) / (largeur * hauteur))


def _profil(points: np.ndarray, normale_deg: float, pas: float):
    angle = math.radians(normale_deg)
    projection = points[:, 0] * math.cos(angle) + points[:, 1] * math.sin(angle)
    origine = projection.min()
    indices = ((projection - origine) / pas).astype(int)
    return np.bincount(indices), origine, projection


def _peigne(points, angle: float, pas: float) -> tuple[int, float]:
    """Ce qu'un profil a de rangées, et à défaut ce qu'il a de concentration.

    La direction des rangées se cherchait sur la seule concentration du profil
    — `_nettete`, qui vaut Σh²/(Σh)² et culmine quand la masse tient en peu de
    cases. Sur un champ d'un seul tenant, c'est bien en travers des rangées
    qu'elle culmine : le peigne y occupe la moitié des cases, là où le profil
    en long les remplit toutes.

    Un projet en **deux zones décalées** casse ce raisonnement. Relevé le
    29/09/2026 sur Saint-Aubin-sur-Loire : à 20,55°, les nuages des deux zones
    se superposent et la masse se concentre, pour une note de 0,0113 et **une
    seule bande** ; à 90°, la vraie direction, le profil montre **35 rangées**
    pour une note de 0,0069. La concentration gagnait contre la périodicité, et
    le plan était refusé faute de rangées.

    On compte donc les rangées d'abord, et la concentration ne tranche plus que
    les égalités — ce qu'elle fait très bien au dixième de degré près, où le
    compte de bandes ne bouge plus.
    """
    histogramme = _profil(points, angle, pas)[0]
    return len(_bandes(histogramme)), _nettete(histogramme)


def _nettete(histogramme: np.ndarray) -> float:
    h = histogramme.astype(float)
    return float((h * h).sum() / max(h.sum(), 1.0) ** 2)


#: Seuil de présence d'une rangée sur le profil, en fraction de son 95e
#: centile. Les creux entre rangées sont vides — zéro pixel de tables sur toute
#: leur largeur, mesuré sur Gannay et Bray — et une rangée courte pèse peu : à
#: 20 %, les rangées de quatre tables des deux bouts de Gannay disparaissaient,
#: et avec elles 14 % de l'emprise en travers.
SEUIL_PROFIL = 0.03


def _bandes(histogramme: np.ndarray) -> list[tuple[int, int]]:
    """Plages du profil que les rangées occupent, en indices de case."""
    lisse = np.convolve(histogramme.astype(float), np.ones(3) / 3.0, mode="same")
    if not (lisse > 0).any():
        return []
    seuil = SEUIL_PROFIL * np.percentile(lisse[lisse > 0], 95)
    bandes, debut = [], None
    for i, actif in enumerate(lisse > seuil):
        if actif and debut is None:
            debut = i
        elif not actif and debut is not None:
            bandes.append([debut, i - 1])
            debut = None
    if debut is not None:
        bandes.append([debut, len(lisse) - 1])
    # Deux plages séparées d'une case ou deux sont une même rangée coupée par
    # le bruit de l'image.
    fusion = []
    for bande in bandes:
        if fusion and bande[0] - fusion[-1][1] <= 2:
            fusion[-1][1] = bande[1]
        else:
            fusion.append(bande)
    if not fusion:
        return []
    # Une rangée a la profondeur d'une table, quelle que soit sa longueur : ce
    # qui s'en écarte n'en est pas une.
    largeurs = [b[1] - b[0] + 1 for b in fusion]
    largeur_type = statistics.median(largeurs)
    return [
        (b[0], b[1])
        for b, l in zip(fusion, largeurs)
        if 0.5 * largeur_type <= l <= 1.6 * largeur_type
    ]


def _dans_la_bande(projection, origine, pas, bande):
    debut, fin = bande
    return (projection >= origine + debut * pas) & (projection < origine + (fin + 1) * pas)


def mesurer_rangees(fond: ImageDeFond, masque: np.ndarray | None = None) -> RangeesDuPlan:
    """Direction, pas et position des rangées de tables sur la copie d'écran.

    **L'échelle se mesure, elle ne se cherche pas** (décision D3) : les rangées
    ont un pas connu, celui du DXF, et le plan en montre des dizaines. Leur
    direction se lit d'abord sur la netteté du profil — c'est en travers des
    rangées que leurs bandes se détachent le mieux —, puis s'affine sur l'axe
    principal de chaque rangée, que la grille des pixels ne biaise pas. Le pas
    est la médiane des écarts entre rangées voisines : une rangée manquée donne
    un écart double, écarté.
    """
    if masque is None:
        masque = masque_des_tables(fond)
    lignes_px, colonnes_px = np.nonzero(masque)
    if len(lignes_px) < 100:
        raise ErreurPlanPDF(
            "La copie d'écran du plan ne porte pas de tables reconnaissables "
            f"(teinte HelioScope, {TEINTE_TABLES_DEG[0]:.0f} à "
            f"{TEINTE_TABLES_DEG[1]:.0f}°) : il n'y a pas d'échelle à mesurer "
            "(décision D3). Le plan doit porter les tables pour être calé."
        )
    xs, ys = fond.vers_page(colonnes_px, lignes_px)
    points = np.column_stack([xs, ys])
    pas = _pas_pixel(fond)

    echantillon = points[:: max(1, len(points) // 60_000)]
    grossiere = max(
        np.arange(0.0, 180.0, 0.5),
        key=lambda a: _peigne(echantillon, a, pas),
    )
    normale = max(
        np.arange(grossiere - 0.75, grossiere + 0.75, 0.05),
        key=lambda a: _peigne(echantillon, a, pas),
    )

    histogramme, origine, projection = _profil(points, normale, pas)
    directions, poids = [], []
    for bande in _bandes(histogramme):
        dans = _dans_la_bande(projection, origine, pas, bande)
        if dans.sum() < 20:
            continue
        sous = points[dans] - points[dans].mean(axis=0)
        valeurs, vecteurs = np.linalg.eigh(np.cov(sous.T))
        axe = vecteurs[:, int(np.argmax(valeurs))]
        directions.append(math.degrees(math.atan2(axe[1], axe[0])))
        poids.append(int(dans.sum()))
    if not directions:
        raise ErreurPlanPDF(
            "Aucune rangée de tables ne se détache sur la copie d'écran du plan : "
            "le pas des rangées ne se mesure pas (décision D3)."
        )
    reference = directions[int(np.argmax(poids))]
    ecarts = [_dans_demi_tour(d - reference) for d in directions]
    direction = _dans_demi_tour(reference + float(np.average(ecarts, weights=poids)))

    histogramme, origine, projection = _profil(points, direction + 90.0, pas)
    centres = []
    dans_une_bande = np.zeros(len(points), dtype=bool)
    for bande in _bandes(histogramme):
        dans = _dans_la_bande(projection, origine, pas, bande)
        if dans.sum() < 20:
            continue
        centres.append(float(projection[dans].mean()))
        dans_une_bande |= dans
    centres.sort()
    ecarts_rangees = np.diff(centres)
    if len(ecarts_rangees) < 2:
        # La cause est presque toujours la finesse de la copie d'écran, et le
        # chef de projet ne peut pas la deviner du seul compte de rangées.
        # Mesuré le 29/09/2026 : Saint-Aubin-sur-Loire, 807 x 645 pixels et
        # 9 539 pixels de table, une seule bande ; Gannay, 1 232 x 995 et
        # 147 470 pixels de table, quinze rangées séparées. Le message dit donc
        # ce qui a été mesuré et ce qu'il y a à faire.
        hauteur_px, largeur_px = masque.shape
        raise ErreurPlanPDF(
            f"{len(centres)} rangée(s) de tables reconnue(s) sur la copie d'écran "
            "du plan : il en faut trois au moins pour mesurer un pas (décision "
            f"D3). La copie d'écran fait {largeur_px} x {hauteur_px} pixels et "
            f"les tables n'y occupent que {int(masque.sum())} pixels : à cette "
            "finesse les rangées ne se séparent pas. Refaites-la en plein écran, "
            "zoomée sur le site, et remontez le plan par-dessus."
        )
    # Le pas est la pente des centres de rangée sur leur rang, et non la
    # médiane de leurs écarts. Chaque centre porte l'arrondi des bords de sa
    # bande au pixel de l'image — 0,48 pt à Gannay —, et la médiane de quinze
    # écarts en gardait ±2,5 ‰ (mesuré le 23/09/2026), autant que la
    # tolérance. La droite, elle, s'appuie sur toutes les rangées à la fois.
    # Le rang se lit sur l'écart médian : une rangée manquée laisse un rang
    # vide, elle ne décale pas les suivantes.
    median = float(np.median(ecarts_rangees))
    rangs = np.round((np.array(centres) - centres[0]) / median)
    if len(set(rangs.tolist())) != len(rangs):
        raise ErreurPlanPDF(
            "Les rangées du plan ne sont pas régulièrement espacées : deux d'entre "
            "elles tombent au même rang, et le pas ne se mesure pas (écarts "
            f"relevés : {np.round(ecarts_rangees, 2).tolist()} pt)."
        )
    pente, ordonnee = np.polyfit(rangs, centres, 1)
    residus = np.array(centres) - (pente * rangs + ordonnee)
    if np.abs(residus).max() > 0.25 * pente:
        raise ErreurPlanPDF(
            "Les rangées du plan ne tombent pas sur un pas régulier : l'une d'elles "
            f"s'en écarte de {np.abs(residus).max():.2f} pt pour un pas de "
            f"{pente:.2f} pt. Le pas ne se mesure pas (décision D3)."
        )
    dans_une_bande, isolats = _sans_les_isolats(
        points, dans_une_bande, direction, pas
    )
    masque_rangees = np.zeros_like(masque)
    masque_rangees[lignes_px[dans_une_bande], colonnes_px[dans_une_bande]] = True
    return RangeesDuPlan(
        direction_deg=direction,
        pas_pt=float(pente),
        dispersion_pt=float(np.std(residus)),
        centres=centres,
        points=points[dans_une_bande],
        masque=masque_rangees,
        isolats_ecartes=isolats,
    )


@dataclass
class CalagePlan:
    """Passage de la page du plan au repère local du DXF, et ce qui le fonde.

    `dxf = echelle · R(rotation) · page + translation`, en mètres au sol dans le
    repère du DXF HelioScope. Le passage en Lambert 93 est ensuite celui du
    lot 2 : un réglage du calage géographique ne demande pas de recaler le plan.
    """

    echelle_m_par_pt: float
    rotation_deg: float
    translation: tuple[float, float]
    #: Pas des rangées mesuré sur le plan, en points, et sa dispersion.
    pas_plan_pt: float
    dispersion_pas_pt: float
    #: Pas des rangées du DXF, en mètres au sol : l'étalon de l'échelle.
    pas_dxf_m: float
    nb_rangees_plan: int
    nb_rangees_dxf: int
    #: Échelles qu'impliquent l'emprise des tables, le long des rangées et en
    #: travers, en mètres par point : le recoupement de la décision D7.
    echelle_le_long_m_par_pt: float
    echelle_en_travers_m_par_pt: float
    #: Recouvrement de Jaccard des tables du plan et du DXF, une fois calées.
    recouvrement: float
    #: Part des tables du plan qui tombent sur une table du DXF, à un pixel
    #: près. C'est elle qui fonde le calage : voir `FIDELITE_MIN`.
    fidelite: float
    #: Pixels à la teinte des tables écartés comme étrangers au champ.
    isolats_ecartes: int
    #: Le même, le plan tourné d'un demi-tour : ce qui a départagé les deux
    #: sens possibles d'une direction de rangées.
    recouvrement_retourne: float
    direction_plan_deg: float
    direction_dxf_deg: float

    @property
    def m_par_px_reference(self) -> float:
        """L'échelle dans l'unité du brief : mètres par pixel d'un rendu à 300 dpi."""
        return self.echelle_m_par_pt * 72.0 / DPI_REFERENCE

    @property
    def coefficients(self) -> list[float]:
        """Coefficients de `shapely.affinity.affine_transform`, page → DXF."""
        c = self.echelle_m_par_pt * math.cos(math.radians(self.rotation_deg))
        s = self.echelle_m_par_pt * math.sin(math.radians(self.rotation_deg))
        return [c, -s, s, c, self.translation[0], self.translation[1]]

    def vers_dxf(self, geometrie: BaseGeometry) -> BaseGeometry:
        return affinity.affine_transform(geometrie, self.coefficients)

    def point_vers_dxf(self, x: float, y: float) -> tuple[float, float]:
        a, b, d, e, xo, yo = self.coefficients
        return (a * x + b * y + xo, d * x + e * y + yo)

    def direction_vers_dxf(self, direction_deg: float) -> float:
        return _dans_demi_tour(direction_deg + self.rotation_deg)


def _rasteriser(tables, vers_pixels, taille: tuple[int, int], marge: int) -> np.ndarray:
    """Tables du DXF dessinées sur la grille de l'image, avec une marge autour."""
    from PIL import Image, ImageDraw

    largeur, hauteur = taille
    image = Image.new("L", (largeur + 2 * marge, hauteur + 2 * marge), 0)
    dessin = ImageDraw.Draw(image)
    for table in tables:
        for polygone in getattr(table, "geoms", [table]):
            xs, ys = zip(*polygone.exterior.coords)
            colonnes, lignes = vers_pixels(np.array(xs), np.array(ys))
            # Les pixels sont repérés par leur coin dans ImageDraw, par leur
            # centre dans la grille de l'image : d'où le demi-pixel.
            dessin.polygon(
                list(
                    zip(
                        (colonnes + marge - 0.5).tolist(),
                        (lignes + marge - 0.5).tolist(),
                    )
                ),
                fill=1,
            )
    return np.asarray(image, dtype=bool)


def _correlation(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Intersection de `a` et de `b` décalé, pour tous les décalages, par FFT."""
    forme = (a.shape[0] * 2, a.shape[1] * 2)
    fa = np.fft.rfft2(a.astype(np.float32), forme)
    fb = np.fft.rfft2(b.astype(np.float32), forme)
    return np.fft.irfft2(fa * np.conj(fb), forme)


def _sommet_parabolique(gauche: float, centre: float, droite: float) -> float:
    denominateur = gauche - 2.0 * centre + droite
    if denominateur >= 0:
        return 0.0
    return max(-0.5, min(0.5, 0.5 * (gauche - droite) / denominateur))


def _part_du_plan_sur_les_tables(
    fond, rangees, tables_dxf, echelle, rotation, translation, rayon
) -> float:
    """Part des tables du plan qui tombent sur une table du DXF, au pixel près.

    Le pixel de tolérance est ce qui distingue cette mesure du recouvrement :
    il absorbe le débord qu'une copie d'écran grossière donne aux barres, et
    ne comble pas l'absence d'une table. Voir `FIDELITE_MIN`.
    """
    from PIL import Image, ImageFilter

    cos_r, sin_r = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))

    def vers_pixels(x, y):
        dx, dy = (x - translation[0]) / echelle, (y - translation[1]) / echelle
        return fond.vers_pixels(cos_r * dx + sin_r * dy, -sin_r * dx + cos_r * dy)

    marge = int(math.ceil(rayon)) + 2
    du_plan = np.pad(rangees.masque, marge)
    du_dxf = _rasteriser(tables_dxf, vers_pixels, fond.taille, marge)
    voisinage = (
        np.asarray(
            Image.fromarray((du_dxf * 255).astype(np.uint8)).filter(
                ImageFilter.MaxFilter(3)
            )
        )
        > 127
    )
    total = float(du_plan.sum())
    return float((du_plan & voisinage).sum()) / total if total else 0.0


def _essai_de_sens(fond, rangees, tables_dxf, echelle, rotation, rayon):
    """Translation par recouvrement, pour une rotation donnée (décision D4).

    Les centroïdes alignent d'abord les deux damiers — ce sont les mêmes
    tables —, puis le recouvrement de Jaccard se maximise sur un domaine borné
    à 0,6 pas : au delà, c'est une rangée voisine qu'on alignerait. C'est la
    leçon de la corrélation d'image du prototype, dont le pic était sorti à
    -500 px, hors de toute translation possible.
    """
    cos_r, sin_r = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    centre_plan = rangees.points.mean(axis=0)
    centre_dxf = unary_union(tables_dxf).centroid
    depart = (
        centre_dxf.x - echelle * (cos_r * centre_plan[0] - sin_r * centre_plan[1]),
        centre_dxf.y - echelle * (sin_r * centre_plan[0] + cos_r * centre_plan[1]),
    )

    def vers_pixels(x, y, t):
        dx, dy = (x - t[0]) / echelle, (y - t[1]) / echelle
        return fond.vers_pixels(cos_r * dx + sin_r * dy, -sin_r * dx + cos_r * dy)

    marge = int(math.ceil(rayon)) + 2
    a = np.pad(rangees.masque, marge)
    b = _rasteriser(tables_dxf, lambda x, y: vers_pixels(x, y, depart), fond.taille, marge)
    intersections = _correlation(a, b)
    total = float(a.sum() + b.sum())

    def recouvrement(dl, dc):
        i = intersections[dl, dc]
        return i / (total - i)

    rang = int(rayon)
    decalages = [
        (dl, dc)
        for dl in range(-rang, rang + 1)
        for dc in range(-rang, rang + 1)
        if dl * dl + dc * dc <= rayon * rayon
    ]
    dl, dc = max(decalages, key=lambda d: recouvrement(*d))
    fl = dl + _sommet_parabolique(
        recouvrement(dl - 1, dc), recouvrement(dl, dc), recouvrement(dl + 1, dc)
    )
    fc = dc + _sommet_parabolique(
        recouvrement(dl, dc - 1), recouvrement(dl, dc), recouvrement(dl, dc + 1)
    )
    # Le damier du plan est celui du DXF décalé de (fl, fc) pixels : on ramène
    # ce décalage en mètres du DXF.
    x0, y0 = fond.vers_page(0.0, 0.0)
    x1, y1 = fond.vers_page(fc, fl)
    dx_page, dy_page = float(x1 - x0), float(y1 - y0)
    translation = (
        depart[0] - echelle * (cos_r * dx_page - sin_r * dy_page),
        depart[1] - echelle * (sin_r * dx_page + cos_r * dy_page),
    )
    b = _rasteriser(
        tables_dxf, lambda x, y: vers_pixels(x, y, translation), fond.taille, marge
    )
    union = float((a | b).sum())
    return (float((a & b).sum()) / union if union else 0.0), translation


def _etendues(points: np.ndarray, direction_deg: float) -> tuple[float, float]:
    """Étendue d'un nuage de points le long d'une direction, et en travers."""
    u = (math.cos(math.radians(direction_deg)), math.sin(math.radians(direction_deg)))
    le_long = points[:, 0] * u[0] + points[:, 1] * u[1]
    en_travers = -points[:, 0] * u[1] + points[:, 1] * u[0]
    return float(np.ptp(le_long)), float(np.ptp(en_travers))


def _etendues_denses(points: np.ndarray, direction_deg: float, pixel: float):
    """Les étendues d'un nuage de pixels, sans ses pixels égarés.

    Le minimum et le maximum sont les deux statistiques les moins robustes qui
    soient : un seul pixel les emporte. Sur une copie d'écran HelioScope, le
    terrain nu prend par endroits la teinte des tables, et `_sans_les_isolats`
    ne retire que les taches franchement détachées — pas une traînée éparse
    dans le prolongement des rangées.

    L'emprise se prend donc là où le champ est encore dense : on profile le
    nuage en cases d'un pixel, et on s'arrête à la dernière case qui porte au
    moins `PART_BORD_MIN` de la case médiane. Ce n'est pas un repli : c'est
    l'estimateur, le même pour tous les plans, et il mesure la même chose en
    présence de bruit comme en son absence.
    """
    angle = math.radians(direction_deg)
    u = (math.cos(angle), math.sin(angle))
    axes = (
        points[:, 0] * u[0] + points[:, 1] * u[1],
        -points[:, 0] * u[1] + points[:, 1] * u[0],
    )
    etendues = []
    for valeurs in axes:
        brute = float(np.ptp(valeurs))
        cases = max(1, int(math.ceil(brute / pixel)))
        histo, bords = np.histogram(valeurs, bins=cases)
        pleines = histo[histo > 0]
        # Lissé sur cinq cases : une table fait au moins un demi-mètre de
        # profondeur, du bruit non. Sans ce lissage, une seule case un peu
        # fournie dans la traînée rendait le bord au bruit.
        lisse = np.convolve(histo, np.ones(LARGEUR_LISSAGE_BORD) / LARGEUR_LISSAGE_BORD, mode="same")
        gardes = np.nonzero(lisse >= PART_BORD_MIN * np.median(pleines))[0]
        etendues.append(
            brute
            if gardes.size == 0
            else float(bords[gardes[-1] + 1] - bords[gardes[0]])
        )
    return etendues[0], etendues[1]


def caler_sur_tables(plan: PlanPDF, implantation) -> CalagePlan:
    """Cale la page du plan sur les tables que le lot 2 a lues dans le DXF.

    Tout se fait dans le repère local du DXF, en mètres au sol : c'est là que
    le pas des rangées est exact, et que les tables sont celles du plan, nord
    en haut toutes les deux. La convergence des méridiens n'y entre pas — elle
    est le fait du passage en Lambert 93, que le lot 2 applique ensuite aux
    tables comme au reste (décision D5).

    Lève `ErreurEchelleIncoherente` si l'emprise des tables contredit le pas de
    plus de 2 % dans l'une des deux directions, `ErreurRecouvrementInsuffisant`
    si les deux damiers, calés, se recouvrent à moins de 70 % (décision D7).
    """
    from .helioscope import rangees_locales
    from .import_be import azimut_tables

    rangees = mesurer_rangees(plan.fond)
    lignes_dxf, _ = rangees_locales(implantation)
    direction_dxf = azimut_tables(lignes_dxf)
    pas_dxf = implantation.calepinage.pas_rangees_m
    echelle = pas_dxf / rangees.pas_pt
    rotation = _dans_demi_tour(direction_dxf - rangees.direction_deg)

    # L'emprise des tables, dans les deux directions : un plan étiré d'un seul
    # côté garde son pas en travers des rangées et perd son échelle le long.
    tables_dxf = implantation.tables
    sommets_dxf = np.array(
        [
            p
            for table in tables_dxf
            for polygone in getattr(table, "geoms", [table])
            for p in polygone.exterior.coords
        ]
    )
    long_dxf, travers_dxf = _etendues(sommets_dxf, direction_dxf)
    pixel = _pas_pixel(plan.fond)
    # Le DXF n'a pas de bruit : ses sommets sont ceux des tables. Le plan en a,
    # et c'est son étendue seule qu'on prend au dense — voir `_etendues_denses`.
    long_plan, travers_plan = _etendues_denses(
        rangees.points, rangees.direction_deg, pixel
    )
    echelle_long = long_dxf / (long_plan + pixel)
    echelle_travers = travers_dxf / (travers_plan + pixel)
    for nom, valeur in (
        ("le long des rangées", echelle_long),
        ("en travers des rangées", echelle_travers),
    ):
        if abs(valeur / echelle - 1.0) > TOLERANCE_ECHELLE:
            raise ErreurEchelleIncoherente(
                f"L'échelle mesurée sur le pas des rangées — {rangees.pas_pt:.2f} pt "
                f"pour {pas_dxf:.3f} m, soit {echelle * 72 / DPI_REFERENCE:.4f} m/px "
                f"à {DPI_REFERENCE:.0f} dpi — s'écarte de {valeur / echelle - 1:+.1%} "
                f"de celle qu'implique l'emprise des tables {nom} "
                f"({valeur * 72 / DPI_REFERENCE:.4f} m/px). Au delà de "
                f"{TOLERANCE_ECHELLE:.0%}, le plan ne montre pas le même calepinage "
                "que le DXF, ou sa copie d'écran a été étirée d'un seul côté."
            )

    rayon = 0.6 * rangees.pas_pt / pixel
    retournee = rotation - 180.0 if rotation > 0 else rotation + 180.0
    essais = sorted(
        (
            (*_essai_de_sens(plan.fond, rangees, tables_dxf, echelle, sens, rayon), sens)
            for sens in (rotation, retournee)
        ),
        key=lambda essai: -essai[0],
    )
    recouvrement, translation, sens = essais[0]
    nb_plan, nb_dxf = len(rangees.centres), implantation.calepinage.nb_rangees
    if abs(nb_plan - nb_dxf) > ECART_RANGEES_MAX:
        raise ErreurRecouvrementInsuffisant(
            f"Le plan montre {nb_plan} rangée(s) de tables et le DXF en porte "
            f"{nb_dxf} : le plan n'a pas été dressé sur ce calepinage. Vérifiez "
            "que le DXF HelioScope et le plan PDF décrivent la même version du "
            "projet."
        )
    if recouvrement < RECOUVREMENT_PLANCHER:
        raise ErreurRecouvrementInsuffisant(
            f"Une fois calées, les tables du plan et celles du DXF ne se "
            f"recouvrent qu'à {recouvrement:.1%} ({RECOUVREMENT_PLANCHER:.0%} au "
            f"moins), alors que leurs {nb_plan} rangées se répondent : le calage "
            "a trouvé la direction des rangées mais pas leur place."
        )
    fidelite = _part_du_plan_sur_les_tables(
        plan.fond, rangees, tables_dxf, echelle, sens, translation, rayon
    )
    if fidelite < FIDELITE_MIN:
        raise ErreurRecouvrementInsuffisant(
            f"{1 - fidelite:.0%} des tables que montre le plan ne tombent sur "
            f"aucune table du DXF ({FIDELITE_MIN:.0%} de concordance au moins, "
            f"recouvrement de Jaccard {recouvrement:.1%}). Le plan n'a pas été "
            "dressé sur ce calepinage : vérifiez que le DXF HelioScope et le plan "
            "PDF décrivent la même version du projet."
        )
    return CalagePlan(
        echelle_m_par_pt=echelle,
        rotation_deg=sens,
        translation=translation,
        pas_plan_pt=rangees.pas_pt,
        dispersion_pas_pt=rangees.dispersion_pt,
        pas_dxf_m=pas_dxf,
        nb_rangees_plan=len(rangees.centres),
        nb_rangees_dxf=implantation.calepinage.nb_rangees,
        echelle_le_long_m_par_pt=echelle_long,
        echelle_en_travers_m_par_pt=echelle_travers,
        recouvrement=recouvrement,
        fidelite=fidelite,
        isolats_ecartes=rangees.isolats_ecartes,
        recouvrement_retourne=essais[1][0],
        direction_plan_deg=rangees.direction_deg,
        direction_dxf_deg=direction_dxf,
    )


# ---------------------------------------------------------------------------
# Du plan au contrat : l'enceinte, les ouvrages, les portails
# ---------------------------------------------------------------------------

#: Le classeur des gabarits UNITe, ressource de l'outil. C'est une copie de
#: `exemples/Standards UNITe .xlsx`, la référence des cotes d'ouvrages, que
#: `tests/test_plan_pdf.py` garde identique à l'octet.
CHEMIN_GABARITS = Path(__file__).resolve().parent / "ressources" / "gabarits_unite.xlsx"

#: Variante du local de stockage : un dossier de déclaration préalable porte sur
#: moins de 3 MWc, c'est donc toujours celle-ci — P ≤ 5 MWc, un conteneur de
#: 20 pieds.
VARIANTE_LOCAL_DP = "Local de stockage matériel — P<=5MWc"

#: Volumes de citerne incendie du catalogue, en m³. Le plan dit « réserve
#: incendie » sans volume, et c'est le chef de projet qui tranche.
VOLUMES_CITERNE_M3 = (30, 60, 120, 240)

#: Longueur au delà de laquelle une interruption de la clôture n'est pas
#: refermée, même au droit d'un ouvrage, en mètres. À Bray, le poste de
#: livraison et le portail interrompent la clôture sur 16,5 m, le local
#: technique sur 9,6 m (mesuré le 23/09/2026).
INTERRUPTION_MAX_M = 40.0

#: Un ouvrage est au droit d'une interruption de la clôture quand son centre
#: tombe à moins de ceci du segment qui la referme, en mètres — ou de la
#: moitié de l'interruption, si elle est plus longue.
AU_DROIT_M = 5.0

#: Distance d'un ouvrage à la clôture en deçà de laquelle il est tenu pour posé
#: dessus, en mètres, et retrait au delà duquel la correction D8 n'est plus
#: proposée : à Gannay le poste de livraison a son centre à 7,8 m du tracé.
SUR_LA_CLOTURE_M = 1.0
RETRAIT_CORRIGEABLE_M = 15.0

#: Écart d'orientation admis entre un poste et la clôture qu'il longe, en
#: degrés, pour lui proposer de s'y poser.
PARALLELISME_DEG = 15.0

#: Distance au delà de laquelle un portail n'est plus tenu pour posé sur la
#: clôture, en mètres : il garde alors sa propre orientation, et le rapport le dit.
PORTAIL_SUR_LA_CLOTURE_M = 10.0

#: Segments d'un arc de débattement de portail. Relevé le 23/09/2026 sur le
#: calque du BE de Saint-Cyr (lot 2bis) : chaque portail y est fait de cinq
#: entités jointives — l'ouverture de 7 m sur la clôture, deux vantaux de
#: 3,5 m ouverts à angle droit vers l'intérieur de l'enceinte, et deux quarts
#: de cercle de 16 segments qui ramènent chaque vantail au milieu de
#: l'ouverture. Le portail du plan PDF se dessine de même.
SEGMENTS_ARC_PORTAIL = 16

#: Catégories de poste auxquelles la correction D8 se propose : ce sont les
#: postes de livraison qui ferment l'enceinte sur leur long pan, le raccordement
#: se faisant depuis l'extérieur.
POSTES_EN_LIMITE = ("pdl", "pdl_ptr")

#: Préfixe des corrections de mise en limite de propriété. Elles se calculent
#: sur l'emprise cadastrale, en Lambert 93, donc au calage courant — et non
#: dans la construction, qui ne connaît que le repère du DXF.
PREFIXE_EN_LIMITE = "poste_en_limite"

#: Écart à la limite de propriété en deçà duquel un poste y est déjà calé, en
#: mètres. Au delà de `RETRAIT_CORRIGEABLE_M`, l'y caler serait redessiner le
#: plan : rien ne se propose, et le rapport le dit.
SUR_LA_LIMITE_M = 0.1

#: Le couloir d'accès d'un portail, où un poste calé en limite ne se pose
#: pas : l'ouverture, élargie de `MARGE_PORTAIL_M` de part et d'autre, sur
#: `DEGAGEMENT_PORTAIL_M` vers l'extérieur de l'enceinte, d'où l'on arrive. À
#: Bray, le poste calé contre la limite se tenait entre la voie et le portail
#: (retour du chef de projet du 24/09/2026) : il glisse alors le long de la
#: limite, par pas de `PAS_GLISSEMENT_M`, jusqu'à `GLISSEMENT_MAX_M`.
DEGAGEMENT_PORTAIL_M = 10.0
MARGE_PORTAIL_M = 2.0
PAS_GLISSEMENT_M = 0.25
GLISSEMENT_MAX_M = 40.0

#: Préfixe de la correction qui recale la clôture sur la limite de propriété.
#: Comme les mises en limite d'un poste, elle se calcule sur l'emprise
#: cadastrale, en Lambert 93, donc au calage courant.
PREFIXE_CLOTURE_EN_LIMITE = "cloture_en_limite"

#: Les catégories qu'un recalage de clôture entraîne avec lui.
CATEGORIES_HAIE = ("haie", "haie_existante", "haie_a_renforcer")

#: Écart maximal à la clôture pour qu'une haie soit tenue pour la longer.
#:
#: 5 m : à Gannay, les deux haies qui bordent le site courent à 3,3 et 3,6 m
#: du grillage, d'un bout à l'autre ; les autres s'en tiennent à 44 m et plus.
#: Le seuil sépare les deux sans hésitation.
HAIE_LE_LONG_CLOTURE_M = 5.0

#: Longueur de haie hors emprise en deçà de laquelle on ne dit rien, en mètres.
#: Absorbe l'imprécision du tracé au plan ; un vrai débord se compte en
#: dizaines de mètres.
LONGUEUR_HAIE_NEGLIGEABLE_M = 2.0

#: Écart à la limite de propriété en deçà duquel un sommet de la clôture y est
#: ramené, en mètres. Mesuré le 24/09/2026 sur le plan de Bray : onze de ses
#: quatorze sommets sont à 0,2 à 2,2 m de la limite — le tracé la longe sans
#: la suivre —, deux autres à 4,8 et 5,0 m, et le dernier à 7,1 m. Porté de 3
#: à 5 m le 25/09/2026 : à 3 m, l'angle nord-ouest restait en retrait autour du
#: poste calé en limite, et l'enceinte partait l'y chercher.
CLOTURE_EN_LIMITE_M = 5.0

#: Ce qui fait qu'un segment de clôture longe la limite : au moins
#: `SEGMENT_LE_LONG_M` de long, et à moins de `CLOTURE_LE_LONG_DEG` d'elle. Un
#: sommet ne se recale que si l'un de ses deux segments la longe : les
#: décrochements de 80 cm que le tracé fait dans ses angles ne suffisent pas.
SEGMENT_LE_LONG_M = 5.0
CLOTURE_LE_LONG_DEG = 15.0

#: Deux sommets recalés à moins de ceci l'un de l'autre n'en font qu'un, en
#: mètres : les deux bouts d'un décrochement de 80 cm se projettent sur la
#: limite dans l'ordre inverse, et le tracé s'y croisait.
SOMMET_CONFONDU_M = 1.0

#: Surface au delà de laquelle le débord de la clôture hors de l'emprise est
#: dit, en mètres carrés. Une clôture recalée garde les côtés droits du plan :
#: là où la limite rentre, ils la franchissent. À Bray, 169 m² en trois langues
#: de 1,2 m de large au plus, contre 111 m² avant recalage.
DEBORD_DIT_M2 = 1.0

#: Écart au delà duquel un portail ne suit plus la clôture recalée, en mètres,
#: et le rapport le dit — mesuré sur les cinq traits de son symbole. À Bray,
#: avec le seuil à 5 m, l'un reste sur le tracé et l'autre s'en détache de
#: 0,83 m, moins d'un millimètre au 1/1000 : assez peu pour ne pas déplacer le
#: portail d'office, assez pour le dire.
PORTAIL_SUIT_LA_CLOTURE_M = 0.5


@dataclass
class ChoixDuPlan:
    """Ce que le plan ne dit pas, et que le chef de projet tranche.

    Aucune valeur par défaut : un volume de citerne ou une largeur de portail
    supposés se dessineraient parfaitement et ne se verraient jamais.
    """

    volume_citerne_m3: int | None = None
    largeur_portail_m: float | None = None
    #: Identifiants des corrections de plan acceptées (décision D8).
    corrections: tuple = ()

    def cle(self) -> tuple:
        return (self.volume_citerne_m3, self.largeur_portail_m, tuple(sorted(self.corrections)))


@dataclass(frozen=True)
class CorrectionProposee:
    """Une correction du plan que l'import offre, sans jamais l'appliquer d'office.

    Décision D8 : à Gannay, le poste de livraison était dessiné à 7,7 m en
    retrait de la clôture, alors qu'il en tient lieu sur sa longueur. C'est une
    correction du plan, pas une lecture.
    """

    identifiant: str
    categorie: str
    libelle: str
    #: Distance entre le long pan du poste et la clôture, en mètres.
    retrait_m: float
    raison: str
    #: Centre du poste une fois posé sur la clôture, en mètres du DXF.
    centre_corrige: tuple
    #: Direction de la clôture qu'il longe, en degrés dans le repère du DXF.
    direction_deg: float

    @property
    def intitule(self) -> str:
        return f"Poser « {self.libelle} » sur la clôture"


@dataclass(frozen=True)
class CorrectionDesPistes:
    """Les pistes qui longent la clôture, serrées contre elle (décision D8).

    À Gannay, le trait du plan passe à 2,1 m de la clôture sur trois côtés et à
    5,5 m sur le quatrième : la piste de 5 m menée dessus chevauche la clôture
    et mord sur 21 m² de tables. Demande du chef de projet du 23/09/2026 : la
    serrer plus près de la clôture, sans la toucher, pour dégager les tables.
    C'est une correction du plan : proposée, jamais appliquée d'office, et
    inscrite au contrat avec sa raison quand elle l'est.
    """

    identifiant: str
    categorie: str
    libelle: str
    #: Jeu laissé entre le bord des pistes et la clôture, en mètres.
    retrait_m: float
    raison: str

    @property
    def intitule(self) -> str:
        return f"Serrer les pistes contre la clôture, à {nombre_fr(self.retrait_m)} m"


def nombre_fr(valeur: float) -> str:
    """Un nombre écrit à la française, sans zéro inutile."""
    return f"{valeur:g}".replace(".", ",")


def _bouts_raccordes_confondus(axes: list) -> list:
    """Les tracés, leurs bouts mis bout à bout ramenés à un même point.

    Serrés chacun de son côté, deux bouts voisins d'un angle de la clôture se
    projetaient de part et d'autre de l'angle : 4,4 m les séparaient à Gannay,
    au-delà d'un raccord (`pistes.JONCTION_M`), et la boucle s'ouvrait. Ramenés
    d'abord à leur milieu, ils se projettent au même point.
    """
    from .pistes import JONCTION_M

    coords = [list(axe.ligne.coords) for axe in axes]
    ouverts = [
        i for i, c in enumerate(coords) if len(c) > 1 and math.dist(c[0], c[-1]) > 0.01
    ]
    for rang, i in enumerate(ouverts):
        for j in ouverts[rang + 1 :]:
            for bout_i in (0, -1):
                for bout_j in (0, -1):
                    p, q = coords[i][bout_i], coords[j][bout_j]
                    if math.dist(p, q) < JONCTION_M:
                        milieu = ((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0)
                        coords[i][bout_i] = coords[j][bout_j] = milieu
    return [
        AxePiste(axe.categorie, axe.libelle, LineString(c)) for axe, c in zip(axes, coords)
    ]


def _pistes_contre_la_cloture(axes: list, pistes: list, enceinte, tables) -> tuple:
    """La correction qui serre contre la clôture les pistes qui la longent, s'il y a lieu.

    Elle n'est proposée que si ces pistes, menées sur le trait du plan,
    chevauchent la clôture ou mordent sur des tables. Sa raison dit ce qu'elle
    règle et ce qu'elle ne peut pas régler : une table à moins de 5,5 m de la
    clôture reste sous une piste de 5 m, où qu'on la pose.
    """
    if enceinte is None or not axes:
        return None, axes
    serres = []
    for axe, net in zip(axes, _bouts_raccordes_confondus(axes)):
        ligne = serrer_contre(net.ligne, enceinte)
        serres.append(axe if ligne is None else AxePiste(axe.categorie, axe.libelle, ligne))
    deplaces = [i for i, (axe, serre) in enumerate(zip(axes, serres)) if serre is not axe]
    if not deplaces:
        return None, axes
    anneau = enceinte.exterior
    toutes_les_tables = unary_union(list(tables))

    def bilan(dessinees):
        surface = unary_union([dessinees[i].surface for i in deplaces])
        sur_tables = float(surface.intersection(toutes_les_tables).area) if tables else 0.0
        touchees = sum(1 for t in tables if t.intersection(surface).area > 0.01)
        return sur_tables, touchees, float(anneau.intersection(surface).length)

    tables_avant, _, cloture_avant = bilan(pistes)
    if tables_avant <= 0.5 and cloture_avant <= 0.5:
        return None, axes
    apres, _ = dessiner_pistes(serres)
    tables_apres, touchees_apres, cloture_apres = bilan(apres)

    avant = []
    if cloture_avant > 0.5:
        avant.append(f"chevauchent la clôture sur {cloture_avant:.0f} m")
    if tables_avant > 0.5:
        avant.append(f"recouvrent {tables_avant:.0f} m² de tables")
    ensuite = [
        "ne touchent plus la clôture"
        if cloture_apres < 0.01
        else f"la touchent encore sur {cloture_apres:.0f} m"
    ]
    if tables_apres > 0.05:
        ensuite.append(
            f"ne recouvrent plus que {nombre_fr(round(tables_apres, 1))} m² de tables, "
            f"les bouts de {touchees_apres} rangée(s) venus à moins de "
            f"{nombre_fr(LARGEUR_PISTE_M + JEU_CLOTURE_M)} m de la clôture : une piste "
            f"de {nombre_fr(LARGEUR_PISTE_M)} m ne peut y passer sans les toucher"
        )
    else:
        ensuite.append("ne recouvrent plus aucune table")
    libelles = sorted({axes[i].libelle for i in deplaces})
    correction = CorrectionDesPistes(
        identifiant="pistes_contre_cloture",
        categorie=", ".join(sorted({axes[i].categorie for i in deplaces})),
        libelle="Pistes le long de la clôture",
        retrait_m=JEU_CLOTURE_M,
        raison=(
            "Menées sur le trait du plan, les pistes qui longent la clôture ("
            + ", ".join(f"« {l} »" for l in libelles)
            + ") "
            + " et ".join(avant)
            + f". Serrées à {nombre_fr(JEU_CLOTURE_M)} m de la clôture — correction du "
            "plan —, elles "
            + " et ".join(ensuite)
            + "."
        ),
    )
    return correction, serres


@dataclass
class OuvragePlace:
    """Un ouvrage du plan, posé aux cotes de son gabarit, en mètres du DXF."""

    categorie: str
    libelle: str
    #: Libellé de la cote du catalogue UNITe, ou None si elle reste à trancher.
    gabarit: str | None
    longueur_m: float | None
    largeur_m: float | None
    centre: tuple
    direction_deg: float
    #: D'où vient l'orientation : le grand côté dessiné, ou la clôture voisine
    #: quand le repère dessiné est carré.
    orientation: str
    dessine_m: tuple
    correction: str | None = None
    #: D'où vient la variante du gabarit : le catalogue seul, la légende, ou
    #: le choix fait à l'écran — c'est ce que `projet.json` doit pouvoir dire.
    source_gabarit: str | None = None

    def geometrie(self) -> Polygon | None:
        if self.longueur_m is None or self.largeur_m is None:
            return None
        ux = math.cos(math.radians(self.direction_deg))
        uy = math.sin(math.radians(self.direction_deg))
        a, b = self.longueur_m / 2.0, self.largeur_m / 2.0
        cx, cy = self.centre
        return Polygon(
            [
                (cx + ux * a - uy * b, cy + uy * a + ux * b),
                (cx - ux * a - uy * b, cy - uy * a + ux * b),
                (cx - ux * a + uy * b, cy - uy * a - ux * b),
                (cx + ux * a + uy * b, cy + uy * a - ux * b),
            ]
        )


@dataclass
class Enceinte:
    """La clôture du plan en mètres du DXF, refermée au droit des ouvrages."""

    #: Les tracés de clôture tels que le plan les dessine.
    lignes: list
    #: L'anneau fermé, ponts compris, ou None s'il ne se referme pas.
    anneau: LineString | None
    #: Ce que l'anneau enjambe : longueur et ouvrages au droit de chaque pont.
    interruptions: list = field(default_factory=list)

    @property
    def polygone(self) -> Polygon | None:
        return Polygon(self.anneau.coords) if self.anneau is not None else None


def symbole_portail(
    centre: Point, direction_deg: float, largeur_m: float, vers_interieur: tuple
) -> list[LineString]:
    """Un portail à deux vantaux vu en plan, tel que le bureau d'études le dessine.

    Un simple segment posé sur la clôture ne se lisait pas comme le portail que
    la légende du dossier annonce : celle-ci montre les vantaux et leur
    débattement (`planches/legende.py`), parce que c'est ce que le calque du BE
    porte. Mesuré le 23/09/2026 sur le DP 2 de Gannay : un trait rouge épaissi
    sur la clôture, sous une légende à deux arcs.

    `vers_interieur` est la normale à la clôture qui entre dans l'enceinte :
    les vantaux s'ouvrent de ce côté, comme à Saint-Cyr.
    """
    rayon = largeur_m / 2.0
    ux, uy = math.cos(math.radians(direction_deg)), math.sin(math.radians(direction_deg))
    nx, ny = vers_interieur
    a = (centre.x - ux * rayon, centre.y - uy * rayon)
    b = (centre.x + ux * rayon, centre.y + uy * rayon)
    entites = [LineString([a, b])]
    for pivot, sens in ((a, 1.0), (b, -1.0)):
        entites.append(LineString([pivot, (pivot[0] + nx * rayon, pivot[1] + ny * rayon)]))
        # De la pointe du vantail ouvert au milieu de l'ouverture.
        arc = []
        for rang in range(SEGMENTS_ARC_PORTAIL + 1):
            t = math.radians(90.0 * rang / SEGMENTS_ARC_PORTAIL)
            arc.append(
                (
                    pivot[0] + rayon * (nx * math.cos(t) + sens * ux * math.sin(t)),
                    pivot[1] + rayon * (ny * math.cos(t) + sens * uy * math.sin(t)),
                )
            )
        entites.append(LineString(arc))
    return entites


def _normale_vers(enceinte: Polygon | None, centre: Point, direction_deg: float, repere: Point):
    """Normale à une direction, du côté de l'enceinte.

    Sur la clôture, le côté se juge au contact : un pas d'un demi-mètre doit
    entrer dans l'enceinte, ce qui vaut aussi pour une enceinte concave. Loin
    d'elle, ou sans enceinte fermée, il se juge au point de repère donné.
    """
    ux, uy = math.cos(math.radians(direction_deg)), math.sin(math.radians(direction_deg))
    nx, ny = -uy, ux
    if enceinte is not None and enceinte.exterior.distance(centre) < 0.01:
        if not enceinte.contains(Point(centre.x + nx * 0.5, centre.y + ny * 0.5)):
            nx, ny = -nx, -ny
    elif (repere.x - centre.x) * nx + (repere.y - centre.y) * ny < 0:
        nx, ny = -nx, -ny
    return nx, ny


def _direction_de_ligne(ligne: LineString, point: Point) -> float:
    """Direction du segment d'une ligne le plus proche d'un point, en degrés."""
    coords = list(ligne.coords)
    meilleur = min(
        zip(coords, coords[1:]),
        key=lambda s: LineString(s).distance(point) if s[0] != s[1] else math.inf,
    )
    return _dans_demi_tour(
        math.degrees(math.atan2(meilleur[1][1] - meilleur[0][1], meilleur[1][0] - meilleur[0][0]))
    )


def _trou_de_cloture(restes: list[LineString]) -> float | None:
    """Le plus petit écart entre deux bouts libres des tracés non refermés.

    C'est la mesure qui manquait au rapport : « la clôture ne se referme pas »
    laisse chercher partout, « il lui manque 6,0 m » désigne l'endroit. Mesuré
    le 02/10/2026 sur La Chapelle-sous-Aubenas : un seul tracé de 659,9 m dont
    les deux bouts sont à 6,02 m l'un de l'autre, soit 0,9 % du périmètre.
    """
    bouts = []
    for ligne in restes:
        sommets = list(ligne.coords)
        bouts.append(((id(ligne), 0), sommets[0]))
        bouts.append(((id(ligne), -1), sommets[-1]))
    ecarts = [
        math.dist(a[:2], b[:2])
        for i, (cle_a, a) in enumerate(bouts)
        for cle_b, b in bouts[i + 1 :]
        if cle_a != cle_b
    ]
    return min(ecarts) if ecarts else None


def _ouvrages_annonces_sans_forme(lecture, reperes_par_categorie) -> list[str]:
    """Les entrées de légende qui annoncent un ouvrage que la carte ne porte pas.

    Un trou de clôture que rien n'explique et un portail déclaré sans forme ne
    sont pas deux anomalies : c'est la même, vue deux fois. Les rapprocher dans
    un seul message évite au chef de projet d'avoir à faire le lien lui-même —
    il l'a fait trois fois cette semaine, et c'est trois fois de trop.
    """
    places = {
        repere.libelle
        for liste in reperes_par_categorie.values()
        for repere in liste
    }
    return sorted(
        entree.libelle
        for entree in lecture.legende
        if entree.categorie in CATEGORIES_OUVRAGES and entree.libelle not in places
    )


def _message_cloture_ouverte(restes: list[LineString], manquants: list[str]) -> str:
    """Ce qu'on dit d'une clôture qui ne se referme pas : la mesure et la cause.

    La phrase finale — « le dossier ne peut pas être généré » — est le signal
    que l'interface reconnaît pour remonter ce message en tête, avec les
    contrôles croisés bloquants (`app.MARQUEUR_BLOQUANT`). La changer ici sans
    la changer là-bas le renverrait au milieu des remarques ordinaires, où il
    arrivait dix-septième sur vingt-trois à La Chapelle-sous-Aubenas.
    """
    trou = _trou_de_cloture(restes)
    return (
        f"Clôture ouverte : {len(restes)} tracé(s) ne se referment sur aucun "
        "ouvrage"
        + (f", et il lui manque {trou:.1f} m" if trou is not None else "")
        + ". "
        + (
            "La légende annonce pourtant "
            + " ; ".join(f"« {n} »" for n in manquants)
            + " dont la carte ne porte aucune forme : c'est probablement là que "
            "la clôture s'interrompt. Ajoutez l'ouvrage au plan et refaites "
            "l'import. "
            if manquants
            else ""
        )
        + "Sans contour fermé, ni la surface clôturée ni la coupe A-A' ne se "
        "calculent, et le dossier ne peut pas être généré."
    )


def _refermer(lignes: list[LineString], centres_ouvrages: list, libelles: list):
    """Referme une clôture interrompue au droit d'un ouvrage, en le disant.

    À Bray, le chef de projet a dessiné la clôture comme elle sera bâtie : elle
    s'arrête au poste de livraison et au portail, reprend après, et s'arrête
    encore au local technique. Deux tracés ouverts ne font pas une enceinte, et
    la surface clôturée, l'étendue de la coupe et le cadrage des planches en
    ont besoin. Chaque interruption qu'enjambe un ouvrage est donc refermée
    d'un trait droit — et seulement celles-là : un trou sans ouvrage reste un
    trou, et le rapport le dit.
    """
    morceaux = [list(l.coords) for l in lignes]
    fermes = [m for m in morceaux if len(m) > 3 and math.dist(m[0], m[-1]) < 1e-9]
    ouverts = [m for m in morceaux if not (len(m) > 3 and math.dist(m[0], m[-1]) < 1e-9)]
    interruptions = []

    def au_droit(a, b) -> list:
        pont = LineString([a, b])
        longueur = pont.length
        rayon = max(AU_DROIT_M, 0.5 * longueur)
        return [
            libelle
            for centre, libelle in zip(centres_ouvrages, libelles)
            if pont.distance(Point(centre)) <= rayon
        ]

    while ouverts:
        candidats = []
        for i, m in enumerate(ouverts):
            for j, n in enumerate(ouverts):
                if j < i:
                    continue
                for bout_m in (0, -1):
                    for bout_n in (0, -1):
                        if i == j and bout_m == bout_n:
                            continue
                        if i == j and len(m) < 3:
                            continue
                        d = math.dist(m[bout_m], n[bout_n])
                        if d > INTERRUPTION_MAX_M:
                            continue
                        ouvrages = au_droit(m[bout_m], n[bout_n])
                        if ouvrages:
                            candidats.append((d, i, j, bout_m, bout_n, ouvrages))
        if not candidats:
            break
        d, i, j, bout_m, bout_n, ouvrages = min(candidats, key=lambda c: c[0])
        interruptions.append({"longueur_m": round(d, 2), "ouvrages": sorted(set(ouvrages))})
        if i == j:
            m = ouverts.pop(i)
            fermes.append(m + [m[0]])
            continue
        m, n = ouverts[i], ouverts[j]
        tete = m if bout_m == -1 else m[::-1]
        queue = n if bout_n == 0 else n[::-1]
        for k in sorted((i, j), reverse=True):
            ouverts.pop(k)
        ouverts.append(tete + queue)

    lignes_fermees = [LineString(m) for m in fermes]
    anneau = max(lignes_fermees, key=lambda l: Polygon(l.coords).area) if lignes_fermees else None
    return anneau, [LineString(m) for m in ouverts], len(lignes_fermees), interruptions


def _ouvrage(repere: Repere, calage: CalagePlan, gabarit, enceinte_ligne) -> OuvragePlace:
    """L'ouvrage d'un repère, posé aux cotes de son gabarit (décision D2)."""
    centre = calage.point_vers_dxf(*repere.centre)
    direction = calage.direction_vers_dxf(repere.direction_deg)
    orientation = "grand côté dessiné"
    if repere.orientation_ambigue and enceinte_ligne is not None:
        # Un repère carré ne dit pas où va le grand côté : on le pose parallèle
        # à la clôture la plus proche, comme le sont tous les ouvrages des deux
        # plans d'essai — et le rapport le dit.
        direction = _direction_de_ligne(enceinte_ligne, Point(centre))
        orientation = "clôture voisine (repère carré au plan)"
    longueur = largeur = None
    if gabarit is not None:
        cotes = sorted((gabarit.longueur_m, gabarit.largeur_m), reverse=True)
        longueur, largeur = cotes
    return OuvragePlace(
        categorie=repere.categorie,
        libelle=repere.libelle,
        gabarit=gabarit.ouvrage if gabarit is not None else None,
        longueur_m=longueur,
        largeur_m=largeur,
        centre=centre,
        direction_deg=direction,
        orientation=orientation,
        dessine_m=(
            repere.longueur_dessinee * calage.echelle_m_par_pt,
            repere.largeur_dessinee * calage.echelle_m_par_pt,
        ),
    )


@dataclass(frozen=True)
class CorrectionEnLimite:
    """Un poste à caler en limite de propriété, dans l'enceinte, qu'il ferme.

    Instructions du chef de projet du 24/09/2026 : le poste de livraison se pose
    à l'intérieur de la clôture, en limite de propriété, et sur sa longueur il
    tient lui-même lieu de clôture, comme à Gannay. À Bray, il était dessiné
    hors de la clôture, à 1,8 m de la limite et tourné par rapport à elle.
    Comme la correction D8, elle se propose et ne s'applique que cochée.
    """

    identifiant: str
    categorie: str
    libelle: str
    #: Écart entre le poste et la limite de propriété, en mètres.
    retrait_m: float
    raison: str
    #: Le poste recalé, en Lambert 93.
    geometrie_l93: BaseGeometry

    @property
    def intitule(self) -> str:
        return f"Caler « {self.libelle} » en limite de propriété, dans l'enceinte"


def _contre_la_limite(poste: Polygon, limite, emprise: BaseGeometry):
    """Le poste tourné pour longer la limite, puis poussé jusqu'à la toucher.

    La limite se prend sur la longueur du poste, et non sur un seul segment : à
    Bray, elle fait un coude de 2,6° sous le poste, et un alignement sur le seul
    segment voisin le faisait déborder de l'emprise. Le poste glisse vers elle
    jusqu'au dernier point où il reste entier dans l'emprise. Rend le poste
    calé, ou None s'il n'y tient pas, et l'écart d'orientation en degrés.
    """
    _, direction_poste, longueur, _ = _rectangle_minimal(poste)
    # Les abscisses se prennent modulo le tour de l'anneau, qui est fermé.
    abscisse = limite.project(poste.centroid)
    a = limite.interpolate((abscisse - longueur / 2.0) % limite.length)
    b = limite.interpolate((abscisse + longueur / 2.0) % limite.length)
    ecart = _dans_demi_tour(math.degrees(math.atan2(b.y - a.y, b.x - a.x)) - direction_poste)
    tourne = affinity.rotate(poste, ecart, origin="centroid")
    # La normale à la corde, tournée vers la limite.
    corde = math.hypot(b.x - a.x, b.y - a.y)
    nx, ny = -(b.y - a.y) / corde, (b.x - a.x) / corde
    centre = tourne.centroid
    proche = limite.interpolate(limite.project(centre))
    if (proche.x - centre.x) * nx + (proche.y - centre.y) * ny < 0:
        nx, ny = -nx, -ny

    def place(pas: float):
        return affinity.translate(tourne, pas * nx, pas * ny)

    # Par dichotomie : `dedans_m` reste dans l'emprise, `dehors_m` en déborde.
    ecart_limite = poste.distance(limite)
    dedans_m, dehors_m = (0.0, ecart_limite + longueur) if emprise.contains(place(0.0)) else (
        -(longueur + RETRAIT_CORRIGEABLE_M),
        0.0,
    )
    if not emprise.contains(place(dedans_m)) or emprise.contains(place(dehors_m)):
        return None, ecart
    for _ in range(40):
        milieu = (dedans_m + dehors_m) / 2.0
        if emprise.contains(place(milieu)):
            dedans_m = milieu
        else:
            dehors_m = milieu
    return place(dedans_m), ecart


def _couloir_de_portail(ouverture: LineString, enceinte=None) -> Polygon:
    """Ce qui s'étend devant un portail, du côté d'où l'on arrive.

    L'ouverture, élargie de `MARGE_PORTAIL_M` de part et d'autre, sur
    `DEGAGEMENT_PORTAIL_M` vers l'extérieur de l'enceinte ; des deux côtés
    quand l'enceinte ne se referme pas.
    """
    (x0, y0), (x1, y1) = ouverture.coords[0], ouverture.coords[-1]
    longueur = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / longueur, (y1 - y0) / longueur
    m = MARGE_PORTAIL_M
    debut, fin = (x0 - m * ux, y0 - m * uy), (x1 + m * ux, y1 + m * uy)

    def cote(nx: float, ny: float) -> Polygon:
        d = DEGAGEMENT_PORTAIL_M
        return Polygon(
            [debut, fin, (fin[0] + d * nx, fin[1] + d * ny), (debut[0] + d * nx, debut[1] + d * ny)]
        )

    nx, ny = -uy, ux
    if enceinte is None:
        return cote(nx, ny).union(cote(-nx, -ny))
    milieu = Point((x0 + x1) / 2.0 + 0.5 * nx, (y0 + y1) / 2.0 + 0.5 * ny)
    return cote(-nx, -ny) if enceinte.contains(milieu) else cote(nx, ny)


def _correction_en_limite(
    poste_l93: Polygon, emprise: BaseGeometry, ouvrage, rang: int, enceinte_l93=None, couloirs=()
):
    """La mise en limite de propriété d'un poste, en Lambert 93, et ce qu'il faut en dire.

    Le poste se cale contre la limite (`_contre_la_limite`). S'il se tient alors
    dans le couloir d'accès d'un portail, il glisse le long de la limite, à
    l'écart du portail, jusqu'à le dégager. `couloirs` porte, pour chaque
    portail, son libellé et son couloir (`_couloir_de_portail`). Rend la
    correction, ou None, et une note quand le poste n'est pas en limite sans
    pouvoir y être calé d'office.
    """
    limite = min(
        (polygone.exterior for polygone in getattr(emprise, "geoms", [emprise])),
        key=lambda anneau: anneau.distance(poste_l93),
    )
    retrait = poste_l93.distance(limite)
    dedans = poste_l93.intersection(emprise).area / poste_l93.area
    dans_l_enceinte = enceinte_l93 is None or poste_l93.within(enceinte_l93.buffer(0.01))
    devant = [libelle for libelle, couloir in couloirs if poste_l93.intersects(couloir)]
    if retrait <= SUR_LA_LIMITE_M and dedans >= 0.999 and dans_l_enceinte and not devant:
        return None, None
    nom = f"« {ouvrage.libelle} »"
    if retrait > RETRAIT_CORRIGEABLE_M:
        return None, (
            f"{nom} est à {retrait:.1f} m de la limite de propriété : un poste de "
            "livraison s'y pose, entièrement dans l'emprise. Trop loin pour l'y "
            "caler d'office : c'est au plan de le placer."
        )
    cale, ecart = _contre_la_limite(poste_l93, limite, emprise)
    if abs(ecart) > PARALLELISME_DEG:
        return None, (
            f"{nom} est tourné de {abs(ecart):.0f}° par rapport à la limite de "
            "propriété qu'il borde : il ne la longe pas, et ne s'y cale pas "
            "d'office. C'est au plan de le placer."
        )
    if cale is None:
        return None, (
            f"{nom} n'est pas en limite de propriété, et ne tient pas entier dans "
            "l'emprise en la longeant : le poste est au droit d'un angle, ou la "
            "limite trop courte. C'est au plan de le placer."
        )

    glissement, degages = 0.0, []
    genants = [(libelle, couloir) for libelle, couloir in couloirs if cale.intersects(couloir)]
    if genants:
        degages = [libelle for libelle, _ in genants]
        genant = unary_union([couloir for _, couloir in genants])
        # La tangente à la limite au droit du poste, tournée à l'écart du portail.
        abscisse = limite.project(cale.centroid)
        a = limite.interpolate((abscisse - 1.0) % limite.length)
        b = limite.interpolate((abscisse + 1.0) % limite.length)
        norme = math.hypot(b.x - a.x, b.y - a.y)
        tx, ty = (b.x - a.x) / norme, (b.y - a.y) / norme
        # Le sens se lit sur les centres : comparer les distances au couloir ne
        # départage rien tant que le poste y empiète des deux côtés — à Bray, il
        # glissait vers l'angle, et le portail qui s'y tient.
        centre, milieu_couloir = cale.centroid, genant.centroid
        if (centre.x - milieu_couloir.x) * tx + (centre.y - milieu_couloir.y) * ty < 0:
            tx, ty = -tx, -ty
        for rang_pas in range(1, int(GLISSEMENT_MAX_M / PAS_GLISSEMENT_M) + 1):
            pas = rang_pas * PAS_GLISSEMENT_M
            candidat, ecart_candidat = _contre_la_limite(
                affinity.translate(cale, pas * tx, pas * ty), limite, emprise
            )
            if (
                candidat is not None
                and abs(ecart_candidat) <= PARALLELISME_DEG
                and not any(candidat.intersects(couloir) for _, couloir in couloirs)
            ):
                cale, glissement = candidat, pas
                break
        else:
            return None, (
                f"{nom}, calé en limite de propriété, se tiendrait devant "
                + ", ".join(f"« {libelle} »" for libelle in degages)
                + f", sans place pour s'en écarter à moins de {GLISSEMENT_MAX_M:.0f} m "
                "le long de la limite. C'est au plan de le placer."
            )

    etat = (
        f"à {retrait:.1f} m de la limite de propriété"
        if dedans >= 0.999
        else f"à {100 * (1 - dedans):.0f} % hors de l'emprise"
    ) + ("" if dans_l_enceinte else ", hors de l'enceinte")
    degagement = (
        f" Il glisse de {glissement:.1f} m le long de la limite pour ne pas se tenir "
        "devant " + ", ".join(f"« {libelle} »" for libelle in degages) + "."
        if glissement
        else ""
    )
    return CorrectionEnLimite(
        identifiant=f"{PREFIXE_EN_LIMITE}:{ouvrage.categorie}:{rang}",
        categorie=ouvrage.categorie,
        libelle=ouvrage.libelle,
        retrait_m=retrait,
        raison=(
            f"{nom} est dessiné {etat}, tourné de {abs(ecart):.0f}° par rapport à "
            "la limite. Un poste de livraison se pose en limite de propriété, à "
            "l'intérieur de la clôture, et tient lui-même lieu de clôture sur sa "
            "longueur (instructions du 24/09/2026) : calé, il longe la limite, "
            "et l'enceinte le rejoint à ses pignons."
            + degagement
            + " C'est une correction du plan, pas une lecture."
        ),
        geometrie_l93=cale,
    ), None


@dataclass(frozen=True)
class CorrectionClotureEnLimite:
    """La clôture ramenée sur la limite de propriété là où elle la longe de près.

    Instruction du chef de projet du 24/09/2026 : à Bray, la clôture est
    dessinée à un ou deux mètres à l'intérieur de la limite de parcelle, alors
    qu'elle la suivra. Le poste calé en limite s'en trouvait détaché, et
    l'enceinte partait le chercher. Comme la mise en limite d'un poste, elle se
    propose et ne s'applique que cochée.
    """

    identifiant: str
    libelle: str
    #: Le plus grand écart rattrapé, en mètres.
    retrait_m: float
    #: Le linéaire de clôture que le recalage déplace, en mètres.
    lineaire_m: float
    raison: str
    #: L'enceinte recalée, en Lambert 93.
    geometrie_l93: Polygon
    categorie: str = "cloture"

    @property
    def intitule(self) -> str:
        return f"Recaler « {self.libelle} » sur la limite de propriété"


def _cloture_sur_la_limite(enceinte_l93: Polygon, emprise: BaseGeometry, libelle: str):
    """La clôture recalée sur la limite de propriété, et ce qu'il faut en dire.

    Un sommet se ramène sur la limite s'il en est à moins de
    `CLOTURE_EN_LIMITE_M` et si l'un de ses deux segments la longe : un sommet
    isolé qui passe près d'elle sans la suivre resterait où le plan l'a mis.
    Rend la correction, ou None, et une note quand le tracé recalé se croise.
    """
    anneaux = [polygone.exterior for polygone in getattr(emprise, "geoms", [emprise])]

    def sur_la_limite(point: Point) -> Point:
        anneau = min(anneaux, key=lambda a: a.distance(point))
        return nearest_points(anneau, point)[0]

    def direction_limite(point: Point) -> float:
        return _direction_de_ligne(min(anneaux, key=lambda a: a.distance(point)), point)

    sommets = list(enceinte_l93.exterior.coords)[:-1]
    nombre = len(sommets)
    # Les segments qui longent la limite : c'est eux qui donnent à leurs
    # sommets le droit d'y être ramenés.
    le_long = []
    for a, b in zip(sommets, sommets[1:] + sommets[:1]):
        segment = LineString([a, b])
        milieu = segment.interpolate(0.5, normalized=True)
        ecart = _dans_demi_tour(
            direction_limite(milieu)
            - math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        )
        le_long.append(
            segment.length >= SEGMENT_LE_LONG_M and abs(ecart) <= CLOTURE_LE_LONG_DEG
        )

    places, ecarts = [], []
    for rang, sommet in enumerate(sommets):
        point = Point(sommet)
        distance = min(anneau.distance(point) for anneau in anneaux)
        if distance <= CLOTURE_EN_LIMITE_M and (le_long[rang] or le_long[rang - 1]):
            sur = sur_la_limite(point)
            places.append((sur.x, sur.y))
            ecarts.append(distance)
        else:
            places.append(sommet)
            ecarts.append(0.0)
    if not any(ecarts):
        return None, None

    # Deux sommets que le recalage confond n'en font qu'un : le décrochement
    # qu'ils portaient n'existe pas sur la limite, et le garder croisait le tracé.
    gardes, retenus = [], []
    for sommet, ecart in zip(places, ecarts):
        if gardes and ecart and retenus[-1] and math.dist(sommet, gardes[-1]) < SOMMET_CONFONDU_M:
            continue
        gardes.append(sommet)
        retenus.append(ecart)
    recalee = Polygon(gardes)
    if not recalee.is_valid or recalee.geom_type != "Polygon":
        from shapely.validation import explain_validity

        return None, (
            f"« {libelle} » recalée sur la limite de propriété donnerait un tracé "
            f"qui se croise ({explain_validity(recalee)}) : rien n'est proposé, "
            "c'est au plan de la tracer."
        )

    def recales(anneau_ferme: list) -> list:
        """Les segments dont les deux bouts ont été ramenés sur la limite."""
        return [
            LineString([a, b])
            for (a, ea), (b, eb) in zip(
                anneau_ferme, anneau_ferme[1:] + anneau_ferme[:1]
            )
            if ea and eb
        ]

    def ventre(segments: list) -> float:
        """Ce que le tracé droit laisse entre lui et la limite, au plus, en mètres.

        Un sommet ramené sur la limite ne met pas le segment qui en part
        dessus : le tracé garde les quatorze côtés que le plan lui donne, quand
        la limite de Bray en compte trente-trois. Là où elle fait un ventre, la
        clôture le coupe — comme elle le coupait déjà.
        """
        return max(
            (
                min(anneau.distance(s.interpolate(i / 20.0, normalized=True)) for anneau in anneaux)
                for s in segments
                for i in range(21)
            ),
            default=0.0,
        )

    lineaire = sum(s.length for s in recales(list(zip(gardes, retenus))))
    dehors_avant = enceinte_l93.difference(emprise).area
    dehors_apres = recalee.difference(emprise).area
    ventre_apres = ventre(recales(list(zip(gardes, retenus))))
    ventre_avant = ventre(recales(list(zip(sommets, ecarts))))
    bouges = [e for e in ecarts if e]
    confondus = len(places) - len(gardes)
    return CorrectionClotureEnLimite(
        identifiant=f"{PREFIXE_CLOTURE_EN_LIMITE}:cloture",
        libelle=libelle,
        retrait_m=max(bouges),
        lineaire_m=lineaire,
        raison=(
            f"« {libelle} » longe la limite de propriété sans la suivre : "
            f"{len(bouges)} de ses {nombre} sommets s'en écartent de "
            f"{min(bouges):.1f} à {max(bouges):.1f} m, du côté intérieur comme "
            f"elle sera bâtie. Les y ramener déplace {lineaire:.0f} m de tracé et "
            f"porte la surface clôturée de {enceinte_l93.area / 1e4:.2f} à "
            f"{recalee.area / 1e4:.2f} ha"
            + (
                f", {confondus} décrochement(s) de moins de "
                f"{SOMMET_CONFONDU_M:.0f} m disparaissant avec eux"
                if confondus
                else ""
            )
            + f". Le reste du tracé ne bouge pas : au delà de "
            f"{CLOTURE_EN_LIMITE_M:.0f} m, un retrait est un choix de tracé, pas "
            "une imprécision."
            + (
                " Le tracé garde les côtés droits du plan, quand la limite en "
                "compte davantage : là où elle fait un ventre, il s'en écarte "
                f"encore de {ventre_apres:.1f} m ({ventre_avant:.1f} m avant), et "
                f"il la franchit sur {dehors_apres:.0f} m² ({dehors_avant:.0f} m² "
                "avant) là où elle rentre. À vérifier sur la planche DP 2."
                if ventre_apres > CLOTURE_EN_LIMITE_M or dehors_apres > DEBORD_DIT_M2
                else ""
            )
            + " C'est une correction du plan, pas une lecture."
        ),
        geometrie_l93=recalee,
    ), None


def _controle_des_haies(traces_l93, cloture: Polygon | None, emprise) -> tuple:
    """Les haies du plan qui n'ont pas leur place sur une planche de DP.

    Décision du chef de projet du 30/09/2026 : **le plan PDF ne porte que les
    haies de l'emprise du projet, en bord de clôture**. Celles qui s'en
    écartent relèvent de l'aménagement paysager et vont à la notice, pas au
    plan — un dossier qui dessine des plantations sur des parcelles dont on
    n'a pas la maîtrise foncière se le fait reprocher à l'instruction.

    C'est aussi ce qui rend le recalage tenable : une haie du bord de clôture
    suit la clôture, et il n'y a plus de bloc qui dépasse.

    Rend (hors_emprise, loin_de_la_cloture), deux listes de (libellé, mesure).
    """
    hors_emprise, loin = [], []
    for categorie, libelle, ligne in traces_l93:
        if categorie not in CATEGORIES_HAIE:
            continue
        if emprise is not None and not emprise.is_empty:
            dehors = ligne.difference(emprise).length
            if dehors > LONGUEUR_HAIE_NEGLIGEABLE_M:
                hors_emprise.append((libelle, dehors))
                continue
        if cloture is not None:
            ecart = cloture.exterior.distance(ligne)
            if ecart > HAIE_LE_LONG_CLOTURE_M:
                loin.append((libelle, ecart))
    return hors_emprise, loin


def _haies_qui_suivent(traces_l93, avant: Polygon, apres: Polygon) -> dict:
    """Les haies qui longent la clôture, et où elles vont quand elle bouge.

    Instruction du chef de projet du 30/09/2026, et elle corrige la mienne :
    ramener une haie sur la limite de propriété est risqué, parce que **c'est
    souvent la clôture qui y est**, la haie courant un peu en retrait. Mesuré
    à Gannay : le grillage touche la limite, et les haies sont trois mètres
    plus loin. Les y ramener les aurait posées sur le grillage.

    Ce qui est juste, c'est de garder leur écart : une haie qui longe la
    clôture sur toute sa longueur suit son déplacement, et reste à la distance
    que le plan lui donne. Elle se déplace **en bloc** — la translation
    moyenne du grillage sous ses sommets — pour ne pas la déformer : une haie
    dont un bout longe le grillage et l'autre s'en va à vingt mètres ne bouge
    pas du tout, faute de savoir ce que le plan voulait.

    Rend {rang du tracé : haie déplacée}.
    """
    suivies = {}
    for rang, (categorie, _libelle, ligne) in enumerate(traces_l93):
        if categorie not in CATEGORIES_HAIE:
            continue
        sommets = list(ligne.coords)
        points = [Point(s) for s in sommets]
        if any(
            avant.exterior.distance(point) > HAIE_LE_LONG_CLOTURE_M for point in points
        ):
            continue
        ecarts = []
        for point in points:
            sur_avant = nearest_points(avant.exterior, point)[0]
            sur_apres = nearest_points(apres.exterior, point)[0]
            ecarts.append((sur_apres.x - sur_avant.x, sur_apres.y - sur_avant.y))
        dx = sum(e[0] for e in ecarts) / len(ecarts)
        dy = sum(e[1] for e in ecarts) / len(ecarts)
        if math.hypot(dx, dy) < 1e-9:
            continue
        suivies[rang] = LineString([(x + dx, y + dy) for x, y in sommets])
    return suivies


def _enceinte_jusqu_au_poste(enceinte: Polygon, poste: Polygon) -> Polygon:
    """L'enceinte prolongée jusqu'au poste, qui en tient lieu de clôture sur sa longueur.

    La clôture rejoint les pignons du poste à angle droit : l'enceinte s'étend
    sur le poste et sur la bande qui le sépare d'elle, sur la seule longueur du
    poste. Une enveloppe convexe partait en biais dans l'angle de la clôture de
    Bray, et avalait le bout de l'ouverture du portail voisin (mesuré le
    24/09/2026). Un poste déjà dans l'enceinte la laisse telle quelle.
    """
    if poste.within(enceinte.buffer(0.01)):
        return enceinte
    coins = list(poste.exterior.coords)[:-1]
    # Les deux coins tournés vers l'enceinte, et la direction qui y mène,
    # perpendiculaire au long pan du poste.
    interieurs = sorted(coins, key=lambda c: Point(c).distance(enceinte))[:2]
    (xa, ya), (xb, yb) = interieurs
    longueur = math.hypot(xb - xa, yb - ya)
    nx, ny = -(yb - ya) / longueur, (xb - xa) / longueur
    cx, cy = poste.centroid.x, poste.centroid.y
    if ((xa + xb) / 2.0 - cx) * nx + ((ya + yb) / 2.0 - cy) * ny < 0:
        nx, ny = -nx, -ny
    portee = poste.distance(enceinte) + 2.0 * math.hypot(*_rectangle_minimal(poste)[2:])

    def rabattu(coin):
        rayon = LineString([coin, (coin[0] + portee * nx, coin[1] + portee * ny)])
        touche = rayon.intersection(enceinte.exterior)
        points = [q for q in getattr(touche, "geoms", [touche]) if not q.is_empty]
        if not points:
            return nearest_points(enceinte.exterior, Point(coin))[0]
        return min(points, key=lambda q: Point(coin).distance(q))

    pieds = [rabattu(c) for c in interieurs]
    raccord = Polygon(
        [interieurs[0], (pieds[0].x, pieds[0].y), (pieds[1].x, pieds[1].y), interieurs[1]]
    ).buffer(0)
    prolongee = enceinte.union(raccord).union(poste)
    if prolongee.geom_type == "MultiPolygon":
        prolongee = max(prolongee.geoms, key=lambda g: g.area)
    return prolongee


def _correction_proposee(ouvrage: OuvragePlace, rang: int, anneau: LineString | None):
    """La correction D8 d'un poste posé en retrait de la clôture, s'il y a lieu."""
    if anneau is None or ouvrage.categorie not in POSTES_EN_LIMITE:
        return None
    if ouvrage.largeur_m is None:
        return None
    centre = Point(ouvrage.centre)
    distance = anneau.distance(centre)
    retrait = distance - ouvrage.largeur_m / 2.0
    if retrait <= SUR_LA_CLOTURE_M or retrait > RETRAIT_CORRIGEABLE_M:
        return None
    direction_cloture = _direction_de_ligne(anneau, centre)
    if abs(_dans_demi_tour(direction_cloture - ouvrage.direction_deg)) > PARALLELISME_DEG:
        return None
    sur_la_ligne = nearest_points(anneau, centre)[0]
    # Le long pan affleure le tracé : le centre s'arrête à une demi-largeur de
    # la clôture, du côté où il était.
    vx, vy = centre.x - sur_la_ligne.x, centre.y - sur_la_ligne.y
    norme = math.hypot(vx, vy) or 1.0
    centre_corrige = (
        sur_la_ligne.x + vx / norme * ouvrage.largeur_m / 2.0,
        sur_la_ligne.y + vy / norme * ouvrage.largeur_m / 2.0,
    )
    return CorrectionProposee(
        identifiant=f"poste_sur_cloture:{ouvrage.categorie}:{rang}",
        categorie=ouvrage.categorie,
        libelle=ouvrage.libelle,
        retrait_m=retrait,
        raison=(
            f"« {ouvrage.libelle} » est dessiné en retrait de la clôture et "
            f"parallèle à elle : son centre à {distance:.1f} m du tracé, son long "
            f"pan à {retrait:.1f} m une fois le poste à ses cotes. Un poste de "
            "livraison ferme d'ordinaire l'enceinte sur son long pan, la clôture "
            "s'arrêtant à ses pignons. L'y poser est une correction du plan, pas "
            "une lecture."
        ),
        centre_corrige=centre_corrige,
        direction_deg=direction_cloture,
    )


@dataclass
class Construction:
    """Le plan traduit en géométries du repère DXF, avant projection."""

    traces: list
    enceinte: Enceinte | None
    ouvrages: list
    #: Un couple (libellé, entités) par portail : les cinq traits de son symbole.
    portails: list
    corrections_proposees: list
    corrections_appliquees: list
    gabarits: list
    notes: list
    #: Ce qui reste à trancher pour dimensionner les ouvrages du plan.
    manques: list = field(default_factory=list)
    #: Les pistes, en bandes de 5 m aux virages arrondis (`pistes.PisteDessinee`).
    pistes: list = field(default_factory=list)
    #: Un triplet (libellé, largeur, d'où elle vient) par portail posé.
    largeurs_portails: list = field(default_factory=list)


def _gabarit_de(categorie: str, catalogue: dict, choix: ChoixDuPlan, cote: dict | None = None):
    """Cote du catalogue pour une catégorie, ce qui manque, et d'où vient la variante.

    Le volume d'une réserve se prend à la légende quand elle le porte
    (instruction du chef de projet du 23/09/2026), au choix fait à l'écran
    sinon. Un volume de légende que le catalogue n'a pas n'est pas retenu.
    """
    from .contrat import LIBELLES_COTES, decoder_cote

    source = "gabarit UNITe"
    if categorie == "bache_incendie":
        volume = (cote or {}).get("volume_citerne_m3")
        if volume in VOLUMES_CITERNE_M3:
            source = "volume porté en légende"
        else:
            volume = choix.volume_citerne_m3
            source = "volume choisi à l'écran"
        if volume is None:
            return None, "le volume de la réserve incendie", None
        libelle = f"Citerne incendie — {volume}"
    elif categorie == "local_technique":
        libelle = VARIANTE_LOCAL_DP
    else:
        libelles = LIBELLES_COTES.get(categorie, ())
        if len(libelles) != 1:
            return None, f"le gabarit de « {categorie} »", None
        libelle = libelles[0]
    brut = catalogue.get(libelle)
    if brut is None:
        raise ErreurPlanPDF(
            f"Le gabarit « {libelle} » manque au classeur des gabarits UNITe "
            f"({CHEMIN_GABARITS.name}) : l'ouvrage « {categorie} » ne peut pas "
            "être dimensionné."
        )
    return decoder_cote(brut), None, source


def construire(
    lecture: PlanPDF,
    calage: CalagePlan,
    choix: ChoixDuPlan,
    catalogue: dict,
    tables: tuple = (),
) -> Construction:
    """Les tracés, l'enceinte, les ouvrages et les portails, en mètres du DXF.

    `tables` sont celles du lot 2, dans le même repère : ce que les pistes
    recouvrent se mesure sur elles.
    """
    notes: list[str] = []
    traces_dxf: list = []
    cloture: list = []
    axes_de_pistes: list = []
    # Une forme de piste plus épaisse qu'une piste est une surface — la
    # plateforme existante de Bray, 99 × 39 m : elle garde sa forme, et n'est
    # pas réduite à l'axe d'une bande de 5 m.
    epaisseur_pt = EPAISSEUR_SURFACE_M / calage.echelle_m_par_pt
    surfaces_de_piste = {}
    for categorie in CATEGORIES_PISTES:
        for element in lecture.elements_de(categorie):
            forme = (
                _polygone_de(element.objet.principal)
                if element.objet.nature == "aplat"
                else None
            )
            if forme is not None and 2.0 * forme.area / forme.length > epaisseur_pt:
                surfaces_de_piste[id(element.objet)] = (categorie, element.entree.libelle, forme)
    for categorie in CATEGORIES_TRACEES:
        lus, remarques = traces(lecture, categorie, frozenset(surfaces_de_piste))
        notes.extend(remarques)
        for trace in lus:
            ligne = calage.vers_dxf(trace.ligne)
            if categorie == "cloture":
                cloture.append(ligne)
            elif categorie in CATEGORIES_PISTES:
                axes_de_pistes.append(AxePiste(trace.categorie, trace.libelle, ligne))
            else:
                traces_dxf.append((trace.categorie, trace.libelle, ligne))
    for categorie, libelle, forme in surfaces_de_piste.values():
        notes.append(
            f"« {libelle} » : une surface de "
            f"{forme.area * calage.echelle_m_par_pt ** 2:.0f} m², plus épaisse "
            "qu'une piste, est gardée telle que dessinée, et non réduite à l'axe "
            f"d'une piste de {LARGEUR_PISTE_M:.0f} m."
        )
        for morceau in getattr(forme, "geoms", [forme]):
            traces_dxf.append((categorie, libelle, calage.vers_dxf(morceau)))
    for categorie in CATEGORIES_SURFACES:
        for element in lecture.elements_de(categorie):
            forme = _polygone_de(element.objet.principal)
            if forme is None:
                centre = MultiPoint(
                    [p for c in element.objet.principal.sous_chemins for p in c]
                ).centroid
                notes.append(
                    f"« {element.entree.libelle} » : une forme vers ({centre.x:.0f}, "
                    f"{centre.y:.0f}) "
                    "pt n'est pas fermée et ne délimite aucune surface : elle n'est "
                    "pas importée. Refermez-la sur le plan."
                )
                continue
            for morceau in getattr(forme, "geoms", [forme]):
                traces_dxf.append((categorie, element.entree.libelle, calage.vers_dxf(morceau)))
    importables = set(CATEGORIES_IMPORTABLES)
    for entree in lecture.legende:
        formes = [x for x in lecture.elements if x.entree is entree]
        if entree.categorie and entree.categorie not in importables and formes:
            notes.append(
                f"« {entree.libelle} » est apparié à « {entree.categorie} », qu'un "
                f"plan PDF ne sait pas importer : ses {len(formes)} forme(s) ne sont "
                "pas au contrat. S'importent d'un plan PDF la clôture, les haies, "
                "les pistes, les ouvrages et la végétation en place."
            )
    # Le plan donne le tracé et le type de chaque piste ; la piste elle-même
    # se dessine comme sur un vrai plan : 5 m de large, virages arrondis. Ses
    # notes attendent de savoir si la correction des pistes est appliquée.
    pistes, notes_pistes = dessiner_pistes(axes_de_pistes)

    reperes_par_categorie = {c: reperes(lecture, c) for c in CATEGORIES_OUVRAGES}
    centres = []
    libelles = []
    for liste in reperes_par_categorie.values():
        for repere in liste:
            centres.append(calage.point_vers_dxf(*repere.centre))
            libelles.append(repere.libelle)

    enceinte = None
    if cloture:
        anneau, restes, nb_anneaux, interruptions = _refermer(cloture, centres, libelles)
        enceinte = Enceinte(lignes=cloture, anneau=anneau, interruptions=interruptions)
        for pont in interruptions:
            notes.append(
                f"Clôture interrompue sur {pont['longueur_m']:.1f} m au droit de "
                f"{', '.join(pont['ouvrages'])} : refermée d'un trait droit pour "
                "la surface clôturée et l'étendue de la coupe, comme le plan la "
                "dessine."
            )
        if restes:
            notes.append(
                _message_cloture_ouverte(
                    restes,
                    _ouvrages_annonces_sans_forme(lecture, reperes_par_categorie),
                )
            )
            enceinte.anneau = None
            enceinte.lignes = restes + ([anneau] if anneau is not None else [])
        elif nb_anneaux > 1:
            notes.append(
                f"La clôture forme {nb_anneaux} enceintes disjointes : seule la "
                "plus grande délimite le projet ici. Vérifiez le plan."
            )
    anneau = enceinte.anneau if enceinte is not None else None

    ouvrages: list[OuvragePlace] = []
    gabarits_utilises: list = []
    manques: set[str] = set()
    cotes = {e.libelle: cote_lue(e.libelle, e.categorie) for e in lecture.legende}
    for entree in lecture.entree("bache_incendie"):
        volume = cotes[entree.libelle].get("volume_citerne_m3")
        if volume is not None and volume not in VOLUMES_CITERNE_M3:
            notes.append(
                f"« {entree.libelle} » : {volume:g} m³ en légende, un volume que le "
                "catalogue UNITe n'a pas "
                f"({', '.join(str(v) for v in VOLUMES_CITERNE_M3)} m³). Il n'est "
                "pas retenu : corrigez la légende, ou choisissez un volume à l'écran."
            )
    for categorie, liste in reperes_par_categorie.items():
        if categorie == "portail":
            continue
        for repere in liste:
            gabarit, manque, source = _gabarit_de(
                categorie, catalogue, choix, cotes.get(repere.libelle)
            )
            if manque:
                manques.add(manque)
            elif gabarit not in gabarits_utilises:
                gabarits_utilises.append(gabarit)
            ouvrage = _ouvrage(repere, calage, gabarit, anneau)
            ouvrage.source_gabarit = source
            if ouvrage.orientation != "grand côté dessiné":
                notes.append(
                    f"« {repere.libelle} » : repère carré au plan, le grand côté "
                    f"du gabarit ({ouvrage.longueur_m or 0:.1f} m) est posé "
                    "parallèle à la clôture voisine. À vérifier sur le plan."
                )
            ouvrages.append(ouvrage)

    proposees, appliquees = [], []
    for rang, ouvrage in enumerate(ouvrages, start=1):
        correction = _correction_proposee(ouvrage, rang, anneau)
        if correction is None:
            continue
        proposees.append(correction)
        if correction.identifiant in choix.corrections:
            ouvrage.centre = correction.centre_corrige
            ouvrage.direction_deg = correction.direction_deg
            ouvrage.correction = correction.identifiant
            appliquees.append(correction)
            if enceinte is not None:
                enceinte.interruptions.append(
                    {
                        "longueur_m": round(ouvrage.longueur_m, 2),
                        "ouvrages": [ouvrage.libelle],
                        "origine": "correction D8",
                    }
                )
    correction_pistes, axes_serres = _pistes_contre_la_cloture(
        axes_de_pistes, pistes, enceinte.polygone if enceinte is not None else None, tables
    )
    if correction_pistes is not None:
        proposees.append(correction_pistes)
        if correction_pistes.identifiant in choix.corrections:
            appliquees.append(correction_pistes)
            pistes, notes_pistes = dessiner_pistes(axes_serres)
    notes.extend(notes_pistes)
    # Les mises en limite de propriété se vérifient au calage, dans
    # `ImportPlanPDF` : la construction ne connaît pas l'emprise cadastrale.
    inconnues = {
        i
        for i in choix.corrections
        if not i.startswith((PREFIXE_EN_LIMITE, PREFIXE_CLOTURE_EN_LIMITE))
    } - {c.identifiant for c in proposees}
    if inconnues:
        raise ErreurPlanPDF(
            f"Correction(s) demandée(s) sans objet sur ce plan : "
            f"{', '.join(sorted(inconnues))}. Corrections proposées : "
            f"{', '.join(c.identifiant for c in proposees) or 'aucune'}."
        )

    portails = []
    largeurs_portails: list = []
    polygone = enceinte.polygone if enceinte is not None else None
    if polygone is not None:
        repere_interieur = polygone.representative_point()
    elif cloture:
        repere_interieur = unary_union(cloture).convex_hull.centroid
    else:
        repere_interieur = None
    for repere in reperes_par_categorie["portail"]:
        centre = Point(calage.point_vers_dxf(*repere.centre))
        direction = calage.direction_vers_dxf(repere.direction_deg)
        if anneau is not None and anneau.distance(centre) <= PORTAIL_SUR_LA_CLOTURE_M:
            centre = nearest_points(anneau, centre)[0]
            direction = _direction_de_ligne(anneau, centre)
        else:
            notes.append(
                f"« {repere.libelle} » à plus de {PORTAIL_SUR_LA_CLOTURE_M:.0f} m de "
                "la clôture : posé selon sa propre orientation au plan, ses "
                "vantaux ouverts du côté de la clôture."
            )
        largeur = cotes.get(repere.libelle, {}).get("largeur_portail_m")
        source = "largeur portée en légende"
        if largeur is None:
            largeur, source = choix.largeur_portail_m, "largeur choisie à l'écran"
        if largeur is None:
            manques.add("la largeur du portail")
            continue
        largeurs_portails.append((repere.libelle, largeur, source))
        if repere_interieur is None:
            notes.append(
                f"« {repere.libelle} » : aucune clôture au plan pour dire de quel "
                "côté ses vantaux s'ouvrent. Ils sont dessinés à gauche de son "
                "orientation, sans autre raison : à vérifier."
            )
        normale = _normale_vers(polygone, centre, direction, repere_interieur or centre)
        portails.append(
            (repere.libelle, symbole_portail(centre, direction, largeur, normale))
        )
    if len({l for _, l, _ in largeurs_portails}) > 1:
        notes.append(
            "Portails de largeurs différentes ("
            + ", ".join(f"« {n} » {l:g} m" for n, l, _ in largeurs_portails)
            + ") : le plan de masse les dessine chacun à la sienne, l'élévation "
            "de DP 4-2 au plus large."
        )

    return Construction(
        traces=traces_dxf,
        enceinte=enceinte,
        ouvrages=ouvrages,
        portails=portails,
        corrections_proposees=proposees,
        corrections_appliquees=appliquees,
        gabarits=gabarits_utilises,
        notes=notes,
        manques=sorted(manques),
        pistes=pistes,
        largeurs_portails=largeurs_portails,
    )


# ---------------------------------------------------------------------------
# L'import complet, et le contrat qu'il écrit
# ---------------------------------------------------------------------------


def _catalogue() -> tuple[dict, list[str]]:
    """Le catalogue des gabarits UNITe, indexé par libellé d'ouvrage."""
    from .tableau_bilan import lire_gabarits

    cotes, ecartees = lire_gabarits(CHEMIN_GABARITS)
    return {c.ouvrage: c.__dict__ for c in cotes}, ecartees


@dataclass
class ImportPlanPDF:
    """Un plan PDF calé sur un export HelioScope : de quoi écrire le contrat.

    Même interface qu'`import_be.ImportBE` là où l'application la lit —
    `plan`, `controles`, `bloquants`, `avertissements`, `ligne_coupe`,
    `profil`, `ecrire` — pour que la carte, la coupe et la validation servent
    aux trois producteurs sans savoir lequel les alimente. Il n'y a pas de
    tableau bilan, et aucun attribut n'en fait semblant.

    Les géométries en Lambert 93 se recalculent à chaque lecture sur le calage
    courant du lot 2 : régler la longitude ou le nord-sud déplace le plan avec
    les tables, sans recaler la page (décision D5).
    """

    implantation: object
    lecture: PlanPDF
    calage: CalagePlan
    choix: ChoixDuPlan
    source_export: str
    emprise_cadastrale: BaseGeometry | None = None
    prepositionnement: object | None = None
    ligne_coupe: object | None = None
    profil: object | None = None
    #: Toujours None : le DXF HelioScope est plat, et le contrôle le dit.
    coherence: object | None = None
    terrain_be: list = field(default_factory=list)
    _memoire: dict = field(default_factory=dict, repr=False)

    # -- construction -----------------------------------------------------

    def _cle(self) -> tuple:
        calage = self.implantation.calage
        return (calage.longitude_origine, calage.correction_nord_sud_m, self.choix.cle())

    def _garder(self, nom: str, cle: tuple, valeur):
        """Retient `valeur` pour ce calage et ces choix, et oublie les précédents.

        Chaque recalage change la clé : garder chaque état essayé accumulerait
        un plan entier — les milliers de modules projetés — par réglage, ce que
        le bouton « Caler sur l'ortho » et les recalages successifs rendent
        fréquent.
        """
        for ancienne in [
            k for k in self._memoire if isinstance(k, tuple) and k[0] == nom and k[1] != cle
        ]:
            del self._memoire[ancienne]
        self._memoire[(nom, cle)] = valeur
        return valeur

    @property
    def catalogue(self) -> tuple[dict, list[str]]:
        if "catalogue" not in self._memoire:
            self._memoire["catalogue"] = _catalogue()
        return self._memoire["catalogue"]

    @property
    def construction(self) -> Construction:
        cle = ("construction", self.choix.cle())
        if cle not in self._memoire:
            self._memoire[cle] = construire(
                self.lecture,
                self.calage,
                self.choix,
                self.catalogue[0],
                tables=tuple(self.implantation.tables),
            )
        return self._memoire[cle]

    def changer_de_choix(self, choix: ChoixDuPlan) -> None:
        """Retient de nouveaux choix ; les géométries suivront à la prochaine lecture."""
        self.choix = choix

    @property
    def etat(self) -> tuple:
        """Ce qui, réglé à l'écran, change les géométries écrites.

        Le calage du lot 2, les choix du plan et la correspondance de la
        légende. L'écran le compare à ce qu'il a écrit pour savoir si la sortie
        sur le disque est encore celle de l'import en mémoire, et garder la
        carte sous les réglages tant qu'elle ne l'est pas.
        """
        return self._cle() + (tuple(sorted(self.lecture.correspondance.items())),)

    @property
    def corrections_proposees(self) -> list:
        return self.construction.corrections_proposees + self._en_limite()[0]

    @property
    def corrections_appliquees(self) -> list:
        """Les corrections cochées : celles de la construction, et les mises en limite."""
        return self.construction.corrections_appliquees + [
            c for c in self._en_limite()[0] if c.identifiant in self.choix.corrections
        ]

    def _en_limite(self) -> tuple[list, list[str]]:
        """Les postes à caler en limite de propriété, et ce qu'il faut en dire.

        Au calage courant, gardés comme le plan : l'emprise est en Lambert 93,
        le poste s'y projette avec le calepinage, et un recalage change l'écart.
        """
        cle = self._cle()
        gardes = self._memoire.get(("en_limite", cle))
        if gardes is None or gardes[0] is not self.emprise_cadastrale:
            gardes = self._garder(
                "en_limite", cle, (self.emprise_cadastrale, self._proposer_en_limite())
            )
        return gardes[1]

    def _proposer_en_limite(self) -> tuple[list, list[str]]:
        from .helioscope import projeter

        corrections, notes = [], []
        emprise = self.emprise_cadastrale
        calage = self.implantation.calage
        enceinte = self.construction.enceinte
        enceinte_l93 = (
            projeter(enceinte.polygone, calage)
            if enceinte is not None and enceinte.anneau is not None
            else None
        )
        # La clôture d'abord : recalée sur la limite, c'est elle que le poste
        # doit rejoindre, et c'est d'elle que se lit le côté d'un couloir de
        # portail. L'ordre inverse calait le poste sur un tracé périmé.
        if enceinte_l93 is not None and emprise is not None and not emprise.is_empty:
            correction, note = _cloture_sur_la_limite(
                enceinte_l93, emprise, self.lecture.entree("cloture")[0].libelle
            )
            if correction is not None:
                corrections.append(correction)
                if correction.identifiant in self.choix.corrections:
                    enceinte_l93 = correction.geometrie_l93
                    for libelle_portail, entites_portail in self.construction.portails:
                        # Les cinq traits du symbole, et non la seule ouverture :
                        # un vantail détaché du tracé se voit comme le reste.
                        ecart = max(
                            projeter(entite, calage).distance(enceinte_l93.exterior)
                            for entite in entites_portail
                        )
                        if ecart > PORTAIL_SUIT_LA_CLOTURE_M:
                            notes.append(
                                f"« {libelle_portail} » se retrouve à {ecart:.1f} m de "
                                "la clôture recalée sur la limite de propriété : le "
                                "plan le pose sur le tracé d'avant, et le déplacer "
                                "serait deviner où le chef de projet le voulait. À "
                                "vérifier sur la planche DP 2."
                            )
            if note:
                notes.append(note)
        # Le couloir d'accès de chaque portail : un poste calé en limite ne
        # s'y pose pas (retour du chef de projet du 24/09/2026).
        couloirs = [
            (libelle, _couloir_de_portail(projeter(entites_portail[0], calage), enceinte_l93))
            for libelle, entites_portail in self.construction.portails
        ]
        if emprise is not None and not emprise.is_empty:
            for rang, ouvrage in enumerate(self.construction.ouvrages, start=1):
                if ouvrage.categorie not in POSTES_EN_LIMITE:
                    continue
                geometrie = ouvrage.geometrie()
                if geometrie is None:
                    continue
                correction, note = _correction_en_limite(
                    projeter(geometrie, calage), emprise, ouvrage, rang, enceinte_l93, couloirs
                )
                if correction is not None:
                    corrections.append(correction)
                if note:
                    notes.append(note)
        # Un recalage peut ôter son objet à une mise en limite cochée avant lui :
        # le dire, plutôt que de lever sur une page qui se réaffiche.
        sans_objet = {
            i
            for i in self.choix.corrections
            if i.startswith((PREFIXE_EN_LIMITE, PREFIXE_CLOTURE_EN_LIMITE))
        } - {c.identifiant for c in corrections}
        for identifiant in sorted(sans_objet):
            notes.append(
                f"Mise en limite de propriété cochée, sans objet au calage courant "
                f"({identifiant}) : elle ne s'applique pas."
            )
        return corrections, notes

    @property
    def decisions_manquantes(self) -> list[str]:
        """Ce que le chef de projet doit trancher avant d'écrire le contrat."""
        return list(self.construction.manques)

    # -- géométries du contrat --------------------------------------------

    def entites(self) -> list:
        """Les géométries du contrat, en Lambert 93 : les tables du lot 2, le reste du plan."""
        cle = ("entites", self._cle())
        if cle in self._memoire:
            return self._memoire[cle]
        from .helioscope import entites_contrat, projeter
        from .import_be import EntiteBE

        calage = self.implantation.calage
        construction = self.construction
        entites = list(entites_contrat(self.implantation))

        def ajouter(categorie, libelle, geometrie):
            entites.append(
                EntiteBE(
                    categorie=categorie,
                    calque=libelle,
                    geometrie=projeter(geometrie, calage),
                    z_reel=False,
                )
            )

        # Un poste calé en limite de propriété l'est en Lambert 93, et
        # l'enceinte le rejoint : les deux entrent tels quels, sans repasser
        # par la projection.
        en_limite = {
            c.identifiant: c for c in self._en_limite()[0] if c.identifiant in self.choix.corrections
        }
        postes_en_limite = {
            i: c for i, c in en_limite.items() if i.startswith(PREFIXE_EN_LIMITE)
        }
        cloture_recalee = next(
            (c for i, c in en_limite.items() if i.startswith(PREFIXE_CLOTURE_EN_LIMITE)),
            None,
        )
        enceinte = construction.enceinte
        if enceinte is not None:
            libelle = self.lecture.entree("cloture")[0].libelle
            if enceinte.anneau is not None:
                # Un polygone, comme la clôture fermée du plan de Saint-Cyr :
                # le lot 4 lit l'enceinte par son contour, et la coupe du
                # terrain la retrouve là où elle franchit ce contour.
                polygone = (
                    cloture_recalee.geometrie_l93
                    if cloture_recalee is not None
                    else projeter(enceinte.polygone, calage)
                )
                for correction in postes_en_limite.values():
                    polygone = _enceinte_jusqu_au_poste(polygone, correction.geometrie_l93)
                entites.append(
                    EntiteBE(categorie="cloture", calque=libelle, geometrie=polygone, z_reel=False)
                )
            else:
                for ligne in enceinte.lignes:
                    ajouter("cloture", libelle, ligne)
        # Les haies qui longent la clôture la suivent : c'est la même
        # correction, pas une seconde case à cocher.
        haies_suivies = {}
        if cloture_recalee is not None and enceinte is not None and enceinte.anneau is not None:
            haies_suivies = _haies_qui_suivent(
                [
                    (categorie, libelle, projeter(ligne, calage))
                    for categorie, libelle, ligne in construction.traces
                ],
                projeter(enceinte.polygone, calage),
                cloture_recalee.geometrie_l93,
            )
        for rang, (categorie, libelle, ligne) in enumerate(construction.traces):
            suivie = haies_suivies.get(rang)
            if suivie is not None:
                # Déjà en Lambert 93, comme le poste et la clôture recalés :
                # repasser par la projection la remettrait où le plan l'avait.
                entites.append(
                    EntiteBE(
                        categorie=categorie,
                        calque=libelle,
                        geometrie=suivie,
                        z_reel=False,
                    )
                )
                continue
            ajouter(categorie, libelle, ligne)
        # Une piste est une surface, comme au calque du BE : un polygone par
        # morceau, la couche n'en mélangeant pas les types.
        for piste in construction.pistes:
            for polygone in piste.polygones:
                ajouter(piste.categorie, piste.libelle, polygone)
        for rang, ouvrage in enumerate(construction.ouvrages, start=1):
            geometrie = ouvrage.geometrie()
            if geometrie is None:
                continue
            recale = postes_en_limite.get(
                f"{PREFIXE_EN_LIMITE}:{ouvrage.categorie}:{rang}"
            )
            if recale is None:
                ajouter(ouvrage.categorie, ouvrage.libelle, geometrie)
            else:
                entites.append(
                    EntiteBE(
                        categorie=ouvrage.categorie,
                        calque=ouvrage.libelle,
                        geometrie=recale.geometrie_l93,
                        z_reel=False,
                    )
                )
        # Cinq entités par portail, comme au calque du BE : l'ouverture d'abord.
        for libelle, entites_portail in construction.portails:
            for ligne in entites_portail:
                ajouter("portail", libelle, ligne)
        return self._garder(*cle, entites)

    @property
    def plan(self):
        """Le plan normalisé, sous la forme que la carte et la coupe savent lire."""
        cle = ("plan", self._cle())
        if cle in self._memoire:
            return self._memoire[cle]
        from .helioscope import azimut_rangees
        from .import_be import PlanBE

        vides = [
            e.libelle
            for e in self.lecture.legende
            if e.categorie and not self.lecture.elements_de(e.categorie)
        ]
        plan = PlanBE(
            entites=self.entites(),
            azimut_tables_deg=azimut_rangees(self.implantation),
            correspondance=self.lecture.correspondance,
            unite="mètre",
            facteur_unite=1.0,
            calques_ignores=[e.libelle for e in self.lecture.legende if not e.categorie],
            calques_vides=vides,
            source=f"{self.lecture.source} sur {self.source_export}",
            avertissements=self._avertissements_du_plan(),
        )
        return self._garder(*cle, plan)

    def _avertissements_du_plan(self) -> list[str]:
        construction = self.construction
        messages = list(self.implantation.avertissements) + list(self.lecture.avertissements)
        messages.extend(construction.notes)
        ecartees = self.catalogue[1]
        if ecartees:
            messages.append(
                "Gabarits UNITe : cases de surface écartées à la lecture du "
                f"classeur — {' ; '.join(ecartees)}. Aucune ne porte une "
                "dimension d'ouvrage."
            )
        appliquees = self.corrections_appliquees
        for correction in self.corrections_proposees:
            if correction not in appliquees:
                messages.append(
                    f"Correction de plan proposée, non appliquée : {correction.raison}"
                )
        messages.extend(self._en_limite()[1])
        portails = [e.geometrie for e in self.entites() if e.categorie == "portail"]
        for correction in appliquees:
            if correction.identifiant.startswith(PREFIXE_EN_LIMITE):
                # Le portail voisin garde la place que le plan lui donne : le
                # déplacer, ce serait deviner où le chef de projet le voulait.
                voisin = any(
                    g.distance(correction.geometrie_l93) < PORTAIL_SUR_LA_CLOTURE_M for g in portails
                )
                messages.append(
                    f"« {correction.libelle} » calé en limite de propriété : "
                    "l'enceinte le rejoint à ses pignons, et il tient lieu de "
                    "clôture sur sa longueur."
                    + (
                        " Le portail voisin garde la place que le plan lui donne : "
                        "à vérifier sur la planche DP 2."
                        if voisin
                        else ""
                    )
                )
            elif correction.identifiant.startswith(PREFIXE_CLOTURE_EN_LIMITE):
                messages.append(
                    f"« {correction.libelle} » recalée sur la limite de propriété : "
                    f"{correction.lineaire_m:.0f} m de tracé les suivent, d'au "
                    f"plus {correction.retrait_m:.1f} m. Ce qui s'en écartait de plus "
                    f"de {CLOTURE_EN_LIMITE_M:.0f} m est laissé tel quel."
                )
        messages.extend(self._recoupements_du_tableau_du_plan())
        return messages

    def _recoupements_du_tableau_du_plan(self) -> list[str]:
        """Ce que le tableau du plan déclare et que l'export HelioScope dément.

        Les modules se prennent à l'export (instruction du chef de projet du
        23/09/2026) : un cartouche qui en annonce un autre nombre est à mettre à
        jour, pas à suivre. À Bray, 5 296 au plan pour 4 590 à l'export.
        """
        informations = self.lecture.informations
        calepinage = self.implantation.calepinage
        messages = []
        if "nb_modules" in informations:
            annonce = informations["nb_modules"]["valeur"]
            if annonce != calepinage.nb_modules:
                messages.append(
                    f"Le plan annonce {f'{annonce:,}'.replace(',', ' ')} modules, "
                    "l'export HelioScope en porte "
                    f"{f'{calepinage.nb_modules:,}'.replace(',', ' ')} : c'est "
                    "l'export qui fait foi. Mettez le tableau du plan à jour."
                )
        inclinaison = calepinage.module.inclinaison_deg
        if "inclinaison_deg" in informations and inclinaison is not None:
            annoncee = informations["inclinaison_deg"]["valeur"]
            if abs(annoncee - inclinaison) > 0.5:
                messages.append(
                    f"Le plan annonce une inclinaison de {annoncee:g}°, l'export "
                    f"HelioScope porte {inclinaison:g}° : c'est l'export qui fait "
                    "foi pour la coupe. Mettez le tableau du plan à jour."
                )
        return messages

    # -- contrôles ----------------------------------------------------------

    @property
    def controles(self) -> list:
        """Les recoupements du plan, du calepinage et du foncier.

        Gardés pour un calage et des choix donnés, comme le plan : l'application
        les lit cinq fois à chaque affichage de la page — bloquants, titre du
        détail, tableau, avertissements, validation —, et chaque lecture
        refaisait rangées et recoupements, 2,6 s à Gannay : 12,8 s sur les
        13,7 s d'un affichage (mesuré le 23/09/2026). L'emprise cadastrale,
        fixée à l'import, est retenue avec eux : une autre les ferait refaire.
        """
        cle = self._cle()
        gardes = self._memoire.get(("controles", cle))
        if gardes is None or gardes[0] is not self.emprise_cadastrale:
            gardes = self._garder(
                "controles", cle, (self.emprise_cadastrale, self._recouper())
            )
        return list(gardes[1])

    def _recouper(self) -> list:
        """Le calcul de `controles`, sans mémoire."""
        from .helioscope import limites_helioscope, projeter, rangees
        from .import_be import (
            AVERTISSEMENT,
            DEBORDEMENT_NEGLIGEABLE_M2,
            IMPOSSIBLE,
            OK,
            Controle,
            _emprise,
        )

        haies_l93 = [
            (categorie, libelle, projeter(ligne, self.implantation.calage))
            for categorie, libelle, ligne in self.construction.traces
            if categorie in CATEGORIES_HAIE
        ]
        enceinte_plan = self.construction.enceinte
        cloture_l93 = (
            projeter(enceinte_plan.polygone, self.implantation.calage)
            if enceinte_plan is not None and enceinte_plan.anneau is not None
            else None
        )
        hors_emprise, loin = _controle_des_haies(
            haies_l93, cloture_l93, self.emprise_cadastrale
        )
        if hors_emprise or loin:
            detail = []
            if hors_emprise:
                detail.append(
                    "hors de l'emprise cadastrale : "
                    + " ; ".join(f"« {n} » sur {d:.0f} m" for n, d in hors_emprise)
                )
            if loin:
                detail.append(
                    f"à plus de {HAIE_LE_LONG_CLOTURE_M:.0f} m de la clôture : "
                    + " ; ".join(f"« {n} » à {e:.0f} m" for n, e in loin)
                )
            message_haies = (
                f"{len(hors_emprise) + len(loin)} haie(s) du plan ne sont pas en "
                "bord de clôture dans l'emprise du projet — "
                + ", et ".join(detail)
                + ". Un plan de DP ne porte que les haies du projet : celles-là "
                "relèvent de l'aménagement paysager et vont à la notice. En "
                "dessiner sur des parcelles sans maîtrise foncière se reproche à "
                "l'instruction. Retirez-les du plan PDF et refaites l'import."
            )
        else:
            message_haies = (
                f"{len(haies_l93)} haie(s) au plan, toutes en bord de clôture dans "
                "l'emprise du projet."
                if haies_l93
                else "Le plan ne porte aucune haie."
            )

        controles = [
            Controle(
                "Haies du plan",
                None,
                None,
                "",
                AVERTISSEMENT if (hors_emprise or loin) else OK,
                message_haies,
            ),
            Controle(
                "Recoupement avec le tableau bilan",
                None,
                None,
                "",
                IMPOSSIBLE,
                "Le plan PDF et l'export HelioScope sont les seules sources : il n'y "
                "a pas de tableau bilan à leur confronter. Surfaces, puissance et "
                "nombre de modules ne sont pas recoupés avec une déclaration.",
            ),
            Controle(
                "Cohérence altimétrique des tables",
                None,
                None,
                "",
                IMPOSSIBLE,
                "Le DXF HelioScope est plat et le plan PDF n'a pas d'altitude : le "
                "profil du terrain reste disponible par le RGE ALTI, mais sans "
                "recoupement possible avec l'implantation.",
            ),
            Controle(
                "Calage du plan sur les tables",
                round(self.calage.recouvrement, 4),
                None,
                "",
                OK if self.calage.recouvrement >= RECOUVREMENT_MIN else AVERTISSEMENT,
                f"Les {self.calage.nb_rangees_plan} rangées du plan répondent aux "
                f"{self.calage.nb_rangees_dxf} du DXF, à l'échelle de "
                f"{self.calage.m_par_px_reference:.4f} m/px à {DPI_REFERENCE:.0f} dpi "
                f"mesurée sur leur pas. {self.calage.fidelite:.0%} des tables "
                f"du plan tombent sur une table du DXF, et les deux damiers se "
                f"recouvrent à {self.calage.recouvrement:.1%}"
                + (
                    "."
                    if self.calage.recouvrement >= RECOUVREMENT_MIN
                    else (
                        f", sous les {RECOUVREMENT_MIN:.0%} d'une copie d'écran "
                        "fine : à cette résolution les rangées ne font que "
                        "quelques pixels, et un demi-pixel de décalage coûte un "
                        "quart de l'union. Le calage tient sur l'accord des "
                        "rangées — vérifiez-le sur l'aperçu."
                    )
                )
                + (
                    f" {self.calage.isolats_ecartes} pixel(s) à la teinte "
                    "des tables ont été écartés hors du champ : pastille de "
                    "légende, flèche du nord ou échelle, qui fausseraient "
                    "l'emprise mesurée."
                    if self.calage.isolats_ecartes
                    else ""
                ),
                f"{self.calage.nb_rangees_dxf} rangées",
            ),
        ]

        plan = self.plan
        enceinte = plan.polygone_cloture
        lignes = rangees(self.implantation)
        if enceinte is not None and lignes:
            hors = float(unary_union(lignes).difference(enceinte).area)
            controles.append(
                Controle(
                    "Tables contenues dans la clôture",
                    round(hors, 1),
                    None,
                    "m²",
                    OK if hors <= DEBORDEMENT_NEGLIGEABLE_M2 else AVERTISSEMENT,
                    "Les tables du calepinage sont dans la clôture du plan."
                    if hors <= DEBORDEMENT_NEGLIGEABLE_M2
                    else f"{hors:.0f} m² de tables du calepinage tombent hors de la "
                    "clôture du plan : les deux sources ne décrivent pas la même "
                    "implantation, ou la clôture a été dessinée trop serrée.",
                )
            )
        elif enceinte is None:
            controles.append(
                Controle(
                    "Tables contenues dans la clôture",
                    None,
                    None,
                    "",
                    AVERTISSEMENT,
                    "La clôture du plan ne se referme pas : les tables ne peuvent pas "
                    "être confrontées à l'enceinte.",
                )
            )
        controles.append(_emprise(plan, self.emprise_cadastrale))
        controles.extend(
            c
            for c in limites_helioscope(self.implantation, self.emprise_cadastrale)
            if "emprise cadastrale" in c.libelle
        )
        controle_pistes = self._controle_des_pistes(plan)
        if controle_pistes is not None:
            controles.append(controle_pistes)
        return controles

    def _controle_des_pistes(self, plan):
        """Ce que la piste de 5 m recouvre, là où le trait du plan passait au ras.

        Le trait du plan n'a pas de largeur : il passe au ras des tables et de
        la clôture sans rien toucher. Une piste de 5 m menée sur ce trait peut
        les recouvrir. On ne la déplace pas — ce serait corriger le plan —, on
        dit où et de combien. Mesuré le 23/09/2026 à Gannay : 21 m² de tables,
        et la clôture couverte sur 113 m le long de la piste à créer, dont l'axe
        passe à 2,1 m d'elle.
        """
        from .import_be import AVERTISSEMENT, OK, Controle

        pistes = [g for c in CATEGORIES_PISTES for g in plan.geometries(c)]
        if not pistes:
            return None
        surface = unary_union(pistes)
        tables = unary_union(plan.geometries("tables_pv"))
        ouvrages = unary_union(
            [g for c in CATEGORIES_OUVRAGES if c != "portail" for g in plan.geometries(c)]
        )
        sur_tables = float(surface.intersection(tables).area) if not tables.is_empty else 0.0
        sur_ouvrages = float(surface.intersection(ouvrages).area) if not ouvrages.is_empty else 0.0
        enceinte = plan.polygone_cloture
        sur_cloture = 0.0
        if enceinte is not None:
            # Une piste franchit la clôture à ses portails : ce n'est pas un
            # recouvrement.
            portails = unary_union(plan.geometries("portail")).buffer(0.5)
            # `boundary` et non `exterior` : une clôture en deux enceintes
            # disjointes — le cas est prévu plus haut — arrive en MultiPolygon,
            # qui n'a pas d'`exterior`. Mesuré le 01/10/2026 : le contrôle
            # tombait sur un `AttributeError` au lieu de rendre son rapport.
            couverte = enceinte.boundary.intersection(surface)
            if not portails.is_empty:
                couverte = couverte.difference(portails)
            sur_cloture = float(couverte.length)
        constats = []
        if sur_tables > 0.5:
            constats.append(f"{sur_tables:.0f} m² de tables")
        if sur_ouvrages > 0.5:
            constats.append(f"{sur_ouvrages:.0f} m² d'ouvrages")
        if sur_cloture > 1.0:
            constats.append(f"la clôture sur {sur_cloture:.0f} m hors portails")
        serrees = any(
            c.identifiant == "pistes_contre_cloture"
            for c in self.construction.corrections_appliquees
        )
        if not constats:
            message = (
                f"Les pistes de {LARGEUR_PISTE_M:.0f} m ne recouvrent ni table, ni "
                "ouvrage, ni la clôture hors des portails."
            )
        elif serrees:
            # Le trait n'est plus celui du plan : le dire, et dire ce qu'aucun
            # placement de la piste ne peut régler.
            message = (
                f"Serrées contre la clôture, les pistes de {LARGEUR_PISTE_M:.0f} m "
                f"recouvrent encore {', '.join(constats)} : ce qui s'avance à moins "
                f"de {nombre_fr(LARGEUR_PISTE_M + JEU_CLOTURE_M)} m de la clôture ne "
                "leur laisse pas la place. C'est au plan de la leur faire."
            )
        else:
            message = (
                f"Menées sur le tracé du plan, les pistes de {LARGEUR_PISTE_M:.0f} m "
                f"recouvrent {', '.join(constats)} : le trait du plan passe trop près. "
                "Elles sont dessinées là où le plan les place ; c'est au plan de "
                "leur faire la place."
            )
        return Controle(
            "Pistes de 5 m sur le tracé du plan",
            round(sur_tables, 1),
            None,
            "m²",
            AVERTISSEMENT if constats else OK,
            message,
        )

    @property
    def bloquants(self) -> list:
        return [c for c in self.controles if c.bloquant]

    @property
    def avertissements(self) -> list[str]:
        from .import_be import AVERTISSEMENT

        messages = list(self.plan.avertissements)
        for controle in self.controles:
            if controle.statut == AVERTISSEMENT:
                messages.append(f"{controle.libelle} : {controle.message}")
        if self.ligne_coupe is not None:
            messages.extend(self.ligne_coupe.avertissements)
        if self.profil is not None:
            messages.extend(self.profil.avertissements)
        return messages

    # -- écriture -----------------------------------------------------------

    def parametres(self) -> dict:
        """`projet.json` de sortie : celui du lot 2, complété de ce que dit le plan."""
        from .helioscope import parametres_contrat
        from .import_be import ORIGINE_PLAN_PDF

        construction = self.construction
        plan = self.plan
        donnees = parametres_contrat(
            self.implantation,
            self.controles,
            ligne_coupe=self.ligne_coupe,
            profil=self.profil,
        )
        donnees["origine"] = ORIGINE_PLAN_PDF
        donnees["sources"].update(
            {
                "export_helioscope": self.source_export,
                "plan_pdf": self.lecture.source,
                "page_plan_pdf": self.lecture.page,
                "gabarits": CHEMIN_GABARITS.name,
            }
        )
        donnees["plan"].update(
            {
                "nb_portails": plan.nb_portails,
                "surface_cloturee_m2": plan.surface_cloturee_m2,
                "lineaire_cloture_m": plan.lineaire_cloture_m,
                "correspondance_calques": self.lecture.correspondance,
                "calques_ignores": plan.calques_ignores,
                "avertissements": plan.avertissements,
            }
        )
        if construction.largeurs_portails:
            # L'élévation de DP 4-2 se dessine à une largeur : la plus grande,
            # et la note de construction le dit quand elles diffèrent.
            donnees["parametres"]["generalites"]["largeur_portails_m"] = max(
                l for _, l, _ in construction.largeurs_portails
            )
        # La hauteur des tables se prend au tableau du plan quand il la donne
        # (instruction du chef de projet du 23/09/2026), là où DP 3 la cherche
        # d'abord ; sans elle, DP 3 prend le standard UNITe et le dit. Le reste
        # du tableau ne sert qu'à recouper l'export.
        informations = self.lecture.informations
        structures = donnees["parametres"].setdefault("structures", {})
        for cle in ("point_bas_m", "point_haut_m"):
            if cle in informations:
                structures[cle] = informations[cle]["valeur"]
        donnees["informations_plan"] = informations
        donnees["parametres"]["generalites"]["nb_portails"] = plan.nb_portails
        # Le catalogue entier, comme le lot 2bis le recopie du tableau bilan :
        # le lot 4 y retrouve chaque ouvrage par son libellé, et la variante
        # d'une citerne par la surface de ce qui est dessiné.
        donnees["cotes_normalisees"] = [
            {
                "ouvrage": brut["ouvrage"],
                "dimensions": brut["dimensions"],
                "ordre_cotes": brut["ordre_cotes"],
                "surface_m2": brut["surface_m2"],
                "surface_plateforme_m2": brut["surface_plateforme_m2"],
            }
            for brut in self.catalogue[0].values()
        ]
        donnees["calage_plan"] = {
            "echelle_m_par_pt": self.calage.echelle_m_par_pt,
            "m_par_px_300dpi": self.calage.m_par_px_reference,
            "rotation_deg": self.calage.rotation_deg,
            "translation_m": list(self.calage.translation),
            "pas_rangees_plan_pt": self.calage.pas_plan_pt,
            "dispersion_pas_pt": self.calage.dispersion_pas_pt,
            "pas_rangees_dxf_m": self.calage.pas_dxf_m,
            "nb_rangees_plan": self.calage.nb_rangees_plan,
            "nb_rangees_dxf": self.calage.nb_rangees_dxf,
            "echelle_le_long_m_par_pt": self.calage.echelle_le_long_m_par_pt,
            "echelle_en_travers_m_par_pt": self.calage.echelle_en_travers_m_par_pt,
            "recouvrement_jaccard": self.calage.recouvrement,
            "recouvrement_plan_retourne": self.calage.recouvrement_retourne,
        }
        donnees["legende_plan"] = [
            {
                "libelle": e.libelle,
                "categorie": e.categorie,
                "couleur_rgb": list(e.couleur),
                "nature": e.pastille.nature,
                "lisere_rgb": list(e.pastille.lisere) if e.pastille.lisere else None,
                "motif": e.pastille.motif,
                "nb_formes": sum(1 for x in self.lecture.elements if x.entree is e),
            }
            for e in self.lecture.legende
        ]
        donnees["ouvrages_plan"] = [
            {
                "categorie": o.categorie,
                "libelle": o.libelle,
                "gabarit": o.gabarit,
                "longueur_m": o.longueur_m,
                "largeur_m": o.largeur_m,
                "centre_dxf_m": list(o.centre),
                "direction_dxf_deg": o.direction_deg,
                "orientation": o.orientation,
                "dessine_au_plan_m": [round(v, 2) for v in o.dessine_m],
                "correction": o.correction,
                "source_gabarit": o.source_gabarit,
            }
            for o in construction.ouvrages
        ]
        donnees["portails_plan"] = [
            {"libelle": libelle, "largeur_m": largeur, "source": source}
            for libelle, largeur, source in construction.largeurs_portails
        ]
        # Ce que le plan donne d'une piste — son tracé, son type — et ce qui
        # vient d'ailleurs : sa largeur et ses rayons, d'une instruction.
        donnees["pistes_plan"] = {
            "largeur_m": LARGEUR_PISTE_M,
            "rayon_interieur_m": RAYON_INTERIEUR_M,
            "rayon_axe_m": RAYON_AXE_M,
            "source": (
                "Instruction du chef de projet du 23/09/2026 : le plan donne le "
                "tracé et le type ; la piste a 5 m de large et des virages de "
                "11 m au bord intérieur (« voie engins »)."
            ),
            "pistes": [
                {
                    "categorie": p.categorie,
                    "libelle": p.libelle,
                    "longueur_axe_m": round(p.axe.length, 1),
                    "surface_m2": round(p.surface.area, 1),
                    "rayon_axe_min_m": p.rayon_axe_min_m,
                    "rayons_raccords_m": p.rayons_raccords_m,
                }
                for p in construction.pistes
            ],
        }
        if construction.enceinte is not None:
            donnees["enceinte_plan"] = {
                "fermee": construction.enceinte.anneau is not None,
                # Un poste calé en limite de propriété ferme l'enceinte sur sa
                # longueur, comme celui que la correction D8 pose sur la clôture.
                "interruptions": construction.enceinte.interruptions
                + [
                    {
                        "longueur_m": round(_rectangle_minimal(c.geometrie_l93)[2], 2),
                        "ouvrages": [c.libelle],
                        "origine": "mise en limite de propriété",
                    }
                    for c in self.corrections_appliquees
                    if c.identifiant.startswith(PREFIXE_EN_LIMITE)
                ],
            }
        # Décision D8 : une correction appliquée figure ici avec sa raison.
        donnees["corrections_plan"] = [
            {
                "identifiant": c.identifiant,
                "ouvrage": c.libelle,
                "categorie": c.categorie,
                "retrait_m": round(c.retrait_m, 2),
                "raison": c.raison,
            }
            for c in self.corrections_appliquees
        ]
        return donnees

    def ecrire(self, dossier: str | Path) -> tuple[Path, Path]:
        """Écrit le GeoPackage et `projet.json`, une fois tout tranché.

        Un ouvrage dont la dimension n'est pas tranchée — volume de citerne,
        largeur de portail — refuse l'écriture, comme une voirie non tranchée :
        la supposer donnerait un ouvrage juste de forme et faux de taille.
        """
        from .erreurs import ErreurGabaritIndecis
        from .import_be import ecrire_geopackage, ecrire_parametres

        manques = self.decisions_manquantes
        if manques:
            raise ErreurGabaritIndecis(
                "Le plan porte des ouvrages dont une dimension reste à trancher : "
                f"{', '.join(manques)}. Le plan ne les donne pas à l'échelle "
                "(décision D2), et les supposer dessinerait un ouvrage faux de "
                "taille sans que rien ne le montre."
            )
        gpkg = ecrire_geopackage(self.entites(), dossier, ligne_coupe=self.ligne_coupe)
        parametres = ecrire_parametres(self.parametres(), dossier)
        return gpkg, parametres


def importer_plan_pdf(
    chemin_pdf: str | Path,
    chemin_export: str | Path,
    emprise_cadastrale: BaseGeometry | None = None,
    correspondance: dict | None = None,
    choix: ChoixDuPlan | None = None,
    longitude_origine: float | None = None,
    correction_nord_sud_m: float = 0.0,
) -> ImportPlanPDF:
    """Lit l'export HelioScope, le plan PDF, et cale l'un sur l'autre.

    Le géoréférencement vient du lot 2 (décision D5) : pré-positionné sur
    l'emprise cadastrale, ou donné par une longitude déjà validée. Le plan se
    cale ensuite sur les tables, dans le repère du DXF.
    """
    from .erreurs import ErreurCalage
    from .helioscope import corriger_nord_sud, importer, prepositionner

    implantation = importer(chemin_export)
    prepositionnement = None
    if longitude_origine is not None:
        implantation.calage.longitude_origine = float(longitude_origine)
        # Une longitude déjà validée est le point d'où partent les réglages.
        implantation.calage.longitude_reference = float(longitude_origine)
        corriger_nord_sud(implantation.calage, correction_nord_sud_m)
    elif emprise_cadastrale is not None and not emprise_cadastrale.is_empty:
        prepositionnement = prepositionner(implantation, emprise_cadastrale)
        corriger_nord_sud(implantation.calage, correction_nord_sud_m)
    else:
        raise ErreurCalage(
            "Ni emprise cadastrale ni longitude de calage : l'export HelioScope ne "
            "peut pas être placé en Lambert 93, et le plan PDF avec lui."
        )
    lecture = lire_plan_pdf(chemin_pdf, correspondance)
    calage = caler_sur_tables(lecture, implantation)
    return ImportPlanPDF(
        implantation=implantation,
        lecture=lecture,
        calage=calage,
        choix=choix or ChoixDuPlan(),
        source_export=Path(chemin_export).name,
        emprise_cadastrale=emprise_cadastrale,
        prepositionnement=prepositionnement,
    )
