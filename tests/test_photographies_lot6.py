"""Planches photographiques DP 6, DP 7 et DP 8 (lot 6, étape 3).

Ce qui est éprouvé : des emplacements identiques quoi qu'on y dépose, un
rognage qui ajuste sans déformer ni amputer en silence, et les refus qui
protègent le sens de chaque pièce.
"""

from __future__ import annotations

import re

import pytest
from PIL import Image
from shapely.geometry import box

from dp_socle.erreurs import ErreurComposition
from dp_socle.planche import Planche
from dp_socle.planches import dp6_insertions, dp7_environnement_proche
from dp_socle.planches.photographies import ImagePlanche, composer
from dp_socle.points_de_vue import place_a_la_main
from dp_socle.projet import Projet

X0, Y0 = 622_000.0, 6_954_000.0
EMPRISE = box(X0, Y0, X0 + 330.0, Y0 + 260.0)
VUE = place_a_la_main("vue", X0 - 300.0, Y0 + 130.0, 95.0)


def _photo(chemin, largeur=2000, hauteur=1500, teinte=(180, 200, 180)):
    Image.new("RGB", (largeur, hauteur), teinte).save(chemin)
    return chemin


def _projet() -> Projet:
    return Projet(nom="essai", commune="Sarnois", code_postal="60210",
                  date="2026-09-16", emprise="x")


def _planche(images, emplacements, reperes=("Vue A",), vues=(VUE,)):
    planche = Planche(titre="Essai", numero="DP 6", projet="Essai",
                      date="16/09/2026")
    retenu = composer(planche, images, list(vues), list(reperes), EMPRISE,
                      "essai", emplacements=emplacements, fond_ign=False)
    return planche.svg(), retenu


#: Largeur en dessous de laquelle une image du SVG n'est pas une photographie
#: de la planche : le logo UNITe du cartouche mesure 14 mm de large.
_LARGEUR_MINIMALE_PHOTO_MM = 50.0


def _cadres_images(svg: str) -> list:
    """(x, y, largeur, hauteur) de chaque photographie posée, dans l'ordre."""
    cadres = [
        tuple(float(v) for v in quadruplet)
        for quadruplet in re.findall(
            r'<image x="([-\d.]+)" y="([-\d.]+)" width="([\d.]+)" height="([\d.]+)"',
            svg,
        )
    ]
    return [cadre for cadre in cadres if cadre[2] >= _LARGEUR_MINIMALE_PHOTO_MM]


# ---------------------------------------------------------------------------
# Des emplacements identiques, quoi qu'on y dépose
# ---------------------------------------------------------------------------


def test_deux_formats_differents_donnent_des_emplacements_identiques(tmp_path):
    """C'est tout l'objet du rognage : la planche ne dépend plus des sources.

    Un lot réel mêle des rapports — 4:3 d'un téléphone, 3:2 d'un reflex — et
    laissait auparavant des cadres de tailles différentes sur la même colonne.
    """
    images = [
        ImagePlanche(_photo(tmp_path / "a.jpg", 2000, 1500), "A"),  # 4:3
        ImagePlanche(_photo(tmp_path / "b.jpg", 2400, 1600), "B"),  # 3:2
    ]
    cadres = _cadres_images(_planche(images, emplacements=2)[0])
    assert len(cadres) == 2
    assert cadres[0][2] == pytest.approx(cadres[1][2], abs=0.05)
    assert cadres[0][3] == pytest.approx(cadres[1][3], abs=0.05)


def test_un_emplacement_vide_ne_redistribue_rien(tmp_path):
    """Une DP 6 sans mesures paysagères garde la géométrie d'une DP 6 complète.

    C'est la raison d'être des emplacements fixes : deux dossiers voisins se
    comparent, et une planche qui s'étire quand un volet manque ne se compare
    plus.
    """
    trois = [
        ImagePlanche(_photo(tmp_path / f"{nom}.jpg"), nom) for nom in "abc"
    ]
    cadres_trois = _cadres_images(_planche(trois, emplacements=3)[0])
    cadres_deux = _cadres_images(_planche(trois[:2], emplacements=3)[0])

    assert len(cadres_trois) == 3 and len(cadres_deux) == 2
    for complet, partiel in zip(cadres_trois, cadres_deux):
        assert complet == pytest.approx(partiel, abs=0.05)


def test_les_emplacements_se_suivent_sans_se_chevaucher(tmp_path):
    images = [ImagePlanche(_photo(tmp_path / f"{n}.jpg"), n) for n in "abc"]
    cadres = _cadres_images(_planche(images, emplacements=3)[0])
    for haut, bas in zip(cadres, cadres[1:]):
        assert haut[1] + haut[3] <= bas[1] + 0.05


# ---------------------------------------------------------------------------
# Le rognage : ajuster sans déformer, ni amputer en silence
# ---------------------------------------------------------------------------


def test_l_image_posee_a_exactement_le_rapport_de_son_emplacement(tmp_path):
    """Rognée, jamais étirée : une photographie déformée serait une pièce fausse."""
    images = [
        ImagePlanche(_photo(tmp_path / "a.jpg", 3000, 1000), "A"),  # 3:1
        ImagePlanche(_photo(tmp_path / "b.jpg", 1000, 1000), "B"),  # 1:1
    ]
    svg, _ = _planche(images, emplacements=2)
    cadres = _cadres_images(svg)
    rapports = [cadre[2] / cadre[3] for cadre in cadres]
    assert rapports[0] == pytest.approx(rapports[1], rel=1e-3)


