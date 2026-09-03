"""Lecture du tableau bilan Excel du bureau d'études (lot 2bis, étape B).

L'onglet « 2. Caractéristiques du projet » est organisé en colonnes, une par
indice de révision : le libellé en colonne A, puis `IND05` en B, `IND06` en C…

Deux pièges, tous deux capables de produire des valeurs fausses sans lever la
moindre erreur :

- **repérer les paramètres par leur libellé, jamais par leur numéro de ligne.**
  Le fichier est déjà en version 6 et la mise en page bouge d'une version à
  l'autre ;
- **les valeurs sont typées de façon irrégulière** : `0°` avec le symbole
  degré, `13 / 26` pour deux longueurs de table, des dates en `datetime`. Les
  convertisseurs sont tolérants sur la forme et **échouent explicitement** quand
  le motif ne correspond pas, plutôt que de rendre une valeur par défaut.

Mesuré sur `20260825_SCV_Tableau_Bilan_V6.xlsx` le 03/09/2026.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from .erreurs import ErreurTableauBilan
from .import_be import normaliser

ONGLET_CARACTERISTIQUES = "2. Caractéristiques du projet"
ONGLET_DIMENSIONS = "Dimensions postes et pieux"
ONGLET_STANDARDS = "Standards UNITe"

#: Motif de l'indice de révision, tel qu'il apparaît en en-tête de colonne et
#: dans le nom du fichier DXF (`20260903_SCV_IND06.dxf`).
MOTIF_INDICE = re.compile(r"IND\s*0*(\d+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Convertisseurs
# ---------------------------------------------------------------------------


def _texte(valeur, libelle: str) -> str:
    if valeur is None or not str(valeur).strip():
        raise ErreurTableauBilan(f"« {libelle} » est vide dans le tableau bilan.")
    return str(valeur).strip()


def _nombre(valeur, libelle: str) -> float:
    """Nombre décimal, en tolérant la virgule, les espaces et un symbole d'unité."""
    if isinstance(valeur, bool):
        raise ErreurTableauBilan(f"« {libelle} » vaut un booléen, un nombre est attendu.")
    if isinstance(valeur, (int, float)):
        return float(valeur)
    if valeur is None:
        raise ErreurTableauBilan(f"« {libelle} » est vide, un nombre est attendu.")
    texte = str(valeur).strip().replace(" ", "").replace(" ", "")
    texte = texte.replace(",", ".")
    trouve = re.fullmatch(r"[-+]?\d*\.?\d+\s*[^\d]*", texte)
    if not trouve:
        raise ErreurTableauBilan(
            f"« {libelle} » vaut {valeur!r} : impossible d'y lire un nombre."
        )
    return float(re.match(r"[-+]?\d*\.?\d+", texte).group())


def _entier(valeur, libelle: str) -> int:
    nombre = _nombre(valeur, libelle)
    if abs(nombre - round(nombre)) > 1e-9:
        raise ErreurTableauBilan(
            f"« {libelle} » vaut {valeur!r} : un nombre entier est attendu."
        )
    return int(round(nombre))


def _angle(valeur, libelle: str) -> float:
    """Angle en degrés, avec ou sans le symbole °."""
    return _nombre(valeur, libelle)


def _date(valeur, libelle: str) -> _dt.date:
    if isinstance(valeur, _dt.datetime):
        return valeur.date()
    if isinstance(valeur, _dt.date):
        return valeur
    texte = _texte(valeur, libelle)
    for motif in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(texte, motif).date()
        except ValueError:
            continue
    raise ErreurTableauBilan(
        f"« {libelle} » vaut {valeur!r} : format de date non reconnu "
        "(attendu jj/mm/aaaa)."
    )


def _couple(valeur, libelle: str) -> tuple[int, ...]:
    """Valeur composite « 13 / 26 », rendue en tuple d'entiers.

    Le tableau y met les deux longueurs de table du projet. Une valeur simple
    est acceptée et rendue en tuple d'un élément.
    """
    if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
        return (_entier(valeur, libelle),)
    texte = _texte(valeur, libelle)
    morceaux = [m.strip() for m in re.split(r"[/;]", texte) if m.strip()]
    if not morceaux:
        raise ErreurTableauBilan(f"« {libelle} » vaut {valeur!r} : valeur illisible.")
    return tuple(_entier(m, libelle) for m in morceaux)


