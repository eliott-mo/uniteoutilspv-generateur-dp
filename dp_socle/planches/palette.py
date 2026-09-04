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

from dataclasses import dataclass

from ..planche import STYLE_BATIMENT, STYLE_PARCELLE, EntreeLegende, Style

#: Écart perceptuel minimal entre deux teintes susceptibles de se retrouver sur
#: la même planche, en ΔE CIE76.
#:
#: 12 : au-delà de « perceptible d'un coup d'œil » (ΔE ≈ 5) et assez large pour
#: tenir sur une épreuve papier, où l'encre étale et où l'objet fait quelques
#: millimètres. Le seuil ne s'applique qu'aux paires dont au moins une teinte
#: est dérivée : une collision entre deux relevées est héritée du dossier de
#: référence et ne se corrige pas ici.
ECART_MINIMAL = 12.0


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


def _remplie(couleur: str, filet: str, epaisseur: float = 0.2) -> Style:
    return Style(trait=filet, epaisseur_mm=epaisseur, remplissage=couleur)


#: Styles du dossier, par catégorie du contrat.
#:
#: `libelle` est l'intitulé de légende. Deux catégories peuvent délibérément
#: partager le même : elles ne produisent alors qu'une entrée (décision D3).
STYLES = {
    # -- surfaces de sol ----------------------------------------------------
    # Dérivée : le gris 215 du contrat est celui de la plateforme et de la
    # piste légère, deux relevées, et aucun gris clair ne s'en distingue assez.
    # Une zone évitée n'est pas une surface aménagée mais une surface qu'on
    # s'interdit : contour tireté sans remplissage, comme se dessine une
    # servitude. Elle se lit alors sous les ouvrages qui la bordent.
    "zone_evitee": StyleDP(
        "Zone évitée", 1,
        Style(trait="#6a7a52", epaisseur_mm=0.35, remplissage="none",
              tirets="2.2 1.2"),
    ),
    "plateforme": StyleDP(
        "Plateforme", 2, _remplie("#d7d7d7", "#6e6e6e"), relevee=True
    ),
    "piste_lourde_existante": StyleDP(
        "Piste lourde existante", 3, _remplie("#a2a2a2", "#6e6e6e"), relevee=True
    ),
    "piste_lourde_a_creer": StyleDP(
        "Piste lourde à créer", 4, _remplie("#a2a2a2", "#000000"), relevee=True
    ),
    # Le gris clair de la piste légère est celui de la plateforme : c'est ainsi
    # sur le dossier de référence. Le filet plus clair et l'entrée de légende
    # propre portent la distinction.
    "piste_legere": StyleDP(
        "Piste légère", 5, _remplie("#d7d7d7", "#8c8c8c"), relevee=True
    ),
    "piste_lourde": StyleDP(
        "Voie lourde", 6, _remplie("#a2a2a2", "#6e6e6e"), relevee=True
    ),
    # Même intitulé et même style que la voie lourde, délibérément : une aire de
    # grutage est un élargissement de voie, que le tableau bilan compte en
    # « supplément piste lourde » et que la légende du dossier ne distingue pas.
    # Une seule entrée en sort.
    "aire_grutage": StyleDP(
        "Voie lourde", 7, _remplie("#a2a2a2", "#6e6e6e"), relevee=True
    ),
    # Dérivée : le gris 215 du contrat la confondait avec la plateforme, dont
    # elle est toujours voisine. Bleu clair, comme l'ouvrage SDIS qu'elle sert.
    "aire_aspiration": StyleDP(
        "Aire d'aspiration", 8, _remplie("#c3dcef", "#3f7f9f")
    ),
    "espace_vert": StyleDP("Espace vert", 9, _remplie("#c9dfa8", "#7d9b55")),
    "arbre_existant": StyleDP(
        "Arbres existants", 10, _remplie("#5a8f4a", "#37592c")
    ),
    # Installations de chantier : temporaires. Elles ne sont ni dessinées ni
    # portées en légende (décision D3), et gardent un style pour le seul cas où
    # une planche de contrôle voudrait les montrer.
    "base_vie": StyleDP(
        "Base vie (chantier)", 11, _remplie("#e8d8be", "#967646"), dessinee=False
    ),
    "stockage_chantier": StyleDP(
        "Stockage logistique (chantier)", 12, _remplie("#e8d8be", "#967646"),
        dessinee=False,
    ),
    "haie": StyleDP(
        "Haie plantée", 13,
        Style(trait="#50780a", epaisseur_mm=0.4, remplissage="#6faa0b"),
        relevee=True,
    ),
    # Dérivée : vert sombre, pour se lire contre la haie plantée sans lui
    # disputer sa teinte relevée.
    "haie_existante": StyleDP(
        "Haie existante", 14,
        Style(trait="#1e3a10", epaisseur_mm=0.4, remplissage="#2f5c18"),
    ),
    # -- structures ---------------------------------------------------------
    # Tables et modules décrivent le même ouvrage à deux niveaux de détail :
    # même teinte, même intitulé — celui du dossier de référence, « Panneaux
    # photovoltaïques » — donc une seule entrée de légende.
    "tables_pv": StyleDP(
        "Panneaux photovoltaïques", 16,
        Style(trait="#2c4a8a", epaisseur_mm=0.2, remplissage="#97caca"),
        relevee=True,
    ),
    "modules_pv": StyleDP(
        "Panneaux photovoltaïques", 17,
        Style(trait="#2c4a8a", epaisseur_mm=0.08, remplissage="#97caca"),
    ),
    # -- postes -------------------------------------------------------------
    "pdl_ptr": StyleDP(
        "Poste de livraison / transformation", 18, _remplie("#7fffbf", "#000000"),
        relevee=True,
    ),
    # Dérivées : trois postes distincts au tableau bilan, trois entrées de
    # légende au dossier. Le vert du PDL/PTR est relevé ; les deux autres s'en
    # écartent en clarté, ce qui reste lisible sur un objet de 12 x 3 mm.
    "ptr": StyleDP("Poste de transformation", 19, _remplie("#2f9e6a", "#000000")),
    "pdl": StyleDP("Poste de livraison", 20, _remplie("#d5f7e6", "#000000")),
    # Dérivée : le contrat lui donnait le vert du PDL/PTR, qu'elle ne peut pas
    # porter — les deux se côtoient sur le même plan. Un local technique n'est
    # pas un poste électrique : teinte neutre chaude.
    "local_technique": StyleDP(
        "Local technique", 21, _remplie("#cfc0a8", "#7a6a50")
    ),
    "bess": StyleDP("Conteneurs BESS", 22, _remplie("#ffcd78", "#8a5a10")),
    # Dérivée : le bac de rétention retient de l'huile, pas de l'eau. Le
    # cyan du contrat le confondait avec la citerne incendie, teinte relevée.
    "bac_retention": StyleDP(
        "Bac de rétention", 23, _remplie("#6e96b4", "#2f4d66")
    ),
    # Dérivée : cyan sombre, distinct de la citerne incendie (relevée, cyan
    # moyen) comme de la teinte des tables.
    "citerne_refroidissement": StyleDP(
        "Citerne de refroidissement", 24, _remplie("#1d7d99", "#0d3f4f")
    ),
    # Dérivée : orangé pâle, de la même famille que le BESS qu'elle dessert.
    "zone_remise": StyleDP("Zone de remise", 25, _remplie("#ffe6bb", "#8a5a10")),
    "bac_equarrissage": StyleDP(
        "Bac d'équarrissage", 26, _remplie("#a8703c", "#5c3c1e")
    ),
    "bache_incendie": StyleDP(
        "Citerne incendie", 27, _remplie("#3fbfbf", "#000000"), relevee=True
    ),
    # -- linéaires ----------------------------------------------------------
    "limite_paddock": StyleDP(
        "Limite de paddock", 28,
        Style(trait="#966e14", epaisseur_mm=0.3, remplissage="none",
              tirets="2.0 1.2"),
    ),
    # Dérivée : ocre franc. Le beige pâle du contrat se confondait avec la
    # zone de remise, dont elle ne partage ni la fonction ni la planche.
    "zone_contention": StyleDP(
        "Zone de contention", 29, _remplie("#d8bc72", "#7a5a10")
    ),
    # Tracés d'étude, exclus du dossier (décision D3) : seule la clôture
    # délimite le projet à l'instruction.
    "recul_implantation": StyleDP(
        "Recul d'implantation (étude)", 30,
        Style(trait="#c87828", epaisseur_mm=0.2, remplissage="none"),
        dessinee=False,
    ),
    "zone_implantation_pv": StyleDP(
        "Zone d'implantation (étude)", 31,
        Style(trait="#ff2d2d", epaisseur_mm=0.3, remplissage="none"),
        dessinee=False,
    ),
    "cloture": StyleDP(
        "Clôture du projet solaire", 32,
        Style(trait="#ff0000", epaisseur_mm=0.5, remplissage="none"),
        relevee=True,
    ),
    "portail": StyleDP(
        "Portail", 33,
        Style(trait="#ff0000", epaisseur_mm=0.7, remplissage="none"),
        relevee=True,
    ),
    # Dérivée : rouge sombre et tireté, pour ne pas se lire comme le portail
    # d'accès, que seul le tableau bilan compte.
    "portail_exploitant": StyleDP(
        "Portail d'exploitation", 34,
        Style(trait="#8a0000", epaisseur_mm=0.45, remplissage="none",
              tirets="1.4 0.8"),
    ),
}