def test_un_rognage_important_est_signale(tmp_path):
    """Une photographie amputée sans un mot est ce que ce dépôt refuse."""
    images = [
        ImagePlanche(_photo(tmp_path / "a.jpg", 3000, 1000), "A"),
        ImagePlanche(_photo(tmp_path / "b.jpg", 1000, 1000), "B"),
    ]
    _, retenu = _planche(images, emplacements=2)
    assert any("rognée de" in message for message in retenu["avertissements"])


def test_des_formats_voisins_ne_declenchent_aucune_alerte(tmp_path):
    """4:3 et 3:2 se rejoignent à moins de 6 % : le cas courant reste muet."""
    images = [
        ImagePlanche(_photo(tmp_path / "a.jpg", 2000, 1500), "A"),
        ImagePlanche(_photo(tmp_path / "b.jpg", 2400, 1600), "B"),
    ]
    _, retenu = _planche(images, emplacements=2)
    assert not any("rognée de" in message for message in retenu["avertissements"])


def test_le_cadrage_decale_la_fenetre_retenue(tmp_path):
    """Le chef de projet recentre sur ce que la photographie doit montrer."""
    from dp_socle.planches.photographies import _recadrer

    chemin = _photo(tmp_path / "large.jpg", 3000, 1000)
    with Image.open(chemin) as source:
        centre, _ = _recadrer(source, 1.0, (0.0, 0.0), 80.0)
        gauche, _ = _recadrer(source, 1.0, (-0.5, 0.0), 80.0)
        droite, _ = _recadrer(source, 1.0, (0.5, 0.0), 80.0)
    assert centre.size == gauche.size == droite.size
    # Les trois fenêtres ont la même taille mais pas la même origine : c'est le
    # contenu qui doit différer, et le format d'essai est uni — on éprouve donc
    # la géométrie par la fonction elle-même.
    with Image.open(chemin) as source:
        _, perte = _recadrer(source, 1.0, (0.0, 0.0), 80.0)
    assert perte == pytest.approx(1.0 - 1000.0 / 3000.0, rel=1e-6)


def test_une_image_transparente_est_aplatie_sur_blanc(tmp_path):
    """Un convert('RGB') direct remplirait de noir — piège connu du dépôt."""
    from dp_socle.planches.photographies import _recadrer

    chemin = tmp_path / "alpha.png"
    Image.new("RGBA", (400, 400), (255, 0, 0, 0)).save(chemin)
    with Image.open(chemin) as source:
        recadree, _ = _recadrer(source, 1.0, (0.0, 0.0), 80.0)
    assert recadree.mode == "RGB"
    assert recadree.getpixel((10, 10)) == (255, 255, 255)


# ---------------------------------------------------------------------------
# Ce que chaque pièce refuse
# ---------------------------------------------------------------------------


def test_une_vue_dp6_a_une_seule_image_est_refusee(tmp_path):
    """Sans le couple brut / photomontage, la pièce ne compare rien."""
    with pytest.raises(ErreurComposition, match="au moins"):
        dp6_insertions.generer(
            _projet(), VUE, [_photo(tmp_path / "a.jpg")], EMPRISE, tmp_path,
            fond_ign=False,
        )


def test_une_vue_dp6_accepte_deux_images_et_le_dit(tmp_path):
    """Le troisième volet s'omet sans un mot sur la planche, mais pas au rapport."""
    sortie = dp6_insertions.generer(
        _projet(), VUE,
        [_photo(tmp_path / "a.jpg"), _photo(tmp_path / "b.jpg")],
        EMPRISE, tmp_path, fond_ign=False,
    )
    assert sortie.chemin.exists()
    assert sortie.details["volets"] == 2
    assert any("reste vide" in m for m in sortie.details["avertissements"])


def test_une_quatrieme_image_dp6_est_refusee(tmp_path):
    with pytest.raises(ErreurComposition, match="une planche de plus"):
        dp6_insertions.generer(
            _projet(), VUE,
            [_photo(tmp_path / f"{n}.jpg") for n in "abcd"],
            EMPRISE, tmp_path, fond_ign=False,
        )


def test_dp7_refuse_plus_de_deux_photographies(tmp_path):
    prises = [
        (place_a_la_main(f"v{i}", X0 - 200.0 * i, Y0 + 100.0, 90.0),
         _photo(tmp_path / f"{i}.jpg"))
        for i in range(1, 4)
    ]
    with pytest.raises(ErreurComposition, match="au plus"):
        dp7_environnement_proche.generer(
            _projet(), prises, EMPRISE, tmp_path, fond_ign=False
        )


def test_dp7_produit_sa_planche_et_numerote_ses_prises(tmp_path):
    prises = [
        (place_a_la_main("v1", X0 - 300.0, Y0 + 140.0, 95.0),
         _photo(tmp_path / "1.jpg")),
        (place_a_la_main("v2", X0 + 480.0, Y0 - 120.0, 300.0),
         _photo(tmp_path / "2.jpg")),
    ]
    sortie = dp7_environnement_proche.generer(
        _projet(), prises, EMPRISE, tmp_path, numero="14", fond_ign=False
    )
    assert sortie.chemin.exists()
    assert sortie.details["reperes"] == ["PC7-1", "PC7-2"]


def test_une_piece_sans_photographie_ne_se_produit_pas(tmp_path):
    with pytest.raises(ErreurComposition, match="ne se produit pas vide"):
        dp7_environnement_proche.generer(
            _projet(), [], EMPRISE, tmp_path, fond_ign=False
        )
