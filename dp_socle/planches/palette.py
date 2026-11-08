"""Palette et légende des planches du dossier (lot 4).

À ne pas confondre avec `dp_socle.apercu_be.STYLES`, qui est la palette de
l'**image de contrôle à l'écran** du lot 2bis. Celle-ci est celle du **dossier
imprimé**, et les deux n'ont pas les mêmes contraintes : à l'écran on zoome, sur
une épreuve A3 un poste de 12 x 3 m au 1/1 000 fait 12 x 3 mm.

Deux familles de teintes, et elles ne se traitent pas pareil (décision D4) :

- les **relevées** le sont au pixel sur la planche DP 2 du dossier HOCH « Les
  Islettes » du 25/04/2024. Elles sont reprises telles quelles : c'est le
  document que l'instructeur a l'habitude de voir. Deux d'entre elles se
  confondent — `plateforme` et `piste_legere` partagent le gris 215 — et c'est
  un fait du document de référence, pas une décision de ce lot ; le filet les
  distingue, et la légende porte deux entrées.
- les **dérivées** ne figurent sur aucune planche de référence, faute d'ouvrage
  correspondant. Celles du contrat sont celles d'une image d'écran : elles sont
  refaites ici, et le critère est mesuré — `tests/test_palette_dp.py` vérifie
  que deux catégories pouvant se retrouver sur la même planche restent
  distinguables. Le seuil est un écart perceptuel, pas une impression.

Réserve, notée le 04/09/2026 : le brief demande de s'approcher de la convention
UNITe des annexes de demande d'examen au cas par cas pour le BESS, le bac de
rétention et le local technique. Ces annexes ne sont pas dans le dépôt et n'ont
pas pu être consultées. L'orangé du BESS, seul indice disponible, vient du
contrat et est conservé ; les deux autres sont construites sur le seul critère
mesurable ici, la distinguabilité à l'impression. À reprendre sur pièce.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from dataclasses import dataclass as _dataclass

from shapely.ops import unary_union

from ..erreurs import ErreurComposition
from ..planche import (
    REF_PISTE_A_CREER,
    REF_POINTS_STATIONNEMENT,
    STYLE_BATIMENT,
    STYLE_PARCELLE,
    Style,
)
from .primitives import union_valide

#: Écart perceptuel minimal entre deux teintes susceptibles de se retrouver sur
#: la même planche, en ΔE CIE76.
#:
#: 12 : au-delà de « perceptible d'un coup d'œil » (ΔE ≈ 5) et assez large pour
#: tenir sur une épreuve papier, où l'encre étale et où l'objet fait quelques
#: millimètres. Le seuil ne s'applique qu'aux paires dont au moins une teinte
#: est dérivée : une collision entre deux relevées est héritée du dossier de
#: référence et ne se corrige pas ici.
ECART_MINIMAL = 12.0


@_dataclass(frozen=True)
class EntreeDP:
    """Une entrée de légende : son intitulé, son style, et son symbole."""

    libelle: str
    style: Style
    symbole: str = "surface"


@dataclass(frozen=True)
class StyleDP:
    """Style d'une catégorie sur les planches du dossier."""

    libelle: str
    #: Rang de dessin du contrat. Il ordonne le tracé et, à l'identique, la
    #: légende : une légende dans un autre ordre que le dessin se relit mal.
    rang: int
    style: Style
    #: Vrai si la teinte est relevée au pixel sur le dossier de référence.
    relevee: bool = False
    #: Catégorie dessinée sur le plan de masse (DP 2).
    dessinee: bool = True
    #: Symbole de légende, parmi ceux de `dp_socle.planches.legende`. Une
    #: surface se lit comme un aplat, un linéaire comme un trait, un portail
    #: comme un portail : le rectangle du moteur les confondait tous.
    symbole: str = "surface"
    #: Matière du sol, quand plusieurs catégories décrivent le **même**
    #: revêtement sous des statuts différents — une voie lourde existante, une
    #: à créer et une aire de grutage sont la même grave compactée. Elles
    #: partagent donc délibérément leur teinte, et ce sont leur filet et leur
    #: intitulé qui portent la distinction. Le critère d'écart perceptuel ne
    #: s'applique pas entre elles : les séparer reviendrait à faire croire à
    #: trois revêtements là où il n'y en a qu'un.
    matiere: str | None = None


def _remplie(couleur: str, filet: str, epaisseur: float = 0.2) -> Style:
    return Style(trait=filet, epaisseur_mm=epaisseur, remplissage=couleur)


