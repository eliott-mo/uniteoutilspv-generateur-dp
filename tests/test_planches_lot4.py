"""Planches du lot 4, mesurées dans le PDF produit.

Le critère n'est pas « le code tourne » mais « la planche produite est
juste ». Les coupes et les dessins d'ouvrages ont leur propre échelle locale,
distincte de celle du cartouche : elles demandent le même traitement que
`test_echelle_pdf.py` réserve à la transformation Lambert 93, et pour la même
raison — une échelle fausse se dessine parfaitement.

Deux familles de tests ici :

- ceux qui mesurent le repère local sur un PDF composé exprès. Ils ne
  demandent aucun service en ligne, et ce sont eux qui portent les critères de
  validation n°1 (échelle vraie) et n°2 (isotropie) ;
- ceux qui produisent une planche entière depuis un contrat. Le plan de masse
  et la coupe du terrain portent le parcellaire, qui vient du WFS IGN : ils
  sont marqués `reseau`.
"""

from __future__ import annotations

import math
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, box

from dp_socle.assemblage import TAILLE_MAX_MO, generer_dossier
from dp_socle.contrat import charger_contrat
from dp_socle.dossier import codes_produits, numero_planche
from dp_socle.erreurs import ErreurComposition
from dp_socle.import_be import ORIGINE_HELIOSCOPE
from dp_socle.planche import Planche
from dp_socle.planches import dp3_coupes, dp4_ouvrages
from dp_socle.planches.primitives import TRAIT_FORT, Dessin
from dp_socle.planches.standards import (
    HAUTEUR_ARBRE_M,
    LARGEUR_ARBRE_M,
)
from dp_socle.projet import Projet

from . import contrat_synthetique as synthese
from .mesure_pdf import longueur, segments, segments_obliques

pytest.importorskip(
    "cairosvg", reason="CairoSVG et libcairo sont nécessaires pour produire le PDF"
)

MM_PAR_PT = 25.4 / 72.0
ECART_ADMIS = 0.005


def _planche_nue() -> Planche:
    return Planche(
        titre="TÉMOIN", numero="T", projet="Contrôle métrologique",
        date="04/09/2026", avec_cartouche=False,
    )


# ---------------------------------------------------------------------------
# Critère n°1 — l'échelle locale est vraie dans le PDF produit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("denominateur", [50, 80, 100, 200, 500, 1000])
def test_echelle_locale_vraie_a_moins_de_0_5_pourcent(tmp_path, denominateur):
    """Un segment de longueur connue, mesuré dans le PDF, à l'échelle annoncée.

    Les coupes et les dessins d'ouvrages ne passent pas par la transformation
    Lambert 93 : leur échelle est celle de `Dessin`, et elle demande son
    propre contrôle métrologique.
    """
    planche = _planche_nue()
    dessin = Dessin(
        planche=planche, denominateur=denominateur, origine_mm=(60.0, 200.0)
    )
    # Segment oblique, pour se distinguer sans ambiguïté du cadre et du fond.
    delta_x_m = 20.0
    delta_y_m = 12.0
    dessin.ligne((0.0, 0.0), (delta_x_m, delta_y_m), TRAIT_FORT)

    chemin = planche.rendre_pdf(tmp_path / f"temoin_{denominateur}.pdf")
    obliques = segments_obliques(chemin)
    assert obliques, "aucun segment oblique trouvé dans le PDF produit"

    mesure_mm = max(longueur(s) for s in obliques) * MM_PAR_PT
    attendu_mm = math.hypot(delta_x_m, delta_y_m) * 1000.0 / denominateur
    ecart = abs(mesure_mm - attendu_mm) / attendu_mm
    assert ecart < ECART_ADMIS, (
        f"segment mesuré {mesure_mm:.3f} mm dans le PDF, attendu "
        f"{attendu_mm:.3f} mm au 1:{denominateur} — écart {ecart:.3%}"
    )


# ---------------------------------------------------------------------------
# Critère n°2 — isotropie : un mètre vertical vaut un mètre horizontal
# ---------------------------------------------------------------------------


def test_isotropie_mesuree_dans_le_pdf(tmp_path):
    """Décision D2, vérifiée là où elle compte : sur le fichier produit.

    Une coupe dont les deux axes n'ont pas le même rapport n'est plus à
    l'échelle qu'elle annonce. L'aperçu de contrôle du lot 2bis applique une
    exagération verticale, avec raison ; une planche ne le peut pas.
    """
    planche = _planche_nue()
    dessin = Dessin(planche=planche, denominateur=200, origine_mm=(60.0, 220.0))
    cote_m = 40.0
    dessin.ligne((0.0, 0.0), (cote_m, 0.0), TRAIT_FORT)
    dessin.ligne((0.0, 0.0), (0.0, cote_m), TRAIT_FORT)

    chemin = planche.rendre_pdf(tmp_path / "isotropie.pdf")
    horizontaux, verticaux = [], []
    for segment in segments(chemin):
        (x1, y1), (x2, y2) = segment
        if abs(y2 - y1) < 0.5 and abs(x2 - x1) > 1.0:
            horizontaux.append(longueur(segment))
        elif abs(x2 - x1) < 0.5 and abs(y2 - y1) > 1.0:
            verticaux.append(longueur(segment))

    attendu_pt = cote_m * 1000.0 / 200 / MM_PAR_PT
    horizontal = min(horizontaux, key=lambda v: abs(v - attendu_pt))
    vertical = min(verticaux, key=lambda v: abs(v - attendu_pt))
    assert horizontal == pytest.approx(vertical, rel=ECART_ADMIS), (
        f"{cote_m} m mesurent {horizontal * MM_PAR_PT:.3f} mm à l'horizontale "
        f"et {vertical * MM_PAR_PT:.3f} mm à la verticale"
    )
    assert horizontal * MM_PAR_PT == pytest.approx(
        cote_m * 1000.0 / 200, rel=ECART_ADMIS
    )


