"""Palette et légende des planches du dossier (décisions D3 et D4).

La légende est ce qui se relit le plus vite sur une planche déposée, et une
catégorie qui y manque ou qui s'y confond avec une autre ne se voit pas à la
relecture. Les deux règles qui la gouvernent sont mesurées ici plutôt que
confiées à l'œil : ce qui n'est pas dessiné n'y figure pas, et deux teintes
susceptibles de se côtoyer restent distinguables à l'impression.
"""

from __future__ import annotations

from itertools import combinations

import pytest

from dp_socle.planches.palette import (
    ECART_MINIMAL,
    EXCLUES,
    LIBELLE_BATIMENT,
    LIBELLE_PARCELLE,
    STYLES,
    categories_dessinables,
    construire_legende,
    couleur_significative,
    ecart_perceptuel,
    style,
    vers_lab,
)

#: Teintes relevées au pixel sur la planche DP 2 du dossier HOCH « Les
#: Islettes » du 25/04/2024, telles que le contrat les porte. Elles sont
#: reprises telles quelles : c'est le document que l'instructeur a l'habitude
#: de voir, et le lot 4 n'a pas à le redessiner.
RELEVEES_DU_CONTRAT = {
    "tables_pv": "#97caca",
    "pdl_ptr": "#7fffbf",
    "plateforme": "#d7d7d7",
    "piste_lourde_existante": "#a2a2a2",
    "piste_lourde_a_creer": "#a2a2a2",
    "piste_lourde": "#a2a2a2",
    "piste_legere": "#d7d7d7",
    "aire_grutage": "#a2a2a2",
    "bache_incendie": "#3fbfbf",
    "haie": "#6faa0b",
}


# ---------------------------------------------------------------------------
# D4 — les relevées font foi
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("categorie, couleur", sorted(RELEVEES_DU_CONTRAT.items()))
def test_les_teintes_relevees_sont_reprises_telles_quelles(categorie, couleur):
    fiche = style(categorie)
    assert fiche.relevee, f"« {categorie} » devrait être marquée relevée"
    assert fiche.style.remplissage == couleur


def test_la_cloture_et_le_portail_restent_rouges():
    """Deux relevées sans remplissage : c'est leur filet qui est relevé."""
    assert style("cloture").style.trait == "#ff0000"
    assert style("portail").style.trait == "#ff0000"


# ---------------------------------------------------------------------------
# D4 — les dérivées se justifient : elles doivent rester distinguables
# ---------------------------------------------------------------------------


def _paires_a_distinguer():
    """Paires de catégories dessinables dont au moins une teinte est dérivée.

    Deux relevées qui se confondent — `plateforme` et `piste_legere` partagent
    le gris 215 du dossier de référence — sont hors critère : la collision est
    héritée, et la corriger reviendrait à redessiner le document que
    l'instructeur connaît. Deux catégories partageant volontairement le même
    intitulé sont hors critère aussi : elles ne font qu'une entrée de légende.
    """
    for a, b in combinations(categories_dessinables(), 2):
        fa, fb = STYLES[a], STYLES[b]
        if fa.libelle == fb.libelle:
            continue
        if fa.relevee and fb.relevee:
            continue
        yield a, b


def test_les_categories_dessinables_restent_distinguables():
    """Critère de D4, mesuré : un ΔE, pas une impression.

    Un poste de 12 x 3 m au 1/1 000 fait 12 x 3 mm sur l'épreuve : deux teintes
    qui se ressemblent à l'écran zoomé n'y sont plus séparables.
    """
    trop_proches = []
    for a, b in _paires_a_distinguer():
        ecart = ecart_perceptuel(
            couleur_significative(STYLES[a]), couleur_significative(STYLES[b])
        )
        if ecart < ECART_MINIMAL:
            trop_proches.append(f"{a} / {b} : ΔE {ecart:.1f}")
    assert not trop_proches, "teintes trop proches à l'impression :\n" + "\n".join(
        trop_proches
    )


def test_les_trois_postes_se_distinguent_entre_eux():
    """Trois postes au tableau bilan, trois entrées de légende, trois teintes."""
    for a, b in combinations(("pdl_ptr", "ptr", "pdl"), 2):
        ecart = ecart_perceptuel(
            couleur_significative(STYLES[a]), couleur_significative(STYLES[b])
        )
        assert ecart >= ECART_MINIMAL, f"{a} / {b} : ΔE {ecart:.1f}"


def test_lab_repere_le_noir_et_le_blanc():
    """Garde-fou de la conversion elle-même, qui sert de juge à tout le reste."""
    assert vers_lab("#000000")[0] == pytest.approx(0.0, abs=0.01)
    assert vers_lab("#ffffff")[0] == pytest.approx(100.0, abs=0.05)
    assert ecart_perceptuel("#000000", "#000000") == 0.0


# ---------------------------------------------------------------------------
# D3 — la légende se construit depuis ce qui a été dessiné
# ---------------------------------------------------------------------------


