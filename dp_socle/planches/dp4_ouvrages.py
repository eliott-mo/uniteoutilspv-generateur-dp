"""DP 4 — Ouvrages techniques : postes, clôture, portail, citerne.

Chaque planche est partagée en deux : le **plan de repérage** à gauche, les
**dessins d'ouvrages** à droite. Le plan de repérage montre l'emprise clôturée
et ses ouvrages, à sa propre échelle, portée en clair ; les dessins d'ouvrages
partagent l'échelle du cartouche, calée sur le plus grand d'entre eux.

⚠️ Le dossier de référence annote les objets du plan de repérage par des
**lignes de rappel** vers des libellés placés autour du dessin. Ce procédé
n'est **pas** repris : placer automatiquement des libellés sans chevauchement
est un problème de mise en page non résolu, et un libellé mal posé sur une
planche déposée coûte plus cher que le confort qu'il apporte. Le bloc de
légende standard porte exactement la même information, sans ce risque.

**Un ouvrage absent du projet n'a pas de bloc**, et la planche se recompose sur
ce qui reste : si DP 4-2 n'a que la clôture et le portail, les deux blocs
occupent la place.

Les cotes viennent de `cotes_normalisees`, jamais de la géométrie du plan : le
GeoPackage donne une emprise au sol, pas une hauteur. Un ouvrage sans cote
n'est pas dessiné, et son absence est portée au rapport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..contrat import Contrat
from ..dossier import piece
from ..erreurs import ErreurComposition, ErreurCoteOuvrage
from shapely.geometry import box

from ..planche import GRIS, PT, Planche, Style, nombre_fr
from ..projet import Projet
from .commun import Sortie, nouvelle_planche
from .legende import dessiner_legende, hauteur_bloc
from .modules import tracer_trame, trame_du_projet
from .palette import STYLES, construire_legende, objets_a_dessiner
from .standards import (
    ESPACEMENT_POTEAUX_M,
    HAUTEUR_CLOTURE_M,
    HAUTEUR_PORTAIL_M,
    MESSAGE_HAUTEURS,
    PASSAGE_FAUNE_HAUTEUR_M,
    PASSAGE_FAUNE_LARGEUR_M,
)
from .primitives import (
    BLANC_TOURNANT_MM,
    hauteur_titre_cadre,
    TRAIT_COTE,
    TAILLE_COTE,
    TRAIT_FIN,
    TRAIT_FORT,
    TRAIT_MOYEN,
    Dessin,
    cote_horizontale,
    cote_verticale,
    echelle_du_dessin,
    hachurer,
    mention_echelle,
    silhouette,
    sol_hachure,
    sous_cadre,
    union_valide,
    zone_interieure,
)

#: Ouvrages qui reçoivent le traitement complet du dossier de référence :
#: plan de toiture, quatre élévations et une coupe. Ce sont les seuls bâtis
#: du site, et les seuls dont le volume compte à l'instruction.
POSTES = ("pdl_ptr", "ptr", "pdl")

#: Répartition des ouvrages sur les planches, décidée au brief. La troisième
#: n'existe que si le projet porte les ouvrages qu'elle loge.
REPARTITION = {
    "DP 4-1": ("pdl_ptr", "ptr", "pdl"),
    "DP 4-2": ("cloture", "portail", "bache_incendie"),
    "DP 4-3": (
        "bess",
        "local_technique",
        "bac_retention",
        "citerne_refroidissement",
        "aire_aspiration",
    ),
}

#: Échelles autorisées (décision D2).
ECHELLES_OUVRAGES = (50, 100, 200)

#: Échelles du plan de repérage. Les quatre premières sont celles du brief ;
#: les suivantes sont une extension, et leur emploi est signalé au rapport.
#:
#: Mesuré le 04/09/2026 sur la sortie réelle de Sarnois : l'emprise clôturée y
#: fait 327 x 264 m, soit 327 x 264 mm au 1/1 000 — la zone de dessin d'un A3
#: entier mesure 410 x 268 mm. Le plan de repérage y remplirait donc la
#: planche à lui seul, et il n'y aurait plus de place pour les dessins
#: d'ouvrages que la même planche doit porter. Aucune des quatre échelles du
#: brief ne tient dans un demi-A3 pour un site de 5 ha, et c'est la taille
#: courante de nos projets.
#:
#: Plutôt que de refuser de produire DP 4 sur un site réel, ou de rogner le
#: plan en silence, la liste est prolongée et le dépassement est écrit au
#: rapport. L'échelle retenue est de toute façon portée en clair à côté du
#: dessin : le lecteur sait toujours à quelle échelle il lit.
ECHELLES_REPERAGE_BRIEF = (200, 300, 500, 1000)
ECHELLES_REPERAGE = ECHELLES_REPERAGE_BRIEF + (1500, 2000, 2500, 5000)

#: Marge autour des ouvrages repérés, en fraction de leur emprise. Le plan de
#: repérage cadre sur **la zone concernée** et non sur tout le site : c'est ce
#: que fait le dossier de référence, et c'est ce qui rend un poste de 12 x 3 m
#: visible sur un site de 5 ha. La marge donne le contexte qui permet de situer
#: la zone dans la clôture.
MARGE_REPERAGE = 0.55

#: Part de l'emprise clôturée en deçà de laquelle le cadrage se resserre. Au
#: delà, la zone concernée couvre déjà presque tout le site et le resserrement
#: n'apporte rien.
PART_MAXIMALE_ZOOM = 0.45

#: Partage de la planche : le plan de repérage à gauche, les ouvrages à droite.
LARGEUR_REPERAGE_MM = 140.0
INTERVALLE_PANNEAUX_MM = 6.0

#: Épaisseur du filet encadrant chaque bloc d'ouvrage, et jeu intérieur.
#: Le dossier de référence structure sa planche en cadres : chaque ouvrage a le
#: sien, et l'œil ne confond pas deux séries de vues voisines.
JEU_CADRE_MM = 2.0

#: Place d'un titre de vue et de ses cotes autour du dessin, en millimètres.
#:
#: Ces valeurs sont serrées à dessein. Les échelles autorisées vont du simple
#: au double : trois millimètres de marge de trop sur une planche font passer
#: tous ses ouvrages du 1/100 au 1/200, et une clôture de 7,50 m y tombe à
#: 37 mm avec un passage à petite faune de moins d'un millimètre. Mesuré le
#: 04/09/2026 sur DP 4-2 du site d'essai.
HAUTEUR_TITRE_VUE_MM = 4.0
MARGE_VUE_MM = 10.0
ESPACEMENT_VUES_MM = 3.5
HAUTEUR_TITRE_BLOC_MM = 5.0

#: Hauteur réservée au titre et à l'échelle en tête du panneau de droite.
HAUTEUR_ENTETE_MM = 11.0

#: Hauteurs standard UNITe, absentes du contrat : voir `standards.py`, qui
#: porte leur justification et le message qui les accompagne au rapport.
MESSAGE_HAUTEURS_STANDARD = MESSAGE_HAUTEURS

#: Figuré d'un poste préfabriqué, relevé sur les élévations du dossier de
#: Massay du 17/04/2025 et sur la planche type UNITe.
#:
#: Un poste n'est pas un parallélépipède nu : sa toiture déborde des murs, il
#: repose sur un socle de 0,3 à 0,5 m, et sa teinte est un RAL, pas une couleur
#: de légende. La couleur de la légende sert au plan de masse, où elle repère
#: l'ouvrage parmi d'autres ; l'élévation, elle, montre l'ouvrage tel qu'il
#: sera, et le dossier de référence l'écrit sur le dessin : « RAL 6003 ».
COULEUR_POSTE = "#4b573e"
COULEUR_TOITURE = "#585d51"
COULEUR_SOCLE = "#cfcbc2"
REFERENCE_RAL = "RAL 6003"

DEBORD_TOITURE_M = 0.16
EPAISSEUR_TOITURE_M = 0.14
#: Le dossier de référence cote le socle « 0,3 à 0,5 m » : c'est une
#: fourchette de pose, pas une cote. On dessine la valeur basse et on écrit la
#: fourchette, comme lui.
HAUTEUR_SOCLE_M = 0.30
HAUTEUR_SOCLE_MAX_M = 0.50

LARGEUR_LEGENDE_MM = 62.0

#: Largeur qu'il faut laisser libre à droite de la dernière ligne de vues pour
#: y écrire les caractéristiques d'un ouvrage plutôt que sous le dessin.
#:
#: C'est la disposition du dossier de référence, et elle rend la planche
#: possible : mesuré sur Sarnois le 04/09/2026, les cinq blocs de sa DP 4-3
#: prenaient 87 mm rien qu'en caractéristiques posées sous les vues, et la
#: planche débordait de 40 mm.
LARGEUR_CARACTERISTIQUES_MM = 52.0


# ---------------------------------------------------------------------------
# Vues et blocs
# ---------------------------------------------------------------------------


@dataclass
class Vue:
    """Un dessin d'ouvrage, avec l'encombrement qu'il réclame en mètres."""

    titre: str
    largeur_m: float
    hauteur_m: float
    tracer: object