def test_isotropie_du_profil_de_terrain(tmp_path):
    """Sur une planche réelle, la pente dessinée est la pente du terrain.

    Le profil synthétique descend d'une pente constante de 2 %. Chaque segment
    du profil tracé doit donc montrer, dans le PDF, un rapport de 0,02 entre
    son élévation et sa longueur. Une exagération verticale, si discrète
    soit-elle, se lirait ici.
    """
    dessin_planche = _planche_nue()
    # L'origine du repère est posée à l'altitude du point A : un profil se
    # dessine en cotes NGF, et une origine à zéro le placerait à 190 m
    # au-dessus de la feuille.
    dessin = Dessin(
        planche=dessin_planche,
        denominateur=500,
        origine_mm=(40.0, 240.0),
        origine_m=(0.0, synthese.ALTITUDE_A_M),
    )
    profil = [
        (abscisse, synthese.altitude_a(abscisse))
        for abscisse in range(0, int(synthese.LONGUEUR_COUPE_M) + 1, 5)
    ]
    dessin.polyligne(profil, TRAIT_FORT)
    chemin = dessin_planche.rendre_pdf(tmp_path / "profil.pdf")

    attendu_dx_pt = 5.0 * 1000.0 / 500 / MM_PAR_PT
    pentes = []
    for (x1, y1), (x2, y2) in segments(chemin):
        if abs(abs(x2 - x1) - attendu_dx_pt) > 0.2:
            continue
        pentes.append(abs(y2 - y1) / abs(x2 - x1))
    assert pentes, "aucun segment du profil retrouvé dans le PDF"
    for pente in pentes:
        assert pente == pytest.approx(synthese.PENTE, abs=0.001), (
            f"pente dessinée {pente:.4f} pour {synthese.PENTE} au terrain"
        )


# ---------------------------------------------------------------------------
# Composition des planches
# ---------------------------------------------------------------------------


@pytest.fixture
def site(tmp_path):
    """Contrat synthétique, emprise cadastrale et projet, prêts à générer."""

    def _preparer(origine=None, **options):
        dossier = tmp_path / "sortie" / "Essai"
        synthese.ecrire(
            dossier, **({"origine": origine} if origine else {}), **options
        )
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
            nom="Essai", commune="Sarnois", code_postal="60210",
            date="2026-09-04", emprise=str(emprise), libelle="Essai lot 4",
        )
        return projet, dossier

    return _preparer


def test_les_planches_dp4_suivent_les_ouvrages_du_projet(site):
    """Un ouvrage absent n'a pas de bloc, une planche vide n'existe pas."""
    _, dossier = site()
    contrat = charger_contrat(dossier)
    assert dp4_ouvrages.planches_necessaires(contrat) == ["DP 4-1", "DP 4-2"]
    assert dp4_ouvrages.ouvrages_de(contrat, "DP 4-1") == ["pdl_ptr"]
    assert dp4_ouvrages.ouvrages_de(contrat, "DP 4-3") == []


def test_une_planche_dp4_sans_ouvrage_leve(site, tmp_path):
    _, dossier = site()
    contrat = charger_contrat(dossier)
    projet = Projet(
        nom="Essai", commune="Sarnois", code_postal="60210", date="2026-09-04",
        emprise=str(tmp_path / "emprise.geojson"),
    )
    with pytest.raises(ErreurComposition, match="ne se produit pas vide"):
        dp4_ouvrages.generer(projet, contrat, tmp_path, "DP 4-3")


def test_le_rampant_se_mesure_sur_les_tables_du_plan(site):
    """Et non sur l'écart des deux hauteurs, qui bornent l'autorisation.

    Les deux hauteurs du tableau bilan sont un minimum garanti et un maximum
    autorisé, pas les deux bouts d'une table : les lire comme une géométrie
    donnait un rampant qui ne refermait ni le pas ni le nombre de modules.
    """
    _, dossier = site()
    contrat = charger_contrat(dossier)
    table, avertissements = dp3_coupes.geometrie_table(contrat)

    mesure = dp3_coupes.rampant_mesure(contrat, table.inclinaison_deg)
    assert mesure is not None
    assert table.rampant_m == pytest.approx(mesure)
    # Le point haut dessiné se déduit du rampant, et reste sous le maximum.
    assert table.point_haut_m == pytest.approx(
        table.point_bas_m + mesure * math.sin(math.radians(table.inclinaison_deg))
    )
    assert table.point_haut_max_m >= table.point_haut_m
    assert table.pas_m == pytest.approx(table.inter_table_m + table.projection_m, abs=0.5)
    assert avertissements == []