#: Styles du dossier, par catégorie du contrat.
#:
#: `libelle` est l'intitulé de légende. Deux catégories peuvent délibérément
#: partager le même : elles ne produisent alors qu'une entrée (décision D3).
STYLES = {
    # -- surfaces de sol ----------------------------------------------------
    # Écartée du dossier depuis le 26/09/2026 — voir `EXCLUES`. Le style reste
    # pour l'aperçu de calage, qui montre ce que l'export contient, et pour que
    # la catégorie garde un intitulé là où on la nomme.
    #
    # Dérivée : le gris 215 du contrat est celui de la plateforme et de la
    # piste légère, deux relevées, et aucun gris clair ne s'en distingue assez.
    # Une zone évitée n'est pas une surface aménagée mais une surface qu'on
    # s'interdit : contour tireté sans remplissage, comme se dessine une
    # servitude. Elle se lit alors sous les ouvrages qui la bordent.
    "zone_evitee": StyleDP(
        "Zone évitée", 1,
        Style(trait="#6a7a52", epaisseur_mm=0.35, remplissage="none",
              tirets="2.2 1.2"),
        symbole="tirete",
    ),
    # Les trois gris de sol s'étagent du plus clair au plus sombre, dans
    # l'ordre de la portance : plateforme, piste légère, voie lourde. C'est un
    # écart délibéré à D4, demandé à la relecture du 05/09/2026 — le dossier de
    # référence donne le **même** gris 215 à la plateforme et à la piste
    # légère, et sur nos planches les deux se touchent constamment. Les valeurs
    # relevées étaient #d7d7d7 et #a2a2a2 ; les nouvelles gardent leur ordre et
    # leur famille, et sont séparées d'au moins 12 unités ΔE deux à deux.
    "plateforme": StyleDP(
        "Plateforme", 2, _remplie("#e4e4e4", "#6e6e6e")
    ),
    # Le béton déjà en place, que le bureau d'études appelle « chemin
    # existant » et dessine en jaune. Ce n'est ni de la grave compactée ni un
    # ouvrage du projet : c'est l'état du terrain, et le tableau bilan ne le
    # compte pas — mesuré sur Saint-Cyr IND07 le 29/09/2026, 3 362 m² de voie
    # lourde au plan pour 3 365 déclarés, chemins exclus des deux côtés.
    #
    # La teinte n'est pas un gris : les trois gris de sol occupent déjà toute
    # la bande neutre, et aucun quatrième ne tient les 12 ΔE du critère —
    # balayé le 29/09/2026, le meilleur neutre clair plafonne à 10,5. Le jaune
    # est celui sous lequel le chef de projet et le bureau d'études lisent déjà
    # ces chemins sur leur plan, et il tient le critère avec 17,8.
    "chemin_existant": StyleDP(
        "Chemin existant", 3, _remplie("#ddc44f", "#8a6f1e")
    ),
    # L'intitulé est celui de la légende du plan du bureau d'études, relevé sur
    # le PDF de Saint-Cyr le 04/09/2026 : « Piste lourde existante (à renforcer
    # si nécessaire) ». Le renforcement d'une piste existante n'est pas la
    # création d'une piste, et c'est la distinction qui compte à l'instruction.
    "piste_lourde_existante": StyleDP(
        "Piste lourde existante (à renforcer si nécessaire)", 4,
        _remplie("#979797", "#6e6e6e"), matiere="voie_lourde",
    ),
    # Même gris que l'existante — c'est la même grave compactée — et une
    # hachure par-dessus. Le filet seul ne suffisait pas : 0,2 mm de noir
    # contre 0,2 mm de gris moyen, et deux pastilles de légende identiques.
    "piste_lourde_a_creer": StyleDP(
        "Piste lourde à créer", 5,
        Style(trait="#000000", epaisseur_mm=0.2, remplissage="#979797",
              hachure=REF_PISTE_A_CREER),
        matiere="voie_lourde",
    ),
    "piste_legere": StyleDP(
        "Piste légère", 6, _remplie("#bdbdbd", "#8c8c8c")
    ),
    "piste_lourde": StyleDP(
        "Voie lourde", 7, _remplie("#979797", "#6e6e6e"), matiere="voie_lourde"
    ),
    # Même intitulé et même style que la voie lourde, délibérément : une aire de
    # grutage est un élargissement de voie, que le tableau bilan compte en
    # « supplément piste lourde » et que la légende du dossier ne distingue pas.
    # Une seule entrée en sort.
    "aire_grutage": StyleDP(
        "Voie lourde", 8, _remplie("#979797", "#6e6e6e"), matiere="voie_lourde"
    ),
    # Même revêtement que la voie lourde — même gris, même matière —, et c'est
    # le semis de points qui la distingue, les hachures étant prises par la
    # piste à créer. Demande du chef de projet du 02/10/2026 : une entrée de
    # légende à part, parce qu'une aire de stationnement n'est pas une voie et
    # que l'instruction lit la destination d'une surface autant que sa nature.
    "aire_stationnement": StyleDP(
        "Aire de stationnement", 9,
        Style(trait="#6e6e6e", epaisseur_mm=0.2, remplissage="#979797",
              hachure=REF_POINTS_STATIONNEMENT),
        matiere="voie_lourde",
    ),
    # Dérivée : le gris 215 du contrat la confondait avec la plateforme, dont
    # elle est toujours voisine. Bleu clair, comme l'ouvrage SDIS qu'elle sert.
    "aire_aspiration": StyleDP(
        "Aire d'aspiration", 10, _remplie("#c3dcef", "#3f7f9f")
    ),
    "espace_vert": StyleDP("Espace vert", 11, _remplie("#c9dfa8", "#7d9b55")),
    "arbre_existant": StyleDP(
        "Arbres existants", 12, _remplie("#5a8f4a", "#37592c"),
        symbole="vegetation",
    ),
    # Installations de chantier : temporaires. Elles ne sont ni dessinées ni
    # portées en légende (décision D3), et gardent un style pour le seul cas où
    # une planche de contrôle voudrait les montrer.
    "base_vie": StyleDP(
        "Base vie (chantier)", 13, _remplie("#e8d8be", "#967646"), dessinee=False
    ),
    "stockage_chantier": StyleDP(
        "Stockage logistique (chantier)", 14, _remplie("#e8d8be", "#967646"),
        dessinee=False,
    ),
    # Le symbole est une **bande**, et non le houppier bosselé des arbres : au
    # plan, une haie plantée est une bande continue de 2 m de large, et c'est
    # ainsi que le dossier de référence la dessine. Un houppier en légende pour
    # une bande au plan faisait chercher des arbres qui n'y sont pas.
    "haie": StyleDP(
        "Haie plantée", 15,
        Style(trait="#50780a", epaisseur_mm=0.4, remplissage="#6faa0b"),
        relevee=True, symbole="bande",
    ),
    # Dérivée : vert sombre, pour se lire contre la haie plantée sans lui
    # disputer sa teinte relevée.
    "haie_existante": StyleDP(
        "Haie existante", 16,
        Style(trait="#1e3a10", epaisseur_mm=0.4, remplissage="#2f5c18"),
        symbole="vegetation", matiere="haie_en_place",
    ),
    # La haie qui existe **et** qu'on complète : même vert que l'existante —
    # c'est la même haie — et le tiret dit le travail qu'on y fait. Demandé le
    # 30/09/2026 : le plan du bureau d'études légende « haie à crée » et
    # « haie à renforcer » séparément, et les confondre engageait le dossier
    # sur une plantation là où il y a un complètement.
    #
    # Un tiret et non une hachure : la hachure convient aux pistes, qui sont
    # des surfaces ; une haie se trace en ligne de 0,8 mm, où une hachure ne
    # se verrait pas. Le tiret dit la même chose sur un linéaire, et
    # `style_de` le reporte du remplissage au trait.
    "haie_a_renforcer": StyleDP(
        "Haie à renforcer", 17, Style(
            trait="#1e3a10", epaisseur_mm=0.4, remplissage="#2f5c18",
            tirets="2.4 1.2",
        ),
        matiere="haie_en_place", symbole="vegetation_tiretee",
    ),
    # -- structures ---------------------------------------------------------
    # Tables et modules décrivent le même ouvrage à deux niveaux de détail :
    # même teinte, même intitulé — celui du dossier de référence, « Panneaux
    # photovoltaïques » — donc une seule entrée de légende.
    "tables_pv": StyleDP(
        "Panneaux photovoltaïques", 18,
        Style(trait="#2c4a8a", epaisseur_mm=0.2, remplissage="#97caca"),
        relevee=True,
    ),
    "modules_pv": StyleDP(
        "Panneaux photovoltaïques", 19,
        Style(trait="#2c4a8a", epaisseur_mm=0.08, remplissage="#97caca"),
    ),
    # -- postes -------------------------------------------------------------
    "pdl_ptr": StyleDP(
        "Poste de livraison / transformation", 20, _remplie("#7fffbf", "#000000"),
        relevee=True,
    ),
    # Dérivées : trois postes distincts au tableau bilan, trois entrées de
    # légende au dossier. Le vert du PDL/PTR est relevé ; les deux autres s'en
    # écartent en clarté, ce qui reste lisible sur un objet de 12 x 3 mm.
    "ptr": StyleDP("Poste de transformation", 21, _remplie("#2f9e6a", "#000000")),
    "pdl": StyleDP("Poste de livraison", 22, _remplie("#d5f7e6", "#000000")),
    # Dérivée : le contrat lui donnait le vert du PDL/PTR, qu'elle ne peut pas
    # porter — les deux se côtoient sur le même plan. Un local technique n'est
    # pas un poste électrique : teinte neutre chaude.
    "local_technique": StyleDP(
        "Local technique", 23, _remplie("#cfc0a8", "#7a6a50")
    ),
    "bess": StyleDP("Conteneurs BESS", 24, _remplie("#ffcd78", "#8a5a10")),
    # Dérivée : le bac de rétention retient de l'huile, pas de l'eau. Le
    # cyan du contrat le confondait avec la citerne incendie, teinte relevée.
    "bac_retention": StyleDP(
        "Bac de rétention", 25, _remplie("#6e96b4", "#2f4d66")
    ),
    # Dérivée : cyan sombre, distinct de la citerne incendie (relevée, cyan
    # moyen) comme de la teinte des tables.
    "citerne_refroidissement": StyleDP(
        "Citerne de refroidissement", 26, _remplie("#1d7d99", "#0d3f4f")
    ),
    # Dérivée : orangé pâle, de la même famille que le BESS qu'elle dessert.
    "zone_remise": StyleDP("Zone de remise", 27, _remplie("#ffe6bb", "#8a5a10")),
    "bac_equarrissage": StyleDP(
        "Bac d'équarrissage", 28, _remplie("#a8703c", "#5c3c1e")
    ),
    "bache_incendie": StyleDP(
        "Citerne incendie", 29, _remplie("#3fbfbf", "#000000"), relevee=True
    ),
    # -- linéaires ----------------------------------------------------------
    "limite_paddock": StyleDP(
        "Limite de paddock", 30,
        Style(trait="#966e14", epaisseur_mm=0.3, remplissage="none",
              tirets="2.0 1.2"),
        symbole="ligne",
    ),
    # Dérivée : ocre franc. Le beige pâle du contrat se confondait avec la
    # zone de remise, dont elle ne partage ni la fonction ni la planche.
    "zone_contention": StyleDP(
        "Zone de contention", 31, _remplie("#d8bc72", "#7a5a10")
    ),
    # Tracés d'étude, exclus du dossier (décision D3) : seule la clôture
    # délimite le projet à l'instruction.
    "recul_implantation": StyleDP(
        "Recul d'implantation (étude)", 32,
        Style(trait="#c87828", epaisseur_mm=0.2, remplissage="none"),
        dessinee=False, symbole="tirete",
    ),
    "zone_implantation_pv": StyleDP(
        "Zone d'implantation (étude)", 33,
        Style(trait="#ff2d2d", epaisseur_mm=0.3, remplissage="none"),
        dessinee=False, symbole="tirete",
    ),
    # Un simple trait, comme sur le dossier de référence : au plan la clôture
    # **est** un trait rouge continu, et lui donner en légende un grillage sur
    # poteaux promettait un figuré que la planche ne porte pas.
    "cloture": StyleDP(
        "Clôture du projet solaire", 34,
        Style(trait="#ff0000", epaisseur_mm=0.5, remplissage="none"),
        relevee=True, symbole="ligne",
    ),
    # Le portail porte le rouge de la clôture, relevé, dont il est
    # l'interruption : ce qui l'en distingue au plan est son épaisseur, et
    # c'est aussi tout ce qui les sépare en légende — le pavé de légende du
    # moteur est un rectangle, et la clôture comme le portail sont rouges au
    # dossier de référence. Deux entrées, deux libellés, un même rouge.
    "portail": StyleDP(
        "Portail", 35,
        Style(trait="#ff0000", epaisseur_mm=0.9, remplissage="none"),
        relevee=True, symbole="portail",
    ),
    # Dérivée : rouge sombre et tireté, pour ne pas se lire comme le portail
    # d'accès, que seul le tableau bilan compte.
    "portail_exploitant": StyleDP(
        "Portail d'exploitation", 36,
        Style(trait="#8a0000", epaisseur_mm=0.45, remplissage="none",
              tirets="1.4 0.8"),
        symbole="portail",
    ),
}

