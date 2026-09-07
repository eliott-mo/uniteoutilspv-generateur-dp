"""DP 3 — Coupe des tables photovoltaïques et coupe du terrain.

Une planche, deux dessins superposés, **deux échelles**. Le cartouche ne peut
en annoncer qu'une : il porte celle de la coupe des tables, et la coupe du
terrain porte la sienne en clair à côté d'elle.

Les deux ne lisent pas les mêmes hauteurs, et c'est la décision D1 :

- la **coupe des tables** est un dessin de type, à grande échelle. Elle prend
  `point_bas_m` et `point_haut_m` du tableau bilan, qui sont des engagements
  d'enveloppe — le PDF de profil du bureau d'études écrit « 2.5m min » et
  « 4m max », des bornes sur tout le site. C'est aussi ce qu'annoncera la
  notice DP 11, et une planche qui contredit sa propre notice est une
  faiblesse à l'instruction.
- la **coupe du terrain** est une coupe de site, à petite échelle. Elle prend
  le Z des tables du GeoPackage, qui décrit chaque table là où elle est posée.
  L'écart entre les deux sources n'est pas constant — 2,50 m déclarés contre
  1,70 m mesurés à Saint-Cyr, 1,50 contre 1,29 à Sarnois — mais à cette
  échelle 0,80 m fait moins de 3 mm sur la feuille.

Aucune exagération verticale, sur aucun des deux dessins : `Dessin` ne porte
qu'un facteur d'échelle pour les deux axes, et il n'y a pas moyen d'en écrire
une.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import LineString, Point

from ..contrat import Contrat
from ..dossier import piece
from ..erreurs import ErreurComposition, ErreurContrat
from ..ign import telecharger_parcelles
from ..planche import GRIS, PT, Planche
from ..planche import nombre_fr
from ..projet import Projet
from .commun import Sortie, nouvelle_planche
from .palette import STYLES
from .standards import (
    HAUTEUR_ARBRE_M,
    HAUTEUR_CLOTURE_M,
    HAUTEUR_HAIE_M,
    MESSAGE_VEGETATION,
)
from .primitives import (
    BLANC_TOURNANT_MM,
    hauteur_titre_cadre,
    TAILLE_COTE,
    TRAIT_COTE,
    TRAIT_FIN,
    TRAIT_FORT,
    TRAIT_MOYEN,
    Dessin,
    attache,
    cote_horizontale,
    cote_oblique,
    cote_verticale,
    echelle_du_dessin,
    herbe,
    repartir_hauteurs,
    repere_coupe,
    silhouette,
    sol_hachure,
    sol_profond,
    sous_cadre,
    zone_interieure,
)

NUMERO = "DP 3"
TITRE = piece("DP 3").titre

#: Échelles autorisées, décision D2. Aucune n'est figée : le pas inter-rangées
#: de Saint-Cyr est de 9,5 m contre 3 m aux Islettes, et deux tables au 1/50 y
#: occuperaient toute la largeur utile sans place pour les cotes.
ECHELLES_TABLES = (50, 80, 100, 200)
ECHELLES_TERRAIN = (200, 250, 300, 500, 750, 1000)

#: Rangées dessinées sur la coupe de type, et minimum garanti par l'échelle.
#:
#: Deux, décidé à la relecture du 05/09/2026. Le brief calait l'échelle sur deux
#: rangées complètes et le dessin en montrait trois quand la place le permettait,
#: mais elle ne le permettait jamais : au 1:80, trois rangées d'un pas de 9,50 m
#: demandent 400 mm quand le cadre en offre 380, et l'avertissement « 2 rangées
#: au lieu de 3 » tombait sur les trois dossiers d'essai. Or deux rangées
#: suffisent à faire lire le pas et l'inter-table ; la troisième était une
#: répétition, et la chercher coûtait le passage au 1:100.
RANGEES_DESSINEES = 2
RANGEES_MINIMALES = 2

#: Longueurs de module admises pour le contrôle d'ordre de grandeur du
#: rampant. `format_module` est une désignation commerciale (« G12R »), pas une
#: dimension : le rampant se déduit des deux hauteurs et de l'inclinaison, et
#: c'est le nombre de modules qui permet de vérifier que le résultat tient
#: debout. Un module photovoltaïque courant mesure de 1,6 à 2,5 m de long.
LONGUEUR_MODULE_MIN_M = 1.6
LONGUEUR_MODULE_MAX_M = 2.5

#: Hauteurs standard UNITe des tables, **quand le contrat n'en porte pas**.
#:
#: Relevées dans le bloc `standards_unite` d'un tableau bilan réel
#: (Bray-Saint-Aignan, 04/09/2026), où elles sont écrites « Hauteur point bas »
#: et « Hauteur point haut ». Elles ne servent qu'en dernier recours.
#:
#: Un dossier d'origine HelioScope n'a **aucune** de ces deux valeurs : l'export
#: ne décrit pas la garde au sol de la structure, et son DXF est plat. La
#: décision D1 suppose des hauteurs déclarées ; il n'y en a pas. Plutôt que de
#: ne pas produire DP 3 sur ces dossiers, la coupe est dessinée au standard, et
#: le rapport de génération dit d'où viennent les deux cotes. C'est ce que la
#: règle demande : la substitution est le seul comportement possible, mais elle
#: doit se voir.
POINT_BAS_STANDARD_M = 1.50
POINT_HAUT_STANDARD_M = 3.12

#: Écart admis entre le pas déclaré et l'inter-table augmenté de la projection
#: du rampant, en mètres. Les trois valeurs viennent du même tableau bilan et
#: doivent se recouper ; 0,5 m laisse passer les arrondis de saisie.
TOLERANCE_PAS_M = 0.5

#: Marges de mise en page autour d'un dessin, en **millimètres de papier**.
#:
#: Une ligne de cote se pose à distance constante du dessin, quelle que soit
#: l'échelle : c'est une convention de dessin, pas une longueur de terrain.
#: Exprimées en mètres, ces marges enflaient avec l'échelle et la coupe des
#: tables au 1/80 sortait de son cadre de 16 mm.
MARGE_COTE_LATERALE_MM = 15.0
#: Sous la ligne de sol il n'y a plus que le sol hachuré, dont l'épaisseur est
#: un figuré ; au-dessus des tables, les deux lignes de cote horizontales.
MARGE_COTES_BASSES_MM = 19.0
MARGE_HAUT_MM = 17.0

#: Hauteur des lignes de cote **au-dessus** du point haut des tables, en
#: millimètres de papier.
#:
#: Le dossier de référence cote le pas et l'inter-table au-dessus du dessin.
#: Posées sous la ligne de sol, elles traversaient l'épaisseur hachurée du
#: terrain et devenaient illisibles.
HAUTEUR_INTER_TABLE_MM = 6.0
HAUTEUR_PAS_MM = 12.0
#: Écart d'une cote verticale au bord du dessin qu'elle cote.
ECART_COTE_VERTICALE_MM = 3.0

#: Marges de la coupe du terrain : l'axe altimétrique à gauche, le bandeau
#: parcellaire et les repères A et A' en dessous.
MARGE_AXE_MM = 18.0
MARGE_REPERES_MM = 24.0

#: Bandeau parcellaire sous la coupe : retrait sous la ligne de sol, et hauteur.
#:
#: Les numéros de parcelle étaient portés en haut du dessin, où ils tombaient
#: au milieu des tables — celui de la parcelle centrale de Saint-Cyr était
#: illisible, recouvert par une rangée. Sous la coupe, dans une bande qui leur
#: est réservée, ils se lisent tous.
RETRAIT_BANDEAU_MM = 7.0
HAUTEUR_BANDEAU_MM = 5.0

#: Figuré d'une table en coupe de principe, en mètres.
#:
#: Relevé sur la coupe de principe de Massay du 17/04/2025 : le plan des
#: modules y est une **bande** — verre et cadre — portée par deux poteaux
#: reliés d'une jambe de force, et non un simple trait sur deux piquets. C'est
#: cette structure qui fait qu'on reconnaît une table.
EPAISSEUR_MODULE_M = 0.06

#: Position des deux pieux sur le rampant, en fraction depuis le point bas.
APPUIS_RAMPANT = (0.22, 0.76)
#: Largeur d'un pieu battu, en mètres. Un profilé courant fait 8 à 12 cm
#: d'aile ; dessiné en trait unique, il ne se lit pas comme une structure.
LARGEUR_PIEU_M = 0.09
#: Fiche du pieu sous le terrain naturel, en mètres. Elle est dessinée : c'est
#: elle qui fait comprendre qu'il s'agit d'un pieu battu et non d'un plot posé.
FICHE_PIEU_M = 1.10
#: Hauteur de la platine de tête et du collier de contreventement, en mètres.
PLATINE_M = 0.16
COLLIER_M = 0.14
#: Hauteur du collier sur le pieu, en fraction de sa hauteur hors sol.
HAUTEUR_COLLIER = 0.42
#: Hauteur de la panne sous le plan des modules, en mètres.
HAUTEUR_PANNE_M = 0.14
#: Position du gousset central du contreventement sur le rampant.
GOUSSET_RAMPANT = 0.50
COTE_GOUSSET_M = 0.22

#: Épaisseur d'une piste dessinée sur le profil, en millimètres de papier. Une
#: piste n'a pas d'épaisseur mesurable à cette échelle : c'est un figuré.
#:
#: Elle se dessine **sous** la ligne de terrain, pas au-dessus : une piste est
#: incrustée dans le sol, décaissée puis remblayée de grave. Posée en
#: surépaisseur, elle se lisait comme un merlon.
EPAISSEUR_PISTE_MM = 1.3

#: Végétation traversée par la coupe, avec sa hauteur conventionnelle.
VEGETATION_TRAVERSEE = {
    "haie": HAUTEUR_HAIE_M,
    "haie_existante": HAUTEUR_HAIE_M,
    "arbre_existant": HAUTEUR_ARBRE_M,
}

#: Ouvrages dont la hauteur vient des cotes normalisées du tableau bilan.
OUVRAGES_TRAVERSES = (
    "pdl_ptr",
    "ptr",
    "pdl",
    "local_technique",
    "bess",
    "bache_incendie",
    "bac_retention",
    "citerne_refroidissement",
    "zone_remise",
    "aire_aspiration",
)

#: Catégories de sol que la coupe montre là où elle les traverse, dans l'ordre
#: de dessin du contrat.
SOLS_TRAVERSES = (
    "plateforme",
    "piste_lourde_existante",
    "piste_lourde_a_creer",
    "piste_legere",
    "piste_lourde",
    "aire_grutage",
)

#: Pas admis pour les graduations de l'axe altimétrique, en mètres, et écart
#: minimal entre deux d'entre elles sur le papier.
#:
#: Le pas se choisit sur l'écart imprimé, pas sur la dénivelée : à 1:750, une
#: graduation par mètre met quatre cotes dans huit millimètres, et elles se
#: chevauchent. C'est la lisibilité de l'épreuve qui décide.
PAS_ALTIMETRIQUES_M = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0)
ECART_GRADUATIONS_MM = 4.0


# ---------------------------------------------------------------------------
# Géométrie paramétrique d'une table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeometrieTable:
    """Profil d'une table, déduit des paramètres du tableau bilan."""

    point_bas_m: float
    point_haut_m: float
    inclinaison_deg: float
    inter_table_m: float
    pas_m: float
    rampant_m: float
    projection_m: float
    nb_modules_rampant: int | None


