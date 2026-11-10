"""Les dimensions des ouvrages sur le plan de repérage des DP 4 (10/11/2026).

Décidé sur la relecture des planches de façades des vingt dossiers HOCH du
dépôt : huit cotent, sur leur plan de repérage, la longueur et la largeur de
l'ouvrage que la planche décrit, et l'ouverture du portail — des permis datés
de décembre 2025 à juillet 2026, dont Épeigné, le plus récent. Les douze autres,
dont les trois dossiers en DP, n'y portent aucune cote. **Aucun n'y reporte
une distance** : elles restent au plan de masse (DP 2 et ses planches de
détail, lot 10). Les répéter ici les poserait deux fois, à deux échelles, et
un écart entre les deux se verrait à l'instruction. La maquette, jouée sur
Saint-Cyr, Auzainvilliers et Sarnois, a été retenue telle quelle.

Ce que le module pose, pour chaque ouvrage décrit par la planche et entier
dans le zoom — tous les exemplaires visibles, comme HOCH à Épeigné :

- sa longueur et sa largeur **aux cotes du catalogue**, celles que dessinent
  ses élévations à droite, jamais mesurées sur le plan. Ne se cote que le
  **corps** de l'ouvrage, reconnu comme au lot 10 (`palette.separer_les_corps`) :
  l'objet du calque aux cotes du catalogue à 5 % près, compté une fois s'il est
  dessiné deux fois. Un ouvrage dont aucun objet n'est aux cotes du catalogue
  n'est pas coté : y écrire le catalogue serait faux sur le plan, y écrire la
  mesure contredirait l'élévation ;
- sur une ligne parallèle à ses côtés, posée hors de lui, avec ses lignes
  d'attache. Le côté se choisit sur ce que la ligne et sa valeur
  recouvriraient ;
- sur la planche qui décrit le portail, son ouverture, à la largeur des
  paramètres du contrat comme son élévation, hors de l'enclos.

La valeur s'écrit à la précision du catalogue : une décimale quand elle est
ronde au dixième, « 12,0 m », comme les cotes de la DP 2 et comme HOCH ; deux
sinon, « 7,95 m », comme l'élévation de la citerne de 30 m³ — au dixième, la
cote aurait écrit 8,0 m à côté d'elle.

Une cote qui ne se pose pas se dit au rapport : ouvrage coupé par le bord du
zoom ou trop près de lui, dimension sous les 3 mm lisibles, pas de place dans
le zoom, ouvrage hors des cotes du catalogue, portail sans ouverture mesurable,
catalogue ou largeur de portail absents. Les valeurs se placent avec
`pose_des_cotes`, comme sur la DP 2 (méthode 2 de l'ISO 129). La légende ne
gagne pas d'entrée « Cote » : la valeur porte son unité et ses lignes d'attache
désignent l'ouvrage, et une ligne de plus changerait l'échelle de zooms déjà
relus.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import shapely
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

from ..erreurs import ErreurCoteOuvrage
from ..planche import nombre_fr
from .cotation_plan_masse import (
    CATEGORIES_OUVRAGES,
    SEUIL_LISIBLE_MM,
    CoteAPoser,
    polygones_de,
)
from .palette import STYLES, contour_de, separer_les_corps
from .pose_des_cotes import RETRAIT_CADRE_MM, AEviter, poser_les_cotes
from .primitives import TRAIT_COTE

#: Écart entre le côté de l'ouvrage et sa ligne de cote, sur le papier.
RECUL_MM = 3.5
#: Une ligne de cote ne court pas le long d'un bord du dessin : elle se lirait
#: comme lui. Un bord parallèle au côté qui passe à moins de ce jeu de sa place
#: la repousse de `RECUL_MM` au-delà de lui. Relevé sur la maquette du
#: 10/11/2026 : à Saint-Cyr, la piste à créer cerne le poste de 1 m, 3,3 mm au
#: 1:300, et la cote tombait sur son contour. La règle porte sur le bord le plus
#: proche, et non sur l'étendue de ce qui touche l'ouvrage : le chemin existant
#: de 2 800 m² et la piste existante touchent aussi ce poste, et leur étendue
#: gardait la cote sur le contour de la piste à créer.
JEU_BORD_MM = 2.0
#: Un bord compte s'il est parallèle au côté à ce nombre de degrés près, et
#: s'il en longe au moins cette part.
ANGLE_BORD_DEG = 15.0
PART_DU_COTE = 0.25
#: Au-delà de cet écart, la ligne ne s'éloigne plus : elle ne situerait plus
#: l'ouvrage, et reste à `RECUL_MM`.
RECUL_MAX_MM = 12.0
#: Jour entre l'ouvrage et le départ d'une ligne d'attache, et ce qu'elle
#: dépasse au-delà de la ligne de cote (ISO 129).
JOUR_ATTACHE_MM = 0.8
DEPASSEMENT_MM = 1.2
#: Demi-largeur de la bande que la ligne et sa valeur occupent (le corps de la
#: valeur fait 2,3 mm), pour juger ce qu'elles recouvriraient.
BANDE_MM = 1.6
#: Les traits d'un même portail se touchent à moins de cette distance.
JOINT_PORTAIL_M = 0.3
#: Une géométrie est l'ouvrage même — sa géométrie d'origine, une copie, une
#: collection qui le contient — si elle en couvre cette part, à cette part de
#: son aire près ; un voisin qui le touche, ou la plateforme qui le porte, non.
MEME_OUVRAGE = 0.9

#: Ce qui enclôt le site : son contour gêne une cote.
ENCLOS = ("cloture", "limite_paddock")

#: Poids de ce qu'une cote recouvrirait, pour choisir son côté. Une valeur sur
#: une table reste lisible (lot 10, 08/11/2026) ; sur l'aire d'aspiration aussi,
#: mais elle se lit mieux à côté.
POIDS_OUVRAGE = 1.0
POIDS_AIRE_ASPIRATION = 0.5
POIDS_TABLES = 0.2
POIDS_AUTRE_COTE = 2.0
#: La bande large, trois fois la bande, départage deux côtés libres l'un et
#: l'autre : la cote va vers le plus dégagé. Sans elle, la largeur du poste de
#: Saint-Cyr allait contre la clôture alors que l'autre bout était vide.
POIDS_ABORDS = 0.1
#: Ce qu'il en coûte à l'ouverture d'un portail d'être cotée dans l'enclos.
DANS_L_ENCLOS = 1e3


@dataclass
class CotesDuReperage:
    """Ce que la pose a mis sur le plan de repérage, et ce qu'elle a à dire."""

    cotes: list = field(default_factory=list)
    messages: list = field(default_factory=list)


