"""Import d'un plan projet PDF calé sur un export HelioScope (lot 2ter).

Ce qui est mesuré ici est le **résultat** : l'échelle et le recouvrement du
calage, la clôture et les ouvrages tels qu'ils sortent dans le GeoPackage écrit,
et les refus nommés. Les valeurs attendues ont été mesurées le 23/09/2026 sur
les deux plans d'essai, et recoupées avec celles du prototype du dépôt
`photomontage` là où il en donnait.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from dp_socle.erreurs import (
    ErreurEchelleIncoherente,
    ErreurGabaritIndecis,
    ErreurLegendeIntrouvable,
    ErreurRecouvrementInsuffisant,
)
from dp_socle.plan_pdf import (
    CHEMIN_GABARITS,
    ChoixDuPlan,
    ImageDeFond,
    caler_sur_tables,
    importer_plan_pdf,
    lire_plan_pdf,
)
from tests.jeux_plan_pdf import (
    DXF_BRAY,
    DXF_GANNAY,
    EMPRISE_BRAY,
    EXEMPLES,
    FOND_BRAY,
    FOND_GANNAY,
    LONGITUDE_GANNAY,
    NORD_SUD_GANNAY_M,
    PLAN_BRAY,
    PLAN_GANNAY,
    PLAN_GANNAY_SANS_CLOTURE,
    bray_present,
    gannay_present,
    layout_cad,
)

besoin_gannay = pytest.mark.skipif(not gannay_present(), reason="jeu de Gannay absent")
besoin_bray = pytest.mark.skipif(not bray_present(), reason="jeu de Bray absent")

#: Les deux choix que le plan de Gannay laisse ouverts, tranchés comme le
#: prototype les avait pris : une réserve de 120 m³, un portail de 7 m — la
#: largeur que portent les tableaux bilan de Saint-Cyr et de Sarnois.
CHOIX_GANNAY = ChoixDuPlan(volume_citerne_m3=120, largeur_portail_m=7.0)


@pytest.fixture(scope="module")
def lecture_gannay():
    return lire_plan_pdf(PLAN_GANNAY)


@pytest.fixture(scope="module")
def export_gannay(tmp_path_factory):
    return layout_cad(tmp_path_factory.mktemp("gannay"), DXF_GANNAY, FOND_GANNAY)


@pytest.fixture(scope="module")
def import_gannay(export_gannay):
    return importer_plan_pdf(
        PLAN_GANNAY,
        export_gannay,
        longitude_origine=LONGITUDE_GANNAY,
        correction_nord_sud_m=NORD_SUD_GANNAY_M,
        choix=CHOIX_GANNAY,
    )


@pytest.fixture(scope="module")
def contrat_gannay(import_gannay, tmp_path_factory):
    """Le contrat écrit, relu par le lecteur du lot 4."""
    from dp_socle.contrat import charger_contrat

    dossier = tmp_path_factory.mktemp("sortie_gannay")
    import_gannay.ecrire(dossier)
    return charger_contrat(dossier)


@pytest.fixture(scope="module")
def import_bray(tmp_path_factory):
    from dp_socle.geometrie import charger_emprise

    export = layout_cad(tmp_path_factory.mktemp("bray"), DXF_BRAY, FOND_BRAY)
    return importer_plan_pdf(
        PLAN_BRAY,
        export,
        emprise_cadastrale=charger_emprise(EMPRISE_BRAY).geometrie,
        correspondance={
            "Piste existante": "piste_lourde_existante",
            "Piste à créer": "piste_lourde_a_creer",
        },
        choix=ChoixDuPlan(volume_citerne_m3=120, largeur_portail_m=7.0),
    )


# ---------------------------------------------------------------------------
# Les critères du brief, mesurés sur le plan de Gannay
# ---------------------------------------------------------------------------


@besoin_gannay
def test_echelle_mesuree_sur_le_pas_des_rangees(import_gannay):
    """0,1531 m/px à 300 dpi, à 2 ‰ près : le critère n°1 du brief (D3).

    Mesuré le 23/09/2026 : 0,15307 m/px, pour un pas de 71,39 px contre les
    71,40 ± 0,17 du prototype. Le pas est la pente des centres de rangée sur
    leur rang ; la médiane des écarts, qu'employait le prototype, en gardait
    ±2,5 ‰ sur l'image native à 150 dpi.
    """
    calage = import_gannay.calage
    assert calage.m_par_px_reference == pytest.approx(0.1531, rel=0.002)
    assert calage.pas_plan_pt * 300 / 72 == pytest.approx(71.40, abs=0.17)
    assert calage.nb_rangees_plan == calage.nb_rangees_dxf == 16
    # L'emprise des tables confirme le pas dans les deux directions (D7).
    for echelle in (calage.echelle_le_long_m_par_pt, calage.echelle_en_travers_m_par_pt):
        assert echelle == pytest.approx(calage.echelle_m_par_pt, rel=0.005)


@besoin_gannay
def test_recouvrement_des_tables_une_fois_calees(import_gannay):
    """Jaccard au moins 0,85 : le critère n°2 du brief (D4). Mesuré : 0,954.

    Le plan et le DXF sont tous deux nord en haut, dans le repère du DXF : la
    rotation mesurée est nulle, et le demi-tour, essayé aussi, recouvre
    nettement moins.
    """
    calage = import_gannay.calage
    assert calage.recouvrement >= 0.85
    assert calage.rotation_deg == pytest.approx(0.0, abs=0.05)
    assert calage.recouvrement_retourne < calage.recouvrement - 0.1


@besoin_gannay
def test_la_cloture_sort_fermee_a_la_longueur_de_son_trace(contrat_gannay):
    """Clôture fermée de 684,4 m au sol, et non les 667 m du brief.

    Mesuré le 23/09/2026 dans le GeoPackage écrit : 683,8 m en Lambert 93, soit
    684,4 m au sol — le facteur d'échelle de la projection vaut 0,99906 au
    droit du site. Les 667 m du brief venaient du prototype, qui ordonnait les
    pixels de la clôture en secteurs de 6° autour du centre : ses sommets
    tombent bien sur le tracé, mais chacun des quatre angles est coupé de 2,6
    à 4,9 m. Les 180 points du pointillé, relus comme des points, donnent quatre
    côtés droits à 0,06 pt près, et leurs angles.
    """
    clotures = contrat_gannay.geometries("cloture")
    assert len(clotures) == 1
    enceinte = clotures[0]
    assert enceinte.geom_type == "Polygon"
    assert len(enceinte.exterior.coords) == 5
    assert enceinte.exterior.length == pytest.approx(683.8, rel=0.01)
    assert enceinte.exterior.length > 667.0 * 1.01
    # Le plan annonce « Emprise clôturée ~3 ha ».
    assert enceinte.area == pytest.approx(29_145, rel=0.01)


# ---------------------------------------------------------------------------
# La légende : les couleurs se relèvent, elles ne se supposent pas (D1)
# ---------------------------------------------------------------------------


@besoin_gannay
def test_chaque_couleur_se_releve_sur_sa_pastille(lecture_gannay):
    legende = {e.libelle: e for e in lecture_gannay.legende}
    assert len(legende) == 12
    assert legende["Clôture"].couleur == (193, 15, 193)
    assert legende["Clôture"].pastille.motif == "pointille"
    # Le portail porte le même magenta : c'est le motif qui les sépare.
    assert legende["Portail"].couleur == (193, 15, 193)
    assert legende["Portail"].pastille.motif == "plein"
    assert legende["Poste combiné de Livraison/transformation"].categorie == "pdl_ptr"
    assert legende["Haie à crée"].categorie == "haie"
    assert all(e.categorie for e in legende.values())


@besoin_gannay
def test_une_forme_de_la_carte_se_range_sous_une_couleur_approchee(lecture_gannay):
    """La carte ne reprend pas toujours la couleur exacte de sa pastille.

    Les pistes à créer de Gannay sont (237, 125, 49) sur la carte et
    (244, 99, 34) sur la pastille : 30,8 d'écart. Elles vont bien à leur
    entrée, et nulle part ailleurs.
    """
    pistes = lecture_gannay.elements_de("piste_lourde_a_creer")
    assert len(pistes) == 3
    assert {e.objet.couleur for e in pistes} == {(237, 125, 49)}
    assert not lecture_gannay.non_reconnus


@besoin_gannay
def test_un_ouvrage_dessine_une_fois_est_lu_une_fois(lecture_gannay):
    """Le prototype relevait au pixel : huit locaux techniques, quatre BESS.

    Le plan en dessine un de chaque, et deux réserves incendie. Lu dans les
    tracés du PDF, chacun est une forme, et une seule.
    """
    compte = {c: len(lecture_gannay.elements_de(c)) for c in (
        "local_technique", "bess", "pdl_ptr", "ptr", "bac_retention",
        "bache_incendie", "portail",
    )}
    assert compte == {
        "local_technique": 1, "bess": 1, "pdl_ptr": 1, "ptr": 1,
        "bac_retention": 1, "bache_incendie": 2, "portail": 1,
    }


@besoin_bray
def test_les_couleurs_d_un_autre_plan_sont_d_autres_couleurs():
    """Même modèle PowerPoint, autres couleurs : la clôture est rouge à Bray.

    Et deux citernes y portent le même cyan : seul le liseré noir de la citerne
    de refroidissement la distingue de la citerne incendie.
    """
    lecture = lire_plan_pdf(PLAN_BRAY)
    legende = {e.libelle: e for e in lecture.legende}
    assert legende["Clôture"].couleur == (231, 18, 36)
    assert legende["Citerne Incendie"].couleur == legende["Citerne de refroidissement"].couleur
    assert legende["Citerne de refroidissement"].pastille.lisere == (0, 0, 0)
    assert len(lecture.elements_de("bache_incendie")) == 1
    assert len(lecture.elements_de("citerne_refroidissement")) == 1
    # « Piste existante » ne dit pas si elle est lourde ou légère : elle ne se
    # range nulle part d'office, et le rapport le dit.
    assert legende["Piste existante"].categorie is None
    assert any("Piste existante" in a for a in lecture.avertissements)


@besoin_gannay
def test_sans_cloture_en_legende_le_plan_est_refuse():
    """La version du 28/08/2026 du plan de Gannay n'a pas encore de clôture."""
    with pytest.raises(ErreurLegendeIntrouvable, match="clôture"):
        lire_plan_pdf(PLAN_GANNAY_SANS_CLOTURE)


