"""Lot 10 — la pose d'une cote sur la planche : sa ligne, ses flèches, sa valeur.

Les cotes arrivent calculées en Lambert 93, de `cotation_plan_masse`. Ici, on
les dessine selon la **méthode 2 de l'ISO 129**, la cotation unidirectionnelle
(brief du lot 10, D8). La relecture du 03/11/2026 a demandé de petites
flèches, et signalé que « quand il y a beaucoup d'éléments, on peut avoir des
difficultés à identifier à quelle flèche est attribuée la valeur » : posée à
côté de sa ligne, une valeur s'attribuait à la plus proche, qui n'était pas
toujours la sienne. D'où :

- le texte reste horizontal, avec un halo : `Planche.ajouter_texte` n'a pas de
  rotation (vérifié le 03/11/2026), et le moteur ne change pas ;
- la valeur **interrompt sa propre ligne**, de préférence en son milieu : elle
  n'appartient alors qu'à la ligne qui la traverse ;
- une ligne trop courte porte sa valeur sur son prolongement, au-delà d'un de
  ses bouts ; à défaut, un renvoi la relie au milieu de sa ligne ;
- les flèches sont pleines, de 1,6 mm ; une ligne plus courte que deux flèches
  et 0,6 mm les porte dehors, pointes vers l'intérieur.

La place d'une valeur se cherche sur le papier, en millimètres : c'est là que
se mesurent un texte et ses voisins. Les géométries Lambert 93 y sont portées
par la transformation de la planche, la seule qui soit (`echelle.py`). Ce que
le module ne peut pas poser proprement, il le rend (`Gene`) : c'est à
l'appelant de le dire, ou d'en tirer une planche de détail (D7).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from ..echelle import mm_vers_metres
from ..planche import Planche, Style
from .primitives import TAILLE_COTE, TRAIT_COTE

#: Longueur d'une flèche, de sa pointe à sa base, et demi-largeur de sa base,
#: en millimètres papier (D8).
FLECHE_MM = 1.6
DEMI_BASE_FLECHE_MM = 0.45

#: Une ligne plus courte que cela porte ses flèches dehors, pointes vers
#: l'intérieur : deux flèches, et 0,6 mm de ligne entre elles.
FLECHES_DEDANS_MM = 2 * FLECHE_MM + 0.6

#: Air entre une flèche et la valeur qui interrompt la ligne.
GARDE_MM = 0.4

#: La ligne se prolonge d'au moins cela au-delà de son bout, jusqu'à la valeur
#: posée dehors.
AMORCE_MM = 1.2

#: Une valeur reste à cela, au moins, du bord de la zone de dessin.
RETRAIT_CADRE_MM = 4.0

#: Marges de la boîte d'une valeur autour de son texte.
JEU_TEXTE_X_MM = 0.4
JEU_TEXTE_Y_MM = 0.3

#: Hauteur du milieu d'une valeur au-dessus de sa ligne de base, en part de son
#: corps : celle des chiffres, que la ligne doit traverser en leur milieu.
MILIEU_DU_TEXTE = 0.35

#: Les places essayées sur la ligne, en fraction de sa longueur : le milieu
#: d'abord.
FRACTIONS_SUR_LA_LIGNE = (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8)

#: Sur le prolongement, la valeur s'essaie de plus en plus loin du bout.
PROLONGEMENTS_ESSAYES = 6

#: Faute de place dans l'axe, un renvoi part du milieu de la ligne : ses
#: longueurs et ses angles avec elle.
RAYONS_RENVOI_MM = (2.5, 4.0, 6.0, 8.5)
ANGLES_RENVOI_DEG = (90, -90, 60, -60, 120, -120)

#: Un prolongement ou un renvoi qui ne fait que toucher un ouvrage, sur moins
#: que cela, ne le traverse pas.
TRAVERSEE_MM = 0.05

STYLE_FLECHE = Style(trait="#000000", epaisseur_mm=0.05, remplissage="#000000")


@dataclass(frozen=True)
class AEviter:
    """Ce qu'une valeur évite sans que ce soit interdit (D8), en Lambert 93.

    `gene` : une valeur posée dessus se lit mal, et l'appelant le dit — un
    ouvrage qu'elle cache, la clôture qu'elle fait lire comme interrompue.
    Faux pour les tables : une valeur posée dessus reste lisible (08/11/2026).

    `infranchissable` : ni le prolongement d'une ligne ni un renvoi ne la
    traversent. Prolongée à travers le local mesuré, une ligne se lisait
    jusqu'à son autre face (Auzainvilliers, 03/11/2026).
    """

    nom: str
    geometrie: BaseGeometry
    gene: bool = True
    infranchissable: bool = False


@dataclass(frozen=True)
class Gene:
    """Une cote qui se lit mal sur la planche, et pourquoi."""

    cote: object
    texte: str
    raison: str

    @property
    def message(self) -> str:
        return f"Cote « {self.texte} » : {self.raison}."


@dataclass
class _Ligne:
    """Une cote portée sur le papier, avant et après le choix de sa place."""

    cote: object
    texte: str
    #: Ses deux bouts, en Lambert 93 et en millimètres.
    a: tuple
    b: tuple
    am: tuple
    bm: tuple
    #: Sa direction sur le papier, et sa longueur.
    u: tuple
    longueur: float
    #: Les flèches dehors, et la ligne prolongée d'autant de chaque côté.
    dehors: bool
    rallonge: float
    trace: LineString
    #: Un bout coupé au bord du dessin n'a pas de flèche : la cote ne s'y
    #: arrête pas, elle sort.
    fleche_a: bool = True
    fleche_b: bool = True
    place: tuple | None = None
    boite: tuple | None = None

    @property
    def milieu(self) -> tuple:
        return ((self.am[0] + self.bm[0]) / 2.0, (self.am[1] + self.bm[1]) / 2.0)


def en_mm(planche: Planche, geometrie: BaseGeometry) -> BaseGeometry:
    """Une géométrie Lambert 93 portée sur le papier de la planche, en millimètres."""
    transformation = planche.transformation
    return transform(lambda x, y, z=None: transformation.point(x, y), geometrie)


def boite_de_texte(centre: tuple, largeur: float, hauteur: float) -> tuple:
    """La boîte d'une valeur centrée en `centre` : (x0, y0, x1, y1), en millimètres."""
    return (
        centre[0] - largeur / 2.0 - JEU_TEXTE_X_MM,
        centre[1] - hauteur / 2.0 - JEU_TEXTE_Y_MM,
        centre[0] + largeur / 2.0 + JEU_TEXTE_X_MM,
        centre[1] + hauteur / 2.0 + JEU_TEXTE_Y_MM,
    )


