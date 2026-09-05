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

#: Gris du cadre qui tient la place du photomontage tant qu'il n'est pas
#: fourni. Assez pâle pour ne pas concurrencer le titre, assez présent pour
#: qu'on voie qu'il manque une pièce.
GRIS_CADRE_VIDE = "#a8a8a8"

#: Hauteur du bandeau de légende posé au-dessus du photomontage.
HAUTEUR_LEGENDE_IMAGE = 6.5

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
        taille=15 * PT, ancre="middle", gras=True, couleur=BLEU_UNITE,
    )
    # Filet vert court et centré, repris des plaquettes UNITe.
    planche.ajouter_ligne(
        centre - 22.0, 106.0, centre + 22.0, 106.0,
        Style(trait=VERT_UNITE, epaisseur_mm=1.2),
    )

    image = projet.chemin_image_garde
    if image is not None and image.exists():
        x_img, y_img, largeur_img, hauteur_img = CADRE_IMAGE
        # L'image est posée d'abord : le bandeau de légende et le filet se calent
        # ensuite sur la zone qu'elle occupe réellement, quelles que soient ses
        # proportions. Sinon un cadre plus large que la photo laisse du blanc
        # entre les deux.
        zone = planche.ajouter_image_mm(
            image, x_img, y_img + HAUTEUR_LEGENDE_IMAGE,
            largeur_img, hauteur_img - HAUTEUR_LEGENDE_IMAGE,
        )
        x_reel, y_reel, largeur_reelle, hauteur_reelle = zone
        # Case titrée seulement s'il y a une image : une case surmontant du vide
        # serait pire que du blanc.
        _cellule_titre(
            planche, x_reel, y_reel - HAUTEUR_LEGENDE_IMAGE, largeur_reelle,
            HAUTEUR_LEGENDE_IMAGE, "VUE EN PERSPECTIVE DU PROJET", centre=True,
        )
        planche.ajouter_rectangle(
            x_reel, y_reel, largeur_reelle, hauteur_reelle,
            Style(trait=NOIR, epaisseur_mm=0.25, remplissage="none"),
        )
    else:
        # Sans photomontage, un cadre léger tient la place et la nomme. Le vide
        # laissé nu se lisait comme une page mal composée ; un cadre annoncé
        # « à insérer » se lit comme une pièce à venir, et rappelle au chef de
        # projet ce qu'il reste à fournir.
        x_img, y_img, largeur_img, hauteur_img = CADRE_IMAGE
        _cellule_titre(
            planche, x_img, y_img, largeur_img, HAUTEUR_LEGENDE_IMAGE,
            "VUE EN PERSPECTIVE DU PROJET", centre=True,
        )
        planche.ajouter_rectangle(
            x_img, y_img + HAUTEUR_LEGENDE_IMAGE, largeur_img,
            hauteur_img - HAUTEUR_LEGENDE_IMAGE,
            Style(trait=GRIS_CADRE_VIDE, epaisseur_mm=0.25, remplissage="none",
                  tirets="2.5 2.0"),
        )
        planche.ajouter_texte(
            x_img + largeur_img / 2.0,
            y_img + HAUTEUR_LEGENDE_IMAGE + (hauteur_img - HAUTEUR_LEGENDE_IMAGE) / 2.0,
            "Photomontage à insérer",
            taille=8 * PT, couleur=GRIS_CADRE_VIDE, ancre="middle",
        )

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
                   hauteur: float, intitule: str, centre: bool = False) -> None:
    """Case de titre fermée, à fond gris : le tableau se lit d'un coup d'œil."""
    planche.ajouter_rectangle(
        x, y, largeur, hauteur,
        Style(trait=NOIR, epaisseur_mm=0.25, remplissage=GRIS_FOND),
    )
    planche.ajouter_texte(
        x + largeur / 2.0 if centre else x + 4.0, y + hauteur - 2.4, intitule,
        taille=8 * PT, couleur=GRIS if not centre else BLEU_UNITE, gras=True,
        ancre="middle" if centre else "start",
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
    """Sommaire à trois colonnes : code de la pièce, intitulé, page(s).

    Les pièces des lots suivants y figurent sans page. `pages` accepte un entier
    ou un couple (première, dernière) : une pièce sur plusieurs planches, comme
    les insertions paysagères, s'affiche « 9-10 ».
    """
    hauteur_titre = 7.0
    hauteur_ligne = 5.0
    pieces = [p for p in PIECES if p.code]  # la page de garde ne s'y liste pas
    hauteur_contenu = hauteur_ligne * len(pieces)

    _cellule_titre(planche, x, y, LARGEUR_COLONNE, hauteur_titre, "SOMMAIRE",
                   centre=True)
    haut = y + hauteur_titre
    planche.ajouter_rectangle(
        x, haut, LARGEUR_COLONNE, hauteur_contenu,
        Style(trait=NOIR, epaisseur_mm=0.25, remplissage="none"),
    )

    filet = Style(trait="#9a9a9a", epaisseur_mm=0.15)
    colonne_titre = x + 20.0
    colonne_page = x + LARGEUR_COLONNE - 18.0
    for abscisse in (colonne_titre, colonne_page):
        planche.ajouter_ligne(abscisse, haut, abscisse, haut + hauteur_contenu, filet)

    for index, piece in enumerate(pieces):
        sommet = haut + index * hauteur_ligne
        ligne_de_base = sommet + 3.5
        if index:
            planche.ajouter_ligne(x, sommet, x + LARGEUR_COLONNE, sommet, filet)

        page = pages.get(piece.code)
        couleur = NOIR if page else GRIS
        planche.ajouter_texte(x + 3.0, ligne_de_base, piece.code,
                              taille=9 * PT, couleur=couleur)
        planche.ajouter_texte(colonne_titre + 3.0, ligne_de_base, piece.titre,
                              taille=9 * PT, couleur=couleur)
        planche.ajouter_texte(
            (colonne_page + x + LARGEUR_COLONNE) / 2.0, ligne_de_base,
            _pagination(page), taille=9 * PT, ancre="middle", couleur=couleur,
        )
    return haut + hauteur_contenu


def _pagination(page) -> str:
    """« 4 », « 9-10 » ou « — » pour une pièce non encore produite."""
    if page is None:
        return "—"
    if isinstance(page, tuple):
        premiere, derniere = page
        return f"{premiere}" if premiere == derniere else f"{premiere}-{derniere}"
    return str(page)
