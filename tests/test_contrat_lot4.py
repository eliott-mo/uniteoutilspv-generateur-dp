"""Lecture du contrat d'entrée du lot 4.

Ce qui se joue ici est ce que le lot 4 refuse : une version de contrat qu'il ne
sait pas lire, une couche `voirie` dont personne n'a tranché le type, une cote
d'ouvrage absente ou ambiguë. Chacun de ces refus vaut mieux qu'une planche
présentable et fausse, et aucun ne peut se vérifier sur le dessin.
"""

from __future__ import annotations

import json

import pytest
from shapely.geometry import Polygon

from dp_socle.contrat import (
    TOLERANCE_VARIANTE,
    Cote,
    charger_contrat,
    decoder_cote,
)
from dp_socle.erreurs import (
    ErreurContrat,
    ErreurCoteOuvrage,
    ErreurImportBE,
    ErreurVoirieIndecise,
)
from dp_socle.import_be import ORIGINE_HELIOSCOPE, VERSION_CONTRAT

from . import contrat_synthetique as synthese


# ---------------------------------------------------------------------------
# Décodage des cotes normalisées
# ---------------------------------------------------------------------------


def test_ordre_cotes_donne_le_sens_des_nombres():
    """« largeur x longueur » et « longueur x largeur » ne se lisent pas pareil."""
    ptr = decoder_cote(
        {
            "ouvrage": "Poste de transformation - PTR",
            "dimensions": "10 x 3 x 3m",
            "ordre_cotes": "largeur x longueur x hauteur",
        }
    )
    assert ptr.largeur_m == 10.0
    assert ptr.longueur_m == 3.0

    pdl_ptr = decoder_cote(
        {
            "ouvrage": "Poste de livraison et de transformation - PDL/PTR",
            "dimensions": "12 x 3 x 3m",
            "ordre_cotes": "longueur x largeur x hauteur",
        }
    )
    assert pdl_ptr.longueur_m == 12.0
    assert pdl_ptr.largeur_m == 3.0


def test_inverser_lordre_des_cotes_change_le_poste_dessine():
    """Critère de validation n°7 : l'inversion volontaire doit se voir.

    Un poste de 12 x 3 m dessiné 3 x 12 se dessine parfaitement et ne se
    remarque pas à la relecture. Ce test est là pour que le jour où quelqu'un
    câblerait la position au lieu de lire `ordre_cotes`, quelque chose casse.
    """
    juste = decoder_cote(
        {
            "ouvrage": "PDL/PTR",
            "dimensions": "12 x 3 x 3m",
            "ordre_cotes": "longueur x largeur x hauteur",
        }
    )
    inverse = decoder_cote(
        {
            "ouvrage": "PDL/PTR",
            "dimensions": "12 x 3 x 3m",
            "ordre_cotes": "largeur x longueur x hauteur",
        }
    )
    assert juste.longueur_m != inverse.longueur_m
    assert (juste.longueur_m, juste.largeur_m) == (inverse.largeur_m, inverse.longueur_m)


@pytest.mark.parametrize(
    "dimensions, attendu",
    [
        ("12 x 3 x 3m", (12.0, 3.0, 3.0)),
        ("11,7 x 9,3 x 1 m", (11.7, 9.3, 1.0)),
        ("1 conteneur 20 pieds 6 x 3 x 3m", (6.0, 3.0, 3.0)),
        ("2 conteneurs 40 pieds 12 x 3 x 3m", (12.0, 3.0, 3.0)),
    ],
)
def test_dimensions_lues_malgre_le_prefixe(dimensions, attendu):
    """Le libellé du catalogue préfixe parfois les cotes ; elles restent lues."""
    cote = decoder_cote(
        {
            "ouvrage": "essai",
            "dimensions": dimensions,
            "ordre_cotes": "longueur x largeur x hauteur",
        }
    )
    assert (cote.longueur_m, cote.largeur_m, cote.hauteur_m) == attendu


def test_cote_sans_hauteur_leve_plutot_que_de_la_deviner():
    """Le GeoPackage donne une emprise au sol, jamais une hauteur."""
    aire = decoder_cote(
        {
            "ouvrage": "Aire d'aspiration",
            "dimensions": "8 x 4 m",
            "ordre_cotes": "longueur x largeur",
        }
    )
    assert not aire.a_hauteur
    with pytest.raises(ErreurCoteOuvrage, match="hauteur"):
        _ = aire.hauteur_m


