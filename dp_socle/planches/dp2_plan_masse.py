"""DP 2 — Plan de masse, à échelle adaptative.

Le cadrage se fait sur l'**emprise cadastrale plus 10 % de marge**, et non sur
la clôture : le plan doit montrer le contexte parcellaire alentour, comme celui
du dossier de référence. Une planche cadrée sur la seule clôture donnerait un
projet posé dans le vide.

Pas de fond raster. Le plan de masse de référence est sur fond blanc, et une
ortho écraserait la lecture des ouvrages — c'est DP 1-2 qui porte la photo
aérienne.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from shapely.geometry import box

from ..contrat import Contrat
from ..dossier import SUFFIXES_DETAIL_PLAN_DE_MASSE, piece
from ..echelle import echelle_adaptative, mm_vers_metres
from ..erreurs import ErreurComposition, ErreurDP, ErreurEchelle, ErreurService
from ..geometrie import Emprise
from ..ign import (
    telecharger_batiments,
    telecharger_batiments_bd_topo,
    telecharger_parcelles,
    telecharger_troncons_de_route,
)
from ..planche import (
    GRIS,
    MOTIF_BATIMENT,
    STYLE_BATIMENT,
    STYLE_PARCELLE,
    TAILLE_COURANTE,
    TAILLE_ETIQUETTE,
    Planche,
    Style,
    nombre_fr,
)
from ..projet import Projet
from .commun import Sortie, nouvelle_planche
from .dp1_3_cadastre import SURFACE_MIN_ETIQUETTE_MM2
from .legende import dessiner_legende, hauteur_bloc
from .modules import tracer_trame, trame_du_projet
from .palette import (
    STYLES,
    EntreeDP,
    construire_legende,
    objets_a_dessiner,
    style,
    style_de,
)
from .primitives import COTE_REPERE_MM, TRAIT_AXE, TRAIT_COTE, repere_coupe, union_valide

NUMERO = "DP 2"
TITRE = piece("DP 2").titre

#: Échelles autorisées pour le plan de masse (décision D2).
ECHELLES_PLAN_MASSE = (500, 1000, 2000, 2500, 5000)

#: Marge autour de l'emprise cadastrale, en fraction de ses dimensions.
MARGE = 0.10

#: Distance des repères A et A' au-delà de l'extrémité de la ligne de coupe,
#: en millimètres papier : ils doivent se lire hors du dessin qu'ils repèrent.
RECUL_REPERE_MM = 4.0

LARGEUR_LEGENDE_MM = 82.0

#: La ligne de source, en pied du dessin, et son corps en millimètres.
SOURCE = (
    "Parcellaire et bâtiments : IGN — Parcellaire Express (PCI), WFS "
    "Géoplateforme. Ouvrages : plan du bureau d'études."
)
TAILLE_SOURCE = 1.9

#: L'axe d'une voie publique jusqu'où une cote est prise (C2, C8) : en gris,
#: pour ne pas se lire comme la ligne de coupe, qui est noire.
STYLE_AXE_DE_VOIE = Style(trait="#6b6b6b", epaisseur_mm=0.25, tirets="4 1 0.6 1")

#: Les planches de détail de la zone technique, dans l'ordre (lot 10, D7) :
#: DP 2 bis, ter… Ce sont les pièces facultatives que `dossier.PIECES` connaît,
#: et la liste vient de lui.
SUFFIXES_DETAIL = SUFFIXES_DETAIL_PLAN_DE_MASSE

#: L'échelle d'une planche de détail : la plus grande de celles-ci où tiennent
#: les ouvrages de la zone et le bout de leurs cotes, avec cette marge (D7).
ECHELLES_DETAIL = (200, 500, 1000)
MARGE_DETAIL = 0.25

#: Sur la DP 2, le cadre d'une zone partie en détail entoure ses ouvrages à
#: cela près, en bleu tireté, et son renvoi s'écrit de la même couleur.
MARGE_CADRE_DETAIL_MM = 3.0
STYLE_CADRE_DETAIL = Style(
    trait="#1f4e79", epaisseur_mm=0.35, remplissage="none", tirets="2.5 1.2"
)
COULEUR_RENVOI = "#1f4e79"
TAILLE_RENVOI = 2.2

#: Ce que la légende gagne avec les cotes (lot 10, D9).
LIBELLE_COTE = "Cote, en mètres"
LIBELLE_AXE_DE_VOIE = "Axe de voie (BD TOPO, IGN)"

#: Le pied énonce les règles, une ligne par idée : d'un seul tenant, la phrase
#: dépassait 200 mm (07/11/2026). Celles de la DP 2, puis celles de la planche
#: qui porte des cotes d'ouvrages (D9, 08 et 09/11/2026).
PIED_DP2 = (
    "Cotes en mètres, mesurées en Lambert 93. Limite parcellaire : celle du terrain "
    "d'assiette (parcellaire IGN). Voie publique (axe, ou extrémité quand elle s'arrête "
    "avant le site) et habitation la plus proche selon la BD TOPO (IGN).",
    "Constructions en légende : longueur × largeur, h : hauteur (catalogue UNITe ; "
    "clôture et portail : standard UNITe ; tables : hauteur maximale du tableau bilan).",
)
PIED_OUVRAGES = (
    "Distances entre ouvrages permanents voisins, et à la limite parcellaire, cotées en "
    "deçà de 30 m ; batteries et locaux de stockage cotés à la limite parcellaire à toute "
    "distance.",
    "Batteries et citernes : distance la plus courte jusqu'aux panneaux ; poste de "
    "livraison coté jusqu'à l'axe de la voie publique la plus proche, en deçà de 30 m.",
)

#: Les lignes du pied s'empilent au-dessus de la ligne de source, de ce pas.
PAS_PIED_MM = 2.6


#: Part du bloc de légende que le dessin peut occuper sans qu'on le déplace.
#: Sous ce seuil, la légende garde le coin du dossier de référence : une
#: planche où elle ne gênait pas ne doit pas changer d'allure.
RECOUVREMENT_LEGENDE_TOLERE = 0.02

#: Rayon dont on épaissit le dessin avant de mesurer ce que la légende
#: couvrirait, en mètres. Une clôture est une ligne, d'aire nulle : sans cette
#: épaisseur elle passerait pour de la place libre.
EPAISSEUR_MESURE_LEGENDE_M = 2.0


def _coin_de_legende(planche, zone, objets, largeur_mm, hauteur_mm, traits=(),
                     pied_mm: float = 0.0):
    """Coin de la zone de dessin où la légende masque le moins le plan.

    Le bloc se posait toujours en haut à gauche. Relevé le 30/09/2026 sur
    Auzainvilliers : le site passe dessous, et le cadre blanc de la légende
    couvre une piste et une plateforme. Une planche d'instruction qui cache une
    partie de ce qu'elle montre est fausse par omission.

    L'ordre des coins est celui du dossier de référence — haut-gauche d'abord —
    et la légende n'en bouge que si le dessin l'occupe vraiment.

    Depuis le lot 10 (D9), elle ne couvre ni une cote ni le cadre d'un
    détail : posée sans connaître les cotes, elle en cachait une (« 13,4 m
    (limite) », Auzainvilliers, 03/11/2026). Un coin dont le bloc touche un
    des `traits`, en Lambert 93, est écarté ; s'ils les touchent tous, rien
    n'est rendu, et l'appelant cherche ailleurs. Les coins du bas se posent
    au-dessus du pied, haut de `pied_mm` : la légende le recouvrait (Saint-Cyr,
    DP 2 bis, 07/11/2026).
    """
    from shapely.geometry import box as _boite
    from shapely.ops import unary_union as _union

    x, y, largeur_zone, hauteur_zone = zone
    coins = (
        (x + 3.0, y + 3.0),
        (x + largeur_zone - largeur_mm - 3.0, y + 3.0),
        (x + 3.0, y + hauteur_zone - hauteur_mm - 3.0 - pied_mm),
        (x + largeur_zone - largeur_mm - 3.0, y + hauteur_zone - hauteur_mm - 3.0 - pied_mm),
    )
    transformation = planche.transformation
    if transformation is None:
        return coins[0]

    def vers_l93(x_mm, y_mm):
        return (
            transformation._origine_x
            + (x_mm - transformation._x_mm) / transformation.mm_par_metre,
            transformation._origine_y
            - (y_mm - transformation._y_mm) / transformation.mm_par_metre,
        )

    def boite_du_coin(coin):
        x0, y0 = vers_l93(coin[0], coin[1])
        x1, y1 = vers_l93(coin[0] + largeur_mm, coin[1] + hauteur_mm)
        return _boite(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    libres = [
        coin for coin in coins
        if not any(boite_du_coin(coin).intersects(trait) for trait in traits)
    ]
    if not libres:
        return None
    dessin = [g for _, geometries in objets for g in geometries]
    if not dessin:
        return libres[0]
    couvert = _union(dessin).buffer(EPAISSEUR_MESURE_LEGENDE_M)

    parts = []
    for coin in libres:
        boite = boite_du_coin(coin)
        aire = boite.area
        parts.append(boite.intersection(couvert).area / aire if aire else 0.0)

    for coin, part in zip(libres, parts):
        if part <= RECOUVREMENT_LEGENDE_TOLERE:
            return coin
    return libres[parts.index(min(parts))]


def _place_de_la_legende(planche, objets, largeur_mm, nb_entrees, traits, pied_mm):
    """Le coin de la légende, et sur combien de colonnes : (position, colonnes, message).

    Un coin qui ne couvre ni une cote ni le cadre d'un détail, d'abord sur une
    colonne ; puis sur deux, deux fois moins haute : sur la DP 2
    d'Auzainvilliers, ses vingt entrées couvraient le haut du cadre du détail
    (08/11/2026). Faute de coin même ainsi, le coin le moins dessiné, et le
    message le dit (D9).
    """
    zone = planche.zone_dessin()
    hauteur = hauteur_bloc(nb_entrees)
    coin = _coin_de_legende(planche, zone, objets, largeur_mm, hauteur, traits, pied_mm)
    if coin is not None:
        return coin, 1, None
    demi = hauteur_bloc(math.ceil(nb_entrees / 2))
    coin = _coin_de_legende(planche, zone, objets, 2 * largeur_mm, demi, traits, pied_mm)
    if coin is not None:
        return coin, 2, (
            f"Légende sur deux colonnes ({nb_entrees} entrées) : aucun coin ne la "
            "reçoit sur une seule sans couvrir une cote ou le cadre d'un détail."
        )
    coin = _coin_de_legende(planche, zone, objets, largeur_mm, hauteur, (), pied_mm)
    return coin, 1, (
        "Légende : aucun coin ne la reçoit sans couvrir une cote ou le cadre d'un "
        "détail, ni sur une colonne ni sur deux ; elle est posée au coin le moins "
        "dessiné."
    )


def _largeur_de_legende(planche, entrees) -> float:
    """La largeur de la légende : 82 mm, ou ce que demande son intitulé le plus long (D12).

    La légende n'a pas de retour à la ligne. Avec leurs dimensions, les
    intitulés s'allongent — celui du PDL/PTR d'Auzainvilliers tenait en 79 mm
    des 82 (08/11/2026) —, et un intitulé renommé peut aller au-delà : la
    légende s'élargit plutôt que de le laisser déborder de son cadre.
    """
    from .legende import ECART_LIBELLE_MM, LARGEUR_SYMBOLE_MM, MARGE_MM

    texte = max(
        (planche.mesurer_texte(entree.libelle, TAILLE_COURANTE) for entree in entrees),
        default=0.0,
    )
    besoin = texte + 2 * MARGE_MM + LARGEUR_SYMBOLE_MM + ECART_LIBELLE_MM
    return max(LARGEUR_LEGENDE_MM, float(math.ceil(besoin + 1.0)))


def _hauteur_du_pied(nb_lignes: int) -> float:
    """Ce dont les coins du bas de la légende remontent pour laisser le pied lisible.

    Le pied, c'est la ligne de source et les `nb_lignes` qui s'empilent
    au-dessus d'elle ; la légende garde déjà 3 mm du bord.
    """
    haut = (5.6 + PAS_PIED_MM * (nb_lignes - 1)) if nb_lignes else 2.5
    return haut + TAILLE_SOURCE + 0.5 - 3.0


def _libelle_absence() -> str:
    """L'absence d'habitation à 1 000 m, telle que la légende la dit (D5)."""
    from .cotation_plan_masse import RAYON_HABITATION_M

    return (
        f"Aucune habitation à moins de {nombre_fr(RAYON_HABITATION_M, 0)} m de la "
        "clôture (BD TOPO, IGN)"
    )


def _ce_que_la_planche_cadre(contrat: Contrat, emprise: Emprise):
    """Ce sur quoi le plan de masse se cadre : la zone clôturée, et à défaut l'emprise.

    Décision du chef de projet du 02/10/2026 : **la zone clôturée**, et non
    l'emprise cadastrale déposée. Celle-ci dit ce qui est maîtrisé — parfois
    plusieurs fois le projet — et l'échelle s'y réglait : à Boisné-La Tude, le
    plan de masse sortait au 1:5 000, le site perdu au milieu de deux
    kilomètres de parcellaire, là où Saint-Cyr-en-Val — dont l'emprise épouse
    la clôture à 1 % près — sortait au 1:2 000, bien lisible.

    Sans clôture au contrat, l'emprise reprend son rôle : c'est la seule
    étendue qui reste, et l'appelant le dit.

    Rend (ce qui a cadré, dimensions en mètres, centre).
    """
    cloture = union_valide(contrat.geometries("cloture"))
    if cloture is None or cloture.is_empty:
        return "emprise", emprise.dimensions_m, emprise.centre
    minx, miny, maxx, maxy = cloture.bounds
    return (
        "cloture",
        (maxx - minx, maxy - miny),
        ((minx + maxx) / 2.0, (miny + maxy) / 2.0),
    )


def generer(
    projet: Projet,
    contrat: Contrat,
    emprise: Emprise,
    dossier: str | Path,
    numero: str | None = None,
) -> Sortie:
    from .cotation_plan_masse import raisons_du_detail

    planche = nouvelle_planche(projet, NUMERO, numero=numero)
    zone = planche.zone_dessin()

    avertissements = []
    cadre_sur, dimensions, centre = _ce_que_la_planche_cadre(contrat, emprise)
    denominateur = echelle_adaptative(
        *dimensions, zone, marge=MARGE, valeurs=ECHELLES_PLAN_MASSE
    )
    planche.definir_echelle(denominateur)
    planche.centrer_sur(centre)

    minx, miny, maxx, maxy = planche.emprise_terrain()
    if cadre_sur == "emprise":
        avertissements.append(
            "Pas de clôture au contrat : le plan de masse est cadré sur "
            "l'emprise cadastrale, faute de mieux. Si elle déborde largement du "
            "projet, la planche sera peu zoomée."
        )

    # 1. Parcellaire du WFS IGN, en filet fin, avec les numéros de parcelle.
    #    Le cadastre embarqué par le bureau d'études est écarté d'office : le
    #    dossier prend le sien de l'IGN, que l'instructeur peut vérifier.
    tampon = max(50.0, 0.05 * max(maxx - minx, maxy - miny))
    cadre_requete = (minx - tampon, miny - tampon, maxx + tampon, maxy + tampon)
    parcelles = telecharger_parcelles(cadre_requete)
    if not parcelles:
        raise ErreurService(
            "Aucune parcelle cadastrale sur l'emprise du plan de masse. "
            "Le plan de masse porte le parcellaire : il n'est pas produit sans."
        )
    # 2. Bâtiments, hachurés à 45° comme sur DP 1-3.
    batiments = telecharger_batiments(cadre_requete)

    # 3. Les catégories du GeoPackage, dans l'ordre de dessin du contrat.
    objets = objets_a_dessiner(contrat, avertissements)
    if not objets:
        raise ErreurComposition(
            "Le contrat ne porte aucun objet à dessiner : le plan de masse "
            "serait vide. Vérifiez l'appariement des calques à l'import."
        )
    lectures = (parcelles, batiments, objets)

    # 4. Les cotes (lot 10), calculées une fois pour la DP 2 et ses planches de
    #    détail : la place d'une valeur change d'un essai à l'autre, pas la cote.
    calcul = _calculer_les_cotes(contrat, emprise, parcelles, objets, denominateur, avertissements)

    # 5. Une zone technique part sur sa planche de détail quand la DP 2 la lit
    #    mal (D7, 04/11/2026) : une cote de moins de 3 mm se voit avant tout
    #    dessin ; une valeur sans place nette, ou une ligne sous la légende, ne
    #    se voient qu'en essayant la DP 2. Elle s'essaie donc, les zones fautives
    #    partent, et elle se refait sans elles : retirer une zone libère de la
    #    place, mais y pose un cadre, et la légende peut changer de coin. On
    #    recommence jusqu'à ce que plus aucune zone ne bouge.
    zones = calcul.zones
    partantes = {}
    for rang, zone_technique in enumerate(zones):
        raisons = raisons_du_detail(zone_technique, denominateur, [])
        if raisons:
            partantes[rang] = raisons
    for essai in range(1, len(zones) + 2):
        codes, refus = _codes_des_details(partantes, zones, calcul)
        cadres = [
            (codes[rang], _cadre_du_detail(zones[rang], calcul, denominateur))
            for rang in sorted(codes)
        ]
        a_poser = _a_poser_sur_la_dp2(calcul, codes)
        planche = nouvelle_planche(projet, NUMERO, numero=numero)
        planche.definir_echelle(denominateur)
        planche.centrer_sur(centre)
        # Le pied dit les règles de ce que la planche porte : celles des
        # ouvrages, tant qu'une zone y reste.
        pied = PIED_DP2 + (PIED_OUVRAGES if len(codes) < len(zones) else ())
        genes, messages, details = _composer(
            planche, projet, contrat, lectures, a_poser, calcul, cadres=cadres,
            pied=pied,
        )
        nouvelles = {}
        for rang, zone_technique in enumerate(zones):
            if rang in partantes:
                continue
            raisons = raisons_du_detail(zone_technique, denominateur, genes)
            if raisons:
                nouvelles[rang] = raisons
        if not nouvelles:
            break
        if essai > len(zones):
            messages.append(
                f"DP 2 : des zones techniques se lisent encore mal après {essai} "
                "essais ; elles restent sur la planche."
            )
            break
        partantes.update(nouvelles)
    avertissements.extend(refus)
    avertissements.extend(messages)
    avertissements.extend(gene.message for gene in genes)

    # 6. Les planches de détail, une par zone partie, à la suite de la DP 2.
    sorties_detail = []
    for rang_detail, rang in enumerate(sorted(codes)):
        code = codes[rang]
        avertissements.append(
            f"Zone technique ({_noms_des_ouvrages(zones[rang], calcul)}) : sur la "
            f"planche {code} — {' ; '.join(partantes[rang])}."
        )
        sorties_detail.append(_planche_de_detail(
            projet, contrat, code,
            None if numero is None else str(int(numero) + rang_detail + 1),
            zones[rang], lectures, calcul, dossier,
        ))

    chemin = planche.rendre_pdf(Path(dossier) / "DP_2_plan_de_masse.pdf")
    return Sortie(
        numero=NUMERO,
        titre=TITRE,
        chemin=chemin,
        echelle=denominateur,
        planche=planche,
        details={
            **details,
            "avertissements": avertissements,
            "planches_de_detail": sorties_detail,
        },
    )


def _composer(planche, projet, contrat, lectures, a_poser, calcul, cadres=(),
              detail: bool = False, pied=()):
    """Une planche du plan de masse : son fond, sa légende, et les cotes posées dessus.

    Sert à la DP 2, essai après essai, et à ses planches de détail (D7), sur les
    mêmes lectures. `a_poser` : les cotes de cette planche. `cadres` : sur la
    DP 2, le cadre de chaque zone partie en détail, avec son code. `detail` :
    une planche de détail ne montre qu'une partie du site, et ne dit pas des
    objets ou de la coupe qui tombent hors de son cadre qu'ils manquent.
    `pied` : les règles que la planche énonce sous son dessin, une ligne par
    idée (D9).

    Rend (gênes, messages, détails) : ce que la pose rend des cotes qui se
    lisent mal, ce que la planche a à dire, et de quoi remplir sa `Sortie`.
    """
    from .pose_des_cotes import AEviter, en_mm, poser_les_cotes

    messages = []
    parcelles, batiments, objets = lectures
    zone = planche.zone_dessin()
    minx, miny, maxx, maxy = planche.emprise_terrain()
    cadre_planche = box(minx, miny, maxx, maxy)

    for parcelle in parcelles:
        planche.ajouter_geometrie(parcelle.geometrie, STYLE_PARCELLE)

    #    Seuls les bâtiments qui tombent dans le cadre comptent pour la légende.
    #    La requête WFS déborde du cadre d'un tampon, pour que les limites soient
    #    tracées jusqu'au bord ; en tirer une entrée « Bâtiment » ferait
    #    annoncer à la légende un objet que la planche ne montre pas.
    batiments_visibles = [
        b for b in batiments if cadre_planche.intersects(b.geometrie)
    ]
    if batiments_visibles:
        planche.ajouter_definition(MOTIF_BATIMENT)
        for batiment in batiments_visibles:
            planche.ajouter_geometrie(batiment.geometrie, STYLE_BATIMENT)

    hors_cadre = []
    tables_visibles = []
    visibles = []
    for categorie, geometries in objets:
        # Une catégorie qui dessine aussi une surface ici : ses traits y sont
        # des détails posés dessus, et se tracent au filet.
        avec_surface = any(
            g.geom_type in ("Polygon", "MultiPolygon") for g in geometries
        )
        for geometrie in geometries:
            if not cadre_planche.intersects(geometrie):
                hors_cadre.append(categorie)
                continue
            planche.ajouter_geometrie(
                geometrie, style_de(categorie, geometrie, avec_surface)
            )
            if categorie not in visibles:
                visibles.append(categorie)
            if categorie == "tables_pv":
                tables_visibles.append(geometrie)

    # La trame des modules, par-dessus le contour des rangées : c'est elle qui
    # fait lire une table comme un panneau plutôt que comme une dalle, et c'est
    # ce que porte le plan de masse du dossier de référence.
    messages.extend(_tramer_les_tables(planche, contrat, tables_visibles))
    if hors_cadre and not detail:
        # Le contenu cartographique est découpé sur la zone de dessin : un objet
        # hors cadre disparaîtrait sans rien dire, et c'est exactement le genre
        # d'absence que personne ne remarque à la relecture.
        messages.append(
            f"{len(hors_cadre)} objet(s) du plan tombent hors du cadre de DP 2 "
            f"({', '.join(sorted(set(hors_cadre)))}) : ils ne sont pas dessinés. "
            "L'emprise cadastrale ne couvre pas tout le projet."
        )

    # Étiquettes de parcelle, là où la parcelle est assez grande sur le papier
    # pour en porter une — même mécanique que DP 1-3. Leur place se relève :
    # aucune valeur de cote ne doit les recouvrir (lot 10, D8 ; « 0495 » sous
    # une cote à Saint-Cyr, relecture du 08/11/2026).
    occupees = _etiqueter_parcelles(planche, parcelles, cadre_planche)

    # La ligne de coupe, en trait d'axe, et ses repères A / A'.
    trace = _tracer_ligne_coupe(planche, contrat, occupees)
    if trace is None and not detail:
        messages.append(
            "Aucune ligne de coupe au contrat : le plan de masse ne porte pas "
            "les repères A et A', et DP 3 n'est pas produite."
        )

    # L'axe de chaque voie jusqu'où une cote posée ici est prise (C2, C8), et
    # le cadre de chaque zone partie en détail.
    for cote, axe in calcul.axes:
        if any(cote is posee for posee in a_poser):
            planche.ajouter_geometrie(axe, STYLE_AXE_DE_VOIE)
    for _, cadre in cadres:
        planche.ajouter_geometrie(cadre, STYLE_CADRE_DETAIL)

    # La légende, bâtie sur ce qui vient d'être dessiné, et sur rien d'autre.
    # Sa place est connue avant les cotes, qui ne doivent pas y poser leurs
    # valeurs ; elle se dessine après elles. Une planche de détail ne montre
    # qu'une partie du site : sa légende ne nomme que ce qu'elle montre.
    categories_tracees = visibles if detail else [c for c, _ in objets]
    # Les intitulés que le chef de projet a corrigés à l'écran, s'il en a
    # corrigé : la légende est dans l'image de la planche, elle ne se retouche
    # donc pas après coup. Chaque construction y porte ses dimensions (D12),
    # ajoutées à l'intitulé quel qu'il soit : la maquette ne les posait que sur
    # l'intitulé par défaut, et un intitulé renommé les perdait sans le dire.
    # Un intitulé vide le reste, pour que la légende le refuse.
    libelles = dict(projet.legendes or {})
    for categorie, complement in calcul.dimensions.items():
        if categorie not in categories_tracees:
            continue
        intitule = libelles.get(categorie, style(categorie).libelle)
        if str(intitule).strip():
            libelles[categorie] = f"{intitule} {complement}"
    entrees = construire_legende(
        categories_tracees,
        avec_parcelles=True,
        avec_batiments=bool(batiments_visibles),
        libelles=libelles,
    )
    # Ce que la planche porte du lot 10 (D9), et l'absence d'habitation, qui
    # est un résultat (D5).
    if a_poser:
        entrees.append(EntreeDP(LIBELLE_COTE, TRAIT_COTE, "ligne"))
    if any(any(cote is posee for posee in a_poser) for cote, _ in calcul.axes):
        entrees.append(EntreeDP(LIBELLE_AXE_DE_VOIE, STYLE_AXE_DE_VOIE, "ligne"))
    if calcul.sans_habitation and not detail:
        entrees.append(EntreeDP(_libelle_absence(), Style(), "aucun"))
    largeur_legende = _largeur_de_legende(planche, entrees)

    # Le pied, au-dessus de la ligne de source : une ligne par idée (D9).
    x_source, y_source = zone[0] + 3.0, zone[1] + zone[3] - 2.5
    occupees.append(_boite_de_ligne(planche, x_source, y_source, SOURCE, TAILLE_SOURCE))
    for rang, ligne in enumerate(reversed(pied)):
        y_ligne = zone[1] + zone[3] - 5.6 - PAS_PIED_MM * rang
        planche.ajouter_texte(x_source, y_ligne, ligne, taille=TAILLE_SOURCE, halo=True)
        occupees.append(_boite_de_ligne(planche, x_source, y_ligne, ligne, TAILLE_SOURCE))

    # La légende, hors des cotes, des cadres de détail et du pied (D9).
    traits = [cote.ligne for cote in a_poser] + [cadre.exterior for _, cadre in cadres]
    position, colonnes, message = _place_de_la_legende(
        planche, objets, largeur_legende, len(entrees), traits, _hauteur_du_pied(len(pied))
    )
    if message:
        messages.append(message)
    hauteur_legende = hauteur_bloc(math.ceil(len(entrees) / colonnes))
    boite_legende = (
        position[0], position[1],
        position[0] + colonnes * largeur_legende, position[1] + hauteur_legende,
    )
    occupees.append(boite_legende)

    # Le renvoi de chaque cadre, une fois la légende placée : écrit avant elle,
    # il tombait dessous (04/11/2026).
    lignes = [en_mm(planche, cote.ligne) for cote in a_poser]
    genants = [en_mm(planche, e.geometrie) for e in calcul.a_eviter if e.gene]
    for code, cadre in cadres:
        place = _poser_le_renvoi(planche, code, cadre, occupees, lignes, genants)
        if place is None:
            messages.append(
                f"Renvoi au {code} : aucune place libre autour de son cadre, "
                "posé au mieux."
            )
        else:
            occupees.append(place)

    # Les cotes. Le cadre d'un détail est à éviter, pas interdit : le traverser
    # ne cache rien (D8).
    a_eviter = list(calcul.a_eviter) + [
        AEviter("le cadre d'un détail", cadre.exterior, gene=False) for _, cadre in cadres
    ]
    genes = poser_les_cotes(
        planche, a_poser, occupees,
        traits=[trace] if trace is not None else [],
        a_eviter=a_eviter, masques=[boite_legende], rapport=messages,
    )

    dessiner_legende(
        planche, entrees, position=position, largeur_mm=largeur_legende, colonnes=colonnes
    )
    planche.ajouter_texte(
        x_source, y_source, SOURCE, taille=TAILLE_SOURCE, couleur=GRIS, halo=True,
    )
    return genes, messages, {
        "categories_dessinees": categories_tracees,
        "nb_parcelles": len(parcelles),
        "nb_batiments": len(batiments_visibles),
        "coupe_tracee": trace is not None,
    }


@dataclass
class _Calcul:
    """Les cotes du plan de masse, calculées une fois pour la DP 2 et ses détails.

    `hors_zones` : celles qui restent sur la DP 2 (C1, C2, C4, C5, C6).
    `zones` : les zones techniques, avec leurs cotes C3, C7 et C8 (D7).
    `axes` : (cote, axe) de chaque cote vers une voie, l'axe se dessinant là où
    sa cote est posée. `a_eviter` : ce que les valeurs évitent (D8).
    """

    hors_zones: list
    zones: list
    axes: list
    a_eviter: list
    ouvrages: list
    #: Ce que chaque construction ajoute à son intitulé de légende (D12).
    dimensions: dict = field(default_factory=dict)
    #: Vrai quand la BD TOPO a répondu, sans habitation à 1 000 m (D5).
    sans_habitation: bool = False
    #: (C2, C8) quand C2 part déjà du poste de livraison vers sa voie : la même
    #: cote, hors zone et dans la zone du poste. Voir `_a_poser_sur_la_dp2`.
    doubles: tuple = ()


def _calculer_les_cotes(contrat, emprise, parcelles, objets, denominateur, rapport) -> _Calcul:
    """Les cotes du plan de masse (lot 10), calculées, et ce que le calcul écarte.

    Le calcul est dans `cotation_plan_masse`, qui ne dessine rien ; la pose,
    dans `pose_des_cotes`. Les cotes se prennent sur ce que la planche
    dessine, `objets` : une clôture refermée par `objets_a_dessiner` l'est
    aussi pour ses cotes. Chaque cote qu'une règle écarte est nommée au
    `rapport` avec sa raison — aucune n'est retirée en silence (D9).
    """
    from shapely.ops import unary_union

    from . import cotation_plan_masse as cotation
    from .pose_des_cotes import AEviter

    dessines = dict(objets)
    clotures = list(dessines.get("cloture", []))
    tables = cotation.polygones_de(dessines.get("tables_pv", []))

    # C1 — tables → limite parcellaire, à travers la clôture. La limite est
    # celle du terrain d'assiette, retenu par la règle de la DP 1-3 (D4).
    terrain = cotation.terrain_d_assiette(parcelles, emprise.geometrie)
    enclos = cotation.enclos_de_la_cloture(clotures, rapport)
    pans = cotation.pans_de_la_cloture(enclos)
    cotes_des_pans = cotation.cotes_tables_cloture_limite(
        pans, tables, terrain, denominateur, rapport
    )
    cotes = [cotes_du_pan.tables_limite for cotes_du_pan in cotes_des_pans]

    # C5 — l'écartement entre deux rangées, une fois, à la valeur de la coupe :
    # celle de `geometrie_table`, la fonction même de la DP 3 (D6).
    table = cotation.table_de_la_coupe(contrat, rapport)
    if table is not None:
        inter_rangee = cotation.cote_inter_rangee(tables, table.inter_table_m, rapport)
        if inter_rangee is not None:
            cotes.append(inter_rangee)

    # Les ouvrages permanents, mesurés sur leur corps (D2, D3).
    ouvrages = cotation.ouvrages_permanents(contrat, objets, rapport)

    # C6 — la largeur de chaque piste, prise en travers.
    cotes += cotation.cotes_de_largeur_de_piste(objets, ouvrages, rapport)

    # C3 — chaque ouvrage → ses voisins directs, et → la limite parcellaire ;
    # C7 — batteries et citernes → la table la plus proche.
    limite = terrain.boundary if terrain is not None and not terrain.is_empty else None
    cotes += cotation.cotes_entre_ouvrages(ouvrages, limite, rapport)
    cotes += cotation.cotes_vers_les_tables(ouvrages, tables, rapport)

    # C4 — clôture → habitation la plus proche, selon la BD TOPO (D5).
    habitation, sans_habitation = _cote_habitation(clotures, rapport, parcelles)
    if habitation is not None:
        cotes.append(habitation)

    # C2 et C8 — vers l'axe de la voie publique la plus proche. Elles ne se
    # superposent à aucune des cotes déjà calculées.
    vers_les_voies = _cotes_vers_les_voies(
        tables, ouvrages, clotures, enclos, cotes, denominateur, rapport
    )
    cotes += [resultat.cote for resultat in vers_les_voies]

    # C1 — clôture → limite parcellaire, ailleurs sur le côté. Sa place se
    # choisit en dernier, là où elle gêne le moins les autres cotes, et loin
    # de la ligne de coupe, qu'aucune valeur ne doit couper.
    ligne_de_coupe = _ligne_de_coupe(contrat)
    traits = [ligne_de_coupe] if ligne_de_coupe is not None else []
    cotes += cotation.choisir_les_places_cloture_limite(cotes_des_pans, cotes, traits)

    a_eviter = []
    if clotures:
        trait = unary_union([
            g.boundary if g.geom_type in ("Polygon", "MultiPolygon") else g
            for g in clotures
        ])
        a_eviter.append(AEviter("la clôture", trait))
    if tables:
        a_eviter.append(AEviter("les tables", unary_union(tables), gene=False))
    for ouvrage in ouvrages:
        a_eviter.append(
            AEviter(f"« {_libelle(ouvrage.categorie)} »", ouvrage.geometrie, infranchissable=True)
        )

    zones = cotation.zones_techniques(cotes)
    dans_les_zones = {id(cote) for zone_technique in zones for cote in zone_technique.cotes}
    return _Calcul(
        hors_zones=[cote for cote in cotes if id(cote) not in dans_les_zones],
        zones=zones,
        axes=[(resultat.cote, resultat.axe) for resultat in vers_les_voies],
        a_eviter=a_eviter,
        ouvrages=ouvrages,
        dimensions=cotation.dimensions_en_legende(contrat, ouvrages, table, rapport),
        sans_habitation=sans_habitation,
        doubles=tuple(
            (resultat.confondue_avec, resultat.cote) for resultat in vers_les_voies
            if resultat.confondue_avec is not None
        ),
    )


def _a_poser_sur_la_dp2(calcul, codes) -> list:
    """Les cotes de la DP 2, quand les zones de `codes` sont parties en détail.

    Celles qui ne sont d'aucune zone, et celles des zones qui restent. La cote
    vers la voie qui part du poste de livraison vaut C2 et C8 (Sarnois,
    10/11/2026) : la DP 2 n'en pose qu'une. Tant que la zone du poste y reste,
    c'est sa C8, et la zone répond de sa place (D7) ; partie, c'est la C2, et
    la C8 va sur la planche de détail.
    """
    restent = [
        cote for rang, zone_technique in enumerate(calcul.zones)
        if rang not in codes for cote in zone_technique.cotes
    ]
    remplacees = {
        id(c2) for c2, c8 in calcul.doubles if any(c8 is cote for cote in restent)
    }
    return [cote for cote in calcul.hors_zones if id(cote) not in remplacees] + restent


def _libelle(categorie: str) -> str:
    """L'intitulé de légende d'une catégorie, pour la nommer au rapport."""
    return getattr(STYLES.get(categorie), "libelle", categorie)


def _noms_des_ouvrages(zone_technique, calcul) -> str:
    noms = []
    for rang in zone_technique.ouvrages:
        nom = _libelle(calcul.ouvrages[rang].categorie)
        if nom not in noms:
            noms.append(nom)
    return ", ".join(noms)


def _codes_des_details(partantes, zones, calcul):
    """Le code de la planche de chaque zone partie : DP 2 bis, ter… dans l'ordre des zones.

    Au-delà de la dernière pièce que le dossier connaît, une zone reste sur la
    DP 2. Une zone dont aucune échelle de détail ne loge les ouvrages et le
    bout des cotes y reste aussi. Rend (codes, refus) : les refus sont ce que
    le rapport doit en dire.
    """
    codes, rapport = {}, []
    for rang in sorted(partantes):
        if len(codes) >= len(SUFFIXES_DETAIL):
            rapport.append(
                f"Zone technique ({_noms_des_ouvrages(zones[rang], calcul)}) : elle se "
                f"lit mal sur la DP 2, mais le dossier ne compte que "
                f"{len(SUFFIXES_DETAIL)} planches de détail ; elle y reste."
            )
            continue
        try:
            _echelle_du_detail(zones[rang], calcul)
        except ErreurEchelle as erreur:
            rapport.append(
                f"Zone technique ({_noms_des_ouvrages(zones[rang], calcul)}) : elle se "
                f"lit mal sur la DP 2, et ne tient sur aucune planche de détail "
                f"({erreur}) ; elle y reste."
            )
            continue
        codes[rang] = f"{NUMERO} {SUFFIXES_DETAIL[len(codes)]}"
    return codes, rapport


def _etendue_du_detail(zone_technique, calcul):
    """Ce que la planche de détail doit montrer : les ouvrages de la zone et le bout de leurs cotes."""
    from shapely.ops import unary_union

    return unary_union(
        [calcul.ouvrages[rang].geometrie for rang in zone_technique.ouvrages]
        + [cote.ligne for cote in zone_technique.cotes]
    )


def _echelle_du_detail(zone_technique, calcul) -> int:
    """La plus grande des échelles de détail où la zone tient sur la planche (D7)."""
    # La zone de dessin d'une planche du dossier, cartouche compris : celle que
    # la planche de détail aura.
    zone = Planche(titre="", numero="", projet="", date="").zone_dessin()
    x0, y0, x1, y1 = _etendue_du_detail(zone_technique, calcul).bounds
    return echelle_adaptative(
        max(x1 - x0, 1.0), max(y1 - y0, 1.0), zone,
        marge=MARGE_DETAIL, valeurs=ECHELLES_DETAIL,
    )


def _cadre_du_detail(zone_technique, calcul, denominateur):
    """Sur la DP 2, le cadre d'une zone partie : ses ouvrages, à 3 mm de papier près.

    Et non toute la planche de détail : au 1:500, celle-ci couvrait la moitié
    est d'Auzainvilliers sur la DP 2 au 1:1 000, passait sous la légende et
    sortait du cadre (04/11/2026). Les cotes de la zone n'y entrent pas : elles
    sont sur la planche de détail.
    """
    from shapely.ops import unary_union

    ouvrages = unary_union(
        [calcul.ouvrages[rang].geometrie for rang in zone_technique.ouvrages]
    )
    x0, y0, x1, y1 = ouvrages.bounds
    marge = mm_vers_metres(MARGE_CADRE_DETAIL_MM, denominateur)
    return box(x0 - marge, y0 - marge, x1 + marge, y1 + marge)


def _poser_le_renvoi(planche, code, cadre, occupees, lignes, genants):
    """Le renvoi au-dessus du cadre, sinon dessous, sinon à côté.

    Ni sur la légende, ni sur une autre étiquette, ni sur une cote, ni en
    travers de la clôture ou d'un ouvrage : posé dessous à Auzainvilliers, la
    clôture le barrait (04/11/2026). Rend la boîte occupée, ou `None` si
    aucune place n'est libre : il est alors écrit à la première, et l'appelant
    le dit.
    """
    texte = f"Détail de la zone technique : {code}"
    largeur = planche.mesurer_texte(texte, TAILLE_RENVOI)
    x_zone, y_zone, largeur_zone, hauteur_zone = planche.zone_dessin()
    gauche, haut = planche.transformation.point(cadre.bounds[0], cadre.bounds[3])
    droite, bas = planche.transformation.point(cadre.bounds[2], cadre.bounds[1])
    places = [
        (gauche, haut - 1.2), (droite - largeur, haut - 1.2),
        (gauche, bas + 3.0), (droite - largeur, bas + 3.0),
        (gauche - largeur - 1.5, haut + 2.2), (droite + 1.5, haut + 2.2),
        (gauche - largeur - 1.5, bas - 0.8), (droite + 1.5, bas - 0.8),
    ]
    for x, y in places:
        boite = (x - 0.4, y - 2.6, x + largeur + 0.4, y + 0.8)
        if (
            boite[0] < x_zone + 3.0 or boite[2] > x_zone + largeur_zone - 3.0
            or boite[1] < y_zone + 3.0 or boite[3] > y_zone + hauteur_zone - 3.0
        ):
            continue
        if any(not (boite[2] < o[0] or o[2] < boite[0] or boite[3] < o[1] or o[3] < boite[1])
               for o in occupees):
            continue
        rectangle = box(*boite)
        if any(rectangle.intersects(ligne) for ligne in lignes):
            continue
        if any(rectangle.intersects(genant) for genant in genants):
            continue
        planche.ajouter_texte(
            x, y, texte, taille=TAILLE_RENVOI, couleur=COULEUR_RENVOI, halo=True
        )
        return boite
    planche.ajouter_texte(
        *places[0], texte, taille=TAILLE_RENVOI, couleur=COULEUR_RENVOI, halo=True
    )
    return None


def _planche_de_detail(projet, contrat, code, numero, zone_technique, lectures, calcul,
                       dossier) -> Sortie:
    """DP 2 bis, ter… : la zone technique à sa plus grande échelle de détail (D7).

    Cadrée sur les ouvrages de la zone et le bout de leurs cotes, au 1:200, au
    1:500 ou au 1:1 000. Elle porte les cotes de la zone, et seulement elles ;
    le fond est celui de la DP 2, lu une fois.
    """
    etendue = _etendue_du_detail(zone_technique, calcul)
    x0, y0, x1, y1 = etendue.bounds
    denominateur = _echelle_du_detail(zone_technique, calcul)
    planche = nouvelle_planche(projet, code, numero=numero)
    planche.definir_echelle(denominateur)
    planche.centrer_sur(((x0 + x1) / 2.0, (y0 + y1) / 2.0))
    genes, messages, details = _composer(
        planche, projet, contrat, lectures, list(zone_technique.cotes), calcul,
        detail=True, pied=PIED_OUVRAGES,
    )
    messages.extend(gene.message for gene in genes)
    suffixe = code.split()[-1]
    chemin = planche.rendre_pdf(
        Path(dossier) / f"DP_2_{suffixe}_detail_zone_technique.pdf"
    )
    return Sortie(
        numero=code,
        titre=piece(code).titre,
        chemin=chemin,
        echelle=denominateur,
        planche=planche,
        details={**details, "avertissements": [f"{code} — {m}" for m in messages]},
    )


#: Ce qui ne répond pas n'arrête pas la DP 2 (lot 10, D11) : c'est la règle de
#: la phase de mise au point (README, « Ce qui deviendra bloquant »).
SANS_ELLE = "La DP 2 est produite sans elle, le temps de la mise au point."
SANS_ELLES = "La DP 2 est produite sans elles, le temps de la mise au point."


def _elargie(bornes: tuple, marge_m: float) -> tuple:
    minx, miny, maxx, maxy = bornes
    return (minx - marge_m, miny - marge_m, maxx + marge_m, maxy + marge_m)


def _detail(erreur: Exception) -> str:
    """Le message d'une erreur de service, sans son point final, pour le citer."""
    return str(erreur).strip().rstrip(".")