def test_une_table_qui_perce_le_gabarit_est_signalee(site):
    """Le maximum déclaré est un engagement : le dépasser doit se voir."""
    _, dossier = site()
    contrat = charger_contrat(dossier)
    contrat.donnees["parametres"]["structures"]["point_haut_m"] = 2.0
    _, avertissements = dp3_coupes.geometrie_table(contrat)
    assert any("gabarit" in message for message in avertissements)


def test_un_pas_incoherent_est_signale(site):
    """Un pas qui ne vaut pas l'inter-table plus la projection se dit."""
    _, dossier = site()
    contrat = charger_contrat(dossier)
    contrat.donnees["parametres"]["structures"]["pitch_m"] = 25.0
    _, avertissements = dp3_coupes.geometrie_table(contrat)
    assert any("Pas déclaré" in message for message in avertissements)


def test_une_inclinaison_impossible_leve(site):
    from dp_socle.erreurs import ErreurContrat

    _, dossier = site()
    contrat = charger_contrat(dossier)
    contrat.donnees["parametres"]["structures"]["inclinaison_deg"] = 0.0
    with pytest.raises(ErreurContrat, match="sens physique"):
        dp3_coupes.geometrie_table(contrat)


# ---------------------------------------------------------------------------
# Décision D1 — la substitution des hauteurs se voit
# ---------------------------------------------------------------------------


def test_un_dossier_helioscope_annonce_ses_hauteurs_substituees(site):
    """Critère de validation n°5.

    Un export HelioScope ne décrit pas la garde au sol de la structure, et son
    DXF est plat. La coupe est dessinée aux hauteurs standard, et le rapport
    doit le dire — sans quoi rien ne distingue une cote du projet d'une cote
    de catalogue.
    """
    _, dossier = site(origine=ORIGINE_HELIOSCOPE)
    contrat = charger_contrat(dossier)
    # Un contrat HelioScope ne porte pas les hauteurs du tableau bilan.
    contrat.donnees["parametres"]["structures"].pop("point_bas_m")
    contrat.donnees["parametres"]["structures"].pop("point_haut_m")
    contrat.donnees["standards_unite"] = {}

    table, avertissements = dp3_coupes.geometrie_table(contrat)
    assert table.point_bas_m == dp3_coupes.POINT_BAS_STANDARD_M
    assert any("point_bas_m" in m and "standard" in m for m in avertissements)
    assert any("point_haut_m" in m and "standard" in m for m in avertissements)


def test_le_z_plat_dun_dossier_helioscope_est_signale(site):
    """Les tables sont posées sur le profil RGE ALTI, et cela s'écrit."""
    _, dossier = site(origine=ORIGINE_HELIOSCOPE)
    contrat = charger_contrat(dossier)
    assert not contrat.z_reel("tables_pv")

    table, _ = dp3_coupes.geometrie_table(contrat)
    profil = [(a, z) for a, z in contrat.profil["points"]]

    class _DessinMuet:
        """Recueille les tracés sans planche : on ne mesure ici que le message."""

        def __init__(self):
            self.planche = None

        def ligne(self, *args, **kwargs):
            pass

        def metres(self, valeur):
            return valeur

    posees, messages = dp3_coupes._tables_sur_le_profil(
        _DessinMuet(), contrat, table, profil
    )
    assert any("RGE ALTI" in message for message in messages)
    assert any("hauteurs déclarées" in message for message in messages)


def test_un_contour_replie_sur_lui_meme_se_dessine_sans_planter():
    """La planche doit sortir même d'une géométrie que `make_valid` a recousue.

    Le plan d'Auzainvilliers porte un contour de citerne de refroidissement qui
    se replie sur lui-même ; `make_valid` en fait un `GeometryCollection`, dont
    `boundary` vaut None, et le tracé du filet s'arrêtait en `AttributeError`
    au milieu des DP 4 (27/09/2026). Le plan était fautif — l'import le disait,
    calque nommé — mais un dossier ne s'interrompt pas sur une trace Python :
    il se produit, et ce qui cloche se lit au rapport.
    """
    from shapely import make_valid
    from shapely.geometry import Polygon, box

    from dp_socle.planches.palette import STYLES

    planche = _planche_nue()
    planche.definir_echelle(500, centre_l93=(622_905.0, 6_750_705.0))
    recousue = make_valid(
        Polygon([
            (622_900, 6_750_700), (622_910, 6_750_700), (622_910, 6_750_710),
            (622_900, 6_750_710), (622_900, 6_750_700), (622_895, 6_750_700),
            (622_900, 6_750_700),
        ])
    )
    assert recousue.boundary is None

    tracee = dp4_ouvrages._tracer_decoupe(
        planche,
        recousue,
        STYLES["citerne_refroidissement"].style,
        box(622_890, 6_750_690, 622_920, 6_750_720),
    )
    assert tracee, "ni surface ni filet n'ont été tracés"
    assert "<path" in planche.svg()


