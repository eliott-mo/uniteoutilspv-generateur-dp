"""Plan de repérage des prises de vue (lot 6, étape 2).

Le cadrage et le choix d'échelle se mesurent sur des distances terrain, et la
symbolisation sur le PDF produit — pas sur les valeurs intermédiaires.
"""

from __future__ import annotations

import pytest
from shapely.geometry import box

from dp_socle.erreurs import ErreurPointDeVue
from dp_socle.planches import reperage_vues
from dp_socle.planches.reperage_vues import (
    ECHELLES_REPERAGE_VUES,
    plan_de_reperage,
    repere_de_vue,
    zone_de_reperage,
)
from dp_socle.points_de_vue import place_a_la_main

#: Emprise d'essai : 330 x 260 m, la taille d'un site de 5 ha, posée en Oise.
X0, Y0 = 622_000.0, 6_954_000.0
EMPRISE = box(X0, Y0, X0 + 330.0, Y0 + 260.0)
CENTRE = (X0 + 165.0, Y0 + 130.0)

#: La colonne de gauche d'une A3 paysage, cartouche déduit : c'est la place que
#: les planches du lot laissent au plan de repérage.
COLONNE_MM = (12.0, 12.0, 168.0, 210.0)


def _vue(dx, dy, cap=None, nom="vue"):
    return place_a_la_main(nom, CENTRE[0] + dx, CENTRE[1] + dy, cap)


# ---------------------------------------------------------------------------
# Les repères, dans la langue du dossier de référence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code, rang, attendu",
    [
        ("DP 6", 1, "Vue A"),
        ("DP 6", 2, "Vue B"),
        ("DP 7", 1, "PC7-1"),
        ("DP 7", 2, "PC7-2"),
        ("DP 8", 2, "PC8-2"),
    ],
)
def test_le_repere_suit_le_dossier_de_reference(code, rang, attendu):
    """Relevé sur Massay : DP 6 nomme par lettres, DP 7 et DP 8 numérotent."""
    assert repere_de_vue(code, rang) == attendu


def test_un_rang_hors_nomenclature_est_refuse():
    with pytest.raises(ErreurPointDeVue):
        repere_de_vue("DP 7", 0)
    with pytest.raises(ErreurPointDeVue, match="s'arrête à Z"):
        repere_de_vue("DP 6", 27)


# ---------------------------------------------------------------------------
# Le cadrage : ce qui doit tenir, et ce qui peut sortir
# ---------------------------------------------------------------------------


def test_le_cadre_contient_tous_les_points_de_vue():
    """Sans eux, la planche ne repère rien — c'est la seule exigence dure."""
    vues = [_vue(-400.0, 0.0), _vue(250.0, 300.0), _vue(0.0, -520.0)]
    reperage = plan_de_reperage(vues, EMPRISE, COLONNE_MM)
    minx, miny, maxx, maxy = reperage.cadre
    for vue in vues:
        assert minx <= vue.x <= maxx and miny <= vue.y <= maxy


def test_le_cadre_garde_le_site_entier_quand_il_le_peut():
    vues = [_vue(-120.0, 60.0), _vue(180.0, -40.0)]
    reperage = plan_de_reperage(vues, EMPRISE, COLONNE_MM)
    assert reperage.site_entier
    minx, miny, maxx, maxy = reperage.cadre
    e_minx, e_miny, e_maxx, e_maxy = EMPRISE.bounds
    assert minx <= e_minx and maxx >= e_maxx
    assert miny <= e_miny and maxy >= e_maxy
    assert reperage.avertissements == ()


def test_un_paysage_lointain_a_un_gros_kilometre_tient_avec_tout_le_site():
    """La distance réelle d'une prise de vue de DP 8, relevée le 16/09/2026.

    Quelques centaines de mètres du site, un gros kilomètre au plus — et non les
    « plusieurs kilomètres » qu'annonçait le brief. La liste s'arrête donc au
    1/10 000, qui couvre 1,68 km dans la colonne.
    """
    vues = [_vue(0.0, 1_100.0), _vue(-900.0, 0.0)]
    reperage = plan_de_reperage(vues, EMPRISE, COLONNE_MM)
    assert reperage.site_entier
    assert reperage.denominateur <= 10000
    assert reperage.avertissements == ()


