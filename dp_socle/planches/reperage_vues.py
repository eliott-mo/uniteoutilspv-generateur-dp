"""Plan de repérage des prises de vue, commun à DP 6, DP 7 et DP 8 (lot 6).

Il répond à une seule question : d'où la photographie d'à côté a-t-elle été
prise, et — quand on le sait vraiment — que regarde-t-elle ?

CE QUI DOIT TENIR DANS LE CADRE, ET CE QUI PEUT EN SORTIR
----------------------------------------------------------
Le brief du lot exigeait que le cadre couvre l'emprise clôturée **et** tous les
points de vue. Cette exigence est levée (décision du 14/09/2026) : un point de
vue de DP 8 peut être à plusieurs kilomètres, et tout faire tenir réduirait le
site à un timbre-poste où l'on ne repère plus rien. Le lecteur qui veut voir le
site en entier a DP 2.

Ce qui reste impératif, et que `zone_de_reperage` garantit :

- **tous les points de vue de la pièce** — sans eux la planche ne repère rien ;
- **le centre du site**, pour que la relation entre les deux se lise.

L'emprise complète est visée d'abord, et son débordement est écrit au rapport
plutôt que payé par une échelle qui rend la planche inutile. C'est le même
arbitrage que le plan de repérage de DP 4, qui a dû prolonger sa liste
d'échelles, à ceci près qu'ici c'est le cadrage qui cède, pas l'échelle.

LA SYMBOLISATION, ET SON ÉCART ASSUMÉ AU DOSSIER DE RÉFÉRENCE
---------------------------------------------------------------
Mesuré le 15/09/2026 dans le flux vectoriel de la DP 7 de Massay : autour de
l'étiquette « PC7-1 », il n'y a que trois points de tracé formant un segment
vertical de 8 pt. HOCH ne dessine donc **ni cône ni triangle** — une étiquette,
un trait de rappel, rien d'autre. Le flux ne porte aucun pointillé.

Le cône est donc un ajout volontaire. Il reprend le marqueur de
`photos-geoloc` — secteur de 50°, taille fixe — que le chef de projet a déjà
sous les yeux dans l'outil voisin : il dit d'où l'on regarde et vers où, ce
qu'une étiquette seule ne dit pas, sans prétendre à une portée ni à un champ de
vue mesuré. Deux états, et deux seulement :

| Ce qu'on sait                    | Ce qui est dessiné           |
|----------------------------------|------------------------------|
| la position seule                | repère et étiquette          |
| position et direction confirmée  | + cône orienté               |
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin

from ..erreurs import ErreurPointDeVue
from ..planche import Planche, Style
from ..points_de_vue import PointDeVue
from .primitives import echelle_du_dessin

#: Échelles admises pour un plan de repérage de prise de vue.
#:
#: Relevées sur le dossier de référence le 10/09/2026 : 1/1 500 pour les deux
#: DP 6, 1/2 500 pour la DP 7, 1/6 500 pour la DP 8. HOCH cadre sur son contenu
#: sans liste ; nous restons sur une liste, comme au lot 4, et le 1/6 500 tombe
#: alors sur le 1/7 500.
#:
#: La liste s'arrête au 1/10 000, qui couvre 1,68 km dans la colonne de gauche.
#: Elle avait été prolongée au 1/20 000 le 15/09/2026, sur la foi du brief qui
#: annonçait des points de vue « à plusieurs kilomètres » pour DP 8 ; la mesure
#: de l'usage le dément (16/09/2026) : ces prises de vue se font à quelques
#: centaines de mètres du site, un gros kilomètre au plus. Deux crans de plus
#: n'auraient donc jamais servi qu'à sortir en silence une planche où le site
#: n'occupe plus que seize millimètres, au lieu de signaler une position
#: douteuse.
ECHELLES_REPERAGE_VUES = (1000, 1500, 2000, 2500, 5000, 7500, 10000)

#: Marge autour du contenu utile, en part de sa plus grande dimension. Le cadre
#: **tracé** est ce qu'on mesure, marge comprise : c'est la leçon du lot 4, où
#: une zone sous le seuil débordait une fois sa marge posée.
MARGE_REPERAGE = 0.08

#: Rayon du disque de repère, en millimètres sur la planche.
RAYON_REPERE_MM = 2.4

#: Ouverture du cône de visée, en degrés, et son rayon rapporté à celui du
#: repère. Repris tels quels du marqueur de `photos-geoloc`
#: (`generation_html.py:1379`, secteur de 50° et rayon de 30 px pour une pastille
#: de 9) : le chef de projet voit le même symbole des deux côtés.
#:
#: C'est un **symbole d'orientation**, pas un champ de vue mesuré : il dit d'où
#: l'on regarde et vers où, ce qui est tout ce que la pièce demande. La décision
#: du 16/09/2026 écarte le calcul de focale que D6 prescrivait — avec lui
#: partent la question du rognage 9:16, l'ambiguïté de la convention
#: `FocalLengthIn35mmFilm`, et le cas des photographies qui n'annoncent aucune
#: focale, soit une sur cinq du jeu de validation.
OUVERTURE_CONE_DEG = 50.0
RAYON_CONE_MM = 8.0

_NOIR = "#1a1a1a"
_BLANC = "#ffffff"

#: Teinte des visées. Le magenta ne figure pas dans la palette des ouvrages
#: (vérifié le 15/09/2026 dans `palette.STYLES`) : un cône ne peut donc pas se
#: confondre avec une catégorie du plan.
_VISEE = "#d81b8c"


@dataclass(frozen=True)
class Reperage:
    """Ce qu'un plan de repérage a retenu, pour le cartouche et le rapport."""

    denominateur: int
    #: Cadre couvert, en Lambert 93 : (minx, miny, maxx, maxy).
    cadre: tuple[float, float, float, float]
    #: Vrai si l'emprise du site y tient en entier.
    site_entier: bool
    avertissements: tuple[str, ...] = ()

    @property
    def centre(self) -> tuple[float, float]:
        minx, miny, maxx, maxy = self.cadre
        return ((minx + maxx) / 2.0, (miny + maxy) / 2.0)


