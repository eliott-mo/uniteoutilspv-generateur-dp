"""DP 1-3 — Plan de cadastre, à échelle adaptative.

Limites parcellaires tracées en vectoriel depuis le WFS Parcellaire Express,
numéros de parcelle étiquetés, et tableau récapitulatif section / numéro /
contenance des parcelles d'assiette.

L'échelle est choisie dans la liste normalisée (1:500, 1:1 000, 1:2 000,
1:5 000) : la plus grande qui fasse tenir l'emprise plus 20 % de marge dans la
zone de dessin. Si aucune ne convient, `ErreurEchelle` est levée — pas de repli
sur une échelle bâtarde.
"""

from __future__ import annotations

from pathlib import Path

from shapely.geometry import box

from ..dossier import piece
from ..echelle import echelle_adaptative
from ..erreurs import ErreurRendu, ErreurService
from ..geometrie import Emprise
from ..ign import telecharger_batiments, telecharger_parcelles
from ..planche import (
    BLEU_UNITE,
    GRIS,
    MOTIF_BATIMENT,
    NOIR,
    PT,
    STYLE_BATIMENT,
    STYLE_EMPRISE,
    STYLE_PARCELLE,
    STYLE_PARCELLE_CONCERNEE,
    TAILLE_COURANTE,
    TAILLE_ETIQUETTE,
    Style,
    nombre_fr,
)
from ..projet import Projet
from .commun import Sortie, nouvelle_planche

NUMERO = "DP 1-3"
TITRE = piece("DP 1-3").titre

#: La planche annexe, produite seulement quand le tableau ne tient pas sur le
#: plan. Voir `generer_tableau`.
NUMERO_TABLEAU = "DP 1-3 bis"
TITRE_TABLEAU = piece("DP 1-3 bis").titre

#: D'où viennent les parcelles, porté sur les deux planches.
SOURCE_IGN = "Source : IGN — Parcellaire Express (PCI), WFS Géoplateforme"

#: Échelles autorisées pour cette planche.
ECHELLES_CADASTRE = (500, 1000, 2000, 5000)

#: Marge autour de l'emprise, exprimée en fraction de ses dimensions.
MARGE = 0.20

#: Surface minimale d'une parcelle sur le papier, en mm², pour être étiquetée.
SURFACE_MIN_ETIQUETTE_MM2 = 12.0

#: Part minimale d'une parcelle recouverte par l'emprise pour qu'elle compte
#: comme parcelle d'assiette. L'emprise et le Parcellaire Express ne sont pas
#: numérisés à partir des mêmes sources : leurs limites se croisent en produisant
#: des échardes de quelques mètres carrés, qui ne sont pas des parcelles du
#: projet et qui pollueraient le tableau récapitulatif comme la notice.
PART_MIN_ASSIETTE = 0.02

#: Part au-delà de laquelle une parcelle est tenue pour entièrement couverte.
#:
#: L'emprise d'un projet est un **découpage foncier** : elle suit les limites
#: cadastrales, elle ne les traverse pas. Une parcelle recoupée à 40 % n'est
#: donc ni une écharde de calage ni une parcelle d'assiette : c'est le signe
#: que le fichier d'emprise ne correspond pas au parcellaire.
#:
#: Mesuré le 05/09/2026 : le premier jeu d'essai de Sarnois portait une emprise
#: de 8,51 ha qui mordait sur dix parcelles voisines, alors que le projet tient
#: sur la seule ZA 0057. Rien ne le signalait — la planche dessinait fidèlement
#: ce qu'on lui donnait, et le tableau annonçait 27,96 ha de contenance pour
#: 8,51 ha d'emprise.
PART_PLEINE_ASSIETTE = 0.98

LARGEUR_TABLEAU_MM = 72.0

#: Colonnes que le tableau peut prendre sur le plan lui-même, et sur sa planche
#: dédiée. Au-delà de deux, il masque l'emprise qu'il est censé décrire ; seul
#: un plan vide, celui de la planche annexe, en porte davantage.
COLONNES_SUR_LE_PLAN = 2
COLONNES_SUR_SA_PLANCHE = 5


