"""Maquette du lot 10 : la DP 2 cotée, sans toucher au socle.

Versée dans `_briefs/` le 07/11/2026, mise à jour le 09/11, comme référence du brief
`BRIEF_DP_lot10_cotation_plan_masse.md`. Ce n'est pas du code du dépôt : rien
ne l'importe, la suite ne la joue pas, et elle n'est pas maintenue. Elle
remplace à l'exécution des fonctions du socle (`dp2_plan_masse`, `palette`,
`commun`) pour poser ses cotes sur la DP 2 du lot 4 : elle ne vaut donc que pour
l'état du code du 08/11/2026. La construction du lot en reprend les règles et
les pièges mesurés, pas la forme.

Mode d'emploi, avec un contrat déjà écrit (`geometries.gpkg` et `projet.json`,
par l'application ou par `importer_be`) :

    python -I _briefs/maquette_lot10_cotes_dp2.py <dépôt> <dossier du contrat>
        <emprise> <sortie> <nom> <commune> <code postal> <libellé> <préfixe>

Elle interroge la Géoplateforme (parcellaire, BD TOPO), écrit dans <sortie> la
DP 2, les planches de détail et leurs images, et sort le rapport sur la console.

Les règles, dans l'ordre des relectures. Corrections de la première version,
sur Sarnois (03/11/2026) :
- un ouvrage se mesure depuis l'objet aux dimensions du catalogue (le poste),
  jamais depuis sa plateforme ou son contour ;
- un ouvrage se cote vers ses voisins et vers la limite, plus vers la voie ;
- un côté de clôture dont les tables sont à plus de 30 m ne se cote pas ;
- une seule cote d'inter-rangée, à la valeur de la coupe ;
- une voirie qui recouvre un ouvrage n'est pas une piste ;
- l'axe de la voie se dessine là où la cote s'y arrête.

Puis, après la relecture d'Auzainvilliers (03/11/2026) :
- un ouvrage se mesure sur ce que la planche dessine : le BESS du bureau
  d'études est un aplat de 6 x 8 m sous un conteneur de 6 x 3 m, et l'aplat se
  dessine maintenant comme la terre remise autour d'un poste ;
- le bac de rétention et la zone de remise sont des ouvrages ; une citerne
  arrivée en collection de géométries aussi ; un ouvrage qu'on ne sait pas
  mesurer se dit au rapport ;
- un ouvrage se cote vers ses voisins naturels, plus vers tous ceux à moins de 30 m.

Puis les quatre règles validées par le chef de projet le 04/11/2026 :
- entre ouvrages, les voisins directs seulement (inchangé) ;
- les batteries et le local de stockage, que l'instructeur nomme, se cotent
  toujours jusqu'à la limite : sans seuil, et même par-dessus un autre ouvrage ;
- une zone technique part sur une planche de détail dès qu'elle se lit mal sur
  la DP 2 : une cote de moins de 3 mm, une valeur sans place nette, ou une cote
  que la légende recouvre. La DP 2 est essayée, puis refaite sans ces zones ;
- l'aplat sous les conteneurs se dessine en plateforme (inchangé), et le
  rapport demande au bureau d'études de confirmer ce qu'il est.
Et ce que leur application a montré, le même jour :
- sur la DP 2, le cadre d'une zone partie en détail entoure ses ouvrages, et
  non toute la planche de détail, qui couvrait au 1:500 la moitié du site ;
- la légende écarte tout coin qui couvre une cote tant qu'il en reste un ;
- le renvoi « Détail de la zone technique » s'écrit après la légende, hors de
  la clôture, des ouvrages et des cotes.

Puis les retours des chefs de projet sur Saint-Cyr et Auzainvilliers (07/11/2026) :
- chaque cote de la chaîne dit ce qu'elle mesure, et la limite son orientation :
  « 15,7 m (clôture en limite) » se lisait comme la distance de la clôture à la
  limite, nulle à cet endroit (Saint-Cyr) ;
- les conteneurs BESS et les deux citernes se cotent jusqu'à la table la plus
  proche (Auzainvilliers), sauf si un autre ouvrage s'intercale, comme une
  paire d'ouvrages ;
- le poste de livraison se cote jusqu'à l'axe de la voie du domaine public la
  plus proche, en deçà de 30 m. Une voie posée sur des parcelles cadastrées
  n'en est pas une, ni un chemin de la BD TOPO dans la clôture (Saint-Cyr) ;
- SIMULATION, et non règle du lot : plusieurs postes d'une même catégorie se
  dessinent tous en poste. À Auzainvilliers, le PTR des batteries est dessiné
  sur le calque 0 ; il est apparié à la main, comme l'écran le permet.
Et la mise en page qui en découle : la légende ne recouvre plus ni le pied ni
le cadre d'un détail, et le pied se lit de haut en bas.

Puis les décisions du chef de projet du lot, le 08/11/2026, sur la relecture
des deux demandes de compléments :
- la chaîne tables | clôture | limite est coupée en deux cotes, posées à deux
  endroits du côté : à 1:2 000, un écart de 1 m entre clôture et limite faisait
  0,5 mm, et ses flèches se posaient sur celles de la grande cote. La première
  va des tables à la limite parcellaire, à travers la clôture : c'est la
  distance que les deux demandes réclament. La seconde va de la clôture à la
  limite, ailleurs sur le côté, et seulement si l'écart dépasse 0,5 m ;
- les libellés disent « limite parcellaire », sans orientation : le plan montre
  où est la limite ;
- C2 revient : la construction la plus proche de la voie publique la plus
  proche, jusqu'à l'axe de celle-ci, à toute distance — Saint-Cyr demande les
  distances « par rapport aux voies et emprises publiques » ;
- les trois dimensions (Auzainvilliers, art. R. 431-36 b) : la légende donne
  les cotes et la hauteur de chaque construction, au catalogue, et la hauteur
  maximale des tables, celle de la coupe ;
- la plateforme d'un poste n'est plus simulée : la palette sépare chaque corps
  depuis le 08/11/2026, et la simulation de la v3 est retirée.
Et ce que leur application a montré, le même jour :
- le côté de clôture, simplifié à 1,5 m, ne donne plus que la direction de la
  cote : la v3 mesurait depuis lui, et en tirait à Saint-Cyr des écarts
  clôture → limite de 0,9 et 1,0 m là où la clôture réelle est sur la limite ;
- la cote clôture → limite se pose, parmi les endroits du côté qui conviennent,
  là où elle gêne le moins les autres cotes ;
- la cote vers l'axe d'une voie qui longe le terrain se superposait à celle de
  la même construction à la limite : l'axe se dit dans le libellé de celle-ci.

Puis la seconde relecture du chef de projet, le 08/11/2026 (v5) :
- la cote vers une voie publique est perpendiculaire à son axe, et ses flèches
  le touchent : à Auzainvilliers, la cote fondue dans celle de la limite
  s'arrêtait au bord de la D18. Elle part de la face de la construction tournée
  vers la voie, et s'y décale pour ne pas se superposer à la cote à la limite.
  Quand la voie publique s'arrête avant le site — à Saint-Cyr, la route
  empierrée finit à l'angle nord-ouest, et les chemins qui longent le côté
  ouest sont sur des parcelles —, aucune perpendiculaire n'existe : la cote va
  à son extrémité, et le dit ;
- la valeur d'une cote vers la limite se pose de préférence au-delà de la
  limite, hors de la centrale ; aucune valeur ne recouvre un numéro de parcelle,
  et les tables sont à éviter ;
- la légende passe sur deux colonnes quand aucun coin ne la reçoit en une.

Puis le 09/11/2026 (v6) :
- la clôture porte sa hauteur en légende, 2 m : la constante UNITe que
  l'élévation de la DP 4 cote déjà (`standards.HAUTEUR_CLOTURE_M`), puisque le
  contrat n'en porte aucune ;
- une seule cote C7 par famille, la plus courte : le BESS nord d'Auzainvilliers,
  à 28,3 m des tables quand le BESS sud en est à 8,3 m, n'était « pas utile ».
"""

import math
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
depot, dossier_contrat, chemin_emprise, sortie = map(Path, sys.argv[1:5])
nom, commune, code_postal, libelle, prefixe = sys.argv[5:10]
sys.path.insert(0, str(depot))

import pypdfium2 as pdfium  # noqa: E402
import shapely  # noqa: E402
from pyogrio import list_layers  # noqa: E402
from shapely.geometry import LineString, Point, box, shape  # noqa: E402
from shapely.ops import linemerge, nearest_points, substring, unary_union  # noqa: E402

from dp_socle import ign  # noqa: E402
from dp_socle.environnement import preparer_cairo  # noqa: E402

preparer_cairo()

from dp_socle.contrat import NOM_GEOPACKAGE, charger_contrat  # noqa: E402
from dp_socle.erreurs import ErreurDP  # noqa: E402
from dp_socle.geometrie import charger_emprise  # noqa: E402
from dp_socle.import_be import CATEGORIES_PISTE_LEGERE, CATEGORIES_VOIE_LOURDE  # noqa: E402
from dp_socle.planche import (NOIR, TAILLE_CARTOUCHE, TAILLE_COURANTE, EntreeLegende,  # noqa: E402
                              Planche, Style, nombre_fr)
from dp_socle.planches import commun, dp2_plan_masse  # noqa: E402
from dp_socle.planches.dp1_3_cadastre import PART_MIN_ASSIETTE  # noqa: E402
from dp_socle.planches.dp3_coupes import resoudre_parametre  # noqa: E402
from dp_socle.planches.dp4_ouvrages import CITERNES, CONTENEURS, POSTES  # noqa: E402
from dp_socle.planches.legende import hauteur_bloc  # noqa: E402
from dp_socle.planches.palette import TOLERANCE_COTES_POSTE  # noqa: E402
from dp_socle.planches.primitives import PATTE_COTE_MM, TAILLE_COTE, TRAIT_COTE  # noqa: E402
from dp_socle.projet import Projet  # noqa: E402

SEUIL_VOISINS_M = 30.0
SEUIL_TABLES_COTE_M = 30.0
SEUIL_LISIBLE_MM = 3.0
TOLERANCE_CATALOGUE = 0.15
RAYON_HABITATION_M = 1000.0
RAYON_VOIE_M = 300.0
NATURES_ECARTEES = {"Sentier", "Escalier", "Piste cyclable"}
SEUIL_VOIE_PDL_M = 30.0
# Ce que le SDIS regarde : le risque (batteries, citerne de refroidissement) et
# la défense (citerne incendie). Demandé à Auzainvilliers le 07/11/2026.
OUVRAGES_VERS_TABLES = ("bess", "citerne_refroidissement", "bache_incendie")
POSTES_DE_LIVRAISON = ("pdl", "pdl_ptr")
POINTS_CARDINAUX = ("est", "nord-est", "nord", "nord-ouest", "ouest", "sud-ouest", "sud", "sud-est")
# En deçà, la clôture est tenue pour posée sur la limite : pas de seconde cote.
ECART_CLOTURE_LIMITE_MIN_M = 0.5
# Écart minimal, sur le papier de la DP 2, entre les deux cotes d'un même côté :
# assez pour qu'elles ne se lisent pas comme une chaîne. Valeur de départ.
SEPARATION_COTES_COTE_MM = 20.0
# Fractions du côté où l'on essaie de poser la cote clôture → limite, dans
# l'ordre : le milieu d'abord.
FRACTIONS_COTE_CLOTURE = (0.5, 0.35, 0.65, 0.2, 0.8)
# Écart minimal, sur le papier, entre une cote vers l'axe d'une voie et une cote
# qui lui serait parallèle : en deçà, les deux se lisent comme une seule.
ECART_COTES_PARALLELES_MM = 4.0
# Les pistes existantes comptent : à Saint-Cyr elles sont « à renforcer si
# nécessaire », donc des travaux du projet. L'aire de grutage n'est pas une piste.
CATEGORIES_PISTES = tuple(
    c for c in CATEGORIES_VOIE_LOURDE + CATEGORIES_PISTE_LEGERE if c != "aire_grutage"
) + ("voirie",)