def test_une_categorie_non_dessinee_ne_figure_pas():
    legende = construire_legende(("tables_pv", "cloture"))
    libelles = [e.libelle for e in legende]
    assert libelles == ["Panneaux photovoltaïques", "Clôture du projet solaire"]


def test_deux_categories_de_meme_intitule_ne_font_quune_entree():
    """`piste_lourde` et `aire_grutage` sont toutes deux « Voie lourde »."""
    legende = construire_legende(("piste_lourde", "aire_grutage"))
    assert [e.libelle for e in legende] == ["Voie lourde"]


def test_tables_et_modules_ne_font_quune_entree():
    """Le même ouvrage à deux niveaux de détail, comme chez HOCH."""
    legende = construire_legende(("tables_pv", "modules_pv"))
    assert [e.libelle for e in legende] == ["Panneaux photovoltaïques"]


def test_lordre_de_la_legende_est_celui_du_dessin():
    categories = ("cloture", "tables_pv", "plateforme", "bache_incendie")
    rangs = [STYLES[c].rang for c in categories]
    assert rangs != sorted(rangs), "le jeu d'essai doit être désordonné"

    legende = construire_legende(categories)
    attendus = [STYLES[c].libelle for c in sorted(categories, key=lambda c: STYLES[c].rang)]
    assert [e.libelle for e in legende] == attendus


@pytest.mark.parametrize("categorie", sorted(EXCLUES))
def test_les_categories_exclues_ne_figurent_jamais(categorie):
    """Chantier et contours d'étude : ni dessinés, ni en légende (D3)."""
    assert categorie not in categories_dessinables()
    assert construire_legende((categorie, "cloture")) == construire_legende(("cloture",))


def test_la_voirie_na_pas_dentree_propre():
    """Elle est rattachée à la voie lourde ou à la piste légère, jamais dessinée
    sous son propre nom (D5)."""
    assert "voirie" not in categories_dessinables()
    assert construire_legende(("voirie", "cloture")) == construire_legende(("cloture",))


def test_parcelles_et_batiments_viennent_du_wfs_et_figurent_en_legende():
    """Deux entrées qui ne sont pas au contrat, et que HOCH porte (D3)."""
    legende = construire_legende(
        ("tables_pv",), avec_parcelles=True, avec_batiments=True
    )
    libelles = [e.libelle for e in legende]
    assert libelles == [
        LIBELLE_PARCELLE,
        LIBELLE_BATIMENT,
        "Panneaux photovoltaïques",
    ]


def test_sans_batiment_pas_dentree_batiment():
    """Une emprise en secteur agricole peut n'en porter aucun."""
    legende = construire_legende(("tables_pv",), avec_parcelles=True)
    assert LIBELLE_BATIMENT not in [e.libelle for e in legende]


def test_toutes_les_categories_du_contrat_ont_un_style():
    """Une catégorie sans style disparaîtrait de la planche sans rien dire."""
    from dp_socle.import_be import CATEGORIES
    from dp_socle.planches.palette import SANS_STYLE

    manquantes = [c for c in CATEGORIES if c not in STYLES and c not in SANS_STYLE]
    assert not manquantes, (
        "catégories du contrat sans style de dossier : " + ", ".join(manquantes)
    )


# ---------------------------------------------------------------------------
# Symboles de légende
# ---------------------------------------------------------------------------


def test_chaque_categorie_a_un_symbole_connu():
    """Un symbole inconnu retomberait en silence sur l'aplat rectangulaire."""
    from dp_socle.planches.legende import SYMBOLES_CONNUS

    inconnus = [c for c, s in STYLES.items() if s.symbole not in SYMBOLES_CONNUS]
    assert not inconnus, "symboles de légende inconnus : " + ", ".join(inconnus)


def test_la_cloture_et_le_portail_ne_partagent_pas_leur_symbole():
    """Deux linéaires rouges que le rectangle du moteur rendait identiques."""
    assert style("cloture").symbole == "cloture"
    assert style("portail").symbole == "portail"
    assert style("cloture").symbole != style("portail").symbole


def test_lintitule_de_la_piste_existante_est_celui_du_bureau_detudes():
    """« à renforcer » n'est pas « à créer », et c'est ce qui compte au dossier.

    Relevé le 04/09/2026 dans la légende du plan PDF de Saint-Cyr.
    """
    assert style("piste_lourde_existante").libelle == (
        "Piste lourde existante (à renforcer si nécessaire)"
    )
    assert "à créer" in style("piste_lourde_a_creer").libelle


def test_la_legende_dessinee_a_la_hauteur_quelle_annonce():
    """Les planches DP 4 calent le plan sur cette hauteur avant de la dessiner."""
    from dp_socle.planche import Planche
    from dp_socle.planches.legende import dessiner_legende, hauteur_bloc

    planche = Planche(
        titre="T", numero="T", projet="T", date="04/09/2026", avec_cartouche=False
    )
    entrees = construire_legende(("cloture", "portail", "tables_pv"))
    _, _, _, hauteur = dessiner_legende(
        planche, entrees, position=(10.0, 10.0), largeur_mm=70.0
    )
    assert hauteur == pytest.approx(hauteur_bloc(len(entrees)))