# ---------------------------------------------------------------------------
# Description des paramètres attendus
# ---------------------------------------------------------------------------

#: (clé, libellé attendu en colonne A, convertisseur, obligatoire)
#: Le libellé est comparé après normalisation tolérante : les espaces de fin
#: (« Phase », « Format ») et les accents ne comptent pas.
PARAMETRES = {
    "generalites": (
        ("phase", "Phase", _texte, True),
        ("date", "Date (jj/mm/aaaa)", _date, True),
        ("type_projet", "Type de projet", _texte, True),
        ("surface_cloturee_ha", "Surface clôturée (ha)", _nombre, True),
        ("lineaire_cloture_m", "Linéaire de clôture (m)", _nombre, True),
        ("nb_portails", "Nombre de portails d'accès", _entier, True),
        ("largeur_portails_m", "Largeur des portails (m)", _nombre, True),
    ),
    "structures": (
        ("type_structure", "Type de structure", _texte, True),
        ("format_table", "Format table", _texte, True),
        ("inclinaison_deg", "Inclinaison (°)", _angle, True),
        ("azimut_deg", "Azimut (°)", _angle, True),
        ("nb_tables", "Nombre de tables", _entier, True),
        ("inter_table_m", "Inter-table (m)", _nombre, True),
        ("pitch_m", "Pitch (m)", _nombre, True),
        ("point_bas_m", "Point bas (m)", _nombre, True),
        ("point_haut_m", "Point haut (m)", _nombre, True),
        ("nb_modules_rampant", "Nb de mod en rampant", _entier, True),
        ("nb_modules_longueur", "Nb de mod en longueur", _couple, True),
        ("nb_modules_table", "Nb de mod/table", _couple, True),
        ("type_fondation", "Type de fondation", _texte, True),
        ("nb_pieux", "Nombre de pieux", _entier, True),
    ),
    "modules": (
        ("format_module", "Format", _texte, True),
        ("puissance_unitaire_wc", "Puissance unitaire (Wc)", _nombre, True),
        ("surface_unitaire_m2", "Surface unitaire (m²)", _nombre, True),
        ("nb_modules", "Nombre installé", _entier, True),
        ("gcr", "GCR (%)", _nombre, True),
        ("surface_modules_m2", "Surface modules (m²)", _nombre, True),
        ("surface_projetee_m2", "Surface module projetée au sol (m²)", _nombre, True),
        ("puissance_mwc", "Puissance projet (MWc)", _nombre, True),
    ),
    "postes": (
        ("nb_ptr", "Nombre de PTR", _entier, True),
        ("surface_ptr_m2", "Surface des PTR (m²)", _nombre, True),
        ("surface_plateforme_ptr_m2", "Surface plateforme PTR (m²)", _nombre, True),
        ("nb_pdl_ptr", "Nombre de PDL /PTR", _entier, True),
        ("surface_pdl_ptr_m2", "Surface des PDL/PTR (m²)", _nombre, True),
        (
            "surface_plateforme_pdl_ptr_m2",
            "Surface plateforme PDL/PTR (m²)",
            _nombre,
            True,
        ),
        ("nb_pdl", "Nombre de PDL", _entier, True),
        ("surface_pdl_m2", "Surface des PDL (m²)", _nombre, True),
        ("surface_plateforme_pdl_m2", "Surface plateforme PDL (m²)", _nombre, True),
        ("nb_bess", "Nombre de conteneurs de batteries", _entier, True),
        ("surface_bess_m2", "Surface des conteneurs (m²)", _nombre, True),
        (
            "surface_plateforme_bess_m2",
            "Surface plateforme batteries (m²)",
            _nombre,
            True,
        ),
        ("nb_citerne_refroidissement", "Citerne de refroidissement (120m3)", _entier, True),
        ("nb_bac_retention", "Bac de rétention (120m3)", _entier, True),
        ("nb_local_stockage", "Nombre de locaux de stockage matériel", _entier, True),
        (
            "surface_local_stockage_m2",
            "Surface locaux de stockage matériel (m²)",
            _nombre,
            True,
        ),
    ),
}


# ---------------------------------------------------------------------------
# Modèle
# ---------------------------------------------------------------------------


