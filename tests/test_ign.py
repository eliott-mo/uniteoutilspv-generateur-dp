"""La session de la Géoplateforme : une seule, et un contexte TLS chargé une fois.

requests 2.33 et urllib3 2.6 rechargeaient le magasin de certificats de certifi
à chaque nouvelle connexion — de 0,3 à 4 s sur un poste Windows —, et la
Géoplateforme ferme une connexion inactive en moins de 15 s (mesuré le
24/09/2026). Ce qui se vérifie ici : la vérification des certificats n'a rien
perdu, la session partagée ne garde rien d'un utilisateur à l'autre, une
nouvelle connexion ne recharge plus rien, et une reprise après un échec part
d'une connexion neuve, comme avant la session partagée.

La pagination du WFS, aussi : jusqu'au 03/11/2026, une lecture qui atteignait
son plafond rendait ses premières entités sans le dire. Elle lève désormais, et
sous le plafond rien n'a changé.
"""

from __future__ import annotations

import io
import ssl
import urllib.request
from email.message import Message

import pytest
from PIL import Image

from dp_socle import ign
from dp_socle.erreurs import ErreurPlafondWFS


def test_une_seule_session_qui_verifie_certificat_et_nom_d_hote():
    session = ign._session()
    assert ign._session() is session
    adaptateur = session.get_adapter(ign.URL_WMS)
    assert isinstance(adaptateur, ign._AdaptateurTLS)
    contexte = adaptateur._contexte
    assert contexte.verify_mode == ssl.CERT_REQUIRED
    assert contexte.check_hostname
    # Les autorités de requests — celles de certifi —, chargées dans le contexte.
    assert contexte.cert_store_stats()["x509_ca"] > 100


class _ReponseQuiPoseUnCookie:
    """Ce que `CookieJar.extract_cookies` lit d'une réponse : ses en-têtes."""

    def info(self):
        entetes = Message()
        entetes["Set-Cookie"] = "noeud=wms-b; Path=/"
        return entetes


def test_la_session_partagee_ne_garde_aucun_cookie():
    """Partagée par toutes les sessions de l'application, elle ne passe rien de l'une à l'autre."""
    cookies = ign._session().cookies
    try:
        cookies.extract_cookies(_ReponseQuiPoseUnCookie(), urllib.request.Request(ign.URL_WMS))
        assert len(cookies) == 0
    finally:
        cookies.clear()


class _Reponse:
    """Ce que le module lit d'une réponse HTTP."""

    def __init__(self, statut: int, type_contenu: str, contenu: bytes = b"", donnees=None):
        self.status_code = statut
        self.headers = {"content-type": type_contenu}
        self.content = contenu
        self.text = contenu.decode("latin-1")
        self._donnees = donnees

    def json(self):
        return self._donnees


class _NoeudDefaillant:
    """Une session dont la connexion ouverte mène à un nœud en panne.

    Tant qu'elle n'est pas refermée, chaque requête rend `panne` ; une
    connexion neuve trouve un nœud sain, qui rend `saine`.
    """

    def __init__(self, panne: _Reponse, saine: _Reponse):
        self.panne, self.saine = panne, saine
        self.fermetures = 0

    def get(self, url, params=None, headers=None, timeout=None):
        return self.saine if self.fermetures else self.panne

    def close(self):
        self.fermetures += 1


def _jpeg(taille: tuple) -> bytes:
    flux = io.BytesIO()
    Image.new("RGB", taille, (90, 120, 60)).save(flux, "JPEG")
    return flux.getvalue()


def test_une_reprise_du_wms_passe_par_une_connexion_neuve(monkeypatch):
    """Réutilisée, la connexion ramenait les trois tentatives au même échec."""
    session = _NoeudDefaillant(
        _Reponse(400, "text/xml", b'<ServiceException code="LayerNotDefined"/>'),
        _Reponse(200, "image/jpeg", _jpeg((76, 76))),
    )
    monkeypatch.setattr(ign, "_session", lambda: session)
    monkeypatch.setattr(ign.time, "sleep", lambda _: None)
    with pytest.warns(RuntimeWarning, match="tentative 1 sur 3"):
        fond = ign.telecharger_fond(ign.COUCHE_ORTHO, (0.0, 0.0, 50.0, 50.0), 20.0, 20.0, dpi=96)
    assert fond.tentatives == 2
    assert session.fermetures == 1


def test_une_reprise_du_rge_alti_passe_par_une_connexion_neuve(monkeypatch):
    session = _NoeudDefaillant(
        _Reponse(503, "text/plain", b"Service Unavailable"),
        _Reponse(200, "application/json", donnees={"elevations": [101.5]}),
    )
    monkeypatch.setattr(ign, "_session", lambda: session)
    monkeypatch.setattr(ign.time, "sleep", lambda _: None)
    with pytest.warns(RuntimeWarning, match="tentative 1 sur 3"):
        altitudes = ign.telecharger_altitudes([(650_000.0, 6_750_000.0)])
    assert altitudes == [101.5]
    assert session.fermetures == 1


@pytest.mark.reseau
def test_une_nouvelle_connexion_ne_recharge_pas_les_certificats(monkeypatch):
    """Deux fonds demandés sur deux connexions neuves : aucun rechargement.

    Fermer les connexions de la session avant chaque requête, c'est ce qui
    arrive entre deux clics : la Géoplateforme ne les garde pas 15 s.
    """
    ign._session()  # le contexte se charge ici, une fois, s'il ne l'est pas déjà
    chargements = []
    charger = ssl.SSLContext.load_verify_locations

    def compter(contexte, *args, **kwargs):
        chargements.append(args or kwargs)
        return charger(contexte, *args, **kwargs)

    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", compter)
    for _ in range(2):
        ign._session().close()
        fond = ign.telecharger_fond(
            ign.COUCHE_ORTHO, (745_800.0, 6_625_800.0, 745_850.0, 6_625_850.0), 20.0, 20.0, dpi=96
        )
        assert fond.image.size == (76, 76)
    assert chargements == []


