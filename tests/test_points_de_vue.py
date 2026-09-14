"""Points de vue du lot 6 : lecture EXIF, lecture d'une carte photos-geoloc.

Ce qui est éprouvé ici, ce sont les décisions du lot, pas le code :
aucun cap inventé, aucune version de carte lue à moitié, aucun repli muet.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from dp_socle import lecture_exif
from dp_socle.carte_photos import depuis_carte, lire_carte
from dp_socle.erreurs import ErreurCartePhotos, ErreurPhotoIllisible
from dp_socle.points_de_vue import (
    ORIGINE_CARTE,
    ORIGINE_EXIF,
    MetadonneesPhoto,
    cap_vers,
    depuis_exif,
    place_a_la_main,
)

# ---------------------------------------------------------------------------
# Fabrication des jeux d'essai
# ---------------------------------------------------------------------------

#: Position de référence : Sarnois, dans le nord de la France.
LAT, LON = 48.7343, 6.6516


def _photo(chemin, *, gps: dict | None = None) -> str:
    """Un JPEG minuscule, avec l'EXIF GPS demandé."""
    image = Image.new("RGB", (8, 8), "white")
    exif = image.getexif()
    if gps:
        exif.get_ifd(0x8825).update(gps)
    image.save(chemin, "JPEG", exif=exif)
    return str(chemin)


def _gps(lat=48.0, lon=6.0, cap=None, precision=None, reference_cap="T") -> dict:
    champs = {
        1: "N",
        2: (float(int(lat)), (lat % 1) * 60.0, 0.0),
        3: "E",
        4: (float(int(lon)), (lon % 1) * 60.0, 0.0),
    }
    if cap is not None:
        champs.update({16: reference_cap, 17: float(cap)})
    if precision is not None:
        champs[31] = float(precision)
    return champs


def _carte(points: list[dict], *, version: int = 5, offset: float = 0.0, emprise=None):
    """Une carte photos-geoloc minimale, en octets, comme un fichier déposé.

    Leaflet est représenté par un remplissage avant le bloc de données : le
    module doit chercher son marqueur par la fin, et le test le vérifie en
    plaçant un leurre du même nom dans ce remplissage.
    """
    import json

    donnees = {
        "version": version,
        "titre": "Visite de site",
        "offset": offset,
        "emprise": emprise,
        "points": points,
    }
    corps = json.dumps(donnees, ensure_ascii=False)
    return (
        "<html><head><script>/* Leaflet inliné, volumineux */</script></head>"
        "<body>" + "x" * 5000 + f'<script id="donnees-carte" type="application/json">'
        f"{corps}</script></body></html>"
    ).encode("utf-8")


def _point(
    identifiant=0,
    nom="IMG_0420.JPG",
    ordre=0,
    lat=LAT,
    lon=LON,
    cap=None,
    masque=False,
    image="/9j/4AAQ",
    **reste,
):
    """Un point du bloc de données, aux champs du format v5."""
    point = {
        "id": identifiant,
        "nom": nom,
        "ordre": ordre,
        "lat_brut": lat,
        "lon_brut": lon,
        "lat_manuel": None,
        "lon_manuel": None,
        "lat": lat,
        "lon": lon,
        "cap_brut": cap,
        "cap_manuel": None,
        "cap": cap,
        "precision_m": None,
        "masque": masque,
        "commentaire": "",
    }
    point.update(reste)
    point["image"] = image  # dernière clé, comme le format l'écrit
    return point


# ---------------------------------------------------------------------------
# La convention d'angle, qui est le piège du module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "azimut, trigonometrique",
    [(0.0, 90.0), (90.0, 0.0), (180.0, 270.0), (270.0, 180.0)],
)
def test_le_cap_se_convertit_en_angle_mathematique(azimut, trigonometrique):
    """Azimut géographique (0 au nord, horaire) vers 0 à l'est, trigonométrique.

    Les deux conventions cohabitent dans le dépôt — `azimut_tables_deg` est un
    angle depuis l'est. Les mélanger donnerait un cône qui pointe ailleurs sans
    que rien ne le signale.
    """
    vue = place_a_la_main("vue", 700000.0, 6800000.0, azimut)
    assert vue.cap_trigonometrique_deg == pytest.approx(trigonometrique)


@pytest.mark.parametrize(
    "cible, azimut",
    [((0.0, 100.0), 0.0), ((100.0, 0.0), 90.0), ((0.0, -100.0), 180.0), ((-100.0, 0.0), 270.0)],
)
def test_viser_un_point_donne_son_azimut(cible, azimut):
    """Viser, c'est cliquer ce que la photo regarde — le cap s'en déduit."""
    assert cap_vers(0.0, 0.0, *cible) == pytest.approx(azimut)


