"""Lecture du contrat d'entrée du lot 4.

Le lot 4 lit **une seule structure** — `sortie/{projet}/geometries.gpkg` et
`sortie/{projet}/projet.json` — sans savoir lequel des deux producteurs l'a
écrite. Le champ `origine` les distingue, et il ne sert qu'à deux choses : le
dire au rapport, et savoir que le Z d'un dossier HelioScope ne décrit pas le
terrain (voir `dp_socle.planches.dp3_coupes`).

Ce module ne dessine rien. Il lit, il valide, et il refuse : une version de
contrat plus récente que celle que l'outil sait lire, une couche `voirie`
peuplée dont personne n'a tranché le type, une cote d'ouvrage introuvable ou
ambiguë. Chacun de ces refus vaut mieux qu'une planche présentable et fausse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
from shapely import force_2d, make_valid
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .erreurs import ErreurContrat, ErreurCoteOuvrage, ErreurVoirieIndecise
from .import_be import (
    NOM_GEOPACKAGE,
    ORIGINE_HELIOSCOPE,
    VERSION_CONTRAT,
    lire_parametres,
)

#: Ce qu'un objet de voirie sans surface reçoit : un axe ou un bout de limite
#: n'est pas une voie dessinée, il n'entre dans aucun calcul et ne va sur aucune
#: planche. Le dire explicitement vaut mieux que de lui attribuer un type au
#: hasard — un choix muet resterait un choix, et il se lirait au contrat.
VOIRIE_SANS_OBJET = "sans_objet"

#: Types de voirie entre lesquels le chef de projet tranche (décision D5).
#: Aucune valeur par défaut : c'est tout l'objet de la règle.
VOIRIES_ADMISES = ("piste_lourde", "piste_legere")


# ---------------------------------------------------------------------------
# Cotes normalisées
# ---------------------------------------------------------------------------

#: Dimensions repérées à la fin d'un libellé de cote : « 12 x 3 x 3m »,
#: « 11,7 x 9,3 x 1 m », « 1 conteneur 20 pieds 6 x 3 x 3m ». Le préfixe est
#: ignoré, la dernière suite de nombres séparés par des « x » fait foi.
_MOTIF_DIMENSIONS = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)"
    r"(?:\s*[x×]\s*(\d+(?:[.,]\d+)?))?\s*m?\s*$",
    re.IGNORECASE,
)

#: Noms de dimension reconnus dans `ordre_cotes`, et l'attribut correspondant.
_NOMS_COTES = ("longueur", "largeur", "hauteur")


@dataclass(frozen=True)
class Cote:
    """Une ligne de `cotes_normalisees`, dimensions décodées.

    ⚠️ `ordre_cotes` change d'un ouvrage à l'autre — « largeur x longueur x
    hauteur » pour le PTR, « longueur x largeur x hauteur » pour le PDL/PTR.
    C'est lui qui donne le sens de chaque nombre, jamais leur position. Un
    poste de 12 x 3 m dessiné 3 x 12 se dessine parfaitement et ne se voit pas.
    """

    ouvrage: str
    dimensions: str
    ordre_cotes: str
    surface_m2: float | None
    surface_plateforme_m2: float | None
    #: Dimensions rapportées à leur nom, décodées depuis `ordre_cotes`.
    valeurs: dict = field(default_factory=dict)

    @property
    def longueur_m(self) -> float:
        return self._valeur("longueur")

    @property
    def largeur_m(self) -> float:
        return self._valeur("largeur")

    @property
    def hauteur_m(self) -> float:
        return self._valeur("hauteur")

    @property
    def a_hauteur(self) -> bool:
        return "hauteur" in self.valeurs

    def _valeur(self, nom: str) -> float:
        if nom not in self.valeurs:
            raise ErreurCoteOuvrage(
                f"L'ouvrage « {self.ouvrage} » n'a pas de {nom} : son ordre de "
                f"cotes est « {self.ordre_cotes} » pour les dimensions "
                f"« {self.dimensions} ». Le GeoPackage donne une emprise au sol, "
                "jamais une hauteur : la planche n'est pas dessinée."
            )
        return self.valeurs[nom]


def _nombre(texte: str) -> float:
    return float(texte.replace(",", "."))


def decoder_cote(brut: dict) -> Cote:
    """Décode une entrée de `cotes_normalisees`, ou lève.

    Le décodage échoue plutôt que de rendre une cote partielle : une dimension
    mal comprise produit un ouvrage juste de forme et faux de taille.
    """
    ouvrage = str(brut.get("ouvrage", "")).strip()
    dimensions = str(brut.get("dimensions", "")).strip()
    ordre = str(brut.get("ordre_cotes", "")).strip()

    correspondance = _MOTIF_DIMENSIONS.search(dimensions)
    if not correspondance:
        raise ErreurCoteOuvrage(
            f"Cote illisible pour « {ouvrage} » : « {dimensions} ». Attendu des "
            "dimensions de la forme « 12 x 3 x 3 m » en fin de libellé."
        )
    nombres = [_nombre(g) for g in correspondance.groups() if g is not None]

    noms = [n.strip().lower() for n in re.split(r"[x×]", ordre) if n.strip()]
    if len(noms) != len(nombres):
        raise ErreurCoteOuvrage(
            f"« {ouvrage} » : {len(nombres)} dimensions lues dans "
            f"« {dimensions} » pour {len(noms)} nommées dans « {ordre} ». "
            "Impossible de savoir laquelle est la longueur."
        )
    inconnus = [n for n in noms if n not in _NOMS_COTES]
    if inconnus:
        raise ErreurCoteOuvrage(
            f"« {ouvrage} » : ordre de cotes « {ordre} » — dimension(s) non "
            f"reconnue(s) : {', '.join(inconnus)}. Attendu parmi "
            f"{', '.join(_NOMS_COTES)}."
        )
    return Cote(
        ouvrage=ouvrage,
        dimensions=dimensions,
        ordre_cotes=ordre,
        surface_m2=brut.get("surface_m2"),
        surface_plateforme_m2=brut.get("surface_plateforme_m2"),
        valeurs=dict(zip(noms, nombres)),
    )


#: Libellé de `cotes_normalisees` correspondant à chaque catégorie dessinée.
#:
#: Relevés le 04/09/2026 sur la sortie de Bray-Saint-Aignan, qui porte le
#: catalogue complet du tableau bilan. Ce catalogue liste **tous** les
#: ouvrages standards d'UNITe, pas seulement ceux du projet : l'appariement se
#: fait donc sur le libellé, et les familles à plusieurs variantes se
#: départagent ensuite sur la surface (voir `cote_de_categorie`).
LIBELLES_COTES = {
    "pdl_ptr": ("Poste de livraison et de transformation - PDL/PTR",),
    "ptr": ("Poste de transformation - PTR",),
    "pdl": ("Poste de livraison - PDL",),
    "bess": ("Aire de charge (BESS) — Conteneurs",),
    "bac_retention": ("Aire de charge (BESS) — Bac de rétention",),
    "citerne_refroidissement": ("Aire de charge (BESS) — Citerne de refroidissement",),
    "zone_remise": ("Aire de charge (BESS) — Zone de remise",),
    "aire_aspiration": ("Aire d'aspiration",),
    # Familles à variantes : quatre volumes de citerne incendie, trois tailles
    # de local de stockage selon la puissance. Le libellé ne suffit pas.
    "bache_incendie": (
        "Citerne incendie — 30",
        "Citerne incendie — 60",
        "Citerne incendie — 120",
        "Citerne incendie — 240",
    ),
    "local_technique": (
        "Local de stockage matériel — P<=5MWc",
        "Local de stockage matériel — P>5MWc",
        "Local de stockage matériel — P>17MWc",
    ),
}

#: Écart admis entre la surface au sol mesurée sur le GeoPackage et celle
#: déclarée au catalogue, pour départager les variantes d'une famille.
#:
#: 15 % : le plan du BE dessine l'emprise réelle, le catalogue arrondit
#: (7,95 x 4,44 = 35,3 m² déclarés 35). Deux variantes voisines de la famille
#: « citerne incendie » sont à 60 et 104 m², soit 70 % d'écart : la tolérance
#: peut être large sans confondre deux variantes.
TOLERANCE_VARIANTE = 0.15


# ---------------------------------------------------------------------------
# Le contrat
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntiteContrat:
    """Une géométrie du contrat, à plat, avec les bornes de son Z."""

    geometrie: BaseGeometry
    categorie: str
    calque: str
    z_min: float | None
    z_max: float | None
    z_reel: bool


def _reel_ou_rien(valeur):
    """Un réel, ou None : les colonnes du GeoPackage rendent des NaN."""
    if valeur is None:
        return None
    try:
        reel = float(valeur)
    except (TypeError, ValueError):
        return None
    return None if reel != reel else reel


@dataclass
class Contrat:
    """Contenu de `sortie/{projet}/`, prêt à dessiner."""

    dossier: Path
    donnees: dict
    couches: dict
    #: Type retenu pour la couche `voirie`, quand il a fallu trancher (D5).
    #:
    #: Une chaîne vaut pour toute la couche ; une liste donne un type par objet,
    #: dans l'ordre de la couche. Le second cas est le courant : un projet a
    #: presque toujours de la voie lourde **et** de la piste légère, et le calque
    #: du bureau d'études les mélange sans les nommer.
    voirie: str | list | None = None

    # -- métadonnées ---------------------------------------------------------

    @property
    def origine(self) -> str:
        return str(self.donnees.get("origine", ""))

    @property
    def version(self) -> int:
        return int(self.donnees.get("version_contrat", 0))

    @property
    def helioscope(self) -> bool:
        """Vrai si le dossier vient du lot 2 — donc d'un DXF sans terrain."""
        return self.origine == ORIGINE_HELIOSCOPE

    @property
    def parametres(self) -> dict:
        return self.donnees.get("parametres") or {}

    @property
    def generalites(self) -> dict:
        return self.parametres.get("generalites") or {}

    @property
    def structures(self) -> dict:
        return self.parametres.get("structures") or {}

    @property
    def modules(self) -> dict:
        return self.parametres.get("modules") or {}

    @property
    def postes(self) -> dict:
        return self.parametres.get("postes") or {}

    @property
    def plan(self) -> dict:
        return self.donnees.get("plan") or {}

    @property
    def profil(self) -> dict | None:
        """Profil du terrain naturel, ou None si la coupe n'a pas été tracée."""
        return self.donnees.get("profil_terrain")

    @property
    def coupe(self) -> dict | None:
        return self.donnees.get("ligne_coupe")

    # -- couches -------------------------------------------------------------

    @property
    def categories(self) -> tuple:
        """Catégories effectivement présentes, hors ligne de coupe."""
        return tuple(c for c in self.couches if c != "ligne_coupe")

    def presente(self, categorie: str) -> bool:
        return categorie in self.couches and len(self.couches[categorie]) > 0

    def geometries(self, categorie: str) -> list:
        """Géométries d'une catégorie, à plat et valides, prêtes à dessiner.

        **À plat** : le contrat porte des `Polygon Z`, et le moteur de planche
        ne trace que des coordonnées à deux dimensions — il lève sur les
        troisièmes. C'est cohérent avec ce qu'est un plan de masse, une
        projection au sol ; l'altitude ne s'y dessine pas, elle se lit sur la
        coupe. Le Z reste accessible par `z_bornes` et `entites`, où il porte
        un sens, plutôt que traîné dans une géométrie qui n'en a pas l'usage.

        **Valides** : `make_valid` systématiquement, pas seulement là où ça a
        déjà planté (D6). Le calque « ESPACE VERT » de Sarnois portait un
        polygone auto-intersectant qui faisait échouer `unary_union` au lot
        2bis, et rien ne dit que c'est le seul fichier du parc dans ce cas.
        """
        return [entite.geometrie for entite in self.entites(categorie)]

    def voiries_de(self, categorie: str) -> list:
        """Objets de la couche `voirie` que le chef de projet a rangés ici.

        Le calque du bureau d'études mélange les deux revêtements sans les
        nommer, et un projet a presque toujours les deux : le tri se fait objet
        par objet, et cette méthode est le seul endroit qui sache le relire.
        """
        if not self.voirie:
            return []
        objets = self.geometries("voirie")
        return [
            geometrie
            for geometrie, choisi in zip(objets, self.voirie)
            # `area > 0` est un garde-fou et non une redite : un objet sans
            # surface ne va sur aucune planche, quel que soit le type qu'on lui
            # ait donné — un axe dessiné comme une piste serait faux.
            if choisi == categorie and geometrie.area > 0
        ]

    def entites(self, categorie: str) -> list:
        """Géométries d'une catégorie avec les bornes de leur Z, une par une.

        La coupe du terrain a besoin de l'altitude table par table, pas de
        celle de la couche : `z_bornes` donne la seconde, celle-ci la première.
        """
        couche = self.couches.get(categorie)
        if couche is None:
            return []
        resultat = []
        for ligne in couche.itertuples():
            geometrie = ligne.geometry
            if geometrie is None or geometrie.is_empty:
                continue
            resultat.append(
                EntiteContrat(
                    geometrie=make_valid(force_2d(geometrie)),
                    categorie=categorie,
                    calque=str(getattr(ligne, "calque", "") or ""),
                    z_min=_reel_ou_rien(getattr(ligne, "z_min", None)),
                    z_max=_reel_ou_rien(getattr(ligne, "z_max", None)),
                    z_reel=bool(getattr(ligne, "z_reel", False)),
                )
            )
        return resultat

    def union(self, categorie: str) -> BaseGeometry | None:
        geometries = self.geometries(categorie)
        if not geometries:
            return None
        return unary_union(geometries)

    def z_bornes(self, categorie: str) -> tuple[float | None, float | None]:
        """Bornes du Z d'une couche, telles que le producteur les a écrites."""
        couche = self.couches.get(categorie)
        if couche is None or couche.empty:
            return (None, None)
        bas = couche["z_min"].dropna()
        haut = couche["z_max"].dropna()
        return (
            float(bas.min()) if len(bas) else None,
            float(haut.max()) if len(haut) else None,
        )

    def z_reel(self, categorie: str) -> bool:
        """Vrai si le Z de la couche porte une altitude de terrain.

        Faux dès qu'une seule entité de la couche ne le porte pas : mélanger
        des cotes de terrain et des zéros d'élévation dans un même dessin
        donnerait une coupe où une table sur deux est enterrée.
        """
        couche = self.couches.get(categorie)
        if couche is None or couche.empty or "z_reel" not in couche:
            return False
        return bool(couche["z_reel"].fillna(False).all())

    # -- cotes ---------------------------------------------------------------

    @property
    def cotes(self) -> list:
        return [decoder_cote(brut) for brut in self.donnees.get("cotes_normalisees", [])]

    def cote_de_categorie(self, categorie: str, surface_m2: float | None = None) -> Cote:
        """Cote normalisée d'un ouvrage, ou lève.

        `surface_m2` est la surface au sol mesurée sur le GeoPackage : elle
        départage les familles à plusieurs variantes (quatre volumes de citerne
        incendie, trois tailles de local de stockage). Sans elle, une famille à
        variantes est ambiguë et l'ouvrage n'est pas dessiné.
        """
        libelles = LIBELLES_COTES.get(categorie)
        if not libelles:
            raise ErreurCoteOuvrage(
                f"Aucune cote normalisée n'est prévue pour la catégorie "
                f"« {categorie} » : elle ne se dessine pas en ouvrage technique."
            )
        catalogue = {cote.ouvrage: cote for cote in self.cotes}
        candidates = [catalogue[libelle] for libelle in libelles if libelle in catalogue]
        if not candidates:
            raise ErreurCoteOuvrage(
                f"« {categorie} » est dessinée mais aucune de ses cotes "
                f"normalisées n'est au contrat (cherché : "
                f"{', '.join(libelles)}). Le GeoPackage donne son emprise au "
                "sol, jamais sa hauteur : la planche n'est pas dessinée."
            )
        if len(candidates) == 1:
            return candidates[0]

        if surface_m2 is None:
            raise ErreurCoteOuvrage(
                f"« {categorie} » a {len(candidates)} variantes au catalogue "
                f"({', '.join(c.ouvrage for c in candidates)}) et aucune surface "
                "mesurée pour les départager."
            )
        retenues = [
            cote
            for cote in candidates
            if _surface_proche(cote, surface_m2, TOLERANCE_VARIANTE)
        ]
        if len(retenues) != 1:
            detail = ", ".join(
                f"{c.ouvrage} ({c.dimensions})" for c in (retenues or candidates)
            )
            raise ErreurCoteOuvrage(
                f"« {categorie} » mesure {surface_m2:.1f} m² au plan et "
                f"{'aucune' if not retenues else 'plusieurs'} variante(s) du "
                f"catalogue n'y correspond(ent) à "
                f"{TOLERANCE_VARIANTE:.0%} près : {detail}. La cote est levée à "
                "la main dans le tableau bilan plutôt que devinée."
            )
        return retenues[0]