def test_une_emprise_etendue_cede_avant_l_echelle():
    """Décision du 14/09/2026 : DP 2 montre le site, cette planche le repérage.

    Le cas demande une emprise d'un kilomètre et demi, très au-delà des 3 MWc
    de nos dossiers, mais c'est lui qui vérifie l'ordre des renoncements : le
    cadre lâche le site avant de lâcher les prises de vue ou de sortir de la
    liste.

    Le site d'essai est passé de 1 000 à 1 500 m le 07/10/2026 : la liste a
    gagné deux crans — 1/12 500 et 1/15 000, pour les photomontages à 500–750 m
    du site — et le kilomètre d'avant y tenait de nouveau en entier, ce qui ne
    vérifiait plus rien.
    """
    large = box(X0, Y0, X0 + 1_500.0, Y0 + 300.0)
    centre_large = (X0 + 750.0, Y0 + 150.0)
    vues = [place_a_la_main("loin", X0 - 1_200.0, Y0 + 150.0)]
    reperage = plan_de_reperage(vues, large, COLONNE_MM)
    assert not reperage.site_entier
    assert reperage.denominateur in ECHELLES_REPERAGE_VUES
    assert any("ne tient pas en entier" in m for m in reperage.avertissements)
    minx, miny, maxx, maxy = reperage.cadre
    # Ce qui reste garanti : la prise de vue, et le centre du site.
    assert minx <= vues[0].x <= maxx
    assert minx <= centre_large[0] <= maxx and miny <= centre_large[1] <= maxy


def test_une_prise_de_vue_a_50_km_est_refusee():
    """À cette distance, ce n'est plus une photographie de ce site."""
    with pytest.raises(ErreurPointDeVue, match="plus une photographie"):
        plan_de_reperage([_vue(50_000.0, 0.0)], EMPRISE, COLONNE_MM)


def test_l_echelle_retenue_est_la_plus_grande_qui_tienne():
    """La liste est ordonnée : la précédente ne doit pas convenir."""
    vues = [_vue(-300.0, 0.0), _vue(300.0, 0.0)]
    reperage = plan_de_reperage(vues, EMPRISE, COLONNE_MM)
    rang = ECHELLES_REPERAGE_VUES.index(reperage.denominateur)
    if rang == 0:
        return
    minx, miny, maxx, maxy = reperage.cadre
    plus_grande = ECHELLES_REPERAGE_VUES[rang - 1]
    largeur_mm = (maxx - minx) * 1000.0 / plus_grande
    hauteur_mm = (maxy - miny) * 1000.0 / plus_grande
    assert largeur_mm > COLONNE_MM[2] or hauteur_mm > COLONNE_MM[3]


def test_le_cadre_tient_dans_la_colonne_a_l_echelle_retenue():
    """Le cadre **tracé**, marge comprise : c'est la leçon du lot 4."""
    vues = [_vue(-700.0, 250.0), _vue(400.0, -600.0)]
    reperage = plan_de_reperage(vues, EMPRISE, COLONNE_MM)
    minx, miny, maxx, maxy = reperage.cadre
    assert (maxx - minx) * 1000.0 / reperage.denominateur <= COLONNE_MM[2] + 1e-6
    assert (maxy - miny) * 1000.0 / reperage.denominateur <= COLONNE_MM[3] + 1e-6


def test_une_seule_vue_au_centre_ne_donne_pas_un_cadre_plat():
    """Une boîte dégénérée donnerait une échelle infinie."""
    reperage = plan_de_reperage([_vue(0.0, 0.0)], EMPRISE, COLONNE_MM)
    minx, miny, maxx, maxy = reperage.cadre
    assert maxx - minx > 1.0 and maxy - miny > 1.0


def test_sans_point_de_vue_le_plan_de_reperage_refuse():
    with pytest.raises(ErreurPointDeVue, match="ne repère rien"):
        zone_de_reperage([], EMPRISE)


def test_sans_emprise_le_plan_de_reperage_refuse():
    with pytest.raises(ErreurPointDeVue, match="ne situerait rien"):
        zone_de_reperage([_vue(0.0, 0.0)], None)


# ---------------------------------------------------------------------------
# Ce qui est dessiné, mesuré sur le SVG de la planche
# ---------------------------------------------------------------------------


def _planche_avec(vues, reperes, denominateur=2500):
    from dp_socle.planche import Planche

    planche = Planche(
        titre="Essai", numero="DP 7", projet="Essai", date="15/09/2026",
        echelle=denominateur,
    )
    planche.centrer_sur(CENTRE)
    messages = reperage_vues.dessiner_points_de_vue(planche, vues, reperes)
    return planche.svg(), messages