# ---------------------------------------------------------------------------
# La végétation traversée : un peuplement, et non un sujet géant
# ---------------------------------------------------------------------------


class _DessinEspion:
    """Recueille houppiers et troncs, sans planche : on mesure ce qui est tracé."""

    def __init__(self):
        self.planche = None
        self.houppiers = []
        self.troncs = []

    def metres(self, valeur):
        return valeur

    def rectangle(self, x, y, largeur, hauteur, style=None):
        self.troncs.append((x, y, largeur, hauteur))

    def polyligne(self, points, style=None, fermer=False):
        self.houppiers.append([(float(x), float(y)) for x, y in points])


class _ContratDeVegetation:
    """Le strict nécessaire à `_vegetation_sur_le_profil` : des couches."""

    def __init__(self, **couches):
        self._couches = couches

    def geometries(self, categorie):
        return self._couches.get(categorie, [])


#: Une coupe de 200 m sur une pente de 2 %, dans le repère de la ligne.
_LIGNE_DE_COUPE = LineString([(0.0, 0.0), (200.0, 0.0)])
_PROFIL = [(float(x), 100.0 + 0.02 * x) for x in range(0, 201, 5)]


def _vegetation(**couches) -> _DessinEspion:
    dessin = _DessinEspion()
    dessin.messages = dp3_coupes._vegetation_sur_le_profil(
        dessin, _ContratDeVegetation(**couches), _PROFIL, _LIGNE_DE_COUPE
    )
    return dessin


def _largeur(houppier) -> float:
    return max(x for x, _ in houppier) - min(x for x, _ in houppier)


def test_une_zone_boisee_porte_autant_d_arbres_qu_elle_en_contient():
    """Une zone légendée « arbres existants » est un peuplement, pas un sujet.

    Elle se dessinait d'un seul houppier étiré sur toute sa largeur : un bois de
    120 m donnait un arbre unique de 120 m de large et de 8 m de haut, ce qu'un
    instructeur ne peut pas lire autrement que comme une erreur (signalé le
    26/09/2026 sur la coupe de Sarnois).
    """
    dessin = _vegetation(arbre_existant=[box(0.0, -10.0, 120.0, 10.0)])

    assert len(dessin.houppiers) == round(120.0 / LARGEUR_ARBRE_M)
    # Aucun sujet plus large qu'un arbre, recouvrement des couronnes compris.
    assert max(_largeur(h) for h in dessin.houppiers) == pytest.approx(
        LARGEUR_ARBRE_M * dp3_coupes.CHEVAUCHEMENT_COURONNES, abs=0.01
    )
    # Le peuplement couvre la zone d'un bout à l'autre, sans la déborder de
    # plus d'une demi-couronne.
    gauches = [min(x for x, _ in h) for h in dessin.houppiers]
    droites = [max(x for x, _ in h) for h in dessin.houppiers]
    assert min(gauches) == pytest.approx(0.0, abs=LARGEUR_ARBRE_M / 2.0)
    assert max(droites) == pytest.approx(120.0, abs=LARGEUR_ARBRE_M / 2.0)
    # Et aucun ne dépasse la hauteur conventionnelle annoncée au rapport : le
    # bloc de la planche est dimensionné sur elle.
    assert max(y for h in dessin.houppiers for _, y in h) <= max(
        altitude for _, altitude in _PROFIL
    ) + HAUTEUR_ARBRE_M
    assert any("autant qu'elle en contient" in message for message in dessin.messages)


def test_chaque_arbre_est_pose_sur_le_terrain_qui_le_porte():
    """Le houppier unique se posait sur l'altitude du milieu de la zone.

    Sur une pente de 2 %, un bois de 120 m voyait donc ses arbres de bout
    s'enterrer d'un mètre ou flotter d'autant.
    """
    dessin = _vegetation(arbre_existant=[box(0.0, -10.0, 120.0, 10.0)])

    for x_tronc, pied, largeur_tronc, _hauteur in dessin.troncs:
        centre = x_tronc + largeur_tronc / 2.0
        assert pied == pytest.approx(100.0 + 0.02 * centre, abs=0.05)


def test_un_sujet_isole_reste_un_arbre_entier():
    """La coupe effleure un bosquet d'un mètre : ce qui est là est un arbre.

    Sa couronne ne se réduit pas à la largeur traversée, sinon un arbre frôlé
    par la coupe se dessinerait comme un buisson.
    """
    dessin = _vegetation(arbre_existant=[box(60.0, -0.5, 61.0, 0.5)])

    assert len(dessin.houppiers) == 1
    assert _largeur(dessin.houppiers[0]) == pytest.approx(
        LARGEUR_ARBRE_M * dp3_coupes.CHEVAUCHEMENT_COURONNES, abs=0.01
    )