def _cote_habitation(clotures, rapport: list, parcelles=()):
    """C4, et les lectures qu'elle demande, à 1 000 m de la clôture (D5).

    Une BD TOPO qui ne répond pas, ou dont la réponse atteint le plafond de
    lecture (`ErreurPlafondWFS`, qui dérive d'`ErreurService`), n'arrête pas la
    DP 2 : la cote manque, et le rapport le dit (D11).

    Les bâtiments du cadastre se lisent sur la même étendue : la cote va au
    contour cadastral de l'habitation, et ceux que la BD TOPO ne connaît pas,
    plus proches qu'elle, se disent au rapport avec leur parcelle parmi
    `parcelles` (Saint-Cyr, 10/11/2026). Un cadastre qui ne répond pas
    n'arrête pas la DP 2 non plus : la cote vise alors le contour de la BD
    TOPO, la comparaison manque, et le rapport le dit.

    Rend (cote, absence) : `absence` est vraie quand la BD TOPO a répondu sans
    habitation à 1 000 m. C'est un résultat, que la légende dit (D5) ; une BD
    TOPO qui n'a pas répondu ne dit rien de l'absence.
    """
    from shapely.ops import unary_union

    from . import cotation_plan_masse as cotation

    if not clotures:
        return cotation.cote_habitation(clotures, [], rapport), False
    bbox = _elargie(unary_union(clotures).bounds, cotation.RAYON_HABITATION_M)
    try:
        batiments = telecharger_batiments_bd_topo(bbox)
    except ErreurService as erreur:
        rapport.append(
            "Habitation la plus proche : pas de cote — la lecture de la BD TOPO a "
            f"échoué ({_detail(erreur)}). {SANS_ELLE}"
        )
        return None, False
    try:
        cadastre = telecharger_batiments(bbox)
    except ErreurService as erreur:
        rapport.append(
            "Habitation la plus proche : la lecture des bâtiments du cadastre autour "
            f"de la clôture a échoué ({_detail(erreur)}) : la cote vise le contour "
            "de l'habitation dans la BD TOPO, et rien ne dit si des bâtiments qu'elle "
            "ne connaît pas en sont plus proches. La DP 2 est produite sans le "
            "cadastre, le temps de la mise au point."
        )
        cadastre = None
    habitation = cotation.cote_habitation(
        clotures, batiments, rapport, cadastre=cadastre, parcelles=parcelles
    )
    return habitation, habitation is None


