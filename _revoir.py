from dp_socle.environnement import preparer_cairo
preparer_cairo()
import sys
SCR = "C:/Users/ELIOTT~1.MOR/AppData/Local/Temp/claude/C--Users-eliott-moreau-OneDrive---Unite-Docs-Eliott-Moreau-0-Claude-Repo-git-unite-generateur-dp/eaad09dd-705b-4ca4-b144-b4ea98fa2388/scratchpad"
sys.path.insert(0, SCR)
import apercu  # noqa
from pathlib import Path
from dp_socle.contrat import charger_contrat
from dp_socle.geometrie import charger_emprise
from dp_socle.planches import dp2_plan_masse, dp4_ouvrages
from dp_socle.projet import Projet

base = Path(SCR) / "reel/Saint-Cyr"
sortie = Path(SCR) / "apercus3"
sortie.mkdir(parents=True, exist_ok=True)
projet = Projet(nom="Saint-Cyr", commune="Saint-Cyr-en-Val", code_postal="45590",
                date="2026-09-04", emprise=str(base / "emprise.geojson"),
                libelle="Saint-Cyr-en-Val")
contrat = charger_contrat(base / "sortie/Saint-Cyr")
s = dp2_plan_masse.generer(projet, contrat, charger_emprise(projet.chemin_emprise), sortie, numero="5")
print("DP 2", s.echelle)
for m in s.details["avertissements"]:
    print("   -", m)
for i, code in enumerate(dp4_ouvrages.planches_necessaires(contrat), start=7):
    s = dp4_ouvrages.generer(projet, contrat, sortie, code, numero=str(i))
    print(code, "ouvrages", s.details["echelle_ouvrages"], "repérage", s.details["echelle_reperage"])
