"""Composition commune aux planches photographiques DP 6, DP 7 et DP 8 (lot 6).

Les trois pièces ont la même forme, relevée le 10/09/2026 sur le dossier de
référence : les images empilées dans une colonne à droite, le plan de repérage
des prises de vue dans la colonne de gauche. Seul change ce qu'elles montrent —
un point de vue décliné en deux ou trois volets pour DP 6, une ou deux
photographies distinctes pour DP 7 et DP 8.

DES EMPLACEMENTS IDENTIQUES, ET LA PHOTO QUI S'Y AJUSTE
--------------------------------------------------------
La planche porte un nombre d'emplacements **fixé par la pièce** — trois volets
pour DP 6, deux photographies pour DP 7 et DP 8 — tous de mêmes dimensions. Des
photographies de rapports différents ne donnent donc plus des cadres de tailles
différentes, et un emplacement qui reste vide ne redistribue rien : la planche
d'un dossier ressemble à celle du suivant.

Chaque photographie est **rognée** pour remplir son emplacement, jamais
déformée ni bordée de blanc. Le rognage se fait au centre par défaut, et
`ImagePlanche.cadrage` permet de le décaler quand le sujet n'est pas centré.

LE FORMAT EST CELUI DE L'EMPLACEMENT, ET LE CHEF DE PROJET CHOISIT CE QU'IL GARDE
---------------------------------------------------------------------------------
Trois emplacements empilés sur une A3 paysage imposent un format de **3,11:1**,
deux emplacements **1,92:1**. Ce sont les bandeaux du dossier de référence, et
c'est ce format que les images prennent.

Le lot 6 avait d'abord retenu l'inverse — le rapport **médian des images** — pour
une raison mesurée le 16/09/2026 et qui reste vraie : sur trois emplacements, une
photographie d'iPhone y perd 57 % de sa hauteur, un panoramique 2:1 encore 36 %,
et ce qui disparaît est le ciel et le premier plan. Mais le remède était pire :
des photographies d'un même appareil partagent leur rapport, l'emplacement
prenait ce rapport, et la planche ne ressemblait plus au dossier de référence —
une image portrait y occupait une colonne étroite (constaté sur une DP 7
produite le 23/09/2026).

La perte n'est donc pas niée, elle est **rendue choisissable** : le cadrage dit
quelle part de l'image est gardée, et l'écran de saisie montre le cadre sur
l'image entière avant de générer. Au-delà de `ROGNAGE_SIGNALE`, le rapport de
génération dit ce qui a été retiré — une photographie amputée sans un mot est
exactement ce que ce dépôt refuse.

La conséquence pratique, à dire aux chefs de projet : **une insertion paysagère
se photographie en paysage large**, et non en portrait.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..erreurs import ErreurComposition
from ..planche import Planche
from .primitives import (
    BLANC_TOURNANT_MM,
    MARGE_SOUS_CADRE_MM,
    hauteur_titre_cadre,
    repartir_hauteurs,
    sous_cadre,
    zone_interieure,
)
from .reperage_vues import dessiner_points_de_vue, plan_de_reperage

#: Largeur de la colonne d'images, relevée le 10/09/2026 sur Massay.
#:
#: Les images y mesurent 229 mm de large et sont calées à x = 179 mm sur une
#: zone de dessin qui va de 5 à 415. Nous reprenons la largeur ; le calage se
#: déduit du blanc tournant, qui est la marge unique de toutes nos planches.
LARGEUR_COLONNE_IMAGES_MM = 229.0

#: Hauteur minimale d'une image sur la planche. En dessous, une insertion
#: paysagère ne se lit plus : c'est la comparaison avant/après qui fait la
#: pièce, et elle demande de voir le paysage.
HAUTEUR_IMAGE_MINIMALE_MM = 38.0

#: Part rognée au-delà de laquelle le rapport de génération le signale.
ROGNAGE_SIGNALE = 0.12

#: Résolution à laquelle les images sont rééchantillonnées avant d'entrer dans
#: le PDF. Au-delà, le poids du dossier croît sans rien apporter à l'impression :
#: une photographie de 4 000 px dans un cadre de 222 mm porterait du 460 dpi.
DPI_IMAGE = 300


@dataclass(frozen=True)
class ImagePlanche:
    """Une image de la colonne de droite, et le titre de son cadre.

    `cadrage` décale le rognage quand le sujet n'est pas au centre : deux
    fractions dans [-0,5 ; 0,5], horizontale puis verticale, comptées dans le
    sens de lecture — négatif vers la gauche et vers le haut. À zéro, l'image est
    rognée symétriquement.
    """

    chemin: Path
    intitule: str
    cadrage: tuple[float, float] = (0.0, 0.0)


def composer(
    planche: Planche,
    images,
    points_de_vue,
    reperes,
    emprise,
    libelle_reperage: str,
    contrat,
    emplacements: int | None = None,
    fond_ign: bool = True,
    dpi: int | None = None,
) -> dict:
    """Pose la colonne d'images et le plan de repérage sur une planche prête.

    Rend ce que la planche a retenu : l'échelle du repérage, son cadre, et les
    avertissements à porter au rapport de génération. L'appelant garde la main
    sur le cartouche, puisqu'il connaît sa pièce.
    """
    images = list(images)
    emplacements = emplacements or len(images)
    if not images:
        raise ErreurComposition(
            f"{libelle_reperage} : aucune image à porter. Une planche "
            "photographique vide ne se produit pas."
        )

    zone_x, zone_y, zone_l, zone_h = planche.zone_dessin()
    utile_x = zone_x + BLANC_TOURNANT_MM
    utile_y = zone_y + BLANC_TOURNANT_MM
    utile_l = zone_l - 2 * BLANC_TOURNANT_MM
    utile_h = zone_h - 2 * BLANC_TOURNANT_MM

    # La colonne d'images est calée à droite, comme au dossier de référence ; ce
    # qui reste à gauche revient au plan de repérage.
    x_images = utile_x + utile_l - LARGEUR_COLONNE_IMAGES_MM
    largeur_reperage = x_images - BLANC_TOURNANT_MM - utile_x
    if largeur_reperage < 60.0:
        raise ErreurComposition(
            f"{libelle_reperage} : la colonne d'images ne laisse que "
            f"{largeur_reperage:.0f} mm au plan de repérage, où rien ne serait "
            "lisible."
        )

    messages_images = _poser_images(
        planche, images, x_images, utile_y, LARGEUR_COLONNE_IMAGES_MM,
        utile_h, emplacements,
    )

    panneau = (utile_x, utile_y, largeur_reperage, utile_h)
    interieur = _interieur_du_cadre(panneau)
    reperage = plan_de_reperage(points_de_vue, emprise, interieur, libelle_reperage)

    interieur = sous_cadre(
        planche, *panneau, titre="Plan de repérage", echelle=reperage.denominateur
    )
    planche.definir_echelle(reperage.denominateur)
    _centrer_sur_le_panneau(planche, interieur, reperage.centre)

    messages = messages_images + list(reperage.avertissements)
    if fond_ign:
        _poser_fond(planche, interieur, reperage)
    messages.extend(_poser_le_plan(planche, contrat, reperage))
    _poser_emprise(planche, emprise)
    messages.extend(dessiner_points_de_vue(planche, points_de_vue, reperes))
    return {
        "echelle_reperage": reperage.denominateur,
        "cadre_reperage": reperage.cadre,
        "site_entier": reperage.site_entier,
        "avertissements": messages,
    }


def _interieur_du_cadre(panneau) -> tuple:
    """Place que le sous-cadre laisse à son contenu, connue avant de le tracer.

    Le choix d'échelle a besoin de cette zone, et le tracé du cadre a besoin de
    l'échelle pour l'inscrire à son titre : il faut donc pouvoir calculer l'une
    sans avoir posé l'autre. C'est ce que `zone_interieure` fait au lot 4.
    """
    return zone_interieure(*panneau)


def _centrer_sur_le_panneau(planche: Planche, interieur, centre_cadre) -> None:
    """Recentre la carte sur le panneau de gauche plutôt que sur la planche.

    Le moteur centre la carte sur la zone de dessin entière. Pour qu'elle tombe
    dans le panneau, c'est le **centre terrain** qu'on décale, du même écart
    converti à l'échelle : la transformation n'est pas détournée, on lui donne
    un autre centre. Repris tel quel du plan de repérage de DP 4, y compris
    l'inversion de l'axe vertical — le papier descend, le terrain monte.
    """
    zone_x, zone_y, zone_l, zone_h = planche.zone_dessin()
    interieur_x, interieur_y, interieur_l, interieur_h = interieur
    centre_zone = (zone_x + zone_l / 2.0, zone_y + zone_h / 2.0)
    centre_panneau = (
        interieur_x + interieur_l / 2.0,
        interieur_y + interieur_h / 2.0,
    )
    facteur = planche.echelle / 1000.0
    planche.centrer_sur(
        (
            centre_cadre[0] + (centre_zone[0] - centre_panneau[0]) * facteur,
            centre_cadre[1] + (centre_panneau[1] - centre_zone[1]) * facteur,
        )
    )


def _poser_fond(planche: Planche, interieur, reperage) -> None:
    """Plan IGN v2 sous le repérage, demandé à la fenêtre du seul panneau.

    Le plan de repérage du dossier de référence est vectoriel et porte les
    lieux-dits ; le Plan IGN v2 porte les mêmes toponymes, et c'est ce qui situe
    une prise de vue pour un instructeur qui ne connaît pas la commune.

    La fenêtre demandée est celle du **panneau**, non de la planche : un fond
    couvrant toute la zone de dessin passerait sous la colonne d'images, pour
    plusieurs mégaoctets invisibles.
    """
    from ..ign import COUCHE_PLAN, DPI_DEFAUT, telecharger_fond

    _, _, interieur_l, interieur_h = interieur
    facteur = planche.echelle / 1000.0
    centre = reperage.centre
    fenetre = (
        centre[0] - interieur_l * facteur / 2.0,
        centre[1] - interieur_h * facteur / 2.0,
        centre[0] + interieur_l * facteur / 2.0,
        centre[1] + interieur_h * facteur / 2.0,
    )
    fond = telecharger_fond(
        COUCHE_PLAN, fenetre, interieur_l, interieur_h,
        dpi=DPI_DEFAUT, format_image="image/jpeg",
    )
    planche.ajouter_fond_raster(fond.image, fond.bbox)


def _poser_le_plan(planche: Planche, contrat, reperage) -> list:
    """Le plan de masse sous les repères : tables, pistes, postes, clôture.

    « Avec juste le contour du site on ne se rend pas bien compte de ce qu'on
    regarde » (retour d'usage du 23/09/2026). Le plan de repérage du dossier de
    référence porte l'implantation entière ; le nôtre n'avait que l'emprise, et
    un contour seul ne dit ni où sont les rangées ni par où l'on entre.

    Les objets viennent de `objets_a_dessiner`, comme pour DP 2 et pour les
    plans de repérage du lot 4 : une règle appliquée à deux endroits finit par
    y différer, et c'est à cela que sert ce point d'entrée unique.

    La **trame des modules** n'est pas reprise, elle. DP 2 la trace au 1/2 000
    pour faire lire une table comme un panneau ; ici l'échelle va jusqu'au
    1/10 000, où ses traits se confondraient en un aplat tout en pesant leur
    poids dans le PDF. Le contour des rangées suffit à la lecture.
    """
    from shapely.geometry import box

    from .palette import STYLES, objets_a_dessiner

    messages: list[str] = []
    if contrat is None:
        # Jamais en silence : sans contrat la planche sort avec le seul contour
        # du site, et c'est précisément ce que l'usage a signalé comme
        # insuffisant. L'appelant qui ne le passe pas doit le lire au rapport.
        return [
            "Plan de repérage dessiné sans le plan de masse : aucun contrat ne "
            "lui a été transmis. Seul le contour du site y figure."
        ]
    cadre = box(*reperage.cadre)
    for categorie, geometries in objets_a_dessiner(contrat, messages):
        style = STYLES[categorie].style
        for geometrie in geometries:
            # Hors cadre : le plan de repérage se cadre sur le site et ses
            # points de vue, pas sur les abords lointains du plan du BE.
            if cadre.intersects(geometrie):
                planche.ajouter_geometrie(geometrie, style)
    return messages


def _poser_emprise(planche: Planche, emprise) -> None:
    """L'emprise du site sous les repères, dans la couleur des autres planches."""
    from ..planche import STYLE_EMPRISE

    planche.ajouter_geometrie(emprise, STYLE_EMPRISE)


def _poser_images(
    planche: Planche, images, x_mm: float, y_mm: float, largeur_mm: float,
    hauteur_mm: float, emplacements: int,
) -> list:
    """Empile les images dans des emplacements identiques, et rend les messages.

    `emplacements` est fixé par la pièce, non par le nombre d'images reçues :
    une DP 6 sans mesures paysagères garde ses trois emplacements et en laisse
    un vide, plutôt que d'étirer les deux autres.
    """
    if len(images) > emplacements:
        raise ErreurComposition(
            f"{len(images)} images pour {emplacements} emplacement(s) sur la "
            "planche."
        )
    rapports = [_rapport(image.chemin) for image in images]
    habillage = hauteur_titre_cadre()
    largeur_utile = largeur_mm - 2 * MARGE_SOUS_CADRE_MM

    blancs = BLANC_TOURNANT_MM * (emplacements - 1)
    hauteur_cadre = (hauteur_mm - blancs) / emplacements
    hauteur_image = hauteur_cadre - habillage
    if hauteur_image < HAUTEUR_IMAGE_MINIMALE_MM:
        raise ErreurComposition(
            f"{emplacements} emplacements sur une même planche réduiraient "
            f"chaque image à {hauteur_image:.0f} mm de haut, sous les "
            f"{HAUTEUR_IMAGE_MINIMALE_MM:.0f} mm où une insertion paysagère cesse "
            "de se lire."
        )

    # Le format de l'emplacement, et non celui des images : c'est le bandeau du
    # dossier de référence, et il ne dépend pas de ce qu'on y dépose. Voir
    # l'en-tête du module pour ce que ce choix coûte, et comment il se règle.
    largeur_image = largeur_utile
    largeur_cadre = largeur_image + 2 * MARGE_SOUS_CADRE_MM
    x_cadre = x_mm + (largeur_mm - largeur_cadre) / 2.0

    messages = []
    ordonnee = y_mm
    for image, rapport in zip(images, rapports):
        sous_cadre(planche, x_cadre, ordonnee, largeur_cadre, hauteur_cadre,
                   titre=image.intitule)
        perte = _poser_une_image(
            planche, image,
            x_cadre + MARGE_SOUS_CADRE_MM, ordonnee + habillage - MARGE_SOUS_CADRE_MM,
            largeur_image, hauteur_image,
        )
        if perte > ROGNAGE_SIGNALE:
            cote = "de sa largeur" if 1.0 / rapport > largeur_image / hauteur_image else "de sa hauteur"
            messages.append(
                f"« {Path(image.chemin).name} » a été rognée de {perte:.0%} "
                f"{cote} pour remplir son emplacement. Déposez-la au format des "
                "autres vues si ce recadrage retire ce qu'il fallait montrer."
            )
        ordonnee += hauteur_cadre + BLANC_TOURNANT_MM
    return messages


def _poser_une_image(planche: Planche, image: ImagePlanche, x_mm: float,
                     y_mm: float, largeur_mm: float, hauteur_mm: float) -> float:
    """Rogne l'image au format du cadre, l'y pose, et rend la part retirée.

    Le rognage se fait ici plutôt que dans le moteur : `Planche.ajouter_image_mm`
    appartient au lot 1, qui ne se touche pas. L'image recadrée transite par un
    fichier temporaire, lu immédiatement puis effacé — elle n'a pas à survivre à
    la planche.
    """
    import tempfile

    from PIL import Image

    with Image.open(image.chemin) as source:
        recadree, perte = _recadrer(
            source, largeur_mm / hauteur_mm, image.cadrage, hauteur_mm
        )
    with tempfile.TemporaryDirectory() as dossier:
        chemin = Path(dossier) / "recadree.jpg"
        recadree.save(chemin, "JPEG", quality=88, optimize=True)
        planche.ajouter_image_mm(chemin, x_mm, y_mm, largeur_mm, hauteur_mm)
    return perte


def fenetre_de_cadrage(taille: tuple, rapport_cible: float, cadrage: tuple):
    """Part de l'image que la planche garde, et part qu'elle retire.

    Rend `((gauche, haut, droite, bas), perte)`, en pixels de l'image d'origine.

    **Un seul calcul, pour la planche et pour l'écran.** L'écran de saisie
    dessine ce cadre sur l'image entière pour que le chef de projet voie ce
    qu'il garde ; s'il le recalculait de son côté, les deux finiraient par
    montrer des choses différentes — c'est ce qui est arrivé aux deux listes de
    types de voirie, le 19/09/2026.

    Le rognage ne touche qu'un axe : la largeur d'une photographie plus
    panoramique que son emplacement, sa hauteur sinon.
    """
    largeur, hauteur = taille
    if largeur / hauteur > rapport_cible:
        # Plus panoramique que le cadre : on retire de la largeur.
        gardee = hauteur * rapport_cible
        perte = 1.0 - gardee / largeur
        depart = (largeur - gardee) * (0.5 + _borne(cadrage[0]))
        return (depart, 0.0, depart + gardee, float(hauteur)), perte
    gardee = largeur / rapport_cible
    perte = 1.0 - gardee / hauteur
    depart = (hauteur - gardee) * (0.5 + _borne(cadrage[1]))
    return (0.0, depart, float(largeur), depart + gardee), perte


def rapport_de_l_emplacement(planche: Planche, emplacements: int) -> float:
    """Le bandeau qu'impose la planche, largeur sur hauteur.

    L'écran de saisie en a besoin pour dessiner le bon cadre avant de générer :
    c'est le format que la photographie prendra, et il ne dépend pas d'elle.
    """
    _, _, _, zone_h = planche.zone_dessin()
    hauteur_utile = zone_h - 2 * BLANC_TOURNANT_MM
    blancs = BLANC_TOURNANT_MM * (emplacements - 1)
    hauteur_image = (hauteur_utile - blancs) / emplacements - hauteur_titre_cadre()
    if hauteur_image <= 0:
        raise ErreurComposition(
            f"{emplacements} emplacements ne laissent aucune hauteur d'image."
        )
    return (LARGEUR_COLONNE_IMAGES_MM - 2 * MARGE_SOUS_CADRE_MM) / hauteur_image


def _recadrer(source, rapport_cible: float, cadrage: tuple, hauteur_mm: float):
    """Image rognée au rapport voulu, et part retirée à son plus grand côté.

    Rééchantillonnée au passage à `DPI_IMAGE` : une photographie de 4 000 px dans
    un cadre de 222 mm porterait du 460 dpi, que l'impression ne rend pas et que
    le PDF paie au poids.
    """
    from PIL import Image

    boite, perte = fenetre_de_cadrage(source.size, rapport_cible, cadrage)
    image = source.crop(tuple(int(round(valeur)) for valeur in boite))
    # Aplatir une éventuelle transparence sur blanc AVANT la conversion : un
    # convert("RGB") direct remplirait de noir.
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        fond = Image.new("RGBA", image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(fond, image)
    image = image.convert("RGB")

    hauteur_px = max(1, int(round(hauteur_mm / 25.4 * DPI_IMAGE)))
    if image.height > hauteur_px:
        image = image.resize(
            (max(1, int(round(hauteur_px * rapport_cible))), hauteur_px),
            Image.LANCZOS,
        )
    return image, perte


def _borne(valeur: float) -> float:
    """Décalage de cadrage ramené dans [-0,5 ; 0,5]."""
    return max(-0.5, min(0.5, float(valeur)))


def _rapport(chemin) -> float:
    """Hauteur sur largeur de l'image, pour dimensionner son cadre."""
    from PIL import Image

    try:
        with Image.open(chemin) as image:
            largeur, hauteur = image.size
    except OSError as erreur:
        raise ErreurComposition(
            f"« {Path(chemin).name} » ne s'ouvre pas comme une image ({erreur})."
        ) from erreur
    if not largeur or not hauteur:
        raise ErreurComposition(
            f"« {Path(chemin).name} » n'a pas de dimensions exploitables."
        )
    return hauteur / largeur