#: Où lire chaque paramètre de la coupe de type, dans l'ordre d'essai.
#:
#: Les deux producteurs du contrat remplissent des clés différentes, et c'est
#: légitime : le lot 2bis lit un tableau bilan, le lot 2 mesure un DXF. Le
#: lot 4 lit une seule structure, mais il doit savoir où chaque valeur peut se
#: trouver. Tout recours à autre chose que la source principale est écrit au
#: rapport : ce n'est pas la même chose de lire une inclinaison au tableau
#: bilan et de la mesurer sur un calepinage.
SOURCES_PARAMETRES = {
    "inclinaison_deg": (
        ("structures", "inclinaison_deg", None),
        ("modules", "inclinaison_deg", "mesurée sur le calepinage HelioScope"),
    ),
    "pas_m": (
        ("structures", "pitch_m", None),
        ("generalites", "pas_rangees_m", "mesuré sur le calepinage HelioScope"),
    ),
    "point_bas_m": (
        ("structures", "point_bas_m", None),
        ("standards_unite", "Hauteur point bas", "standard UNITe du tableau bilan"),
    ),
    "point_haut_m": (
        ("structures", "point_haut_m", None),
        ("standards_unite", "Hauteur point haut", "standard UNITe du tableau bilan"),
    ),
    "inter_table_m": (
        ("structures", "inter_table_m", None),
        ("standards_unite", "Distance inter-table", "standard UNITe du tableau bilan"),
    ),
}

#: Les deux hauteurs sont celles du tableau bilan, et **rien d'autre**.
#:
#: Une version de ce module allait chercher les hauteurs du bloc
#: `standards_unite` du même fichier quand les hauteurs déclarées ne refermaient
#: pas la géométrie du pas — sur Saint-Cyr, 1,10/2,34 m referment à 3 cm quand
#: les 2,50/4,00 m déclarés donnent un pas de 10,50 m contre 9,50 m portés au
#: tableau. C'était une liberté prise avec la donnée d'entrée, et elle est
#: retirée (relecture du 05/09/2026) : les hauteurs déclarées sont les bonnes,
#: une structure peut être haute. L'écart de pas reste écrit au rapport, parce
#: qu'il porte sur trois valeurs d'un même tableau qui ne se recoupent pas ;
#: c'est au tableau qu'il se règle, pas à la planche.
#:
#: Valeurs de dernier recours, quand une hauteur manque tout à fait, et ce
#: qu'il faut en dire.
DERNIER_RECOURS = {
    "point_bas_m": (POINT_BAS_STANDARD_M, "hauteur standard UNITe"),
    "point_haut_m": (POINT_HAUT_STANDARD_M, "hauteur standard UNITe"),
}


def _blocs_de_lecture(contrat: Contrat) -> dict:
    return {
        "structures": contrat.structures,
        "modules": contrat.modules,
        "generalites": contrat.generalites,
        "standards_unite": contrat.donnees.get("standards_unite") or {},
    }


def resoudre_parametre(contrat: Contrat, nom: str, avertissements: list) -> float:
    """Valeur d'un paramètre de la coupe de type, et d'où elle vient.

    L'ordre d'essai est celui de `SOURCES_PARAMETRES`. Dès qu'on quitte la
    source principale, le rapport le dit : une coupe dessinée sur des valeurs
    standard n'est pas la même chose qu'une coupe dessinée sur le tableau
    bilan du projet, et rien sur la planche ne les distingue.
    """
    blocs = _blocs_de_lecture(contrat)
    for bloc, cle, origine in SOURCES_PARAMETRES[nom]:
        brut = blocs.get(bloc, {}).get(cle)
        if brut is None or brut == "":
            continue
        try:
            valeur = float(brut)
        except (TypeError, ValueError):
            continue
        if origine is not None:
            avertissements.append(
                f"Coupe des tables : « {nom} » = {nombre_fr(valeur)} lu comme "
                f"{origine}, faute de valeur au tableau bilan du projet."
            )
        return valeur

    if nom in DERNIER_RECOURS:
        valeur, origine = DERNIER_RECOURS[nom]
        avertissements.append(
            f"Coupe des tables : « {nom} » absent du contrat d'entrée — "
            f"{origine} de {nombre_fr(valeur)} m appliquée. Un export "
            "HelioScope ne décrit pas la garde au sol de la structure, et son "
            "DXF est plat : cette cote ne vient pas du projet."
        )
        return valeur

    raise ErreurContrat(
        f"« {nom} » introuvable dans le contrat d'entrée (cherché dans "
        + ", ".join(
            f"{bloc}.{cle}" for bloc, cle, _ in SOURCES_PARAMETRES[nom]
        )
        + "). La coupe des tables ne peut pas être dessinée."
    )


