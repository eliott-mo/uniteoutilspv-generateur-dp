"""Aperçu du plan importé sur fond d'ortho IGN (lot 2bis, étape F).

Image de contrôle destinée à l'écran, **pas une planche** : le dessin du dossier
relève du lot 4. Elle existe parce que la validation de l'import est obligatoire
et ne peut pas se juger sur des chiffres — un calque mal apparié se voit d'un
coup d'œil et ne se lit dans aucun tableau.

Les couleurs sont celles de la légende DP, relevées le 03/09/2026 sur la planche
DP 2 du dossier de référence HOCH « Les Islettes » du 25/04/2024. **Les couleurs
du DXF ne sont pas héritées** : les codes ACI y sont des couleurs de travail CAO,
non signifiantes — sur le fichier BE de Saint-Cyr, la clôture, le PDL et les
portails partagent la valeur 1.
"""

from __future__ import annotations

import math

from dataclasses import dataclass

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .erreurs import ErreurImportBE

#: Suréchantillonnage du rendu avant réduction, comme pour l'aperçu de calage du
#: lot 2 : les filets d'un pixel deviennent lisibles après réduction Lanczos.
SURECHANTILLONNAGE = 3

#: Jeu minimal autour du plan, en mètres, pour que la clôture ne touche pas le
#: bord de l'image.
JEU_CADRE_M = 25.0


@dataclass(frozen=True)
class StyleCategorie:
    """Couleur de remplissage et de filet d'une catégorie sur l'aperçu."""

    libelle: str
    remplissage: tuple[int, int, int] | None
    filet: tuple[int, int, int]
    opacite: int = 235
    epaisseur: int = 1


#: Palette de la légende DP. Les six premières valeurs sont relevées au pixel sur
#: la planche DP 2 de référence ; les suivantes n'y figurent pas (le projet des
#: Islettes ne portait ni BESS, ni bac de rétention, ni local technique) et sont
#: dérivées de la même famille, ce qui est signalé ici pour que le lot 4 les
#: reprenne ou les corrige en connaissance de cause.
STYLES = {
    "tables_pv": StyleCategorie("Tables photovoltaïques", (151, 202, 202), (0, 0, 255)),
    "cloture": StyleCategorie("Clôture du projet solaire", None, (255, 0, 0), epaisseur=4),
    "portail": StyleCategorie("Portail", None, (255, 0, 0), epaisseur=3),
    "pdl_ptr": StyleCategorie(
        "Poste de livraison / transformation", (127, 255, 191), (0, 0, 0)
    ),
    # Le poste de transformation et le poste de livraison ne figurent pas
    # séparément sur la planche de référence, qui n'a qu'une entrée « Poste de
    # livraison/transformation » : leurs teintes en sont dérivées, assez
    # distinctes pour se lire l'une de l'autre en légende.
    "ptr": StyleCategorie("Poste de transformation", (90, 214, 160), (0, 0, 0)),
    "pdl": StyleCategorie("Poste de livraison", (176, 255, 224), (0, 0, 0)),
    "bache_incendie": StyleCategorie("Citerne incendie", (63, 191, 191), (0, 0, 0)),
    "piste_lourde_existante": StyleCategorie(
        "Piste lourde existante", (162, 162, 162), (110, 110, 110)
    ),
    "piste_lourde_a_creer": StyleCategorie(
        "Piste lourde à créer", (162, 162, 162), (0, 0, 0)
    ),
    # Les deux gris de la légende de référence, repris sous les intitulés du
    # BE : « voie lourde » et « piste légère ».
    "piste_lourde": StyleCategorie("Voie lourde", (162, 162, 162), (110, 110, 110)),
    "piste_legere": StyleCategorie("Piste légère", (215, 215, 215), (140, 140, 140)),
    # Même style et même intitulé que la voie lourde : une aire de grutage est
    # un élargissement ponctuel de la voie, que le tableau bilan compte en
    # « supplément piste lourde » et que la légende du dossier de référence ne
    # distingue pas. Deux catégories dessinées à l'identique n'apparaissent
    # qu'une fois en légende.
    "aire_grutage": StyleCategorie("Voie lourde", (162, 162, 162), (110, 110, 110)),
    "plateforme": StyleCategorie("Plateforme", (215, 215, 215), (110, 110, 110)),
    "aire_aspiration": StyleCategorie(
        "Aire d'aspiration", (215, 215, 215), (63, 191, 191), epaisseur=2
    ),
    "haie": StyleCategorie("Haie plantée", (111, 170, 11), (80, 120, 8), epaisseur=2),
    # Absentes de la planche de référence, dérivées de la teinte voisine.
    "haie_existante": StyleCategorie(
        "Haie existante", (74, 112, 24), (45, 70, 12), epaisseur=2
    ),
    "voirie": StyleCategorie("Voirie (type non précisé)", (188, 188, 188), (90, 90, 90)),
    "portail_exploitant": StyleCategorie(
        "Portail d'exploitation", None, (170, 0, 0), epaisseur=2
    ),
    # Installations de chantier : hachurées en clair, ce sont des emprises
    # temporaires qu'on ne doit pas confondre avec un ouvrage définitif.
    "base_vie": StyleCategorie("Base vie (chantier)", (232, 216, 190), (150, 120, 70)),
    "stockage_chantier": StyleCategorie(
        "Stockage logistique (chantier)", (232, 216, 190), (150, 120, 70)
    ),
    # Éléments agrivoltaïques.
    "limite_paddock": StyleCategorie("Limite de paddock", None, (150, 110, 20), epaisseur=2),
    "zone_contention": StyleCategorie(
        "Zone de contention", (222, 205, 160), (150, 110, 20), epaisseur=2
    ),
    "bac_equarrissage": StyleCategorie("Bac d'équarrissage", (200, 170, 120), (0, 0, 0)),
    "espace_vert": StyleCategorie("Espace vert", (176, 208, 140), (111, 170, 11)),
    # Végétation en place, dessinée en vert sombre pour se distinguer de la haie
    # plantée sans lui disputer la lisibilité.
    "arbre_existant": StyleCategorie(
        "Arbres existants", (96, 148, 74), (55, 95, 40)
    ),
    # Compléments de l'aire de charge BESS.
    "citerne_refroidissement": StyleCategorie(
        "Citerne de refroidissement", (63, 191, 191), (0, 0, 0)
    ),
    "zone_remise": StyleCategorie("Zone de remise", (255, 205, 120), (0, 0, 0)),
    # Absentes de la planche de référence, dérivées de la même famille.
    "local_technique": StyleCategorie(
        "Local technique", (127, 255, 191), (0, 0, 0)
    ),
    "bess": StyleCategorie("Conteneurs BESS", (255, 205, 120), (0, 0, 0)),
    "bac_retention": StyleCategorie("Bac de rétention", (63, 191, 191), (0, 0, 0)),
    "ligne_coupe": StyleCategorie("Ligne de coupe A-A'", None, (0, 0, 0), epaisseur=4),
    # Produites par le seul import HelioScope. Les modules reprennent la teinte
    # des tables du dossier de référence, dont ils sont le détail ; la zone
    # d'implantation et les reculs sont des tracés d'étude, en trait fin et
    # sans remplissage pour qu'on ne les prenne pas pour des ouvrages.
    "modules_pv": StyleCategorie("Modules photovoltaïques", (151, 202, 202), (0, 0, 255)),
    "zone_implantation_pv": StyleCategorie(
        "Zone d'implantation (étude)", None, (255, 45, 45), epaisseur=2
    ),
    "recul_implantation": StyleCategorie(
        "Recul d'implantation (étude)", None, (200, 120, 40), epaisseur=1
    ),
    "zone_evitee": StyleCategorie("Zone évitée", (215, 215, 215), (110, 110, 110)),
}

