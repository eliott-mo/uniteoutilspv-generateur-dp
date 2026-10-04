"""Lot 9 — locaux techniques surélevés au-dessus des plus hautes eaux.

Ce qui se vérifie ici, dans l'ordre où le défaut coûterait le plus cher :

1. les deux hauteurs saisies sont relatives au terrain naturel, et le dépôt
   refuse une saisie qui se contredit elle-même ;
2. la planche produite **montre** la surélévation — mesurée dans le PDF, pas
   dans les valeurs intermédiaires, selon la règle du dépôt ;
3. un projet sans surélévation sort exactement comme avant.

Le troisième point est le plus important des trois : la quasi-totalité des
dossiers ne sont pas en zone inondable, et ce lot ne doit rien leur changer.
"""

from __future__ import annotations

import json

import pytest

from dp_socle.erreurs import ErreurDP
from dp_socle.projet import Projet


def _projet(tmp_path, **cotes):
    """Un `projet.json` minimal, prêt à valider."""
    emprise = tmp_path / "emprise.geojson"
    emprise.write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    return Projet(
        nom="essai",
        commune="Saint-Cyr-en-Val",
        code_postal="45590",
        date="2026-10-04",
        emprise=str(emprise),
        **cotes,
    )


def test_les_deux_cotes_de_saint_cyr_se_valident(tmp_path):
    """Les valeurs réelles du projet qui a demandé le lot, relevées le 02/10/2026."""
    _projet(tmp_path, surelevation_locaux_m=2.25, phec_locaux_m=1.95).valider()


def test_la_surelevation_seule_suffit(tmp_path):
    """La PHEC est facultative : sans elle, le reste se dessine quand même."""
    _projet(tmp_path, surelevation_locaux_m=2.25).valider()


def test_un_projet_sans_surelevation_reste_valide(tmp_path):
    """Le cas courant : rien de saisi, rien de changé."""
    projet = _projet(tmp_path)
    projet.valider()
    assert projet.surelevation_locaux_m is None
    assert projet.phec_locaux_m is None


def test_la_phec_seule_est_refusee(tmp_path):
    """Elle ne permet pas de déduire le plancher : leur écart est la revanche.

    10 cm à Périgny pour 30 à Saint-Cyr (mesuré le 02/10/2026) : il n'y a pas
    de valeur à supposer, et supposer serait le repli que le dépôt interdit.
    """
    with pytest.raises(ErreurDP, match="revanche"):
        _projet(tmp_path, phec_locaux_m=1.95).valider()


def test_une_phec_au_niveau_du_plancher_est_refusee(tmp_path):
    """Le dessin se contredirait : l'eau au-dessus du plancher qu'elle épargne."""
    with pytest.raises(ErreurDP, match="contredirait"):
        _projet(tmp_path, surelevation_locaux_m=1.95, phec_locaux_m=1.95).valider()
    with pytest.raises(ErreurDP, match="contredirait"):
        _projet(tmp_path, surelevation_locaux_m=1.95, phec_locaux_m=2.25).valider()


@pytest.mark.parametrize("hauteur", [0.0, -2.25])
def test_une_hauteur_nulle_ou_negative_est_refusee(tmp_path, hauteur):
    """Zéro n'est pas « posé au sol » : c'est un champ qu'on laisse vide.

    Les distinguer a une raison : `None` dit « non concerné » et sort la ligne
    de constat au rapport, tandis qu'un zéro saisi laisserait croire à une
    surélévation réglée à zéro, ce qui n'existe pas en PPRI.
    """
    with pytest.raises(ErreurDP, match="laissez le champ vide|hauteur en mètres"):
        _projet(tmp_path, surelevation_locaux_m=hauteur).valider()


def test_une_valeur_non_numerique_est_refusee(tmp_path):
    """Un `projet.json` corrigé à la main de travers se refuse, il ne s'arrondit pas."""
    with pytest.raises(ErreurDP, match="hauteur en mètres"):
        _projet(tmp_path, surelevation_locaux_m="2,25").valider()


def test_les_cotes_font_l_aller_retour_par_projet_json(tmp_path):
    """Écrites puis relues, elles valent la même chose.

    `ecrire` ne garde que les champs renseignés : une surélévation absente ne
    doit pas apparaître dans le fichier, sans quoi tous les dossiers porteraient
    un champ de zone inondable.
    """
    chemin = _projet(
        tmp_path, surelevation_locaux_m=2.25, phec_locaux_m=1.95
    ).ecrire(tmp_path / "projet.json")
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    assert donnees["surelevation_locaux_m"] == 2.25
    assert donnees["phec_locaux_m"] == 1.95

    chemin_nu = _projet(tmp_path).ecrire(tmp_path / "nu" / "projet.json")
    nues = json.loads(chemin_nu.read_text(encoding="utf-8"))
    assert "surelevation_locaux_m" not in nues
    assert "phec_locaux_m" not in nues


