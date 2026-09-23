"""Pistes d'un plan projet PDF : du tracé du plan à la piste d'un vrai plan (lot 2ter).

Le plan PDF donne le tracé et le type de chaque piste, pas sa géométrie : un
trait de PowerPoint, fait de segments mis bout à bout, avec un angle vif à
chaque changement de direction. Un plan de bureau d'études dessine autre chose :
une bande de largeur constante, dont les virages sont des arcs — de 12 m de
rayon sur les plans de Sarnois, mesurés le 23/09/2026.

Instruction du chef de projet du 23/09/2026 : partir du tracé et du type que le
plan donne, et reproduire la piste comme sur un vrai plan — **5 m de large**, et
des virages qui respectent un rayon de courbure. Le rayon retenu le même jour
est celui de la « voie engins » des pompiers : **11 m au bord intérieur** du
virage, soit 13,5 m sur l'axe d'une piste de 5 m.

Trois cas se présentent aux extrémités d'un tracé, tous trois sur les plans
d'essai :

- **deux tracés mis bout à bout** — à Gannay, la piste existante et la piste à
  créer ferment une boucle, leurs extrémités à 1,9 et 2,2 m l'une de l'autre.
  C'est un virage comme un autre, arrondi de même, et partagé entre les deux ;
- **un tracé qui aboutit sur un autre, en T** — la bretelle du portail de
  Gannay, entre la boucle et l'anneau. L'extrémité est menée jusqu'à l'axe
  qu'elle rejoint, et les deux angles rentrants du raccord sont arrondis au même
  rayon intérieur, dans la limite de la place ;
- **une extrémité libre** — une piste qui s'arrête à un ouvrage. La bande s'y
  arrête d'équerre. À Bray, les deux pistes finissent au local technique, à
  3,6 m l'une de l'autre : ce sont deux accès, pas une piste continue.

Ce qui ne tient pas se dit. Un virage que le tracé ne laisse pas arrondir au
rayon voulu l'est au plus grand rayon qui tient, et une note le dit ; deux
virages trop rapprochés pour être arrondis chacun se fondent en un seul, pris
sur les deux alignements qui les encadrent — c'est ce que ferait un
projeteur —, et une note le dit aussi.

Tout se fait en mètres au sol, dans le repère du DXF HelioScope. Ce module ne
lit pas le PDF, et ne connaît rien du contrat.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

#: Largeur d'une piste, en mètres : instruction du chef de projet du
#: 23/09/2026, pour toutes les pistes du plan, lourdes ou légères, existantes
#: ou à créer.
LARGEUR_PISTE_M = 5.0

#: Rayon d'un virage au bord intérieur de la piste, en mètres : celui de la
#: « voie engins » des pompiers, retenu par le chef de projet le 23/09/2026.
#: Les plans du BE de Sarnois tracent leurs virages à 12 m.
RAYON_INTERIEUR_M = 11.0

#: Le même rayon, rapporté à l'axe : c'est l'axe que l'on arrondit.
RAYON_AXE_M = RAYON_INTERIEUR_M + LARGEUR_PISTE_M / 2.0

#: Deux extrémités de tracé à moins de ceci l'une de l'autre sont deux traits
#: mis bout à bout, en mètres. Mesuré le 23/09/2026 : 1,9 et 2,2 m aux deux
#: raccords de la boucle de Gannay ; 3,6 m entre les deux pistes de Bray, qui
#: aboutissent chacune au local technique sans se continuer.
JONCTION_M = 3.0

#: Une extrémité à moins de ceci de l'axe d'un autre tracé s'y raccorde en T,
#: en mètres. Mesuré le 23/09/2026 : de 0,04 à 0,36 m aux trois raccords de
#: Gannay.
RACCORD_M = 3.0

#: Pas angulaire des arcs, en degrés : 5° font une flèche de 1,3 cm sur un
#: rayon de 13,5 m, invisible à toute échelle du dossier.
PAS_ARC_DEG = 5.0

#: Deux virages voisins de même sens ne se fondent en un seul que si leur
#: déviation cumulée reste en deçà, en degrés : au delà, c'est un demi-tour,
#: dont le sommet commun partirait à l'infini.
DEVIATION_FUSION_MAX_DEG = 160.0

#: Déviation en deçà de laquelle un sommet est tenu pour aligné, en radians.
ALIGNE_RAD = 1e-6

#: Jeu entre le bord d'une piste serrée contre la clôture et la clôture, en
#: mètres : « plus près de la clôture, sans la toucher », demande du chef de
#: projet du 23/09/2026 pour la boucle de Gannay. Un demi-mètre laisse la place
#: des poteaux et de leurs massifs.
JEU_CLOTURE_M = 0.5

#: Une piste longe la clôture quand au moins cette part de son axe court à
#: moins de `LONGE_M` d'elle, du côté de l'enceinte. La boucle de Gannay y est
#: tout entière, à 2,1-5,5 m ; la bretelle du portail, qui la franchit, et
#: l'anneau, dehors, n'y sont pas.
PART_LE_LONG = 0.8
LONGE_M = 10.0


@dataclass(frozen=True)
class AxePiste:
    """Le tracé d'une piste tel que le plan le donne, en mètres au sol."""

    categorie: str
    libelle: str
    ligne: LineString