# ---------------------------------------------------------------------------
# Critères n°8 et n°9 — taille du dossier, numérotation et sommaire
# ---------------------------------------------------------------------------


@pytest.mark.reseau
def test_dossier_complet_numerote_et_sous_la_cible(site):
    """Critères de validation n°8 et n°9, sur le dossier assemblé.

    La numérotation est vérifiée deux fois : `assemblage` refuse un cartouche
    qui n'est pas à sa page, et le sommaire est relu ici pour que la page de
    garde annonce les mêmes numéros.
    """
    projet, dossier = site()
    rapport = generer_dossier(projet, dossier.parent, dpi=120)

    assert rapport.origine_contrat == "import_be"
    assert rapport.taille_mo < TAILLE_MAX_MO

    # La page de garde est dans `planches` sous un code à elle : le sommaire
    # la compte à part, et elle n'a pas de code de pièce.
    numeros = [s.numero for s in rapport.planches if s.numero.startswith("DP ")]
    assert numeros == ["DP 1-1", "DP 1-2", "DP 1-3", "DP 2", "DP 3", "DP 4-1", "DP 4-2"]

    produites = codes_produits(numeros)
    for entree in rapport.sommaire:
        if entree["numero"] == "—":
            assert entree["page"] == 1
            continue
        assert entree["page"] == numero_planche(entree["numero"], produites)

    from pypdf import PdfReader

    assert len(PdfReader(str(rapport.assemblage)).pages) == len(numeros) + 1


@pytest.mark.reseau
def test_les_echelles_declarees_sont_vraies_sur_dp3(site, tmp_path):
    """Critère n°1 sur la planche réelle : la cote de pas mesure le pas.

    Le cartouche porte l'échelle de la coupe des tables, et la ligne de cote
    du pas a exactement la longueur du pas à cette échelle. La retrouver dans
    le PDF vérifie l'échelle du cartouche sur le fichier produit.
    """
    projet, dossier = site()
    contrat = charger_contrat(dossier)
    sortie = dp3_coupes.generer(projet, contrat, tmp_path, numero="6")

    table, _ = dp3_coupes.geometrie_table(contrat)
    attendu_mm = table.pas_m * 1000.0 / sortie.details["echelle_tables"]

    horizontaux = [
        longueur(s) * MM_PAR_PT
        for s in segments(sortie.chemin)
        if abs(s[0][1] - s[1][1]) < 0.5 and abs(s[0][0] - s[1][0]) > 1.0
    ]
    assert any(
        abs(mesure - attendu_mm) / attendu_mm < ECART_ADMIS for mesure in horizontaux
    ), (
        f"aucun segment de {attendu_mm:.2f} mm dans le PDF pour un pas de "
        f"{table.pas_m} m au 1:{sortie.details['echelle_tables']} ; "
        f"mesures relevées : {sorted(round(m, 1) for m in horizontaux)[:12]}"
    )


@pytest.mark.reseau
def test_dp2_ne_porte_que_les_categories_dessinees(site, tmp_path):
    """Critère n°4 : la légende suit le projet, pas le contrat."""
    projet, dossier = site()
    from dp_socle.geometrie import charger_emprise
    from dp_socle.planches import dp2_plan_masse

    contrat = charger_contrat(dossier)
    sortie = dp2_plan_masse.generer(
        projet, contrat, charger_emprise(projet.chemin_emprise), tmp_path, numero="5"
    )
    dessinees = set(sortie.details["categories_dessinees"])
    assert "tables_pv" in dessinees
    # Le site synthétique ne porte ni BESS ni haie existante.
    assert "bess" not in dessinees
    assert "haie_existante" not in dessinees
    assert sortie.echelle in (500, 1000, 2000, 2500, 5000)


@pytest.mark.reseau
def test_deux_projets_differents_donnent_deux_legendes(site, tmp_path):
    """Critère n°4, énoncé sur ce qui le décide : les catégories présentes."""
    from dp_socle.planches.palette import construire_legende, objets_a_dessiner

    _, dossier_a = site()
    contrat_a = charger_contrat(dossier_a)
    legende_a = [e.libelle for e in construire_legende(
        [c for c, _ in objets_a_dessiner(contrat_a)]
    )]

    _, dossier_b = site()
    contrat_b = charger_contrat(dossier_b)
    # Un projet sans citerne ni haie : sa légende doit s'en trouver plus courte.
    del contrat_b.couches["bache_incendie"]
    del contrat_b.couches["haie"]
    legende_b = [e.libelle for e in construire_legende(
        [c for c, _ in objets_a_dessiner(contrat_b)]
    )]

    assert legende_a != legende_b
    assert "Citerne incendie" in legende_a
    assert "Citerne incendie" not in legende_b