# ---------------------------------------------------------------------------
# Aucun cap inventé : critère de validation 3 du lot
# ---------------------------------------------------------------------------


def test_un_cap_exif_ne_suffit_pas_a_dessiner_un_cone():
    """Le cap EXIF propose, il ne fait pas autorité.

    Mesuré à 15° d'erreur sur le dépôt `photomontage`, et 30 à 40° pour un
    téléphone mal calibré. Tant que le chef de projet n'a pas visé sur fond
    satellite, la planche porte le repère seul.
    """
    vue = depuis_exif(
        MetadonneesPhoto(nom="vue.jpg", lat=LAT, lon=LON, cap_deg=340.0)
    )
    assert vue.cap_deg == 340.0
    assert vue.origine_cap == ORIGINE_EXIF
    assert not vue.cap_confirme
    assert not vue.dessine_un_cone


def test_un_cap_venu_de_la_carte_est_confirme_d_office():
    """La confirmation a déjà eu lieu, sur fond satellite, dans le rapport."""
    carte = lire_carte(_carte([_point(cap=340.0)]))
    vue = depuis_carte(carte.points[0])
    assert vue.origine_cap == ORIGINE_CARTE
    assert vue.cap_confirme
    assert vue.dessine_un_cone


def test_un_point_sans_cap_ne_dessine_pas_de_cone_et_ce_n_est_pas_une_erreur():
    """Le cas normal d'un drone : la position sans la direction."""
    vue = place_a_la_main("drone.jpg", 700000.0, 6800000.0)
    assert vue.cap_deg is None
    assert not vue.dessine_un_cone

    carte = lire_carte(_carte([_point(cap=None)]))
    assert depuis_carte(carte.points[0]).dessine_un_cone is False


def test_viser_sur_la_carte_de_l_application_confirme_le_cap():
    vue = place_a_la_main("vue.jpg", 700000.0, 6800000.0, 340.0)
    assert vue.cap_confirme and vue.dessine_un_cone


def test_une_photo_sans_position_ne_donne_pas_un_point_de_vue_invente():
    with pytest.raises(ErreurPhotoIllisible, match="position GPS"):
        depuis_exif(MetadonneesPhoto(nom="sans-gps.jpg"))


# ---------------------------------------------------------------------------
# Le contrat de la carte photos-geoloc
# ---------------------------------------------------------------------------


def test_une_carte_plus_recente_est_refusee_pas_lue_a_moitie():
    """Critère de validation 5 : refuser plutôt que lire au mieux.

    `photos-geoloc` la lit quand même avec un avertissement, ce qui convient à
    un rapport interne. Un dossier qui part à l'instruction, non.
    """
    with pytest.raises(ErreurCartePhotos, match="plus récent"):
        lire_carte(_carte([_point()], version=99))


def test_une_carte_ancienne_se_lit_sans_migration():
    """Avant la v3 il n'y a pas de `cap_brut` : le champ déduit est tout ce qu'on a."""
    ancien = _point(cap=340.0)
    del ancien["cap_brut"]
    del ancien["lat_brut"]
    del ancien["lon_brut"]
    carte = lire_carte(_carte([ancien], version=2))
    assert carte.points[0].cap_deg == pytest.approx(340.0)
    assert carte.points[0].lat == pytest.approx(LAT)


def test_un_fichier_qui_n_est_pas_une_carte_le_dit():
    with pytest.raises(ErreurCartePhotos, match="n'est pas une carte"):
        lire_carte(b"<html><body>bonjour</body></html>")


def test_les_points_en_corbeille_sont_ecartes_et_comptes():
    carte = lire_carte(
        _carte(
            [
                _point(identifiant=0, nom="gardee.jpg", ordre=0),
                _point(identifiant=1, nom="jetee.jpg", ordre=1, masque=True),
            ]
        )
    )
    assert [point.nom for point in carte.points] == ["gardee.jpg"]
    assert carte.masques == 1


def test_le_numero_est_le_rang_des_visibles_tries_par_ordre():
    """Le seul repère commun avec le chef de projet, qui l'a sur ses marqueurs.

    Mesuré le 15/09/2026 : `rendreMarqueurs()` numérote par `i + 1` sur
    `pointsVisibles()`, qui écarte les masqués **avant** de trier. Le numéro
    n'est donc pas la valeur du champ `ordre`, et la corbeille le décale — écart
    au brief du lot, qui l'annonçait calculé sur la liste complète.
    """
    carte = lire_carte(
        _carte(
            [
                _point(identifiant=7, nom="troisieme.jpg", ordre=30),
                _point(identifiant=3, nom="jetee.jpg", ordre=10, masque=True),
                _point(identifiant=5, nom="premiere.jpg", ordre=20),
            ]
        )
    )
    assert [(point.numero, point.nom) for point in carte.points] == [
        (1, "premiere.jpg"),
        (2, "troisieme.jpg"),
    ]


