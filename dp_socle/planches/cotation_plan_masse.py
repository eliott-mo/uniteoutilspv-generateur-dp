"""Lot 10 — les cotes du plan de masse, calculées à part du dessin.

Les demandes de pièces complémentaires de Saint-Cyr-en-Val et
d'Auzainvilliers (novembre 2026) réclament une DP 2 « cotée correctement » :
distances aux limites, aux voies, entre ouvrages, écartement des rangées. Ce
module calcule ces cotes, **peu nombreuses et choisies par règle**, sans rien
dessiner : il rend des segments en Lambert 93, leur valeur et leur libellé, et
écrit au rapport chaque cote qu'une règle écarte, avec sa raison. Leur pose sur
la planche — la place de la valeur, les flèches, les planches de détail —
revient à la planche, `dp2_plan_masse`.

Rien ici n'interroge un service : le parcellaire et la BD TOPO arrivent en
arguments, si bien que chaque règle se vérifie sur des cas construits, sans
réseau (`tests/test_cotation_lot10.py`).

Les règles sont celles du brief `_briefs/BRIEF_DP_lot10_cotation_plan_masse.md`
(décisions D1 à D12, familles C1 à C8), arrêtées sur une maquette relue par les
chefs de projet des deux sites. Le risque propre au lot n'est pas la cote
absente, c'est **la cote juste en apparence et fausse sur le fond** : une
distance à la clôture présentée comme un recul à la limite, un hangar pris pour
une habitation, un inter-rangée qui contredit la coupe. Chaque règle ci-dessous
dit le piège qu'elle évite, quand c'est la mesure qui l'a montré.

Un mot de vocabulaire : le brief appelle « côté » un tronçon droit de la
clôture. Le code dit **pan** (`PanDeCloture`), pour qu'un côté ne se lise pas
comme une cote.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

from ..echelle import metres_vers_mm
from ..planche import nombre_fr
from .dp1_3_cadastre import PART_MIN_ASSIETTE
from .dp4_ouvrages import CITERNES, CONTENEURS, POSTES

# ---------------------------------------------------------------------------
# Réglages
# ---------------------------------------------------------------------------

#: Tolérance de simplification de la clôture avant son découpage en côtés, en
#: mètres. Le tracé simplifié **ne sert qu'à grouper et à orienter** : toute
#: distance se prend sur la clôture réelle (voir `PanDeCloture`).
SIMPLIFICATION_CLOTURE_M = 1.5

#: Deux segments consécutifs du tracé simplifié qui tournent de moins de cet
#: angle appartiennent au même côté.
VIRAGE_MAX_DEG = 25.0

#: Longueur minimale d'un côté. Les trois réglages — 1,5 m, 25°, 20 m — ont tenu
#: sur Sarnois, Saint-Cyr et Auzainvilliers (brief, 08/11/2026) ; ils restent à
#: éprouver sur Bray-Saint-Aignan, Chaumont-sur-Aire et Les Islettes.
LONGUEUR_MIN_PAN_M = 20.0

#: Au-delà, un côté de clôture ne se cote pas : ses tables en sont trop loin
#: pour que la distance à la limite dise quelque chose de l'implantation
#: (03/11/2026).
SEUIL_TABLES_PAN_M = 30.0

#: Portée du rayon qui part des tables vers la limite, à travers la clôture.
PORTEE_TABLES_LIMITE_M = 500.0

#: Portée du rayon qui part de la clôture vers la limite. L'écart le plus grand
#: mesuré est de 16,5 m (Auzainvilliers, 08/11/2026) ; au-delà de la portée,
#: la limite est dite introuvable, et la cote ne se pose pas.
PORTEE_CLOTURE_LIMITE_M = 60.0

#: En deçà, la clôture est tenue pour posée sur la limite : pas de seconde cote,
#: le dessin le montre de lui-même.
ECART_CLOTURE_LIMITE_MIN_M = 0.5

#: Écart minimal, sur le papier, entre la cote tables → limite et la cote
#: clôture → limite d'un même côté. À 1:2 000, la chaîne tables | clôture |
#: limite du 03/11 faisait 0,5 mm pour un écart de 1 m, et ses flèches tombaient
#: sur celles de la grande cote (08/11/2026) : les deux se posent à deux
#: endroits du côté, assez loin pour ne pas se lire comme une chaîne.
SEPARATION_COTES_PAN_MM = 20.0

#: Endroits du côté où l'on essaie de poser la cote clôture → limite, en
#: fraction de sa longueur : le milieu d'abord.
FRACTIONS_COTE_CLOTURE = (0.5, 0.35, 0.65, 0.2, 0.8)

#: Demi-longueur du tracé qui donne la direction locale d'un côté, de part et
#: d'autre du point essayé, en mètres.
DEMI_TANGENTE_M = 1.0

#: Un croisement plus proche que cela du point de départ est le départ
#: lui-même, pas la limite.
DEPART_EXCLU_M = 0.05

# ---------------------------------------------------------------------------
# Ce que le module rend
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoteAPoser:
    """Une cote calculée, en Lambert 93, que la planche n'a pas encore posée.

    `texte` est ce que la planche écrit, valeur comprise, de la forme
    « 6,6 m (tables – limite parcellaire) » : la valeur est `nombre_fr` de la
    distance mesurée, et le libellé dit ce que la cote relie — sauf entre deux
    ouvrages, « 4,8 m », que le dessin désigne de lui-même. Sans libellé, la
    largeur d'une piste qui longe la clôture se lisait comme leur écart
    (03/11/2026), et « 15,7 m (clôture en limite) » comme la distance de la
    clôture à la limite, nulle à cet endroit (Saint-Cyr, 07/11/2026).

    Une exception : l'inter-rangée (C5) écrit la valeur de la coupe, et sa
    ligne mesure l'écart du plan qui la vaut à 0,15 m près — voir
    `cote_inter_rangee`.

    `vers_la_limite` : la valeur se pose de préférence au-delà de la limite,
    hors de la centrale, où elle ne recouvre rien (D8, 08/11/2026).

    `ouvrages` : les rangs, dans la liste des ouvrages permanents, de ceux que
    la cote relie. C'est ce qui fait les zones techniques (D7).
    """

    famille: str
    depart: tuple
    arrivee: tuple
    texte: str
    valeur_m: float
    vers_la_limite: bool = False
    ouvrages: tuple = ()

    @property
    def ligne(self) -> LineString:
        return LineString([self.depart, self.arrivee])

    @property
    def longueur_m(self) -> float:
        return math.dist(self.depart, self.arrivee)


@dataclass(frozen=True)
class PanDeCloture:
    """Un côté de la clôture : un tronçon droit de son tracé simplifié.

    `trace` groupe et oriente, rien de plus. Simplifiée à 1,5 m, la clôture
    s'écarte d'autant de son tracé, et plus encore dans les courbes : la
    maquette du 07/11/2026 mesurait depuis lui, et annonçait à Saint-Cyr des
    écarts clôture → limite de 0,9 et 1,0 m là où la clôture réelle est sur la
    limite (0,00 m, relevé le 08/11/2026). Les distances se prennent donc sur
    `anneau`, la clôture réelle de l'enclos, et `enclos` dit où est l'intérieur.
    """

    trace: LineString
    anneau: BaseGeometry
    enclos: Polygon

    @property
    def longueur_m(self) -> float:
        return self.trace.length


@dataclass(frozen=True)
class CotesDuPan:
    """Les deux cotes d'un côté de clôture (C1).

    `places_cloture` : les endroits du côté où la cote clôture → limite peut se
    poser, dans l'ordre d'essai. Vide quand la clôture est sur la limite, ou
    que le côté n'a pas de place à 20 mm de papier de la première cote : le
    rapport l'a dit. La place se choisit une fois toutes les autres cotes
    connues, par `choisir_les_places_cloture_limite`.
    """

    pan: PanDeCloture
    tables_limite: CoteAPoser
    places_cloture: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------


def polygones_de(geometries) -> list:
    """Les polygones d'un lot de géométries, multiples et collections dépliées.

    Une collection n'est pas une surface qu'on saute : la citerne de
    refroidissement d'Auzainvilliers arrive en `GeometryCollection` — un contour
    auto-intersectant redressé par `make_valid` —, et une version de la maquette
    la sautait, si bien qu'elle sortait des cotes sans un mot.
    """
    resultat = []
    for geometrie in geometries:
        if geometrie is None or geometrie.is_empty:
            continue
        if geometrie.geom_type == "Polygon":
            resultat.append(geometrie)
        elif geometrie.geom_type in ("MultiPolygon", "GeometryCollection"):
            resultat.extend(polygones_de(geometrie.geoms))
    return resultat


def _metres(valeur: float, decimales: int = 1) -> str:
    return f"{nombre_fr(valeur, decimales)} m"


def _direction_deg(a, b) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _virage_deg(segment_a, segment_b) -> float:
    """L'angle dont on tourne en passant d'un segment au suivant, de 0 à 180°."""
    ecart = _direction_deg(*segment_b) - _direction_deg(*segment_a)
    return abs((ecart + 180.0) % 360.0 - 180.0)


def _points_de(geometrie) -> list:
    """Les points d'un croisement : points isolés, et bouts des chevauchements."""
    if geometrie.is_empty:
        return []
    if geometrie.geom_type == "Point":
        return [geometrie]
    if geometrie.geom_type in ("LineString", "LinearRing"):
        return [Point(c) for c in (geometrie.coords[0], geometrie.coords[-1])]
    if hasattr(geometrie, "geoms"):
        return [p for partie in geometrie.geoms for p in _points_de(partie)]
    return []


def premier_croisement(depart, direction, limite, portee_m):
    """Le premier point de `limite` sur la demi-droite, ou `None` dans la portée.

    `depart` est un `Point`, `direction` un vecteur unitaire. Les tables sont
    dans le terrain : partie d'elles, la demi-droite sort du terrain à son
    premier croisement de la limite, et c'est lui qu'on cote.
    """
    rayon = LineString([
        (depart.x, depart.y),
        (depart.x + direction[0] * portee_m, depart.y + direction[1] * portee_m),
    ])
    points = [
        p for p in _points_de(rayon.intersection(limite))
        if depart.distance(p) > DEPART_EXCLU_M
    ]
    return min(points, key=depart.distance) if points else None


# ---------------------------------------------------------------------------
# D4 — la limite parcellaire
# ---------------------------------------------------------------------------


def terrain_d_assiette(parcelles, emprise) -> BaseGeometry | None:
    """L'union des parcelles d'assiette, retenues par la règle de la DP 1-3.

    La règle est celle de `dp1_3_cadastre.generer` : une parcelle que l'emprise
    recouvre à `PART_MIN_ASSIETTE` au moins de sa surface. Le plan de masse et
    le plan cadastral ne peuvent pas désigner deux terrains différents (D4). Ce
    n'est pas le fichier d'emprise lui-même : le premier jeu d'essai de Sarnois
    mordait sur dix parcelles voisines.

    L'union efface les limites entre deux parcelles d'assiette, qui ne sont pas
    des limites séparatives. Rend `None` sans parcelle d'assiette : il n'y a
    alors pas de limite à coter, et l'appelant le dit.
    """
    retenues = []
    for parcelle in parcelles:
        geometrie = parcelle.geometrie
        aire = geometrie.area
        if not aire or not geometrie.intersects(emprise):
            continue
        if geometrie.intersection(emprise).area / aire >= PART_MIN_ASSIETTE:
            retenues.append(geometrie)
    if not retenues:
        return None
    return unary_union(retenues)


# ---------------------------------------------------------------------------
# Les côtés de la clôture
# ---------------------------------------------------------------------------


