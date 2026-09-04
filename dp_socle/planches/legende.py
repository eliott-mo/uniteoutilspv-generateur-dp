"""Bloc de légende du dossier, à symboles dessinés.

Le moteur du lot 1 compose une légende dont chaque entrée est un rectangle de
6 x 3 mm rempli du style de la catégorie. C'est juste pour une surface — une
piste, une plateforme, un poste — et faux pour tout le reste : la clôture et le
portail sont deux linéaires rouges sans remplissage, et leurs deux entrées
sortaient identiques, deux rectangles au filet rouge.

Ce module compose le même bloc, à la même géométrie, mais laisse chaque
catégorie dessiner son propre symbole : un portail se reconnaît à ses deux
vantaux, une clôture à ses poteaux, une haie à sa silhouette. C'est ce que fait
la légende du dossier de référence, et c'est ce qui permet de lire une planche
sans compter les nuances de rouge.

Le moteur n'est pas modifié : ce bloc se compose avec `ajouter_rectangle`,
`ajouter_ligne` et `ajouter_texte`, comme n'importe quel autre habillage.
"""

from __future__ import annotations

from ..planche import NOIR, TAILLE_CARTOUCHE, TAILLE_COURANTE, Planche, Style

#: Géométrie du bloc, en millimètres. Le pavé de symbole est un peu plus grand
#: que celui du moteur : un portail dessiné dans 6 x 3 mm n'est plus qu'un
#: griffonnage.
MARGE_MM = 2.4
PAS_ENTREE_MM = 5.6
LARGEUR_SYMBOLE_MM = 9.0
HAUTEUR_SYMBOLE_MM = 4.0
ECART_LIBELLE_MM = 3.0
HAUTEUR_TITRE_MM = 5.4


def hauteur_bloc(nb_entrees: int, avec_titre: bool = True) -> float:
    """Hauteur qu'occupera le bloc, connue avant de le dessiner.

    Les planches DP 4 en ont besoin pour savoir la place qui reste au plan de
    repérage : la légende n'est pas un ajout de dernière minute posé par-dessus
    le dessin, c'est elle qui décide de ce qui lui reste.
    """
    return (
        2 * MARGE_MM
        + (HAUTEUR_TITRE_MM if avec_titre else 0.0)
        + PAS_ENTREE_MM * nb_entrees
    )


def dessiner_legende(
    planche: Planche,
    entrees,
    position: tuple,
    largeur_mm: float = 70.0,
    titre: str | None = "Légende",
) -> tuple:
    """Bloc encadré à fond blanc, chaque entrée dessinant son symbole."""
    x_mm, y_mm = position
    hauteur = hauteur_bloc(len(entrees), titre is not None)

    planche.ajouter_rectangle(
        x_mm, y_mm, largeur_mm, hauteur,
        Style(trait=NOIR, epaisseur_mm=0.25, remplissage="#ffffff",
              opacite_remplissage=0.92),
    )
    curseur = y_mm + MARGE_MM
    if titre:
        planche.ajouter_texte(
            x_mm + MARGE_MM, curseur + 3.2, titre,
            taille=TAILLE_CARTOUCHE, gras=True,
        )
        curseur += HAUTEUR_TITRE_MM

    for entree in entrees:
        haut = curseur + (PAS_ENTREE_MM - HAUTEUR_SYMBOLE_MM) / 2.0
        _dessiner_symbole(
            planche, entree, x_mm + MARGE_MM, haut,
            LARGEUR_SYMBOLE_MM, HAUTEUR_SYMBOLE_MM,
        )
        planche.ajouter_texte(
            x_mm + MARGE_MM + LARGEUR_SYMBOLE_MM + ECART_LIBELLE_MM,
            haut + HAUTEUR_SYMBOLE_MM - 1.1,
            entree.libelle,
            taille=TAILLE_COURANTE,
        )
        curseur += PAS_ENTREE_MM
    return (x_mm, y_mm, largeur_mm, hauteur)


