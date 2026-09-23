"""Le chemin du plan projet PDF dans l'application (lot 2ter), joué par `AppTest`.

Même parcours que celui du plan du bureau d'études, par l'autre porte : cadrer
le projet, choisir la source, déposer l'export HelioScope et le plan, importer,
trancher ce que le plan ne dit pas, valider. Ce qui compte est ce qui arrive au
bout : le contrat écrit, d'origine `plan_pdf`, que les sections suivantes
liront sans savoir d'où il vient.

Gannay n'a pas d'emprise cadastrale au dépôt : un carré de 500 m centré sur le
site en tient lieu, et un relevé altimétrique de synthèse évite le RGE ALTI. Ces
tests ne demandent aucun service en ligne.
"""

from __future__ import annotations

import json

import pytest

from tests.jeux_plan_pdf import (
    DXF_GANNAY,
    FOND_GANNAY,
    PLAN_GANNAY,
    gannay_present,
    layout_cad,
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
    export = layout_cad(donnees, DXF_GANNAY, FOND_GANNAY)
    _televerser(application, "Export HelioScope", (export.name, export.read_bytes(), "application/zip"))
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