#: Catégories écartées du dossier, et pourquoi (décision D3). Elles ne sont ni
#: dessinées ni portées en légende.
EXCLUES = {
    "base_vie": "installation de chantier, temporaire",
    "stockage_chantier": "installation de chantier, temporaire",
    "zone_implantation_pv": "contour d'étude ; seule la clôture délimite le projet",
    "recul_implantation": "contour d'étude ; seule la clôture délimite le projet",
    # Le calque « Keepouts » de l'export HelioScope, et lui seul : les trois
    # producteurs du contrat, seul le lot 2 l'écrit. Ce n'est pas une servitude
    # ni une surface qu'on s'interdit, comme le laissait croire l'intitulé
    # « Zone évitée » : c'est la **réservation** que le chef de projet pose
    # dans HelioScope pour garder la place des locaux techniques, afin que le
    # calepinage n'y mette pas de modules. Les ouvrages qu'elle annonce sont
    # ensuite dessinés pour eux-mêmes, avec leurs cotes ; la réservation, elle,
    # n'existe pas sur le terrain et n'a rien à faire sur une planche
    # d'instruction (relevé sur un dossier de chef de projet le 26/09/2026).
    "zone_evitee": "réservation posée dans HelioScope pour les locaux "
    "techniques ; pas un élément du projet",
}

#: Catégories qui ne se dessinent jamais sous leur propre nom.
#:
#: `voirie` n'est pas une catégorie de dessin : c'est une question posée au chef
#: de projet, qui la rattache à la voie lourde ou à la piste légère (D5). Elle
#: n'a donc ni teinte ni entrée de légende propre.
SANS_STYLE = ("voirie", "ligne_coupe")

#: Entrées de légende venues du WFS IGN et non du contrat, comme chez HOCH.
#: Elles précèdent les catégories du projet : c'est l'ordre du dessin.
LIBELLE_PARCELLE = "Limite de parcelle"
LIBELLE_BATIMENT = "Bâtiment"
SYMBOLE_PARCELLE = "ligne"
SYMBOLE_BATIMENT = "surface"
RANG_PARCELLE = -2
RANG_BATIMENT = -1


def style(categorie: str) -> StyleDP:
    if categorie not in STYLES:
        raise KeyError(
            f"Catégorie « {categorie} » sans style de dossier. Catégories "
            f"connues : {', '.join(sorted(STYLES))}."
        )
    return STYLES[categorie]


def categories_dessinables() -> tuple:
    """Catégories que le plan de masse trace, dans l'ordre de dessin."""
    return tuple(
        sorted(
            (c for c, s in STYLES.items() if s.dessinee and c not in EXCLUES),
            key=lambda c: STYLES[c].rang,
        )
    )


#: Recollement admis entre deux bouts de contour, en mètres. La CAO ne referme
#: pas ses polylignes au point près.
TOLERANCE_CONTOUR_M = 0.01

#: Surface en deçà de laquelle un contour recousu n'est pas un ouvrage.
AIRE_CONTOUR_MINIMALE_M2 = 0.5


def dimensions_au_sol(geometrie) -> tuple | None:
    """Longueur et largeur du rectangle minimal d'une géométrie, en mètres."""
    rectangle = geometrie.minimum_rotated_rectangle
    if rectangle.geom_type != "Polygon":
        return None
    sommets = list(rectangle.exterior.coords)[:-1]
    if len(sommets) < 4:
        return None
    cotes = sorted(
        math.dist(sommets[index][:2], sommets[(index + 1) % 4][:2])
        for index in range(4)
    )
    return cotes[-1], cotes[0]


def _est_le_poste(geometrie, longueur_m: float, largeur_m: float) -> bool:
    """Vrai si cette géométrie a les cotes de l'ouvrage au catalogue.

    L'ouvrage est un poste ou, depuis le 07/11/2026, un conteneur : la règle
    est la même, voir `separer_les_corps`.
    """
    mesure = dimensions_au_sol(geometrie)
    if mesure is None:
        return False
    for attendu, obtenu in zip(sorted((longueur_m, largeur_m), reverse=True), mesure):
        if not attendu or abs(obtenu - attendu) > TOLERANCE_COTES_POSTE * attendu:
            return False
    return True