def repere_de_vue(code: str, rang: int) -> str:
    """L'étiquette d'une prise de vue, dans la langue du dossier de référence.

    Relevé le 15/09/2026 sur Massay : DP 6 nomme ses vues par lettres — « Vue A »
    page 12, « Vue B » page 13, une planche chacune — tandis que DP 7 et DP 8
    numérotent leurs points sur une planche unique, « PC7-1 », « PC7-2 »,
    « PC8-1 », « PC8-2 ». Les services instructeurs sont habitués à cette
    seconde forme, et c'est elle qui a présidé aux intitulés de `dossier.py`.

    La numérotation repart de 1 à chaque pièce : celle du rapport de visite
    compte tous les points de la visite et n'a pas le même sens dans le dossier.
    """
    if rang < 1:
        raise ErreurPointDeVue(
            f"Rang de prise de vue invalide ({rang}) : la numérotation d'une "
            "pièce commence à 1."
        )
    if code == "DP 6":
        # 26 vues sur un dossier est déjà invraisemblable ; au-delà, le repère
        # deviendrait faux en silence.
        if rang > 26:
            raise ErreurPointDeVue(
                f"{rang} vues pour DP 6 : la nomenclature par lettres du dossier "
                "de référence s'arrête à Z."
            )
        return f"Vue {chr(ord('A') + rang - 1)}"
    return f"PC{code.split()[-1]}-{rang}"


def zone_de_reperage(
    points_de_vue, emprise, avertissements: list | None = None
) -> tuple:
    """Cadre à couvrir, et si l'emprise du site y tient en entier.

    L'emprise complète est visée d'abord. Quand les points de vue sont trop
    éloignés pour que l'ensemble tienne à une échelle utile, c'est l'emprise qui
    cède : le cadre garde tous les points de vue et le centre du site, et le
    débordement part au rapport.

    Le renoncement est **mesuré, pas choisi d'avance** : on ne sait qu'après le
    choix d'échelle si l'ensemble tenait. `plan_de_reperage` enchaîne donc les
    deux, et cette fonction rend les deux zones candidates.
    """
    from shapely.geometry import box

    messages = [] if avertissements is None else avertissements
    vues = list(points_de_vue)
    if not vues:
        raise ErreurPointDeVue(
            "Aucun point de vue à reporter : un plan de repérage sans prise de "
            "vue ne repère rien."
        )
    if emprise is None or emprise.is_empty:
        raise ErreurPointDeVue(
            "Aucune emprise à montrer sous les points de vue : le plan de "
            "repérage ne situerait rien."
        )

    xs = [vue.x for vue in vues]
    ys = [vue.y for vue in vues]
    e_minx, e_miny, e_maxx, e_maxy = emprise.bounds
    centre_site = ((e_minx + e_maxx) / 2.0, (e_miny + e_maxy) / 2.0)

    complet = _avec_marge(
        min(xs + [e_minx]), min(ys + [e_miny]), max(xs + [e_maxx]), max(ys + [e_maxy])
    )
    minimal = _avec_marge(
        min(xs + [centre_site[0]]),
        min(ys + [centre_site[1]]),
        max(xs + [centre_site[0]]),
        max(ys + [centre_site[1]]),
    )
    return box(*complet), box(*minimal), messages