@dataclass
class PisteDessinee:
    """Une piste comme un vrai plan la dessine : son axe arrondi, et sa bande."""

    categorie: str
    libelle: str
    axe: LineString
    #: La bande de 5 m, raccords en T compris : un polygone, ou plusieurs.
    surface: BaseGeometry
    #: Rayon appliqué sur l'axe à chacun de ses virages, en mètres.
    rayons_axe_m: list = field(default_factory=list)
    #: Rayon intérieur appliqué à chaque angle rentrant de ses raccords en T.
    rayons_raccords_m: list = field(default_factory=list)

    @property
    def rayon_axe_min_m(self) -> float | None:
        return min(self.rayons_axe_m) if self.rayons_axe_m else None

    @property
    def polygones(self) -> list[Polygon]:
        if self.surface.geom_type == "Polygon":
            return [self.surface]
        return [g for g in getattr(self.surface, "geoms", []) if g.geom_type == "Polygon"]


# ---------------------------------------------------------------------------
# Géométrie plane
# ---------------------------------------------------------------------------


def _direction(a, b) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    norme = math.hypot(dx, dy)
    return (dx / norme, dy / norme)


def _deviation(u, v) -> float:
    """Angle signé de la direction u à la direction v, en radians, dans ]-π, π]."""
    return math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1])


def _intersection_droites(p, u, q, v):
    """Intersection des droites (p, u) et (q, v), ou None si elles sont parallèles."""
    determinant = u[0] * v[1] - u[1] * v[0]
    if abs(determinant) < 1e-9:
        return None
    t = ((q[0] - p[0]) * v[1] - (q[1] - p[1]) * v[0]) / determinant
    return (p[0] + t * u[0], p[1] + t * u[1])


def _sans_doublons(coords: list, ferme: bool) -> list:
    """Les sommets d'un tracé, sans sommet répété ni, s'il est fermé, sa reprise."""
    resultat = []
    for point in coords:
        if not resultat or math.dist(point, resultat[-1]) > 0.01:
            resultat.append((float(point[0]), float(point[1])))
    if ferme and len(resultat) > 1 and math.dist(resultat[0], resultat[-1]) <= 0.01:
        resultat.pop()
    return resultat


# ---------------------------------------------------------------------------
# Arrondi des virages d'un chemin
# ---------------------------------------------------------------------------


@dataclass
class _Chemin:
    """Une suite de sommets, et le tracé d'origine de chacun de ses segments.

    Un chemin enchaîne un ou plusieurs tracés mis bout à bout ; le segment k va
    du sommet k au suivant, et `troncons[k]` dit de quel tracé il vient. Un
    chemin fermé a autant de segments que de sommets.
    """

    sommets: list
    troncons: list
    ferme: bool

    def _voisins(self, i: int) -> tuple[int, int]:
        n = len(self.sommets)
        return (i - 1) % n, (i + 1) % n

    def arrondissable(self, i: int) -> bool:
        """Un sommet d'extrémité ne s'arrondit pas : rien n'y tourne."""
        return self.ferme or 0 < i < len(self.sommets) - 1

    def deviation(self, i: int) -> float:
        if not self.arrondissable(i):
            return 0.0
        avant, apres = self._voisins(i)
        s = self.sommets
        return _deviation(_direction(s[avant], s[i]), _direction(s[i], s[apres]))

    def segments(self) -> list[tuple[int, int]]:
        n = len(self.sommets)
        if self.ferme:
            return [(i, (i + 1) % n) for i in range(n)]
        return [(i, i + 1) for i in range(n - 1)]

    def fondre(self, a: int, b: int, point) -> None:
        """Remplace les sommets a et b = a + 1 par un seul, le segment a-b disparaissant."""
        n = len(self.sommets)
        if b == 0:
            # Le segment a-b ferme le chemin : on le fait tourner pour que la
            # fusion tombe à l'intérieur des listes.
            self.sommets = self.sommets[1:] + self.sommets[:1]
            self.troncons = self.troncons[1:] + self.troncons[:1]
            a, b = n - 2, n - 1
        self.sommets[a] = point
        del self.sommets[b]
        del self.troncons[a]