@dataclass(frozen=True)
class _Candidate:
    """Une place possible pour une cote : un des deux côtés parallèles."""

    a: tuple
    b: tuple
    normale: tuple
    recul_m: float
    ligne: LineString
    score: float

    @property
    def preference(self) -> float:
        # À encombrement égal, la cote va au sud ou à l'est, comme d'usage :
        # deux générations du même dossier la posent au même endroit.
        return self.normale[1] - self.normale[0]


@dataclass
class _Lieu:
    """Ce que la pose sait du plan de repérage, pour chaque cote."""

    fenetre: Polygon
    utile: Polygon
    mm: float
    obstacles: list
    enclos: object


def coter_les_ouvrages(planche, contrat, visibles, *, decrits, avec_portail, fenetre,
                       occupees=(), masques=()) -> CotesDuReperage:
    """Pose les dimensions des ouvrages décrits, et l'ouverture du portail.

    - `visibles` : ce que le plan de repérage dessine, `(catégorie, géométries)`,
      en Lambert 93 ;
    - `decrits` : les catégories d'ouvrages que la planche décrit, à coter ;
    - `avec_portail` : la planche décrit le portail ;
    - `fenetre` : le plan de repérage sur le terrain. Une cote et son ouvrage
      restent à `RETRAIT_CADRE_MM` de son bord ;
    - `occupees`, `masques` : comme pour `poser_les_cotes` — tout ce qui, sur la
      planche, n'est pas le plan.
    """
    resultat = CotesDuReperage()
    mm = planche.transformation.mm_par_metre
    obstacles, a_eviter, enclos = _obstacles(visibles, mm)
    lieu = _Lieu(
        fenetre=fenetre,
        utile=fenetre.buffer(-RETRAIT_CADRE_MM / mm, join_style="mitre"),
        mm=mm, obstacles=obstacles, enclos=enclos,
    )
    attaches = []

    for categorie, parties in visibles:
        if categorie in decrits:
            _coter_une_categorie(categorie, parties, contrat, visibles, lieu, resultat, attaches)
    if avec_portail:
        _coter_les_portails(visibles, contrat, lieu, resultat, attaches)

    for attache in attaches:
        planche.ajouter_geometrie(attache, TRAIT_COTE)
    # Les lignes d'attache sont des traits qu'aucune valeur ne coupe : posée
    # dessus, une valeur se lirait comme celle de l'autre cote.
    genes = poser_les_cotes(
        planche, resultat.cotes, list(occupees), traits=attaches, a_eviter=a_eviter,
        masques=list(masques), rapport=resultat.messages,
    )
    resultat.messages.extend(gene.message for gene in genes)
    return resultat


