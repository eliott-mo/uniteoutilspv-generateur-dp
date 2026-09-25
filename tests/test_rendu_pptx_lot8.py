"""Le rendu des planches pour le `.pptx` : la voie retenue, et ce qu'elle pèse.

Le lot 8 ne choisit pas d'avance entre vectoriel et matriciel : il rend les deux
et garde le plus léger **une fois déflaté**, parce que c'est le poids que le ZIP
du `.pptx` portera. Ces tests mesurent trois choses que rien d'autre ne
rattraperait :

- que `poids_dans_le_paquet` dit bien ce qu'un vrai ZIP écrit — sans quoi la
  comparaison des deux voies se ferait sur un chiffre imaginaire ;
- que la voie retenue tombe du bon côté sur une planche vectorielle comme sur une
  planche que son fond raster domine ;
- que le SVG produit ne porte plus aucun `<text>`, seule chose qui garantisse que
  PowerPoint ne recomposera pas le cartouche avec ses propres métriques.

Aucun service en ligne : les planches sont composées ici, et le fond raster est
un bruit fabriqué exprès — incompressible, donc représentatif d'une ortho IGN.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from PIL import Image
from shapely.geometry import box

from dp_socle import rendu_pptx
from dp_socle.erreurs import ErreurSortiePPTX
from dp_socle.planche import HAUTEUR_MM, LARGEUR_MM, Planche

pytest.importorskip(
    "cairosvg", reason="CairoSVG et libcairo sont nécessaires pour rendre une planche"
)

#: Taille de pixel d'une A3 paysage à 200 dpi. Mesurée le 25/09/2026 dans un PDF
#: réellement exporté depuis PowerPoint : c'est exactement ce que l'export rend,
#: quelle que soit la résolution qu'on lui donne en entrée.
PIXELS_A3_200_DPI = (3308, 2339)


def _planche(titre: str = "TÉMOIN") -> Planche:
    return Planche(
        titre=titre, numero="1", projet="Contrôle du rendu PPTX",
        date="25/09/2026", echelle=2000,
    )


def _planche_vectorielle() -> Planche:
    """Une planche sans autre raster que le logo : du trait et du texte."""
    planche = _planche("PLAN DE MASSE")
    planche.centrer_sur((700000.0, 6900000.0))
    for rang in range(40):
        planche.ajouter_geometrie(
            box(699800 + rang * 10, 6899800, 699806 + rang * 10, 6900200)
        )
    planche.ajouter_legende([("Tables photovoltaïques", {"remplissage": "#1C2445"})])
    return planche


def _planche_a_fond_raster() -> Planche:
    """Une planche que son fond raster domine, comme une DP 1-2 sur ortho.

    Le fond est un bruit pseudo-aléatoire : il ne se comprime pas, exactement
    comme le grain d'une orthophotographie. Un aplat uni se comprimerait à
    quelques kilo-octets et ne mesurerait rien.
    """
    import random

    generateur = random.Random(25092026)
    largeur, hauteur = 1200, 850
    image = Image.new("RGB", (largeur, hauteur))
    image.putdata([
        (generateur.randrange(256), generateur.randrange(256), generateur.randrange(256))
        for _ in range(largeur * hauteur)
    ])
    planche = _planche("PHOTO AÉRIENNE")
    planche.centrer_sur((700000.0, 6900000.0))
    planche.ajouter_fond_raster(image, (699000.0, 6899200.0, 701000.0, 6900800.0))
    return planche


# ---------------------------------------------------------------------------
# La mesure sur laquelle tout repose
# ---------------------------------------------------------------------------


def test_le_poids_deflate_est_celui_qu_un_vrai_zip_ecrit(tmp_path):
    """La comparaison des deux voies se fait sur ce chiffre : il doit être juste.

    Mesuré contre `zipfile` lui-même, et non contre une constante : c'est la
    bibliothèque standard qui écrira le `.pptx`.
    """
    donnees = ("<svg>" + "du texte qui se comprime bien " * 500 + "</svg>").encode()

    annonce = rendu_pptx.poids_dans_le_paquet(donnees)

    archive = tmp_path / "temoin.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as paquet:
        paquet.writestr("media/planche.svg", donnees)
    with zipfile.ZipFile(archive) as paquet:
        reel = paquet.getinfo("media/planche.svg").compress_size
    assert annonce == reel


def test_la_taille_de_pixel_est_celle_que_l_export_pdf_rend():
    """3 308 x 2 339 px : la mesure du 25/09/2026, et le plafond de PowerPoint."""
    assert rendu_pptx.taille_en_pixels(LARGEUR_MM, HAUTEUR_MM) == PIXELS_A3_200_DPI


# ---------------------------------------------------------------------------
# La voie retenue
# ---------------------------------------------------------------------------


def test_une_planche_de_trait_part_en_vectoriel():
    """Là où tout est vectoriel, le SVG en tracés pèse moins que le JPEG."""
    fond = rendu_pptx.rendre_fond(_planche_vectorielle(), "DP 2")

    assert fond.voie == rendu_pptx.VECTORIELLE
    assert fond.svg is not None
    assert fond.poids[rendu_pptx.VECTORIELLE] < fond.poids[rendu_pptx.MATRICIELLE]
    # Le repli matriciel accompagne le SVG, et doit rester marginal : c'est lui
    # qui annulerait la raison d'être de la voie s'il partait à 200 dpi.
    assert rendu_pptx.poids_dans_le_paquet(fond.image) < fond.poids[
        rendu_pptx.VECTORIELLE
    ]


def test_une_planche_que_son_fond_raster_domine_part_en_matriciel():
    """Vectoriser une photographie ne fait que la réencoder, en plus lourd."""
    fond = rendu_pptx.rendre_fond(_planche_a_fond_raster(), "DP 1-2")

    assert fond.voie == rendu_pptx.MATRICIELLE
    assert fond.svg is None
    assert fond.poids[rendu_pptx.MATRICIELLE] < fond.poids[rendu_pptx.VECTORIELLE]


def test_le_svg_retenu_ne_porte_plus_de_texte_a_composer():
    """Zéro `<text>` : c'est ce qui garantit le cartouche du PDF, au pixel près.

    Avec du texte vivant, PowerPoint le recompose avec ses propres métriques et
    la chasse change — le défaut mesuré le 25/09/2026 avant de passer en tracés.
    """
    fond = rendu_pptx.rendre_fond(_planche_vectorielle(), "DP 2")

    assert b"<text" not in fond.svg
    assert b"<path" in fond.svg
    # Le SVG reste un SVG complet, que PowerPoint doit pouvoir ouvrir seul.
    assert fond.svg.lstrip().startswith(b"<?xml")


def test_le_matriciel_est_une_image_lisible_a_la_bonne_taille():
    """Le fond matriciel plein format porte exactement les pixels de l'export."""
    fond = rendu_pptx.rendre_fond(_planche_a_fond_raster(), "DP 1-2")

    with Image.open(io.BytesIO(fond.image)) as image:
        assert image.size == PIXELS_A3_200_DPI
        assert image.format == "JPEG"


