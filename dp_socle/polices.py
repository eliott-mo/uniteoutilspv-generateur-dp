"""Disponibilité de la police de composition (Aptos) pour le moteur cairo.

Contrainte du lot : Aptos est une police Microsoft, absente des environnements
Linux et donc de Streamlit Community Cloud. Le fichier TTF est embarqué dans le
dépôt, sous `dp_socle/ressources/polices/`.

Point important, vérifié dans le code de CairoSVG : le rendu de texte passe par
`cairo_select_font_face`, l'API « toy » de cairo. Elle résout les polices par
**nom de famille auprès du système** (fontconfig sous Linux, GDI sous Windows).
CairoSVG n'implémente pas `@font-face`, donc référencer le chemin du TTF dans le
SVG ne sert à rien : il faut faire connaître le fichier au système de polices
avant le rendu. C'est ce que fait `installer_polices()`.

Comme une substitution silencieuse produirait des planches décalées sans que
personne ne le voie, `etat_polices()` vérifie réellement que cairo résout la
famille demandée, en comparant les métriques obtenues avec celles d'une famille
volontairement inexistante.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from .erreurs import ErreurPolice

#: Famille attendue pour le corps de texte et le cartouche.
POLICE_PRINCIPALE = "Aptos"

#: Chaîne de repli **déclarée** : elle figure telle quelle dans les attributs
#: font-family du SVG, de sorte que le repli soit lisible dans le fichier.
POLICES_REPLI = ("Carlito", "Calibri", "DejaVu Sans", "sans-serif")

#: Valeur de l'attribut font-family écrit dans le SVG.
FAMILLE_SVG = ", ".join((POLICE_PRINCIPALE,) + POLICES_REPLI)

DOSSIER_POLICES = Path(__file__).parent / "ressources" / "polices"

_FAMILLE_INEXISTANTE = "ZzPoliceQuiNExistePas42"


@dataclass
class EtatPolices:
    """Diagnostic à afficher au démarrage de l'application."""

    disponible: bool
    fichiers_embarques: list[str] = field(default_factory=list)
    message: str = ""

    def __bool__(self) -> bool:
        return self.disponible


def fichiers_embarques() -> list[Path]:
    if not DOSSIER_POLICES.is_dir():
        return []
    return sorted(
        p for p in DOSSIER_POLICES.iterdir() if p.suffix.lower() in (".ttf", ".otf")
    )


def installer_polices() -> list[Path]:
    """Fait connaître les TTF embarqués au système de polices du poste.

    Retourne la liste des fichiers pris en charge. Ne lève pas : l'échec est
    constaté par `etat_polices()`, qui est la source de vérité.
    """
    fichiers = fichiers_embarques()
    if not fichiers:
        return []

    if sys.platform.startswith("win"):
        _installer_windows(fichiers)
    else:
        _installer_fontconfig(fichiers)
    return fichiers


def _installer_windows(fichiers: list[Path]) -> None:
    import ctypes

    FR_PRIVATE = 0x10
    for fichier in fichiers:
        try:
            ctypes.windll.gdi32.AddFontResourceExW(str(fichier), FR_PRIVATE, 0)
        except OSError:
            pass


def _installer_fontconfig(fichiers: list[Path]) -> None:
    cible = Path.home() / ".local" / "share" / "fonts"
    try:
        cible.mkdir(parents=True, exist_ok=True)
        for fichier in fichiers:
            destination = cible / fichier.name
            if not destination.exists() or destination.stat().st_size != fichier.stat().st_size:
                shutil.copy2(fichier, destination)
    except OSError:
        return
    fc_cache = shutil.which("fc-cache")
    if fc_cache:
        try:
            subprocess.run(
                [fc_cache, "-f", str(cible)],
                check=False,
                capture_output=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            pass


def _metriques(famille: str):
    """Métriques cairo d'un texte témoin dans une famille donnée."""
    import cairocffi

    surface = cairocffi.ImageSurface(cairocffi.FORMAT_A8, 8, 8)
    contexte = cairocffi.Context(surface)
    contexte.select_font_face(famille)
    contexte.set_font_size(64.0)
    extents = contexte.text_extents("Hamburgefonstiv 0123456789")
    police = contexte.font_extents()
    surface.finish()
    return tuple(round(v, 4) for v in tuple(extents) + tuple(police))


def police_resolue(famille: str = POLICE_PRINCIPALE) -> bool:
    """Vrai si cairo rend réellement `famille`, et non une police de substitution."""
    try:
        return _metriques(famille) != _metriques(_FAMILLE_INEXISTANTE)
    except Exception:  # cairo indisponible : traité ailleurs, au rendu
        return False


def etat_polices(installer: bool = True) -> EtatPolices:
    """Diagnostic complet, destiné à être affiché dans l'interface."""
    fichiers = installer_polices() if installer else fichiers_embarques()
    noms = [f.name for f in fichiers]

    if not fichiers:
        return EtatPolices(
            disponible=False,
            fichiers_embarques=noms,
            message=(
                f"Police « {POLICE_PRINCIPALE} » absente : aucun fichier TTF dans "
                f"{DOSSIER_POLICES}. Les planches seront composées avec un repli "
                f"({', '.join(POLICES_REPLI)}), dont les métriques diffèrent : "
                "la mise en page du cartouche sera décalée. Déposez Aptos.ttf "
                "dans ce dossier avant de produire un dossier destiné au dépôt."
            ),
        )

    if not police_resolue(POLICE_PRINCIPALE):
        return EtatPolices(
            disponible=False,
            fichiers_embarques=noms,
            message=(
                f"Police « {POLICE_PRINCIPALE} » embarquée ({', '.join(noms)}) mais "
                "non résolue par cairo : le moteur de rendu ne la trouve pas dans le "
                "système de polices. Les planches seront composées avec un repli et "
                "la mise en page sera décalée."
            ),
        )

    return EtatPolices(
        disponible=True,
        fichiers_embarques=noms,
        message=f"Police « {POLICE_PRINCIPALE} » disponible ({', '.join(noms)}).",
    )


def exiger_police(etat: EtatPolices | None = None) -> EtatPolices:
    """Variante bloquante, pour une production destinée au dépôt du dossier."""
    etat = etat or etat_polices()
    if not etat.disponible:
        raise ErreurPolice(etat.message)
    return etat


def avertir_si_indisponible(etat: EtatPolices | None = None) -> EtatPolices:
    """Émet un avertissement visible plutôt qu'un repli muet."""
    etat = etat or etat_polices()
    if not etat.disponible:
        warnings.warn(etat.message, RuntimeWarning, stacklevel=2)
        print(f"AVERTISSEMENT : {etat.message}", file=sys.stderr)
    return etat
