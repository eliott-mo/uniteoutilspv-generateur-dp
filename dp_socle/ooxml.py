"""Ce que `python-pptx` ne sait pas écrire, et que le lot 8 écrit à la main.

Six recettes, trouvées à tâtons par les sondes des 25 et 26/09/2026 et
vérifiées sur un fichier réellement ouvert dans PowerPoint. Elles sont ici
plutôt que dans `sortie_pptx` parce qu'elles ne parlent que du paquet OOXML :
c'est le seul endroit du dépôt où l'on descend sous l'API de la bibliothèque, et
le seul où l'on doive relire ce qu'on vient d'écrire.

CE QUI JUSTIFIE DE DESCENDRE AUSSI BAS
---------------------------------------
`python-pptx` n'offre aucune de ces six choses. Mais surtout, **il accepte sans
lever** qu'on lui règle une propriété qui n'existe pas : `fill.transparency =
0.45` ne faisait rien, et le cône de visée sortait magenta opaque par-dessus le
plan de repérage. C'est exactement le repli silencieux que la charte du dépôt
interdit. Chaque fonction de ce module relit donc l'élément qu'elle a produit et
lève `ErreurMontagePPTX` si ce qu'elle voulait n'y est pas.

LES REPÈRES
-----------
Tout entre en **millimètres papier**, comme dans `dp_socle.planche` : c'est
`pptx.util.Mm` qui convertit en EMU (914 400 par pouce), et la conversion ne se
refait nulle part ailleurs.
"""

from __future__ import annotations

import copy

from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.opc.constants import CONTENT_TYPE as CT
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn
from pptx.parts.slide import SlideLayoutPart
from pptx.util import Mm

from .erreurs import ErreurMontagePPTX

#: Rang de la mise en page « Blank » du modèle par défaut de `python-pptx`.
#:
#: C'est elle qu'on clone, parce qu'elle ne porte aucune réservation de titre ni
#: de contenu : une planche A3 n'a ni l'un ni l'autre. Vérifié le 25/09/2026,
#: `Presentation().slide_layouts[6].name == "Blank"` — d'où le contrôle du nom
#: dans `nouvelle_mise_en_page`, qui refuse plutôt que de cloner au hasard si un
#: jour le modèle de la bibliothèque changeait d'ordre.
RANG_MISE_EN_PAGE_VIERGE = 6
NOM_MISE_EN_PAGE_VIERGE = "Blank"

#: Réservations de pied de page héritées du modèle, retirées des mises en page
#: que nous fabriquons.
#:
#: Deux raisons, la seconde mesurée. Une date ou un numéro de diapo n'a rien à
#: faire sur une planche qui porte déjà son cartouche — et PowerPoint les
#: affiche dès que l'en-tête et le pied de page sont activés, réglage qui
#: appartient au poste et non au fichier. Mais surtout, **elles occupent les
#: `idx` 10, 11 et 12** de la mise en page « Blank » : une réservation d'image
#: posée à l'`idx` 10 se retrouvait à hériter des cotes de la case de date,
#: 59 x 10 mm au lieu de 222 x 115 mm (mesuré le 25/09/2026). Les laisser, c'est
#: donner au cadre photo une géométrie fausse qui s'affiche correctement.
TYPES_PIED_DE_PAGE = (
    PP_PLACEHOLDER.DATE,
    PP_PLACEHOLDER.FOOTER,
    PP_PLACEHOLDER.SLIDE_NUMBER,
)

#: Identifiant de l'extension `svgBlip`, lue par PowerPoint 2016 et suivants.
#: Relevé dans un fichier écrit par PowerPoint lui-même (sonde du 25/09/2026) :
#: c'est une constante de Microsoft, pas un choix.
URI_EXTENSION_SVG = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
NS_SVG = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"

#: Première valeur d'`id` des entrées `p:sldLayoutId`, imposée par le schéma
#: (ST_SlideLayoutId : au moins 2 147 483 648). Le modèle par défaut en occupe
#: onze à partir de 2 147 483 649 ; nous partons franchement au-dessus pour ne
#: pas avoir à compter.
PREMIER_ID_MISE_EN_PAGE = 2147484000


# ---------------------------------------------------------------------------
# Les mises en page, une par diapo
# ---------------------------------------------------------------------------


