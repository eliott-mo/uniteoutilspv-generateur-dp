"""Éléments partagés par les planches cartographiques du socle."""

from __future__ import annotations

from dataclasses import dataclass

from ..dossier import numero_planche as _numero
from ..dossier import piece as _piece
from ..geometrie import Emprise
from ..planche import STYLE_EMPRISE, EntreeLegende, Planche, nombre_fr
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
    projet: Projet,
    code: str,
    echelle: int | None = None,
    numero: str | None = None,
) -> Planche:
    """Planche d'une pièce du dossier, titrée et repérée depuis `dp_socle.dossier`.

    Le titre du cartouche porte le code de la pièce (« DP 1-3 : PLAN DE
    CADASTRE ») ; la case NUMÉRO porte le rang de la planche dans le dossier
    assemblé, page de garde comprise (« 4 »).

    `numero` permet de passer un rang calculé sur les pièces réellement
    produites : depuis le lot 4, les planches d'ouvrages n'existent que si le
    projet porte les ouvrages correspondants, et le rang ne se déduit plus de
    la seule liste des pièces.
    """
    piece = _piece(code)
    return Planche(
        titre=piece.intitule_cartouche,
        numero=str(numero if numero is not None else _numero(code)),
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
            f"Emprise du projet — {nombre_fr(hectares)} ha",
            STYLE_EMPRISE,
        )
    ]