def _cotes_au_catalogue(contrat, categorie: str, surface_m2: float):
    """Cotes de l'ouvrage au catalogue, ou `None` si le catalogue ne tranche pas."""
    from ..erreurs import ErreurCoteOuvrage

    try:
        cote = contrat.cote_de_categorie(categorie, surface_m2=surface_m2)
    except ErreurCoteOuvrage:
        return None
    if not cote.longueur_m or not cote.largeur_m:
        return None
    return cote.longueur_m, cote.largeur_m


def emprise_de_poste(contrat, categorie: str, avertissements: list) -> tuple:
    """Les postes dessinés au plan, et ce que le calque porte autour d'eux.

    Un calque de poste ne porte pas que le poste. Mesuré le 05/09/2026 sur les
    trois dossiers d'essai :

    - Saint-Cyr, `pdl_ptr` : un rectangle de **12,00 x 3,00 m** — exactement le
      PDL/PTR du catalogue — accompagné de deux bandes de 12 x 1,50 et 12 x 1,00
      qui le bordent sur toute sa longueur ;
    - Sarnois indice B, `ptr` : un rectangle de **10,00 x 3,00 m**, le PTR du
      catalogue, au milieu de deux patatoïdes de 41 et 83 m² et de deux plots.

    Ces objets qui entourent le poste sont la terre remise autour de lui : un
    poste préfabriqué a son seuil de porte cinquante à soixante-dix centimètres
    au-dessus de sa semelle, et le talus comble la différence. Ce n'est pas du
    poste, et le dessiner de la couleur du poste lui donnait une emprise deux
    fois trop large — 12 x 5,50 m à Saint-Cyr pour un poste de 12 x 3, quand
    l'élévation de DP 4 le dessine, elle, à ses cotes de catalogue.

    Le poste est donc **reconnu** à ses cotes plutôt que reconstruit : il est
    déjà là, au centimètre. Ce qui l'entoure est rendu à part, pour être dessiné
    comme du sol remanié.

    **Chaque** objet aux cotes du catalogue est un poste, et non le seul plus
    grand : un calque peut en porter plusieurs. La reconnaissance est celle de
    `separer_les_corps`, qui ne compte qu'une fois un poste que le bureau
    d'études a dessiné plusieurs fois.

    Faute d'objet aux cotes du catalogue — le calque de Sarnois indice A porte un
    seul rectangle de 10 x 3 m là où le tableau déclare un PDL/PTR de 12 x 3 —
    on retombe sur l'ancienne règle : l'union du calque, redressée si elle est
    déjà rectangulaire, et l'écart au tableau écrit au rapport.

    Le nombre et la surface des postes se recoupent avec le tableau bilan, voir
    `_recouper_avec_le_tableau` — même quand le calque est vide.
    """
    parties = contrat.geometries(categorie)
    union = union_valide(parties) if parties else None
    if union is not None and (union.is_empty or union.area <= 0):
        union = None
    postes, autour, copies = (
        separer_les_corps(contrat, categorie, parties)
        if union is not None
        else ([], list(parties), {})
    )
    _recouper_avec_le_tableau(
        contrat, categorie, postes, autour, union, avertissements
    )
    if union is None:
        return parties, []

    if postes:
        if autour or copies:
            avertissements.append(
                _dire_les_postes(categorie, postes, autour, copies)
            )
        return postes, autour

    dessinee = parties
    rectangle = union.minimum_rotated_rectangle
    if (
        rectangle.area > 0
        and union.area / rectangle.area >= REMPLISSAGE_RECTANGULAIRE
    ):
        dessinee = [rectangle]
        if len(parties) > 1:
            avertissements.append(
                f"« {categorie} » : les {len(parties)} objets du calque sont "
                f"dessinés comme une seule emprise de {rectangle.area:.1f} m². "
                "Leurs bouts ne s'alignaient pas et donnaient au poste une "
                "silhouette en escalier."
            )

    return dessinee, []


def _recouper_avec_le_tableau(
    contrat, categorie: str, postes: list, autour: list, union, avertissements: list
) -> None:
    """Le nombre et la surface des postes d'une catégorie, recoupés avec le tableau.

    **La surface déclarée se lit de deux façons**, et les deux se rencontrent.
    Le tableau intitule la ligne « Surface des PTR (m²) » : la surface des
    postes eux-mêmes, tous ceux de la catégorie. Auzainvilliers V3 déclare ainsi
    30 m² pour un PTR de 10 x 3 m et 36 m² pour un PDL/PTR de 12 x 3 m ; mais
    Saint-Cyr, en V6 comme en V7, déclare 66 m² pour un PDL/PTR de 36 m² flanqué
    de deux bandes de 18 et 12 m² — l'union du calque. Le contrôle accepte l'une
    ou l'autre, à `TOLERANCE_EMPRISE_POSTE` près. Il ne lisait que l'union, et
    annonçait à Auzainvilliers « 132.4 m² dessinés au plan pour 36.0 m²
    déclarés » pour un poste dessiné au centimètre (relevé le 07/11/2026) : le
    message laissait croire le poste faux. Hors des deux lectures, il dit la
    déclaration, les postes et leur surface, et l'union avec la terre remise.
    Sans rien au plan, seul le nombre parle.

    **Le nombre se compare toujours** : les postes reconnus, copies comptées une
    fois, contre la ligne « Nombre de … ». À Auzainvilliers, le calque 0 apparié
    au PTR, le plan porte deux PTR pour un au tableau : le second est celui des
    batteries, que le catalogue range dans sa section « Aire de charge (BESS) —
    PTR » et que le tableau peut ne pas compter avec les autres. Le message le
    rappelle quand le plan porte une aire de charge.

    Aucun des deux messages ne bloque : ce sont des écarts à lire.
    """
    cles = COMPTEES_AU_TABLEAU.get(categorie)
    if not cles:
        return
    cle_nombre, cle_surface = cles
    declares = contrat.postes or {}
    nombre = declares.get(cle_nombre)
    surface = declares.get(cle_surface)

    if surface and union is not None:
        corps = sum(g.area for g in postes)
        lectures = ([corps] if postes else []) + [union.area]
        if not any(
            abs(lue - surface) <= TOLERANCE_EMPRISE_POSTE * surface for lue in lectures
        ):
            tolerance = f"{TOLERANCE_EMPRISE_POSTE * 100:.0f} %"
            declaration = (
                f"« {categorie} » : {surface:.1f} m² déclarés au tableau bilan "
                f"(« {_libelle_au_tableau(cle_surface)} »)"
            )
            if postes:
                texte = (
                    f"{declaration}, pour {_postes(len(postes))} aux cotes du "
                    f"catalogue au plan, {corps:.1f} m²"
                    + (" au total" if len(postes) > 1 else "")
                )
                if autour:
                    qui = "de lui" if len(postes) == 1 else "d'eux"
                    texte += (
                        f", et {union.area:.1f} m² avec la terre remise autour "
                        f"{qui} : aucune des deux surfaces ne correspond à la "
                        f"déclaration, à {tolerance} près."
                    )
                else:
                    texte += (
                        " : la surface ne correspond pas à la déclaration, à "
                        f"{tolerance} près."
                    )
                texte += " La planche dessine les postes à leurs cotes de catalogue."
            else:
                texte = (
                    f"{declaration}, pour {union.area:.1f} m² dessinés au plan, "
                    "où aucun objet n'a les cotes du catalogue : la planche "
                    "montre ce que le plan porte."
                )
            avertissements.append(texte)

    if nombre is not None and len(postes) != int(nombre):
        texte = (
            f"« {categorie} » : {_postes(len(postes))} aux cotes du catalogue au "
            f"plan, pour {int(nombre)} au tableau bilan "
            f"(« {_libelle_au_tableau(cle_nombre)} »)."
        )
        if categorie == "ptr" and len(postes) > int(nombre) and contrat.presente("bess"):
            # Le libellé de la section est celui du catalogue des gabarits UNITe,
            # relevé le 07/11/2026 ; `contrat.LIBELLES_COTES` ne le rattache à
            # aucune catégorie, et c'est bien le problème.
            texte += (
                " Le catalogue range le PTR d'une aire de charge BESS dans sa "
                "propre section, « Aire de charge (BESS) — PTR » : le tableau peut "
                "ne pas le compter avec les autres PTR."
            )
        avertissements.append(texte)


