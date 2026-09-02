"""Disponibilité et métriques de la police de composition (Aptos).

## Ce que fait réellement CairoSVG

Vérifié dans son code source : le rendu de texte appelle
`cairo_select_font_face`, l'API « toy » de cairo, et il ne retient que **la
première** famille de l'attribut `font-family` (`.split(',')[0]`). Une chaîne de
repli CSS écrite dans le SVG n'a donc aucun effet : c'est cairo qui substitue,
en silence, ce qu'il veut. CairoSVG n'implémente pas non plus `@font-face`,
donc référencer le chemin du TTF dans le SVG ne sert à rien.

Conséquence : ce module choisit lui-même la famille à écrire dans le SVG, parmi
celles que cairo résout vraiment, et le dit. Le repli est décidé et nommé, pas
subi.

## Comment cairo trouve les polices, selon la plateforme

- **Linux** (cible de déploiement, Streamlit Community Cloud) : FreeType et
  fontconfig. Copier le TTF dans `~/.local/share/fonts` puis rafraîchir le cache
  suffit — c'est ce que fait `installer_polices()`.
- **Windows** : cairo 1.18 passe par DirectWrite, qui ne voit **que** les
  polices installées pour l'utilisateur ou la machine. Ni `AddFontResourceEx`
  (polices privées GDI), ni `FcConfigAppFontAddFile`, ni `FONTCONFIG_FILE` ne
  l'atteignent — les trois ont été essayés et mesurés. Sur un poste de
  développement Windows, il faut donc **installer Aptos** (clic droit sur le
  TTF, « Installer »). Voir le README.

## Vérification

`etat_polices()` ne se contente pas de constater la présence du fichier : il
compare la chasse mesurée par cairo à celle calculée depuis le TTF embarqué. Un
écart signifie que cairo compose avec une autre police, et l'avertissement dit
laquelle sera réellement utilisée.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import warnings
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .erreurs import ErreurPolice

#: Famille attendue pour le corps de texte et le cartouche.
POLICE_PRINCIPALE = "Aptos"

#: Replis, dans l'ordre de préférence. Le premier que cairo résout vraiment est
#: retenu, et son emploi est signalé.
POLICES_REPLI = ("Carlito", "Calibri", "DejaVu Sans", "Liberation Sans")

DOSSIER_POLICES = Path(__file__).parent / "ressources" / "polices"

#: Texte témoin des mesures de contrôle.
_TEMOIN = "Hamburgefonstiv 0123456789"
_TAILLE_TEMOIN = 64.0

#: Écart relatif de chasse admis entre cairo et le TTF embarqué.
_TOLERANCE = 1e-4


@dataclass
class EtatPolices:
    """Diagnostic à afficher au démarrage de l'application."""

    disponible: bool
    famille_utilisee: str
    fichiers_embarques: list = field(default_factory=list)
    message: str = ""

    def __bool__(self) -> bool:
        return self.disponible


def fichiers_embarques() -> list:
    if not DOSSIER_POLICES.is_dir():
        return []
    return sorted(
        p for p in DOSSIER_POLICES.iterdir() if p.suffix.lower() in (".ttf", ".otf")
    )


def fichier_principal() -> Path | None:
    """Le TTF embarqué dont le nom de famille est `POLICE_PRINCIPALE`."""
    for fichier in fichiers_embarques():
        if _famille_du_fichier(fichier) == POLICE_PRINCIPALE:
            return fichier
    return None


@lru_cache(maxsize=None)
def _famille_du_fichier(fichier: Path) -> str | None:
    from fontTools.ttLib import TTFont

    try:
        with TTFont(str(fichier), lazy=True) as police:
            for enregistrement in police["name"].names:
                if enregistrement.nameID == 1:
                    return enregistrement.toUnicode()
    except Exception:
        return None
    return None


def installer_polices() -> list:
    """Fait connaître les TTF embarqués au système de polices du poste.

    Ne lève pas : le succès est constaté par `etat_polices()`, qui mesure.
    """
    fichiers = fichiers_embarques()
    if not fichiers:
        return []
    if sys.platform.startswith("win"):
        _installer_windows(fichiers)
    else:
        _installer_fontconfig(fichiers)
    return fichiers


def _installer_windows(fichiers: list) -> None:
    """Ajout aux polices privées du processus.

    Sans effet sur cairo 1.18, qui passe par DirectWrite ; conservé parce que
    c'est sans risque et que d'autres constructions de cairo utilisent GDI.
    """
    import ctypes

    FR_PRIVATE = 0x10
    gdi = ctypes.WinDLL("gdi32")
    gdi.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32,
                                       ctypes.c_void_p]
    for fichier in fichiers:
        try:
            gdi.AddFontResourceExW(str(fichier), FR_PRIVATE, None)
        except OSError:
            pass