def _obstacles(visibles, mm: float):
    """Ce qu'une cote recouvrirait, pondéré ; ce que sa valeur évite ; l'enclos."""
    obstacles = []
    a_eviter = []
    clotures = []
    for categorie, geometries in visibles:
        for g in geometries:
            if categorie in CATEGORIES_OUVRAGES and g.area > 0:
                obstacles.append((g, POIDS_OUVRAGE))
                a_eviter.append(AEviter(categorie, g, gene=True, infranchissable=True))
            elif categorie in ENCLOS:
                # Une clôture peut être une surface, un trait ouvert ou une
                # collection redressée : `contour_de` rend son trait dans les
                # trois cas, là où `boundary` rendrait `None` sur une collection.
                contour = contour_de(g)
                if contour is not None and not contour.is_empty:
                    trait = contour.buffer(0.6 / mm)
                    obstacles.append((trait, POIDS_OUVRAGE))
                    a_eviter.append(AEviter(categorie, trait, gene=True))
                if categorie == "cloture":
                    clotures.append(g)
            elif categorie == "portail":
                obstacles.append((g.buffer(0.4 / mm), POIDS_OUVRAGE))
            elif categorie == "tables_pv":
                obstacles.append((g, POIDS_TABLES))
                a_eviter.append(AEviter(categorie, g, gene=False))
            elif categorie == "aire_aspiration" and g.area > 0:
                obstacles.append((g, POIDS_AIRE_ASPIRATION))
    return obstacles, a_eviter, _enclos(clotures)


def _enclos(clotures):
    """La surface que la clôture ferme, qu'elle soit dessinée en surface ou en trait.

    Une clôture en trait ouvert ne ferme rien : `None`.
    """
    surfaces = polygones_de(clotures)
    traits = [g for g in clotures if g.area == 0]
    if traits:
        surfaces.extend(polygonize(unary_union([contour_de(t) for t in traits])))
    return unary_union(surfaces) if surfaces else None


def _coter_une_categorie(categorie, parties, contrat, visibles, lieu, resultat, attaches):
    """Les corps d'une catégorie décrite : chacun reçoit ses deux cotes."""
    libelle = STYLES[categorie].libelle
    surfaces = polygones_de(parties)
    if not surfaces:
        resultat.messages.append(
            f"Plan de repérage : « {libelle} » n'a aucune surface à mesurer — un "
            "contour resté ouvert ; ses dimensions n'y sont pas cotées."
        )
        return
    corps, _, _ = separer_les_corps(contrat, categorie, surfaces)
    if not corps:
        resultat.messages.append(_sans_corps(contrat, categorie, libelle, surfaces))
        return
    # Plusieurs exemplaires dans le zoom : le rapport dit lequel ne se cote pas.
    # « Conteneurs BESS est coupé par le bord du zoom » se lisait, à
    # Auzainvilliers, comme le conteneur sur lequel le zoom est centré.
    nom = f"un exemplaire de « {libelle} »" if len(corps) > 1 else f"« {libelle} »"
    for un_corps in corps:
        _coter_un_corps(categorie, nom, un_corps, contrat, visibles, lieu, resultat, attaches)


