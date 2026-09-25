"""DP 6 — Insertions paysagères : une planche par point de vue (lot 6).

Le dossier de référence en porte deux, « Vue A » et « Vue B », parce que Massay
avait deux photomontages — pas parce que la pièce en demande deux. Le cas
courant est **une** planche.

LES TROIS VOLETS, ET POURQUOI LE TROISIÈME EST FACULTATIF
----------------------------------------------------------
Une planche décline le **même** point de vue, dans cet ordre relevé le
10/09/2026 sur les pages 12 et 13 de Massay :

1. l'image brute, l'état actuel, le projet absent ;
2. la même image avec le photomontage ;
3. le même photomontage avec l'aménagement paysager.

Le troisième n'existe que s'il y a des mesures paysagères, et tous les projets
n'en portent pas. Les deux premiers, eux, sont indissociables : c'est la
comparaison avant/après qui fait la pièce, et une image seule ne compare rien.
Une vue à une seule image est donc refusée, jamais complétée en silence.

Le point de vue est celui de l'**image brute** : un photomontage est un rendu,
il ne porte aucun EXIF et n'est allé sur aucun terrain. Les volets (ii) et (iii)
héritent donc de sa position et de sa direction, puisque c'est la même prise de
vue.
"""

from __future__ import annotations

from pathlib import Path

from ..dossier import piece
from ..erreurs import ErreurComposition
from ..projet import Projet
from .commun import Sortie, nouvelle_planche
from .photographies import ImagePlanche, composer
from .reperage_vues import repere_de_vue

CODE = "DP 6"

#: Intitulés des trois volets, relevés sur le dossier de référence. Ils sont
#: préfixés du repère de la vue : « Vue A : Emplacement du projet ».
INTITULES = (
    "Emplacement du projet",
    "Projet dans son environnement",
    "Projet avec mesures paysagères",
)


def generer(
    projet: Projet,
    point_de_vue,
    images,
    emprise,
    dossier: str | Path,
    contrat=None,
    rang: int = 1,
    numero: str | None = None,
    cadrages=None,
    fond_ign: bool = True,
) -> Sortie:
    """Une planche d'insertion paysagère, pour un point de vue et ses volets.

    `images` porte deux ou trois chemins, dans l'ordre des volets. `rang` est le
    rang de la vue dans la pièce, qui lui donne sa lettre.
    """
    images = [Path(chemin) for chemin in images]
    repere = repere_de_vue(CODE, rang)

    if len(images) < 2:
        raise ErreurComposition(
            f"{repere} : {len(images)} image(s) déposée(s). Une insertion "
            "paysagère compare l'état actuel et le projet — il en faut au moins "
            "deux, l'image brute et son photomontage."
        )
    if len(images) > len(INTITULES):
        raise ErreurComposition(
            f"{repere} : {len(images)} images pour une même vue, alors que la "
            f"pièce en décline {len(INTITULES)} au plus "
            f"({', '.join(INTITULES)}). Une vue de plus est une planche de plus."
        )

    planche = nouvelle_planche(projet, CODE, numero=numero)
    retenu = composer(
        planche,
        [
            ImagePlanche(chemin, f"{repere} : {intitule}", cadrage)
            for chemin, intitule, cadrage in zip(
                images, INTITULES, _cadrages(cadrages, len(images))
            )
        ],
        [point_de_vue],
        [repere],
        emprise,
        f"{repere} — plan de repérage",
        contrat,
        emplacements=len(INTITULES),
        fond_ign=fond_ign,
    )

    if len(images) == 2:
        # L'emplacement du troisième volet reste vide plutôt que d'étirer les
        # deux autres : la planche d'un dossier sans mesures paysagères garde la
        # même géométrie que celle d'un dossier qui en porte.
        retenu["avertissements"].append(
            f"{repere} : pas de volet « {INTITULES[2]} », son emplacement reste "
            "vide. C'est normal si le projet ne porte pas de mesures paysagères."
        )

    chemin = planche.rendre_pdf(
        Path(dossier) / f"DP_6_insertion_{repere.split()[-1].lower()}.pdf"
    )
    return Sortie(
        numero=CODE,
        titre=piece(CODE).titre,
        chemin=chemin,
        echelle=retenu["echelle_reperage"],
        planche=planche,
        details={"repere": repere, "volets": len(images), **retenu},
    )


def _cadrages(cadrages, nombre: int) -> list:
    """Un décalage de rognage par image, centré à défaut."""
    cadrages = list(cadrages or [])
    return [
        tuple(cadrages[rang]) if rang < len(cadrages) else (0.0, 0.0)
        for rang in range(nombre)
    ]