@pytest.mark.reseau
def test_sans_contrat_le_dossier_sarrete_au_cadastre(site, tmp_path):
    """Un projet dont le plan n'est pas importé produit le socle, en le disant."""
    projet, dossier = site()
    (dossier / "projet.json").unlink()
    (dossier / "geometries.gpkg").unlink()

    rapport = generer_dossier(projet, dossier.parent, dpi=120)
    assert rapport.origine_contrat is None
    assert [s.numero for s in rapport.planches if s.numero.startswith("DP ")] == [
        "DP 1-1", "DP 1-2", "DP 1-3"
    ]
    assert any("Aucun plan importé" in m for m in rapport.avertissements)


# ---------------------------------------------------------------------------
# Mise en page : blanc tournant et sous-cadres
# ---------------------------------------------------------------------------


def test_le_blanc_tournant_est_le_meme_partout():
    """Une marge qui change d'un bloc à l'autre se remarque plus qu'elle ne sert."""
    from dp_socle.planches import dp3_coupes, dp4_ouvrages
    from dp_socle.planches.primitives import BLANC_TOURNANT_MM

    assert dp3_coupes.BLANC_TOURNANT_MM == BLANC_TOURNANT_MM
    assert dp4_ouvrages.BLANC_TOURNANT_MM == BLANC_TOURNANT_MM


def test_un_sous_cadre_laisse_une_marge_interieure():
    """Un texte collé au filet ne fait pas propre."""
    from dp_socle.planches.primitives import (
        MARGE_SOUS_CADRE_MM,
        zone_interieure,
    )

    x, y, largeur, hauteur = zone_interieure(10.0, 20.0, 100.0, 60.0)
    assert x == 10.0 + MARGE_SOUS_CADRE_MM
    assert largeur == 100.0 - 2 * MARGE_SOUS_CADRE_MM
    # Le titre prend sa place en haut ; le bas garde la marge.
    assert y > 20.0 + MARGE_SOUS_CADRE_MM
    assert y + hauteur == 20.0 + 60.0 - MARGE_SOUS_CADRE_MM


def test_les_ouvrages_etendus_ne_commandent_pas_le_cadrage(site):
    """Critère du zoom : la clôture ceint le site, elle ne le cadre pas.

    Sans cette règle, la planche des citernes revenait au plan de masse
    entier — 1:2 000 pour une citerne de 8 m — alors que sa voisine, qui décrit
    le poste, était au 1:300.
    """
    from dp_socle.planches.dp4_ouvrages import _zone_reperee
    from dp_socle.planches.primitives import union_valide

    _, dossier = site()
    contrat = charger_contrat(dossier)
    emprise = union_valide(contrat.geometries("cloture"))

    # La planche des citernes : clôture, portail et citerne.
    cadre, resserre = _zone_reperee(
        contrat, ("cloture", "portail", "bache_incendie"), emprise
    )
    assert resserre, "le cadrage aurait dû se resserrer sur la citerne"
    assert cadre.area < emprise.area

    # Une planche qui ne décrirait que la clôture se cadre sur le site.
    _, resserre_seul = _zone_reperee(contrat, ("cloture",), emprise)
    assert not resserre_seul


def test_aucune_planche_dp4_ne_revient_au_plan_entier(site):
    """Chaque planche zoome sur ce qu'elle décrit, y compris celle des citernes.

    C'est le point : une planche dont les ouvrages sont locaux ne doit pas
    revenir au plan de masse entier sous prétexte qu'elle porte aussi la
    clôture. Les deux cadrages ne sont pas forcément identiques — ils suivent
    les ouvrages de chaque planche — mais aucun ne rend le zoom inutile.
    """
    from dp_socle.planches.dp4_ouvrages import _zone_reperee
    from dp_socle.planches.primitives import union_valide

    _, dossier = site()
    contrat = charger_contrat(dossier)
    emprise = union_valide(contrat.geometries("cloture"))

    postes, _ = _zone_reperee(contrat, ("pdl_ptr",), emprise)
    citernes, _ = _zone_reperee(
        contrat, ("cloture", "portail", "bache_incendie"), emprise
    )
    for cadre in (postes, citernes):
        assert cadre.area < 0.25 * emprise.area


def test_le_vide_se_partage_a_parts_egales_entre_les_cadres():
    """Caler le premier cadre sur son contenu laissait le second à moitié vide.

    Deux cadres qui demandent 40 et 10 mm dans une colonne de 100 mm doivent
    ressortir à 63 et 33 : les 46 mm qui restent une fois retirés leurs besoins
    et le blanc tournant qui les sépare vont pour moitié à chacun.
    """
    from dp_socle.planches.primitives import (
        BLANC_TOURNANT_MM,
        repartir_hauteurs,
    )

    hauteurs = repartir_hauteurs([40.0, 10.0], 100.0)
    assert hauteurs == pytest.approx([63.0, 33.0])
    vides = [hauteur - besoin for hauteur, besoin in zip(hauteurs, [40.0, 10.0])]
    assert vides[0] == pytest.approx(vides[1])
    # La colonne remplit sa page : rien ne reste en bas.
    assert sum(hauteurs) + BLANC_TOURNANT_MM == pytest.approx(100.0)