#: Ordre de dessin : d'abord les surfaces de sol, puis les ouvrages posés
#: dessus, puis les tables, et enfin les linéaires. Suivre l'ordre du
#: dictionnaire faisait passer les pistes par-dessus le poste de livraison, qui
#: disparaissait de l'aperçu — exactement ce que cette image sert à contrôler.
ORDRE_DESSIN = (
    "zone_evitee",
    "plateforme",
    "piste_lourde_existante",
    "piste_lourde_a_creer",
    "piste_legere",
    "piste_lourde",
    "aire_grutage",
    "aire_aspiration",
    "espace_vert",
    "arbre_existant",
    "base_vie",
    "stockage_chantier",
    "haie",
    "haie_existante",
    "voirie",
    "tables_pv",
    # Les modules par-dessus la silhouette des rangées : c'est leur trame qui
    # rend le plan lisible, le contour groupé ne sert qu'à les cerner.
    "modules_pv",
    "pdl_ptr",
    "ptr",
    "pdl",
    "local_technique",
    "bess",
    "bac_retention",
    "citerne_refroidissement",
    "zone_remise",
    "bac_equarrissage",
    "bache_incendie",
    "limite_paddock",
    "zone_contention",
    "recul_implantation",
    "zone_implantation_pv",
    "cloture",
    "portail",
    "portail_exploitant",
)

#: Tracé initial de l'utilisateur, montré sous la ligne corrigée pour qu'il voie
#: ce qui a été redressé.
COULEUR_TRACE_INITIAL = (255, 140, 0)
COULEUR_COUPE_CORRIGEE = (0, 0, 0)
COULEUR_EMPRISE_CADASTRALE = (255, 215, 0)


def cadre_apercu(plan, extra: BaseGeometry | None = None, marge: float = 0.08):
    """Emprise géographique de l'aperçu, en Lambert 93.

    L'enveloppe est prise sur les bornes de chaque géométrie, sans les unir.
    Une union coûte cher pour un simple rectangle, et surtout elle **échoue** sur
    une géométrie invalide : le plan de Sarnois porte un polygone
    auto-intersectant sur « ESPACE VERT », et `unary_union` levait là-dessus une
    `GEOSException` qui emportait tout l'aperçu. Les bornes, elles, se lisent sur
    n'importe quelle géométrie.
    """
    boites = [e.geometrie.bounds for e in plan.entites if not e.geometrie.is_empty]
    if extra is not None and not extra.is_empty:
        boites.append(extra.bounds)
    if not boites:
        raise ErreurImportBE("Plan vide : aucun aperçu possible.")
    minx = min(b[0] for b in boites)
    miny = min(b[1] for b in boites)
    maxx = max(b[2] for b in boites)
    maxy = max(b[3] for b in boites)
    tampon = marge * max(maxx - minx, maxy - miny) + JEU_CADRE_M
    return (minx - tampon, miny - tampon, maxx + tampon, maxy + tampon)


def fond_apercu(cadre, largeur_px: int = 1100, dpi: int = 150):
    """Ortho IGN du cadre, suréchantillonnée, à ne télécharger qu'une fois."""
    from .ign import COUCHE_ORTHO, telecharger_fond

    minx, miny, maxx, maxy = cadre
    largeur = largeur_px * SURECHANTILLONNAGE
    hauteur = max(1, round(largeur * (maxy - miny) / (maxx - minx)))
    return telecharger_fond(
        COUCHE_ORTHO, cadre, largeur / dpi * 25.4, hauteur / dpi * 25.4, dpi=dpi
    )


