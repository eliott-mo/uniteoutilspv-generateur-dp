"""Tests de mesure de texte et de justification.

SVG n'a pas de justification native et CairoSVG n'implémente ni `textLength`
ni `lengthAdjust` : les mots sont positionnés un par un, à partir des chasses
mesurées par cairo. Ces tests vérifient que le bord droit des lignes justifiées
tombe bien sur la largeur demandée.
"""

from __future__ import annotations

import re

import pytest

from dp_socle.planche import Planche

pytest.importorskip("cairocffi", reason="cairo est nécessaire pour mesurer le texte")

TEXTE = (
    "Le terrain d'assiette du projet est situé sur la commune de "
    "Bray-Saint-Aignan, en bordure de la route départementale, sur des parcelles "
    "agricoles aujourd'hui cultivées. Le projet consiste en l'implantation de "
    "structures photovoltaïques fixes, ancrées au sol par pieux battus."
)

LARGEUR = 120.0
TAILLE = 3.0


def _planche():
    return Planche(
        titre="TEST", numero="T", projet="Test", date="01/09/2026",
        avec_cartouche=False,
    )


def test_mesure_proportionnelle_a_la_taille():
    planche = _planche()
    simple = planche.mesurer_texte("Bray-Saint-Aignan", 4.0)
    double = planche.mesurer_texte("Bray-Saint-Aignan", 8.0)
    assert simple > 0
    assert double == pytest.approx(2 * simple, rel=1e-6)


def test_decoupage_respecte_la_largeur():
    planche = _planche()
    for mots in planche.decouper_en_lignes(TEXTE, LARGEUR, TAILLE):
        assert planche.mesurer_texte(" ".join(mots), TAILLE) <= LARGEUR


def _lignes_du_svg(svg: str):
    """Regroupe les éléments <text> du SVG par ordonnée."""
    lignes = {}
    motif = re.compile(r'<text x="([-\d.]+)" y="([-\d.]+)"[^>]*>([^<]*)</text>')
    for x, y, contenu in motif.findall(svg):
        lignes.setdefault(float(y), []).append((float(x), contenu))
    return [sorted(v) for _, v in sorted(lignes.items())]


def test_justification_atteint_le_bord_droit():
    planche = _planche()
    planche.ajouter_paragraphe(20.0, 40.0, TEXTE, LARGEUR, taille=TAILLE)
    lignes = _lignes_du_svg(planche.svg())
    assert len(lignes) >= 3, "le texte témoin doit tenir sur plusieurs lignes"

    for mots in lignes[:-1]:  # toutes sauf la dernière ligne du paragraphe
        abscisse, dernier = mots[-1]
        bord_droit = abscisse + planche.mesurer_texte(dernier, TAILLE)
        assert bord_droit == pytest.approx(20.0 + LARGEUR, abs=0.01)


def test_derniere_ligne_non_etiree():
    planche = _planche()
    planche.ajouter_paragraphe(20.0, 40.0, TEXTE, LARGEUR, taille=TAILLE)
    lignes = _lignes_du_svg(planche.svg())
    abscisse, dernier = lignes[-1][-1]
    bord_droit = abscisse + planche.mesurer_texte(dernier, TAILLE)
    assert bord_droit < 20.0 + LARGEUR


def test_paragraphe_non_justifie_reste_une_seule_ligne_par_ordonnee():
    planche = _planche()
    planche.ajouter_paragraphe(
        20.0, 40.0, TEXTE, LARGEUR, taille=TAILLE, justifie=False
    )
    for mots in _lignes_du_svg(planche.svg()):
        assert len(mots) == 1
