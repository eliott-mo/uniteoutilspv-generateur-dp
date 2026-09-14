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
    #: Numéros que les cartouches de la pièce annoncent réellement, dans
    #: l'ordre de ses pages.
    #:
    #: Vide pour les pièces d'une seule page : `dp_socle.assemblage` recalcule
    #: alors leur rang par `dossier.numero_planche`, comme au lot 4. Une pièce
    #: qui couvre plusieurs pages — la notice DP 11 — les déclare ici, et
    #: l'assemblage vérifie qu'elles suivent la pagination du dossier au lieu
    #: de comparer un numéro unique.
    numeros: tuple = ()


def nouvelle_planche(
    projet: Projet,
    code: str,
    echelle: int | None = None,
    numero: str | None = None,
    reperes_cartographiques: bool = True,
) -> Planche:
    """Planche d'une pièce du dossier, titrée et repérée depuis `dp_socle.dossier`.

    Le titre du cartouche porte le code de la pièce (« DP 1-3 : PLAN DE
    CADASTRE ») ; la case NUMÉRO porte le rang de la planche dans le dossier
    assemblé, page de garde comprise (« 4 »).

    `numero` permet de passer un rang calculé sur les pièces réellement
    produites : depuis le lot 4, les planches d'ouvrages n'existent que si le
    projet porte les ouvrages correspondants, et le rang ne se déduit plus de
    la seule liste des pièces.

    `reperes_cartographiques` à faux retire la flèche nord et la case ÉCHELLE
    du cartouche : une planche qui ne montre pas de terrain n'a ni l'une ni
    l'autre (lot 5, notice DP 11).
    """
    piece = _piece(code)
    return Planche(
        titre=piece.intitule_cartouche,
        numero=str(numero if numero is not None else _numero(code)),
        projet=projet.libelle_affiche,
        date=projet.date_francaise(),
        echelle=echelle,
        reperes_cartographiques=reperes_cartographiques,
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