def test_la_calibration_de_la_boussole_est_appliquee():
    """L'offset global corrige un téléphone mal calibré, et suit la carte."""
    carte = lire_carte(_carte([_point(cap=10.0)], offset=-30.0))
    assert carte.points[0].cap_deg == pytest.approx(340.0)


def test_une_direction_figee_a_la_main_ignore_la_calibration():
    point = _point(cap=10.0, cap_manuel=125.0)
    point["cap"] = 125.0
    carte = lire_carte(_carte([point], offset=-30.0))
    assert carte.points[0].cap_deg == pytest.approx(125.0)


def test_un_cap_en_cache_qui_ment_est_signale_et_la_carte_fait_foi():
    """Le champ `cap` est un cache ; la page, elle, recalcule à l'affichage.

    Ce que le chef de projet a validé à l'écran est la valeur recalculée. Sur un
    fichier retouché hors de l'outil, les deux divergent : on retient ce qu'il a
    vu, et on le dit.
    """
    point = _point(cap=10.0)
    point["cap"] = 200.0  # le cache ne suit plus sa source
    carte = lire_carte(_carte([point]))
    assert carte.points[0].cap_deg == pytest.approx(10.0)
    assert any("retouché hors de l'outil" in message for message in carte.avertissements)


def test_une_position_replacee_a_la_main_l_emporte():
    """Décision du 10/09/2026 : elle vaut une position mesurée, sans mention."""
    point = _point(lat_manuel=49.0, lon_manuel=7.0)
    point["lat"], point["lon"] = 49.0, 7.0
    carte = lire_carte(_carte([point]))
    assert carte.points[0].lat == pytest.approx(49.0)
    assert carte.avertissements == ()


def test_l_emprise_du_rapport_est_lue_quand_elle_existe():
    emprise = {"nom": "site_polygone", "poches": [[[48.7, 6.6], [48.8, 6.7]]]}
    carte = lire_carte(_carte([_point()], emprise=emprise))
    assert carte.emprise_wgs84 == (((48.7, 6.6), (48.8, 6.7)),)


def test_une_carte_sans_emprise_ne_bloque_pas():
    """Les cartes d'avant la v5 n'en portent pas, et la nôtre fait foi."""
    assert lire_carte(_carte([_point()])).emprise_wgs84 is None


# ---------------------------------------------------------------------------
# La mémoire : les images ne doivent pas traverser la lecture
# ---------------------------------------------------------------------------


def test_les_images_sont_ecartees_avant_l_analyse():
    """Une carte de quarante photos pèse une vingtaine de mégaoctets de base64.

    Streamlit relit un fichier déposé à chaque exécution du script : le coût
    serait payé à chaque interaction, pas une fois.
    """
    lourde = "A" * 200_000
    document = _carte([_point(image=lourde), _point(identifiant=1, image=lourde)])
    carte = lire_carte(document)
    assert len(carte.points) == 2
    assert carte.avertissements == ()


def test_une_carte_sans_image_elaguable_se_lit_quand_meme_en_le_disant():
    """L'élagage est une optimisation, jamais une condition de justesse."""
    point = _point()
    del point["image"]
    carte = lire_carte(_carte([point]))
    assert len(carte.points) == 1
    assert any("en entier en mémoire" in message for message in carte.avertissements)


def test_le_bloc_se_cherche_par_la_fin():
    """Le bloc est écrit après Leaflet inliné : un scan avant le traverserait.

    Le leurre placé avant vérifie que c'est bien la dernière occurrence qui est
    retenue, et pas la première.
    """
    document = _carte([_point(nom="vraie.jpg")])
    leurre = b'<script id="donnees-carte" type="application/json">{"version":5,"points":[]}</script>'
    carte = lire_carte(document.replace(b"<body>", b"<body>" + leurre, 1))
    assert [point.nom for point in carte.points] == ["vraie.jpg"]


# ---------------------------------------------------------------------------
# La lecture EXIF, et ses replis qui ne sont jamais muets
# ---------------------------------------------------------------------------


