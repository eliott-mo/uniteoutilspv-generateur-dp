"""Caler un export HelioScope sur l'ortho IGN, en y cherchant son image de fond.

Le lot 2 place le calepinage par la latitude que donne la résolution du fond
— celle du centre de l'image — et par une longitude pré-positionnée sur
l'emprise cadastrale, puis réglée à l'œil. Or l'image de fond HelioScope est
une photographie aérienne du site. Projetée avec le calage courant, elle se
cherche dans l'ortho IGN, et le décalage trouvé est l'erreur du calage.

Méthode mesurée le 23/09/2026 sur les cinq exports du dépôt, avant d'être
écrite ici : corrélation des magnitudes de gradient — les deux photographies
n'ont ni la même date ni la même radiométrie, mais les routes, les bâtiments
et les limites de culture sont aux mêmes endroits —, affinée au sous-pixel.
Sur Gannay, elle retrouve à 1 m près le calage obtenu indépendamment dans le
dépôt `photomontage` ; sur les quatre autres, le décalage nord-sud qu'elle
mesure est celui qu'annonce le centre de l'image, à 0,7 m près sur trois
d'entre eux et 4,1 m sur le dernier, dont la corrélation est la plus faible.

Ce qui n'est pas reconnu nettement n'est pas appliqué : le calage reste à
l'œil, et l'erreur dit pourquoi.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image
from shapely.geometry import Point

from .erreurs import ErreurCalage
from .helioscope import corriger_nord_sud, decaler_longitude, projeter

#: Marge de recherche autour du placement courant, en mètres. Le
#: pré-positionnement sur l'emprise laissait Bray à 22 m de sa place en
#: est-ouest (mesuré le 23/09/2026) ; au-delà de 200 m, c'est un autre endroit
#: que l'on calerait.
MARGE_RECHERCHE_M = 220.0

#: Pas de la grille de corrélation, en mètres : celui du fond HelioScope, sans
#: descendre sous 0,4 m. Le fond de Gannay est à 0,20 m/px ; l'ortho n'en dit
#: pas plus à cette finesse, pour quatre fois plus de calcul.
PAS_MINIMAL_M = 0.4

#: Seuils de confiance, mesurés le 23/09/2026 sur les cinq exports : pics de
#: corrélation de 0,21 à 0,52, chacun au moins 2,7 fois le plus haut pic situé
#: à plus de 30 m. En deçà, le fond ne se reconnaît pas dans l'ortho — autre
#: site, saison, chantier —, et le calage reste à l'œil.
PIC_MINIMAL = 0.15
RAPPORT_MINIMAL = 1.8
ECART_SECOND_PIC_M = 30.0

#: Lissage avant le calcul des gradients, en pixels de la grille : il efface
#: le bruit de compression des deux images sans émousser les contours.
SIGMA_LISSAGE_PX = 1.2


@dataclass(frozen=True)
class MesureOrtho:
    """Ce que la corrélation dit du calage courant."""

    #: Déplacement à appliquer pour que le fond tombe sur l'ortho, en mètres.
    decalage_est_m: float
    decalage_nord_m: float
    #: Corrélation au meilleur accord, et la plus haute à plus de 30 m de lui.
    pic: float
    second_pic: float
    pas_m: float

    @property
    def message(self) -> str:
        est_ouest = "l'est" if self.decalage_est_m >= 0 else "l'ouest"
        nord_sud = "le nord" if self.decalage_nord_m >= 0 else "le sud"
        return (
            f"Calé sur l'ortho : déplacé de {_fr(abs(self.decalage_est_m), '.1f')} m "
            f"vers {est_ouest} et de {_fr(abs(self.decalage_nord_m), '.1f')} m vers "
            f"{nord_sud}. Le fond HelioScope s'y reconnaît avec une corrélation de "
            f"{_fr(self.pic, '.2f')}, contre {_fr(self.second_pic, '.2f')} au mieux "
            "ailleurs."
        )


def _fr(valeur: float, forme: str) -> str:
    """Un nombre au format donné, à la française."""
    return format(valeur, forme).replace(".", ",")


# ---------------------------------------------------------------------------
# Corrélation
# ---------------------------------------------------------------------------


def _lisser(image: np.ndarray, sigma: float = SIGMA_LISSAGE_PX) -> np.ndarray:
    """Lissage gaussien séparable, bords prolongés."""
    rayon = max(1, int(3 * sigma + 0.5))
    abscisses = np.arange(-rayon, rayon + 1)
    noyau = np.exp(-0.5 * (abscisses / sigma) ** 2)
    noyau /= noyau.sum()
    etendue = np.pad(image, rayon, mode="edge")
    lignes = sum(
        poids * etendue[:, k : k + image.shape[1]] for k, poids in enumerate(noyau)
    )
    return sum(poids * lignes[k : k + image.shape[0], :] for k, poids in enumerate(noyau))


def gradient(image: np.ndarray) -> np.ndarray:
    """Magnitude du gradient d'une image lissée : ce qui se compare d'une photo à l'autre."""
    gy, gx = np.gradient(_lisser(np.asarray(image, dtype=float)))
    return np.hypot(gx, gy)


