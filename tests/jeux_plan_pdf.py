"""Jeux d'essai du lot 2ter : un plan PDF et le DXF HelioScope qu'il couvre.

Le lot 2 lit un export HelioScope en ZIP — le « Layout CAD », qui porte le DXF
du calepinage et son image de fond. Les jeux d'essai sont versionnés en
fichiers séparés, tels qu'ils ont été reçus ; le ZIP se recompose ici, à
l'identique de ce que HelioScope livre.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

EXEMPLES = Path(__file__).resolve().parent.parent / "exemples"

#: Gannay-sur-Loire (03), septembre 2026 : le cas qui a fait le lot. Le plan
#: du 21/09 porte la clôture ; celui du 28/08 ne l'a pas encore en légende.
GANNAY = EXEMPLES / "gannay-PDF"
PLAN_GANNAY = GANNAY / "Annexe5_CasXCas_PlanProjet_2026-09-21.pdf"
PLAN_GANNAY_SANS_CLOTURE = GANNAY / "Annexe5_CasXCas_PlanProjet_2026-08-28.pdf"
DXF_GANNAY = GANNAY / "helioscope_design_10465241.dxf"
FOND_GANNAY = GANNAY / "design_10465241_baseimage.jpg"

#: Calage de l'export de Gannay, validé sur l'ortho IGN : le fond HelioScope y
#: a été corrélé dans le dépôt `photomontage` le 21/09/2026 (`ancrage.json`,
#: dE = 745 855,87, dN = 6 625 785,12), puis traduit le 23/09/2026 dans les
#: deux réglages du lot 2. La correction nord-sud valait −6,26 m, dont −5,22 m
#: venaient du centre de l'image de fond, que le calage compte lui-même depuis
#: le même jour : il en reste −1,04 m, pour le même placement. Le projet n'a
#: pas d'emprise cadastrale au dépôt.
LONGITUDE_GANNAY = 3.600487654
NORD_SUD_GANNAY_M = -1.04

#: Bray-Saint-Aignan (45) : un second plan, tiré du même modèle PowerPoint mais
#: exporté autrement — ses traits y sont des contours remplis — et aux couleurs
#: toutes différentes de celles de Gannay.
BRAY = EXEMPLES / "bray-saint-aignan-PDF"
PLAN_BRAY = BRAY / "Plan implantation_Bray-Saint-Aignan.pdf"
DXF_BRAY = BRAY / "helioscope_design_10482797.dxf"
FOND_BRAY = BRAY / "design_10482797_baseimage.jpg"
#: L'emprise réelle du projet, celle du lot 1 : 27,99 ha.
EMPRISE_BRAY = BRAY / "emprise_reelle.zip"
#: L'emprise cadastrale du site seul, 5,08 ha — les « 5,1 ha » du tableau du
#: plan —, tirée le 23/09/2026 de l'emprise « geoperso-3 » dont les trois
#: autres morceaux étaient à plusieurs kilomètres.
EMPRISE_SITE_BRAY = BRAY / "alr_45_bray-saint-aignan-geoperso-3-23_09_2026_13_39.zip"

#: Calage de l'export de Bray, mesuré le 23/09/2026 en corrélant son fond
#: HelioScope avec l'ortho IGN, une fois le centre de l'image compté (pic de
#: corrélation 0,34 contre 0,10 pour le second) : 22,34 m à l'est du
#: pré-positionnement sur `EMPRISE_SITE_BRAY`, 0,66 m au sud de la latitude
#: du fichier.
LONGITUDE_BRAY = 2.347192657
NORD_SUD_BRAY_M = -0.66


def layout_cad(dossier: Path, dxf: Path, fond: Path) -> Path:
    """Le ZIP « Layout CAD » que HelioScope livre, recomposé dans `dossier`."""
    chemin = Path(dossier) / f"{dxf.stem}_layout_cad.zip"
    with zipfile.ZipFile(chemin, "w") as archive:
        archive.write(dxf, dxf.name)
        archive.write(fond, fond.name)
    return chemin


def gannay_present() -> bool:
    return all(p.exists() for p in (PLAN_GANNAY, DXF_GANNAY, FOND_GANNAY))


def bray_present() -> bool:
    return all(p.exists() for p in (PLAN_BRAY, DXF_BRAY, FOND_BRAY, EMPRISE_BRAY))
