"""DP 1-2 — Photographie aérienne du terrain, au 1:5 000.

Fond : ORTHOIMAGERY.ORTHOPHOTOS (BD ORTHO), demandé au WMS-R à la bbox exacte
de la zone de dessin, en EPSG:2154. Aucune imagerie Google.
"""

from __future__ import annotations

from pathlib import Path

from ..dossier import piece
from ..geometrie import Emprise
from ..ign import COUCHE_ORTHO, DPI_DEFAUT, telecharger_fond
from ..planche import Style, nombre_fr
from ..projet import Projet
from .commun import Sortie, nouvelle_planche

NUMERO = "DP 1-2"
TITRE = piece("DP 1-2").titre
ECHELLE = 5000

#: Sur photo aérienne, l'emprise se lit mieux en contour franc sans aplat.
STYLE_EMPRISE_ORTHO = Style(
    trait="#ff1a1a", epaisseur_mm=0.7, remplissage="none"
)


def generer(
    projet: Projet, emprise: Emprise, dossier: Path, dpi: int = DPI_DEFAUT
) -> Sortie:
    planche = nouvelle_planche(projet, NUMERO, ECHELLE)
    planche.centrer_sur(emprise.centre)

    zone = planche.zone_dessin()
    fond = telecharger_fond(
        COUCHE_ORTHO,
        planche.emprise_terrain(),
        zone[2],
        zone[3],
        dpi=dpi,
        format_image="image/jpeg",
    )
    planche.ajouter_fond_raster(fond.image, fond.bbox)
    planche.ajouter_geometrie(emprise.geometrie, STYLE_EMPRISE_ORTHO)

    hectares = emprise.surface_m2 / 10_000.0
    planche.ajouter_legende(
        [(f"Emprise du projet — {nombre_fr(hectares)} ha", STYLE_EMPRISE_ORTHO)]
    )
    planche.ajouter_texte(
        zone[0] + 3.0,
        zone[1] + zone[3] - 2.5,
        f"Fond : IGN — BD ORTHO (WMS-R Géoplateforme), {fond.dpi} dpi",
        taille=1.9,
        couleur="#ffffff",
        halo=False,
    )

    chemin = planche.rendre_pdf(Path(dossier) / "DP_1-2_photographie_aerienne.pdf")
    return Sortie(
        numero=NUMERO,
        titre=TITRE,
        chemin=chemin,
        echelle=ECHELLE,
        details={"couche": fond.couche, "dpi": fond.dpi, "taille_px": fond.taille_px},
    )
