"""Lot 10, étape 2 — les cotes posées sur la DP 2, mesurées dans le PDF produit.

Le critère est celui du dépôt : non pas « la cote est calculée », mais « la
planche produite la porte, juste ». Sur le modèle de `test_echelle_pdf.py`,
chaque cote se retrouve dans le flux de contenu du PDF : ses deux flèches, dont
les pointes doivent tomber aux deux bouts attendus ; sa longueur papier, qui,
ramenée à l'échelle, égale la distance Lambert 93 à 0,5 % près ; et sa valeur,
écrite dans l'axe de sa ligne (brief du lot 10, « Comment le tester » et D8).

Le site est celui du lot 4, `contrat_synthetique` : une clôture de 200 x 120 m,
six rangées de 160 x 4 m au pas de 10 m. Le parcellaire est simulé — une seule
parcelle, le terrain d'assiette, dont chaque limite est à une distance connue
de la clôture : 10 m à l'ouest, 8 m au sud, 12 m à l'est, 6 m au nord. Les
cotes attendues se lisent sur le dessin du site, sans relire le code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import geopandas as gpd
import pytest
from shapely.geometry import box

from dp_socle.contrat import charger_contrat
from dp_socle.geometrie import charger_emprise
from dp_socle.planches.primitives import TAILLE_COTE
from dp_socle.projet import Projet

from . import contrat_synthetique as synthese
from .mesure_pdf import format_page, pointes_de_fleche, textes

pytest.importorskip(
    "cairosvg", reason="CairoSVG et libcairo sont nécessaires pour produire le PDF"
)

MM_PAR_PT = 25.4 / 72.0
ECART_ADMIS = 0.005

#: Une pointe de flèche tombe à son bout attendu à cela près, en points.
TOLERANCE_PT = 0.25

#: Ce que le terrain d'assiette déborde de la clôture, de chaque côté, en mètres.
RECUL_OUEST_M = 10.0
RECUL_SUD_M = 8.0
RECUL_EST_M = 12.0
RECUL_NORD_M = 6.0

X0, Y0 = synthese.ORIGINE_L93

#: Le champ : six rangées de 160 x 4 m, de X0 + 20 à X0 + 180, de Y0 + 20 à
#: Y0 + 74 — à 20 m de la clôture à l'ouest, au sud et à l'est, à 46 m au nord.
TABLES_OUEST, TABLES_EST = X0 + 20.0, X0 + 180.0
TABLES_SUD, TABLES_NORD = Y0 + 20.0, Y0 + 74.0

LIMITE_OUEST = X0 - RECUL_OUEST_M
LIMITE_SUD = Y0 - RECUL_SUD_M
LIMITE_EST = X0 + synthese.LARGEUR_SITE_M + RECUL_EST_M
LIMITE_NORD = Y0 + synthese.HAUTEUR_SITE_M + RECUL_NORD_M


def _terrain(ouest=LIMITE_OUEST, sud=LIMITE_SUD, est=LIMITE_EST, nord=LIMITE_NORD):
    return box(ouest, sud, est, nord)


@pytest.fixture
def dp2(tmp_path, monkeypatch):
    """La DP 2 du site synthétique, sur un parcellaire simulé : le terrain seul.

    Le fichier d'emprise est le terrain lui-même : la parcelle est d'assiette
    par la règle de la DP 1-3, et sa limite est celle qu'on cote. La DP 2 écrit
    `from ..ign import telecharger_parcelles` : c'est sa référence qu'on
    remplace (voir `dp2_sans_geoplateforme`, lot 4).

    `produire(entites, terrain, parametres)` : le site synthétique, ou les
    entités données ; le terrain de `_terrain()`, ou celui donné ; les
    paramètres du site synthétique, ou ceux donnés. `produire.dernier` garde le
    projet et le dossier du contrat, pour produire une autre planche du même
    contrat.
    """
    from dp_socle.ign import Parcelle
    from dp_socle.import_be import ecrire_geopackage, ecrire_parametres
    from dp_socle.planches import dp2_plan_masse, dp3_coupes

    courant = {"terrain": _terrain()}

    def parcelles(bbox, *args, **kwargs):
        terrain = courant["terrain"]
        return [
            Parcelle(
                geometrie=terrain, idu="00000000ZZ0001", section="ZZ",
                numero="0001", contenance_m2=terrain.area, commune="00000",
            )
        ]

    monkeypatch.setattr(dp2_plan_masse, "telecharger_parcelles", parcelles)
    monkeypatch.setattr(dp2_plan_masse, "telecharger_batiments", lambda *a, **k: [])
    # La DP 3, qu'on produit du même contrat pour comparer l'inter-rangée, lit
    # aussi le parcellaire, pour le bandeau sous la coupe.
    monkeypatch.setattr(dp3_coupes, "telecharger_parcelles", parcelles)

    def produire(entites=None, terrain=None, parametres=None):
        terrain = courant["terrain"] = terrain or _terrain()
        dossier = tmp_path / "sortie" / "Essai"
        if entites is None and parametres is None:
            synthese.ecrire(dossier)
        else:
            ecrire_geopackage(
                synthese.entites() if entites is None else entites,
                dossier, synthese.ligne_coupe(),
            )
            ecrire_parametres(parametres or synthese.parametres(), dossier)
        emprise = tmp_path / "emprise.geojson"
        gpd.GeoDataFrame(geometry=[terrain], crs="EPSG:2154").to_file(
            emprise, driver="GeoJSON"
        )
        projet = Projet(
            nom="Essai", commune="Sarnois", code_postal="60210",
            date="2026-11-09", emprise=str(emprise), libelle="Essai lot 10",
        )
        produire.dernier = {"projet": projet, "dossier": dossier}
        sortie = dp2_plan_masse.generer(
            projet, charger_contrat(dossier), charger_emprise(emprise),
            tmp_path, numero="5",
        )
        transformation = sortie.planche.transformation
        _, hauteur_pt = format_page(sortie.chemin)

        def vers_la_page(x, y):
            """Un point Lambert 93 sur la page du PDF, en points PostScript."""
            x_mm, y_mm = transformation.point(x, y)
            return (x_mm / MM_PAR_PT, hauteur_pt - y_mm / MM_PAR_PT)

        return sortie, vers_la_page

    return produire


@dataclass(frozen=True)
class CoteAttendue:
    """Une cote horizontale ou verticale du site, telle que le dessin la donne.

    `depart` et `arrivee` sont la coordonnée de ses deux bouts le long de la
    cote — x pour une cote horizontale, y sinon ; `plage`, l'intervalle où elle
    peut glisser le long du côté, que la règle ne fixe pas.
    """

    nom: str
    depart: float
    arrivee: float
    plage: tuple
    horizontale: bool
    libelle: str

    @property
    def distance_m(self) -> float:
        return abs(self.arrivee - self.depart)

    @property
    def texte(self) -> str:
        from dp_socle.planche import nombre_fr

        return f"{nombre_fr(self.distance_m, 1)} m ({self.libelle})"


def _pointes_aux_bouts(chemin, attendue: CoteAttendue, vers_la_page):
    """Les deux pointes de flèche aux bouts de la cote attendue, ou `None`.

    Chaque flèche doit pointer vers l'extérieur de la cote, sa pointe sur le
    bout : celle du départ s'éloigne de l'arrivée, et inversement.
    """
    def page(fixe, glissant):
        x, y = (fixe, glissant) if attendue.horizontale else (glissant, fixe)
        return vers_la_page(x, y)

    axe = 0 if attendue.horizontale else 1
    travers = 1 - axe
    depart = page(attendue.depart, attendue.plage[0])[axe]
    arrivee = page(attendue.arrivee, attendue.plage[0])[axe]
    bornes = sorted(page(attendue.depart, v)[travers] for v in attendue.plage)
    sens = 1.0 if arrivee > depart else -1.0

    fleches = pointes_de_fleche(chemin)
    for p, dp in fleches:
        if abs(p[axe] - depart) > TOLERANCE_PT:
            continue
        if not bornes[0] - TOLERANCE_PT <= p[travers] <= bornes[1] + TOLERANCE_PT:
            continue
        for q, dq in fleches:
            if abs(q[axe] - arrivee) > TOLERANCE_PT or abs(q[travers] - p[travers]) > TOLERANCE_PT:
                continue
            if dp[axe] * sens < -0.99 and dq[axe] * sens > 0.99:
                return p, q
    return None


def _texte_de(chemin, texte):
    """Les places où la page écrit `texte` : (x du début, y de la base, corps)."""
    return [(x, y, corps) for x, y, corps, t in textes(chemin) if t == texte]


# ---------------------------------------------------------------------------
# C1 — tables → limite parcellaire
# ---------------------------------------------------------------------------

LIBELLE_TABLES = "tables – limite parcellaire"

COTES_TABLES_LIMITE = [
    CoteAttendue("ouest", TABLES_OUEST, LIMITE_OUEST, (TABLES_SUD, TABLES_NORD), True, LIBELLE_TABLES),
    CoteAttendue("sud", TABLES_SUD, LIMITE_SUD, (TABLES_OUEST, TABLES_EST), False, LIBELLE_TABLES),
    CoteAttendue("est", TABLES_EST, LIMITE_EST, (TABLES_SUD, TABLES_NORD), True, LIBELLE_TABLES),
]


@pytest.mark.parametrize("attendue", COTES_TABLES_LIMITE, ids=lambda c: c.nom)
def test_la_cote_tables_limite_se_mesure_dans_le_pdf(dp2, attendue):
    """Ses flèches aux deux bouts, sa longueur à l'échelle, sa valeur dans son axe.

    De la table la plus proche du côté jusqu'à la limite du terrain, à travers
    la clôture : 30 m à l'ouest (20 + 10), 28 m au sud (20 + 8), 32 m à l'est
    (20 + 12). La valeur se lit dans l'axe de sa ligne, au-delà de la limite,
    hors de la centrale (D8, 08/11/2026).

    Le côté sud est celui qui éprouve cette dernière règle : sa ligne est
    verticale, et la valeur, horizontale, y tiendrait entre les deux flèches
    sans rien toucher. Seule la préférence pour l'au-delà de la limite l'en
    écarte. À l'ouest et à l'est, la ligne, horizontale et longue de 30 à
    32 mm, ne loge pas sa valeur : elle irait au-delà de toute façon.
    """
    sortie, vers_la_page = dp2()

    pointes = _pointes_aux_bouts(sortie.chemin, attendue, vers_la_page)
    assert pointes is not None, (
        f"côté {attendue.nom} : pas de cote de {attendue.distance_m} m dont les "
        "flèches tombent sur les tables et sur la limite"
    )
    mesure_mm = math.dist(*pointes) * MM_PAR_PT
    attendu_mm = attendue.distance_m * 1000.0 / sortie.echelle
    assert abs(mesure_mm - attendu_mm) / attendu_mm < ECART_ADMIS, (
        f"côté {attendue.nom} : {mesure_mm:.3f} mm mesurés entre les pointes, "
        f"{attendu_mm:.3f} mm attendus au 1:{sortie.echelle}"
    )

    places = _texte_de(sortie.chemin, attendue.texte)
    assert places, f"« {attendue.texte} » n'est pas écrit sur la planche"
    largeur_pt = sortie.planche.mesurer_texte(attendue.texte, TAILLE_COTE) / MM_PAR_PT
    limite = pointes[1]
    for x, y, corps in places:
        centre = (x + largeur_pt / 2.0, y + 0.35 * corps)
        axe = 0 if attendue.horizontale else 1
        travers = 1 - axe
        # Dans l'axe de sa ligne…
        assert abs(centre[travers] - limite[travers]) < 0.5 / MM_PAR_PT, (
            f"« {attendue.texte} » hors de l'axe de sa ligne"
        )
        # … et au-delà de la limite, du côté opposé aux tables.
        dehors = (limite[axe] - pointes[0][axe]) * (centre[axe] - limite[axe])
        assert dehors > 0, f"« {attendue.texte} » n'est pas au-delà de la limite"


def test_un_cote_aux_tables_lointaines_se_dit_au_rapport(dp2):
    """Au nord, les tables sont à 46 m de la clôture : pas de cote, et le rapport le dit."""
    sortie, _ = dp2()
    assert any(
        "non coté : les tables en sont à 46,0 m" in message
        for message in sortie.details["avertissements"]
    ), sortie.details["avertissements"]


# ---------------------------------------------------------------------------
# C1 — clôture → limite parcellaire, ailleurs sur le côté
# ---------------------------------------------------------------------------

LIBELLE_CLOTURE = "clôture – limite parcellaire"

#: La clôture : de X0 à X0 + 200, de Y0 à Y0 + 120.
CLOTURE_EST, CLOTURE_NORD = X0 + synthese.LARGEUR_SITE_M, Y0 + synthese.HAUTEUR_SITE_M

#: Chaque cote clôture → limite, et la cote tables → limite du même côté.
COTES_CLOTURE_LIMITE = [
    (CoteAttendue("ouest", X0, LIMITE_OUEST, (Y0, CLOTURE_NORD), True, LIBELLE_CLOTURE),
     COTES_TABLES_LIMITE[0]),
    (CoteAttendue("sud", Y0, LIMITE_SUD, (X0, CLOTURE_EST), False, LIBELLE_CLOTURE),
     COTES_TABLES_LIMITE[1]),
    (CoteAttendue("est", CLOTURE_EST, LIMITE_EST, (Y0, CLOTURE_NORD), True, LIBELLE_CLOTURE),
     COTES_TABLES_LIMITE[2]),
]


@pytest.mark.parametrize(
    "attendue, des_tables", COTES_CLOTURE_LIMITE, ids=lambda c: getattr(c, "nom", "")
)
def test_la_cote_cloture_limite_se_mesure_dans_le_pdf(dp2, attendue, des_tables):
    """Depuis la clôture, perpendiculaire au côté : 10 m à l'ouest, 8 au sud, 12 à l'est.

    Elle se pose ailleurs sur le côté que la cote des tables, à 20 mm de papier
    au moins : à 1:2 000, la chaîne tables | clôture | limite du 03/11 faisait
    0,5 mm pour un écart de 1 m, et l'on ne savait plus quelle valeur allait où
    (relecture du 08/11/2026).
    """
    sortie, vers_la_page = dp2()

    pointes = _pointes_aux_bouts(sortie.chemin, attendue, vers_la_page)
    assert pointes is not None, (
        f"côté {attendue.nom} : pas de cote de {attendue.distance_m} m dont les "
        "flèches tombent sur la clôture et sur la limite"
    )
    mesure_mm = math.dist(*pointes) * MM_PAR_PT
    attendu_mm = attendue.distance_m * 1000.0 / sortie.echelle
    assert abs(mesure_mm - attendu_mm) / attendu_mm < ECART_ADMIS

    places = _texte_de(sortie.chemin, attendue.texte)
    assert places, f"« {attendue.texte} » n'est pas écrit sur la planche"
    axe = 0 if attendue.horizontale else 1
    travers = 1 - axe
    largeur_pt = sortie.planche.mesurer_texte(attendue.texte, TAILLE_COTE) / MM_PAR_PT
    for x, y, corps in places:
        centre = (x + largeur_pt / 2.0, y + 0.35 * corps)
        assert abs(centre[travers] - pointes[1][travers]) < 0.5 / MM_PAR_PT
        dehors = (pointes[1][axe] - pointes[0][axe]) * (centre[axe] - pointes[1][axe])
        assert dehors > 0, f"« {attendue.texte} » n'est pas au-delà de la limite"

    tables = _pointes_aux_bouts(sortie.chemin, des_tables, vers_la_page)
    assert tables is not None
    ecart_mm = abs(pointes[0][travers] - tables[0][travers]) * MM_PAR_PT
    assert ecart_mm >= 20.0 - 0.05, (
        f"côté {attendue.nom} : les deux cotes ne sont qu'à {ecart_mm:.1f} mm l'une de l'autre"
    )


def test_la_cloture_sur_la_limite_n_a_pas_de_seconde_cote(dp2):
    """Posée sur la limite, la clôture n'a pas de cote clôture → limite : le dessin le montre.

    Le terrain épouse ici la clôture à l'ouest : la cote des tables y vaut 20 m,
    et la seule cote clôture → limite de la planche est celle des autres côtés.
    """
    sortie, vers_la_page = dp2(terrain=_terrain(ouest=X0))
    sur_la_limite = CoteAttendue(
        "ouest", TABLES_OUEST, X0, (TABLES_SUD, TABLES_NORD), True, LIBELLE_TABLES
    )
    assert _pointes_aux_bouts(sortie.chemin, sur_la_limite, vers_la_page) is not None
    ecrits = [t for _, _, _, t in textes(sortie.chemin) if LIBELLE_CLOTURE in t]
    assert ecrits and not any(t.startswith("0,") for t in ecrits), ecrits
    assert any(
        "la clôture est sur la limite" in message
        for message in sortie.details["avertissements"]
    ), sortie.details["avertissements"]


# ---------------------------------------------------------------------------
# C5 — l'écartement entre deux rangées, à la valeur de la coupe
# ---------------------------------------------------------------------------


def _nombre(texte: str) -> float:
    """Le premier nombre d'un texte écrit à la française."""
    import re

    trouve = re.search(r"\d+(?:,\d+)?", texte)
    return float(trouve.group(0).replace(",", "."))


