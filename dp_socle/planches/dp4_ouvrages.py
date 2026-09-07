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

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..contrat import Contrat
from ..dossier import piece
from ..erreurs import ErreurComposition, ErreurCoteOuvrage, ErreurService
from shapely.geometry import box

from ..ign import telecharger_parcelles
from ..planche import GRIS, PT, STYLE_PARCELLE, Planche, Style, nombre_fr
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
    forme_pleine,
    hachurer,
    mention_echelle,
    repartir_hauteurs,
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

#: Ouvrages qui sont des conteneurs maritimes, et se dessinent comme tels :
#: tôle nervurée, cadre à longerons, portes à barres de condamnation, pose sur
#: plots. Le dossier de référence leur consacre une planche chacun.
CONTENEURS = ("bess", "local_technique")

#: Ouvrages qui sont des citernes : cuve à angles arrondis, vue de dessus avec
#: son trop-plein et ses trappes, vue de face bombée.
CITERNES = ("bache_incendie", "citerne_refroidissement")

#: Ouvrages livrés en teinte de catalogue, dessinés à leur RAL sur les
#: élévations : conteneurs et citernes, comme les postes et la clôture.
TEINTE_RAL = CONTENEURS + CITERNES

#: Ouvrages dont la façade n'apprend rien de plus dès qu'un autre du même genre
#: est déjà décrit dans le dossier, et le second qui les couvre.
#:
#: Une citerne est une citerne : même cuve, mêmes congés, même vue de face, à
#: la cote près — et les cotes sont écrites au bloc de caractéristiques comme
#: au tableau bilan. Décidé à la relecture du 05/09/2026. Les deux restent
#: dessinées et repérées au plan de masse : c'est leur planche de façade qui
#: fait double emploi, pas leur existence.
REDONDANTS = {"citerne_refroidissement": "bache_incendie"}

#: Répartition des ouvrages sur les planches, décidée au brief. La troisième
#: n'existe que si le projet porte les ouvrages qu'elle loge.
#:
#: La liste est celle arrêtée à la relecture du 04/09/2026 : postes de
#: livraison, de transformation et combiné, clôture et portail, citernes, local
#: de stockage, conteneur BESS. Ce sont les seuls ouvrages dont une façade
#: apprenne quelque chose à l'instruction.
#:
#: En sont sortis l'aire d'aspiration et le bac de rétention : le premier est
#: un revêtement de sol sans élévation, le second une cuvette au sol. Tous deux
#: restent tracés sur le plan de masse et sur le plan de repérage — ils
#: disparaissent des façades, pas du dossier.
REPARTITION = {
    "DP 4-1": ("pdl_ptr", "ptr", "pdl"),
    "DP 4-2": ("cloture", "portail", "bache_incendie"),
    "DP 4-3": ("bess", "local_technique", "citerne_refroidissement"),
}

#: Échelles autorisées pour les dessins d'ouvrages (décision D2).
ECHELLES_OUVRAGES = (50, 100, 200)

#: Échelle de référence des planches d'ouvrages : celle du dossier HOCH, dont
#: les cartouches portent tous « 1 : 100 ».
#:
#: Chaque ouvrage la reçoit, et n'en descend que s'il n'y tient pas. Deux
#: raisons de ne pas chercher plus grand que le 1:100 : un panneau de clôture de
#: 7,50 m y fait déjà 75 mm, et au 1:50 il écraserait ses voisins ; et une
#: planche dont les cadres mélangeraient trois échelles ne se compare plus.
#:
#: Écart assumé à D2, décidé à la relecture du 05/09/2026. D2 posait **une**
#: échelle par planche : la citerne de 11,7 m tirait alors tout le reste au
#: 1:200, où un conteneur de 6 m mesurait 30 mm. L'échelle se choisit donc
#: maintenant par ouvrage, et chaque sous-cadre porte la sienne en clair — c'est
#: ce que fait le dossier de référence, dont le plan de repérage est au 1:500
#: quand ses élévations sont au 1:100.
ECHELLE_OUVRAGE_PREFEREE = 100

