"""Retours de relecture du 05/09/2026, mesurés.

Chaque test répond à une remarque faite sur les trois dossiers d'essai, et
mesure ce qui avait été vu à l'œil : un contour qui ne se remplissait pas, une
maille de grillage qui changeait de finesse avec l'échelle de la planche, une
emprise qui mordait sur les parcelles voisines.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from shapely.geometry import LineString, Polygon, box

from dp_socle.planches.dp1_3_cadastre import (
    PART_MIN_ASSIETTE,
    PART_PLEINE_ASSIETTE,
    message_emprise_entamee,
    parcelles_entamees,
)
from dp_socle.planches.dp4_ouvrages import (
    CITERNES,
    CONTENEURS,
    MAILLE_GRILLAGE_M,
    REDONDANTS,
)
from dp_socle.planches.palette import fermer_les_contours


# ---------------------------------------------------------------------------
# Un contour ouvert n'est pas un trait : il se remplit
# ---------------------------------------------------------------------------


def _contour_en_morceaux(largeur: float, hauteur: float) -> list:
    """Les quatre côtés d'un rectangle, exportés séparément par la CAO."""
    return [
        LineString([(0.0, 0.0), (largeur, 0.0)]),
        LineString([(largeur, 0.0), (largeur, hauteur)]),
        LineString([(largeur, hauteur), (0.0, hauteur)]),
        LineString([(0.0, hauteur), (0.0, 0.0)]),
    ]


def test_un_contour_ouvert_est_recousu_en_surface():
    """La citerne de refroidissement sortait en contour, sans remplissage.

    Relevé sur Sarnois : son calque porte dix polylignes et aucun polygone. La
    légende annonçait un aplat et la planche montrait un trait.
    """
    messages = []
    obtenu = fermer_les_contours(
        _contour_en_morceaux(11.7, 9.3), "citerne_refroidissement", messages
    )
    surfaces = [g for g in obtenu if g.geom_type == "Polygon"]
    assert len(surfaces) == 1
    assert surfaces[0].area == pytest.approx(11.7 * 9.3, rel=1e-6)
    assert messages, "une recomposition doit s'écrire au rapport"


def test_un_lineaire_n_est_pas_recousu():
    """Le portail est un linéaire : ses arcs de débattement se referment.

    Mesuré le 05/09/2026 : sans ce garde-fou, les deux arcs du portail de
    Sarnois donnaient deux surfaces de 9,6 m² qui n'existent pas.
    """
    messages = []
    lignes = _contour_en_morceaux(3.5, 2.8)
    assert fermer_les_contours(lignes, "portail", messages) == lignes
    assert not messages


def test_un_contour_minuscule_n_est_pas_un_ouvrage():
    messages = []
    lignes = _contour_en_morceaux(0.4, 0.4)
    assert fermer_les_contours(lignes, "bess", messages) == lignes
    assert not messages


# ---------------------------------------------------------------------------
# La maille du grillage est une dimension, pas un figuré
# ---------------------------------------------------------------------------


@dataclass
class _DessinCompteur:
    """Un `Dessin` réduit à ce que `_grillage` lui demande."""

    denominateur: int
    lignes: int = 0
    rectangles: int = 0

    def ligne(self, depart, arrivee, style=None) -> None:
        self.lignes += 1

    def rectangle(self, x, y, largeur, hauteur, style=None) -> None:
        self.rectangles += 1


def test_la_maille_du_grillage_ne_depend_pas_de_l_echelle():
    """Le même grillage sortait deux fois plus fin sur une planche au 1:100.

    La maille était exprimée en millimètres de papier : elle valait 8 cm de
    terrain au 1:100 et 16 cm au 1:200. C'est une dimension d'ouvrage, elle se
    dessine à sa taille.
    """
    from dp_socle.planches.dp4_ouvrages import _grillage

    comptes = []
    for denominateur in (100, 200):
        dessin = _DessinCompteur(denominateur=denominateur)
        _grillage(dessin, 0.0, 7.5, 2.0)
        comptes.append(dessin.lignes)
    assert comptes[0] == comptes[1]
    # 7,50 m de large et 2,00 m de haut à la maille retenue.
    attendu = int(7.5 / MAILLE_GRILLAGE_M) - 1 + int(2.0 / MAILLE_GRILLAGE_M) - 1
    assert comptes[0] == attendu


# ---------------------------------------------------------------------------
# Une citerne est une citerne
# ---------------------------------------------------------------------------


def test_la_citerne_de_refroidissement_s_efface_devant_la_citerne_incendie():
    """Deux planches de citerne à cotes près l'une de l'autre : une suffit."""
    assert REDONDANTS["citerne_refroidissement"] == "bache_incendie"
    assert "citerne_refroidissement" in CITERNES
    assert "bache_incendie" in CITERNES


def test_les_conteneurs_se_dessinent_comme_des_conteneurs():
    """BESS et local de stockage sont des conteneurs maritimes, pas des bacs."""
    assert set(CONTENEURS) == {"bess", "local_technique"}


# ---------------------------------------------------------------------------
# Une emprise de projet épouse le parcellaire
# ---------------------------------------------------------------------------


@dataclass
class _Parcelle:
    section: str
    numero: str
    geometrie: Polygon


def test_une_emprise_qui_coupe_une_parcelle_est_signalee():
    """Le premier jeu d'essai de Sarnois mordait sur dix parcelles voisines.

    Rien ne le signalait : la planche dessinait fidèlement ce qu'on lui donnait,
    et le tableau annonçait 27,96 ha de contenance pour 8,51 ha d'emprise.
    """
    parcelles = [
        _Parcelle("ZA", "0057", box(0.0, 0.0, 100.0, 100.0)),
        _Parcelle("ZA", "0058", box(100.0, 0.0, 200.0, 100.0)),
    ]
    # L'emprise prend la première en entier et mord de moitié sur la seconde.
    entamees = parcelles_entamees(parcelles, box(0.0, 0.0, 150.0, 100.0))

    assert [p.numero for p, _ in entamees] == ["0058"]
    assert entamees[0][1] == pytest.approx(0.5)
    assert "0058" in message_emprise_entamee(entamees)


def test_une_emprise_qui_suit_le_parcellaire_ne_dit_rien():
    parcelles = [
        _Parcelle("ZA", "0057", box(0.0, 0.0, 100.0, 100.0)),
        _Parcelle("ZA", "0058", box(100.0, 0.0, 200.0, 100.0)),
    ]
    assert parcelles_entamees(parcelles, box(0.0, 0.0, 100.0, 100.0)) == []
    assert message_emprise_entamee([]) == ""


def test_les_deux_seuils_de_l_assiette_encadrent_bien():
    """Une écharde de calage n'est pas une parcelle coupée en deux."""
    assert 0.0 < PART_MIN_ASSIETTE < PART_PLEINE_ASSIETTE < 1.0
