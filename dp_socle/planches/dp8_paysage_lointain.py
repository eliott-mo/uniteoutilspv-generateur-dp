"""DP 8 — Photographies du paysage lointain (lot 6).

Une planche unique, portant **une ou deux** photographies et leur plan de
repérage. Les prises de vue y sont numérotées `PC8-1` et `PC8-2`, forme
relevée le 10/09/2026 sur la page 15 du dossier de référence : les services
instructeurs y sont habitués, et c'est la raison qui a présidé au choix des
intitulés dans `dp_socle/dossier.py`.

C'est la pièce du **lointain**, mais lointain reste relatif : quelques
centaines de mètres du site, un gros kilomètre au plus (mesuré le
16/09/2026 sur l'usage réel). Massay la porte au 1/6 500, que notre liste
d'échelles arrondit au 1/7 500.

La numérotation repart de 1 pour cette pièce. Celle d'un rapport de visite
compte tous les points de la visite et n'aurait pas le même sens ici.
"""

from __future__ import annotations

from pathlib import Path

from ..dossier import piece
from ..erreurs import ErreurComposition
from ..projet import Projet
from .commun import Sortie, nouvelle_planche
from .photographies import ImagePlanche, composer
from .reperage_vues import repere_de_vue

CODE = "DP 8"

#: Intitulé porté par chaque cadre d'image, préfixé du repère de la prise de vue.
INTITULE = "Photographie du paysage lointain"

#: Au-delà, la planche ne les logerait plus à une taille lisible — et la pièce
#: n'en demande pas davantage.
PRISES_MAXIMALES = 2


def generer(
    projet: Projet,
    prises,
    emprise,
    dossier: str | Path,
    numero: str | None = None,
    cadrages=None,
    fond_ign: bool = True,
) -> Sortie:
    """La planche de la pièce, pour une ou deux prises de vue.

    `prises` porte des couples `(point_de_vue, chemin_image)`, dans l'ordre où
    les repères doivent être numérotés.
    """
    prises = list(prises)
    if not prises:
        raise ErreurComposition(
            "DP 8 : aucune photographie déposée. La pièce ne se produit pas vide."
        )
    if len(prises) > PRISES_MAXIMALES:
        raise ErreurComposition(
            f"{CODE} : {len(prises)} photographies déposées, pour "
            f"{PRISES_MAXIMALES} "
            "au plus sur une planche. Retirez-en, ou traitez le surplus dans une "
            "pièce jointe libre."
        )

    points_de_vue = [prise[0] for prise in prises]
    reperes = [repere_de_vue(CODE, rang) for rang in range(1, len(prises) + 1)]

    planche = nouvelle_planche(projet, CODE, numero=numero)
    retenu = composer(
        planche,
        [
            ImagePlanche(Path(prise[1]), f"{repere} : {INTITULE}", cadrage)
            for prise, repere, cadrage in zip(
                prises, reperes, _cadrages(cadrages, len(prises))
            )
        ],
        points_de_vue,
        reperes,
        emprise,
        "DP 8 — plan de repérage",
        emplacements=PRISES_MAXIMALES,
        fond_ign=fond_ign,
    )

    chemin = planche.rendre_pdf(Path(dossier) / "DP_8_paysage_lointain.pdf")
    return Sortie(
        numero=CODE,
        titre=piece(CODE).titre,
        chemin=chemin,
        echelle=retenu["echelle_reperage"],
        details={"reperes": reperes, **retenu},
    )


def _cadrages(cadrages, nombre: int) -> list:
    """Un décalage de rognage par photographie, centré à défaut."""
    cadrages = list(cadrages or [])
    return [
        tuple(cadrages[rang]) if rang < len(cadrages) else (0.0, 0.0)
        for rang in range(nombre)
    ]