#: Échelles du plan de repérage, en deux listes.
#:
#: Le brief demandait 1:200, 1:300, 1:500 et 1:1 000. Le 1:200 en est écarté à
#: la relecture du 04/09/2026 : à cette échelle le cadre serre les ouvrages de
#: si près qu'on ne les situe plus dans le site, et le zoom cesse d'être un
#: plan de repérage. `ECHELLES_REPERAGE_ADMISES` est donc ce qui reste du
#: brief, et c'est elle qui fait référence : en sortir se signale au rapport.
#:
#: `ECHELLES_REPERAGE` la prolonge pour les grands sites. Mesuré le 04/09/2026
#: sur la sortie réelle de Sarnois : l'emprise clôturée y fait 327 x 264 m,
#: soit 327 x 264 mm au 1/1 000 — la zone de dessin d'un A3 entier mesure
#: 410 x 268 mm. Le plan de repérage y remplirait la planche à lui seul, et il
#: n'y aurait plus de place pour les dessins d'ouvrages que la même planche
#: doit porter. Aucune échelle du brief ne tient dans un demi-A3 pour un site
#: de 5 ha, et c'est la taille courante de nos projets.
#:
#: Plutôt que de refuser de produire DP 4 sur un site réel, ou de rogner le
#: plan en silence, la liste est prolongée et le dépassement est écrit au
#: rapport. L'échelle retenue est de toute façon portée en clair à côté du
#: dessin : le lecteur sait toujours à quelle échelle il lit.
ECHELLES_REPERAGE_ADMISES = (300, 500, 1000)
ECHELLES_REPERAGE = ECHELLES_REPERAGE_ADMISES + (1500, 2000, 2500, 5000)

#: Débord de la requête parcellaire autour du cadre, en mètres : une parcelle
#: qui déborde du cadre doit quand même tracer sa limite jusqu'au bord.
MARGE_PARCELLAIRE_M = 40.0

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

#: Maille du grillage, en **mètres** de terrain.
#:
#: Elle était exprimée en millimètres de papier, et changeait donc de finesse
#: d'une planche à l'autre : mesuré le 05/09/2026, le même grillage sortait à
#: 8 cm de maille sur une planche au 1:100 et à 16 cm sur une planche au
#: 1:200. Une maille est une dimension d'ouvrage, pas un figuré : c'est un
#: grillage à moutons à grosse maille, et il se dessine à sa taille.
MAILLE_GRILLAGE_M = 0.15

#: Pas de l'ondulation d'un conteneur maritime, en mètres. Relevé le
#: 05/09/2026 sur les planches « LOCAL DE STOCKAGE MATERIEL » et « LOCAL DE
#: STOCKAGE BATTERIE » du dossier de référence : la tôle nervurée est ce qui
#: fait lire un conteneur, et sans elle il ne restait qu'un rectangle plein.
PAS_ONDULATION_M = 0.28

#: Hauteur des longerons haut et bas du cadre d'un conteneur, en mètres.
LONGERON_M = 0.16

#: Plots de pose d'un conteneur : largeur et hauteur, en mètres. Le dossier de
#: référence pose ses conteneurs sur plots et cote la fourchette « 0,3 à
#: 0,5 m », comme pour le socle des postes.
PLOT_LARGEUR_M = 0.30

#: Rayon des congés d'une citerne, en mètres. Une citerne souple ou métallique
#: n'a pas d'angle vif : le dossier de référence la dessine à angles arrondis,
#: en plan comme en élévation.
RAYON_CITERNE_M = 0.9

#: Écart entre deux barreaux de portail, en mètres. Un portail n'est pas un
#: panneau de grillage : ses vantaux sont barreaudés, et c'est ce qui les
#: distingue de la clôture qui les encadre.
ECART_BARREAUX_M = 0.12

#: Longueur de grillage montrée de part et d'autre du portail, en mètres. Sans
#: elle le portail flottait : le dossier de référence le montre toujours pris
#: dans la clôture qu'il interrompt.
RETOUR_CLOTURE_M = 1.6

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
    """Catégories de la planche que le projet porte réellement.

    Un ouvrage redondant avec un autre déjà décrit dans le dossier n'y figure
    pas : deux planches de citerne à cotes près l'une de l'autre n'apprennent
    rien de plus qu'une seule.
    """
    retenues = []
    for categorie in REPARTITION[code]:
        if not contrat.presente(categorie):
            continue
        couvrante = REDONDANTS.get(categorie)
        if couvrante is not None and contrat.presente(couvrante):
            continue
        retenues.append(categorie)
    return retenues


def ouvrages_ecartes(contrat: Contrat) -> list:
    """Ouvrages présents au contrat que la redondance a écartés des façades.

    Écarter en silence un ouvrage du dossier serait exactement le repli que le
    dépôt s'interdit : ce que la règle retire, le rapport le dit.
    """
    messages = []
    for categorie, couvrante in REDONDANTS.items():
        if contrat.presente(categorie) and contrat.presente(couvrante):
            messages.append(
                f"« {STYLES[categorie].libelle} » n'a pas de planche de façade : "
                f"« {STYLES[couvrante].libelle} » en décrit déjà une, et les deux "
                "ouvrages ne diffèrent que par leurs cotes, portées au tableau "
                "bilan. L'ouvrage reste dessiné et repéré au plan de masse."
            )
    return messages


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


