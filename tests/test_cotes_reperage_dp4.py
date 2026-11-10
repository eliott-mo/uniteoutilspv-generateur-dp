"""Les dimensions des ouvrages sur le plan de repérage des DP 4.

Décidé le 10/11/2026, après la relecture des planches de façades des vingt
dossiers HOCH du dépôt : huit y cotent la longueur et la largeur de l'ouvrage
que la planche décrit, et l'ouverture du portail ; aucun n'y reporte une
distance, qui reste au plan de masse. La maquette, jouée sur Saint-Cyr,
Auzainvilliers et Sarnois, a été retenue telle quelle.

Le critère est celui du dépôt : une cote se mesure dans le PDF produit — ses
deux flèches, à l'échelle du plan de repérage et non à celle du cartouche, et
sa valeur écrite. Les cas où elle ne se pose pas se lisent au rapport : aucun
ne passe en silence.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace

import geopandas as gpd
import pytest
from shapely import affinity
from shapely.geometry import GeometryCollection, LineString, box

from dp_socle.contrat import charger_contrat, decoder_cote
from dp_socle.erreurs import ErreurCoteOuvrage
from dp_socle.import_be import ecrire_geopackage, ecrire_parametres
from dp_socle.planche import Planche
from dp_socle.planches import dp4_ouvrages
from dp_socle.planches.primitives import BLANC_TOURNANT_MM, TAILLE_COTE, zone_interieure
from dp_socle.projet import Projet

from . import contrat_synthetique as synthese
from .mesure_pdf import format_page, textes
from .test_cotes_dp2_lot10 import CoteAttendue, _pointes_aux_bouts, _vers_la_page_de

pytest.importorskip(
    "cairosvg", reason="CairoSVG et libcairo sont nécessaires pour produire le PDF"
)

MM_PAR_PT = 25.4 / 72.0
ECART_ADMIS = 0.005
X0, Y0 = synthese.ORIGINE_L93
VALEUR_DE_COTE = re.compile(r"^\d[\d ]*(,\d+)? m$")

#: Le portail du site synthétique, sous la citerne. À sa place d'origine, au
#: milieu du côté sud, le zoom de la DP 4-2 — cadré sur la citerne — ne le
#: montre pas, et sa cote ne se mesurerait pas.
PORTAIL = LineString([(X0 + 140.0, Y0), (X0 + 147.0, Y0)])

#: Le poste du site synthétique, 12 x 3 m, et sa plateforme de 20 x 11 m.
POSTE = box(X0 + 170.0, Y0 + 8.0, X0 + 182.0, Y0 + 11.0)


@pytest.fixture
def dp4(tmp_path, monkeypatch):
    """Produit une planche DP 4 du site synthétique, sans la Géoplateforme."""
    monkeypatch.setattr(dp4_ouvrages, "telecharger_parcelles", lambda *a, **k: [])
    dossier = tmp_path / "contrat"
    lot = [
        replace(entite, geometrie=PORTAIL) if entite.categorie == "portail" else entite
        for entite in synthese.entites()
    ]
    ecrire_geopackage(lot, dossier, synthese.ligne_coupe())
    ecrire_parametres(synthese.parametres(), dossier)
    emprise = tmp_path / "emprise.geojson"
    gpd.GeoDataFrame(
        geometry=[box(
            X0 - 60, Y0 - 60,
            X0 + synthese.LARGEUR_SITE_M + 60, Y0 + synthese.HAUTEUR_SITE_M + 60,
        )],
        crs="EPSG:2154",
    ).to_file(emprise, driver="GeoJSON")
    projet = Projet(nom="Essai", commune="Sarnois", code_postal="60210",
                    date="2026-11-10", emprise=str(emprise))
    contrat = charger_contrat(dossier)

    def produire(code):
        return dp4_ouvrages.generer(projet, contrat, tmp_path / "planches", code)

    return produire


def _mesure_mm(sortie, attendue):
    """La distance entre les deux pointes de la cote attendue, en mm, ou `None`."""
    pointes = _pointes_aux_bouts(sortie.chemin, attendue, _vers_la_page_de(sortie))
    return None if pointes is None else (math.dist(*pointes) * MM_PAR_PT, pointes)


def _attendu_mm(sortie, attendue) -> float:
    """La cote attendue sur le papier, à l'échelle du plan de repérage."""
    return attendue.distance_m * 1000.0 / sortie.details["echelle_reperage"]