def _cotes_vers_les_voies(tables, ouvrages, clotures, enclos, posees, denominateur,
                          rapport: list) -> list:
    """C2 et C8, et les lectures qu'elles demandent : les voies, et le parcellaire autour.

    Les voies de la BD TOPO à 300 m de la clôture (D5) ; le parcellaire à 350 m
    autour d'elle, pour juger sur 50 m de part et d'autre de son point le plus
    proche si une voie est publique (D10). Ni l'une ni l'autre n'arrête la
    DP 2 : sans elles, C2 et C8 manquent, et le rapport le dit (D11).

    Rend les `CoteVersVoie`, C2 d'abord : C8 la connaît, pour ne pas la doubler.
    """
    from shapely.ops import unary_union

    from . import cotation_plan_masse as cotation

    constructions = cotation.polygones_de(tables) + [o.geometrie for o in ouvrages]
    if not constructions:
        return []
    autour = unary_union(clotures or constructions).bounds
    try:
        troncons = telecharger_troncons_de_route(_elargie(autour, cotation.RAYON_VOIE_M))
    except ErreurService as erreur:
        rapport.append(
            "Cotes vers la voie publique : pas de cote — la lecture de la BD TOPO a "
            f"échoué ({_detail(erreur)}). {SANS_ELLES}"
        )
        return []
    marge = cotation.RAYON_VOIE_M + cotation.PORTEE_DOMAINE_PUBLIC_M
    try:
        parcelles = telecharger_parcelles(_elargie(autour, marge))
    except ErreurService as erreur:
        rapport.append(
            "Cotes vers la voie publique : pas de cote — la lecture du parcellaire "
            f"autour des constructions a échoué ({_detail(erreur)}), et rien ne dit "
            f"quelles voies sont publiques. {SANS_ELLES}"
        )
        return []
    cadastre = unary_union([parcelle.geometrie for parcelle in parcelles])

    c2 = cotation.cote_vers_la_voie_publique(
        tables, ouvrages, troncons, cadastre, enclos, posees, denominateur, rapport
    )
    c8 = cotation.cotes_poste_de_livraison(
        ouvrages, troncons, cadastre, enclos, list(posees) + ([c2.cote] if c2 else []),
        denominateur, c2, rapport,
    )
    return ([c2] if c2 else []) + c8