# ---------------------------------------------------------------------------
# Symboles
# ---------------------------------------------------------------------------


def _dessiner_symbole(planche, entree, x, y, largeur, hauteur) -> None:
    symbole = getattr(entree, "symbole", "surface") or "surface"
    _SYMBOLES.get(symbole, _surface)(planche, entree.style, x, y, largeur, hauteur)


def _surface(planche, style, x, y, largeur, hauteur) -> None:
    """Un aplat bordé : pistes, plateformes, postes, citernes."""
    planche.ajouter_rectangle(x, y, largeur, hauteur, style)


def _ligne(planche, style, x, y, largeur, hauteur) -> None:
    """Un linéaire : limite de parcelle, paddock, portail d'exploitation."""
    milieu = y + hauteur / 2.0
    planche.ajouter_ligne(x, milieu, x + largeur, milieu, style)


def _cloture(planche, style, x, y, largeur, hauteur) -> None:
    """Un grillage sur ses poteaux, vu en élévation.

    C'est ainsi que la clôture se lit sur une planche : un fil courant et des
    poteaux réguliers, et non un rectangle plein.
    """
    haut = y + hauteur * 0.25
    bas = y + hauteur * 0.85
    fin = Style(trait=style.trait, epaisseur_mm=0.22, remplissage="none")
    planche.ajouter_ligne(x, haut, x + largeur, haut, style)
    planche.ajouter_ligne(x, bas, x + largeur, bas, fin)
    for index in range(4):
        abscisse = x + largeur * index / 3.0
        planche.ajouter_ligne(abscisse, haut - 0.5, abscisse, bas, style)


def _portail(planche, style, x, y, largeur, hauteur) -> None:
    """Deux vantaux entre leurs poteaux, comme sur le dossier de référence."""
    haut = y + hauteur * 0.2
    bas = y + hauteur * 0.9
    montant = Style(trait=style.trait, epaisseur_mm=0.35, remplissage="none")
    barreau = Style(trait=style.trait, epaisseur_mm=0.15, remplissage="none")

    # Les deux poteaux d'ancrage, plus hauts que les vantaux.
    for abscisse in (x, x + largeur):
        planche.ajouter_ligne(abscisse, y, abscisse, bas + 0.3, montant)
    # Les deux vantaux, avec leurs barreaux.
    for vantail in range(2):
        gauche = x + vantail * largeur / 2.0
        droite = gauche + largeur / 2.0
        planche.ajouter_rectangle(
            gauche, haut, largeur / 2.0 - 0.15, bas - haut, montant
        )
        for index in range(1, 3):
            abscisse = gauche + (droite - gauche) * index / 3.0
            planche.ajouter_ligne(abscisse, haut, abscisse, bas, barreau)


def _vegetation(planche, style, x, y, largeur, hauteur) -> None:
    """Une bande plantée, bosselée : haie ou alignement d'arbres."""
    planche.ajouter_rectangle(x, y + hauteur * 0.35, largeur, hauteur * 0.65, style)
    houppier = Style(
        trait=style.trait, epaisseur_mm=0.25, remplissage=style.remplissage
    )
    for index in range(4):
        largeur_touffe = largeur / 4.0
        planche.ajouter_rectangle(
            x + index * largeur_touffe + 0.25,
            y + hauteur * 0.1,
            largeur_touffe - 0.5,
            hauteur * 0.5,
            houppier,
        )


def _tirete(planche, style, x, y, largeur, hauteur) -> None:
    """Un contour tireté, sans remplissage : zone évitée, limite de paddock."""
    planche.ajouter_rectangle(x, y + 0.4, largeur, hauteur - 0.8, style)


#: Symboles disponibles. Le nom est porté par la catégorie, dans `palette.py`.
_SYMBOLES = {
    "surface": _surface,
    "ligne": _ligne,
    "cloture": _cloture,
    "portail": _portail,
    "vegetation": _vegetation,
    "tirete": _tirete,
}

SYMBOLES_CONNUS = tuple(_SYMBOLES)
