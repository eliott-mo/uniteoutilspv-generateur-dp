"""Tests du référentiel des pièces du dossier."""

from __future__ import annotations

import pytest

from dp_socle.dossier import (
    PIECES,
    PIECES_PRODUITES,
    codes_produits,
    numero_planche,
    piece,
)


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


def test_les_planches_du_lot_4_sont_produites():
    for code in ("DP 2", "DP 3", "DP 4-1", "DP 4-2", "DP 4-3"):
        assert piece(code).produite


def test_les_pieces_photographiques_sont_produites_depuis_le_lot_6():
    """Insertions paysagères et photographies, avec leur plan de repérage.

    Le générateur compose la planche autour des images déposées : il ne les
    fabrique pas, mais il les assemble, les numérote et les pagine au sommaire —
    c'est tout ce que `produite` décide.
    """
    for code in ("DP 6", "DP 7", "DP 8"):
        assert piece(code).produite


def test_la_notice_est_produite_depuis_le_lot_5():
    """Fournie en PDF par le chef de projet, mais habillée par l'outil.

    « Produite » ne dit pas qu'elle est composée : elle l'est au sens du
    dossier, c'est-à-dire que le générateur écrit ses planches, les numérote et
    les pagine au sommaire — c'est tout ce que `produite` décide.
    """
    assert piece("DP 11").produite


# ---------------------------------------------------------------------------
# Numérotation d'un dossier où toutes les pièces ne sont pas produites
# ---------------------------------------------------------------------------


def test_le_rang_se_calcule_sur_les_pieces_reellement_produites():
    """Un projet sans poste n'a pas de DP 4-1, et la suivante remonte d'un rang.

    Sans ce calcul, le cartouche de DP 4-2 annoncerait la planche 8 sur la
    page 7 du dossier assemblé — ce que `assemblage` refuserait, mais après
    avoir produit toutes les planches.
    """
    sans_poste = codes_produits(
        ["DP 1-1", "DP 1-2", "DP 1-3", "DP 2", "DP 3", "DP 4-2"]
    )
    assert numero_planche("DP 2", sans_poste) == 5
    assert numero_planche("DP 4-2", sans_poste) == 7


def test_un_dossier_sans_lot_4_garde_la_numerotation_du_socle():
    """Un projet sans contrat d'entrée s'arrête au plan de cadastre."""
    socle = codes_produits(["DP 1-1", "DP 1-2", "DP 1-3"])
    assert numero_planche("DP 1-3", socle) == 4
    with pytest.raises(KeyError, match="DP 2"):
        numero_planche("DP 2", socle)


def test_codes_produits_ordonne_selon_le_dossier():
    """L'ordre du dossier fait foi, pas celui dans lequel on cite les pièces."""
    assert codes_produits(["DP 3", "DP 1-1", "DP 2"]) == [
        "", "DP 1-1", "DP 2", "DP 3"
    ]


def test_codes_produits_refuse_une_piece_inconnue():
    with pytest.raises(KeyError, match="DP 99"):
        codes_produits(["DP 99"])


def test_piece_inconnue():
    with pytest.raises(KeyError):
        piece("DP 99")


# ---------------------------------------------------------------------------
# Le sommaire et les pièces facultatives (relevé du 02/10/2026)
# ---------------------------------------------------------------------------


def test_une_piece_facultative_ne_se_liste_au_sommaire_que_produite():
    """« DP 1-3 bis — » annonçait une pièce manquante qui n'avait pas lieu d'être.

    Relevé par le chef de projet : le tableau des parcelles n'est produit que
    lorsqu'il ne tient pas sur DP 1-3 — au-delà de deux colonnes il masque
    l'emprise qu'il décrit. Sur un dossier où il tient, le sommaire le listait
    quand même, sans page, et se lisait comme un oubli.

    Une pièce **attendue** et absente, elle, reste listée sans page : DP 3 sans
    coupe, DP 11 sans notice. C'est précisément leur absence qu'il faut voir
    avant le dépôt, et la distinction tient à ce seul champ.
    """
    from dp_socle.dossier import PIECES, PAR_CODE

    facultatives = {p.code for p in PIECES if p.facultative}
    assert facultatives == {"DP 1-3 bis", "DP 4-3"}
    # Celles qu'on veut voir manquer ne le sont pas.
    assert not PAR_CODE["DP 3"].facultative
    assert not PAR_CODE["DP 11"].facultative
    assert not PAR_CODE["DP 2"].facultative


def test_le_sommaire_saute_la_facultative_absente_et_garde_l_attendue():
    """Ce qui se mesure est la liste dessinée, pas l'intention.

    Le sommaire se compose des pièces à code ; la facultative n'y entre que si
    `pages` lui en donne une.
    """
    from dp_socle.dossier import PIECES

    def listees(pages):
        return [
            p.code
            for p in PIECES
            if p.code and (not p.facultative or pages.get(p.code))
        ]

    sans_tableau = listees({"DP 1-1": 2, "DP 1-3": 4, "DP 2": 5, "DP 4-3": 9})
    assert "DP 1-3 bis" not in sans_tableau
    assert "DP 4-3" in sans_tableau, "produite, donc listée"
    # L'attendue sans page reste au sommaire : c'est son absence qui doit se voir.
    assert "DP 3" in sans_tableau and "DP 11" in sans_tableau

    avec_tableau = listees({"DP 1-3 bis": 5, "DP 1-3": 4})
    assert "DP 1-3 bis" in avec_tableau
    assert "DP 4-3" not in avec_tableau, "non produite sur ce dossier-là"
