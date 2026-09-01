"""DP 1-1 — Plan de situation du terrain, au 1:10 000.

Fond : GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2, demandé au WMS-R à la bbox exacte de
la zone de dessin, en EPSG:2154.
"""

from __future__ import annotations

from pathlib import Path

from ..geometrie import Emprise
from ..ign import COUCHE_PLAN, DPI_DEFAUT, telecharger_fond
from ..projet import Projet
from .commun import Sortie, legende_emprise, nouvelle_planche, poser_emprise

NUMERO = "DP 1-1"
TITRE = "PLAN DE SITUATION DU TERRAIN"
ECHELLE = 10000


def generer(
    projet: Projet, emprise: Emprise, dossier: Path, dpi: int = DPI_DEFAUT
) -> Sortie:
    planche = nouvelle_planche(projet, NUMERO, TITRE, ECHELLE)
    planche.centrer_sur(emprise.centre)

    _, _, largeur_mm, hauteur_mm = planche.zone_dessin()
    fond = telecharger_fond(
        COUCHE_PLAN,
        planche.emprise_terrain(),
        largeur_mm,
        hauteur_mm,
        dpi=dpi,
        format_image="image/jpeg",
    )
    planche.ajouter_fond_raster(fond.image, fond.bbox)
    poser_emprise(planche, emprise)
    planche.ajouter_legende(legende_emprise(emprise.surface_m2))
    planche.ajouter_texte(
        planche.zone_dessin()[0] + 3.0,
        planche.zone_dessin()[1] + planche.zone_dessin()[3] - 2.5,
        f"Fond : IGN — Plan IGN v2 (WMS-R Géoplateforme), {fond.dpi} dpi",
        taille=1.9,
        couleur="#333333",
        halo=True,
    )

    chemin = planche.rendre_pdf(Path(dossier) / "DP_1-1_plan_de_situation.pdf")
    return Sortie(
        numero=NUMERO,
        titre=TITRE,
        chemin=chemin,
        echelle=ECHELLE,
        details={"couche": fond.couche, "dpi": fond.dpi, "taille_px": fond.taille_px},
    )