# ---------------------------------------------------------------------------
# Ce que la planche montre, mesuré dans le PDF produit
# ---------------------------------------------------------------------------

import geopandas as gpd
from pypdf import PdfReader
from shapely.geometry import box

from dp_socle.contrat import charger_contrat
from dp_socle.planches import dp4_ouvrages

from . import contrat_synthetique as synthese
from .mesure_pdf import longueur, segments_obliques


@pytest.fixture
def site(tmp_path, monkeypatch):
    """Contrat synthétique et projet, prêts à produire DP 4-1.

    Le parcellaire du plan de repérage est neutralisé : sans cela le vert du
    test dépend de la Géoplateforme, et `_parcelles_du_cadre` rattrape une
    panne en produisant la planche sans fond — le défaut serait invisible.
    """
    monkeypatch.setattr(dp4_ouvrages, "telecharger_parcelles", lambda *a, **k: [])

    def _preparer(**cotes):
        dossier = tmp_path / "sortie" / "Essai"
        synthese.ecrire(dossier)
        x0, y0 = synthese.ORIGINE_L93
        emprise = tmp_path / "emprise.geojson"
        gpd.GeoDataFrame(
            geometry=[
                box(
                    x0 - 60, y0 - 60,
                    x0 + synthese.LARGEUR_SITE_M + 60,
                    y0 + synthese.HAUTEUR_SITE_M + 60,
                )
            ],
            crs="EPSG:2154",
        ).to_file(emprise, driver="GeoJSON")
        projet = Projet(
            nom="Essai", commune="Saint-Cyr-en-Val", code_postal="45590",
            date="2026-10-04", emprise=str(emprise), libelle="Essai lot 9",
            **cotes,
        )
        return projet, charger_contrat(dossier)

    return _preparer


def _texte(chemin) -> str:
    return PdfReader(str(chemin)).pages[0].extract_text()


def test_la_planche_porte_la_surelevation_et_la_phec(site, tmp_path):
    """Les deux hauteurs se lisent sur la planche produite, en relatif.

    Et aucune cote NGF n'y figure : c'est la décision D1, et c'est ce qui
    dispense la planche de s'accorder avec la topographie relevée.
    """
    projet, contrat = site(surelevation_locaux_m=2.25, phec_locaux_m=1.95)
    sortie = dp4_ouvrages.generer(projet, contrat, tmp_path, "DP 4-1")
    texte = _texte(sortie.chemin)

    assert "PHEC (1,95 m)" in texte
    assert "plus hautes eaux connues" in texte
    assert "2,25 m au-dessus du terrain naturel" in texte
    assert "13 marches" in texte
    # La convention de l'escalier est écrite sur la planche, pas seulement dans
    # le code : le bureau d'études doit savoir qu'il lit une convention.
    assert dp4_ouvrages.COTE_ESCALIER in texte
    # Aucune cote NGF : ni la cote PHEC de Saint-Cyr, ni celle du plancher.
    for absolu in ("97,45", "97,75", "95,50", "NGF"):
        assert absolu not in texte, absolu


def test_la_phec_omise_ne_trace_aucune_ligne_d_eau(site, tmp_path):
    """Sans elle, la plateforme est dessinée mais la planche se tait."""
    projet, contrat = site(surelevation_locaux_m=2.25)
    sortie = dp4_ouvrages.generer(projet, contrat, tmp_path, "DP 4-1")
    texte = _texte(sortie.chemin)

    assert "2,25 m au-dessus du terrain naturel" in texte
    assert "PHEC" not in texte


def test_l_escalier_est_bien_trace(site, tmp_path):
    """Mesuré dans le PDF : la main courante est une longue oblique.

    C'est la seule oblique de cette longueur sur la planche — les autres sont
    les pattes des lignes de cote, qui font moins de 2 mm. Sans surélévation il
    n'y en a aucune, et c'est ce qui prouve que la volée est dessinée plutôt
    qu'annoncée.
    """
    projet, contrat = site(surelevation_locaux_m=2.25)
    avec = dp4_ouvrages.generer(projet, contrat, tmp_path / "avec", "DP 4-1")
    nu, contrat_nu = site()
    sans = dp4_ouvrages.generer(nu, contrat_nu, tmp_path / "sans", "DP 4-1")

    def plus_longue(chemin) -> float:
        obliques = segments_obliques(chemin)
        return max((longueur(s) for s in obliques), default=0.0)

    # Deux élévations long pan portent la volée, donc deux mains courantes.
    longues = [
        s for s in segments_obliques(avec.chemin) if longueur(s) > 50.0
    ]
    assert len(longues) == 2, f"{len(longues)} oblique(s) longue(s)"
    assert plus_longue(sans.chemin) < 50.0