def _valeurs_au_reperage(sortie) -> list:
    """Les valeurs de cote écrites dans le panneau du plan de repérage."""
    x_zone = sortie.planche.zone_dessin()[0]
    droite_pt = (x_zone + BLANC_TOURNANT_MM + dp4_ouvrages.LARGEUR_REPERAGE_MM) / MM_PAR_PT
    return sorted(
        t for x, _, _, t in textes(sortie.chemin)
        if x < droite_pt and VALEUR_DE_COTE.match(t)
    )


# ---------------------------------------------------------------------------
# Dans le PDF produit
# ---------------------------------------------------------------------------

COTES_DU_POSTE = [
    (CoteAttendue("longueur du poste", X0 + 170.0, X0 + 182.0, (Y0 - 4.0, Y0 + 23.0), True, ""),
     "12,0 m"),
    (CoteAttendue("largeur du poste", Y0 + 8.0, Y0 + 11.0, (X0 + 158.0, X0 + 194.0), False, ""),
     "3,0 m"),
]


@pytest.mark.parametrize("attendue, texte", COTES_DU_POSTE, ids=lambda c: getattr(c, "nom", ""))
def test_le_poste_porte_ses_dimensions_au_plan_de_reperage(dp4, attendue, texte):
    """12 x 3 m, mesurés entre les flèches à l'échelle du repérage, et écrits.

    La ligne de cote est à côté du poste, pas dessus : ses flèches tombent à
    3 mm au moins de lui, sans quoi la cote se lit comme un trait du poste.
    """
    sortie = dp4("DP 4-1")

    mesure = _mesure_mm(sortie, attendue)
    assert mesure is not None, f"{attendue.nom} : pas de cote dont les flèches tombent à ses bouts"
    longueur_mm, (pointe, _) = mesure
    attendu = _attendu_mm(sortie, attendue)
    assert abs(longueur_mm - attendu) / attendu < ECART_ADMIS
    assert texte in _valeurs_au_reperage(sortie), f"« {texte} » n'est pas écrit au repérage"

    vers_la_page = _vers_la_page_de(sortie)
    travers = 1 if attendue.horizontale else 0
    bords = sorted(
        vers_la_page(*coin)[travers]
        for coin in ((POSTE.bounds[0], POSTE.bounds[1]), (POSTE.bounds[2], POSTE.bounds[3]))
    )
    ecart_mm = min(abs(pointe[travers] - b) for b in bords) * MM_PAR_PT
    assert not bords[0] < pointe[travers] < bords[1], "la cote est posée sur le poste"
    assert ecart_mm >= 3.0 - 0.05


def test_la_dp_4_1_ne_cote_que_le_poste(dp4):
    """La planche cote ce qu'elle décrit, et rien d'autre : pas de distance."""
    assert _valeurs_au_reperage(dp4("DP 4-1")) == ["12,0 m", "3,0 m"]


COTES_DE_LA_DP_4_2 = [
    (CoteAttendue("longueur de la citerne", X0 + 140.0, X0 + 151.7, (Y0 - 6.0, Y0 + 20.0), True, ""),
     "11,7 m"),
    (CoteAttendue("largeur de la citerne", Y0 + 4.0, Y0 + 13.3, (X0 + 128.0, X0 + 164.0), False, ""),
     "9,3 m"),
    # L'ouverture du portail, hors de l'enclos : au sud de la clôture.
    (CoteAttendue("ouverture du portail", X0 + 140.0, X0 + 147.0, (Y0 - 8.0, Y0 - 0.3), True, ""),
     "7,0 m"),
]