def test_nombre_de_cotes_incoherent_avec_lordre_leve():
    with pytest.raises(ErreurCoteOuvrage, match="dimensions"):
        decoder_cote(
            {
                "ouvrage": "essai",
                "dimensions": "12 x 3 m",
                "ordre_cotes": "longueur x largeur x hauteur",
            }
        )


def test_cote_illisible_leve():
    with pytest.raises(ErreurCoteOuvrage, match="illisible"):
        decoder_cote(
            {"ouvrage": "essai", "dimensions": "environ 12 mètres",
             "ordre_cotes": "longueur"}
        )


# ---------------------------------------------------------------------------
# Chargement du contrat
# ---------------------------------------------------------------------------


def test_contrat_synthetique_se_lit(tmp_path):
    site = synthese.ecrire(tmp_path)
    contrat = charger_contrat(site.dossier)

    assert contrat.version == VERSION_CONTRAT
    assert not contrat.helioscope
    assert contrat.presente("tables_pv")
    assert not contrat.presente("bess")
    assert contrat.z_reel("tables_pv")
    assert contrat.profil is not None
    assert len(contrat.geometries("tables_pv")) == 6


def test_origine_helioscope_reconnue_et_z_non_reel(tmp_path):
    site = synthese.ecrire(tmp_path, origine=ORIGINE_HELIOSCOPE, avec_profil=False)
    contrat = charger_contrat(site.dossier)

    assert contrat.helioscope
    assert not contrat.z_reel("tables_pv")
    assert contrat.profil is None


def test_contrat_absent_leve(tmp_path):
    with pytest.raises(ErreurContrat, match="Aucun contrat"):
        charger_contrat(tmp_path)


def test_geopackage_absent_leve(tmp_path):
    site = synthese.ecrire(tmp_path)
    site.gpkg.unlink()
    with pytest.raises(ErreurContrat, match="incomplet"):
        charger_contrat(tmp_path)


