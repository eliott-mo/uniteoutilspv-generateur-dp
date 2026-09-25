"""Comment une planche entre dans le `.pptx` : deux voies, et la mesure qui tranche.

Le PPTX porte **la planche telle que le moteur la dessine**, en une seule image
posée pleine page (décision D0 du lot 8) : la retraduire en formes DrawingML
serait un second moteur de rendu, avec ses propres métriques de texte, et une
planche qui s'afficherait autrement dans PowerPoint que dans le PDF est
exactement la planche fausse que personne ne détecte.

DEUX VOIES, ET POURQUOI ON NE CHOISIT PAS D'AVANCE
---------------------------------------------------
Une planche peut voyager de deux façons :

- **vectorielle** — le SVG de la planche, repassé par cairo pour que son texte
  devienne des tracés de glyphes, greffé au `a:blip` dans l'extension
  `asvg:svgBlip` que PowerPoint 2016 et suivants affichent en vectoriel. Net à
  tout grossissement, et affranchi du plafond de 200 dpi que l'export PDF de
  PowerPoint impose au matriciel ;
- **matricielle** — la même planche rendue en JPEG à 200 dpi.

Le brief tranchait par une table de codes de pièces : vectoriel pour DP 2, DP 3,
DP 4 et la page de garde, matriciel pour celles que le fond IGN domine. La table
dit vrai, mais elle dérive — elle ne prévoyait pas DP 1-3, qui ne porte aucun
raster, ni une page de garde chargée d'un photomontage, qui en porte un gros. La
voie se **mesure** donc planche par planche : on rend les deux et on garde la
plus légère. Le rapport de génération dit laquelle a gagné et de combien.

LE POIDS QUI COMPTE EST LE POIDS DÉFLATÉ
-----------------------------------------
Un `.pptx` est un ZIP. Comparer les tailles brutes trompe du tout au tout, et
c'est ce qui explique l'écart entre les chiffres du brief et ceux relevés ici
le 25/09/2026 sur le plan de masse de Sarnois :

| Voie                 | Brut    | Déflaté, dans le paquet |
|----------------------|---------|--------------------------|
| SVG en tracés        | 2,16 Mo | **0,43 Mo**              |
| JPEG q88 à 200 dpi   | 0,86 Mo | 0,77 Mo                  |
| PNG à 200 dpi        | 1,69 Mo | 1,66 Mo                  |

Le SVG est du texte : il se comprime d'un facteur cinq. Le JPEG et le PNG sont
déjà comprimés et ne gagnent rien. La comparaison se fait donc sur le poids
déflaté, le seul que le fichier livré portera.

LE REPLI MATRICIEL, ET SON ÉCART AU BRIEF
------------------------------------------
Le `a:blip` d'une planche vectorielle porte quand même une image matricielle :
c'est ce qu'affiche une version de PowerPoint antérieure à 2016. Le brief la
voulait à 3 308 x 2 339 px, comme la voie matricielle. Mesuré, ce repli pèse à
lui seul 1,66 Mo déflaté sur le plan de masse, soit près de quatre fois la
planche vectorielle qu'il accompagne : la voie vectorielle deviendrait la plus
lourde des deux, et sa raison d'être disparaîtrait.

Le repli se rend donc à `LARGEUR_REPLI_PX`, quelques dizaines de kilo-octets.
C'est un écart assumé au brief, et il tient à ce que D7 et D8 ont établi : le
poste du chef de projet est sous Microsoft 365, qui lit le SVG. Un poste plus
ancien afficherait une planche visiblement floue — pas une planche fausse.
"""

from __future__ import annotations

import io
import math
import zlib
from dataclasses import dataclass
from pathlib import Path

from .erreurs import ErreurSortiePPTX

#: Résolution du matriciel, en points par pouce.
#:
#: Mesuré le 25/09/2026 sur un PDF réellement exporté depuis PowerPoint
#: (« Enregistrer au format PDF », qualité standard), à partir d'une sonde
#: portant la même planche à 200, 300 et 400 dpi : les trois pages en
#: ressortent à 3 308 x 2 339 px, soit exactement 200 dpi. Ce qu'on met au-delà
#: est jeté à l'export et ne coûte que du poids.
DPI_PPTX = 200

#: Qualité JPEG du matriciel. La même que celle des fonds IGN des planches
#: (`Planche.ajouter_fond_raster`) : le grain d'une ortho ne supporte pas mieux,
#: et le trait noir sur blanc du cartouche y tient encore.
QUALITE_JPEG = 88

#: Largeur du repli matriciel d'une planche vectorielle, en pixels. Voir
#: l'en-tête du module : à 3 308 px le repli pèse plus que la planche qu'il
#: accompagne.
LARGEUR_REPLI_PX = 1000

