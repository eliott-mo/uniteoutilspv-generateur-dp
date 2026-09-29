"""Coupe le réseau pour tout test qui ne porte pas la marque `reseau`.

POURQUOI CE GARDE-FOU EXISTE
----------------------------
La marque `reseau` sépare les tests qui interrogent la Géoplateforme de ceux
qui mesurent le montage. La CI joue les seconds à chaque poussée, et c'est
d'eux qu'elle tire son vert. Encore faut-il que la séparation soit vraie.

Le 28/09/2026 elle ne l'était pas. `tests/test_sortie_pptx_lot8.py` remplaçait
les trois appels IGN par des doublures, mais les planches écrivent
`from ..ign import telecharger_fond` : le nom est lié à l'import, et remplacer
l'attribut du module `ign` ne les atteignait pas. La doublure n'a jamais servi
— ces tests interrogeaient le vrai service à chaque passage, sans porter la
marque. Un hoquet du service ce soir-là, et la CI est tombée deux fois de
suite sur du code sain, avant de repasser au vert le lendemain sans qu'une
ligne ait changé.

Rien dans le dépôt ne pouvait le dire : un test qui sort sans le déclarer
passe tant que le service répond. C'est cette coupure qui l'a trouvé, et
c'est pour qu'elle le retrouve seule qu'elle est ici plutôt que dans un
fichier de passage.

CE QU'ELLE NE COUVRE PAS
------------------------
Les connexions TCP, c'est-à-dire tout ce qui monte en HTTP. Une résolution de
nom seule ne passe pas par `connect` et n'est pas vue ; elle ne sert à rien
sans la connexion qui suit.
"""

from __future__ import annotations

import socket


class ReseauCoupe(BaseException):
    """Un test non marqué `reseau` a tenté de sortir.

    Dérive de `BaseException` et non d'`Exception` **à dessein** : le code de
    production attrape les pannes réseau pour les dire proprement, et un
    `except Exception` avalerait celle-ci. Le test passerait alors en cachant
    la dépendance que cette coupure sert justement à interdire.
    """


def _adresse(arguments) -> str:
    """L'hôte visé, tel qu'on peut le lire des arguments de l'appel."""
    for valeur in arguments:
        if isinstance(valeur, tuple) and valeur:
            return f"{valeur[0]}:{valeur[1]}" if len(valeur) > 1 else str(valeur[0])
    return "une adresse extérieure"


def couper(substitution) -> None:
    """Remplace les deux voies de connexion sortante par un refus nommé.

    `substitution` est un `monkeypatch` : la coupure se défait donc avec lui,
    à la fin du test.
    """

    def refuser(*arguments, **_):
        raise ReseauCoupe(
            f"Ce test a tenté de joindre {_adresse(arguments)} sans porter la "
            "marque `reseau`. Soit il mesure le montage et doit remplacer le "
            "service par une doublure — en suivant chaque module qui en tient "
            "une référence, voir `tests/test_sortie_pptx_lot8.py` —, soit il "
            "mesure le service et doit porter la marque."
        )

    substitution.setattr(socket.socket, "connect", refuser)
    substitution.setattr(socket, "create_connection", refuser)
