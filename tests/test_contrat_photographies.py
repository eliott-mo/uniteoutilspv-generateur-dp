"""Les prises de vue survivent à un rechargement (lot 6, étape 4).

Placer un point de vue est un geste qu'on ne refait pas volontiers : il vit donc
dans `projet.json`, à côté de `image_garde`, et non dans le contrat d'entrée du
lot 4 qui décrit le plan du bureau d'études et rien d'autre.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from dp_socle.erreurs import ErreurDP, ErreurPointDeVue
from dp_socle.points_de_vue import (
    ORIGINE_CARTE,
    PriseDeVue,
    place_a_la_main,
    prise_depuis_json,
    prise_en_json,
)
from dp_socle.projet import Projet

X0, Y0 = 622_000.0, 6_954_000.0


def _image(chemin):
    Image.new("RGB", (60, 40), (200, 200, 190)).save(chemin)
    return chemin


def _projet(tmp_path, photographies=None) -> Projet:
    emprise = tmp_path / "emprise.geojson"
    emprise.write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    return Projet(
        nom="sarnois", commune="Sarnois", code_postal="60210",
        date="2026-09-16", emprise=str(emprise), photographies=photographies,
    )


# ---------------------------------------------------------------------------
# L'aller-retour, qui est tout le contrat
# ---------------------------------------------------------------------------


def test_une_prise_de_vue_se_relit_a_l_identique():
    prise = PriseDeVue(
        point_de_vue=place_a_la_main("brute.jpg", X0, Y0, 95.0),
        images=("a.jpg", "b.jpg"),
        cadrages=((0.0, 0.0), (0.12, -0.25)),
    )
    assert prise_depuis_json(prise_en_json(prise)) == prise


def test_la_confirmation_du_cap_traverse_le_fichier():
    """C'est elle qui décide du cône : la perdre ferait disparaître la visée.

    Et la retrouver à tort en ferait apparaître une que personne n'a validée.
    """
    for confirme in (True, False):
        vue = place_a_la_main("v.jpg", X0, Y0, 95.0)
        vue = type(vue)(**{**vue.__dict__, "cap_confirme": confirme,
                           "origine_cap": ORIGINE_CARTE})
        relue = prise_depuis_json(
            prise_en_json(PriseDeVue(vue, ("a.jpg",)))
        ).point_de_vue
        assert relue.cap_confirme is confirme
        assert relue.dessine_un_cone is confirme


def test_le_fichier_ne_porte_pas_les_champs_deduits():
    """`dessine_un_cone` se recalcule.

    L'écrire permettrait à un fichier retouché à la main de faire dessiner un
    cône que la règle du cap refuse — le fichier ne porte que ce qui a été
    décidé.
    """
    ecrit = prise_en_json(
        PriseDeVue(place_a_la_main("v.jpg", X0, Y0, 95.0), ("a.jpg",))
    )
    assert "dessine_un_cone" not in ecrit["point_de_vue"]
    assert "cap_trigonometrique_deg" not in ecrit["point_de_vue"]


def test_une_prise_sans_position_est_refusee():
    with pytest.raises(ErreurPointDeVue, match="sans position"):
        prise_depuis_json({"images": ["a.jpg"], "point_de_vue": {"nom": "x"}})


def test_une_prise_sans_image_est_refusee():
    with pytest.raises(ErreurPointDeVue, match="sans image"):
        prise_depuis_json({"images": [], "point_de_vue": {"x": X0, "y": Y0}})


# ---------------------------------------------------------------------------
# Ce que le projet en fait
# ---------------------------------------------------------------------------


def test_le_projet_rend_les_prises_de_chaque_piece(tmp_path):
    prise = prise_en_json(
        PriseDeVue(place_a_la_main("v.jpg", X0, Y0), (str(_image(tmp_path / "a.jpg")),))
    )
    projet = _projet(tmp_path, {"DP 7": [prise], "DP 8": []})
    assert len(projet.prises_de("DP 7")) == 1
    assert projet.prises_de("DP 8") == []
    assert projet.prises_de("DP 6") == []


def test_une_image_declaree_mais_absente_bloque_au_demarrage(tmp_path):
    """Plus tôt le manque se signale, mieux c'est.

    Contrôlé ici et non à la composition : une planche qui échoue après le
    téléchargement de tous les fonds IGN fait perdre la génération entière.
    """
    prise = prise_en_json(
        PriseDeVue(place_a_la_main("v.jpg", X0, Y0), (str(tmp_path / "fantome.jpg"),))
    )
    projet = _projet(tmp_path, {"DP 7": [prise]})
    with pytest.raises(ErreurDP, match="image introuvable"):
        projet.valider_photographies()


def test_une_piece_qui_ne_decrit_pas_une_liste_est_refusee(tmp_path):
    projet = _projet(tmp_path, {"DP 7": {"images": ["a.jpg"]}})
    with pytest.raises(ErreurDP, match="ne décrit pas une liste"):
        projet.valider_photographies()


def test_les_chemins_d_images_sont_relatifs_au_projet_json(tmp_path):
    """Comme ceux de l'emprise et de la notice : un dossier se déplace."""
    dossier = tmp_path / "projets" / "sarnois"
    (dossier / "DP_7").mkdir(parents=True)
    _image(dossier / "DP_7" / "vue.jpg")
    (dossier / "emprise.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    (dossier / "projet.json").write_text(
        json.dumps(
            {
                "nom": "sarnois", "commune": "Sarnois", "code_postal": "60210",
                "date": "2026-09-16", "emprise": "emprise.geojson",
                "photographies": {
                    "DP 7": [
                        {
                            "images": ["DP_7/vue.jpg"],
                            "cadrages": [[0, 0]],
                            "point_de_vue": {"nom": "vue.jpg", "x": X0, "y": Y0},
                        }
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    projet = Projet.charger(dossier / "projet.json")
    image = projet.prises_de("DP 7")[0].images[0]
    assert Path(image).is_absolute() and Path(image).exists()


# ---------------------------------------------------------------------------
# Ce que le fichier écrit porte, et non ce qu'on souhaiterait qu'il porte
# ---------------------------------------------------------------------------


def _projet_ecrit(tmp_path):
    """Un projet complet, écrit comme l'application l'écrit. Rend (json, dossier)."""
    dossier = tmp_path / "projets" / "sarnois"
    (dossier / "DP_7").mkdir(parents=True)
    image = _image(dossier / "DP_7" / "vue.jpg")
    emprise = dossier / "emprise.geojson"
    emprise.write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    (dossier / "DP_11").mkdir()
    notice = dossier / "DP_11" / "notice.pdf"
    notice.write_bytes(b"%PDF-1.4")

    projet = Projet(
        nom="sarnois", commune="Sarnois", code_postal="60210",
        date="2026-09-16",
        # `str(Path)` est ce que l'application passe : c'est lui qu'on teste.
        emprise=str(emprise),
        notice=str(notice),
        photographies={
            "DP 7": [
                prise_en_json(
                    PriseDeVue(
                        point_de_vue=place_a_la_main("vue.jpg", X0, Y0, 95.0),
                        images=(str(image),),
                        cadrages=((0.0, 0.0),),
                    )
                )
            ]
        },
    )
    return projet.ecrire(dossier / "projet.json"), dossier


def test_le_fichier_ecrit_ne_porte_aucun_separateur_windows(tmp_path):
    """Mesuré le 24/09/2026 : `projet.json` était illisible sur la cible Linux.

    `str(Path)` rend des antislashs sous Windows. Le test voisin, qui écrivait
    lui-même le fichier avec des barres obliques, validait le format souhaité et
    jamais celui que `ecrire()` produit : le défaut a traversé tout le lot 6 sans
    se voir, et aurait bloqué la reprise d'un dossier au lot 7.
    """
    chemin, _ = _projet_ecrit(tmp_path)
    brut = chemin.read_text(encoding="utf-8")
    assert "\\" not in brut, brut


def test_les_chemins_ecrits_sont_relatifs_au_dossier_du_fichier(tmp_path):
    """Un dossier se déplace, et le ZIP de reprise du lot 7 le dépliera ailleurs.

    Des chemins absolus survivraient au déplacement sous Windows et nulle part
    ailleurs ; des chemins relatifs au dossier de lancement dépendraient de
    l'endroit d'où l'application a été lancée.
    """
    chemin, _ = _projet_ecrit(tmp_path)
    donnees = json.loads(chemin.read_text(encoding="utf-8"))

    assert donnees["emprise"] == "emprise.geojson"
    assert donnees["notice"] == "DP_11/notice.pdf"
    assert donnees["photographies"]["DP 7"][0]["images"] == ["DP_7/vue.jpg"]

    # Et le fichier écrit se relit, ce qui est tout l'objet de l'opération.
    projet = Projet.charger(chemin)
    relue = Path(projet.prises_de("DP 7")[0].images[0])
    assert relue.exists() and relue.is_absolute()


def test_un_projet_sans_photographies_reste_valide(tmp_path):
    """Le champ est facultatif : un dossier d'étude amont n'en a pas encore."""
    projet = _projet(tmp_path)
    projet.valider_photographies()
    assert projet.prises_de("DP 6") == []
