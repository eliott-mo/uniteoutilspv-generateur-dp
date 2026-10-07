"""Le cadrage d'un plan de repérage dont les prises de vue n'existent pas encore.

C'est la conséquence la plus profonde du lot 8 : la sortie PowerPoint se produit
**avant** que le chef de projet ait traité ses photographies, donc avant qu'il y
ait des points de vue à faire tenir dans le cadre. `zone_de_reperage` vise les
points de vue d'abord et ne peut pas servir ; `cadrages_sans_vues` cadre sur
l'emprise plus 150 m, et décline le même cadre aux crans d'échelle suivants pour
que le chef de projet garde celui où son point de vue tombe (décision D2).

Ces tests mesurent aussi que la géométrie des cadres photo est **une seule
arithmétique** : celle de `photographies.disposition`, partagée par la planche du
dossier PDF, l'écran de saisie et les réservations d'image du `.pptx`.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from dp_socle.erreurs import ErreurComposition, ErreurPointDeVue
from dp_socle.planche import Planche
from dp_socle.planches.photographies import disposition, rapport_de_l_emplacement
from dp_socle.planches.reperage_vues import (
    ECHELLES_REPERAGE_VUES,
    MARGE_SANS_VUES_M,
    cadrages_sans_vues,
)

#: Cotes des deux cadres d'une planche à deux emplacements, relevées le
#: 25/09/2026 par la sonde du lot 8 et par le dossier de référence avant elle.
CADRES_ATTENDUS = (
    (185.5, 18.1, 222.0, 115.4),
    (185.5, 150.1, 222.0, 115.4),
)

#: Rapports imposés par le nombre d'emplacements, mesurés sur la planche.
RAPPORT_DEUX = 1.924
RAPPORT_TROIS = 3.109


def _planche() -> Planche:
    return Planche(
        titre="DP 7 : PHOTOGRAPHIE ENVIRONNEMENT PROCHE", numero="12",
        projet="PV-TÉMOIN", date="25/09/2026",
    )


def _emprise(largeur_m: float = 400.0, hauteur_m: float = 300.0):
    return box(700000.0, 6900000.0, 700000.0 + largeur_m, 6900000.0 + hauteur_m)


# ---------------------------------------------------------------------------
# La géométrie des cadres, une seule fois pour trois usages
# ---------------------------------------------------------------------------


def test_les_cadres_tombent_ou_la_sonde_les_a_mesures():
    plan = disposition(_planche(), 2)

    mesures = [
        (
            round(pose.image[0], 1), round(pose.image[1], 1),
            round(pose.image[2], 1), round(pose.image[3], 1),
        )
        for pose in plan.emplacements
    ]
    assert mesures == [
        (round(c[0], 1), round(c[1], 1), round(c[2], 1), round(c[3], 1))
        for c in CADRES_ATTENDUS
    ]


@pytest.mark.parametrize(
    "emplacements, rapport", [(2, RAPPORT_DEUX), (3, RAPPORT_TROIS)]
)
def test_le_rapport_du_cadre_ne_depend_que_du_nombre_d_emplacements(
    emplacements, rapport
):
    """1,92:1 à deux cadres, 3,11:1 à trois : les bandeaux du dossier de référence."""
    plan = disposition(_planche(), emplacements)

    for pose in plan.emplacements:
        assert pose.rapport == pytest.approx(rapport, abs=0.005)


def test_l_ecran_de_saisie_et_la_planche_lisent_le_meme_cadre():
    """Deux arithmétiques donneraient deux rognages, et l'écran mentirait."""
    planche = _planche()

    assert rapport_de_l_emplacement(planche, 2) == pytest.approx(
        disposition(planche, 2).emplacements[0].rapport
    )


def test_le_panneau_de_reperage_prend_ce_que_la_colonne_d_images_laisse():
    plan = disposition(_planche(), 2)

    panneau_x, panneau_y, panneau_l, panneau_h = plan.panneau
    cadre_x = plan.emplacements[0].cadre[0]
    # Le panneau s'arrête un blanc tournant avant la colonne d'images.
    assert panneau_x + panneau_l + 4.0 == pytest.approx(cadre_x)
    assert panneau_l == pytest.approx(169.0, abs=0.5)
    assert (panneau_y, panneau_h) == pytest.approx(
        (plan.emplacements[0].cadre[1], 260.0), abs=0.5
    )


def test_une_colonne_d_images_qui_ne_laisse_rien_est_refusee(monkeypatch):
    """Un plan de repérage de moins de 60 mm ne se lit pas : on refuse."""
    import dp_socle.planches.photographies as photographies

    monkeypatch.setattr(photographies, "LARGEUR_COLONNE_IMAGES_MM", 390.0)
    with pytest.raises(ErreurComposition, match="plan de repérage"):
        photographies.disposition(_planche(), 2)