def test_l_inter_rangee_se_mesure_dans_le_pdf_et_vaut_la_coupe(dp2, tmp_path):
    """La ligne tient l'écart du plan ; la valeur écrite est celle de la coupe (D6).

    Les rangées sont au pas de 10 m, larges de 4 m : 6 m les séparent. Le
    contrat déclare ici 5,9 m d'inter-table, dans les 0,15 m qui font dire
    qu'un écart du plan la mesure. Sur la DP 2, la ligne tient les 6 m du plan,
    à l'échelle, entre deux rangées voisines ; sa valeur est 5,9, le nombre
    même que la DP 3 écrit sur le même contrat (« Comment le tester »). Une
    valeur relue sur le plan écrirait 6,0.
    """
    from dp_socle.planches import dp3_coupes

    donnees = synthese.parametres()
    assert donnees["parametres"]["structures"]["pitch_m"] == 10.0
    donnees["parametres"]["structures"]["inter_table_m"] = 5.9
    sortie, vers_la_page = dp2(parametres=donnees)

    # Entre deux rangées voisines : du haut de l'une au bas de la suivante.
    trouvees = []
    for k in range(5):
        entre = CoteAttendue(
            "C5", Y0 + 24.0 + 10.0 * k, Y0 + 30.0 + 10.0 * k,
            (TABLES_OUEST, TABLES_EST), False, "",
        )
        pointes = _pointes_aux_bouts(sortie.chemin, entre, vers_la_page)
        if pointes:
            trouvees.append(pointes)
    assert len(trouvees) == 1, (
        f"{len(trouvees)} cote(s) d'inter-rangée sur la planche, une attendue"
    )
    pointes = trouvees[0]
    mesure_mm = math.dist(*pointes) * MM_PAR_PT
    attendu_mm = 6.0 * 1000.0 / sortie.echelle
    assert abs(mesure_mm - attendu_mm) / attendu_mm < ECART_ADMIS

    ecrits = [
        (x, t) for x, _, _, t in textes(sortie.chemin) if t.endswith("m entre rangées")
    ]
    assert ecrits, "aucune valeur d'inter-rangée sur la planche"
    x, texte = ecrits[0]
    largeur_pt = sortie.planche.mesurer_texte(texte, TAILLE_COTE) / MM_PAR_PT
    # Dans l'axe de sa ligne, qui est verticale.
    assert abs(x + largeur_pt / 2.0 - pointes[0][0]) < 0.5 / MM_PAR_PT

    (tmp_path / "coupe").mkdir()
    coupe = dp3_coupes.generer(
        dp2.dernier["projet"], charger_contrat(dp2.dernier["dossier"]),
        tmp_path / "coupe", numero="6",
    )
    inter_table = [t for _, _, _, t in textes(coupe.chemin) if t.startswith("inter-table")]
    assert inter_table, "la DP 3 n'écrit pas son inter-table"
    assert _nombre(texte) == _nombre(inter_table[0]) == 5.9