def apercu_plan(
    plan,
    ligne_coupe=None,
    emprise_cadastrale: BaseGeometry | None = None,
    fond=None,
    cadre=None,
    largeur_px: int = 1100,
    dpi: int = 150,
):
    """Superposition des géométries importées sur l'ortho IGN, pour validation."""
    from PIL import Image, ImageDraw

    if cadre is None:
        cadre = cadre_apercu(plan, emprise_cadastrale)
    if fond is None:
        fond = fond_apercu(cadre, largeur_px=largeur_px, dpi=dpi)

    minx, miny, maxx, maxy = cadre
    largeur_m, hauteur_m = maxx - minx, maxy - miny
    image = fond.image.copy()
    px_largeur, px_hauteur = image.size
    dessin = ImageDraw.Draw(image, "RGBA")

    def en_pixels(coordonnees):
        return [
            (
                (c[0] - minx) / largeur_m * px_largeur,
                (maxy - c[1]) / hauteur_m * px_hauteur,
            )
            for c in coordonnees
        ]

    def anneaux(geometrie):
        for partie in _parties(geometrie):
            if partie.geom_type == "Polygon":
                yield en_pixels(partie.exterior.coords)
                for interieur in partie.interiors:
                    yield en_pixels(interieur.coords)
            elif partie.geom_type == "LineString":
                yield en_pixels(partie.coords)

    # Les filets sont dimensionnés dans l'image suréchantillonnée : ils
    # retrouvent leur épaisseur nominale après réduction.
    filet = max(1, round(px_largeur / largeur_px))

    if emprise_cadastrale is not None and not emprise_cadastrale.is_empty:
        for anneau in anneaux(emprise_cadastrale):
            dessin.line(
                anneau, fill=COULEUR_EMPRISE_CADASTRALE, width=filet * 3, joint="curve"
            )

    for categorie in ORDRE_DESSIN:
        style = STYLES[categorie]
        for entite in plan.par_categorie(categorie):
            for anneau in anneaux(entite.geometrie):
                if len(anneau) < 2:
                    continue
                if style.remplissage is not None and len(anneau) >= 3:
                    # Remplissage et filet séparés : `polygon(width=…)` de Pillow
                    # coûte des secondes sur une centaine de tables, `line` des
                    # centièmes. Mesuré au lot 2, même piège ici.
                    dessin.polygon(
                        anneau, fill=style.remplissage + (style.opacite,)
                    )
                dessin.line(
                    anneau,
                    fill=style.filet,
                    width=filet * style.epaisseur,
                    joint="curve",
                )

    if ligne_coupe is not None:
        dessin.line(
            en_pixels(ligne_coupe.trace_initial.coords),
            fill=COULEUR_TRACE_INITIAL,
            width=filet * 3,
            joint="curve",
        )
        dessin.line(
            en_pixels(ligne_coupe.geometrie.coords),
            fill=COULEUR_COUPE_CORRIGEE,
            width=filet * 4,
            joint="curve",
        )
        _reperes(dessin, en_pixels(ligne_coupe.geometrie.coords), filet)

    hauteur_cible = max(1, round(largeur_px * px_hauteur / px_largeur))
    return image.resize((largeur_px, hauteur_cible), Image.LANCZOS)


def _reperes(dessin, points, filet: int) -> None:
    """Marque les extrémités A et A' de la coupe, comme sur la planche DP 2."""
    rayon = filet * 6
    for point in (points[0], points[-1]):
        dessin.ellipse(
            [
                point[0] - rayon,
                point[1] - rayon,
                point[0] + rayon,
                point[1] + rayon,
            ],
            fill=COULEUR_COUPE_CORRIGEE,
        )


def _parties(geometrie: BaseGeometry):
    if hasattr(geometrie, "geoms"):
        for partie in geometrie.geoms:
            yield from _parties(partie)
    else:
        yield geometrie


def legende_presente(plan) -> list[tuple[str, StyleCategorie, int]]:
    """Entrées de légende des seules catégories réellement importées.

    Deux catégories dessinées à l'identique ne font qu'une entrée, leurs objets
    comptés ensemble : l'aire de grutage est une voie lourde élargie, et la
    faire apparaître à part dirait au lecteur du dossier une distinction que le
    plan ne montre pas.
    """
    entrees: list[tuple[str, StyleCategorie, int]] = []
    par_libelle: dict[str, int] = {}
    for categorie, style in STYLES.items():
        nombre = len(plan.par_categorie(categorie))
        if not nombre:
            continue
        if style.libelle in par_libelle:
            rang = par_libelle[style.libelle]
            entrees[rang] = (entrees[rang][0], entrees[rang][1], entrees[rang][2] + nombre)
            continue
        par_libelle[style.libelle] = len(entrees)
        entrees.append((categorie, style, nombre))
    return entrees


def figure_profil(profil, largeur_px: int = 1100, hauteur_px: int = 320):
    """Tracé du profil du terrain le long de la coupe, en PNG.

    L'échelle verticale n'est volontairement pas égale à l'horizontale : sur le
    site de référence, 0,96 m de dénivelée pour 355 m de coupe donnerait une
    ligne parfaitement plate, dont on ne pourrait rien juger. L'exagération est
    donc annoncée sur la figure elle-même.
    """
    import io

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(figsize=(largeur_px / 100, hauteur_px / 100), dpi=100)
    axes.plot(profil.abscisses_m, profil.altitudes_m, color="#8B5A2B", linewidth=1.6)
    axes.fill_between(
        profil.abscisses_m, profil.altitudes_m, min(profil.altitudes_m), color="#E8D9C5"
    )
    axes.set_xlabel("Abscisse le long de la coupe A-A' (m)")
    axes.set_ylabel("Altitude NGF (m)")
    axes.grid(True, linewidth=0.4, alpha=0.5)
    axes.margins(x=0)
    figure.tight_layout()

    # L'exagération est mesurée sur les axes réellement composés, pas estimée :
    # l'annoncer de travers serait pire que de ne rien annoncer.
    axes.set_title(
        f"Profil du terrain naturel — dénivelée {profil.denivelee_m:.2f} m sur "
        f"{profil.abscisses_m[-1]:.0f} m "
        f"(échelle verticale exagérée × {_exageration(figure, axes):.0f})",
        fontsize=9,
    )
    figure.tight_layout()

    tampon = io.BytesIO()
    figure.savefig(tampon, format="png")
    plt.close(figure)
    tampon.seek(0)
    return tampon.getvalue()