def _sans_corps(contrat, categorie, libelle, surfaces) -> str:
    """Pourquoi aucun objet d'une catégorie n'est son corps."""
    plus_grande = max(surfaces, key=lambda s: s.area)
    try:
        cote = contrat.cote_de_categorie(categorie, surface_m2=plus_grande.area)
        attendu = f"{_valeur(cote.longueur_m)} x {_valeur(cote.largeur_m)} m"
    except ErreurCoteOuvrage:
        return (
            f"Plan de repérage : « {libelle} » n'est pas coté — le catalogue du "
            "contrat ne porte pas sa cote."
        )
    return (
        f"Plan de repérage : « {libelle} » n'est pas coté — aucun objet du plan "
        f"n'a ses cotes au catalogue, {attendu}. Y écrire le catalogue serait faux "
        "sur le plan, y écrire la mesure contredirait son élévation."
    )


def _coter_un_corps(categorie, nom, corps, contrat, visibles, lieu, resultat, attaches):
    """Les deux cotes d'un corps. `nom` le désigne au rapport, guillemets compris."""
    if not lieu.fenetre.contains(corps):
        resultat.messages.append(
            f"Plan de repérage : {nom} est coupé par le bord du zoom — ses "
            "dimensions n'y sont pas cotées ; son élévation les porte."
        )
        return
    if not lieu.utile.contains(corps):
        resultat.messages.append(
            f"Plan de repérage : {nom} est trop près du bord du zoom pour que "
            "ses cotes y tiennent — elles n'y sont pas posées ; son élévation les porte."
        )
        return
    # Le corps est aux cotes du catalogue : `separer_les_corps` vient de le
    # reconnaître ainsi. Le sens de chaque nombre vient de l'ordre des cotes, qui
    # change d'un ouvrage à l'autre : c'est par leur taille qu'ils vont aux côtés.
    cote = contrat.cote_de_categorie(categorie, surface_m2=corps.area)
    grande, petite = sorted((cote.longueur_m, cote.largeur_m), reverse=True)
    longs, courts = _paires_de_cotes(shapely.oriented_envelope(corps))
    bords = _bords(corps, visibles)
    autres = [(g, p) for g, p in lieu.obstacles if not _est_lui(g, corps)]
    for genre, valeur, paire in (("longueur", grande, longs), ("largeur", petite, courts)):
        mesure = paire[0][2]
        if mesure * lieu.mm < SEUIL_LISIBLE_MM:
            resultat.messages.append(
                f"Plan de repérage : la {genre} de {nom} ne ferait que "
                f"{nombre_fr(mesure * lieu.mm, 1)} mm sur le papier, sous les "
                f"{nombre_fr(SEUIL_LISIBLE_MM, 0)} mm lisibles — elle n'y est pas "
                "cotée ; son élévation la porte."
            )
            continue
        candidates = [
            _candidate(a, b, normale, _recul(bords, a, b, normale, lieu.mm), lieu.mm,
                       autres, resultat)
            for a, b, _, normale in paire
        ]
        retenue = _meilleure(candidates, lieu.utile)
        if retenue is None:
            resultat.messages.append(
                f"Plan de repérage : la {genre} de {nom} n'a pas de place dans "
                "le zoom — elle n'y est pas cotée ; son élévation la porte."
            )
            continue
        _retenir(retenue, valeur, lieu.mm, resultat, attaches)