def _tramer_les_tables(planche: Planche, contrat: Contrat, tables) -> list:
    """Divise chaque table en modules, ou dit pourquoi elle ne l'est pas."""
    if not tables:
        return []
    from .dp3_coupes import geometrie_table
    from .modules import controler_trame

    try:
        table, _ = geometrie_table(contrat)
        rampant = table.rampant_m
    except ErreurDP:
        rampant = None

    trame, raison = trame_du_projet(contrat, tables, rampant)
    if trame is None:
        # Sans raison, il n'y a rien à dire : les modules du contrat sont
        # dessinés tels quels.
        return [raison] if raison else []

    tramees, comptes = tracer_trame(
        planche, tables, trame, STYLES["tables_pv"].style,
        planche.transformation.mm_par_metre,
    )
    messages = []
    ecart = controler_trame(contrat.structures, comptes)
    if ecart:
        messages.append(ecart)
    if tramees == 0:
        messages.append(
            f"Trame des modules non dessinée : au 1:{planche.echelle}, un "
            "module ne mesurerait pas un millimètre sur la planche."
        )
    elif tramees < len(tables):
        messages.append(
            f"Trame des modules dessinée sur {tramees} rangées sur "
            f"{len(tables)} : les autres ne se divisent pas en un nombre "
            f"entier de modules de {nombre_fr(trame.largeur_module_m)} m."
        )
    return messages


