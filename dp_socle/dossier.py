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
    Piece("DP 2", "Plan de masse", produite=True),
    Piece("DP 3", "Coupe des tables photovoltaïques et du terrain", produite=True),
    Piece("DP 4-1", "Poste de livraison/transformation", produite=True),
    Piece("DP 4-2", "Citerne, portail et clôture", produite=True),
    # Troisième planche d'ouvrages, pour les projets qui en portent plus que
    # les deux premières n'en logent : BESS, local technique, bac de rétention,
    # citerne de refroidissement, aire d'aspiration. Elle n'existe que si ces
    # ouvrages existent — d'où la numérotation calculée sur les pièces
    # réellement produites et non sur cette liste.
    Piece("DP 4-3", "Autres ouvrages techniques", produite=True),
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


def numero_planche(code: str, codes_produits=None) -> int:
    """Rang de la planche dans le dossier assemblé.

    La page de garde compte comme la planche 1 : le plan de cadastre est donc
    la planche 4, comme dans les dossiers de l'agence. Chaque pièce tenant sur
    une page, ce rang est aussi son numéro de page ; `dp_socle.assemblage` le
    vérifie sur le PDF produit plutôt que de s'en remettre à cette hypothèse.

    `codes_produits` est la liste des pièces réellement produites pour **ce**
    dossier. Depuis le lot 4, elle ne se déduit plus de `PIECES` : un projet
    sans poste n'a pas de DP 4-1, un dossier d'origine HelioScope n'a aucune
    DP 4, et le rang des pièces suivantes s'en trouve décalé. Sans cet
    argument, le rang est celui du dossier complet — ce qui reste juste pour
    les planches du socle, toujours produites et toujours en tête.
    """
    codes = list(codes_produits) if codes_produits is not None else [
        p.code for p in PIECES_PRODUITES
    ]
    if code not in codes:
        raise KeyError(
            f"La pièce « {code} » n'est pas dans les pièces produites de ce "
            f"dossier ({', '.join(c for c in codes if c) or 'aucune'}) : son "
            "rang n'a pas de sens."
        )
    return codes.index(code) + 1


def codes_produits(planches) -> list:
    """Codes des pièces produites, page de garde comprise, dans l'ordre.

    `planches` est la liste des codes de planches effectivement générées. La
    page de garde y est ajoutée en tête : c'est elle qui occupe la page 1.
    """
    ordre = [p.code for p in PIECES]
    inconnus = [c for c in planches if c not in ordre]
    if inconnus:
        raise KeyError(
            f"Pièces inconnues du dossier : {', '.join(inconnus)}."
        )
    return [""] + [c for c in ordre if c and c in set(planches)]
