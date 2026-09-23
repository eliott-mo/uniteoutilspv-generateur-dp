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
    EMPRISE_BRAY,
    EMPRISE_SITE_BRAY,
    EXEMPLES,
    EXPORT_GANNAY,
    FOND_BRAY,
    LONGITUDE_BRAY,
    LONGITUDE_GANNAY,
    NORD_SUD_BRAY_M,
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
def export_gannay():
    return EXPORT_GANNAY


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


@pytest.mark.parametrize(
    "libelle, categorie, cote",
    [
        ("Réserve incendie 120 m³", "bache_incendie", {"volume_citerne_m3": 120}),
        ("Réserve Incendie (60m3)", "bache_incendie", {"volume_citerne_m3": 60}),
        ("Citerne incendie - 240 m3", "bache_incendie", {"volume_citerne_m3": 240}),
        ("Portail 7 m", "portail", {"largeur_portail_m": 7.0}),
        ("Portail (7,5 m)", "portail", {"largeur_portail_m": 7.5}),
        ("Portail de 6m", "portail", {"largeur_portail_m": 6.0}),
        ("Portail", "portail", {}),
        ("Réserve Incendie", "bache_incendie", {}),
    ],
)
def test_une_cote_portee_en_legende_se_lit_sans_changer_la_categorie(libelle, categorie, cote):
    """Instruction du chef de projet du 23/09/2026 : volume et largeur se portent en légende."""
    from dp_socle.plan_pdf import categorie_proposee, cote_lue

    assert categorie_proposee(libelle) == categorie
    assert cote_lue(libelle, categorie) == cote


@besoin_gannay
def test_le_volume_et_la_largeur_portes_en_legende_suffisent(lecture_gannay, import_gannay, tmp_path):
    """La légende de Gannay, complétée comme le chef de projet la complétera.

    Rien ne reste alors à trancher à l'écran : la réserve prend la variante de
    120 m³, le portail 7 m, et `projet.json` dit que les deux viennent de la
    légende.
    """
    import copy
    import json

    from dp_socle.plan_pdf import CATEGORIES_OUVRAGES, ImportPlanPDF

    lecture = copy.deepcopy(lecture_gannay)
    for entree in lecture.legende:
        if entree.categorie == "bache_incendie":
            entree.libelle += " 120 m³"
        elif entree.categorie == "portail":
            entree.libelle += " 7 m"
    complete = ImportPlanPDF(
        implantation=import_gannay.implantation,
        lecture=lecture,
        calage=import_gannay.calage,
        choix=ChoixDuPlan(),
        source_export=import_gannay.source_export,
    )
    assert complete.decisions_manquantes == []
    _, chemin_json = complete.ecrire(tmp_path)
    donnees = json.loads(chemin_json.read_text(encoding="utf-8"))
    reserves = [o for o in donnees["ouvrages_plan"] if o["categorie"] == "bache_incendie"]
    assert {o["gabarit"] for o in reserves} == {"Citerne incendie — 120"}
    assert {o["source_gabarit"] for o in reserves} == {"volume porté en légende"}
    assert donnees["portails_plan"] == [
        {"libelle": "Portail 7 m", "largeur_m": 7.0, "source": "largeur portée en légende"}
    ]
    assert donnees["parametres"]["generalites"]["largeur_portails_m"] == 7.0
    assert "bache_incendie" in CATEGORIES_OUVRAGES


