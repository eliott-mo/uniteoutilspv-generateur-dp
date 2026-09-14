"""DP 11 — Notice, reprise du PDF fourni par le chef de projet.

L'outil n'écrit pas la notice : il l'habille. Chaque page du PDF déposé est
posée dans la zone de dessin d'une planche A3 paysage, sous le cadre et le
cartouche du dossier, de sorte que la pièce se feuillette comme les autres.

**Posée, pas rastérisée.** La page fournie est fusionnée telle quelle par
`pypdf.PageObject.merge_transformed_page` : son texte reste du texte dans le
dossier assemblé, sélectionnable et indexable par le service instructeur.
`tests/test_notice_lot5.py` le vérifie par extraction sur le PDF produit.

Trois écarts mesurés le 14/09/2026 entre le brief du lot et le résultat :

- la zone de dessin d'une planche à cartouche vaut bien **410 × 268 mm** à
  (5, 5) — elle est lue sur la planche elle-même (`zone_dessin()`), jamais
  recopiée — mais la notice n'y est pas posée à fleur : elle garde le **blanc
  tournant de 4 mm** des planches du lot 4, soit 402 × 260 mm utiles. Posée à
  fleur, une page qui peint son propre fond blanc — ce que font les exports
  d'Illustrator et les pages scannées — recouvrait la moitié du filet du cadre
  sur sa largeur, le filet étant centré sur la limite de la zone. Le facteur
  d'une A4 portrait passe donc de 0,9024 à **0,8754**, et le blanc latéral de
  110 à 113 mm de chaque côté. C'est le prix de la décision D1, une page
  fournie pour une page de dossier, et le sommaire y gagne de pointer une page
  juste ;
- une notice **déjà en A3 paysage plein format** ne passe pas au facteur 1,
  contrairement à ce qu'avançait D2, mais à 0,875 elle aussi : 420 × 297 mm ne
  tient pas dans 402 × 260 mm. Le facteur 1 ne concerne qu'une page composée
  aux dimensions exactes de la zone utile. Rien à corriger — le facteur se
  mesure page par page — mais l'écart est noté ici pour qu'il ne se
  redécouvre pas ;
- le texte de la notice **reste du texte** après fusion, mesuré par extraction
  à 30,3 mm et 43,8 mm du haut de la planche produite, à 8,95 pt pour 9,92 pt
  d'origine : le rapport des deux est le facteur appliqué, ce qui est la preuve
  qu'aucune rastérisation n'a eu lieu.
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.errors import PdfReadError

from ..dossier import piece
from ..erreurs import ErreurNotice
from ..planche import HAUTEUR_MM, Planche
from ..projet import Projet
from .commun import Sortie, nouvelle_planche
from .primitives import BLANC_TOURNANT_MM

#: Nom du PDF produit, dans le dossier de sortie du projet.
NOM_FICHIER = "DP_11_notice.pdf"

CODE = "DP 11"

MM_EN_PT = 72.0 / 25.4

#: En deçà de ce facteur d'ajustement, la notice est refusée (décision D2).
#:
#: Fixé à la mesure des formats qu'il admet, et non à l'estime : ajustée aux
#: 402 × 260 mm utiles, une page A4 portrait passe à 0,875, une A3 portrait à
#: 0,619, une A2 portrait à 0,438, une A1 portrait à 0,309 et une A0 à 0,219.
#: Le seuil laisse donc passer tout ce qui est une notice — jusqu'au A2, réduit
#: de plus de moitié mais encore lisible — et arrête ce qui n'en est pas : un
#: plan A1 ou A0 déposé par mégarde dans la case de la notice, dont le corps de
#: texte tomberait sous 3,5 pt. Un dossier qui part à l'instruction avec une
#: pièce illisible ne se rattrape pas.
FACTEUR_MINIMAL = 0.40

#: Au-dessous, la réduction est signalée au rapport.
#:
#: 0,60 est le facteur sous lequel un corps de 10 pt — celui des notices qui
#: circulent — descend sous 6 pt, la limite basse de ce qui s'imprime et se
#: lit. La notice n'est pas refusée pour autant : c'est au chef de projet de
#: décider s'il la refait à un autre format, mais il doit l'apprendre avant le
#: dépôt et non à l'instruction.
FACTEUR_ALERTE = 0.60

#: Formats normalisés reconnus, en millimètres, pour nommer ce qui a été lu.
#: La tolérance de 2 mm absorbe les arrondis de conversion points/millimètres
#: des générateurs de PDF, qui ne tombent pas tous sur la même décimale.
FORMATS_ISO = {
    "A0": (841.0, 1189.0),
    "A1": (594.0, 841.0),
    "A2": (420.0, 594.0),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "Letter": (215.9, 279.4),
}
TOLERANCE_FORMAT_MM = 2.0


def nom_format(largeur_mm: float, hauteur_mm: float) -> str:
    """« A4 portrait », « A3 paysage », ou les dimensions quand rien ne colle."""
    dimensions = f"{largeur_mm:.0f} × {hauteur_mm:.0f} mm"
    petit, grand = sorted((largeur_mm, hauteur_mm))
    for nom, (ref_petit, ref_grand) in FORMATS_ISO.items():
        if (
            abs(petit - ref_petit) <= TOLERANCE_FORMAT_MM
            and abs(grand - ref_grand) <= TOLERANCE_FORMAT_MM
        ):
            sens = "paysage" if largeur_mm > hauteur_mm else "portrait"
            return f"{nom} {sens} ({dimensions})"
    return dimensions


def lire(chemin: str | Path) -> PdfReader:
    """Ouvre le PDF déposé, ou dit pourquoi il n'est pas exploitable.

    Aucun repli : un fichier qui n'est pas un PDF, un PDF chiffré ou un PDF
    sans page ne donne pas un dossier amputé d'une pièce en silence.
    """
    chemin = Path(chemin)
    if not chemin.exists():
        raise ErreurNotice(f"Notice DP 11 déclarée mais introuvable : {chemin}.")
    try:
        lecteur = PdfReader(str(chemin))
        nombre = len(lecteur.pages)
    except (PdfReadError, OSError, ValueError) as exc:
        raise ErreurNotice(
            f"Notice DP 11 illisible ({chemin.name}) : {exc}. Déposez un PDF "
            "valide — un document Word ou une image renommée en .pdf n'en est "
            "pas un."
        ) from exc
    if lecteur.is_encrypted:
        raise ErreurNotice(
            f"Notice DP 11 chiffrée ({chemin.name}) : son contenu ne peut pas "
            "être repris dans le dossier. Réexportez-la sans mot de passe."
        )
    if nombre == 0:
        raise ErreurNotice(
            f"Notice DP 11 sans aucune page ({chemin.name}) : il n'y a rien à "
            "mettre au dossier."
        )
    return lecteur


def zone_utile(planche) -> tuple[float, float, float, float]:
    """Zone de dessin de la planche, moins le blanc tournant du dossier.

    Lue sur la planche et non recopiée : le gabarit du lot 1 reste la seule
    source des dimensions, et le blanc tournant celle du lot 4.
    """
    x_mm, y_mm, largeur_mm, hauteur_mm = planche.zone_dessin()
    return (
        x_mm + BLANC_TOURNANT_MM,
        y_mm + BLANC_TOURNANT_MM,
        largeur_mm - 2 * BLANC_TOURNANT_MM,
        hauteur_mm - 2 * BLANC_TOURNANT_MM,
    )


def _ajustement(page, zone_mm) -> tuple[Transformation, float, tuple[float, float]]:
    """Transformation qui pose la page fournie dans la zone utile.

    Rend aussi le facteur appliqué et les dimensions lues, en millimètres :
    c'est ce que le rapport annonce, et ce sur quoi le refus se décide.

    La rotation déclarée de la page est intégrée à la transformation :
    `merge_transformed_page` ne l'applique pas, et une notice exportée en
    portrait avec `/Rotate 90` se serait retrouvée couchée dans le cadre, à un
    facteur calculé sur les mauvaises dimensions. Elle est composée ici plutôt
    que reportée dans la page par `transfer_rotation_to_content()` : celui-ci
    réécrit le contenu de la page lue, ce que pypdf 6.16 refuse de faire hors
    d'un `PdfWriter` (DeprecationWarning, vérifié le 14/09/2026).
    """
    boite = page.mediabox
    gauche, bas = float(boite.left), float(boite.bottom)
    largeur_pt, hauteur_pt = float(boite.width), float(boite.height)
    if largeur_pt <= 0.0 or hauteur_pt <= 0.0:
        raise ErreurNotice(
            "Une page de la notice DP 11 est de dimensions nulles "
            f"({largeur_pt:.1f} × {hauteur_pt:.1f} pt) : elle n'a rien à montrer."
        )

    # Remise à l'origine, rotation déclarée comprise : le contenu occupe
    # ensuite le rectangle (0, 0, largeur_pt, hauteur_pt) tel qu'il se voit à
    # l'écran, les deux dimensions échangées pour un quart de tour.
    redresse = Transformation().translate(-gauche, -bas)
    rotation = int(page.rotation) % 360
    if rotation:
        redresse = redresse.rotate(-rotation)
        if rotation in (90, 270):
            largeur_pt, hauteur_pt = hauteur_pt, largeur_pt
        coins = [
            redresse.apply_on((0.0, 0.0)),
            redresse.apply_on((float(boite.width), float(boite.height))),
        ]
        redresse = redresse.translate(
            -min(x for x, _ in coins), -min(y for _, y in coins)
        )

    x_mm, y_mm, largeur_zone_mm, hauteur_zone_mm = zone_mm
    zone_l = largeur_zone_mm * MM_EN_PT
    zone_h = hauteur_zone_mm * MM_EN_PT
    facteur = min(zone_l / largeur_pt, zone_h / hauteur_pt)

    # L'origine du PDF est en bas à gauche de la feuille, celle de la planche
    # en haut à gauche : la zone se retourne avant de placer quoi que ce soit.
    x0 = x_mm * MM_EN_PT + (zone_l - largeur_pt * facteur) / 2.0
    y0 = (HAUTEUR_MM - y_mm - hauteur_zone_mm) * MM_EN_PT + (
        zone_h - hauteur_pt * facteur
    ) / 2.0
    transformation = redresse.scale(facteur).translate(x0, y0)
    dimensions_mm = (largeur_pt / MM_EN_PT, hauteur_pt / MM_EN_PT)
    return transformation, facteur, dimensions_mm


def _zone_temoin() -> tuple[float, float, float, float]:
    """Zone utile d'une planche à cartouche, sans rien dessiner.

    La planche témoin n'est pas composée : seule sa géométrie est lue, et elle
    ne dépend ni du projet ni du contenu.
    """
    return zone_utile(
        Planche(titre="", numero="", projet="", date="", avec_cartouche=True)
    )


def examiner(chemin_notice: str | Path):
    """Ce que chaque page de la notice deviendra, ou le refus, sans rien écrire.

    Rend la liste des (transformation, facteur, format lu) page par page, et
    lève `ErreurNotice` sur ce qui n'est pas exploitable. Appelé **au démarrage**
    de la génération par `dp_socle.assemblage` : une notice illisible découverte
    après le téléchargement de tous les fonds IGN coûte la génération entière,
    et le dépôt a déjà payé ce genre de diagnostic tardif une fois, sur cairo.
    """
    lecteur = lire(chemin_notice)
    zone = _zone_temoin()
    examen = []
    for index, page in enumerate(lecteur.pages):
        transformation, facteur, dimensions = _ajustement(page, zone)
        format_lu = nom_format(*dimensions)
        if facteur < FACTEUR_MINIMAL:
            raise ErreurNotice(
                f"Notice DP 11, page {index + 1} : {format_lu} ne tient dans la "
                f"zone utile qu'au facteur {facteur:.2f}, sous le minimum de "
                f"{FACTEUR_MINIMAL:.2f}. Réduite à ce point, elle serait "
                "illisible au dossier. Est-ce bien une notice, et non un plan "
                "déposé à sa place ?"
            )
        examen.append((transformation, facteur, format_lu))
    return lecteur, examen


def generer(
    projet: Projet,
    chemin_notice: str | Path,
    dossier: str | Path,
    premier_numero: int,
) -> Sortie:
    """Habille la notice fournie et rend la pièce DP 11 du dossier.

    `premier_numero` est le rang de la **première page** de la notice dans le
    dossier assemblé. Chaque page suivante porte le rang suivant : c'est la
    décision D3, et le dossier de référence la tranche — Massay porte sa notice
    sur deux pages, dont les cartouches annoncent NUMERO 16 puis NUMERO 17.
    """
    lecteur, examen = examiner(chemin_notice)
    dossier = Path(dossier)

    avertissements: list[str] = []
    formats = [format_lu for _t, _f, format_lu in examen]
    facteurs = [facteur for _t, facteur, _format in examen]
    ecrivain = PdfWriter()

    with tempfile.TemporaryDirectory(prefix="dp11-") as travail:
        for index, page_notice in enumerate(lecteur.pages):
            numero = premier_numero + index
            transformation = examen[index][0]
            planche = nouvelle_planche(
                projet, CODE, numero=str(numero), reperes_cartographiques=False
            )
            fond = Path(travail) / f"fond_{numero}.pdf"
            planche.rendre_pdf(fond)
            # Relu depuis la mémoire : `PdfReader` garde ouvert le fichier
            # qu'on lui nomme, et le dossier temporaire ne s'effacerait pas
            # sous Windows.
            #
            # La planche rejoint l'écrivain **avant** la fusion : depuis
            # pypdf 6, fusionner dans une page qui n'appartient à aucun
            # writer est déprécié, et le dépôt traite les DeprecationWarning
            # comme des erreurs.
            page_fond = ecrivain.add_page(
                PdfReader(io.BytesIO(fond.read_bytes())).pages[0]
            )
            page_fond.merge_transformed_page(page_notice, transformation, over=True)

        chemin = dossier / NOM_FICHIER
        chemin.parent.mkdir(parents=True, exist_ok=True)
        ecrivain.compress_identical_objects()
        with open(chemin, "wb") as fichier:
            ecrivain.write(fichier)

    minimum = min(facteurs)
    if minimum < FACTEUR_ALERTE:
        avertissements.append(
            f"Notice DP 11 réduite au facteur {minimum:.2f} pour tenir dans le "
            f"cadre A3 ({formats[facteurs.index(minimum)]}) : un corps de 10 pt "
            f"y descend à {10 * minimum:.1f} pt. Refaites-la dans un format plus "
            "proche de l'A4 si elle doit rester confortable à lire."
        )

    return Sortie(
        numero=CODE,
        titre=piece(CODE).titre,
        chemin=chemin,
        numeros=tuple(premier_numero + i for i in range(len(facteurs))),
        details={
            "avertissements": avertissements,
            "notice": {
                "source": Path(chemin_notice).name,
                "pages": len(facteurs),
                "formats": sorted(set(formats)),
                "facteur_min": minimum,
                "facteur_max": max(facteurs),
            },
        },
    )