@dataclass
class BlocOuvrage:
    """Les vues d'un même ouvrage, présentées ensemble."""

    titre: str
    vues: list = field(default_factory=list)
    #: Lignes de caractéristiques affichées à côté des vues.
    caracteristiques: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Planche
# ---------------------------------------------------------------------------


def ouvrages_de(contrat: Contrat, code: str) -> list:
    """Catégories de la planche que le projet porte réellement."""
    return [c for c in REPARTITION[code] if contrat.presente(c)]


def planches_necessaires(contrat: Contrat) -> list:
    """Codes des planches DP 4 à produire pour ce dossier.

    Un projet sans poste n'a pas de DP 4-1 ; un projet sans BESS ni local
    technique n'a pas de DP 4-3. La planche n'est pas produite vide, et le
    rang des suivantes suit.
    """
    return [code for code in REPARTITION if ouvrages_de(contrat, code)]


def generer(
    projet: Projet,
    contrat: Contrat,
    dossier: str | Path,
    code: str,
    numero: str | None = None,
) -> Sortie:
    categories = ouvrages_de(contrat, code)
    if not categories:
        raise ErreurComposition(
            f"{code} : aucun des ouvrages qu'elle porte "
            f"({', '.join(REPARTITION[code])}) n'est au contrat. La planche ne "
            "se produit pas vide."
        )

    avertissements = []
    blocs = []
    for categorie in categories:
        try:
            bloc = _bloc_ouvrage(contrat, categorie, avertissements)
        except ErreurCoteOuvrage as exc:
            avertissements.append(
                f"{code} : « {categorie} » n'est pas dessiné — {exc}"
            )
            continue
        blocs.append(bloc)
    if not blocs:
        raise ErreurComposition(
            f"{code} : aucun ouvrage dessinable. "
            + " ".join(avertissements)
        )

    planche = nouvelle_planche(projet, code, numero=numero)
    zone_x, zone_y, zone_l, zone_h = planche.zone_dessin()

    # Blanc tournant : la planche ne colle rien à son cadre, et laisse le même
    # jeu entre ses deux panneaux.
    utile_x = zone_x + BLANC_TOURNANT_MM
    utile_y = zone_y + BLANC_TOURNANT_MM
    utile_l = zone_l - 2 * BLANC_TOURNANT_MM
    utile_h = zone_h - 2 * BLANC_TOURNANT_MM

    panneau_gauche = (utile_x, utile_y, LARGEUR_REPERAGE_MM, utile_h)
    x_droite = utile_x + LARGEUR_REPERAGE_MM + BLANC_TOURNANT_MM
    panneau_droit = (x_droite, utile_y, utile_x + utile_l - x_droite, utile_h)

    echelle_ouvrages = _dessiner_ouvrages(planche, blocs, panneau_droit)
    echelle_reperage, messages = _plan_de_reperage(
        planche, contrat, panneau_gauche, categories
    )
    avertissements.extend(messages)

    # Le cartouche annonce l'échelle des ouvrages, celle du dessin principal ;
    # le plan de repérage porte la sienne en clair à côté de lui.
    #
    # L'ordre compte : le plan de repérage est cartographique, il a fallu
    # donner son échelle à la planche pour le tracer, et c'est elle qui
    # tomberait au cartouche. Le contenu géographique étant posé, seule reste
    # à corriger la valeur que le cartouche lira.
    planche.echelle = echelle_ouvrages

    chemin = planche.rendre_pdf(
        Path(dossier) / f"DP_{code.split()[1]}_{_nom_fichier(code)}.pdf"
    )
    return Sortie(
        numero=code,
        titre=piece(code).titre,
        chemin=chemin,
        echelle=echelle_ouvrages,
        details={
            "ouvrages": [b.titre for b in blocs],
            "categories": categories,
            "echelle_ouvrages": echelle_ouvrages,
            "echelle_reperage": echelle_reperage,
            "avertissements": avertissements,
        },
    )