def generer(projet: Projet, emprise: Emprise, dossier: Path) -> Sortie:
    avertissements = []
    planche = nouvelle_planche(projet, NUMERO)
    zone = planche.zone_dessin()

    largeur_m, hauteur_m = emprise.dimensions_m
    denominateur = echelle_adaptative(
        largeur_m, hauteur_m, zone, marge=MARGE, valeurs=ECHELLES_CADASTRE
    )
    planche.definir_echelle(denominateur)
    planche.centrer_sur(emprise.centre)

    # Parcelles sur l'emprise de la planche élargie d'un tampon, pour que les
    # limites soient tracées jusqu'au bord du cadre.
    minx, miny, maxx, maxy = planche.emprise_terrain()
    tampon = max(50.0, 0.05 * max(maxx - minx, maxy - miny))
    parcelles = telecharger_parcelles(
        (minx - tampon, miny - tampon, maxx + tampon, maxy + tampon)
    )

    emprise_geom = emprise.geometrie
    touchees = [p for p in parcelles if p.geometrie.intersects(emprise_geom)]
    if not touchees:
        raise ErreurService(
            "Aucune parcelle cadastrale n'intersecte l'emprise du projet. "
            "Vérifiez le fichier d'emprise et son système de coordonnées."
        )
    concernees, echardes = [], []
    for parcelle in touchees:
        aire = parcelle.geometrie.area
        part = (
            parcelle.geometrie.intersection(emprise_geom).area / aire if aire else 0.0
        )
        (concernees if part >= PART_MIN_ASSIETTE else echardes).append(parcelle)
    entamees = parcelles_entamees(touchees, emprise_geom)
    if not concernees:
        raise ErreurService(
            f"Les {len(touchees)} parcelles rencontrées ne sont recoupées par "
            f"l'emprise qu'à moins de {PART_MIN_ASSIETTE:.0%} de leur surface : "
            "aucune parcelle d'assiette identifiable. Vérifiez le fichier d'emprise."
        )

    message = message_emprise_entamee(entamees)
    if message:
        avertissements.append(message)

    cadre_planche = box(minx, miny, maxx, maxy)
    ids_concernees = {p.idu for p in concernees}

    for parcelle in parcelles:
        if parcelle.idu in ids_concernees:
            continue
        planche.ajouter_geometrie(parcelle.geometrie, STYLE_PARCELLE)
    for parcelle in concernees:
        planche.ajouter_geometrie(parcelle.geometrie, STYLE_PARCELLE_CONCERNEE)

    # Bâtiments, hachurés comme sur un plan cadastral. Une emprise en secteur
    # agricole peut n'en contenir aucun : c'est un résultat, pas une anomalie.
    batiments = telecharger_batiments(
        (minx - tampon, miny - tampon, maxx + tampon, maxy + tampon)
    )
    if batiments:
        planche.ajouter_definition(MOTIF_BATIMENT)
        for batiment in batiments:
            planche.ajouter_geometrie(batiment.geometrie, STYLE_BATIMENT)

    # Étiquettes : seulement là où la parcelle est assez grande sur le papier.
    facteur = planche.transformation.mm_par_metre ** 2
    points, textes = [], []
    for parcelle in parcelles:
        visible = parcelle.geometrie.intersection(cadre_planche)
        if visible.is_empty or visible.area * facteur < SURFACE_MIN_ETIQUETTE_MM2:
            continue
        points.append(visible.representative_point())
        textes.append(parcelle.numero)
    planche.ajouter_etiquettes(
        points, textes, {"taille_mm": TAILLE_ETIQUETTE, "couleur": "#5a3800"}
    )

    planche.ajouter_geometrie(emprise_geom, STYLE_EMPRISE)

    planche.ajouter_legende(
        [
            (f"Emprise du projet — {nombre_fr(emprise.surface_m2 / 10_000.0)} ha",
             STYLE_EMPRISE),
            ("Parcelles d'assiette du projet", STYLE_PARCELLE_CONCERNEE),
            ("Autres parcelles cadastrales", STYLE_PARCELLE),
        ]
        + ([("Bâtiment", STYLE_BATIMENT)] if batiments else [])
    )

    tableau_reporte = not _tableau_parcelles(planche, concernees, emprise.surface_m2)
    if tableau_reporte:
        # Le plan ne dit pas où est passé son tableau : un lecteur qui ne le
        # trouve pas croirait la pièce incomplète.
        zone_x, zone_y, zone_l, zone_h = planche.zone_dessin()
        planche.ajouter_texte(
            zone_x + zone_l - 3.0, zone_y + 5.0,
            f"Tableau des {len(concernees)} parcelles d'assiette : "
            f"voir « {TITRE_TABLEAU} », planche suivante.",
            taille=TAILLE_COURANTE, ancre="end", gras=True, couleur=BLEU_UNITE,
            halo=True,
        )
    planche.ajouter_texte(
        zone[0] + 3.0,
        zone[1] + zone[3] - 2.5,
        SOURCE_IGN,
        taille=1.9,
        couleur="#333333",
        halo=True,
    )

    chemin = planche.rendre_pdf(Path(dossier) / "DP_1-3_plan_de_cadastre.pdf")
    return Sortie(
        numero=NUMERO,
        titre=TITRE,
        chemin=chemin,
        echelle=denominateur,
        planche=planche,
        details={
            "avertissements": avertissements,
            "tableau_reporte": tableau_reporte,
            "surface_emprise_m2": emprise.surface_m2,
            "nb_parcelles_tracees": len(parcelles),
            "nb_batiments": len(batiments),
            "parcelles_echardes": [p.designation for p in _triees(echardes)],
            "parcelles_assiette": [
                {
                    "idu": p.idu,
                    "section": p.section,
                    "numero": p.numero,
                    "contenance_m2": p.contenance_m2,
                    "commune": p.commune,
                }
                for p in _triees(concernees)
            ],
        },
    )


