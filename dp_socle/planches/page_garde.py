"""Page de garde du dossier de déclaration préalable.

Le sommaire porte les numéros de page réels : il est composé après génération
des planches, quand le nombre de pages de chacune est connu (voir
`dp_socle.assemblage`).

Le dossier ne se présente pas comme un dossier d'architecte : ni mention d'un
numéro d'inscription à l'ordre, ni case de signature.
"""

from __future__ import annotations

from pathlib import Path

from ..dossier import PIECES
from ..planche import (
    BLEU_UNITE,
    CADRE,
    GRIS,
    GRIS_FOND,
    LARGEUR_MM,
    LOGO_UNITE,
    MENTION_BANDEAU,
    NOIR,
    PT,
    VERT_UNITE,
    Planche,
    Style,
)
from ..projet import MOA_ADRESSE, MOA_NOM, MOA_VILLE, Projet
from .commun import Sortie

NUMERO = "GARDE"
TITRE = "PAGE DE GARDE"

#: Cadre réservé à la perspective. Laissé blanc si aucune image n'est fournie :
#: un rectangle vide sur une page de garde se remarque plus que du blanc.
CADRE_IMAGE = (22.0, 118.0, 228.0, 140.0)

COLONNE_DROITE = 266.0
LARGEUR_COLONNE = 132.0


def generer(
    projet: Projet, dossier: Path, pages: dict | None = None
) -> Sortie:
    """Compose la page de garde.

    `pages` associe le code de chaque pièce produite à son numéro de page réel.
    Les pièces des lots suivants figurent quand même au sommaire, sans numéro :
    le dossier s'annonce complet dès maintenant.
    """
    planche = Planche(
        titre=TITRE,
        numero=NUMERO,
        projet=projet.libelle_affiche,
        date=projet.date_francaise(),
        avec_cartouche=False,
    )

    cadre_x, cadre_y, cadre_l, cadre_h = CADRE
    planche.ajouter_rectangle(
        cadre_x, cadre_y, cadre_l, cadre_h,
        Style(trait=NOIR, epaisseur_mm=0.35, remplissage="none"),
    )

    if LOGO_UNITE.exists():
        planche.ajouter_image_mm(LOGO_UNITE, 18.0, 16.0, 58.0, 28.0)

    centre = LARGEUR_MM / 2.0
    planche.ajouter_texte(
        centre, 70.0, "DÉCLARATION PRÉALABLE",
        taille=30 * PT, ancre="middle", gras=True, couleur=BLEU_UNITE,
    )
    planche.ajouter_texte(
        centre, 85.0, "PROJET DE CENTRALE PHOTOVOLTAÏQUE AU SOL",
        taille=17 * PT, ancre="middle", couleur=BLEU_UNITE,
    )
    planche.ajouter_texte(
        centre, 98.0, f"{projet.commune.upper()}  {projet.code_postal}",
        taille=15 * PT, ancre="middle", couleur=BLEU_UNITE,
    )
    # Filet vert court et centré, repris des plaquettes UNITe.
    planche.ajouter_ligne(
        centre - 22.0, 106.0, centre + 22.0, 106.0,
        Style(trait=VERT_UNITE, epaisseur_mm=1.2),
    )

    image = projet.chemin_image_garde
    if image is not None and image.exists():
        planche.ajouter_image_mm(image, *CADRE_IMAGE)

    bas = _bloc_maitrise(planche, COLONNE_DROITE, 118.0)
    _bloc_sommaire(planche, COLONNE_DROITE, bas + 8.0, pages or {})

    planche.ajouter_texte(
        cadre_x + 3.0, cadre_h + cadre_y - 4.0,
        f"UNITe — {projet.libelle_affiche} — {projet.date_francaise()}",
        taille=8 * PT, couleur=GRIS,
    )
    planche.ajouter_texte(
        cadre_x + cadre_l - 3.0, cadre_h + cadre_y - 4.0, MENTION_BANDEAU,
        taille=8 * PT, ancre="end", couleur=GRIS,
    )

    chemin = planche.rendre_pdf(Path(dossier) / "DP_0_page_de_garde.pdf")
    return Sortie(numero=NUMERO, titre=TITRE, chemin=chemin)


def _cellule_titre(planche: Planche, x: float, y: float, largeur: float,
                   hauteur: float, intitule: str) -> None:
    """Case de titre fermée, à fond gris : le tableau se lit d'un coup d'œil."""
    planche.ajouter_rectangle(
        x, y, largeur, hauteur,
        Style(trait=NOIR, epaisseur_mm=0.25, remplissage=GRIS_FOND),
    )
    planche.ajouter_texte(
        x + 4.0, y + hauteur - 2.4, intitule,
        taille=8 * PT, couleur=GRIS, gras=True,
    )


def _bloc_maitrise(planche: Planche, x: float, y: float) -> float:
    hauteur_titre = 7.0
    hauteur_contenu = 24.0
    demi = LARGEUR_COLONNE / 2.0

    for index, intitule in enumerate(("MAÎTRE D'OUVRAGE", "MAÎTRE D'ŒUVRE")):
        gauche = x + index * demi
        _cellule_titre(planche, gauche, y, demi, hauteur_titre, intitule)
        planche.ajouter_rectangle(
            gauche, y + hauteur_titre, demi, hauteur_contenu,
            Style(trait=NOIR, epaisseur_mm=0.25, remplissage="none"),
        )
        planche.ajouter_bloc_texte(
            gauche + 4.0, y + hauteur_titre + 6.0,
            (MOA_NOM, MOA_ADRESSE, MOA_VILLE),
            taille=10 * PT, interligne=1.45,
        )
    return y + hauteur_titre + hauteur_contenu


def _bloc_sommaire(planche: Planche, x: float, y: float, pages: dict) -> float:
    hauteur_titre = 7.0
    hauteur_ligne = 5.0
    pieces = [p for p in PIECES if p.code]  # la page de garde ne s'y liste pas
    hauteur_contenu = 4.0 + hauteur_ligne * len(pieces)

    _cellule_titre(planche, x, y, LARGEUR_COLONNE, hauteur_titre, "SOMMAIRE")
    planche.ajouter_rectangle(
        x, y + hauteur_titre, LARGEUR_COLONNE, hauteur_contenu,
        Style(trait=NOIR, epaisseur_mm=0.25, remplissage="none"),
    )

    for index, piece in enumerate(pieces):
        ordonnee = y + hauteur_titre + 5.4 + index * hauteur_ligne
        page = pages.get(piece.code)
        couleur = NOIR if page else GRIS
        planche.ajouter_texte(
            x + 4.0, ordonnee, piece.intitule, taille=9 * PT, couleur=couleur
        )
        # Pas de mention de lot ici : la page de garde part en mairie, elle n'a
        # pas à porter le découpage interne du développement.
        planche.ajouter_texte(
            x + LARGEUR_COLONNE - 4.0, ordonnee, str(page) if page else "—",
            taille=9 * PT, ancre="end", couleur=couleur,
        )
    return y + hauteur_titre + hauteur_contenu
