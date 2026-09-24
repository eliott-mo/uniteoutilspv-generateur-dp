"""Le chemin du plan projet PDF dans l'application (lot 2ter), joué par `AppTest`.

Même parcours que celui du plan du bureau d'études, par l'autre porte : cadrer
le projet, choisir la source, déposer l'export HelioScope et le plan, importer,
trancher ce que le plan ne dit pas, valider. Ce qui compte est ce qui arrive au
bout : le contrat écrit, d'origine `plan_pdf`, que les sections suivantes
liront sans savoir d'où il vient.

Un carré de 500 m centré sur le site tient lieu d'emprise cadastrale — il pose
le site à sa place dès le pré-positionnement, et le relevé altimétrique de
synthèse qui évite le RGE ALTI le couvre exactement. L'emprise réelle de Gannay,
déposée le 23/09/2026, sert au calage sur l'ortho (`tests/test_calage_ortho.py`),
dont la mesure est ici remplacée. Ces tests ne demandent aucun service en ligne.
"""

from __future__ import annotations

import json

import pytest

from tests.jeux_plan_pdf import (
    EXPORT_GANNAY,
    PLAN_GANNAY,
    gannay_present,
)
from tests.test_app_streamlit import _application, _cliquer, _televerser, _titres

pytestmark = pytest.mark.skipif(not gannay_present(), reason="jeu de Gannay absent")

#: Centre du site de Gannay en Lambert 93 : celui des tables, une fois l'export
#: calé sur l'ortho IGN (voir `tests/jeux_plan_pdf.py`).
CENTRE_GANNAY = (745_843.7, 6_625_810.2)
DEMI_COTE_M = 250.0

SOURCE_PLAN_PDF = "Plan projet PDF sur un export HelioScope — sans plan du BE"


def _emprise_gannay(dossier) -> list:
    """Un carré de 500 m autour du site, en shapefile, `.prj` compris."""
    import geopandas as gpd
    from shapely.geometry import box

    x, y = CENTRE_GANNAY
    carre = box(x - DEMI_COTE_M, y - DEMI_COTE_M, x + DEMI_COTE_M, y + DEMI_COTE_M)
    chemin = dossier / "emprise_gannay.shp"
    gpd.GeoDataFrame({"nom": ["essai"]}, geometry=[carre], crs="EPSG:2154").to_file(chemin)
    return [
        (f.name, f.read_bytes(), "application/octet-stream")
        for f in sorted(dossier.iterdir())
        if f.stem == "emprise_gannay" and f.suffix.lower() in (".shp", ".shx", ".dbf", ".prj")
    ]


def _releve_gannay() -> bytes:
    """Un relevé « X Y Z » de synthèse sur le site, au pas de 2 m en x."""
    x0, y0 = CENTRE_GANNAY
    lignes = ["# X Y Z — relevé de synthèse, Lambert 93"]
    x = x0 - DEMI_COTE_M
    while x <= x0 + DEMI_COTE_M:
        y = y0 - DEMI_COTE_M
        while y <= y0 + DEMI_COTE_M:
            lignes.append(f"{x:.2f} {y:.2f} {200.0 + 0.01 * (y - y0):.2f}")
            y += 5.0
        x += 2.0
    return "\n".join(lignes).encode("utf-8")


def _plan_pdf_importe(tmp_path, monkeypatch):
    """Le projet cadré, la source choisie, les deux fichiers déposés, l'import fait."""
    donnees = tmp_path / "donnees"
    donnees.mkdir()
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("Gannay-sur-Loire")
    _televerser(application, "Emprise cadastrale", _emprise_gannay(donnees))
    application = application.run()
    application.radio(key="source_plan").set_value(SOURCE_PLAN_PDF)
    application = application.run()
    _televerser(
        application,
        "Export HelioScope",
        (EXPORT_GANNAY.name, EXPORT_GANNAY.read_bytes(), "application/zip"),
    )
    _televerser(
        application, "Plan projet (PDF)", (PLAN_GANNAY.name, PLAN_GANNAY.read_bytes(), "application/pdf")
    )
    _televerser(application, "Relevé altimétrique", ("releve.txt", _releve_gannay(), "text/plain"))
    application = application.run()
    _cliquer(application, "Importer et caler le plan")
    return application.run()