def _postes(nombre: int) -> str:
    if nombre == 0:
        return "aucun poste"
    return f"{nombre} poste" + ("s" if nombre > 1 else "")


def _libelle_au_tableau(cle: str) -> str:
    """La ligne du tableau bilan qui porte `cle`, telle que le chef de projet la lit.

    Lue dans `tableau_bilan.PARAMETRES`, qui la cherche par ce libellé : la
    recopier ici la laisserait dériver. Importée dans la fonction : le module
    des planches ne dépend pas de la lecture du tableau pour se charger.
    """
    from ..tableau_bilan import PARAMETRES

    return {cle_: libelle for cle_, libelle, *_ in PARAMETRES["postes"]}[cle]


def emprise_de_conteneur(contrat, categorie: str, avertissements: list) -> tuple:
    """Les conteneurs dessinés au plan, et ce que le calque porte autour d'eux.

    Mesuré le 07/11/2026 sur le DXF d'Auzainvilliers : chaque conteneur BESS de
    6,06 x 3,00 m est posé sur un aplat plein de 8,06 x 6,00 m, à 1 m de ses
    bords, dans le même calque que les 162 détails du bloc « BESS Skyray », tous
    sous le conteneur. Dessiné d'un bloc à la teinte du BESS, l'aplat cachait le
    conteneur : la DP 2 montrait 48 m² de batteries là où la DP 4 en dessine 18.

    Validé par le chef de projet le 04/11/2026 (décision D3 du brief du lot 10) :
    le conteneur aux cotes du catalogue garde sa teinte, l'aplat et les détails
    passent en plateforme. L'aplat est la plateforme des batteries : le tableau
    la déclare (« Surface plateforme batteries (m²) », 100 pour deux
    conteneurs à Auzainvilliers, 50 pour un à Sarnois), et le rapport le dit
    sans plus le demander au bureau d'études (décidé le 08/11/2026). C'est la
    reconnaissance des postes, `separer_les_corps`, sans le recoupement avec le
    tableau bilan, que `COMPTEES_AU_TABLEAU` réserve aux postes, et sans
    redressement : faute de conteneur aux cotes du catalogue, le calque se
    dessine tel quel, comme avant.
    """
    parties = contrat.geometries(categorie)
    conteneurs, autour, copies = separer_les_corps(contrat, categorie, parties)
    if not conteneurs:
        return parties, []
    if autour or copies:
        avertissements.append(
            _dire_les_conteneurs(categorie, conteneurs, autour, copies)
        )
    return conteneurs, autour


def separer_les_corps(contrat, categorie: str, parties) -> tuple[list, list, dict]:
    """Les ouvrages d'un calque, reconnus à leurs cotes de catalogue, et le reste.

    Le corps d'un ouvrage est l'objet du calque qui a ses dimensions au
    catalogue : le poste, jamais sa plateforme ni la terre remise autour de
    lui. **Chaque** objet à ces cotes est un corps. La règle n'en gardait
    qu'un par catégorie, le plus grand — à aire égale, le premier venu — et
    rendait les autres au sol. Mesuré le 07/11/2026 à Auzainvilliers, le
    calque 0 apparié au PTR : le calque des PTR y porte le poste principal et
    celui des batteries, deux 10 x 3 m, et l'un des deux passait en gris sur
    la DP 2, les plans de repérage de la DP 4 et le volet photographique.

    Un corps que le bureau d'études a dessiné plusieurs fois ne compte qu'une
    fois. Ses copies, à `TOLERANCE_DOUBLON_M2` près, ne se dessinent ni en
    ouvrage ni en sol — c'est l'ouvrage, déjà dessiné —, et l'appelant les
    compte au rapport.

    La variante du catalogue se cherche sur la surface de chaque objet, et non
    sur celle du calque entier : un calque qui porte un ouvrage et ce qui
    l'entoure n'a la surface d'aucune variante, quand l'ouvrage a la sienne.

    Rend `(corps, autour, copies)` : les corps dans l'ordre du calque, ce qui
    n'en est pas, et le nombre de copies écartées par rang de corps.
    """
    corps, autour = [], []
    copies: dict[int, int] = {}
    for geometrie in parties:
        # Un trait n'est pas un corps, même à ses cotes : c'est un contour ou
        # un détail, et il n'a pas d'aire à recouper avec le catalogue.
        cotes = (
            _cotes_au_catalogue(contrat, categorie, geometrie.area)
            if geometrie.area > 0
            else None
        )
        if cotes is None or not _est_le_poste(geometrie, *cotes):
            autour.append(geometrie)
            continue
        rang = next(
            (
                rang
                for rang, deja in enumerate(corps)
                if geometrie.symmetric_difference(deja).area < TOLERANCE_DOUBLON_M2
            ),
            None,
        )
        if rang is None:
            corps.append(geometrie)
        else:
            copies[rang] = copies.get(rang, 0) + 1
    return corps, autour, copies


def _dire_les_postes(categorie: str, postes: list, autour: list, copies: dict) -> str:
    """Ce que porte le calque d'un poste : les postes, leurs copies, la terre remise."""
    phrases = [f"« {categorie} » : {_phrase_des_corps('poste', postes)}"]
    if copies:
        phrases.append(_phrase_des_copies(len(postes), copies))
    if autour:
        qui = "de lui" if len(postes) == 1 else "d'eux"
        phrases.append(
            f"Les {len(autour)} autre(s) objet(s) du calque, "
            f"{sum(g.area for g in autour):.1f} m² au total, sont la terre "
            f"remise autour {qui} : ils sont dessinés comme du sol et non "
            "comme du poste."
        )
    return " ".join(phrases)