def test_le_resume_dit_la_voie_et_les_deux_poids():
    """Une voie choisie sans qu'on sache pourquoi est une décision illisible."""
    fond = rendu_pptx.rendre_fond(_planche_vectorielle(), "DP 2")

    resume = fond.resume("DP 2")

    assert "DP 2" in resume
    assert rendu_pptx.VECTORIELLE in resume
    assert "en matriciel" in resume
    assert "Mo dans le fichier" in resume


# ---------------------------------------------------------------------------
# La notice, rastérisée depuis le PDF produit
# ---------------------------------------------------------------------------


def test_chaque_page_de_la_notice_devient_un_png_a_200_dpi(tmp_path):
    """La notice n'a pas de SVG : elle est fusionnée au niveau du PDF.

    Elle se rastérise donc depuis le PDF produit, page par page, et en PNG :
    voir `rendre_pages_pdf` pour ce que cet encodage coûte et pourquoi il reste
    retenu.
    """
    planche = _planche("NOTICE")
    planche.ajouter_texte(40.0, 60.0, "Notice descriptive du projet", taille=4.0)
    pdf = planche.rendre_pdf(tmp_path / "DP_11_notice.pdf")

    pages = rendu_pptx.rendre_pages_pdf(pdf, "DP 11")

    assert len(pages) == 1
    with Image.open(io.BytesIO(pages[0])) as image:
        assert image.format == "PNG"
        assert image.size == PIXELS_A3_200_DPI
        # Aplatie sur blanc, jamais sur noir : un `convert("RGB")` direct
        # remplirait de noir le fond transparent du rendu.
        assert image.convert("RGB").getpixel((10, 10)) == (255, 255, 255)


def test_une_notice_introuvable_est_refusee_plutot_que_sautee(tmp_path):
    with pytest.raises(ErreurSortiePPTX, match="introuvable"):
        rendu_pptx.rendre_pages_pdf(tmp_path / "absente.pdf", "DP 11")