def _echelles_des_blocs(blocs, largeur_mm: float, hauteur_mm: float) -> list:
    """Une échelle par ouvrage : le 1:100 de référence, sauf s'il n'y tient pas.

    L'ouvrage qui déborde descend d'un cran, et lui seul : c'est la citerne de
    11,7 m qui doit passer au 1:200, pas le conteneur de 6 m qui l'accompagne.
    Si la colonne déborde encore en hauteur, on redescend l'ouvrage le plus
    encombrant, jusqu'à ce que l'ensemble tienne.
    """
    candidates = [e for e in sorted(ECHELLES_OUVRAGES) if e >= ECHELLE_OUVRAGE_PREFEREE]
    utile = zone_interieure(0.0, 0.0, largeur_mm, 0.0)[2]

    echelles = []
    for bloc in blocs:
        for candidate in candidates:
            # Une vue plus large que le panneau ne tiendra à aucune hauteur.
            if all(
                v.largeur_m * 1000.0 / candidate <= utile - MARGE_VUE_MM
                for v in bloc.vues
            ):
                echelles.append(candidate)
                break
        else:
            plus_grand = max((v.largeur_m for v in bloc.vues), default=0.0)
            raise ErreurComposition(
                f"« {bloc.titre} » ne tient pas dans les {utile:.0f} mm du "
                f"panneau, même au 1:{max(candidates)} : sa plus grande vue "
                f"mesure {plus_grand:.1f} m."
            )

    def _hauteur_totale() -> float:
        return sum(
            _hauteur_contenu(bloc, echelle, utile)
            + hauteur_titre_cadre()
            + BLANC_TOURNANT_MM
            for bloc, echelle in zip(blocs, echelles)
        )

    while _hauteur_totale() > hauteur_mm:
        # Le bloc le plus haut est celui qui coûte le plus : c'est lui qui
        # descend, et pas ses voisins qui n'y sont pour rien.
        reductibles = [
            index
            for index, echelle in enumerate(echelles)
            if echelle != max(candidates)
        ]
        if not reductibles:
            raise ErreurComposition(
                f"Les {sum(len(b.vues) for b in blocs)} vues d'ouvrages ne "
                f"tiennent pas dans {largeur_mm:.0f} x {hauteur_mm:.0f} mm, même "
                f"au 1:{max(candidates)}. Répartissez les ouvrages sur une "
                "planche de plus."
            )
        pire = max(
            reductibles,
            key=lambda i: _hauteur_contenu(blocs[i], echelles[i], utile),
        )
        suivante = candidates[candidates.index(echelles[pire]) + 1]
        echelles[pire] = suivante
    return echelles


def _dessiner_ouvrages(planche: Planche, blocs, panneau) -> int:
    """Dispose les blocs d'ouvrages, chacun dans son sous-cadre.

    Chaque ouvrage a son cadre, comme sur le dossier de référence, porte son
    échelle en clair et voit ses vues centrées. Le cartouche reçoit l'échelle
    partagée par le plus grand nombre de cadres.
    """
    x, y, largeur, hauteur = panneau
    echelles = _echelles_des_blocs(blocs, largeur, hauteur)

    # Le blanc qui reste se partage à parts égales entre les cadres, au lieu
    # de s'accumuler en bas de la colonne : deux cadres serrés sur leur contenu
    # sous une demi-planche vide se lisent comme une mise en page inachevée.
    utile = zone_interieure(x, y, largeur, 0.0)[2]
    hauteurs = repartir_hauteurs(
        [
            _hauteur_contenu(bloc, echelle, utile) + hauteur_titre_cadre()
            for bloc, echelle in zip(blocs, echelles)
        ],
        hauteur,
    )

    curseur_y = y
    for bloc, echelle, hauteur_cadre in zip(blocs, echelles, hauteurs):
        interieur = sous_cadre(
            planche, x, curseur_y, largeur, hauteur_cadre,
            titre=bloc.titre, echelle=echelle,
        )
        _disposer_vues(planche, bloc, echelle, interieur)
        curseur_y += hauteur_cadre + BLANC_TOURNANT_MM
    # Au cartouche, l'échelle du plus grand nombre de cadres ; à égalité, la
    # plus grande. Chaque cadre porte la sienne, comme chez HOCH.
    return max(set(echelles), key=lambda e: (echelles.count(e), -e))