#: Catégories écartées du dossier, et pourquoi (décision D3). Elles ne sont ni
#: dessinées ni portées en légende.
EXCLUES = {
    "base_vie": "installation de chantier, temporaire",
    "stockage_chantier": "installation de chantier, temporaire",
    "zone_implantation_pv": "contour d'étude ; seule la clôture délimite le projet",
    "recul_implantation": "contour d'étude ; seule la clôture délimite le projet",
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


def construire_legende(
    categories,
    avec_parcelles: bool = False,
    avec_batiments: bool = False,
) -> list:
    """Légende bâtie sur ce qui a été dessiné, et sur rien d'autre (D3).

    Une catégorie sans objet dessiné n'y figure pas ; deux catégories partageant
    le même intitulé n'y font qu'une entrée — le dédoublonnage se fait sur
    l'intitulé, pas sur la catégorie. L'ordre est celui du rang de dessin du
    contrat.
    """
    entrees = []
    if avec_parcelles:
        entrees.append((RANG_PARCELLE, LIBELLE_PARCELLE, STYLE_PARCELLE))
    if avec_batiments:
        entrees.append((RANG_BATIMENT, LIBELLE_BATIMENT, STYLE_BATIMENT))

    for categorie in categories:
        if categorie in EXCLUES or categorie in SANS_STYLE:
            continue
        fiche = style(categorie)
        entrees.append((fiche.rang, fiche.libelle, fiche.style))

    entrees.sort(key=lambda e: e[0])
    vues = set()
    legende = []
    for _, libelle, trace in entrees:
        if libelle in vues:
            continue
        vues.add(libelle)
        legende.append(EntreeLegende(libelle, trace))
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