def test_un_fichier_qui_n_est_pas_un_pdf_est_refuse(tmp_path):
    from dp_socle.erreurs import ErreurPlanPDF

    faux = tmp_path / "plan.pdf"
    faux.write_bytes(b"ceci n'est pas un PDF")
    with pytest.raises(ErreurPlanPDF, match="pas un PDF lisible"):
        lire_plan_pdf(faux)


# ---------------------------------------------------------------------------
# Les refus du calage (D7)
# ---------------------------------------------------------------------------


@besoin_gannay
def test_un_plan_etire_d_un_seul_cote_est_refuse(lecture_gannay, import_gannay):
    """Une copie d'écran étirée de 5 % en largeur garde son pas en travers.

    Le pas seul ne le verrait pas : c'est l'emprise des tables le long des
    rangées qui le trahit.
    """
    a, b, c, d, e, f = lecture_gannay.fond.matrice
    etiree = replace(
        lecture_gannay,
        fond=ImageDeFond(lecture_gannay.fond.pixels, (a * 1.05, b, c, d, e, f)),
    )
    with pytest.raises(ErreurEchelleIncoherente, match="le long des rangées"):
        caler_sur_tables(etiree, import_gannay.implantation)


@besoin_gannay
def test_un_calepinage_qui_n_est_pas_celui_du_plan_est_refuse(
    lecture_gannay, import_gannay
):
    """Une table sur deux retirée : même pas, même emprise, autre damier."""
    implantation = import_gannay.implantation
    from dp_socle.helioscope import _dans_le_repere_du_calepinage

    bornes = _dans_le_repere_du_calepinage(implantation)
    rangs = {}
    for indice, b in enumerate(bornes):
        rangs.setdefault(round((b[1] + b[3]) / 2, 1), []).append(indice)
    gardees = set()
    for indices in rangs.values():
        indices.sort(key=lambda i: bornes[i][0])
        gardees.update(indices[::2])
        gardees.add(indices[-1])
    amputee = replace(
        implantation, tables=[t for i, t in enumerate(implantation.tables) if i in gardees]
    )
    with pytest.raises(ErreurRecouvrementInsuffisant, match="Jaccard"):
        caler_sur_tables(lecture_gannay, amputee)