def _nom_fichier(code: str) -> str:
    return {
        "DP 4-1": "postes",
        "DP 4-2": "cloture_portail_citerne",
        "DP 4-3": "autres_ouvrages",
    }[code]


# ---------------------------------------------------------------------------
# Panneau de droite : les ouvrages
# ---------------------------------------------------------------------------


def _place_pour_caracteristiques(bloc, lignes, denominateur, largeur_mm) -> bool:
    """Reste-t-il de quoi écrire les caractéristiques à droite des vues ?

    C'est la disposition du dossier de référence, et elle rend la planche
    possible : mesuré sur Sarnois, les cinq blocs de sa DP 4-3 prenaient 87 mm
    rien qu'en caractéristiques posées sous les vues.
    """
    if not bloc.caracteristiques or not lignes:
        return False
    prise = sum(
        vue.largeur_m * 1000.0 / denominateur + MARGE_VUE_MM + ESPACEMENT_VUES_MM
        for vue in lignes[-1]
    )
    return largeur_mm - prise >= LARGEUR_CARACTERISTIQUES_MM


def _lignes_de_vues(bloc: BlocOuvrage, denominateur: int, largeur_mm: float) -> list:
    """Répartit les vues d'un bloc en lignes tenant dans la largeur."""
    lignes, courante, prise = [], [], 0.0
    for vue in bloc.vues:
        largeur_vue = vue.largeur_m * 1000.0 / denominateur + MARGE_VUE_MM
        if courante and prise + largeur_vue > largeur_mm:
            lignes.append(courante)
            courante, prise = [], 0.0
        courante.append(vue)
        prise += largeur_vue + ESPACEMENT_VUES_MM
    if courante:
        lignes.append(courante)
    return lignes


def _hauteur_contenu(bloc, denominateur: int, largeur_mm: float) -> float:
    """Hauteur du contenu d'un bloc, cadre exclu."""
    total = 0.0
    lignes = _lignes_de_vues(bloc, denominateur, largeur_mm)
    for ligne in lignes:
        hauteur_ligne = max(v.hauteur_m * 1000.0 / denominateur for v in ligne)
        total += hauteur_ligne + MARGE_VUE_MM + HAUTEUR_TITRE_VUE_MM
    if bloc.caracteristiques and not _place_pour_caracteristiques(
        bloc, lignes, denominateur, largeur_mm
    ):
        total += 3.0 + 3.6 * len(bloc.caracteristiques)
    return total


def _hauteur_disposition(blocs, denominateur: int, largeur_mm: float) -> float:
    """Hauteur qu'occuperaient tous les blocs, cadres et blancs compris."""
    utile = zone_interieure(0.0, 0.0, largeur_mm, 0.0)[2]
    total = 0.0
    for bloc in blocs:
        total += _hauteur_contenu(bloc, denominateur, utile)
        total += hauteur_titre_cadre() + BLANC_TOURNANT_MM
    return total


def _dessiner_ouvrages(planche: Planche, blocs, panneau) -> int:
    """Dispose les blocs d'ouvrages, chacun dans son sous-cadre.

    Une planche, une échelle pour ses ouvrages : elle est calée sur le plus
    grand d'entre eux (D2) et inscrite au cartouche. Chaque ouvrage a son
    cadre, comme sur le dossier de référence, et ses vues y sont centrées.
    """
    x, y, largeur, hauteur = panneau

    denominateur = None
    for candidat in sorted(ECHELLES_OUVRAGES):
        if _hauteur_disposition(blocs, candidat, largeur) <= hauteur:
            denominateur = candidat
            break
    if denominateur is None:
        plus_grand = max(
            (v.largeur_m for bloc in blocs for v in bloc.vues), default=0.0
        )
        raise ErreurComposition(
            f"Les {sum(len(b.vues) for b in blocs)} vues d'ouvrages ne tiennent "
            f"pas dans {largeur:.0f} x {hauteur:.0f} mm, même au "
            f"1:{max(ECHELLES_OUVRAGES)} — le plus grand ouvrage mesure "
            f"{plus_grand:.1f} m. Répartissez les ouvrages sur une planche de "
            "plus."
        )

    curseur_y = y
    for bloc in blocs:
        utile = zone_interieure(x, curseur_y, largeur, 0.0)
        contenu = _hauteur_contenu(bloc, denominateur, utile[2])
        hauteur_cadre = contenu + hauteur_titre_cadre()
        interieur = sous_cadre(
            planche, x, curseur_y, largeur, hauteur_cadre,
            titre=bloc.titre, echelle=denominateur,
        )
        _disposer_vues(planche, bloc, denominateur, interieur)
        curseur_y += hauteur_cadre + BLANC_TOURNANT_MM
    return denominateur


def _disposer_vues(planche, bloc, denominateur, interieur) -> None:
    """Pose les vues d'un bloc dans son cadre, chaque ligne centrée.

    Tassées à gauche, les vues laissaient un vide à droite du cadre qui se
    lisait comme un oubli.
    """
    x, y, largeur, _ = interieur
    curseur_y = y
    lignes = _lignes_de_vues(bloc, denominateur, largeur)
    a_cote = _place_pour_caracteristiques(bloc, lignes, denominateur, largeur)

    for index, ligne in enumerate(lignes):
        hauteur_ligne = max(v.hauteur_m * 1000.0 / denominateur for v in ligne)
        prise = sum(
            v.largeur_m * 1000.0 / denominateur + MARGE_VUE_MM for v in ligne
        ) + ESPACEMENT_VUES_MM * (len(ligne) - 1)
        derniere = index == len(lignes) - 1
        if derniere and a_cote:
            prise += ESPACEMENT_VUES_MM + LARGEUR_CARACTERISTIQUES_MM
        curseur_x = x + max(0.0, (largeur - prise) / 2.0)

        for vue in ligne:
            largeur_vue = vue.largeur_m * 1000.0 / denominateur
            planche.ajouter_texte(
                curseur_x, curseur_y + 2.6, vue.titre,
                taille=6 * PT, couleur=GRIS,
            )
            dessin = Dessin(
                planche=planche,
                denominateur=denominateur,
                # Le repère de la vue a son origine au pied du dessin. La
                # marge est prise à gauche : c'est là que se posent la cote
                # verticale et son texte.
                origine_mm=(
                    curseur_x + MARGE_VUE_MM,
                    curseur_y + HAUTEUR_TITRE_VUE_MM + hauteur_ligne,
                ),
            )
            vue.tracer(dessin)
            curseur_x += largeur_vue + MARGE_VUE_MM + ESPACEMENT_VUES_MM

        if derniere and a_cote:
            _bloc_caracteristiques(
                planche, bloc.caracteristiques, curseur_x,
                curseur_y + HAUTEUR_TITRE_VUE_MM,
            )
        curseur_y += hauteur_ligne + MARGE_VUE_MM + HAUTEUR_TITRE_VUE_MM

    if bloc.caracteristiques and not a_cote:
        _bloc_caracteristiques(planche, bloc.caracteristiques, x, curseur_y)