def _disposer_vues(planche, bloc, denominateur, interieur) -> None:
    """Pose les vues d'un bloc dans son cadre, centrées dans les deux sens.

    Tassées en haut à gauche, les vues laissaient tout leur blanc en bas et à
    droite du cadre, ce qui se lisait comme un oubli.
    """
    x, y, largeur, hauteur = interieur
    lignes = _lignes_de_vues(bloc, denominateur, largeur)
    a_cote = _place_pour_caracteristiques(bloc, lignes, denominateur, largeur)
    curseur_y = y + max(
        0.0, (hauteur - _hauteur_contenu(bloc, denominateur, largeur)) / 2.0
    )

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

    Un ouvrage présent en plusieurs exemplaires n'est repéré que sur **un**
    d'entre eux. Mesuré le 05/09/2026 sur Sarnois : ses deux citernes sont aux
    deux bouts du site, et les englober toutes les deux ramenait le « zoom » au
    plan de masse entier, au 1:2 000. Les élévations décrivent un ouvrage type,
    identique d'un exemplaire à l'autre ; les situer tous est le travail du
    plan de masse, pas celui de cette planche.
    """
    locales = [c for c in categories if c not in CATEGORIES_ETENDUES]
    ouvrages = []
    for categorie in locales:
        ouvrages.append(_exemplaire_repere(contrat.geometries(categorie)))
    ouvrages = [g for g in ouvrages if g is not None]
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


def _exemplaire_repere(geometries):
    """L'exemplaire qui vaut pour tous : le plus grand de la catégorie.

    Le plus grand, et non le premier, pour que le cadrage ne dépende pas de
    l'ordre du GeoPackage — deux générations du même dossier n'auraient pas
    cadré au même endroit.
    """
    surfaces = [g for g in geometries if g is not None and not g.is_empty]
    if not surfaces:
        return None
    return max(surfaces, key=lambda g: (g.area, g.length))


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
        # Les messages de chaque passe sont recueillis à part : la boucle est
        # une recherche, et une passe abandonnée n'a rien à dire au rapport.
        # Sans cela le même avertissement y figurait autant de fois qu'il avait
        # fallu de passes.
        messages_du_plan = []
        visibles = _categories_visibles(contrat, fenetre, messages_du_plan)
        besoin = hauteur_bloc(
            len(construire_legende([c for c, _ in visibles], avec_parcelles=True))
        )
        if besoin <= hauteur_legende:
            break
        hauteur_legende = besoin
    avertissements.extend(messages_du_plan)

    if denominateur not in ECHELLES_REPERAGE_ADMISES:
        avertissements.append(
            f"Plan de repérage DP 4 dessiné au 1:{denominateur}, hors de la "
            f"liste retenue ({', '.join('1:' + str(e) for e in ECHELLES_REPERAGE_ADMISES)}) : "
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

    # Le parcellaire d'abord, sous tout le reste : sans lui le zoom flottait
    # au milieu de nulle part, sans rien pour situer les ouvrages dans le
    # foncier. C'est ce que porte le plan de repérage du dossier de référence.
    parcelles = _parcelles_du_cadre(fenetre, avertissements)
    for parcelle in parcelles:
        _tracer_decoupe(planche, parcelle, STYLE_PARCELLE, fenetre)

    # Le contenu cartographique n'est découpé que sur la zone de dessin
    # entière : sans découpe, la clôture d'un site de 5 ha traversait le
    # panneau des ouvrages et passait par-dessus la légende.
    for categorie, geometries in visibles:
        style = STYLES[categorie].style
        for geometrie in geometries:
            _tracer_decoupe(planche, geometrie, style, fenetre)
        if categorie == "tables_pv":
            _tracer_tables(planche, contrat, geometries, fenetre, avertissements)

    entrees = construire_legende(
        [c for c, _ in visibles], avec_parcelles=bool(parcelles)
    )
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


def _parcelles_du_cadre(fenetre, avertissements) -> list:
    """Limites de parcelle sous le plan de repérage, depuis le WFS IGN.

    Le parcellaire est le fond commun de toutes les planches du dossier ; le
    plan de repérage sans lui montrait des ouvrages posés sur du blanc. Une
    panne du service n'empêche pas de produire la planche — les ouvrages, eux,
    viennent du contrat — mais elle s'écrit au rapport.
    """
    minx, miny, maxx, maxy = fenetre.bounds
    marge = MARGE_PARCELLAIRE_M
    try:
        parcelles = telecharger_parcelles(
            (minx - marge, miny - marge, maxx + marge, maxy + marge)
        )
    except ErreurService as exc:
        avertissements.append(
            f"Plan de repérage DP 4 : parcellaire IGN indisponible ({exc}). "
            "La planche est produite sans fond cadastral."
        )
        return []
    return [p.geometrie for p in parcelles if fenetre.intersects(p.geometrie)]


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
        # Le tableau bilan ne donne à cet ouvrage que deux dimensions. Le
        # dessiner en élévation demanderait une hauteur qu'il n'a pas : il se
        # dessine en plan, et son cadre le dit.
        return _bloc_surface(cote, STYLES[categorie].libelle, categorie)
    if categorie in POSTES:
        return _bloc_volume(cote, STYLES[categorie].libelle, categorie)
    if categorie in CONTENEURS:
        return _bloc_conteneur(cote, STYLES[categorie].libelle, categorie)
    if categorie in CITERNES:
        return _bloc_citerne(cote, STYLES[categorie].libelle, categorie)
    # Tout le reste est un équipement posé, pas un bâtiment : deux vues et ses
    # caractéristiques le décrivent entièrement.
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
    """Teinte d'un ouvrage sur son dessin de façade.

    Un dessin de façade montre l'ouvrage **tel qu'il sera**, pas la couleur qui
    le repère au plan : les ouvrages livrés en teinte de catalogue portent donc
    leur RAL, comme le poste et comme la clôture. Le dossier de référence fait
    de même — sa citerne est cyan sur le plan de repérage et olive sur son
    dessin de face.

    Relevé le 05/09/2026 : la citerne sortait au cyan de la légende sous une
    ligne de caractéristiques annonçant « teinte RAL 6003 ». Le dessin
    contredisait sa propre légende.
    """
    if categorie in TEINTE_RAL:
        return Style(trait="#2f3529", epaisseur_mm=0.3, remplissage=COULEUR_POSTE)
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
        #
        # Calée à gauche, et non centrée : centrée, elle tombait exactement sur
        # la cote de largeur, qui l'est aussi, et les deux textes s'écrivaient
        # l'un sur l'autre.
        if coter_socle:
            dessin.texte(
                0.0, 0.0,
                f"socle {nombre_fr(HAUTEUR_SOCLE_M, 1)} à "
                f"{nombre_fr(HAUTEUR_SOCLE_MAX_M, 1)} m",
                taille=5.5 * PT, ancre="start", decalage_mm=(0.0, 5.0),
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

    Recours pour un ouvrage dont le tableau bilan ne porte pas de hauteur.
    Plutôt que d'en inventer une, la vue en plan le décrit avec les deux
    dimensions dont on dispose, et la ligne de caractéristiques annonce qu'il
    n'a pas d'élévation.
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


def _grillage(dessin: Dessin, x0: float, x1: float, hauteur: float) -> None:
    """Un panneau de grillage à moutons, dessiné à la maille réelle.

    La trame est tracée fil à fil, en mètres de terrain : c'est ce qui la fait
    lire comme un grillage et non comme la hachure d'une coupe, et c'est ce qui
    lui donne la même finesse quelle que soit l'échelle de la planche.
    """
    fil = Style(trait=COULEUR_POSTE, epaisseur_mm=0.08, remplissage="none")
    nb_v = max(int((x1 - x0) / MAILLE_GRILLAGE_M), 1)
    for index in range(1, nb_v):
        x = x0 + (x1 - x0) * index / nb_v
        dessin.ligne((x, 0.0), (x, hauteur), fil)
    nb_h = max(int(hauteur / MAILLE_GRILLAGE_M), 1)
    for index in range(1, nb_h):
        y = hauteur * index / nb_h
        dessin.ligne((x0, y), (x1, y), fil)
    dessin.rectangle(
        x0, 0.0, x1 - x0, hauteur,
        Style(trait=COULEUR_POSTE, epaisseur_mm=0.25, remplissage="none"),
    )


def _poteau(dessin: Dessin, x: float, hauteur: float, largeur: float = 0.10) -> None:
    """Un montant plein, débordant légèrement du panneau qu'il tient."""
    dessin.rectangle(
        x - largeur / 2.0, 0.0, largeur, hauteur + 0.06,
        Style(trait=COULEUR_POSTE, epaisseur_mm=0.25, remplissage=COULEUR_POSTE),
    )


