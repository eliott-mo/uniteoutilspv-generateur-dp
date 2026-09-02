"""Exceptions nommées du générateur DP.

Règle du lot : aucun repli silencieux. Chaque situation anormale lève une
exception explicite plutôt que de produire une planche fausse mais d'aspect
correct.
"""


class ErreurDP(Exception):
    """Base de toutes les erreurs du générateur."""


class ErreurEmprise(ErreurDP):
    """Le fichier d'emprise est illisible, vide ou dégénéré."""


class ErreurCRS(ErreurDP):
    """Le système de coordonnées du fichier d'emprise est absent ou refusé."""


class ErreurEchelle(ErreurDP):
    """Aucune échelle normalisée ne convient, ou échelle incohérente."""


class ErreurService(ErreurDP):
    """Un service IGN (WMS-R ou WFS) n'a pas répondu comme attendu."""


class ErreurPolice(ErreurDP):
    """La police de composition n'est pas disponible pour le moteur de rendu."""


class ErreurRendu(ErreurDP):
    """La conversion SVG vers PDF a échoué."""


class ErreurHelioScope(ErreurDP):
    """L'export HelioScope est illisible, incomplet ou ne suit pas le modèle."""


class ErreurModulesAbsents(ErreurHelioScope):
    """Le DXF ne porte aucun module : export réalisé trop tôt."""


class ErreurCalage(ErreurHelioScope):
    """Le calage géographique du DXF est impossible ou invalide."""