def enclos_de_la_cloture(clotures, rapport: list):
    """L'intérieur de la clôture : ses contours fermés, et ses tracés refermables.

    L'enclos dit de quel côté de la clôture est l'extérieur (C1), et ce qui est
    dans la clôture (C2, C8). La clôture arrive au contrat en polygone quand
    l'import l'a refermée, en lignes sinon : `import_be._geometrie_de` ne
    referme une polyligne qu'au micromètre près, et le lot 2ter rend des lignes
    quand son enceinte ne se ferme pas. Les tracés sont donc recousus, puis
    refermés si leurs bouts se manquent de `JEU_CONTOUR_FERME_M` au plus — la
    règle même de l'import, 10 cm, mesurée sur Bédarieux, dont la clôture de
    747,6 m se manque de 9 mm —, et le rapport le dit. Au-delà, le tracé reste
    ouvert, il n'a pas d'intérieur, et le rapport dit de combien.

    Rend l'union des enclos, sans leurs trous, ou `None`.
    """
    from shapely import line_merge

    from ..import_be import JEU_CONTOUR_FERME_M

    contours = polygones_de(clotures)
    lignes = [
        g for g in clotures
        if g is not None and not g.is_empty
        and g.geom_type in ("LineString", "LinearRing", "MultiLineString")
    ]
    if lignes:
        recousues = line_merge(unary_union(lignes))
        for trace in getattr(recousues, "geoms", [recousues]):
            if trace.geom_type != "LineString" or len(trace.coords) < 3:
                continue
            debut, fin = trace.coords[0][:2], trace.coords[-1][:2]
            jeu = math.dist(debut, fin)
            if jeu <= JEU_CONTOUR_FERME_M:
                refermee = Polygon([c[:2] for c in trace.coords])
                if refermee.is_valid and refermee.area > 0:
                    contours.append(refermee)
                    if jeu > 1e-6:
                        rapport.append(
                            f"Clôture : un tracé de {_metres(trace.length, 0)}, dont les "
                            f"bouts se manquent de {nombre_fr(jeu * 1000, 0)} mm, est "
                            "refermé pour se découper en côtés — l'import la tient pour "
                            f"fermée à {nombre_fr(JEU_CONTOUR_FERME_M * 100, 0)} cm près."
                        )
                    continue
            rapport.append(
                f"Clôture : un tracé de {_metres(trace.length, 0)} reste ouvert, ses "
                f"bouts à {_metres(jeu)} l'un de l'autre : il n'a pas d'intérieur, "
                "et ses côtés ne se cotent pas."
            )
    if not contours:
        return None
    return unary_union([Polygon(p.exterior) for p in polygones_de([unary_union(contours)])])


def pans_de_la_cloture(enclos) -> list:
    """Les côtés de chaque enclos de la clôture, de 20 m au moins.

    `enclos` est celui de `enclos_de_la_cloture`. Son contour est simplifié à
    1,5 m, et ses segments qui tournent de moins de 25° se fondent en un côté —
    y compris le dernier et le premier, que le départ du contour coupe
    arbitrairement.
    """
    if enclos is None or enclos.is_empty:
        return []
    pans = []
    for polygone in polygones_de([enclos]):
        anneau = polygone.exterior
        interieur = Polygon(anneau)
        simplifie = interieur.simplify(SIMPLIFICATION_CLOTURE_M)
        if simplifie.is_empty or simplifie.geom_type != "Polygon":
            continue
        sommets = list(simplifie.exterior.coords)[:-1]
        if len(sommets) < 3:
            continue
        for troncon in _troncons(sommets):
            trace = LineString([troncon[0][0]] + [segment[1] for segment in troncon])
            if trace.length >= LONGUEUR_MIN_PAN_M:
                pans.append(PanDeCloture(trace=trace, anneau=anneau, enclos=interieur))
    return pans


def _troncons(sommets) -> list:
    segments = [(sommets[i], sommets[(i + 1) % len(sommets)]) for i in range(len(sommets))]
    troncons, courant = [], [segments[0]]
    for segment in segments[1:]:
        if _virage_deg(courant[-1], segment) < VIRAGE_MAX_DEG:
            courant.append(segment)
        else:
            troncons.append(courant)
            courant = [segment]
    if troncons and _virage_deg(courant[-1], troncons[0][0]) < VIRAGE_MAX_DEG:
        troncons[0] = courant + troncons[0]
    else:
        troncons.append(courant)
    return troncons


# ---------------------------------------------------------------------------
# C1 — tables → limite parcellaire, et clôture → limite parcellaire
# ---------------------------------------------------------------------------


def cotes_tables_cloture_limite(
    pans, tables, terrain, denominateur: int, rapport: list
) -> list:
    """Les deux cotes de chaque côté de clôture dont les tables sont à moins de 30 m.

    Les deux demandes visent la distance des constructions **aux limites**,
    pas à la clôture : « par rapport aux limites parcellaires » à Saint-Cyr,
    « avec les limites séparatives » à Auzainvilliers (08/11/2026). D'où, par
    côté :

    - **tables → limite parcellaire**, depuis la table la plus proche du côté,
      dans la direction de la clôture, jusqu'au premier croisement de la
      limite : la ligne traverse la clôture, et le libellé dit ses deux bouts ;
    - **clôture → limite parcellaire**, ailleurs sur le côté, depuis la clôture
      réelle et perpendiculairement au côté, si l'écart dépasse 0,5 m — voir
      `CotesDuPan.places_cloture`.

    `denominateur` est l'échelle de la planche : l'écart de 20 mm de papier
    entre les deux cotes d'un côté y devient un écart sur le terrain.
    """
    if terrain is None or terrain.is_empty:
        rapport.append(
            "Cotes aux limites parcellaires : aucune parcelle d'assiette, il n'y a "
            "pas de limite à coter."
        )
        return []
    surfaces = polygones_de(tables)
    if not surfaces:
        rapport.append("Cotes aux limites parcellaires : aucune table au plan.")
        return []
    if not pans:
        rapport.append(
            "Cotes aux limites parcellaires : la clôture n'a aucun côté de "
            f"{_metres(LONGUEUR_MIN_PAN_M, 0)} au moins, ou pas de contour fermé "
            "qui dise où est l'intérieur — pas de cote tables – limite."
        )
        return []
    limite = terrain.boundary
    separation_m = SEPARATION_COTES_PAN_MM * denominateur / 1000.0

    # Les tables d'un enclos, et non toutes : sinon celles d'un enclos voisin
    # passeraient pour les plus proches d'un côté qui n'en a pas.
    tables_des_enclos = {}
    resultats = []
    for pan in pans:
        longueur = _metres(pan.longueur_m, 0)
        if id(pan.enclos) not in tables_des_enclos:
            dedans = [t for t in surfaces if t.intersects(pan.enclos)]
            tables_des_enclos[id(pan.enclos)] = unary_union(dedans) if dedans else None
            if not dedans:
                rapport.append(
                    f"Enclos de clôture de {_metres(pan.enclos.exterior.length, 0)} "
                    "sans table : ses côtés ne se cotent pas aux limites."
                )
        tables_union = tables_des_enclos[id(pan.enclos)]
        if tables_union is None:
            continue
        p_t, p_c = nearest_points(tables_union, pan.trace)
        distance = p_t.distance(p_c)
        if distance > SEUIL_TABLES_PAN_M:
            rapport.append(
                f"Côté de clôture de {longueur} non coté : les tables en sont à "
                f"{_metres(distance)}, au-delà de {_metres(SEUIL_TABLES_PAN_M, 0)}."
            )
            continue
        if distance < DEPART_EXCLU_M:
            rapport.append(
                f"Côté de clôture de {longueur} non coté : les tables touchent la "
                "clôture, et la cote n'a pas de direction."
            )
            continue
        if not terrain.covers(p_t):
            rapport.append(
                f"Côté de clôture de {longueur} non coté : la table la plus proche "
                "est hors du terrain d'assiette, et sa cote mesurerait l'entrée "
                "dans le terrain, pas sa limite."
            )
            continue
        direction = ((p_c.x - p_t.x) / distance, (p_c.y - p_t.y) / distance)
        p_l = premier_croisement(p_t, direction, limite, PORTEE_TABLES_LIMITE_M)
        if p_l is None:
            rapport.append(
                f"Côté de clôture de {longueur} non coté : aucune limite "
                "parcellaire dans l'axe des tables à moins de "
                f"{_metres(PORTEE_TABLES_LIMITE_M, 0)}."
            )
            continue
        valeur = p_t.distance(p_l)
        cote_tables = CoteAPoser(
            famille="C1",
            depart=(p_t.x, p_t.y),
            arrivee=(p_l.x, p_l.y),
            texte=f"{_metres(valeur)} (tables – limite parcellaire)",
            valeur_m=valeur,
            vers_la_limite=True,
        )
        places = _places_cloture_limite(pan, cote_tables, limite, separation_m, rapport)
        resultats.append(CotesDuPan(pan=pan, tables_limite=cote_tables, places_cloture=places))
    return resultats


def _places_cloture_limite(pan, cote_tables, limite, separation_m, rapport) -> list:
    """Les endroits du côté où la cote clôture → limite peut se poser.

    Essayés au milieu, puis à 35, 65, 20 et 80 % du côté. Le point essayé est
    ramené sur la clôture réelle, et la cote part de là, perpendiculairement au
    côté, vers l'extérieur de l'enclos.
    """
    longueur = pan.longueur_m
    places, essais = [], []
    for fraction in FRACTIONS_COTE_CLOTURE:
        abscisse = fraction * longueur
        essai = pan.trace.interpolate(abscisse)
        _, sur_la_cloture = nearest_points(essai, pan.anneau)
        avant = pan.trace.interpolate(max(0.0, abscisse - DEMI_TANGENTE_M))
        apres = pan.trace.interpolate(min(longueur, abscisse + DEMI_TANGENTE_M))
        tx, ty = apres.x - avant.x, apres.y - avant.y
        norme = math.hypot(tx, ty)
        if norme < 1e-9:
            continue
        nx, ny = -ty / norme, tx / norme
        sonde = Point(sur_la_cloture.x + nx * 0.5, sur_la_cloture.y + ny * 0.5)
        if pan.enclos.contains(sonde):
            nx, ny = -nx, -ny
        # La clôture sur la limite : c'est un écart nul, pas une limite
        # introuvable, et il n'y a pas de seconde cote.
        a_la_limite = sur_la_cloture.distance(limite)
        if a_la_limite <= ECART_CLOTURE_LIMITE_MIN_M:
            essais.append((fraction, a_la_limite, "sur la limite"))
            continue
        croisement = premier_croisement(
            sur_la_cloture, (nx, ny), limite, PORTEE_CLOTURE_LIMITE_M
        )
        if croisement is None:
            essais.append((fraction, None, "limite introuvable"))
            continue
        ecart = sur_la_cloture.distance(croisement)
        cote = CoteAPoser(
            famille="C1",
            depart=(sur_la_cloture.x, sur_la_cloture.y),
            arrivee=(croisement.x, croisement.y),
            texte=f"{_metres(ecart)} (clôture – limite parcellaire)",
            valeur_m=ecart,
            vers_la_limite=True,
        )
        if cote.ligne.distance(cote_tables.ligne) < separation_m:
            essais.append((fraction, ecart, "trop près"))
            continue
        places.append(cote)

    if not places:
        rapport.append(_dire_les_essais(pan, cote_tables, essais, separation_m))
    return places


def _dire_les_essais(pan, cote_tables, essais, separation_m) -> str:
    entete = (
        f"Côté de clôture de {_metres(pan.longueur_m, 0)}, tables – limite "
        f"{_metres(cote_tables.valeur_m)} : pas de cote clôture – limite"
    )
    if essais and all(raison == "sur la limite" for _, _, raison in essais):
        plus_grand = max(ecart for _, ecart, _ in essais)
        return (
            f"{entete}, la clôture est sur la limite (écart de {_metres(plus_grand, 2)} "
            "au plus aux endroits essayés) : le dessin le montre."
        )
    details = []
    for fraction, ecart, raison in essais:
        valeur = "limite introuvable" if ecart is None else _metres(ecart)
        if raison == "trop près":
            raison = (
                f"trop près de la cote des tables, à moins de "
                f"{nombre_fr(SEPARATION_COTES_PAN_MM, 0)} mm de papier "
                f"({_metres(separation_m, 0)})"
            )
        details.append(
            f"{valeur} à {nombre_fr(fraction * 100, 0)} %" + ("" if raison == "limite introuvable" else f", {raison}")
        )
    return f"{entete} (essais : {' ; '.join(details)})."