@besoin_gannay
def test_un_volume_de_legende_hors_catalogue_n_est_pas_retenu(lecture_gannay, import_gannay):
    """100 m³ n'existe pas au catalogue : la légende ne l'impose pas, et le rapport le dit."""
    import copy

    from dp_socle.plan_pdf import ImportPlanPDF

    lecture = copy.deepcopy(lecture_gannay)
    for entree in lecture.legende:
        if entree.categorie == "bache_incendie":
            entree.libelle += " 100 m³"
    hors = ImportPlanPDF(
        implantation=import_gannay.implantation,
        lecture=lecture,
        calage=import_gannay.calage,
        choix=ChoixDuPlan(largeur_portail_m=7.0),
        source_export=import_gannay.source_export,
    )
    assert hors.decisions_manquantes == ["le volume de la réserve incendie"]
    assert any("100 m³ en légende" in a for a in hors.avertissements)


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
    proposees = {c.identifiant: c for c in import_gannay.corrections_proposees}
    assert set(proposees) == {"poste_sur_cloture:pdl_ptr:1", "pistes_contre_cloture"}
    assert proposees["poste_sur_cloture:pdl_ptr:1"].retrait_m == pytest.approx(6.3, abs=0.2)
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
def test_les_modules_de_gannay_se_dessinent_sans_trame_par_dessus(contrat_gannay):
    """264 tables de 18 modules, séparées de 0,5 m : la trame les doublait mal.

    Relevé par le chef de projet le 23/09/2026 : une table sur deux paraissait
    deux fois plus dense. Les modules du calepinage se dessinent tels quels, et
    le plan de masse n'a rien à en dire.
    """
    from dp_socle.planches.dp2_plan_masse import _tramer_les_tables
    from dp_socle.planches.modules import trame_du_projet

    assert len(contrat_gannay.geometries("modules_pv")) == 4752
    tables = contrat_gannay.geometries("tables_pv")
    assert trame_du_projet(contrat_gannay, tables, None) == (None, None)

    class PlancheQuiRefuse:
        def ajouter_geometrie(self, *_):
            raise AssertionError("aucune trame ne doit être tracée")

    assert _tramer_les_tables(PlancheQuiRefuse(), contrat_gannay, tables) == []


@besoin_gannay
def test_le_portail_est_dessine_comme_au_calque_du_be(contrat_gannay):
    """L'ouverture sur la clôture, deux vantaux ouverts vers l'intérieur, leurs arcs.

    Cinq entités jointives, de 7 m, 2 x 3,5 m et 2 x 5,50 m : c'est ce que
    porte le calque du BE de Saint-Cyr, et ce que la légende du dossier
    annonce. Un simple segment sur la clôture ne ressemblait pas à sa légende.
    """
    parties = contrat_gannay.geometries("portail")
    enceinte = contrat_gannay.geometries("cloture")[0]
    # À 2 ‰ près : 7 m au sol font 6,993 m en Lambert 93 à Gannay, dont
    # l'altération linéaire est de −0,9 ‰ — comme pour les tables du lot 2.
    longueurs = sorted(p.length for p in parties)
    assert longueurs == pytest.approx(
        [3.5, 3.5, 3.5 * math.pi / 2, 3.5 * math.pi / 2, 7.0], rel=0.002
    )
    ouverture = parties[[p.length for p in parties].index(longueurs[-1])]
    assert enceinte.exterior.distance(ouverture.centroid) < 0.01
    # Tout le débattement est du côté de l'enceinte.
    for partie in parties:
        assert enceinte.buffer(0.01).contains(partie)
    for arc in (p for p in parties if p.length == pytest.approx(5.5, rel=0.01)):
        assert arc.distance(ouverture.centroid) < 0.01
    assert contrat_gannay.generalites["largeur_portails_m"] == 7.0
    assert contrat_gannay.donnees["plan"]["nb_portails"] == 1


