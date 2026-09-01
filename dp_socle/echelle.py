"""Échelle et transformation Lambert 93 vers coordonnées SVG.

Ce module est le SEUL endroit du projet où l'on passe des mètres terrain aux
millimètres papier. Les fonctions de dessin utilisent une instance de
`TransformationL93` et ne refont jamais ce calcul localement : c'est ce qui
garantit qu'une planche imprimée en A3 sans ajustement à la page est à l'échelle
annoncée dans le cartouche.

Convention du document SVG : 1 unité utilisateur = 1 millimètre papier.
Le gabarit déclare width="420mm" height="297mm" viewBox="0 0 420 297", ce qui
donne un PDF de 420 x 297 mm exactement.
"""

from __future__ import annotations

from .erreurs import ErreurEchelle

#: Échelles normalisées proposées pour les planches à échelle adaptative.
ECHELLES_NORMALISEES = (200, 500, 1000, 2000, 5000, 10000)


def mm_vers_metres(longueur_mm: float, denominateur: int) -> float:
    """Longueur terrain, en mètres, d'un segment de `longueur_mm` sur le papier.

    À l'échelle 1:D, 1 mm papier représente D mm terrain, soit D/1000 mètres.
    """
    _valider_denominateur(denominateur)
    return longueur_mm * denominateur / 1000.0


def metres_vers_mm(longueur_m: float, denominateur: int) -> float:
    """Longueur papier, en millimètres, d'un segment de `longueur_m` au sol."""
    _valider_denominateur(denominateur)
    return longueur_m * 1000.0 / denominateur


def _valider_denominateur(denominateur) -> None:
    if not isinstance(denominateur, (int, float)) or denominateur <= 0:
        raise ErreurEchelle(
            f"Dénominateur d'échelle invalide : {denominateur!r}. "
            "Attendu un nombre strictement positif, par exemple 10000 pour 1:10 000."
        )


def formater_echelle(denominateur: int) -> str:
    """Rend « 1:10 000 » avec une espace insécable comme séparateur de milliers."""
    _valider_denominateur(denominateur)
    return "1:" + f"{int(denominateur):,}".replace(",", "\u00a0")


def echelle_adaptative(
    largeur_m: float,
    hauteur_m: float,
    zone_mm: tuple[float, float, float, float],
    marge: float = 0.20,
    valeurs=ECHELLES_NORMALISEES,
) -> int:
    """Plus grande échelle normalisée où l'emprise + marge tient dans la zone.

    « Plus grande échelle » = plus petit dénominateur. `marge` = 0.20 signifie
    que l'on veut loger l'emprise élargie de 20 % dans chaque direction.

    Lève `ErreurEchelle` si aucune valeur ne convient : pas de repli silencieux
    sur une échelle hors liste.
    """
    if largeur_m <= 0 or hauteur_m <= 0:
        raise ErreurEchelle(
            f"Emprise dégénérée : {largeur_m} x {hauteur_m} m. "
            "Impossible de choisir une échelle."
        )
    _, _, zone_w_mm, zone_h_mm = zone_mm
    besoin_l = largeur_m * (1.0 + marge)
    besoin_h = hauteur_m * (1.0 + marge)
    for denominateur in sorted(valeurs):
        if (
            metres_vers_mm(besoin_l, denominateur) <= zone_w_mm
            and metres_vers_mm(besoin_h, denominateur) <= zone_h_mm
        ):
            return int(denominateur)
    raise ErreurEchelle(
        f"Emprise de {largeur_m:.0f} x {hauteur_m:.0f} m (+{marge:.0%} de marge) "
        f"trop grande pour la zone de dessin de {zone_w_mm:.1f} x {zone_h_mm:.1f} mm "
        f"aux échelles normalisées {sorted(valeurs)}."
    )


class TransformationL93:
    """Passage Lambert 93 (mètres) vers coordonnées SVG (millimètres papier).

    Unique et centralisée : construite une fois par planche à partir de la zone
    de dessin, du dénominateur d'échelle et du centre terrain visé.

    L'axe Y du SVG descend, l'axe Y du Lambert 93 monte : la transformation
    inclut le retournement. Les axes X et Y du Lambert 93 restent parallèles aux
    axes du papier, ce qui veut dire que le haut de la planche est le nord de la
    grille Lambert 93 — et non le nord géographique.
    """

    def __init__(
        self,
        zone_mm: tuple[float, float, float, float],
        denominateur: int,
        centre_l93: tuple[float, float],
    ):
        _valider_denominateur(denominateur)
        self.zone_mm = tuple(float(v) for v in zone_mm)
        self.denominateur = int(denominateur)
        self.centre_l93 = (float(centre_l93[0]), float(centre_l93[1]))

        x_mm, y_mm, w_mm, h_mm = self.zone_mm
        if w_mm <= 0 or h_mm <= 0:
            raise ErreurEchelle(f"Zone de dessin dégénérée : {self.zone_mm}.")

        #: millimètres papier par mètre terrain — facteur unique du module
        self.mm_par_metre = 1000.0 / self.denominateur

        largeur_m = mm_vers_metres(w_mm, self.denominateur)
        hauteur_m = mm_vers_metres(h_mm, self.denominateur)
        cx, cy = self.centre_l93
        #: emprise terrain couverte par la zone de dessin (minx, miny, maxx, maxy)
        self.emprise = (
            cx - largeur_m / 2.0,
            cy - hauteur_m / 2.0,
            cx + largeur_m / 2.0,
            cy + hauteur_m / 2.0,
        )
        self._origine_x = self.emprise[0]
        self._origine_y = self.emprise[3]  # coin haut-gauche du papier : maxy
        self._x_mm = x_mm
        self._y_mm = y_mm

    def point(self, x_l93: float, y_l93: float) -> tuple[float, float]:
        """Un point Lambert 93 vers ses coordonnées SVG en millimètres."""
        return (
            self._x_mm + (x_l93 - self._origine_x) * self.mm_par_metre,
            self._y_mm + (self._origine_y - y_l93) * self.mm_par_metre,
        )

    def points(self, coords) -> list[tuple[float, float]]:
        return [self.point(x, y) for x, y in coords]

    def longueur(self, longueur_m: float) -> float:
        """Une longueur terrain en millimètres papier."""
        return longueur_m * self.mm_par_metre

    def __repr__(self) -> str:  # pragma: no cover - confort de débogage
        return (
            f"TransformationL93(echelle={formater_echelle(self.denominateur)}, "
            f"emprise={tuple(round(v, 1) for v in self.emprise)})"
        )