def _contour_plein(dessin: Dessin, points_m, style: Style) -> None:
    """Remplit un contour quelconque du dessin, puis le cerne.

    `Dessin.polyligne` ne trace que des segments : un contour fermé y sortait en
    filet, sans remplissage. Mesuré le 05/09/2026 sur la citerne, dont la cuve
    ressortait blanche sur une planche dont la légende annonçait un aplat RAL
    6003. Le remplissage passe donc par `forme_pleine`, le balayage vectoriel du
    lot 4, et l'étendue est notée à la main puisqu'il court-circuite le dessin.
    """
    points_mm = [dessin.point(x, y) for x, y in points_m]
    if style.remplissage and style.remplissage != "none":
        forme_pleine(dessin.planche, points_mm, style.remplissage)
    boucle = points_mm + [points_mm[0]]
    filet = Style(
        trait=style.trait or "#000000",
        epaisseur_mm=style.epaisseur_mm,
        remplissage="none",
    )
    for depart, arrivee in zip(boucle, boucle[1:]):
        dessin.planche.ajouter_ligne(
            depart[0], depart[1], arrivee[0], arrivee[1], filet
        )
    dessin._noter(*points_mm)


def _rectangle_arrondi(dessin: Dessin, x, y, largeur, hauteur, rayon, style) -> None:
    """Un rectangle à congés, plein.

    Le moteur ne connaît que le rectangle à angles vifs. Une citerne n'en a
    pas : ses quatre congés sont ce qui la distingue au premier coup d'œil d'un
    bac ou d'un local.
    """
    rayon = min(rayon, largeur / 2.0, hauteur / 2.0)
    points = []
    coins = (
        (x + largeur - rayon, y + rayon, -90.0),
        (x + largeur - rayon, y + hauteur - rayon, 0.0),
        (x + rayon, y + hauteur - rayon, 90.0),
        (x + rayon, y + rayon, 180.0),
    )
    for cx, cy, depart in coins:
        for pas in range(0, 91, 15):
            angle = math.radians(depart + pas)
            points.append((cx + rayon * math.cos(angle), cy + rayon * math.sin(angle)))
    _contour_plein(dessin, points, style)