def _exageration(figure, axes) -> float:
    """Rapport entre l'échelle verticale et l'échelle horizontale du tracé."""
    boite = axes.get_window_extent(figure.canvas.get_renderer())
    x_min, x_max = axes.get_xlim()
    y_min, y_max = axes.get_ylim()
    metres_par_px_x = (x_max - x_min) / max(boite.width, 1e-9)
    metres_par_px_y = (y_max - y_min) / max(boite.height, 1e-9)
    return metres_par_px_x / max(metres_par_px_y, 1e-12)


# ---------------------------------------------------------------------------
# Carte interactive du tracé de la coupe
# ---------------------------------------------------------------------------

#: Tuiles de l'ortho IGN pour la carte interactive. Le WMTS est employé ici — et
#: non le WMS-R du reste de l'outil — parce que la carte de tracé est une carte
#: à tuiles Web Mercator : elle ne porte aucune échelle imprimée, donc aucun des
#: motifs qui imposent le Lambert 93 natif aux planches ne s'applique.
#: Vérifié le 03/09/2026 : réponse 200, image/jpeg.
URL_TUILES_ORTHO = (
    "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
    "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&TILEMATRIXSET=PM&FORMAT=image/jpeg"
    "&STYLE=normal&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
)


def _transformateurs():
    from pyproj import Transformer

    return (
        Transformer.from_crs(2154, 4326, always_xy=True),
        Transformer.from_crs(4326, 2154, always_xy=True),
    )


def en_wgs84(geometries: list[BaseGeometry]) -> dict:
    """Géométries L93 en collection GeoJSON WGS84, pour l'affichage sur la carte.

    Une **FeatureCollection**, et non une `GeometryCollection` : folium calcule
    le cadrage de la carte en descendant l'arbre de ses couches, et sa lecture
    d'une `GeometryCollection` lève `KeyError: 'coordinates'` — la carte ne
    s'affiche alors pas du tout.

    Conversion faite pour l'affichage seulement : rien de ce qui est mesuré ou
    écrit ne quitte le Lambert 93.
    """
    from shapely.geometry import mapping
    from shapely.ops import transform

    vers_wgs84, _ = _transformateurs()
    traits = []
    for geometrie in geometries:
        if geometrie is None or geometrie.is_empty:
            continue
        # Le Z du DXF n'a pas de sens sur une carte 2D et alourdit le GeoJSON.
        plan = transform(lambda x, y, z=None: vers_wgs84.transform(x, y), geometrie)
        traits.append(
            {"type": "Feature", "properties": {}, "geometry": mapping(plan)}
        )
    return {"type": "FeatureCollection", "features": traits}


def en_wgs84_point(x: float, y: float) -> tuple[float, float]:
    """Un point Lambert 93 en (latitude, longitude), pour un marqueur folium.

    Folium attend l'ordre (lat, lon), l'inverse de celui des transformateurs :
    l'intervertir place le marqueur au milieu de l'océan Indien, ce qui se
    remarque, ou à quelques kilomètres, ce qui ne se remarque pas.
    """
    vers_wgs84, _ = _transformateurs()
    lon, lat = vers_wgs84.transform(x, y)
    return lat, lon


def bornes_wgs84(geometrie: BaseGeometry) -> tuple[float, float, float, float]:
    """(sud, ouest, nord, est) en degrés, pour cadrer la carte."""
    vers_wgs84, _ = _transformateurs()
    minx, miny, maxx, maxy = geometrie.bounds
    ouest, sud = vers_wgs84.transform(minx, miny)
    est, nord = vers_wgs84.transform(maxx, maxy)
    return sud, ouest, nord, est


def clic_l93(resultat_carte: dict | None):
    """Dernier point cliqué sur la carte, ramené en Lambert 93, ou None.

    Vérifié le 15/09/2026 dans `streamlit_folium` 0.27.2 : le composant expose
    `last_clicked` (`__init__.py:347`), alimenté par `onMapClick` que son bundle
    accroche à l'événement `click` de la carte Leaflet. C'est l'objet `LatLng` de
    Leaflet tel quel, soit `{"lat": …, "lng": …}` : aucun outil de dessin n'est
    nécessaire pour recueillir un clic simple.

    Attention à l'usage : la valeur **persiste** d'une exécution du script à la
    suivante tant que le composant n'est pas remonté. Elle dit où a eu lieu le
    dernier clic, pas qu'un clic vient d'avoir lieu — c'est à l'appelant de
    retenir celui qu'il a déjà consommé.
    """
    from shapely.geometry import Point

    if not resultat_carte:
        return None
    clic = resultat_carte.get("last_clicked")
    if not isinstance(clic, dict):
        return None
    latitude, longitude = clic.get("lat"), clic.get("lng")
    if latitude is None or longitude is None:
        return None
    _, vers_l93 = _transformateurs()
    return Point(vers_l93.transform(float(longitude), float(latitude)))


#: Longueur des tirets du trait d'aperçu, en pixels. Assez longs pour se lire au
#: milieu des rangées, assez espacés pour ne pas se confondre avec la coupe
#: retenue, qui est pleine.
TIRETS_APERCU = "10 8"


