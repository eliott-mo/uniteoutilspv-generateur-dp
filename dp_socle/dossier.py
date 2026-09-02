"""Composition du dossier de déclaration préalable.

Référentiel unique des pièces : le sommaire de la page de garde et les titres
de cartouche en sortent tous les deux, de sorte qu'ils ne puissent pas diverger.

Les pièces des lots suivants y figurent dès maintenant, sans numéro de page :
le sommaire annonce le dossier complet, et il suffira de basculer `produite` à
vrai au fur et à mesure.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Piece:
    """Une pièce du dossier."""

    code: str
    titre: str
    #: Produite par le générateur, ou fournie / à venir dans un lot ultérieur.
    produite: bool = False
    #: Précision affichée au sommaire pour les pièces non produites.
    mention: str = ""

    @property
    def intitule(self) -> str:
        """« DP 1-3 : Plan de cadastre », pour le sommaire."""
        return f"{self.code} : {self.titre}" if self.code else self.titre

    @property
    def intitule_cartouche(self) -> str:
        """Même chose en capitales, pour le cartouche des planches."""
        return self.intitule.upper()


#: Ordre et intitulés du dossier. Les libellés reprennent ceux du sommaire des
#: dossiers HOCH (relevés sur le dossier Les Islettes du 25/04/2024) : les
#: services instructeurs sont habitués à cette formulation, et la reprendre évite
#: de leur faire lire un vocabulaire différent d'un dossier UNITe à l'autre.
PIECES = (
    Piece("", "Page de garde", produite=True),
    Piece("DP 1-1", "Plan de situation", produite=True),
    Piece("DP 1-2", "Photo aérienne", produite=True),
    Piece("DP 1-3", "Plan de cadastre", produite=True),
    Piece("DP 2", "Plan de masse", mention="lot 4"),
    Piece("DP 3", "Coupe des tables photovoltaïques et du terrain", mention="lot 4"),
    Piece("DP 4-1", "Poste de livraison/transformation", mention="lot 4"),
    Piece("DP 4-2", "Citerne, portail et clôture", mention="lot 4"),
    Piece("DP 6", "Insertions paysagères", mention="fournie"),
    Piece("DP 7", "Photographie environnement proche", mention="fournie"),
    Piece("DP 8", "Photographie paysage lointain", mention="fournie"),
    Piece("DP 11", "Notice", mention="lot 5"),
)

PAR_CODE = {piece.code: piece for piece in PIECES if piece.code}

#: Pièces effectivement produites par le socle, dans l'ordre du dossier.
PIECES_PRODUITES = tuple(piece for piece in PIECES if piece.produite)

#: Planches produites, hors page de garde.
PLANCHES_PRODUITES = tuple(piece for piece in PIECES_PRODUITES if piece.code)


def piece(code: str) -> Piece:
    return PAR_CODE[code]


def numero_planche(code: str) -> int:
    """Rang de la planche dans le dossier assemblé.

    La page de garde compte comme la planche 1 : le plan de cadastre est donc
    la planche 4, comme dans les dossiers de l'agence. Chaque pièce tenant sur
    une page, ce rang est aussi son numéro de page ; `dp_socle.assemblage` le
    vérifie sur le PDF produit plutôt que de s'en remettre à cette hypothèse.
    """
    codes = [p.code for p in PIECES_PRODUITES]
    return codes.index(code) + 1