def test_version_de_contrat_superieure_refusee(tmp_path):
    """Refuser plutôt que lire à moitié une sortie plus récente que l'outil."""
    site = synthese.ecrire(tmp_path)
    donnees = json.loads(site.parametres.read_text(encoding="utf-8"))
    donnees["version_contrat"] = VERSION_CONTRAT + 1
    site.parametres.write_text(
        json.dumps(donnees, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(ErreurImportBE, match="version"):
        charger_contrat(tmp_path)


# ---------------------------------------------------------------------------
# Décision D5 : la voirie bloque, elle ne se devine pas
# ---------------------------------------------------------------------------


def test_voirie_peuplee_bloque(tmp_path):
    """Critère de validation n°6."""
    synthese.ecrire(tmp_path, avec_voirie=True)
    with pytest.raises(ErreurVoirieIndecise, match="voie lourde ou de piste"):
        charger_contrat(tmp_path)


def test_voirie_tranchee_passe(tmp_path):
    """Une chaîne vaut pour toute la couche, et se déplie en un choix par objet."""
    synthese.ecrire(tmp_path, avec_voirie=True)
    contrat = charger_contrat(tmp_path, voirie="piste_legere")
    assert contrat.voirie == ["piste_legere"]
    assert contrat.voiries_de("piste_legere") == contrat.geometries("voirie")
    assert contrat.voiries_de("piste_lourde") == []


def test_la_voirie_se_tranche_objet_par_objet(tmp_path):
    """Un projet a presque toujours de la voie lourde ET de la piste légère.

    Le calque du bureau d'études les mélange sans les nommer : le tri se fait
    donc objet par objet, et non d'un seul choix pour toute la couche.
    """
    synthese.ecrire(tmp_path, avec_voirie=True)
    nombre = len(charger_contrat(tmp_path, voirie="piste_legere").geometries("voirie"))
    choix = ["piste_lourde"] + ["piste_legere"] * (nombre - 1)

    contrat = charger_contrat(tmp_path, voirie=choix)
    assert len(contrat.voiries_de("piste_lourde")) == 1
    assert len(contrat.voiries_de("piste_legere")) == nombre - 1


def test_un_choix_par_objet_et_pas_un_de_moins(tmp_path):
    """Le plan a changé depuis le tri : mieux vaut refuser que décaler."""
    synthese.ecrire(tmp_path, avec_voirie=True)
    with pytest.raises(ErreurVoirieIndecise, match="objet par objet"):
        charger_contrat(tmp_path, voirie=["piste_lourde", "piste_legere"])


def test_voirie_absente_ne_demande_rien(tmp_path):
    synthese.ecrire(tmp_path, avec_voirie=False)
    assert charger_contrat(tmp_path).voirie is None


def test_type_de_voirie_inconnu_refuse(tmp_path):
    synthese.ecrire(tmp_path, avec_voirie=True)
    with pytest.raises(ErreurVoirieIndecise, match="inconnu"):
        charger_contrat(tmp_path, voirie="piste_moyenne")


# ---------------------------------------------------------------------------
# Appariement des cotes aux catégories
# ---------------------------------------------------------------------------


def test_cote_de_categorie_apparie_sur_le_libelle(tmp_path):
    contrat = charger_contrat(synthese.ecrire(tmp_path).dossier)
    cote = contrat.cote_de_categorie("pdl_ptr")
    assert cote.longueur_m == synthese.POSTE_LONGUEUR_M
    assert cote.largeur_m == synthese.POSTE_LARGEUR_M


def test_famille_a_variantes_departagee_par_la_surface(tmp_path):
    """Quatre volumes de citerne incendie : c'est la surface qui tranche."""
    contrat = charger_contrat(synthese.ecrire(tmp_path).dossier)
    cote = contrat.cote_de_categorie("bache_incendie", surface_m2=11.7 * 9.3)
    assert cote.ouvrage.endswith("120")


def test_famille_a_variantes_sans_surface_leve(tmp_path):
    contrat = charger_contrat(synthese.ecrire(tmp_path).dossier)
    with pytest.raises(ErreurCoteOuvrage, match="variantes"):
        contrat.cote_de_categorie("bache_incendie")


def test_surface_qui_ne_correspond_a_aucune_variante_leve(tmp_path):
    contrat = charger_contrat(synthese.ecrire(tmp_path).dossier)
    with pytest.raises(ErreurCoteOuvrage, match="aucune"):
        contrat.cote_de_categorie("bache_incendie", surface_m2=500.0)


def test_categorie_sans_cote_au_contrat_leve(tmp_path):
    """Un ouvrage dessiné sans cote normalisée n'est pas dimensionné au plan."""
    contrat = charger_contrat(synthese.ecrire(tmp_path).dossier)
    with pytest.raises(ErreurCoteOuvrage, match="aucune de ses cotes"):
        contrat.cote_de_categorie("bess")


def test_tolerance_de_variante_reste_loin_des_variantes_voisines():
    """La tolérance sépare les variantes du catalogue au lieu de les confondre.

    Les deux citernes les plus proches font 60 et 104 m² : la tolérance de
    15 % ne peut pas les faire se recouvrir. Le vérifier ici évite de
    l'élargir un jour sans mesurer ce qu'on y perd.
    """
    petite, grande = 60.0, 104.0
    assert petite * (1 + TOLERANCE_VARIANTE) < grande * (1 - TOLERANCE_VARIANTE)


# ---------------------------------------------------------------------------
# Décision D6 : make_valid avant toute union
# ---------------------------------------------------------------------------


def test_polygone_auto_intersectant_ne_fait_pas_echouer_lunion(tmp_path):
    """Le calque « ESPACE VERT » de Sarnois portait un nœud papillon.

    Il faisait échouer `unary_union` au lot 2bis. `make_valid` est appliqué
    systématiquement, pas seulement là où ça a déjà planté.
    """
    from dp_socle.import_be import EntiteBE, ecrire_geopackage, ecrire_parametres

    x0, y0 = synthese.ORIGINE_L93
    papillon = Polygon(
        [(x0, y0), (x0 + 10, y0 + 10), (x0 + 10, y0), (x0, y0 + 10)]
    )
    assert not papillon.is_valid

    ecrire_geopackage(
        [
            EntiteBE(
                categorie="espace_vert", calque="ESPACE VERT",
                geometrie=papillon, z_reel=False,
            )
        ],
        tmp_path,
        synthese.ligne_coupe(),
    )
    ecrire_parametres(synthese.parametres(), tmp_path)

    contrat = charger_contrat(tmp_path)
    union = contrat.union("espace_vert")
    assert union is not None and union.is_valid and union.area > 0


def test_cote_est_immuable():
    """Une cote se lit, elle ne se corrige pas en cours de dessin."""
    cote = Cote("essai", "12 x 3 m", "longueur x largeur", None, None, {})
    with pytest.raises(Exception):
        cote.ouvrage = "autre"


# ---------------------------------------------------------------------------
# Emprise au sol des postes
# ---------------------------------------------------------------------------


def test_un_poste_dessine_en_plusieurs_bandes_devient_une_emprise(tmp_path):
    """Le calque `UNI_PDL` de Saint-Cyr porte trois bandes mal alignées en bout.

    Elles totalisent bien la surface déclarée au tableau bilan : ce n'est pas
    un objet de trop, c'est un tracé approximatif. Le rectangle minimal de leur
    union est l'emprise du poste, et il vaut la surface déclarée.
    """
    import math

    from shapely.geometry import Polygon

    from dp_socle.import_be import EntiteBE, ecrire_geopackage, ecrire_parametres
    from dp_socle.planches.palette import emprise_de_poste

    x0, y0 = synthese.ORIGINE_L93
    angle = math.radians(20.0)

    def bande(decalage, largeur, biais):
        """Bande de 12 m de long, posée à `decalage`, légèrement désalignée."""
        coins = []
        for long, trav in ((0, 0), (12.0 + biais, 0), (12.0 + biais, largeur), (0, largeur)):
            coins.append(
                (
                    x0 + long * math.cos(angle) - (trav + decalage) * math.sin(angle),
                    y0 + long * math.sin(angle) + (trav + decalage) * math.cos(angle),
                )
            )
        return Polygon(coins)

    bandes = [bande(0.0, 3.0, 0.0), bande(3.0, 1.5, -0.1), bande(4.5, 1.0, -0.15)]
    ecrire_geopackage(
        [
            EntiteBE(categorie="pdl_ptr", calque="UNI_PDL", geometrie=g, z_reel=False)
            for g in bandes
        ],
        tmp_path,
        synthese.ligne_coupe(),
    )
    donnees = synthese.parametres()
    donnees["parametres"]["postes"]["surface_pdl_ptr_m2"] = sum(g.area for g in bandes)
    ecrire_parametres(donnees, tmp_path)

    contrat = charger_contrat(tmp_path)
    assert len(contrat.geometries("pdl_ptr")) == 3

    avertissements = []
    emprise, abords = emprise_de_poste(contrat, "pdl_ptr", avertissements)

    # La première bande a les cotes du catalogue : c'est le poste, et les deux
    # autres sont la terre remise autour de lui.
    assert len(emprise) == 1
    assert emprise[0].area == pytest.approx(12.0 * 3.0, rel=1e-3)
    assert len(abords) == 2
    assert any("terre remise" in m for m in avertissements)


def test_une_emprise_de_poste_non_rectangulaire_reste_telle_quelle(tmp_path):
    """Redresser autre chose qu'un rectangle inventerait une forme."""
    from shapely.geometry import Polygon

    from dp_socle.import_be import EntiteBE, ecrire_geopackage, ecrire_parametres
    from dp_socle.planches.palette import emprise_de_poste

    x0, y0 = synthese.ORIGINE_L93
    triangle = Polygon([(x0, y0), (x0 + 12, y0), (x0, y0 + 6)])
    ecrire_geopackage(
        [EntiteBE(categorie="pdl_ptr", calque="UNI_PDL", geometrie=triangle,
                  z_reel=False)],
        tmp_path,
        synthese.ligne_coupe(),
    )
    ecrire_parametres(synthese.parametres(), tmp_path)

    contrat = charger_contrat(tmp_path)
    emprise, abords = emprise_de_poste(contrat, "pdl_ptr", [])
    assert len(emprise) == 1
    assert emprise[0].area == pytest.approx(triangle.area)
    assert abords == []


def test_un_ecart_de_surface_avec_le_tableau_est_signale(tmp_path):
    """30 m² dessinés pour 36 déclarés : la planche montre le plan, et le dit."""
    from dp_socle.planches.palette import emprise_de_poste

    synthese.ecrire(tmp_path)
    contrat = charger_contrat(tmp_path)
    contrat.donnees["parametres"]["postes"]["surface_pdl_ptr_m2"] = 90.0
    avertissements = []
    emprise_de_poste(contrat, "pdl_ptr", avertissements)
    assert any("déclarés au tableau bilan" in m for m in avertissements)
