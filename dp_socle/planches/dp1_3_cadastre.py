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

from ..echelle import echelle_adaptative
from ..erreurs import ErreurService
from ..geometrie import Emprise
from ..ign import telecharger_parcelles
from ..planche import (
    NOIR,
    STYLE_EMPRISE,
    STYLE_PARCELLE,
    STYLE_PARCELLE_CONCERNEE,
    TAILLE_COURANTE,
    TAILLE_ETIQUETTE,
    Style,
)
from ..projet import Projet
from .commun import Sortie, nouvelle_planche

NUMERO = "DP 1-3"
TITRE = "PLAN DE CADASTRE"

#: Échelles autorisées pour cette planche.
ECHELLES_CADASTRE = (500, 1000, 2000, 5000)

#: Marge autour de l'emprise, exprimée en fraction de ses dimensions.
MARGE = 0.20

#: Surface minimale d'une parcelle sur le papier, en mm², pour être étiquetée.
SURFACE_MIN_ETIQUETTE_MM2 = 12.0

LARGEUR_TABLEAU_MM = 72.0


def generer(projet: Projet, emprise: Emprise, dossier: Path) -> Sortie:
    planche = nouvelle_planche(projet, NUMERO, TITRE)
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
    concernees = [p for p in parcelles if p.geometrie.intersects(emprise_geom)]
    if not concernees:
        raise ErreurService(
            "Aucune parcelle cadastrale n'intersecte l'emprise du projet. "
            "Vérifiez le fichier d'emprise et son système de coordonnées."
        )

    cadre_planche = box(minx, miny, maxx, maxy)
    ids_concernees = {p.idu for p in concernees}

    for parcelle in parcelles:
        if parcelle.idu in ids_concernees:
            continue
        planche.ajouter_geometrie(parcelle.geometrie, STYLE_PARCELLE)
    for parcelle in concernees:
        planche.ajouter_geometrie(parcelle.geometrie, STYLE_PARCELLE_CONCERNEE)

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
            (f"Emprise du projet ({emprise.surface_m2 / 10_000.0:.2f} ha)",
             STYLE_EMPRISE),
            ("Parcelles d'assiette du projet", STYLE_PARCELLE_CONCERNEE),
            ("Autres parcelles cadastrales", STYLE_PARCELLE),
        ]
    )

    _tableau_parcelles(planche, concernees)
    planche.ajouter_texte(
        zone[0] + 3.0,
        zone[1] + zone[3] - 2.5,
        "Source : IGN — Parcellaire Express (PCI), WFS Géoplateforme",
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
        details={
            "nb_parcelles_tracees": len(parcelles),
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


def _triees(parcelles):
    return sorted(parcelles, key=lambda p: (p.section, p.numero))


def _tableau_parcelles(planche, concernees) -> None:
    """Tableau récapitulatif section / numéro / contenance, en haut à droite."""
    zone_x, zone_y, zone_l, _ = planche.zone_dessin()
    x = zone_x + zone_l - LARGEUR_TABLEAU_MM - 3.0
    y = zone_y + 3.0

    lignes = _triees(concernees)
    hauteur_ligne = 4.2
    hauteur = 2 * 2.2 + 5.0 + hauteur_ligne * (len(lignes) + 2)

    planche.ajouter_rectangle(
        x, y, LARGEUR_TABLEAU_MM, hauteur,
        Style(trait=NOIR, epaisseur_mm=0.25, remplissage="#ffffff",
              opacite_remplissage=0.92),
    )
    planche.ajouter_texte(
        x + 2.2, y + 5.2, "Parcelles d'assiette", taille=TAILLE_COURANTE, gras=True
    )

    colonnes = (x + 2.2, x + 18.0, x + 40.0)
    y_entete = y + 10.4
    for abscisse, intitule in zip(colonnes, ("Section", "Numéro", "Contenance")):
        planche.ajouter_texte(
            abscisse, y_entete, intitule, taille=TAILLE_ETIQUETTE, gras=True
        )
    planche.ajouter_ligne(
        x + 2.0, y_entete + 1.4, x + LARGEUR_TABLEAU_MM - 2.0, y_entete + 1.4,
        Style(trait=NOIR, epaisseur_mm=0.2),
    )

    total = 0.0
    for index, parcelle in enumerate(lignes):
        ordonnee = y_entete + hauteur_ligne * (index + 1)
        total += parcelle.contenance_m2
        valeurs = (
            parcelle.section,
            parcelle.numero,
            _contenance(parcelle.contenance_m2),
        )
        for abscisse, valeur in zip(colonnes, valeurs):
            planche.ajouter_texte(
                abscisse, ordonnee, valeur, taille=TAILLE_ETIQUETTE
            )

    ordonnee = y_entete + hauteur_ligne * (len(lignes) + 1)
    planche.ajouter_ligne(
        x + 2.0, ordonnee - 2.8, x + LARGEUR_TABLEAU_MM - 2.0, ordonnee - 2.8,
        Style(trait=NOIR, epaisseur_mm=0.2),
    )
    planche.ajouter_texte(
        colonnes[0], ordonnee, f"Total ({len(lignes)} parcelles)",
        taille=TAILLE_ETIQUETTE, gras=True,
    )
    planche.ajouter_texte(
        colonnes[2], ordonnee, _contenance(total), taille=TAILLE_ETIQUETTE, gras=True
    )


def _contenance(valeur_m2: float) -> str:
    return f"{valeur_m2:,.0f}".replace(",", " ") + " m²"
