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

from dp_socle.erreurs import ErreurComposition
from dp_socle.planches.palette import (
    ECART_MINIMAL,
    CLE_PARCELLE,
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
    "bache_incendie": "#3fbfbf",
    "haie": "#6faa0b",
}

#: Écart délibéré à D4, décidé à la relecture du 05/09/2026 : les gris de sol.
#:
#: Le dossier de référence donne le **même** gris 215 à la plateforme et à la
#: piste légère, et le même gris 162 à toutes les voies lourdes. Sur nos
#: planches ces surfaces se touchent constamment — une plateforme de poste est
#: toujours au bord d'une piste — et la légende annonçait trois entrées que
#: l'œil ne pouvait pas séparer. Les trois gris s'étagent donc maintenant dans
#: l'ordre de la portance, en gardant la famille du document de référence.
GRIS_DE_SOL = {
    "plateforme": ("#e4e4e4", "#d7d7d7"),
    "piste_legere": ("#bdbdbd", "#d7d7d7"),
    "piste_lourde": ("#979797", "#a2a2a2"),
    "piste_lourde_existante": ("#979797", "#a2a2a2"),
    "piste_lourde_a_creer": ("#979797", "#a2a2a2"),
    "aire_grutage": ("#979797", "#a2a2a2"),
}


@pytest.mark.parametrize("categorie, teintes", sorted(GRIS_DE_SOL.items()))
def test_les_gris_de_sol_sont_etages(categorie, teintes):
    """Ils ne sont plus relevés : l'écart au document de référence est assumé.

    La piste à créer garde ce gris-là depuis qu'elle est hachurée : la hachure
    se pose par-dessus, elle ne remplace pas le revêtement.
    """
    retenue, relevee = teintes
    fiche = style(categorie)
    assert fiche.style.remplissage == retenue
    assert not fiche.relevee, "l'écart à D4 doit rester visible dans la fiche"
    assert retenue != relevee or categorie == "plateforme"


