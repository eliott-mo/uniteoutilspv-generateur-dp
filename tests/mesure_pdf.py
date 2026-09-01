"""Mesure de segments tracés dans un PDF produit, en points PostScript.

Ce module lit le flux de contenu de la page et suit la matrice de
transformation courante (opérateurs q / Q / cm), afin que les mesures portent
sur le fichier réellement produit et non sur des valeurs intermédiaires du
générateur.
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