def test_la_source_du_plan_se_choisit_et_change_la_section(tmp_path, monkeypatch):
    """Le plan du BE reste la porte par défaut ; l'autre s'ouvre sur demande."""
    donnees = tmp_path / "donnees"
    donnees.mkdir()
    application = _application(tmp_path, monkeypatch).run()
    application.text_input[0].set_value("Gannay-sur-Loire")
    _televerser(application, "Emprise cadastrale", _emprise_gannay(donnees))
    application = application.run()
    assert "2. Plan du bureau d'études" in _titres(application)
    libelles = [t.label for t in application.get("file_uploader")]
    assert any(l.startswith("Plan BE (DXF") for l in libelles)
    assert not any(l.startswith("Plan projet (PDF)") for l in libelles)

    application.radio(key="source_plan").set_value(SOURCE_PLAN_PDF)
    application = application.run()
    assert not application.exception
    assert "2. Plan projet PDF sur un export HelioScope" in _titres(application)
    libelles = [t.label for t in application.get("file_uploader")]
    assert any(l.startswith("Export HelioScope") for l in libelles)
    assert any(l.startswith("Plan projet (PDF)") for l in libelles)
    assert not any(l.startswith("Plan BE (DXF") for l in libelles)


def test_le_plan_pdf_s_importe_et_se_cale(tmp_path, monkeypatch):
    application = _plan_pdf_importe(tmp_path, monkeypatch)
    assert not application.exception, application.exception
    mesures = {m.label: m.value for m in application.metric}
    assert mesures["Échelle du plan"] == "0,1531 m/px"
    assert mesures["Rangées de tables"] == "16"
    # Ce que le plan ne dit pas se tranche avant de valider, et rien ne le
    # suppose : la liste du volume est vide, le champ de la largeur aussi.
    assert application.selectbox(key="volume_citerne_plan_pdf").value is None
    assert application.number_input(key="largeur_portail_plan_pdf").value is None
    assert any("Tranchez d'abord" in w.value for w in application.warning)
    assert not any("Valider l'import" in b.label for b in application.button)
    # La correction du poste est offerte, pas cochée.
    assert application.checkbox(
        key="correction_plan_poste_sur_cloture:pdl_ptr:1"
    ).value is False
    # La légende ne propose que ce qu'un plan PDF sait importer : une plateforme
    # choisie ici ne sortait pas du plan, et rien ne le disait (24/09/2026).
    options = next(
        s.options for s in application.selectbox if (s.key or "").startswith("categorie_legende_")
    )
    assert "arbre_existant" in options
    assert "plateforme" not in options

    # La carte se lit sous les réglages qui la changent — le calage, puis les
    # choix du plan —, et non sous les alertes, qui la repoussaient à plusieurs
    # écrans (retour d'usage du 23/09/2026).
    ordre = _dans_l_ordre_de_la_page(application)

    def rang(predicat, quoi):
        for i, element in enumerate(ordre):
            if predicat(element):
                return i
        raise AssertionError(f"{quoi} n'est pas sur la page")

    def texte(element) -> str:
        """Le texte d'un élément, ou rien : la valeur d'un tableau n'en est pas un."""
        for attribut in ("value", "label"):
            valeur = getattr(element, attribut, None)
            if isinstance(valeur, str) and valeur:
                return valeur
        return ""

    recaler = rang(lambda e: texte(e) == "Recaler", "le bouton « Recaler »")
    choix = rang(
        lambda e: "Ce que le plan ne dit pas de ses ouvrages" in texte(e),
        "le titre des choix du plan",
    )
    carte = rang(
        lambda e: "Le plan importé, et la ligne de coupe" in texte(e), "le titre de la carte"
    )
    alerte = rang(
        lambda e: e.type == "warning" and texte(e).startswith("Pistes de 5 m"),
        "l'alerte des pistes",
    )
    validation = rang(lambda e: texte(e) == "### Validation", "le titre de la validation")
    assert recaler < choix < carte < alerte < validation


def _dans_l_ordre_de_la_page(application) -> list:
    """Les éléments de la page principale, dans l'ordre où ils s'affichent."""
    elements = []

    def parcourir(noeud):
        enfants = getattr(noeud, "children", None)
        if enfants is None:
            elements.append(noeud)
            return
        for indice in sorted(enfants):
            parcourir(enfants[indice])

    parcourir(application.main)
    return elements


def _annonces_de_l_ortho(application) -> list:
    """Ce que le calage sur l'ortho dit avoir fait — l'annonce de la coupe est à part."""
    return [s.value for s in application.success if s.value.startswith("Calé sur l'ortho")]


def _correction_nord_sud(application):
    """Le champ de la correction nord-sud du formulaire de placement."""
    for champ in application.number_input:
        if champ.label.startswith("Correction nord-sud"):
            return champ
    raise AssertionError("le champ de la correction nord-sud n'est pas affiché")


