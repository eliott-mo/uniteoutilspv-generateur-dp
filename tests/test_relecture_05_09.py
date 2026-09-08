"""Retours de relecture du 05/09/2026, mesurés.

Chaque test répond à une remarque faite sur les trois dossiers d'essai, et
mesure ce qui avait été vu à l'œil : un contour qui ne se remplissait pas, une
maille de grillage qui changeait de finesse avec l'échelle de la planche, une
emprise qui mordait sur les parcelles voisines.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from shapely.geometry import LineString, Polygon, box

from dp_socle.planches.dp1_3_cadastre import (
    PART_MIN_ASSIETTE,
    PART_PLEINE_ASSIETTE,
    message_emprise_entamee,
    parcelles_entamees,
)
from dp_socle.planches.dp4_ouvrages import (
    CITERNES,
    CONTENEURS,
    MAILLE_GRILLAGE_M,
    REDONDANTS,
)
from dp_socle.planches.palette import fermer_les_contours


# ---------------------------------------------------------------------------
# Un contour ouvert n'est pas un trait : il se remplit
# ---------------------------------------------------------------------------


def _contour_en_morceaux(largeur: float, hauteur: float) -> list:
    """Les quatre côtés d'un rectangle, exportés séparément par la CAO."""
    return [
        LineString([(0.0, 0.0), (largeur, 0.0)]),
        LineString([(largeur, 0.0), (largeur, hauteur)]),
        LineString([(largeur, hauteur), (0.0, hauteur)]),
        LineString([(0.0, hauteur), (0.0, 0.0)]),
    ]


def test_un_contour_ouvert_est_recousu_en_surface():
    """La citerne de refroidissement sortait en contour, sans remplissage.

    Relevé sur Sarnois : son calque porte dix polylignes et aucun polygone. La
    légende annonçait un aplat et la planche montrait un trait.
    """
    messages = []
    obtenu = fermer_les_contours(
        _contour_en_morceaux(11.7, 9.3), "citerne_refroidissement", messages
    )
    surfaces = [g for g in obtenu if g.geom_type == "Polygon"]
    assert len(surfaces) == 1
    assert surfaces[0].area == pytest.approx(11.7 * 9.3, rel=1e-6)
    assert messages, "une recomposition doit s'écrire au rapport"


def test_un_lineaire_n_est_pas_recousu():
    """Le portail est un linéaire : ses arcs de débattement se referment.

    Mesuré le 05/09/2026 : sans ce garde-fou, les deux arcs du portail de
    Sarnois donnaient deux surfaces de 9,6 m² qui n'existent pas.
    """
    messages = []
    lignes = _contour_en_morceaux(3.5, 2.8)
    assert fermer_les_contours(lignes, "portail", messages) == lignes
    assert not messages


def test_un_contour_minuscule_n_est_pas_un_ouvrage():
    messages = []
    lignes = _contour_en_morceaux(0.4, 0.4)
    assert fermer_les_contours(lignes, "bess", messages) == lignes
    assert not messages


# ---------------------------------------------------------------------------
# La maille du grillage est une dimension, pas un figuré
# ---------------------------------------------------------------------------


@dataclass
class _DessinCompteur:
    """Un `Dessin` réduit à ce que `_grillage` lui demande."""

    denominateur: int
    lignes: int = 0
    rectangles: int = 0

    def ligne(self, depart, arrivee, style=None) -> None:
        self.lignes += 1

    def rectangle(self, x, y, largeur, hauteur, style=None) -> None:
        self.rectangles += 1


def test_la_maille_du_grillage_ne_depend_pas_de_l_echelle():
    """Le même grillage sortait deux fois plus fin sur une planche au 1:100.

    La maille était exprimée en millimètres de papier : elle valait 8 cm de
    terrain au 1:100 et 16 cm au 1:200. C'est une dimension d'ouvrage, elle se
    dessine à sa taille.
    """
    from dp_socle.planches.dp4_ouvrages import _grillage

    comptes = []
    for denominateur in (100, 200):
        dessin = _DessinCompteur(denominateur=denominateur)
        _grillage(dessin, 0.0, 7.5, 2.0)
        comptes.append(dessin.lignes)
    assert comptes[0] == comptes[1]
    # 7,50 m de large et 2,00 m de haut à la maille retenue.
    attendu = int(7.5 / MAILLE_GRILLAGE_M) - 1 + int(2.0 / MAILLE_GRILLAGE_M) - 1
    assert comptes[0] == attendu