def apercu_au_survol(
    reference,
    couleur: str = "#000000",
    epaisseur: int = 3,
    opacite: float = 0.75,
    message_attente: str = "Coupe prise — relevé du profil du terrain…",
):
    """Trait montrant où la coupe se posera, qui suit la souris sans rechargement.

    **Tout se passe dans le navigateur.** Faire suivre la souris côté Python
    demanderait `return_on_hover`, qui relance le script Streamlit à chaque
    mouvement — la carte se redessine, le plan se recompose, et l'écran pédale.
    Ici Leaflet déplace une polyligne qu'il a déjà : rien ne remonte à Streamlit
    tant que le chef de projet n'a pas cliqué.

    Le calcul tient en une propriété mesurée le 15/09/2026 : déplacer la coupe la
    **translate en bloc**. `_etendre` projette les sommets de l'emprise sur la
    direction de coupe *relativement au point de passage* ; déplacer ce point
    perpendiculairement à la coupe ne change aucune de ces projections, et le
    segment glisse sans tourner ni changer de longueur — vérifié exact au bit
    près. L'aperçu est donc le segment de référence translaté jusqu'au curseur,
    et non une coupe recalculée.

    La translation se fait dans le plan de la carte, en pixels, et non en
    Lambert 93 : c'est ce dont Leaflet dispose. Le Web Mercator étant conforme, le
    trait reste parallèle à la coupe ; l'écart au tracé réel a été mesuré sur
    Saint-Cyr à **1,3 cm au pire**, soit trente-six fois moins qu'un pixel de
    carte au zoom 18. L'aperçu ne ment pas sur l'endroit où la coupe ira.

    `reference` est n'importe quelle ligne de coupe du plan, en Lambert 93 : elles
    sont toutes parallèles, et seule sa direction sert.

    À savoir avant de le prendre pour un défaut : **la coupe n'est pas verticale à
    l'écran**, et le trait se décale donc un peu latéralement quand on survole de
    haut en bas à abscisse constante. Ce n'est pas un glissement parasite, c'est
    la convergence des méridiens — le nord de grille du Lambert 93 n'est pas le
    nord vrai auquel le Web Mercator s'aligne. Mesurée à Saint-Cyr le 15/09/2026 :
    0,745°, soit 8,5 px de décalage pour 650 px de survol vertical, relevés à 7 px
    dans le navigateur, l'écart étant l'arrondi au pixel entier de Leaflet. Une
    coupe perpendiculaire aux rangées l'est aux rangées, pas au bord de l'écran.
    """
    from branca.element import MacroElement, Template

    vers_wgs84, _ = _transformateurs()
    (x1, y1), (x2, y2) = reference.coords[0][:2], reference.coords[-1][:2]
    depart = vers_wgs84.transform(x1, y1)
    arrivee = vers_wgs84.transform(x2, y2)

    class _ApercuAuSurvol(MacroElement):
        _template = Template(
            """
            {% macro script(this, kwargs) %}
            (function () {
                var carte = {{ this._parent.get_name() }};
                var ancre = [
                    [{{ this.depart_lat }}, {{ this.depart_lon }}],
                    [{{ this.arrivee_lat }}, {{ this.arrivee_lon }}]
                ];
                var apercu = L.polyline(ancre, {
                    color: "{{ this.couleur }}",
                    weight: {{ this.epaisseur }},
                    opacity: 0,
                    dashArray: "{{ this.tirets }}",
                    interactive: false
                }).addTo(carte);

                // Vrai des que le clic est donne : le trait ne suit plus rien.
                var fige = false;

                var attente = L.DomUtil.create("div", "", carte.getContainer());
                attente.textContent = "{{ this.message_attente }}";
                attente.style.cssText = [
                    "display:none",
                    "position:absolute",
                    "top:10px",
                    "left:50%",
                    "transform:translateX(-50%)",
                    "z-index:1000",
                    "padding:6px 12px",
                    "border-radius:4px",
                    "background:rgba(17,17,17,0.88)",
                    "color:#ffffff",
                    "font:13px system-ui, sans-serif",
                    "pointer-events:none",
                    "white-space:nowrap"
                ].join(";");

                function placer(curseur) {
                    var a = carte.latLngToLayerPoint(L.latLng(ancre[0][0], ancre[0][1]));
                    var b = carte.latLngToLayerPoint(L.latLng(ancre[1][0], ancre[1][1]));
                    var c = carte.latLngToLayerPoint(curseur);
                    var dx = b.x - a.x, dy = b.y - a.y;
                    var norme = Math.sqrt(dx * dx + dy * dy);
                    if (!norme) { return; }
                    var ux = dx / norme, uy = dy / norme;
                    var vx = c.x - a.x, vy = c.y - a.y;
                    // Composante du curseur perpendiculaire a la coupe : c'est
                    // de cela, et de cela seulement, que le segment se decale.
                    var t = vx * ux + vy * uy;
                    var wx = vx - t * ux, wy = vy - t * uy;
                    apercu.setLatLngs([
                        carte.layerPointToLatLng(L.point(a.x + wx, a.y + wy)),
                        carte.layerPointToLatLng(L.point(b.x + wx, b.y + wy))
                    ]);
                    apercu.setStyle({opacity: {{ this.opacite }}});
                }

                carte.on("mousemove", function (e) {
                    if (!fige) { placer(e.latlng); }
                });
                // Souris sortie de la carte : le trait n'a plus de sens, et le
                // laisser fige un aperçu la ou la souris a quitte l'ecran. Une
                // fois le clic donne, en revanche, il doit rester ou il est.
                carte.on("mouseout", function () {
                    if (!fige) { apercu.setStyle({opacity: 0}); }
                });

                // Le clic Leaflet arrive tout de suite ; Streamlit, lui, met une
                // a deux secondes a rejouer le script — releve du profil et
                // controles de coherence compris. Pendant ce temps la carte
                // affichee est encore l'ancienne, et un trait qui continuerait de
                // suivre la souris donne a croire que le clic n'a pas pris : le
                // chef de projet reclique, et son second point est ignore parce
                // que le geste est deja desarme. Le trait se fige donc ici, prend
                // l'aspect d'une coupe retenue, et le dit.
                carte.on("click", function (e) {
                    if (fige) { return; }
                    placer(e.latlng);
                    fige = true;
                    apercu.setStyle({
                        dashArray: null,
                        opacity: 1,
                        weight: {{ this.epaisseur_fige }}
                    });
                    attente.style.display = "block";
                    carte.getContainer().style.cursor = "progress";
                });
            })();
            {% endmacro %}
            """
        )

        def __init__(self):
            super().__init__()
            # Après `super().__init__()`, et non en attribut de classe :
            # `MacroElement.__init__` pose `self._name = "MacroElement"` sur
            # l'instance et écraserait le nôtre. C'est ce nom qui permet de
            # retrouver le calque sur la carte, et donc de le tester.
            self._name = "ApercuCoupeAuSurvol"
            self.depart_lat, self.depart_lon = depart[1], depart[0]
            self.arrivee_lat, self.arrivee_lon = arrivee[1], arrivee[0]
            self.couleur = couleur
            self.epaisseur = epaisseur
            self.opacite = opacite
            self.tirets = TIRETS_APERCU
            self.message_attente = message_attente
            # Une fois le clic donne, le trait prend l'epaisseur de la coupe
            # retenue : ce n'est plus un apercu, c'est la coupe, que Streamlit
            # n'a pas encore fini de redessiner.
            self.epaisseur_fige = epaisseur + 1

    return _ApercuAuSurvol()


