"""Où l'outil écrit ses fichiers de travail, et ce qu'il en dit.

Signalé en usage réel le 16/09/2026 : un `PermissionError` sur un DXF que
OneDrive tenait ouvert. Le correctif d'écriture a refermé l'essentiel de la
fenêtre ; ces dossiers n'ont pour autant rien à faire dans un espace
synchronisé, et l'outil doit le dire.
"""

from __future__ import annotations

from pathlib import Path

from dp_socle.environnement import (
    NOMS_TRAVAIL,
    VARIABLE_TRAVAIL,
    dossiers_de_travail,
    etat_travail,
)


def test_sans_variable_les_dossiers_restent_ou_ils_etaient(monkeypatch):
    """La cible de déploiement n'a rien à changer : Linux, chemins relatifs."""
    monkeypatch.delenv(VARIABLE_TRAVAIL, raising=False)
    projets, sortie = dossiers_de_travail()
    assert projets == Path("projets") and sortie == Path("sortie")
    assert not projets.is_absolute()


def test_la_variable_deplace_les_deux_dossiers(monkeypatch, tmp_path):
    monkeypatch.setenv(VARIABLE_TRAVAIL, str(tmp_path))
    projets, sortie = dossiers_de_travail()
    assert projets == tmp_path / "projets"
    assert sortie == tmp_path / "sortie"


def test_un_chemin_avec_tilde_est_developpe(monkeypatch):
    """« ~/travail » doit désigner le dossier de l'utilisateur, pas un dossier
    nommé « ~ » à côté du script."""
    monkeypatch.setenv(VARIABLE_TRAVAIL, "~/travail-dp")
    projets, _ = dossiers_de_travail()
    assert "~" not in str(projets)
    assert projets == Path.home() / "travail-dp" / "projets"


def test_un_dossier_synchronise_est_signale(monkeypatch, tmp_path):
    """La détection lit les variables posées par le client OneDrive lui-même.

    Chercher « OneDrive » dans le chemin se tromperait sur un dossier local
    simplement nommé ainsi.
    """
    racine = tmp_path / "OneDrive - Unite"
    (racine / "depot").mkdir(parents=True)
    monkeypatch.setenv("OneDriveCommercial", str(racine))
    monkeypatch.setenv(VARIABLE_TRAVAIL, str(racine / "depot"))

    etat = etat_travail()
    assert etat.synchronise
    assert VARIABLE_TRAVAIL in etat.message
    assert "OneDrive" in etat.message


def test_un_dossier_local_ne_declenche_aucune_alerte(monkeypatch, tmp_path):
    for variable in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv(VARIABLE_TRAVAIL, str(tmp_path))
    etat = etat_travail()
    assert not etat.synchronise
    assert str(tmp_path) in etat.message


def test_un_dossier_voisin_de_onedrive_n_est_pas_dedans(monkeypatch, tmp_path):
    """Un chemin qui commence par les mêmes lettres n'est pas un sous-dossier.

    « OneDrive-local » et « OneDrive » se ressemblent ; seule la comparaison par
    segments les distingue.
    """
    (tmp_path / "OneDrive").mkdir()
    voisin = tmp_path / "OneDrive-local"
    voisin.mkdir()
    monkeypatch.setenv("OneDrive", str(tmp_path / "OneDrive"))
    monkeypatch.setenv(VARIABLE_TRAVAIL, str(voisin))
    assert not etat_travail().synchronise


def test_les_deux_dossiers_sont_ceux_que_l_outil_ecrit():
    assert NOMS_TRAVAIL == ("projets", "sortie")
