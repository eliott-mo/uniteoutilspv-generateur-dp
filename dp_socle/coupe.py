"""Ligne de coupe A-A' et profil du terrain naturel (lot 2bis, étapes D et E).

La coupe DP 3 se lit au 1/300 pour le terrain et au 1/50 pour la structure. La
ligne A-A' n'existe ni dans le DXF ni dans le tableau bilan : elle est tracée à
la main par le chef de projet, **puis corrigée pour être perpendiculaire aux
rangées**.

Pourquoi cette correction est obligatoire : une coupe de terrain n'a de sens que
perpendiculairement aux rangées, c'est la direction dans laquelle le terrain fait
varier la hauteur des tables. Un tracé à main levée est toujours approximatif, et
quelques degrés d'oblique allongent toutes les distances lues sur la planche du
facteur 1/cos θ, sans que rien ne le signale.

Le profil du terrain est récupéré automatiquement auprès du RGE ALTI de la
Géoplateforme ; un fichier d'altimétrie fourni à la main prend le pas sur cet
appel, en le disant.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from math import atan2, cos, degrees, hypot, radians, sin
from pathlib import Path

from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

from .erreurs import ErreurCoupe
from .ign import telecharger_altitudes

#: Marge ajoutée de chaque côté de l'emprise clôturée, en mètres, pour que la
#: coupe la traverse entièrement et montre le terrain de part et d'autre.
MARGE_COUPE_M = 10.0

#: Part de l'emprise écartée à chaque bout pour le placement de la coupe.
#:
#: Une coupe qui longe le bord du site ne montre ni le terrain ni les rangées :
#: elle traverse deux tables et beaucoup d'herbe. Le quart de chaque côté est
#: donc exclu de la recherche, et la ligne se place dans la moitié centrale.
BANDE_EXCLUE = 0.25

#: Longueur minimale d'une traversée pour qu'une table compte, en mètres.
#:
#: `intersects` compte aussi les tables qu'on effleure au coin. Mesuré le
#: 05/09/2026 sur Sarnois : la position ainsi jugée optimale longeait le bord
#: d'une rangée, comptait 15 tables et n'en coupait réellement que 5 — la coupe
#: dessinée en montrait cinq, groupées sur un bout du profil. Le critère de
#: recherche doit être celui du dessin : une table compte quand la ligne la
#: traverse sur une longueur.
LARGEUR_TRAVERSEE_MIN_M = 0.5

#: Pas de la recherche de position, en mètres. Plus fin que la largeur d'une
#: table : c'est ce qui permet de trouver le passage entre deux rangées décalées
#: plutôt que de tomber dessus par hasard.
PAS_RECHERCHE_M = 1.0

#: Écart au-delà duquel le tracé de l'utilisateur est jugé pris à l'envers, en
#: degrés. Au-delà de 45°, il a probablement voulu couper dans l'autre sens ou
#: s'est trompé de repère. La correction s'applique quand même, jamais en
#: silence.
ECART_SUSPECT_DEG = 45.0

#: Pas d'échantillonnage du profil, en mètres. Sur une coupe de site de quelques
#: centaines de mètres, cela fait quelques dizaines de points, soit une requête.
PAS_ECHANTILLONNAGE_M = 5.0

#: Écart systématique admis entre le profil du terrain et le bas des tables, en
#: mètres.
#:
#: Mesuré sur le fichier de référence : le bord bas des tables se tient 1,70 m
#: au-dessus du RGE ALTI en médiane (de 1,15 m à 2,00 m selon la table). C'est
#: la garde au sol de la structure, pas une erreur. Ce contrôle ne cherche donc
#: pas la valeur zéro : il cherche un décalage de référentiel altimétrique, qui
#: se compte en dizaines de mètres, et c'est la **médiane** des écarts qu'on
#: compare au seuil pour qu'une table isolée ne le déclenche pas.
ECART_ALTIMETRIQUE_MAX_M = 2.0

#: Distance en deçà de laquelle une table est tenue pour proche de la coupe, en
#: mètres. Un peu plus que le pitch inter-rangées du fichier de référence
#: (9,5 m) : la coupe passe forcément près d'une table de chaque rangée
#: traversée.
DISTANCE_TABLE_COUPE_M = 12.0

#: Demi-largeur du couloir dans lequel un nuage de points est retenu, en mètres.
#:
#: L'outil topographique interne rend un nuage sur une grille au mètre, pas un
#: profil. À ±2 m, une coupe de n'importe quelle orientation trouve au moins un
#: point par mètre d'abscisse — au pire, en diagonale, les points d'une grille
#: au mètre sont espacés de 1,41 m. Moyenner sur une bande de 4 m lisse le
#: terrain de quelques centimètres sur une pente de 5 %, invisible au 1/300 de
#: la coupe DP 3.
DEMI_COULOIR_M = 2.0

#: Pas de regroupement des altitudes du couloir par abscisse, en mètres. Plus
#: fin que la grille du relevé : il sert à fusionner les points qui se
#: projettent au même endroit, pas à rééchantillonner.
_PAS_REGROUPEMENT_M = 0.25

#: Bornes d'une altitude NGF plausible en France métropolitaine, en mètres.
#:
#: Le point le plus bas est aux environs de -4 m dans les polders du Nord, le
#: plus haut au mont Blanc à 4 809 m. La fourchette est large à dessein : elle
#: ne cherche pas à valider un relevé, mais à refuser un fichier dont la
#: troisième colonne n'est pas une altitude. Un export « X Y » sans altitude
#: passait sans rien dire et rendait un profil plat à 6 954 200 m.
ALTITUDE_MIN_PLAUSIBLE_M = -50.0
ALTITUDE_MAX_PLAUSIBLE_M = 5000.0

#: Trou admis dans le couloir sans le signaler, en mètres. Au-delà, le profil
#: est interpolé en ligne droite sur une distance où le terrain peut faire
#: n'importe quoi.
TROU_MAX_M = 10.0


# ---------------------------------------------------------------------------
# Étape D — correction de perpendicularité
# ---------------------------------------------------------------------------


@dataclass
class LigneCoupe:
    """Ligne A-A', corrigée ou assumée manuelle, avec le tracé d'origine."""

    geometrie: LineString
    trace_initial: LineString
    azimut_tables_deg: float
    #: Écart, en degrés, entre le tracé de l'utilisateur et la perpendiculaire
    #: aux rangées. Conservé pour montrer à l'écran ce qui a été redressé.
    ecart_initial_deg: float
    corrigee: bool
    avertissements: list[str] = field(default_factory=list)

    @property
    def longueur_m(self) -> float:
        return float(self.geometrie.length)

    @property
    def azimut_coupe_deg(self) -> float:
        (x1, y1), (x2, y2) = self.geometrie.coords[0][:2], self.geometrie.coords[-1][:2]
        return degrees(atan2(y2 - y1, x2 - x1))


def position_de_coupe(
    azimut_tables_deg: float,
    emprise_cloturee: BaseGeometry,
    tables: list[BaseGeometry],
) -> tuple[Point, int, int]:
    """Point de passage de la coupe : celui qui traverse le plus de rangées.

    La coupe est perpendiculaire aux rangées ; la déplacer revient donc à la
    faire glisser **le long** des rangées, sur l'axe `azimut_tables_deg`. La
    recherche se fait sur la moitié centrale de l'emprise : une coupe collée au
    bord du site ne montre presque aucune table, et un dossier ne se juge pas
    sur son coin.

    Rend le point retenu, le nombre de tables qu'il fait traverser, et le nombre
    que traversait le milieu de la bande — de quoi dire au rapport ce que le
    déplacement a gagné.
    """
    if not tables:
        raise ErreurCoupe(
            "Aucune table au plan : la position de la coupe ne peut pas être "
            "choisie sur le nombre de rangées traversées."
        )
    ux, uy = cos(radians(azimut_tables_deg)), sin(radians(azimut_tables_deg))
    sommets = list(_sommets(emprise_cloturee))
    if not sommets:
        raise ErreurCoupe(
            "L'emprise clôturée ne porte aucun sommet exploitable : la position "
            "de la coupe ne peut pas être cherchée."
        )
    origine = emprise_cloturee.centroid
    projections = [(x - origine.x) * ux + (y - origine.y) * uy for x, y in sommets]
    debut, fin = min(projections), max(projections)
    largeur = fin - debut
    bas = debut + BANDE_EXCLUE * largeur
    haut = fin - BANDE_EXCLUE * largeur

    def _point(decalage: float) -> Point:
        return Point(origine.x + decalage * ux, origine.y + decalage * uy)

    def _traversees(decalage: float) -> int:
        ligne = _etendre(
            _point(decalage), azimut_tables_deg + 90.0, emprise_cloturee, MARGE_COUPE_M
        )
        return sum(
            1
            for table in tables
            if ligne.intersection(table).length >= LARGEUR_TRAVERSEE_MIN_M
        )

    milieu = (bas + haut) / 2.0
    pas = max(PAS_RECHERCHE_M, largeur / 400.0)
    candidats = []
    decalage = bas
    while decalage <= haut + 1e-9:
        candidats.append(decalage)
        decalage += pas
    if not candidats:
        candidats = [milieu]

    # À nombre de rangées égal, la position la plus centrale l'emporte : c'est
    # celle qui décrit le mieux le site, et elle ne dépend pas du pas de
    # recherche — deux générations du même dossier coupent au même endroit.
    meilleur = max(candidats, key=lambda d: (_traversees(d), -abs(d - milieu)))
    return _point(meilleur), _traversees(meilleur), _traversees(milieu)


def coupe_par_defaut(
    azimut_tables_deg: float,
    emprise_cloturee: BaseGeometry,
    tables: list[BaseGeometry],
    marge_m: float = MARGE_COUPE_M,
) -> LigneCoupe:
    """La coupe que l'outil propose de lui-même, sans que rien n'ait été tracé.

    Le tracé du chef de projet n'apporte, en pratique, que l'intention : la
    direction vient de l'azimut des tables et la position se choisit sur le
    nombre de rangées traversées. Autant la proposer d'emblée — celui qui la
    trouve bien placée n'a plus rien à faire, et celui qui veut la déplacer
    trace par-dessus.

    Elle n'a pas de tracé d'origine à redresser : `trace_initial` est la ligne
    elle-même et l'écart est nul. Ce n'est pas une valeur de repli muette, elle
    dit au rapport où elle s'est placée et ce qu'elle y traverse.
    """
    milieu, retenues, au_milieu = position_de_coupe(
        azimut_tables_deg, emprise_cloturee, tables
    )
    geometrie = _etendre(
        milieu, azimut_tables_deg + 90.0, emprise_cloturee, marge_m
    )
    if retenues > au_milieu:
        message = (
            f"Coupe par défaut : placée dans la moitié centrale de l'emprise, "
            f"où elle traverse {retenues} table(s) contre {au_milieu} au centre "
            "exact."
        )
    else:
        message = (
            f"Coupe par défaut : placée au centre de l'emprise, "
            f"perpendiculairement aux rangées, où elle traverse {retenues} "
            "table(s)."
        )
    return LigneCoupe(
        geometrie=geometrie,
        trace_initial=geometrie,
        azimut_tables_deg=azimut_tables_deg,
        ecart_initial_deg=0.0,
        corrigee=True,
        avertissements=[message],
    )


def corriger_ligne_coupe(
    trace: LineString,
    azimut_tables_deg: float,
    emprise_cloturee: BaseGeometry,
    marge_m: float = MARGE_COUPE_M,
    manuel: bool = False,
    tables: list[BaseGeometry] | None = None,
) -> LigneCoupe:
    """Redresse le tracé perpendiculairement aux rangées et l'étend à l'emprise.

    La direction est imposée par la géométrie des tables. La **position**, elle,
    est choisie sur le nombre de rangées traversées dès que les tables sont
    fournies : le tracé du chef de projet dit qu'il veut une coupe, la
    géométrie dit où elle apprend le plus. Sans `tables`, le point milieu du
    tracé est conservé et rien ne bouge.

    `manuel=True` conserve la direction **et** la position tracées. C'est un
    contournement, désactivé par défaut : il doit rester un choix explicite,
    pour les rares cas où la perpendicularité ne conviendrait pas.
    """
    if trace is None or trace.is_empty or len(trace.coords) < 2:
        raise ErreurCoupe(
            "Aucune ligne de coupe tracée : la coupe DP 3 ne peut pas être "
            "générée sans elle."
        )
    if emprise_cloturee is None or emprise_cloturee.is_empty:
        raise ErreurCoupe(
            "Emprise clôturée absente : la ligne de coupe ne peut pas être "
            "étendue à la largeur du site."
        )

    depart = trace.coords[0][:2]
    arrivee = trace.coords[-1][:2]
    if hypot(arrivee[0] - depart[0], arrivee[1] - depart[1]) < 1e-6:
        raise ErreurCoupe(
            "Le tracé de la ligne de coupe est réduit à un point : tracez un "
            "segment traversant le site."
        )

    milieu = trace.interpolate(0.5, normalized=True)
    trace_milieu = milieu
    direction_tracee = degrees(atan2(arrivee[1] - depart[1], arrivee[0] - depart[0]))
    perpendiculaire = azimut_tables_deg + 90.0
    ecart = abs(_dans_demi_tour(direction_tracee - perpendiculaire))

    avertissements: list[str] = []
    if manuel:
        direction = direction_tracee
        avertissements.append(
            "Mode manuel : la direction tracée est conservée telle quelle. La "
            f"coupe fait {ecart:.1f}° avec la perpendiculaire aux rangées ; les "
            "distances qu'on y lira seront allongées d'autant."
        )
    else:
        direction = perpendiculaire
        if tables:
            milieu, retenues, au_milieu = position_de_coupe(
                azimut_tables_deg, emprise_cloturee, tables
            )
            deplacement = trace_milieu.distance(milieu)
            avertissements.append(
                f"Coupe placée à {deplacement:.0f} m du tracé, dans la moitié "
                f"centrale de l'emprise : elle y traverse {retenues} table(s) "
                f"contre {au_milieu} au centre exact. Le tracé donne la coupe, "
                "sa position se choisit sur le nombre de rangées traversées."
                if deplacement >= 1.0
                else f"Coupe placée au centre de l'emprise, où elle traverse "
                f"{retenues} table(s)."
            )
        if ecart > ECART_SUSPECT_DEG:
            avertissements.append(
                f"Le tracé fait {ecart:.0f}° avec la perpendiculaire aux rangées, "
                f"au-delà des {ECART_SUSPECT_DEG:g}° attendus. Vous avez "
                "probablement voulu couper dans l'autre sens, ou vous êtes trompé "
                "de repère. La ligne a été redressée malgré tout — vérifiez-la "
                "sur l'aperçu."
            )

    geometrie = _etendre(milieu, direction, emprise_cloturee, marge_m)
    # Une coupe qui ne rencontre pas le site n'est pas une coupe de ce site.
    # Le cas se produit à la reprise d'un import précédent : le dossier de
    # sortie garde le tracé du projet d'avant, et le rejouer sur un autre plan
    # donnait une ligne à 185 km de là — avec un profil du terrain d'apparence
    # parfaitement normale, relevé quelque part entre les deux sites.
    if not geometrie.intersects(emprise_cloturee):
        raise ErreurCoupe(
            f"La ligne de coupe obtenue ne traverse pas l'emprise clôturée : son "
            f"point milieu en est distant de "
            f"{milieu.distance(emprise_cloturee):,.0f} m. Ce tracé décrit un "
            "autre site — tracez la coupe sur ce plan-ci."
            .replace(",", " ")
        )
    return LigneCoupe(
        geometrie=geometrie,
        trace_initial=LineString([depart, arrivee]),
        azimut_tables_deg=azimut_tables_deg,
        ecart_initial_deg=ecart,
        corrigee=not manuel,
        avertissements=avertissements,
    )


def _etendre(
    milieu: Point, direction_deg: float, emprise: BaseGeometry, marge_m: float
) -> LineString:
    """Segment centré sur `milieu`, de direction donnée, traversant l'emprise.

    L'étendue se calcule en projetant les sommets de l'emprise sur la direction
    de coupe, plutôt qu'en prenant la diagonale de sa boîte englobante : une
    emprise allongée en biais donnerait sinon une coupe deux fois trop longue.
    """
    ux, uy = cos(radians(direction_deg)), sin(radians(direction_deg))
    projections = [
        (x - milieu.x) * ux + (y - milieu.y) * uy for x, y in _sommets(emprise)
    ]
    if not projections:
        raise ErreurCoupe(
            "L'emprise clôturée ne porte aucun sommet exploitable : la ligne de "
            "coupe ne peut pas être dimensionnée."
        )
    debut, fin = min(projections) - marge_m, max(projections) + marge_m
    return LineString(
        [
            (milieu.x + debut * ux, milieu.y + debut * uy),
            (milieu.x + fin * ux, milieu.y + fin * uy),
        ]
    )


def _sommets(geometrie: BaseGeometry):
    if hasattr(geometrie, "geoms"):
        for partie in geometrie.geoms:
            yield from _sommets(partie)
        return
    if geometrie.geom_type == "Polygon":
        for x, y, *_ in geometrie.exterior.coords:
            yield x, y
    else:
        for x, y, *_ in geometrie.coords:
            yield x, y


def _dans_demi_tour(angle: float) -> float:
    """Ramène un angle dans ]-90, 90] : une coupe n'a pas de sens de parcours."""
    angle = (angle + 90.0) % 180.0 - 90.0
    return 90.0 if angle == -90.0 else angle