def _coter_les_portails(visibles, contrat, lieu, resultat, attaches) -> None:
    """L'ouverture de chaque portail du zoom, à la largeur des paramètres."""
    traits = [g for categorie, gs in visibles if categorie == "portail" for g in gs]
    if not traits:
        return
    # Le symbole d'un portail est fait de plusieurs traits — son seuil, ses
    # vantaux, leurs arcs : relevé sur Saint-Cyr IND07, quinze traits pour ses
    # portails. On les regroupe par portail avant de le mesurer.
    zones = unary_union([t.buffer(JOINT_PORTAIL_M) for t in traits])
    largeur = contrat.generalites.get("largeur_portails_m")
    for zone in getattr(zones, "geoms", [zones]):
        portail = unary_union([t for t in traits if zone.intersects(t)])
        # Un trait de longueur nulle s'unit en géométrie vide : ni dedans ni
        # dehors, il passerait pour coupé par le bord du zoom.
        if portail.is_empty or portail.length <= 0:
            resultat.messages.append(
                "Plan de repérage : un portail n'a pas d'ouverture mesurable au plan "
                "— elle n'y est pas cotée ; son élévation la porte."
            )
            continue
        if not lieu.fenetre.contains(portail):
            resultat.messages.append(
                "Plan de repérage : un portail est coupé par le bord du zoom — son "
                "ouverture n'y est pas cotée ; son élévation la porte."
            )
            continue
        if not lieu.utile.contains(portail):
            resultat.messages.append(
                "Plan de repérage : un portail est trop près du bord du zoom pour que "
                "son ouverture y tienne — elle n'y est pas cotée ; son élévation la porte."
            )
            continue
        if not largeur:
            resultat.messages.append(
                "Plan de repérage : l'ouverture du portail n'est pas cotée — aucune "
                "largeur de portail aux paramètres du contrat."
            )
            return
        cotes = _cotes_d_ouverture(portail)
        if not cotes:
            resultat.messages.append(
                "Plan de repérage : un portail n'a pas d'ouverture mesurable au plan "
                "— elle n'y est pas cotée ; son élévation la porte."
            )
            continue
        _coter_un_portail(portail, cotes, float(largeur), lieu, resultat, attaches)


def _coter_un_portail(portail, cotes, largeur, lieu, resultat, attaches) -> None:
    # Ses propres traits ne le gênent pas ; la clôture qu'il interrompt, si.
    siens = portail.buffer(1.0 / lieu.mm)
    autres = [(g, p) for g, p in lieu.obstacles if not g.within(siens)]
    candidates = []
    for a, b, _, normale in cotes:
        candidate = _candidate(a, b, normale, RECUL_MM / lieu.mm, lieu.mm, autres, resultat)
        # L'ouverture se cote hors de l'enclos, le long de la clôture, comme
        # chez HOCH : du côté des vantaux, la ligne tombe dans la piste.
        if lieu.enclos is not None and lieu.enclos.contains(candidate.ligne.centroid):
            candidate = replace(candidate, score=candidate.score + DANS_L_ENCLOS)
        candidates.append(candidate)
    retenue = _meilleure(candidates, lieu.utile)
    if retenue is None:
        resultat.messages.append(
            "Plan de repérage : l'ouverture d'un portail n'a pas de place dans le zoom "
            "— elle n'y est pas cotée ; son élévation la porte."
        )
        return
    if lieu.enclos is None:
        resultat.messages.append(
            "Plan de repérage : la clôture ne ferme pas d'enclos dans le zoom — "
            "l'ouverture du portail s'y cote du côté le plus dégagé, sans savoir "
            "lequel est dehors."
        )
    elif lieu.enclos.contains(retenue.ligne.centroid):
        resultat.messages.append(
            "Plan de repérage : l'ouverture d'un portail se cote côté vantaux, dans "
            "l'enclos — dehors, elle sortait du zoom."
        )
    _retenir(retenue, largeur, lieu.mm, resultat, attaches)


def _paires_de_cotes(rectangle: Polygon):
    """Les deux grands côtés, puis les deux petits : (a, b, longueur, normale sortante)."""
    coins = list(rectangle.exterior.coords)[:4]
    centre = rectangle.centroid
    cotes = []
    for i in range(4):
        a, b = coins[i][:2], coins[(i + 1) % 4][:2]
        milieu = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        cotes.append((a, b, LineString([a, b]).length,
                      _unitaire(milieu[0] - centre.x, milieu[1] - centre.y)))
    # Les côtés opposés d'un rectangle sont égaux : 0 et 2 d'un côté, 1 et 3 de l'autre.
    paire_a, paire_b = [cotes[0], cotes[2]], [cotes[1], cotes[3]]
    return (paire_a, paire_b) if cotes[0][2] >= cotes[1][2] else (paire_b, paire_a)