@dataclass
class CoteNormalisee:
    """Une ligne de l'onglet « Dimensions postes et pieux »."""

    ouvrage: str
    dimensions: str
    #: Ordre des cotes tel qu'annoncé par l'en-tête de la section. Il change
    #: d'une section à l'autre dans le fichier de référence (« largeur x
    #: longueur x hauteur » pour le PTR, « longueur x largeur x hauteur » pour
    #: le PDL/PTR) : le lot 4 doit lire cet ordre et non le supposer.
    ordre_cotes: str
    surface_m2: float | None
    surface_plateforme_m2: float | None


@dataclass
class TableauBilan:
    """Paramètres techniques du projet, pour un indice de révision donné."""

    indice: str
    indices_disponibles: list[str]
    nom_projet: str
    generalites: dict
    structures: dict
    modules: dict
    postes: dict
    cotes: list[CoteNormalisee]
    standards: dict
    source: str
    avertissements: list[str] = field(default_factory=list)

    def tous_parametres(self) -> dict:
        return {
            **self.generalites,
            **self.structures,
            **self.modules,
            **self.postes,
        }


# ---------------------------------------------------------------------------
# Sélection de l'indice
# ---------------------------------------------------------------------------


def indice_depuis_nom(nom: str | Path) -> str | None:
    """Indice de révision porté par un nom de fichier DXF, ou None.

    Sert uniquement à *proposer* un appariement : il est toujours confirmé par
    l'utilisateur, un DXF pouvant très bien être exporté sous un autre nom.
    """
    trouve = MOTIF_INDICE.search(Path(str(nom)).name)
    return f"IND{int(trouve.group(1)):02d}" if trouve else None


def _classeur(chemin: Path):
    if not chemin.exists():
        raise ErreurTableauBilan(f"Tableau bilan introuvable : {chemin}")
    try:
        return openpyxl.load_workbook(str(chemin), data_only=True)
    except Exception as exc:  # noqa: BLE001 - remonté en erreur nommée
        raise ErreurTableauBilan(
            f"Tableau bilan illisible ({chemin.name}) : {exc}"
        ) from exc


def _onglet(classeur, nom: str, chemin: Path):
    if nom not in classeur.sheetnames:
        attendus = ", ".join(classeur.sheetnames)
        raise ErreurTableauBilan(
            f"Onglet « {nom} » absent de {chemin.name}. Onglets présents : {attendus}."
        )
    return classeur[nom]


def indices_disponibles(chemin: str | Path) -> list[str]:
    """Indices de révision présents en en-tête de l'onglet caractéristiques."""
    chemin = Path(chemin)
    feuille = _onglet(_classeur(chemin), ONGLET_CARACTERISTIQUES, chemin)
    return _indices_de(feuille)[0]


def _indices_de(feuille) -> tuple[list[str], dict[str, int]]:
    """Indices de la ligne 1 et colonne où chacun se trouve."""
    colonnes: dict[str, int] = {}
    for colonne in range(2, feuille.max_column + 1):
        valeur = feuille.cell(1, colonne).value
        if valeur is None or not str(valeur).strip():
            continue
        trouve = MOTIF_INDICE.fullmatch(str(valeur).strip())
        if trouve:
            colonnes[f"IND{int(trouve.group(1)):02d}"] = colonne
    return list(colonnes), colonnes


# ---------------------------------------------------------------------------
# Étape B — lecture
# ---------------------------------------------------------------------------


