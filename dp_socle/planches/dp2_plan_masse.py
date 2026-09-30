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
from .primitives import TRAIT_AXE, repere_coupe

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


def generer(
    projet: Projet,
    contrat: Contrat,
    emprise: Emprise,
    dossier: str | Path,
    numero: str | None = None,
) -> Sortie:
    planche = nouvelle_planche(projet, NUMERO, numero=numero)
    zone = planche.zone_dessin()

    largeur_m, hauteur_m = emprise.dimensions_m
    denominateur = echelle_adaptative(
        largeur_m, hauteur_m, zone, marge=MARGE, valeurs=ECHELLES_PLAN_MASSE
    )
    planche.definir_echelle(denominateur)
    planche.centrer_sur(emprise.centre)

    minx, miny, maxx, maxy = planche.emprise_terrain()
    avertissements = []

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
    #    papier pour en porter une — même mécanique que DP 1-3.
    _etiqueter_parcelles(planche, parcelles, cadre_planche)

    # 5. La ligne de coupe, en trait d'axe, et ses repères A / A'.
    trace = _tracer_ligne_coupe(planche, contrat)
    if trace is None:
        avertissements.append(
            "Aucune ligne de coupe au contrat : le plan de masse ne porte pas "
            "les repères A et A', et DP 3 n'est pas produite."
        )

    # 6. La légende, bâtie sur ce qui vient d'être dessiné, et sur rien d'autre.
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
    dessiner_legende(
        planche,
        entrees,
        position=_coin_de_legende(
            planche, zone, objets, LARGEUR_LEGENDE_MM, hauteur_bloc(len(entrees))
        ),
        largeur_mm=LARGEUR_LEGENDE_MM,
    )
    planche.ajouter_texte(
        zone[0] + 3.0,
        zone[1] + zone[3] - 2.5,
        "Parcellaire et bâtiments : IGN — Parcellaire Express (PCI), WFS "
        "Géoplateforme. Ouvrages : plan du bureau d'études.",
        taille=1.9,
        couleur=GRIS,
        halo=True,
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


def _etiqueter_parcelles(planche: Planche, parcelles, cadre) -> None:
    """Numéros de parcelle, sous le seuil de lisibilité près.

    Reprise de la mécanique de DP 1-3 : en dessous de quelques millimètres
    carrés sur le papier, l'étiquette déborde de sa parcelle et se lit comme
    celle de la voisine.
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


def _tracer_ligne_coupe(planche: Planche, contrat: Contrat):
    """Ligne de coupe en trait d'axe, repères A et A' aux extrémités.

    Les triangles pointent l'un vers l'autre, dans le sens de lecture de la
    coupe : c'est ce que porte le plan de masse du dossier de référence, et ce
    que l'instructeur cherche pour savoir de quel côté la coupe regarde.
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

    repere_coupe(
        planche,
        depart_mm[0] - ux * RECUL_REPERE_MM,
        depart_mm[1] - uy * RECUL_REPERE_MM,
        "A",
        (ux, uy),
    )
    repere_coupe(
        planche,
        arrivee_mm[0] + ux * RECUL_REPERE_MM,
        arrivee_mm[1] + uy * RECUL_REPERE_MM,
        "A'",
        (-ux, -uy),
    )
    return ligne