# ---------------------------------------------------------------------------
# Une citerne est une citerne
# ---------------------------------------------------------------------------


def test_la_citerne_de_refroidissement_s_efface_devant_la_citerne_incendie():
    """Deux planches de citerne à cotes près l'une de l'autre : une suffit."""
    assert REDONDANTS["citerne_refroidissement"] == "bache_incendie"
    assert "citerne_refroidissement" in CITERNES
    assert "bache_incendie" in CITERNES


def test_les_conteneurs_se_dessinent_comme_des_conteneurs():
    """BESS et local de stockage sont des conteneurs maritimes, pas des bacs."""
    assert set(CONTENEURS) == {"bess", "local_technique"}


# ---------------------------------------------------------------------------
# Une emprise de projet épouse le parcellaire
# ---------------------------------------------------------------------------


@dataclass
class _Parcelle:
    section: str
    numero: str
    geometrie: Polygon


def test_une_emprise_qui_coupe_une_parcelle_est_signalee():
    """Le premier jeu d'essai de Sarnois mordait sur dix parcelles voisines.

    Rien ne le signalait : la planche dessinait fidèlement ce qu'on lui donnait,
    et le tableau annonçait 27,96 ha de contenance pour 8,51 ha d'emprise.
    """
    parcelles = [
        _Parcelle("ZA", "0057", box(0.0, 0.0, 100.0, 100.0)),
        _Parcelle("ZA", "0058", box(100.0, 0.0, 200.0, 100.0)),
    ]
    # L'emprise prend la première en entier et mord de moitié sur la seconde.
    entamees = parcelles_entamees(parcelles, box(0.0, 0.0, 150.0, 100.0))

    assert [p.numero for p, _ in entamees] == ["0058"]
    assert entamees[0][1] == pytest.approx(0.5)
    assert "0058" in message_emprise_entamee(entamees)


def test_une_emprise_qui_suit_le_parcellaire_ne_dit_rien():
    parcelles = [
        _Parcelle("ZA", "0057", box(0.0, 0.0, 100.0, 100.0)),
        _Parcelle("ZA", "0058", box(100.0, 0.0, 200.0, 100.0)),
    ]
    assert parcelles_entamees(parcelles, box(0.0, 0.0, 100.0, 100.0)) == []
    assert message_emprise_entamee([]) == ""


def test_les_deux_seuils_de_l_assiette_encadrent_bien():
    """Une écharde de calage n'est pas une parcelle coupée en deux."""
    assert 0.0 < PART_MIN_ASSIETTE < PART_PLEINE_ASSIETTE < 1.0


# ---------------------------------------------------------------------------
# La coupe se place là où elle traverse le plus de rangées
# ---------------------------------------------------------------------------


def _rangees(nombre: int, pas: float = 10.0, longueur: float = 200.0) -> list:
    """Un champ de rangées est-ouest, régulières, larges de 4 m."""
    return [
        box(0.0, index * pas, longueur, index * pas + 4.0) for index in range(nombre)
    ]


def test_la_coupe_se_place_dans_la_moitie_centrale():
    """Une coupe collée au bord du site ne montre ni terrain ni rangées."""
    from dp_socle.coupe import BANDE_EXCLUE, position_de_coupe

    tables = _rangees(20)
    emprise = box(0.0, -10.0, 200.0, 210.0)
    point, _, _ = position_de_coupe(0.0, emprise, tables)

    # Les rangées courent d'est en ouest : la coupe glisse sur l'axe des x.
    largeur = 200.0
    assert BANDE_EXCLUE * largeur <= point.x <= (1.0 - BANDE_EXCLUE) * largeur


