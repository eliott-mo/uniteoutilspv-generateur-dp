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

from pathlib import Path

from shapely.geometry import box

from ..contrat import Contrat
from ..dossier import piece
from ..echelle import echelle_adaptative
from ..erreurs import ErreurComposition, ErreurDP, ErreurService
from ..geometrie import Emprise
from ..ign import telecharger_batiments, telecharger_parcelles
from ..planche import (
    GRIS,
    MOTIF_BATIMENT,
    STYLE_BATIMENT,
    STYLE_PARCELLE,
    TAILLE_ETIQUETTE,
    Planche,
    nombre_fr,
)
from ..projet import Projet
from .commun import Sortie, nouvelle_planche
from .dp1_3_cadastre import SURFACE_MIN_ETIQUETTE_MM2
from .legende import dessiner_legende, hauteur_bloc
from .modules import tracer_trame, trame_du_projet
from .palette import STYLES, construire_legende, objets_a_dessiner, style_de
from .primitives import COTE_REPERE_MM, TRAIT_AXE, repere_coupe, union_valide

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


#: Part du bloc de légende que le dessin peut occuper sans qu'on le déplace.
#: Sous ce seuil, la légende garde le coin du dossier de référence : une
#: planche où elle ne gênait pas ne doit pas changer d'allure.
RECOUVREMENT_LEGENDE_TOLERE = 0.02

#: Rayon dont on épaissit le dessin avant de mesurer ce que la légende
#: couvrirait, en mètres. Une clôture est une ligne, d'aire nulle : sans cette
#: épaisseur elle passerait pour de la place libre.
EPAISSEUR_MESURE_LEGENDE_M = 2.0