couches = {n for n, _ in list_layers(dossier_contrat / NOM_GEOPACKAGE)}
contrat = charger_contrat(dossier_contrat, voirie="piste_legere" if "voirie" in couches else None)
emprise = charger_emprise(chemin_emprise)
projet = Projet(nom=nom, commune=commune, code_postal=code_postal,
                date="2026-11-08", emprise=str(chemin_emprise), libelle=libelle)
rapport = []


def geometries(nom_couche):
    if nom_couche not in couches:
        return []
    return [shapely.force_2d(g) for g in contrat.geometries(nom_couche)
            if g is not None and not g.is_empty]


def polygones(geoms):
    for g in geoms:
        if g.geom_type == "Polygon":
            yield g
        elif g.geom_type in ("MultiPolygon", "GeometryCollection"):
            # La citerne de refroidissement d'Auzainvilliers arrive en collection
            # (contour auto-intersectant) : sautée, elle sortait des cotes sans un mot.
            yield from polygones(g.geoms)


tables_liste = list(polygones(geometries("tables_pv")))
tables = unary_union(tables_liste)
cloture = unary_union(geometries("cloture"))
anneau = cloture.exterior if cloture.geom_type == "Polygon" else max(
    cloture.geoms, key=lambda p: p.area).exterior

# --- Le terrain d'assiette, par la règle de la DP 1-3 -----------------------
minx, miny, maxx, maxy = emprise.geometrie.bounds
parcelles = ign.telecharger_parcelles((minx - 100, miny - 100, maxx + 100, maxy + 100))
terrain = unary_union([
    p.geometrie for p in parcelles
    if p.geometrie.intersects(emprise.geometrie)
    and p.geometrie.intersection(emprise.geometrie).area / p.geometrie.area >= PART_MIN_ASSIETTE
])
limite = terrain.boundary

# --- BD TOPO -------------------------------------------------------------------
cx0, cy0, cx1, cy1 = cloture.bounds
voies = []
for entite in ign._interroger_wfs(
    "BDTOPO_V3:troncon_de_route",
    (cx0 - RAYON_VOIE_M, cy0 - RAYON_VOIE_M, cx1 + RAYON_VOIE_M, cy1 + RAYON_VOIE_M),
    120, 1000, 5000, "voies",
):
    p = entite.get("properties") or {}
    if p.get("nature") not in NATURES_ECARTEES:
        voies.append((shapely.force_2d(shape(entite["geometry"])), p))
brut = ign._interroger_wfs(
    "BDTOPO_V3:batiment",
    (cx0 - RAYON_HABITATION_M, cy0 - RAYON_HABITATION_M,
     cx1 + RAYON_HABITATION_M, cy1 + RAYON_HABITATION_M),
    120, 1000, 5000, "bâtiments",
)
if len(brut) >= 5000:
    rapport.append(f"!! BD TOPO bâtiments : {len(brut)} entités, la requête est TRONQUÉE")
batiments = [(shapely.force_2d(shape(e["geometry"])), e.get("properties") or {}) for e in brut]


def nom_de_voie(p):
    numero = p.get("cpx_numero")
    nature = (p.get("nature") or "voie").lower()
    if numero:
        return f"de la {numero}"
    if nature.startswith("route"):
        return "de la route"
    if nature == "chemin":
        return "du chemin"
    return f"de la voie ({nature})"


def cote_simple(p1, p2, texte, cote=1):
    return ([p1, p2], [texte], [cote])


cotes_dp2, cotes_c3, axes = [], [], []