def lire_tableau(chemin: str | Path, indice: str) -> TableauBilan:
    """Lit le tableau bilan pour un indice donné et renvoie ses paramètres."""
    chemin = Path(chemin)
    classeur = _classeur(chemin)
    feuille = _onglet(classeur, ONGLET_CARACTERISTIQUES, chemin)

    disponibles, colonnes = _indices_de(feuille)
    if not disponibles:
        raise ErreurTableauBilan(
            f"Aucun indice de révision en ligne 1 de l'onglet "
            f"« {ONGLET_CARACTERISTIQUES} » de {chemin.name}."
        )
    if indice not in colonnes:
        raise ErreurTableauBilan(
            f"Indice « {indice} » absent du tableau bilan {chemin.name}. "
            f"Indices présents : {', '.join(disponibles)}."
        )
    colonne = colonnes[indice]

    lignes = _index_des_libelles(feuille, chemin.name)
    avertissements: list[str] = []

    valeurs: dict[str, dict] = {}
    for groupe, definitions in PARAMETRES.items():
        valeurs[groupe] = {}
        for cle, libelle, convertir, obligatoire in definitions:
            ligne = lignes.get(normaliser(libelle))
            if ligne is None:
                if obligatoire:
                    raise ErreurTableauBilan(
                        f"Paramètre « {libelle} » introuvable en colonne A de "
                        f"l'onglet « {ONGLET_CARACTERISTIQUES} » de {chemin.name}. "
                        "La mise en page du tableau a probablement changé."
                    )
                continue
            brut = feuille.cell(ligne, colonne).value
            if brut is None and not obligatoire:
                continue
            valeurs[groupe][cle] = convertir(brut, f"{libelle} ({indice})")

    nom_projet = str(feuille.cell(1, 1).value or "").strip()
    if not nom_projet:
        avertissements.append(
            f"La cellule A1 de l'onglet « {ONGLET_CARACTERISTIQUES} » ne porte pas "
            "de nom de projet."
        )

    cotes, avertissements_cotes = _lire_cotes(classeur, chemin)
    avertissements.extend(avertissements_cotes)

    type_projet = valeurs["generalites"].get("type_projet", "")
    standards, avertissements_standards = _lire_standards(classeur, chemin, type_projet)
    avertissements.extend(avertissements_standards)

    return TableauBilan(
        indice=indice,
        indices_disponibles=disponibles,
        nom_projet=nom_projet,
        generalites=valeurs["generalites"],
        structures=valeurs["structures"],
        modules=valeurs["modules"],
        postes=valeurs["postes"],
        cotes=cotes,
        standards=standards,
        source=chemin.name,
        avertissements=avertissements,
    )


def _index_des_libelles(feuille, nom_fichier: str) -> dict[str, int]:
    """Libellé normalisé de la colonne A → numéro de ligne.

    Un libellé qui apparaît deux fois est écarté de l'index : le tableau porte
    plusieurs « TOTAL », « Nombre » et « Surface (m²) » dans des sections
    différentes. Aucun paramètre lu ici n'en fait partie, mais laisser passer
    une ambiguïté reviendrait à lire au hasard l'une des deux lignes.
    """
    index: dict[str, int] = {}
    ambigus: set[str] = set()
    for ligne in range(1, feuille.max_row + 1):
        libelle = normaliser(feuille.cell(ligne, 1).value)
        if not libelle:
            continue
        if libelle in index:
            ambigus.add(libelle)
            continue
        index[libelle] = ligne
    for libelle in ambigus:
        index.pop(libelle, None)

    attendus = {
        normaliser(libelle)
        for definitions in PARAMETRES.values()
        for _, libelle, _, _ in definitions
    }
    collisions = sorted(attendus & ambigus)
    if collisions:
        raise ErreurTableauBilan(
            f"{nom_fichier} : les libellés {', '.join(collisions)} apparaissent "
            "plusieurs fois en colonne A. Impossible de savoir quelle ligne lire."
        )
    return index


# ---------------------------------------------------------------------------
# Onglet « Dimensions postes et pieux »
# ---------------------------------------------------------------------------

#: Sections de l'onglet des cotes, repérées par leur titre. Chaque titre est
#: suivi d'une ligne d'en-tête « Dimensions (…) », puis des lignes de données.
SECTIONS_COTES = (
    "Poste de transformation - PTR",
    "Transformateur -  PT",
    "Poste de livraison et de transformation - PDL/PTR",
    "Poste de livraison - PDL",
    "Aire de charge (BESS)",
    "Local de stockage matériel",
    "Citerne incendie",
)

#: Cote de l'aire d'aspiration : elle n'a pas de section à elle, seulement une
#: phrase libre en fin d'onglet (« Compter une aire d'aspiration de 32m²
#: (8 x 4m) »). Elle est extraite par motif, et son absence est signalée.
MOTIF_AIRE_ASPIRATION = re.compile(
    r"aire\s+d.aspiration.*?(\d+(?:[.,]\d+)?)\s*m.*?\(\s*(\d+(?:[.,]\d+)?)\s*[x×]\s*"
    r"(\d+(?:[.,]\d+)?)\s*m\s*\)",
    re.IGNORECASE | re.DOTALL,
)