def test_la_coupe_prefere_traverser_plutot_qu_effleurer():
    """`intersects` compte les tables qu'on frôle au coin, et trompe la mesure.

    Le champ ci-dessous a un trou au milieu de sa moitié centrale : la coupe
    doit l'éviter et se poser là où elle coupe vraiment les rangées.
    """
    from dp_socle.coupe import LARGEUR_TRAVERSEE_MIN_M, position_de_coupe

    pleines = [box(0.0, index * 10.0, 200.0, index * 10.0 + 4.0) for index in range(20)]
    # Un couloir vide de 60 à 140 m en x, sur toute la hauteur du champ.
    troue = [
        geom
        for bande in pleines
        for geom in (
            box(0.0, bande.bounds[1], 60.0, bande.bounds[3]),
            box(140.0, bande.bounds[1], 200.0, bande.bounds[3]),
        )
    ]
    emprise = box(0.0, -10.0, 200.0, 210.0)
    point, retenues, _ = position_de_coupe(0.0, emprise, troue)

    assert not 60.0 < point.x < 140.0, "la coupe s'est posée dans le couloir vide"
    assert retenues == 20, "les vingt rangées doivent être vraiment traversées"
    # Et ce sont bien des traversées, pas des contacts de bord.
    for table in troue:
        if table.bounds[0] <= point.x <= table.bounds[2]:
            assert table.bounds[3] - table.bounds[1] >= LARGEUR_TRAVERSEE_MIN_M


def test_une_coupe_sans_table_refuse_de_se_placer():
    from dp_socle.coupe import position_de_coupe
    from dp_socle.erreurs import ErreurCoupe

    with pytest.raises(ErreurCoupe, match="Aucune table"):
        position_de_coupe(0.0, box(0.0, 0.0, 100.0, 100.0), [])


# ---------------------------------------------------------------------------
# Une échelle par ouvrage, le 1:100 par défaut
# ---------------------------------------------------------------------------


def test_un_grand_ouvrage_descend_seul_au_1_200():
    """La citerne tirait toute la planche au 1:200, conteneurs compris."""
    from dp_socle.planches.dp4_ouvrages import (
        ECHELLE_OUVRAGE_PREFEREE,
        Vue,
        BlocOuvrage,
        _echelles_des_blocs,
    )

    def _rien(dessin):
        return None

    petit = BlocOuvrage(
        titre="Conteneur", vues=[Vue("Élévation", 6.0, 3.0, _rien)]
    )
    grand = BlocOuvrage(
        titre="Citerne", vues=[Vue("Vue de dessus", 40.0, 9.3, _rien)]
    )
    echelles = _echelles_des_blocs([petit, grand], largeur_mm=260.0, hauteur_mm=240.0)

    assert echelles[0] == ECHELLE_OUVRAGE_PREFEREE
    assert echelles[1] > echelles[0], "le grand ouvrage seul descend d'un cran"


def test_le_1_50_n_est_jamais_choisi_tout_seul():
    """Un panneau de clôture au 1:50 écraserait ses voisins."""
    from dp_socle.planches.dp4_ouvrages import (
        ECHELLE_OUVRAGE_PREFEREE,
        Vue,
        BlocOuvrage,
        _echelles_des_blocs,
    )

    def _rien(dessin):
        return None

    minuscule = BlocOuvrage(titre="Portail", vues=[Vue("Élévation", 2.0, 2.0, _rien)])
    assert _echelles_des_blocs([minuscule], 260.0, 240.0) == [ECHELLE_OUVRAGE_PREFEREE]


# ---------------------------------------------------------------------------
# Des ouvrages dispersés : on en situe un seul
# ---------------------------------------------------------------------------


class _ContratFactice:
    """Le strict nécessaire pour `_zone_reperee` : des géométries par catégorie."""

    def __init__(self, couches):
        self._couches = couches

    def geometries(self, categorie):
        return self._couches.get(categorie, [])


def test_des_ouvrages_disperses_ne_sont_repere_que_sur_un():
    """Les englober tous ramenait le zoom au plan de masse entier.

    Mesuré sur la DP 4-3 de Sarnois indice A : ses trois ouvrages de 6 m sont
    répartis sur 114 m ; le cadre les englobant faisait 239 x 154 m, les trois
    quarts du site, et la planche sortait au 1:2 000.
    """
    from dp_socle.planches.dp4_ouvrages import _zone_reperee

    emprise = box(0.0, 0.0, 300.0, 300.0)
    contrat = _ContratFactice(
        {
            "bess": [box(10.0, 150.0, 16.0, 153.0)],
            "local_technique": [box(270.0, 150.0, 276.0, 153.0)],
        }
    )
    messages = []
    cadre, resserre = _zone_reperee(
        contrat, ("bess", "local_technique"), emprise, messages
    )

    assert resserre
    minx, miny, maxx, maxy = cadre.bounds
    assert maxx - minx < 0.45 * 300.0, "le cadre couvre encore tout le site"
    assert any("dispersés" in message for message in messages)


