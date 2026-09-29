"""Préparation commune aux tests."""

import pytest

from dp_socle.environnement import preparer_cairo

from .sans_reseau import couper

preparer_cairo()


@pytest.fixture(autouse=True)
def sans_reseau(request, monkeypatch):
    """Aucun test ne sort, sauf ceux qui portent la marque `reseau`.

    Ce n'est pas une commodité d'exécution hors ligne : c'est ce qui rend la
    marque vraie. Voir `tests/sans_reseau.py` pour ce que son absence a coûté.
    """
    if request.node.get_closest_marker("reseau"):
        return
    couper(monkeypatch)