# ---------------------------------------------------------------------------
# C6 — la largeur de chaque piste, prise en travers
# ---------------------------------------------------------------------------

#: Deux pistes dégagées de tout ouvrage : une piste légère de 160 x 4 m au nord
#: des tables, une piste lourde de 6 x 100 m le long de la clôture est.
PISTE_LEGERE = box(X0 + 20.0, Y0 + 90.0, X0 + 180.0, Y0 + 94.0)
PISTE_LOURDE = box(X0 + 190.0, Y0 + 10.0, X0 + 196.0, Y0 + 110.0)


def _site_aux_pistes_degagees():
    """Le site synthétique, ses deux pistes remplacées par `PISTE_LEGERE` et `PISTE_LOURDE`.

    Celles du site passent sous le poste et la citerne incendie : la règle de
    C6 les tient, avec raison, pour la plateforme de ces ouvrages (03/11/2026).
    """
    from dp_socle.import_be import EntiteBE

    lot = [
        e for e in synthese.entites()
        if e.categorie not in ("piste_lourde", "piste_legere")
    ]
    lot.append(EntiteBE(categorie="piste_legere", calque="SYNTHESE",
                        geometrie=PISTE_LEGERE, z_reel=False))
    lot.append(EntiteBE(categorie="piste_lourde", calque="SYNTHESE",
                        geometrie=PISTE_LOURDE, z_reel=False))
    return lot


