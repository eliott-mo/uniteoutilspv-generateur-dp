"""Calage d'un export HelioScope sur l'ortho IGN (« Caler sur l'ortho », section 2).

L'image de fond de l'export est une photographie aérienne du site : projetée
avec le calage courant, elle se cherche dans l'ortho IGN, et le décalage
trouvé est l'erreur du calage. Ce qui se mesure ici : la corrélation retrouve
un gabarit à sa place ; un fond qui ne se reconnaît pas ne change rien ; le
décalage mesuré a le signe et l'amplitude du déplacement ; et, sur l'ortho
réelle, Bray et Gannay, pré-positionnées sur leur emprise comme le fait
l'application, se calent là où les mesures indépendantes les avaient placées.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import pytest
from PIL import Image

from dp_socle.calage_ortho import (
    _affine_vers_l93,
    caler_sur_ortho,
    correlation_normalisee,
    fond_sur_grille,
    mesurer_sur_ortho,
)
from dp_socle.erreurs import ErreurCalage
from dp_socle.helioscope import (
    corriger_nord_sud,
    decaler_longitude,
    importer,
    metres_par_degre_longitude,
)
from tests.jeux_plan_pdf import (
    EXPORT_GANNAY,
    LONGITUDE_GANNAY,
    NORD_SUD_GANNAY_M,
    gannay_present,
)

besoin_gannay = pytest.mark.skipif(not gannay_present(), reason="jeu de Gannay absent")


def _texture(taille: int, graine: int = 0) -> np.ndarray:
    """Une texture lisse et sans motif répété, comme une photographie."""
    bruit = np.random.default_rng(graine).random((taille, taille))
    spectre = np.fft.rfft2(bruit)
    fy = np.fft.fftfreq(taille)[:, None]
    fx = np.fft.rfftfreq(taille)[None, :]
    return np.fft.irfft2(spectre * np.exp(-(fx**2 + fy**2) * 400), s=bruit.shape)


def test_la_correlation_retrouve_un_gabarit_a_sa_place():
    image = _texture(300)
    gabarit = image[40:240, 70:270]
    carte = correlation_normalisee(image, gabarit)
    ligne, colonne = np.unravel_index(int(np.argmax(carte)), carte.shape)
    assert (ligne, colonne) == (40, 70)
    assert carte[ligne, colonne] == pytest.approx(1.0, abs=1e-9)


def test_la_correlation_ne_voit_pas_la_luminosite():
    """Deux photographies du même lieu n'ont ni la même exposition ni le même contraste."""
    image = _texture(300, graine=1)
    gabarit = 3.0 * image[100:220, 30:200] + 50.0
    carte = correlation_normalisee(image, gabarit)
    assert np.unravel_index(int(np.argmax(carte)), carte.shape) == (100, 30)


@dataclass
class _Fond:
    image: Image.Image


def _implantation_gannay():
    implantation = importer(EXPORT_GANNAY)
    implantation.calage.longitude_origine = LONGITUDE_GANNAY
    corriger_nord_sud(implantation.calage, NORD_SUD_GANNAY_M)
    return implantation


@besoin_gannay
def test_un_fond_qui_ne_se_reconnait_pas_ne_change_rien():
    """Une ortho sans relief — autre site, nuage, chantier : on le dit, on ne cale pas."""
    implantation = _implantation_gannay()
    avant = (implantation.calage.longitude_origine, implantation.calage.correction_nord_sud_m)

    def grise(_couche, cadre, largeur_mm, hauteur_mm, dpi):
        taille = (round(largeur_mm / 25.4 * dpi), round(hauteur_mm / 25.4 * dpi))
        bruit = np.random.default_rng(3).integers(118, 122, size=(taille[1], taille[0]))
        return _Fond(Image.fromarray(bruit.astype(np.uint8)))

    with pytest.raises(ErreurCalage, match="ne se reconnaît pas"):
        caler_sur_ortho(implantation, telecharger=grise)
    assert (implantation.calage.longitude_origine, implantation.calage.correction_nord_sud_m) == avant


