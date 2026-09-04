"""Primitives de dessin des coupes et des plans techniques (lot 4).

Les coupes et les dessins d'ouvrages **ne sont pas cartographiques** : ils se
composent dans le repère papier, en millimètres, avec leur propre facteur
d'échelle local. La transformation Lambert 93 du moteur n'est pas détournée
pour les tracer — elle place des mètres terrain sur une feuille, ce qui n'a
aucun sens pour une élévation de poste.

`Dessin` est ce repère local. Il porte **un seul** facteur d'échelle pour les
deux axes, et c'est délibéré : c'est ce qui rend l'exagération verticale
impossible à écrire par mégarde (décision D2). Une coupe dont les deux axes
n'ont pas le même rapport n'est plus à l'échelle qu'elle annonce ; l'aperçu de
contrôle du lot 2bis en applique une, avec raison, et il ne faut surtout pas
reprendre son code ici par mimétisme.

La conversion mètres → millimètres passe par `dp_socle.echelle`, comme partout
ailleurs dans le projet : elle n'est refaite nulle part.

Le moteur `Planche` du lot 1 n'est pas modifié. Là où il manque une primitive —
il ne trace, en millimètres, que des lignes et des rectangles — la forme se
construit par-dessus (voir `forme_pleine`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from ..echelle import formater_echelle, metres_vers_mm, mm_vers_metres
from ..erreurs import ErreurComposition
from ..planche import PT, Planche, Style

#: Traits normalisés des dessins techniques.
TRAIT_FORT = Style(trait="#000000", epaisseur_mm=0.35)
TRAIT_MOYEN = Style(trait="#000000", epaisseur_mm=0.25)
TRAIT_FIN = Style(trait="#000000", epaisseur_mm=0.15)
TRAIT_COTE = Style(trait="#000000", epaisseur_mm=0.12)
#: Trait d'axe : alternance long / point, convention du dessin technique.
TRAIT_AXE = Style(trait="#000000", epaisseur_mm=0.25, tirets="4 1.2 0.6 1.2")

TAILLE_COTE = 6.5 * PT
TAILLE_MENTION = 8 * PT

#: Pas des hachures de sol, sur le papier. Constant quelle que soit l'échelle :
#: une hachure est une convention de dessin, pas une mesure.
PAS_HACHURE_MM = 1.3
#: Épaisseur de la bande hachurée sous une ligne de sol.
EPAISSEUR_SOL_MM = 3.0

#: Hauteur de la silhouette humaine, en mètres. 1,75 m : la taille qui donne
#: l'échelle sans prétendre décrire quelqu'un.
HAUTEUR_SILHOUETTE_M = 1.75


# ---------------------------------------------------------------------------
# Repère local d'un dessin
# ---------------------------------------------------------------------------


@dataclass
class Dessin:
    """Repère d'un dessin non cartographique, en millimètres papier.

    `origine_mm` est le point de la feuille où tombe `origine_m` du dessin.
    L'axe des ordonnées monte, comme sur une élévation ; le moteur, lui,
    compte vers le bas, et la conversion est faite ici une fois pour toutes.
    """

    planche: Planche
    denominateur: int
    origine_mm: tuple
    origine_m: tuple = (0.0, 0.0)
    #: Cadre que le dessin ne doit pas déborder, en millimètres papier.
    cadre_mm: tuple | None = None
    #: Enveloppe de ce qui a été tracé, pour le contrôle de débordement.
    _etendue: list = field(default_factory=list, init=False)

    def __post_init__(self):
        # Une seule conversion, pour les deux axes : voir l'en-tête du module.
        self.mm_par_metre = metres_vers_mm(1.0, self.denominateur)

    # -- conversion ----------------------------------------------------------

    def longueur(self, valeur_m: float) -> float:
        """Longueur papier, en millimètres, d'une longueur du dessin."""
        return metres_vers_mm(valeur_m, self.denominateur)

    def metres(self, longueur_mm: float) -> float:
        """Longueur du dessin correspondant à une longueur de papier.

        Les écarts de mise en page — le retrait d'une ligne de cote sous le
        dessin, le décalage d'un texte — se pensent en millimètres de papier
        et non en mètres de terrain : ils doivent rester les mêmes quelle que
        soit l'échelle. Exprimés en mètres, ils enflaient avec elle, et la
        coupe des tables au 1/50 sortait de son cadre.
        """
        return mm_vers_metres(longueur_mm, self.denominateur)

    def point(self, x_m: float, y_m: float) -> tuple:
        """Un point du dessin vers le repère papier."""
        x0_mm, y0_mm = self.origine_mm
        x0_m, y0_m = self.origine_m
        return (
            x0_mm + self.longueur(x_m - x0_m),
            y0_mm - self.longueur(y_m - y0_m),
        )

    def _noter(self, *points_mm) -> None:
        self._etendue.extend(points_mm)

    # -- tracés --------------------------------------------------------------

    def ligne(self, depart_m, arrivee_m, style: Style = TRAIT_MOYEN) -> None:
        x1, y1 = self.point(*depart_m)
        x2, y2 = self.point(*arrivee_m)
        self._noter((x1, y1), (x2, y2))
        self.planche.ajouter_ligne(x1, y1, x2, y2, style)

    def polyligne(self, points_m, style: Style = TRAIT_MOYEN, fermer: bool = False) -> None:
        """Suite de segments jointifs.

        Le moteur ne trace pas de polyligne en millimètres, mais ses segments
        ont des extrémités et des jointures arrondies : une suite de segments
        partageant leurs extrémités se lit comme un trait continu.
        """
        points = list(points_m)
        if fermer and points and points[0] != points[-1]:
            points.append(points[0])
        for depart, arrivee in zip(points, points[1:]):
            self.ligne(depart, arrivee, style)

    def rectangle(self, x_m, y_m, largeur_m, hauteur_m, style: Style = TRAIT_MOYEN) -> None:
        """Rectangle à côtés parallèles aux axes, coin bas-gauche en (x, y)."""
        haut_gauche = self.point(x_m, y_m + hauteur_m)
        largeur_mm = self.longueur(largeur_m)
        hauteur_mm = self.longueur(hauteur_m)
        self._noter(
            haut_gauche, (haut_gauche[0] + largeur_mm, haut_gauche[1] + hauteur_mm)
        )
        self.planche.ajouter_rectangle(
            haut_gauche[0], haut_gauche[1], largeur_mm, hauteur_mm, style
        )

    def texte(
        self, x_m, y_m, texte: str, taille: float = TAILLE_COTE,
        decalage_mm: tuple = (0.0, 0.0), **kwargs,
    ) -> None:
        x_mm, y_mm = self.point(x_m, y_m)
        x_mm += decalage_mm[0]
        y_mm += decalage_mm[1]
        self._noter((x_mm, y_mm))
        self.planche.ajouter_texte(x_mm, y_mm, texte, taille=taille, **kwargs)

    # -- contrôle de débordement --------------------------------------------

    def etendue_mm(self) -> tuple | None:
        """Enveloppe de ce qui a été tracé : (x, y, largeur, hauteur)."""
        if not self._etendue:
            return None
        xs = [p[0] for p in self._etendue]
        ys = [p[1] for p in self._etendue]
        return (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def verifier_cadre(self, libelle: str, marge_mm: float = 0.5) -> None:
        """Refuse un dessin qui sort de la place qu'on lui a donnée.

        Les tracés en millimètres passent par l'habillage, qui n'est pas
        découpé sur la zone de dessin : un dessin trop grand ne serait pas
        rogné, il s'imprimerait par-dessus le cartouche. Mieux vaut ne pas
        produire la planche.
        """
        if self.cadre_mm is None:
            return
        etendue = self.etendue_mm()
        if etendue is None:
            return
        x, y, largeur, hauteur = etendue
        cx, cy, clargeur, chauteur = self.cadre_mm
        deborde = (
            x < cx - marge_mm
            or y < cy - marge_mm
            or x + largeur > cx + clargeur + marge_mm
            or y + hauteur > cy + chauteur + marge_mm
        )
        if deborde:
            raise ErreurComposition(
                f"{libelle} : le dessin occupe "
                f"{largeur:.1f} x {hauteur:.1f} mm en ({x:.1f}, {y:.1f}) et sort "
                f"du cadre de {clargeur:.1f} x {chauteur:.1f} mm en "
                f"({cx:.1f}, {cy:.1f}) qui lui est réservé, à l'échelle "
                f"{formater_echelle(self.denominateur)}. Le dessin n'est pas "
                "rogné : il s'imprimerait par-dessus le reste de la planche."
            )


# ---------------------------------------------------------------------------
# Formes pleines
# ---------------------------------------------------------------------------

#: Pas de balayage d'une forme pleine, en millimètres, et recouvrement des
#: traits qui la remplissent. Un pas de 0,22 mm sous un trait de 0,40 mm : les
#: passes se chevauchent largement, l'aplat est franc et n'est pas rayé.
PAS_REMPLISSAGE_MM = 0.22
RECOUVREMENT_REMPLISSAGE = 1.8

#: Au-delà de cette hauteur, le pas s'élargit à proportion : une forme de
#: 200 mm remplie au pas de 0,22 mm ferait un millier de traits pour un aplat
#: qu'un pas plus large rend aussi bien.
HAUTEUR_PAS_CONSTANT_MM = 45.0


def forme_pleine(planche: Planche, points_mm, couleur: str, filet: str | None = None,
                 epaisseur_mm: float = 0.25) -> None:
    """Trace une forme quelconque, pleine, dans le repère papier.

    Le moteur du lot 1 ne trace un contour quelconque que dans le repère
    Lambert 93 (`ajouter_geometrie`) ; en millimètres il n'offre que la ligne
    et le rectangle. Une silhouette humaine et le triangle d'un repère de coupe
    ne sont ni l'une ni l'autre, et le brief interdit de toucher au moteur.

    La forme est donc remplie par balayage : des traits jointifs, dans le
    contour, plus le contour lui-même. C'est un aplat vectoriel, qui reste net
    à toute résolution et qui se mesure dans le PDF produit.

    ⚠️ La voie évidente — déclarer la forme comme motif dans `<defs>` et la
    peindre par un rectangle, comme le fait la hachure des bâtiments de
    DP 1-3 — a été essayée et écartée le 04/09/2026 : cairo **pixellise** les
    motifs. Mesurée sur un aperçu à 600 dpi, une silhouette de 35 mm en
    ressortait floue, bords fondus. Un aplat de 20 mm passait, un de 3 mm
    était illisible. La taille du carreau décide, ce qui est exactement le
    genre de dépendance qu'on ne veut pas sur une planche déposée.
    """
    points = list(points_mm)
    if len(points) < 3:
        raise ErreurComposition(
            f"Forme pleine à {len(points)} point(s) : il en faut au moins trois."
        )
    contour = Polygon(points)
    if not contour.is_valid:
        contour = contour.buffer(0)
    if contour.is_empty or contour.area <= 0:
        raise ErreurComposition("Forme pleine d'aire nulle.")

    minx, miny, maxx, maxy = contour.bounds
    hauteur = maxy - miny
    pas = PAS_REMPLISSAGE_MM * max(1.0, hauteur / HAUTEUR_PAS_CONSTANT_MM)
    remplissage = Style(
        trait=couleur, epaisseur_mm=pas * RECOUVREMENT_REMPLISSAGE, remplissage="none"
    )

    ordonnee = miny + pas / 2.0
    while ordonnee < maxy:
        morceaux = LineString(
            [(minx - 1.0, ordonnee), (maxx + 1.0, ordonnee)]
        ).intersection(contour)
        if not morceaux.is_empty:
            parties = (
                morceaux.geoms if morceaux.geom_type.startswith("Multi") else [morceaux]
            )
            for partie in parties:
                if partie.geom_type != "LineString" or partie.length <= 0:
                    continue
                (x1, y1), (x2, y2) = partie.coords[0], partie.coords[-1]
                planche.ajouter_ligne(x1, y1, x2, y2, remplissage)
        ordonnee += pas

    # Le contour, pour que le bord soit franc : les traits de balayage ont des
    # bouts arrondis qui dentellent les obliques, et le contour les recouvre.
    trait = Style(
        trait=filet or couleur, epaisseur_mm=epaisseur_mm, remplissage="none"
    )
    boucle = points + [points[0]]
    for depart, arrivee in zip(boucle, boucle[1:]):
        planche.ajouter_ligne(depart[0], depart[1], arrivee[0], arrivee[1], trait)


# ---------------------------------------------------------------------------
# Hachure de sol
# ---------------------------------------------------------------------------


def hachurer(dessin: Dessin, contour_m, pas_mm: float = PAS_HACHURE_MM,
             angle_deg: float = 45.0, style: Style = TRAIT_FIN) -> None:
    """Hachure l'intérieur d'un contour donné dans le repère du dessin.

    Les hachures sont calculées en géométrie plutôt que confiées à un motif
    SVG : un motif se répète en coordonnées de page et ne connaît pas le
    contour, ce qui oblige à un masque — et les traits obtenus ici se
    mesurent dans le PDF, contrairement à ceux d'un motif.
    """
    contour = Polygon(contour_m)
    if not contour.is_valid:
        contour = contour.buffer(0)
    if contour.is_empty or contour.area <= 0:
        return

    pas_m = pas_mm / dessin.mm_par_metre
    if pas_m <= 0:
        raise ErreurComposition(f"Pas de hachure invalide : {pas_mm} mm.")

    minx, miny, maxx, maxy = contour.bounds
    diagonale = math.hypot(maxx - minx, maxy - miny)
    centre = ((minx + maxx) / 2.0, (miny + maxy) / 2.0)
    angle = math.radians(angle_deg)
    # Direction des hachures, et normale le long de laquelle on les espace.
    dx, dy = math.cos(angle), math.sin(angle)
    nx, ny = -dy, dx

    nombre = int(diagonale / pas_m) + 2
    for index in range(-nombre, nombre + 1):
        decalage = index * pas_m
        base = (centre[0] + nx * decalage, centre[1] + ny * decalage)
        trait = LineString(
            [
                (base[0] - dx * diagonale, base[1] - dy * diagonale),
                (base[0] + dx * diagonale, base[1] + dy * diagonale),
            ]
        )
        morceaux = trait.intersection(contour)
        if morceaux.is_empty:
            continue
        parties = (
            morceaux.geoms if morceaux.geom_type.startswith("Multi") else [morceaux]
        )
        for partie in parties:
            if partie.geom_type != "LineString" or partie.length <= 0:
                continue
            coords = list(partie.coords)
            dessin.ligne(coords[0], coords[-1], style)


def bande_de_sol(points_m, epaisseur_m: float) -> list:
    """Contour d'une bande d'épaisseur constante sous une ligne de sol.

    Hachurer tout ce qui est sous le terrain noircirait la moitié de la
    planche : la convention est une bande, et c'est celle du PDF de profil du
    bureau d'études comme du dossier de référence.
    """
    points = list(points_m)
    if len(points) < 2:
        raise ErreurComposition("Ligne de sol à moins de deux points.")
    dessous = [(x, y - epaisseur_m) for x, y in reversed(points)]
    return points + dessous


def sol_hachure(dessin: Dessin, points_m, epaisseur_mm: float = EPAISSEUR_SOL_MM,
                style_ligne: Style = TRAIT_FORT) -> None:
    """Ligne de sol en trait plein, surmontant sa bande hachurée."""
    epaisseur_m = epaisseur_mm / dessin.mm_par_metre
    hachurer(dessin, bande_de_sol(points_m, epaisseur_m))
    dessin.polyligne(points_m, style_ligne)


# ---------------------------------------------------------------------------
# Silhouette humaine
# ---------------------------------------------------------------------------


def _contour_silhouette() -> list:
    """Silhouette debout, normalisée : 1 de haut, pieds sur y = 0.

    Un personnage donne l'échelle d'un coup d'œil, ce qu'aucune cote ne fait
    aussi vite. C'est ce que porte le dossier de référence, et le PDF de profil
    du bureau d'études.

    Le contour est parcouru d'un seul tenant : moitié droite de la tête, côté
    droit du corps, entrejambe, côté gauche remonté en miroir, moitié gauche de
    la tête. Ne décrire que la moitié droite de la tête laissait le contour se
    refermer en ligne droite sur l'autre moitié, et la silhouette avait le
    crâne plat à gauche.
    """
    rayon = 0.062
    tete_centre_y = 1.0 - rayon

    def arc(depart_deg: int, arrivee_deg: int) -> list:
        pas = 20 if arrivee_deg > depart_deg else -20
        return [
            (
                rayon * math.sin(math.radians(angle)),
                tete_centre_y + rayon * math.cos(math.radians(angle)),
            )
            for angle in range(depart_deg, arrivee_deg + pas, pas)
        ]

    cote_droit = [
        (0.022, 0.855),   # cou
        (0.105, 0.815),   # épaule
        (0.118, 0.600),   # bras, bord externe
        (0.112, 0.470),   # poignet
        (0.088, 0.462),   # main
        # Le bord interne du bras reste en dehors de la hanche : ramené plus
        # près du corps, il coupait le trait taille-hanche et le contour
        # devenait un polygone auto-intersectant, rempli par morceaux.
        (0.086, 0.490),   # bras, bord interne
        (0.084, 0.620),
        (0.070, 0.760),   # aisselle
        (0.052, 0.560),   # taille
        (0.078, 0.500),   # hanche
        (0.072, 0.260),   # cuisse
        (0.062, 0.020),   # cheville
        (0.100, 0.000),   # pointe du pied
        (0.046, 0.000),   # talon
        (0.038, 0.260),
        (0.000, 0.470),   # entrejambe
    ]
    # Le miroir repart de l'entrejambe, déjà posé : on ne le redouble pas.
    gauche = [(-x, y) for x, y in reversed(cote_droit[:-1])]
    # La moitié gauche de la tête remonte jusqu'au sommet, où le contour se
    # referme : ce sommet est déjà le premier point, on l'omet.
    return arc(0, 180) + cote_droit + gauche + arc(180, 360)[1:-1]


#: Contour normalisé, calculé une fois.
CONTOUR_SILHOUETTE = _contour_silhouette()


def silhouette(dessin: Dessin, x_m: float, y_sol_m: float,
               hauteur_m: float = HAUTEUR_SILHOUETTE_M,
               couleur: str = "#4a4a4a") -> None:
    """Silhouette humaine à l'échelle du dessin, posée sur le sol."""
    points_mm = [
        dessin.point(x_m + x * hauteur_m, y_sol_m + y * hauteur_m)
        for x, y in CONTOUR_SILHOUETTE
    ]
    forme_pleine(dessin.planche, points_mm, couleur)
    # La silhouette passe par un motif, invisible au contrôle d'étendue :
    # ses extrémités sont notées pour que le débordement se voie quand même.
    dessin._noter(*points_mm)


# ---------------------------------------------------------------------------
# Lignes de cote
# ---------------------------------------------------------------------------

#: Demi-longueur du trait oblique aux extrémités d'une cote, en millimètres.
PATTE_COTE_MM = 0.9
#: Place minimale, en millimètres, pour écrire la cote entre ses extrémités.
JEU_TEXTE_MM = 1.2


def cote_horizontale(dessin: Dessin, x1_m: float, x2_m: float, y_m: float,
                     texte: str, au_dessus: bool = True) -> None:
    """Ligne de cote horizontale, extrémités obliques et cote centrée.

    Quand la place manque entre les deux extrémités, la cote est reportée à
    côté du dessin plutôt que superposée au trait : une cote illisible est une
    cote absente, et personne ne la redemande.
    """
    gauche, droite = sorted((x1_m, x2_m))
    p1 = dessin.point(gauche, y_m)
    p2 = dessin.point(droite, y_m)
    dessin.planche.ajouter_ligne(p1[0], p1[1], p2[0], p2[1], TRAIT_COTE)
    dessin._noter(p1, p2)
    for point in (p1, p2):
        dessin.planche.ajouter_ligne(
            point[0] - PATTE_COTE_MM, point[1] + PATTE_COTE_MM,
            point[0] + PATTE_COTE_MM, point[1] - PATTE_COTE_MM,
            TRAIT_COTE,
        )

    largeur_texte = dessin.planche.mesurer_texte(texte, TAILLE_COTE)
    disponible = p2[0] - p1[0]
    ecart = 1.0 if au_dessus else -1.0
    if largeur_texte + 2 * JEU_TEXTE_MM <= disponible:
        x_texte = (p1[0] + p2[0]) / 2.0
        ancre = "middle"
    else:
        x_texte = p2[0] + JEU_TEXTE_MM
        ancre = "start"
    y_texte = p1[1] - ecart * 1.1 + (0.0 if au_dessus else TAILLE_COTE)
    dessin.planche.ajouter_texte(
        x_texte, y_texte, texte, taille=TAILLE_COTE, ancre=ancre
    )
    dessin._noter((x_texte, y_texte), (x_texte + largeur_texte, y_texte))


def cote_verticale(dessin: Dessin, y1_m: float, y2_m: float, x_m: float,
                   texte: str, a_gauche: bool = True) -> None:
    """Ligne de cote verticale. Le texte se pose toujours à côté du trait."""
    bas, haut = sorted((y1_m, y2_m))
    p1 = dessin.point(x_m, bas)
    p2 = dessin.point(x_m, haut)
    dessin.planche.ajouter_ligne(p1[0], p1[1], p2[0], p2[1], TRAIT_COTE)
    dessin._noter(p1, p2)
    for point in (p1, p2):
        dessin.planche.ajouter_ligne(
            point[0] - PATTE_COTE_MM, point[1] + PATTE_COTE_MM,
            point[0] + PATTE_COTE_MM, point[1] - PATTE_COTE_MM,
            TRAIT_COTE,
        )
    largeur_texte = dessin.planche.mesurer_texte(texte, TAILLE_COTE)
    x_texte = p1[0] + (-1.2 if a_gauche else 1.2)
    y_texte = (p1[1] + p2[1]) / 2.0 + TAILLE_COTE * 0.35
    dessin.planche.ajouter_texte(
        x_texte, y_texte, texte, taille=TAILLE_COTE,
        ancre="end" if a_gauche else "start",
    )
    borne = x_texte - largeur_texte if a_gauche else x_texte + largeur_texte
    dessin._noter((borne, y_texte))


def attache(dessin: Dessin, x_m: float, y1_m: float, y2_m: float) -> None:
    """Trait d'attache reliant l'objet coté à sa ligne de cote."""
    dessin.ligne((x_m, y1_m), (x_m, y2_m), TRAIT_COTE)


# ---------------------------------------------------------------------------
# Repères et mentions
# ---------------------------------------------------------------------------

#: Côté du triangle d'un repère de coupe, en millimètres.
COTE_REPERE_MM = 2.6


def repere_coupe(planche: Planche, x_mm: float, y_mm: float, lettre: str,
                 direction: tuple, couleur: str = "#000000") -> None:
    """Repère A ou A' : la lettre, et le triangle plein pointant vers la coupe.

    `direction` est le vecteur unitaire, dans le repère papier, du sens de
    lecture de la coupe — celui vers lequel pointe le triangle, comme sur le
    plan de masse du dossier de référence.
    """
    dx, dy = direction
    norme = math.hypot(dx, dy)
    if norme == 0:
        raise ErreurComposition("Repère de coupe sans direction.")
    dx, dy = dx / norme, dy / norme
    # Normale, pour la base du triangle.
    nx, ny = -dy, dx
    demi = COTE_REPERE_MM / 2.0
    pointe = (x_mm + dx * COTE_REPERE_MM, y_mm + dy * COTE_REPERE_MM)
    forme_pleine(
        planche,
        [
            pointe,
            (x_mm + nx * demi, y_mm + ny * demi),
            (x_mm - nx * demi, y_mm - ny * demi),
        ],
        couleur,
    )
    planche.ajouter_texte(
        x_mm - dx * 3.4, y_mm - dy * 3.4 + 1.0, lettre,
        taille=11 * PT, ancre="middle", gras=True, couleur=couleur, halo=True,
    )


def mention_echelle(planche: Planche, x_mm: float, y_mm: float, denominateur: int,
                    titre: str | None = None, ancre: str = "start") -> float:
    """Titre et échelle en clair d'un dessin qui n'est pas celui du cartouche.

    Le cartouche ne peut annoncer qu'une échelle. Tout autre dessin porte la
    sienne à côté de lui, sans quoi rien ne dit à quelle échelle il est lu.
    """
    ordonnee = y_mm
    if titre:
        planche.ajouter_texte(
            x_mm, ordonnee, titre, taille=TAILLE_MENTION, gras=True, ancre=ancre
        )
        ordonnee += TAILLE_MENTION * 1.45
    planche.ajouter_texte(
        x_mm, ordonnee, f"Échelle {formater_echelle(denominateur)}",
        taille=TAILLE_MENTION, ancre=ancre,
    )
    return ordonnee + TAILLE_MENTION * 1.45


def echelle_du_dessin(largeur_m: float, hauteur_m: float, zone_mm: tuple,
                      valeurs, marge: float = 0.0, libelle: str = "dessin") -> int:
    """Plus grande échelle de la liste où le contenu utile tient dans la zone.

    Reprend `dp_socle.echelle.echelle_adaptative` pour ne pas refaire son
    calcul, et rhabille son message d'erreur du nom du dessin concerné : à
    quatre dessins par planche, savoir lequel ne tient pas fait gagner le
    diagnostic.
    """
    from ..echelle import echelle_adaptative
    from ..erreurs import ErreurEchelle

    try:
        return echelle_adaptative(
            largeur_m, hauteur_m, zone_mm, marge=marge, valeurs=valeurs
        )
    except ErreurEchelle as exc:
        raise ErreurEchelle(f"{libelle} — {exc}") from exc


def union_valide(geometries):
    """Union d'un lot de géométries, chacune passée par `make_valid` (D6)."""
    from shapely import make_valid

    valides = [make_valid(g) for g in geometries if g is not None and not g.is_empty]
    if not valides:
        return None
    return unary_union(valides)