def _surface_proche(cote: Cote, mesuree: float, tolerance: float) -> bool:
    """La cote décrit-elle un ouvrage de cette surface au sol ?

    On compare à la surface de l'ouvrage lui-même, et à défaut au produit de
    ses deux dimensions au sol : les citernes incendie n'ont pas de
    `surface_m2` au catalogue, seulement une surface de plateforme.
    """
    references = [cote.surface_m2]
    try:
        references.append(cote.longueur_m * cote.largeur_m)
    except ErreurCoteOuvrage:
        pass
    for reference in references:
        if reference and abs(mesuree - reference) <= tolerance * reference:
            return True
    return False


def charger_contrat(dossier: str | Path, voirie=None) -> Contrat:
    """Lit le GeoPackage et le `projet.json` d'un dossier de sortie.

    `voirie` tranche le type des voiries dont le calque ne le disait pas
    (décision D5) : sans ce choix, une couche `voirie` peuplée fait lever. Ne
    pas la rattacher d'office à l'une ou l'autre — le tableau bilan sépare les
    deux et la légende du dossier les distingue.
    """
    dossier = Path(dossier)
    chemin_gpkg = dossier / NOM_GEOPACKAGE

    # `lire_parametres` refuse déjà une origine étrangère et une version de
    # contrat supérieure à celle que l'outil sait lire : ce refus n'est pas
    # réécrit ici, il n'aurait aucune raison de rester le même des deux côtés.
    donnees = lire_parametres(dossier)
    if donnees is None:
        raise ErreurContrat(
            f"Aucun contrat d'entrée dans {dossier} : `projet.json` absent. "
            "Importez le plan du bureau d'études (lot 2bis) ou l'export "
            "HelioScope (lot 2) avant de dessiner les planches DP 2 à DP 4."
        )
    if not chemin_gpkg.exists():
        raise ErreurContrat(
            f"{chemin_gpkg} absent alors que {dossier / 'projet.json'} est "
            "présent : le contrat est incomplet. Rejouez l'import."
        )

    couches = _lire_couches(chemin_gpkg)

    nb_voiries = len(couches.get("voirie", []))
    choix = [voirie] * nb_voiries if isinstance(voirie, str) else voirie
    if choix is not None:
        admis = set(VOIRIES_ADMISES) | {VOIRIE_SANS_OBJET}
        inconnus = sorted({c for c in choix if c not in admis})
        if inconnus:
            raise ErreurVoirieIndecise(
                f"Type de voirie « {', '.join(map(str, inconnus))} » inconnu, "
                f"attendu parmi {', '.join(sorted(admis))}."
            )
        if len(choix) != nb_voiries:
            raise ErreurVoirieIndecise(
                f"{len(choix)} type(s) de voirie tranché(s) pour "
                f"{nb_voiries} objet(s) sur la couche « voirie » : le choix se "
                "fait objet par objet, et il en faut autant que le plan en "
                "porte. Rejouez le tri — le plan a probablement changé depuis."
            )
    if nb_voiries and choix is None:
        raise ErreurVoirieIndecise(
            f"{nb_voiries} objet(s) sur la couche « voirie » : le calque du "
            "bureau d'études ne dit pas s'il s'agit de voie lourde ou de piste "
            "légère, alors que le tableau bilan sépare les deux et que la "
            "légende du dossier les distingue. Tranchez avant de dessiner : "
            "aucune des deux n'est plus probable que l'autre."
        )

    return Contrat(dossier=dossier, donnees=donnees, couches=couches, voirie=choix)