def _installer_fontconfig(fichiers: list) -> None:
    cible = Path.home() / ".local" / "share" / "fonts"
    try:
        cible.mkdir(parents=True, exist_ok=True)
        for fichier in fichiers:
            destination = cible / fichier.name
            if (
                not destination.exists()
                or destination.stat().st_size != fichier.stat().st_size
            ):
                shutil.copy2(fichier, destination)
    except OSError:
        return
    fc_cache = shutil.which("fc-cache")
    if fc_cache:
        try:
            subprocess.run(
                [fc_cache, "-f", str(cible)], check=False, capture_output=True,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            pass


# -- mesures ----------------------------------------------------------------


def chasse_cairo(texte: str, famille: str, taille: float, gras: bool = False) -> float:
    """Chasse (avance horizontale) d'un texte, telle que cairo la composera.

    Même moteur et même API que CairoSVG au rendu : la mesure est donc exacte,
    quelle que soit la police que cairo aura finalement retenue. C'est cette
    fonction qui permet de justifier les blocs de texte.
    """
    import cairocffi

    surface = cairocffi.ImageSurface(cairocffi.FORMAT_A8, 8, 8)
    contexte = cairocffi.Context(surface)
    contexte.select_font_face(
        famille,
        cairocffi.FONT_SLANT_NORMAL,
        cairocffi.FONT_WEIGHT_BOLD if gras else cairocffi.FONT_WEIGHT_NORMAL,
    )
    contexte.set_font_size(taille)
    avance = contexte.text_extents(texte)[4]
    surface.finish()
    return float(avance)


def _chasse_ttf(fichier: Path, texte: str, taille: float) -> float | None:
    """Chasse attendue, calculée depuis le fichier TTF embarqué."""
    from fontTools.ttLib import TTFont

    try:
        with TTFont(str(fichier), lazy=True) as police:
            unites = police["head"].unitsPerEm
            table = police.getBestCmap()
            metriques = police["hmtx"]
            total = 0
            for caractere in texte:
                nom = table.get(ord(caractere))
                if nom is None:
                    return None
                total += metriques[nom][0]
    except Exception:
        return None
    return total / unites * taille


@lru_cache(maxsize=None)
def _famille_disponible(famille: str) -> bool:
    """Vrai si cairo résout `famille` autrement que par sa substitution par défaut."""
    try:
        reference = chasse_cairo(_TEMOIN, "ZzPoliceQuiNExistePas42", _TAILLE_TEMOIN)
        return abs(chasse_cairo(_TEMOIN, famille, _TAILLE_TEMOIN) - reference) > 1e-6
    except Exception:
        return False


@lru_cache(maxsize=None)
def _controle_principale() -> tuple:
    """(résolue, chasse cairo, chasse attendue) pour la police principale."""
    fichier = fichier_principal()
    if fichier is None:
        return (False, None, None)
    attendue = _chasse_ttf(fichier, _TEMOIN, _TAILLE_TEMOIN)
    try:
        mesuree = chasse_cairo(_TEMOIN, POLICE_PRINCIPALE, _TAILLE_TEMOIN)
    except Exception:
        return (False, None, attendue)
    if attendue is None:
        return (_famille_disponible(POLICE_PRINCIPALE), mesuree, None)
    ecart = abs(mesuree - attendue) / attendue
    return (ecart <= _TOLERANCE, mesuree, attendue)


@lru_cache(maxsize=None)
def famille_active() -> str:
    """Famille effectivement écrite dans les SVG.

    CairoSVG ne lit que la première famille de `font-family` : on y met donc
    celle que cairo résout réellement, pour que la substitution soit choisie et
    nommée plutôt que subie.
    """
    if _controle_principale()[0]:
        return POLICE_PRINCIPALE
    for repli in POLICES_REPLI:
        if _famille_disponible(repli):
            return repli
    return POLICE_PRINCIPALE


@lru_cache(maxsize=None)
def etat_polices(installer: bool = True) -> EtatPolices:
    """Diagnostic complet, destiné à être affiché dans l'interface."""
    fichiers = installer_polices() if installer else fichiers_embarques()
    noms = [f.name for f in fichiers]
    resolue, mesuree, attendue = _controle_principale()
    famille = famille_active()

    if resolue:
        return EtatPolices(
            disponible=True,
            famille_utilisee=famille,
            fichiers_embarques=noms,
            message=(
                f"Police « {POLICE_PRINCIPALE} » disponible et vérifiée "
                f"({', '.join(noms)}) : chasse mesurée {mesuree:.3f} pour "
                f"{attendue:.3f} attendus." if attendue
                else f"Police « {POLICE_PRINCIPALE} » disponible ({', '.join(noms)})."
            ),
        )

    if not fichiers:
        cause = (
            f"aucun fichier TTF dans {DOSSIER_POLICES}"
        )
    elif fichier_principal() is None:
        cause = (
            f"aucun des fichiers embarqués ({', '.join(noms)}) ne déclare la "
            f"famille « {POLICE_PRINCIPALE} »"
        )
    elif mesuree is not None and attendue is not None:
        cause = (
            f"cairo compose une autre police (chasse mesurée {mesuree:.3f} au lieu "
            f"de {attendue:.3f})"
        )
    else:
        cause = "cairo n'a pas pu mesurer la police"

    conseil = (
        "Sous Windows, cairo passe par DirectWrite : installez Aptos sur le poste "
        "(clic droit sur le TTF, « Installer »)."
        if sys.platform.startswith("win")
        else "Vérifiez que fontconfig voit ~/.local/share/fonts (paquet fontconfig)."
    )
    return EtatPolices(
        disponible=False,
        famille_utilisee=famille,
        fichiers_embarques=noms,
        message=(
            f"Police « {POLICE_PRINCIPALE} » non utilisée : {cause}. Les planches "
            f"seront composées en « {famille} », dont les métriques diffèrent : la "
            f"mise en page du cartouche sera décalée. {conseil}"
        ),
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
