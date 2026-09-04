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
    union_valide,
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

    panneau_gauche = (zone_x, zone_y, LARGEUR_REPERAGE_MM, zone_h)
    x_droite = zone_x + LARGEUR_REPERAGE_MM + INTERVALLE_PANNEAUX_MM
    panneau_droit = (x_droite, zone_y, zone_x + zone_l - x_droite, zone_h)

    echelle_ouvrages = _dessiner_ouvrages(planche, blocs, panneau_droit)
    echelle_reperage, messages = _plan_de_reperage(
        planche, contrat, panneau_gauche, zone_x, zone_y, zone_l, zone_h,
        categories,
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


def _dessiner_ouvrages(planche: Planche, blocs, panneau) -> int:
    """Dispose les blocs d'ouvrages, tous à la même échelle.

    Une planche, une échelle pour ses ouvrages : elle est calée sur le plus
    grand d'entre eux (D2) et inscrite au cartouche. Les vues s'écoulent de
    gauche à droite et reviennent à la ligne quand la largeur est prise ;
    c'est ce qui permet de loger sept vues d'un poste sans les rétrécir.
    """
    x, y, largeur, hauteur = panneau
    hauteur_utile = hauteur - HAUTEUR_ENTETE_MM

    denominateur = None
    for candidat in sorted(ECHELLES_OUVRAGES):
        if _hauteur_disposition(blocs, candidat, largeur) <= hauteur_utile:
            denominateur = candidat
            break
    if denominateur is None:
        plus_grand = max(
            (v.largeur_m for bloc in blocs for v in bloc.vues), default=0.0
        )
        raise ErreurComposition(
            f"Les {sum(len(b.vues) for b in blocs)} vues d'ouvrages ne tiennent "
            f"pas dans {largeur:.0f} x {hauteur_utile:.0f} mm, même au "
            f"1:{max(ECHELLES_OUVRAGES)} — le plus grand ouvrage mesure "
            f"{plus_grand:.1f} m. Répartissez les ouvrages sur une planche de "
            "plus."
        )

    mention_echelle(
        planche, x, y + 3.5, denominateur, titre="Ouvrages techniques"
    )

    curseur_y = y + HAUTEUR_ENTETE_MM
    for bloc in blocs:
        haut_cadre = curseur_y
        planche.ajouter_texte(
            x + JEU_CADRE_MM, curseur_y + 3.4, bloc.titre,
            taille=7.5 * PT, gras=True,
        )
        curseur_y += HAUTEUR_TITRE_BLOC_MM
        curseur_y = _disposer_vues(
            planche, bloc, denominateur, x + JEU_CADRE_MM, curseur_y,
            largeur - 2 * JEU_CADRE_MM,
        )
        if bloc.caracteristiques:
            utile = largeur - 2 * JEU_CADRE_MM
            lignes = _lignes_de_vues(bloc, denominateur, utile)
            if _place_pour_caracteristiques(bloc, lignes, denominateur, utile):
                prise = sum(
                    v.largeur_m * 1000.0 / denominateur
                    + MARGE_VUE_MM
                    + ESPACEMENT_VUES_MM
                    for v in lignes[-1]
                )
                _bloc_caracteristiques(
                    planche,
                    bloc.caracteristiques,
                    x + JEU_CADRE_MM + prise,
                    curseur_y - _hauteur_derniere_ligne(lignes, denominateur) - 2.0,
                )
            else:
                curseur_y = _bloc_caracteristiques(
                    planche, bloc.caracteristiques, x + JEU_CADRE_MM, curseur_y
                )
        # Le cadre est tracé une fois la hauteur du bloc connue.
        planche.ajouter_rectangle(
            x, haut_cadre, largeur, curseur_y - haut_cadre + JEU_CADRE_MM,
            Style(trait="#8a8a8a", epaisseur_mm=0.25, remplissage="none"),
        )
        curseur_y += ESPACEMENT_VUES_MM + JEU_CADRE_MM
    return denominateur


def _place_pour_caracteristiques(bloc, lignes, denominateur, largeur_mm) -> bool:
    """Reste-t-il de quoi écrire les caractéristiques à droite des vues ?"""
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


def _hauteur_disposition(blocs, denominateur: int, largeur_mm: float) -> float:
    """Hauteur qu'occuperaient tous les blocs à cette échelle."""
    total = 0.0
    for bloc in blocs:
        total += HAUTEUR_TITRE_BLOC_MM + 2 * JEU_CADRE_MM
        lignes = _lignes_de_vues(bloc, denominateur, largeur_mm - 2 * JEU_CADRE_MM)
        for ligne in lignes:
            hauteur_ligne = max(
                v.hauteur_m * 1000.0 / denominateur for v in ligne
            )
            total += hauteur_ligne + MARGE_VUE_MM + HAUTEUR_TITRE_VUE_MM
        if bloc.caracteristiques and not _place_pour_caracteristiques(
            bloc, lignes, denominateur, largeur_mm - 2 * JEU_CADRE_MM
        ):
            total += 3.0 + 3.6 * len(bloc.caracteristiques)
        total += ESPACEMENT_VUES_MM
    return total


def _disposer_vues(planche, bloc, denominateur, x, y, largeur_mm) -> float:
    curseur_y = y
    for ligne in _lignes_de_vues(bloc, denominateur, largeur_mm):
        hauteur_ligne = max(v.hauteur_m * 1000.0 / denominateur for v in ligne)
        curseur_x = x
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
        curseur_y += hauteur_ligne + MARGE_VUE_MM + HAUTEUR_TITRE_VUE_MM
    return curseur_y


def _hauteur_derniere_ligne(lignes, denominateur: int) -> float:
    return max(v.hauteur_m * 1000.0 / denominateur for v in lignes[-1])


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


def _zone_reperee(contrat: Contrat, categories, emprise):
    """Emprise à cadrer : les ouvrages de la planche, élargis, dans la clôture.

    Le dossier de référence ne remet pas tout le plan de masse sur ses planches
    d'ouvrages : il zoome sur la zone concernée. Sur un site de 5 ha, un poste
    de 12 x 3 m au 1/5 000 mesure 2,4 mm et ne se repère pas.

    Le cadrage se resserre seulement si la zone reste petite devant le site :
    la clôture ou les portails courent sur toute l'emprise, et il n'y a alors
    rien à resserrer.
    """
    ouvrages = []
    for categorie in categories:
        ouvrages.extend(contrat.geometries(categorie))
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
        if any(cadre.intersects(g) for g in geometries):
            visibles.append((categorie, [g for g in geometries if cadre.intersects(g)]))
    return visibles


def _plan_de_reperage(
    planche, contrat, panneau, zone_x, zone_y, zone_l, zone_h, categories
):
    """L'emprise repérée et ses ouvrages, dans le panneau de gauche.

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
    # La légende est construite sur le cadre demandé ; elle sera reprise sur la
    # fenêtre réellement affichée une fois l'échelle connue.
    entrees = construire_legende(
        [c for c, _ in _categories_visibles(contrat, cadre, avertissements)]
    )
    hauteur_legende = hauteur_bloc(len(entrees))

    minx, miny, maxx, maxy = cadre.bounds
    largeur_m = max(maxx - minx, 1.0)
    hauteur_m = max(maxy - miny, 1.0)

    hauteur_plan = panneau_h - HAUTEUR_ENTETE_MM - hauteur_legende - 3.0
    if hauteur_plan <= 20.0:
        raise ErreurComposition(
            f"Plan de repérage DP 4 : la légende occupe {hauteur_legende:.0f} mm "
            f"du panneau de {panneau_h:.0f} mm et il ne reste plus de place "
            "pour le plan."
        )
    denominateur = echelle_du_dessin(
        largeur_m,
        hauteur_m,
        (panneau_x, panneau_y + HAUTEUR_ENTETE_MM, panneau_l, hauteur_plan),
        ECHELLES_REPERAGE,
        marge=0.02,
        libelle="plan de repérage DP 4",
    )
    if denominateur not in ECHELLES_REPERAGE_BRIEF:
        avertissements.append(
            f"Plan de repérage DP 4 dessiné au 1:{denominateur}, hors de la "
            f"liste retenue ({', '.join('1:' + str(e) for e in ECHELLES_REPERAGE_BRIEF)}) : "
            f"la zone repérée mesure {largeur_m:.0f} x {hauteur_m:.0f} m et ne "
            "tient dans le panneau à aucune d'entre elles. L'échelle est portée "
            "en clair sur la planche."
        )
    planche.definir_echelle(denominateur)

    centre_zone_mm = (zone_x + zone_l / 2.0, zone_y + zone_h / 2.0)
    centre_plan_mm = (
        panneau_x + panneau_l / 2.0,
        panneau_y + HAUTEUR_ENTETE_MM + hauteur_plan / 2.0,
    )
    facteur = denominateur / 1000.0
    centre_cadre = ((minx + maxx) / 2.0, (miny + maxy) / 2.0)

    planche.centrer_sur(
        (
            centre_cadre[0] + (centre_zone_mm[0] - centre_plan_mm[0]) * facteur,
            centre_cadre[1] + (centre_plan_mm[1] - centre_zone_mm[1]) * facteur,
        )
    )

    mention_echelle(
        planche, panneau_x, panneau_y + 3.5, denominateur,
        titre="Plan de repérage" + (" — zone concernée" if resserre else ""),
    )

    # Le contenu cartographique n'est découpé que sur la zone de dessin
    # entière : sans découpe, la clôture d'un site de 5 ha traversait le
    # panneau des ouvrages et passait par-dessus la légende. La fenêtre du
    # panneau est donc calculée en Lambert 93, et chaque géométrie y est
    # recoupée avant d'être tracée.
    fenetre = box(
        centre_cadre[0] - panneau_l * facteur / 2.0,
        centre_cadre[1] - hauteur_plan * facteur / 2.0,
        centre_cadre[0] + panneau_l * facteur / 2.0,
        centre_cadre[1] + hauteur_plan * facteur / 2.0,
    )
    tracees = []
    for categorie, geometries in _categories_visibles(
        contrat, fenetre, avertissements
    ):
        style = STYLES[categorie].style
        dessine = False
        for geometrie in geometries:
            visible = geometrie.intersection(fenetre)
            if visible.is_empty:
                continue
            planche.ajouter_geometrie(visible, style)
            dessine = True
        if dessine:
            tracees.append(categorie)

    # Le bloc de légende, et non des lignes de rappel : voir l'en-tête du
    # module. Il ne porte que ce que la fenêtre montre.
    dessiner_legende(
        planche,
        construire_legende(tracees),
        position=(panneau_x, panneau_y + panneau_h - hauteur_legende - 1.0),
        largeur_mm=panneau_l,
    )
    return denominateur, avertissements


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


def _bloc_volume(cote, libelle: str, categorie: str) -> BlocOuvrage:
    """Un ouvrage parallélépipédique : plan de toiture, élévations, coupe.

    C'est la présentation du dossier de référence pour un poste : la toiture
    vue de dessus, les quatre faces, et une coupe où une silhouette donne
    l'échelle.
    """
    longueur = cote.longueur_m
    largeur = cote.largeur_m
    hauteur = cote.hauteur_m
    style = _style_ouvrage(categorie)

    def plan(dessin: Dessin) -> None:
        dessin.rectangle(0.0, 0.0, longueur, largeur, style)
        # Sens de pente de la toiture, marqué par une flèche simple.
        dessin.ligne((longueur * 0.25, largeur / 2.0), (longueur * 0.75, largeur / 2.0), TRAIT_FIN)
        _coter_rectangle(dessin, longueur, largeur)

    def elevation_long(porte: bool):
        def tracer(dessin: Dessin) -> None:
            sol_hachure(dessin, [(-0.6, 0.0), (longueur + 0.6, 0.0)], epaisseur_mm=1.6)
            dessin.rectangle(0.0, 0.0, longueur, hauteur, style)
            if porte:
                _porte(dessin, longueur * 0.5, hauteur)
            else:
                _grille(dessin, longueur * 0.25, hauteur)
                _grille(dessin, longueur * 0.75, hauteur)
            _coter_rectangle(dessin, longueur, hauteur)

        return tracer

    def pignon(avec_grille: bool):
        def tracer(dessin: Dessin) -> None:
            sol_hachure(dessin, [(-0.6, 0.0), (largeur + 0.6, 0.0)], epaisseur_mm=1.6)
            dessin.rectangle(0.0, 0.0, largeur, hauteur, style)
            if avec_grille:
                _grille(dessin, largeur / 2.0, hauteur)
            _coter_rectangle(dessin, largeur, hauteur)

        return tracer

    def coupe(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.6, 0.0), (largeur + 2.6, 0.0)], epaisseur_mm=1.6)
        dessin.rectangle(0.0, 0.0, largeur, hauteur, TRAIT_FORT)
        # Épaisseur d'enveloppe et niveau de plancher, pour que la coupe se
        # lise comme une coupe et non comme une cinquième élévation.
        dessin.rectangle(0.12, 0.12, largeur - 0.24, hauteur - 0.24, TRAIT_FIN)
        dessin.ligne((0.0, 0.35), (largeur, 0.35), TRAIT_MOYEN)
        silhouette(dessin, largeur + 1.4, 0.0)
        _coter_rectangle(dessin, largeur, hauteur)

    return BlocOuvrage(
        titre=f"{libelle} — {cote.dimensions}",
        vues=[
            Vue("Plan de toiture", longueur, largeur, plan),
            Vue("Élévation long pan (façade)", longueur, hauteur, elevation_long(True)),
            Vue("Élévation long pan (arrière)", longueur, hauteur, elevation_long(False)),
            Vue("Élévation pignon", largeur, hauteur, pignon(True)),
            Vue("Élévation pignon opposé", largeur, hauteur, pignon(False)),
            Vue("Coupe transversale", largeur + 3.0, max(hauteur, 1.9), coupe),
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
    """Élévation de clôture : grillage, poteaux, passage à petite faune."""
    largeur = ESPACEMENT_POTEAUX_M * 3
    hauteur = HAUTEUR_CLOTURE_M
    style = STYLES["cloture"].style

    def tracer(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.4, 0.0), (largeur + 0.4, 0.0)], epaisseur_mm=1.6)
        # Le grillage, figuré par sa trame : c'est ce qui le distingue d'un mur.
        hachurer(
            dessin,
            [(0.0, 0.0), (largeur, 0.0), (largeur, hauteur), (0.0, hauteur)],
            pas_mm=1.1, angle_deg=45.0,
        )
        hachurer(
            dessin,
            [(0.0, 0.0), (largeur, 0.0), (largeur, hauteur), (0.0, hauteur)],
            pas_mm=1.1, angle_deg=-45.0,
        )
        dessin.rectangle(0.0, 0.0, largeur, hauteur, style)
        # Poteaux, tous les 2,50 m.
        nombre = int(round(largeur / ESPACEMENT_POTEAUX_M))
        for index in range(nombre + 1):
            x = index * ESPACEMENT_POTEAUX_M
            dessin.rectangle(x - 0.04, 0.0, 0.08, hauteur, TRAIT_FORT)

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
            f"Grillage soudé, hauteur {nombre_fr(HAUTEUR_CLOTURE_M)} m, "
            f"poteaux tous les {nombre_fr(ESPACEMENT_POTEAUX_M)} m.",
            "Passages à petite faune ménagés au pied de la clôture.",
        ],
    )


def _bloc_portail(largeur_m: float) -> BlocOuvrage:
    """Portail : une élévation et une coupe, largeur depuis le tableau bilan."""
    hauteur = HAUTEUR_PORTAIL_M
    style = STYLES["portail"].style

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
            )
        # Poteaux d'ancrage de part et d'autre.
        for x in (-0.12, largeur_m + 0.04):
            dessin.rectangle(x, 0.0, 0.08, hauteur + 0.1, TRAIT_FORT)
        silhouette(dessin, largeur_m + 0.9, 0.0)
        cote_horizontale(
            dessin, 0.0, largeur_m, -dessin.metres(6.5), f"{nombre_fr(largeur_m)} m"
        )
        cote_verticale(
            dessin, 0.0, hauteur, -dessin.metres(3.5), f"{nombre_fr(hauteur)} m"
        )

    def coupe(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.5, 0.0), (1.1, 0.0)], epaisseur_mm=1.6)
        dessin.rectangle(0.0, 0.0, 0.08, hauteur + 0.1, TRAIT_FORT)
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
    """Double porte d'un poste, en élévation."""
    largeur_porte = min(1.9, hauteur_m * 0.75)
    hauteur_porte = min(2.1, hauteur_m * 0.82)
    dessin.rectangle(
        x_centre - largeur_porte / 2.0, 0.0, largeur_porte, hauteur_porte, TRAIT_MOYEN
    )
    dessin.ligne(
        (x_centre, 0.0), (x_centre, hauteur_porte), TRAIT_FIN
    )


def _grille(dessin: Dessin, x_centre: float, hauteur_m: float) -> None:
    """Grille de ventilation, en élévation."""
    largeur = 0.7
    hauteur = 0.55
    bas = hauteur_m * 0.45
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
