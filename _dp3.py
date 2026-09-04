from dp_socle.environnement import preparer_cairo
preparer_cairo()
import sys
SCR = "C:/Users/ELIOTT~1.MOR/AppData/Local/Temp/claude/C--Users-eliott-moreau-OneDrive---Unite-Docs-Eliott-Moreau-0-Claude-Repo-git-unite-generateur-dp/eaad09dd-705b-4ca4-b144-b4ea98fa2388/scratchpad"
sys.path.insert(0, SCR)
import apercu  # noqa
from pathlib import Path
from dp_socle.contrat import charger_contrat
from dp_socle.planches import dp3_coupes
from dp_socle.projet import Projet
base = Path(SCR) / "reel/Saint-Cyr"
sortie = Path(SCR) / "apercus3"
projet = Projet(nom="Saint-Cyr", commune="Saint-Cyr-en-Val", code_postal="45590",
                date="2026-09-04", emprise=str(base / "emprise.geojson"),
                libelle="Saint-Cyr-en-Val")
s = dp3_coupes.generer(projet, charger_contrat(base / "sortie/Saint-Cyr"), sortie, numero="6")
print("tables", s.details["echelle_tables"], "terrain", s.details["echelle_terrain"])
