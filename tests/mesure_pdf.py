"""Mesure de segments tracés et de surfaces remplies dans un PDF produit.

Ce module lit le flux de contenu de la page et suit la matrice de
transformation courante (opérateurs q / Q / cm), afin que les mesures portent
sur le fichier réellement produit et non sur des valeurs intermédiaires du
générateur. Les coordonnées sont en points PostScript.
"""

from __future__ import annotations

import math

from pypdf import PdfReader

#: Opérateurs de tracé pris en charge.
_NOMBRE = set("0123456789+-.")


def _tokens(donnees: bytes):
    """Découpe grossièrement un flux de contenu en nombres et opérateurs."""
    texte = donnees.decode("latin-1")
    courant = []
    dans_chaine = 0
    for caractere in texte:
        if dans_chaine:
            if caractere == ")":
                dans_chaine -= 1
            elif caractere == "(":
                dans_chaine += 1
            continue
        if caractere == "(":
            dans_chaine = 1
            continue
        if caractere.isspace() or caractere in "[]<>/":
            if courant:
                yield "".join(courant)
                courant = []
            continue
        courant.append(caractere)
    if courant:
        yield "".join(courant)


def _appliquer(matrice, point):
    a, b, c, d, e, f = matrice
    x, y = point
    return (a * x + c * y + e, b * x + d * y + f)


def _multiplier(m1, m2):
    """m1 appliquée avant m2 (convention PDF : nouvelle CTM = m1 x CTM)."""
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (
        a1 * a2 + b1 * c2,
        a1 * b2 + b1 * d2,
        c1 * a2 + d1 * c2,
        c1 * b2 + d1 * d2,
        e1 * a2 + f1 * c2 + e2,
        e1 * b2 + f1 * d2 + f2,
    )


def segments(chemin, page: int = 0) -> list[tuple[tuple, tuple]]:
    """Tous les segments droits de la page, en points PostScript."""
    lecteur = PdfReader(str(chemin))
    contenu = lecteur.pages[page].get_contents()
    donnees = contenu.get_data() if contenu is not None else b""

    ctm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    pile: list[tuple] = []
    operandes: list[float] = []
    resultat: list[tuple[tuple, tuple]] = []
    courant = None
    depart = None

    for token in _tokens(donnees):
        if token and token[0] in _NOMBRE and token not in ("-", "+", "."):
            try:
                operandes.append(float(token))
                continue
            except ValueError:
                pass
        if token == "q":
            pile.append(ctm)
        elif token == "Q":
            if pile:
                ctm = pile.pop()
        elif token == "cm" and len(operandes) >= 6:
            ctm = _multiplier(tuple(operandes[-6:]), ctm)
        elif token == "m" and len(operandes) >= 2:
            courant = _appliquer(ctm, tuple(operandes[-2:]))
            depart = courant
        elif token == "l" and len(operandes) >= 2:
            suivant = _appliquer(ctm, tuple(operandes[-2:]))
            if courant is not None:
                resultat.append((courant, suivant))
            courant = suivant
        elif token == "h" and courant is not None and depart is not None:
            resultat.append((courant, depart))
            courant = depart
        elif token == "re" and len(operandes) >= 4:
            x, y, largeur, hauteur = operandes[-4:]
            coins = [
                _appliquer(ctm, (x, y)),
                _appliquer(ctm, (x + largeur, y)),
                _appliquer(ctm, (x + largeur, y + hauteur)),
                _appliquer(ctm, (x, y + hauteur)),
            ]
            for index in range(4):
                resultat.append((coins[index], coins[(index + 1) % 4]))
            courant = None
        if not token or token[0] not in _NOMBRE or token in ("-", "+", "."):
            operandes = []
    return resultat


def longueur(segment) -> float:
    (x1, y1), (x2, y2) = segment
    return math.hypot(x2 - x1, y2 - y1)


def segments_obliques(chemin, page: int = 0, tolerance: float = 1.0):
    """Segments ni horizontaux ni verticaux — donc ni cadre ni fond de page."""
    obliques = []
    for segment in segments(chemin, page):
        (x1, y1), (x2, y2) = segment
        if abs(x2 - x1) > tolerance and abs(y2 - y1) > tolerance:
            obliques.append(segment)
    return obliques


def format_page(chemin, page: int = 0) -> tuple[float, float]:
    boite = PdfReader(str(chemin)).pages[page].mediabox
    return (float(boite.width), float(boite.height))