def _etiqueter_parcelles(planche: Planche, parcelles, cadre) -> list:
    """Numéros de parcelle, sous le seuil de lisibilité près.

    Reprise de la mécanique de DP 1-3 : en dessous de quelques millimètres
    carrés sur le papier, l'étiquette déborde de sa parcelle et se lit comme
    celle de la voisine.

    Rend la boîte de chaque numéro sur le papier, en millimètres : les cotes
    se posent après eux, et aucune valeur ne doit en recouvrir un (lot 10, D8).
    """
    facteur = planche.transformation.mm_par_metre ** 2
    points, textes = [], []
    for parcelle in parcelles:
        visible = parcelle.geometrie.intersection(cadre)
        if visible.is_empty or visible.area * facteur < SURFACE_MIN_ETIQUETTE_MM2:
            continue
        points.append(visible.representative_point())
        textes.append(parcelle.numero)
    planche.ajouter_etiquettes(
        points, textes, {"taille_mm": TAILLE_ETIQUETTE, "couleur": "#5a3800"}
    )
    # `ajouter_etiquettes` centre le texte sur le point, sa ligne de base au
    # point même.
    boites = []
    for point, texte in zip(points, textes):
        x, y = planche.transformation.point(point.x, point.y)
        largeur = planche.mesurer_texte(str(texte), TAILLE_ETIQUETTE)
        boites.append((
            x - largeur / 2.0 - 0.3, y - 0.75 * TAILLE_ETIQUETTE - 0.3,
            x + largeur / 2.0 + 0.3, y + 0.25 * TAILLE_ETIQUETTE + 0.3,
        ))
    return boites


