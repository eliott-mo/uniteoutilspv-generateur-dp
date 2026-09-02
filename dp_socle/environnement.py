"""Préparation de l'environnement de rendu, côté poste de développement.

La cible de déploiement est Streamlit Community Cloud, sous Linux : `libcairo2`
y est fourni par `packages.txt` et ce module n'a rien à faire.

Sous Windows en revanche, CairoSVG ne trouve aucune bibliothèque cairo par
défaut. `DP_CAIRO_DLL_DIR` permet de désigner explicitement le dossier qui
contient `libcairo-2.dll`. À défaut, ce module cherche dans une liste de
dossiers connus — et **dit lequel il a retenu**. Chercher n'est pas se replier :
rien n'est substitué, c'est bien la bibliothèque demandée qui est chargée, et
l'endroit d'où elle vient est rapporté à l'interface.

Historique : jusqu'au 03/09/2026, seule la variable d'environnement était lue.
Lancer `streamlit run app.py` sans l'avoir exportée produisait un dossier
refusé au dernier moment, sur une trace CairoSVG illisible, après le
téléchargement de tous les fonds IGN.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

VARIABLE = "DP_CAIRO_DLL_DIR"

NOM_DLL = "libcairo-2.dll"

#: Dossiers fouillés quand `DP_CAIRO_DLL_DIR` n'est pas renseignée. Ce sont les
#: emplacements des logiciels qui embarquent cairo et qu'on trouve couramment
#: sur un poste de chef de projet. Tesseract vient en tête parce que c'est celui
#: qui est installé sur les postes du parc.
DOSSIERS_CONNUS = (
    r"%LOCALAPPDATA%\Programs\Tesseract-OCR",
    r"%PROGRAMFILES%\Tesseract-OCR",
    r"%PROGRAMFILES%\GTK3-Runtime Win64\bin",
    r"%PROGRAMFILES%\Inkscape\bin",
    r"%PROGRAMFILES%\GIMP 2\bin",
    r"C:\msys64\mingw64\bin",
)

_prepare: Path | None | bool = False


@dataclass
class EtatCairo:
    """Diagnostic de la bibliothèque de rendu, destiné à l'interface."""

    disponible: bool
    dossier: Path | None
    message: str

    def __bool__(self) -> bool:
        return self.disponible


def _candidats() -> list[Path]:
    dossiers = []
    for motif in DOSSIERS_CONNUS:
        chemin = Path(os.path.expandvars(motif))
        # expandvars laisse le motif tel quel si la variable n'existe pas.
        if "%" not in str(chemin):
            dossiers.append(chemin)
    return dossiers


def preparer_cairo() -> Path | None:
    """Rend `libcairo-2.dll` chargeable, sous Windows. Renvoie le dossier retenu.

    N'installe rien et ne masque aucune erreur. Si `DP_CAIRO_DLL_DIR` est
    renseignée mais fausse, on lève : une variable explicitement fournie et
    invalide est une erreur de configuration, pas une invitation à chercher
    ailleurs.
    """
    global _prepare
    if _prepare is not False or not sys.platform.startswith("win"):
        return _prepare if isinstance(_prepare, Path) else None

    dossier = os.environ.get(VARIABLE)
    if dossier:
        chemin = Path(dossier)
        if not chemin.is_dir():
            raise FileNotFoundError(
                f"{VARIABLE} pointe sur un dossier inexistant : {chemin}"
            )
        if not (chemin / NOM_DLL).is_file():
            raise FileNotFoundError(
                f"{VARIABLE} pointe sur {chemin}, qui ne contient pas {NOM_DLL}."
            )
        retenu = chemin
    else:
        retenu = next(
            (d for d in _candidats() if (d / NOM_DLL).is_file()),
            None,
        )
        if retenu is None:
            _prepare = None
            return None

    os.add_dll_directory(str(retenu))
    os.environ["PATH"] = str(retenu) + os.pathsep + os.environ.get("PATH", "")
    _prepare = retenu
    return retenu


def etat_cairo() -> EtatCairo:
    """Vérifie que cairo se charge réellement, et non qu'un fichier existe.

    Le contrôle passe par `cairocffi`, c'est-à-dire par le même chemin que
    CairoSVG au rendu : une DLL présente mais incomplète — dépendances
    manquantes — est ainsi vue ici plutôt qu'à la dernière planche.
    """
    dossier = preparer_cairo()
    try:
        import cairocffi

        cairocffi.ImageSurface(cairocffi.FORMAT_A8, 8, 8).finish()
    except Exception as exc:
        if sys.platform.startswith("win"):
            fouilles = "\n".join(f"    {d}" for d in _candidats())
            conseil = (
                f"Aucun {NOM_DLL} exploitable. Dossiers fouillés :\n{fouilles}\n"
                f"Installez Tesseract-OCR, ou exportez {VARIABLE} vers un dossier "
                f"contenant {NOM_DLL}."
            )
        else:
            conseil = (
                "Installez les bibliothèques système listées dans packages.txt "
                "(libcairo2)."
            )
        return EtatCairo(
            disponible=False,
            dossier=dossier,
            message=(
                f"Bibliothèque cairo indisponible : {exc}. Aucune planche ne "
                f"pourra être produite. {conseil}"
            ),
        )

    origine = f" depuis {dossier}" if dossier else ""
    return EtatCairo(
        disponible=True,
        dossier=dossier,
        message=f"Bibliothèque cairo chargée{origine}.",
    )