#: Opérateurs qui remplissent le chemin courant, seul ou avec son trait.
_REMPLISSAGE = {"f", "F", "f*", "B", "B*", "b", "b*"}

#: Opérateurs qui terminent le chemin courant sans le remplir : un trait seul,
#: ou un chemin de découpe.
_SANS_REMPLISSAGE = {"S", "s", "n"}


def surfaces_remplies(chemin, page: int = 0) -> list[tuple]:
    """Les chemins remplis de la page, dans l'ordre du dessin, avec leur teinte.

    Rend une liste de `(teinte, anneaux)`. `teinte` est le triplet RVB du
    remplissage, de 0 à 1 et arrondi au millième — posé par `rg`, ou par `g`
    pour un gris —, ou `None` quand il ne se lit pas en RVB, sous un motif.
    `anneaux` sont les contours du chemin, en points PostScript dans le repère
    de la page, comme les segments de `segments`. Une courbe s'y réduit à son
    point d'arrivée : ce qu'on mesure ainsi, ce sont des ouvrages, qui sont des
    polygones.

    `q` et `Q` sauvent et rendent la teinte avec la matrice : elle fait partie
    de l'état graphique, comme pour le lecteur.
    """
    lecteur = PdfReader(str(chemin))
    contenu = lecteur.pages[page].get_contents()
    donnees = contenu.get_data() if contenu is not None else b""

    ctm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    teinte = (0.0, 0.0, 0.0)
    pile: list[tuple] = []
    operandes: list[float] = []
    anneaux: list[list[tuple]] = []
    resultat: list[tuple] = []

    for token in _tokens(donnees):
        if token and token[0] in _NOMBRE and token not in ("-", "+", "."):
            try:
                operandes.append(float(token))
                continue
            except ValueError:
                pass
        if token == "q":
            pile.append((ctm, teinte))
        elif token == "Q":
            if pile:
                ctm, teinte = pile.pop()
        elif token == "cm" and len(operandes) >= 6:
            ctm = _multiplier(tuple(operandes[-6:]), ctm)
        elif token == "rg" and len(operandes) >= 3:
            teinte = tuple(round(v, 3) for v in operandes[-3:])
        elif token == "g" and operandes:
            teinte = (round(operandes[-1], 3),) * 3
        elif token in ("sc", "scn"):
            teinte = (
                tuple(round(v, 3) for v in operandes[-3:])
                if len(operandes) >= 3
                else None
            )
        elif token == "m" and len(operandes) >= 2:
            anneaux.append([_appliquer(ctm, tuple(operandes[-2:]))])
        elif token in ("l", "c", "v", "y") and len(operandes) >= 2 and anneaux:
            anneaux[-1].append(_appliquer(ctm, tuple(operandes[-2:])))
        elif token == "re" and len(operandes) >= 4:
            x, y, largeur, hauteur = operandes[-4:]
            anneaux.append(
                [
                    _appliquer(ctm, (x, y)),
                    _appliquer(ctm, (x + largeur, y)),
                    _appliquer(ctm, (x + largeur, y + hauteur)),
                    _appliquer(ctm, (x, y + hauteur)),
                ]
            )
        elif token in _REMPLISSAGE:
            resultat.append((teinte, [a for a in anneaux if len(a) >= 3]))
            anneaux = []
        elif token in _SANS_REMPLISSAGE:
            anneaux = []
        if not token or token[0] not in _NOMBRE or token in ("-", "+", "."):
            operandes = []
    return resultat


def teinte_visible(surfaces, point) -> tuple | None:
    """La teinte que la page montre en `point`, ou `None` si rien n'y est rempli.

    C'est celle du dernier chemin rempli qui couvre le point : ce que l'œil
    lit. Un ouvrage peut être dessiné juste et ne pas se voir, recouvert par un
    aplat tracé après lui, sans qu'aucune valeur intermédiaire soit fausse. Un
    point est dans un chemin s'il est dans un nombre impair de ses anneaux — la
    règle pair-impair, qui rend les trous des surfaces percées.
    """
    from shapely.geometry import Point, Polygon

    cible = Point(point)
    visible = None
    for teinte, anneaux in surfaces:
        if sum(1 for anneau in anneaux if Polygon(anneau).covers(cible)) % 2:
            visible = teinte
    return visible