# ---------------------------------------------------------------------------
# Les ouvrages : position et orientation du plan, cotes des gabarits (D2)
# ---------------------------------------------------------------------------


def _cotes_au_sol(geometrie) -> tuple[float, float]:
    rectangle = geometrie.minimum_rotated_rectangle
    sommets = list(rectangle.exterior.coords)[:4]
    cotes = sorted(math.dist(sommets[i], sommets[(i + 1) % 4]) for i in range(4))
    return cotes[-1], cotes[0]


@besoin_gannay
def test_un_ouvrage_prend_les_cotes_de_son_gabarit_et_non_celles_du_dessin(
    contrat_gannay, import_gannay
):
    """Le poste combiné est dessiné 7,25 × 3,65 m ; son gabarit fait 12 × 3.

    Mesuré dans le GeoPackage, en Lambert 93 : le facteur d'échelle de la
    projection y retire un millième.
    """
    postes = contrat_gannay.geometries("pdl_ptr")
    assert len(postes) == 1
    longueur, largeur = _cotes_au_sol(postes[0])
    assert longueur == pytest.approx(12.0, rel=0.002)
    assert largeur == pytest.approx(3.0, rel=0.002)
    ouvrage = next(o for o in import_gannay.construction.ouvrages if o.categorie == "pdl_ptr")
    assert ouvrage.dessine_m[0] == pytest.approx(7.25, abs=0.05)
    # Et le lot 4 retrouve sa cote au catalogue, variante de citerne comprise.
    assert contrat_gannay.cote_de_categorie("pdl_ptr").longueur_m == 12.0
    citerne = contrat_gannay.geometries("bache_incendie")[0]
    assert contrat_gannay.cote_de_categorie(
        "bache_incendie", citerne.area
    ).ouvrage == "Citerne incendie — 120"