def _boite_de_ligne(planche: Planche, x_mm: float, y_mm: float, texte: str,
                    taille: float) -> tuple:
    """La boîte d'une ligne de texte écrite depuis (x, y), sa ligne de base en y."""
    largeur = planche.mesurer_texte(texte, taille)
    return (x_mm - 0.3, y_mm - taille, x_mm + largeur + 0.3, y_mm + 0.6)


def _boite_de_repere(x_mm: float, y_mm: float, direction: tuple) -> tuple:
    """La boîte d'un repère de coupe posé par `repere_coupe` : triangle et lettre.

    Le triangle part du point dans la direction de la coupe, sur
    `COTE_REPERE_MM` ; la lettre, de 11 points, se centre 3,4 mm en arrière.
    """
    dx, dy = direction
    nx, ny = -dy, dx
    demi = COTE_REPERE_MM / 2.0
    lettre = (x_mm - dx * 3.4, y_mm - dy * 3.4)
    points = [
        (x_mm + dx * COTE_REPERE_MM, y_mm + dy * COTE_REPERE_MM),
        (x_mm + nx * demi, y_mm + ny * demi),
        (x_mm - nx * demi, y_mm - ny * demi),
        (lettre[0] - 2.4, lettre[1] - 2.2),
        (lettre[0] + 2.4, lettre[1] + 1.6),
    ]
    return (
        min(p[0] for p in points) - 0.3, min(p[1] for p in points) - 0.3,
        max(p[0] for p in points) + 0.3, max(p[1] for p in points) + 0.3,
    )


