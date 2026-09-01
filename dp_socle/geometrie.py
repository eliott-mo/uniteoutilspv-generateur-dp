"""Chargement de l'emprise du projet et mise en Lambert 93.

Pièges traités ici, tous signalés explicitement plutôt que devinés :
- le shapefile arrive en ZIP ou décompressé ;
- il peut contenir plusieurs polygones : on traite l'union, pas le premier ;
- son CRS peut ne pas être le Lambert 93 : on reprojette, en le disant ;
- son `.prj` peut manquer : on refuse, on ne suppose pas.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .erreurs import ErreurCRS, ErreurEmprise

CRS_PROJET = "EPSG:2154"

_EXTENSIONS_VECTEUR = (".shp", ".geojson", ".json", ".gpkg", ".kml", ".gml")


@dataclass
class Emprise:
    """Emprise du projet, toujours en Lambert 93."""

    geometrie: BaseGeometry
    crs_source: str
    reprojetee: bool
    nb_polygones: int
    source: str

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return tuple(self.geometrie.bounds)

    @property
    def centre(self) -> tuple[float, float]:
        minx, miny, maxx, maxy = self.bbox
        return ((minx + maxx) / 2.0, (miny + maxy) / 2.0)

    @property
    def dimensions_m(self) -> tuple[float, float]:
        minx, miny, maxx, maxy = self.bbox
        return (maxx - minx, maxy - miny)

    @property
    def surface_m2(self) -> float:
        return float(self.geometrie.area)


def _chemin_lecture(chemin: Path) -> str:
    """Chemin à passer à geopandas, en gérant le cas du ZIP."""
    if chemin.suffix.lower() == ".zip":
        with zipfile.ZipFile(chemin) as archive:
            noms = archive.namelist()
        shp = [n for n in noms if n.lower().endswith(".shp")]
        if not shp:
            raise ErreurEmprise(
                f"L'archive {chemin.name} ne contient aucun fichier .shp "
                f"(contenu : {', '.join(noms[:10]) or 'vide'})."
            )
        if len(shp) > 1:
            raise ErreurEmprise(
                f"L'archive {chemin.name} contient plusieurs .shp "
                f"({', '.join(shp)}). Précisez lequel utiliser en n'en laissant qu'un."
            )
        racine = shp[0][:-4]
        if not any(n.lower() == f"{racine.lower()}.prj" for n in noms):
            raise ErreurCRS(
                f"L'archive {chemin.name} ne contient pas de fichier .prj pour "
                f"{shp[0]} : le système de coordonnées est inconnu. Le générateur "
                "refuse de supposer le Lambert 93. Ajoutez le .prj et recommencez."
            )
        return f"zip://{chemin}!{shp[0]}"

    if chemin.is_dir():
        candidats = sorted(chemin.glob("*.shp"))
        if len(candidats) != 1:
            raise ErreurEmprise(
                f"{chemin} contient {len(candidats)} fichiers .shp ; il en faut un seul."
            )
        chemin = candidats[0]

    if chemin.suffix.lower() == ".shp" and not chemin.with_suffix(".prj").exists():
        raise ErreurCRS(
            f"{chemin.name} n'a pas de fichier .prj : le système de coordonnées est "
            "inconnu. Le générateur refuse de supposer le Lambert 93."
        )
    return str(chemin)


def charger_emprise(chemin: str | Path) -> Emprise:
    """Lit un fichier d'emprise et renvoie son union en Lambert 93."""
    chemin = Path(chemin)
    if not chemin.exists():
        raise ErreurEmprise(f"Fichier d'emprise introuvable : {chemin}")
    if (
        chemin.is_file()
        and chemin.suffix.lower() not in _EXTENSIONS_VECTEUR + (".zip",)
    ):
        raise ErreurEmprise(
            f"Format d'emprise non pris en charge : {chemin.suffix}. "
            f"Attendu un shapefile (.shp ou .zip) ou {', '.join(_EXTENSIONS_VECTEUR)}."
        )

    source = _chemin_lecture(chemin)
    try:
        gdf = gpd.read_file(source)
    except ErreurEmprise:
        raise
    except Exception as exc:
        raise ErreurEmprise(f"Lecture impossible de {chemin.name} : {exc}") from exc

    if gdf.empty:
        raise ErreurEmprise(f"{chemin.name} ne contient aucune entité.")

    if gdf.crs is None:
        raise ErreurCRS(
            f"{chemin.name} n'a pas de système de coordonnées déclaré. Le générateur "
            "refuse de supposer le Lambert 93 : fournissez un fichier projeté."
        )

    crs_source = gdf.crs.to_string()
    reprojetee = gdf.crs.to_epsg() != 2154
    if reprojetee:
        gdf = gdf.to_crs(CRS_PROJET)

    geometries = [g for g in gdf.geometry if g is not None and not g.is_empty]
    if not geometries:
        raise ErreurEmprise(f"{chemin.name} ne contient que des géométries vides.")

    union = unary_union(geometries)
    if union.is_empty:
        raise ErreurEmprise(f"L'union des géométries de {chemin.name} est vide.")
    if union.geom_type not in ("Polygon", "MultiPolygon"):
        raise ErreurEmprise(
            f"L'emprise de {chemin.name} est de type {union.geom_type} ; "
            "un polygone est attendu."
        )
    if union.area <= 0:
        raise ErreurEmprise(f"L'emprise de {chemin.name} a une surface nulle.")

    nb = len(union.geoms) if union.geom_type == "MultiPolygon" else 1
    return Emprise(
        geometrie=union,
        crs_source=crs_source,
        reprojetee=reprojetee,
        nb_polygones=nb,
        source=chemin.name,
    )


def polygones(geom: BaseGeometry):
    """Itère les polygones d'une géométrie, simple ou multiple."""
    if geom.geom_type == "Polygon":
        yield geom
    elif geom.geom_type == "MultiPolygon":
        yield from geom.geoms
    else:
        raise ErreurEmprise(f"Type de géométrie inattendu : {geom.geom_type}")
