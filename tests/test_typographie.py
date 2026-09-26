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
    """Deux fois la taille, deux fois la chasse — au millionième près.

    C'est la propriété que le crénage des métriques détruit : cairo arrondit
    alors l'avance de chaque glyphe à l'entier, et deux arrondis à deux tailles
    ne sont pas proportionnels. Ce test est donc le garde-fou portable du
    réglage posé par `polices._options_de_mesure` — il ne tombe pas sur Windows,
    dont le backend DirectWrite ignore le crénage, mais il tomberait sur la
    plateforme de déploiement si la mesure repassait en métriques crénées.
    """
    planche = _planche()
    simple = planche.mesurer_texte("Bray-Saint-Aignan", 4.0)
    double = planche.mesurer_texte("Bray-Saint-Aignan", 8.0)
    assert simple > 0
    assert double == pytest.approx(2 * simple, rel=1e-6)


def test_la_mesure_demande_des_metriques_non_crenees():
    """La chasse mesurée doit être celle du fichier de police, pas celle de l'écran.

    cairo arrondit l'avance de chaque glyphe à l'entier sur une surface
    **matricielle** — celle qui sert à mesurer — et la laisse fractionnaire sur
    une surface **vectorielle** — celle dont sortent les planches. Une même
    chaîne se mesurait donc autrement qu'elle ne se dessine.

    Constaté au premier déploiement, le 26/09/2026 : sous Linux, où FreeType
    honore ce crénage, les 26 glyphes du texte témoin d'Aptos mesuraient 830,000
    au lieu de 832,375 — exactement la somme de leurs avances arrondies une à
    une. Le contrôle de démarrage en concluait « Aptos non utilisée » et
    annonçait aux chefs de projet un cartouche décalé, alors que la police était
    bien celle-là. Windows ne peut pas le montrer, son backend DirectWrite
    ignorant le crénage : c'est pourquoi le réglage se vérifie ici tel qu'il est
    demandé, et son effet dans le test de proportionnalité ci-dessus.
    """
    import cairocffi

    from dp_socle.polices import _options_de_mesure

    assert _options_de_mesure().get_hint_metrics() == cairocffi.HINT_METRICS_OFF


def test_la_chasse_mesuree_est_celle_du_fichier_de_police():
    """Ce que cairo mesure et ce que le TTF déclare doivent coïncider.

    C'est le critère du contrôle de démarrage, posé ici en test : il n'a de sens
    que si Aptos est réellement résolue par cairo — sur un poste de
    développement, cela demande de l'avoir installée (voir le README).
    """
    from dp_socle.polices import (
        POLICE_PRINCIPALE,
        _TAILLE_TEMOIN,
        _TEMOIN,
        _chasse_ttf,
        chasse_cairo,
        etat_polices,
        fichier_principal,
    )

    if not etat_polices().disponible:
        pytest.skip("Aptos n'est pas résolue par cairo sur ce poste")
    attendue = _chasse_ttf(fichier_principal(), _TEMOIN, _TAILLE_TEMOIN)
    mesuree = chasse_cairo(_TEMOIN, POLICE_PRINCIPALE, _TAILLE_TEMOIN)
    assert mesuree == pytest.approx(attendue, rel=1e-6)
    # La somme des avances arrondies une à une, que le crénage aurait donnée.
    assert mesuree != pytest.approx(830.0, abs=1e-6)


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
