"""Générateur de dossier de déclaration préalable — socle (lot 1).

Moteur de planche A3 paysage et planches cartographiques DP 1-1, DP 1-2, DP 1-3.
"""

from .erreurs import (
    ErreurCRS,
    ErreurDP,
    ErreurEchelle,
    ErreurEmprise,
    ErreurPolice,
    ErreurRendu,
    ErreurService,
)
from .planche import Planche

__all__ = [
    "Planche",
    "ErreurDP",
    "ErreurEmprise",
    "ErreurCRS",
    "ErreurEchelle",
    "ErreurService",
    "ErreurPolice",
    "ErreurRendu",
]

__version__ = "1.0.0"