def _sans_sommet_confondu(sommets: list, troncons: list, ferme: bool) -> _Chemin:
    """Un chemin sans deux sommets consécutifs confondus.

    Deux tracés serrés contre la clôture se raccordent sur le même alignement :
    le sommet de raccord tombe alors sur le premier sommet du tracé suivant, et
    un segment de longueur nulle n'a pas de direction. Le segment disparaît ;
    celui qui suit garde son tracé d'origine.
    """
    sommets, troncons = list(sommets), list(troncons)
    k = 1
    while k < len(sommets):
        if math.dist(sommets[k - 1], sommets[k]) < 0.01:
            del sommets[k]
            del troncons[k - 1]
        else:
            k += 1
    if ferme and len(sommets) > 1 and math.dist(sommets[0], sommets[-1]) < 0.01:
        # Le segment nul est celui qui refermait le chemin : le dernier.
        sommets.pop()
        troncons.pop()
    return _Chemin(sommets, troncons, ferme)


def _tangentes(chemin: _Chemin, rayon: float) -> list[float]:
    """Longueur prise sur chaque segment voisin par l'arc de chaque sommet."""
    return [
        rayon * math.tan(abs(chemin.deviation(i)) / 2.0)
        for i in range(len(chemin.sommets))
    ]


def _fusionner_les_virages_serres(chemin: _Chemin, rayon: float) -> list[str]:
    """Fond deux à deux les virages qui n'ont pas la place d'être arrondis.

    Deux virages de même sens se fondent au sommet commun de leurs deux
    alignements extérieurs : c'est le virage qu'un projeteur tracerait. Deux
    virages de sens contraires sont un décrochement du trait — un segment court
    entre deux alignements presque parallèles, qui reste d'un raccord mal
    ajusté dans PowerPoint : ses deux sommets se fondent en son milieu.
    """
    notes = []
    while len(chemin.sommets) > (3 if chemin.ferme else 2):
        tangentes = _tangentes(chemin, rayon)
        exces = []
        for a, b in chemin.segments():
            longueur = math.dist(chemin.sommets[a], chemin.sommets[b])
            besoin = tangentes[a] + tangentes[b]
            if besoin > longueur + 1e-9 and chemin.arrondissable(a) and chemin.arrondissable(b):
                exces.append((besoin / max(longueur, 1e-9), a, b, longueur))
        fondu = False
        for _, a, b, longueur in sorted(exces, reverse=True):
            deviation_a, deviation_b = chemin.deviation(a), chemin.deviation(b)
            avant, _ = chemin._voisins(a)
            _, apres = chemin._voisins(b)
            s = chemin.sommets
            if deviation_a * deviation_b > 0:
                if abs(deviation_a + deviation_b) > math.radians(DEVIATION_FUSION_MAX_DEG):
                    continue
                point = _intersection_droites(
                    s[avant], _direction(s[avant], s[a]), s[b], _direction(s[b], s[apres])
                )
                if point is None:
                    continue
                note = (
                    f"deux virages distants de {longueur:.1f} m fondus en un seul, "
                    f"de {math.degrees(abs(deviation_a + deviation_b)):.0f}°"
                )
            else:
                point = ((s[a][0] + s[b][0]) / 2.0, (s[a][1] + s[b][1]) / 2.0)
                note = f"décrochement de {longueur:.1f} m du trait effacé"
            chemin.fondre(a, b, point)
            notes.append(note)
            fondu = True
            break
        if not fondu:
            break
    return notes


def _arc(centre, rayon: float, depart: float, balayage: float) -> list:
    pas = max(1, math.ceil(abs(math.degrees(balayage)) / PAS_ARC_DEG))
    return [
        (
            centre[0] + rayon * math.cos(depart + balayage * k / pas),
            centre[1] + rayon * math.sin(depart + balayage * k / pas),
        )
        for k in range(pas + 1)
    ]


#: Déviation en deçà de laquelle un sommet n'est qu'un point de l'alignement,
#: en radians : 0,1°. Un raccord entre deux tracés qui tombe là n'est pas un
#: virage.
ALIGNE_RACCORD_RAD = math.radians(0.1)


def _raccords(chemin: _Chemin) -> list:
    """Les points où le chemin passe d'un tracé à l'autre, dans son ordre."""
    n = len(chemin.sommets)
    indices = range(n) if chemin.ferme else range(1, n - 1)
    return [
        (chemin.sommets[i], chemin.troncons[i - 1], chemin.troncons[i])
        for i in indices
        if chemin.troncons[i - 1] != chemin.troncons[i]
    ]


def _geometrie_seule(chemin: _Chemin) -> _Chemin:
    """Le chemin sans ses sommets alignés, et sans distinction de tracé."""
    sommets = list(chemin.sommets)
    minimum = 3 if chemin.ferme else 2
    retire = True
    while retire and len(sommets) > minimum:
        retire = False
        n = len(sommets)
        for i in range(n) if chemin.ferme else range(1, n - 1):
            a, b, c = sommets[(i - 1) % n], sommets[i], sommets[(i + 1) % n]
            if abs(_deviation(_direction(a, b), _direction(b, c))) < ALIGNE_RACCORD_RAD:
                del sommets[i]
                retire = True
                break
    nb_segments = len(sommets) if chemin.ferme else len(sommets) - 1
    return _Chemin(sommets, [0] * nb_segments, chemin.ferme)