def geometrie_table(contrat: Contrat) -> tuple:
    """Profil de type d'une table, et ce que les recoupements ont montré.

    Le rampant n'est pas lu : il se déduit des deux hauteurs et de
    l'inclinaison, qui sont les valeurs que la notice DP 11 annoncera. Il est
    ensuite recoupé de deux façons — par le nombre de modules qu'il porte, et
    par le pas déclaré, qui doit valoir l'inter-table plus la projection du
    rampant. Ces trois valeurs viennent du même tableau : si elles ne se
    recoupent pas, c'est le tableau qu'il faut reprendre, et le dire vaut
    mieux que dessiner une table qui ne ferme pas.
    """
    avertissements = []

    point_bas = resoudre_parametre(contrat, "point_bas_m", avertissements)
    point_haut = resoudre_parametre(contrat, "point_haut_m", avertissements)
    inclinaison = resoudre_parametre(contrat, "inclinaison_deg", avertissements)
    pas = resoudre_parametre(contrat, "pas_m", avertissements)

    if not 0.0 < inclinaison < 90.0:
        raise ErreurContrat(
            f"Inclinaison de {inclinaison}° hors de tout sens physique pour une "
            "table fixe : la coupe n'est pas dessinée."
        )
    if point_haut <= point_bas:
        raise ErreurContrat(
            f"Point haut ({point_haut} m) au niveau du point bas "
            f"({point_bas} m) ou en dessous : la table serait à plat, ce que "
            f"contredit l'inclinaison de {inclinaison}° du même tableau."
        )

    rampant = (point_haut - point_bas) / math.sin(math.radians(inclinaison))
    projection = rampant * math.cos(math.radians(inclinaison))

    # L'inter-table se déduit du pas quand elle n'est pas portée : les deux
    # décrivent la même géométrie, et c'est le pas qui commande le dessin.
    try:
        inter_table = resoudre_parametre(contrat, "inter_table_m", avertissements)
    except ErreurContrat:
        inter_table = pas - projection
        avertissements.append(
            f"Coupe des tables : inter-table absente du contrat, déduite du pas "
            f"({nombre_fr(pas)} m) moins la projection du rampant "
            f"({nombre_fr(projection)} m), soit {nombre_fr(inter_table)} m."
        )
    if inter_table <= 0:
        raise ErreurContrat(
            f"Inter-table de {nombre_fr(inter_table)} m : les rangées se "
            f"chevaucheraient. Pas de {nombre_fr(pas)} m pour une projection "
            f"de rampant de {nombre_fr(projection)} m."
        )

    ecart_pas = abs(pas - (inter_table + projection))
    if ecart_pas > TOLERANCE_PAS_M:
        avertissements.append(
            f"Pas déclaré de {nombre_fr(pas)} m, contre "
            f"{nombre_fr(inter_table + projection)} m attendus (inter-table "
            f"{nombre_fr(inter_table)} m + projection du rampant "
            f"{nombre_fr(projection)} m), soit {nombre_fr(ecart_pas)} m d'écart. "
            "La coupe est dessinée au pas et aux hauteurs du tableau bilan, "
            "comme la notice les annoncera : ces trois valeurs viennent du même "
            "tableau, et c'est là qu'il faut les reprendre si l'écart n'est pas "
            "voulu."
        )

    structures = contrat.structures
    nb_modules = structures.get("nb_modules_rampant")
    if nb_modules:
        longueur_module = rampant / float(nb_modules)
        if not LONGUEUR_MODULE_MIN_M <= longueur_module <= LONGUEUR_MODULE_MAX_M:
            avertissements.append(
                f"Rampant déduit de {nombre_fr(rampant)} m pour "
                f"{int(nb_modules)} module(s), soit "
                f"{nombre_fr(longueur_module)} m par module — hors de la "
                f"fourchette {nombre_fr(LONGUEUR_MODULE_MIN_M, 1)}–"
                f"{nombre_fr(LONGUEUR_MODULE_MAX_M, 1)} m d'un module courant. "
                "Vérifiez l'inclinaison et les deux hauteurs du tableau bilan."
            )

    return (
        GeometrieTable(
            point_bas_m=point_bas,
            point_haut_m=point_haut,
            inclinaison_deg=inclinaison,
            inter_table_m=inter_table,
            pas_m=pas,
            rampant_m=rampant,
            projection_m=projection,
            nb_modules_rampant=int(nb_modules) if nb_modules else None,
        ),
        avertissements,
    )


# ---------------------------------------------------------------------------
# Planche
# ---------------------------------------------------------------------------


def generer(
    projet: Projet,
    contrat: Contrat,
    dossier: str | Path,
    numero: str | None = None,
) -> Sortie:
    if contrat.profil is None or not (contrat.profil.get("points") or []):
        raise ErreurContrat(
            "Aucun profil de terrain au contrat : la coupe du terrain de DP 3 "
            "ne peut pas être dessinée. Tracez la ligne de coupe A-A' à "
            "l'import et relevez le profil avant de générer le dossier."
        )

    table, avertissements = geometrie_table(contrat)

    # L'échelle du cartouche est celle de la coupe des tables ; celle de la
    # coupe du terrain est portée en clair à côté d'elle.
    planche = nouvelle_planche(projet, NUMERO, numero=numero)
    zone_x, zone_y, zone_l, zone_h = planche.zone_dessin()

    # Blanc tournant : la planche ne colle rien à son cadre, et laisse le même
    # jeu entre ses deux sous-cadres.
    utile_x = zone_x + BLANC_TOURNANT_MM
    utile_y = zone_y + BLANC_TOURNANT_MM
    utile_l = zone_l - 2 * BLANC_TOURNANT_MM
    utile_h = zone_h - 2 * BLANC_TOURNANT_MM

    # Les deux cadres sont d'abord mesurés à vide sur un partage provisoire de
    # la hauteur, puis le blanc qui reste se partage à parts égales entre eux.
    # Caler le premier sur son contenu et donner tout le reste au second
    # donnait un cadre plein et un cadre presque vide.
    provisoire = (utile_h - BLANC_TOURNANT_MM) / 2.0
    _, _, besoin_tables = _coupe_des_tables(
        planche, table, (utile_x, utile_y, utile_l, provisoire), tracer=False
    )
    _, _, besoin_terrain = _coupe_du_terrain(
        planche, contrat, table, (utile_x, utile_y, utile_l, provisoire),
        tracer=False,
    )
    hauteur_tables, hauteur_terrain = repartir_hauteurs(
        [besoin_tables, besoin_terrain], utile_h
    )

    bloc_tables = (utile_x, utile_y, utile_l, hauteur_tables)
    echelle_tables, nb_rangees, _ = _coupe_des_tables(planche, table, bloc_tables)
    planche.definir_echelle(echelle_tables)

    haut_terrain = utile_y + hauteur_tables + BLANC_TOURNANT_MM
    bloc_terrain = (utile_x, haut_terrain, utile_l, hauteur_terrain)
    echelle_terrain, messages, _ = _coupe_du_terrain(
        planche, contrat, table, bloc_terrain
    )
    avertissements.extend(messages)
    if nb_rangees < RANGEES_DESSINEES:
        avertissements.append(
            f"Coupe des tables : {nb_rangees} rangées dessinées au lieu de "
            f"{RANGEES_DESSINEES}, faute de largeur au 1:{echelle_tables} pour "
            f"un pas de {nombre_fr(table.pas_m)} m."
        )

    chemin = planche.rendre_pdf(Path(dossier) / "DP_3_coupes.pdf")
    return Sortie(
        numero=NUMERO,
        titre=TITRE,
        chemin=chemin,
        echelle=echelle_tables,
        details={
            "echelle_tables": echelle_tables,
            "echelle_terrain": echelle_terrain,
            "nb_rangees": nb_rangees,
            "rampant_m": table.rampant_m,
            "avertissements": avertissements,
        },
    )