def _lire_couches(chemin: Path) -> dict:
    """Toutes les couches du GeoPackage, indexées par catégorie."""
    import fiona

    try:
        noms = fiona.listlayers(str(chemin))
    except Exception as exc:
        raise ErreurContrat(f"{chemin} illisible : {exc}") from exc

    couches = {}
    for nom in noms:
        gdf = gpd.read_file(chemin, layer=nom)
        if gdf.crs is None or gdf.crs.to_epsg() != 2154:
            raise ErreurContrat(
                f"Couche « {nom} » de {chemin.name} en "
                f"{gdf.crs.to_string() if gdf.crs is not None else 'CRS absent'} "
                "au lieu d'EPSG:2154. Tout le traitement géométrique du "
                "générateur est en Lambert 93."
            )
        couches[nom] = gdf
    return couches


def version_lue() -> int:
    """Version maximale du contrat que le lot 4 sait lire."""
    return VERSION_CONTRAT


def decrire_voiries(dossier: str | Path) -> list:
    """Les objets de la couche `voirie` d'un dossier, décrits pour l'interface.

    Un chef de projet ne peut pas trancher sur un numéro d'ordre : il lui faut
    de quoi reconnaître chaque objet. Une voie lourde fait cinq à six mètres de
    large, une piste légère trois à quatre — la largeur moyenne, surface divisée
    par longueur, suffit le plus souvent à les séparer.

    Le champ `surfacique` dit lesquels appellent une décision. Un linéaire sur
    ce calque n'est pas une voie dessinée mais un axe ou un bout de limite : il
    n'a pas de surface, il n'entrera dans aucun calcul, et demander s'il est
    lourd ou léger n'aurait pas de sens. Deux des trois objets de Sarnois sont
    dans ce cas (mesuré le 17/09/2026).
    """
    import fiona
    from shapely.geometry import shape

    chemin = Path(dossier) / NOM_GEOPACKAGE
    if not chemin.exists():
        return []
    try:
        if "voirie" not in fiona.listlayers(str(chemin)):
            return []
        with fiona.open(str(chemin), layer="voirie") as source:
            objets = [shape(entite["geometry"]) for entite in source]
    except Exception:
        return []

    return decrire_geometries_voirie(objets)