def choisir_la_place_cloture_limite(places, autres, traits=()) -> CoteAPoser:
    """La place de la cote clôture → limite qui gêne le moins les autres cotes.

    Parmi les endroits du côté qui conviennent, celui qui reste le plus loin de
    toutes les autres cotes, une fois qu'elles sont connues : au milieu du côté,
    elle tombait à Auzainvilliers parmi celles de la citerne incendie et du
    local, et la cote de la voie n'avait plus de place (08/11/2026).

    `traits` : les lignes de la planche qu'aucune valeur ne coupe, comme la
    ligne de coupe, en Lambert 93. Elles comptent ici comme d'autres cotes. Sur
    le site synthétique de la DP 2, la coupe passe au milieu du côté sud : la
    cote s'y confondait avec le trait d'axe, et sa valeur n'avait plus de place
    (09/11/2026).
    """
    if not places:
        return None
    lignes = [autre.ligne for autre in autres] + list(traits)

    def eloignement(place):
        return min((place.ligne.distance(ligne) for ligne in lignes), default=math.inf)

    return max(places, key=eloignement)


def choisir_les_places_cloture_limite(cotes_des_pans, autres, traits=()) -> list:
    """La cote clôture → limite de chaque côté qui en a une, côté après côté.

    Chaque cote choisie rejoint `autres` avant le choix suivant, comme dans la
    maquette (v7, 09/11/2026) : de part et d'autre d'un angle, deux cotes
    choisies chacune pour soi peuvent tomber au pied l'une de l'autre. À
    Auzainvilliers, ce choix donne 12,8, 6,0 et 5,2 m, comme la maquette v7 ;
    le 6,4 m du brief vient d'un état antérieur de la maquette (rejoué le
    09/11/2026). `traits` : voir `choisir_la_place_cloture_limite`.
    """
    deja = list(autres)
    choisies = []
    for cotes_du_pan in cotes_des_pans:
        if not cotes_du_pan.places_cloture:
            continue
        choisie = choisir_la_place_cloture_limite(cotes_du_pan.places_cloture, deja, traits)
        choisies.append(choisie)
        deja.append(choisie)
    return choisies


# ---------------------------------------------------------------------------
# D2 et D3 — les ouvrages permanents, mesurés sur leur corps
# ---------------------------------------------------------------------------

#: Les ouvrages permanents (D2, 03/11/2026) : les trois familles de la DP 4,
#: lues dans `dp4_ouvrages` sans être recopiées, et depuis le 04/11 le bac de
#: rétention et la zone de remise. La première maquette n'en cotait aucun, et
#: la relecture a demandé pourquoi rien ne situait le bac parmi les ouvrages qui
#: l'entourent : le catalogue leur donne une hauteur, 2,3 et 3 m, ce sont des
#: constructions. Restent dehors la base vie et le stockage de chantier, qui
#: sont temporaires, le bac d'équarrissage et la contention, qui relèvent du
#: pâturage, l'aire d'aspiration et la plateforme, qui sont des sols.
CATEGORIES_OUVRAGES = POSTES + CONTENEURS + CITERNES + ("bac_retention", "zone_remise")

#: Deux corps d'une même catégorie plus proches que cela ne font qu'un ouvrage.
JOINT_CORPS_M = 0.025

#: En deçà, deux ouvrages se touchent : ni cote entre eux, ni obstacle pour un
#: segment qui ne fait que les effleurer.
CONTACT_M = 0.05


@dataclass(frozen=True)
class Ouvrage:
    """Un ouvrage permanent, tel que les cotes le mesurent.

    `geometrie` est l'union de ses `corps`, les objets du calque aux cotes du
    catalogue : le poste, jamais sa plateforme ni la terre remise autour de lui
    (D3). Un ouvrage qu'aucun objet ne représente aux cotes du catalogue a pour
    corps tout son dessin, et le rapport l'a dit.
    """

    categorie: str
    geometrie: BaseGeometry
    corps: tuple = ()


def ouvrages_permanents(contrat, objets, rapport: list) -> list:
    """Les ouvrages permanents du plan, chacun mesuré sur son corps.

    `objets` est ce que la planche dessine, `palette.objets_a_dessiner` : la
    reconnaissance des corps y est faite pour les postes et les conteneurs —
    l'aplat de 6,0 x 8,1 m sous chaque BESS d'Auzainvilliers y passe en
    plateforme. Les autres ouvrages se reconnaissent ici par la même fonction,
    `palette.separer_les_corps`, à la même tolérance : la maquette refaisait
    cette reconnaissance à 15 %, quand les corps mesurés sont à moins de 1 % du
    catalogue.

    Les corps d'une même catégorie qui se touchent, à 2,5 cm près, forment un
    seul ouvrage ; un corps dessiné deux fois compte une fois. Un ouvrage sans
    aucune surface — un contour resté ouvert — se dit au rapport : il ne sort
    jamais des cotes en silence, ce qu'a fait dans une version de la maquette la
    citerne de refroidissement d'Auzainvilliers.
    """
    from .palette import separer_les_corps

    dessines = dict(objets)
    ouvrages = []
    for categorie in CATEGORIES_OUVRAGES:
        parties = dessines.get(categorie) or []
        if not parties:
            continue
        surfaces = polygones_de(parties)
        if not surfaces:
            rapport.append(
                f"Ouvrage « {categorie} » : dessiné, mais aucune surface à mesurer "
                f"({len(parties)} objet(s) sans aire, un contour resté ouvert) — "
                "il n'est pas coté."
            )
            continue
        corps, autour, _ = separer_les_corps(contrat, categorie, surfaces)
        if not corps:
            mesure = (
                f"mesuré sur toutes ses surfaces ({len(surfaces)}, "
                f"{nombre_fr(sum(s.area for s in surfaces), 1)} m²)"
            )
            if _au_catalogue(contrat, categorie):
                raison = "aucun objet aux cotes du catalogue"
            else:
                # Le dessin n'y est pour rien : c'est le contrat qui ne porte
                # pas la cote de l'ouvrage.
                raison = "le catalogue du contrat ne porte pas sa cote"
            rapport.append(f"Ouvrage « {categorie} » : {raison}, {mesure}.")
            corps = surfaces
        elif autour:
            rapport.append(
                f"Ouvrage « {categorie} » : coté sur son corps aux cotes du "
                f"catalogue ; {len(autour)} autre(s) surface(s) du calque, "
                "dessinée(s) de la même teinte, ne sont pas mesurées."
            )
        # Chacun s'épaissit de la moitié du joint : deux corps se rejoignent
        # quand ils sont à `JOINT_CORPS_M` l'un de l'autre, et non au double.
        paquets = unary_union([g.buffer(JOINT_CORPS_M / 2.0) for g in corps])
        for paquet in polygones_de([paquets]):
            membres = tuple(g for g in corps if g.intersects(paquet))
            ouvrages.append(
                Ouvrage(categorie=categorie, geometrie=unary_union(membres), corps=membres)
            )
    return ouvrages


def _au_catalogue(contrat, categorie: str) -> bool:
    """Le contrat porte-t-il une cote normalisée pour cette catégorie ?

    Lu sur les libellés bruts, sans décoder les cotes : un catalogue mal formé
    se dit ailleurs, quand on lit ses dimensions.
    """
    from ..contrat import LIBELLES_COTES

    portes = {
        str(brut.get("ouvrage", "")).strip()
        for brut in contrat.donnees.get("cotes_normalisees", [])
    }
    return any(libelle in portes for libelle in LIBELLES_COTES.get(categorie, ()))


def _sur_le_trajet(segment, ouvrages, exclus) -> list:
    """Les catégories des ouvrages, hors `exclus`, que le segment traverse."""
    return [
        o.categorie
        for k, o in enumerate(ouvrages)
        if k not in exclus
        and segment.intersects(o.geometrie)
        and segment.intersection(o.geometrie).length > CONTACT_M
    ]


def _guillemets(categories) -> str:
    return ", ".join(f"« {c} »" for c in categories)


# ---------------------------------------------------------------------------
# C3 — un ouvrage → ses voisins directs, et → la limite parcellaire
# ---------------------------------------------------------------------------

#: Seuil des cotes entre ouvrages voisins, et de leur cote à la limite.
SEUIL_VOISINS_M = 30.0

#: Les batteries et le local de stockage se cotent jusqu'à la limite **à toute
#: distance**, et même par-dessus un autre ouvrage : c'est eux que
#: l'instructeur nomme, « la distance des locaux de stockage et de batteries »
#: (04/11/2026). À Auzainvilliers, aucun des deux BESS n'avait de cote, l'un à
#: 19,7 m derrière le PDL/PTR, l'autre à 30,9 m. Le calque
#: `UNI_Local_Stockage` arrive en `local_technique` (`import_be.py`).
TOUJOURS_A_LA_LIMITE = ("bess", "local_technique")


def cotes_entre_ouvrages(ouvrages, limite, rapport: list) -> list:
    """Chaque ouvrage → ses voisins directs, à moins de 30 m, et → la limite (C3).

    Les **voisins directs** sont ceux du graphe de voisinage relatif : la paire
    i–j ne se cote pas quand un troisième ouvrage k est plus proche des deux,
    max(d(i, k), d(j, k)) < d(i, j). Les deux cotes qui passent par k situent
    déjà la paire ; chaque ouvrage garde son plus proche voisin, et une zone
    reste d'un seul tenant. À Auzainvilliers : 9 cotes au lieu de 24 paires à
    moins de 30 m (10/11/2026). Un ouvrage posé sur le segment interdit aussi
    la cote, sans quoi trois conteneurs alignés donneraient la cote du premier
    au troisième à travers le deuxième.

    Le brief annonçait 19 paires à Auzainvilliers, pour les mêmes 9 cotes : la
    maquette retirait de son compte, sans le dire, les paires qu'un ouvrage
    sépare, et tenait pour séparée au moindre contact une paire dont le segment
    frôle un conteneur sur 4 mm — bac de rétention et zone de remise, que le
    module, à `CONTACT_M` près, dit située (rejouée le 10/11/2026). Ici, chaque
    paire compte, et le rapport dit ce qu'elle devient.

    La cote **à la limite** se pose en deçà de 30 m, quand aucun ouvrage n'est
    sur le trajet, et toujours pour `TOUJOURS_A_LA_LIMITE` : le rapport dit
    alors quelle règle commune elle franchit. Un ouvrage ne se cote pas vers la
    voie (03/11/2026), sauf le poste de livraison, voir
    `cotes_poste_de_livraison`.
    """
    if limite is None and ouvrages:
        rapport.append(
            "Cotes à la limite : pas de limite parcellaire connue, les ouvrages "
            "permanents ne se cotent pas à la limite."
        )
    distances = [[a.geometrie.distance(b.geometrie) for b in ouvrages] for a in ouvrages]
    cotes = []
    sous_le_seuil = separees = situees = 0
    a_la_limite = 0
    for i, a in enumerate(ouvrages):
        for j in range(i + 1, len(ouvrages)):
            b = ouvrages[j]
            d = distances[i][j]
            if not CONTACT_M < d < SEUIL_VOISINS_M:
                continue
            pa, pb = nearest_points(a.geometrie, b.geometrie)
            sous_le_seuil += 1
            entre = _sur_le_trajet(LineString([pa, pb]), ouvrages, {i, j})
            if entre:
                separees += 1
                rapport.append(
                    f"Cote entre ouvrages : « {a.categorie} » – « {b.categorie} » "
                    f"({_metres(d)}) non cotée, {_guillemets(entre)} "
                    f"{'est posé' if len(entre) == 1 else 'sont posés'} sur le segment "
                    "qui les joint."
                )
                continue
            k = _plus_proche_des_deux(distances, i, j)
            if k is not None:
                situees += 1
                rapport.append(
                    f"Cote entre ouvrages : « {a.categorie} » – « {b.categorie} » "
                    f"({_metres(d)}) non cotée, « {ouvrages[k].categorie} » est "
                    f"plus proche des deux ({_metres(distances[i][k])} et "
                    f"{_metres(distances[j][k])}), et ses deux cotes la situent."
                )
                continue
            cotes.append(CoteAPoser(
                famille="C3", depart=(pa.x, pa.y), arrivee=(pb.x, pb.y),
                texte=_metres(d), valeur_m=d, ouvrages=(i, j),
            ))
        if limite is None:
            continue
        cote = _cote_a_la_limite(i, a, ouvrages, limite, rapport)
        if cote is not None:
            cotes.append(cote)
            a_la_limite += 1
    paires = sum(1 for c in cotes if len(c.ouvrages) == 2)
    rapport.append(
        f"Cotes entre ouvrages : {len(ouvrages)} ouvrage(s) permanent(s) ; "
        f"{sous_le_seuil} paire(s) à moins de {_metres(SEUIL_VOISINS_M, 0)} — "
        f"{paires} cotée(s), {separees} séparée(s) par un ouvrage, {situees} "
        f"située(s) par un troisième — ; {a_la_limite} cote(s) à la limite "
        "parcellaire."
    )
    return cotes


