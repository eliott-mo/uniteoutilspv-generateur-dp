"""La session de la Géoplateforme : une seule, et un contexte TLS chargé une fois.

requests 2.33 et urllib3 2.6 rechargeaient le magasin de certificats de certifi
à chaque nouvelle connexion — de 0,3 à 4 s sur un poste Windows —, et la
Géoplateforme ferme une connexion inactive en moins de 15 s (mesuré le
24/09/2026). Ce qui se vérifie ici : la vérification des certificats n'a rien
perdu, la session partagée ne garde rien d'un utilisateur à l'autre, une
nouvelle connexion ne recharge plus rien, et une reprise après un échec part
d'une connexion neuve, comme avant la session partagée.
"""

from __future__ import annotations

import io
import ssl
import urllib.request
from email.message import Message

import pytest
from PIL import Image

from dp_socle import ign


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