def _dire_les_conteneurs(
    categorie: str, conteneurs: list, autour: list, copies: dict
) -> str:
    """Ce que porte le calque d'un conteneur : les conteneurs, leurs copies, l'aplat.

    L'aplat est l'objet du calque qui porte un conteneur — qui le contient, à
    `JEU_APLAT_M` près. Le reste, ce sont les détails du bloc. Les deux passent
    en plateforme, et le message le dit sans rien demander : c'est une
    information, que l'application range parmi les points à savoir du dossier.

    Jusqu'au 08/11/2026, il demandait au bureau d'études si l'aplat était une
    dalle ou une aire dégagée. Le tableau bilan répond : il déclare une
    « Surface plateforme batteries (m²) » de 50 m² par conteneur — 100 à
    Auzainvilliers pour deux, 50 à Sarnois pour un —, et l'aplat en mesure
    48,3. Pour un BESS, l'aplat se nomme donc la plateforme des batteries ; pour
    un local technique, rien ne le dit, et il reste un aplat.
    """
    phrases = [f"« {categorie} » : {_phrase_des_corps('conteneur', conteneurs)}"]
    if copies:
        phrases.append(_phrase_des_copies(len(conteneurs), copies))
    aplats = [
        g
        for g in autour
        if g.area > 0 and any(g.buffer(JEU_APLAT_M).contains(c) for c in conteneurs)
    ]
    details = [g for g in autour if not any(g is aplat for aplat in aplats)]
    seul = len(conteneurs) == 1
    autres = (
        f"les {len(details)} autre(s) objet(s) du calque, "
        f"{sum(g.area for g in details):.1f} m² au total"
    )
    if aplats:
        un = len(aplats) == 1
        sujet = "Il est posé" if seul else "Ils sont posés"
        support = "un aplat" if un else f"{len(aplats)} aplats"
        dessine = "dessiné" if un else "dessinés"
        nom = ""
        if categorie == "bess":
            nom = (
                ", la plateforme des batteries,"
                if un
                else ", les plateformes des batteries,"
            )
        phrases.append(
            f"{sujet} sur {support} de {_formats(aplats)}{nom} {dessine} en "
            f"plateforme{f' comme {autres}' if details else ''}."
        )
    elif details:
        phrases.append(
            f"{autres[0].upper()}{autres[1:]}, ne sont pas "
            f"{'le conteneur' if seul else 'les conteneurs'} : ils sont "
            "dessinés comme du sol."
        )
    return " ".join(phrases)


def _formats(geometries) -> str:
    """Les cotes au sol de quelques objets, sans redite.

    Du plus grand côté au plus petit : le catalogue les porte tantôt
    « longueur x largeur », tantôt l'inverse, et « 3,00 x 10,00 m » se lit
    mal. Ce sont les cotes du plan, celles que la planche dessine.
    """
    vus = []
    for geometrie in geometries:
        mesure = dimensions_au_sol(geometrie)
        if mesure is None:
            continue
        texte = f"{mesure[0]:.2f} x {mesure[1]:.2f} m"
        if texte not in vus:
            vus.append(texte)
    return " et ".join(vus)


def _phrase_des_corps(nom: str, corps: list) -> str:
    """« le poste est l'objet de 10.00 x 3.00 m du calque », ou son pluriel."""
    if len(corps) == 1:
        return (
            f"le {nom} est l'objet de {_formats(corps)} du calque, aux cotes "
            "du catalogue."
        )
    return (
        f"les {len(corps)} {nom}s sont les {len(corps)} objets de "
        f"{_formats(corps)} du calque, aux cotes du catalogue : chacun se "
        f"dessine comme un {nom}."
    )


def _phrase_des_copies(nombre: int, copies: dict) -> str:
    """Ce que le bureau d'études a dessiné plusieurs fois, et qui compte une fois."""
    total = sum(copies.values())
    if nombre == 1:
        return (
            f"Le bureau d'études l'a dessiné {_fois(1 + total)} à l'identique : "
            "il ne compte qu'une fois."
        )
    if len(copies) == nombre and len(set(copies.values())) == 1:
        return (
            "Le bureau d'études les a dessinés chacun "
            f"{_fois(1 + total // nombre)} à l'identique : chacun ne compte "
            "qu'une fois."
        )
    if len(copies) == 1:
        return (
            f"Le bureau d'études a dessiné l'un d'eux {_fois(1 + total)} à "
            "l'identique : il ne compte qu'une fois."
        )
    return (
        f"Le bureau d'études en a dessiné {len(copies)} plusieurs fois à "
        f"l'identique, {total} copie(s) en tout : chacun ne compte qu'une fois."
    )


def _fois(nombre: int) -> str:
    return {2: "deux fois", 3: "trois fois", 4: "quatre fois"}.get(
        nombre, f"{nombre} fois"
    )


#: Clés sous lesquelles les deux entrées qui ne viennent pas du contrat se
#: renomment. Le parcellaire et les bâtiments viennent du WFS IGN, pas du plan du
#: bureau d'études : ils n'ont pas de catégorie de contrat à porter leur nom.
CLE_PARCELLE = "_parcelle"
CLE_BATIMENT = "_batiment"


def construire_legende(
    categories,
    avec_parcelles: bool = False,
    avec_batiments: bool = False,
    libelles: dict | None = None,
) -> list:
    """Légende bâtie sur ce qui a été dessiné, et sur rien d'autre (D3).

    Une catégorie sans objet dessiné n'y figure pas ; deux catégories partageant
    le même intitulé n'y font qu'une entrée — le dédoublonnage se fait sur
    l'intitulé, pas sur la catégorie. L'ordre est celui du rang de dessin du
    contrat.

    `libelles` remplace l'intitulé de certaines catégories, `{catégorie: texte}`.
    C'est ce que le chef de projet peut corriger à l'écran avant de générer : nos
    intitulés sont ceux du dossier de référence, mais un projet peut avoir ses
    mots — une « piste lourde » qui s'appelle une voie de desserte sur les autres
    pièces du dossier. Le parcellaire et les bâtiments se renomment sous
    `CLE_PARCELLE` et `CLE_BATIMENT`.

    Le remplacement se fait **avant** le dédoublonnage, et c'est ce qui compte :
    renommer deux catégories qui partageaient un intitulé les sépare en deux
    entrées, et leur donner le même les réunit en une. La légende suit donc ce que
    le chef de projet a écrit, et non ce que la table prévoyait.

    Un intitulé vide est refusé plutôt que laissé vide : une entrée de légende
    sans texte est un aplat de couleur que rien ne nomme.
    """
    libelles = dict(libelles or {})
    vides = [cle for cle, texte in libelles.items() if not str(texte).strip()]
    if vides:
        raise ErreurComposition(
            "Intitulé de légende vide pour "
            f"{', '.join(sorted(vides))} : une entrée de légende sans texte est "
            "un aplat de couleur que rien ne nomme."
        )

    entrees = []
    if avec_parcelles:
        entrees.append((
            RANG_PARCELLE,
            libelles.get(CLE_PARCELLE, LIBELLE_PARCELLE),
            STYLE_PARCELLE,
            SYMBOLE_PARCELLE,
        ))
    if avec_batiments:
        entrees.append((
            RANG_BATIMENT,
            libelles.get(CLE_BATIMENT, LIBELLE_BATIMENT),
            STYLE_BATIMENT,
            SYMBOLE_BATIMENT,
        ))

    for categorie in categories:
        if categorie in EXCLUES or categorie in SANS_STYLE:
            continue
        fiche = style(categorie)
        entrees.append((
            fiche.rang,
            libelles.get(categorie, fiche.libelle),
            fiche.style,
            fiche.symbole,
        ))

    entrees.sort(key=lambda e: e[0])
    vues = set()
    legende = []
    for _, libelle, trace, symbole in entrees:
        if libelle in vues:
            continue
        vues.add(libelle)
        legende.append(EntreeDP(libelle, trace, symbole))
    return legende