def _chevauchent(a: tuple, b: tuple) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _sortie(ux: float, uy: float, largeur: float, hauteur: float) -> float:
    """Du centre d'une valeur au bord de sa boîte, dans la direction (ux, uy).

    C'est là que la ligne doit l'atteindre : plus loin, le texte flotterait à
    côté de son axe ; plus près, il couvrirait la flèche.
    """
    return min(
        (largeur / 2.0 + JEU_TEXTE_X_MM) / abs(ux) if abs(ux) > 1e-9 else math.inf,
        (hauteur / 2.0 + JEU_TEXTE_Y_MM) / abs(uy) if abs(uy) > 1e-9 else math.inf,
    )


def _entre(a: tuple, b: tuple, fraction: float) -> tuple:
    return (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)


def _hors_cadre(texte: str) -> str:
    """Le libellé d'une cote arrêtée au bord du cadre : elle le dit (D5)."""
    if texte.endswith(")"):
        return texte[:-1] + ", hors cadre)"
    return texte + " (hors cadre)"


def _preparer(planche: Planche, cote, dessin: Polygon, rapport: list):
    """La cote sur le papier, arrêtée au bord du dessin si elle en sort.

    `dessin` est la zone de dessin elle-même, et non le cadre en retrait où
    se posent les valeurs : une cote qui finit à 2 mm du bord est entière.
    """
    transformation = planche.transformation
    a, b = tuple(cote.depart), tuple(cote.arrivee)
    am, bm = transformation.point(*a), transformation.point(*b)
    texte = cote.texte
    ligne = LineString([am, bm])
    fleche_a = fleche_b = True
    if ligne.length < 1e-9:
        rapport.append(f"Cote « {texte} » de longueur nulle sur la planche : non posée.")
        return None
    if not dessin.covers(ligne):
        visible = ligne.intersection(dessin)
        if visible.is_empty or visible.geom_type != "LineString" or visible.length < 1e-9:
            rapport.append(
                f"Cote « {texte} » hors du cadre de la planche : non posée."
            )
            return None
        # Elle va jusqu'au bord, et le dit (D5) : sa valeur reste la distance
        # entière, son libellé le précise, et le bout coupé n'a pas de flèche.
        fractions = sorted(
            ligne.project(Point(c)) / ligne.length for c in visible.coords
        )
        fleche_a, fleche_b = fractions[0] < 1e-9, fractions[-1] > 1.0 - 1e-9
        a, b = _entre(a, b, fractions[0]), _entre(a, b, fractions[-1])
        am, bm = transformation.point(*a), transformation.point(*b)
        texte = _hors_cadre(texte)
        rapport.append(
            f"Cote « {cote.texte} » : elle sort du cadre de la planche, et "
            "s'arrête à son bord."
        )
    longueur = math.dist(am, bm)
    u = ((bm[0] - am[0]) / longueur, (bm[1] - am[1]) / longueur)
    dehors = longueur < FLECHES_DEDANS_MM
    rallonge = FLECHE_MM + AMORCE_MM if dehors else 0.0
    trace = LineString([
        (am[0] - u[0] * rallonge, am[1] - u[1] * rallonge),
        (bm[0] + u[0] * rallonge, bm[1] + u[1] * rallonge),
    ])
    return _Ligne(
        cote=cote, texte=texte, a=a, b=b, am=am, bm=bm, u=u, longueur=longueur,
        dehors=dehors, rallonge=rallonge, trace=trace,
        fleche_a=fleche_a, fleche_b=fleche_b,
    )