@pytest.mark.parametrize("attendue, texte", COTES_DE_LA_DP_4_2, ids=lambda c: getattr(c, "nom", ""))
def test_la_citerne_et_l_ouverture_du_portail_se_cotent_sur_la_dp_4_2(dp4, attendue, texte):
    """La citerne au catalogue, 11,7 x 9,3 m ; le portail à sa largeur des paramètres, 7 m."""
    sortie = dp4("DP 4-2")

    mesure = _mesure_mm(sortie, attendue)
    assert mesure is not None, f"{attendue.nom} : pas de cote dont les flèches tombent à ses bouts"
    attendu = _attendu_mm(sortie, attendue)
    assert abs(mesure[0] - attendu) / attendu < ECART_ADMIS
    assert texte in _valeurs_au_reperage(sortie), f"« {texte} » n'est pas écrit au repérage"


def test_la_dp_4_2_ne_cote_que_ce_qu_elle_decrit(dp4):
    assert _valeurs_au_reperage(dp4("DP 4-2")) == ["11,7 m", "7,0 m", "9,3 m"]


@pytest.mark.parametrize("code", ["DP 4-1", "DP 4-2"])
def test_les_valeurs_restent_dans_le_plan(dp4, code):
    """Ni dans la marge du sous-cadre, ni sous le plan, ni sur la légende."""
    sortie = dp4(code)
    x, y, _, h = sortie.planche.zone_dessin()
    ix, iy, il, _ = zone_interieure(
        x + BLANC_TOURNANT_MM, y + BLANC_TOURNANT_MM,
        dp4_ouvrages.LARGEUR_REPERAGE_MM, h - 2 * BLANC_TOURNANT_MM,
    )
    _, hauteur_pt = format_page(sortie.chemin)
    ecrits = [e for e in textes(sortie.chemin) if e[0] < (ix + il) / MM_PAR_PT]
    y_legende = next(y for _, y, _, t in ecrits if t == "Légende")
    valeurs = [e for e in ecrits if VALEUR_DE_COTE.match(e[3])]
    assert valeurs
    for x_pt, y_pt, corps, texte in valeurs:
        largeur_pt = sortie.planche.mesurer_texte(texte, TAILLE_COTE) / MM_PAR_PT
        assert x_pt >= ix / MM_PAR_PT, f"« {texte} » dans la marge de gauche"
        assert x_pt + largeur_pt <= (ix + il) / MM_PAR_PT + 0.5, f"« {texte} » dans la marge de droite"
        assert y_pt > y_legende + corps, f"« {texte} » sous le plan"
        assert y_pt < hauteur_pt - iy / MM_PAR_PT, f"« {texte} » dans le titre"


# ---------------------------------------------------------------------------
# Les cas où une cote ne se pose pas, et le choix de sa place
# ---------------------------------------------------------------------------


class _Contrat:
    """Ce que la pose des dimensions lit du contrat : le catalogue et les paramètres.

    Le catalogue est celui du site synthétique : le PDL/PTR de 12 x 3 m, et les
    deux citernes incendie, 30 m³ (7,95 x 4,44 m) et 120 m³ (11,7 x 9,3 m),
    départagées sur la surface comme le fait le contrat.
    """

    def __init__(self, generalites=None):
        self.generalites = {"largeur_portails_m": 7.0} if generalites is None else generalites

    def cote_de_categorie(self, categorie, surface_m2=None):
        if categorie == "pdl_ptr":
            return decoder_cote(synthese.COTES[0])
        if categorie == "bache_incendie":
            petite, grande = decoder_cote(synthese.COTES[2]), decoder_cote(synthese.COTES[3])
            return petite if surface_m2 is not None and surface_m2 < 60.0 else grande
        raise ErreurCoteOuvrage(f"« {categorie} » n'est pas au catalogue d'essai.")


def _planche(denominateur=300, centre=(X0 + 176.0, Y0 + 9.5)) -> Planche:
    planche = Planche(titre="T", numero="T", projet="T", date="10/11/2026")
    planche.definir_echelle(denominateur, centre_l93=centre)
    return planche