def _cotes_d_ouverture(portail):
    """Les deux places de la cote d'ouverture : le long du portail, de part et d'autre."""
    enveloppe = shapely.oriented_envelope(portail)
    if enveloppe.is_empty:
        return []
    if enveloppe.geom_type == "Polygon":
        return _paires_de_cotes(enveloppe)[0]
    if enveloppe.geom_type != "LineString" or enveloppe.length <= 0:
        return []
    # Un portail tracé d'un seul trait : son enveloppe est ce trait.
    a, b = enveloppe.coords[0][:2], enveloppe.coords[-1][:2]
    u = _unitaire(b[0] - a[0], b[1] - a[1])
    n = (-u[1], u[0])
    return [(a, b, enveloppe.length, n), (b, a, enveloppe.length, (-n[0], -n[1]))]


def _est_lui(geometrie, corps) -> bool:
    """La géométrie est-elle l'ouvrage même — son origine, une copie, une collection ?"""
    if geometrie.area <= 0:
        return False
    return (
        abs(geometrie.area - corps.area) <= (1.0 - MEME_OUVRAGE) * corps.area
        and geometrie.intersection(corps).area >= MEME_OUVRAGE * corps.area
    )


def _bords(corps, visibles):
    """Les bords que le plan de repérage dessine, sauf ceux de l'ouvrage même."""
    contours = []
    for _, geometries in visibles:
        for g in geometries:
            if _est_lui(g, corps):
                continue
            contour = contour_de(g)
            if contour is not None and not contour.is_empty:
                contours.append(contour)
    return unary_union(contours) if contours else None


def _recul(bords, a, b, normale, mm: float) -> float:
    """À quelle distance du côté (a, b) poser sa ligne de cote, en mètres.

    À `RECUL_MM`, sauf si un bord parallèle du dessin y court : la ligne passe
    alors `RECUL_MM` au-delà de lui, et ainsi de suite jusqu'à `RECUL_MAX_MM`.
    """
    recul = RECUL_MM / mm
    if bords is None:
        return recul
    longueur = LineString([a, b]).length
    u = ((b[0] - a[0]) / longueur, (b[1] - a[1]) / longueur)
    jeu = JEU_BORD_MM / mm
    ecart = recul
    while ecart * mm <= RECUL_MAX_MM:
        bande = _bande(a, b, normale, ecart - jeu, ecart + jeu)
        paralleles = [
            (p, q) for p, q in _segments(bords.intersection(bande)) if _parallele(p, q, u)
        ]
        if sum(LineString([p, q]).length for p, q in paralleles) < PART_DU_COTE * longueur:
            return ecart
        ecart = recul + max(
            (x - a[0]) * normale[0] + (y - a[1]) * normale[1]
            for p, q in paralleles for x, y in (p, q)
        )
    return recul


def _bande(a, b, normale, de: float, a_: float) -> Polygon:
    """La bande devant le côté (a, b), de `de` à `a_` mètres de lui."""
    return Polygon([
        (a[0] + normale[0] * de, a[1] + normale[1] * de),
        (b[0] + normale[0] * de, b[1] + normale[1] * de),
        (b[0] + normale[0] * a_, b[1] + normale[1] * a_),
        (a[0] + normale[0] * a_, a[1] + normale[1] * a_),
    ])


def _segments(geometrie):
    """Les segments des lignes d'une géométrie, quelle que soit sa nature."""
    if geometrie is None or geometrie.is_empty:
        return
    if hasattr(geometrie, "geoms"):
        for partie in geometrie.geoms:
            yield from _segments(partie)
        return
    if geometrie.geom_type in ("LineString", "LinearRing"):
        coords = [c[:2] for c in geometrie.coords]
        yield from zip(coords, coords[1:])