def _avec_marge(minx, miny, maxx, maxy) -> tuple:
    """Boîte élargie de `MARGE_REPERAGE`, jamais dégénérée.

    Un seul point de vue au centre du site donnerait une boîte plate, et une
    échelle infinie : le plancher de 1 m tient la boîte ouverte.
    """
    largeur = max(maxx - minx, 1.0)
    hauteur = max(maxy - miny, 1.0)
    marge = MARGE_REPERAGE * max(largeur, hauteur)
    return (minx - marge, miny - marge, maxx + marge, maxy + marge)


def plan_de_reperage(
    points_de_vue, emprise, zone_mm: tuple, libelle: str = "plan de repérage"
) -> Reperage:
    """Choisit le cadre et l'échelle du plan de repérage, dans cet ordre.

    On tente d'abord de faire tenir le site entier. Si aucune échelle de la
    liste n'y suffit, on retombe sur le cadre minimal — tous les points de vue,
    plus le centre du site — et on le dit. Si celui-là ne tient pas davantage,
    c'est que le point de vue est à une distance qui n'est plus celle d'une
    photographie du site : la planche refuse plutôt que de sortir de la liste.
    """
    avertissements: list[str] = []
    complet, minimal, _ = zone_de_reperage(points_de_vue, emprise, avertissements)

    for cadre, site_entier in ((complet, True), (minimal, False)):
        minx, miny, maxx, maxy = cadre.bounds
        denominateur = _echelle_ou_rien(
            maxx - minx, maxy - miny, zone_mm, libelle
        )
        if denominateur is None:
            continue
        if not site_entier:
            avertissements.append(
                f"{libelle} : le site ne tient pas en entier dans le cadre à "
                f"côté de points de vue aussi éloignés. Le cadre garde toutes "
                "les prises de vue et le centre du site ; c'est DP 2 qui montre "
                "le site en entier."
            )
        return Reperage(
            denominateur=denominateur,
            cadre=(minx, miny, maxx, maxy),
            site_entier=site_entier,
            avertissements=tuple(avertissements),
        )

    minx, miny, maxx, maxy = minimal.bounds
    raise ErreurPointDeVue(
        f"{libelle} : même réduit aux prises de vue et au centre du site, le "
        f"cadre mesure {maxx - minx:.0f} x {maxy - miny:.0f} m et ne tient à "
        f"aucune échelle de la liste (jusqu'au 1/{ECHELLES_REPERAGE_VUES[-1]}). "
        "Vérifiez la position des points de vue : à cette distance, ce n'est "
        "plus une photographie de ce site."
    )


def _echelle_ou_rien(largeur_m, hauteur_m, zone_mm, libelle) -> int | None:
    """L'échelle retenue, ou `None` si aucune de la liste ne convient."""
    from ..erreurs import ErreurEchelle

    try:
        return echelle_du_dessin(
            max(largeur_m, 1.0),
            max(hauteur_m, 1.0),
            zone_mm,
            ECHELLES_REPERAGE_VUES,
            libelle=libelle,
        )
    except ErreurEchelle:
        return None


# ---------------------------------------------------------------------------
# Le dessin
# ---------------------------------------------------------------------------