def _bloc_caracteristiques(planche, lignes, x, y) -> float:
    """Caractéristiques en clair, comme sur la planche de citerne de référence."""
    curseur = y + 3.0
    for ligne in lignes:
        planche.ajouter_texte(x + 1.0, curseur, ligne, taille=6.5 * PT)
        curseur += 3.6
    return curseur


# ---------------------------------------------------------------------------
# Panneau de gauche : le plan de repérage
# ---------------------------------------------------------------------------


def _tracer_tables(planche, contrat, tables, fenetre, avertissements) -> None:
    """Trame des modules sur les tables du plan de repérage.

    Même reconstruction que sur le plan de masse : le plan du bureau d'études
    ne descend pas au module, la trame vient du tableau bilan.
    """
    from ..erreurs import ErreurDP
    from .dp3_coupes import geometrie_table

    try:
        table, _ = geometrie_table(contrat)
        rampant = table.rampant_m
    except ErreurDP:
        rampant = None
    visibles = [g for g in tables if fenetre.intersects(g)]
    trame, _raison = trame_du_projet(contrat, contrat.geometries("tables_pv"), rampant)
    if trame is None:
        return
    tracer_trame(
        planche, visibles, trame, STYLES["tables_pv"].style,
        planche.transformation.mm_par_metre, fenetre=fenetre,
    )


def _tracer_decoupe(planche, geometrie, style, fenetre) -> bool:
    """Trace une géométrie recoupée sur la fenêtre, sans refermer son contour.

    Découper un polygone sur la fenêtre le **referme le long du bord** : la
    clôture d'un site plus grand que le zoom y gagnait un trait rouge droit au
    ras du cadre, qui se lisait comme une limite de projet alors que ce n'est
    que le bord du dessin.

    Le remplissage et le filet sont donc tracés séparément : la surface est
    bien coupée à la fenêtre — il faut bien qu'elle s'arrête — mais le filet ne
    suit que le contour réel de l'objet, recoupé lui aussi.
    """
    tracee = False
    remplissage = style.remplissage
    if remplissage and remplissage != "none":
        surface = geometrie.intersection(fenetre)
        if not surface.is_empty:
            planche.ajouter_geometrie(
                surface,
                Style(trait=None, epaisseur_mm=0.0, remplissage=remplissage,
                      opacite_remplissage=style.opacite_remplissage),
            )
            tracee = True

    contour = geometrie.boundary if geometrie.geom_type != "LineString" else geometrie
    visible = contour.intersection(fenetre)
    if not visible.is_empty:
        planche.ajouter_geometrie(
            visible,
            Style(trait=style.trait, epaisseur_mm=style.epaisseur_mm,
                  remplissage="none", tirets=style.tirets),
        )
        tracee = True
    return tracee


#: Catégories qui courent sur tout le site et ne peuvent donc pas commander un
#: cadrage resserré.
#:
#: La clôture ceint l'emprise entière : cadrer dessus revient à cadrer sur le
#: site, et la planche des citernes se retrouvait au 1:2 000 alors que sa
#: citerne mesure 8 m. Elle est donc écartée du calcul de la zone, mais reste
#: dessinée — c'est elle qui situe les ouvrages dans le projet.
CATEGORIES_ETENDUES = ("cloture", "portail", "portail_exploitant", "limite_paddock")


def _zone_reperee(contrat: Contrat, categories, emprise):
    """Emprise à cadrer : les ouvrages décrits par la planche, élargis.

    Le dossier de référence ne remet pas tout le plan de masse sur ses planches
    d'ouvrages : il zoome sur la zone concernée. Sur un site de 5 ha, un poste
    de 12 x 3 m au 1/5 000 mesure 2,4 mm et ne se repère pas.

    Les ouvrages qui courent sur tout le site — la clôture, les portails — ne
    commandent pas le cadrage : sinon la planche qui les décrit revient au plan
    de masse entier. Le zoom se fait alors sur les autres ouvrages de la
    planche, et à défaut sur toute l'emprise.
    """
    locales = [c for c in categories if c not in CATEGORIES_ETENDUES]
    ouvrages = []
    for categorie in locales:
        ouvrages.extend(contrat.geometries(categorie))
    if not ouvrages:
        # Une planche qui ne décrit que des ouvrages étendus se cadre sur le
        # site : c'est bien lui qu'elle montre.
        return emprise, False

    zone = union_valide(ouvrages)
    if zone is None or zone.is_empty:
        return emprise, False

    minx, miny, maxx, maxy = zone.bounds
    largeur = max(maxx - minx, 1.0)
    hauteur = max(maxy - miny, 1.0)
    e_minx, e_miny, e_maxx, e_maxy = emprise.bounds
    part = max(
        largeur / max(e_maxx - e_minx, 1.0), hauteur / max(e_maxy - e_miny, 1.0)
    )
    if part > PART_MAXIMALE_ZOOM:
        return emprise, False

    marge = MARGE_REPERAGE * max(largeur, hauteur)
    return box(minx - marge, miny - marge, maxx + marge, maxy + marge), True


def _categories_visibles(contrat: Contrat, cadre, avertissements) -> list:
    """Catégories qui tombent dans le cadre du plan de repérage.

    La légende ne porte que ce que le zoom montre : sur une planche cadrée sur
    le poste, une entrée « bac d'équarrissage » situé à 200 m ferait chercher
    sur le dessin un objet qui n'y est pas.
    """
    visibles = []
    for categorie, geometries in objets_a_dessiner(contrat, avertissements):
        retenues = [g for g in geometries if cadre.intersects(g)]
        if retenues:
            visibles.append((categorie, retenues))
    return visibles