@besoin_gannay
def test_les_pistes_sortent_en_bandes_de_5_m_aux_virages_arrondis(contrat_gannay):
    """Le plan donne le tracé et le type ; la piste est celle d'un vrai plan.

    Instruction du chef de projet du 23/09/2026 : 5 m de large, 11 m au bord
    intérieur des virages, soit 13,5 m sur l'axe. À Gannay, la piste existante
    et la piste à créer ferment une boucle autour des tables.
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    categories = ("piste_lourde_existante", "piste_lourde_a_creer")
    surfaces = [g for c in categories for g in contrat_gannay.geometries(c)]
    assert surfaces and all(g.geom_type == "Polygon" for g in surfaces)
    pistes = contrat_gannay.donnees["pistes_plan"]
    assert pistes["largeur_m"] == 5.0
    assert pistes["rayon_interieur_m"] == 11.0
    for piste in pistes["pistes"]:
        largeur = piste["surface_m2"] / piste["longueur_axe_m"]
        if piste["rayons_raccords_m"]:
            assert largeur > 5.0
        else:
            assert largeur == pytest.approx(5.0, rel=0.002)
        if piste["rayon_axe_min_m"] is not None:
            assert piste["rayon_axe_min_m"] == 13.5
    boucle = unary_union(surfaces)
    centre_des_tables = unary_union(contrat_gannay.geometries("tables_pv")).centroid
    assert any(
        Polygon(interieur).contains(centre_des_tables)
        for morceau in getattr(boucle, "geoms", [boucle])
        for interieur in morceau.interiors
    )


@besoin_gannay
def test_les_pistes_se_serrent_contre_la_cloture_sur_demande(
    import_gannay, export_gannay, tmp_path
):
    """Demande du chef de projet du 23/09/2026 : dégager les tables sans toucher la clôture.

    La correction est proposée, pas appliquée. Appliquée, les deux pistes de
    la boucle passent à 0,5 m de la clôture, la boucle reste fermée, et il ne
    reste sous elles que les bouts des quatre rangées venues à moins de 5,5 m
    de la clôture — une piste de 5 m ne peut y passer sans les toucher. Le
    contrat inscrit la correction avec sa raison.
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    from dp_socle.contrat import charger_contrat

    correction = next(
        c for c in import_gannay.corrections_proposees if c.identifiant == "pistes_contre_cloture"
    )
    assert "correction du plan" in correction.raison
    assert "5,8 m²" in correction.raison

    serre = importer_plan_pdf(
        PLAN_GANNAY,
        export_gannay,
        longitude_origine=LONGITUDE_GANNAY,
        correction_nord_sud_m=NORD_SUD_GANNAY_M,
        choix=replace(CHOIX_GANNAY, corrections=("pistes_contre_cloture",)),
    )
    construction = serre.construction
    anneau = construction.enceinte.polygone.exterior
    tables = unary_union(list(serre.implantation.tables))
    # Les deux pistes de la boucle intérieure ; l'anneau, dehors, est fermé.
    boucle = [p for p in construction.pistes if p.axe.length > 150 and not p.axe.is_ring]
    assert len(boucle) == 2
    for piste in boucle:
        assert piste.surface.distance(anneau) == pytest.approx(0.5, abs=0.02)
    recouvert = unary_union([p.surface for p in boucle]).intersection(tables).area
    assert recouvert == pytest.approx(5.8, abs=0.5)
    fermee = unary_union([p.surface for p in boucle])
    centre_des_tables = tables.centroid
    assert any(Polygon(i).contains(centre_des_tables) for i in fermee.interiors)
    # Le contrôle ne dit plus que les pistes suivent le trait du plan.
    controle = next(c for c in serre.controles if c.libelle.startswith("Pistes de 5 m"))
    assert controle.message.startswith("Serrées contre la clôture")
    assert "clôture sur" not in controle.message

    serre.ecrire(tmp_path)
    corrections = charger_contrat(tmp_path).donnees["corrections_plan"]
    assert [c["identifiant"] for c in corrections] == ["pistes_contre_cloture"]
    assert corrections[0]["retrait_m"] == 0.5


@besoin_gannay
def test_une_piste_qui_recouvre_tables_et_cloture_est_signalee(import_gannay):
    """Le trait du plan passe au ras des tables et de la clôture ; la piste de 5 m non.

    Elle reste là où le plan la place — la déplacer serait corriger le plan —,
    et le contrôle dit ce qu'elle recouvre.
    """
    controle = next(
        c for c in import_gannay.controles if c.libelle == "Pistes de 5 m sur le tracé du plan"
    )
    assert controle.statut == "avertissement"
    assert "tables" in controle.message
    assert "clôture" in controle.message
    assert controle.valeur_dxf == pytest.approx(21.0, abs=3.0)


# ---------------------------------------------------------------------------
# Bray : un plan exporté autrement, une clôture qui s'arrête aux ouvrages
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def contrat_bray(import_bray, tmp_path_factory):
    from dp_socle.contrat import charger_contrat

    dossier = tmp_path_factory.mktemp("sortie_bray")
    import_bray.ecrire(dossier)
    return charger_contrat(dossier)


