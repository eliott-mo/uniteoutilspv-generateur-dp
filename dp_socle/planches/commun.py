"""Éléments partagés par les planches cartographiques du socle."""

from __future__ import annotations

from dataclasses import dataclass

from ..geometrie import Emprise
from ..planche import STYLE_EMPRISE, EntreeLegende, Planche
from ..projet import Projet


@dataclass
class Sortie:
    """Résultat de la génération d'une planche."""

    numero: str
    titre: str
    chemin: object
    echelle: int | None = None
    details: dict | None = None


def nouvelle_planche(
    projet: Projet, numero: str, titre: str, echelle: int | None = None
) -> Planche:
    return Planche(
        titre=titre,
        numero=numero,
        projet=projet.libelle_affiche,
        date=projet.date_francaise(),
        echelle=echelle,
    )


def poser_emprise(planche: Planche, emprise: Emprise) -> None:
    """Trace l'emprise du projet, union de tous les polygones du shapefile."""
    planche.ajouter_geometrie(emprise.geometrie, STYLE_EMPRISE)


def legende_emprise(surface_m2: float) -> list[EntreeLegende]:
    hectares = surface_m2 / 10_000.0
    return [
        EntreeLegende(
            f"Emprise du projet ({hectares:.2f} ha)",
            STYLE_EMPRISE,
        )
    ]