def _polyligne_arrondie(chemin: _Chemin, rayon: float) -> tuple[list, list]:
    """Les points du chemin, chaque virage remplacé par son arc, et ces arcs."""
    sommets, n = chemin.sommets, len(chemin.sommets)
    voulues = _tangentes(chemin, rayon)
    # Ce qui n'a pas pu se fondre se réduit : sur un segment trop court, les deux
    # arcs voisins se partagent sa longueur au prorata de ce qu'ils voulaient.
    permises = list(voulues)
    for a, b in chemin.segments():
        longueur = math.dist(sommets[a], sommets[b])
        besoin = voulues[a] + voulues[b]
        if besoin > longueur:
            permises[a] = min(permises[a], voulues[a] * longueur / besoin)
            permises[b] = min(permises[b], voulues[b] * longueur / besoin)

    points = [] if chemin.ferme else [sommets[0]]
    arcs = []
    for i in range(n) if chemin.ferme else range(1, n - 1):
        deviation = chemin.deviation(i)
        if abs(deviation) < ALIGNE_RAD or permises[i] <= 1e-9:
            points.append(sommets[i])
            continue
        avant, _ = chemin._voisins(i)
        entree = _direction(sommets[avant], sommets[i])
        tangente = permises[i]
        rayon_ici = tangente / math.tan(abs(deviation) / 2.0)
        debut = (sommets[i][0] - entree[0] * tangente, sommets[i][1] - entree[1] * tangente)
        # Le centre est à gauche de la marche pour un virage à gauche.
        cote = 1.0 if deviation > 0 else -1.0
        normale = (-entree[1] * cote, entree[0] * cote)
        centre = (debut[0] + normale[0] * rayon_ici, debut[1] + normale[1] * rayon_ici)
        depart = math.atan2(debut[1] - centre[1], debut[0] - centre[0])
        arc = _arc(centre, rayon_ici, depart, deviation)
        points.extend(arc)
        arcs.append((rayon_ici, arc))
    points = _sans_doublons(points if chemin.ferme else points + [sommets[-1]], ferme=False)
    if chemin.ferme:
        # Un anneau se referme exactement, sans quoi sa bande garderait une
        # coupure là où il commence.
        if math.dist(points[0], points[-1]) < 0.01:
            points[-1] = points[0]
        else:
            points.append(points[0])
    return points, arcs


def _entre(position: float, debut: float, fin: float) -> bool:
    """Vrai si une abscisse tombe entre deux autres, en passant l'origine s'il le faut."""
    if debut <= fin:
        return debut - 1e-9 <= position <= fin + 1e-9
    return position >= debut - 1e-9 or position <= fin + 1e-9