class _WfsFeint:
    """Un WFS qui porte `nombre` entités et les sert par pages.

    Il lit `COUNT` et `STARTINDEX` et rend la tranche demandée, avec les
    décomptes du vrai service (relevés sur la Géoplateforme le 03/11/2026) :
    une page est pleine tant qu'il reste de quoi la remplir. `debuts` garde le
    `STARTINDEX` de chaque requête reçue.
    """

    def __init__(self, nombre: int, entite):
        self.nombre, self.entite = nombre, entite
        self.debuts: list[int] = []

    def get(self, url, params=None, headers=None, timeout=None):
        debut = int(params["STARTINDEX"])
        self.debuts.append(debut)
        fin = min(debut + int(params["COUNT"]), self.nombre)
        page = [self.entite(rang) for rang in range(debut, fin)]
        return _Reponse(
            200,
            "application/json",
            donnees={
                "type": "FeatureCollection",
                "features": page,
                "totalFeatures": self.nombre,
                "numberMatched": self.nombre,
                "numberReturned": len(page),
            },
        )

    def close(self):
        pass


#: Emprise des lectures : 2 km de côté, de quoi loger 7 500 entités.
_BBOX = (745_800.0, 6_625_800.0, 747_800.0, 6_627_800.0)


def _coin(rang: int) -> tuple[float, float]:
    """Coin sud-ouest de l'entité de rang `rang`, sur une grille de 20 m : il dit laquelle est rendue."""
    return (_BBOX[0] + 20.0 * (rang % 100), _BBOX[1] + 20.0 * (rang // 100))


def _carre(rang: int) -> dict:
    x, y = _coin(rang)
    anneau = [[x, y], [x + 10.0, y], [x + 10.0, y + 10.0], [x, y + 10.0], [x, y]]
    return {"type": "MultiPolygon", "coordinates": [[anneau]]}


def _batiment(rang: int) -> dict:
    """Une entité de `PARCELLAIRE_EXPRESS:batiment`, telle que le service la rend."""
    return {
        "type": "Feature",
        "id": f"batiment.{rang}",
        "geometry": _carre(rang),
        "geometry_name": "geom",
        "properties": {"gid": rang, "type": "Bâtiment en dur", "code_dep": "45", "code_insee": "45286"},
    }


def _parcelle(rang: int) -> dict:
    """Une entité de `PARCELLAIRE_EXPRESS:parcelle`, telle que le service la rend."""
    numero = f"{rang:04d}"
    return {
        "type": "Feature",
        "id": f"parcelle.{rang}",
        "geometry": _carre(rang),
        "geometry_name": "geom",
        "properties": {
            "gid": rang,
            "numero": numero,
            "feuille": 1,
            "section": "AK",
            "code_dep": "45",
            "nom_com": "Saint-Jean-le-Blanc",
            "code_com": "286",
            "com_abs": "000",
            "code_arr": "000",
            "idu": f"45286000AK{numero}",
            "contenance": 655,
            "code_insee": "45286",
        },
    }


@pytest.mark.parametrize(
    "nombre, debuts",
    [
        (2500, [0, 1000, 2000]),
        # Quatre pages pleines, puis une vide : la page pleine d'avant le
        # plafond ne lève pas.
        (4000, [0, 1000, 2000, 3000, 4000]),
        # La dernière page sous le plafond, à une entité près.
        (4999, [0, 1000, 2000, 3000, 4000]),
    ],
    ids=["2500", "4000", "4999"],
)
def test_sous_le_plafond_une_page_incomplete_termine_la_lecture(monkeypatch, nombre, debuts):
    service = _WfsFeint(nombre, _batiment)
    monkeypatch.setattr(ign, "_session", lambda: service)
    batiments = ign.telecharger_batiments(_BBOX, taille_page=1000, maximum=5000)
    # Toutes les entités du service, chacune une fois, dans l'ordre où il les sert.
    assert [b.geometrie.bounds[:2] for b in batiments] == [_coin(rang) for rang in range(nombre)]
    assert service.debuts == debuts


@pytest.mark.parametrize(
    "telecharger, entite, service_nomme",
    [
        (ign.telecharger_batiments, _batiment, "bâtiments"),
        (ign.telecharger_parcelles, _parcelle, "cadastre"),
    ],
    ids=["batiments", "parcelles"],
)
def test_au_plafond_la_lecture_leve_plutot_que_de_rendre_une_liste_tronquee(
    monkeypatch, telecharger, entite, service_nomme
):
    """7 500 entités sur l'emprise, un plafond de 5 000 : la boucle rendait les 5 000 premières.

    Sans un mot. Le lot 10 cherche dans ces bâtiments l'habitation la plus
    proche de la clôture : elle pouvait être celle qui manquait.
    """
    service = _WfsFeint(7500, entite)
    monkeypatch.setattr(ign, "_session", lambda: service)
    with pytest.raises(ErreurPlafondWFS) as erreur:
        telecharger(_BBOX, taille_page=1000, maximum=5000)
    message = str(erreur.value)
    assert service_nomme in message
    assert str(_BBOX) in message
    assert "5000" in message
    # Le plafond n'est pas relevé en cachette : rien n'est demandé au-delà.
    assert service.debuts == [0, 1000, 2000, 3000, 4000]