#: Nombre de segments du bord courbe du cône d'aperçu. Huit suffisent pour un
#: secteur de 50° : l'arc y est lisse à l'œil, et chaque sommet de plus est
#: recalculé à chaque mouvement de souris.
SEGMENTS_CONE_APERCU = 8

#: Rayon terrestre servant à convertir un rayon en mètres en écart de latitude.
#: Le cône d'aperçu n'a pas à être métriquement exact — il montre une direction
#: — mais un rayon en mètres le fait ressembler au cône de la planche, à tous
#: les niveaux de zoom.
_METRES_PAR_DEGRE_LAT = 111_320.0


def apercu_de_visee(
    lat: float,
    lon: float,
    ouverture_deg: float,
    rayon_m: float,
    couleur: str,
    message_attente: str = "Direction prise — mise à jour de la carte…",
):
    """Cône ancré à la prise de vue, qui pivote vers la souris sans rechargement.

    Même principe que `apercu_au_survol`, et pour la même raison : **tout se
    passe dans le navigateur**. Faire suivre la souris côté Python demanderait
    `return_on_hover`, qui relance le script Streamlit à chaque mouvement.

    Sans lui, viser était un geste aveugle : « je clique sur Viser, la carte
    semble se rafraîchir, mais rien ne m'indique quel point est concerné ni dans
    quelle direction je vise » (retour d'usage du 22/09/2026). Le cône montre
    les deux — son sommet est la photographie, sa direction est celle du
    curseur — et il se fige au clic, comme le trait de la coupe, parce que
    Streamlit met une à deux secondes à redessiner et qu'un cône qui
    continuerait de suivre la souris ferait croire que le clic n'a pas pris.

    L'angle est calculé **en pixels de l'écran**, et non en Lambert 93 : c'est
    ce dont Leaflet dispose, et c'est aussi la direction que l'œil voit. Le cap
    retenu, lui, est recalculé en Lambert 93 par `cap_vers` une fois le clic
    remonté — l'aperçu montre, il ne mesure pas.
    """
    from branca.element import MacroElement, Template

    class _ApercuDeVisee(MacroElement):
        _template = Template(
            """
            {% macro script(this, kwargs) %}
            (function () {
                var carte = {{ this._parent.get_name() }};
                var ancre = L.latLng({{ this.lat }}, {{ this.lon }});
                var cone = L.polygon([], {
                    color: "{{ this.couleur }}",
                    weight: 1,
                    opacity: 0,
                    fillColor: "{{ this.couleur }}",
                    fillOpacity: 0,
                    interactive: false
                }).addTo(carte);

                // Le sommet du cone : la photographie elle-meme, bien visible
                // des que le geste est arme. C'est la reponse a « quel point
                // est concerne ».
                var sommet = L.circleMarker(ancre, {
                    radius: 9,
                    color: "{{ this.couleur }}",
                    weight: 3,
                    fillColor: "#ffffff",
                    fillOpacity: 1,
                    interactive: false
                }).addTo(carte);

                var fige = false;

                var attente = L.DomUtil.create("div", "", carte.getContainer());
                attente.textContent = "{{ this.message_attente }}";
                attente.style.cssText = [
                    "display:none", "position:absolute", "top:10px", "left:50%",
                    "transform:translateX(-50%)", "z-index:1000",
                    "padding:6px 12px", "border-radius:4px",
                    "background:rgba(17,17,17,0.88)", "color:#ffffff",
                    "font:13px system-ui, sans-serif", "pointer-events:none",
                    "white-space:nowrap"
                ].join(";");

                function rayonEnPixels() {
                    var a = carte.latLngToLayerPoint(ancre);
                    var b = carte.latLngToLayerPoint(
                        L.latLng(ancre.lat + {{ this.delta_lat }}, ancre.lng)
                    );
                    return Math.max(12, Math.abs(b.y - a.y));
                }

                function placer(curseur) {
                    var a = carte.latLngToLayerPoint(ancre);
                    var c = carte.latLngToLayerPoint(curseur);
                    var dx = c.x - a.x, dy = c.y - a.y;
                    if (!dx && !dy) { return; }
                    // Angle a l'ecran : y descend, ce qui inverse le sens, mais
                    // le cone n'a qu'a pointer vers le curseur.
                    var axe = Math.atan2(dy, dx);
                    var demi = {{ this.demi_ouverture_rad }};
                    var rayon = rayonEnPixels();
                    var sommets = [carte.layerPointToLatLng(a)];
                    var n = {{ this.segments }};
                    for (var i = 0; i <= n; i += 1) {
                        var angle = axe - demi + (2 * demi * i) / n;
                        sommets.push(carte.layerPointToLatLng(L.point(
                            a.x + rayon * Math.cos(angle),
                            a.y + rayon * Math.sin(angle)
                        )));
                    }
                    cone.setLatLngs(sommets);
                    cone.setStyle({opacity: 0.9, fillOpacity: 0.35});
                }

                carte.on("mousemove", function (e) {
                    if (!fige) { placer(e.latlng); }
                });
                carte.on("mouseout", function () {
                    if (!fige) { cone.setStyle({opacity: 0, fillOpacity: 0}); }
                });
                carte.on("zoomend", function () {
                    if (fige) { return; }
                    cone.setStyle({opacity: 0, fillOpacity: 0});
                });
                carte.on("click", function (e) {
                    if (fige) { return; }
                    placer(e.latlng);
                    fige = true;
                    cone.setStyle({opacity: 1, fillOpacity: 0.55});
                    attente.style.display = "block";
                    carte.getContainer().style.cursor = "progress";
                });
            })();
            {% endmacro %}
            """
        )

        def __init__(self):
            super().__init__()
            # Après `super().__init__()` : voir `apercu_au_survol`.
            self._name = "ApercuDeVisee"
            self.lat = lat
            self.lon = lon
            self.couleur = couleur
            self.segments = SEGMENTS_CONE_APERCU
            self.demi_ouverture_rad = math.radians(ouverture_deg) / 2.0
            self.delta_lat = rayon_m / _METRES_PAR_DEGRE_LAT
            self.message_attente = message_attente

    return _ApercuDeVisee()