def correlation_normalisee(image: np.ndarray, gabarit: np.ndarray) -> np.ndarray:
    """Corrélation normalisée du gabarit sur l'image, pour chaque position entière.

    La carte a une valeur par coin haut-gauche possible du gabarit dans
    l'image, de −1 à 1 : 1 quand l'image y reproduit le gabarit à un facteur
    et un décalage de luminosité près.
    """
    image = np.asarray(image, dtype=float)
    centre = np.asarray(gabarit, dtype=float)
    centre = centre - centre.mean()
    hauteur, largeur = centre.shape
    norme = math.sqrt(float((centre * centre).sum()))
    produit = np.fft.irfft2(
        np.fft.rfft2(image) * np.conj(np.fft.rfft2(centre, s=image.shape)), s=image.shape
    )[: image.shape[0] - hauteur + 1, : image.shape[1] - largeur + 1]

    def somme_glissante(a: np.ndarray) -> np.ndarray:
        cumul = np.pad(a, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        return (
            cumul[hauteur:, largeur:]
            - cumul[:-hauteur, largeur:]
            - cumul[hauteur:, :-largeur]
            + cumul[:-hauteur, :-largeur]
        )

    somme = somme_glissante(image)
    variance = np.maximum(somme_glissante(image * image) - somme * somme / centre.size, 0.0)
    denominateur = np.sqrt(variance) * norme
    valide = denominateur > 1e-9
    carte = np.zeros_like(produit)
    carte[valide] = produit[valide] / denominateur[valide]
    return carte


def _sommet(carte: np.ndarray) -> tuple[float, float, float]:
    """Position du maximum, affinée au sous-pixel par une parabole sur chaque axe."""
    ligne, colonne = np.unravel_index(int(np.argmax(carte)), carte.shape)

    def affiner(valeurs: np.ndarray, i: int) -> float:
        if 0 < i < len(valeurs) - 1:
            gauche, milieu, droite = valeurs[i - 1], valeurs[i], valeurs[i + 1]
            courbure = gauche - 2.0 * milieu + droite
            if courbure < 0:
                return i + 0.5 * (gauche - droite) / courbure
        return float(i)

    return (
        affiner(carte[ligne, :], colonne),
        affiner(carte[:, colonne], ligne),
        float(carte[ligne, colonne]),
    )


# ---------------------------------------------------------------------------
# Le fond HelioScope sur une grille Lambert 93
# ---------------------------------------------------------------------------


def _affine_vers_l93(calage, fond) -> np.ndarray:
    """L'affine repère DXF → Lambert 93 du calage courant, sur l'emprise du fond.

    La projection du lot 2 n'est pas affine, mais sur les quelques centaines de
    mètres d'un fond elle l'est au millimètre près.
    """
    x0, y0 = fond.origine_m
    largeur_px, hauteur_px = fond.taille_px
    xs = np.linspace(x0, x0 + largeur_px * fond.resolution_m_px, 6)
    ys = np.linspace(y0, y0 + hauteur_px * fond.resolution_m_px, 6)
    source = np.array([(x, y, 1.0) for x in xs for y in ys])
    cible = np.array([projeter(Point(x, y), calage).coords[0] for x, y, _ in source])
    coefficients, *_ = np.linalg.lstsq(source, cible, rcond=None)
    return coefficients


def fond_sur_grille(fond, affine: np.ndarray, coin: tuple, pas: float, taille: tuple) -> np.ndarray:
    """Le fond HelioScope rééchantillonné sur une grille Lambert 93, en niveaux de gris.

    `coin` est le coin haut-gauche de la grille (est, nord), `taille` son nombre
    de colonnes et de lignes. Coordonnées continues de part et d'autre : le
    centre du pixel (i, j) est en (i + 0,5, j + 0,5). Hors du fond, zéro.
    """
    x0, y0 = fond.origine_m
    resolution = fond.resolution_m_px
    hauteur_px = fond.taille_px[1]
    # (est, nord) = coin + (u·pas, −v·pas) ; (x, y) = inverse de l'affine ;
    # (colonne, ligne) du fond = ((x − x0)/res, H − (y − y0)/res).
    lineaire = affine[:2, :].T  # (est, nord) = lineaire @ (x, y) + translation
    translation = affine[2, :]
    inverse = np.linalg.inv(lineaire)
    vers_grille = np.array([[pas, 0.0], [0.0, -pas]])
    decalage_grille = np.array(coin) - translation
    vers_dxf = inverse @ vers_grille
    origine_dxf = inverse @ decalage_grille
    vers_fond = np.array([[1.0 / resolution, 0.0], [0.0, -1.0 / resolution]])
    lineaire_total = vers_fond @ vers_dxf
    constante = vers_fond @ (origine_dxf - np.array([x0, y0])) + np.array([0.0, hauteur_px])
    donnees = (
        lineaire_total[0, 0], lineaire_total[0, 1], constante[0],
        lineaire_total[1, 0], lineaire_total[1, 1], constante[1],
    )
    image = Image.open(io.BytesIO(fond.image)).convert("L")
    rééchantillonnée = image.transform(
        taille, Image.Transform.AFFINE, donnees, resample=Image.Resampling.BILINEAR
    )
    return np.asarray(rééchantillonnée, dtype=float)


# ---------------------------------------------------------------------------
# La mesure, et son application
# ---------------------------------------------------------------------------


def mesurer_sur_ortho(implantation, telecharger=None) -> MesureOrtho:
    """Le déplacement qui pose le fond HelioScope sur l'ortho IGN, au calage courant.

    `telecharger` remplace le téléchargement de l'ortho — pour les tests ; il a
    la signature de `ign.telecharger_fond`.
    """
    from .ign import COUCHE_ORTHO, telecharger_fond

    telecharger = telecharger or telecharger_fond
    fond = implantation.fond
    if fond is None:
        raise ErreurCalage(
            "L'export HelioScope ne porte pas d'image de fond : rien à chercher "
            "dans l'ortho IGN. Réglez le calage à l'œil, ou réexportez le Layout "
            "CAD avec son image."
        )
    affine = _affine_vers_l93(implantation.calage, fond)
    x0, y0 = fond.origine_m
    largeur_m = fond.taille_px[0] * fond.resolution_m_px
    hauteur_m = fond.taille_px[1] * fond.resolution_m_px
    coins = np.array(
        [(x, y, 1.0) for x in (x0, x0 + largeur_m) for y in (y0, y0 + hauteur_m)]
    ) @ affine
    est_min, nord_min = coins.min(axis=0)
    est_max, nord_max = coins.max(axis=0)
    pas = max(fond.resolution_m_px, PAS_MINIMAL_M)

    cadre = (
        est_min - MARGE_RECHERCHE_M,
        nord_min - MARGE_RECHERCHE_M,
        est_max + MARGE_RECHERCHE_M,
        nord_max + MARGE_RECHERCHE_M,
    )
    colonnes = int(round((cadre[2] - cadre[0]) / pas))
    lignes = int(round((cadre[3] - cadre[1]) / pas))
    dpi = 96
    ortho = telecharger(
        COUCHE_ORTHO, cadre, colonnes / dpi * 25.4, lignes / dpi * 25.4, dpi=dpi
    )
    image_ortho = np.asarray(
        ortho.image.convert("L").resize((colonnes, lignes), Image.Resampling.BILINEAR),
        dtype=float,
    )

    # Le gabarit : le fond sur la grille, dans son emprise, rogné de ce que la
    # convergence des méridiens a fait tourner hors de l'image — 1,5° aux
    # Islettes, 26 pixels à rogner de chaque côté.
    colonne_fond = int(round((est_min - cadre[0]) / pas))
    ligne_fond = int(round((cadre[3] - nord_max) / pas))
    taille_fond = (int(round((est_max - est_min) / pas)), int(round((nord_max - nord_min) / pas)))
    gabarit = fond_sur_grille(
        fond,
        affine,
        (cadre[0] + colonne_fond * pas, cadre[3] - ligne_fond * pas),
        pas,
        taille_fond,
    )
    rogne = 12 + int(0.05 * min(gabarit.shape))
    gabarit = gabarit[rogne:-rogne, rogne:-rogne]

    carte = correlation_normalisee(gradient(image_ortho), gradient(gabarit))
    colonne, ligne, pic = _sommet(carte)
    voisinage = int(ECART_SECOND_PIC_M / pas)
    masquee = carte.copy()
    i, j = int(round(ligne)), int(round(colonne))
    masquee[max(0, i - voisinage) : i + voisinage + 1, max(0, j - voisinage) : j + voisinage + 1] = -1.0
    second = float(masquee.max())

    if pic < PIC_MINIMAL or pic < RAPPORT_MINIMAL * max(second, 0.0):
        raise ErreurCalage(
            "Le fond HelioScope ne se reconnaît pas nettement dans l'ortho IGN : "
            f"corrélation de {pic:.2f} au meilleur accord, {second:.2f} ailleurs "
            f"(il faut au moins {PIC_MINIMAL:.2f}, et {RAPPORT_MINIMAL:.1f} fois "
            "mieux qu'ailleurs). Le calage n'est pas modifié : réglez-le à l'œil "
            "sur la carte."
        )
    return MesureOrtho(
        decalage_est_m=(colonne - (colonne_fond + rogne)) * pas,
        decalage_nord_m=-(ligne - (ligne_fond + rogne)) * pas,
        pic=pic,
        second_pic=second,
        pas_m=pas,
    )


def caler_sur_ortho(implantation, telecharger=None) -> MesureOrtho:
    """Mesure le déplacement sur l'ortho, et l'applique au calage.

    Le nord-sud d'abord : c'est lui qui peut sortir de sa borne, et rien ne
    doit avoir bougé quand il refuse.
    """
    mesure = mesurer_sur_ortho(implantation, telecharger)
    calage = implantation.calage
    corriger_nord_sud(calage, calage.correction_nord_sud_m + mesure.decalage_nord_m)
    decaler_longitude(calage, mesure.decalage_est_m)
    return mesure