# --- C1 : tables | clôture | limite, une chaîne par côté ---------------------
def direction(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def virage(s0, s1):
    return abs((direction(*s1) - direction(*s0) + 180) % 360 - 180)


def orientation(origine, vers):
    """Le point cardinal vers lequel on va d'`origine` à `vers` : le côté de la limite.

    Le nord du quadrillage Lambert 93 tient lieu de nord géographique : la
    convergence des méridiens n'y dépasse pas quelques degrés, loin des 22,5°
    qui séparent deux points cardinaux.
    """
    angle = direction(origine, vers) % 360
    return POINTS_CARDINAUX[int(((angle + 22.5) % 360) // 45)]


sommets = list(shapely.Polygon(anneau).simplify(1.5).exterior.coords)[:-1]
segments = [(sommets[i], sommets[(i + 1) % len(sommets)]) for i in range(len(sommets))]
troncons, courant = [], [segments[0]]
for segment in segments[1:]:
    if virage(courant[-1], segment) < 25:
        courant.append(segment)
    else:
        troncons.append(courant)
        courant = [segment]
if troncons and virage(courant[-1], troncons[0][0]) < 25:
    troncons[0] = courant + troncons[0]
else:
    troncons.append(courant)
# L'échelle de la DP 2, dès maintenant : les deux cotes d'un même côté doivent
# s'écarter sur le papier, et c'est l'échelle qui dit de combien sur le terrain.
_planche_echelle = commun.nouvelle_planche(projet, "DP 2")
_, _dimensions_cadre, _ = dp2_plan_masse._ce_que_la_planche_cadre(contrat, emprise)
DENOMINATEUR_DP2 = dp2_plan_masse.echelle_adaptative(
    *_dimensions_cadre, _planche_echelle.zone_dessin(), marge=dp2_plan_masse.MARGE,
    valeurs=dp2_plan_masse.ECHELLES_PLAN_MASSE)
SEPARATION_COTES_COTE_M = SEPARATION_COTES_COTE_MM * DENOMINATEUR_DP2 / 1000.0
enclos_c1 = shapely.Polygon(anneau)


def premier_croisement(depart, vers_x, vers_y, longueur, au_dela_de=0.05):
    """Le premier point de la limite sur la demi-droite, au-delà de `au_dela_de`."""
    rayon = LineString([depart, (depart[0] + vers_x * longueur, depart[1] + vers_y * longueur)])
    croisement = rayon.intersection(limite)
    points = [croisement] if croisement.geom_type == "Point" else list(getattr(croisement, "geoms", []))
    points = [q for q in points if q.geom_type == "Point" and Point(depart).distance(q) > au_dela_de]
    return min(points, key=lambda q: Point(depart).distance(q)) if points else None


nb_c1 = 0
cotes_cloture_a_poser, candidats_cloture = [], []
for troncon in troncons:
    ligne = LineString([troncon[0][0]] + [s[1] for s in troncon])
    if ligne.length < 20:
        continue
    p_t, p_c = nearest_points(tables, ligne)
    if p_t.distance(p_c) > SEUIL_TABLES_COTE_M:
        rapport.append(f"C1 : côté de {ligne.length:.0f} m non coté, tables à {p_t.distance(p_c):.1f} m")
        continue
    # 1. Tables → limite parcellaire, dans l'axe tables → clôture, à travers la
    #    clôture : c'est la distance que les deux demandes réclament (08/11/2026).
    # Le côté est un tracé simplifié à 1,5 m : il ne donne que la direction. Sa
    # distance à la limite n'est pas celle de la clôture — la v3 en tirait des
    # « 1,0 m (clôture – limite) » à Saint-Cyr, où la clôture réelle est sur la
    # limite (relevé le 08/11/2026). Les tables sont dans le terrain : le
    # premier croisement de la limite, en partant d'elles, est le bon.
    dx, dy = p_c.x - p_t.x, p_c.y - p_t.y
    norme = math.hypot(dx, dy)
    p_l = premier_croisement((p_t.x, p_t.y), dx / norme, dy / norme, 500)
    if p_l is None:
        rapport.append(f"C1 : côté de {ligne.length:.0f} m sans limite dans l'axe des tables")
        continue
    cote_tables = LineString([(p_t.x, p_t.y), (p_l.x, p_l.y)])
    cotes_dp2.append(cote_simple((p_t.x, p_t.y), (p_l.x, p_l.y),
                                 f"{nombre_fr(p_t.distance(p_l), 1)} m (tables – limite parcellaire)", "dehors"))
    nb_c1 += 1
    # 2. Clôture → limite parcellaire, ailleurs sur le même côté, si l'écart y
    #    dépasse 0,5 m. Posée dans le prolongement de la première, ses flèches
    #    tombaient sur les siennes (Saint-Cyr, 08/11/2026).
    essais = []
    for f in FRACTIONS_COTE_CLOTURE:
        q = ligne.interpolate(f * ligne.length)
        _, q_reel = nearest_points(q, anneau)
        avant = ligne.interpolate(max(0.0, f * ligne.length - 1.0))
        apres = ligne.interpolate(min(ligne.length, f * ligne.length + 1.0))
        tx, ty = apres.x - avant.x, apres.y - avant.y
        nt = math.hypot(tx, ty)
        if nt < 1e-6:
            continue
        nx, ny = -ty / nt, tx / nt
        if enclos_c1.contains(Point(q_reel.x + nx * 0.5, q_reel.y + ny * 0.5)):
            nx, ny = -nx, -ny
        # Clôture sur la limite à cet endroit : le rayon la croise au départ, et
        # c'est un écart nul, pas une limite introuvable.
        if q_reel.distance(limite) <= ECART_CLOTURE_LIMITE_MIN_M:
            essais.append((f, q_reel.distance(limite), math.inf))
            continue
        r = premier_croisement((q_reel.x, q_reel.y), nx, ny, 60)
        if r is None:
            essais.append((f, math.nan, math.inf))
            continue
        ecart = q_reel.distance(r)
        eloignement = cote_tables.distance(LineString([(q_reel.x, q_reel.y), (r.x, r.y)]))
        essais.append((f, ecart, eloignement))
        if ecart > ECART_CLOTURE_LIMITE_MIN_M and eloignement >= SEPARATION_COTES_COTE_M:
            candidats_cloture.append((f, q_reel, r, ecart))
    if candidats_cloture:
        # Posée plus bas, une fois toutes les autres cotes connues : au milieu du
        # côté, elle tombait à Auzainvilliers parmi celles de la citerne
        # incendie et du local, et « 11,0 m (axe de la D18) » n'avait plus de
        # place (08/11/2026).
        cotes_cloture_a_poser.append((ligne.length, p_t.distance(p_l), list(candidats_cloture)))
    else:
        rapport.append(f"C1 : côté de {ligne.length:.0f} m, tables → limite {p_t.distance(p_l):.1f} m ; "
                       "pas de cote clôture → limite (écarts essayés : "
                       + ", ".join(f"{e:.1f} m à {f:.0%}" + (" trop près" if el < SEPARATION_COTES_COTE_M else "")
                                   for f, e, el in essais) + ")")
    candidats_cloture.clear()

# --- C2, retirée le 03/11/2026, revient le 08/11 : elle se calcule plus bas, une
# fois les ouvrages connus, puisqu'elle part de la construction la plus proche.

# --- C4 : clôture → habitation la plus proche ----------------------------------
residentiels = sorted(((g.distance(anneau), g) for g, p in batiments
                       if p.get("usage_1") == "Résidentiel"), key=lambda t: t[0])
if residentiels:
    d_hab, g_hab = residentiels[0]
    p_c, p_h = nearest_points(anneau, g_hab)
    cotes_dp2.append(cote_simple((p_c.x, p_c.y), (p_h.x, p_h.y),
                                 f"{nombre_fr(d_hab, 0)} m (habitation la plus proche)"))
    indifferencies = [g.distance(anneau) for g, p in batiments
                      if p.get("usage_1") == "Indifférencié" and g.distance(anneau) < d_hab]
    if indifferencies:
        rapport.append(f"C4 : {len(indifferencies)} bâtiment(s) d'usage indifférencié plus "
                       f"proche(s) que l'habitation ({d_hab:.0f} m), le premier à {min(indifferencies):.0f} m")
else:
    g_hab = None
    rapport.append(f"C4 : aucune habitation à moins de {RAYON_HABITATION_M:.0f} m")

# --- C5 : l'inter-rangée de la coupe, une seule fois ---------------------------
avertissements = []
inter_coupe = resoudre_parametre(contrat, "inter_table_m", avertissements)
angles = []
for t in tables_liste:
    r = list(t.minimum_rotated_rectangle.exterior.coords)
    cote_long = max(((r[i], r[i + 1]) for i in range(4)), key=lambda s: math.dist(*s))
    angles.append(direction(*cote_long) % 180)
axe_rangees = sorted(angles)[len(angles) // 2]
ecarts = []
for i, a in enumerate(tables_liste):
    for b in tables_liste[i + 1:]:
        d = a.distance(b)
        if not 1.0 < d < 15.0:
            continue
        pa, pb = nearest_points(a, b)
        if abs(((direction((pa.x, pa.y), (pb.x, pb.y)) % 180 - axe_rangees) % 180) - 90) < 10:
            ecarts.append((d, pa, pb))
rapport.append(f"C5 : coupe {inter_coupe} m ; écarts mesurés : {sorted({round(e[0], 1) for e in ecarts})}")
justes = [e for e in ecarts if abs(e[0] - inter_coupe) <= 0.15]
if justes:
    centre = tables.centroid
    d, pa, pb = min(justes, key=lambda e: Point((e[1].x + e[2].x) / 2, (e[1].y + e[2].y) / 2).distance(centre))
    cotes_dp2.append(cote_simple((pa.x, pa.y), (pb.x, pb.y), f"{nombre_fr(d, 1)} m entre rangées"))
else:
    rapport.append("C5 : AUCUN écart du plan ne mesure la valeur de la coupe")

# --- Les ouvrages permanents, mesurés sur leur corps ---------------------------
def dimensions(g):
    r = list(g.minimum_rotated_rectangle.exterior.coords)
    return sorted((math.dist(r[0], r[1]), math.dist(r[1], r[2])))


def corps_de(categorie, geoms):
    """Les objets aux dimensions du catalogue : le poste, pas sa plateforme."""
    corps = []
    for g in polygones(geoms):
        if g.area < 1:
            continue
        try:
            cote = contrat.cote_de_categorie(categorie, surface_m2=g.area)
        except ErreurDP:
            continue
        attendu = sorted((cote.longueur_m, cote.largeur_m))
        if all(abs(m - a) / a <= TOLERANCE_CATALOGUE for m, a in zip(dimensions(g), attendu)):
            corps.append(g)
    return corps


def separer_corps(categorie, geoms):
    """Les conteneurs aux cotes du catalogue, et ce que le calque porte autour.

    Relevé au DXF d'Auzainvilliers le 03/11/2026 : chaque BESS est un aplat
    plein de 6,0 x 8,1 m sous le bloc du conteneur de 6 x 3 m. De la même
    couleur, l'aplat cachait le conteneur, et la cote, prise sur le conteneur,
    s'arrêtait au milieu de l'orange. C'est la règle des postes
    (`palette.emprise_de_poste`), pour plusieurs ouvrages par calque.
    """
    corps, reste = [], []
    for g in geoms:
        if g.geom_type == "Polygon" and g.area >= 1:
            try:
                cote = contrat.cote_de_categorie(categorie, surface_m2=g.area)
            except ErreurDP:
                cote = None
            if cote is not None and all(
                    abs(m - a) <= TOLERANCE_COTES_POSTE * a
                    for m, a in zip(dimensions(g), sorted((cote.longueur_m, cote.largeur_m)))):
                # Le bureau d'études double parfois le même conteneur.
                if not any(g.symmetric_difference(c).area < 0.05 for c in corps):
                    corps.append(g)
                continue
        reste.append(g)
    return corps, reste


objets_d_origine = dp2_plan_masse.objets_a_dessiner
deja_dit = set()

# La v3 simulait ici la reconnaissance de tous les postes d'une catégorie. La
# palette le fait depuis le 08/11/2026 (`palette.separer_les_corps`) : la
# simulation est retirée, et `objets_avec_conteneurs` ne trouve plus rien à
# séparer qu'elle n'ait déjà séparé.
from dp_socle.planches import palette  # noqa: E402


def objets_avec_conteneurs(contrat_, avertissements=None):
    """`objets_a_dessiner`, avec les conteneurs séparés de leur aplat."""
    objets = objets_d_origine(contrat_, avertissements)
    abords = []
    for rang, (categorie, geoms) in enumerate(objets):
        if categorie not in CONTENEURS:
            continue
        corps, reste = separer_corps(categorie, geoms)
        if corps and reste:
            objets[rang] = (categorie, corps)
            abords.extend(reste)
            if categorie not in deja_dit:
                deja_dit.add(categorie)
                # Le bloc DXF d'un BESS porte aussi ses détails (148 polygones et
                # 20 traits à Auzainvilliers, relevé le 04/11/2026) : ils passent
                # sous le conteneur. Seul l'aplat qui le porte se voit, et c'est
                # sur lui que le bureau d'études doit se prononcer.
                aplats = [g for g in reste if g.geom_type == "Polygon"
                          and any(g.buffer(0.05).contains(c) for c in corps)]
                formats = sorted({" × ".join(nombre_fr(x, 1) for x in dimensions(g)) for g in aplats})
                rapport.append(f"dessin : {categorie}, {len(corps)} conteneur(s) aux cotes du catalogue, "
                               f"posé(s) sur {len(aplats)} aplat(s) de {' ; '.join(formats)} m dessiné(s) "
                               f"en plateforme ({len(reste) - len(aplats)} détail(s) du bloc dessous) — "
                               "dalle ou aire dégagée : à faire confirmer par le bureau d'études")
    if abords:
        for rang, (categorie, geoms) in enumerate(objets):
            if categorie == "plateforme":
                objets[rang] = (categorie, list(geoms) + abords)
                break
        else:
            objets.insert(0, ("plateforme", abords))
    return objets


# Le bac de rétention et la zone de remise sont des ouvrages permanents
# (chef de projet, 03/11/2026). L'aire d'aspiration non : c'est un sol.
CATEGORIES_OUVRAGES = POSTES + CONTENEURS + CITERNES + ("bac_retention", "zone_remise")
dessines = dict(objets_avec_conteneurs(contrat, []))
ouvrages, tout_ouvrage = [], []
for categorie in CATEGORIES_OUVRAGES:
    geoms = dessines.get(categorie, [])
    if not geoms:
        continue
    tout_ouvrage.extend(geoms)
    if not list(polygones(geoms)):
        rapport.append(f"!! ouvrage {categorie} : dessiné, mais aucune surface à mesurer — NON COTÉ")
        continue
    corps = corps_de(categorie, geoms)
    rapport.append(
        f"ouvrage {categorie} : {len(geoms)} objet(s), {len(corps)} aux dimensions du catalogue "
        f"{[tuple(round(x, 1) for x in dimensions(c)) for c in corps]}"
    )
    if not corps:
        rapport.append(f"   {categorie} : AUCUN objet aux dimensions du catalogue, mesuré sur tout son dessin")
        corps = list(polygones(geoms))
    paquets = unary_union([g.buffer(0.025) for g in corps])
    for partie in getattr(paquets, "geoms", [paquets]):
        ouvrages.append((categorie, unary_union([g for g in corps if g.intersects(partie)])))


def separe(segment, exclus):
    return any(segment.intersects(g) for k, (_, g) in enumerate(ouvrages) if k not in exclus)


def traverses(segment, exclus):
    return [ouvrages[k][0] for k in range(len(ouvrages))
            if k not in exclus and segment.intersects(ouvrages[k][1])]


# Les batteries et le local de stockage : l'instructeur demande « la distance
# des locaux de stockage et de batterie » (demande de compléments). Leur cote à
# la limite se pose à toute distance, et même si un autre ouvrage s'intercale
# (chef de projet, 04/11/2026). Mesuré le 04/11 à Auzainvilliers : aucun des
# deux BESS n'en avait, l'un à 19,7 m derrière le PDL/PTR, l'autre à 30,9 m.
# Le calque UNI_Local_Stockage arrive en `local_technique` (import_be.py).
TOUJOURS_A_LA_LIMITE = ("bess", "local_technique")


# --- C3 : chaque ouvrage → ses voisins naturels, et la limite --------------------
distances = [[a.distance(b) for _, b in ouvrages] for _, a in ouvrages]


def court_circuitee(i, j):
    """Un troisième ouvrage est plus proche de chacun des deux.

    Les deux cotes qui passent par lui situent déjà la paire : c'est le graphe
    de voisinage relatif. Chaque ouvrage y garde son plus proche voisin, et une
    zone y reste d'un seul tenant.
    """
    return any(max(distances[i][k], distances[j][k]) < distances[i][j]
               for k in range(len(ouvrages)) if k not in (i, j))


liens_c3, paires_sous_seuil = [], 0
for i, (_, a) in enumerate(ouvrages):
    for j in range(i + 1, len(ouvrages)):
        b = ouvrages[j][1]
        d = distances[i][j]
        if 0.05 < d < SEUIL_VOISINS_M:
            pa, pb = nearest_points(a, b)
            if not separe(LineString([pa, pb]), {i, j}):
                paires_sous_seuil += 1
                if court_circuitee(i, j):
                    k = min((k for k in range(len(ouvrages)) if k not in (i, j)),
                            key=lambda k: max(distances[i][k], distances[j][k]))
                    rapport.append(f"C3 : {ouvrages[i][0]} — {ouvrages[j][0]} {d:.1f} m non cotée, "
                                   f"{ouvrages[k][0]} est plus proche des deux "
                                   f"({distances[i][k]:.1f} et {distances[j][k]:.1f} m)")
                    continue
                cotes_c3.append(cote_simple((pa.x, pa.y), (pb.x, pb.y), f"{nombre_fr(d, 1)} m"))
                liens_c3.append((i, j))
    d = a.distance(limite)
    pa, pl = nearest_points(a, limite)
    sur_le_trajet = traverses(LineString([pa, pl]), {i})
    if ouvrages[i][0] in TOUJOURS_A_LA_LIMITE:
        cotes_c3.append(cote_simple((pa.x, pa.y), (pl.x, pl.y), f"{nombre_fr(d, 1)} m (limite parcellaire)", "dehors"))
        liens_c3.append((i, i))
        if d >= SEUIL_VOISINS_M or sur_le_trajet:
            pourquoi = ([f"au-delà de {SEUIL_VOISINS_M:.0f} m"] if d >= SEUIL_VOISINS_M else []) + (
                [f"par-dessus {', '.join(sur_le_trajet)}"] if sur_le_trajet else [])
            rapport.append(f"C3 : {ouvrages[i][0]} à {d:.1f} m de la limite, coté {' et '.join(pourquoi)}")
    elif d < SEUIL_VOISINS_M and not sur_le_trajet:
        cotes_c3.append(cote_simple((pa.x, pa.y), (pl.x, pl.y), f"{nombre_fr(d, 1)} m (limite parcellaire)", "dehors"))
        liens_c3.append((i, i))
rapport.append(f"C3 : {len(ouvrages)} ouvrage(s) ; {paires_sous_seuil} paire(s) à moins de "
               f"{SEUIL_VOISINS_M:.0f} m, {sum(1 for i, j in liens_c3 if i != j)} gardée(s) "
               f"par le voisinage relatif ; {sum(1 for i, j in liens_c3 if i == j)} cote(s) à la limite")

# --- C2 : la construction la plus proche → axe de la voie publique la plus proche (08/11/2026)
# Saint-Cyr demande les distances des constructions « par rapport aux voies et
# emprises publiques », panneaux compris : une cote, à toute distance, depuis
# la construction la plus proche. Publique au sens de C8 : hors des parcelles
# cadastrales et hors de la clôture, sur les 50 m qui entourent le point le
# plus proche de la voie.
enclos = shapely.Polygon(anneau)
constructions = unary_union([tables] + [g for _, g in ouvrages])
kx0, ky0, kx1, ky1 = constructions.bounds
cadastre_site = unary_union([p.geometrie for p in ign.telecharger_parcelles(
    (kx0 - RAYON_VOIE_M - 50, ky0 - RAYON_VOIE_M - 50, kx1 + RAYON_VOIE_M + 50, ky1 + RAYON_VOIE_M + 50))])
publiques_site = []
for v, p in voies:
    a_c, a_v = nearest_points(constructions, v)
    pres = v.intersection(a_v.buffer(50.0))
    if pres.is_empty or pres.length == 0:
        continue
    if pres.intersection(enclos).length / pres.length < 0.5 and \
            pres.difference(cadastre_site).length / pres.length >= 0.5:
        publiques_site.append((a_c.distance(a_v), v, p, a_c, a_v))
ECART_PARALLELES_M = ECART_COTES_PARALLELES_MM * DENOMINATEUR_DP2 / 1000.0


def superpose(segment, ligne, ecart_m):
    """Deux cotes parallèles à moins de `ecart_m` : elles se liraient comme une seule."""
    (x0, y0), (x1, y1) = segment.coords[0], segment.coords[-1]
    (u0, v0), (u1, v1) = ligne.coords[0], ligne.coords[-1]
    a = math.atan2(y1 - y0, x1 - x0)
    b = math.atan2(v1 - v0, u1 - u0)
    parallele = abs((a - b + math.pi / 2) % math.pi - math.pi / 2) < math.radians(15)
    return parallele and segment.distance(ligne) < ecart_m


def pieds_perpendiculaires(g, axe, pas=0.25):
    """(distance, point du bord de g, pied sur l'axe) quand le pied tombe dans l'axe.

    Un pied qui tombe au bout de l'axe n'est pas perpendiculaire : c'est le point
    le plus proche d'une voie qui s'arrête là.
    """
    resultats = []
    for poly in getattr(g, "geoms", [g]):
        if poly.geom_type != "Polygon":
            continue
        bord = poly.exterior
        n = max(8, int(bord.length / pas))
        for k in range(n):
            pt = bord.interpolate(k * bord.length / n)
            abscisse = axe.project(pt)
            if abscisse <= 0.05 or abscisse >= axe.length - 0.05:
                continue
            pied = axe.interpolate(abscisse)
            segment = LineString([pt, pied])
            if segment.length < 0.05 or segment.intersection(poly).length > 0.05:
                continue
            resultats.append((segment.length, pt, pied))
    return resultats


def cote_vers_voie(objets, publiques_vp):
    """La cote la plus courte des objets à une voie publique, et son genre.

    Perpendiculaire à l'axe quand c'est possible (relecture du 08/11/2026), depuis
    la face de l'objet tournée vers la voie, décalée le long de cette face pour
    ne se superposer à aucune autre cote. Les tronçons se fondent en un réseau :
    la BD TOPO coupe une route à chaque carrefour, et le bout d'un tronçon n'est
    pas le bout de la route. Quand le point le plus proche est l'extrémité d'une
    voie qui s'arrête avant le site, aucune perpendiculaire n'existe : la cote va
    à cette extrémité. Rend (distance, départ, pied, propriétés, genre), le genre
    valant « axe » ou « extrémité ».
    """
    reseau = linemerge(unary_union([v for v, _ in publiques_vp]))
    lignes_reseau = list(getattr(reseau, "geoms", [reseau]))
    objets_union = unary_union(objets)
    a_o, a_r = nearest_points(objets_union, reseau)
    d_min = a_o.distance(a_r)

    def proprietes(pied):
        return min(publiques_vp, key=lambda vp: vp[0].distance(pied))[1]

    candidats = []
    for axe in lignes_reseau:
        if axe.distance(objets_union) > d_min + 60.0:
            continue
        for g in sorted(objets, key=lambda g: g.distance(axe))[:6]:
            candidats.extend(pieds_perpendiculaires(g, axe))
    candidats.sort(key=lambda c: c[0])
    if not candidats or candidats[0][0] > d_min + 1.0:
        return d_min, a_o, a_r, proprietes(a_r), "extrémité"
    posees = [LineString(p) for p, _, _ in cotes_dp2 + cotes_c3]
    for d, pt, pied in candidats:
        if not any(superpose(LineString([pt, pied]), ligne, ECART_PARALLELES_M) for ligne in posees):
            if d > candidats[0][0] + 0.05:
                rapport.append(f"cote vers l'axe décalée le long de la face : {d:.2f} m au lieu de "
                               f"{candidats[0][0]:.2f} m, pour ne pas se superposer à une autre cote")
            return d, pt, pied, proprietes(pied), "axe"
    d, pt, pied = candidats[0]
    rapport.append(f"!! cote vers l'axe ({d:.1f} m) superposée à une autre cote, faute de place sur la face")
    return d, pt, pied, proprietes(pied), "axe"


def texte_voie(d, p, genre):
    valeur = nombre_fr(d, 0 if d >= 100 else 1)
    return f"{valeur} m ({'axe' if genre == 'axe' else 'extrémité'} {nom_de_voie(p)})"


def dessiner_l_axe(pied, tronçons):
    v_axe = min(tronçons, key=lambda v: v.distance(pied))
    abscisse = v_axe.project(pied)
    axes.append(substring(v_axe, max(0.0, abscisse - 25.0), min(v_axe.length, abscisse + 25.0)))


c2_segment = None
if publiques_site:
    publiques_c2 = [(v, p) for _, v, p, _, _ in publiques_site]
    objets_c2 = list(tables_liste) + [g for _, g in ouvrages]
    d, depart, pied, p, genre = cote_vers_voie(objets_c2, publiques_c2)
    cotes_dp2.append(cote_simple((depart.x, depart.y), (pied.x, pied.y), texte_voie(d, p, genre)))
    dessiner_l_axe(pied, [v for v, _ in publiques_c2])
    c2_segment = (depart, pied)
    rapport.append(f"C2 : {d:.1f} m de la construction la plus proche à "
                   f"{'l’axe' if genre == 'axe' else 'l’extrémité'} {nom_de_voie(p)} ({p.get('nature')})")
else:
    rapport.append(f"C2 : aucune voie publique à moins de {RAYON_VOIE_M:.0f} m des constructions")

# --- C7 : batteries et citernes → la table la plus proche (Auzainvilliers, 07/11/2026)
# Une cote par famille, la plus courte : c'est elle que le SDIS lit. Le BESS nord
# d'Auzainvilliers, à 28,3 m des tables quand le BESS sud en est à 8,3 m, a été
# jugé « pas utile » à la relecture du 09/11/2026.
plus_pres_par_famille = {}
for i, (categorie, g) in enumerate(ouvrages):
    if categorie in OUVRAGES_VERS_TABLES:
        d = g.distance(tables)
        if categorie not in plus_pres_par_famille or d < plus_pres_par_famille[categorie][1]:
            plus_pres_par_famille[categorie] = (i, d)
for i, (categorie, g) in enumerate(ouvrages):
    if categorie not in OUVRAGES_VERS_TABLES:
        continue
    if plus_pres_par_famille[categorie][0] != i:
        rapport.append(f"C7 : {categorie} à {g.distance(tables):.2f} m de la table la plus proche, non coté : "
                       f"un autre {categorie} en est à {plus_pres_par_famille[categorie][1]:.2f} m")
        continue
    pa, pt = nearest_points(g, tables)
    d = pa.distance(pt)
    suivantes = sorted(t.distance(g) for t in tables_liste)[:3]
    # Un ouvrage qui s'intercale porte déjà la distance qui compte, celle qui
    # sépare les tables du premier ouvrage : la règle des paires (C3). À
    # Auzainvilliers, le BESS nord passait par-dessus la citerne de
    # refroidissement, à 28,3 m (07/11/2026) ; c'est le BESS sud que le chef de
    # projet demandait.
    entre = traverses(LineString([pa, pt]), {i})
    if entre:
        rapport.append(f"C7 : {categorie} à {d:.2f} m de la table la plus proche, non coté : "
                       f"{', '.join(entre)} s'intercale")
        continue
    cotes_c3.append(cote_simple((pa.x, pa.y), (pt.x, pt.y), f"{nombre_fr(d, 1)} m (table la plus proche)"))
    liens_c3.append((i, i))
    rapport.append(f"C7 : {categorie} à {d:.2f} m de la table la plus proche "
                   f"(les trois plus proches : {', '.join(f'{x:.2f}' for x in suivantes)} m)")

# --- C8 : poste de livraison → axe de la voie publique la plus proche (Saint-Cyr, 07/11/2026)
# Une voie du domaine public n'est pas cadastrée : un tronçon BD TOPO posé sur
# des parcelles est un chemin d'exploitation ou une voie privée, et la piste
# existante que le projet reprend y figure aussi, à l'intérieur de la clôture.
for i, (categorie, g) in enumerate(ouvrages):
    if categorie not in POSTES_DE_LIVRAISON:
        continue
    cadastre = cadastre_site
    candidates = []
    for v, p in voies:
        d = v.distance(g)
        pres = v.intersection(g.buffer(d + 50.0))
        if pres.is_empty or pres.length == 0:
            continue
        candidates.append((d, v, p, pres.intersection(enclos).length / pres.length,
                           pres.difference(cadastre).length / pres.length))
    candidates.sort(key=lambda c: c[0])
    publiques = [c for c in candidates if c[3] < 0.5 and c[4] >= 0.5]
    plus_proches = [c for c in candidates if not publiques or c[0] < publiques[0][0]]
    ecartees = "; ".join(
        f"{c[2].get('nature')} à {c[0]:.1f} m, "
        + ("dans la clôture" if c[3] >= 0.5 else "sur des parcelles cadastrées")
        for c in plus_proches[:4])
    if publiques and publiques[0][0] < SEUIL_VOIE_PDL_M:
        d, pa, pv, p, genre = cote_vers_voie([g], [(c[1], c[2]) for c in publiques])
        if c2_segment is not None and pa.distance(c2_segment[0]) < 0.5 and pv.distance(c2_segment[1]) < 0.5:
            rapport.append(f"C8 : {categorie} à {d:.1f} m {nom_de_voie(p)}, confondue avec C2")
            continue
        cotes_c3.append(cote_simple((pa.x, pa.y), (pv.x, pv.y), texte_voie(d, p, genre)))
        liens_c3.append((i, i))
        dessiner_l_axe(pv, [c[1] for c in publiques])
        rapport.append(f"C8 : {categorie} à {d:.1f} m de {'l’axe' if genre == 'axe' else 'l’extrémité'} "
                       f"{nom_de_voie(p)} ({p.get('nature')})"
                       + (f" ; plus proches mais écartées : {ecartees}" if ecartees else ""))
    else:
        loin = (f"la plus proche à {publiques[0][0]:.0f} m ({publiques[0][2].get('nature')})"
                if publiques else "aucune à moins de 300 m")
        rapport.append(f"C8 : {categorie} non coté — aucune voie du domaine public à moins de "
                       f"{SEUIL_VOIE_PDL_M:.0f} m, {loin}" + (f" ; écartées : {ecartees}" if ecartees else ""))

# --- Les trois dimensions : cotes et hauteur des constructions, en légende (08/11/2026)
# Auzainvilliers demande un plan « coté dans les trois dimensions »
# (art. R. 431-36 b) du code de l'urbanisme). Les hauteurs viennent du catalogue,
# comme sur les élévations de la DP 4, et celle des tables de la coupe (D6) :
# le maximum déclaré au tableau bilan, que la notice annonce.
from dp_socle.planches.dp3_coupes import geometrie_table  # noqa: E402


def metres(x):
    texte = f"{x:.2f}".rstrip("0").rstrip(".")
    return texte.replace(".", ",")


libelles_dimensions = {}
for categorie in CATEGORIES_OUVRAGES:
    corps_cat = [g for c, g in ouvrages if c == categorie]
    if not corps_cat:
        continue
    variantes = set()
    for g in corps_cat:
        try:
            cote = contrat.cote_de_categorie(categorie, surface_m2=g.area)
        except ErreurDP as exc:
            rapport.append(f"dimensions : « {categorie} » sans cote au catalogue ({exc})")
            continue
        if not cote.a_hauteur:
            rapport.append(f"dimensions : « {categorie} » sans hauteur au catalogue ({cote.dimensions})")
            continue
        grand, petit = sorted((cote.longueur_m, cote.largeur_m), reverse=True)
        variantes.add(f"{metres(grand)} × {metres(petit)} m, h {metres(cote.hauteur_m)} m")
    if len(variantes) == 1:
        libelles_dimensions[categorie] = f"{palette.style(categorie).libelle} ({variantes.pop()})"
    elif variantes:
        rapport.append(f"!! dimensions : « {categorie} » en plusieurs variantes ({sorted(variantes)}), "
                       "une seule entrée de légende")
try:
    table_type, _ = geometrie_table(contrat)
    haut = table_type.point_haut_max_m if table_type.point_haut_max_m is not None else table_type.point_haut_m
    libelles_dimensions["tables_pv"] = (f"{palette.style('tables_pv').libelle} "
                                        f"(hauteur maximale {metres(haut)} m)")
except ErreurDP as exc:
    rapport.append(f"!! hauteur des tables : {exc}")
# La clôture a une hauteur, et elle manquait à la légende (09/11/2026). Le contrat
# n'en porte aucune : c'est la constante UNITe, celle que l'élévation de la DP 4
# cote et que la légende du plan du bureau d'études écrit (« clôture à créer
# (2m) », Saint-Cyr). L'entrée ne paraît que si la planche dessine une clôture.
from dp_socle.planches.standards import HAUTEUR_CLOTURE_M  # noqa: E402

libelles_dimensions["cloture"] = f"{palette.style('cloture').libelle} (h {metres(HAUTEUR_CLOTURE_M)} m)"
rapport.append("légende : " + " ; ".join(libelles_dimensions.values()))

# Des intitulés plus longs : la légende s'élargit plutôt que de les laisser
# déborder de son cadre, qui a une largeur fixe.
from dp_socle.planches import legende as module_legende  # noqa: E402
from dp_socle.polices import chasse_cairo, famille_active  # noqa: E402

LARGEUR_LEGENDE_D_ORIGINE = dp2_plan_masse.LARGEUR_LEGENDE_MM
_besoin = max([0.0] + [
    chasse_cairo(t, famille_active(), module_legende.TAILLE_COURANTE, False)
    + 2 * module_legende.MARGE_MM + module_legende.LARGEUR_SYMBOLE_MM + module_legende.ECART_LIBELLE_MM
    for t in libelles_dimensions.values()])
LARGEUR_LEGENDE_V4 = max(LARGEUR_LEGENDE_D_ORIGINE, math.ceil(_besoin + 1.0))

# --- C6 : largeur de chaque piste, en travers ----------------------------------
ouvrages_union = unary_union(tout_ouvrage) if tout_ouvrage else None


def largeur_en_travers(g):
    """Largeur prise perpendiculairement au bord, médiane le long du contour.

    Un rayon lancé du bord, vers l'intérieur et à angle droit, traverse la
    piste dans sa largeur même quand elle tourne ; la médiane écarte les
    bouts, les virages et les élargissements.
    """
    bord = g.exterior
    mesures = []
    n = max(12, int(bord.length // 3.0))
    for k in range(n):
        s = k * bord.length / n
        b = bord.interpolate(s)
        avant, apres_ = bord.interpolate(max(0.0, s - 1.0)), bord.interpolate(min(bord.length, s + 1.0))
        tx, ty = apres_.x - avant.x, apres_.y - avant.y
        nt = math.hypot(tx, ty)
        if nt < 1e-6:
            continue
        for sens in (1, -1):
            nx, ny = -ty / nt * sens, tx / nt * sens
            if g.contains(Point(b.x + nx * 0.05, b.y + ny * 0.05)):
                break
        else:
            continue
        rayon = LineString([(b.x + nx * 0.01, b.y + ny * 0.01), (b.x + nx * 60, b.y + ny * 60)])
        dedans = rayon.intersection(g)
        if dedans.is_empty:
            continue
        if dedans.geom_type != "LineString":
            dedans = min(dedans.geoms, key=lambda m: m.distance(b))
        mesures.append(LineString([(b.x, b.y), dedans.coords[-1]]))
    if not mesures:
        return None
    mesures.sort(key=lambda m: m.length)
    return mesures[len(mesures) // 2]


nb_c6 = 0
for categorie in CATEGORIES_PISTES:
    morceaux = geometries(categorie)
    if not morceaux:
        continue
    deja = set()
    # Une piste dessinée en morceaux jointifs est une seule piste. Les plus
    # grandes d'abord : c'est sur elles que la largeur se lit le mieux.
    fondues = unary_union([m.buffer(0.05) for m in polygones(morceaux)]).buffer(-0.05)
    for g in sorted(polygones([fondues]), key=lambda p: -p.area):
        if g.area < 20:
            continue
        if ouvrages_union is not None and g.intersection(ouvrages_union).area > 0.8 * g.area:
            rapport.append(f"C6 : {categorie} de {g.area:.0f} m² écartée, elle recouvre un ouvrage")
            continue
        # Une « piste » qui porte le corps d'un ouvrage est sa plateforme.
        if any(g.intersection(o).area >= 0.5 * o.area for _, o in ouvrages):
            rapport.append(f"C6 : {categorie} de {g.area:.0f} m² écartée, c'est la plateforme d'un ouvrage")
            continue
        travers = largeur_en_travers(g)
        if travers is None:
            rapport.append(f"C6 : {categorie} de {g.area:.0f} m², largeur non mesurable")
            continue
        w = travers.length
        if w < 2.0:
            rapport.append(f"C6 : {categorie} de {g.area:.0f} m² écartée, {w:.1f} m de large : une lanière, pas une piste")
            continue
        if g.area / (w * w) < 3.0:
            rapport.append(f"C6 : {categorie} de {g.area:.0f} m² écartée, {w:.1f} m de large : une aire, pas une piste")
            continue
        cle = round(w * 2) / 2
        if cle in deja:
            rapport.append(f"C6 : {categorie} de {g.area:.0f} m², {w:.1f} m : largeur déjà cotée pour ce type")
            continue
        deja.add(cle)
        (x1, y1), (x2, y2) = travers.coords[0], travers.coords[-1]
        # Une piste qui longe la clôture : sans son nom, sa largeur se lit
        # comme une distance de la piste à la clôture (relevé le 03/11/2026).
        cotes_dp2.append(cote_simple((x1, y1), (x2, y2), f"{nombre_fr(w, 1)} m (piste)"))
        rapport.append(f"C6 : {categorie} de {g.area:.0f} m², {w:.1f} m en travers — cotée")
        nb_c6 += 1

# --- C1, seconde cote : clôture → limite, là où elle gêne le moins (08/11/2026)
# Parmi les endroits du côté qui conviennent, celui qui reste le plus loin de
# toutes les autres cotes, maintenant qu'elles sont connues.
lignes_posees = [LineString(p) for p, _, _ in cotes_dp2 + cotes_c3]
for longueur, d_tables, candidats in cotes_cloture_a_poser:
    f, q_reel, r, ecart = max(
        candidats,
        key=lambda c: min((LineString([c[1], c[2]]).distance(ligne_) for ligne_ in lignes_posees),
                          default=math.inf))
    cotes_dp2.append(cote_simple((q_reel.x, q_reel.y), (r.x, r.y),
                                 f"{nombre_fr(ecart, 1)} m (clôture – limite parcellaire)", "dehors"))
    lignes_posees.append(LineString([q_reel, r]))
    rapport.append(f"C1 : côté de {longueur:.0f} m, tables → limite {d_tables:.1f} m ; "
                   f"clôture → limite {ecart:.1f} m à {f:.0%} du côté")

# --- Où vont les cotes d'ouvrages : DP 2, ou DP 2 bis --------------------------
planche_essai = commun.nouvelle_planche(projet, "DP 2")
zone = planche_essai.zone_dessin()
_, dimensions_cadre, _ = dp2_plan_masse._ce_que_la_planche_cadre(contrat, emprise)
denominateur = dp2_plan_masse.echelle_adaptative(
    *dimensions_cadre, zone, marge=dp2_plan_masse.MARGE, valeurs=dp2_plan_masse.ECHELLES_PLAN_MASSE)
# Une zone technique : les ouvrages que des cotes relient. Chacune décide
# pour elle-même : elle reste sur la DP 2 si toutes ses cotes s'y lisent.
parent = list(range(len(ouvrages)))


def racine(k):
    while parent[k] != k:
        parent[k] = parent[parent[k]]
        k = parent[k]
    return k


for i, j in liens_c3:
    parent[racine(i)] = racine(j)
par_racine = {}
for cote, (i, _) in zip(cotes_c3, liens_c3):
    par_racine.setdefault(racine(i), []).append(cote)
zones = list(par_racine.values())
# Les zones envoyées sur une planche de détail, par leur rang dans `zones`.
# Une cote trop courte se voit avant tout dessin ; une valeur sans place nette
# ou une cote sous la légende ne se voient qu'en essayant la DP 2 (plus bas).
renvoyees = set()
for rang, cotes_zone in enumerate(zones):
    plus_courte = min(LineString(p).length * 1000 / denominateur for p, _, _ in cotes_zone)
    if plus_courte < SEUIL_LISIBLE_MM:
        renvoyees.add(rang)
    rapport.append(f"zone {rang + 1} : {len(cotes_zone)} cote(s), la plus courte {plus_courte:.1f} mm "
                   f"au 1:{denominateur} → "
                   f"{'planche de détail' if plus_courte < SEUIL_LISIBLE_MM else 'essayée sur la DP 2'}")

# --- Le dessin ------------------------------------------------------------------
STYLE_AXE = Style(trait="#6b6b6b", epaisseur_mm=0.25, tirets="4,1,0.6,1")
STYLE_CADRE_DETAIL = Style(trait="#1f4e79", epaisseur_mm=0.35, remplissage="none", tirets="2.5,1.2")


def boite(cx, cy, largeur, hauteur):
    return (cx - largeur / 2 - 0.4, cy - hauteur / 2 - 0.3, cx + largeur / 2 + 0.4, cy + hauteur / 2 + 0.3)


def chevauche(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


STYLE_FLECHE = Style(trait="#000000", epaisseur_mm=0.05, remplissage="#000000")
FLECHE_MM = 1.6
DEMI_FLECHE_MM = 0.45


def fleche(planche, pointe, corps):
    """Flèche pleine : la pointe touche `pointe`, le corps part dans la direction `corps`."""
    m = planche.echelle / 1000.0
    bx, by = pointe[0] + corps[0] * FLECHE_MM * m, pointe[1] + corps[1] * FLECHE_MM * m
    nx, ny = -corps[1] * DEMI_FLECHE_MM * m, corps[0] * DEMI_FLECHE_MM * m
    planche.ajouter_geometrie(
        shapely.Polygon([pointe, (bx + nx, by + ny), (bx - nx, by - ny)]), STYLE_FLECHE)


GARDE_MM = 0.4    # air entre une flèche et le texte qui interrompt la ligne
AMORCE_MM = 1.2   # ligne prolongée au-delà de l'extrémité, jusqu'au texte posé dehors


def vers_l93(t, x_mm, y_mm):
    """L'inverse de `transformation.point`, écrit comme la DP 2 l'écrit déjà."""
    return (t._origine_x + (x_mm - t._x_mm) / t.mm_par_metre,
            t._origine_y - (y_mm - t._y_mm) / t.mm_par_metre)


def boite_l93(t, b):
    return box(*vers_l93(t, b[0], b[3]), *vers_l93(t, b[2], b[1]))


def poser(planche, cotes, occupees, obstacles_l93=(), souples_l93=(), masques=()):
    """Pose les cotes selon la méthode 2 de l'ISO 129, la cotation unidirectionnelle.

    Le texte reste horizontal (la planche ne sait pas le tourner) et interrompt
    sa propre ligne de cote, de préférence en son milieu : une valeur ne peut
    alors appartenir qu'à la ligne qui la traverse. Posée à côté de sa ligne,
    elle s'attribuait à la plus proche, qui n'était pas toujours la sienne
    (Auzainvilliers, 03/11/2026). Une ligne trop courte pour la loger la porte
    sur son prolongement, au-delà d'une extrémité libre.

    Rend ce qui se lit mal, cote par cote : (cote, texte, raison). Une valeur
    posée sur un ouvrage ou en travers de la clôture, une valeur sans place, une
    ligne qu'un des `masques` (la légende) recouvre. L'appelant en tire la
    décision d'envoyer la zone sur une planche de détail.
    """
    problemes = []
    t = planche.transformation
    m = planche.echelle / 1000.0
    x0, y0, x1, y1 = planche.emprise_terrain()
    retrait = 4.0 * m
    cadre = box(x0 + retrait, y0 + retrait, x1 - retrait, y1 - retrait)
    gauche, haut = t.point(x0 + retrait, y1 - retrait)
    droite, bas = t.point(x1 - retrait, y0 + retrait)
    # À éviter sans l'exiger : un texte posé sur un ouvrage le cache, posé en
    # travers de la clôture il la fait lire comme interrompue, et le cadre d'un
    # détail n'est qu'un trait de repère. On retient la place qui en touche le moins.
    # Seuls les deux premiers genres font dire qu'une valeur se lit mal : le
    # cadre d'un détail n'est qu'un repère, le traverser ne cache rien.
    souples = ([(c, g) for c, g in ouvrages] + [("clôture", anneau), ("tables", tables)]
               + [("cadre de détail", g) for g in souples_l93])

    # 1. Tous les segments d'abord : chaque étiquette doit éviter les lignes des autres.
    segments = []
    for cote in cotes:
        points, textes, _ = cote
        if len(points) == 2 and not cadre.contains(Point(points[1])):
            # La cote sort du cadre : elle s'arrête au bord, et le dit.
            morceau = LineString(points).intersection(cadre)
            if morceau.is_empty:
                rapport.append(f"cote « {textes[0]} » entièrement hors du cadre, non posée")
                continue
            if morceau.geom_type != "LineString":
                morceau = min(morceau.geoms, key=lambda g: g.distance(Point(points[0])))
            points = [points[0], morceau.coords[-1]]
            textes = [textes[0].replace(")", ", hors cadre)") if ")" in textes[0] else textes[0] + " (hors cadre)"]
        dernier = len(points) - 2
        for rang, (a, b, texte) in enumerate(zip(points, points[1:], textes)):
            am, bm = t.point(*a), t.point(*b)
            longueur = math.dist(am, bm)
            if longueur == 0:
                continue
            ux, uy = (bm[0] - am[0]) / longueur, (bm[1] - am[1]) / longueur
            # Trop court pour loger ses deux flèches : il les porte dehors, pointes
            # vers l'intérieur, sur une ligne prolongée — la convention du dessin technique.
            dehors = longueur < 2 * FLECHE_MM + 0.6
            rallonge = FLECHE_MM + AMORCE_MM if dehors else 0.0
            segments.append(dict(
                cote=cote, a=a, b=b, am=am, bm=bm, u=(ux, uy), longueur=longueur, texte=texte,
                dehors=dehors, rallonge=rallonge,
                # Dans une chaîne, seules les extrémités extérieures sont libres.
                debut_libre=rang == 0, fin_libre=rang == dernier,
                trace=LineString([(am[0] - ux * rallonge, am[1] - uy * rallonge),
                                  (bm[0] + ux * rallonge, bm[1] + uy * rallonge)]),
            ))

    # 2. Les étiquettes, les segments les plus courts d'abord : ils ont le moins de choix.
    pas = TAILLE_COTE + 0.8
    obstacles = [LineString(t.points(g.coords)) for g in obstacles_l93
                 if g is not None and g.geom_type in ("LineString", "LinearRing")]
    for s in sorted(segments, key=lambda s: s["longueur"]):
        largeur = planche.mesurer_texte(s["texte"], TAILLE_COTE)
        (ux, uy), (ax, ay), (bx, by) = s["u"], s["am"], s["bm"]
        # Du centre de l'étiquette au bord de sa boîte, le long de la ligne : c'est
        # là que la ligne doit l'atteindre, sans quoi le texte flotte à côté de son axe.
        sortie = min((largeur / 2 + 0.4) / abs(ux) if ux else math.inf,
                     (TAILLE_COTE / 2 + 0.3) / abs(uy) if uy else math.inf)
        candidats = []
        if not s["dehors"]:
            for f in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
                d = f * s["longueur"]
                if min(d, s["longueur"] - d) - sortie >= FLECHE_MM + GARDE_MM:
                    candidats.append(("sur", (ax + ux * d, ay + uy * d), 0.0))
        # Sur le prolongement, de plus en plus loin : le texte reste dans l'axe de sa ligne.
        for k in range(6):
            prolongement = (s["rallonge"] if s["dehors"] else AMORCE_MM) + k * pas
            ecart = prolongement + sortie
            if s["fin_libre"]:
                candidats.append(("fin", (bx + ux * ecart, by + uy * ecart), prolongement))
            if s["debut_libre"]:
                candidats.append(("debut", (ax - ux * ecart, ay - uy * ecart), prolongement))
        # Faute de place sur la ligne et dans son axe, la valeur est reportée et
        # reliée au milieu de sa ligne par un renvoi (ISO 129). Entre un conteneur
        # et le bac d'Auzainvilliers, les deux prolongements traversaient un ouvrage.
        mx, my = (ax + bx) / 2, (ay + by) / 2
        for rayon in (2.5, 4.0, 6.0, 8.5):
            for angle in (90, -90, 60, -60, 120, -120):
                cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
                dx, dy = ux * cos - uy * sin, ux * sin + uy * cos
                sortie_r = min((largeur / 2 + 0.4) / abs(dx) if abs(dx) > 1e-9 else math.inf,
                               (TAILLE_COTE / 2 + 0.3) / abs(dy) if abs(dy) > 1e-9 else math.inf)
                candidats.append(("renvoi", (mx + dx * (rayon + sortie_r), my + dy * (rayon + sortie_r)),
                                  (rayon, dx, dy)))
        autres = [o["trace"] for o in segments if o is not s] + obstacles

        def conflits(candidat):
            """None si la place est interdite, sinon les obstacles souples touchés."""
            genre, centre, prolongement = candidat
            b = boite(centre[0], centre[1], largeur, TAILLE_COTE)
            if b[0] < gauche or b[2] > droite or b[1] < haut or b[3] > bas:
                return None
            if any(chevauche(b, o) for o in occupees):
                return None
            if any(box(*b).intersects(o) for o in autres):
                return None
            if genre == "renvoi":
                rayon, dx, dy = prolongement
                # Reportée, la valeur ne touche pas sa propre ligne : elle s'y lirait posée.
                if box(*b).intersects(s["trace"]):
                    return None
                renvoi = LineString([(mx, my), (mx + dx * rayon, my + dy * rayon)])
                if any(renvoi.intersects(box(*o)) for o in occupees) or any(renvoi.intersects(o) for o in autres):
                    return None
                renvoi_l93 = LineString([vers_l93(t, *p) for p in renvoi.coords])
                if any(renvoi_l93.intersection(g).length > 0.05 for _, g in ouvrages):
                    return None
            elif genre != "sur":
                # La ligne prolongée jusqu'au texte ne traverse aucun autre texte.
                (px, py), sens = ((bx, by), 1) if genre == "fin" else ((ax, ay), -1)
                amorce = LineString([(px, py), (px + sens * ux * prolongement, py + sens * uy * prolongement)])
                if any(amorce.intersects(box(*o)) for o in occupees):
                    return None
                # Ni aucun ouvrage : prolongée à travers le local mesuré, elle faisait
                # lire la cote jusqu'à son autre face (Auzainvilliers, 03/11/2026).
                amorce_l93 = LineString([vers_l93(t, *p) for p in amorce.coords])
                if any(amorce_l93.intersection(g).length > 0.05 for _, g in ouvrages):
                    return None
            rectangle = boite_l93(t, b)
            return [nom for nom, g in souples if rectangle.intersects(g)]

        # La place qui touche le moins d'obstacles souples ; à égalité, la plus proche.
        # Un renvoi ajoute un trait au plan : il ne passe devant une place dans
        # l'axe que si celle-ci touche deux obstacles souples de plus.
        notes = []
        for rang, c in enumerate(candidats):
            touches = conflits(c)
            if touches is not None:
                # Une cote vers la limite porte sa valeur au-delà de la limite, hors
                # de la centrale (relecture du 08/11/2026) : toute autre place
                # compte une gêne de plus.
                dehors = s["cote"][2][0] == "dehors" and c[0] != "fin"
                notes.append((len(touches) + (1 if c[0] == "renvoi" else 0) + (1 if dehors else 0),
                              rang, touches))
        if notes:
            _, rang, touches = min(notes, key=lambda n: n[:2])
            choix = candidats[rang]
            # Les tables sont à éviter, pas interdites : une valeur posée dessus
            # se lit, et ne fait pas partir une zone en détail.
            genants = [nom for nom in touches if nom not in ("cadre de détail", "tables")]
            if genants:
                problemes.append((s["cote"], s["texte"], f"posée sur {', '.join(genants)}"))
        else:
            choix = candidats[0]
            rapport.append(f"étiquette « {s['texte']} » : aucune place sans conflit, posée au mieux")
            problemes.append((s["cote"], s["texte"], "sans place libre"))
        s["etiquette"] = choix
        s["boite"] = boite(choix[1][0], choix[1][1], largeur, TAILLE_COTE)
        occupees.append(s["boite"])

    # Une ligne que la légende recouvre, même en partie, ne se lit plus jusqu'à
    # sa flèche (« 13,4 m (limite) » à Auzainvilliers, 03/11/2026).
    for s in segments:
        if any(s["trace"].intersects(box(*m)) for m in masques):
            problemes.append((s["cote"], s["texte"], "sous la légende"))

    # 3. Le dessin : la ligne interrompue par son texte, ou prolongée jusqu'à lui.
    for s in segments:
        a, b = s["a"], s["b"]
        n = math.dist(a, b)
        vx, vy = (b[0] - a[0]) / n, (b[1] - a[1]) / n
        genre, (cx, cy), prolongement = s["etiquette"]
        avant = (prolongement if genre == "debut" else s["rallonge"]) * m
        apres = (prolongement if genre == "fin" else s["rallonge"]) * m
        ligne = LineString([(a[0] - vx * avant, a[1] - vy * avant), (b[0] + vx * apres, b[1] + vy * apres)])
        if genre == "sur":
            ligne = ligne.difference(boite_l93(t, s["boite"]))
        planche.ajouter_geometrie(ligne, TRAIT_COTE)
        if genre == "renvoi":
            rayon, dx, dy = prolongement
            mx, my = (s["am"][0] + s["bm"][0]) / 2, (s["am"][1] + s["bm"][1]) / 2
            planche.ajouter_geometrie(LineString([vers_l93(t, mx, my),
                                                  vers_l93(t, mx + dx * rayon, my + dy * rayon)]), TRAIT_COTE)
        sens = -1 if s["dehors"] else 1
        fleche(planche, a, (vx * sens, vy * sens))
        fleche(planche, b, (-vx * sens, -vy * sens))
        planche.ajouter_texte(cx, cy + TAILLE_COTE * 0.35, s["texte"], taille=TAILLE_COTE,
                              ancre="middle", halo=True)
    return problemes


coupe_d_origine = dp2_plan_masse._tracer_ligne_coupe
legende_d_origine = dp2_plan_masse.construire_legende
coin_de_legende_d_origine = dp2_plan_masse._coin_de_legende
dessiner_legende_d_origine = dp2_plan_masse.dessiner_legende
piece_d_origine = commun._piece
SOURCE_DP2 = ("Parcellaire et bâtiments : IGN — Parcellaire Express (PCI), WFS "
              "Géoplateforme. Ouvrages : plan du bureau d'études.")


def legende_en_deux_colonnes(planche, entrees, position, largeur_colonne, titre="Légende"):
    """La légende du générateur, sur deux colonnes : même cadre, mêmes symboles.

    `legende.dessiner_legende` n'en dessine qu'une. Celle-ci reprend sa géométrie
    — marges, pas, symbole, écart — et partage les entrées en deux, la première
    colonne la plus longue.
    """
    x, y = position
    par_colonne = math.ceil(len(entrees) / 2)
    hauteur = hauteur_bloc(par_colonne, titre is not None)
    planche.ajouter_rectangle(
        x, y, 2 * largeur_colonne, hauteur,
        Style(trait=NOIR, epaisseur_mm=0.25, remplissage="#ffffff", opacite_remplissage=0.92))
    curseur = y + module_legende.MARGE_MM
    if titre:
        planche.ajouter_texte(x + module_legende.MARGE_MM, curseur + 3.2, titre,
                              taille=TAILLE_CARTOUCHE, gras=True)
        curseur += module_legende.HAUTEUR_TITRE_MM
    for k, entree in enumerate(entrees):
        colonne, rang = divmod(k, par_colonne)
        x0 = x + colonne * largeur_colonne
        haut = curseur + rang * module_legende.PAS_ENTREE_MM + (
            module_legende.PAS_ENTREE_MM - module_legende.HAUTEUR_SYMBOLE_MM) / 2.0
        module_legende._dessiner_symbole(planche, entree, x0 + module_legende.MARGE_MM, haut,
                                         module_legende.LARGEUR_SYMBOLE_MM, module_legende.HAUTEUR_SYMBOLE_MM)
        planche.ajouter_texte(x0 + module_legende.MARGE_MM + module_legende.LARGEUR_SYMBOLE_MM
                              + module_legende.ECART_LIBELLE_MM,
                              haut + module_legende.HAUTEUR_SYMBOLE_MM - 1.1, entree.libelle,
                              taille=TAILLE_COURANTE)
    return (x, y, 2 * largeur_colonne, hauteur)


def generer(cotes, dossier, pied, axes_=(), apres=None, numero="5", avec_axe=False):
    def legende(*args, **kwargs):
        libelles = dict(kwargs.get("libelles") or {})
        for cle, texte in libelles_dimensions.items():
            libelles.setdefault(cle, texte)
        kwargs["libelles"] = libelles
        entrees = list(legende_d_origine(*args, **kwargs))
        entree = EntreeLegende("Cote, en mètres", TRAIT_COTE)
        entree.symbole = "ligne"
        entrees.append(entree)
        if avec_axe:
            axe = EntreeLegende("Axe de voie (BD TOPO, IGN)", STYLE_AXE)
            axe.symbole = "ligne"
            entrees.append(axe)
        etat["nb_entrees"] = len(entrees)
        return entrees

    etat = {"etiquettes": []}
    ajouter_etiquettes_d_origine = Planche.ajouter_etiquettes

    def ajouter_etiquettes_relevees(planche, points, textes, style=None):
        """Les numéros de parcelle, et la place qu'ils occupent sur le papier.

        Aucune valeur de cote ne doit les recouvrir (relecture du 08/11/2026 :
        « 0495 » sous une cote à Saint-Cyr). Ils sont posés avant les cotes.
        """
        taille = (style or {}).get("taille_mm", 2.5)
        t = planche.transformation
        for point, texte in zip(points, textes):
            x, y = t.point(*((point.x, point.y) if hasattr(point, "x") else point))
            largeur = planche.mesurer_texte(str(texte), taille)
            etat["etiquettes"].append((x - largeur / 2 - 0.3, y - taille * 0.75 - 0.3,
                                       x + largeur / 2 + 0.3, y + taille * 0.25 + 0.3))
        return ajouter_etiquettes_d_origine(planche, points, textes, style)

    def coupe_puis_cotes(planche, contrat_):
        trace = coupe_d_origine(planche, contrat_)
        for axe in axes_:
            if not axe.is_empty:
                planche.ajouter_geometrie(axe, STYLE_AXE)
        # Ce qui est déjà écrit réserve sa place avant que les cotes cherchent la leur.
        lignes, renvois = apres(planche) if apres else ([], [])
        occupees = list(etat["etiquettes"])
        z = planche.zone_dessin()
        # Les lignes s'empilent vers le haut depuis la source : la dernière écrite
        # est la plus haute. On les prend à rebours pour qu'elles se lisent dans
        # leur ordre, de haut en bas (07/11/2026).
        for k, ligne in enumerate(reversed(pied)):
            x, y = z[0] + 3.0, z[1] + z[3] - 5.6 - 2.6 * k
            planche.ajouter_texte(x, y, ligne, taille=1.9, halo=True)
            occupees.append((x - 0.3, y - 1.9, x + planche.mesurer_texte(ligne, 1.9) + 0.3, y + 0.6))
        # La ligne de source que la DP 2 écrira en pied, après la légende.
        x, y = z[0] + 3.0, z[1] + z[3] - 2.5
        occupees.append((x - 0.3, y - 1.9, x + planche.mesurer_texte(SOURCE_DP2, 1.9) + 0.3, y + 0.6))
        # Hauteur du bloc de pied, source comprise : le coin bas gauche de la
        # légende se pose au-dessus, sans quoi elle le recouvrait (Saint-Cyr,
        # DP 2 bis, 07/11/2026).
        etat.update(trace=trace, occupees=occupees, lignes=lignes, renvois=renvois,
                    pied_mm=5.5 + 2.6 * max(0, len(pied) - 1))
        return trace

    def coin_hors_des_cotes(planche, zone, objets, largeur_mm, hauteur_mm):
        """Le coin de la légende : d'abord aucune cote dessous, puis le moins de dessin.

        Posée sans connaître les cotes, la légende en cachait une (« 13,4 m
        (limite) », Auzainvilliers, 03/11/2026). Comptées comme du dessin, des
        traits épaissis de 2 m, elles pesaient trop peu : la légende fuyait une
        piste et couvrait une chaîne de cotes. Un coin qui couvre une cote est
        donc écarté tant qu'il en reste un autre ; entre les coins restants,
        la règle du générateur. Le cadre d'un détail y compte comme un trait,
        à l'égal de la clôture.
        """
        t = planche.transformation
        x, y, largeur_zone, hauteur_zone = zone
        # Le cadre d'un détail compte comme une cote : sous la légende, il perd
        # son renvoi et une partie de ce qu'il désigne (Auzainvilliers, DP 2,
        # 07/11/2026 ; déjà vrai en partie le 04/11).
        traits = [LineString(p) for p, _, _ in cotes] + list(etat["lignes"])
        dessin = [g for _, geoms in objets for g in geoms] + list(etat["lignes"])
        couvert = unary_union(dessin).buffer(dp2_plan_masse.EPAISSEUR_MESURE_LEGENDE_M)

        def coins_de(largeur, hauteur):
            return ((x + 3.0, y + 3.0), (x + largeur_zone - largeur - 3.0, y + 3.0),
                    (x + 3.0, y + hauteur_zone - hauteur - 3.0 - etat["pied_mm"]),
                    (x + largeur_zone - largeur - 3.0, y + hauteur_zone - hauteur - 3.0))

        def boite_du_coin(c, largeur, hauteur):
            return boite_l93(t, (c[0], c[1], c[0] + largeur, c[1] + hauteur))

        def choisir(largeur, hauteur):
            coins = coins_de(largeur, hauteur)
            libres = [c for c in coins
                      if not any(boite_du_coin(c, largeur, hauteur).intersects(tr) for tr in traits)]

            def part(c):
                b = boite_du_coin(c, largeur, hauteur)
                return b.intersection(couvert).area / b.area

            for c in libres:
                if part(c) <= dp2_plan_masse.RECOUVREMENT_LEGENDE_TOLERE:
                    return c, libres, coins, part
            return (min(libres, key=part) if libres else None), libres, coins, part

        # Une colonne d'abord ; deux, quand aucun coin ne reçoit la légende sans
        # couvrir une cote ou un cadre (Auzainvilliers, DP 2, 08/11/2026).
        coin, _, coins_1, part_1 = choisir(largeur_mm, hauteur_mm)
        if coin is not None:
            etat["colonnes"] = 1
            return coin
        nb = etat.get("nb_entrees", 0)
        coin, _, _, _ = choisir(2 * largeur_mm, hauteur_bloc(math.ceil(nb / 2)))
        if coin is not None:
            etat["colonnes"] = 2
            rapport.append(f"légende sur deux colonnes ({nb} entrées) : aucun coin libre en une")
            return coin
        etat["colonnes"] = 1
        rapport.append("!! légende : aucun coin libre de cote et de cadre, ni en une colonne ni en deux, "
                       "posée au coin le moins dessiné")
        return min(coins_1, key=part_1)

    def legende_puis_cotes(planche, entrees, position, largeur_mm=70.0, titre="Légende"):
        if etat.get("colonnes") == 2:
            resultat = legende_en_deux_colonnes(planche, entrees, position, largeur_mm, titre)
            boite_legende = (position[0], position[1], position[0] + 2 * largeur_mm,
                             position[1] + hauteur_bloc(math.ceil(len(entrees) / 2), titre is not None))
        else:
            resultat = dessiner_legende_d_origine(planche, entrees, position=position,
                                                  largeur_mm=largeur_mm, titre=titre)
            boite_legende = (position[0], position[1], position[0] + largeur_mm,
                             position[1] + hauteur_bloc(len(entrees), titre is not None))
        occupees = etat["occupees"] + [boite_legende]
        problemes = []
        # Le renvoi de chaque cadre, une fois la légende posée : écrit avant
        # elle, il tombait dessous (04/11/2026).
        traits = [LineString(planche.transformation.points(LineString(p).coords)) for p, _, _ in cotes]
        for code, cadre in etat["renvois"]:
            place = etiqueter_cadre(planche, code, cadre, occupees, traits)
            if place is None:
                problemes.append((None, f"renvoi au {code}", "sans place libre"))
            else:
                occupees.append(place)
        # La ligne de coupe est un trait : un texte posé dessus la coupe aussi.
        problemes += poser(planche, cotes, occupees, [etat["trace"]], etat["lignes"],
                           masques=[boite_legende])
        sous_la_legende = boite_l93(planche.transformation, boite_legende)
        for ligne in etat["lignes"]:
            if sous_la_legende.intersects(ligne):
                problemes.append((None, "cadre de détail", "en partie sous la légende"))
        etat["problemes"] = problemes
        return resultat

    dp2_plan_masse._tracer_ligne_coupe = coupe_puis_cotes
    Planche.ajouter_etiquettes = ajouter_etiquettes_relevees
    dp2_plan_masse.LARGEUR_LEGENDE_MM = LARGEUR_LEGENDE_V4
    dp2_plan_masse.construire_legende = legende
    dp2_plan_masse.objets_a_dessiner = objets_avec_conteneurs
    dp2_plan_masse._coin_de_legende = coin_hors_des_cotes
    dp2_plan_masse.dessiner_legende = legende_puis_cotes
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        sortie_planche = dp2_plan_masse.generer(projet, contrat, emprise, dossier, numero=numero)
        return sortie_planche, etat["problemes"]
    finally:
        dp2_plan_masse._tracer_ligne_coupe = coupe_d_origine
        Planche.ajouter_etiquettes = ajouter_etiquettes_d_origine
        dp2_plan_masse.LARGEUR_LEGENDE_MM = LARGEUR_LEGENDE_D_ORIGINE
        dp2_plan_masse.construire_legende = legende_d_origine
        dp2_plan_masse.objets_a_dessiner = objets_d_origine
        dp2_plan_masse._coin_de_legende = coin_de_legende_d_origine
        dp2_plan_masse.dessiner_legende = dessiner_legende_d_origine


# Une ligne de pied par idée : d'un seul tenant, la phrase dépassait 200 mm.
PIED_DP2 = ["Cotes en mètres, mesurées en Lambert 93. Limite parcellaire : celle du terrain d'assiette "
            "(parcellaire IGN). Voie publique (axe, ou extrémité quand elle s'arrête avant le site) et habitation "
            "la plus proche selon la BD TOPO (IGN).",
            "Constructions en légende : longueur × largeur, h : hauteur (catalogue UNITe ; clôture : "
            "standard UNITe ; tables : hauteur maximale du tableau bilan)."]
PIED_C3 = ["Distances entre ouvrages permanents voisins, et à la limite parcellaire, cotées en deçà de 30 m ; "
           "batteries et locaux de stockage cotés à la limite parcellaire à toute distance.",
           "Batteries et citernes : distance la plus courte jusqu'aux panneaux ; poste de livraison coté jusqu'à "
           "l'axe de la voie publique la plus proche, en deçà de 30 m."]

SUFFIXES = ("bis", "ter", "quater", "quinquies", "sexies")


def ouvrages_de(cotes_zone):
    membres = {k for c, (i, j) in zip(cotes_c3, liens_c3) if c in cotes_zone for k in (i, j)}
    return unary_union([ouvrages[k][1] for k in membres])


def etendue_de(cotes_zone):
    return unary_union([ouvrages_de(cotes_zone)] + [LineString(p) for p, _, _ in cotes_zone])


noyaux = {}   # code de la planche de détail → les ouvrages que son cadre entoure sur la DP 2


def planche_de_detail(rang, cotes_zone):
    code = f"DP 2 {SUFFIXES[rang]}"
    noyaux[code] = ouvrages_de(cotes_zone)
    etendue = etendue_de(cotes_zone)
    ex0, ey0, ex1, ey1 = etendue.bounds
    echelle_detail = dp2_plan_masse.echelle_adaptative(
        ex1 - ex0, ey1 - ey0, zone, marge=0.25, valeurs=(200, 500, 1000))

    class PieceDetail:
        intitule_cartouche = f"{code.upper()} : PLAN DE MASSE — DÉTAIL DE LA ZONE TECHNIQUE"

    cadrage, echelle_f, numero_f = (dp2_plan_masse._ce_que_la_planche_cadre,
                                    dp2_plan_masse.echelle_adaptative, dp2_plan_masse.NUMERO)
    dp2_plan_masse._ce_que_la_planche_cadre = lambda c, e, b=(ex0, ey0, ex1, ey1): (
        "cloture", (b[2] - b[0], b[3] - b[1]), ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))
    dp2_plan_masse.echelle_adaptative = lambda *a, e=echelle_detail, **k: e
    commun._piece = lambda c, code=code, piece=PieceDetail: piece() if c == code else piece_d_origine(c)
    dp2_plan_masse.NUMERO = code
    try:
        detail, problemes = generer(cotes_zone, sortie / code.replace(" ", ""), PIED_C3,
                                    axes_=axes, numero=str(6 + rang), avec_axe=bool(axes))
    finally:
        dp2_plan_masse._ce_que_la_planche_cadre = cadrage
        dp2_plan_masse.echelle_adaptative = echelle_f
        commun._piece = piece_d_origine
        dp2_plan_masse.NUMERO = numero_f
    return detail, code, etendue, problemes


planches_detail = []   # (sortie, code, étendue, problèmes)


MARGE_CADRE_MM = 3.0


def cadres_des_details(planche):
    """Le cadre de chaque zone partie en détail ; son renvoi s'écrit après la légende.

    Le cadre entoure les ouvrages de la zone, à 3 mm près, et non toute la
    planche de détail : au 1:500, celle-ci couvrait la moitié est
    d'Auzainvilliers sur la DP 2 au 1:1 000, passait sous la légende et
    sortait du cadre (04/11/2026). Les cotes de la zone n'y entrent pas : elles
    sont sur la planche de détail, pas sur la DP 2.
    """
    lignes, renvois = [], []
    marge = MARGE_CADRE_MM * planche.echelle / 1000.0
    for _, code, _, _ in planches_detail:
        ex0, ey0, ex1, ey1 = noyaux[code].bounds
        cadre = box(ex0 - marge, ey0 - marge, ex1 + marge, ey1 + marge)
        planche.ajouter_geometrie(cadre, STYLE_CADRE_DETAIL)
        lignes.append(cadre.exterior)
        renvois.append((code, cadre))
    return lignes, renvois


def etiqueter_cadre(planche, code, cadre, occupees, traits):
    """Le renvoi au-dessus du cadre, sinon dessous, sinon à côté.

    Ni sur la légende, ni sur une cote, ni en travers de la clôture ou d'un
    ouvrage : posé dessous à Auzainvilliers, la clôture le barrait (04/11/2026).
    Rend la boîte occupée, ou None si aucune place n'est libre : le renvoi est
    alors écrit à la première, et l'appelant le dit.
    """
    texte = f"Détail de la zone technique : {code}"
    largeur = planche.mesurer_texte(texte, 2.2)
    t = planche.transformation
    zx, zy, zl, zh = planche.zone_dessin()
    gauche, haut = t.point(cadre.bounds[0], cadre.bounds[3])
    droite, bas = t.point(cadre.bounds[2], cadre.bounds[1])
    places = [(gauche, haut - 1.2), (droite - largeur, haut - 1.2),
              (gauche, bas + 3.0), (droite - largeur, bas + 3.0),
              (gauche - largeur - 1.5, haut + 2.2), (droite + 1.5, haut + 2.2),
              (gauche - largeur - 1.5, bas - 0.8), (droite + 1.5, bas - 0.8)]
    genants = [anneau] + [g for _, g in ouvrages]
    for x, y in places:
        b = (x - 0.4, y - 2.6, x + largeur + 0.4, y + 0.8)
        if b[0] < zx + 3.0 or b[2] > zx + zl - 3.0 or b[1] < zy + 3.0 or b[3] > zy + zh - 3.0:
            continue
        if any(chevauche(b, o) for o in occupees) or any(box(*b).intersects(tr) for tr in traits):
            continue
        if any(boite_l93(t, b).intersects(g) for g in genants):
            continue
        planche.ajouter_texte(x, y, texte, taille=2.2, couleur="#1f4e79", halo=True)
        return b
    planche.ajouter_texte(*places[0], texte, taille=2.2, couleur="#1f4e79", halo=True)
    return None


# La DP 2 s'essaie avec les zones qui y restent. Une zone dont une valeur n'a
# pas de place nette, ou dont une ligne passe sous la légende, part sur une
# planche de détail, et la DP 2 se refait sans elle. Retirer une zone libère de
# la place mais y pose un cadre de détail, et la légende peut changer de coin :
# on recommence jusqu'à ce que plus aucune zone ne bouge.
zone_de = {id(c): k for k, z in enumerate(zones) for c in z}
construites = None
ESSAIS_MAX = len(zones) + 1
for essai in range(1, ESSAIS_MAX + 1):
    if sorted(renvoyees) != construites:
        construites = sorted(renvoyees)
        planches_detail = [planche_de_detail(r, zones[k]) for r, k in enumerate(construites)]
    sur_dp2 = [c for k, z in enumerate(zones) if k not in renvoyees for c in z]
    principal, problemes_dp2 = generer(
        cotes_dp2 + sur_dp2, sortie / "dp2", PIED_DP2 + (PIED_C3 if sur_dp2 else []),
        axes_=axes, apres=cadres_des_details, avec_axe=bool(axes))
    motifs = {}
    for cote, texte, raison in problemes_dp2:
        k = zone_de.get(id(cote))
        if k is not None:
            motifs.setdefault(k, []).append(f"« {texte} » {raison}")
    if not motifs:
        break
    if essai == ESSAIS_MAX:
        rapport.append(f"!! DP 2 : des zones se lisent encore mal après {essai} essais : {sorted(motifs)}")
        break
    for k, liste in sorted(motifs.items()):
        rapport.append(f"essai {essai} de la DP 2 : zone {k + 1} → planche de détail ({' ; '.join(liste)})")
        renvoyees.add(k)

# Ce qui se lit mal et ne peut plus partir : les cotes de la DP 2 elle-même
# (chaînes, habitation, inter-rangée, pistes), et celles des planches de détail.
for cote, texte, raison in problemes_dp2:
    if id(cote) not in zone_de:
        rapport.append(f"!! DP 2 : « {texte} » {raison}")
for detail, code, _, problemes in planches_detail:
    for cote, texte, raison in problemes:
        rapport.append(f"!! {code} : « {texte} » {raison}")

# --- Les images -------------------------------------------------------------------
PT_PAR_MM = 72 / 25.4


def rendre(sortie_planche, nom_image, zone_l93, marge_mm, pleine_page=True, dpi=300):
    document = pdfium.PdfDocument(str(sortie_planche.chemin))
    page = document[0]
    largeur_pt, hauteur_pt = page.get_size()
    if pleine_page:
        page.render(scale=150 / 72).to_pil().convert("RGB").save(sortie / f"{nom_image}.png")
    t = sortie_planche.planche.transformation
    x0, y0, x1, y1 = zone_l93
    coins = [t.point(x0, y0), t.point(x1, y1)]
    gauche = min(c[0] for c in coins) - marge_mm
    droite = max(c[0] for c in coins) + marge_mm
    haut = min(c[1] for c in coins) - marge_mm
    bas = max(c[1] for c in coins) + marge_mm
    rognure = (max(0.0, gauche * PT_PAR_MM), max(0.0, hauteur_pt - bas * PT_PAR_MM),
               max(0.0, largeur_pt - droite * PT_PAR_MM), max(0.0, haut * PT_PAR_MM))
    page.render(scale=dpi / 72, crop=rognure).to_pil().convert("RGB").save(
        sortie / f"{nom_image}{'_zoom' if pleine_page else ''}.png")
    document.close()


pres = cloture.buffer(40.0)
avec_habitation = g_hab is not None and g_hab.distance(cloture) < 250
emprise_zoom = unary_union([pres] + ([g_hab] if avec_habitation else [])).bounds
rendre(principal, f"{prefixe}_1_DP2", emprise_zoom, 4.0)
for detail, code, etendue, _ in planches_detail:
    rendre(detail, f"{prefixe}_2_{code.replace(' ', '')}", etendue.bounds, 10.0)
# Les zones techniques restées sur la DP 2, en gros plan : c'est là que les cotes se serrent.
for k, cotes_zone in enumerate(zones):
    if k in renvoyees or len(cotes_zone) < 3:
        continue
    rendre(principal, f"{prefixe}_3_zone_{k + 1}", etendue_de(cotes_zone).bounds, 6.0,
           pleine_page=False, dpi=600)

print(f"DP 2 : 1:{principal.echelle} après {essai} essai(s), {nb_c1} côté(s) C1, "
      f"{len(cotes_dp2) - nb_c1 - nb_c6} cote(s) C4/C5, {nb_c6} largeur(s) de piste, "
      f"{len(sur_dp2)} cote(s) d'ouvrages")
for detail, code, _, _ in planches_detail:
    print(f"{code} : 1:{detail.echelle}, {len(zones[construites[SUFFIXES.index(code.split()[-1])]])} cote(s)")
for ligne in rapport + avertissements:
    print("   ", ligne)