def _arrondir(chemin: _Chemin, rayon: float) -> tuple[dict, dict, list[str]]:
    """Arrondit chaque virage du chemin, au rayon voulu ou au plus grand qui tient.

    Rend, pour chaque tracé d'origine, les points de son axe arrondi dans
    l'ordre du chemin, les rayons appliqués à ses virages, et les notes.

    L'arrondi se fait sur la géométrie seule, sans ses sommets alignés, et le
    chemin arrondi se recoupe ensuite à ses raccords. Un raccord entre deux
    tracés qui tombe sur un alignement n'est pas un virage : gardé comme
    sommet, il empêchait l'arc de l'angle voisin de le franchir. À Gannay, une
    fois les pistes serrées contre la clôture, un raccord tombé à 4,6 m d'un
    angle se prenait pour un décrochement, et l'angle se déplaçait de 2,3 m.
    Un raccord qui tombe dans un virage le partage.
    """
    from shapely.ops import substring

    raccords = _raccords(chemin)
    geometrie = _geometrie_seule(chemin)
    notes = _fusionner_les_virages_serres(geometrie, rayon)
    points, arcs = _polyligne_arrondie(geometrie, rayon)
    if not raccords:
        troncon = chemin.troncons[0]
        return {troncon: points}, {troncon: [r for r, _ in arcs]}, notes

    ligne = LineString(points)
    longueur = ligne.length
    positions = [(ligne.project(Point(p)), entrant, sortant) for p, entrant, sortant in raccords]
    etendues: dict = {}
    if chemin.ferme:
        positions.sort(key=lambda position: position[0])
        for k, (debut, _, sortant) in enumerate(positions):
            etendues[sortant] = (debut, positions[(k + 1) % len(positions)][0])
    else:
        bornes = [0.0] + [p for p, _, _ in positions] + [longueur]
        suite = [positions[0][1]] + [sortant for _, _, sortant in positions]
        for k, troncon in enumerate(suite):
            etendues[troncon] = (bornes[k], bornes[k + 1])

    morceaux: dict = {}
    for troncon, (debut, fin) in etendues.items():
        if debut <= fin:
            coords = list(substring(ligne, debut, fin).coords)
        else:
            coords = (
                list(substring(ligne, debut, longueur).coords)
                + list(substring(ligne, 0.0, fin).coords)[1:]
            )
        morceaux[troncon] = _sans_doublons(coords, ferme=False)

    rayons_par_troncon: dict = {}
    for rayon_arc, arc in arcs:
        abscisses = [ligne.project(Point(q)) for q in (arc[0], arc[len(arc) // 2], arc[-1])]
        for troncon, (debut, fin) in etendues.items():
            if any(_entre(s, debut, fin) for s in abscisses):
                rayons_par_troncon.setdefault(troncon, []).append(rayon_arc)
    return morceaux, rayons_par_troncon, notes


# ---------------------------------------------------------------------------
# Raccords entre tracés
# ---------------------------------------------------------------------------


@dataclass
class _Extremite:
    axe: int
    #: 0 pour le début du tracé, -1 pour sa fin.
    bout: int


@dataclass
class _RaccordEnT:
    """Une extrémité de tracé menée jusqu'à l'axe d'un autre."""

    axe: int
    bout: int
    sur: int
    point: tuple


def _est_ferme(coords: list) -> bool:
    return len(coords) > 3 and math.dist(coords[0], coords[-1]) < 0.01


def _mener_jusqu_a(coords: list, bout: int, cible: LineString):
    """Prolonge ou recoupe l'extrémité d'un tracé jusqu'à l'axe qu'elle rejoint.

    Le long de son dernier segment quand il coupe l'axe à portée ; sinon au
    point de l'axe le plus proche.
    """
    extremite = coords[bout]
    voisin = coords[1] if bout == 0 else coords[-2]
    direction = _direction(voisin, extremite)
    portee = 2.0 * RACCORD_M
    droite = LineString(
        [
            (voisin[0], voisin[1]),
            (extremite[0] + direction[0] * portee, extremite[1] + direction[1] * portee),
        ]
    )
    coupe = droite.intersection(cible)
    candidats = []
    for partie in getattr(coupe, "geoms", [coupe]):
        if partie.is_empty:
            continue
        if partie.geom_type == "Point":
            candidats.append((partie.x, partie.y))
        else:
            candidats.extend(tuple(c) for c in partie.coords)
    candidats = [c for c in candidats if math.dist(c, extremite) <= portee]
    if candidats:
        return min(candidats, key=lambda c: math.dist(c, extremite))
    proche = cible.interpolate(cible.project(Point(extremite)))
    return (proche.x, proche.y)


def _raccorder(
    axes: list[AxePiste],
) -> tuple[list[_Chemin], list[_RaccordEnT], list[list], list[str]]:
    """Enchaîne les tracés mis bout à bout, mène les autres jusqu'aux axes qu'ils rejoignent."""
    coords = [_sans_doublons(list(a.ligne.coords), ferme=False) for a in axes]
    fermes = [_est_ferme(c) for c in coords]
    lignes = [LineString(c) for c in coords]
    notes = []

    # Les raccords bout à bout, du plus serré au plus lâche, une extrémité
    # ne servant qu'une fois.
    candidates = []
    extremites = [
        _Extremite(i, bout) for i in range(len(axes)) if not fermes[i] for bout in (0, -1)
    ]
    for rang, e1 in enumerate(extremites):
        for e2 in extremites[rang + 1 :]:
            if e1.axe == e2.axe:
                continue
            distance = math.dist(coords[e1.axe][e1.bout], coords[e2.axe][e2.bout])
            if distance < JONCTION_M:
                candidates.append((distance, e1, e2))
            elif distance < 2.0 * LARGEUR_PISTE_M:
                # Assez près pour que les bandes se touchent, trop loin pour
                # être deux traits mis bout à bout : le plan ne dit pas si la
                # piste se continue, et on ne le décide pas à sa place.
                notes.append(
                    f"Pistes « {axes[e1.axe].libelle} » et « {axes[e2.axe].libelle} » : "
                    f"extrémités à {distance:.1f} m l'une de l'autre, laissées sans "
                    "raccord. Si elles se continuent, rapprochez-les sur le plan."
                )
    liens: dict = {}
    for _, e1, e2 in sorted(candidates, key=lambda c: c[0]):
        if (e1.axe, e1.bout) in liens or (e2.axe, e2.bout) in liens:
            continue
        liens[(e1.axe, e1.bout)] = e2
        liens[(e2.axe, e2.bout)] = e1

    # Les raccords en T : une extrémité libre près de l'axe d'un autre tracé,
    # loin de ses extrémités.
    raccords = []
    for e in extremites:
        if (e.axe, e.bout) in liens:
            continue
        point = Point(coords[e.axe][e.bout])
        meilleur = None
        for j, ligne in enumerate(lignes):
            if j == e.axe:
                continue
            distance = ligne.distance(point)
            if distance >= RACCORD_M:
                continue
            projete = ligne.project(point)
            if not fermes[j] and min(projete, ligne.length - projete) < JONCTION_M:
                continue
            if meilleur is None or distance < meilleur[0]:
                meilleur = (distance, j)
        if meilleur is not None:
            j = meilleur[1]
            cible = _mener_jusqu_a(coords[e.axe], e.bout, lignes[j])
            if e.bout == 0:
                coords[e.axe][0] = cible
            else:
                coords[e.axe][-1] = cible
            raccords.append(_RaccordEnT(e.axe, e.bout, j, cible))

    # Les chemins : chaque tracé fermé en est un ; les autres s'enchaînent.
    chemins = []
    vus = set()
    for i in range(len(axes)):
        if fermes[i]:
            chemins.append(
                _sans_sommet_confondu(coords[i][:-1], [i] * (len(coords[i]) - 1), ferme=True)
            )
            vus.add(i)
    for i in range(len(axes)):
        if i in vus:
            continue
        # Remonter jusqu'au début de la chaîne, ou faire le tour d'une boucle.
        debut, bout_libre = i, 0
        tour = {i}
        while (debut, bout_libre) in liens:
            voisin = liens[(debut, bout_libre)]
            if voisin.axe in tour:
                break
            tour.add(voisin.axe)
            debut, bout_libre = voisin.axe, -1 if voisin.bout == 0 else 0
        sommets, troncons = [], []
        courant, entree = debut, bout_libre
        ferme = False
        while True:
            vus.add(courant)
            points = coords[courant] if entree == 0 else coords[courant][::-1]
            if sommets:
                # Le raccord : le sommet commun des deux alignements qui s'y
                # rejoignent, ou le milieu des deux extrémités s'ils sont
                # parallèles.
                precedent = sommets[-2]
                fin = sommets[-1]
                suivant = points[1]
                sommet = _intersection_droites(
                    fin, _direction(precedent, fin), points[0], _direction(points[0], suivant)
                )
                if sommet is None or max(math.dist(sommet, fin), math.dist(sommet, points[0])) > 2 * JONCTION_M:
                    sommet = ((fin[0] + points[0][0]) / 2.0, (fin[1] + points[0][1]) / 2.0)
                sommets[-1] = sommet
                points = points[1:]
            sommets.extend(points)
            troncons.extend([courant] * (len(points) - (0 if len(sommets) > len(points) else 1)))
            sortie = -1 if entree == 0 else 0
            suite = liens.get((courant, sortie))
            if suite is None:
                break
            if suite.axe in vus:
                ferme = suite.axe == debut
                break
            courant, entree = suite.axe, suite.bout
        if ferme:
            # Le dernier raccord referme la boucle sur le premier sommet.
            fin, precedent = sommets[-1], sommets[-2]
            premier, second = sommets[0], sommets[1]
            sommet = _intersection_droites(
                fin, _direction(precedent, fin), premier, _direction(premier, second)
            )
            if sommet is None or max(math.dist(sommet, fin), math.dist(sommet, premier)) > 2 * JONCTION_M:
                sommet = ((fin[0] + premier[0]) / 2.0, (fin[1] + premier[1]) / 2.0)
            # Le dernier sommet et le premier ne font plus qu'un : le dernier
            # segment, déjà compté, devient celui qui referme la boucle.
            sommets[0] = sommet
            sommets.pop()
        chemins.append(_sans_sommet_confondu(sommets, troncons, ferme))
    return chemins, raccords, coords, notes


# ---------------------------------------------------------------------------
# Les angles rentrants d'un raccord en T
# ---------------------------------------------------------------------------


def _direction_locale(ligne: LineString, point) -> tuple[float, float]:
    """Direction du segment d'une ligne le plus proche d'un point."""
    coords = list(ligne.coords)
    cible = Point(point)
    a, b = min(
        ((p, q) for p, q in zip(coords, coords[1:]) if math.dist(p, q) > 1e-9),
        key=lambda s: LineString(s).distance(cible),
    )
    return _direction(a, b)


def _longueur_droite_en_bout(coords: list, bout: int) -> float:
    """Longueur de la partie droite d'un axe à l'une de ses extrémités."""
    points = coords if bout == 0 else coords[::-1]
    direction = _direction(points[0], points[1])
    longueur = 0.0
    for p, q in zip(points, points[1:]):
        if math.dist(p, q) < 1e-9:
            continue
        if abs(_deviation(direction, _direction(p, q))) > math.radians(0.5):
            break
        longueur += math.dist(p, q)
    return longueur


def _evasements(
    raccord: _RaccordEnT, axe: LineString, cible: LineString, disponible: float
) -> tuple[list[Polygon], list[float]]:
    """Les deux angles rentrants d'un raccord en T, arrondis au rayon intérieur.

    Chaque angle est celui que font le bord de la piste qui arrive et le bord
    de celle qu'elle rejoint ; l'arc qui l'arrondit est tangent aux deux. Il
    prend au plus `disponible` le long de la piste qui arrive, et ce qui reste
    de la piste rejointe jusqu'à son extrémité.
    """
    coords = list(axe.coords)
    extremite = coords[raccord.bout]
    voisin = coords[1] if raccord.bout == 0 else coords[-2]
    arrivee = _direction(voisin, extremite)
    principale = _direction_locale(cible, raccord.point)
    demi = LARGEUR_PISTE_M / 2.0
    # Côté de la piste rejointe où se trouve celle qui arrive.
    cote_cible = 1.0 if (principale[0] * -arrivee[1] - principale[1] * -arrivee[0]) > 0 else -1.0
    bord_cible = (
        raccord.point[0] - principale[1] * demi * cote_cible,
        raccord.point[1] + principale[0] * demi * cote_cible,
    )
    projete = cible.project(Point(raccord.point))
    reste_cible = math.inf if cible.is_ring else min(projete, cible.length - projete) - demi

    evasements, rayons = [], []
    for cote in (1.0, -1.0):
        normale = (-arrivee[1] * cote, arrivee[0] * cote)
        bord = (extremite[0] + normale[0] * demi, extremite[1] + normale[1] * demi)
        coin = _intersection_droites(bord, arrivee, bord_cible, principale)
        if coin is None:
            continue
        # Le long de la piste rejointe, du côté de ce bord-ci.
        long_cible = principale if principale[0] * normale[0] + principale[1] * normale[1] > 0 else (
            -principale[0], -principale[1]
        )
        retour = (-arrivee[0], -arrivee[1])
        cosinus = max(-1.0, min(1.0, retour[0] * long_cible[0] + retour[1] * long_cible[1]))
        ouverture = math.acos(cosinus)
        if not math.radians(1.0) < ouverture < math.radians(179.0):
            continue
        tangente = min(
            RAYON_INTERIEUR_M / math.tan(ouverture / 2.0), disponible, reste_cible
        )
        if tangente <= 0.05:
            continue
        rayon = tangente * math.tan(ouverture / 2.0)
        p1 = (coin[0] + retour[0] * tangente, coin[1] + retour[1] * tangente)
        p2 = (coin[0] + long_cible[0] * tangente, coin[1] + long_cible[1] * tangente)
        bissectrice = _direction((0.0, 0.0), (retour[0] + long_cible[0], retour[1] + long_cible[1]))
        distance_centre = rayon / math.sin(ouverture / 2.0)
        centre = (coin[0] + bissectrice[0] * distance_centre, coin[1] + bissectrice[1] * distance_centre)
        debut = math.atan2(p1[1] - centre[1], p1[0] - centre[0])
        fin = math.atan2(p2[1] - centre[1], p2[0] - centre[0])
        balayage = (fin - debut + math.pi) % (2 * math.pi) - math.pi
        arc = _arc(centre, rayon, debut, balayage)
        forme = Polygon([coin] + arc + [coin])
        if forme.is_valid and forme.area > 0.01:
            evasements.append(forme)
            rayons.append(rayon)
    return evasements, rayons


# ---------------------------------------------------------------------------
# Une piste serrée contre la clôture
# ---------------------------------------------------------------------------


def longe(axe: LineString, enceinte: Polygon) -> bool:
    """Vrai quand la piste court le long de la clôture, du côté de l'enceinte."""
    bande = enceinte.exterior.buffer(LONGE_M).intersection(enceinte)
    return axe.intersection(bande).length >= PART_LE_LONG * axe.length


def serrer_contre(
    axe: LineString, enceinte: Polygon, jeu: float = JEU_CLOTURE_M
) -> LineString | None:
    """L'axe d'une piste qui longe la clôture, reporté pour que sa bande passe à `jeu` d'elle.

    C'est la clôture décalée vers l'intérieur de la demi-largeur de la piste et
    du jeu, prise entre les points où l'axe du plan commence et finit, dans le
    sens qui le suit. Les virages s'arrondissent ensuite comme ceux de toute
    piste ; deux pistes serrées bout à bout restent raccordées. None si la
    piste ne longe pas la clôture.
    """
    from shapely.ops import substring

    if not longe(axe, enceinte):
        return None
    decale = enceinte.buffer(-(LARGEUR_PISTE_M / 2.0 + jeu), join_style="mitre")
    if decale.is_empty:
        return None
    if decale.geom_type == "MultiPolygon":
        decale = max(decale.geoms, key=lambda g: g.area)
    anneau = LineString(decale.exterior.coords)
    coords = list(axe.coords)
    if _est_ferme(coords):
        return anneau
    longueur = anneau.length
    debut = anneau.project(Point(coords[0]))
    fin = anneau.project(Point(coords[-1]))

    def arc(a: float, b: float) -> LineString:
        """De a à b dans le sens de l'anneau, en passant son origine s'il le faut."""
        if a <= b:
            return substring(anneau, a, b)
        return LineString(
            list(substring(anneau, a, longueur).coords)
            + list(substring(anneau, 0.0, b).coords)[1:]
        )

    aller = arc(debut, fin)
    retour = LineString(list(arc(fin, debut).coords)[::-1])
    return min((aller, retour), key=lambda ligne: ligne.hausdorff_distance(axe))


# ---------------------------------------------------------------------------
# Du tracé du plan à la piste
# ---------------------------------------------------------------------------


def dessiner_pistes(axes: list[AxePiste]) -> tuple[list[PisteDessinee], list[str]]:
    """Les pistes d'un plan, arrondies et élargies, et ce qu'il faut en dire.

    Une piste par tracé du plan, de sa catégorie et de son libellé : le type
    vient du plan, la géométrie d'un vrai plan.
    """
    if not axes:
        return [], []
    chemins, raccords, coords, notes = _raccorder(axes)
    axes_arrondis: dict = {}
    rayons_axe: dict = {}
    for chemin in chemins:
        morceaux, rayons, notes_chemin = _arrondir(chemin, RAYON_AXE_M)
        libelles = sorted({axes[t].libelle for t in set(chemin.troncons)})
        for note in notes_chemin:
            notes.append(f"Piste « {' / '.join(libelles)} » : {note}.")
        axes_arrondis.update(morceaux)
        for troncon, liste in rayons.items():
            rayons_axe.setdefault(troncon, []).extend(liste)

    lignes = {i: LineString(points) for i, points in axes_arrondis.items()}
    surfaces = {
        i: ligne.buffer(LARGEUR_PISTE_M / 2.0, cap_style="flat", join_style="round")
        for i, ligne in lignes.items()
    }

    rayons_raccords: dict = {}
    nb_raccords = {i: 0 for i in lignes}
    for raccord in raccords:
        nb_raccords[raccord.axe] += 1
    for raccord in raccords:
        axe = lignes[raccord.axe]
        coords_axe = list(axe.coords)
        # Le point de raccord sur l'axe arrondi : l'extrémité correspondante.
        bout = 0 if math.dist(coords_axe[0], raccord.point) <= math.dist(coords_axe[-1], raccord.point) else -1
        raccord_ici = _RaccordEnT(raccord.axe, bout, raccord.sur, coords_axe[bout])
        # Ce que la piste qui arrive offre à ses évasements : sa partie droite
        # au bout, moins la demi-largeur de celle qu'elle rejoint — et, si ses
        # deux bouts se raccordent, la moitié de ce qui reste à découvert entre
        # les deux pistes qu'elle relie : 3,2 m pour la bretelle de 11,4 m du
        # portail de Gannay.
        demi = LARGEUR_PISTE_M / 2.0
        nombre = nb_raccords[raccord.axe]
        disponible = min(
            _longueur_droite_en_bout(coords_axe, bout) - demi,
            (axe.length - demi * nombre) / nombre,
        )
        evasements, rayons = _evasements(raccord_ici, axe, lignes[raccord.sur], max(0.0, disponible))
        if evasements:
            # Un évasement ne touche la bande que le long de son bord, au
            # flottant près : sans un centimètre de recouvrement, l'union le
            # laissait en polygone à part (mesuré à Gannay le 23/09/2026).
            surfaces[raccord.axe] = unary_union(
                [surfaces[raccord.axe]] + [e.buffer(0.01, join_style="mitre") for e in evasements]
            )
        rayons_raccords.setdefault(raccord.axe, []).extend(rayons)
        etroits = [r for r in rayons if r < RAYON_INTERIEUR_M - 0.05]
        if etroits or len(rayons) < 2:
            notes.append(
                f"Piste « {axes[raccord.axe].libelle} » : raccord sur « "
                f"{axes[raccord.sur].libelle} » arrondi à "
                + (" et ".join(f"{r:.1f} m" for r in rayons) if rayons else "aucun rayon")
                + f" au bord intérieur, faute de place pour {RAYON_INTERIEUR_M:.0f} m."
            )

    for i, liste in rayons_axe.items():
        serres = [r for r in liste if r < RAYON_AXE_M - 0.05]
        if serres:
            notes.append(
                f"Piste « {axes[i].libelle} » : {len(serres)} virage(s) de "
                f"{min(serres):.1f} m de rayon sur l'axe, en deçà des "
                f"{RAYON_AXE_M:.1f} m voulus — le tracé du plan ne laisse pas la place."
            )

    pistes = [
        PisteDessinee(
            categorie=axes[i].categorie,
            libelle=axes[i].libelle,
            axe=lignes[i],
            surface=surfaces[i],
            rayons_axe_m=[round(r, 2) for r in rayons_axe.get(i, [])],
            rayons_raccords_m=[round(r, 2) for r in rayons_raccords.get(i, [])],
        )
        for i in sorted(lignes)
    ]
    return pistes, notes
