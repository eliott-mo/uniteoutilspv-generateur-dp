"""Page de garde du dossier de déclaration préalable.

Le sommaire porte les numéros de page réels : il est composé après génération
des planches, quand le nombre de pages de chacune est connu (voir
`dp_socle.assemblage`).

Le dossier ne se présente pas comme un dossier d'architecte : ni mention d'un
numéro d'inscription à l'ordre, ni case de signature.
"""

from __future__ import annotations

from pathlib import Path

from ..planche import (
    CADRE,
    GRIS,
    LARGEUR_MM,
    LOGO_UNITE,
    MENTION_BANDEAU,
    NOIR,
    PT,
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
    projet: Projet, dossier: Path, sommaire: list[dict] | None = None
) -> Sortie:
    planche = Planche(
        titre=TITRE,
        numero=NUMERO,
        projet=projet.nom,
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
        taille=30 * PT, ancre="middle", gras=True,
    )
    planche.ajouter_texte(
        centre, 85.0, "PROJET DE CENTRALE PHOTOVOLTAÏQUE AU SOL",
        taille=17 * PT, ancre="middle",
    )
    planche.ajouter_texte(
        centre, 98.0, f"{projet.commune.upper()}  {projet.code_postal}",
        taille=15 * PT, ancre="middle",
    )
    planche.ajouter_ligne(
        70.0, 105.0, LARGEUR_MM - 70.0, 105.0,
        Style(trait=NOIR, epaisseur_mm=0.4),
    )

    image = projet.chemin_image_garde
    if image is not None and image.exists():
        planche.ajouter_image_mm(image, *CADRE_IMAGE)

    _bloc_maitrise(planche, COLONNE_DROITE, 120.0)
    if sommaire:
        _bloc_sommaire(planche, COLONNE_DROITE, 176.0, sommaire)

    planche.ajouter_texte(
        cadre_x + 3.0, cadre_h + cadre_y - 4.0,
        f"UNITe — {projet.nom} — {projet.date_francaise()}",
        taille=8 * PT, couleur=GRIS,
    )
    planche.ajouter_texte(
        cadre_x + cadre_l - 3.0, cadre_h + cadre_y - 4.0, MENTION_BANDEAU,
        taille=8 * PT, ancre="end", couleur=GRIS,
    )

    chemin = planche.rendre_pdf(Path(dossier) / "DP_0_page_de_garde.pdf")
    return Sortie(numero=NUMERO, titre=TITRE, chemin=chemin)


def _bloc_maitrise(planche: Planche, x: float, y: float) -> None:
    planche.ajouter_rectangle(
        x, y, LARGEUR_COLONNE, 46.0,
        Style(trait=NOIR, epaisseur_mm=0.25, remplissage="none"),
    )
    colonnes = ((x + 4.0, "MAÎTRE D'OUVRAGE"), (x + LARGEUR_COLONNE / 2.0 + 2.0,
                                                "MAÎTRE D'ŒUVRE"))
    for abscisse, intitule in colonnes:
        planche.ajouter_texte(
            abscisse, y + 7.0, intitule, taille=8 * PT, couleur=GRIS, gras=True
        )
        planche.ajouter_bloc_texte(
            abscisse, y + 14.5, (MOA_NOM, MOA_ADRESSE, MOA_VILLE),
            taille=10 * PT, interligne=1.45,
        )


def _bloc_sommaire(planche: Planche, x: float, y: float, sommaire: list[dict]) -> None:
    hauteur_ligne = 5.4
    hauteur = 12.0 + hauteur_ligne * len(sommaire)
    planche.ajouter_rectangle(
        x, y, LARGEUR_COLONNE, hauteur,
        Style(trait=NOIR, epaisseur_mm=0.25, remplissage="none"),
    )
    planche.ajouter_texte(
        x + 4.0, y + 7.5, "SOMMAIRE", taille=8 * PT, couleur=GRIS, gras=True
    )
    for index, entree in enumerate(sommaire):
        ordonnee = y + 14.5 + index * hauteur_ligne
        libelle = entree["titre"].capitalize() if entree["numero"] == NUMERO else (
            f"{entree['numero']} — {entree['titre'].capitalize()}"
        )
        planche.ajouter_texte(x + 4.0, ordonnee, libelle, taille=9 * PT)
        planche.ajouter_texte(
            x + LARGEUR_COLONNE - 4.0, ordonnee, str(entree["page"]),
            taille=9 * PT, ancre="end",
        )
