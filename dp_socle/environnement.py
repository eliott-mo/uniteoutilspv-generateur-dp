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


# ---------------------------------------------------------------------------
# Où l'outil écrit ses fichiers de travail
# ---------------------------------------------------------------------------

VARIABLE_TRAVAIL = "DP_DOSSIER_TRAVAIL"

#: Noms des deux dossiers que l'outil écrit : les fichiers déposés par pièce, et
#: les dossiers assemblés.
NOMS_TRAVAIL = ("projets", "sortie")


@dataclass(frozen=True)
class EtatTravail:
    """Où les fichiers de travail sont écrits, et ce qu'il faut en penser."""

    projets: Path
    sortie: Path
    #: Vrai si ces dossiers sont sous un dossier synchronisé par OneDrive.
    synchronise: bool
    message: str


def _racine_travail() -> Path:
    """Le dossier qui contient `projets/` et `sortie/`.

    `DP_DOSSIER_TRAVAIL` le déplace ; à défaut, ils restent où ils ont toujours
    été, à côté du script. La cible de déploiement n'a donc rien à changer, et
    un poste Windows peut les sortir d'un dossier synchronisé.
    """
    demande = os.environ.get(VARIABLE_TRAVAIL, "").strip()
    return Path(demande).expanduser() if demande else Path()


def dossiers_de_travail() -> tuple[Path, Path]:
    """Les chemins de `projets/` et `sortie/`, dans cet ordre."""
    racine = _racine_travail()
    return tuple(racine / nom for nom in NOMS_TRAVAIL)


def _sous_onedrive(chemin: Path) -> bool:
    """Vrai si ce chemin tombe dans un dossier synchronisé par OneDrive.

    Les variables `OneDrive` et `OneDriveCommercial` sont posées par le client
    Windows lui-même : les lire vaut mieux que de chercher « OneDrive » dans le
    chemin, qui se tromperait sur un dossier simplement nommé ainsi.
    """
    try:
        absolu = chemin.resolve()
    except OSError:
        return False
    for variable in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        racine = os.environ.get(variable, "").strip()
        if not racine:
            continue
        try:
            absolu.relative_to(Path(racine).resolve())
        except (ValueError, OSError):
            continue
        return True
    return False


def etat_travail() -> EtatTravail:
    """Où l'outil écrit, et l'avertissement s'il écrit dans un dossier synchronisé.

    Signalé en usage réel le 16/09/2026 : un `PermissionError` sur un DXF que
    OneDrive tenait ouvert pendant qu'il le téléversait. L'outil ne réécrit plus
    un fichier inchangé, ce qui referme l'essentiel de la fenêtre — mais un
    dossier de travail synchronisé reste une mauvaise idée. Ces fichiers sont
    volumineux, régénérables, et réécrits à chaque génération : les synchroniser
    coûte de la bande passante pour rien et rouvre le risque à chaque écriture.

    Dit au démarrage, comme l'état de cairo : ce qui gêne doit se savoir avant
    de travailler, pas au milieu d'une génération.
    """
    projets, sortie = dossiers_de_travail()
    if not any(_sous_onedrive(chemin) for chemin in (projets, sortie)):
        return EtatTravail(projets, sortie, False, f"Fichiers de travail : {projets.resolve()}")
    return EtatTravail(
        projets,
        sortie,
        True,
        "Les dossiers « projets » et « sortie » sont dans un dossier synchronisé "
        "par OneDrive. Ils contiennent des fichiers volumineux, régénérables et "
        "réécrits à chaque génération : la synchronisation les téléverse pour "
        "rien, et peut bloquer une écriture en cours. Déplacez-les en posant "
        f"{VARIABLE_TRAVAIL} vers un dossier local, par exemple "
        r"« %LOCALAPPDATA%\UNITe\generateur-dp ».",
    )

#: Racine du dépôt, d'où se lisent la date de déploiement et le commit.
_RACINE = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class VersionDeployee:
    """Ce que l'outil en ligne porte, et depuis quand."""

    date: str
    commit: str | None

    @property
    def message(self) -> str:
        return f"Version du {self.date}" + (f" ({self.commit})" if self.commit else "")


def _commit_du_depot() -> str | None:
    """Les sept premiers caractères du commit déployé, ou None.

    Lu dans `.git` à la main plutôt que par un appel à `git` : la commande
    n'est pas garantie présente dans le conteneur de déploiement, et une
    version qui ne s'affiche pas vaut mieux qu'un sous-processus qui échoue.
    """
    git = _RACINE / ".git"
    try:
        tete = (git / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not tete.startswith("ref:"):
        return tete[:7] or None
    reference = tete.partition("ref:")[2].strip()
    try:
        return (git / reference).read_text(encoding="utf-8").strip()[:7] or None
    except OSError:
        pass
    # Un dépôt fraîchement cloné range ses références dans un seul fichier.
    try:
        lignes = (git / "packed-refs").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for ligne in lignes:
        if ligne.endswith(" " + reference):
            return ligne.split(" ", 1)[0][:7] or None
    return None


def version_deployee() -> VersionDeployee:
    """Date du code en ligne, et le commit s'il se lit.

    Trois chefs de projet en deux jours ont conclu à un défaut de l'outil alors
    qu'ils tenaient une version antérieure — un onglet resté ouvert, ou un
    redéploiement qui n'avait pas pris. Chaque fois, le diagnostic a coûté des
    heures et un aller-retour. La date se lit donc à l'écran.

    Elle est celle du fichier source le plus récent : la cible de déploiement
    recopie le dépôt à chaque mise en ligne, et c'est exactement la date qu'on
    cherche. Prendre celle du commit dirait quand le code a été écrit, pas
    quand il a été déployé — et c'est la seconde que le chef de projet doit
    pouvoir confronter à l'heure de son test.
    """
    from datetime import datetime

    sources = list((_RACINE / "dp_socle").rglob("*.py")) + [_RACINE / "app.py"]
    horodatages = []
    for chemin in sources:
        try:
            horodatages.append(chemin.stat().st_mtime)
        except OSError:
            continue
    quand = datetime.fromtimestamp(max(horodatages)) if horodatages else None
    return VersionDeployee(
        date=quand.strftime("%d/%m/%Y à %H:%M") if quand else "inconnue",
        commit=_commit_du_depot(),
    )