def _ligne_de_coupe(contrat: Contrat):
    """La ligne de coupe du contrat, ou `None` s'il n'en porte pas."""
    couche = contrat.couches.get("ligne_coupe")
    if couche is None or couche.empty:
        return None
    ligne = couche.geometry.iloc[0]
    if ligne is None or ligne.is_empty:
        return None
    return ligne


def _tracer_ligne_coupe(planche: Planche, contrat: Contrat, occupees: list | None = None):
    """Ligne de coupe en trait d'axe, repères A et A' aux extrémités.

    Les triangles pointent l'un vers l'autre, dans le sens de lecture de la
    coupe : c'est ce que porte le plan de masse du dossier de référence, et ce
    que l'instructeur cherche pour savoir de quel côté la coupe regarde.

    `occupees`, s'il est donné, reçoit la boîte des deux repères : aucune
    valeur de cote ne s'y pose (lot 10, D8).
    """
    ligne = _ligne_de_coupe(contrat)
    if ligne is None:
        return None

    planche.ajouter_geometrie(ligne, TRAIT_AXE)

    coords = list(ligne.coords)
    depart_mm = planche.transformation.point(coords[0][0], coords[0][1])
    arrivee_mm = planche.transformation.point(coords[-1][0], coords[-1][1])
    dx = arrivee_mm[0] - depart_mm[0]
    dy = arrivee_mm[1] - depart_mm[1]
    norme = (dx * dx + dy * dy) ** 0.5
    if norme == 0:
        return None
    ux, uy = dx / norme, dy / norme

    reperes = (
        (depart_mm[0] - ux * RECUL_REPERE_MM, depart_mm[1] - uy * RECUL_REPERE_MM,
         "A", (ux, uy)),
        (arrivee_mm[0] + ux * RECUL_REPERE_MM, arrivee_mm[1] + uy * RECUL_REPERE_MM,
         "A'", (-ux, -uy)),
    )
    for x_mm, y_mm, lettre, direction in reperes:
        repere_coupe(planche, x_mm, y_mm, lettre, direction)
        if occupees is not None:
            occupees.append(_boite_de_repere(x_mm, y_mm, direction))
    return ligne