# ---------------------------------------------------------------------------
# Étape E — profil altimétrique
# ---------------------------------------------------------------------------


@dataclass
class ProfilTerrain:
    """Profil du terrain naturel le long de la coupe A-A'."""

    #: Abscisses curvilignes depuis l'origine A, en mètres.
    abscisses_m: list[float]
    #: Altitudes NGF, en mètres.
    altitudes_m: list[float]
    origine: str
    pas_m: float
    avertissements: list[str] = field(default_factory=list)

    @property
    def denivelee_m(self) -> float:
        return max(self.altitudes_m) - min(self.altitudes_m)

    @property
    def altitude_min_m(self) -> float:
        return min(self.altitudes_m)

    @property
    def altitude_max_m(self) -> float:
        return max(self.altitudes_m)

    def altitude_a(self, abscisse_m: float) -> float:
        """Altitude interpolée linéairement à une abscisse donnée."""
        if abscisse_m <= self.abscisses_m[0]:
            return self.altitudes_m[0]
        if abscisse_m >= self.abscisses_m[-1]:
            return self.altitudes_m[-1]
        for indice in range(1, len(self.abscisses_m)):
            if self.abscisses_m[indice] >= abscisse_m:
                s0, s1 = self.abscisses_m[indice - 1], self.abscisses_m[indice]
                z0, z1 = self.altitudes_m[indice - 1], self.altitudes_m[indice]
                if s1 == s0:
                    return z0
                return z0 + (z1 - z0) * (abscisse_m - s0) / (s1 - s0)
        return self.altitudes_m[-1]