#: Noms des deux voies, tels qu'ils paraissent au rapport de génération.
VECTORIELLE = "vectorielle"
MATRICIELLE = "matricielle"


@dataclass(frozen=True)
class Fond:
    """Ce qui entre dans le `a:blip` d'une diapo, et ce que la mesure a dit.

    `image` est toujours peuplée : c'est le matriciel, plein format en voie
    matricielle, repli léger en voie vectorielle. `svg` ne l'est qu'en voie
    vectorielle.
    """

    image: bytes
    svg: bytes | None
    voie: str
    #: Poids déflatés comparés, en octets, par voie. C'est ce qui a tranché, et
    #: le rapport de génération le dit : une voie choisie sans qu'on sache
    #: pourquoi est une décision qu'on ne peut pas relire.
    poids: dict

    @property
    def octets(self) -> int:
        """Poids déflaté de ce que ce fond ajoute au paquet."""
        total = poids_dans_le_paquet(self.image)
        if self.svg is not None:
            total += poids_dans_le_paquet(self.svg)
        return total

    def resume(self, libelle: str) -> str:
        """Une ligne pour le rapport de génération."""
        ecart = self.poids[MATRICIELLE] - self.poids[VECTORIELLE]
        return (
            f"{libelle} : voie {self.voie} "
            f"({self.poids[VECTORIELLE] / 1e6:.2f} Mo en vectoriel contre "
            f"{self.poids[MATRICIELLE] / 1e6:.2f} Mo en matriciel, "
            f"{abs(ecart) / 1e6:.2f} Mo d'écart), "
            f"{self.octets / 1e6:.2f} Mo dans le fichier."
        )


def poids_dans_le_paquet(donnees: bytes) -> int:
    """Poids de ces octets une fois déflatés par le ZIP du `.pptx`.

    Sans en-tête zlib ni somme de contrôle (`wbits` négatif) : c'est ce que
    `zipfile` écrit, et c'est donc la seule mesure comparable d'une voie à
    l'autre. Voir l'en-tête du module pour ce que la mesure brute trompe.
    """
    compresseur = zlib.compressobj(9, zlib.DEFLATED, -15)
    return len(compresseur.compress(donnees) + compresseur.flush())


def taille_en_pixels(largeur_mm: float, hauteur_mm: float,
                     dpi: int = DPI_PPTX) -> tuple[int, int]:
    """Taille de pixel d'une page, arrondie au pixel supérieur.

    À 200 dpi une A3 paysage fait 3 308 x 2 339 px, ce que l'export PDF de
    PowerPoint rend exactement (mesuré le 25/09/2026).
    """
    return (
        math.ceil(largeur_mm / 25.4 * dpi),
        math.ceil(hauteur_mm / 25.4 * dpi),
    )


def rendre_fond(planche, libelle: str) -> Fond:
    """Rend la planche dans les deux voies, et garde la plus légère.

    `libelle` ne sert qu'aux messages d'erreur et au rapport : c'est le nom de la
    pièce, pas un chemin.
    """
    from .planche import HAUTEUR_MM, LARGEUR_MM

    svg = planche.svg().encode("utf-8")
    traces = _en_traces(svg, libelle)
    largeur_px, hauteur_px = taille_en_pixels(LARGEUR_MM, HAUTEUR_MM)
    plein_format = _en_jpeg(svg, largeur_px, hauteur_px, libelle)

    poids = {
        # La voie vectorielle porte les deux : le SVG et son repli.
        VECTORIELLE: poids_dans_le_paquet(traces),
        MATRICIELLE: poids_dans_le_paquet(plein_format),
    }
    if poids[VECTORIELLE] < poids[MATRICIELLE]:
        hauteur_repli = max(1, round(hauteur_px * LARGEUR_REPLI_PX / largeur_px))
        return Fond(
            image=_en_jpeg(svg, LARGEUR_REPLI_PX, hauteur_repli, libelle),
            svg=traces,
            voie=VECTORIELLE,
            poids=poids,
        )
    return Fond(image=plein_format, svg=None, voie=MATRICIELLE, poids=poids)