def _bloc_conteneur(cote, libelle: str, categorie: str) -> BlocOuvrage:
    """Un conteneur maritime : tôle nervurée, cadre, portes, plots.

    C'est la présentation du dossier de référence pour le local de stockage et
    le conteneur batterie. La version précédente les dessinait en rectangles
    pleins : à cette échelle un conteneur et un bac de rétention en sortaient
    identiques, alors que rien ne se ressemble moins sur le terrain.
    """
    longueur = cote.longueur_m
    largeur = cote.largeur_m
    hauteur = cote.hauteur_m
    style = _style_ouvrage(categorie)
    nervure = Style(trait="#2f3529", epaisseur_mm=0.08, remplissage="none")
    cadre = Style(trait="#2f3529", epaisseur_mm=0.22, remplissage=COULEUR_TOITURE)

    def _plots(dessin: Dessin, portee: float) -> None:
        """Les deux plots de pose, et la fourchette de hauteur."""
        for x in (portee * 0.12, portee * 0.88 - PLOT_LARGEUR_M):
            dessin.rectangle(
                x, -HAUTEUR_SOCLE_M, PLOT_LARGEUR_M, HAUTEUR_SOCLE_M,
                Style(trait="#6e6e6e", epaisseur_mm=0.2, remplissage="#c8c8c8"),
            )

    def _nervures(dessin: Dessin, portee: float, bas: float, haut: float) -> None:
        nombre = max(int(portee / PAS_ONDULATION_M), 2)
        for index in range(1, nombre):
            x = portee * index / nombre
            dessin.ligne((x, bas), (x, haut), nervure)

    def plan(dessin: Dessin) -> None:
        dessin.rectangle(0.0, 0.0, longueur, largeur, style)
        _nervures(dessin, longueur, 0.0, largeur)
        # Pièces de coin, aux quatre angles.
        for cx in (0.0, longueur - 0.22):
            for cy in (0.0, largeur - 0.22):
                dessin.rectangle(cx, cy, 0.22, 0.22, cadre)
        _coter_rectangle(dessin, longueur, largeur)

    def long_pan(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.5, 0.0), (longueur + 0.5, 0.0)], epaisseur_mm=1.6)
        _plots(dessin, longueur)
        dessin.rectangle(0.0, 0.0, longueur, hauteur, style)
        _nervures(dessin, longueur, LONGERON_M, hauteur - LONGERON_M)
        # Longerons haut et bas : le cadre du conteneur, lisse.
        dessin.rectangle(0.0, 0.0, longueur, LONGERON_M, cadre)
        dessin.rectangle(0.0, hauteur - LONGERON_M, longueur, LONGERON_M, cadre)
        _coter_rectangle(dessin, longueur, hauteur)
        dessin.texte(
            longueur, hauteur, REFERENCE_RAL,
            taille=5.5 * PT, ancre="end", decalage_mm=(0.0, -2.0),
        )

    def pignon(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.5, 0.0), (largeur + 0.5, 0.0)], epaisseur_mm=1.6)
        _plots(dessin, largeur)
        dessin.rectangle(0.0, 0.0, largeur, hauteur, style)
        dessin.rectangle(0.0, 0.0, largeur, LONGERON_M, cadre)
        dessin.rectangle(0.0, hauteur - LONGERON_M, largeur, LONGERON_M, cadre)
        # Les deux vantaux et leurs barres de condamnation : c'est ce qui
        # désigne le pignon d'accès, et ce qui manquait le plus.
        battant = Style(trait="#2f3529", epaisseur_mm=0.18, remplissage="none")
        for vantail in range(2):
            x0 = 0.06 + vantail * (largeur - 0.12) / 2.0
            large = (largeur - 0.12) / 2.0
            dessin.rectangle(x0, LONGERON_M, large, hauteur - 2 * LONGERON_M, battant)
            for index in (1, 2):
                x = x0 + large * index / 3.0
                dessin.ligne((x, LONGERON_M), (x, hauteur - LONGERON_M), nervure)
        # Poignées, au milieu de la hauteur.
        for x in (largeur * 0.44, largeur * 0.56):
            dessin.ligne((x, hauteur * 0.45), (x, hauteur * 0.58), battant)
        _coter_rectangle(dessin, largeur, hauteur)

    return BlocOuvrage(
        titre=f"{libelle} — {cote.dimensions}",
        vues=[
            Vue("Plan de toiture", longueur, largeur, plan),
            Vue("Élévation long pan", longueur, hauteur + HAUTEUR_SOCLE_M, long_pan),
            Vue("Élévation pignon (portes)", largeur, hauteur + HAUTEUR_SOCLE_M,
                pignon),
        ],
        caracteristiques=[
            f"Type : {cote.ouvrage}",
            f"Conteneur maritime, teinte {REFERENCE_RAL}.",
            f"Hors tout : {nombre_fr(longueur)} x {nombre_fr(largeur)} x "
            f"{nombre_fr(hauteur)} m.",
            f"Posé sur plots de {nombre_fr(HAUTEUR_SOCLE_M, 1)} à "
            f"{nombre_fr(HAUTEUR_SOCLE_MAX_M, 1)} m.",
        ],
    )