def _plus_proche_des_deux(distances, i, j):
    """Le troisième ouvrage plus proche de i et de j qu'ils ne le sont entre eux."""
    candidats = [
        k for k in range(len(distances))
        if k not in (i, j) and max(distances[i][k], distances[j][k]) < distances[i][j]
    ]
    if not candidats:
        return None
    return min(candidats, key=lambda k: max(distances[i][k], distances[j][k]))


def _cote_a_la_limite(rang, ouvrage, ouvrages, limite, rapport):
    d = ouvrage.geometrie.distance(limite)
    if d < CONTACT_M:
        # Le lot 2ter pose les postes de livraison sur la limite
        # (`plan_pdf.POSTES_EN_LIMITE`) : une cote de longueur nulle ne porte
        # pas de flèches, et ferait partir sa zone en détail à toute échelle.
        rapport.append(
            f"Cote à la limite : « {ouvrage.categorie} » posé sur la limite "
            "parcellaire, pas de cote : le dessin le montre."
        )
        return None
    pa, pl = nearest_points(ouvrage.geometrie, limite)
    sur_le_trajet = _sur_le_trajet(LineString([pa, pl]), ouvrages, {rang})
    loin = d >= SEUIL_VOISINS_M
    debut = (
        f"Cote à la limite : « {ouvrage.categorie} » à {_metres(d)} de la limite "
        "parcellaire"
    )
    franchies = ([f"au-delà de {_metres(SEUIL_VOISINS_M, 0)}"] if loin else []) + (
        [f"par-dessus {_guillemets(sur_le_trajet)}"] if sur_le_trajet else []
    )
    if ouvrage.categorie not in TOUJOURS_A_LA_LIMITE and franchies:
        raison = (
            f"au-delà de {_metres(SEUIL_VOISINS_M, 0)}" if loin
            else f"{_guillemets(sur_le_trajet)} s'intercale"
        )
        rapport.append(f"{debut}, non coté : {raison}.")
        return None
    if franchies:
        rapport.append(
            f"{debut}, coté {' et '.join(franchies)} : les batteries et le local de "
            "stockage se cotent toujours à la limite."
        )
    return CoteAPoser(
        famille="C3", depart=(pa.x, pa.y), arrivee=(pl.x, pl.y),
        texte=f"{_metres(d)} (limite parcellaire)", valeur_m=d,
        vers_la_limite=True, ouvrages=(rang,),
    )


# ---------------------------------------------------------------------------
# C7 — batteries et citernes → la table la plus proche
# ---------------------------------------------------------------------------

#: Ce que le SDIS regarde : le risque d'un côté, batteries et citerne de
#: refroidissement, la défense de l'autre, la citerne incendie (07/11/2026).
#: Une cote par famille, la plus courte (09/11/2026).
FAMILLES_VERS_LES_TABLES = ("bess", "citerne_refroidissement", "bache_incendie")


def cotes_vers_les_tables(ouvrages, tables, rapport: list) -> list:
    """Pour chaque famille, l'ouvrage le plus proche des tables → la table (C7).

    **Une cote par famille, la plus courte.** La relecture d'Auzainvilliers la
    demandait pour le BESS sud et les deux citernes ; la cote du BESS nord, à
    28,3 m des tables quand le BESS sud en est à 8,3 m, a été jugée « pas
    utile » (09/11/2026). Les autres membres de la famille sont nommés au
    rapport, avec la distance du plus proche.

    Comme pour une paire d'ouvrages, la cote ne se pose pas quand un autre
    ouvrage est sur le segment : il porte déjà la distance qui compte. À
    Auzainvilliers, le BESS nord passait par-dessus la citerne de
    refroidissement (07/11/2026).
    """
    surfaces = polygones_de(tables)
    if not surfaces:
        if any(o.categorie in FAMILLES_VERS_LES_TABLES for o in ouvrages):
            rapport.append(
                "Cote vers les tables : aucune table au plan, les batteries et les "
                "citernes ne se cotent pas vers elles."
            )
        return []
    tables_union = unary_union(surfaces)
    cotes = []
    for famille in FAMILLES_VERS_LES_TABLES:
        membres = [
            (rang, o, o.geometrie.distance(tables_union))
            for rang, o in enumerate(ouvrages)
            if o.categorie == famille
        ]
        if not membres:
            continue
        rang, plus_proche, d = min(membres, key=lambda m: m[2])
        for autre_rang, _, d_autre in membres:
            if autre_rang != rang:
                rapport.append(
                    f"Cote vers les tables : « {famille} » à "
                    f"{nombre_fr(d_autre, 2)} m de la table la plus proche, non "
                    f"coté : un autre « {famille} » en est à {nombre_fr(d, 2)} m, "
                    "et une famille n'a qu'une cote, la plus courte."
                )
        pa, pt = nearest_points(plus_proche.geometrie, tables_union)
        entre = _sur_le_trajet(LineString([pa, pt]), ouvrages, {rang})
        if entre:
            rapport.append(
                f"Cote vers les tables : « {famille} » à {nombre_fr(d, 2)} m de la "
                f"table la plus proche, non coté : {_guillemets(entre)} s'intercale "
                "et porte déjà la distance qui compte."
            )
            continue
        cotes.append(CoteAPoser(
            famille="C7", depart=(pa.x, pa.y), arrivee=(pt.x, pt.y),
            texte=f"{_metres(d)} (table la plus proche)", valeur_m=d,
            ouvrages=(rang,),
        ))
    return cotes


# ---------------------------------------------------------------------------
# D7 — les zones techniques, et ce qui les envoie sur une planche de détail
# ---------------------------------------------------------------------------

#: Une cote plus courte que cela sur la DP 2 envoie sa zone sur une planche de
#: détail (04/11/2026 ; 10 mm dans le brief du 03/11/2026).
SEUIL_LISIBLE_MM = 3.0


@dataclass(frozen=True)
class ZoneTechnique:
    """Des ouvrages que des cotes C3 relient, et toutes leurs cotes (D7).

    `ouvrages` : leurs rangs dans la liste des ouvrages permanents. `cotes` :
    leurs cotes C3, entre eux et à la limite, et les cotes C7 et C8 qui
    partent d'eux, dans l'ordre où elles ont été calculées.
    """

    ouvrages: tuple
    cotes: tuple


