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


#: Ordre du dossier. Les intitulés DP 6 / DP 7 / DP 8 reprennent la
#: nomenclature du formulaire Cerfa de déclaration préalable.
PIECES = (
    Piece("", "Page de garde", produite=True),
    Piece("DP 1-1", "Plan de situation du terrain", produite=True),
    Piece("DP 1-2", "Photographie aérienne du terrain", produite=True),
    Piece("DP 1-3", "Plan de cadastre", produite=True),
    Piece("DP 2", "Plan de masse des constructions", mention="lot 4"),
    Piece("DP 3", "Plan en coupe du terrain et de la construction", mention="lot 4"),
    Piece("DP 4-1", "Aspect extérieur — postes et citerne", mention="lot 4"),
    Piece("DP 4-2", "Aspect extérieur — clôture et portails", mention="lot 4"),
    Piece("DP 6", "Insertion du projet dans son environnement", mention="fournie"),
    Piece("DP 7", "Photographie de l'environnement proche", mention="fournie"),
    Piece("DP 8", "Photographie de l'environnement lointain", mention="fournie"),
    Piece("DP 11", "Notice descriptive", mention="lot 5"),
)

PAR_CODE = {piece.code: piece for piece in PIECES if piece.code}

#: Pièces effectivement produites par le socle, dans l'ordre du dossier.
PIECES_PRODUITES = tuple(piece for piece in PIECES if piece.produite)

#: Planches produites, hors page de garde : c'est sur elles que porte le
#: repère « n/N » inscrit dans la case NUMÉRO du cartouche.
PLANCHES_PRODUITES = tuple(piece for piece in PIECES_PRODUITES if piece.code)


def piece(code: str) -> Piece:
    return PAR_CODE[code]


def repere(code: str) -> str:
    """Numéro de planche, sous la forme « 2/3 »."""
    codes = [p.code for p in PLANCHES_PRODUITES]
    return f"{codes.index(code) + 1}/{len(codes)}"