@besoin_gannay
def test_le_decalage_mesure_est_celui_du_site_dans_l_ortho():
    """Le site est dans l'ortho 12 m plus à l'est et 7 m plus au sud que le calage ne le pose.

    L'« ortho » est ici le fond HelioScope lui-même, posé au bon endroit : ce
    qui se vérifie, c'est que la mesure rend ce déplacement, avec son signe.
    """
    implantation = _implantation_gannay()
    vrai = copy.deepcopy(implantation.calage)
    decaler_longitude(vrai, 12.0)
    corriger_nord_sud(vrai, vrai.correction_nord_sud_m - 7.0)
    fond = implantation.fond

    def site_deplace(_couche, cadre, largeur_mm, hauteur_mm, dpi):
        taille = (round(largeur_mm / 25.4 * dpi), round(hauteur_mm / 25.4 * dpi))
        pas = (cadre[2] - cadre[0]) / taille[0]
        pixels = fond_sur_grille(fond, _affine_vers_l93(vrai, fond), (cadre[0], cadre[3]), pas, taille)
        return _Fond(Image.fromarray(pixels.clip(0, 255).astype(np.uint8)))

    mesure = mesurer_sur_ortho(implantation, telecharger=site_deplace)
    assert mesure.decalage_est_m == pytest.approx(12.0, abs=0.2)
    assert mesure.decalage_nord_m == pytest.approx(-7.0, abs=0.2)
    assert mesure.pic > 0.9


@pytest.mark.reseau
def test_bray_se_cale_la_ou_la_mesure_l_avait_place(tmp_path):
    """Pré-positionnée sur son emprise, Bray est à 22 m de sa place en est-ouest.

    Le calage sur l'ortho l'y ramène : là où l'avait placée, le 23/09/2026, la
    même corrélation faite avec OpenCV (`tests/jeux_plan_pdf.py`).
    """
    from dp_socle.geometrie import charger_emprise
    from dp_socle.helioscope import prepositionner
    from tests.jeux_plan_pdf import (
        DXF_BRAY,
        EMPRISE_SITE_BRAY,
        FOND_BRAY,
        LONGITUDE_BRAY,
        NORD_SUD_BRAY_M,
        bray_present,
        layout_cad,
    )

    if not bray_present():
        pytest.skip("jeu de Bray absent")
    implantation = importer(layout_cad(tmp_path, DXF_BRAY, FOND_BRAY))
    prepositionner(implantation, charger_emprise(EMPRISE_SITE_BRAY).geometrie)
    mesure = caler_sur_ortho(implantation)
    calage = implantation.calage
    ecart_est = (calage.longitude_origine - LONGITUDE_BRAY) * metres_par_degre_longitude(
        calage.latitude_origine
    )
    assert mesure.decalage_est_m == pytest.approx(22.3, abs=1.0)
    # 8 cm et 3 cm du calage d'OpenCV le 23/09/2026 ; le mètre de tolérance
    # laisse l'IGN renouveler son ortho sans que le test ne tombe.
    assert ecart_est == pytest.approx(0.0, abs=1.0)
    assert calage.correction_nord_sud_m == pytest.approx(NORD_SUD_BRAY_M, abs=1.0)
    assert mesure.pic > 3 * mesure.second_pic


@pytest.mark.reseau
@besoin_gannay
def test_gannay_se_cale_depuis_son_emprise_la_ou_le_photomontage_l_a_placee():
    """Pré-positionnée sur son emprise, Gannay est à 18 m de sa place en est-ouest.

    Le calage sur l'ortho la ramène à moins d'un mètre du calage qu'une
    corrélation indépendante avait trouvé dans le dépôt `photomontage` : 0,85 m
    à l'ouest et 0,23 m au nord, mesuré le 23/09/2026.
    """
    from dp_socle.geometrie import charger_emprise
    from dp_socle.helioscope import prepositionner
    from tests.jeux_plan_pdf import EMPRISE_GANNAY

    implantation = importer(EXPORT_GANNAY)
    prepositionner(implantation, charger_emprise(EMPRISE_GANNAY).geometrie)
    mesure = caler_sur_ortho(implantation)
    calage = implantation.calage
    ecart_est = (calage.longitude_origine - LONGITUDE_GANNAY) * metres_par_degre_longitude(
        calage.latitude_origine
    )
    assert mesure.decalage_est_m == pytest.approx(-18.6, abs=1.0)
    assert abs(ecart_est) < 1.5
    assert abs(calage.correction_nord_sud_m - NORD_SUD_GANNAY_M) < 1.5
