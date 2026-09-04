"""Trame des modules à l'intérieur des tables photovoltaïques.

Le plan de masse du dossier de référence ne montre pas des rectangles pleins :
chaque table y porte la trame de ses modules, et c'est ce qui la fait lire comme
un panneau plutôt que comme une dalle. Relevé sur le plan de masse de Massay du
17/04/2025, au 1/500.

Le plan du bureau d'études, lui, **ne descend pas au module** : son DXF ne porte
que le contour groupé des rangées. La trame se reconstruit donc depuis le
tableau bilan — nombre de modules sur le rampant, et largeur d'un module déduite
de sa surface unitaire.

Rien n'est deviné : si la trame reconstruite ne retombe pas sur un nombre entier
de modules plausible, elle n'est pas dessinée et le rapport le dit. Une table
divisée en dix-sept modules là où il y en a treize se dessine parfaitement et ne
se remarque pas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString

from ..planche import Style, nombre_fr

#: Largeurs de module admises, en mètres. Un module photovoltaïque courant
#: mesure de 1,0 à 1,4 m de large ; un G12R fait 1,134 m. La fourchette ne
#: valide pas un module, elle refuse un calcul qui a dérapé.
LARGEUR_MODULE_MIN_M = 0.90
LARGEUR_MODULE_MAX_M = 1.45

#: Écart admis entre la largeur de table mesurée et un nombre entier de
#: modules. 12 % : les contours du bureau d'études débordent légèrement des
#: modules, cadre et jeu de pose compris.
TOLERANCE_TRAME = 0.12

#: En deçà de cette largeur sur le papier, la trame n'est plus lisible et
#: charge le dessin sans rien apprendre : une table de 26 modules au 1/2 000
#: donnerait des cases de 0,6 mm.
LARGEUR_MODULE_MINIMALE_MM = 0.5


@dataclass(frozen=True)
class Trame:
    """De quoi diviser une table en modules."""

    largeur_module_m: float
    nb_rampant: int
    #: Provenance de la largeur de module, pour le rapport.
    origine: str
    #: Formats de table déclarés au tableau bilan, en modules par rangée.
    formats: tuple = ()


def trame_du_projet(contrat, tables=None, rampant_declare_m=None):
    """Trame des modules du projet, ou None avec la raison de son absence.

    Trois sources, dans cet ordre :

    1. **Les deux côtés mesurés du module**, quand le contrat les porte. Seul
       l'import HelioScope les a, parce qu'il descend au module.
    2. **La largeur des tables dessinées.** Le côté court d'une table est la
       projection au sol du rampant : divisée par le cosinus de l'inclinaison
       elle rend le rampant, et le rampant divisé par le nombre de modules
       qu'il porte rend la longueur d'un module. Sa largeur suit de la surface
       unitaire. C'est la source la plus sûre pour un dossier du bureau
       d'études : elle vient du plan lui-même.
    3. **Le rampant déduit des deux hauteurs déclarées**, en dernier recours.

    Le passage par le plan n'est pas un raffinement. Mesuré sur Saint-Cyr le
    04/09/2026 : les hauteurs déclarées (2,50 et 4,00 m) donnent un rampant de
    5,80 m et un module de 0,93 m de large, tandis que la largeur des tables
    dessinées (4,62 m) donne 4,78 m de rampant et un module de 2,39 x 1,13 m —
    un G12R, le module que le tableau bilan nomme par ailleurs. Ce sont les
    hauteurs déclarées qui sont des bornes d'enveloppe, pas la géométrie.
    """
    modules = contrat.modules or {}
    structures = contrat.structures or {}
    nb_rampant = _nb_rampant(structures)

    largeur = modules.get("largeur_m")
    if largeur:
        return (
            Trame(float(largeur), nb_rampant or 1, "mesurée sur le calepinage",
                  _formats(structures)),
            None,
        )

    surface = modules.get("surface_unitaire_m2")
    if not surface or not nb_rampant:
        return None, (
            "Trame des modules non dessinée : le contrat ne donne ni les côtés "
            "du module, ni sa surface unitaire avec le nombre de modules sur "
            "le rampant."
        )

    rampant, origine = _rampant_utile(
        structures, tables, rampant_declare_m
    )
    if not rampant:
        return None, (
            "Trame des modules non dessinée : impossible d'établir la longueur "
            "du rampant, ni sur les tables dessinées ni sur les hauteurs "
            "déclarées."
        )

    longueur_module = rampant / nb_rampant
    if longueur_module <= 0:
        return None, "Trame des modules non dessinée : longueur de module nulle."
    largeur = surface / longueur_module
    if not LARGEUR_MODULE_MIN_M <= largeur <= LARGEUR_MODULE_MAX_M:
        return None, (
            f"Trame des modules non dessinée : la largeur déduite vaut "
            f"{nombre_fr(largeur)} m, hors de la fourchette "
            f"{nombre_fr(LARGEUR_MODULE_MIN_M, 2)}–"
            f"{nombre_fr(LARGEUR_MODULE_MAX_M, 2)} m d'un module courant. Elle "
            f"vient de la surface unitaire ({nombre_fr(surface)} m²) divisée "
            f"par la longueur d'un module ({nombre_fr(longueur_module)} m), "
            f"elle-même déduite du rampant {origine}."
        )
    return (
        Trame(largeur, nb_rampant, f"déduite du rampant {origine}",
              _formats(structures)),
        None,
    )


def _rampant_utile(structures: dict, tables, rampant_declare_m):
    """Longueur du rampant, mesurée sur les tables si possible."""
    import statistics

    inclinaison = structures.get("inclinaison_deg")
    if tables and inclinaison:
        largeurs = []
        for geometrie in tables:
            repere = rectangle_oriente(geometrie)
            if repere is not None:
                largeurs.append(repere[4])
        if largeurs:
            cosinus = math.cos(math.radians(float(inclinaison)))
            if cosinus > 0.05:
                return (
                    statistics.median(largeurs) / cosinus,
                    "mesuré sur la largeur des tables du plan",
                )
    if rampant_declare_m:
        return rampant_declare_m, "déduit des deux hauteurs déclarées"
    return None, ""


def controler_trame(structures: dict, comptes) -> str | None:
    """Recoupe les modules comptés par table avec ceux du tableau bilan.

    `nb_modules_longueur` donne les formats de table du projet : y retrouver
    les nombres obtenus est ce qui prouve que la trame tombe juste. Sur
    Saint-Cyr, 13 et 26 modules, exactement les deux valeurs déclarées.
    """
    attendus = structures.get("nb_modules_longueur")
    if not attendus or not comptes:
        return None
    if isinstance(attendus, (int, float)):
        attendus = [attendus]
    attendus = {int(v) for v in attendus}
    obtenus = set(comptes)
    inconnus = sorted(obtenus - attendus)
    if inconnus:
        return (
            f"Trame des modules : {', '.join(str(n) for n in inconnus)} "
            f"module(s) par rangée obtenus, alors que le tableau bilan déclare "
            f"les formats {', '.join(str(n) for n in sorted(attendus))}. La "
            "trame est dessinée telle qu'elle a été mesurée."
        )
    return None


def _formats(structures: dict) -> tuple:
    """Formats de table déclarés, en nombre de modules par rangée."""
    valeurs = structures.get("nb_modules_longueur")
    if valeurs is None:
        return ()
    if isinstance(valeurs, (int, float)):
        valeurs = [valeurs]
    formats = []
    for valeur in valeurs:
        try:
            nombre = int(valeur)
        except (TypeError, ValueError):
            continue
        if nombre > 0:
            formats.append(nombre)
    return tuple(sorted(set(formats)))


def _nb_rampant(structures: dict) -> int:
    valeur = structures.get("nb_modules_rampant")
    try:
        nombre = int(valeur)
    except (TypeError, ValueError):
        return 0
    return nombre if nombre > 0 else 0


def rectangle_oriente(geometrie):
    """Rectangle minimal d'une table, avec ses deux directions et ses côtés.

    Rend (origine, direction_longueur, direction_largeur, longueur, largeur) —
    de quoi poser une trame régulière sur une table quelconque sans supposer
    qu'elle est parallèle aux axes.
    """
    rectangle = geometrie.minimum_rotated_rectangle
    if rectangle.geom_type != "Polygon":
        return None
    coins = list(rectangle.exterior.coords)[:4]
    if len(coins) < 4:
        return None

    cotes = [
        (
            coins[i],
            (coins[(i + 1) % 4][0] - coins[i][0], coins[(i + 1) % 4][1] - coins[i][1]),
        )
        for i in range(4)
    ]
    longueurs = [math.hypot(v[0], v[1]) for _, v in cotes]
    index = max(range(4), key=lambda i: longueurs[i])
    origine, vecteur_long = cotes[index]
    longueur = longueurs[index]
    _, vecteur_larg = cotes[(index + 1) % 4]
    largeur = longueurs[(index + 1) % 4]
    if longueur <= 0 or largeur <= 0:
        return None
    return (
        origine,
        (vecteur_long[0] / longueur, vecteur_long[1] / longueur),
        (vecteur_larg[0] / largeur, vecteur_larg[1] / largeur),
        longueur,
        largeur,
    )


def diviser_table(geometrie, trame: Trame):
    """(lignes, nb modules) d'une table, ou None si le compte ne tombe pas juste.

    Le nombre de modules dans la longueur est **arrondi**, puis vérifié : si la
    largeur de module qui en résulte s'écarte trop de celle du projet, la table
    n'est pas conforme à la trame et on ne la divise pas.
    """
    repere = rectangle_oriente(geometrie)
    if repere is None:
        return None
    origine, direction_long, direction_larg, longueur, largeur = repere

    # Ce sont les formats du tableau bilan qui commandent, pas l'arrondi : le
    # contour d'une rangée déborde de ses modules du cadre et du jeu de pose,
    # et une table de 30,0 m divisée par un module de 1,129 m tombait sur 27
    # modules là où le tableau en déclare 26. On retient donc le format déclaré
    # dont la largeur de module implicite s'approche le plus de la référence.
    if trame.formats:
        nombre = min(
            trame.formats,
            key=lambda n: abs(longueur / n - trame.largeur_module_m),
        )
    else:
        nombre = round(longueur / trame.largeur_module_m)
    if nombre < 2:
        return None
    largeur_obtenue = longueur / nombre
    ecart = abs(largeur_obtenue - trame.largeur_module_m) / trame.largeur_module_m
    if ecart > TOLERANCE_TRAME:
        return None

    lignes = []
    for index in range(1, nombre):
        distance = index * largeur_obtenue
        depart = (
            origine[0] + direction_long[0] * distance,
            origine[1] + direction_long[1] * distance,
        )
        arrivee = (
            depart[0] + direction_larg[0] * largeur,
            depart[1] + direction_larg[1] * largeur,
        )
        lignes.append(LineString([depart, arrivee]))

    # Les modules du rampant : des traits dans l'autre sens, un de moins que
    # le nombre de modules empilés sur la pente.
    for index in range(1, max(trame.nb_rampant, 1)):
        distance = index * largeur / trame.nb_rampant
        depart = (
            origine[0] + direction_larg[0] * distance,
            origine[1] + direction_larg[1] * distance,
        )
        arrivee = (
            depart[0] + direction_long[0] * longueur,
            depart[1] + direction_long[1] * longueur,
        )
        lignes.append(LineString([depart, arrivee]))
    return lignes, nombre


def style_trame(style_table: Style) -> Style:
    """Filet de la trame : le trait de la table, en plus fin."""
    # 0,08 mm : le filet le plus fin qui survive à une impression laser. En
    # dessous, la trame disparaît à l'épreuve alors qu'elle se voit à l'écran.
    return Style(
        trait=style_table.trait,
        epaisseur_mm=0.08,
        remplissage="none",
    )


def tracer_trame(planche, geometries, trame: Trame, style_table: Style,
                 mm_par_metre: float, fenetre=None):
    """Trace la trame sur des tables. Rend (nb tramées, modules par rangée).

    En deçà d'un millimètre de module sur le papier, la trame n'est pas tracée :
    elle noircirait la table sans rien montrer.

    `fenetre` recoupe les traits : sur un plan de repérage, le moteur ne découpe
    qu'à la zone de dessin entière, et la trame d'une table à cheval sur le bord
    traversait sinon le panneau des ouvrages.
    """
    if trame.largeur_module_m * mm_par_metre < LARGEUR_MODULE_MINIMALE_MM:
        return 0, []
    style = style_trame(style_table)
    tramees = 0
    comptes = []
    for geometrie in geometries:
        division = diviser_table(geometrie, trame)
        if not division:
            continue
        lignes, nombre = division
        for ligne in lignes:
            if fenetre is not None:
                ligne = ligne.intersection(fenetre)
                if ligne.is_empty:
                    continue
            planche.ajouter_geometrie(ligne, style)
        comptes.append(nombre)
        tramees += 1
    return tramees, comptes