def test_la_position_et_le_cap_se_lisent_dans_l_exif(tmp_path):
    chemin = _photo(tmp_path / "vue.jpg", gps=_gps(48.5, 6.5, cap=340.0, precision=4.2))
    metadonnees = lecture_exif.lire_metadonnees(chemin)
    assert metadonnees.lat == pytest.approx(48.5, abs=1e-4)
    assert metadonnees.lon == pytest.approx(6.5, abs=1e-4)
    assert metadonnees.cap_deg == pytest.approx(340.0)
    assert metadonnees.precision_m == pytest.approx(4.2)
    assert metadonnees.avertissements == ()


def test_une_photo_sans_gps_avertit_sans_lever(tmp_path):
    """Le cas d'un photomontage : un rendu n'est allé sur aucun terrain."""
    metadonnees = lecture_exif.lire_metadonnees(_photo(tmp_path / "montage.jpg"))
    assert not metadonnees.geolocalisee
    assert any("placez son point de vue" in m for m in metadonnees.avertissements)


def test_une_position_peu_fiable_est_signalee_jamais_ecartee(tmp_path):
    """Un cas réel a placé une photo à 4 km de son emplacement.

    À l'échelle d'une visite, 100 m ne veulent plus rien dire — on change de
    parcelle. La photo reste, et c'est au chef de projet de juger.
    """
    chemin = _photo(tmp_path / "loin.jpg", gps=_gps(cap=None, precision=4260.8))
    vue = depuis_exif(lecture_exif.lire_metadonnees(chemin))
    assert vue.position_peu_fiable


def test_une_precision_inconnue_n_est_pas_une_mauvaise_precision(tmp_path):
    """La plupart des applications photo n'écrivent pas ce champ."""
    chemin = _photo(tmp_path / "vue.jpg", gps=_gps())
    vue = depuis_exif(lecture_exif.lire_metadonnees(chemin))
    assert vue.precision_m is None
    assert not vue.position_peu_fiable


def test_un_cap_magnetique_est_repris_tel_quel_mais_annonce(tmp_path):
    """1 à 2° en France, sous la précision d'une boussole de téléphone.

    On ne corrige donc pas — mais on ne le tait pas non plus.
    """
    chemin = _photo(
        tmp_path / "vue.jpg", gps=_gps(cap=340.0, reference_cap="M")
    )
    metadonnees = lecture_exif.lire_metadonnees(chemin)
    assert metadonnees.cap_deg == pytest.approx(340.0)
    assert any("magnétique" in message for message in metadonnees.avertissements)


def test_le_heic_est_refuse_en_disant_quoi_faire(tmp_path):
    """Sans `pillow-heif`, une erreur Pillow n'aurait pas désigné la vraie cause."""
    chemin = tmp_path / "IMG_0001.HEIC"
    chemin.write_bytes(b"pas vraiment un heic")
    with pytest.raises(ErreurPhotoIllisible, match="photos-geoloc"):
        lecture_exif.lire_metadonnees(chemin)


def test_un_fichier_qui_n_est_pas_une_image_le_dit(tmp_path):
    chemin = tmp_path / "notice.jpg"
    chemin.write_bytes(b"%PDF-1.4 en realite")
    with pytest.raises(ErreurPhotoIllisible, match="ne s'ouvre pas"):
        lecture_exif.lire_metadonnees(chemin)


def test_le_nom_affiche_prend_le_pas_sur_le_fichier_temporaire(tmp_path):
    """Une photo déposée dans Streamlit vit sous un nom qui ne dirait rien."""
    chemin = _photo(tmp_path / "tmp8f3a2b.jpg", gps=_gps())
    metadonnees = lecture_exif.lire_metadonnees(chemin, nom="Vue depuis la RD 48.jpg")
    assert metadonnees.nom == "Vue depuis la RD 48.jpg"


# ---------------------------------------------------------------------------
# Le passage en Lambert 93, où tout le traitement géométrique vit
# ---------------------------------------------------------------------------


def test_le_point_de_vue_est_en_lambert_93():
    """Repère : la France métropolitaine tient dans ces bornes."""
    vue = depuis_carte(lire_carte(_carte([_point()])).points[0])
    assert 100_000 < vue.x < 1_300_000
    assert 6_000_000 < vue.y < 7_200_000
    assert vue.point.x == pytest.approx(vue.x)


def test_deux_points_de_vue_gardent_leur_distance_terrain():
    """0,001° de latitude vaut environ 111 m : la reprojection ne les rapproche pas."""
    carte = lire_carte(
        _carte(
            [
                _point(identifiant=0, ordre=0, lat=LAT, lon=LON),
                _point(identifiant=1, ordre=1, lat=LAT + 0.001, lon=LON),
            ]
        )
    )
    premier, second = (depuis_carte(point) for point in carte.points)
    assert premier.point.distance(second.point) == pytest.approx(111.0, abs=2.0)