def rendre_pages_pdf(chemin_pdf, libelle: str, dpi: int = DPI_PPTX) -> list[bytes]:
    """Rastérise en PNG chaque page d'un PDF déjà produit.

    C'est la voie de la notice DP 11, et d'elle seule. La notice n'est pas
    composée : le PDF fourni par le chef de projet est fusionné **en vecteur**
    dans le cadre A3 au niveau du PDF (`dp11_notice.generer`), et il n'existe
    donc aucun SVG de cette pièce à passer en tracés.

    En **PNG** et non en JPEG (décision D6), mais pas pour la raison que le brief
    avançait. Il l'expliquait par « du texte noir sur blanc, quelques dizaines de
    kilo-octets » ; mesuré le 25/09/2026 sur la notice de Sarnois, c'est faux :
    ses cinq pages portent de 2 000 à 120 000 couleurs distinctes — donc des
    photographies et des figures — et pèsent de 0,36 à 1,67 Mo la page selon
    l'encodage :

    | Encodage à 200 dpi      | Notice de Sarnois, 5 pages |
    |-------------------------|----------------------------|
    | PNG                     | 5,9 Mo                     |
    | PNG ramené à 256 teintes| 2,4 Mo                     |
    | JPEG q88                | 3,8 Mo                     |

    Le PNG reste retenu, et c'est le plus lourd des trois : une notice se lit, et
    les artefacts du JPEG autour d'un petit corps de texte sont précisément ce
    qui rend une pièce illisible à l'instruction. La quantification, elle,
    banderait les photographies. Le poids part au rapport de génération, pour
    qu'une notice épaisse se voie avant le dépôt et non après.

    Son texte cesse d'être du texte — il ne sera plus ni sélectionnable ni
    cherchable dans le PDF final. Accepté le 25/09/2026.
    """
    import pypdfium2

    chemin_pdf = Path(chemin_pdf)
    if not chemin_pdf.exists():
        raise ErreurSortiePPTX(
            f"{libelle} : {chemin_pdf.name} est introuvable, la pièce ne peut "
            "pas entrer dans la sortie PowerPoint."
        )
    pages: list[bytes] = []
    document = pypdfium2.PdfDocument(str(chemin_pdf))
    try:
        for index in range(len(document)):
            page = document[index]
            # `scale` est en pixels par point PostScript : 200 dpi vaut 200/72.
            image = page.render(scale=dpi / 72.0).to_pil()
            tampon = io.BytesIO()
            _aplatir(image).save(tampon, "PNG", optimize=True)
            pages.append(tampon.getvalue())
    finally:
        document.close()
    if not pages:
        raise ErreurSortiePPTX(
            f"{libelle} : {chemin_pdf.name} ne porte aucune page à rastériser."
        )
    return pages


def _en_traces(svg: bytes, libelle: str) -> bytes:
    """Le même SVG, texte passé en tracés de glyphes.

    Sans ce passage, PowerPoint recompose le texte du SVG avec ses propres
    métriques et le cartouche se décale. En tracés, il n'y a plus de `<text>`
    dans le fichier, donc plus rien à recomposer : la mise en page reste celle du
    PDF, puisque c'est le même moteur qui l'a calculée.

    Fidélité mesurée le 25/09/2026, en rendant les deux SVG à 3 308 px et en les
    comparant pixel à pixel : 0,17 % des pixels s'écartent de plus de 8/255,
    écart moyen 0,09/255 — le crénelage des contours, rien d'autre.
    """
    import cairosvg

    try:
        traces = cairosvg.svg2svg(bytestring=svg)
    except Exception as exc:
        raise ErreurSortiePPTX(
            f"{libelle} : le passage du texte en tracés a échoué ({exc}). La "
            "planche ne peut pas partir en vectoriel."
        ) from exc
    if b"<text" in traces:
        raise ErreurSortiePPTX(
            f"{libelle} : le SVG en tracés porte encore un élément <text>. "
            "PowerPoint le recomposerait avec ses propres métriques, et le "
            "cartouche ne tomberait plus où le PDF le pose."
        )
    return traces


def _en_jpeg(svg: bytes, largeur_px: int, hauteur_px: int, libelle: str) -> bytes:
    """La planche rendue à la taille de pixel demandée, en JPEG."""
    import cairosvg

    try:
        png = cairosvg.svg2png(
            bytestring=svg, output_width=largeur_px, output_height=hauteur_px
        )
    except Exception as exc:
        raise ErreurSortiePPTX(
            f"{libelle} : rendu matriciel impossible à {largeur_px} x "
            f"{hauteur_px} px ({exc})."
        ) from exc
    from PIL import Image

    tampon = io.BytesIO()
    _aplatir(Image.open(io.BytesIO(png))).save(
        tampon, "JPEG", quality=QUALITE_JPEG, optimize=True
    )
    return tampon.getvalue()


def _aplatir(image):
    """Image en RGB, transparence aplatie **sur blanc**.

    Un `convert("RGB")` direct remplit de noir : le cadre de la planche
    ressortirait sur fond noir. Le piège est celui de `photographies._recadrer`,
    et il se paie deux fois si on ne le nomme pas.
    """
    from PIL import Image

    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        fond = Image.new("RGBA", image.size, (255, 255, 255, 255))
        image = Image.alpha_composite(fond, image)
    return image.convert("RGB")