def echantillonner(ligne: LineString, pas_m: float = PAS_ECHANTILLONNAGE_M):
    """Abscisses et points L93 le long de la ligne, extrémités comprises."""
    if pas_m <= 0:
        raise ErreurCoupe(f"Pas d'échantillonnage invalide : {pas_m} m.")
    longueur = float(ligne.length)
    if longueur <= 0:
        raise ErreurCoupe("Ligne de coupe de longueur nulle.")
    nombre = max(int(longueur // pas_m), 1)
    abscisses = [i * pas_m for i in range(nombre + 1)]
    if abscisses[-1] < longueur - 1e-6:
        abscisses.append(longueur)
    points = [ligne.interpolate(s) for s in abscisses]
    return abscisses, [(p.x, p.y) for p in points]


def profil_terrain(
    ligne: LigneCoupe | LineString,
    pas_m: float = PAS_ECHANTILLONNAGE_M,
    fichier_altimetrie: str | Path | None = None,
) -> ProfilTerrain:
    """Profil du terrain le long de la coupe, RGE ALTI ou fichier de repli.

    Le fichier fourni prend le pas sur l'appel automatique : il sert quand le
    service est indisponible, ou quand un relevé drone plus précis existe. Ce
    remplacement est signalé, il n'est jamais silencieux.
    """
    geometrie = ligne.geometrie if isinstance(ligne, LigneCoupe) else ligne
    abscisses, points = echantillonner(geometrie, pas_m)

    if fichier_altimetrie is not None:
        altitudes, origine, avertissements = _profil_depuis_fichier(
            Path(fichier_altimetrie), geometrie, abscisses
        )
    else:
        altitudes = telecharger_altitudes(points)
        origine = "RGE ALTI (Géoplateforme IGN)"
        avertissements = []

    return ProfilTerrain(
        abscisses_m=list(abscisses),
        altitudes_m=list(altitudes),
        origine=origine,
        pas_m=pas_m,
        avertissements=avertissements,
    )


#: Séparateurs de colonnes essayés, dans l'ordre, avec leur nom lisible.
#:
#: La virgule est à la fois séparateur de colonnes en CSV anglo-saxon et
#: séparateur décimal en français : `0,0;0,0;100,00` compte trois colonnes et
#: non six. Le séparateur n'est donc pas deviné ligne à ligne, il est
#: **déterminé une fois** sur la première ligne de données — celui qui donne
#: 2 ou 3 nombres — puis appliqué à tout le fichier, et le choix retenu est
#: annoncé à l'utilisateur.
SEPARATEURS_COLONNES = (
    (re.compile(r"\s*;\s*"), "point-virgule"),
    (re.compile(r"\s*\t\s*"), "tabulation"),
    (re.compile(r"\s+"), "espace"),
    (re.compile(r"\s*,\s*"), "virgule"),
)


def _decouper(texte: str, motif: re.Pattern, decimale_virgule: bool):
    """Nombres d'une ligne, ou None si elle ne se lit pas avec ce séparateur."""
    morceaux = [m for m in motif.split(texte.strip()) if m]
    valeurs = []
    for morceau in morceaux:
        if decimale_virgule:
            morceau = morceau.replace(",", ".")
        try:
            valeurs.append(float(morceau))
        except ValueError:
            return None
    return tuple(valeurs)



def _verifier_altitudes(releves: list[tuple[float, ...]], chemin: Path) -> None:
    """Refuse un fichier dont la troisième colonne n'est pas une altitude.

    Rien dans un fichier de nombres ne dit ce que chaque colonne signifie. Le
    seul garde-fou possible est l'ordre de grandeur : un export « X Y » sans
    altitude passait sans rien dire et rendait un profil plat à 6 954 200 m —
    absurde, mais tracé sans anomalie.
    """
    hors_bornes = [
        z
        for *_, z in releves
        if not ALTITUDE_MIN_PLAUSIBLE_M <= z <= ALTITUDE_MAX_PLAUSIBLE_M
    ]
    if hors_bornes:
        raise ErreurCoupe(
            f"{chemin.name} : {len(hors_bornes)} altitude(s) hors de toute "
            f"valeur plausible en France, de {min(hors_bornes):.1f} à "
            f"{max(hors_bornes):.1f} m (attendu entre "
            f"{ALTITUDE_MIN_PLAUSIBLE_M:.0f} et {ALTITUDE_MAX_PLAUSIBLE_M:.0f} m). "
            "La troisième colonne n'est probablement pas une altitude."
        )


def _detecter_format(chemin: Path, utiles: list[str]):
    """Séparateur, convention décimale et première ligne de données du relevé.

    Essayés dans l'ordre sur la première ligne qui se lit en 2 ou 3 nombres :
    point-virgule, tabulation, espace, virgule. Une ligne d'en-tête textuelle
    est sautée, mais pas plus d'une : un fichier qui ne se lit qu'à partir de sa
    troisième ligne n'est pas le format attendu.
    """
    for premiere in (1, 2):
        if premiere > len(utiles):
            break
        texte = utiles[premiere - 1]
        for motif, nom in SEPARATEURS_COLONNES:
            for decimale_virgule in (nom != "virgule", False):
                valeurs = _decouper(texte, motif, decimale_virgule)
                if valeurs is not None and len(valeurs) == 3:
                    return motif, nom, decimale_virgule, premiere
    raise ErreurCoupe(
        f"{chemin.name} : impossible de lire « {utiles[0]} » comme 3 colonnes "
        "« X Y Z » en Lambert 93. Séparateurs "
        "acceptés : point-virgule, tabulation, espace, virgule."
    )

def _profil_depuis_fichier(
    chemin: Path, ligne: LineString, abscisses: list[float]
) -> tuple[list[float], str, list[str]]:
    """Lit un relevé altimétrique en TXT et le rééchantillonne sur la coupe.

    Une seule forme est acceptée : **trois colonnes `X Y Z` en Lambert 93**,
    celle que produit l'outil interne d'extraction topographique.

    Une forme à deux colonnes « abscisse ; altitude » avait d'abord été
    acceptée, écrite sans exemple à la main. Elle a été retirée le 03/09/2026 :
    aucun outil du parc n'en produit, et le lecteur ne devinait le format que
    sur le nombre de colonnes. Un export « matricule ; altitude », que tout
    géomètre peut fournir, était lu comme un profil — altitudes justes, placées
    à des abscisses de 11 700 m sur une coupe de 250 m, donc toutes hors de la
    coupe et rabattues sur la première valeur. Un profil plat, crédible, faux.

    Toute autre forme est donc refusée : un fichier mal interprété donnerait une
    coupe plausible et fausse.
    """
    if not chemin.exists():
        raise ErreurCoupe(f"Fichier d'altimétrie introuvable : {chemin}")
    lignes = [
        texte.strip()
        for texte in chemin.read_text(encoding="utf-8", errors="replace").splitlines()
    ]
    utiles = [t for t in lignes if t and not t.startswith(("#", "//"))]
    if not utiles:
        raise ErreurCoupe(f"{chemin.name} ne contient aucune ligne de données.")

    motif, nom_separateur, decimale_virgule, premiere = _detecter_format(chemin, utiles)

    releves: list[tuple[float, ...]] = []
    for numero, texte in enumerate(utiles, start=1):
        if numero < premiere:
            continue  # ligne d'en-tête, écartée avec le format retenu
        valeurs = _decouper(texte, motif, decimale_virgule)
        if valeurs is None:
            raise ErreurCoupe(
                f"{chemin.name}, ligne de données {numero} : « {texte} » n'est "
                f"pas une suite de nombres séparés par {nom_separateur}."
            )
        if len(valeurs) != 3:
            raise ErreurCoupe(
                f"{chemin.name}, ligne de données {numero} : {len(valeurs)} "
                f"colonnes séparées par {nom_separateur}. Attendu 3 colonnes "
                "« X Y Z » en Lambert 93. Un fichier à deux colonnes n'est pas "
                "lu : rien n'y distingue une abscisse d'un matricule, et le "
                "confondre donnerait un profil crédible et faux."
            )
        releves.append(valeurs)

    if len(releves) < 2:
        raise ErreurCoupe(
            f"{chemin.name} ne contient que {len(releves)} point(s) : un profil "
            "demande au moins deux relevés."
        )
    _verifier_altitudes(releves, chemin)

    avertissements = [
        f"Profil altimétrique lu dans {chemin.name} ({len(releves)} points, "
        f"3 colonnes séparées par {nom_separateur}, décimale "
        f"« {',' if decimale_virgule else '.'} ») : ce fichier prend le pas sur "
        "l'interrogation du RGE ALTI."
    ]
    couples, avertissements_nuage = _couloir_de_coupe(releves, ligne, chemin)
    avertissements.extend(avertissements_nuage)

    abscisses_fichier = [c[0] for c in couples]
    altitudes_fichier = [c[1] for c in couples]
    if abscisses_fichier[0] > abscisses[0] + 1.0 or abscisses_fichier[-1] < (
        abscisses[-1] - 1.0
    ):
        avertissements.append(
            f"Le relevé couvre de {abscisses_fichier[0]:.0f} m à "
            f"{abscisses_fichier[-1]:.0f} m alors que la coupe va de "
            f"{abscisses[0]:.0f} m à {abscisses[-1]:.0f} m : les extrémités sont "
            "prolongées à la dernière altitude connue."
        )

    provisoire = ProfilTerrain(
        abscisses_m=abscisses_fichier,
        altitudes_m=altitudes_fichier,
        origine=chemin.name,
        pas_m=0.0,
    )
    return (
        [provisoire.altitude_a(s) for s in abscisses],
        f"Fichier d'altimétrie « {chemin.name} »",
        avertissements,
    )


def _couloir_de_coupe(
    releves: list[tuple[float, ...]],
    ligne: LineString,
    chemin: Path,
    demi_couloir_m: float = DEMI_COULOIR_M,
) -> tuple[list[tuple[float, float]], list[str]]:
    """Profil extrait d'un nuage de points 3D, le long de la ligne de coupe.

    L'outil topographique interne ne rend pas un profil mais un **nuage** : le
    fichier de référence porte 202 399 points sur une grille au mètre couvrant
    605 × 494 m. Projeter tout le nuage sur la ligne, puis trier par abscisse,
    donne un profil qui *ressemble* à un profil et qui est faux : à chaque
    abscisse c'est le dernier point trié qui l'emporte, quelle que soit sa
    distance à la coupe. Mesuré sur ce fichier le 03/09/2026, l'écart au profil
    réel atteignait 2,57 m d'amplitude 3,14 m, pour un relief de 3,50 m — le
    profil était donc du bruit, sans que rien ne le signale.

    Seuls les points d'un couloir centré sur la coupe sont retenus, et les
    altitudes de même abscisse y sont moyennées.
    """
    if len(ligne.coords) < 2:
        raise ErreurCoupe("Ligne de coupe dégénérée : couloir impossible à définir.")

    minx, miny, maxx, maxy = ligne.bounds
    retenus: list[tuple[float, float, float]] = []
    for x, y, z in releves:
        # Filtre par boîte englobante d'abord : il écarte 201 976 des 202 399
        # points du fichier de référence sans construire un seul objet shapely,
        # ce qui fait passer la lecture de 4,1 s à moins d'une seconde.
        if not (
            minx - demi_couloir_m <= x <= maxx + demi_couloir_m
            and miny - demi_couloir_m <= y <= maxy + demi_couloir_m
        ):
            continue
        point = Point(x, y)
        ecart = float(ligne.distance(point))
        if ecart <= demi_couloir_m:
            retenus.append((float(ligne.project(point)), z, ecart))

    if len(retenus) < 2:
        raise ErreurCoupe(
            f"{chemin.name} : seuls {len(retenus)} point(s) du relevé tombent à "
            f"moins de {demi_couloir_m:g} m de la ligne de coupe. Le nuage ne "
            "couvre pas cette coupe — déplacez la coupe, ou fournissez un relevé "
            "qui la traverse."
        )

    # Moyenne des altitudes de même abscisse : sur une grille au mètre et une
    # coupe nord-sud, les points d'une même rangée se projettent au même endroit.
    par_abscisse: dict[int, list[float]] = {}
    for abscisse, z, _ in retenus:
        par_abscisse.setdefault(round(abscisse / _PAS_REGROUPEMENT_M), []).append(z)
    couples = sorted(
        (cle * _PAS_REGROUPEMENT_M, sum(zs) / len(zs))
        for cle, zs in par_abscisse.items()
    )

    avertissements = [
        f"Relevé traité comme un nuage de points : {len(retenus)} points sur "
        f"{len(releves)} retenus dans un couloir de ±{demi_couloir_m:g} m autour "
        f"de la coupe, moyennés en {len(couples)} abscisses."
    ]
    trou = max(
        (suivant[0] - courant[0] for courant, suivant in zip(couples, couples[1:])),
        default=0.0,
    )
    if trou > TROU_MAX_M:
        avertissements.append(
            f"Le couloir présente un trou de {trou:.0f} m sans aucun point : le "
            "profil y est interpolé en ligne droite entre les deux bords du trou."
        )
    return [(a, z) for a, z in couples], avertissements


# ---------------------------------------------------------------------------
# Reprise d'un import précédent
# ---------------------------------------------------------------------------

#: Écart, en mètres, en deçà duquel la coupe recalculée est tenue pour identique
#: à celle enregistrée, et le profil déjà relevé réutilisable. Le dixième de
#: mètre est bien en dessous du pas d'échantillonnage de 5 m : à cette distance,
#: le RGE ALTI rendrait les mêmes altitudes.
TOLERANCE_REPRISE_M = 0.1


@dataclass
class CoupeEnregistree:
    """Ce qu'un import précédent a laissé du travail de coupe.

    C'est le **tracé initial** qui est la donnée à conserver, pas la ligne
    corrigée : la correction dépend de l'azimut des tables et de l'emprise
    clôturée, qui changent si le BE fournit un nouvel indice. Rejouer la
    correction sur le tracé d'origine redonne une coupe juste ; recharger la
    ligne corrigée telle quelle la figerait sur un plan qui n'existe plus.
    """

    trace_initial: LineString
    #: La ligne corrigée telle qu'elle avait été enregistrée, pour savoir si le
    #: recalcul la déplace.
    geometrie_enregistree: LineString
    azimut_tables_deg: float
    manuel: bool
    profil: ProfilTerrain | None


def coupe_enregistree(donnees: dict | None) -> CoupeEnregistree | None:
    """Extrait la coupe d'une sortie d'import relue, ou None s'il n'y en a pas."""
    if not donnees:
        return None
    brut = donnees.get("ligne_coupe")
    if not isinstance(brut, dict):
        return None

    trace = _ligne_depuis_coordonnees(brut.get("trace_initial_l93"), "trace_initial_l93")
    enregistree = _ligne_depuis_coordonnees(
        brut.get("coordonnees_l93"), "coordonnees_l93"
    )
    if trace is None or enregistree is None:
        raise ErreurCoupe(
            "La sortie précédente porte une ligne de coupe incomplète : le tracé "
            "ne peut pas être repris. Retracez la coupe."
        )
    return CoupeEnregistree(
        trace_initial=trace,
        geometrie_enregistree=enregistree,
        azimut_tables_deg=float(brut.get("azimut_tables_deg", 0.0)),
        manuel=not bool(brut.get("corrigee", True)),
        profil=profil_enregistre(donnees),
    )


def _ligne_depuis_coordonnees(brut, champ: str) -> LineString | None:
    if not isinstance(brut, list) or len(brut) < 2:
        return None
    try:
        return LineString([(float(x), float(y)) for x, y, *_ in brut])
    except (TypeError, ValueError) as exc:
        raise ErreurCoupe(
            f"Le champ « {champ} » de la sortie précédente n'est pas une suite "
            f"de coordonnées : {exc}"
        ) from exc


def profil_enregistre(donnees: dict | None) -> ProfilTerrain | None:
    """Profil relevé lors d'un import précédent, ou None."""
    if not donnees:
        return None
    brut = donnees.get("profil_terrain")
    if not isinstance(brut, dict):
        return None
    points = brut.get("points")
    if not isinstance(points, list) or len(points) < 2:
        return None
    try:
        couples = [(float(s), float(z)) for s, z in points]
    except (TypeError, ValueError) as exc:
        raise ErreurCoupe(
            f"Le profil de la sortie précédente est illisible : {exc}"
        ) from exc
    return ProfilTerrain(
        abscisses_m=[s for s, _ in couples],
        altitudes_m=[z for _, z in couples],
        origine=str(brut.get("origine", "import précédent")),
        pas_m=float(brut.get("pas_m", PAS_ECHANTILLONNAGE_M)),
    )


def reprendre_coupe(
    enregistree: CoupeEnregistree,
    azimut_tables_deg: float,
    emprise_cloturee: BaseGeometry,
    marge_m: float = MARGE_COUPE_M,
    tables: list[BaseGeometry] | None = None,
) -> tuple[LigneCoupe, bool]:
    """Rejoue la correction sur le tracé conservé, avec le plan d'aujourd'hui.

    Renvoie la coupe et un booléen disant si le profil enregistré reste
    utilisable — c'est-à-dire si la ligne recalculée tombe au même endroit. Un
    nouvel indice qui tourne les tables ou déplace la clôture déplace la coupe,
    et le profil doit alors être relevé à nouveau plutôt que réutilisé sous une
    ligne qui a bougé.
    """
    coupe = corriger_ligne_coupe(
        enregistree.trace_initial,
        azimut_tables_deg,
        emprise_cloturee,
        marge_m=marge_m,
        manuel=enregistree.manuel,
        tables=tables,
    )
    ecart = float(
        coupe.geometrie.hausdorff_distance(enregistree.geometrie_enregistree)
    )
    inchangee = ecart <= TOLERANCE_REPRISE_M
    coupe.avertissements.insert(
        0,
        "Tracé de coupe repris de l'import précédent."
        if inchangee
        else f"Tracé de coupe repris de l'import précédent, mais la ligne "
        f"corrigée s'est déplacée de {ecart:.1f} m : l'azimut des tables ou "
        "l'emprise clôturée ont changé depuis. Le profil du terrain est relevé "
        "à nouveau.",
    )
    return coupe, inchangee


# ---------------------------------------------------------------------------
# Contrôle de cohérence altimétrique
# ---------------------------------------------------------------------------


@dataclass
class CoherenceAltimetrique:
    """Comparaison du profil du terrain aux altitudes des tables du DXF."""

    nb_tables_comparees: int
    ecart_median_m: float | None
    ecart_min_m: float | None
    ecart_max_m: float | None
    conforme: bool
    message: str


def controler_coherence(
    profil: ProfilTerrain,
    ligne: LigneCoupe | LineString,
    tables: list[BaseGeometry],
    seuil_m: float = ECART_ALTIMETRIQUE_MAX_M,
    distance_max_m: float = DISTANCE_TABLE_COUPE_M,
) -> CoherenceAltimetrique:
    """Recoupe le profil du terrain avec le bord bas des tables voisines.

    Le Z des tables est celui du plan des modules, pas celui du sol : le bord
    bas se tient au-dessus du terrain de la garde au sol de la structure. Ce
    contrôle ne cherche donc pas l'égalité, mais un décalage de référentiel
    altimétrique, qui se compte en dizaines de mètres. C'est la médiane des
    écarts qui est comparée au seuil, pour qu'une table isolée ne le déclenche
    pas.
    """
    geometrie = ligne.geometrie if isinstance(ligne, LigneCoupe) else ligne
    ecarts = []
    for table in tables:
        if not table.has_z:
            continue
        centre = table.centroid
        if centre.distance(geometrie) > distance_max_m:
            continue
        z_bas = min(c[2] for c in table.exterior.coords)
        ecarts.append(z_bas - profil.altitude_a(float(geometrie.project(centre))))

    if not ecarts:
        return CoherenceAltimetrique(
            0,
            None,
            None,
            None,
            False,
            f"Aucune table à moins de {distance_max_m:g} m de la ligne de coupe : "
            "la cohérence du profil avec les altitudes du DXF n'a pas pu être "
            "contrôlée.",
        )

    median = statistics.median(ecarts)
    conforme = abs(median) <= seuil_m
    return CoherenceAltimetrique(
        nb_tables_comparees=len(ecarts),
        ecart_median_m=median,
        ecart_min_m=min(ecarts),
        ecart_max_m=max(ecarts),
        conforme=conforme,
        message=(
            f"{len(ecarts)} tables comparées : le bord bas des tables se tient "
            f"{median:+.2f} m au-dessus du terrain ({min(ecarts):+.2f} à "
            f"{max(ecarts):+.2f} m). Cohérent avec la garde au sol de la structure."
            if conforme
            else f"{len(ecarts)} tables comparées : écart systématique de "
            f"{median:+.2f} m entre le bord bas des tables et le profil du "
            f"terrain, au-delà des {seuil_m:g} m admis. Les deux jeux de données "
            "ne sont probablement pas dans le même référentiel altimétrique."
        ),
    )


# ---------------------------------------------------------------------------
# Contrôle du profil par les altitudes embarquées dans le DXF
# ---------------------------------------------------------------------------

#: Écart médian admis entre le profil du RGE ALTI et une source d'altitude
#: embarquée dans le DXF, en mètres.
#:
#: Deux modèles du même terrain doivent s'accorder bien mieux que le terrain ne
#: s'accorde avec le bas des tables : 25 cm sépare l'imprécision d'un relevé
#: d'un décalage de référentiel. Mesuré sur Sarnois le 03/09/2026, ce seuil
#: laisse passer les points cotés du géomètre (-0,13 m) et le maillage bâti sur
#: eux (-0,14 m), et attrape le terrain téléchargé par PVcase (-0,80 m).
ECART_TERRAIN_BE_MAX_M = 0.25

#: Dispersion en deçà de laquelle un écart est tenu pour un décalage constant
#: du référentiel, et non pour du bruit de mesure, en mètres.
DISPERSION_DECALAGE_M = 0.15


@dataclass
class ControleTerrainBE:
    """Comparaison du profil RGE ALTI à une source d'altitude du DXF."""

    source: str
    nature: str
    nb_points: int
    ecart_median_m: float
    dispersion_m: float
    ecart_min_m: float
    ecart_max_m: float
    conforme: bool
    message: str


def controler_terrain_embarque(
    profil: ProfilTerrain,
    ligne: LigneCoupe | LineString,
    points_terrain: dict[str, list[tuple[float, float, float]]],
    natures: dict[str, str] | None = None,
    seuil_m: float = ECART_TERRAIN_BE_MAX_M,
    demi_couloir_m: float = DEMI_COULOIR_M,
) -> list[ControleTerrainBE]:
    """Recoupe le profil du RGE ALTI avec les altitudes portées par le DXF.

    Le profil de la coupe reste celui du RGE ALTI : c'est la référence
    altimétrique nationale, celle que l'instructeur du dossier peut vérifier.
    Les altitudes du DXF ne le remplacent pas, elles le **contrôlent** — et ce
    contrôle a de la valeur parce que les sources d'un même fichier se
    contredisent parfois entre elles.

    Chaque source est traitée séparément, et l'écart est qualifié : une
    dispersion faible autour d'une médiane non nulle est un décalage de
    référentiel, pas du bruit. C'est ce qui distingue un relevé imprécis d'un
    modèle pris dans un autre système altimétrique.
    """
    geometrie = ligne.geometrie if isinstance(ligne, LigneCoupe) else ligne
    natures = natures or {}
    resultats: list[ControleTerrainBE] = []

    for source, points in sorted(points_terrain.items()):
        ecarts = _ecarts_au_profil(profil, geometrie, points, demi_couloir_m)
        if len(ecarts) < 3:
            continue
        median = statistics.median(ecarts)
        dispersion = statistics.pstdev(ecarts)
        conforme = abs(median) <= seuil_m
        nature = natures.get(source, "source d'altitude du DXF")
        if conforme:
            message = (
                f"« {source} » ({nature}) : {len(ecarts)} points comparés, écart "
                f"médian de {median:+.2f} m au RGE ALTI, dispersion {dispersion:.2f} m. "
                "Les deux décrivent le même terrain."
            )
        elif dispersion <= DISPERSION_DECALAGE_M:
            message = (
                f"« {source} » ({nature}) : {len(ecarts)} points comparés, "
                f"{median:+.2f} m par rapport au RGE ALTI pour une dispersion de "
                f"seulement {dispersion:.2f} m. C'est le même terrain à un "
                "décalage constant près, donc un référentiel altimétrique "
                "différent, pas une imprécision de relevé. Le profil du dossier "
                "reste celui du RGE ALTI."
            )
        else:
            message = (
                f"« {source} » ({nature}) : {len(ecarts)} points comparés, écart "
                f"médian de {median:+.2f} m au RGE ALTI, dispersion {dispersion:.2f} m "
                f"(de {min(ecarts):+.2f} à {max(ecarts):+.2f} m). Les deux "
                "décrivent des terrains différents. Le profil du dossier reste "
                "celui du RGE ALTI."
            )
        resultats.append(
            ControleTerrainBE(
                source=source,
                nature=nature,
                nb_points=len(ecarts),
                ecart_median_m=median,
                dispersion_m=dispersion,
                ecart_min_m=min(ecarts),
                ecart_max_m=max(ecarts),
                conforme=conforme,
                message=message,
            )
        )
    return resultats


def _ecarts_au_profil(
    profil: ProfilTerrain,
    ligne: LineString,
    points: list[tuple[float, float, float]],
    demi_couloir_m: float,
) -> list[float]:
    """Écarts point à profil, dans le couloir de la coupe.

    Même couloir que pour un relevé fourni en repli : comparer des points
    éloignés de la coupe reviendrait à comparer deux endroits du terrain.
    """
    minx, miny, maxx, maxy = ligne.bounds
    ecarts = []
    for x, y, z in points:
        if not (
            minx - demi_couloir_m <= x <= maxx + demi_couloir_m
            and miny - demi_couloir_m <= y <= maxy + demi_couloir_m
        ):
            continue
        point = Point(x, y)
        if ligne.distance(point) > demi_couloir_m:
            continue
        ecarts.append(z - profil.altitude_a(float(ligne.project(point))))
    return ecarts