def _bloc_citerne(cote, libelle: str, categorie: str) -> BlocOuvrage:
    """Une citerne : cuve à congés vue de dessus, cuve bombée vue de face.

    Relevé le 05/09/2026 sur la planche « CITERNE ~ 60 m³ » du dossier de
    référence : la cuve y est un rectangle à angles arrondis portant son
    trop-plein et ses trappes de visite, et sa vue de face est une calotte, pas
    un rectangle. Une citerne dessinée au carré se lisait comme un bac.
    """
    longueur = cote.longueur_m
    largeur = cote.largeur_m
    hauteur = cote.hauteur_m
    style = _style_ouvrage(categorie)

    def dessus(dessin: Dessin) -> None:
        _rectangle_arrondi(
            dessin, 0.0, 0.0, longueur, largeur, RAYON_CITERNE_M, style
        )
        repere = Style(trait="#2f3529", epaisseur_mm=0.2, remplissage="none")
        for part, intitule in ((0.30, "Trop-plein"), (0.62, "Trappes de visite")):
            x = longueur * part
            y = largeur * 0.52
            dessin.rectangle(x - 0.22, y - 0.22, 0.44, 0.44, repere)
            dessin.texte(
                x, y, intitule, taille=5.0 * PT, ancre="middle",
                decalage_mm=(0.0, 3.4),
            )
        _coter_rectangle(dessin, longueur, largeur)

    def face(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.6, 0.0), (longueur + 0.6, 0.0)], epaisseur_mm=1.6)
        # La calotte : une cuve pleine bombée, plus large que haute.
        points = [(0.0, 0.0)]
        for index in range(0, 41):
            part = index / 40.0
            points.append(
                (longueur * part, hauteur * math.sin(math.pi * part) ** 0.6)
            )
        points.append((longueur, 0.0))
        _contour_plein(dessin, points, style)
        cote_verticale(
            dessin, 0.0, hauteur, -dessin.metres(3.0), f"{nombre_fr(hauteur)} m"
        )
        cote_horizontale(
            dessin, 0.0, longueur, -dessin.metres(6.5), f"{nombre_fr(longueur)} m"
        )

    volume = _volume_de_citerne(cote)
    caracteristiques = [
        f"Volume : {volume} m³" if volume else f"Type : {cote.ouvrage}",
        f"Cuve à congés, teinte {REFERENCE_RAL}.",
        f"Emprise : {nombre_fr(longueur)} x {nombre_fr(largeur)} m.",
        f"Hauteur hors sol : {nombre_fr(hauteur)} m",
    ]
    # Le volume au titre : c'est la première chose qu'un pompier y cherche, et
    # le dossier de référence titre sa planche « CITERNE ~ 60 m³ ».
    intitule = f"{libelle} {volume} m³" if volume else libelle
    return BlocOuvrage(
        titre=f"{intitule} — {cote.dimensions}",
        vues=[
            Vue("Vue de dessus", longueur, largeur, dessus),
            Vue("Vue de face", longueur, max(hauteur, 1.0), face),
        ],
        caracteristiques=caracteristiques,
    )


def _volume_de_citerne(cote) -> str:
    """Volume porté par le catalogue du tableau bilan, en m³, ou chaîne vide.

    Le libellé de catalogue d'une citerne incendie finit par son volume
    (« Citerne incendie — 120 ») ; celui d'une citerne de refroidissement le
    porte ailleurs, et le tableau bilan la compte en « Citerne de
    refroidissement (120m3) ». On ne lit que ce qui est écrit : à défaut de
    volume, le titre reste celui de l'ouvrage.
    """
    fin = cote.ouvrage.rsplit("—", 1)[-1].strip()
    if fin.isdigit():
        return fin
    trouve = re.search(r"\((\d+)\s*m3\)", cote.ouvrage, flags=re.IGNORECASE)
    return trouve.group(1) if trouve else ""