COTES_DE_PISTE = [
    CoteAttendue("légère", Y0 + 90.0, Y0 + 94.0, (X0 + 20.0, X0 + 180.0), False, "piste"),
    CoteAttendue("lourde", X0 + 190.0, X0 + 196.0, (Y0 + 10.0, Y0 + 110.0), True, "piste"),
]


@pytest.mark.parametrize("attendue", COTES_DE_PISTE, ids=lambda c: c.nom)
def test_la_largeur_de_piste_se_mesure_dans_le_pdf(dp2, attendue):
    """En travers de la piste, d'un bord à l'autre : 4 m pour la légère, 6 m pour la lourde.

    Le libellé dit « (piste) » : sans lui, la largeur d'une piste qui longe la
    clôture se lisait comme leur écart (03/11/2026).
    """
    sortie, vers_la_page = dp2(entites=_site_aux_pistes_degagees())

    pointes = _pointes_aux_bouts(sortie.chemin, attendue, vers_la_page)
    assert pointes is not None, (
        f"piste {attendue.nom} : pas de cote de {attendue.distance_m} m d'un bord à l'autre"
    )
    mesure_mm = math.dist(*pointes) * MM_PAR_PT
    attendu_mm = attendue.distance_m * 1000.0 / sortie.echelle
    assert abs(mesure_mm - attendu_mm) / attendu_mm < ECART_ADMIS

    places = _texte_de(sortie.chemin, attendue.texte)
    assert places, f"« {attendue.texte} » n'est pas écrit sur la planche"
    axe = 0 if attendue.horizontale else 1
    travers = 1 - axe
    largeur_pt = sortie.planche.mesurer_texte(attendue.texte, TAILLE_COTE) / MM_PAR_PT
    for x, y, corps in places:
        centre = (x + largeur_pt / 2.0, y + 0.35 * corps)
        assert abs(centre[travers] - pointes[0][travers]) < 0.5 / MM_PAR_PT, (
            f"« {attendue.texte} » hors de l'axe de sa ligne"
        )