def decrire_geometries_voirie(objets) -> list:
    """Décrit des objets de voirie pour l'interface, sans savoir d'où ils viennent.

    Le contrat écrit et le plan encore en mémoire portent la même couche dans le
    même ordre : le choix peut donc se faire dès l'import, avant que le contrat
    n'existe, et se relire ensuite au même rang.
    """
    from shapely.geometry import Point

    descriptions = []
    for rang, geometrie in enumerate(objets):
        if geometrie is None or geometrie.is_empty:
            descriptions.append({"rang": rang, "surfacique": False, "resume": "vide"})
            continue
        if geometrie.area <= 0:
            # Un linéaire sur ce calque n'est pas une voirie dessinée mais un
            # axe ou un bout de limite : il n'a ni surface ni largeur, et le
            # dire vaut mieux que d'afficher deux zéros.
            descriptions.append(
                {
                    "rang": rang,
                    "surfacique": False,
                    "longueur_m": geometrie.length,
                    "resume": f"linéaire de {geometrie.length:.0f} m, sans surface",
                }
            )
            continue
        rectangle = geometrie.minimum_rotated_rectangle
        longueur = geometrie.length
        if rectangle.geom_type == "Polygon":
            sommets = list(rectangle.exterior.coords)[:-1]
            longueur = max(
                Point(a).distance(Point(b))
                for a, b in zip(sommets, sommets[1:] + sommets[:1])
            )
        largeur = geometrie.area / longueur if longueur else 0.0
        descriptions.append(
            {
                "rang": rang,
                "surfacique": True,
                "surface_m2": geometrie.area,
                "longueur_m": longueur,
                "largeur_m": largeur,
                # Les séparateurs de milliers se remplacent **dans les nombres**
                # et non dans la phrase : un `.replace(",", " ")` global mangeait
                # aussi les virgules du texte.
                "resume": (
                    f"{geometrie.area:,.0f}".replace(",", " ") + " m², "
                    + f"{longueur:,.0f}".replace(",", " ") + " m de long, "
                    + f"{largeur:.1f}".replace(".", ",") + " m de large"
                ),
            }
        )
    return descriptions


def voiries_a_trancher(dossier: str | Path) -> int:
    """Nombre d'objets sur la couche `voirie` d'un dossier de sortie.

    Sert à l'interface : elle ne pose la question du type de voirie que si le
    plan importé en porte. Un dossier sans sortie, ou dont le GeoPackage est
    illisible, rend zéro — la question ne se pose pas encore, et c'est le
    chargement du contrat qui refusera plus tard, avec son message à lui.
    """
    import fiona

    chemin = Path(dossier) / NOM_GEOPACKAGE
    if not chemin.exists():
        return 0
    try:
        if "voirie" not in fiona.listlayers(str(chemin)):
            return 0
        with fiona.open(str(chemin), layer="voirie") as source:
            return len(source)
    except Exception:
        return 0