def _plan_de_reperage(planche, contrat, panneau, categories):
    """L'emprise repérée et ses ouvrages, dans un sous-cadre à gauche.

    Le moteur centre la carte sur la zone de dessin entière. Pour qu'elle tombe
    dans le panneau de gauche, c'est le centre terrain qu'on décale, du même
    écart converti à l'échelle : la transformation n'est pas détournée, on lui
    donne un autre centre.
    """
    panneau_x, panneau_y, panneau_l, panneau_h = panneau
    avertissements = []

    emprise = union_valide(contrat.geometries("cloture"))
    if emprise is None or emprise.is_empty:
        return None, [
            "Aucune clôture au contrat : le plan de repérage de DP 4 n'a pas "
            "d'emprise à montrer."
        ]

    cadre, resserre = _zone_reperee(contrat, categories, emprise)
    minx, miny, maxx, maxy = cadre.bounds
    largeur_m = max(maxx - minx, 1.0)
    hauteur_m = max(maxy - miny, 1.0)
    centre_cadre = ((minx + maxx) / 2.0, (miny + maxy) / 2.0)

    interieur = zone_interieure(panneau_x, panneau_y, panneau_l, panneau_h)
    interieur_x, interieur_y, interieur_l, interieur_h = interieur

    # La place de la légende et l'échelle du plan se commandent l'une l'autre :
    # une légende plus haute laisse moins de place au plan, donc une échelle
    # plus petite, donc une fenêtre plus large, donc peut-être plus de
    # catégories à porter en légende. Deux passes suffisent à converger, et on
    # retient la hauteur la plus grande rencontrée.
    hauteur_legende = hauteur_bloc(1)
    denominateur = None
    fenetre = None
    visibles = []
    for _ in range(3):
        hauteur_plan = interieur_h - hauteur_legende - BLANC_TOURNANT_MM
        if hauteur_plan <= 20.0:
            raise ErreurComposition(
                f"Plan de repérage DP 4 : la légende occupe "
                f"{hauteur_legende:.0f} mm du panneau de {interieur_h:.0f} mm "
                "et il ne reste plus de place pour le plan."
            )
        denominateur = echelle_du_dessin(
            largeur_m, hauteur_m,
            (interieur_x, interieur_y, interieur_l, hauteur_plan),
            ECHELLES_REPERAGE, marge=0.02, libelle="plan de repérage DP 4",
        )
        facteur = denominateur / 1000.0
        fenetre = box(
            centre_cadre[0] - interieur_l * facteur / 2.0,
            centre_cadre[1] - hauteur_plan * facteur / 2.0,
            centre_cadre[0] + interieur_l * facteur / 2.0,
            centre_cadre[1] + hauteur_plan * facteur / 2.0,
        )
        visibles = _categories_visibles(contrat, fenetre, avertissements)
        besoin = hauteur_bloc(len(construire_legende([c for c, _ in visibles])))
        if besoin <= hauteur_legende:
            break
        hauteur_legende = besoin

    if denominateur not in ECHELLES_REPERAGE_BRIEF:
        avertissements.append(
            f"Plan de repérage DP 4 dessiné au 1:{denominateur}, hors de la "
            f"liste retenue ({', '.join('1:' + str(e) for e in ECHELLES_REPERAGE_BRIEF)}) : "
            f"la zone repérée mesure {largeur_m:.0f} x {hauteur_m:.0f} m et ne "
            "tient dans le panneau à aucune d'entre elles. L'échelle est portée "
            "en clair sur la planche."
        )

    sous_cadre(
        planche, panneau_x, panneau_y, panneau_l, panneau_h,
        titre="Plan de repérage" + (" — zone concernée" if resserre else ""),
        echelle=denominateur,
    )

    planche.definir_echelle(denominateur)
    centre_zone_mm = _centre_zone(planche)
    centre_plan_mm = (
        interieur_x + interieur_l / 2.0,
        interieur_y + hauteur_plan / 2.0,
    )
    facteur = denominateur / 1000.0
    planche.centrer_sur(
        (
            centre_cadre[0] + (centre_zone_mm[0] - centre_plan_mm[0]) * facteur,
            centre_cadre[1] + (centre_plan_mm[1] - centre_zone_mm[1]) * facteur,
        )
    )

    # Le contenu cartographique n'est découpé que sur la zone de dessin
    # entière : sans découpe, la clôture d'un site de 5 ha traversait le
    # panneau des ouvrages et passait par-dessus la légende.
    for categorie, geometries in visibles:
        style = STYLES[categorie].style
        for geometrie in geometries:
            _tracer_decoupe(planche, geometrie, style, fenetre)
        if categorie == "tables_pv":
            _tracer_tables(planche, contrat, geometries, fenetre, avertissements)

    entrees = construire_legende([c for c, _ in visibles])
    dessiner_legende(
        planche,
        entrees,
        position=(
            interieur_x,
            interieur_y + interieur_h - hauteur_bloc(len(entrees)),
        ),
        largeur_mm=interieur_l,
    )
    return denominateur, avertissements


def _centre_zone(planche: Planche) -> tuple:
    """Centre de la zone de dessin, sur lequel le moteur centre la carte."""
    x, y, largeur, hauteur = planche.zone_dessin()
    return (x + largeur / 2.0, y + hauteur / 2.0)


# ---------------------------------------------------------------------------
# Dessins d'ouvrages
# ---------------------------------------------------------------------------


def _bloc_ouvrage(contrat: Contrat, categorie: str, avertissements: list) -> BlocOuvrage:
    if categorie == "cloture":
        avertissements.append(MESSAGE_HAUTEURS_STANDARD)
        return _bloc_cloture()
    if categorie == "portail":
        largeur = contrat.generalites.get("largeur_portails_m")
        if not largeur:
            raise ErreurCoteOuvrage(
                "Largeur de portail absente de `parametres.generalites` : "
                "l'élévation du portail n'est pas dessinée."
            )
        if MESSAGE_HAUTEURS_STANDARD not in avertissements:
            avertissements.append(MESSAGE_HAUTEURS_STANDARD)
        return _bloc_portail(float(largeur))

    surface = _surface_au_sol(contrat, categorie)
    cote = contrat.cote_de_categorie(categorie, surface_m2=surface)
    if not cote.a_hauteur:
        # Une aire d'aspiration est une surface, pas un volume : le tableau
        # bilan lui donne « 8 x 4 m », en longueur x largeur, et rien d'autre.
        # La dessiner en élévation demanderait une hauteur qu'elle n'a pas ;
        # elle se dessine en plan, ce qui la décrit entièrement.
        return _bloc_surface(cote, STYLES[categorie].libelle, categorie)
    if categorie in POSTES:
        return _bloc_volume(cote, STYLES[categorie].libelle, categorie)
    # Tout le reste — citernes, conteneurs BESS, bacs, local technique — est
    # un équipement posé, pas un bâtiment : deux vues et ses caractéristiques
    # le décrivent entièrement.
    #
    # Le traitement complet du poste, sept vues, n'y est ni utile ni tenable :
    # mesuré sur Sarnois le 04/09/2026, les six équipements de sa DP 4-3
    # faisaient 21 vues qui ne tenaient pas sur la planche, même au 1:200. Le
    # dossier de référence lui-même ne détaille que le poste, qui est le seul
    # ouvrage bâti visible du site.
    return _bloc_equipement(cote, STYLES[categorie].libelle, categorie)