@besoin_bray
def test_la_hauteur_des_tables_se_prend_au_tableau_du_plan(contrat_bray):
    """Instruction du chef de projet du 23/09/2026 : au plan s'il la donne.

    Le tableau de Bray dit « 1.1 mètres min » et « 3 mètres max ». La coupe
    DP 3 dessine la table à partir de 1,10 m, et le maximum en gabarit ; elle
    ne retombe plus sur les 1,50 m du standard UNITe.
    """
    from dp_socle.planches.dp3_coupes import geometrie_table

    assert contrat_bray.structures["point_bas_m"] == 1.1
    assert contrat_bray.structures["point_haut_m"] == 3.0
    table, avertissements = geometrie_table(contrat_bray)
    assert table.point_bas_m == 1.1
    assert table.point_haut_max_m == 3.0
    assert table.point_haut_m == pytest.approx(2.95, abs=0.01)
    assert not any("standard UNITe" in a for a in avertissements)
    lu = contrat_bray.donnees["informations_plan"]["point_bas_m"]
    assert lu["texte"] == "Hauteur point bas | 1.1 mètres min"


@besoin_bray
def test_le_nombre_de_modules_du_tableau_ne_fait_pas_foi(import_bray, contrat_bray):
    """Les modules se prennent à l'export : le cartouche de Bray est périmé, et c'est dit."""
    assert contrat_bray.modules["nb_modules"] == 4590
    assert any(
        "annonce 5 296 modules" in a and "4 590" in a for a in import_bray.avertissements
    )


@besoin_gannay
def test_le_tableau_de_gannay_se_lit_et_concorde_avec_l_export(lecture_gannay, import_gannay):
    informations = lecture_gannay.informations
    assert informations["point_bas_m"]["valeur"] == 1.1
    assert informations["point_haut_m"]["valeur"] == 3.0
    assert informations["nb_modules"]["valeur"] == 4752
    assert informations["inclinaison_deg"]["valeur"] == 15.0
    assert not any("annonce" in a for a in import_gannay.avertissements)


@besoin_bray
def test_les_pistes_de_bray_perdent_leur_decrochement_et_gardent_deux_acces(import_bray):
    """Un décrochement de 0,8 m du trait s'efface ; deux accès au local restent deux."""
    notes = import_bray.avertissements
    assert any("décrochement de 0.8 m" in n for n in notes)
    assert any("3.6 m l'une de l'autre" in n and "sans raccord" in n for n in notes)
    controle = next(
        c for c in import_bray.controles if c.libelle == "Pistes de 5 m sur le tracé du plan"
    )
    assert controle.statut == "ok"
    # Rien à dégager : la correction des pistes n'a pas lieu d'être proposée.
    assert not any(
        c.identifiant == "pistes_contre_cloture" for c in import_bray.corrections_proposees
    )


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
def test_bray_tombe_sur_son_emprise_une_fois_la_latitude_corrigee(tmp_path):
    """Le lot 2 posait Bray 134 m trop au sud, et le réglage ne pouvait l'y ramener.

    Sa latitude était celle du centre de l'image de fond, 135 m au sud de
    l'origine du DXF (corrigé le 23/09/2026). Pré-positionnée sur l'emprise du
    site, la clôture tombe désormais à la bonne latitude — l'est-ouest reste à
    régler, comme au lot 2. Au calage mesuré sur l'ortho, elle épouse
    l'emprise cadastrale du site.
    """
    from dp_socle.geometrie import charger_emprise

    site = charger_emprise(EMPRISE_SITE_BRAY).geometrie
    export = layout_cad(tmp_path, DXF_BRAY, FOND_BRAY)
    commun = dict(
        emprise_cadastrale=site,
        correspondance={
            "Piste existante": "piste_lourde_existante",
            "Piste à créer": "piste_lourde_a_creer",
        },
        choix=ChoixDuPlan(volume_citerne_m3=60, largeur_portail_m=7.0),
    )
    prepositionne = importer_plan_pdf(PLAN_BRAY, export, **commun)
    cloture = prepositionne.plan.polygone_cloture
    assert abs(cloture.centroid.y - site.centroid.y) < 3.0

    cale = importer_plan_pdf(
        PLAN_BRAY,
        export,
        longitude_origine=LONGITUDE_BRAY,
        correction_nord_sud_m=NORD_SUD_BRAY_M,
        **commun,
    )
    cloture = cale.plan.polygone_cloture
    assert cloture.centroid.distance(site.centroid) < 2.0
    assert cloture.difference(site).area < 0.005 * cloture.area


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