FENETRE = box(X0 + 150.0, Y0 - 15.0, X0 + 202.0, Y0 + 35.0)
#: L'enclos d'un portail au nord : la clôture court à Y0 + 12 m.
ENCLOS_NORD = box(X0 + 100.0, Y0 - 60.0, X0 + 260.0, Y0 + 12.0)
PORTAIL_NORD = LineString([(X0 + 170.0, Y0 + 12.0), (X0 + 177.0, Y0 + 12.0)])


def _coter(visibles, denominateur=300, fenetre=FENETRE, contrat=None, decrits=("pdl_ptr",),
           avec_portail=False):
    from dp_socle.planches.cotes_du_reperage import coter_les_ouvrages

    return coter_les_ouvrages(
        _planche(denominateur), contrat or _Contrat(), visibles,
        decrits=decrits, avec_portail=avec_portail, fenetre=fenetre,
    )


def _ligne(cote) -> LineString:
    return LineString([cote.depart, cote.arrivee])


def _textes(resultat) -> list:
    return sorted(c.texte for c in resultat.cotes)


def test_un_ouvrage_coupe_par_le_bord_du_zoom_n_est_pas_cote_et_le_rapport_le_dit():
    """Coter la moitié visible d'un poste écrirait sa longueur sur un bout de lui."""
    coupe = box(X0 + 176.0, Y0 - 15.0, X0 + 202.0, Y0 + 35.0)
    resultat = _coter([("pdl_ptr", [POSTE])], fenetre=coupe)

    assert resultat.cotes == []
    assert any(
        "Poste de livraison / transformation" in m and "coupé par le bord du zoom" in m
        for m in resultat.messages
    ), resultat.messages


def test_un_exemplaire_coupe_se_dit_exemplaire_quand_un_autre_se_cote():
    """Auzainvilliers, DP 4-3 : le zoom est centré sur un conteneur, un second sort du cadre.

    « Conteneurs BESS est coupé » se lisait comme celui du centre, qui est coté.
    """
    second = box(X0 + 195.0, Y0 + 8.0, X0 + 207.0, Y0 + 11.0)
    resultat = _coter([("pdl_ptr", [POSTE, second])])

    assert _textes(resultat) == ["12,0 m", "3,0 m"]
    assert any(
        "un exemplaire de « Poste de livraison / transformation » est coupé" in m
        for m in resultat.messages
    ), resultat.messages


def test_un_ouvrage_trop_pres_du_bord_du_zoom_n_est_pas_cote_et_le_rapport_le_dit():
    """Entier dans le zoom, mais à 1,7 mm de son bord : sa cote n'y tiendrait pas.

    Le rapport ne le dit pas coupé : il ne l'est pas.
    """
    serre = box(X0 + 169.5, Y0 - 15.0, X0 + 202.0, Y0 + 35.0)
    resultat = _coter([("pdl_ptr", [POSTE])], fenetre=serre)

    assert resultat.cotes == []
    assert any("trop près du bord du zoom" in m for m in resultat.messages), resultat.messages
    assert not any("coupé" in m for m in resultat.messages)


def test_une_dimension_trop_courte_pour_etre_lue_n_est_pas_cotee_et_le_rapport_le_dit():
    """Au 1:2 500, les 3 m du poste font 1,2 mm : sous les 3 mm lisibles de la DP 2."""
    resultat = _coter(
        [("pdl_ptr", [POSTE])], denominateur=2500,
        fenetre=box(X0 + 60.0, Y0 - 100.0, X0 + 290.0, Y0 + 120.0),
    )

    assert _textes(resultat) == ["12,0 m"]
    assert any("largeur" in m and "3 mm lisibles" in m for m in resultat.messages), resultat.messages