def _surface_au_sol(contrat: Contrat, categorie: str) -> float | None:
    """Surface au sol du plus grand objet d'une catégorie, pour choisir sa cote."""
    aires = [e.geometrie.area for e in contrat.entites(categorie) if e.geometrie.area > 0]
    return max(aires) if aires else None


def _style_ouvrage(categorie: str) -> Style:
    fond = STYLES[categorie].style
    return Style(
        trait=fond.trait or "#000000",
        epaisseur_mm=0.3,
        remplissage=fond.remplissage,
    )


def _style_poste() -> Style:
    return Style(trait="#2f3529", epaisseur_mm=0.25, remplissage=COULEUR_POSTE)


def _toiture(dessin: Dessin, largeur_m: float, hauteur_m: float) -> None:
    """Dalle de toiture, débordant des murs de part et d'autre."""
    dessin.rectangle(
        -DEBORD_TOITURE_M,
        hauteur_m,
        largeur_m + 2 * DEBORD_TOITURE_M,
        EPAISSEUR_TOITURE_M,
        Style(trait="#2f3529", epaisseur_mm=0.25, remplissage=COULEUR_TOITURE),
    )


def _socle(dessin: Dessin, largeur_m: float) -> None:
    """Socle de pose, entre le sol et le bas des parois."""
    dessin.rectangle(
        -0.10, 0.0, largeur_m + 0.20, HAUTEUR_SOCLE_M,
        Style(trait="#8a8578", epaisseur_mm=0.2, remplissage=COULEUR_SOCLE),
    )


def _elevation_poste(largeur_m: float, hauteur_m: float, ouvertures,
                     coter_socle: bool = False):
    """Une face de poste : socle, parois, toiture débordante et ouvertures.

    `ouvertures` est une suite de (type, fraction de la largeur), le type
    valant « porte » ou « grille ».
    """

    def tracer(dessin: Dessin) -> None:
        sol_hachure(
            dessin, [(-0.9, 0.0), (largeur_m + 0.9, 0.0)], epaisseur_mm=1.8
        )
        _socle(dessin, largeur_m)
        dessin.rectangle(
            0.0, HAUTEUR_SOCLE_M, largeur_m, hauteur_m, _style_poste()
        )
        for nature, fraction in ouvertures:
            abscisse = largeur_m * fraction
            if nature == "porte":
                _porte(dessin, abscisse, hauteur_m)
            else:
                _grille(dessin, abscisse, hauteur_m)
        _toiture(dessin, largeur_m, hauteur_m + HAUTEUR_SOCLE_M)

        cote_horizontale(
            dessin, 0.0, largeur_m, -dessin.metres(6.5),
            f"{nombre_fr(largeur_m)} m",
        )
        cote_verticale(
            dessin, HAUTEUR_SOCLE_M, HAUTEUR_SOCLE_M + hauteur_m,
            -dessin.metres(3.0), f"{nombre_fr(hauteur_m)} m",
        )
        # La fourchette du socle, écrite comme sur le dossier de référence.
        # Portée par une seule vue : répétée sur les quatre, elle débordait sur
        # la vue voisine et n'apprenait rien de plus.
        if coter_socle:
            dessin.texte(
                largeur_m / 2.0, 0.0,
                f"socle {nombre_fr(HAUTEUR_SOCLE_M, 1)} à "
                f"{nombre_fr(HAUTEUR_SOCLE_MAX_M, 1)} m",
                taille=5.5 * PT, ancre="middle", decalage_mm=(0.0, 5.0),
            )

    return tracer


def _bloc_volume(cote, libelle: str, categorie: str) -> BlocOuvrage:
    """Un poste préfabriqué : plan de toiture, quatre élévations, coupe.

    C'est la présentation du dossier de référence pour le seul ouvrage bâti du
    site : la toiture vue de dessus, les quatre faces, et une coupe où une
    silhouette donne l'échelle.
    """
    longueur = cote.longueur_m
    largeur = cote.largeur_m
    hauteur = cote.hauteur_m

    def plan(dessin: Dessin) -> None:
        # La toiture vue de dessus déborde des murs : c'est elle qu'on voit.
        dessin.rectangle(
            -DEBORD_TOITURE_M, -DEBORD_TOITURE_M,
            longueur + 2 * DEBORD_TOITURE_M, largeur + 2 * DEBORD_TOITURE_M,
            Style(trait="#2f3529", epaisseur_mm=0.25, remplissage=COULEUR_TOITURE),
        )
        dessin.rectangle(0.0, 0.0, longueur, largeur, TRAIT_FIN)
        # Sens de pente de la toiture.
        dessin.ligne(
            (longueur * 0.3, largeur / 2.0), (longueur * 0.7, largeur / 2.0),
            TRAIT_FIN,
        )
        _coter_rectangle(dessin, longueur, largeur)

    def coupe(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.9, 0.0), (largeur + 3.2, 0.0)], epaisseur_mm=1.8)
        _socle(dessin, largeur)
        # Une coupe montre l'enveloppe et le vide intérieur, pas un aplat.
        dessin.rectangle(0.0, HAUTEUR_SOCLE_M, largeur, hauteur, TRAIT_FORT)
        dessin.rectangle(
            0.14, HAUTEUR_SOCLE_M + 0.14, largeur - 0.28, hauteur - 0.28,
            TRAIT_FIN,
        )
        _toiture(dessin, largeur, hauteur + HAUTEUR_SOCLE_M)
        silhouette(dessin, largeur + 1.7, 0.0, pleine=False)
        cote_verticale(
            dessin, HAUTEUR_SOCLE_M, HAUTEUR_SOCLE_M + hauteur,
            -dessin.metres(3.0), f"{nombre_fr(hauteur)} m",
        )

    hauteur_vue = hauteur + HAUTEUR_SOCLE_M + EPAISSEUR_TOITURE_M
    return BlocOuvrage(
        titre=f"{libelle} — {cote.dimensions}",
        vues=[
            Vue("Plan de toiture", longueur, largeur, plan),
            Vue(
                "Élévation long pan (façade)", longueur, hauteur_vue,
                _elevation_poste(
                    longueur, hauteur, [("porte", 0.5)], coter_socle=True
                ),
            ),
            Vue(
                "Élévation long pan (arrière)", longueur, hauteur_vue,
                _elevation_poste(
                    longueur, hauteur, [("grille", 0.25), ("grille", 0.75)]
                ),
            ),
            Vue(
                "Élévation pignon", largeur, hauteur_vue,
                _elevation_poste(largeur, hauteur, [("grille", 0.5)]),
            ),
            Vue(
                "Élévation pignon opposé", largeur, hauteur_vue,
                _elevation_poste(largeur, hauteur, []),
            ),
            Vue("Coupe transversale", largeur + 3.4, max(hauteur_vue, 2.1), coupe),
        ],
        caracteristiques=[
            f"Poste préfabriqué, teinte {REFERENCE_RAL}.",
            f"Dimensions hors tout : {cote.dimensions}.",
            f"Socle de {nombre_fr(HAUTEUR_SOCLE_M, 1)} à "
            f"{nombre_fr(HAUTEUR_SOCLE_MAX_M, 1)} m.",
        ],
    )