def nouvelle_mise_en_page(presentation, nom: str):
    """Une mise en page vierge de plus, clonée de « Blank » et rattachée au masque.

    Le lot 8 en veut **une par diapo** : c'est là qu'est posé le fond de
    planche, et c'est ce qui le met hors d'atteinte du chef de projet (décision
    D1). Or `python-pptx` n'a pas d'API pour en créer — `SlideLayouts` sait
    seulement en retirer une. On clone donc l'élément XML de la mise en page
    vierge, et on la déclare des trois côtés qu'il faut : la partie pointe vers
    le masque, le masque pointe vers la partie, et le masque la liste dans son
    `p:sldLayoutIdLst`. Sans cette liste, PowerPoint « répare » le fichier.

    Le clonage porte sur l'**élément**, et la partie neuve n'hérite donc d'aucune
    relation. C'est voulu : une relation clonée pointerait vers l'image d'une
    autre partie, le piège que la sonde du 25/09/2026 a payé en passant par une
    diapo jetable.
    """
    masque = presentation.slide_master
    modele = presentation.slide_layouts[RANG_MISE_EN_PAGE_VIERGE]
    if modele.name != NOM_MISE_EN_PAGE_VIERGE:
        raise ErreurMontagePPTX(
            f"La mise en page de rang {RANG_MISE_EN_PAGE_VIERGE} du modèle "
            f"s'appelle « {modele.name} » et non « {NOM_MISE_EN_PAGE_VIERGE} » : "
            "le modèle par défaut de python-pptx a changé d'ordre, et cloner "
            "celle-là poserait des réservations de titre sur les planches."
        )

    paquet = presentation.part.package
    partie = SlideLayoutPart(
        paquet.next_partname("/ppt/slideLayouts/slideLayout%d.xml"),
        CT.PML_SLIDE_LAYOUT,
        paquet,
        copy.deepcopy(modele.element),
    )
    partie.relate_to(masque.part, RT.SLIDE_MASTER)
    rId = masque.part.relate_to(partie, RT.SLIDE_LAYOUT)

    liste = masque.element.get_or_add_sldLayoutIdLst()
    entree = liste._add_sldLayoutId(rId=rId)
    entree.set("id", str(PREMIER_ID_MISE_EN_PAGE + len(liste.sldLayoutId_lst)))

    mise_en_page = partie.slide_layout
    mise_en_page.element.cSld.set("name", nom)
    _retirer_pieds_de_page(mise_en_page)

    if presentation.slide_layouts.get_by_name(nom) is None:
        raise ErreurMontagePPTX(
            f"La mise en page « {nom} » a été écrite mais le masque ne la "
            "retrouve pas : le fichier serait réparé à l'ouverture."
        )
    return mise_en_page


def _retirer_pieds_de_page(mise_en_page) -> None:
    """Retire les réservations de date, de pied de page et de numéro de diapo.

    Le retrait est **relu** : c'est lui qui libère les `idx` 10 à 12, et une
    réservation d'image qui en hériterait sortirait à 59 x 10 mm. Voir
    `TYPES_PIED_DE_PAGE`.
    """
    arbre = mise_en_page.shapes._spTree
    for forme in list(arbre.iter_ph_elms()):
        if forme.ph_type in TYPES_PIED_DE_PAGE:
            forme.getparent().remove(forme)
    restantes = [e.ph_type for e in arbre.iter_ph_elms()]
    if restantes:
        raise ErreurMontagePPTX(
            "La mise en page garde des réservations héritées du modèle "
            f"({', '.join(str(t) for t in restantes)}) : leurs `idx` entreraient "
            "en collision avec ceux des cadres photo, qui hériteraient alors de "
            "leurs cotes."
        )


# ---------------------------------------------------------------------------
# Le fond de planche
# ---------------------------------------------------------------------------


def poser_fond(mise_en_page, chemin_image, svg: bytes | None = None,
               nom: str = "Fond de planche"):
    """Pose une image pleine page sur la mise en page, hors d'atteinte.

    L'API de `python-pptx` ne propose `add_picture` que sur une diapo. La
    recette, mesurée le 25/09/2026 : `get_or_add_image_part` rend un `rId`
    valable pour la partie de la mise en page, et `add_pic` l'y déclare.

    `svg` est le SVG de la même planche, texte passé en tracés. Fourni, il
    voyage dans une extension du `a:blip` que PowerPoint 2016 et suivants
    affichent en vectoriel, l'image matricielle restant le repli des versions
    antérieures.
    """
    formes = mise_en_page.shapes
    image, rId = mise_en_page.part.get_or_add_image_part(str(chemin_image))
    presentation = mise_en_page.part.package.presentation_part.presentation
    pic = formes._spTree.add_pic(
        formes._next_shape_id, nom, image.desc, rId,
        0, 0, presentation.slide_width, presentation.slide_height,
    )
    # Le fond n'est pas là pour être attrapé : il porte l'échelle de la planche.
    # Ce qui le met hors d'atteinte, c'est d'être sur la mise en page ; le verrou
    # ne fait que dire la même chose dans le fichier.
    verrouiller(pic, selection=True)
    if svg is not None:
        _greffer_svg(mise_en_page.part, pic, svg)
    return pic