def test_un_ouvrage_hors_des_cotes_du_catalogue_n_est_pas_cote_et_le_rapport_le_dit():
    """Un poste dessiné à 13,0 m n'est pas le PDL/PTR de 12 m du catalogue.

    Y écrire 12,0 m serait faux sur le plan, y écrire 13,0 m contredirait son
    élévation. 8 % d'écart, au-delà des 5 % qui reconnaissent le corps d'un
    ouvrage (`palette.TOLERANCE_COTES_POSTE`) ; en deçà, c'est un arrondi de
    tracé, et il se cote sans rien dire.
    """
    long = box(X0 + 170.0, Y0 + 8.0, X0 + 183.0, Y0 + 11.0)
    resultat = _coter([("pdl_ptr", [long])])

    assert resultat.cotes == []
    assert any("aucun objet" in m and "catalogue" in m for m in resultat.messages), resultat.messages

    arrondi = _coter([("pdl_ptr", [box(X0 + 170.0, Y0 + 8.0, X0 + 182.3, Y0 + 11.0)])])
    assert _textes(arrondi) == ["12,0 m", "3,0 m"]
    assert not arrondi.messages


def test_la_valeur_s_ecrit_a_la_precision_du_catalogue():
    """7,95 x 4,44 m pour la citerne de 30 m³ : au dixième, la cote écrirait 8,0 m.

    Son élévation, à droite, écrit 7,95 m : les deux se contrediraient sur la
    même planche. Une valeur ronde au dixième garde sa décimale, « 12,0 m ».
    """
    petite = box(X0 + 172.0, Y0 + 8.0, X0 + 179.95, Y0 + 12.44)
    resultat = _coter([("bache_incendie", [petite])], decrits=("bache_incendie",))

    assert _textes(resultat) == ["4,44 m", "7,95 m"]


def test_un_ouvrage_dessine_deux_fois_ne_se_cote_qu_une_fois():
    resultat = _coter([("pdl_ptr", [POSTE, box(*POSTE.bounds)])])

    assert _textes(resultat) == ["12,0 m", "3,0 m"]


def test_un_ouvrage_redresse_en_collection_se_cote_sur_sa_surface():
    """`make_valid` rend un contour auto-intersectant en collection (Auzainvilliers)."""
    collection = GeometryCollection(
        [POSTE, LineString([(X0 + 182.0, Y0 + 11.0), (X0 + 183.0, Y0 + 12.0)])]
    )
    resultat = _coter([("pdl_ptr", [collection])])

    assert _textes(resultat) == ["12,0 m", "3,0 m"]


def test_un_ouvrage_tourne_se_cote_le_long_de_ses_cotes():
    """Un poste posé à 30° : ses cotes suivent ses côtés, à leurs valeurs du catalogue."""
    tourne = affinity.rotate(POSTE, 30.0, origin="centroid")
    resultat = _coter([("pdl_ptr", [tourne])])

    assert _textes(resultat) == ["12,0 m", "3,0 m"]
    longueur = _ligne(next(c for c in resultat.cotes if c.texte == "12,0 m"))
    (xa, ya), (xb, yb) = longueur.coords
    assert math.degrees(math.atan2(yb - ya, xb - xa)) % 180.0 == pytest.approx(30.0, abs=0.5)
    assert longueur.length == pytest.approx(12.0, abs=0.01)


def test_la_cote_va_du_cote_libre_plutot_que_contre_la_cloture():
    """La clôture longe le poste à 1,2 m au sud : la longueur se cote au nord."""
    enclos = box(X0 + 100.0, Y0 + 6.8, X0 + 260.0, Y0 + 60.0)
    resultat = _coter([("cloture", [enclos]), ("pdl_ptr", [POSTE])])

    longueur = next(c for c in resultat.cotes if c.texte == "12,0 m")
    assert _ligne(longueur).centroid.y > POSTE.bounds[3]


