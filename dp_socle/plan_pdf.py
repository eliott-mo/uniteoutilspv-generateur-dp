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
    # Une haie existante que l'on complète est une plantation : c'est un
    # aménagement au même titre qu'une haie créée, et le dossier s'y engage.
    # Le libellé d'origine reste au contrat, dans la colonne `calque`.
    "Haie à renforcer": "haie",
    "Haie existante": "haie_existante",
    "Poste combiné de Livraison/transformation": "pdl_ptr",
    "Poste de Livraison/transfo": "pdl_ptr",
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
    "Piste lourde existante": "piste_lourde_existante",
    "Piste lourde à créer": "piste_lourde_a_creer",
    "Piste légère": "piste_legere",
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
    "piste_lourde_existante",
    "piste_lourde_a_creer",
    "piste_lourde",
    "piste_legere",
    "voirie",
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

#: Ce que la légende doit porter pour que le plan serve à quelque chose. Sans
#: clôture, le plan ne délimite pas le projet : la version du 28/08/2026 du
#: plan de Gannay est dans ce cas, et c'est bien une version antérieure, pas
#: un plan à lire tel quel.
CATEGORIES_ATTENDUES = ("cloture",)


def categorie_proposee(libelle: str) -> str | None:
    """Catégorie proposée pour un libellé de légende, ou None s'il est inconnu."""
    return _CORRESPONDANCE_NORMALISEE.get(normaliser(libelle))


def motif_a_trancher(libelle: str) -> str | None:
    """Raison pour laquelle un libellé connu ne se rattache à rien d'office."""
    return _A_TRANCHER_NORMALISES.get(normaliser(libelle))


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

#: Recouvrement minimal des tables du plan et du DXF une fois calées
#: (décision D7). Mesuré à Gannay : 88,3 % sur le rendu à 300 dpi du prototype.
RECOUVREMENT_MIN = 0.70