def test_un_projet_sans_surelevation_le_dit_au_rapport(site, tmp_path):
    """Un constat, pas une alerte : le rapport dit ce que l'outil a fait.

    C'est le prix de la saisie discrète (décision D4) : le volet replié se
    rate — celui des intitulés de légende l'a prouvé le 26/09/2026 — et le
    rapport est ce qui rattrape l'oubli avant le dépôt.
    """
    projet, contrat = site()
    sortie = dp4_ouvrages.generer(projet, contrat, tmp_path, "DP 4-1")
    constats = sortie.details["avertissements"]
    assert any("posés au sol" in m and "PPRI" in m for m in constats), constats

    releve, contrat_releve = site(surelevation_locaux_m=2.25)
    avec = dp4_ouvrages.generer(releve, contrat_releve, tmp_path / "avec", "DP 4-1")
    assert not any("posés au sol" in m for m in avec.details["avertissements"])


def test_la_planche_tient_encore_a_une_echelle_autorisee(site, tmp_path):
    """La question laissée ouverte par le brief, et sa réponse mesurée.

    2,25 m de plus par vue et 3,64 m de volée élargissent les élévations long
    pan de moitié. Il fallait vérifier que la planche ne se retrouve pas sous
    les échelles permises : elle y tient, et le chiffre est noté ici pour que
    sa dérive se voie.
    """
    nu, contrat_nu = site()
    sans = dp4_ouvrages.generer(nu, contrat_nu, tmp_path / "sans", "DP 4-1")
    projet, contrat = site(surelevation_locaux_m=2.25, phec_locaux_m=1.95)
    avec = dp4_ouvrages.generer(projet, contrat, tmp_path / "avec", "DP 4-1")

    for sortie in (sans, avec):
        assert sortie.details["echelle_ouvrages"] in dp4_ouvrages.ECHELLES_OUVRAGES
    # La surélévation ne peut qu'agrandir les vues, donc jamais remonter
    # l'échelle : le dénominateur ne descend pas.
    assert avec.details["echelle_ouvrages"] >= sans.details["echelle_ouvrages"]


def test_une_surelevation_absurde_est_refusee_par_la_mise_en_page(site, tmp_path):
    """La seconde question du brief, et sa réponse : aucun plafond à inventer.

    Une faute de frappe — 22,5 au lieu de 2,25 — ne s'absorbe pas en écrasant
    l'échelle : `_echelles_des_blocs` refuse, parce que la vue ne tient plus
    dans le panneau même au 1:200. Le contrôle existait donc déjà, et lui a une
    raison mesurable là où un seuil de vraisemblance serait arbitraire.

    Ce test tient le comportement : si quelqu'un desserre un jour la mise en
    page, il faudra décider sciemment quoi faire de 22,5 m.
    """
    from dp_socle.erreurs import ErreurComposition

    projet, contrat = site(surelevation_locaux_m=22.5)
    with pytest.raises(ErreurComposition, match="ne tient pas"):
        dp4_ouvrages.generer(projet, contrat, tmp_path, "DP 4-1")


def test_l_echelle_de_saint_cyr_descend_d_un_cran(site, tmp_path):
    """Ce que la surélévation coûte à la planche, mesuré le 04/10/2026.

    Le poste du contrat d'essai sort au 1:100 posé au sol, au 1:100 encore avec
    la surélévation de Périgny (0,55 m), et au **1:200** avec celle de
    Saint-Cyr (2,25 m) : cinq vues qui montent de 2,25 m font 112 mm de plus
    sur la colonne, et le panneau n'en a pas la place.

    Le 1:200 est une échelle permise et le cartouche l'annonce — la planche
    reste juste. Le chiffre est pris ici pour que sa dérive se voie, et parce
    que c'est lui qu'il faudra regarder si la lisibilité de la volée est un
    jour contestée.
    """
    cas = {
        "sol": {},
        "perigny": {"surelevation_locaux_m": 0.55, "phec_locaux_m": 0.45},
        "saint_cyr": {"surelevation_locaux_m": 2.25, "phec_locaux_m": 1.95},
    }
    mesures = {}
    for nom, cotes in cas.items():
        projet, contrat = site(**cotes)
        sortie = dp4_ouvrages.generer(projet, contrat, tmp_path / nom, "DP 4-1")
        mesures[nom] = sortie.details["echelle_ouvrages"]

    assert mesures == {"sol": 100, "perigny": 100, "saint_cyr": 200}


# ---------------------------------------------------------------------------
# La saisie, et les deux parcours d'import
# ---------------------------------------------------------------------------