# ---------------------------------------------------------------------------
# Une cote qui sort du cadre s'arrête à son bord, et le dit (D5)
# ---------------------------------------------------------------------------


def test_une_cote_hors_du_cadre_s_arrete_au_bord_sans_fleche_et_le_dit(dp2):
    """La limite ouest à 300 m de la clôture : hors du cadre de la DP 2, au 1:1 000.

    Une emprise qui fait plusieurs fois le projet, comme à Boisné-La Tude
    (`_ce_que_la_planche_cadre`), met la limite hors de la planche. La cote va
    jusqu'au bord du dessin, sans flèche à ce bout — elle ne s'y arrête pas,
    elle sort —, et son libellé le dit. Sa valeur reste la distance entière.
    """
    from .mesure_pdf import segments

    lointaine = X0 - 300.0
    sortie, vers_la_page = dp2(terrain=_terrain(ouest=lointaine))
    texte = "320,0 m (tables – limite parcellaire, hors cadre)"
    assert _texte_de(sortie.chemin, texte), [t for *_, t in textes(sortie.chemin)]
    assert any("sort du cadre" in m for m in sortie.details["avertissements"])

    x_tables = vers_la_page(TABLES_OUEST, Y0)[0]
    bord = sortie.planche.zone_dessin()[0] / MM_PAR_PT
    bas, haut = sorted(vers_la_page(TABLES_OUEST, y)[1] for y in (TABLES_SUD, TABLES_NORD))
    fleches = [
        p for p, _ in pointes_de_fleche(sortie.chemin)
        if bas - TOLERANCE_PT <= p[1] <= haut + TOLERANCE_PT and p[0] < x_tables + TOLERANCE_PT
    ]
    # Une seule flèche, sur les tables : aucune au bord du cadre.
    assert len(fleches) == 1 and abs(fleches[0][0] - x_tables) < TOLERANCE_PT, fleches
    y_ligne = fleches[0][1]
    # Et la ligne va jusqu'au bord du dessin.
    horizontaux = [
        s for s in segments(sortie.chemin)
        if abs(s[0][1] - y_ligne) < TOLERANCE_PT and abs(s[1][1] - y_ligne) < TOLERANCE_PT
    ]
    assert any(min(s[0][0], s[1][0]) <= bord + TOLERANCE_PT for s in horizontaux), (
        "la ligne ne va pas jusqu'au bord du dessin"
    )
