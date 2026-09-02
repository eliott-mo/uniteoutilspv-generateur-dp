"""Tests du référentiel des pièces du dossier."""

from __future__ import annotations

import pytest

from dp_socle.dossier import PIECES, PIECES_PRODUITES, numero_planche, piece


def test_codes_uniques():
    codes = [p.code for p in PIECES if p.code]
    assert len(codes) == len(set(codes))


def test_page_de_garde_en_tete_et_sans_code():
    assert PIECES[0].code == ""
    assert PIECES[0].produite


def test_numerotation_compte_la_page_de_garde():
    """La page de garde est la planche 1 : DP 1-1 commence donc à la planche 2."""
    assert numero_planche("DP 1-1") == 2
    assert numero_planche("DP 1-2") == 3
    assert numero_planche("DP 1-3") == 4


def test_numerotation_continue_et_sans_trou():
    attendus = list(range(1, len(PIECES_PRODUITES) + 1))
    obtenus = [
        numero_planche(p.code) if p.code else 1 for p in PIECES_PRODUITES
    ]
    assert obtenus == attendus


def test_intitules():
    assert piece("DP 1-3").intitule == "DP 1-3 : Plan de cadastre"
    assert piece("DP 1-3").intitule_cartouche == "DP 1-3 : PLAN DE CADASTRE"


def test_pieces_des_lots_suivants_declarees_non_produites():
    for code in ("DP 2", "DP 3", "DP 4-1", "DP 4-2", "DP 6", "DP 11"):
        assert not piece(code).produite


def test_piece_inconnue():
    with pytest.raises(KeyError):
        piece("DP 99")