def _coin_de_legende(planche, zone, objets, largeur_mm, hauteur_mm) -> tuple:
    """Coin de la zone de dessin où la légende masque le moins le plan.

    Le bloc se posait toujours en haut à gauche. Relevé le 30/09/2026 sur
    Auzainvilliers : le site passe dessous, et le cadre blanc de la légende
    couvre une piste et une plateforme. Une planche d'instruction qui cache une
    partie de ce qu'elle montre est fausse par omission.

    L'ordre des coins est celui du dossier de référence — haut-gauche d'abord —
    et la légende n'en bouge que si le dessin l'occupe vraiment.
    """
    from shapely.geometry import box as _boite
    from shapely.ops import unary_union as _union

    transformation = planche.transformation
    if transformation is None:
        return (zone[0] + 3.0, zone[1] + 3.0)

    dessin = [g for _, geometries in objets for g in geometries]
    if not dessin:
        return (zone[0] + 3.0, zone[1] + 3.0)
    couvert = _union(dessin).buffer(EPAISSEUR_MESURE_LEGENDE_M)

    def vers_l93(x_mm, y_mm):
        return (
            transformation._origine_x
            + (x_mm - transformation._x_mm) / transformation.mm_par_metre,
            transformation._origine_y
            - (y_mm - transformation._y_mm) / transformation.mm_par_metre,
        )

    x, y, largeur_zone, hauteur_zone = zone
    coins = (
        (x + 3.0, y + 3.0),
        (x + largeur_zone - largeur_mm - 3.0, y + 3.0),
        (x + 3.0, y + hauteur_zone - hauteur_mm - 3.0),
        (x + largeur_zone - largeur_mm - 3.0, y + hauteur_zone - hauteur_mm - 3.0),
    )

    parts = []
    for coin in coins:
        x0, y0 = vers_l93(coin[0], coin[1])
        x1, y1 = vers_l93(coin[0] + largeur_mm, coin[1] + hauteur_mm)
        boite = _boite(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        aire = boite.area
        parts.append(boite.intersection(couvert).area / aire if aire else 0.0)

    for coin, part in zip(coins, parts):
        if part <= RECOUVREMENT_LEGENDE_TOLERE:
            return coin
    return coins[parts.index(min(parts))]


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
    for parcelle in parcelles:
        planche.ajouter_geometrie(parcelle.geometrie, STYLE_PARCELLE)

    # 2. Bâtiments, hachurés à 45° comme sur DP 1-3.
    #
    #    Seuls ceux qui tombent dans le cadre comptent pour la légende. La
    #    requête WFS déborde du cadre d'un tampon, pour que les limites soient
    #    tracées jusqu'au bord ; en tirer une entrée « Bâtiment » ferait
    #    annoncer à la légende un objet que la planche ne montre pas.
    cadre_planche = box(minx, miny, maxx, maxy)
    batiments = telecharger_batiments(cadre_requete)
    batiments_visibles = [
        b for b in batiments if cadre_planche.intersects(b.geometrie)
    ]
    if batiments_visibles:
        planche.ajouter_definition(MOTIF_BATIMENT)
        for batiment in batiments_visibles:
            planche.ajouter_geometrie(batiment.geometrie, STYLE_BATIMENT)

    # 3. Les catégories du GeoPackage, dans l'ordre de dessin du contrat.
    objets = objets_a_dessiner(contrat, avertissements)
    if not objets:
        raise ErreurComposition(
            "Le contrat ne porte aucun objet à dessiner : le plan de masse "
            "serait vide. Vérifiez l'appariement des calques à l'import."
        )
    hors_cadre = []
    tables_visibles = []
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
            if categorie == "tables_pv":
                tables_visibles.append(geometrie)

    # La trame des modules, par-dessus le contour des rangées : c'est elle qui
    # fait lire une table comme un panneau plutôt que comme une dalle, et c'est
    # ce que porte le plan de masse du dossier de référence.
    avertissements.extend(
        _tramer_les_tables(planche, contrat, tables_visibles)
    )
    if hors_cadre:
        # Le contenu cartographique est découpé sur la zone de dessin : un objet
        # hors cadre disparaîtrait sans rien dire, et c'est exactement le genre
        # d'absence que personne ne remarque à la relecture.
        avertissements.append(
            f"{len(hors_cadre)} objet(s) du plan tombent hors du cadre de DP 2 "
            f"({', '.join(sorted(set(hors_cadre)))}) : ils ne sont pas dessinés. "
            "L'emprise cadastrale ne couvre pas tout le projet."
        )

    # 4. Étiquettes de parcelle, là où la parcelle est assez grande sur le
    #    papier pour en porter une — même mécanique que DP 1-3. Leur place se
    #    relève : aucune valeur de cote ne doit les recouvrir (lot 10, D8 ;
    #    « 0495 » sous une cote à Saint-Cyr, relecture du 08/11/2026).
    occupees = _etiqueter_parcelles(planche, parcelles, cadre_planche)

    # 5. La ligne de coupe, en trait d'axe, et ses repères A / A'.
    trace = _tracer_ligne_coupe(planche, contrat, occupees)
    if trace is None:
        avertissements.append(
            "Aucune ligne de coupe au contrat : le plan de masse ne porte pas "
            "les repères A et A', et DP 3 n'est pas produite."
        )

    # 6. La légende, bâtie sur ce qui vient d'être dessiné, et sur rien d'autre.
    #    Sa place est connue avant les cotes, qui ne doivent pas y poser leurs
    #    valeurs ; elle se dessine après elles.
    categories_tracees = [c for c, _ in objets]
    entrees = construire_legende(
        categories_tracees,
        avec_parcelles=True,
        avec_batiments=bool(batiments_visibles),
        # Les intitulés que le chef de projet a corrigés à l'écran, s'il en a
        # corrigé : la légende est dans l'image de la planche, elle ne se
        # retouche donc pas après coup.
        libelles=projet.legendes,
    )
    hauteur_legende = hauteur_bloc(len(entrees))
    position = _coin_de_legende(
        planche, zone, objets, LARGEUR_LEGENDE_MM, hauteur_legende
    )
    boite_legende = (
        position[0], position[1],
        position[0] + LARGEUR_LEGENDE_MM, position[1] + hauteur_legende,
    )
    x_source, y_source = zone[0] + 3.0, zone[1] + zone[3] - 2.5
    occupees.append(boite_legende)
    occupees.append(_boite_de_ligne(planche, x_source, y_source, SOURCE, TAILLE_SOURCE))

    # 7. Les cotes (lot 10).
    avertissements.extend(
        _coter(planche, contrat, emprise, parcelles, objets, occupees, trace, boite_legende)
    )

    dessiner_legende(planche, entrees, position=position, largeur_mm=LARGEUR_LEGENDE_MM)
    planche.ajouter_texte(
        x_source, y_source, SOURCE, taille=TAILLE_SOURCE, couleur=GRIS, halo=True,
    )

    chemin = planche.rendre_pdf(Path(dossier) / "DP_2_plan_de_masse.pdf")
    return Sortie(
        numero=NUMERO,
        titre=TITRE,
        chemin=chemin,
        echelle=denominateur,
        planche=planche,
        details={
            "categories_dessinees": categories_tracees,
            "nb_parcelles": len(parcelles),
            "nb_batiments": len(batiments_visibles),
            "coupe_tracee": trace is not None,
            "avertissements": avertissements,
        },
    )


def _coter(planche, contrat, emprise, parcelles, objets, occupees, trace, legende) -> list:
    """Les cotes du plan de masse (lot 10) : calculées, posées, et dites.

    Le calcul est dans `cotation_plan_masse`, qui ne dessine rien ; la pose,
    dans `pose_des_cotes`. Les cotes se prennent sur ce que la planche
    dessine, `objets` : une clôture refermée par `objets_a_dessiner` l'est
    aussi pour ses cotes. Rend le rapport : chaque cote qu'une règle écarte,
    ou qui se lit mal sur la planche, y est nommée avec sa raison — aucune
    n'est retirée en silence (D9).

    `occupees` : ce que les valeurs ne recouvrent pas — numéros de parcelle,
    repères de coupe, légende, ligne de source. `legende` : la boîte de la
    légende, sous laquelle une ligne ne se lit plus jusqu'à sa flèche.
    """
    from shapely.ops import unary_union

    from . import cotation_plan_masse as cotation
    from .pose_des_cotes import AEviter, poser_les_cotes

    rapport = []
    dessines = dict(objets)
    clotures = list(dessines.get("cloture", []))
    tables = cotation.polygones_de(dessines.get("tables_pv", []))

    # C1 — tables → limite parcellaire, à travers la clôture. La limite est
    # celle du terrain d'assiette, retenu par la règle de la DP 1-3 (D4).
    terrain = cotation.terrain_d_assiette(parcelles, emprise.geometrie)
    enclos = cotation.enclos_de_la_cloture(clotures, rapport)
    pans = cotation.pans_de_la_cloture(enclos)
    cotes_des_pans = cotation.cotes_tables_cloture_limite(
        pans, tables, terrain, planche.echelle, rapport
    )
    cotes = [cotes_du_pan.tables_limite for cotes_du_pan in cotes_des_pans]

    # C5 — l'écartement entre deux rangées, une fois, à la valeur de la coupe :
    # celle de `geometrie_table`, la fonction même de la DP 3 (D6).
    table = cotation.table_de_la_coupe(contrat, rapport)
    if table is not None:
        inter_rangee = cotation.cote_inter_rangee(tables, table.inter_table_m, rapport)
        if inter_rangee is not None:
            cotes.append(inter_rangee)

    # Les ouvrages permanents, mesurés sur leur corps (D2, D3). À ce point du
    # lot, ils écartent de C6 la plateforme d'un ouvrage, et gardent leurs
    # corps des valeurs de cote. Leurs propres cotes (C3, C7, C8), et ce que le
    # rapport dit de leur mesure, viennent avec elles : il dirait d'un ouvrage
    # qu'il est « coté sur son corps » quand rien ne le cote encore.
    ouvrages = cotation.ouvrages_permanents(contrat, objets, [])

    # C6 — la largeur de chaque piste, prise en travers.
    cotes += cotation.cotes_de_largeur_de_piste(objets, ouvrages, rapport)

    # C1 — clôture → limite parcellaire, ailleurs sur le côté. Sa place se
    # choisit en dernier, là où elle gêne le moins les autres cotes, et loin
    # de la ligne de coupe, qu'aucune valeur ne doit couper.
    traits = [trace] if trace is not None else []
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
        libelle = getattr(STYLES.get(ouvrage.categorie), "libelle", ouvrage.categorie)
        a_eviter.append(
            AEviter(f"« {libelle} »", ouvrage.geometrie, infranchissable=True)
        )

    genes = poser_les_cotes(
        planche, cotes, occupees, traits=traits,
        a_eviter=a_eviter, masques=[legende], rapport=rapport,
    )
    rapport.extend(gene.message for gene in genes)
    return rapport


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


def _tracer_ligne_coupe(planche: Planche, contrat: Contrat, occupees: list | None = None):
    """Ligne de coupe en trait d'axe, repères A et A' aux extrémités.

    Les triangles pointent l'un vers l'autre, dans le sens de lecture de la
    coupe : c'est ce que porte le plan de masse du dossier de référence, et ce
    que l'instructeur cherche pour savoir de quel côté la coupe regarde.

    `occupees`, s'il est donné, reçoit la boîte des deux repères : aucune
    valeur de cote ne s'y pose (lot 10, D8).
    """
    couche = contrat.couches.get("ligne_coupe")
    if couche is None or couche.empty:
        return None
    ligne = couche.geometry.iloc[0]
    if ligne is None or ligne.is_empty:
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
