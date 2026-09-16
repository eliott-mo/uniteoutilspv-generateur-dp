"""Composition du dossier de déclaration préalable.

Référentiel unique des pièces : le sommaire de la page de garde et les titres
de cartouche en sortent tous les deux, de sorte qu'ils ne puissent pas diverger.

Depuis le lot 6, toutes les pièces du dossier sont produites. `produite` reste
le drapeau qui décide de la pagination au sommaire : une pièce qui n'a pas de
page s'y affiche « — », en gris.
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
    # Produites depuis le lot 6. DP 6 peut couvrir **plusieurs planches**, une
    # par point de vue : son rang se compte donc sur les planches réellement
    # produites, comme celui des DP 4, et jamais sur cette liste.
    Piece("DP 6", "Insertions paysagères", produite=True),
    Piece("DP 7", "Photographie environnement proche", produite=True),
    Piece("DP 8", "Photographie paysage lointain", produite=True),
    # Produite depuis le lot 5, mais pas composée : le chef de projet fournit
    # la notice en PDF et l'outil l'habille du cadre et du cartouche du
    # dossier. Elle est la seule pièce à pouvoir couvrir plusieurs pages.
    Piece("DP 11", "Notice", produite=True),
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
    la planche 4, comme dans les dossiers de l'agence. Ce rang n'est le numéro
    de page de la pièce que si toutes celles qui la précèdent tiennent sur une
    page — ce qui est le cas de toutes sauf la notice DP 11, dernière du
    dossier. `dp_socle.assemblage` ne s'en remet pas à cette hypothèse : il
    compte les pages des PDF produits, et une pièce qui en couvre plusieurs
    déclare les numéros de ses cartouches (`Sortie.numeros`).

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