def _parallele(p, q, u) -> bool:
    """Le segment (p, q) est-il parallèle à la direction `u`, à `ANGLE_BORD_DEG` près ?"""
    dx, dy = q[0] - p[0], q[1] - p[1]
    norme = (dx * dx + dy * dy) ** 0.5
    if norme == 0:
        return False
    return abs(dx * u[1] - dy * u[0]) / norme <= math.sin(math.radians(ANGLE_BORD_DEG))


def _candidate(a, b, normale, recul_m, mm, obstacles, resultat) -> _Candidate:
    decalage = (normale[0] * recul_m, normale[1] * recul_m)
    ligne = LineString([
        (a[0] + decalage[0], a[1] + decalage[1]),
        (b[0] + decalage[0], b[1] + decalage[1]),
    ])
    proches = [
        (LineString([c.depart, c.arrivee]).buffer(0.5 / mm), POIDS_AUTRE_COTE)
        for c in resultat.cotes
    ]
    return _Candidate(a, b, normale, recul_m, ligne, _encombrement(ligne, obstacles, proches, mm))


def _encombrement(ligne, obstacles, proches, mm: float) -> float:
    """Ce que la ligne et sa valeur recouvriraient, pondéré. Plus c'est petit, mieux c'est.

    Les cotes déjà posées ne comptent que de près : les deux cotes d'un même
    ouvrage se rejoignent à un coin, et les écarter l'une de l'autre poussait la
    seconde à travers l'aire d'aspiration de la citerne de Saint-Cyr.
    """
    demi = BANDE_MM / mm
    bande = ligne.buffer(demi, cap_style="flat")
    abords = ligne.buffer(3 * demi, cap_style="flat")
    plancher = 0.1 * demi * demi
    score = 0.0
    for geometrie, poids in obstacles:
        if bande.intersects(geometrie):
            score += poids * max(bande.intersection(geometrie).area, plancher)
        if abords.intersects(geometrie):
            score += POIDS_ABORDS * poids * abords.intersection(geometrie).area
    for geometrie, poids in proches:
        if bande.intersects(geometrie):
            score += poids * max(bande.intersection(geometrie).area, plancher)
    return score


def _meilleure(candidates, utile):
    """La place la moins encombrée parmi celles qui tiennent dans le zoom, ou `None`."""
    dedans = [c for c in candidates if utile.contains(c.ligne)]
    if not dedans:
        return None
    # À encombrement égal, le côté où la cote reste le plus près de l'ouvrage :
    # à Saint-Cyr, deux bords parallèles repoussaient la longueur du poste à
    # 10 mm de lui au sud-est, quand le nord-ouest la gardait à 6,8 mm.
    return min(dedans, key=lambda c: (round(c.score, 6), round(c.recul_m, 2), c.preference))


def _retenir(candidate: _Candidate, valeur: float, mm: float, resultat, attaches) -> None:
    """La cote retenue, et ses deux lignes d'attache, des coins de l'ouvrage à elle."""
    depart, arrivee = candidate.ligne.coords[0], candidate.ligne.coords[-1]
    resultat.cotes.append(CoteAPoser(
        famille="dimension", depart=tuple(depart), arrivee=tuple(arrivee),
        texte=f"{_valeur(valeur)} m", valeur_m=valeur,
    ))
    jour, bout = JOUR_ATTACHE_MM / mm, candidate.recul_m + DEPASSEMENT_MM / mm
    n = candidate.normale
    for coin in (candidate.a, candidate.b):
        attaches.append(LineString([
            (coin[0] + n[0] * jour, coin[1] + n[1] * jour),
            (coin[0] + n[0] * bout, coin[1] + n[1] * bout),
        ]))


def _valeur(metres: float) -> str:
    """La valeur à la précision du catalogue : au dixième si elle y est ronde, au centième sinon."""
    ronde = abs(metres * 10.0 - round(metres * 10.0)) < 1e-6
    return nombre_fr(metres, 1 if ronde else 2)


def _unitaire(dx: float, dy: float) -> tuple:
    norme = (dx * dx + dy * dy) ** 0.5
    return (dx / norme, dy / norme)