@besoin_gannay
def test_le_poste_garde_l_orientation_du_plan(contrat_gannay, import_gannay):
    """Dessiné parallèle à la clôture sud-est, il le reste au contrat."""
    poste = contrat_gannay.geometries("pdl_ptr")[0]
    rectangle = list(poste.minimum_rotated_rectangle.exterior.coords)[:4]
    cote = max(
        ((rectangle[i], rectangle[(i + 1) % 4]) for i in range(4)),
        key=lambda s: math.dist(*s),
    )
    direction = math.degrees(math.atan2(cote[1][1] - cote[0][1], cote[1][0] - cote[0][0]))
    attendu = import_gannay.construction.ouvrages[0].direction_deg
    ecart = abs(((direction - attendu - 0.436) + 90) % 180 - 90)
    assert ecart < 0.5


@besoin_gannay
def test_une_dimension_non_tranchee_refuse_l_ecriture(export_gannay, tmp_path):
    """Volume de citerne et largeur de portail : le plan ne les donne pas."""
    sans_choix = importer_plan_pdf(
        PLAN_GANNAY,
        export_gannay,
        longitude_origine=LONGITUDE_GANNAY,
        correction_nord_sud_m=NORD_SUD_GANNAY_M,
    )
    assert sans_choix.decisions_manquantes == [
        "la largeur du portail",
        "le volume de la réserve incendie",
    ]
    with pytest.raises(ErreurGabaritIndecis, match="réserve incendie"):
        sans_choix.ecrire(tmp_path)
    assert not (tmp_path / "geometries.gpkg").exists()


