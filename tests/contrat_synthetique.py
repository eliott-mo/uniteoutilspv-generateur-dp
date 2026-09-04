"""Contrat d'entrée du lot 4 fabriqué de toutes pièces, aux cotes connues.

Les jeux réels de `exemples/` valent pour ce qu'ils montrent d'imprévu, mais on
ne peut pas mesurer une planche contre eux : leurs cotes ne sont connues qu'à ce
que l'import en a lu. Ce site synthétique est dimensionné en nombres ronds — une
clôture de 200 x 120 m, un poste de 12 x 3 m, une coupe de 220 m sur une pente
de 2 % — pour que ce qui est mesuré dans le PDF produit se compare à une valeur
attendue et non à une autre valeur calculée par le même code.

Le GeoPackage est écrit par `import_be.ecrire_geopackage`, le producteur réel :
un fixture qui écrirait son propre schéma cesserait de tester le contrat le jour
où le contrat changerait.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from shapely.geometry import LineString, Polygon, box

from dp_socle.import_be import (
    ORIGINE_HELIOSCOPE,
    ORIGINE_IMPORT_BE,
    VERSION_CONTRAT,
    EntiteBE,
    ecrire_geopackage,
    ecrire_parametres,
)

#: Coin sud-ouest du site, en Lambert 93 : sur la commune de Bray-Saint-Aignan,
#: pour que le parcellaire IGN interrogé par DP 2 existe vraiment.
ORIGINE_L93 = (621_800.0, 6_954_100.0)

LARGEUR_SITE_M = 200.0
HAUTEUR_SITE_M = 120.0

#: Altitude au point A de la coupe, et pente le long de celle-ci.
ALTITUDE_A_M = 190.0
PENTE = 0.02

LONGUEUR_COUPE_M = 220.0
PAS_PROFIL_M = 5.0

#: Cotes du poste, choisies pour que l'inversion longueur/largeur se voie.
POSTE_LONGUEUR_M = 12.0
POSTE_LARGEUR_M = 3.0
POSTE_HAUTEUR_M = 3.0


@dataclass
class SiteSynthetique:
    """Ce que le site contient, pour que les tests l'affirment sans le relire."""

    dossier: Path
    gpkg: Path
    parametres: Path
    categories: tuple


def _rectangle(x0: float, y0: float, largeur: float, hauteur: float, z: float | None):
    """Rectangle en Lambert 93, éventuellement coté en Z."""
    coins = [
        (x0, y0),
        (x0 + largeur, y0),
        (x0 + largeur, y0 + hauteur),
        (x0, y0 + hauteur),
    ]
    if z is None:
        return Polygon(coins)
    return Polygon([(x, y, z) for x, y in coins])


def _entite(categorie: str, geometrie, calque: str = "SYNTHESE", z_reel: bool = False):
    return EntiteBE(
        categorie=categorie, calque=calque, geometrie=geometrie, z_reel=z_reel
    )


@dataclass
class _Coupe:
    """Ce qu'`ecrire_geopackage` attend d'une ligne de coupe."""

    geometrie: LineString
    corrigee: bool
    azimut_tables_deg: float
    ecart_initial_deg: float
    longueur_m: float


def entites(z_reel: bool = True, avec_voirie: bool = False) -> list:
    """Les géométries du site, dans les catégories du contrat.

    `z_reel` faux imite un dossier HelioScope : le DXF y est plat, et le Z des
    tables n'est qu'un zéro d'élévation.
    """
    x0, y0 = ORIGINE_L93
    sol = ALTITUDE_A_M

    lot = [
        # Clôture : le rectangle qui borne tout le site.
        _entite("cloture", _rectangle(x0, y0, LARGEUR_SITE_M, HAUTEUR_SITE_M, sol)),
        # Six rangées de tables, pas de 10 m, larges de 4 m.
        *[
            _entite(
                "tables_pv",
                _rectangle(
                    x0 + 20.0,
                    y0 + 20.0 + index * 10.0,
                    160.0,
                    4.0,
                    # Le Z des tables porte le plan des modules : le terrain
                    # plus la garde au sol, quand il est réel.
                    (sol + PENTE * (20.0 + index * 10.0) + 1.7) if z_reel else 0.0,
                ),
                calque="PVcase PV Modules (optimised)",
                z_reel=z_reel,
            )
            for index in range(6)
        ],
        # Un poste de livraison / transformation, 12 x 3 m, et sa plateforme.
        _entite(
            "pdl_ptr",
            _rectangle(x0 + 170.0, y0 + 8.0, POSTE_LONGUEUR_M, POSTE_LARGEUR_M, sol),
        ),
        _entite("plateforme", _rectangle(x0 + 166.0, y0 + 4.0, 20.0, 11.0, sol)),
        # Une citerne incendie de 120 m³ (11,7 x 9,3 m au catalogue).
        _entite("bache_incendie", _rectangle(x0 + 140.0, y0 + 4.0, 11.7, 9.3, sol)),
        # Piste lourde périphérique, en anneau, et une piste légère interne.
        _entite(
            "piste_lourde",
            box(x0 + 4.0, y0 + 4.0, x0 + 196.0, y0 + 116.0).difference(
                box(x0 + 10.0, y0 + 10.0, x0 + 190.0, y0 + 110.0)
            ),
        ),
        _entite("piste_legere", _rectangle(x0 + 90.0, y0 + 20.0, 4.0, 80.0, sol)),
        _entite("haie", _rectangle(x0 + 2.0, y0 + 116.0, 196.0, 2.0, sol)),
        _entite(
            "portail",
            LineString([(x0 + 100.0, y0), (x0 + 107.0, y0)]),
        ),
    ]
    if avec_voirie:
        lot.append(_entite("voirie", _rectangle(x0 + 30.0, y0 + 4.0, 30.0, 4.0, sol)))
    return lot


