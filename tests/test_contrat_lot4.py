"""Lecture du contrat d'entrée du lot 4.

Ce qui se joue ici est ce que le lot 4 refuse : une version de contrat qu'il ne
sait pas lire, une couche `voirie` dont personne n'a tranché le type, une cote
d'ouvrage absente ou ambiguë. Chacun de ces refus vaut mieux qu'une planche
présentable et fausse, et aucun ne peut se vérifier sur le dessin.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from shapely.geometry import Polygon

from dp_socle.contrat import (
    TOLERANCE_VARIANTE,
    Cote,
    archiver_le_contrat,
    charger_contrat,
    decoder_cote,
)
from dp_socle.erreurs import (
    ErreurContrat,
    ErreurDP,
    ErreurCoteOuvrage,
    ErreurImportBE,
    ErreurVoirieIndecise,
)
from dp_socle.import_be import (
    ORIGINE_HELIOSCOPE,
    ORIGINE_IMPORT_BE,
    VERSION_CONTRAT,
)

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


def _projet_trie(tmp_path, voirie):
    """Un `projet.json` minimal portant un tri de voirie, prêt à valider."""
    from dp_socle.projet import Projet

    emprise = tmp_path / "emprise.geojson"
    emprise.write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    return Projet(
        nom="essai",
        commune="Sarnois",
        code_postal="60210",
        date="2026-09-19",
        emprise=str(emprise),
        voirie=voirie,
    )


def test_un_objet_sans_objet_ne_bloque_pas_la_generation(tmp_path):
    """Régression du 19/09/2026 : trié à l'écran, refusé à la génération.

    « sans objet » était arrivé dans `decrire_voiries` sans arriver dans
    `Projet.valider`, qui construisait sa propre liste. Le chef de projet
    tranchait ses voiries, l'import passait, puis la génération levait
    « voirie = sans_objet inconnu dans projet.json ».
    """
    from dp_socle.contrat import VOIRIE_SANS_OBJET

    _projet_trie(tmp_path, ["piste_legere", VOIRIE_SANS_OBJET]).valider()
    _projet_trie(tmp_path, VOIRIE_SANS_OBJET).valider()


def test_le_contrat_et_le_projet_admettent_les_memes_types_de_voirie(tmp_path):
    """Les deux validations lisent le même ensemble, et rien ne s'y ajoute seul.

    C'est ce contrôle qui manquait : deux listes construites séparément peuvent
    diverger d'un commit, et la divergence ne se voit qu'à la génération d'un
    dossier réel.
    """
    from dp_socle.contrat import VOIRIES_DU_CONTRAT

    synthese.ecrire(tmp_path / "contrat", avec_voirie=True)
    for type_de_voirie in VOIRIES_DU_CONTRAT:
        # Admis du côté du contrat…
        charger_contrat(tmp_path / "contrat", voirie=type_de_voirie)
        # … et du côté du projet.
        _projet_trie(tmp_path, type_de_voirie).valider()

    with pytest.raises(ErreurVoirieIndecise, match="inconnu"):
        charger_contrat(tmp_path / "contrat", voirie="piste_moyenne")
    with pytest.raises(ErreurDP, match="inconnu"):
        _projet_trie(tmp_path, "piste_moyenne").valider()


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


def _contrat_avec_calque(
    dossier, categorie: str, objets, cotes=(), autres=None, postes=None
):
    """Le site synthétique, dont le calque `categorie` porte `objets`.

    `autres` ajoute des calques, `{catégorie: géométries}` ; `postes` remplace
    des lignes du tableau bilan.
    """
    from dp_socle.import_be import EntiteBE, ecrire_geopackage, ecrire_parametres

    calques = {categorie: list(objets), **(autres or {})}
    lot = [e for e in synthese.entites() if e.categorie not in calques] + [
        EntiteBE(categorie=nom, calque="SYNTHESE", geometrie=g, z_reel=False)
        for nom, geometries in calques.items()
        for g in geometries
    ]
    ecrire_geopackage(lot, dossier, synthese.ligne_coupe())
    donnees = synthese.parametres()
    donnees["cotes_normalisees"] = synthese.COTES + list(cotes)
    donnees["parametres"]["postes"].update(postes or {})
    ecrire_parametres(donnees, dossier)
    return charger_contrat(dossier)


def test_chaque_objet_aux_cotes_du_catalogue_est_un_poste(tmp_path):
    """Deux PTR de 10 x 3 m dans un calque : deux postes, et non un poste et du sol.

    Mesuré le 07/11/2026 à Auzainvilliers, le calque 0 apparié au PTR : le
    calque porte le PTR principal, dessiné deux fois à l'identique, et celui
    des batteries. La palette ne gardait que le plus grand des objets aux cotes
    du catalogue — à aire égale, le premier venu — et rendait les autres au
    sol, sous le nom de terre remise : l'un des deux postes passait en gris.
    """
    from shapely.geometry import box

    from dp_socle.planches.palette import objets_a_dessiner

    x0, y0 = synthese.ORIGINE_L93
    principal = box(x0 + 20, y0 + 85, x0 + 30, y0 + 88)
    batteries = box(x0 + 40, y0 + 85, x0 + 50, y0 + 88)
    terre = box(x0 + 18, y0 + 83, x0 + 32, y0 + 90)
    contrat = _contrat_avec_calque(
        tmp_path, "ptr", [terre, principal, batteries, box(*principal.bounds)]
    )

    messages = []
    objets = dict(objets_a_dessiner(contrat, messages))

    postes = objets["ptr"]
    assert len(postes) == 2
    assert {round(g.centroid.x - x0) for g in postes} == {25, 45}
    # La terre remise rejoint la plateforme. La copie du poste, elle, ne se
    # dessine nulle part : c'est le poste, déjà dessiné.
    sol = objets["plateforme"]
    assert any(g.equals(terre) for g in sol)
    assert not any(g.equals(principal) for g in sol)

    # Le rapport sépare les postes de la terre remise, et compte la copie.
    message = next(m for m in messages if m.startswith("« ptr » : les 2 postes"))
    assert "10.00 x 3.00 m" in message
    assert "l'un d'eux deux fois à l'identique" in message
    assert "Les 1 autre(s) objet(s) du calque, 98.0 m² au total, sont la terre" in message


def test_la_surface_declaree_se_lit_sur_les_postes_ou_sur_le_calque(tmp_path):
    """Deux tableaux, deux lectures de « Surface des PDL/PTR (m²) », toutes deux justes.

    Auzainvilliers V3 déclare 36 m² pour son PDL/PTR de 12 x 3 m : la surface du
    poste. Saint-Cyr V6 en déclare 66 pour le même poste flanqué de deux bandes
    de 18 et 12 m² : l'union du calque. Le contrôle ne lisait que la seconde, et
    disait à Auzainvilliers « 132.4 m² dessinés au plan pour 36.0 m²
    déclarés » d'un poste dessiné au centimètre (relevé le 07/11/2026).
    """
    from shapely.geometry import box

    from dp_socle.planches.palette import emprise_de_poste

    x0, y0 = synthese.ORIGINE_L93
    poste = box(x0 + 170, y0 + 8, x0 + 182, y0 + 11)
    bandes = [
        box(x0 + 170, y0 + 11, x0 + 182, y0 + 12.5),
        box(x0 + 170, y0 + 12.5, x0 + 182, y0 + 13.5),
    ]
    contrat = _contrat_avec_calque(tmp_path, "pdl_ptr", [poste, *bandes])

    def ecarts_pour(surface):
        contrat.donnees["parametres"]["postes"]["surface_pdl_ptr_m2"] = surface
        avertissements = []
        emprise_de_poste(contrat, "pdl_ptr", avertissements)
        return [m for m in avertissements if "déclarés au tableau bilan" in m]

    assert ecarts_pour(36.0) == []  # la surface du poste, comme à Auzainvilliers
    assert ecarts_pour(66.0) == []  # l'union du calque, comme à Saint-Cyr

    # Hors des deux lectures, le message dit tout, et n'accuse pas le poste.
    (ecart,) = ecarts_pour(90.0)
    assert ecart.startswith(
        "« pdl_ptr » : 90.0 m² déclarés au tableau bilan "
        "(« Surface des PDL/PTR (m²) »), pour 1 poste aux cotes du catalogue au "
        "plan, 36.0 m², et 66.0 m² avec la terre remise autour de lui"
    )
    assert ecart.endswith("La planche dessine les postes à leurs cotes de catalogue.")


def test_le_nombre_de_postes_se_compare_au_tableau(tmp_path):
    """Deux PTR au plan pour un au tableau : l'écart se dit, avec sa cause probable.

    Mesuré le 07/11/2026 à Auzainvilliers, le calque 0 apparié au PTR : le PTR
    principal et celui des batteries pour « Nombre de PTR » à 1. Le catalogue
    range le second dans sa section « Aire de charge (BESS) — PTR », et le
    tableau ne le compte pas avec les autres : le message le rappelle quand le
    plan porte une aire de charge, et seulement alors.
    """
    from shapely.geometry import box

    from dp_socle.planches.palette import objets_a_dessiner

    x0, y0 = synthese.ORIGINE_L93
    ptr = [
        box(x0 + 20, y0 + 85, x0 + 30, y0 + 88),
        box(x0 + 40, y0 + 85, x0 + 50, y0 + 88),
    ]
    conteneur = box(x0 + 60, y0 + 85, x0 + 66.06, y0 + 88)
    tableau = {"nb_ptr": 1, "surface_ptr_m2": 30.0}

    def messages_de(dossier, **options):
        messages = []
        objets_a_dessiner(
            _contrat_avec_calque(dossier, "ptr", ptr, postes=tableau, **options),
            messages,
        )
        return messages

    avec_bess = messages_de(
        tmp_path / "bess",
        cotes=[synthese.COTE_CONTENEUR_BESS],
        autres={"bess": [conteneur]},
    )
    (ecart,) = [m for m in avec_bess if "(« Nombre de PTR »)" in m]
    assert ecart.startswith(
        "« ptr » : 2 postes aux cotes du catalogue au plan, pour 1 au tableau "
        "bilan (« Nombre de PTR »)."
    )
    assert "« Aire de charge (BESS) — PTR »" in ecart
    # La surface, elle, dit ce que portent les postes, sans les accuser.
    (surface,) = [m for m in avec_bess if "déclarés au tableau bilan" in m]
    assert "pour 2 postes aux cotes du catalogue au plan, 60.0 m² au total" in surface
    # Le PDL/PTR du site, un au plan pour un au tableau, ne dit rien.
    assert not any(m.startswith("« pdl_ptr »") for m in avec_bess)

    sans_bess = messages_de(tmp_path / "sans")
    (ecart,) = [m for m in sans_bess if "(« Nombre de PTR »)" in m]
    assert "Aire de charge" not in ecart


def test_un_poste_declare_et_absent_du_plan_se_dit(tmp_path):
    """Un PDL/PTR au tableau, aucun au plan : le nombre parle, même calque vide.

    Sur le DXF V2 de Sarnois indice B, le calque `UNI_PDL` ne porte qu'un
    remplissage, que l'import signale et n'importe pas : le plan n'a plus de
    PDL/PTR, et le tableau en déclare un (relevé le 08/11/2026).
    """
    from dp_socle.planches.palette import objets_a_dessiner

    contrat = _contrat_avec_calque(tmp_path, "pdl_ptr", [])
    messages = []
    objets_a_dessiner(contrat, messages)
    assert (
        "« pdl_ptr » : aucun poste aux cotes du catalogue au plan, pour 1 au "
        "tableau bilan (« Nombre de PDL /PTR »)."
    ) in messages


def test_un_conteneur_se_separe_de_son_aplat(tmp_path):
    """Un conteneur BESS sur son aplat : le conteneur en BESS, l'aplat en plateforme.

    Mesuré le 07/11/2026 à Auzainvilliers : chaque conteneur de 6,06 x 3,00 m,
    dessiné deux fois, repose sur un aplat plein de 8,06 x 6,00 m du même
    calque, avec les détails du bloc par-dessous. Tout sortait à la teinte du
    BESS — 48 m² de batteries sur la DP 2, 18 sur la DP 4. Décidé le
    04/11/2026 : le conteneur garde sa teinte, l'aplat et les détails passent en
    plateforme, et le rapport demande au bureau d'études ce qu'est l'aplat.
    """
    from shapely.geometry import LineString, box

    from dp_socle.planches.palette import objets_a_dessiner

    x0, y0 = synthese.ORIGINE_L93
    conteneur = box(x0 + 60, y0 + 85, x0 + 66.06, y0 + 88)
    aplat = box(x0 + 59, y0 + 83.5, x0 + 67.06, y0 + 89.5)
    details = [
        box(x0 + 60.5, y0 + 85.5, x0 + 61.5, y0 + 86.5),
        LineString([(x0 + 62, y0 + 86.5), (x0 + 65, y0 + 86.5)]),
    ]
    contrat = _contrat_avec_calque(
        tmp_path, "bess", [aplat, conteneur, *details, box(*conteneur.bounds)],
        cotes=[synthese.COTE_CONTENEUR_BESS],
    )

    messages = []
    objets = dict(objets_a_dessiner(contrat, messages))

    assert len(objets["bess"]) == 1
    assert objets["bess"][0].equals(conteneur)
    sol = objets["plateforme"]
    assert any(g.equals(aplat) for g in sol)
    assert all(any(g.equals(detail) for g in sol) for detail in details)
    assert not any(g.equals(conteneur) for g in sol)

    message = next(m for m in messages if m.startswith("« bess »"))
    assert "le conteneur est l'objet de 6.06 x 3.00 m du calque" in message
    assert "l'a dessiné deux fois à l'identique" in message
    # L'aplat est la plateforme des batteries que le tableau déclare : le
    # message le dit, sans plus le demander au bureau d'études (08/11/2026).
    assert (
        "Il est posé sur un aplat de 8.06 x 6.00 m, la plateforme des batteries, "
        "dessiné en plateforme comme les 2 autre(s) objet(s) du calque"
    ) in message
    assert "à demander au bureau d'études" not in message
    assert "?" not in message
    # Une information, rangée parmi les points à savoir du dossier : elle n'est
    # pas lue comme une pièce absente, qui s'affiche à part en rouge.
    from dp_socle.sortie_pptx import annonce_une_piece_absente

    assert not annonce_une_piece_absente(message)


def test_un_conteneur_hors_catalogue_se_dessine_tel_quel(tmp_path):
    """Sans objet aux cotes du catalogue, rien ne se sépare : le calque est dessiné.

    C'est le comportement d'avant la règle, et il reste celui d'un conteneur que
    le bureau d'études n'a pas dessiné à ses cotes : on ne reconstruit pas un
    ouvrage qu'on ne reconnaît pas.
    """
    from shapely.geometry import box

    from dp_socle.planches.palette import objets_a_dessiner

    x0, y0 = synthese.ORIGINE_L93
    bloc = [box(x0 + 60, y0 + 85, x0 + 65, y0 + 90), box(x0 + 61, y0 + 86, x0 + 62, y0 + 87)]
    contrat = _contrat_avec_calque(
        tmp_path, "bess", bloc, cotes=[synthese.COTE_CONTENEUR_BESS]
    )

    messages = []
    objets = dict(objets_a_dessiner(contrat, messages))

    assert len(objets["bess"]) == 2
    assert not any(m.startswith("« bess »") for m in messages)


# ---------------------------------------------------------------------------
# L'archive du contrat, qui doit quitter le serveur et revenir entière
# ---------------------------------------------------------------------------
#
# L'application tourne sur un serveur : `sortie/` y vit, et le chef de projet
# n'en repart qu'avec ce qu'il télécharge. Le contrat est aussi ce que lit le
# dépôt voisin `photomontage` — il ne relit plus aucun plan depuis le
# 24/09/2026. Ce qui est mesuré ici est donc le **voyage** : ce qui descend doit
# se déplier en un contrat lisible, sans que le destinataire ait à remettre quoi
# que ce soit en ordre.


def test_l_archive_se_deplie_en_un_contrat_relisable(tmp_path):
    """Le critère n'est pas que le ZIP s'écrive, mais qu'il se relise.

    Écrit, téléchargé, déplié, relu : c'est le geste complet, et c'est le seul
    qui dise si l'archive sert à quelque chose.
    """
    dossier = tmp_path / "sortie" / "PV-TÉMOIN"
    synthese.ecrire(dossier)

    octets = archiver_le_contrat(dossier, "PV-TÉMOIN")

    assert octets is not None
    deplie = tmp_path / "recu"
    with zipfile.ZipFile(io.BytesIO(octets)) as archive:
        # Un dossier portant les deux fichiers à leurs noms d'origine : c'est ce
        # que `charger_contrat` attend ici, et `lecture_contrat.lire` là-bas.
        assert sorted(archive.namelist()) == [
            "PV-TÉMOIN/geometries.gpkg",
            "PV-TÉMOIN/projet.json",
        ]
        archive.extractall(deplie)

    contrat = charger_contrat(deplie / "PV-TÉMOIN")

    assert contrat.origine == ORIGINE_IMPORT_BE
    assert len(contrat.geometries("tables_pv")) == len(
        charger_contrat(dossier).geometries("tables_pv")
    )


def test_l_archive_porte_le_meme_geopackage_octet_pour_octet(tmp_path):
    """Rien n'est recomposé au passage : c'est le fichier du dossier, tel quel.

    Un GeoPackage réécrit par une autre version de la pile, même à géométrie
    égale, ne serait plus celui que les planches ont lu — et c'est justement ce
    que l'archive doit garantir à qui montera le photomontage.
    """
    dossier = tmp_path / "sortie" / "PV-TÉMOIN"
    synthese.ecrire(dossier)

    octets = archiver_le_contrat(dossier, "PV-TÉMOIN")

    with zipfile.ZipFile(io.BytesIO(octets)) as archive:
        embarque = archive.read("PV-TÉMOIN/geometries.gpkg")
    assert embarque == (dossier / "geometries.gpkg").read_bytes()


def test_sans_contrat_il_n_y_a_rien_a_emporter(tmp_path):
    """Un dossier d'étude amont n'a pas de plan importé : pas d'archive, et pas
    de bouton non plus — plutôt qu'un ZIP vide qui se télécharge sans rien dire.
    """
    vide = tmp_path / "sortie" / "PV-SANS-PLAN"
    vide.mkdir(parents=True)

    assert archiver_le_contrat(vide, "PV-SANS-PLAN") is None