def test_le_classeur_des_gabarits_dit_ce_que_dit_celui_de_reference():
    """La ressource de l'outil est une copie : ses cotes ne doivent pas diverger.

    La comparaison porte sur ce que les classeurs disent, cote par cote, et non
    sur leurs octets. Mesuré le 23/09/2026 : dans une bibliothèque SharePoint
    synchronisée, le service d'identifiant de document réécrit les propriétés
    de tout nouveau fichier Office (`_dlc_DocId`) dans l'instant qui suit sa
    copie — les cellules restent intactes, l'empreinte change à chaque fois.
    """
    from dp_socle.tableau_bilan import lire_gabarits

    reference = EXEMPLES / "Standards UNITe .xlsx"
    if not reference.exists():
        pytest.skip("classeur de référence absent")
    assert lire_gabarits(CHEMIN_GABARITS) == lire_gabarits(reference)
    cotes, _ = lire_gabarits(CHEMIN_GABARITS)
    assert len(cotes) == 17


# ---------------------------------------------------------------------------
# La correction de plan se déclare, elle ne se fait pas toute seule (D8)
# ---------------------------------------------------------------------------


@besoin_gannay
def test_la_correction_du_poste_est_proposee_et_pas_appliquee(import_gannay, contrat_gannay):
    """Le poste de livraison de Gannay est dessiné en retrait de la clôture.

    Son centre est à 7,8 m du tracé — les 7,7 m du brief —, son long pan à
    6,3 m une fois le poste à ses cotes. L'import le propose, et ne le fait pas.
    """
    proposees = import_gannay.corrections_proposees
    assert [c.identifiant for c in proposees] == ["poste_sur_cloture:pdl_ptr:1"]
    assert proposees[0].retrait_m == pytest.approx(6.3, abs=0.2)
    assert contrat_gannay.donnees["corrections_plan"] == []
    poste = contrat_gannay.geometries("pdl_ptr")[0]
    enceinte = contrat_gannay.geometries("cloture")[0]
    assert enceinte.exterior.distance(poste) > 5.0


@besoin_gannay
def test_la_correction_appliquee_figure_au_contrat_avec_sa_raison(
    export_gannay, tmp_path
):
    from dp_socle.contrat import charger_contrat

    corrige = importer_plan_pdf(
        PLAN_GANNAY,
        export_gannay,
        longitude_origine=LONGITUDE_GANNAY,
        correction_nord_sud_m=NORD_SUD_GANNAY_M,
        choix=replace(CHOIX_GANNAY, corrections=("poste_sur_cloture:pdl_ptr:1",)),
    )
    corrige.ecrire(tmp_path)
    contrat = charger_contrat(tmp_path)
    poste = contrat.geometries("pdl_ptr")[0]
    enceinte = contrat.geometries("cloture")[0]
    # Son long pan affleure le tracé, du côté intérieur.
    assert enceinte.exterior.distance(poste) < 0.05
    assert enceinte.buffer(0.05).contains(poste)
    corrections = contrat.donnees["corrections_plan"]
    assert len(corrections) == 1
    assert "correction du plan" in corrections[0]["raison"]
    interruptions = contrat.donnees["enceinte_plan"]["interruptions"]
    assert interruptions[-1]["origine"] == "correction D8"
    assert interruptions[-1]["longueur_m"] == pytest.approx(12.0)