# ---------------------------------------------------------------------------
# Moitié haute — coupe des tables
# ---------------------------------------------------------------------------


def _coupe_des_tables(planche: Planche, table: GeometrieTable, bloc,
                      tracer: bool = True) -> tuple:
    """Dessin de type : trois rangées en profil, sur un sol hachuré.

    Aucune géométrie n'est lue du GeoPackage. C'est une coupe de principe, et
    ses cotes sont celles que la notice reprendra.
    """
    bloc_x, bloc_y, bloc_l, bloc_h = bloc
    interieur = zone_interieure(bloc_x, bloc_y, bloc_l, bloc_h)
    interieur_x, interieur_y, interieur_l, interieur_h = interieur

    # L'échelle est calée sur deux rangées complètes et leurs lignes de cote
    # (D2) : c'est la largeur qu'il faut garantir, pas celle des trois rangées
    # dessinées. Les cotes occupent une place fixe sur le papier, retranchée de
    # la zone avant de chercher l'échelle plutôt qu'ajoutée au contenu.
    largeur_utile_m = table.pas_m * (RANGEES_MINIMALES - 1) + table.projection_m
    largeur_utile_m += table.inter_table_m  # le sol déborde de part et d'autre
    hauteur_utile_m = table.point_haut_m
    zone_contenu = (
        interieur_x + MARGE_COTE_LATERALE_MM,
        interieur_y + MARGE_HAUT_MM,
        interieur_l - 2 * MARGE_COTE_LATERALE_MM,
        interieur_h - MARGE_HAUT_MM - MARGE_COTES_BASSES_MM,
    )
    denominateur = echelle_du_dessin(
        largeur_utile_m,
        hauteur_utile_m,
        zone_contenu,
        ECHELLES_TABLES,
        libelle="coupe des tables",
    )

    hauteur_dessin_mm = (
        MARGE_HAUT_MM
        + hauteur_utile_m * 1000.0 / denominateur
        + MARGE_COTES_BASSES_MM
    )
    if not tracer:
        # Mesure seule : la planche a besoin de savoir ce que ce cadre demande
        # pour partager le blanc entre ses deux cadres, avant que rien ne soit
        # tracé. Le nombre de rangées ne se sait qu'au tracé.
        return denominateur, None, hauteur_dessin_mm + hauteur_titre_cadre()
    sous_cadre(
        planche, bloc_x, bloc_y, bloc_l, bloc_h,
        titre="Coupe de principe des tables photovoltaïques",
        echelle=denominateur,
    )
    # Le dessin est centré dans le cadre qu'on lui a donné : posé en haut, il
    # laissait tout son blanc en bas, ce qui se lit comme un oubli.
    haut_groupe = interieur_y + max(0.0, (interieur_h - hauteur_dessin_mm) / 2.0)

    # Autant de rangées complètes que la largeur en loge, trois au plus.
    largeur_disponible_m = (
        (interieur_l - 2 * MARGE_COTE_LATERALE_MM) * denominateur / 1000.0
        - table.inter_table_m
    )
    nb_rangees = int((largeur_disponible_m - table.projection_m) // table.pas_m) + 1
    nb_rangees = max(RANGEES_MINIMALES, min(RANGEES_DESSINEES, nb_rangees))

    largeur_dessin_m = table.pas_m * (nb_rangees - 1) + table.projection_m
    # Le sol déborde des tables d'un demi inter-table de chaque côté : une
    # coupe qui s'arrête au bord de la première table se lit comme un talus.
    debord_m = table.inter_table_m / 2.0
    sol_gauche = -debord_m
    sol_droite = largeur_dessin_m + debord_m

    # Le dessin est centré horizontalement, et posé assez haut pour laisser
    # sous le sol la place des cotes de pas et d'inter-table.
    largeur_totale_mm = (sol_droite - sol_gauche) * 1000.0 / denominateur
    origine_x_mm = interieur_x + (interieur_l - largeur_totale_mm) / 2.0
    origine_y_mm = haut_groupe + hauteur_dessin_mm - MARGE_COTES_BASSES_MM

    dessin = Dessin(
        planche=planche,
        denominateur=denominateur,
        origine_mm=(origine_x_mm, origine_y_mm),
        origine_m=(sol_gauche, 0.0),
        cadre_mm=(bloc_x, bloc_y, bloc_l, bloc_h),
    )

    sol_profond(dessin, sol_gauche, sol_droite)
    # Les fiches des pieux se dessinent après le sol : elles doivent se lire à
    # travers les hachures, comme sur le dossier de référence.

    style_table = STYLES["tables_pv"].style
    trait_table = type(TRAIT_FORT)(
        trait=style_table.trait, epaisseur_mm=0.3,
        remplissage=style_table.remplissage,
    )
    pieds = []
    for index in range(nb_rangees):
        x_bas = index * table.pas_m
        _tracer_table(dessin, table, x_bas, trait_table)
        pieds.append((x_bas - 0.3, x_bas + table.projection_m + 0.3))

    # L'herbe court sous les tables : c'est une prairie qui reste pâturée, et
    # une coupe sans elle se lit comme un terrassement.
    herbe(dessin, sol_gauche, sol_droite, eviter=[])

    _coter_table(dessin, table, nb_rangees)

    # La silhouette donne l'échelle d'un coup d'œil, ce qu'aucune cote ne fait
    # aussi vite. Elle est posée dans l'inter-rangée, où elle ne masque rien.
    if nb_rangees >= 2:
        silhouette(
            dessin, table.projection_m + table.inter_table_m / 2.0, 0.0,
            pleine=False,
        )

    dessin.verifier_cadre("Coupe des tables")
    return denominateur, nb_rangees, hauteur_dessin_mm + hauteur_titre_cadre()


def _point_sur_rampant(table: GeometrieTable, x_bas: float, fraction: float):
    """Point du plan des modules, repéré en fraction du rampant."""
    return (
        x_bas + table.projection_m * fraction,
        table.point_bas_m + (table.point_haut_m - table.point_bas_m) * fraction,
    )


def _bande(dessin: Dessin, depart, arrivee, epaisseur_m: float, style) -> None:
    """Bande d'épaisseur constante le long d'un segment quelconque.

    C'est ce qui distingue une structure d'un trait de construction : un pieu,
    une panne et un plan de modules ont une épaisseur, et le dossier de
    référence les dessine tous à double trait.
    """
    dx = arrivee[0] - depart[0]
    dy = arrivee[1] - depart[1]
    norme = math.hypot(dx, dy)
    if norme == 0:
        return
    nx, ny = -dy / norme, dx / norme
    demi = epaisseur_m / 2.0
    dessin.polyligne(
        [
            (depart[0] + nx * demi, depart[1] + ny * demi),
            (arrivee[0] + nx * demi, arrivee[1] + ny * demi),
            (arrivee[0] - nx * demi, arrivee[1] - ny * demi),
            (depart[0] - nx * demi, depart[1] - ny * demi),
        ],
        style,
        fermer=True,
    )


def _tracer_table(dessin: Dessin, table: GeometrieTable, x_bas: float, style) -> None:
    """Une table en profil : le plan des modules et sa structure porteuse.

    Reprise de la coupe de principe du dossier de Massay du 17/04/2025, où la
    structure se lit entièrement : deux pieux battus à double trait, fichés
    sous le terrain, une platine de tête et un collier sur chacun, la panne
    continue sous le plan des modules, et un contreventement triangulé partant
    d'un gousset central.

    Un pieu dessiné d'un trait unique ne se lit pas comme une structure : il se
    lit comme une ligne de rappel.
    """
    acier = type(TRAIT_MOYEN)(trait="#3a3a3a", epaisseur_mm=0.2, remplissage="none")
    fiche = type(TRAIT_FIN)(trait="#7a7a7a", epaisseur_mm=0.15, remplissage="none")

    bas = _point_sur_rampant(table, x_bas, 0.0)
    haut = _point_sur_rampant(table, x_bas, 1.0)

    # La panne, continue sous le plan des modules, décalée de sa hauteur.
    pente_x = table.projection_m
    pente_y = table.point_haut_m - table.point_bas_m
    norme = math.hypot(pente_x, pente_y)
    normale = (-pente_y / norme, pente_x / norme)

    def sous_rampant(point, distance):
        return (
            point[0] - normale[0] * distance,
            point[1] - normale[1] * distance,
        )

    _bande(
        dessin,
        sous_rampant(bas, HAUTEUR_PANNE_M / 2.0),
        sous_rampant(haut, HAUTEUR_PANNE_M / 2.0),
        HAUTEUR_PANNE_M,
        acier,
    )

    # Le plan des modules, en bande, posé sur la panne.
    dessus = [
        (bas[0] + normale[0] * EPAISSEUR_MODULE_M,
         bas[1] + normale[1] * EPAISSEUR_MODULE_M),
        (haut[0] + normale[0] * EPAISSEUR_MODULE_M,
         haut[1] + normale[1] * EPAISSEUR_MODULE_M),
    ]
    dessin.polyligne([bas, haut, dessus[1], dessus[0]], style, fermer=True)

    # Les deux pieux, à double trait, fichés sous le terrain.
    colliers = []
    for fraction in APPUIS_RAMPANT:
        tete = sous_rampant(
            _point_sur_rampant(table, x_bas, fraction), HAUTEUR_PANNE_M
        )
        x = tete[0]
        dessin.polyligne(
            [
                (x - LARGEUR_PIEU_M / 2.0, 0.0),
                (x - LARGEUR_PIEU_M / 2.0, tete[1]),
                (x + LARGEUR_PIEU_M / 2.0, tete[1]),
                (x + LARGEUR_PIEU_M / 2.0, 0.0),
            ],
            acier,
        )
        # La fiche, sous le terrain naturel.
        for cote in (-1, 1):
            dessin.ligne(
                (x + cote * LARGEUR_PIEU_M / 2.0, 0.0),
                (x + cote * LARGEUR_PIEU_M / 2.0, -FICHE_PIEU_M),
                fiche,
            )
        # Platine de tête, entre le pieu et la panne.
        dessin.rectangle(
            x - PLATINE_M / 2.0, tete[1] - PLATINE_M / 4.0,
            PLATINE_M, PLATINE_M * 0.75, acier,
        )
        # Collier de contreventement.
        y_collier = tete[1] * HAUTEUR_COLLIER
        dessin.rectangle(
            x - COLLIER_M / 2.0, y_collier - COLLIER_M / 2.0,
            COLLIER_M, COLLIER_M, acier,
        )
        colliers.append((x, y_collier))

    # Le contreventement : un gousset sur la panne, deux diagonales vers les
    # colliers. C'est ce triangle qui tient la table au vent.
    gousset = sous_rampant(
        _point_sur_rampant(table, x_bas, GOUSSET_RAMPANT), HAUTEUR_PANNE_M
    )
    dessin.rectangle(
        gousset[0] - COTE_GOUSSET_M / 2.0, gousset[1] - COTE_GOUSSET_M / 2.0,
        COTE_GOUSSET_M, COTE_GOUSSET_M, acier,
    )
    for collier in colliers:
        _bande(dessin, gousset, collier, 0.05, acier)


def _coter_table(dessin: Dessin, table: GeometrieTable, nb_rangees: int) -> None:
    """Les cinq cotes du PDF de profil du bureau d'études."""
    ecart = dessin.metres(ECART_COTE_VERTICALE_MM)
    # Hauteurs, de part et d'autre de la première table.
    cote_verticale(
        dessin, 0.0, table.point_bas_m, -ecart,
        f"{nombre_fr(table.point_bas_m)} m",
    )
    cote_verticale(
        dessin, 0.0, table.point_haut_m, table.projection_m + ecart,
        f"{nombre_fr(table.point_haut_m)} m", a_gauche=False,
    )

    if nb_rangees >= 2:
        # Inter-table : du haut d'une rangée au bas de la suivante, cotée
        # au-dessus du dessin comme sur le dossier de référence.
        y_cote = table.point_haut_m + dessin.metres(HAUTEUR_INTER_TABLE_MM)
        attache(dessin, table.projection_m, table.point_haut_m, y_cote)
        attache(dessin, table.pas_m, table.point_bas_m, y_cote)
        cote_horizontale(
            dessin, table.projection_m, table.pas_m, y_cote,
            f"inter-table {nombre_fr(table.inter_table_m)} m",
        )
        # Pas : du bas d'une rangée au bas de la suivante.
        y_pas = table.point_haut_m + dessin.metres(HAUTEUR_PAS_MM)
        attache(dessin, 0.0, table.point_bas_m, y_pas)
        attache(dessin, table.pas_m, table.point_bas_m, y_pas)
        cote_horizontale(
            dessin, 0.0, table.pas_m, y_pas, f"pas {nombre_fr(table.pas_m)} m"
        )

    # Le rampant, coté le long de la pente : sa projection ne dit pas la même
    # chose, et c'est la longueur du rampant qui donne le nombre de modules.
    cote_oblique(
        dessin,
        (0.0, table.point_bas_m),
        (table.projection_m, table.point_haut_m),
        f"rampant {nombre_fr(table.rampant_m)} m",
        decalage_mm=7.0,
    )
    _coter_angle(dessin, table)


def _coter_angle(dessin: Dessin, table: GeometrieTable) -> None:
    """L'inclinaison, en arc entre l'horizontale et le plan des modules."""
    rayon = min(table.projection_m * 0.30, table.rampant_m * 0.30)
    origine = (0.0, table.point_bas_m)
    dessin.ligne(origine, (rayon * 1.25, table.point_bas_m), TRAIT_COTE)

    angle = math.radians(table.inclinaison_deg)
    arc = [
        (
            origine[0] + rayon * math.cos(angle * fraction / 12.0),
            origine[1] + rayon * math.sin(angle * fraction / 12.0),
        )
        for fraction in range(13)
    ]
    dessin.polyligne(arc, TRAIT_COTE)
    dessin.texte(
        origine[0] + rayon * 1.25,
        origine[1] + rayon * math.sin(angle) * 0.30,
        f"{nombre_fr(table.inclinaison_deg, 0)}°",
        taille=TAILLE_COTE, decalage_mm=(0.0, 1.4),
    )


# ---------------------------------------------------------------------------
# Moitié basse — coupe du terrain
# ---------------------------------------------------------------------------


def _coupe_du_terrain(
    planche: Planche, contrat: Contrat, table: GeometrieTable, bloc,
    tracer: bool = True,
) -> tuple:
    """Coupe de site : le terrain naturel, les tables posées dessus.

    Les tables prennent leur hauteur du Z du GeoPackage quand il décrit le
    terrain. Quand il ne le décrit pas — tout dossier d'origine HelioScope,
    dont le DXF est plat — elles sont posées sur le profil RGE ALTI en
    appliquant les hauteurs déclarées, et la substitution est écrite au
    rapport de génération (décision D1). Ce n'est pas un repli silencieux :
    c'est le seul comportement possible, mais il doit se voir.
    """
    bloc_x, bloc_y, bloc_l, bloc_h = bloc
    avertissements = []

    profil = [
        (float(abscisse), float(altitude))
        for abscisse, altitude in contrat.profil["points"]
    ]
    if len(profil) < 2:
        raise ErreurContrat(
            f"Profil du terrain réduit à {len(profil)} point(s) : la coupe du "
            "terrain n'est pas dessinée."
        )
    longueur_m = profil[-1][0] - profil[0][0]
    altitudes = [altitude for _, altitude in profil]
    alt_min, alt_max = min(altitudes), max(altitudes)

    interieur = zone_interieure(bloc_x, bloc_y, bloc_l, bloc_h)
    interieur_x, interieur_y, interieur_l, interieur_h = interieur
    # Hauteur utile : le relief, plus le plus haut de ce qui est posé dessus.
    # Un arbre traversé par la coupe monte à 8 m, bien au-dessus d'une table :
    # l'oublier ici le faisait sortir du bloc.
    hauteur_posee_m = max(
        [table.point_haut_m]
        + [
            hauteur
            for categorie, hauteur in VEGETATION_TRAVERSEE.items()
            if contrat.presente(categorie)
        ]
    )
    hauteur_utile_m = (alt_max - alt_min) + hauteur_posee_m
    zone_contenu = (
        interieur_x + MARGE_AXE_MM,
        interieur_y + MARGE_HAUT_MM,
        interieur_l - MARGE_AXE_MM - MARGE_COTE_LATERALE_MM,
        interieur_h - MARGE_HAUT_MM - MARGE_REPERES_MM,
    )
    denominateur = echelle_du_dessin(
        longueur_m,
        hauteur_utile_m,
        zone_contenu,
        ECHELLES_TERRAIN,
        libelle="coupe du terrain",
    )

    hauteur_dessin_mm = (
        MARGE_HAUT_MM
        + hauteur_utile_m * 1000.0 / denominateur
        + MARGE_REPERES_MM
    )
    if not tracer:
        return denominateur, [], hauteur_dessin_mm + hauteur_titre_cadre()
    sous_cadre(
        planche, bloc_x, bloc_y, bloc_l, bloc_h,
        titre="Coupe du terrain naturel A-A'", echelle=denominateur,
    )
    # Ce cadre occupe le bas de la planche : son dessin y est centré plutôt
    # que posé en haut.
    haut_groupe = interieur_y + max(0.0, (interieur_h - hauteur_dessin_mm) / 2.0)

    largeur_mm = longueur_m * 1000.0 / denominateur
    origine_x_mm = (
        interieur_x + MARGE_AXE_MM
        + (interieur_l - MARGE_AXE_MM - MARGE_COTE_LATERALE_MM - largeur_mm) / 2.0
    )
    origine_y_mm = haut_groupe + hauteur_dessin_mm - MARGE_REPERES_MM

    dessin = Dessin(
        planche=planche,
        denominateur=denominateur,
        origine_mm=(origine_x_mm, origine_y_mm),
        origine_m=(profil[0][0], alt_min),
        cadre_mm=(bloc_x, bloc_y, bloc_l, bloc_h),
    )

    # 1. Le terrain naturel.
    sol_hachure(dessin, profil)

    # 2. Les sols traversés — pistes, plateformes — posés sur le profil. Sans
    #    eux la coupe montre des tables flottant sur un terrain nu, alors que
    #    la coupe traverse presque toujours une piste.
    _sols_sur_le_profil(dessin, contrat, profil)

    # 3. Les tables, à leur abscisse réelle le long de la coupe.
    posees, messages = _tables_sur_le_profil(dessin, contrat, table, profil)
    avertissements.extend(messages)
    if not posees:
        avertissements.append(
            "Aucune table n'est traversée par la ligne de coupe : la coupe du "
            "terrain ne montre que le terrain naturel. Vérifiez le tracé A-A'."
        )

    # 4. Les ouvrages traversés par la coupe.
    avertissements.extend(_ouvrages_sur_le_profil(dessin, contrat, profil))

    # 5. La clôture, là où la coupe la franchit : c'est elle qui délimite le
    #    projet, et une coupe de site qui ne la montre pas ne dit pas où il
    #    commence.
    avertissements.extend(_cloture_sur_le_profil(dessin, contrat, profil))

    # 6. L'axe altimétrique, le bandeau parcellaire et les repères A / A'.
    _axe_altimetrique(dessin, profil, alt_min, alt_max, table)
    avertissements.extend(
        _bandeau_parcellaire(dessin, contrat, profil, alt_min)
    )
    _reperes_de_coupe(dessin, profil, alt_min)

    dessin.verifier_cadre("Coupe du terrain")
    return denominateur, avertissements, hauteur_dessin_mm + hauteur_titre_cadre()


def _altitude_a(profil, abscisse: float) -> float:
    """Altitude du terrain à une abscisse, par interpolation linéaire."""
    if abscisse <= profil[0][0]:
        return profil[0][1]
    if abscisse >= profil[-1][0]:
        return profil[-1][1]
    for (x1, z1), (x2, z2) in zip(profil, profil[1:]):
        if x1 <= abscisse <= x2:
            if x2 == x1:
                return z1
            part = (abscisse - x1) / (x2 - x1)
            return z1 + part * (z2 - z1)
    return profil[-1][1]


def _ligne_de_coupe(contrat: Contrat) -> LineString:
    couche = contrat.couches.get("ligne_coupe")
    if couche is None or couche.empty:
        raise ErreurContrat(
            "Aucune ligne de coupe au contrat : la coupe du terrain ne peut "
            "pas être située."
        )
    ligne = couche.geometry.iloc[0]
    if ligne is None or ligne.is_empty:
        raise ErreurContrat("Ligne de coupe vide au contrat.")
    return LineString([(x, y) for x, y, *_ in ligne.coords])


def _tables_sur_le_profil(dessin, contrat: Contrat, table: GeometrieTable, profil):
    """Les tables que la coupe traverse, posées à leur abscisse réelle."""
    ligne = _ligne_de_coupe(contrat)
    z_reel = contrat.z_reel("tables_pv")
    avertissements = []
    if not z_reel:
        # Décision D1 : le Z d'un DXF plat ne décrit pas le terrain. Les tables
        # sont posées sur le profil RGE ALTI en appliquant les hauteurs
        # déclarées, et cela doit se voir au rapport.
        avertissements.append(
            f"Dossier d'origine « {contrat.origine} » : le Z des tables ne "
            "porte pas d'altitude de terrain. Les tables de la coupe du "
            "terrain sont posées sur le profil RGE ALTI en leur appliquant les "
            f"hauteurs déclarées ({nombre_fr(table.point_bas_m)} m au point "
            f"bas, {nombre_fr(table.point_haut_m)} m au point haut) et non "
            "les altitudes du plan."
        )

    style_table = STYLES["tables_pv"].style
    trait = type(TRAIT_FORT)(
        trait=style_table.trait, epaisseur_mm=0.55, remplissage="none"
    )
    posees = 0
    for entite in contrat.entites("tables_pv"):
        traversee = entite.geometrie.intersection(ligne)
        if traversee.is_empty:
            continue
        abscisses = sorted(
            ligne.project(Point(coord)) for coord in _extremites(traversee)
        )
        if len(abscisses) < 2 or abscisses[-1] - abscisses[0] <= 0:
            continue
        debut, fin = abscisses[0], abscisses[-1]

        if z_reel and entite.z_min is not None and entite.z_max is not None:
            z_bas, z_haut = entite.z_min, entite.z_max
        else:
            sol = _altitude_a(profil, (debut + fin) / 2.0)
            z_bas = sol + table.point_bas_m
            z_haut = sol + table.point_haut_m

        # Le bord bas d'une table est celui qui regarde le sud : les rangées
        # sont orientées vers l'équateur, et la coupe leur est perpendiculaire.
        # C'est donc l'extrémité la plus au sud de la traversée qui porte le
        # point bas, quel que soit le sens du tracé A vers A'.
        if _extremite_sud(ligne, debut) <= _extremite_sud(ligne, fin):
            bas_x, haut_x = debut, fin
        else:
            bas_x, haut_x = fin, debut
        dessin.ligne((bas_x, z_bas), (haut_x, z_haut), trait)
        # Un pieu, pour que la table ne flotte pas au-dessus du terrain.
        milieu = (debut + fin) / 2.0
        dessin.ligne(
            (milieu, _altitude_a(profil, milieu)),
            (milieu, (z_bas + z_haut) / 2.0),
            TRAIT_FIN,
        )
        posees += 1
    return posees, avertissements


def _extremites(geometrie):
    """Extrémités d'une intersection, qu'elle soit point, segment ou multiple."""
    if geometrie.geom_type == "Point":
        return [(geometrie.x, geometrie.y)]
    if geometrie.geom_type == "LineString":
        return [geometrie.coords[0], geometrie.coords[-1]]
    if hasattr(geometrie, "geoms"):
        points = []
        for partie in geometrie.geoms:
            points.extend(_extremites(partie))
        return points
    return []


def _extremite_sud(ligne: LineString, abscisse: float) -> float:
    """Ordonnée Lambert 93 d'un point de la coupe, repérée par son abscisse."""
    return ligne.interpolate(abscisse).y


def _portions_traversees(ligne, geometries) -> list:
    """Abscisses de début et de fin des portions de coupe dans ces géométries."""
    portions = []
    for geometrie in geometries:
        traversee = geometrie.intersection(ligne)
        if traversee.is_empty:
            continue
        parties = (
            traversee.geoms
            if traversee.geom_type.startswith("Multi")
            or traversee.geom_type == "GeometryCollection"
            else [traversee]
        )
        for partie in parties:
            abscisses = [
                ligne.project(Point(coord)) for coord in _extremites(partie)
            ]
            if len(abscisses) < 2:
                continue
            debut, fin = min(abscisses), max(abscisses)
            if fin - debut > 0:
                portions.append((debut, fin))
    return portions


def _sols_sur_le_profil(dessin, contrat: Contrat, profil) -> None:
    """Pistes et plateformes, posées sur le terrain là où la coupe les croise.

    Elles se dessinent en léger relief sur le profil, à l'épaisseur d'un
    figuré : une piste lourde fait 25 cm de structure, soit un quart de
    millimètre au 1/1 000, et personne ne la verrait.
    """
    ligne = _ligne_de_coupe(contrat)
    epaisseur = dessin.metres(EPAISSEUR_PISTE_MM)
    for categorie in SOLS_TRAVERSES:
        geometries = list(contrat.geometries(categorie))
        geometries.extend(contrat.voiries_de(categorie))
        if not geometries:
            continue
        style = STYLES[categorie].style
        for debut, fin in _portions_traversees(ligne, geometries):
            pas = max((fin - debut) / 24.0, 0.5)
            abscisses = []
            courante = debut
            while courante < fin:
                abscisses.append(courante)
                courante += pas
            abscisses.append(fin)
            # La piste est **incrustée** dans le terrain : décaissée puis
            # remblayée, sa surface est celle du sol. Sa bande se dessine donc
            # sous le profil, et non par-dessus.
            haut = [(x, _altitude_a(profil, x)) for x in abscisses]
            bas = [
                (x, _altitude_a(profil, x) - epaisseur)
                for x in reversed(abscisses)
            ]
            dessin.polyligne(haut + bas, style, fermer=True)


def _cloture_sur_le_profil(dessin, contrat: Contrat, profil) -> list:
    """La clôture, en élévation, là où la coupe franchit son contour."""
    geometries = contrat.geometries("cloture")
    if not geometries:
        return []
    ligne = _ligne_de_coupe(contrat)
    style = STYLES["cloture"].style
    fin = type(TRAIT_FIN)(trait=style.trait, epaisseur_mm=0.2, remplissage="none")

    passages = []
    for geometrie in geometries:
        contour = geometrie.boundary
        croisement = contour.intersection(ligne)
        if croisement.is_empty:
            continue
        parties = (
            croisement.geoms
            if hasattr(croisement, "geoms")
            else [croisement]
        )
        for partie in parties:
            for coord in _extremites(partie):
                passages.append(ligne.project(Point(coord)))
    if not passages:
        return [
            "La ligne de coupe ne franchit pas la clôture : elle ne montre pas "
            "les limites du projet. Vérifiez le tracé A-A'."
        ]

    debut_coupe, fin_coupe = profil[0][0], profil[-1][0]
    for abscisse in sorted(set(round(a, 2) for a in passages)):
        if not debut_coupe <= abscisse <= fin_coupe:
            continue
        sol = _altitude_a(profil, abscisse)
        haut = sol + HAUTEUR_CLOTURE_M
        dessin.ligne((abscisse, sol), (abscisse, haut), style)
        # Trois fils, pour que le poteau se lise comme une clôture.
        largeur = dessin.metres(1.2)
        for fraction in (0.35, 0.7, 1.0):
            hauteur = sol + HAUTEUR_CLOTURE_M * fraction
            dessin.ligne(
                (abscisse - largeur / 2.0, hauteur),
                (abscisse + largeur / 2.0, hauteur),
                fin,
            )
        dessin.texte(
            abscisse, haut, "Clôture", taille=5.5 * PT, ancre="middle",
            decalage_mm=(0.0, -1.4), couleur=style.trait,
        )
    return []


def _ouvrages_sur_le_profil(dessin, contrat: Contrat, profil) -> list:
    """Les ouvrages que la coupe traverse, en élévation sur le terrain.

    Un ouvrage sans cote normalisée n'est pas dessiné, et son absence est
    portée au rapport : le GeoPackage donne son emprise au sol, jamais sa
    hauteur, et l'inventer donnerait une coupe fausse d'aspect correct.
    """
    from ..erreurs import ErreurCoteOuvrage

    ligne = _ligne_de_coupe(contrat)
    avertissements = []
    avertissements.extend(_vegetation_sur_le_profil(dessin, contrat, profil, ligne))
    for categorie in OUVRAGES_TRAVERSES:
        for entite in contrat.entites(categorie):
            traversee = entite.geometrie.intersection(ligne)
            if traversee.is_empty:
                continue
            try:
                cote = contrat.cote_de_categorie(
                    categorie, surface_m2=entite.geometrie.area
                )
                hauteur = cote.hauteur_m
            except ErreurCoteOuvrage as exc:
                avertissements.append(
                    f"Coupe du terrain : « {categorie} » est traversé par la "
                    f"coupe mais n'est pas dessiné — {exc}"
                )
                continue
            abscisses = sorted(
                ligne.project(Point(coord)) for coord in _extremites(traversee)
            )
            if len(abscisses) < 2:
                continue
            debut, fin = abscisses[0], abscisses[-1]
            sol = _altitude_a(profil, (debut + fin) / 2.0)
            dessin.rectangle(
                debut, sol, fin - debut, hauteur, STYLES[categorie].style
            )
    return avertissements


def _vegetation_sur_le_profil(dessin, contrat: Contrat, profil, ligne) -> list:
    """Haies et arbres traversés par la coupe, à hauteur conventionnelle.

    Ni le tableau bilan ni le plan ne portent de hauteur de végétation. Une
    haie de deux mètres devant une rangée change pourtant la perception du
    projet, et c'est ce qu'un instructeur regarde : elle doit apparaître, et sa
    hauteur doit être annoncée pour ce qu'elle est.
    """
    messages = []
    employees = False
    for categorie, hauteur in VEGETATION_TRAVERSEE.items():
        geometries = contrat.geometries(categorie)
        if not geometries:
            continue
        style = STYLES[categorie].style
        for debut, fin in _portions_traversees(ligne, geometries):
            sol = _altitude_a(profil, (debut + fin) / 2.0)
            largeur = max(fin - debut, dessin.metres(1.2))
            centre = (debut + fin) / 2.0
            # Un houppier sur son tronc, et non un rectangle, qui se lirait
            # comme un bâtiment.
            tronc = max(largeur * 0.12, dessin.metres(0.4))
            dessin.rectangle(
                centre - tronc / 2.0, sol, tronc, hauteur * 0.35,
                type(TRAIT_FIN)(trait="#5a4020", epaisseur_mm=0.2,
                                remplissage="#8a6a3a"),
            )
            demi = largeur / 2.0
            bas = sol + hauteur * 0.3
            sommet = sol + hauteur
            dessin.polyligne(
                [
                    (centre - demi, bas),
                    (centre - demi * 0.85, sommet - hauteur * 0.22),
                    (centre - demi * 0.35, sommet),
                    (centre + demi * 0.35, sommet),
                    (centre + demi * 0.85, sommet - hauteur * 0.22),
                    (centre + demi, bas),
                ],
                style,
                fermer=True,
            )
            employees = True
    if employees:
        messages.append(MESSAGE_VEGETATION)
    return messages


def _bandeau_parcellaire(dessin, contrat: Contrat, profil, alt_min) -> list:
    """Limites de parcelle traversées et numéros, dans un bandeau sous la coupe.

    C'est ce que porte la coupe du dossier de référence, avec ses AD 211 /
    AD 212 / AD 213 : sans cela, rien ne dit sur quelles parcelles la coupe
    passe. Le parcellaire vient du WFS IGN, comme partout ailleurs.

    Le bandeau est **sous** le terrain. Portés en haut du dessin, les numéros
    tombaient au milieu des tables : celui de la parcelle centrale de Saint-Cyr
    était illisible, recouvert par une rangée.
    """
    ligne = _ligne_de_coupe(contrat)
    minx, miny, maxx, maxy = ligne.bounds
    tampon = 20.0
    parcelles = telecharger_parcelles(
        (minx - tampon, miny - tampon, maxx + tampon, maxy + tampon)
    )
    if not parcelles:
        return [
            "Coupe du terrain : aucune parcelle cadastrale le long de la "
            "coupe, le bandeau parcellaire n'est pas porté."
        ]

    debut_coupe, fin_coupe = profil[0][0], profil[-1][0]
    traversees = []
    for parcelle in parcelles:
        portions = _portions_traversees(ligne, [parcelle.geometrie])
        for debut, fin in portions:
            traversees.append((debut, fin, parcelle.numero))
    if not traversees:
        return [
            "Coupe du terrain : la coupe ne traverse aucune parcelle du "
            "Parcellaire Express."
        ]
    traversees.sort()

    haut = alt_min - dessin.metres(RETRAIT_BANDEAU_MM)
    bas = haut - dessin.metres(HAUTEUR_BANDEAU_MM)
    trait = type(TRAIT_FIN)(trait="#7a4b00", epaisseur_mm=0.2, remplissage="none")
    dessin.ligne((debut_coupe, haut), (fin_coupe, haut), trait)
    dessin.ligne((debut_coupe, bas), (fin_coupe, bas), trait)

    ruptures = sorted({round(a, 2) for debut, fin, _ in traversees for a in (debut, fin)})
    for abscisse in ruptures:
        if not debut_coupe <= abscisse <= fin_coupe:
            continue
        dessin.ligne((abscisse, bas), (abscisse, haut), trait)
        # Le trait de rappel remonte jusqu'au terrain, pour qu'on sache où la
        # limite tombe sur la coupe.
        dessin.ligne(
            (abscisse, haut),
            (abscisse, _altitude_a(profil, abscisse)),
            type(TRAIT_FIN)(trait="#7a4b00", epaisseur_mm=0.15,
                            remplissage="none", tirets="1.4 1.0"),
        )

    milieu = (haut + bas) / 2.0
    for debut, fin, numero in traversees:
        centre = (max(debut, debut_coupe) + min(fin, fin_coupe)) / 2.0
        if not debut_coupe <= centre <= fin_coupe:
            continue
        largeur_mm = dessin.longueur(min(fin, fin_coupe) - max(debut, debut_coupe))
        if largeur_mm < dessin.planche.mesurer_texte(numero, 6.0 * PT) + 1.0:
            # Une parcelle trop étroite sur le papier porterait un numéro
            # débordant sur ses voisines : elle n'en porte pas.
            continue
        dessin.texte(
            centre, milieu, numero, taille=6.0 * PT, ancre="middle",
            couleur="#5a3800", gras=True, decalage_mm=(0.0, 1.0),
        )
    dessin.texte(
        debut_coupe, bas, "Limites de parcelle", taille=5.5 * PT,
        ancre="start", couleur="#5a3800", decalage_mm=(0.0, 3.2),
    )
    return []


def _pas_altimetrique(dessin) -> float:
    """Plus petit pas dont deux graduations restent séparées sur le papier."""
    for pas in PAS_ALTIMETRIQUES_M:
        if dessin.longueur(pas) >= ECART_GRADUATIONS_MM:
            return pas
    return PAS_ALTIMETRIQUES_M[-1]


def _axe_altimetrique(dessin, profil, alt_min, alt_max, table) -> None:
    """Axe des altitudes NGF, gradué, à gauche de la coupe.

    Une coupe de terrain sans cote d'altitude ne se lit pas : la dénivelée y
    est vraie mais rien ne dit à quelle hauteur on est. L'axe est aussi ce qui
    rend l'isotropie du dessin vérifiable — un mètre y mesure la même chose
    qu'un mètre le long de la coupe.
    """
    pas = _pas_altimetrique(dessin)
    bas = math.floor(alt_min / pas) * pas
    haut = math.ceil((alt_max + table.point_haut_m * 0.4) / pas) * pas
    x_axe = profil[0][0] - dessin.metres(4.0)

    dessin.ligne((x_axe, bas), (x_axe, haut), TRAIT_MOYEN)
    nombre = int(round((haut - bas) / pas))
    for index in range(nombre + 1):
        altitude = bas + index * pas
        dessin.ligne((x_axe, altitude), (profil[0][0], altitude), TRAIT_COTE)
        dessin.texte(
            x_axe, altitude, f"{nombre_fr(altitude, 1)}", taille=5.5 * PT,
            ancre="end", decalage_mm=(-0.8, 0.8),
        )
    dessin.texte(
        x_axe, haut, "NGF", taille=5.5 * PT, ancre="end",
        decalage_mm=(-0.8, -2.2), couleur=GRIS,
    )


def _reperes_de_coupe(dessin, profil, alt_min) -> None:
    """Les repères A et A' aux extrémités, comme sur le plan de masse."""
    for abscisse, lettre, direction in (
        (profil[0][0], "A", (1.0, 0.0)),
        (profil[-1][0], "A'", (-1.0, 0.0)),
    ):
        x_mm, y_sol_mm = dessin.point(abscisse, alt_min)
        y_mm = y_sol_mm + 7.0
        repere_coupe(dessin.planche, x_mm, y_mm, lettre, direction)
        dessin._noter((x_mm, y_mm))