# ---------------------------------------------------------------------------
# Le cadrage qui ignore les points de vue
# ---------------------------------------------------------------------------


def test_le_cadre_est_l_emprise_elargie_de_150_m():
    plan = disposition(_planche(), 2)
    emprise = _emprise()

    reperages, avertissements = cadrages_sans_vues(
        emprise, plan.panneau, "DP 7 — plan de repérage"
    )

    assert avertissements == []
    assert len(reperages) == 1
    minx, miny, maxx, maxy = reperages[0].cadre
    e_minx, e_miny, e_maxx, e_maxy = emprise.bounds
    assert (minx, miny) == pytest.approx(
        (e_minx - MARGE_SANS_VUES_M, e_miny - MARGE_SANS_VUES_M)
    )
    assert (maxx, maxy) == pytest.approx(
        (e_maxx + MARGE_SANS_VUES_M, e_maxy + MARGE_SANS_VUES_M)
    )
    # Le site tient forcément en entier : c'est lui qui décide du cadre.
    assert reperages[0].site_entier


def test_l_echelle_est_la_plus_grande_de_la_liste_qui_contient_le_cadre():
    """La plus grande échelle, donc le plus petit dénominateur qui suffit.

    Le cadre mesure 700 x 600 m pour une emprise de 400 x 300 : dans un panneau
    de 169 mm de large, il faut au moins le 1/5 000.
    """
    plan = disposition(_planche(), 2)

    reperages, _ = cadrages_sans_vues(_emprise(), plan.panneau, "DP 7")

    denominateur = reperages[0].denominateur
    assert denominateur in ECHELLES_REPERAGE_VUES
    rang = ECHELLES_REPERAGE_VUES.index(denominateur)
    if rang:
        # Le cran d'avant ne suffisait pas : sinon ce n'est pas la plus grande.
        precedent = ECHELLES_REPERAGE_VUES[rang - 1]
        largeur_papier = 700.0 / precedent * 1000.0
        assert largeur_papier > plan.panneau[2]


def test_dp8_recoit_trois_cadrages_du_meme_cadre_a_trois_echelles():
    """Trois diapos, même contenu, trois échelles successives (décision D2)."""
    plan = disposition(_planche(), 2)
    emprise = _emprise(200.0, 150.0)

    reperages, avertissements = cadrages_sans_vues(
        emprise, plan.panneau, "DP 8", alternatives=3
    )

    assert avertissements == []
    assert len(reperages) == 3
    denominateurs = [r.denominateur for r in reperages]
    rang = ECHELLES_REPERAGE_VUES.index(denominateurs[0])
    assert denominateurs == list(ECHELLES_REPERAGE_VUES[rang:rang + 3])
    # Le cadre ne change pas : seule l'échelle change, donc ce qu'on voit autour.
    assert all(r.cadre == reperages[0].cadre for r in reperages)


def test_un_site_deja_large_recoit_moins_de_cadrages_et_le_dit():
    """La liste s'arrête au 1/15 000, et le rapport dit combien manquent.

    Aucun repli silencieux : une alternative absente s'écrit, elle ne se devine
    pas au nombre de diapos.

    Le site d'essai s'est élargi le 07/10/2026 : la liste a gagné deux crans —
    1/12 500 et 1/15 000, pour les photomontages à 500–750 m du site — et
    1 300 m de large y trouvaient de nouveau trois cadrages.
    """
    plan = disposition(_planche(), 2)

    reperages, avertissements = cadrages_sans_vues(
        _emprise(1500.0, 900.0), plan.panneau, "DP 8", alternatives=3
    )

    assert len(reperages) < 3
    assert reperages[-1].denominateur == ECHELLES_REPERAGE_VUES[-1]
    assert any("cadrage(s) au choix" in message for message in avertissements)


def test_un_site_plus_large_que_la_liste_est_refuse():
    """Au-delà, le site n'occuperait plus seize millimètres sur la planche."""
    plan = disposition(_planche(), 2)

    with pytest.raises(ErreurPointDeVue, match="ne tient à aucune échelle"):
        cadrages_sans_vues(_emprise(4000.0, 3000.0), plan.panneau, "DP 7")


def test_une_emprise_absente_est_refusee():
    plan = disposition(_planche(), 2)

    with pytest.raises(ErreurPointDeVue, match="aucune emprise"):
        cadrages_sans_vues(None, plan.panneau, "DP 7")