@besoin_gannay
def test_une_correction_inconnue_est_refusee(import_gannay):
    from dp_socle.erreurs import ErreurPlanPDF

    import_gannay.changer_de_choix(replace(CHOIX_GANNAY, corrections=("inventee:1",)))
    try:
        with pytest.raises(ErreurPlanPDF, match="sans objet"):
            import_gannay.construction
    finally:
        import_gannay.changer_de_choix(CHOIX_GANNAY)


# ---------------------------------------------------------------------------
# Le contrat, écrit comme les deux autres producteurs l'écrivent
# ---------------------------------------------------------------------------


@besoin_gannay
def test_le_contrat_porte_les_tables_du_lot_2_et_le_reste_du_plan(contrat_gannay):
    from dp_socle.import_be import ORIGINE_PLAN_PDF, VERSION_CONTRAT

    assert contrat_gannay.origine == ORIGINE_PLAN_PDF
    assert contrat_gannay.version == VERSION_CONTRAT
    assert len(contrat_gannay.geometries("tables_pv")) == 16
    assert len(contrat_gannay.geometries("modules_pv")) == 4752
    for categorie in ("haie", "piste_lourde_existante", "piste_lourde_a_creer",
                      "portail", "ptr", "local_technique", "bess", "bac_retention"):
        assert contrat_gannay.presente(categorie), categorie
    # Les tracés gardent le libellé qui les a nommés : la haie à créer et la
    # haie à renforcer vont toutes deux à `haie`.
    calques = {e.calque for e in contrat_gannay.entites("haie")}
    assert calques == {"Haie à crée", "Haie à renforcer"}
    assert not contrat_gannay.z_reel("tables_pv")
    donnees = contrat_gannay.donnees
    assert donnees["sources"]["plan_pdf"] == PLAN_GANNAY.name
    assert donnees["calage_plan"]["recouvrement_jaccard"] >= 0.85
    assert donnees["plan"]["azimut_tables_deg"] == pytest.approx(0.436, abs=0.01)


@besoin_gannay
def test_le_portail_est_pose_sur_la_cloture_a_sa_largeur(contrat_gannay):
    portail = contrat_gannay.geometries("portail")[0]
    enceinte = contrat_gannay.geometries("cloture")[0]
    assert portail.length == pytest.approx(7.0, rel=0.002)
    assert enceinte.exterior.distance(portail.centroid) < 0.01
    assert contrat_gannay.generalites["largeur_portails_m"] == 7.0


# ---------------------------------------------------------------------------
# Bray : un plan exporté autrement, une clôture qui s'arrête aux ouvrages
# ---------------------------------------------------------------------------


@besoin_bray
def test_bray_se_cale_sur_son_propre_calepinage(import_bray):
    calage = import_bray.calage
    assert calage.nb_rangees_plan == calage.nb_rangees_dxf == 17
    assert calage.recouvrement >= 0.95
    # Tables et clôture dans l'emprise réelle du projet.
    statuts = {c.libelle: c.statut for c in import_bray.controles}
    assert statuts["Clôture dans l'emprise cadastrale"] == "ok"
    assert statuts["Tables contenues dans la clôture"] == "ok"


@besoin_bray
def test_la_cloture_se_referme_au_droit_des_ouvrages_qui_l_interrompent(import_bray):
    """À Bray la clôture s'arrête au poste de livraison, au portail, au local.

    Le chef de projet l'a dessinée comme elle sera bâtie : deux tracés ouverts.
    L'enceinte se referme au droit de ces ouvrages, et seulement là.
    """
    enceinte = import_bray.construction.enceinte
    assert enceinte.anneau is not None
    ponts = sorted(enceinte.interruptions, key=lambda p: p["longueur_m"])
    assert [p["longueur_m"] for p in ponts] == pytest.approx([9.6, 16.6], abs=0.1)
    assert ponts[0]["ouvrages"] == ["Local technique"]
    assert ponts[1]["ouvrages"] == ["Portail", "Poste de Livraison/transfo"]
    assert import_bray.plan.surface_cloturee_m2 == pytest.approx(48_655, rel=0.01)
    assert any("interrompue" in a for a in import_bray.avertissements)