def ligne_coupe() -> _Coupe:
    """Coupe nord-sud passant au milieu du site, perpendiculaire aux rangées."""
    x0, y0 = ORIGINE_L93
    milieu = x0 + LARGEUR_SITE_M / 2.0
    depart = y0 + HAUTEUR_SITE_M / 2.0 - LONGUEUR_COUPE_M / 2.0
    return _Coupe(
        geometrie=LineString(
            [(milieu, depart), (milieu, depart + LONGUEUR_COUPE_M)]
        ),
        corrigee=True,
        azimut_tables_deg=0.0,
        ecart_initial_deg=0.0,
        longueur_m=LONGUEUR_COUPE_M,
    )


def profil() -> dict:
    """Profil régulier : une pente de 2 %, dont la dénivelée est connue."""
    points = [
        [round(index * PAS_PROFIL_M, 2), round(ALTITUDE_A_M + PENTE * index * PAS_PROFIL_M, 3)]
        for index in range(int(LONGUEUR_COUPE_M / PAS_PROFIL_M) + 1)
    ]
    altitudes = [p[1] for p in points]
    return {
        "origine": "profil synthétique (pente constante)",
        "pas_m": PAS_PROFIL_M,
        "denivelee_m": max(altitudes) - min(altitudes),
        "altitude_min_m": min(altitudes),
        "altitude_max_m": max(altitudes),
        "points": points,
        "avertissements": [],
    }


#: Catalogue de cotes normalisées, calqué sur celui du tableau bilan réel.
#:
#: L'ordre des cotes du PTR est inversé par rapport à celui du PDL/PTR, comme
#: dans les fichiers du bureau d'études : c'est le piège que le lot 4 doit lire
#: et non supposer.
COTES = [
    {
        "ouvrage": "Poste de livraison et de transformation - PDL/PTR",
        "dimensions": f"{POSTE_LONGUEUR_M:.0f} x {POSTE_LARGEUR_M:.0f} x "
        f"{POSTE_HAUTEUR_M:.0f}m",
        "ordre_cotes": "longueur x largeur x hauteur",
        "surface_m2": POSTE_LONGUEUR_M * POSTE_LARGEUR_M,
        "surface_plateforme_m2": 132.0,
    },
    {
        "ouvrage": "Poste de transformation - PTR",
        "dimensions": "10 x 3 x 3m",
        "ordre_cotes": "largeur x longueur x hauteur",
        "surface_m2": 30.0,
        "surface_plateforme_m2": 115.0,
    },
    {
        "ouvrage": "Citerne incendie — 30",
        "dimensions": "7,95 x 4,44 x 1,3 m",
        "ordre_cotes": "longueur x largeur x hauteur",
        "surface_m2": None,
        "surface_plateforme_m2": 35.0,
    },
    {
        "ouvrage": "Citerne incendie — 120",
        "dimensions": "11,7 x 9,3 x 1 m",
        "ordre_cotes": "longueur x largeur x hauteur",
        "surface_m2": None,
        "surface_plateforme_m2": 104.0,
    },
    {
        "ouvrage": "Aire d'aspiration",
        "dimensions": "8 x 4 m",
        "ordre_cotes": "longueur x largeur",
        "surface_m2": 32.0,
        "surface_plateforme_m2": None,
    },
]


