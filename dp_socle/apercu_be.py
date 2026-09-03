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
    "bache_incendie": StyleCategorie("Citerne incendie", (63, 191, 191), (0, 0, 0)),
    "piste_lourde_existante": StyleCategorie(
        "Piste lourde existante", (162, 162, 162), (110, 110, 110)
    ),
    "piste_lourde_a_creer": StyleCategorie(
        "Piste lourde à créer", (162, 162, 162), (0, 0, 0)
    ),
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
    "bac_equarrissage": StyleCategorie("Bac d'équarrissage", (200, 170, 120), (0, 0, 0)),
    "espace_vert": StyleCategorie("Espace vert", (176, 208, 140), (111, 170, 11)),
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
    "aire_aspiration",
    "espace_vert",
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
    "local_technique",
    "bess",
    "bac_retention",
    "citerne_refroidissement",
    "zone_remise",
    "bac_equarrissage",
    "bache_incendie",
    "limite_paddock",
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
    """Entrées de légende des seules catégories réellement importées."""
    entrees = []
    for categorie, style in STYLES.items():
        nombre = len(plan.par_categorie(categorie))
        if nombre:
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


def bornes_wgs84(geometrie: BaseGeometry) -> tuple[float, float, float, float]:
    """(sud, ouest, nord, est) en degrés, pour cadrer la carte."""
    vers_wgs84, _ = _transformateurs()
    minx, miny, maxx, maxy = geometrie.bounds
    ouest, sud = vers_wgs84.transform(minx, miny)
    est, nord = vers_wgs84.transform(maxx, maxy)
    return sud, ouest, nord, est


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