def _greffer_svg(partie, pic, svg: bytes) -> None:
    """Ajoute le SVG à côté du matriciel, dans une extension du `a:blip`.

    La partie SVG se déclare à la main : `python-pptx` ne connaît pas ce type de
    contenu, et son `get_or_add_image_part` passe par Pillow, qui ne lit pas le
    SVG.
    """
    paquet = partie.package
    partie_svg = Part(
        paquet.next_partname("/ppt/media/planche%d.svg"),
        "image/svg+xml",
        paquet,
        svg,
    )
    rId = partie.relate_to(partie_svg, RT.IMAGE)
    blip = pic.blipFill.find(qn("a:blip"))
    if blip is None:
        raise ErreurMontagePPTX(
            "L'image posée sur la mise en page n'a pas de `a:blip` : le SVG "
            "vectoriel n'a nulle part à se greffer."
        )
    blip.append(parse_xml(
        f'<a:extLst {nsdecls("a", "r")}>'
        f'<a:ext uri="{URI_EXTENSION_SVG}">'
        f'<asvg:svgBlip xmlns:asvg="{NS_SVG}" r:embed="{rId}"/>'
        "</a:ext></a:extLst>"
    ))
    return partie_svg


# ---------------------------------------------------------------------------
# Les réservations d'image
# ---------------------------------------------------------------------------


def ajouter_reservation_image(mise_en_page, idx: int, nom: str, x_mm: float,
                              y_mm: float, largeur_mm: float, hauteur_mm: float):
    """Une réservation d'image sur la mise en page, que la diapo héritera.

    C'est ce qui fait que PowerPoint **rogne** la photographie déposée au format
    du cadre, au lieu d'étirer le cadre au format de la photographie : « clic
    droit > Remplacer l'image : la forme de la boîte change pour s'adapter à la
    forme de l'image » (sonde du 25/09/2026, sur une image simplement posée).
    Une photographie en portrait étirait le cadre et cassait la planche.

    `python-pptx` ne crée pas de réservation ; le `p:sp` s'écrit donc ici. La
    diapo créée ensuite la porte comme une vraie `PicturePlaceholder`, avec
    `insert_picture`, et hérite de sa position sans la redéclarer.

    L'`idx` est ce par quoi la diapo retrouve la réservation de la mise en page
    et en hérite les cotes : deux réservations du même `idx` donneraient un cadre
    aux cotes de l'autre, sans que rien ne le dise.
    """
    formes = mise_en_page.shapes
    occupes = [e.ph_idx for e in formes._spTree.iter_ph_elms()]
    if idx in occupes:
        raise ErreurMontagePPTX(
            f"La mise en page « {mise_en_page.name} » porte déjà une "
            f"réservation d'idx {idx} : la diapo hériterait des cotes de l'une "
            "pour l'autre."
        )
    sp = parse_xml(
        f"<p:sp {nsdecls('p', 'a')}>"
        "<p:nvSpPr>"
        f'<p:cNvPr id="{formes._next_shape_id}" name="{nom}"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
        f'<p:nvPr><p:ph type="pic" idx="{idx}"/></p:nvPr>'
        "</p:nvSpPr>"
        "<p:spPr>"
        "<a:xfrm>"
        f'<a:off x="{Mm(x_mm)}" y="{Mm(y_mm)}"/>'
        f'<a:ext cx="{Mm(largeur_mm)}" cy="{Mm(hauteur_mm)}"/>'
        "</a:xfrm>"
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "</p:spPr>"
        "<p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>"
        "</p:sp>"
    )
    formes._spTree.append(sp)
    return sp


# ---------------------------------------------------------------------------
# Le verrou, l'alpha, l'étiquette droite
# ---------------------------------------------------------------------------

#: Balises de propriétés non visuelles, selon le genre de forme. Une forme
#: ordinaire porte `p:cNvSpPr`, une image `p:cNvPicPr`, un groupe `p:cNvGrpSpPr`,
#: et les verrous ne s'écrivent pas au même endroit.
_BALISES_PROPRIETES = ("p:cNvSpPr", "p:cNvPicPr", "p:cNvGrpSpPr")