def parametres(
    origine: str = ORIGINE_IMPORT_BE,
    avec_profil: bool = True,
    inclinaison_deg: float = 25.0,
    point_bas_m: float = 1.5,
    point_haut_m: float = 3.53,
) -> dict:
    donnees = {
        "version_contrat": VERSION_CONTRAT,
        "origine": origine,
        "sources": {"dxf": "synthese.dxf", "tableau_bilan": "synthese.xlsx",
                    "indice": "IND01"},
        "projet": {"nom": "Site synthétique", "phase": "APD",
                   "date_tableau": "2026-09-04"},
        "plan": {
            "unite_dxf": "m",
            "azimut_tables_deg": 0.0,
            "nb_tables": 6,
            "nb_portails": 1,
            "surface_cloturee_m2": LARGEUR_SITE_M * HAUTEUR_SITE_M,
            "lineaire_cloture_m": 2 * (LARGEUR_SITE_M + HAUTEUR_SITE_M),
            "surface_tables_m2": 6 * 160.0 * 4.0,
            "correspondance_calques": {},
            "calques_ignores": [],
            "avertissements": [],
        },
        "parametres": {
            "generalites": {
                "phase": "APD",
                "date": "2026-09-04",
                "type_projet": "Ovin",
                "surface_cloturee_ha": LARGEUR_SITE_M * HAUTEUR_SITE_M / 10_000.0,
                "lineaire_cloture_m": 2 * (LARGEUR_SITE_M + HAUTEUR_SITE_M),
                "nb_portails": 1,
                "largeur_portails_m": 7.0,
            },
            "structures": {
                "type_structure": "Fixe",
                "format_table": "2V26",
                "inclinaison_deg": inclinaison_deg,
                "azimut_deg": 0.0,
                "azimut_brut": "0",
                "nb_tables": 6,
                "inter_table_m": 6.0,
                "pitch_m": 10.0,
                "point_bas_m": point_bas_m,
                "point_haut_m": point_haut_m,
                "nb_modules_rampant": 2,
                "type_fondation": "Pieux battus",
            },
            "modules": {
                "format_module": "G12R",
                "puissance_unitaire_wc": 680.0,
                "surface_unitaire_m2": 2.701188,
                "nb_modules": 312,
                "gcr": None,
                "surface_modules_m2": 842.77,
                "puissance_mwc": 0.212,
            },
            "postes": {
                "nb_ptr": 0,
                "surface_ptr_m2": 0.0,
                "nb_pdl_ptr": 1,
                "surface_pdl_ptr_m2": POSTE_LONGUEUR_M * POSTE_LARGEUR_M,
                "surface_plateforme_pdl_ptr_m2": 132.0,
                "nb_pdl": 0,
            },
        },
        "cotes_normalisees": COTES,
        "standards_unite": {
            "Format modules": "G12R",
            "Inclinaison": int(inclinaison_deg),
            "Hauteur point bas": point_bas_m,
            "Hauteur point haut": point_haut_m,
            "Distance inter-table": 6,
            "Setback": 10,
        },
        "controles": [],
        "seuil_puissance_dp_mwc": 3.0,
        "avertissements_tableau": [],
        "ligne_coupe": {
            "corrigee": True,
            "azimut_tables_deg": 0.0,
            "azimut_coupe_deg": 90.0,
            "ecart_initial_deg": 0.0,
            "longueur_m": LONGUEUR_COUPE_M,
            "coordonnees_l93": [list(c) for c in ligne_coupe().geometrie.coords],
            "trace_initial_l93": [list(c) for c in ligne_coupe().geometrie.coords],
            "avertissements": [],
        },
    }
    if avec_profil:
        donnees["profil_terrain"] = profil()
    return donnees


def ecrire(
    dossier: str | Path,
    origine: str = ORIGINE_IMPORT_BE,
    avec_voirie: bool = False,
    avec_profil: bool = True,
    z_reel: bool | None = None,
    **parametres_supplementaires,
) -> SiteSynthetique:
    """Écrit un contrat complet dans `dossier` et dit ce qu'il contient."""
    dossier = Path(dossier)
    if z_reel is None:
        # Un dossier HelioScope vient d'un DXF plat : son Z n'est pas du terrain.
        z_reel = origine != ORIGINE_HELIOSCOPE
    lot = entites(z_reel=z_reel, avec_voirie=avec_voirie)
    gpkg = ecrire_geopackage(lot, dossier, ligne_coupe())
    chemin = ecrire_parametres(
        parametres(origine=origine, avec_profil=avec_profil,
                   **parametres_supplementaires),
        dossier,
    )
    return SiteSynthetique(
        dossier=dossier,
        gpkg=gpkg,
        parametres=chemin,
        categories=tuple(sorted({e.categorie for e in lot})),
    )


def altitude_a(abscisse_m: float) -> float:
    """Altitude du profil à une abscisse donnée, pour comparer sans relire."""
    return ALTITUDE_A_M + PENTE * abscisse_m


def denivelee_m() -> float:
    return PENTE * LONGUEUR_COUPE_M


def longueur_rampant_m(
    point_bas_m: float = 1.5, point_haut_m: float = 3.53, inclinaison_deg: float = 25.0
) -> float:
    """Longueur du rampant déduite des deux hauteurs et de l'inclinaison."""
    return (point_haut_m - point_bas_m) / math.sin(math.radians(inclinaison_deg))
