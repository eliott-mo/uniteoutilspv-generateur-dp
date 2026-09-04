"""Rend une page d'un PDF de référence HOCH en PNG, pour la consulter."""
import sys
from pathlib import Path
import fitz

SCR = Path("C:/Users/ELIOTT~1.MOR/AppData/Local/Temp/claude/C--Users-eliott-moreau-OneDrive---Unite-Docs-Eliott-Moreau-0-Claude-Repo-git-unite-generateur-dp/eaad09dd-705b-4ca4-b144-b4ea98fa2388/scratchpad/hoch")
SCR.mkdir(parents=True, exist_ok=True)
chemin, pages, dpi = sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 130
doc = fitz.open(chemin)
for numero in pages.split(","):
    page = doc[int(numero) - 1]
    pix = page.get_pixmap(dpi=dpi)
    nom = SCR / f"{Path(chemin).stem[:14].replace(' ','_')}_p{numero}.png"
    pix.save(nom)
    print(nom)