def test_le_vide_ne_se_partage_pas_quand_il_n_y_en_a_pas():
    """Faire tenir la colonne est le travail de l'échelle, pas de la marge.

    Rogner ici les cadres pour les faire entrer serait un repli silencieux :
    les besoins sont rendus tels quels, et le débordement se voit.
    """
    from dp_socle.planches.primitives import repartir_hauteurs

    assert repartir_hauteurs([80.0, 60.0], 100.0) == [80.0, 60.0]


@pytest.fixture
def parcellaire_double(monkeypatch):
    """Le parcellaire du plan de repérage, sans interroger la Géoplateforme.

    Ce test-là sortait pour de vrai. Il passait hors ligne parce que
    `_parcelles_du_cadre` rattrape une panne du service et produit la planche
    sans fond cadastral : le défaut de mesure était donc invisible, et le vert
    dépendait de la Géoplateforme. Relevé le 29/09/2026 par la coupure des
    sockets, voir `tests/sans_reseau.py`.

    C'est la référence de `dp4_ouvrages` qu'on remplace, et non l'attribut du
    module `ign` : le module écrit `from ..ign import telecharger_parcelles`,
    et le nom est lié à l'import.
    """
    monkeypatch.setattr(dp4_ouvrages, "telecharger_parcelles", lambda *a, **k: [])


def test_la_legende_cede_le_coin_quand_le_plan_l_occupe():
    """Une planche qui cache une partie de ce qu'elle montre est fausse.

    Relevé le 30/09/2026 sur Auzainvilliers : le bloc de légende se posait
    toujours en haut à gauche, et le site y passait dessous — le cadre blanc
    couvrait une piste et une plateforme.

    Ce qui est mesuré ici : la légende **garde** son coin quand il est libre,
    et n'en change que s'il est occupé. Une planche où elle ne gênait pas ne
    doit pas changer d'allure.
    """
    from shapely.geometry import box

    from dp_socle.planche import Planche
    from dp_socle.planches.dp2_plan_masse import _coin_de_legende

    planche = Planche(titre="T", numero="T", projet="T", date="30/09/2026")
    planche.definir_echelle(1000, centre_l93=(700000.0, 6900000.0))
    zone = planche.zone_dessin()
    haut_gauche = (zone[0] + 3.0, zone[1] + 3.0)

    # Rien de dessiné au coin habituel : la légende y reste.
    minx, miny, maxx, maxy = planche.emprise_terrain()
    au_sud_est = box((minx + maxx) / 2, miny, maxx, (miny + maxy) / 2)
    assert _coin_de_legende(
        planche, zone, [("tables_pv", [au_sud_est])], 70.0, 40.0
    ) == haut_gauche

    # Le dessin occupe le coin habituel : elle en change.
    au_nord_ouest = box(minx, (miny + maxy) / 2, (minx + maxx) / 2, maxy)
    autre = _coin_de_legende(
        planche, zone, [("tables_pv", [au_nord_ouest])], 70.0, 40.0
    )
    assert autre != haut_gauche
    assert zone[0] <= autre[0] and zone[1] <= autre[1]


def test_le_plan_de_reperage_ne_descend_pas_sous_le_1_300(
    site, tmp_path, parcellaire_double
):
    """Retour de relecture : au 1:200 le zoom colle aux ouvrages.

    À cette échelle le cadre serre les ouvrages de si près qu'on ne les situe
    plus dans le site, et le plan de repérage ne repère plus rien.
    """
    from dp_socle.planches.dp4_ouvrages import ECHELLES_REPERAGE

    assert min(ECHELLES_REPERAGE) == 300

    projet, dossier = site()
    contrat = charger_contrat(dossier)
    for code in dp4_ouvrages.planches_necessaires(contrat):
        sortie = dp4_ouvrages.generer(projet, contrat, tmp_path, code)
        assert sortie.details["echelle_reperage"] >= 300, code


def test_seuls_les_ouvrages_a_facade_ont_une_planche():
    """La liste arrêtée à la relecture du 04/09/2026.

    L'aire d'aspiration est un revêtement de sol, le bac de rétention une
    cuvette : ni l'un ni l'autre n'a de façade à montrer. Ils restent tracés
    sur le plan de masse et sur le plan de repérage.
    """
    portes = {c for ouvrages in dp4_ouvrages.REPARTITION.values() for c in ouvrages}
    assert portes == {
        "pdl_ptr", "ptr", "pdl",
        "cloture", "portail",
        "bache_incendie", "citerne_refroidissement",
        "local_technique", "bess",
    }


# ---------------------------------------------------------------------------
# Ce sur quoi le plan de masse se cadre (décision du 02/10/2026)
# ---------------------------------------------------------------------------