def _candidats(ligne: _Ligne, largeur: float, hauteur: float) -> list:
    """Les places essayées pour la valeur, dans l'ordre où on les préfère.

    Sur la ligne d'abord, si elle loge la valeur entre ses deux flèches ; puis
    sur son prolongement, de plus en plus loin ; puis au bout d'un renvoi.
    """
    ux, uy = ligne.u
    sortie = _sortie(ux, uy, largeur, hauteur)
    candidats = []
    if not ligne.dehors:
        for fraction in FRACTIONS_SUR_LA_LIGNE:
            d = fraction * ligne.longueur
            if min(d, ligne.longueur - d) - sortie >= FLECHE_MM + GARDE_MM:
                candidats.append(("sur", (ligne.am[0] + ux * d, ligne.am[1] + uy * d), 0.0))
    pas = hauteur + 0.8
    for k in range(PROLONGEMENTS_ESSAYES):
        prolongement = (ligne.rallonge if ligne.dehors else AMORCE_MM) + k * pas
        ecart = prolongement + sortie
        candidats.append(
            ("fin", (ligne.bm[0] + ux * ecart, ligne.bm[1] + uy * ecart), prolongement)
        )
        candidats.append(
            ("debut", (ligne.am[0] - ux * ecart, ligne.am[1] - uy * ecart), prolongement)
        )
    mx, my = ligne.milieu
    for rayon in RAYONS_RENVOI_MM:
        for angle in ANGLES_RENVOI_DEG:
            cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            dx, dy = ux * cos - uy * sin, ux * sin + uy * cos
            ecart = rayon + _sortie(dx, dy, largeur, hauteur)
            candidats.append(("renvoi", (mx + dx * ecart, my + dy * ecart), (rayon, dx, dy)))
    return candidats