def test_une_cloture_dessinee_en_trait_gene_comme_une_cloture_fermee():
    """Les lots 2bis et 2ter gardent une clôture ouverte en trait : elle gêne autant."""
    trait = LineString([(X0 + 100.0, Y0 + 6.8), (X0 + 260.0, Y0 + 6.8)])
    resultat = _coter([("cloture", [trait]), ("pdl_ptr", [POSTE])])

    longueur = next(c for c in resultat.cotes if c.texte == "12,0 m")
    assert _ligne(longueur).centroid.y > POSTE.bounds[3]


def test_une_cote_ne_court_pas_le_long_du_contour_d_une_piste_qui_cerne_le_poste():
    """Saint-Cyr : la piste à créer cerne le poste de 1 m, 3,3 mm au 1:300.

    La cote tombait sur son contour, parce que le chemin existant, qui touche
    aussi le poste et s'étend au loin, la gardait à 3,5 mm de lui. C'est le bord
    le plus proche qui compte, pas l'étendue de ce qui touche l'ouvrage.
    """
    cerne = box(X0 + 169.0, Y0 + 7.0, X0 + 183.0, Y0 + 12.0).difference(POSTE)
    chemin = box(X0 + 100.0, Y0 - 40.0, X0 + 260.0, Y0 + 8.0)
    resultat = _coter([
        ("chemin_existant", [chemin]), ("piste_lourde_a_creer", [cerne]), ("pdl_ptr", [POSTE]),
    ])

    longueur = _ligne(next(c for c in resultat.cotes if c.texte == "12,0 m"))
    y = longueur.centroid.y
    ecart_au_contour = min(abs(y - (Y0 + 7.0)), abs(y - (Y0 + 12.0)))
    assert y < Y0 + 7.0 or y > Y0 + 12.0, "la cote est sur la piste qui cerne le poste"
    assert ecart_au_contour == pytest.approx(3.5 * 300 / 1000, abs=0.01)


def test_une_plateforme_qui_deborde_a_peine_rejette_la_cote_au_dela_d_elle():
    """Deux bandes de terre remise de 1,50 et 1,00 m le long du poste (Saint-Cyr).

    5,0 et 3,3 mm au 1:300 : leur bord tombait sous la ligne de cote. Une
    grande plateforme, elle, garde la cote près du poste : la rejeter au loin
    l'éloignerait de ce qu'elle mesure.
    """
    bandes = [
        box(X0 + 170.0, Y0 + 6.5, X0 + 182.0, Y0 + 8.0),
        box(X0 + 170.0, Y0 + 11.0, X0 + 182.0, Y0 + 12.0),
    ]
    resultat = _coter([("plateforme", bandes), ("pdl_ptr", [POSTE])])
    longueur = _ligne(next(c for c in resultat.cotes if c.texte == "12,0 m"))
    y = longueur.centroid.y
    assert y < Y0 + 6.5 or y > Y0 + 12.0, "la cote est sur la terre remise"
    assert min(abs(y - (Y0 + 6.5)), abs(y - (Y0 + 12.0))) == pytest.approx(3.5 * 300 / 1000, abs=0.01)

    large = box(X0 + 166.0, Y0 + 4.0, X0 + 186.0, Y0 + 15.0)
    resultat = _coter([("plateforme", [large]), ("pdl_ptr", [POSTE])])
    longueur = _ligne(next(c for c in resultat.cotes if c.texte == "12,0 m"))
    ecart = min(abs(longueur.centroid.y - POSTE.bounds[1]), abs(longueur.centroid.y - POSTE.bounds[3]))
    assert ecart == pytest.approx(3.5 * 300 / 1000, abs=0.01)


def _portail_a_vantaux(x, y, sens) -> list:
    """Le symbole d'un portail de 7 m : son seuil et ses deux vantaux de 3,5 m, en arcs.

    `sens` : +1, les vantaux s'ouvrent vers le nord ; -1, vers le sud. Cinq
    traits, comme le dessinent les plans du bureau d'études (Saint-Cyr IND07).
    """
    def arc(cx, de, a):
        return LineString([
            (cx + 3.5 * math.cos(math.radians(t)), y + sens * 3.5 * math.sin(math.radians(t)))
            for t in range(de, a + 1, 10)
        ])

    return [
        LineString([(x, y), (x + 7.0, y)]),
        LineString([(x, y), (x, y + sens * 3.5)]),
        arc(x, 0, 90),
        LineString([(x + 7.0, y), (x + 7.0, y + sens * 3.5)]),
        arc(x + 7.0, 90, 180),
    ]