def verrouiller(forme, selection: bool = False) -> None:
    """Interdit de déplacer et de redimensionner la forme.

    Le verrou se pose sur la forme de la **diapo**, jamais sur celle de la mise
    en page : le clonage d'une réservation ne reprend que son identifiant et son
    type, et un verrou posé sur la mise en page ne suivait pas (mesuré le
    26/09/2026). Les titres de cadre, laissés libres, se déplaçaient : ils se
    verrouillent de même.

    `selection` interdit en plus de la sélectionner, ce que seul le fond veut :
    un cadre photo doit rester cliquable, c'est là que la photographie entre.
    """
    proprietes = _proprietes_non_visuelles(getattr(forme, "_element", forme))
    verrous = proprietes.find(qn("a:spLocks"))
    if verrous is None:
        verrous = parse_xml(f"<a:spLocks {nsdecls('a')}/>")
        proprietes.insert(0, verrous)
    verrous.set("noMove", "1")
    verrous.set("noResize", "1")
    if selection:
        verrous.set("noSelect", "1")
    if verrous.get("noMove") != "1" or verrous.get("noResize") != "1":
        raise ErreurMontagePPTX(  # pragma: no cover - garde-fou
            "Le verrou `a:spLocks` ne se relit pas dans la forme : elle serait "
            "déplaçable, et un cadre déplacé fausse la planche."
        )


def _proprietes_non_visuelles(element):
    """L'élément `p:cNv*Pr` de la forme, quel que soit son genre."""
    for balise in _BALISES_PROPRIETES:
        trouve = element.find(f".//{qn(balise)}")
        if trouve is not None:
            return trouve
    raise ErreurMontagePPTX(
        f"La forme <{element.tag.split('}')[-1]}> ne porte aucune des balises de "
        f"propriétés non visuelles attendues ({', '.join(_BALISES_PROPRIETES)}) : "
        "impossible d'y écrire un verrou."
    )


def regler_alpha(forme, opacite: float) -> None:
    """Rend le remplissage de la forme partiellement transparent.

    `fill.transparency` **n'existe pas** dans `python-pptx` : Python accepte
    l'affectation sans lever et ne fait rien. Le cône de visée sortait donc
    magenta opaque par-dessus le plan de repérage (mesuré le 25/09/2026).
    L'alpha s'écrit à la main dans le `a:solidFill`, en millièmes de pour cent.
    """
    if not 0.0 < opacite <= 1.0:
        raise ErreurMontagePPTX(
            f"Opacité de {opacite} hors de ]0 ; 1] : une forme invisible ou "
            "opaque ne se règle pas par un alpha."
        )
    element = getattr(forme, "_element", forme)
    couleur = element.find(f".//{qn('a:solidFill')}/{qn('a:srgbClr')}")
    if couleur is None:
        raise ErreurMontagePPTX(
            "La forme n'a pas de remplissage uni à teinter : appelez "
            "`fill.solid()` et posez sa couleur avant de régler son alpha."
        )
    attendu = str(int(round(opacite * 100000)))
    for ancien in couleur.findall(qn("a:alpha")):
        couleur.remove(ancien)
    couleur.append(parse_xml(f'<a:alpha {nsdecls("a")} val="{attendu}"/>'))
    relu = couleur.find(qn("a:alpha"))
    if relu is None or relu.get("val") != attendu:
        raise ErreurMontagePPTX(  # pragma: no cover - garde-fou
            "L'alpha ne se relit pas dans le remplissage : la forme sortirait "
            "opaque et masquerait le plan qu'elle désigne."
        )


def garder_horizontal(forme) -> None:
    """Garde le texte de la forme horizontal dans un groupe qui tourne.

    `upright="1"` seul ne suffit pas : l'étiquette reste droite tant que le
    groupe tourne peu, mais de côté elle se replie à une lettre par ligne — la
    boîte tourne, et le texte horizontal n'y tient plus. `wrap="none"` l'en
    empêche (confirmé le 25/09/2026 : « le texte reste bien horizontal dans
    toutes les positions »).
    """
    element = getattr(forme, "_element", forme)
    corps = element.find(f".//{qn('a:bodyPr')}")
    if corps is None:
        raise ErreurMontagePPTX(
            "La forme n'a pas de corps de texte `a:bodyPr` : rien à garder "
            "horizontal."
        )
    corps.set("upright", "1")
    corps.set("wrap", "none")