class _Ligne:
    """Une parcelle telle que le tableau la lit : trois champs, pas de géométrie.

    Reconstruite depuis les `details` de la planche du plan plutôt que d'un
    second appel au WFS : ce sont les mêmes parcelles, et les redemander
    exposerait le dossier à ce que l'IGN réponde autrement entre deux requêtes.
    """

    __slots__ = ("section", "numero", "contenance_m2")

    def __init__(self, donnees: dict):
        self.section = donnees["section"]
        self.numero = donnees["numero"]
        self.contenance_m2 = donnees["contenance_m2"] or 0.0


def generer_tableau(
    projet: Projet, details: dict, dossier: Path, numero: str | None = None
) -> Sortie:
    """La planche annexe : le tableau des parcelles d'assiette, seul.

    Produite **seulement** quand `generer` a reporté son tableau, c'est-à-dire
    quand il demandait plus de deux colonnes sur le plan. Là, sans plan
    au-dessous, il en prend jusqu'à cinq et part du bord gauche.

    `details` est celui de la `Sortie` du plan : la liste des parcelles
    d'assiette y est déjà, et la surface de l'emprise avec elle.
    """
    parcelles = [_Ligne(d) for d in details["parcelles_assiette"]]
    if not parcelles:
        raise ErreurRendu(
            "Aucune parcelle d'assiette à porter au tableau : la planche "
            "annexe n'a pas lieu d'être."
        )

    planche = nouvelle_planche(projet, NUMERO_TABLEAU, numero=numero)
    if not _tableau_parcelles(
        planche, parcelles, details.get("surface_emprise_m2", 0.0),
        colonnes_max=COLONNES_SUR_SA_PLANCHE, au_centre=True,
        note_source=SOURCE_IGN,
    ):
        zone_x, zone_y, zone_l, zone_h = planche.zone_dessin()
        par_colonne = int((zone_h - 6.0 - 18.8) // 4.2)
        raise ErreurRendu(
            f"{len(parcelles)} parcelles d'assiette : le tableau ne tient pas "
            f"même sur sa propre planche (au plus "
            f"{COLONNES_SUR_SA_PLANCHE * par_colonne}). Il faudrait le porter "
            "sur plusieurs planches, ce que l'outil ne sait pas encore faire."
        )

    chemin = planche.rendre_pdf(
        Path(dossier) / "DP_1-3bis_tableau_des_parcelles.pdf"
    )
    return Sortie(
        numero=NUMERO_TABLEAU,
        titre=TITRE_TABLEAU,
        chemin=chemin,
        planche=planche,
        details={"nb_parcelles": len(parcelles)},
    )


def message_emprise_entamee(entamees) -> str:
    """Ce qu'il faut dire d'une emprise qui coupe des parcelles en deux.

    Rendu à part de la planche pour être vérifiable sans le WFS : le contrôle
    porte sur des parts de surface, pas sur un service en ligne.
    """
    if not entamees:
        return ""
    detail = ", ".join(
        f"{parcelle.section} {parcelle.numero} ({part:.0%})"
        for parcelle, part in sorted(entamees, key=lambda e: e[1])[:6]
    )
    return (
        f"L'emprise traverse {len(entamees)} parcelle(s) au lieu d'en suivre les "
        f"limites : {detail}. Une emprise de projet est un découpage foncier, "
        "elle épouse le parcellaire. Vérifiez le fichier d'emprise — le tableau "
        "des parcelles d'assiette compte ces parcelles en entier, et sa "
        "contenance ne vaudra pas celle du projet."
    )


def parcelles_entamees(parcelles, emprise_geom) -> list:
    """Parcelles que l'emprise recoupe sans les prendre en entier.

    En deçà de `PART_MIN_ASSIETTE` c'est une écharde de calage, au-delà de
    `PART_PLEINE_ASSIETTE` la parcelle est prise entière : entre les deux,
    l'emprise coupe la parcelle en deux, ce qu'un découpage foncier ne fait pas.
    """
    entamees = []
    for parcelle in parcelles:
        aire = parcelle.geometrie.area
        if not aire:
            continue
        part = parcelle.geometrie.intersection(emprise_geom).area / aire
        if PART_MIN_ASSIETTE <= part < PART_PLEINE_ASSIETTE:
            entamees.append((parcelle, part))
    return entamees


def _triees(parcelles):
    return sorted(parcelles, key=lambda p: (p.section, p.numero))


def _tableau_parcelles(
    planche, concernees, surface_emprise_m2: float,
    colonnes_max: int = COLONNES_SUR_LE_PLAN, au_centre: bool = False,
    note_source: str | None = None,
) -> bool:
    """Tableau récapitulatif section / numéro / contenance.

    Le tableau bascule sur deux colonnes plutôt que de déborder du cadre : une
    liste tronquée passerait inaperçue à la relecture.

    Il est **posé par-dessus le plan**, en haut à droite, et non à côté de lui :
    au-delà de deux colonnes il masquerait l'emprise elle-même — mesuré le
    28/09/2026 sur Gannay-sur-Loire, dont les 139 parcelles d'assiette en
    demandaient trois. Ces cas-là reportent le tableau sur sa propre planche,
    où il se centre et prend jusqu'à cinq colonnes (`au_centre`, `colonnes_max`
    relevé).

    Rend **faux** quand la liste ne tient pas dans `colonnes_max` : l'appelant
    décide alors de la reporter, plutôt que de recevoir une exception pour une
    situation qui a une issue.
    """
    zone_x, zone_y, zone_l, zone_h = planche.zone_dessin()
    lignes = _triees(concernees)
    hauteur_ligne = 4.2
    # cadre, titre, en-têtes ; + la note sous le total
    hauteur_entete = 2 * 2.2 + 5.0 + hauteur_ligne
    taille_note = 6 * PT
    interligne_note = 1.35
    note = (
        "Contenance : surface légale portée au cadastre. Surface graphique de "
        f"l'emprise dessinée : {_contenance(surface_emprise_m2)}."
    )
    if note_source:
        # Sur la planche annexe, le tableau occupe toute la hauteur : une
        # mention de source posée au bas du cadre tomberait sur cette note-ci.
        note = f"{note} {note_source}"
    # La note vient sous le total, et sa hauteur doit être réservée **avant**
    # de décider combien de lignes tiennent. Ajoutée après coup, elle poussait
    # le cadre du tableau par-dessus le cartouche — visible le 28/09/2026 sur la
    # planche annexe de Gannay, la seule assez remplie pour que ça se voie. Le
    # repli est mesuré sur une seule colonne, le cas le plus étroit et donc le
    # plus haut : réserver trop vaut mieux que déborder.
    hauteur_note_reservee = 2.0 + taille_note * interligne_note * len(
        planche.decouper_en_lignes(note, LARGEUR_TABLEAU_MM - 4.4, taille_note)
    )
    hauteur_dispo = zone_h - 6.0 - hauteur_note_reservee

    par_colonne = max(1, int((hauteur_dispo - hauteur_entete - hauteur_ligne)
                             // hauteur_ligne))
    nb_colonnes = -(-len(lignes) // par_colonne)
    if nb_colonnes > colonnes_max:
        return False
    nb_colonnes = max(1, nb_colonnes)

    largeur = LARGEUR_TABLEAU_MM * nb_colonnes
    x = (
        zone_x + (zone_l - largeur) / 2.0
        if au_centre
        else zone_x + zone_l - largeur - 3.0
    )
    y = zone_y + 3.0
    # La note est repliée sur la largeur du tableau : mesurée avec le moteur de
    # rendu, elle ne peut pas déborder du cadre.
    lignes_note = planche.decouper_en_lignes(note, largeur - 4.4, taille_note)
    hauteur_note = 2.0 + taille_note * interligne_note * len(lignes_note)
    hauteur = hauteur_entete + hauteur_ligne * (
        min(len(lignes), par_colonne) + 1
    ) + hauteur_note

    planche.ajouter_rectangle(
        x, y, largeur, hauteur,
        Style(trait=NOIR, epaisseur_mm=0.25, remplissage="#ffffff",
              opacite_remplissage=0.92),
    )
    planche.ajouter_texte(
        x + 2.2, y + 5.2, "Parcelles d'assiette", taille=TAILLE_COURANTE,
        gras=True, couleur=BLEU_UNITE,
    )

    y_entete = y + 10.4
    total = 0.0
    for index_colonne in range(nb_colonnes):
        gauche = x + index_colonne * LARGEUR_TABLEAU_MM
        colonnes = (gauche + 2.2, gauche + 18.0, gauche + 40.0)
        for abscisse, intitule in zip(colonnes, ("Section", "Numéro", "Contenance")):
            planche.ajouter_texte(
                abscisse, y_entete, intitule, taille=TAILLE_ETIQUETTE, gras=True
            )
        planche.ajouter_ligne(
            gauche + 2.0, y_entete + 1.4,
            gauche + LARGEUR_TABLEAU_MM - 2.0, y_entete + 1.4,
            Style(trait=NOIR, epaisseur_mm=0.2),
        )
        tranche = lignes[index_colonne * par_colonne:(index_colonne + 1) * par_colonne]
        for index, parcelle in enumerate(tranche):
            ordonnee = y_entete + hauteur_ligne * (index + 1)
            total += parcelle.contenance_m2
            valeurs = (parcelle.section, parcelle.numero,
                       _contenance(parcelle.contenance_m2))
            for abscisse, valeur in zip(colonnes, valeurs):
                planche.ajouter_texte(
                    abscisse, ordonnee, valeur, taille=TAILLE_ETIQUETTE
                )

    ordonnee = y + hauteur - hauteur_note - 2.4
    colonnes = (x + 2.2, x + 18.0, x + 40.0)
    planche.ajouter_ligne(
        x + 2.0, ordonnee - 2.8, x + largeur - 2.0, ordonnee - 2.8,
        Style(trait=NOIR, epaisseur_mm=0.2),
    )
    planche.ajouter_texte(
        colonnes[0], ordonnee,
        f"Total ({len(lignes)} parcelle{'s' if len(lignes) > 1 else ''})",
        taille=TAILLE_ETIQUETTE, gras=True,
    )
    planche.ajouter_texte(
        colonnes[2], ordonnee, _contenance(total), taille=TAILLE_ETIQUETTE, gras=True
    )
    # Les deux surfaces ne se recouvrent pas et n'ont pas à le faire : la
    # contenance est la surface légale portée au cadastre, l'emprise est le
    # polygone dessiné. Les afficher côte à côte évite de chercher l'erreur.
    planche.ajouter_paragraphe(
        colonnes[0], ordonnee + 3.6, note, largeur - 4.4,
        taille=taille_note, interligne=interligne_note, justifie=False,
        couleur=GRIS,
    )
    return True


def _contenance(valeur_m2: float) -> str:
    return nombre_fr(valeur_m2, 0) + " m²"