# ---------------------------------------------------------------------------
# Contrôle de distinguabilité
# ---------------------------------------------------------------------------


def _canal_lineaire(valeur: float) -> float:
    return valeur / 12.92 if valeur <= 0.04045 else ((valeur + 0.055) / 1.055) ** 2.4


def vers_lab(couleur: str) -> tuple[float, float, float]:
    """Couleur hexadécimale sRGB vers CIE L*a*b*, illuminant D65.

    Passer par Lab plutôt que comparer des RVB : deux gris séparés de 30 unités
    RVB se distinguent, deux verts séparés d'autant ne se distinguent pas, et
    c'est l'œil qui juge la planche.
    """
    texte = couleur.lstrip("#")
    if len(texte) != 6:
        raise ValueError(f"Couleur hexadécimale attendue, reçu « {couleur} ».")
    r, v, b = (int(texte[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    r, v, b = (_canal_lineaire(c) for c in (r, v, b))

    # Matrice sRGB → XYZ (D65), et blanc de référence associé.
    x = (0.4124564 * r + 0.3575761 * v + 0.1804375 * b) / 0.95047
    y = 0.2126729 * r + 0.7151522 * v + 0.0721750 * b
    z = (0.0193339 * r + 0.1191920 * v + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def ecart_perceptuel(couleur_a: str, couleur_b: str) -> float:
    """ΔE CIE76 entre deux couleurs, en unités perceptuelles."""
    la, aa, ba = vers_lab(couleur_a)
    lb, ab, bb = vers_lab(couleur_b)
    return ((la - lb) ** 2 + (aa - ab) ** 2 + (ba - bb) ** 2) ** 0.5


def couleur_significative(fiche: StyleDP) -> str:
    """Couleur qui porte l'identité de la catégorie : son fond, sinon son trait.

    Une clôture ou un portail n'ont pas de remplissage : ce qui les distingue
    l'un de l'autre est la couleur du filet.
    """
    remplissage = fiche.style.remplissage
    if remplissage and remplissage != "none":
        return remplissage
    return fiche.style.trait or "#000000"


#: Catégories dont le tableau bilan donne le nombre et la surface au sol, et
#: dont l'emprise dessinée se recoupe donc avec lui.
COMPTEES_AU_TABLEAU = {
    "pdl_ptr": ("nb_pdl_ptr", "surface_pdl_ptr_m2"),
    "ptr": ("nb_ptr", "surface_ptr_m2"),
    "pdl": ("nb_pdl", "surface_pdl_m2"),
}

#: Part de son rectangle minimal qu'une emprise doit remplir pour être tenue
#: pour rectangulaire. 0,97 : un poste est un bâtiment rectangulaire, et ce qui
#: manque à ce point-là n'est plus un défaut de tracé.
REMPLISSAGE_RECTANGULAIRE = 0.97

#: Écart admis entre l'emprise dessinée d'un poste et sa surface déclarée.
TOLERANCE_EMPRISE_POSTE = 0.08

#: Écart admis entre les côtés d'un objet du calque et les cotes du catalogue
#: pour le reconnaître comme étant le poste lui-même.
#:
#: 5 % : mesuré le 05/09/2026, les postes des trois dossiers d'essai sont
#: dessinés **au centimètre** des cotes du catalogue — 12,00 x 3,00 m à
#: Saint-Cyr pour un PDL/PTR de 12 x 3, 10,00 x 3,00 m à Sarnois indice B pour
#: un PTR de 10 x 3. La tolérance n'a pas à être large ; elle absorbe un arrondi
#: de tracé, pas un objet d'une autre nature.
TOLERANCE_COTES_POSTE = 0.05

#: Différence symétrique, en mètres carrés, en deçà de laquelle deux objets aux
#: cotes du catalogue sont le même ouvrage dessiné deux fois.
#:
#: Mesuré le 07/11/2026 : à Auzainvilliers, le PTR principal est dessiné deux
#: fois et le PDL/PTR trois fois, et les copies coïncident à 0,000 m² près ;
#: deux postes distincts de 10 x 3 m en ont 60. Le seuil absorbe un arrondi de
#: tracé, pas un second ouvrage.
TOLERANCE_DOUBLON_M2 = 0.05

#: Jeu admis, en mètres, pour dire qu'un objet du calque porte un conteneur :
#: il le contient à ce jeu près, et c'est son aplat.
#:
#: Mesuré le 07/11/2026 : à Auzainvilliers, chaque conteneur BESS est à 1,00 m
#: du bord de son aplat, comme à Sarnois le 03/11. Le jeu n'absorbe qu'un
#: arrondi de tracé, pour un conteneur dessiné au ras de son aplat.
JEU_APLAT_M = 0.05

#: Recollement admis entre deux bouts de contour, en mètres. La CAO ne referme
#: pas ses polylignes au point près.
TOLERANCE_CONTOUR_M = 0.01

#: Surface en deçà de laquelle un contour recousu n'est pas un ouvrage.
AIRE_CONTOUR_MINIMALE_M2 = 0.5


def objets_a_dessiner(contrat, avertissements=None) -> list:
    """Géométries à tracer, par catégorie, dans l'ordre de dessin du contrat.

    Un seul endroit applique les trois règles qui décident de ce qui figure au
    dossier, pour que le plan de masse et les plans de repérage des DP 4 ne
    puissent pas en appliquer des versions différentes :

    - les catégories exclues ne sont pas dessinées (D3) ;
    - une catégorie sans objet ne produit rien, et n'aura donc pas d'entrée de
      légende (D3) ;
    - les voiries dont le calque ne disait pas le type rejoignent celle que le
      chef de projet a tranchée, et n'existent pas sous leur propre nom (D5).

    S'y ajoute la recomposition des contours ouverts, pour la même raison : une
    règle appliquée à deux endroits finit par y différer. Et, pour la même
    raison encore, la séparation de chaque poste et de chaque conteneur d'avec
    ce qui l'entoure (`separer_les_corps`) : ce qui l'entoure rejoint la
    plateforme, ici et nulle part ailleurs.
    """
    messages = [] if avertissements is None else avertissements
    resultat = []
    autour_des_corps = []
    conteneurs = _conteneurs()
    for categorie in categories_dessinables():
        if categorie in COMPTEES_AU_TABLEAU:
            geometries, autour = emprise_de_poste(contrat, categorie, messages)
        elif categorie in conteneurs:
            geometries, autour = emprise_de_conteneur(contrat, categorie, messages)
        else:
            geometries, autour = contrat.geometries(categorie), []
        geometries = list(geometries)
        autour_des_corps.extend(autour)
        geometries.extend(contrat.voiries_de(categorie))
        geometries = fermer_les_contours(geometries, categorie, messages)
        if geometries:
            resultat.append((categorie, geometries))

    # La plateforme est vue au rang 2, les postes et les conteneurs aux rangs
    # 20 à 24 : ce qui les entoure n'est connu qu'une fois la boucle finie, et
    # c'est là qu'il rejoint le sol. Sans plateforme au plan, il en ouvre une —
    # c'est bien du sol remanié, ou un aplat, et il doit se voir.
    if autour_des_corps:
        for rang, (categorie, geometries) in enumerate(resultat):
            if categorie == "plateforme":
                resultat[rang] = (categorie, geometries + autour_des_corps)
                break
        else:
            resultat.insert(0, ("plateforme", autour_des_corps))
    return resultat


def _conteneurs() -> tuple:
    """Les catégories de conteneurs, dont le corps se reconnaît comme un poste.

    Lues dans `dp4_ouvrages`, qui les dessine en conteneurs maritimes, et non
    recopiées : deux listes finiraient par différer. Importées dans la fonction,
    `dp4_ouvrages` important ce module à son propre chargement.
    """
    from .dp4_ouvrages import CONTENEURS

    return CONTENEURS


def fermer_les_contours(geometries, categorie: str, messages: list) -> list:
    """Recompose en surfaces les contours que le calque a laissés ouverts.

    Mesuré le 05/09/2026 sur Sarnois : la citerne de refroidissement arrive au
    contrat en **onze objets** — un petit polygone et dix polylignes ouvertes,
    les quatre côtés et les quatre congés d'un rectangle à angles arrondis que
    la CAO a exportés séparément. Une polyligne ne se remplit pas : l'ouvrage
    sortait en contour sur une planche dont la légende annonçait un aplat.

    Deux garde-fous, tous deux mesurés le même jour :

    - la recomposition ne vaut que pour les catégories **dessinées en aplat**.
      Le portail est un linéaire, et ses deux arcs de débattement se referment
      parfaitement en deux surfaces de 9,6 m² qui n'existent pas ;
    - les côtés ne se touchent pas au point près — sans recollement à 1 cm, la
      citerne ne se referme pas du tout ; à 20 cm, elle se referme en six
      morceaux. Les 108,7 m² obtenus à 1 cm valent les 108,8 m² déclarés au
      tableau bilan.

    Ce qui reste ouvert est rendu tel quel, et la recomposition est écrite au
    rapport : ce n'est pas la géométrie du calque.

    Une ligne **déjà fermée sur elle-même** n'est pas un contour laissé ouvert :
    un producteur qui ferme un contour écrit un polygone — le lot 2bis le fait
    de toute polyligne fermée du DXF. C'est un axe qui boucle, et il le reste.
    Mesuré le 23/09/2026 sur le contrat du plan PDF de Gannay (lot 2ter) : le
    cercle de piste existante, un axe de 189 m, devenait un disque de voie
    lourde de 2 828 m².
    """
    if STYLES[categorie].style.remplissage in (None, "none"):
        return geometries
    lignes = [
        g
        for g in geometries
        if g.geom_type in ("LineString", "LinearRing") and not _fermee(g)
    ]
    if not lignes:
        return geometries

    from shapely import snap
    from shapely.ops import polygonize

    reseau = unary_union(lignes)
    reseau = snap(reseau, reseau, TOLERANCE_CONTOUR_M)
    surfaces = [
        s for s in polygonize(unary_union(reseau)) if s.area >= AIRE_CONTOUR_MINIMALE_M2
    ]
    if not surfaces:
        return geometries

    # Les lignes qui bordent une surface recomposée ne sont plus dessinées à
    # part : leur tracé est devenu le filet du polygone.
    recomposee = unary_union(surfaces)
    contour = recomposee.buffer(TOLERANCE_CONTOUR_M)
    ouvertes = {id(g) for g in lignes}
    restantes = [
        g for g in geometries
        if id(g) not in ouvertes or not contour.contains(g)
    ]
    messages.append(
        f"« {categorie} » : {len(lignes)} contour(s) ouvert(s) du calque "
        f"recousus en {len(surfaces)} surface(s), {recomposee.area:.1f} m² au "
        "total, pour que l'ouvrage se lise comme un aplat et non comme un trait."
    )
    return restantes + surfaces


def contour_de(geometrie):
    """Le contour à tracer d'une géométrie, quelle que soit sa nature.

    `boundary` rend **None** sur une `GeometryCollection`, et c'est exactement
    ce que `make_valid` produit d'un contour auto-intersectant : le polygone
    d'un côté, les bouts de ligne que l'auto-intersection a détachés de
    l'autre. Relevé le 27/09/2026 sur le calque « UNI_BESS_Refroidissement »
    du plan d'Auzainvilliers — la génération s'arrêtait en `AttributeError` au
    milieu des DP 4, sur un plan dont l'import avait pourtant signalé la
    géométrie invalide et nommé le calque. Le contour de chaque partie est donc
    repris une à une.

    Le contour d'un linéaire est le linéaire lui-même : `boundary` en rendrait
    les deux extrémités, soit deux points là où on attend un trait.
    """
    if geometrie.geom_type in _LINEAIRES:
        return geometrie
    if geometrie.geom_type == "GeometryCollection":
        contours = [contour_de(partie) for partie in geometrie.geoms]
        return unary_union(
            [c for c in contours if c is not None and not c.is_empty]
        )
    return geometrie.boundary


def _fermee(ligne) -> bool:
    coords = list(ligne.coords)
    return len(coords) > 3 and coords[0][:2] == coords[-1][:2]


#: Épaisseur sur le papier, en millimètres, du tracé linéaire d'une catégorie
#: dessinée en aplat — une piste ou une haie dont le contrat ne donne que l'axe.
#:
#: Un plan projet PDF (lot 2ter) ne donne pas autre chose : la largeur qu'il
#: dessine n'est pas à l'échelle, et on ne la suppose pas. L'axe se dessine donc
#: en trait, dans la teinte de l'aplat — celle que montre la légende —, à une
#: épaisseur de symbole et non de terrain. Tracé avec le style de la surface, il
#: se remplissait : le moteur ferme implicitement un chemin rempli, et la piste
#: à créer de Gannay, qui longe trois côtés du site, devenait un aplat gris de
#: tout son intérieur (mesuré le 23/09/2026).
EPAISSEUR_TRACE_MM = 0.8

_LINEAIRES = ("LineString", "LinearRing", "MultiLineString")


def style_de(categorie: str, geometrie, sur_sa_surface: bool = False) -> Style:
    """Style d'un objet : l'aplat de sa catégorie, ou un trait s'il n'est qu'un axe.

    `sur_sa_surface` dit que la catégorie dessine aussi une surface sur cette
    planche. Le trait y est alors un détail **posé dessus**, et il se trace au
    filet et non au remplissage — sinon il disparaît dedans. Relevé le
    30/09/2026 sur Bédarieux : l'aire d'aspiration arrive en un rectangle de
    8 x 4 m et ses deux diagonales, la croix des sapeurs-pompiers. Tracée au
    bleu pâle du remplissage sur ce même bleu pâle, elle était invisible — le
    chef de projet a signalé une croix qu'on ne voit pas.
    """
    style = STYLES[categorie].style
    if style.remplissage in (None, "none") or geometrie.geom_type not in _LINEAIRES:
        return style
    return Style(
        trait=style.trait if sur_sa_surface else style.remplissage,
        epaisseur_mm=max(style.epaisseur_mm, EPAISSEUR_TRACE_MM),
        remplissage="none",
        tirets=style.tirets,
    )