def _bloc_surface(cote, libelle: str, categorie: str) -> BlocOuvrage:
    """Un ouvrage plan : une vue de dessus cotée, et rien de plus.

    L'aire d'aspiration du SDIS est une aire de stationnement pour l'engin
    pompe : elle n'a pas d'élévation, et le tableau bilan ne lui donne que
    deux dimensions.
    """
    longueur = cote.longueur_m
    largeur = cote.largeur_m
    style = _style_ouvrage(categorie)

    def dessus(dessin: Dessin) -> None:
        dessin.rectangle(0.0, 0.0, longueur, largeur, style)
        _coter_rectangle(dessin, longueur, largeur)

    return BlocOuvrage(
        titre=f"{libelle} — {cote.dimensions}",
        vues=[Vue("Vue en plan", longueur, largeur, dessus)],
        caracteristiques=[
            f"Aire de {nombre_fr(longueur)} x {nombre_fr(largeur)} m, "
            "sans ouvrage en élévation.",
        ],
    )


def _bloc_equipement(cote, libelle: str, categorie: str) -> BlocOuvrage:
    """Équipement posé : vue de dessus, vue de face, caractéristiques en clair.

    C'est la présentation de la citerne du dossier de référence, étendue à
    tous les équipements : un conteneur BESS, un bac de rétention ou un local
    technique se décrivent par leur emprise, leur hauteur hors sol et leurs
    deux vues.
    """
    longueur = cote.longueur_m
    largeur = cote.largeur_m
    hauteur = cote.hauteur_m
    style = _style_ouvrage(categorie)

    def dessus(dessin: Dessin) -> None:
        dessin.rectangle(0.0, 0.0, longueur, largeur, style)
        dessin.rectangle(0.35, 0.35, longueur - 0.7, largeur - 0.7, TRAIT_FIN)
        _coter_rectangle(dessin, longueur, largeur)

    def face(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.6, 0.0), (longueur + 0.6, 0.0)], epaisseur_mm=1.6)
        dessin.rectangle(0.0, 0.0, longueur, hauteur, style)
        _coter_rectangle(dessin, longueur, hauteur)

    # Le volume d'une citerne incendie est écrit à la fin de son libellé de
    # catalogue (« Citerne incendie — 120 ») ; les autres équipements n'en ont
    # pas, et c'est leur désignation qui les identifie.
    fin_du_libelle = cote.ouvrage.rsplit("—", 1)[-1].strip()
    caracteristiques = [
        f"Volume : {fin_du_libelle} m³"
        if fin_du_libelle.isdigit()
        else f"Type : {cote.ouvrage}",
        f"Hauteur hors sol : {nombre_fr(hauteur)} m",
        f"Longueur : {nombre_fr(longueur)} m",
        f"Largeur : {nombre_fr(largeur)} m",
    ]
    return BlocOuvrage(
        titre=f"{libelle} — {cote.dimensions}",
        vues=[
            Vue("Vue de dessus", longueur, largeur, dessus),
            Vue("Vue de face", longueur, max(hauteur, 1.0), face),
        ],
        caracteristiques=caracteristiques,
    )


def _bloc_cloture() -> BlocOuvrage:
    """Élévation de clôture : grillage, poteaux, passage à petite faune.

    Comme pour le poste, l'élévation montre l'ouvrage tel qu'il sera — grillage
    rigide teinte RAL 6003 — et non la couleur rouge qui le repère au plan.
    """
    largeur = ESPACEMENT_POTEAUX_M * 3
    hauteur = HAUTEUR_CLOTURE_M
    style = Style(trait=COULEUR_POSTE, epaisseur_mm=0.3, remplissage="none")

    def tracer(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.4, 0.0), (largeur + 0.4, 0.0)], epaisseur_mm=1.6)
        # Le grillage, figuré par sa trame : c'est ce qui le distingue d'un mur.
        # Grillage rigide : une trame croisée serrée, qui se lit comme un
        # treillis et non comme une hachure de coupe.
        maille = Style(trait=COULEUR_POSTE, epaisseur_mm=0.08, remplissage="none")
        contour = [(0.0, 0.0), (largeur, 0.0), (largeur, hauteur), (0.0, hauteur)]
        hachurer(dessin, contour, pas_mm=0.8, angle_deg=90.0, style=maille)
        hachurer(dessin, contour, pas_mm=0.8, angle_deg=0.0, style=maille)
        dessin.rectangle(0.0, 0.0, largeur, hauteur, style)
        # Poteaux, tous les 2,50 m.
        nombre = int(round(largeur / ESPACEMENT_POTEAUX_M))
        montant = Style(
            trait=COULEUR_POSTE, epaisseur_mm=0.25, remplissage=COULEUR_POSTE
        )
        for index in range(nombre + 1):
            x = index * ESPACEMENT_POTEAUX_M
            dessin.rectangle(x - 0.05, 0.0, 0.10, hauteur + 0.06, montant)

        # Passage à petite faune, au pied de la clôture.
        x_passage = ESPACEMENT_POTEAUX_M * 1.5 - PASSAGE_FAUNE_LARGEUR_M / 2.0
        dessin.rectangle(
            x_passage, 0.0, PASSAGE_FAUNE_LARGEUR_M, PASSAGE_FAUNE_HAUTEUR_M,
            Style(trait="#000000", epaisseur_mm=0.3, remplissage="#ffffff"),
        )
        dessin.texte(
            x_passage + PASSAGE_FAUNE_LARGEUR_M / 2.0, 0.0,
            f"Passage petite faune {nombre_fr(PASSAGE_FAUNE_LARGEUR_M * 100, 0)} x "
            f"{nombre_fr(PASSAGE_FAUNE_HAUTEUR_M * 100, 0)} cm",
            taille=5.5 * PT, ancre="middle", decalage_mm=(0.0, 4.6),
        )

        cote_verticale(
            dessin, 0.0, hauteur, -dessin.metres(3.0), f"{nombre_fr(hauteur)} m"
        )
        cote_horizontale(
            dessin, 0.0, ESPACEMENT_POTEAUX_M, hauteur + dessin.metres(4.0),
            f"{nombre_fr(ESPACEMENT_POTEAUX_M)} m",
        )

    return BlocOuvrage(
        titre="Clôture du projet solaire",
        vues=[Vue("Élévation", largeur, hauteur + 1.2, tracer)],
        caracteristiques=[
            f"Grillage métal rigide, teinte {REFERENCE_RAL}.",
            f"Hauteur {nombre_fr(HAUTEUR_CLOTURE_M)} m, montants tous les "
            f"{nombre_fr(ESPACEMENT_POTEAUX_M)} m.",
            "Passages adaptés à la petite faune au pied de la clôture.",
        ],
    )


