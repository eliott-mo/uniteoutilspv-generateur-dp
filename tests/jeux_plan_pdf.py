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


def layout_cad(dossier: Path, dxf: Path, fond: Path) -> Path:
    """Le ZIP « Layout CAD » que HelioScope livre, recomposé dans `dossier`."""
    chemin = Path(dossier) / f"{dxf.stem}_layout_cad.zip"
    with zipfile.ZipFile(chemin, "w") as archive:
        archive.write(dxf, dxf.name)
        archive.write(fond, fond.name)
    return chemin


def gannay_present() -> bool:
    return all(p.exists() for p in (PLAN_GANNAY, DXF_GANNAY, FOND_GANNAY))