def test_des_ouvrages_voisins_sont_repere_ensemble():
    """Deux ouvrages côte à côte tiennent dans le même cadre, et y restent."""
    from dp_socle.planches.dp4_ouvrages import _zone_reperee

    emprise = box(0.0, 0.0, 300.0, 300.0)
    contrat = _ContratFactice(
        {
            "bess": [box(150.0, 150.0, 156.0, 153.0)],
            "local_technique": [box(160.0, 150.0, 166.0, 153.0)],
        }
    )
    messages = []
    cadre, resserre = _zone_reperee(
        contrat, ("bess", "local_technique"), emprise, messages
    )

    assert resserre
    assert cadre.contains(box(150.0, 150.0, 166.0, 153.0))
    assert not messages


def test_le_portail_commande_le_cadrage():
    """Un portail est un ouvrage de 7 m à un endroit précis, pas un linéaire.

    Sur Sarnois indice A, la DP 4-2 ne porte ni citerne ni poste : classé parmi
    les ouvrages étendus, le portail laissait la planche se cadrer sur les
    327 m du site.
    """
    from dp_socle.planches.dp4_ouvrages import CATEGORIES_ETENDUES, _zone_reperee

    assert "portail" not in CATEGORIES_ETENDUES
    assert "cloture" in CATEGORIES_ETENDUES

    emprise = box(0.0, 0.0, 300.0, 300.0)
    contrat = _ContratFactice(
        {
            "cloture": [emprise.exterior],
            "portail": [box(148.0, 0.0, 155.0, 1.0)],
        }
    )
    cadre, resserre = _zone_reperee(contrat, ("cloture", "portail"), emprise, [])
    assert resserre
    minx, _, maxx, _ = cadre.bounds
    assert maxx - minx < 0.45 * 300.0


def test_les_hauteurs_de_table_viennent_du_tableau_bilan():
    """Aucune liberté avec la donnée d'entrée : les hauteurs déclarées font foi.

    Une version allait chercher les hauteurs du bloc `standards_unite` quand les
    déclarées ne refermaient pas la géométrie du pas. C'est retiré : une
    structure peut être haute, et l'écart se règle au tableau bilan.
    """
    from dp_socle.planches import dp3_coupes

    assert not hasattr(dp3_coupes, "_hauteurs_qui_referment")
    assert not hasattr(dp3_coupes, "_piste_des_standards")


def test_le_pdf_assemble_porte_le_nom_du_projet():
    """Trois « DP_complet.pdf » côte à côte ne se distinguent plus.

    Le fichier quitte presque toujours son dossier — courriel, guichet, relecture
    de deux indices du même site — et c'est là qu'il doit se nommer.
    """
    from dp_socle.assemblage import nom_assemblage
    from dp_socle.projet import Projet

    projet = Projet(
        nom="Sarnois-B", commune="Sarnois", code_postal="60210",
        date="2026-09-05", emprise="emprise.geojson",
    )
    assert nom_assemblage(projet) == "Sarnois-B_DP_complet.pdf"


# ---------------------------------------------------------------------------
# Décisions de la relecture du 05/09/2026
# ---------------------------------------------------------------------------


def test_un_seul_nom_saisi_donne_un_dossier_sur():
    """Le cartouche reproduit le nom tel quel, le disque en reçoit une version sûre."""
    from dp_socle.projet import identifiant_de_dossier

    assert identifiant_de_dossier("Saint-Cyr-en-Val") == "Saint-Cyr-en-Val"
    assert identifiant_de_dossier("Centrale PV : tranche 2") == "Centrale-PV-tranche-2"
    assert identifiant_de_dossier("Bray/Saint-Aignan") == "Bray-Saint-Aignan"
    assert identifiant_de_dossier("  Sarnois  indice A ") == "Sarnois-indice-A"


def test_la_coupe_de_principe_montre_deux_rangees():
    """Trois ne tenaient jamais au 1:80, et la troisième ne dit rien de plus."""
    from dp_socle.planches.dp3_coupes import RANGEES_DESSINEES, RANGEES_MINIMALES

    assert RANGEES_DESSINEES == RANGEES_MINIMALES == 2


