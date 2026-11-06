"""Préparation commune aux tests."""

import pytest

from dp_socle.environnement import preparer_cairo
from dp_socle.polices import installer_polices

from .sans_reseau import couper

preparer_cairo()

# Aptos se copie pour fontconfig avant que le premier test compose une lettre,
# comme `app.py` le fait au démarrage, avant tout rendu. Copiée plus tard — par
# le premier test qui joue `app.py` —, elle arrivait après que le lot 7 avait
# figé la police de la session sur Liberation Sans ; et le dossier de polices
# modifié sous un fontconfig déjà chargé le faisait se relire en cours de
# session, après quoi cairo sortait chaque glyphe des planches suivantes dans
# sa propre police — 582 sur une DP 4-1, sans plus une espace lisible. C'était
# la suite Linux du 28/09 au 06/11/2026 ; voir le README, « La suite tourne
# aussi sur Linux ». Sans effet sous Windows, où cairo passe par DirectWrite.
installer_polices()


@pytest.fixture(autouse=True)
def sans_reseau(request, monkeypatch):
    """Aucun test ne sort, sauf ceux qui portent la marque `reseau`.

    Ce n'est pas une commodité d'exécution hors ligne : c'est ce qui rend la
    marque vraie. Voir `tests/sans_reseau.py` pour ce que son absence a coûté.
    """
    if request.node.get_closest_marker("reseau"):
        return
    couper(monkeypatch)