def zones_techniques(cotes) -> list:
    """Les zones des cotes d'ouvrages, dans l'ordre de leur premier ouvrage.

    Une zone est un ensemble d'ouvrages que des cotes C3 relient ; leurs cotes
    C7 et C8 la suivent (D7, 04/11/2026). Une cote qui ne part d'aucun ouvrage
    — C1, C2, C4, C5, C6 — n'est d'aucune zone : elle reste sur la DP 2. Un
    ouvrage sans cote ne fait pas de zone : il n'y a rien à y lire.
    """
    parent = {}

    def racine(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for cote in cotes:
        for k in cote.ouvrages:
            parent.setdefault(k, k)
        if len(cote.ouvrages) == 2:
            parent[racine(cote.ouvrages[0])] = racine(cote.ouvrages[1])
    membres, propres = {}, {}
    for k in parent:
        membres.setdefault(racine(k), []).append(k)
    for cote in cotes:
        if cote.ouvrages:
            propres.setdefault(racine(cote.ouvrages[0]), []).append(cote)
    zones = [
        ZoneTechnique(ouvrages=tuple(sorted(rangs)), cotes=tuple(propres.get(r, ())))
        for r, rangs in membres.items()
    ]
    return sorted(zones, key=lambda zone: zone.ouvrages[0])


def raisons_du_detail(zone, denominateur: int, genes) -> list:
    """Pourquoi la zone part sur une planche de détail, ou rien si la DP 2 la lit (D7).

    - une de ses cotes fait moins de 3 mm de papier à l'échelle de la DP 2 ;
    - une de ses valeurs n'a pas de place nette, ou une de ses lignes passe sous
      la légende : ce que la pose rend en gêne (`pose_des_cotes.Gene`). Ces
      deux-là ne se voient qu'en dessinant. Une valeur posée sur les tables, ou
      en travers d'un cadre de détail, n'en est pas une : elle se lit.
    """
    raisons = []
    courte = min(zone.cotes, key=lambda cote: cote.longueur_m)
    longueur = metres_vers_mm(courte.longueur_m, denominateur)
    if longueur < SEUIL_LISIBLE_MM:
        raisons.append(
            f"« {courte.texte} » ne fait que {nombre_fr(longueur, 1)} mm sur la DP 2, "
            f"sous les {nombre_fr(SEUIL_LISIBLE_MM, 0)} mm lisibles"
        )
    for gene in genes:
        if any(gene.cote is cote for cote in zone.cotes):
            raisons.append(f"« {gene.texte} » : {gene.raison}")
    return raisons


# ---------------------------------------------------------------------------
# C5 — l'écartement entre deux rangées, à la valeur de la coupe
# ---------------------------------------------------------------------------

#: L'écart du plan qui porte la cote vaut celui de la coupe à cela près.
TOLERANCE_INTER_RANGEE_M = 0.15

#: Écarts entre tables tenus pour des écarts entre rangées : en deçà, deux
#: tables se touchent ; au-delà, une piste ou un ouvrage les sépare.
ECART_RANGEES_MIN_M = 1.0
ECART_RANGEES_MAX_M = 15.0

#: Un écart se prend en travers des rangées, à cet angle près.
ANGLE_TRAVERS_DEG = 10.0


def table_de_la_coupe(contrat, rapport: list):
    """La table de la coupe de type, ou `None` si la coupe ne se calcule pas.

    C'est `dp3_coupes.geometrie_table`, la fonction même de la DP 3, et non une
    formule refaite à côté (D6) : sur Sarnois, trois chiffres coexistent — 5,0 m
    d'inter-table, 9,0 m de pas, 8 m aux standards UNITe. Elle donne
    l'inter-rangée (C5) et la hauteur maximale des tables en légende (D12).

    Ses avertissements se disent ici aussi : la DP 3 n'est pas produite sans
    profil de terrain (`assemblage`), et une hauteur prise aux standards UNITe,
    ou une inter-table déduite du pas, arriverait alors sur le plan de masse
    sans un mot (relecture du 09/11/2026, sur le dossier HelioScope des
    Islettes). Quand la DP 3 est produite, le rapport les lit deux fois : c'est
    le prix d'aucun silence.
    """
    from ..erreurs import ErreurDP
    from .dp3_coupes import geometrie_table

    try:
        table, avertissements = geometrie_table(contrat)
        rapport.extend(
            f"Valeurs reprises de la coupe par le plan de masse (inter-rangée, "
            f"hauteur des tables) — {avertissement}"
            for avertissement in avertissements
        )
    except ErreurDP as erreur:
        rapport.append(
            f"Inter-rangée et hauteur des tables : la coupe des tables ne se "
            f"calcule pas — {erreur} Pas de cote d'inter-rangée, ni de hauteur "
            "des tables en légende."
        )
        return None
    return table


def cote_inter_rangee(tables, inter_table_m: float, rapport: list):
    """Une cote d'écartement entre deux rangées, sur un écart qui vaut la coupe (C5).

    La cote se pose **une fois** (03/11/2026), sur l'écart mesuré qui vaut la
    coupe à 0,15 m près, le plus proche du centre du champ. Si aucun écart du
    plan ne la mesure, il n'y a pas de cote, et le rapport signale le
    désaccord : plaquer la valeur sur un écart qui ne la mesure pas, ce serait
    exactement la planche fausse qui s'affiche correctement.

    La valeur écrite est celle de la coupe, au nombre près que la DP 3 écrit ;
    la ligne mesure l'écart du plan. La relecture du 07/11/2026 attendait 4,5 m
    à Saint-Cyr et lisait 4,9 m : la maquette tournait sur l'indice IND06, le
    dossier déposé est l'IND07 — coupe et plan concordent dans chaque indice.
    """
    surfaces = polygones_de(tables)
    if len(surfaces) < 2:
        rapport.append(
            "Inter-rangée : moins de deux tables au plan, pas d'écart entre rangées "
            "à mesurer."
        )
        return None
    # La direction de chaque table, et non un axe pour tout le plan : deux
    # champs d'orientations différentes n'ont pas d'axe commun, et rapporté à
    # leur moyenne, aucun de leurs écarts ne se lisait en travers.
    axes = [_axe_de_la_table(t) for t in surfaces]
    from shapely.strtree import STRtree

    arbre = STRtree(surfaces)
    ecarts = []
    for i, a in enumerate(surfaces):
        for j in arbre.query(a.buffer(ECART_RANGEES_MAX_M)):
            if j <= i:
                continue
            b = surfaces[j]
            d = a.distance(b)
            if not ECART_RANGEES_MIN_M < d < ECART_RANGEES_MAX_M:
                continue
            pa, pb = nearest_points(a, b)
            direction = _direction_deg((pa.x, pa.y), (pb.x, pb.y)) % 180.0
            if all(
                axe is not None
                and abs(((direction - axe) % 180.0) - 90.0) < ANGLE_TRAVERS_DEG
                for axe in (axes[i], axes[j])
            ):
                ecarts.append((d, pa, pb))

    justes = [e for e in ecarts if abs(e[0] - inter_table_m) <= TOLERANCE_INTER_RANGEE_M]
    if not justes:
        mesures = sorted({round(e[0], 1) for e in ecarts})
        vus = (
            f"écarts mesurés entre rangées : {' ; '.join(nombre_fr(m, 1) for m in mesures[:8])} m"
            if mesures else "aucun écart mesuré entre rangées"
        )
        rapport.append(
            f"Inter-rangée : aucun écart du plan ne mesure les "
            f"{_comme_la_coupe(inter_table_m)} m de la coupe, à "
            f"{nombre_fr(TOLERANCE_INTER_RANGEE_M, 2)} m près ({vus}) — pas de "
            "cote : le plan de masse et la coupe ne disent pas la même chose."
        )
        return None
    centre = unary_union(surfaces).centroid
    d, pa, pb = min(
        justes,
        key=lambda e: Point((e[1].x + e[2].x) / 2.0, (e[1].y + e[2].y) / 2.0).distance(centre),
    )
    return CoteAPoser(
        famille="C5", depart=(pa.x, pa.y), arrivee=(pb.x, pb.y),
        texte=f"{_comme_la_coupe(inter_table_m)} m entre rangées",
        valeur_m=inter_table_m,
    )


def _axe_de_la_table(table):
    """La direction d'une table, celle de son grand côté, de 0 à 180°, ou `None`."""
    rectangle = table.minimum_rotated_rectangle
    if rectangle.geom_type != "Polygon":
        return None
    sommets = list(rectangle.exterior.coords)[:4]
    grand = max(
        ((sommets[k], sommets[(k + 1) % 4]) for k in range(4)),
        key=lambda s: math.dist(*s),
    )
    return _direction_deg(*grand) % 180.0


def _comme_la_coupe(valeur: float) -> str:
    """Le nombre que la DP 3 écrit, sans son zéro final : 4,50 → 4,5 ; 4,55 → 4,55."""
    texte = nombre_fr(valeur, 2)
    return texte[:-1] if texte.endswith("0") else texte


# ---------------------------------------------------------------------------
# C6 — la largeur de chaque piste, prise en travers
# ---------------------------------------------------------------------------

#: Ne sont pas des pistes (03/11/2026) : une bande plus étroite que cela…
LARGEUR_PISTE_MIN_M = 2.0
#: … une surface de moins de trois fois le carré de sa largeur, qui est une aire…
ELANCEMENT_PISTE_MIN = 3.0
#: … et les miettes d'un tracé, qui ne portent aucune largeur.
AIRE_PISTE_MIN_M2 = 20.0

#: Une largeur par valeur distincte, à cet écart près, et par type de piste.
ARRONDI_LARGEUR_PISTE_M = 0.5

#: Écart entre deux rayons de mesure le long du bord, et leur portée.
PAS_RAYONS_PISTE_M = 3.0
PORTEE_RAYON_PISTE_M = 60.0

#: Une « piste » que les ouvrages couvrent à ce point, ou qui porte cette part
#: du corps d'un ouvrage, est sa plateforme : la maquette cotait 4,2 m sous un
#: poste (03/11/2026).
RECOUVREMENT_OUVRAGES = 0.8
PART_DU_CORPS_PORTEE = 0.5

#: Morceaux jointifs d'une même piste, recollés à cela près.
JOINT_PISTE_M = 0.05


def _categories_de_piste() -> tuple:
    """Les pistes du contrat, lues dans `import_be` et non recopiées.

    Les pistes existantes comptent : à Saint-Cyr, elles sont « à renforcer si
    nécessaire », donc des travaux du projet. L'aire de grutage n'est pas une
    piste. Importées dans la fonction : les planches ne chargent pas l'import
    du plan pour se charger elles-mêmes.
    """
    from ..import_be import CATEGORIES_PISTE_LEGERE, CATEGORIES_VOIE_LOURDE

    return tuple(
        c for c in CATEGORIES_VOIE_LOURDE + CATEGORIES_PISTE_LEGERE if c != "aire_grutage"
    )


def cotes_de_largeur_de_piste(objets, ouvrages, rapport: list) -> list:
    """Une cote par largeur distincte de piste, et par type de piste (C6).

    `objets` est ce que la planche dessine : une voirie que le chef de projet a
    rangée en piste y figure sous son type. La largeur se prend en travers
    (`largeur_en_travers`). Aucune cote ne relie une piste à la clôture
    (03/11/2026), et le libellé dit « (piste) » : sans lui, la largeur d'une
    piste qui longe la clôture se lisait comme leur écart.
    """
    dessines = dict(objets)
    corps = [o.geometrie for o in ouvrages]
    sous_les_ouvrages = unary_union(corps) if corps else None
    cotes = []
    for categorie in _categories_de_piste():
        traces = dessines.get(categorie) or []
        axes = [g for g in traces if g.geom_type in ("LineString", "LinearRing", "MultiLineString")]
        if axes:
            # Une piste du plan PDF n'a que son axe (lot 2ter) : la palette la
            # dessine en trait, à une épaisseur de symbole et non de terrain.
            rapport.append(
                f"Largeur de piste : « {categorie} », {len(axes)} tracé(s) sans surface "
                "— un axe, dessiné en trait — : pas de largeur à mesurer."
            )
        morceaux = polygones_de(traces)
        if not morceaux:
            continue
        # Une piste dessinée en morceaux jointifs est une seule piste. Les plus
        # grandes d'abord : c'est sur elles que la largeur se lit le mieux.
        fondues = unary_union([m.buffer(JOINT_PISTE_M) for m in morceaux]).buffer(-JOINT_PISTE_M)
        deja, miettes = [], 0
        for piste in sorted(polygones_de([fondues]), key=lambda p: -p.area):
            aire = piste.area
            if aire < AIRE_PISTE_MIN_M2:
                miettes += 1
                continue
            nom = f"Largeur de piste : « {categorie} » de {nombre_fr(aire, 0)} m²"
            if (
                sous_les_ouvrages is not None
                and piste.intersection(sous_les_ouvrages).area > RECOUVREMENT_OUVRAGES * aire
            ):
                rapport.append(f"{nom} écartée : les ouvrages la couvrent, c'est leur sol.")
                continue
            if any(piste.intersection(c).area >= PART_DU_CORPS_PORTEE * c.area for c in corps):
                rapport.append(
                    f"{nom} écartée : elle porte le corps d'un ouvrage, c'est sa plateforme."
                )
                continue
            travers = largeur_en_travers(piste)
            if travers is None:
                rapport.append(f"{nom} : largeur non mesurable, non cotée.")
                continue
            largeur = travers.length
            if largeur < LARGEUR_PISTE_MIN_M:
                rapport.append(
                    f"{nom} écartée, {_metres(largeur)} de large : une lanière, pas une piste."
                )
                continue
            if aire / largeur**2 < ELANCEMENT_PISTE_MIN:
                rapport.append(
                    f"{nom} écartée, {_metres(largeur)} de large : une aire, pas une piste."
                )
                continue
            # À moins d'un demi-mètre d'une largeur déjà cotée, c'est la même :
            # des cases d'arrondi rangeaient 5,2 et 5,3 m dans deux largeurs.
            if any(abs(largeur - autre) < ARRONDI_LARGEUR_PISTE_M for autre in deja):
                rapport.append(
                    f"{nom}, {_metres(largeur)} : largeur déjà cotée pour ce type de piste."
                )
                continue
            deja.append(largeur)
            (x0, y0), (x1, y1) = travers.coords[0], travers.coords[-1]
            cotes.append(CoteAPoser(
                famille="C6", depart=(x0, y0), arrivee=(x1, y1),
                texte=f"{_metres(largeur)} (piste)", valeur_m=largeur,
            ))
        if miettes:
            rapport.append(
                f"Largeur de piste : « {categorie} », {miettes} morceau(x) de moins de "
                f"{nombre_fr(AIRE_PISTE_MIN_M2, 0)} m², trop petit(s) pour porter une "
                "largeur, non coté(s)."
            )
    return cotes


def largeur_en_travers(piste):
    """La largeur d'une piste, prise perpendiculairement à son bord : un segment.

    Des rayons partent du bord, à angle droit, vers l'intérieur, et l'on garde
    leur médiane, qui écarte les bouts, les virages et les élargissements. Un
    rayon traverse la piste dans sa largeur même quand elle tourne. Rend le
    segment médian, du bord au bord opposé, ou `None`.
    """
    bord = piste.exterior
    mesures = []
    nombre = max(12, int(bord.length // PAS_RAYONS_PISTE_M))
    for k in range(nombre):
        s = k * bord.length / nombre
        b = bord.interpolate(s)
        avant = bord.interpolate(max(0.0, s - DEMI_TANGENTE_M))
        apres = bord.interpolate(min(bord.length, s + DEMI_TANGENTE_M))
        tx, ty = apres.x - avant.x, apres.y - avant.y
        norme = math.hypot(tx, ty)
        if norme < 1e-9:
            continue
        for sens in (1.0, -1.0):
            nx, ny = -ty / norme * sens, tx / norme * sens
            if piste.contains(Point(b.x + nx * 0.05, b.y + ny * 0.05)):
                break
        else:
            continue
        rayon = LineString([
            (b.x + nx * 0.01, b.y + ny * 0.01),
            (b.x + nx * PORTEE_RAYON_PISTE_M, b.y + ny * PORTEE_RAYON_PISTE_M),
        ])
        dedans = rayon.intersection(piste)
        if dedans.is_empty:
            continue
        if dedans.geom_type != "LineString":
            parties = [p for p in getattr(dedans, "geoms", []) if p.geom_type == "LineString"]
            if not parties:
                continue
            dedans = min(parties, key=lambda p: p.distance(b))
        bout = max((Point(c) for c in dedans.coords), key=b.distance)
        mesures.append(LineString([(b.x, b.y), (bout.x, bout.y)]))
    if not mesures:
        return None
    mesures.sort(key=lambda m: m.length)
    return mesures[len(mesures) // 2]


# ---------------------------------------------------------------------------
# C4 — clôture → habitation la plus proche
# ---------------------------------------------------------------------------

#: La recherche s'arrête à cette distance de la clôture (D5) : au-delà, la
#: légende dit qu'il n'y a pas d'habitation, ce qui est un résultat.
RAYON_HABITATION_M = 1000.0

#: L'usage BD TOPO d'une habitation, et celui qui ne dit rien (vérifiés sur le
#: WFS de la Géoplateforme le 03/11/2026, `BDTOPO_V3:batiment`, `usage_1`).
USAGE_HABITATION = "Résidentiel"
USAGE_INDIFFERENCIE = "Indifférencié"

#: Un bâtiment du cadastre est connu de la BD TOPO quand ses bâtiments en
#: recouvrent au moins cette part. Leurs contours ne coïncident pas — à
#: Saint-Cyr, la maison l'est à 81 %, une remise à 58 % —, mais sur les trois
#: sites d'épreuve, un bâtiment du cadastre l'est à 50 % ou plus, ou pas du
#: tout (mesuré le 10/11/2026) : le seuil tombe dans le vide entre les deux.
PART_CONNUE_DE_LA_BD_TOPO = 0.25

#: Les bâtiments que la BD TOPO ignore, nommés un à un au rapport ; les
#: suivants se comptent.
INCONNUS_NOMMES = 3

#: Un bâtiment du cadastre est le contour d'un bâtiment de la BD TOPO quand
#: leur partie commune fait au moins cette part du plus petit des deux : une
#: maison n'est parfois qu'une partie d'un grand bâtiment cadastral, une ferme.
#: Mesuré le 10/11/2026 : les 176 habitations des trois sites d'épreuve ont
#: toutes un bâtiment du cadastre qui les recouvre ainsi, de 52 à 100 %.
PART_COMMUNE_DU_CONTOUR = 0.25


def _contours_au_cadastre(cadastre):
    """La fonction qui rend le contour au cadastre d'un bâtiment de la BD TOPO, ou `None`.

    La cote de l'habitation va à ce contour : c'est celui que la DP 2 hachure,
    et celui que mesure l'instructeur (relecture de l'épreuve A3, 10/11/2026).
    """
    geometries = [
        b.geometrie for b in cadastre or ()
        if b.geometrie is not None and not b.geometrie.is_empty and b.geometrie.area > 0
    ]
    if not geometries:
        return lambda geometrie: None
    arbre = STRtree(geometries)

    def contour(geometrie):
        if geometrie.area <= 0:
            return None
        siens = []
        for rang in arbre.query(geometrie):
            candidat = geometries[rang]
            commune = candidat.intersection(geometrie).area
            if commune >= PART_COMMUNE_DU_CONTOUR * min(candidat.area, geometrie.area):
                siens.append(candidat)
        return unary_union(siens) if siens else None

    return contour


def _traces_de_cloture(clotures):
    """Le trait de la clôture : le contour de ses enclos, et ses tronçons ouverts."""
    traits = []
    for geometrie in clotures:
        if geometrie is None or geometrie.is_empty:
            continue
        if geometrie.geom_type in ("LineString", "LinearRing", "MultiLineString"):
            traits.append(geometrie)
        else:
            traits.extend(p.exterior for p in polygones_de([geometrie]))
    return unary_union(traits) if traits else None


def _inconnus_de_la_bd_topo(trace, batiments, cadastre, distance_max, parcelles) -> list:
    """Les bâtiments du cadastre plus près de la clôture que `distance_max`, que la BD TOPO ignore.

    Rend des (distance, aire, parcelle) du plus proche au plus loin ; la
    parcelle est la désignation de celle qui le porte, parmi `parcelles`, ou
    `None` hors d'elles.
    """
    connus = unary_union([g for g, _ in batiments]) if batiments else None
    inconnus = []
    for batiment in cadastre:
        geometrie = batiment.geometrie
        if geometrie is None or geometrie.is_empty or geometrie.area <= 0:
            continue
        distance = geometrie.distance(trace)
        if distance >= distance_max:
            continue
        recouverte = 0.0 if connus is None else geometrie.intersection(connus).area / geometrie.area
        if recouverte >= PART_CONNUE_DE_LA_BD_TOPO:
            continue
        point = geometrie.representative_point()
        parcelle = next((p.designation for p in parcelles if p.geometrie.covers(point)), None)
        inconnus.append((distance, geometrie.area, parcelle))
    return sorted(inconnus, key=lambda inconnu: inconnu[0])


def _liste_des_inconnus(inconnus) -> str:
    noms = [
        f"{nombre_fr(aire, 0)} m² à {_metres(distance, 0)}" + (f" ({parcelle})" if parcelle else "")
        for distance, aire, parcelle in inconnus[:INCONNUS_NOMMES]
    ]
    reste = len(inconnus) - INCONNUS_NOMMES
    return ", ".join(noms) + (f", et {reste} autre(s)" if reste > 0 else "")


def cote_habitation(clotures, batiments, rapport: list, cadastre=None, parcelles=()):
    """La clôture → le bâtiment d'habitation le plus proche (C4).

    `batiments` : des couples (géométrie, propriétés BD TOPO). C'est la BD TOPO
    qui dit quel bâtiment est une habitation : le cadastre ne dit pas l'usage.
    Sur Sarnois, son bâtiment le plus proche est un hangar agricole, à 103 m,
    quand l'habitation est à 166 m (03/11/2026). Un bâtiment d'usage
    indifférencié plus proche que l'habitation se dit au rapport, avec sa
    distance ; il ne la remplace pas sur le plan.

    `cadastre` : les bâtiments du cadastre autour de la clôture, s'ils ont été
    lus. La cote va au contour au cadastre de l'habitation, que la DP 2
    hachure et que mesure l'instructeur, et la plus proche se juge sur lui :
    à Saint-Cyr, 111,5 m par le cadastre, 119,5 m par la BD TOPO (relecture de
    l'épreuve A3, 10/11/2026). Une habitation que le cadastre n'a pas se cote
    sur son contour de la BD TOPO, et le rapport le dit. Les bâtiments du
    cadastre plus proches que l'habitation, et que la BD TOPO ne connaît pas,
    se disent au rapport avec leur parcelle parmi `parcelles` : à Saint-Cyr,
    40 m² à 26 m et 935 m² à 90 m. Rien ne dit s'ils sont habités ; ils ne la
    remplacent pas sur le plan.
    """
    trace = _traces_de_cloture(clotures)
    if trace is None or trace.is_empty:
        rapport.append("Habitation la plus proche : pas de clôture au plan, rien à coter.")
        return None
    contour_de = _contours_au_cadastre(cadastre)

    def a_coter(geometrie):
        """(distance, contour coté, vrai si ce contour est celui de la BD TOPO faute de cadastre)."""
        contour = contour_de(geometrie)
        cible = geometrie if contour is None else contour
        return cible.distance(trace), cible, contour is None

    # Trié sur la seule distance : à égalité, deux maisons mitoyennes, le tri
    # comparait les bâtiments eux-mêmes, et levait (relecture du 09/11/2026).
    habitations = sorted(
        (
            a_coter(g)
            for g, proprietes in batiments
            if (proprietes or {}).get("usage_1") == USAGE_HABITATION
        ),
        key=lambda h: h[0],
    )
    habitations = [h for h in habitations if h[0] <= RAYON_HABITATION_M]
    if not habitations:
        rapport.append(
            f"Habitation la plus proche : aucune habitation à moins de "
            f"{_metres(RAYON_HABITATION_M, 0)} de la clôture selon la BD TOPO — "
            "la légende le dit."
        )
        inconnus = _inconnus_de_la_bd_topo(
            trace, batiments, cadastre or [], RAYON_HABITATION_M, parcelles
        )
        if inconnus:
            rapport.append(
                f"Habitation la plus proche : {len(inconnus)} bâtiment(s) du cadastre à "
                f"moins de {_metres(RAYON_HABITATION_M, 0)} de la clôture, que la BD TOPO "
                f"ne connaît pas — {_liste_des_inconnus(inconnus)}. Rien ne dit s'ils "
                "sont habités : à vérifier sur place, la légende disant qu'aucune "
                "habitation n'est si proche."
            )
        return None
    distance, habitation, sans_contour_cadastral = habitations[0]
    if cadastre is not None and sans_contour_cadastral:
        rapport.append(
            f"Habitation la plus proche, à {_metres(distance, 0)} : aucun bâtiment du "
            "cadastre ne la recouvre, la cote vise son contour de la BD TOPO."
        )
    p_c, p_h = nearest_points(trace, habitation)
    plus_proches = sorted(
        d for d in (
            a_coter(g)[0]
            for g, proprietes in batiments
            if (proprietes or {}).get("usage_1") == USAGE_INDIFFERENCIE
        )
        if d < distance
    )
    if plus_proches:
        rapport.append(
            f"Habitation la plus proche, à {_metres(distance, 0)} : "
            f"{len(plus_proches)} bâtiment(s) d'usage indifférencié plus proche(s), "
            f"le premier à {_metres(plus_proches[0], 0)}. La BD TOPO ne dit pas "
            "s'ils sont habités : la cote reste sur l'habitation."
        )
    inconnus = _inconnus_de_la_bd_topo(trace, batiments, cadastre or [], distance, parcelles)
    if inconnus:
        rapport.append(
            f"Habitation la plus proche, à {_metres(distance, 0)} : {len(inconnus)} "
            "bâtiment(s) du cadastre plus proche(s), que la BD TOPO ne connaît pas — "
            f"{_liste_des_inconnus(inconnus)}. Rien ne dit s'ils sont habités : à "
            "vérifier sur place ; la cote reste sur l'habitation que donne la BD TOPO."
        )
    return CoteAPoser(
        famille="C4", depart=(p_c.x, p_c.y), arrivee=(p_h.x, p_h.y),
        texte=f"{_metres(distance, 0)} (habitation la plus proche)", valeur_m=distance,
    )


# ---------------------------------------------------------------------------
# C2 et C8 — les voies publiques
# ---------------------------------------------------------------------------

#: Rayon de recherche des voies autour de la clôture (D5) : c'est la requête
#: BD TOPO qui le porte ; les voies reçues ici sont celles de ce rayon.
RAYON_VOIE_M = 300.0

#: Natures de `BDTOPO_V3:troncon_de_route` écartées d'office (D5) : on n'y
#: mesure pas la distance d'une construction à la voie.
NATURES_ECARTEES = ("Sentier", "Escalier", "Piste cyclable")

#: Le tracé sur lequel on juge si une voie est publique : cette distance de part
#: et d'autre de son point le plus proche de ce qu'on cote.
PORTEE_DOMAINE_PUBLIC_M = 50.0

#: Une voie est publique quand, sur ce tracé, la moitié au moins passe hors des
#: parcelles cadastrales, et moins de la moitié dans la clôture (C8, 07/11/2026).
PART_PUBLIQUE = 0.5

#: Le poste de livraison se cote jusqu'à la voie publique en deçà de ce seuil.
SEUIL_VOIE_POSTE_M = 30.0

#: Les postes de livraison, que C8 cote vers la voie.
POSTES_DE_LIVRAISON = ("pdl", "pdl_ptr")

#: Deux cotes parallèles plus proches que cela, sur le papier, se lisent comme
#: une seule ; à cet angle près, elles sont parallèles.
ECART_COTES_PARALLELES_MM = 4.0
ANGLE_PARALLELES_DEG = 15.0

#: L'axe de la voie se dessine sur cette longueur de part et d'autre du pied.
DEMI_AXE_M = 25.0

#: Pas d'échantillonnage du bord d'une construction, pour chercher les pieds de
#: perpendiculaire sur l'axe.
PAS_FACE_M = 0.25

#: Une perpendiculaire plus longue que le point le plus proche de cette
#: distance n'est plus la plus courte : la voie s'arrête, ou tourne, avant.
TOLERANCE_PERPENDICULAIRE_M = 1.0

#: Les axes au-delà de la plus courte distance plus cette marge, et les
#: constructions au-delà des six plus proches d'un axe, ne sont pas essayés.
PORTEE_AXES_M = 60.0
OBJETS_ESSAYES_PAR_AXE = 6

#: Deux bouts de cote plus proches que cela sont le même bout.
MEME_POINT_M = 0.5


@dataclass(frozen=True)
class VoieClassee:
    """Un tronçon BD TOPO, et ce qu'en dit le cadastre près de ce qu'on cote.

    Les deux parts sont prises sur le tracé du tronçon à moins de 50 m de son
    point le plus proche de ce qu'on cote.
    """

    geometrie: LineString
    proprietes: dict
    distance_m: float
    part_dans_cloture: float
    part_hors_parcelles: float

    @property
    def publique(self) -> bool:
        return (
            self.part_dans_cloture < PART_PUBLIQUE
            and self.part_hors_parcelles >= PART_PUBLIQUE
        )

    @property
    def nature(self) -> str:
        return str(self.proprietes.get("nature") or "voie")

    @property
    def pourquoi_pas_publique(self) -> str:
        if self.part_dans_cloture >= PART_PUBLIQUE:
            return "dans la clôture"
        return "sur des parcelles cadastrées"


@dataclass(frozen=True)
class CoteVersVoie:
    """Une cote vers une voie publique (C2, C8), et l'axe qu'elle touche.

    `genre` vaut « axe » quand la cote est perpendiculaire à l'axe, et
    « extrémité » quand la voie s'arrête avant le site : aucune perpendiculaire
    n'existe alors, et la cote va au bout de la voie. `axe` est le tracé à
    dessiner, 25 m de part et d'autre du pied.

    `confondue_avec` : la cote C2 que cette C8 répète, quand C2 part déjà du
    poste vers la même voie. C'est la même cote ; elle suit la zone du poste
    (D7), et une planche ne la pose qu'une fois (10/11/2026).
    """

    cote: CoteAPoser
    genre: str
    axe: LineString
    voie: VoieClassee
    confondue_avec: CoteAPoser | None = None


def classer_les_voies(troncons, pres_de, cadastre, enclos) -> list:
    """Les tronçons BD TOPO, publics ou non, triés du plus proche au plus loin.

    `troncons` : des couples (géométrie, propriétés BD TOPO). La BD TOPO ne dit
    pas à qui appartient une voie, le cadastre si : le domaine public n'est pas
    cadastré. `prive` ne suffit pas : il vaut faux sur les deux chemins de
    Saint-Cyr qui passent sur des parcelles (07/11/2026). Et la BD TOPO porte
    aussi les chemins du site : à Saint-Cyr, la « voie » la plus proche du
    PDL/PTR est un chemin à 89 % dans la clôture, à 5,2 m. D'où les deux parts,
    hors des parcelles et dans la clôture, mesurées près de `pres_de`.
    """
    from shapely import force_2d

    classees = []
    for geometrie, proprietes in troncons:
        proprietes = dict(proprietes or {})
        if proprietes.get("nature") in NATURES_ECARTEES:
            continue
        geometrie = force_2d(geometrie)
        if geometrie.is_empty or geometrie.length == 0:
            continue
        p_objet, p_voie = nearest_points(pres_de, geometrie)
        pres = geometrie.intersection(p_voie.buffer(PORTEE_DOMAINE_PUBLIC_M))
        if pres.is_empty or pres.length == 0:
            continue
        dans = pres.intersection(enclos).length / pres.length if enclos is not None else 0.0
        hors = pres.difference(cadastre).length / pres.length
        classees.append(VoieClassee(
            geometrie=geometrie, proprietes=proprietes,
            distance_m=p_objet.distance(p_voie),
            part_dans_cloture=dans, part_hors_parcelles=hors,
        ))
    return sorted(classees, key=lambda v: v.distance_m)


def _peut_juger_le_domaine_public(cadastre, enclos, quoi: str, rapport: list) -> bool:
    """Le parcellaire est-il là pour dire quelles voies sont publiques ?

    Sans lui, toute voie passerait pour publique : la cote ne se pose pas, et le
    rapport le dit. Sans enclos, la part d'une voie dans la clôture ne se
    vérifie pas : la cote se pose, et le rapport le dit aussi.
    """
    if cadastre is None or cadastre.is_empty:
        rapport.append(
            f"{quoi} : pas de parcellaire autour des constructions, rien ne dit "
            "quelles voies sont publiques — pas de cote."
        )
        return False
    if enclos is None or enclos.is_empty:
        rapport.append(
            f"{quoi} : pas d'enclos de clôture, la part d'une voie dans la clôture "
            "n'est pas vérifiée."
        )
    return True


def _nom_de_voie(proprietes) -> str:
    """« de la D18 », « de l'A6 » : le numéro de la voie quand elle en a un, sa nature sinon."""
    numero = str(proprietes.get("cpx_numero") or "").strip()
    if numero:
        return f"de l'{numero}" if numero[0].upper() in "AEIOU" else f"de la {numero}"
    nature = str(proprietes.get("nature") or "voie").lower()
    if nature.startswith("route"):
        return "de la route"
    if nature == "chemin":
        return "du chemin"
    return f"de la voie ({nature})"


def _valeur_de_voie(distance: float) -> str:
    return _metres(distance, 0 if distance >= 100.0 else 1)


def _se_superposent(segment, autre, ecart_m: float) -> bool:
    """Deux cotes parallèles à moins de `ecart_m` : elles se liraient comme une seule."""
    (x0, y0), (x1, y1) = segment.coords[0], segment.coords[-1]
    (u0, v0), (u1, v1) = autre.coords[0], autre.coords[-1]
    a = math.atan2(y1 - y0, x1 - x0)
    b = math.atan2(v1 - v0, u1 - u0)
    ecart_angle = abs((a - b + math.pi / 2.0) % math.pi - math.pi / 2.0)
    return ecart_angle < math.radians(ANGLE_PARALLELES_DEG) and segment.distance(autre) < ecart_m


def _pieds_perpendiculaires(objet, axe) -> list:
    """(longueur, point du bord, pied sur l'axe), là où le pied tombe dans l'axe.

    Un pied qui tombe au bout de l'axe n'est pas perpendiculaire : c'est le point
    le plus proche d'une voie qui s'arrête là. Une boucle n'a pas de bout : son
    départ est un point de l'axe comme un autre. Un segment qui traverse l'objet
    part de la face qui ne regarde pas la voie.
    """
    resultats = []
    for polygone in polygones_de([objet]):
        bord = polygone.exterior
        nombre = max(8, int(bord.length / PAS_FACE_M))
        for k in range(nombre):
            point_du_bord = bord.interpolate(k * bord.length / nombre)
            abscisse = axe.project(point_du_bord)
            if not axe.is_closed and (
                abscisse <= DEPART_EXCLU_M or abscisse >= axe.length - DEPART_EXCLU_M
            ):
                continue
            pied = axe.interpolate(abscisse)
            segment = LineString([point_du_bord, pied])
            if segment.length < DEPART_EXCLU_M:
                continue
            if segment.intersection(polygone).length > DEPART_EXCLU_M:
                continue
            resultats.append((segment.length, point_du_bord, pied))
    return resultats


def _cote_perpendiculaire(objets, publiques, posees, ecart_m, rapport, famille, rangs):
    """La cote la plus courte des objets à l'axe d'une voie publique.

    Perpendiculaire à l'axe, et ses flèches le touchent (seconde relecture du
    08/11/2026). Elle part de la face de l'objet tournée vers la voie, et se
    décale le long de cette face pour ne se superposer à aucune des cotes
    `posees` : une voie qui longe le terrain est parallèle à sa limite, et sa
    cote partait du même point, dans la même direction, que la cote de la même
    construction à la limite. Le rapport dit la distance perdue — à
    Auzainvilliers, 11,6 m depuis la citerne incendie au lieu de 11,0 m à son
    angle.

    Les tronçons publics se fondent d'abord en un réseau : la BD TOPO coupe une
    route à chaque carrefour, et le bout d'un tronçon n'est pas le bout de la
    route. Une voie publique qui s'arrête vraiment avant le site n'a pas de
    perpendiculaire : la cote va à son extrémité, et le dit.
    """
    # `shapely.line_merge` et non `shapely.ops.linemerge`, qui lève sur une
    # ligne seule (shapely 2.1.2, relevé le 09/11/2026).
    from shapely import line_merge

    reseau = line_merge(unary_union([v.geometrie for v in publiques]))
    lignes = [g for g in getattr(reseau, "geoms", [reseau]) if g.geom_type == "LineString"]
    union = unary_union(objets)
    p_objet, p_reseau = nearest_points(union, reseau)
    d_min = p_objet.distance(p_reseau)

    # Chaque candidat garde l'objet dont il part et l'axe qu'il touche.
    candidats = []
    for rang_axe, axe in enumerate(lignes):
        if axe.distance(union) > d_min + PORTEE_AXES_M:
            continue
        proches = sorted(range(len(objets)), key=lambda k: objets[k].distance(axe))
        for rang_objet in proches[:OBJETS_ESSAYES_PAR_AXE]:
            candidats.extend(
                (longueur, depuis, pied, rang_objet, rang_axe)
                for longueur, depuis, pied in _pieds_perpendiculaires(objets[rang_objet], axe)
            )
    # Le couple le plus proche lui-même, quand il touche l'axe ailleurs qu'à un
    # bout de voie : le bord n'est échantillonné que tous les 25 cm, et l'angle
    # d'une construction face au virage d'une route n'en est pas un
    # échantillon — la cote valait 28,4 m pour 28,3 m (relevé le 09/11/2026).
    if not _cul_de_sac(p_reseau, lignes):
        candidats.append((
            d_min, p_objet, p_reseau,
            min(range(len(objets)), key=lambda k: objets[k].distance(p_objet)),
            min(range(len(lignes)), key=lambda k: lignes[k].distance(p_reseau)),
        ))
    candidats.sort(key=lambda c: c[0])

    if not candidats or candidats[0][0] > d_min + TOLERANCE_PERPENDICULAIRE_M:
        genre = "extrémité" if _cul_de_sac(p_reseau, lignes) else "axe"
        depart, pied, distance = p_objet, p_reseau, d_min
    else:
        genre = "axe"
        plus_courte = candidats[0]
        # « Le long de la face » : sur la même construction, vers le même axe.
        # Plus loin, la cote ne partirait plus de la construction la plus
        # proche — au 1:2 000, un BESS à 15 m de la D18 cédait sa cote à une
        # table à 54,5 m, et le rapport la disait décalée le long de la face
        # (relecture du 09/11/2026).
        sur_la_face = [
            c for c in candidats if c[3] == plus_courte[3] and c[4] == plus_courte[4]
        ]
        lignes_posees = [c.ligne for c in posees]
        retenu = next(
            (c for c in sur_la_face
             if not any(_se_superposent(LineString([c[1], c[2]]), l, ecart_m) for l in lignes_posees)),
            None,
        )
        if retenu is None:
            retenu = plus_courte
            rapport.append(
                f"Cote vers la voie publique ({_metres(retenu[0])}) superposée à une "
                "autre cote, faute de place sur la face de la construction."
            )
        elif retenu[0] > plus_courte[0] + DEPART_EXCLU_M:
            rapport.append(
                f"Cote vers la voie publique décalée le long de la face, "
                f"{_metres(retenu[0], 2)} au lieu de {_metres(plus_courte[0], 2)}, "
                f"pour ne pas se superposer à une autre cote à moins de "
                f"{nombre_fr(ECART_COTES_PARALLELES_MM, 0)} mm de papier."
            )
        distance, depart, pied = retenu[:3]

    voie = min(publiques, key=lambda v: v.geometrie.distance(pied))
    axe = _axe_a_dessiner(pied, voie, publiques, lignes)
    cote = CoteAPoser(
        famille=famille, depart=(depart.x, depart.y), arrivee=(pied.x, pied.y),
        texte=f"{_valeur_de_voie(distance)} ({genre} {_nom_de_voie(voie.proprietes)})",
        valeur_m=distance, ouvrages=tuple(rangs),
    )
    return CoteVersVoie(cote=cote, genre=genre, axe=axe, voie=voie)


def _cul_de_sac(point, lignes) -> bool:
    """Le point est-il un bout du réseau public, où la voie s'arrête vraiment ?

    Un bout de ligne qu'une autre ligne touche est un carrefour, et le départ
    d'une boucle n'est le bout de rien.
    """
    touchees = [ligne for ligne in lignes if ligne.distance(point) < DEPART_EXCLU_M]
    if len(touchees) != 1 or touchees[0].is_closed:
        return False
    ligne = touchees[0]
    return any(point.distance(Point(ligne.coords[k])) < DEPART_EXCLU_M for k in (0, -1))


def _axe_a_dessiner(pied, voie, publiques, lignes):
    """L'axe de la voie, sur 25 m de part et d'autre du pied, le long de la voie.

    Une voie numérotée se suit sur tous ses tronçons publics : la BD TOPO coupe
    la D18 à chaque chemin qui la croise, et l'axe s'arrêtait au premier, quand
    un disque autour du pied aurait aussi pris le chemin. Une voie sans numéro
    se lit sur la ligne fondue qui porte le pied. Une boucle s'y prend des deux
    côtés de son départ.
    """
    from shapely import line_merge

    numero = voie.proprietes.get("cpx_numero")
    if numero:
        meme_voie = line_merge(unary_union([
            v.geometrie for v in publiques if v.proprietes.get("cpx_numero") == numero
        ]))
        parties = [g for g in getattr(meme_voie, "geoms", [meme_voie]) if g.geom_type == "LineString"]
    else:
        parties = lignes
    porteuse = min(parties or lignes, key=lambda ligne: ligne.distance(pied))
    return _autour_de(porteuse, porteuse.project(pied))


def _autour_de(ligne, abscisse: float):
    """Le tracé de `ligne` à moins de `DEMI_AXE_M` de l'abscisse, le long d'elle."""
    from shapely import line_merge
    from shapely.ops import substring

    debut, fin, longueur = abscisse - DEMI_AXE_M, abscisse + DEMI_AXE_M, ligne.length
    if not ligne.is_closed:
        return substring(ligne, max(0.0, debut), min(longueur, fin))
    if longueur <= 2.0 * DEMI_AXE_M:
        return ligne
    if debut < 0.0:
        morceaux = [substring(ligne, longueur + debut, longueur), substring(ligne, 0.0, fin)]
    elif fin > longueur:
        morceaux = [substring(ligne, debut, longueur), substring(ligne, 0.0, fin - longueur)]
    else:
        return substring(ligne, debut, fin)
    return line_merge(unary_union(morceaux))


def cote_vers_la_voie_publique(
    tables, ouvrages, troncons, cadastre, enclos, posees, denominateur: int, rapport: list
):
    """La construction la plus proche → l'axe de la voie publique la plus proche (C2).

    Saint-Cyr demande les distances des constructions, panneaux compris, « par
    rapport aux voies et emprises publiques » (08/11/2026). Une cote, à toute
    distance, depuis la construction la plus proche — table ou ouvrage
    permanent. Publique au sens de `classer_les_voies`. Hors du cadre de la
    planche, c'est la pose qui l'arrête au bord, et le dit.

    `posees` : les cotes que celle-ci ne doit pas recouvrir ; `denominateur` :
    l'échelle de la planche, qui donne aux 4 mm de papier leur longueur.
    """
    constructions = polygones_de(tables) + [o.geometrie for o in ouvrages]
    if not constructions:
        return None
    if not _peut_juger_le_domaine_public(cadastre, enclos, "Cote vers la voie publique", rapport):
        return None
    voies = classer_les_voies(troncons, unary_union(constructions), cadastre, enclos)
    publiques = [v for v in voies if v.publique]
    if not publiques:
        ecartees = " ; ".join(
            f"{v.nature} à {_metres(v.distance_m)}, {v.pourquoi_pas_publique}" for v in voies[:4]
        )
        rapport.append(
            "Cote vers la voie publique : aucune voie publique dans le rayon de "
            f"recherche, {_metres(RAYON_VOIE_M, 0)} autour de la clôture"
            + (f" (écartées : {ecartees})" if ecartees else "")
            + " — pas de cote."
        )
        return None
    ecart_m = ECART_COTES_PARALLELES_MM * denominateur / 1000.0
    return _cote_perpendiculaire(constructions, publiques, posees, ecart_m, rapport, "C2", ())


def cotes_poste_de_livraison(
    ouvrages, troncons, cadastre, enclos, posees, denominateur: int, c2, rapport: list
) -> list:
    """Chaque poste de livraison → l'axe de la voie publique la plus proche, en deçà de 30 m (C8).

    Demandé par la relecture de Saint-Cyr, qui notait la limite de son propre
    cas : « on n'a pas cette route au cadastre » (07/11/2026). Mesuré comme C2,
    perpendiculairement à l'axe, sans se superposer à la cote du poste à la
    limite. Les voies plus proches et écartées se disent, avec leur raison.

    Quand la cote vers la voie publique, `c2`, part déjà de ce poste vers la
    même voie, C8 est cette cote-là, rendue avec le rang du poste : elle suit
    sa zone sur la planche de détail, quand la zone part (D7). À Sarnois, la
    DP 2 ne la portait qu'à 1,5 mm de papier, et la DP 2 bis ne la reprenait
    pas (chef de projet, 10/11/2026). Sur une même planche, elle ne se pose
    qu'une fois : c'est `dp2_plan_masse` qui choisit laquelle.
    """
    ecart_m = ECART_COTES_PARALLELES_MM * denominateur / 1000.0
    resultats = []
    postes = [(rang, o) for rang, o in enumerate(ouvrages) if o.categorie in POSTES_DE_LIVRAISON]
    if not postes:
        return []
    if not _peut_juger_le_domaine_public(cadastre, enclos, "Poste de livraison", rapport):
        return []
    for rang, poste in postes:
        voies = classer_les_voies(troncons, poste.geometrie, cadastre, enclos)
        publiques = [v for v in voies if v.publique]
        plus_proches = [
            v for v in voies
            if not v.publique and (not publiques or v.distance_m < publiques[0].distance_m)
        ]
        ecartees = " ; ".join(
            f"{v.nature} à {_metres(v.distance_m)}, {v.pourquoi_pas_publique}"
            for v in plus_proches[:4]
        )
        debut = f"Poste de livraison : « {poste.categorie} »"
        if not publiques or publiques[0].distance_m >= SEUIL_VOIE_POSTE_M:
            loin = (
                f"la plus proche à {_valeur_de_voie(publiques[0].distance_m)} "
                f"({publiques[0].nature})" if publiques
                else "aucune dans le rayon de recherche"
            )
            rapport.append(
                f"{debut} non coté — aucune voie publique à moins de "
                f"{_metres(SEUIL_VOIE_POSTE_M, 0)}, {loin}"
                + (f" ; écartées : {ecartees}" if ecartees else "") + "."
            )
            continue
        if (
            c2 is not None
            and Point(c2.cote.depart).distance(poste.geometrie) < MEME_POINT_M
            and publiques[0].geometrie.distance(Point(c2.cote.arrivee)) < MEME_POINT_M
        ):
            rapport.append(
                f"{debut} : sa cote vers la voie publique est confondue avec celle de "
                "la construction la plus proche, qui part déjà de lui — posée une fois "
                "sur la DP 2, et reprise sur la planche de détail de sa zone si elle part."
            )
            resultats.append(CoteVersVoie(
                cote=replace(c2.cote, famille="C8", ouvrages=(rang,)),
                genre=c2.genre, axe=c2.axe, voie=c2.voie, confondue_avec=c2.cote,
            ))
            continue
        resultat = _cote_perpendiculaire(
            [poste.geometrie], publiques, posees, ecart_m, rapport, "C8", (rang,)
        )
        rapport.append(
            f"{debut} à {_valeur_de_voie(resultat.cote.valeur_m)} de l'"
            f"{resultat.genre} {_nom_de_voie(resultat.voie.proprietes)}"
            + (f" ; plus proches mais écartées : {ecartees}" if ecartees else "") + "."
        )
        resultats.append(resultat)
    return resultats


# ---------------------------------------------------------------------------
# D12 — les trois dimensions, en légende
# ---------------------------------------------------------------------------


def _court(valeur: float) -> str:
    """Un nombre de légende, sans zéro inutile : 12 ; 17,5 ; 7,95."""
    return nombre_fr(valeur, 2).rstrip("0").rstrip(",")


def dimensions_en_legende(contrat, ouvrages, table, rapport: list) -> dict:
    """Ce que chaque entrée de légende ajoute à son intitulé : emprise et hauteur.

    Auzainvilliers demande un plan « coté dans les trois dimensions » : c'est
    l'article R. 431-36 b) du code de l'urbanisme, et la troisième dimension est
    la hauteur. Elle n'est pas cotée sur le plan, où elle chargerait des zones
    déjà serrées : chaque construction la porte dans son entrée de légende, avec
    son emprise (08 et 09/11/2026). Rend `{catégorie: « (12 × 3 m, h 3 m) »}` :

    - les ouvrages permanents, aux longueur, largeur et hauteur du catalogue —
      celles que dessinent les élévations de la DP 4 —, la variante d'une
      famille qui en a plusieurs se choisissant sur la surface du corps. Deux
      variantes d'une même famille se disent au rapport : la légende n'a qu'une
      entrée par famille, et elle ne choisit pas ;
    - les tables, à la hauteur maximale de la coupe, `point_haut_max_m` — le
      maximum déclaré au tableau bilan, que la notice annonce —, et à la hauteur
      dessinée à défaut ;
    - la clôture et le portail, aux hauteurs que leurs élévations de la DP 4
      cotent. Le contrat n'en porte aucune : ce sont des constantes UNITe, que
      la légende du plan du bureau d'études écrit aussi pour la clôture
      (« clôture à créer (2m) », Saint-Cyr), et non une substitution.

    Le complément s'ajoute à l'intitulé, quel qu'il soit : un intitulé que le
    chef de projet a renommé garde ses dimensions.
    """
    from ..erreurs import ErreurDP
    from . import standards

    dimensions = {}
    for categorie in CATEGORIES_OUVRAGES:
        corps = [c for o in ouvrages if o.categorie == categorie for c in o.corps]
        if not corps:
            continue
        variantes, sans_cote = {}, []
        for un_corps in corps:
            try:
                cote = contrat.cote_de_categorie(categorie, surface_m2=un_corps.area)
            except ErreurDP as erreur:
                sans_cote.append(str(erreur))
                continue
            variantes[cote.ouvrage] = cote
        debut = f"Légende : « {categorie} »"
        if sans_cote:
            rapport.append(
                f"{debut}, {len(sans_cote)} ouvrage(s) sans cote au catalogue — "
                f"{sans_cote[0]}"
            )
        if len(variantes) > 1:
            rapport.append(
                f"{debut} en {len(variantes)} variantes au plan "
                f"({', '.join(sorted(variantes))}) : la légende n'a qu'une entrée par "
                "famille, elle ne porte pas de dimensions."
            )
            continue
        if not variantes:
            continue
        (cote,) = variantes.values()
        if not cote.a_hauteur:
            rapport.append(
                f"{debut} sans hauteur au catalogue (« {cote.dimensions} ») : pas de "
                "dimensions en légende."
            )
            continue
        grand, petit = sorted((cote.longueur_m, cote.largeur_m), reverse=True)
        dimensions[categorie] = (
            f"({_court(grand)} × {_court(petit)} m, h {_court(cote.hauteur_m)} m)"
        )
    if table is not None:
        haut = table.point_haut_max_m if table.point_haut_max_m is not None else table.point_haut_m
        dimensions["tables_pv"] = f"(hauteur maximale {_court(haut)} m)"
    dimensions["cloture"] = f"(h {_court(standards.HAUTEUR_CLOTURE_M)} m)"
    dimensions["portail"] = f"(h {_court(standards.HAUTEUR_PORTAIL_M)} m)"
    return dimensions