#: Écart admis entre l'échelle mesurée sur le pas des rangées et celle qu'implique
#: l'emprise des tables, dans chacune des deux directions (décision D7). Une
#: copie d'écran étirée d'un seul côté dans PowerPoint donne un plan
#: anisotrope, que le pas seul ne verrait pas.
TOLERANCE_ECHELLE = 0.02


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
    """
    candidates = []
    for entree in legende:
        pastille = entree.pastille
        if pastille.nature != objet.nature:
            continue
        candidates.append((_distance(objet.couleur, pastille.couleur), entree))
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


def lire_legende(chemin: str | Path) -> list[EntreeLegende]:
    """Les entrées de la légende seules, pour en faire confirmer la correspondance.

    Rien n'y est encore exigé : un plan dont la clôture porte un nom que la
    correspondance ne connaît pas doit pouvoir montrer sa légende, pour qu'on
    l'apparie à la main avant l'import.
    """
    return _page_du_plan(Path(chemin))[1]


def _page_du_plan(chemin: Path):
    """La page qui porte la légende : son rang, sa légende, ses formes, ses images."""
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
            pages_lues.append((indice, legende, objets, images))

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
    indice, legende, objets, images = _page_du_plan(chemin)
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
    for entree in legende:
        if entree.categorie is None:
            avertissements.append(
                f"Libellé de légende « {entree.libelle} » "
                + (
                    f"non rattaché : {entree.a_trancher}. Appariez-le à la main."
                    if entree.a_trancher
                    else "inconnu : ses formes ne sont pas importées. "
                    "Appariez-le à la main s'il désigne un ouvrage du projet."
                )
            )

    fond = _image_de_fond(images, indice + 1, chemin.name)
    cadre = fond.cadre
    surface_cadre = _surface_bornes(cadre)
    pastilles = {id(e.pastille) for e in legende}

    elements, non_reconnus = [], []
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
        elements.append(ElementPlan(entree=entree, objet=objet))

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


def traces(plan: PlanPDF, categorie: str) -> tuple[list[TracePlan], list[str]]:
    """Tracés d'une catégorie linéaire, en points de la page, morceaux recousus.

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
            if element.entree is not entree:
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
        key=lambda a: _nettete(_profil(echantillon, a, pas)[0]),
    )
    normale = max(
        np.arange(grossiere - 0.75, grossiere + 0.75, 0.05),
        key=lambda a: _nettete(_profil(echantillon, a, pas)[0]),
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
        raise ErreurPlanPDF(
            f"{len(centres)} rangée(s) de tables reconnue(s) sur la copie d'écran "
            "du plan : il en faut trois au moins pour mesurer un pas (décision D3)."
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
    masque_rangees = np.zeros_like(masque)
    masque_rangees[lignes_px[dans_une_bande], colonnes_px[dans_une_bande]] = True
    return RangeesDuPlan(
        direction_deg=direction,
        pas_pt=float(pente),
        dispersion_pt=float(np.std(residus)),
        centres=centres,
        points=points[dans_une_bande],
        masque=masque_rangees,
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
    long_plan, travers_plan = _etendues(rangees.points, rangees.direction_deg)
    pixel = _pas_pixel(plan.fond)
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
    if recouvrement < RECOUVREMENT_MIN:
        raise ErreurRecouvrementInsuffisant(
            f"Une fois calées, les tables du plan et celles du DXF ne se "
            f"recouvrent qu'à {recouvrement:.1%} (Jaccard ; {RECOUVREMENT_MIN:.0%} "
            "au moins). Le plan n'a probablement pas été dressé sur ce "
            "calepinage : vérifiez que le DXF HelioScope et le plan PDF décrivent "
            "la même version du projet."
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

#: Catégories de poste auxquelles la correction D8 se propose : ce sont les
#: postes de livraison qui ferment l'enceinte sur leur long pan, le raccordement
#: se faisant depuis l'extérieur.
POSTES_EN_LIMITE = ("pdl", "pdl_ptr")


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
    portails: list
    corrections_proposees: list
    corrections_appliquees: list
    gabarits: list
    notes: list
    #: Ce qui reste à trancher pour dimensionner les ouvrages du plan.
    manques: list = field(default_factory=list)


def _gabarit_de(categorie: str, catalogue: dict, choix: ChoixDuPlan):
    """Cote du catalogue pour une catégorie, ou None et ce qui manque."""
    from .contrat import LIBELLES_COTES, decoder_cote

    if categorie == "bache_incendie":
        if choix.volume_citerne_m3 is None:
            return None, "le volume de la réserve incendie"
        libelle = f"Citerne incendie — {choix.volume_citerne_m3}"
    elif categorie == "local_technique":
        libelle = VARIANTE_LOCAL_DP
    else:
        libelles = LIBELLES_COTES.get(categorie, ())
        if len(libelles) != 1:
            return None, f"le gabarit de « {categorie} »"
        libelle = libelles[0]
    brut = catalogue.get(libelle)
    if brut is None:
        raise ErreurPlanPDF(
            f"Le gabarit « {libelle} » manque au classeur des gabarits UNITe "
            f"({CHEMIN_GABARITS.name}) : l'ouvrage « {categorie} » ne peut pas "
            "être dimensionné."
        )
    return decoder_cote(brut), None


def construire(
    lecture: PlanPDF, calage: CalagePlan, choix: ChoixDuPlan, catalogue: dict
) -> Construction:
    """Les tracés, l'enceinte, les ouvrages et les portails, en mètres du DXF."""
    notes: list[str] = []
    traces_dxf: list = []
    cloture: list = []
    for categorie in CATEGORIES_TRACEES:
        lus, remarques = traces(lecture, categorie)
        notes.extend(remarques)
        for trace in lus:
            ligne = calage.vers_dxf(trace.ligne)
            if categorie == "cloture":
                cloture.append(ligne)
            else:
                traces_dxf.append((trace.categorie, trace.libelle, ligne))

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
                f"Clôture ouverte : {len(restes)} tracé(s) ne se referment sur "
                "aucun ouvrage. La surface clôturée n'est pas calculée, et le "
                "plan est à reprendre."
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
    for categorie, liste in reperes_par_categorie.items():
        if categorie == "portail":
            continue
        for repere in liste:
            gabarit, manque = _gabarit_de(categorie, catalogue, choix)
            if manque:
                manques.add(manque)
            elif gabarit not in gabarits_utilises:
                gabarits_utilises.append(gabarit)
            ouvrage = _ouvrage(repere, calage, gabarit, anneau)
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
    inconnues = set(choix.corrections) - {c.identifiant for c in proposees}
    if inconnues:
        raise ErreurPlanPDF(
            f"Correction(s) demandée(s) sans objet sur ce plan : "
            f"{', '.join(sorted(inconnues))}. Corrections proposées : "
            f"{', '.join(c.identifiant for c in proposees) or 'aucune'}."
        )

    portails = []
    for repere in reperes_par_categorie["portail"]:
        centre = Point(calage.point_vers_dxf(*repere.centre))
        direction = calage.direction_vers_dxf(repere.direction_deg)
        if anneau is not None and anneau.distance(centre) <= PORTAIL_SUR_LA_CLOTURE_M:
            centre = nearest_points(anneau, centre)[0]
            direction = _direction_de_ligne(anneau, centre)
        else:
            notes.append(
                f"« {repere.libelle} » à plus de {PORTAIL_SUR_LA_CLOTURE_M:.0f} m de "
                "la clôture : posé selon sa propre orientation au plan."
            )
        if choix.largeur_portail_m is None:
            manques.add("la largeur du portail")
            continue
        demi = choix.largeur_portail_m / 2.0
        ux, uy = math.cos(math.radians(direction)), math.sin(math.radians(direction))
        portails.append(
            (
                repere.libelle,
                LineString(
                    [(centre.x - ux * demi, centre.y - uy * demi), (centre.x + ux * demi, centre.y + uy * demi)]
                ),
            )
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
                self.lecture, self.calage, self.choix, self.catalogue[0]
            )
        return self._memoire[cle]

    def changer_de_choix(self, choix: ChoixDuPlan) -> None:
        """Retient de nouveaux choix ; les géométries suivront à la prochaine lecture."""
        self.choix = choix

    @property
    def corrections_proposees(self) -> list:
        return self.construction.corrections_proposees

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

        enceinte = construction.enceinte
        if enceinte is not None:
            libelle = self.lecture.entree("cloture")[0].libelle
            if enceinte.anneau is not None:
                # Un polygone, comme la clôture fermée du plan de Saint-Cyr :
                # le lot 4 lit l'enceinte par son contour, et la coupe du
                # terrain la retrouve là où elle franchit ce contour.
                ajouter("cloture", libelle, enceinte.polygone)
            else:
                for ligne in enceinte.lignes:
                    ajouter("cloture", libelle, ligne)
        for categorie, libelle, ligne in construction.traces:
            ajouter(categorie, libelle, ligne)
        for ouvrage in construction.ouvrages:
            geometrie = ouvrage.geometrie()
            if geometrie is not None:
                ajouter(ouvrage.categorie, ouvrage.libelle, geometrie)
        for libelle, ligne in construction.portails:
            ajouter("portail", libelle, ligne)
        self._memoire[cle] = entites
        return entites

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
        self._memoire[cle] = plan
        return plan

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
        for correction in construction.corrections_proposees:
            if correction not in construction.corrections_appliquees:
                messages.append(
                    f"Correction de plan proposée, non appliquée : {correction.raison}"
                )
        return messages

    # -- contrôles ----------------------------------------------------------

    @property
    def controles(self) -> list:
        from .helioscope import limites_helioscope, rangees
        from .import_be import (
            AVERTISSEMENT,
            DEBORDEMENT_NEGLIGEABLE_M2,
            IMPOSSIBLE,
            OK,
            Controle,
            _emprise,
        )

        controles = [
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
                OK,
                f"Les tables du plan et celles du DXF se recouvrent à "
                f"{self.calage.recouvrement:.1%} une fois calées "
                f"({RECOUVREMENT_MIN:.0%} au moins), à l'échelle de "
                f"{self.calage.m_par_px_reference:.4f} m/px à {DPI_REFERENCE:.0f} dpi "
                f"mesurée sur le pas de {self.calage.nb_rangees_plan} rangées.",
                f"{RECOUVREMENT_MIN:.0%}",
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
        return controles

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
        if self.choix.largeur_portail_m is not None:
            donnees["parametres"]["generalites"]["largeur_portails_m"] = (
                self.choix.largeur_portail_m
            )
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
            }
            for o in construction.ouvrages
        ]
        if construction.enceinte is not None:
            donnees["enceinte_plan"] = {
                "fermee": construction.enceinte.anneau is not None,
                "interruptions": construction.enceinte.interruptions,
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
            for c in construction.corrections_appliquees
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