def test_caler_sur_l_ortho_refuse_sans_rien_changer_puis_cale_et_le_dit(tmp_path, monkeypatch):
    """Le bouton applique la mesure aux deux réglages, et dit ce qu'il a fait.

    La mesure, qui télécharge l'ortho, est éprouvée dans
    `tests/test_calage_ortho.py` ; elle est ici remplacée : un refus d'abord,
    puis ce qu'elle mesure sur Gannay pré-positionnée sur son emprise — 18,6 m
    vers l'ouest, 0,8 m vers le sud.
    """
    from dp_socle import calage_ortho
    from dp_socle.erreurs import ErreurCalage
    from dp_socle.helioscope import metres_par_degre_longitude

    application = _plan_pdf_importe(tmp_path, monkeypatch)
    assert not application.exception, application.exception
    calage = application.session_state["import_be"].implantation.calage
    longitude, nord_sud = calage.longitude_origine, calage.correction_nord_sud_m

    def refus(implantation, telecharger=None):
        raise ErreurCalage("Le fond HelioScope ne se reconnaît pas nettement dans l'ortho IGN.")

    monkeypatch.setattr(calage_ortho, "mesurer_sur_ortho", refus)
    _cliquer(application, "Caler sur l'ortho")
    application = application.run()
    assert not application.exception, application.exception
    assert any("ne se reconnaît pas nettement" in e.value for e in application.error)
    assert (calage.longitude_origine, calage.correction_nord_sud_m) == (longitude, nord_sud)
    assert not _annonces_de_l_ortho(application)

    def mesure(implantation, telecharger=None):
        return calage_ortho.MesureOrtho(
            decalage_est_m=-18.6, decalage_nord_m=-0.8, pic=0.51, second_pic=0.19, pas_m=0.4
        )

    monkeypatch.setattr(calage_ortho, "mesurer_sur_ortho", mesure)
    _cliquer(application, "Caler sur l'ortho")
    application = application.run()
    assert not application.exception, application.exception
    deplacement_est = (calage.longitude_origine - longitude) * metres_par_degre_longitude(
        calage.latitude_origine
    )
    assert deplacement_est == pytest.approx(-18.6, abs=0.01)
    assert calage.correction_nord_sud_m == pytest.approx(nord_sud - 0.8)
    assert _annonces_de_l_ortho(application) == [
        "Calé sur l'ortho : déplacé de 18,6 m vers l'ouest et de 0,8 m vers le sud. "
        "Le fond HelioScope s'y reconnaît avec une corrélation de 0,51, contre 0,19 "
        "au mieux ailleurs."
    ]
    # Le formulaire montre la correction appliquée : « Recaler » sans y
    # toucher ne doit pas défaire en silence ce que le bouton a fait.
    assert _correction_nord_sud(application).value == pytest.approx(nord_sud - 0.8)

    # Réglé à la main ensuite, le calage n'est plus celui de l'ortho, et le
    # message qui le disait s'efface.
    _correction_nord_sud(application).set_value(nord_sud)
    _cliquer(application, "Recaler")
    application = application.run()
    assert not application.exception, application.exception
    assert calage.correction_nord_sud_m == pytest.approx(nord_sud)
    assert not _annonces_de_l_ortho(application)


def test_le_contrat_ecrit_est_d_origine_plan_pdf(tmp_path, monkeypatch):
    from dp_socle.projet import identifiant_de_dossier, nom_de_projet

    application = _plan_pdf_importe(tmp_path, monkeypatch)
    application.selectbox(key="volume_citerne_plan_pdf").set_value(120)
    application.number_input(key="largeur_portail_plan_pdf").set_value(7.0)
    application = application.run()
    assert not application.exception, application.exception
    _cliquer(application, "Valider l'import")
    application = application.run()
    assert not application.exception, application.exception

    dossier = tmp_path / "sortie" / identifiant_de_dossier(nom_de_projet("Gannay-sur-Loire"))
    projet = json.loads((dossier / "projet.json").read_text(encoding="utf-8"))
    assert projet["origine"] == "plan_pdf"
    assert projet["parametres"]["generalites"]["largeur_portails_m"] == 7.0
    assert projet["ligne_coupe"]["corrigee"]
    assert projet["corrections_plan"] == []
    assert (dossier / "geometries.gpkg").exists()
    # Les sections suivantes s'ouvrent sur ce contrat comme sur un autre.
    assert "3. Ajout de photographies et photomontages" in _titres(application)