def test_le_plan_de_masse_se_cadre_sur_la_zone_cloturee():
    """L'emprise cadastrale dit ce qui est maîtrisé, pas ce qu'il faut montrer.

    Relevé sur Boisné-La Tude : le plan de masse sortait au 1:5 000, le site
    perdu au milieu de deux kilomètres de parcellaire, parce que l'emprise
    déposée faisait plusieurs fois le projet. Saint-Cyr-en-Val, dont l'emprise
    épouse la clôture à 1 % près, sortait au 1:2 000 — bien lisible.

    Décision du chef de projet : le cadre suit la **zone clôturée**. Les deux
    cas sont mesurés ici, et le troisième aussi : sans clôture au contrat,
    l'emprise reprend son rôle, faute d'autre étendue.
    """
    from shapely.geometry import box

    from dp_socle.echelle import echelle_adaptative
    from dp_socle.planche import Planche
    from dp_socle.planches.dp2_plan_masse import (
        ECHELLES_PLAN_MASSE,
        MARGE,
        _ce_que_la_planche_cadre,
    )

    class _Contrat:
        def __init__(self, cloture):
            self._cloture = cloture

        def geometries(self, categorie):
            return self._cloture if categorie == "cloture" else []

    class _Emprise:
        def __init__(self, geometrie):
            minx, miny, maxx, maxy = geometrie.bounds
            self.geometrie = geometrie
            self.dimensions_m = (maxx - minx, maxy - miny)
            self.centre = ((minx + maxx) / 2.0, (miny + maxy) / 2.0)

    zone = Planche(
        titre="T", numero="DP 2", projet="T", date="02/10/2026"
    ).zone_dessin()

    def echelle(dimensions):
        return echelle_adaptative(
            *dimensions, zone, marge=MARGE, valeurs=ECHELLES_PLAN_MASSE
        )

    cloture = box(0.0, 0.0, 250.0, 350.0)
    large = _Emprise(box(-400.0, -300.0, 650.0, 750.0))  # douze fois la clôture

    quoi, dimensions, centre = _ce_que_la_planche_cadre(_Contrat([cloture]), large)
    assert quoi == "cloture"
    assert dimensions == pytest.approx((250.0, 350.0))
    assert centre == pytest.approx((125.0, 175.0))
    # Le site devient lisible : 1:2 000 au lieu du 1:5 000 de l'emprise.
    assert echelle(dimensions) == 2000
    assert echelle(large.dimensions_m) == 5000

    # Quand l'emprise épouse la clôture, rien ne change : c'est le cas de
    # Saint-Cyr-en-Val, et l'échelle y était déjà la bonne.
    serree = _Emprise(box(0.0, 0.0, 250.0, 350.0))
    _, dimensions_serrees, _ = _ce_que_la_planche_cadre(_Contrat([cloture]), serree)
    assert echelle(dimensions_serrees) == echelle(serree.dimensions_m) == 2000

    # Sans clôture au contrat, l'emprise reprend son rôle.
    quoi, dimensions, centre = _ce_que_la_planche_cadre(_Contrat([]), large)
    assert quoi == "emprise"
    assert dimensions == pytest.approx(large.dimensions_m)


# ---------------------------------------------------------------------------
# Un site long garde sa coupe du terrain (05/10/2026)
# ---------------------------------------------------------------------------


def test_une_coupe_de_site_long_trouve_une_echelle():
    """Saint-Aubin-sur-Loire : le dossier sortait sans DP 3, et presque sans le dire.

    Sa coupe A-A' traverse 493 m de terrain. Les échelles de la coupe du
    terrain s'arrêtaient au 1:1000, soit 493 mm pour une zone de dessin de
    362 mm : `echelle_du_dessin` levait, la génération rattrapait la pièce une à
    une — « DP 3 n'est pas produite : … » — et le `.pptx` partait sans sa coupe,
    le message perdu au milieu des points à savoir.

    Mesuré à la correction : la planche sort désormais, terrain au 1:1500.
    """
    from dp_socle.erreurs import ErreurEchelle
    from dp_socle.planches.dp3_coupes import ECHELLES_TERRAIN
    from dp_socle.planches.primitives import echelle_du_dessin

    # La zone de dessin de la coupe du terrain, telle que mesurée sur la
    # planche de Saint-Aubin le 05/10/2026.
    zone = (0.0, 0.0, 362.0, 74.4)

    denominateur = echelle_du_dessin(493.0, 6.0, zone, ECHELLES_TERRAIN,
                                     libelle="coupe du terrain")
    assert denominateur == 1500

    # L'ancienne liste ne pouvait pas : c'est elle qui faisait disparaître la
    # pièce, et le test le tient pour que personne ne la restreigne sans voir.
    with pytest.raises(ErreurEchelle, match="coupe du terrain"):
        echelle_du_dessin(493.0, 6.0, zone, (200, 250, 300, 500, 750, 1000),
                          libelle="coupe du terrain")

    # Et de la marge au-delà : 700 m est l'ordre de grandeur du plus long site
    # de 3 MWc, et il doit tenir sans que la pièce disparaisse.
    assert echelle_du_dessin(700.0, 10.0, zone, ECHELLES_TERRAIN,
                             libelle="coupe du terrain") == 2000