def apercu_de_placement(
    couleur: str,
    message_attente: str = "Position prise — mise à jour de la carte…",
):
    """Repère qui suit la souris, pour montrer où la photographie se posera.

    Le pendant de `apercu_de_visee` pour le geste de placement : « idem pour le
    replacement, trop lent et pas visuel, on ne comprend pas quoi faire et quand
    on clique pour valider on a l'impression que tout plante l'espace d'une
    seconde » (22/09/2026).

    Le figement au clic répond directement à cette dernière phrase : le repère
    prend sa couleur pleine, la carte passe en curseur d'attente et dit ce
    qu'elle fait, pendant que Streamlit rejoue le script.
    """
    from branca.element import MacroElement, Template

    class _ApercuDePlacement(MacroElement):
        _template = Template(
            """
            {% macro script(this, kwargs) %}
            (function () {
                var carte = {{ this._parent.get_name() }};
                var repere = L.circleMarker(carte.getCenter(), {
                    radius: 8,
                    color: "{{ this.couleur }}",
                    weight: 3,
                    opacity: 0,
                    fillColor: "{{ this.couleur }}",
                    fillOpacity: 0,
                    interactive: false
                }).addTo(carte);

                var fige = false;

                var attente = L.DomUtil.create("div", "", carte.getContainer());
                attente.textContent = "{{ this.message_attente }}";
                attente.style.cssText = [
                    "display:none", "position:absolute", "top:10px", "left:50%",
                    "transform:translateX(-50%)", "z-index:1000",
                    "padding:6px 12px", "border-radius:4px",
                    "background:rgba(17,17,17,0.88)", "color:#ffffff",
                    "font:13px system-ui, sans-serif", "pointer-events:none",
                    "white-space:nowrap"
                ].join(";");

                carte.on("mousemove", function (e) {
                    if (fige) { return; }
                    repere.setLatLng(e.latlng);
                    repere.setStyle({opacity: 0.9, fillOpacity: 0.35});
                });
                carte.on("mouseout", function () {
                    if (!fige) { repere.setStyle({opacity: 0, fillOpacity: 0}); }
                });
                carte.on("click", function (e) {
                    if (fige) { return; }
                    repere.setLatLng(e.latlng);
                    fige = true;
                    repere.setStyle({opacity: 1, fillOpacity: 1});
                    attente.style.display = "block";
                    carte.getContainer().style.cursor = "progress";
                });
            })();
            {% endmacro %}
            """
        )

        def __init__(self):
            super().__init__()
            self._name = "ApercuDePlacement"
            self.couleur = couleur
            self.message_attente = message_attente

    return _ApercuDePlacement()


def trace_l93(resultat_carte: dict | None):
    """Dernière polyligne tracée sur la carte, ramenée en Lambert 93.

    `st_folium` rend les tracés en GeoJSON WGS84. On retient le dernier tracé
    plutôt que le premier : redessiner corrige, et il ne doit pas y avoir à
    supprimer l'ancien pour que le nouveau soit pris.
    """
    from shapely.geometry import LineString

    if not resultat_carte:
        return None
    dessins = resultat_carte.get("all_drawings") or []
    dernier = resultat_carte.get("last_active_drawing") or (
        dessins[-1] if dessins else None
    )
    if not dernier:
        return None
    geometrie = dernier.get("geometry") or {}
    if geometrie.get("type") != "LineString":
        return None
    coordonnees = geometrie.get("coordinates") or []
    if len(coordonnees) < 2:
        return None
    _, vers_l93 = _transformateurs()
    return LineString(
        [vers_l93.transform(float(lon), float(lat)) for lon, lat, *_ in coordonnees]
    )


# ---------------------------------------------------------------------------
# Repérage des voiries à trancher
# ---------------------------------------------------------------------------

