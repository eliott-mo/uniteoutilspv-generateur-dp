"""Préparation de l'environnement de rendu, côté poste de développement.

La cible de déploiement est Streamlit Community Cloud, sous Linux : `libcairo2`
y est fourni par `packages.txt` et ce module n'a rien à faire.

Sous Windows en revanche, CairoSVG ne trouve aucune bibliothèque cairo par
défaut. Il faut lui indiquer un dossier contenant `libcairo-2.dll` et ses
dépendances, via la variable d'environnement `DP_CAIRO_DLL_DIR`. Voir le README.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

VARIABLE = "DP_CAIRO_DLL_DIR"

_prepare = False


def preparer_cairo() -> Path | None:
    """Ajoute le dossier de DLL cairo au chemin de recherche, sous Windows.

    Renvoie le dossier utilisé, ou None si rien n'était à faire. N'installe rien
    et ne masque aucune erreur : si cairo reste introuvable, l'échec survient au
    rendu, avec un message explicite (voir `Planche.rendre_pdf`).
    """
    global _prepare
    if _prepare or not sys.platform.startswith("win"):
        return None

    dossier = os.environ.get(VARIABLE)
    if not dossier:
        return None
    chemin = Path(dossier)
    if not chemin.is_dir():
        raise FileNotFoundError(
            f"{VARIABLE} pointe sur un dossier inexistant : {chemin}"
        )

    os.add_dll_directory(str(chemin))
    os.environ["PATH"] = str(chemin) + os.pathsep + os.environ.get("PATH", "")
    _prepare = True
    return chemin