def test_l_ouverture_du_portail_se_cote_hors_de_l_enclos():
    """Un portail au nord de l'enclos se cote au nord, dehors, le long de la clôture.

    Au sud, l'usage et l'enclos s'accordent ; au nord, seul l'enclos fait
    sortir la cote : du côté des vantaux, elle tomberait dans la piste.
    """
    resultat = _coter(
        [("cloture", [ENCLOS_NORD]), ("portail", [PORTAIL_NORD])], decrits=(), avec_portail=True,
    )

    assert _textes(resultat) == ["7,0 m"]
    assert _ligne(resultat.cotes[0]).centroid.y > Y0 + 12.0


def test_l_ouverture_d_un_portail_a_vantaux_se_cote_hors_de_l_enclos():
    """Le symbole réel, seuil et vantaux ouverts vers l'intérieur : la cote passe dehors."""
    traits = _portail_a_vantaux(X0 + 170.0, Y0 + 12.0, sens=-1)
    resultat = _coter(
        [("cloture", [ENCLOS_NORD]), ("portail", traits)], decrits=(), avec_portail=True,
    )

    assert _textes(resultat) == ["7,0 m"]
    ligne = _ligne(resultat.cotes[0])
    assert ligne.centroid.y > Y0 + 12.0
    assert ligne.length == pytest.approx(7.0, abs=0.01)


def test_une_cloture_fermee_dessinee_en_trait_fait_encore_l_enclos_du_portail():
    anneau = LineString(list(ENCLOS_NORD.exterior.coords))
    resultat = _coter(
        [("cloture", [anneau]), ("portail", [PORTAIL_NORD])], decrits=(), avec_portail=True,
    )

    assert _textes(resultat) == ["7,0 m"]
    assert _ligne(resultat.cotes[0]).centroid.y > Y0 + 12.0


def test_un_portail_sans_place_hors_de_l_enclos_se_cote_dedans_et_le_rapport_le_dit():
    """Au bord nord du zoom, la cote ne tient pas dehors : elle passe côté vantaux."""
    serre_au_nord = box(X0 + 150.0, Y0 - 15.0, X0 + 202.0, Y0 + 13.4)
    resultat = _coter(
        [("cloture", [ENCLOS_NORD]), ("portail", [PORTAIL_NORD])],
        fenetre=serre_au_nord, decrits=(), avec_portail=True,
    )

    assert _textes(resultat) == ["7,0 m"]
    assert _ligne(resultat.cotes[0]).centroid.y < Y0 + 12.0
    assert any("dans l'enclos" in m for m in resultat.messages), resultat.messages


def test_un_portail_sans_ouverture_mesurable_n_est_pas_cote_et_le_rapport_le_dit():
    point = LineString([(X0 + 170.0, Y0 + 12.0), (X0 + 170.0, Y0 + 12.0)])
    resultat = _coter(
        [("cloture", [ENCLOS_NORD]), ("portail", [point])], decrits=(), avec_portail=True,
    )

    assert resultat.cotes == []
    assert any("portail" in m and "mesurable" in m for m in resultat.messages), resultat.messages


def test_un_portail_sans_largeur_aux_parametres_n_est_pas_cote_et_le_rapport_le_dit():
    """Mesurer l'ouverture sur le plan serait un repli : l'élévation, elle, n'est pas dessinée."""
    resultat = _coter(
        [("cloture", [ENCLOS_NORD]), ("portail", [PORTAIL_NORD])],
        contrat=_Contrat(generalites={}), decrits=(), avec_portail=True,
    )

    assert resultat.cotes == []
    assert any("portail" in m and "aucune largeur" in m for m in resultat.messages), resultat.messages