def _appels_dans_app(nom_appel):
    """Où `app.py` appelle une fonction : (portée, ligne), par lecture de l'arbre.

    Contrôlé à la source plutôt qu'à l'exécution parce que l'oubli redouté est
    silencieux : un parcours d'import sur les deux garderait son volet, l'autre
    ne l'aurait jamais, et rien ne le dirait — le chef de projet verrait
    simplement un champ absent, sans savoir qu'il devrait être là.
    """
    import ast
    from pathlib import Path

    arbre = ast.parse(
        (Path(__file__).resolve().parent.parent / "app.py").read_text(
            encoding="utf-8"
        )
    )
    trouves = []

    def descendre(noeud, portee):
        for enfant in ast.iter_child_nodes(noeud):
            if isinstance(enfant, (ast.FunctionDef, ast.AsyncFunctionDef)):
                descendre(enfant, enfant.name)
                continue
            if (
                isinstance(enfant, ast.Call)
                and isinstance(enfant.func, ast.Name)
                and enfant.func.id == nom_appel
            ):
                trouves.append((portee, enfant.lineno))
            descendre(enfant, portee)

    descendre(arbre, "<module>")
    return trouves


def test_la_saisie_est_posee_une_seule_fois_pour_les_deux_parcours():
    """Un seul volet, dans la partie de la section 2 commune aux deux imports.

    Il y en avait deux au premier jet — un par parcours —, le tableau des
    gabarits étant propre au plan PDF et le typage des voiries au plan du bureau
    d'études. Mais la suite de la section 2 est **commune** : sur le parcours
    PDF les deux s'affichaient, et Streamlit levait
    `StreamlitDuplicateElementKey` sur la clé du premier champ. Relevé le
    04/10/2026 par `test_app_plan_pdf`, que rien d'autre n'aurait vu — les
    tests de modules n'exécutent jamais `app.py`.

    Un seul appel, donc, et posé là où le chef de projet tranche déjà le type
    de ses voiries : c'est la place des décisions que les fichiers du bureau
    d'études ne portent pas.
    """
    appels = _appels_dans_app("_saisir_la_surelevation")
    assert len(appels) == 1, appels
    (portee, ligne), = appels
    assert portee == "<module>"
    (_, ligne_voiries), = _appels_dans_app("_trancher_les_voiries")
    assert abs(ligne - ligne_voiries) <= 3


def test_les_cotes_rearment_le_bouton_de_generation():
    """Saisir une surélévation doit redonner la main sur « Générer ».

    Sans cela le bouton reste grisé — la génération est « déjà faite » — et le
    chef de projet ne peut pas corriger un dossier qu'il vient de produire au
    sol. C'est la même mécanique que pour le tri des voiries.
    """
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "app.py").read_text(
        encoding="utf-8"
    )
    # Par l'arbre, et non par découpe de texte : le tuple porte des appels
    # parenthésés, et une coupe sur « ) » s'arrêtait au premier d'entre eux.
    entrees = None
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.Assign) and any(
            isinstance(c, ast.Name) and c.id == "_entrees_generation"
            for c in noeud.targets
        ):
            entrees = ast.get_source_segment(source, noeud.value)
    assert entrees is not None, "_entrees_generation introuvable"
    assert "surelevation_locaux" in entrees
    assert "phec_locaux" in entrees


def test_les_cotes_partent_bien_dans_le_projet():
    """Elles doivent arriver à `Projet`, sans quoi la planche ne les verra pas."""
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "app.py").read_text(
        encoding="utf-8"
    )
    construction = source.split("def _construire_projet", 1)[1]
    assert "surelevation_locaux_m=surelevation_locaux" in construction
    assert "phec_locaux_m=phec_locaux" in construction


def test_la_ligne_phec_ne_deborde_pas_sur_la_vue_voisine(site, tmp_path):
    """Une seule étiquette PHEC sur la planche, et des lignes qui s'arrêtent.

    Relevé à l'œil sur la planche de Saint-Cyr le 04/10/2026, après la première
    version : l'étiquette était portée par les cinq vues et les quatre dernières
    s'écrivaient par-dessus le dessin d'à côté, tandis que les lignes d'eau,
    allongées de 3 mm pour se détacher — 60 cm de terrain au 1:200 —, se
    rejoignaient en une seule traversant la planche.

    C'est le même piège que la fourchette du socle avait rencontré le
    05/09/2026 dans ce fichier, et il se résout de la même façon : une vue la
    porte, les autres non.
    """
    projet, contrat = site(surelevation_locaux_m=2.25, phec_locaux_m=1.95)
    sortie = dp4_ouvrages.generer(projet, contrat, tmp_path, "DP 4-1")
    assert _texte(sortie.chemin).count("PHEC (1,95 m)") == 1