def _bloc_portail(largeur_m: float) -> BlocOuvrage:
    """Portail : une élévation et une coupe, largeur depuis le tableau bilan."""
    hauteur = HAUTEUR_PORTAIL_M
    style = Style(trait=COULEUR_POSTE, epaisseur_mm=0.3, remplissage="none")

    def elevation(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.5, 0.0), (largeur_m + 0.5, 0.0)], epaisseur_mm=1.6)
        for vantail in range(2):
            x = vantail * largeur_m / 2.0
            dessin.rectangle(x, 0.0, largeur_m / 2.0, hauteur, style)
            hachurer(
                dessin,
                [
                    (x + 0.06, 0.06), (x + largeur_m / 2.0 - 0.06, 0.06),
                    (x + largeur_m / 2.0 - 0.06, hauteur - 0.06), (x + 0.06, hauteur - 0.06),
                ],
                pas_mm=1.4, angle_deg=90.0,
                style=Style(trait=COULEUR_POSTE, epaisseur_mm=0.12,
                            remplissage="none"),
            )
        # Poteaux d'ancrage de part et d'autre.
        montant = Style(
            trait=COULEUR_POSTE, epaisseur_mm=0.25, remplissage=COULEUR_POSTE
        )
        for x in (-0.14, largeur_m + 0.04):
            dessin.rectangle(x, 0.0, 0.10, hauteur + 0.12, montant)
        silhouette(dessin, largeur_m + 0.9, 0.0, pleine=False)
        cote_horizontale(
            dessin, 0.0, largeur_m, -dessin.metres(6.5), f"{nombre_fr(largeur_m)} m"
        )
        cote_verticale(
            dessin, 0.0, hauteur, -dessin.metres(3.5), f"{nombre_fr(hauteur)} m"
        )

    def coupe(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.5, 0.0), (1.1, 0.0)], epaisseur_mm=1.6)
        dessin.rectangle(
            0.0, 0.0, 0.10, hauteur + 0.12,
            Style(trait=COULEUR_POSTE, epaisseur_mm=0.25,
                  remplissage=COULEUR_POSTE),
        )
        # Massif d'ancrage, sous le sol.
        dessin.rectangle(-0.18, -0.6, 0.44, 0.6, TRAIT_FIN)
        dessin.ligne((0.08, hauteur * 0.5), (0.6, hauteur * 0.5), style)
        cote_verticale(
            dessin, 0.0, hauteur, -dessin.metres(3.5), f"{nombre_fr(hauteur)} m"
        )

    return BlocOuvrage(
        titre=f"Portail d'accès — {nombre_fr(largeur_m)} m",
        vues=[
            Vue("Élévation", largeur_m + 2.4, hauteur + 1.4, elevation),
            Vue("Coupe sur poteau", 1.8, hauteur + 1.4, coupe),
        ],
        caracteristiques=[
            f"Portail double battant, teinte {REFERENCE_RAL}.",
            f"Largeur {nombre_fr(largeur_m)} m, hauteur "
            f"{nombre_fr(hauteur)} m.",
        ],
    )


# ---------------------------------------------------------------------------
# Détails de dessin
# ---------------------------------------------------------------------------


def _coter_rectangle(dessin: Dessin, largeur_m: float, hauteur_m: float) -> None:
    """Les deux cotes d'une vue rectangulaire, hors du dessin."""
    # La cote horizontale passe sous la bande de sol hachurée des élévations,
    # dans laquelle elle venait sinon s'écrire.
    cote_horizontale(
        dessin, 0.0, largeur_m, -dessin.metres(6.5), f"{nombre_fr(largeur_m)} m"
    )
    cote_verticale(
        dessin, 0.0, hauteur_m, -dessin.metres(3.0), f"{nombre_fr(hauteur_m)} m"
    )


def _porte(dessin: Dessin, x_centre: float, hauteur_m: float) -> None:
    """Double porte d'un poste, en élévation, posée sur le socle."""
    largeur_porte = min(1.9, hauteur_m * 0.75)
    hauteur_porte = min(2.1, hauteur_m * 0.82)
    gauche = x_centre - largeur_porte / 2.0
    dessin.rectangle(
        gauche, HAUTEUR_SOCLE_M, largeur_porte, hauteur_porte, TRAIT_MOYEN
    )
    dessin.ligne(
        (x_centre, HAUTEUR_SOCLE_M),
        (x_centre, HAUTEUR_SOCLE_M + hauteur_porte),
        TRAIT_FIN,
    )
    # Les deux poignées, au tiers de la hauteur.
    for cote in (-1, 1):
        abscisse = x_centre + cote * 0.09
        dessin.ligne(
            (abscisse, HAUTEUR_SOCLE_M + hauteur_porte * 0.45),
            (abscisse, HAUTEUR_SOCLE_M + hauteur_porte * 0.55),
            TRAIT_MOYEN,
        )


def _grille(dessin: Dessin, x_centre: float, hauteur_m: float) -> None:
    """Grille de ventilation, en élévation, posée sur le socle."""
    largeur = 0.7
    hauteur = 0.55
    bas = HAUTEUR_SOCLE_M + hauteur_m * 0.45
    dessin.rectangle(x_centre - largeur / 2.0, bas, largeur, hauteur, TRAIT_FIN)
    hachurer(
        dessin,
        [
            (x_centre - largeur / 2.0, bas),
            (x_centre + largeur / 2.0, bas),
            (x_centre + largeur / 2.0, bas + hauteur),
            (x_centre - largeur / 2.0, bas + hauteur),
        ],
        pas_mm=0.6, angle_deg=0.0,
    )