#: Teintes du croquis de repérage. Le gris des objets écartés n'est pas une
#: couleur de moins : c'est ce qui permet au chef de projet de comprendre
#: pourquoi le plan compte quatre objets et le choix deux.
_CROQUIS_FOND = (250, 250, 248)
_CROQUIS_CLOTURE = (200, 40, 40)
_CROQUIS_TABLES = (196, 208, 226)
_CROQUIS_VOIRIE = (232, 140, 20)
_CROQUIS_ECARTE = (150, 150, 150)


def croquis_voiries(plan, largeur_px: int = 520, marge: float = 0.06):
    """Situe chaque objet de la couche `voirie`, numéroté, sur la silhouette du site.

    Sans fond cartographique : ce croquis répond à une seule question — « l'objet
    2, c'est lequel ? » — et doit s'afficher à côté des boutons sans attendre un
    téléchargement. La clôture et les tables suffisent à situer.

    Les objets **sans surface** y figurent en gris. Ils ne sont pas proposés au
    choix — un axe n'est ni lourd ni léger — mais les taire ferait un croquis à
    deux objets pour un plan qui en compte quatre, et le chef de projet
    chercherait l'erreur.

    Rend une image Pillow, ou `None` si la couche est vide.
    """
    from PIL import Image, ImageDraw

    voiries = plan.geometries("voirie")
    if not voiries:
        return None

    cloture = plan.geometries("cloture")
    tables = plan.tables
    # Le cadre se prend sur le **site**, pas sur les voiries : un objet égaré à
    # neuf cents mètres — cela arrive, et c'est en soi une information —
    # écraserait tout le plan dans un coin de l'image. Ceux qui en sortent sont
    # signalés par `voiries_hors_cadre`, non forcés dans le croquis.
    cadre = _cadre_du_croquis(cloture or voiries, marge)
    if cadre is None:
        return None
    minx, miny, maxx, maxy = cadre
    largeur_m, hauteur_m = maxx - minx, maxy - miny
    hauteur_px = max(1, int(round(largeur_px * hauteur_m / largeur_m)))
    image = Image.new("RGB", (largeur_px, hauteur_px), _CROQUIS_FOND)
    dessin = ImageDraw.Draw(image, "RGBA")

    def en_pixels(coordonnees):
        return [
            (
                (x - minx) / largeur_m * largeur_px,
                (maxy - y) / hauteur_m * hauteur_px,
            )
            for x, y, *_ in coordonnees
        ]

    for table in tables:
        for partie in _parties(table):
            if partie.geom_type == "Polygon":
                dessin.polygon(en_pixels(partie.exterior.coords), fill=_CROQUIS_TABLES)
    for contour in cloture:
        for partie in _parties(contour):
            points = en_pixels(
                partie.exterior.coords if partie.geom_type == "Polygon"
                else partie.coords
            )
            if len(points) > 1:
                dessin.line(points, fill=_CROQUIS_CLOTURE, width=2)

    for rang, geometrie in enumerate(voiries, start=1):
        surfacique = geometrie.area > 0
        couleur = _CROQUIS_VOIRIE if surfacique else _CROQUIS_ECARTE
        for partie in _parties(geometrie):
            if partie.geom_type == "Polygon":
                dessin.polygon(
                    en_pixels(partie.exterior.coords), fill=couleur + (170,),
                    outline=couleur, width=2,
                )
            elif partie.geom_type == "LineString":
                points = en_pixels(partie.coords)
                if len(points) > 1:
                    dessin.line(points, fill=couleur, width=4)
        _etiquette_croquis(
            dessin, en_pixels([geometrie.centroid.coords[0]])[0], str(rang), couleur
        )
    return image


def _cadre_du_croquis(geometries, marge: float):
    """Boîte englobante élargie, ou `None` si rien n'est exploitable."""
    bornes = [g.bounds for g in geometries if g is not None and not g.is_empty]
    if not bornes:
        return None
    minx = min(b[0] for b in bornes)
    miny = min(b[1] for b in bornes)
    maxx = max(b[2] for b in bornes)
    maxy = max(b[3] for b in bornes)
    # Un plancher d'un mètre : une couche réduite à un seul point donnerait une
    # boîte plate, et une division par zéro au passage en pixels.
    largeur = max(maxx - minx, 1.0)
    hauteur = max(maxy - miny, 1.0)
    jeu = marge * max(largeur, hauteur)
    return (minx - jeu, miny - jeu, minx + largeur + jeu, miny + hauteur + jeu)


def voiries_hors_cadre(plan, marge: float = 0.06) -> list:
    """Les objets de voirie que le croquis ne peut pas montrer, et leur éloignement.

    Un objet hors du site n'est pas un détail de cadrage : c'est un résidu de
    dessin, ou une voie oubliée loin du projet. Le dire nommément vaut mieux que
    de le faire disparaître, et mieux que d'écraser le plan pour l'y faire tenir.

    Rend une liste de `(rang, distance en mètres au site)`, rangs comptés à
    partir de 1 comme sur le croquis.
    """
    from shapely.geometry import box

    voiries = plan.geometries("voirie")
    cloture = plan.geometries("cloture")
    cadre = _cadre_du_croquis(cloture or voiries, marge)
    if cadre is None or not cloture:
        return []
    fenetre = box(*cadre)
    site = unary_union([c for c in cloture if c is not None and not c.is_empty])
    return [
        (rang, geometrie.distance(site))
        for rang, geometrie in enumerate(voiries, start=1)
        if not geometrie.is_empty and not fenetre.intersects(geometrie)
    ]


def _etiquette_croquis(dessin, point, texte: str, couleur) -> None:
    """Pastille numérotée, lisible sur n'importe quel fond du croquis."""
    rayon = 11
    x, y = point
    dessin.ellipse(
        [x - rayon, y - rayon, x + rayon, y + rayon],
        fill=(255, 255, 255), outline=couleur, width=2,
    )
    dessin.text((x, y), texte, fill=(26, 26, 26), anchor="mm")