def _bloc_cloture() -> BlocOuvrage:
    """Élévation de clôture : grillage, poteaux, passage à petite faune.

    Comme pour le poste, l'élévation montre l'ouvrage tel qu'il sera — grillage
    à moutons teinte RAL 6003 — et non la couleur rouge qui le repère au plan.
    """
    largeur = ESPACEMENT_POTEAUX_M * 3
    hauteur = HAUTEUR_CLOTURE_M

    def tracer(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.4, 0.0), (largeur + 0.4, 0.0)], epaisseur_mm=1.6)
        _grillage(dessin, 0.0, largeur, hauteur)
        for index in range(int(round(largeur / ESPACEMENT_POTEAUX_M)) + 1):
            _poteau(dessin, index * ESPACEMENT_POTEAUX_M, hauteur)

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
            f"Grillage à moutons, grosse maille, teinte {REFERENCE_RAL}.",
            f"Hauteur {nombre_fr(HAUTEUR_CLOTURE_M)} m, montants tous les "
            f"{nombre_fr(ESPACEMENT_POTEAUX_M)} m.",
            "Passages adaptés à la petite faune au pied de la clôture.",
        ],
    )


def _bloc_portail(largeur_m: float) -> BlocOuvrage:
    """Portail à deux vantaux, pris dans la clôture qu'il interrompt.

    C'est la planche « PORTAIL » du dossier de référence : de part et d'autre,
    le grillage courant ; au milieu, deux vantaux **barreaudés**, dont les
    barreaux verticaux se lisent tout autrement que la maille du grillage. La
    version précédente hachurait les vantaux au pas du grillage, et l'ensemble
    se lisait comme un panneau continu, sans porte.
    """
    hauteur = HAUTEUR_PORTAIL_M
    montant = Style(trait=COULEUR_POSTE, epaisseur_mm=0.3, remplissage="none")

    def elevation(dessin: Dessin) -> None:
        gauche = -RETOUR_CLOTURE_M
        droite = largeur_m + RETOUR_CLOTURE_M
        sol_hachure(
            dessin, [(gauche - 0.3, 0.0), (droite + 0.3, 0.0)], epaisseur_mm=1.6
        )
        # La clôture de part et d'autre : c'est elle qui situe le portail.
        _grillage(dessin, gauche, 0.0, hauteur)
        _grillage(dessin, largeur_m, droite, hauteur)

        # Les deux vantaux, barreaudés.
        barreau = Style(trait=COULEUR_POSTE, epaisseur_mm=0.14, remplissage="none")
        for vantail in range(2):
            x0 = vantail * largeur_m / 2.0
            x1 = x0 + largeur_m / 2.0
            dessin.rectangle(x0, 0.0, x1 - x0, hauteur, montant)
            # Traverses haute et basse du cadre du vantail.
            for y in (hauteur * 0.08, hauteur * 0.92):
                dessin.ligne((x0, y), (x1, y), barreau)
            nombre = max(int((x1 - x0) / ECART_BARREAUX_M), 2)
            for index in range(1, nombre):
                x = x0 + (x1 - x0) * index / nombre
                dessin.ligne((x, hauteur * 0.08), (x, hauteur * 0.92), barreau)

        # Poteaux : les deux d'ancrage, et celui où les vantaux se rejoignent.
        for x in (gauche, 0.0, largeur_m, droite):
            _poteau(dessin, x, hauteur, largeur=0.14)
        silhouette(dessin, droite + 0.9, 0.0, pleine=False)

        cote_horizontale(
            dessin, 0.0, largeur_m, hauteur + dessin.metres(4.5),
            f"{nombre_fr(largeur_m)} m",
        )
        cote_verticale(
            dessin, 0.0, hauteur, gauche - dessin.metres(3.5),
            f"{nombre_fr(hauteur)} m",
        )

    def coupe(dessin: Dessin) -> None:
        sol_hachure(dessin, [(-0.5, 0.0), (1.1, 0.0)], epaisseur_mm=1.6)
        _poteau(dessin, 0.0, hauteur, largeur=0.14)
        # Massif d'ancrage, sous le sol.
        dessin.rectangle(-0.18, -0.6, 0.44, 0.6, TRAIT_FIN)
        silhouette(dessin, 0.75, 0.0, pleine=False)
        cote_verticale(
            dessin, 0.0, hauteur, -dessin.metres(3.5), f"{nombre_fr(hauteur)} m"
        )

    return BlocOuvrage(
        titre=f"Portail d'accès — {nombre_fr(largeur_m)} m",
        vues=[
            Vue(
                "Élévation", largeur_m + 2 * RETOUR_CLOTURE_M + 1.6,
                hauteur + 1.4, elevation,
            ),
            Vue("Coupe sur poteau", 1.8, hauteur + 1.4, coupe),
        ],
        caracteristiques=[
            f"Portail double battant barreaudé, teinte {REFERENCE_RAL}.",
            f"Largeur {nombre_fr(largeur_m)} m, hauteur {nombre_fr(hauteur)} m.",
            "Pris dans la clôture à moutons du projet.",
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