def poser_les_cotes(
    planche: Planche,
    cotes,
    occupees: list,
    traits=(),
    a_eviter=(),
    masques=(),
    rapport: list | None = None,
) -> list:
    """Pose les cotes sur la planche, et rend celles qui se lisent mal (`Gene`).

    - `occupees` : les boîtes, en millimètres, qu'aucune valeur ne recouvre —
      numéros de parcelle, légende, pied, repères. Chaque valeur posée s'y
      ajoute : la liste est complétée sur place.
    - `traits` : les lignes Lambert 93 qu'aucune valeur ne coupe, comme la
      ligne de coupe ; les lignes des autres cotes s'y ajoutent d'office.
    - `a_eviter` : ce qu'une valeur évite sans que ce soit interdit (`AEviter`).
    - `masques` : les boîtes sous lesquelles une ligne ne se lit plus jusqu'à sa
      flèche — la légende. La ligne se pose, et la gêne est rendue.

    Les cotes les plus courtes se placent d'abord : elles ont le moins de
    choix. Une valeur se pose, parmi les places permises, sur celle qui touche
    le moins ce qu'il faut éviter ; un renvoi compte pour une gêne de plus, et,
    pour une cote vers la limite parcellaire, toute place autre qu'au-delà de
    la limite aussi (D8, 08/11/2026). Faute de toute place, la valeur est posée
    au mieux, et la gêne est rendue.
    """
    rapport = [] if rapport is None else rapport
    x, y, largeur_zone, hauteur_zone = planche.zone_dessin()
    gauche, haut = x + RETRAIT_CADRE_MM, y + RETRAIT_CADRE_MM
    droite = x + largeur_zone - RETRAIT_CADRE_MM
    bas = y + hauteur_zone - RETRAIT_CADRE_MM
    dessin = box(x, y, x + largeur_zone, y + hauteur_zone)

    lignes = [ligne for ligne in (_preparer(planche, c, dessin, rapport) for c in cotes) if ligne]
    traits_mm = [en_mm(planche, g) for g in traits if g is not None and not g.is_empty]
    evites = [
        (e, en_mm(planche, e.geometrie))
        for e in a_eviter
        if e.geometrie is not None and not e.geometrie.is_empty
    ]
    infranchissables = [g for e, g in evites if e.infranchissable]
    hauteur = TAILLE_COTE
    genes = []

    for ligne in sorted(lignes, key=lambda l: l.longueur):
        largeur = planche.mesurer_texte(ligne.texte, TAILLE_COTE)
        candidats = _candidats(ligne, largeur, hauteur)
        autres = [o.trace for o in lignes if o is not ligne] + traits_mm
        ux, uy = ligne.u
        mx, my = ligne.milieu

        def touches(candidat):
            """`None` si la place est interdite, sinon ce qu'elle touche à éviter."""
            genre, centre, extra = candidat
            boite = boite_de_texte(centre, largeur, hauteur)
            if boite[0] < gauche or boite[2] > droite or boite[1] < haut or boite[3] > bas:
                return None
            if any(_chevauchent(boite, o) for o in occupees):
                return None
            rectangle = box(*boite)
            if any(rectangle.intersects(o) for o in autres):
                return None
            if genre == "renvoi":
                rayon, dx, dy = extra
                # Reportée, la valeur ne touche pas sa propre ligne : elle s'y
                # lirait posée.
                if rectangle.intersects(ligne.trace):
                    return None
                renvoi = LineString([(mx, my), (mx + dx * rayon, my + dy * rayon)])
                if any(renvoi.intersects(box(*o)) for o in occupees):
                    return None
                if any(renvoi.intersects(o) for o in autres):
                    return None
                if any(renvoi.intersection(g).length > TRAVERSEE_MM for g in infranchissables):
                    return None
            elif genre in ("debut", "fin"):
                bout, sens = (ligne.bm, 1.0) if genre == "fin" else (ligne.am, -1.0)
                amorce = LineString([
                    bout,
                    (bout[0] + sens * ux * extra, bout[1] + sens * uy * extra),
                ])
                if any(amorce.intersects(box(*o)) for o in occupees):
                    return None
                if any(amorce.intersection(g).length > TRAVERSEE_MM for g in infranchissables):
                    return None
            return [e for e, g in evites if rectangle.intersects(g)]

        notes = []
        for rang, candidat in enumerate(candidats):
            touche = touches(candidat)
            if touche is None:
                continue
            genre = candidat[0]
            note = len(touche) + (1 if genre == "renvoi" else 0)
            if getattr(ligne.cote, "vers_la_limite", False) and genre != "fin":
                note += 1
            notes.append((note, rang, touche))
        if notes:
            _, rang, touche = min(notes, key=lambda n: n[:2])
            ligne.place = candidats[rang]
            genants = [e.nom for e in touche if e.gene]
            if genants:
                genes.append(Gene(ligne.cote, ligne.texte, f"valeur posée sur {', '.join(genants)}"))
        else:
            ligne.place = candidats[0]
            genes.append(Gene(ligne.cote, ligne.texte, "aucune place libre, valeur posée au mieux"))
        ligne.boite = boite_de_texte(ligne.place[1], largeur, hauteur)
        occupees.append(ligne.boite)

    # Une ligne que la légende recouvre, même en partie, ne se lit plus jusqu'à
    # sa flèche (« 13,4 m (limite) », Auzainvilliers, 03/11/2026).
    for ligne in lignes:
        if any(ligne.trace.intersects(box(*m)) for m in masques):
            genes.append(Gene(ligne.cote, ligne.texte, "ligne en partie sous la légende"))

    # Les lignes et leurs flèches d'abord, les valeurs ensuite : aucune ligne
    # ne passe sur le halo d'une valeur.
    for ligne in lignes:
        _dessiner_la_ligne(planche, ligne)
    for ligne in lignes:
        cx, cy = ligne.place[1]
        planche.ajouter_texte(
            cx, cy + MILIEU_DU_TEXTE * TAILLE_COTE, ligne.texte, taille=TAILLE_COTE,
            ancre="middle", halo=True, habillage=False,
        )
    return genes