def test_un_point_sans_direction_confirmee_ne_porte_aucun_cone():
    """Critère de validation 3 : aucun cap inventé, et le rapport le dit."""
    svg, messages = _planche_avec([_vue(0.0, 0.0, nom="a")], ["PC7-1"])
    assert reperage_vues._VISEE not in svg
    assert any("sans cône" in m for m in messages)
    assert "PC7-1" in svg


def test_une_direction_confirmee_ouvre_un_cone_sans_rien_demander_de_plus():
    """Décision du 16/09/2026 : position et orientation suffisent.

    Plus de focale à lire, donc plus de photographie écartée faute d'en
    annoncer une — une sur cinq du jeu de validation était dans ce cas.
    """
    svg, messages = _planche_avec([_vue(0.0, 0.0, cap=90.0)], ["PC7-1"])
    assert f'fill="{reperage_vues._VISEE}"' in svg
    assert messages == []


def test_le_cone_garde_sa_taille_quelle_que_soit_l_echelle():
    """C'est un symbole de lecture, comme le repère, pas un objet du site."""
    import re

    largeurs = []
    for denominateur in (1000, 10000):
        svg, _ = _planche_avec([_vue(0.0, 0.0, cap=90.0)], ["PC7-1"], denominateur)
        chemins = re.findall(rf'd="([^"]+)"[^>]*fill="{reperage_vues._VISEE}"', svg)
        assert chemins, f"cône introuvable au 1/{denominateur}"
        points = [float(v) for v in re.findall(r"(-?[\d.]+)", chemins[0])]
        xs = points[0::2]
        largeurs.append(max(xs) - min(xs))
    assert largeurs[0] == pytest.approx(largeurs[1], rel=0.02)


def test_le_cone_pointe_bien_vers_l_est_pour_un_cap_de_90():
    """La conversion azimut vers angle mathématique est le piège du lot.

    Un cap de 90° regarde l'est : le cône doit donc s'étendre à droite du
    repère, et rester centré sur son ordonnée. Inverser les conventions
    l'enverrait au nord.
    """
    import re

    svg, _ = _planche_avec([_vue(0.0, 0.0, cap=90.0)], ["PC7-1"])
    chemins = re.findall(rf'd="([^"]+)"[^>]*fill="{reperage_vues._VISEE}"', svg)
    assert chemins, "cône introuvable"
    points = [float(v) for v in re.findall(r"(-?[\d.]+)", chemins[0])]
    xs, ys = points[0::2], points[1::2]
    sommet_x, sommet_y = xs[0], ys[0]  # le premier point est la prise de vue
    assert max(xs) > sommet_x + 5.0, "le cône ne s'ouvre pas vers l'est"
    assert max(xs) - sommet_x > abs(max(ys) - sommet_y), "le cône penche vers le nord"
    assert abs((max(ys) + min(ys)) / 2 - sommet_y) < 1.0, "le cône n'est pas centré"


def test_le_repere_garde_sa_taille_quelle_que_soit_l_echelle():
    """C'est un symbole de lecture, pas un objet du site.

    Dessiné en unités terrain, il doit suivre l'échelle pour garder le même
    diamètre sur le papier — sans quoi il ferait 2,4 mm au 1/1 000 et 0,6 mm au
    1/10 000, où il disparaîtrait.
    """
    import re

    diametres = []
    for denominateur in (1000, 10000):
        svg, _ = _planche_avec([_vue(0.0, 0.0)], ["PC7-1"], denominateur)
        # Le disque est le seul contour blanc rempli de la planche.
        chemins = re.findall(r'd="([^"]+)"[^>]*fill="#ffffff"', svg)
        assert chemins, f"repère introuvable au 1/{denominateur}"
        points = [float(v) for v in re.findall(r'(-?[\d.]+)', chemins[0])]
        xs = points[0::2]
        diametres.append(max(xs) - min(xs))
    assert diametres[0] == pytest.approx(diametres[1], rel=0.02)
    assert diametres[0] == pytest.approx(2 * reperage_vues.RAYON_REPERE_MM, rel=0.05)


def test_un_repere_manquant_pour_une_vue_est_refuse():
    with pytest.raises(ErreurPointDeVue, match="lequel nommer"):
        _planche_avec([_vue(0.0, 0.0), _vue(10.0, 0.0)], ["PC7-1"])