def _lire_cotes(classeur, chemin: Path) -> tuple[list[CoteNormalisee], list[str]]:
    """Table des cotes normalisées, pour la génération paramétrique du lot 4.

    Cette table ne sert pas aux contrôles de ce lot : son absence n'arrête donc
    pas l'import, mais elle est signalée — le lot 4 ne pourra pas dessiner les
    planches DP 4 sans elle.
    """
    avertissements: list[str] = []
    if ONGLET_DIMENSIONS not in classeur.sheetnames:
        return [], [
            f"Onglet « {ONGLET_DIMENSIONS} » absent de {chemin.name} : les cotes "
            "normalisées des postes ne seront pas disponibles pour les planches DP 4."
        ]
    feuille = classeur[ONGLET_DIMENSIONS]

    positions = {}
    for ligne in range(1, feuille.max_row + 1):
        for colonne in range(1, min(feuille.max_column, 6) + 1):
            libelle = normaliser(feuille.cell(ligne, colonne).value)
            for titre in SECTIONS_COTES:
                if libelle == normaliser(titre) and titre not in positions:
                    positions[titre] = (ligne, colonne)

    cotes: list[CoteNormalisee] = []
    for titre in SECTIONS_COTES:
        if titre not in positions:
            avertissements.append(
                f"Section « {titre} » introuvable dans l'onglet "
                f"« {ONGLET_DIMENSIONS} » : cotes normalisées manquantes."
            )
            continue
        ligne, colonne = positions[titre]
        entete = _entete_dimensions(feuille, ligne, colonne)
        if entete is None:
            avertissements.append(
                f"Section « {titre} » : ligne d'en-tête « Dimensions (…) » "
                "introuvable, cotes non lues."
            )
            continue
        ligne_entete, colonne_dim, ordre, colonne_surface, colonne_plateforme = entete
        cotes.extend(
            _lignes_de_cotes(
                feuille,
                titre,
                ligne_entete,
                colonne_dim,
                ordre,
                colonne_surface,
                colonne_plateforme,
            )
        )

    aire = _aire_aspiration(feuille)
    if aire is None:
        avertissements.append(
            f"Cote de l'aire d'aspiration introuvable dans l'onglet "
            f"« {ONGLET_DIMENSIONS} » : le lot 4 ne pourra pas la dessiner."
        )
    else:
        cotes.append(aire)
    return cotes, avertissements


def _entete_dimensions(feuille, ligne_titre: int, colonne_titre: int):
    """Ligne d'en-tête « Dimensions (…) » suivant un titre de section."""
    for ligne in range(ligne_titre + 1, min(ligne_titre + 4, feuille.max_row) + 1):
        for colonne in range(1, min(feuille.max_column, 8) + 1):
            texte = str(feuille.cell(ligne, colonne).value or "")
            if not normaliser(texte).startswith("dimensions"):
                continue
            ordre = ""
            entre_parentheses = re.search(r"\((.*?)\)", texte, re.DOTALL)
            if entre_parentheses:
                ordre = " ".join(entre_parentheses.group(1).split())
            colonne_surface = colonne_plateforme = None
            for suivante in range(colonne + 1, min(feuille.max_column, colonne + 4) + 1):
                libelle = normaliser(feuille.cell(ligne, suivante).value)
                if libelle.startswith("surfaceplateforme"):
                    colonne_plateforme = suivante
                elif libelle.startswith("surface"):
                    colonne_surface = suivante
            return ligne, colonne, ordre, colonne_surface, colonne_plateforme
    return None


def _lignes_de_cotes(
    feuille,
    titre: str,
    ligne_entete: int,
    colonne_dim: int,
    ordre: str,
    colonne_surface: int | None,
    colonne_plateforme: int | None,
) -> list[CoteNormalisee]:
    """Lignes de données d'une section, jusqu'à la première ligne sans dimension."""
    resultat = []
    for ligne in range(ligne_entete + 1, feuille.max_row + 1):
        dimensions = feuille.cell(ligne, colonne_dim).value
        if dimensions is None or not str(dimensions).strip():
            break
        # Le nom de la variante est à gauche de la colonne des dimensions
        # (« Conteneurs », « P<=5MWc », le volume de la citerne) ; à défaut,
        # la section n'a qu'une ligne et porte son propre nom.
        variante = feuille.cell(ligne, max(colonne_dim - 1, 1)).value
        ouvrage = f"{titre} — {variante}" if variante not in (None, "") else titre
        resultat.append(
            CoteNormalisee(
                ouvrage=str(ouvrage).strip(),
                dimensions=" ".join(str(dimensions).split()),
                ordre_cotes=ordre,
                surface_m2=_valeur_facultative(feuille, ligne, colonne_surface),
                surface_plateforme_m2=_valeur_facultative(
                    feuille, ligne, colonne_plateforme
                ),
            )
        )
    return resultat