def _dessiner_la_ligne(planche: Planche, ligne: _Ligne) -> None:
    """La ligne, interrompue par sa valeur ou prolongée jusqu'à elle, et ses flèches."""
    denominateur = planche.echelle
    a, b = ligne.a, ligne.b
    n = math.dist(a, b)
    vx, vy = (b[0] - a[0]) / n, (b[1] - a[1]) / n
    genre, _, extra = ligne.place
    if genre == "sur":
        # La valeur interrompt sa ligne : on retire de la ligne ce que sa boîte
        # couvre, en fractions de la ligne, que la transformation conserve.
        papier = LineString([ligne.am, ligne.bm])
        couvert = papier.intersection(box(*ligne.boite))
        fractions = sorted(
            papier.project(Point(c)) / ligne.longueur
            for c in getattr(couvert, "coords", [])
        ) if not couvert.is_empty else []
        if len(fractions) >= 2:
            morceaux = [(0.0, fractions[0]), (fractions[-1], 1.0)]
        else:
            morceaux = [(0.0, 1.0)]
        for debut, fin in morceaux:
            if fin - debut > 1e-9:
                planche.ajouter_geometrie(
                    LineString([_entre(a, b, debut), _entre(a, b, fin)]), TRAIT_COTE
                )
    else:
        avant = mm_vers_metres(extra if genre == "debut" else ligne.rallonge, denominateur)
        apres = mm_vers_metres(extra if genre == "fin" else ligne.rallonge, denominateur)
        planche.ajouter_geometrie(
            LineString([
                (a[0] - vx * avant, a[1] - vy * avant),
                (b[0] + vx * apres, b[1] + vy * apres),
            ]),
            TRAIT_COTE,
        )
    if genre == "renvoi":
        rayon, dx, dy = extra
        mx, my = ligne.milieu
        planche.ajouter_ligne(mx, my, mx + dx * rayon, my + dy * rayon, TRAIT_COTE, habillage=False)
    # Dedans, le corps de la flèche part vers l'autre bout ; dehors, il s'en
    # éloigne, et la pointe regarde l'intérieur.
    sens = -1.0 if ligne.dehors else 1.0
    if ligne.fleche_a:
        _fleche(planche, a, (vx * sens, vy * sens))
    if ligne.fleche_b:
        _fleche(planche, b, (-vx * sens, -vy * sens))


def _fleche(planche: Planche, pointe: tuple, corps: tuple) -> None:
    """Une flèche pleine, sa pointe sur `pointe`, son corps dans la direction `corps`.

    Dessinée en Lambert 93, à la taille papier de la planche : sa pointe est
    le bout même de la cote, sans arrondi d'une conversion.
    """
    longueur = mm_vers_metres(FLECHE_MM, planche.echelle)
    demi = mm_vers_metres(DEMI_BASE_FLECHE_MM, planche.echelle)
    bx, by = pointe[0] + corps[0] * longueur, pointe[1] + corps[1] * longueur
    nx, ny = -corps[1] * demi, corps[0] * demi
    planche.ajouter_geometrie(
        Polygon([pointe, (bx + nx, by + ny), (bx - nx, by - ny)]), STYLE_FLECHE
    )