def test_la_hauteur_de_cloture_n_est_plus_un_avertissement():
    """2,00 m est une constante UNITe confirmée, pas une substitution."""
    from dp_socle.planches import standards

    assert standards.HAUTEUR_CLOTURE_M == standards.HAUTEUR_PORTAIL_M == 2.00
    assert not hasattr(standards, "MESSAGE_HAUTEURS")


def test_le_seuil_de_recevabilite_est_une_regle_pas_un_reglage():
    from dp_socle.import_be import SEUIL_DP_MWC

    assert SEUIL_DP_MWC == 3.0


# ---------------------------------------------------------------------------
# Le poste est reconnu, pas reconstruit
# ---------------------------------------------------------------------------


def test_le_poste_se_reconnait_a_ses_cotes_de_catalogue():
    """Un calque de poste porte le poste **et** la terre remise autour de lui.

    Mesuré le 05/09/2026 : à Saint-Cyr le calque `pdl_ptr` porte un rectangle de
    12,00 x 3,00 m — exactement le PDL/PTR du catalogue — et deux bandes de
    12 x 1,50 et 12 x 1,00 qui le bordent. Dessiné d'un bloc, le poste sortait à
    12 x 5,50 m quand son élévation le dessine à 12 x 3.
    """
    from dp_socle.planches.palette import _est_le_poste, dimensions_au_sol

    poste = box(0.0, 0.0, 12.0, 3.0)
    assert dimensions_au_sol(poste) == pytest.approx((12.0, 3.0))
    # Les cotes du catalogue se donnent dans n'importe quel ordre : le
    # catalogue UNITe écrit tantôt « longueur x largeur », tantôt l'inverse.
    assert _est_le_poste(poste, 12.0, 3.0)
    assert _est_le_poste(poste, 3.0, 12.0)

    assert not _est_le_poste(box(0.0, 0.0, 12.0, 1.5), 12.0, 3.0)
    assert not _est_le_poste(box(0.0, 0.0, 12.0, 5.5), 12.0, 3.0)


def test_un_poste_hors_catalogue_reste_dessine_tel_quel():
    """Sarnois indice A porte un 10 x 3 là où le tableau déclare un 12 x 3.

    Aucun objet du calque n'a les cotes du catalogue : on ne reconstruit rien,
    on dessine le plan, et l'écart au tableau se dit.
    """
    from dp_socle.planches.palette import _est_le_poste

    assert not _est_le_poste(box(0.0, 0.0, 10.0, 3.0), 12.0, 3.0)


def test_le_nom_du_projet_se_deduit_de_la_commune():
    """« PV » plus la commune : deux champs de moins à remplir.

    Le champ qui demandait le nom recopiait la commune neuf fois sur dix, et la
    dixième était une coquille.
    """
    from dp_socle.projet import identifiant_de_dossier, nom_de_projet

    assert nom_de_projet("Bray-Saint-Aignan") == "PV Bray-Saint-Aignan"
    assert nom_de_projet("  Sarnois ") == "PV Sarnois"
    assert nom_de_projet("") == ""
    # Et le dossier de sortie en découle, sans caractère interdit.
    assert identifiant_de_dossier(nom_de_projet("Saint-Cyr-en-Val")) == (
        "PV-Saint-Cyr-en-Val"
    )


def test_l_indice_fait_partie_du_nom_du_projet():
    """Deux indices d'un même projet sont deux dossiers.

    Sarnois en a deux, qui diffèrent par leur poste, leur citerne et leur zone de
    contention. Sans l'indice au nom, le second écrasait le premier.
    """
    from dp_socle.projet import identifiant_de_dossier, nom_de_projet

    assert nom_de_projet("Sarnois", "IND10A") == "PV Sarnois IND10A"
    assert nom_de_projet("Sarnois", "IND10B") == "PV Sarnois IND10B"
    assert identifiant_de_dossier(nom_de_projet("Sarnois", "IND10A")) != (
        identifiant_de_dossier(nom_de_projet("Sarnois", "IND10B"))
    )
    # Sans indice — le plan n'a pas encore été importé — le nom reste utilisable.
    assert nom_de_projet("Sarnois") == "PV Sarnois"
    assert nom_de_projet("Sarnois", "  ") == "PV Sarnois"