def test_les_trois_niveaux_de_sol_se_distinguent():
    """C'est le point : plateforme, piste légère et voie lourde sur un plan."""
    for a, b in combinations(("plateforme", "piste_legere", "piste_lourde"), 2):
        ecart = ecart_perceptuel(
            couleur_significative(STYLES[a]), couleur_significative(STYLES[b])
        )
        assert ecart >= ECART_MINIMAL, f"{a} / {b} : ΔE {ecart:.1f}"


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

    Deux relevées qui se confondent sont hors critère : la collision est
    héritée du dossier de référence, et la corriger reviendrait à redessiner le
    document que l'instructeur connaît. Deux catégories partageant volontairement
    le même intitulé sont hors critère aussi : elles ne font qu'une entrée de
    légende. Et deux catégories de même **matière** — une voie lourde existante,
    une à créer, une aire de grutage : la même grave compactée sous trois
    statuts — partagent leur teinte à dessein, leur filet et leur intitulé
    portant la distinction.
    """
    for a, b in combinations(categories_dessinables(), 2):
        fa, fb = STYLES[a], STYLES[b]
        if fa.libelle == fb.libelle:
            continue
        if fa.relevee and fb.relevee:
            continue
        if fa.matiere is not None and fa.matiere == fb.matiere:
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


def test_un_trait_pose_sur_sa_propre_surface_se_trace_au_filet():
    """La croix des sapeurs-pompiers disparaissait dans son aire d'aspiration.

    Relevé le 30/09/2026 sur Bédarieux par le chef de projet : « on ne voit pas
    la croix, elle est de la même couleur que le fond ». L'aire arrive du plan
    du bureau d'études en un rectangle de 8 x 4 m **et ses deux diagonales**,
    longues de 8,9 m chacune — la croix. Un tracé linéaire se dessinait au
    remplissage de sa catégorie, donc en bleu pâle sur ce même bleu pâle.

    Un trait qui n'est qu'un axe garde le remplissage : c'est lui qui donne sa
    couleur à une piste dont le plan ne livre que le fil.
    """
    from shapely.geometry import LineString, box

    from dp_socle.planches.palette import style_de

    fiche = STYLES["aire_aspiration"]
    croix = LineString([(0.0, 0.0), (8.0, 4.0)])

    assert style_de("aire_aspiration", box(0.0, 0.0, 8.0, 4.0)) is fiche.style
    assert style_de("aire_aspiration", croix, True).trait == fiche.style.trait
    assert style_de("aire_aspiration", croix).trait == fiche.style.remplissage
    assert fiche.style.trait != fiche.style.remplissage


def test_la_haie_a_renforcer_garde_le_vert_de_l_existante_et_s_interrompt():
    """Une haie qu'on complète n'est ni une plantation neuve ni un état des lieux.

    Demandé le 30/09/2026 après Gannay, dont le plan légende « haie à crée »
    en noir et « haie à renforcer » en bleu clair : les deux allaient à
    `haie`, et le dossier s'engageait sur une plantation là où il y a un
    complètement.

    C'est la même haie que l'existante, donc le même vert — le critère d'écart
    ne s'applique pas entre deux statuts d'une même chose, comme pour les
    voies lourdes. Ce qui les sépare est le tiret, et non une quatrième teinte
    verte que la palette n'a plus.

    Un tiret et non une hachure : une haie se trace en ligne, où une hachure
    ne se verrait pas. `style_de` reporte le tiret du remplissage au trait.
    """
    from shapely.geometry import LineString

    from dp_socle.planches.palette import style_de

    legende = construire_legende(("haie", "haie_a_renforcer", "haie_existante"))
    assert [e.libelle for e in legende] == [
        "Haie plantée",
        "Haie existante",
        "Haie à renforcer",
    ]

    a_renforcer, existante = STYLES["haie_a_renforcer"], STYLES["haie_existante"]
    assert a_renforcer.style.remplissage == existante.style.remplissage
    assert a_renforcer.matiere == existante.matiere is not None
    assert a_renforcer.style.tirets and not existante.style.tirets

    # Et le tiret survit au passage en trait, qui est la façon dont une haie
    # est dessinée sur le plan.
    trace = style_de("haie_a_renforcer", LineString([(0, 0), (10, 0)]))
    assert trace.remplissage == "none"
    assert trace.trait == existante.style.remplissage
    assert trace.tirets == a_renforcer.style.tirets


def test_le_chemin_existant_a_sa_propre_entree():
    """Le béton en place n'est ni une voie du projet ni de la grave compactée.

    Demandé le 29/09/2026 sur Saint-Cyr : le terrain porte un réseau de chemins
    bétonnés que le bureau d'études dessine en jaune et que son tableau bilan ne
    compte pas — 3 362 m² de voie lourde au plan pour 3 365 déclarés, chemins
    exclus des deux côtés. Les confondre avec la piste lourde existante ferait
    lire au dossier des voies du projet là où il n'y a que l'état du terrain.
    """
    legende = construire_legende(("piste_lourde_existante", "chemin_existant"))

    assert [e.libelle for e in legende] == [
        "Chemin existant",
        "Piste lourde existante (à renforcer si nécessaire)",
    ]


def test_le_chemin_existant_se_dessine_sous_les_voies_du_projet():
    """Le sol qui préexiste passe dessous : ce que le projet pose se voit."""
    assert STYLES["chemin_existant"].rang < STYLES["piste_lourde_existante"].rang
    assert STYLES["plateforme"].rang < STYLES["chemin_existant"].rang


def test_le_chemin_existant_ne_partage_le_gris_d_aucune_voie():
    """Il n'a pas de `matiere` : le béton n'est pas de la grave compactée.

    Conséquence mesurée : sa teinte doit tenir seule le critère d'écart, là où
    les trois statuts de voie lourde en sont dispensés entre eux. Aucun
    quatrième neutre ne le tenait — balayé le 29/09/2026, le meilleur gris
    clair plafonnait à 10,5 ΔE contre 12 exigés — d'où le jaune, celui sous
    lequel le bureau d'études dessine déjà ces chemins.
    """
    fiche = STYLES["chemin_existant"]
    assert fiche.matiere is None
    assert fiche.style.remplissage != STYLES["piste_lourde_existante"].style.remplissage

    ecart = ecart_perceptuel(
        couleur_significative(fiche),
        couleur_significative(STYLES["piste_lourde_existante"]),
    )
    assert ecart >= ECART_MINIMAL, f"ΔE {ecart:.1f}"


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


def test_le_contour_d_une_geometrie_recousue_reste_traçable():
    """Une `GeometryCollection` n'a pas de `boundary`, et le dessin en a besoin.

    C'est ce que `make_valid` produit d'un contour qui se replie sur lui-même :
    le polygone d'un côté, l'éperon détaché de l'autre. Relevé le 27/09/2026 sur
    le calque « UNI_BESS_Refroidissement » du plan d'Auzainvilliers — un contour
    de 603 sommets dont `make_valid` faisait un `GeometryCollection[Polygon,
    MultiLineString]`. La génération s'arrêtait en `AttributeError` au milieu
    des DP 4, sur un plan dont l'import avait pourtant nommé le calque fautif.
    """
    from shapely import make_valid
    from shapely.geometry import LineString, Polygon

    from dp_socle.planches.palette import contour_de

    # Un carré de 10 m prolongé d'un éperon de 5 m qui revient sur lui-même.
    recousue = make_valid(
        Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0), (-5, 0), (0, 0)])
    )
    assert recousue.geom_type == "GeometryCollection"
    assert recousue.boundary is None, "shapely a changé : le piège a disparu"

    contour = contour_de(recousue)
    assert contour is not None and not contour.is_empty
    # Les 40 m du carré, plus l'éperon parcouru dans les deux sens.
    assert contour.length == pytest.approx(45.0)

    # Un linéaire est son propre contour : `boundary` n'en rendrait que les
    # deux extrémités, soit deux points là où on attend un trait.
    ligne = LineString([(0, 0), (3, 4)])
    assert contour_de(ligne) is ligne


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


def test_un_intitule_retouche_par_le_chef_de_projet_est_celui_de_la_planche():
    """Nos intitulés sont ceux du dossier de référence ; un projet peut en vouloir
    d'autres, et la légende est dessinée dans la planche — pas retouchable après.
    """
    legende = construire_legende(
        ("tables_pv", "cloture"),
        avec_parcelles=True,
        libelles={"tables_pv": "Panneaux solaires", CLE_PARCELLE: "Parcelles"},
    )

    assert [e.libelle for e in legende] == [
        "Parcelles", "Panneaux solaires", "Clôture du projet solaire",
    ]


def test_renommer_une_seule_de_deux_categories_jumelles_les_separe():
    """Le remplacement se fait avant le dédoublonnage, et cela se voit.

    `piste_lourde` et `aire_grutage` partagent « Voie lourde » et ne font qu'une
    ligne. Renommer l'une en fait deux : la légende suit ce que le chef de projet
    a écrit, et non ce que la table prévoyait. C'est la raison pour laquelle
    l'interface propose **un champ par intitulé**, et non un par catégorie.
    """
    ensemble = construire_legende(("piste_lourde", "aire_grutage"))
    assert [e.libelle for e in ensemble] == ["Voie lourde"]

    separees = construire_legende(
        ("piste_lourde", "aire_grutage"), libelles={"aire_grutage": "Aire de grutage"}
    )

    assert [e.libelle for e in separees] == ["Voie lourde", "Aire de grutage"]


def test_deux_categories_renommees_pareil_se_rejoignent():
    """L'inverse est vrai, et c'est la même règle."""
    legende = construire_legende(
        ("tables_pv", "cloture"),
        libelles={"tables_pv": "Le projet", "cloture": "Le projet"},
    )

    assert [e.libelle for e in legende] == ["Le projet"]


def test_un_intitule_vide_est_refuse():
    """Une entrée de légende sans texte est un aplat que rien ne nomme."""
    with pytest.raises(ErreurComposition, match="Intitulé de légende vide"):
        construire_legende(("tables_pv",), libelles={"tables_pv": "   "})


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
    """Deux linéaires rouges que le rectangle du moteur rendait identiques.

    La clôture garde le trait simple du dossier de référence — au plan elle
    **est** un trait rouge continu — et le portail son symbole de plan, les
    deux vantaux et leur débattement.
    """
    assert style("cloture").symbole == "ligne"
    assert style("portail").symbole == "portail"
    assert style("cloture").symbole != style("portail").symbole


def test_la_haie_plantee_se_figure_comme_elle_se_dessine():
    """Une bande de 2 m au plan, une bande en légende — pas des houppiers."""
    assert style("haie").symbole == "bande"
    assert style("arbre_existant").symbole == "vegetation"


def test_lintitule_de_la_piste_existante_est_celui_du_bureau_detudes():
    """« à renforcer » n'est pas « à créer », et c'est ce qui compte au dossier.

    Relevé le 04/09/2026 dans la légende du plan PDF de Saint-Cyr.
    """
    assert style("piste_lourde_existante").libelle == (
        "Piste lourde existante (à renforcer si nécessaire)"
    )
    assert "à créer" in style("piste_lourde_a_creer").libelle


def test_la_piste_a_creer_se_hachure_sur_le_plan_et_en_legende():
    """Le même gris que l'existante, et la hachure qui les sépare.

    Mesuré le 29/09/2026 : les deux statuts ne différaient que par un filet de
    0,2 mm — ΔE 0,0 entre leurs remplissages — et leurs deux pastilles de
    légende étaient le même gris. Le lecteur avait deux entrées qu'il ne
    pouvait pas reporter sur le plan, ce qui est exactement ce qu'un dossier
    d'instruction doit rendre lisible.

    Mesuré dans le SVG de sortie, et des deux côtés : la forme du plan et la
    pastille de la légende. Une hachure qui ne serait que dans la légende
    mentirait autant que pas de hachure du tout.
    """
    from dp_socle.planche import REF_PISTE_A_CREER, Planche
    from dp_socle.planches.legende import dessiner_legende

    planche = Planche(
        titre="T", numero="T", projet="T", date="29/09/2026", avec_cartouche=False
    )
    planche.ajouter_rectangle(
        10.0, 40.0, 30.0, 20.0, STYLES["piste_lourde_a_creer"].style
    )
    dessiner_legende(
        planche,
        construire_legende(("piste_lourde_existante", "piste_lourde_a_creer")),
        position=(10.0, 10.0),
    )
    svg = planche.svg()

    assert svg.count(REF_PISTE_A_CREER) == 2, "le plan et la pastille"
    assert svg.count('<pattern id="hachures-piste-a-creer"') == 1, "posé une fois"
    # Et les deux gardent le même gris : la hachure se pose par-dessus le
    # revêtement, elle ne le remplace pas.
    assert STYLES["piste_lourde_existante"].style.remplissage == "#979797"
    assert STYLES["piste_lourde_a_creer"].style.remplissage == "#979797"


def test_un_remplissage_sans_motif_connu_est_refuse():
    """Une référence que `defs` ne porte pas ne lève pas d'elle-même.

    Cairo dessine alors la forme **sans remplissage** : la piste disparaîtrait
    du plan sans un mot, ce qui est le repli silencieux que le dépôt refuse.
    """
    from dp_socle.erreurs import ErreurRendu
    from dp_socle.planche import Planche, Style

    planche = Planche(
        titre="T", numero="T", projet="T", date="29/09/2026", avec_cartouche=False
    )

    with pytest.raises(ErreurRendu, match="sans motif connu"):
        planche.ajouter_rectangle(
            0.0, 0.0, 10.0, 10.0, Style(remplissage="url(#hachures-inventees)")
        )


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