def _valeur_facultative(feuille, ligne: int, colonne: int | None) -> float | None:
    if colonne is None:
        return None
    valeur = feuille.cell(ligne, colonne).value
    if valeur is None or not str(valeur).strip():
        return None
    return _nombre(valeur, f"cellule ligne {ligne} colonne {colonne}")


def _aire_aspiration(feuille) -> CoteNormalisee | None:
    for ligne in range(1, feuille.max_row + 1):
        for colonne in range(1, min(feuille.max_column, 8) + 1):
            texte = str(feuille.cell(ligne, colonne).value or "")
            trouve = MOTIF_AIRE_ASPIRATION.search(texte)
            if trouve:
                return CoteNormalisee(
                    ouvrage="Aire d'aspiration",
                    dimensions=f"{trouve.group(2)} x {trouve.group(3)} m",
                    ordre_cotes="longueur x largeur",
                    surface_m2=float(trouve.group(1).replace(",", ".")),
                    surface_plateforme_m2=None,
                )
    return None


# ---------------------------------------------------------------------------
# Onglet « Standards UNITe »
# ---------------------------------------------------------------------------

#: Ligne de l'onglet des standards portant le type d'activité, qui est la valeur
#: à apparier avec « Type de projet » de l'onglet caractéristiques.
LIBELLE_TYPE_ACTIVITE = "Type d'activité"


def _lire_standards(classeur, chemin: Path, type_projet: str) -> tuple[dict, list[str]]:
    """Valeurs de référence UNITe pour le type de projet, à titre de vraisemblance.

    Ces valeurs ne bloquent rien : elles sont affichées en regard des valeurs du
    projet à l'écran de validation. Sur le fichier de référence, quatre d'entre
    elles s'écartent du projet (format de table, inter-table, hauteurs) sans que
    ce soit une anomalie — un standard n'est pas une contrainte.
    """
    if ONGLET_STANDARDS not in classeur.sheetnames:
        return {}, [
            f"Onglet « {ONGLET_STANDARDS} » absent de {chemin.name} : pas de "
            "contrôle de vraisemblance sur les paramètres de structure."
        ]
    feuille = classeur[ONGLET_STANDARDS]

    ligne_types = None
    for ligne in range(1, feuille.max_row + 1):
        for colonne in range(1, min(feuille.max_column, 4) + 1):
            if normaliser(feuille.cell(ligne, colonne).value) == normaliser(
                LIBELLE_TYPE_ACTIVITE
            ):
                ligne_types = (ligne, colonne)
                break
        if ligne_types:
            break
    if ligne_types is None:
        return {}, [
            f"Ligne « {LIBELLE_TYPE_ACTIVITE} » introuvable dans l'onglet "
            f"« {ONGLET_STANDARDS} » : pas de contrôle de vraisemblance."
        ]

    ligne, colonne_libelles = ligne_types
    cible = normaliser(type_projet)
    colonne_projet = None
    for colonne in range(colonne_libelles + 1, feuille.max_column + 1):
        if normaliser(feuille.cell(ligne, colonne).value) == cible:
            colonne_projet = colonne
            break
    if colonne_projet is None:
        return {}, [
            f"Type de projet « {type_projet} » absent de l'onglet "
            f"« {ONGLET_STANDARDS} » : pas de contrôle de vraisemblance."
        ]

    standards = {}
    for ligne_valeur in range(ligne + 1, feuille.max_row + 1):
        libelle = feuille.cell(ligne_valeur, colonne_libelles).value
        if libelle is None or not str(libelle).strip():
            continue
        valeur = feuille.cell(ligne_valeur, colonne_projet).value
        if valeur is None or not str(valeur).strip():
            continue
        standards[" ".join(str(libelle).split())] = valeur
    return standards, []