def dessiner_points_de_vue(planche: Planche, points_de_vue, reperes) -> list:
    """Pose les repères, leurs étiquettes et leurs cônes d'orientation.

    `reperes` porte l'étiquette de chaque point de vue, dans le même ordre.

    L'ordre du dessin compte : tous les cônes d'abord, tous les repères ensuite.
    Un cône passant par-dessus un repère voisin le masquerait, et deux prises de
    vue depuis le même endroit sont le cas courant — cinq points du rapport de
    Sarnois tiennent dans un mouchoir de poche.
    """
    vues = list(points_de_vue)
    reperes = list(reperes)
    if len(vues) != len(reperes):
        raise ErreurPointDeVue(
            f"{len(vues)} point(s) de vue pour {len(reperes)} repère(s) : la "
            "planche ne saurait pas lequel nommer comment."
        )

    messages = []
    for vue, repere in zip(vues, reperes):
        if vue.dessine_un_cone:
            _tracer_cone(planche, vue)
        else:
            messages.append(
                f"{repere} : aucune direction confirmée — le repère est posé "
                "seul, sans cône d'orientation."
            )
    for vue, repere in zip(vues, reperes):
        _tracer_repere(planche, vue, repere)
    return messages


def _rayon_terrain(planche: Planche, rayon_mm: float) -> float:
    """Convertit un rayon voulu sur le papier en rayon terrain.

    Repères et cônes se dessinent en unités terrain pour suivre la
    transformation de la planche, mais leur taille est voulue **en
    millimètres** : ce sont des symboles de lecture, pas des objets du site. Ils
    gardent donc le même encombrement du 1/1 000 au 1/10 000.
    """
    return rayon_mm * planche.echelle / 1000.0


def _tracer_cone(planche: Planche, vue: PointDeVue) -> None:
    """Le secteur d'orientation, à l'ouverture et à la taille du marqueur voisin.

    Il ne prétend ni à une portée ni à un champ de vue : c'est le symbole que le
    chef de projet voit déjà sur la carte de `photos-geoloc`, transposé sur la
    planche. Voir `OUVERTURE_CONE_DEG`.
    """
    from shapely.geometry import Polygon

    axe = vue.cap_trigonometrique_deg
    demi = OUVERTURE_CONE_DEG / 2.0
    rayon_m = _rayon_terrain(planche, RAYON_CONE_MM)
    sommets = [(vue.x, vue.y)]
    # Un pas par degré de corde : assez pour que l'arc ne se lise pas comme un
    # triangle, sans alourdir le SVG.
    pas = max(3, int(OUVERTURE_CONE_DEG))
    for i in range(pas + 1):
        angle = radians(axe - demi + OUVERTURE_CONE_DEG * i / pas)
        sommets.append((vue.x + rayon_m * cos(angle), vue.y + rayon_m * sin(angle)))
    planche.ajouter_geometrie(
        Polygon(sommets),
        Style(trait=_VISEE, epaisseur_mm=0.3, remplissage=_VISEE,
              opacite_remplissage=0.55),
    )


def _tracer_repere(planche: Planche, vue: PointDeVue, repere: str) -> None:
    """Le disque numéroté, posé en dernier pour rester lisible.

    Le disque est dessiné en unités terrain pour suivre la transformation de la
    planche, mais sa taille est voulue **en millimètres** : c'est un symbole de
    lecture, pas un objet du site. Il garde donc le même diamètre quelle que
    soit l'échelle, du 1/1 000 au 1/10 000.
    """
    from shapely.geometry import Point

    rayon_m = _rayon_terrain(planche, RAYON_REPERE_MM)
    planche.ajouter_geometrie(
        Point(vue.x, vue.y).buffer(rayon_m, quad_segs=16),
        Style(trait=_NOIR, epaisseur_mm=0.4, remplissage=_BLANC),
    )
    # Le décalage de l'étiquette est demandé **en millimètres** plutôt que posé
    # en coordonnées terrain : il reste ainsi le même du 1/1 000 au 1/10 000,
    # là où un décalage terrain collerait l'étiquette au repère à petite échelle
    # et l'en éloignerait à grande. Négatif, car l'axe du papier descend.
    planche.ajouter_etiquettes(
        [(vue.x, vue.y)],
        [repere],
        style={
            "taille_mm": 2.3,
            "couleur": _NOIR,
            "gras": True,
            "halo": True,
            "decalage_mm": -(RAYON_REPERE_MM + 1.4),
        },
    )


