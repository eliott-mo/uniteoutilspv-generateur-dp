"""Moteur de planche : gabarit A3 paysage composé en SVG, rendu en PDF vectoriel.

Un seul moteur graphique pour les huit planches du dossier : les planches
cartographiques du socle comme les coupes et plans techniques des lots suivants
se composent avec les mêmes primitives.

Deux repères coexistent, et il ne faut jamais les confondre :

- le **repère papier**, en millimètres, origine en haut à gauche de la feuille.
  Le document SVG déclare `width="420mm" height="297mm" viewBox="0 0 420 297"`,
  donc une unité utilisateur SVG vaut exactement un millimètre imprimé. Les
  méthodes `ajouter_texte`, `ajouter_rectangle`, `ajouter_image_mm` travaillent
  dans ce repère.
- le **repère terrain**, en Lambert 93. Les méthodes `ajouter_geometrie`,
  `ajouter_fond_raster` et `ajouter_etiquettes` y travaillent, et passent
  systématiquement par `self.transformation` (voir `dp_socle.echelle`), qui est
  la seule conversion mètres → millimètres du projet.

Aucun ajustement à la page n'est fait à l'impression : le PDF produit mesure
420 x 297 mm et l'échelle inscrite au cartouche est vraie.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from .echelle import TransformationL93, formater_echelle
from .erreurs import ErreurEchelle, ErreurRendu
from .polices import chasse_cairo, famille_active

# --- Gabarit A3 paysage -----------------------------------------------------

LARGEUR_MM = 420.0
HAUTEUR_MM = 297.0
MARGE_MM = 5.0
CARTOUCHE_MM = 15.0
BANDEAU_MM = 4.0

#: Coordonnées utiles du gabarit, dérivées des constantes ci-dessus.
CADRE = (MARGE_MM, MARGE_MM, LARGEUR_MM - 2 * MARGE_MM, HAUTEUR_MM - 2 * MARGE_MM)
Y_BANDEAU = HAUTEUR_MM - MARGE_MM - BANDEAU_MM
Y_CARTOUCHE = Y_BANDEAU - CARTOUCHE_MM

#: Découpage du cartouche, de gauche à droite : (identifiant, x, largeur).
CASES_CARTOUCHE = (
    ("logo", MARGE_MM, 40.0),
    ("projet", 45.0, 70.0),
    ("titre", 115.0, 190.0),
    ("nord", 305.0, 20.0),
    ("echelle", 325.0, 30.0),
    ("date", 355.0, 30.0),
    ("numero", 385.0, 30.0),
)

MENTION_BANDEAU = "Ceci n'est pas un plan d'exécution"

# --- Typographie ------------------------------------------------------------

#: 1 pt = 25.4/72 mm. Les tailles sont exprimées en millimètres dans le SVG.
PT = 25.4 / 72.0

TAILLE_ETIQUETTE = 7 * PT
TAILLE_COURANTE = 8 * PT
TAILLE_CARTOUCHE = 9 * PT
TAILLE_TITRE_CARTOUCHE = 12 * PT

NOIR = "#000000"
GRIS = "#555555"

#: Couleurs relevées sur les supports de communication UNITe.
BLEU_UNITE = "#1C2445"
VERT_UNITE = "#89BA44"
GRIS_FOND = "#F7F6F5"

RESSOURCES = Path(__file__).parent / "ressources"
LOGO_UNITE = RESSOURCES / "logo_unite.png"


@dataclass
class Style:
    """Style de tracé, exprimé dans les unités du papier (millimètres)."""

    trait: str | None = NOIR
    epaisseur_mm: float = 0.25
    remplissage: str | None = "none"
    opacite_remplissage: float = 1.0
    tirets: str | None = None

    def attributs(self) -> str:
        morceaux = [
            f'fill="{self.remplissage or "none"}"',
            f'stroke="{self.trait or "none"}"',
            f'stroke-width="{self.epaisseur_mm:g}"',
            'stroke-linejoin="round"',
            'stroke-linecap="round"',
        ]
        if self.opacite_remplissage != 1.0:
            morceaux.append(f'fill-opacity="{self.opacite_remplissage:g}"')
        if self.tirets:
            morceaux.append(f'stroke-dasharray="{self.tirets}"')
        return " ".join(morceaux)


#: Styles employés par les planches du socle.
STYLE_EMPRISE = Style(trait="#d40000", epaisseur_mm=0.6, remplissage="#d40000",
                      opacite_remplissage=0.15)
STYLE_PARCELLE = Style(trait="#7a4b00", epaisseur_mm=0.2, remplissage="none")
STYLE_PARCELLE_CONCERNEE = Style(trait="#7a4b00", epaisseur_mm=0.35,
                                 remplissage="#ffd28a", opacite_remplissage=0.45)


def _style_attributs(style) -> str:
    if isinstance(style, Style):
        return style.attributs()
    if isinstance(style, dict):
        return " ".join(f'{cle}="{valeur}"' for cle, valeur in style.items())
    raise TypeError(f"Style attendu (Style ou dict), reçu {type(style).__name__}")


def nombre_fr(valeur: float, decimales: int = 2) -> str:
    """Nombre à la française : virgule décimale, espace insécable aux milliers."""
    texte = f"{valeur:,.{decimales}f}"
    return texte.replace(",", " ").replace(".", ",")


def _n(valeur: float) -> str:
    """Formatage compact et déterministe d'une coordonnée en millimètres."""
    return f"{valeur:.4f}".rstrip("0").rstrip(".") or "0"


@dataclass
class EntreeLegende:
    libelle: str
    style: Style | dict


@dataclass
class Planche:
    """Une planche A3 paysage du dossier de déclaration préalable."""

    titre: str
    numero: str
    projet: str
    date: str
    echelle: int | None = None
    avec_cartouche: bool = True

    transformation: TransformationL93 | None = field(default=None, init=False)
    _fond: list[str] = field(default_factory=list, init=False)
    _carto: list[str] = field(default_factory=list, init=False)
    _habillage: list[str] = field(default_factory=list, init=False)
    _defs: list[str] = field(default_factory=list, init=False)
    _cartouche_compose: bool = field(default=False, init=False)

    def __post_init__(self):
        if self.echelle is not None:
            self.definir_echelle(self.echelle)

    # -- géométrie du gabarit ------------------------------------------------

    def zone_dessin(self) -> tuple[float, float, float, float]:
        """(x_mm, y_mm, largeur_mm, hauteur_mm) de la zone utile de dessin."""
        x, y, largeur, _ = CADRE
        bas = Y_CARTOUCHE if self.avec_cartouche else HAUTEUR_MM - MARGE_MM
        return (x, y, largeur, bas - y)

    def definir_echelle(self, denominateur: int, centre_l93=None) -> None:
        """Fixe l'échelle de la planche, et donc la transformation terrain/papier.

        `centre_l93` peut être précisé plus tard par `centrer_sur`.
        """
        self.echelle = int(denominateur)
        centre = centre_l93 or (
            self.transformation.centre_l93 if self.transformation else (0.0, 0.0)
        )
        self.transformation = TransformationL93(
            self.zone_dessin(), self.echelle, centre
        )

    def centrer_sur(self, centre_l93: tuple[float, float]) -> None:
        if self.echelle is None:
            raise ErreurEchelle(
                f"Planche « {self.titre} » : définissez l'échelle avant de centrer."
            )
        self.transformation = TransformationL93(
            self.zone_dessin(), self.echelle, centre_l93
        )

    def emprise_terrain(self) -> tuple[float, float, float, float]:
        """Emprise Lambert 93 couverte par la zone de dessin à l'échelle définie."""
        return self._transformation().emprise

    def _transformation(self) -> TransformationL93:
        if self.transformation is None:
            raise ErreurEchelle(
                f"Planche « {self.titre} » : aucune échelle définie. "
                "Appelez definir_echelle() avant de dessiner du contenu géographique."
            )
        return self.transformation

    # -- contenu géographique ------------------------------------------------

    def ajouter_fond_raster(self, image, bbox_l93, qualite: int = 85) -> None:
        """Place une image raster à sa bbox Lambert 93 exacte.

        L'image doit avoir été demandée à cette bbox : aucun recadrage n'est
        fait ici, car recadrer réintroduirait une erreur d'échelle.
        """
        transformation = self._transformation()
        minx, miny, maxx, maxy = bbox_l93
        x0, y0 = transformation.point(minx, maxy)
        x1, y1 = transformation.point(maxx, miny)

        # .convert("RGB") avant tout encodage : critique pour la mémoire.
        if image.mode != "RGB":
            image = image.convert("RGB")
        tampon = io.BytesIO()
        image.save(tampon, format="JPEG", quality=qualite, optimize=True)
        donnees = base64.b64encode(tampon.getvalue()).decode("ascii")

        self._fond.append(
            f'<image x="{_n(x0)}" y="{_n(y0)}" width="{_n(x1 - x0)}" '
            f'height="{_n(y1 - y0)}" preserveAspectRatio="none" '
            f'xlink:href="data:image/jpeg;base64,{donnees}"/>'
        )

    def ajouter_geometrie(self, geom, style: Style | dict = STYLE_EMPRISE) -> None:
        """Trace une géométrie shapely exprimée en Lambert 93."""
        chemin = self._chemin(geom)
        if not chemin:
            return
        self._carto.append(f'<path d="{chemin}" {_style_attributs(style)}/>')

    def ajouter_etiquettes(
        self,
        points,
        textes,
        style: dict | None = None,
    ) -> None:
        """Étiquette des points Lambert 93 (numéros de parcelle, repères).

        `style` accepte les clés `taille_mm`, `couleur`, `ancre`, `gras`,
        `halo` (contour blanc pour la lisibilité sur photo aérienne).
        """
        style = dict(style or {})
        taille = style.get("taille_mm", TAILLE_ETIQUETTE)
        couleur = style.get("couleur", NOIR)
        ancre = style.get("ancre", "middle")
        gras = style.get("gras", False)
        halo = style.get("halo", True)
        decalage = style.get("decalage_mm", 0.0)

        transformation = self._transformation()
        for point, texte in zip(points, textes):
            x_l93, y_l93 = (point.x, point.y) if hasattr(point, "x") else point
            x_mm, y_mm = transformation.point(x_l93, y_l93)
            self._carto.append(
                self._element_texte(
                    x_mm,
                    y_mm + decalage,
                    str(texte),
                    taille=taille,
                    couleur=couleur,
                    ancre=ancre,
                    gras=gras,
                    halo=halo,
                )
            )

    # -- contenu en repère papier -------------------------------------------

    def ajouter_texte(
        self,
        x_mm: float,
        y_mm: float,
        texte: str,
        taille: float = TAILLE_COURANTE,
        couleur: str = NOIR,
        ancre: str = "start",
        gras: bool = False,
        halo: bool = False,
        habillage: bool = True,
    ) -> None:
        element = self._element_texte(
            x_mm, y_mm, texte, taille=taille, couleur=couleur,
            ancre=ancre, gras=gras, halo=halo,
        )
        (self._habillage if habillage else self._carto).append(element)

    def ajouter_bloc_texte(
        self,
        x_mm: float,
        y_mm: float,
        lignes,
        taille: float = TAILLE_COURANTE,
        interligne: float = 1.35,
        **kwargs,
    ) -> float:
        """Empile des lignes déjà découpées et renvoie l'ordonnée finale."""
        lignes = list(lignes)
        pas = taille * interligne
        for index, ligne in enumerate(lignes):
            self.ajouter_texte(x_mm, y_mm + index * pas, ligne, taille=taille, **kwargs)
        return y_mm + len(lignes) * pas

    def mesurer_texte(self, texte: str, taille: float, gras: bool = False) -> float:
        """Largeur d'un texte en millimètres, telle que cairo la composera.

        Le SVG est en millimètres et la mesure passe par le moteur qui fera le
        rendu : la valeur est donc directement exploitable pour la mise en page.
        """
        return chasse_cairo(texte, famille_active(), taille, gras)

    def decouper_en_lignes(self, texte: str, largeur_mm: float, taille: float,
                           gras: bool = False) -> list:
        """Découpe un texte en lignes tenant dans `largeur_mm`."""
        lignes, courante = [], []
        for mot in texte.split():
            essai = courante + [mot]
            if courante and self.mesurer_texte(" ".join(essai), taille, gras) > largeur_mm:
                lignes.append(courante)
                courante = [mot]
            else:
                courante = essai
        if courante:
            lignes.append(courante)
        return lignes

    def ajouter_paragraphe(
        self,
        x_mm: float,
        y_mm: float,
        texte: str,
        largeur_mm: float,
        taille: float = TAILLE_COURANTE,
        interligne: float = 1.35,
        justifie: bool = True,
        gras: bool = False,
        couleur: str = NOIR,
        habillage: bool = True,
    ) -> float:
        """Bloc de texte suivi, justifié, et renvoie l'ordonnée de la ligne suivante.

        SVG n'a pas de justification et CairoSVG n'implémente ni `textLength` ni
        `lengthAdjust` : chaque mot est donc positionné individuellement, à
        partir des chasses mesurées par cairo lui-même. La justification est
        exacte au rendu, et non approchée.
        """
        cible = self._habillage if habillage else self._carto
        lignes = self.decouper_en_lignes(texte, largeur_mm, taille, gras)
        pas = taille * interligne
        espace = self.mesurer_texte(" ", taille, gras)

        for index, mots in enumerate(lignes):
            ordonnee = y_mm + index * pas
            derniere = index == len(lignes) - 1
            if not justifie or derniere or len(mots) == 1:
                cible.append(
                    self._element_texte(
                        x_mm, ordonnee, " ".join(mots), taille=taille,
                        couleur=couleur, gras=gras,
                    )
                )
                continue
            chasses = [self.mesurer_texte(mot, taille, gras) for mot in mots]
            blanc = (largeur_mm - sum(chasses)) / (len(mots) - 1)
            # Une ligne trop serrée serait illisible : on retombe sur l'espace
            # normal plutôt que de faire chevaucher les mots.
            if blanc < espace * 0.5:
                blanc = espace
            abscisse = x_mm
            for mot, chasse in zip(mots, chasses):
                cible.append(
                    self._element_texte(
                        abscisse, ordonnee, mot, taille=taille,
                        couleur=couleur, gras=gras,
                    )
                )
                abscisse += chasse + blanc
        return y_mm + len(lignes) * pas

    def ajouter_rectangle(
        self, x_mm, y_mm, largeur_mm, hauteur_mm, style: Style | dict = Style(),
        habillage: bool = True,
    ) -> None:
        element = (
            f'<rect x="{_n(x_mm)}" y="{_n(y_mm)}" width="{_n(largeur_mm)}" '
            f'height="{_n(hauteur_mm)}" {_style_attributs(style)}/>'
        )
        (self._habillage if habillage else self._carto).append(element)

    def ajouter_ligne(self, x1, y1, x2, y2, style: Style | dict = Style(),
                      habillage: bool = True) -> None:
        element = (
            f'<line x1="{_n(x1)}" y1="{_n(y1)}" x2="{_n(x2)}" y2="{_n(y2)}" '
            f'{_style_attributs(style)}/>'
        )
        (self._habillage if habillage else self._carto).append(element)

    def ajouter_image_mm(
        self, chemin, x_mm, y_mm, largeur_mm, hauteur_mm, ajuster: str = "contenir",
    ) -> tuple[float, float, float, float]:
        """Place une image dans un cadre du repère papier.

        `ajuster="contenir"` conserve les proportions et centre l'image dans le
        cadre ; la zone réellement occupée est renvoyée.
        """
        from PIL import Image as _Image

        chemin = Path(chemin)
        with _Image.open(chemin) as image:
            largeur_px, hauteur_px = image.size
            transparence = image.mode in ("RGBA", "LA", "P")
            # Aplatir sur blanc : un simple convert("RGB") remplirait de noir
            # les zones transparentes, ce qui se voit sur le logo.
            if transparence:
                image = image.convert("RGBA")
                fond = _Image.new("RGBA", image.size, (255, 255, 255, 255))
                image = _Image.alpha_composite(fond, image)
            image_rgb = image.convert("RGB")
            tampon = io.BytesIO()
            # PNG pour les aplats et les traits nets (logo), JPEG pour les photos.
            if transparence or largeur_px * hauteur_px < 1_000_000:
                type_mime = "png"
                image_rgb.save(tampon, format="PNG", optimize=True)
            else:
                type_mime = "jpeg"
                image_rgb.save(tampon, format="JPEG", quality=90, optimize=True)
        donnees = base64.b64encode(tampon.getvalue()).decode("ascii")

        if ajuster == "contenir" and largeur_px and hauteur_px:
            facteur = min(largeur_mm / largeur_px, hauteur_mm / hauteur_px)
            largeur_reelle = largeur_px * facteur
            hauteur_reelle = hauteur_px * facteur
            x_reel = x_mm + (largeur_mm - largeur_reelle) / 2.0
            y_reel = y_mm + (hauteur_mm - hauteur_reelle) / 2.0
        else:
            largeur_reelle, hauteur_reelle = largeur_mm, hauteur_mm
            x_reel, y_reel = x_mm, y_mm

        self._habillage.append(
            f'<image x="{_n(x_reel)}" y="{_n(y_reel)}" width="{_n(largeur_reelle)}" '
            f'height="{_n(hauteur_reelle)}" '
            f'xlink:href="data:image/{type_mime};base64,{donnees}"/>'
        )
        return (x_reel, y_reel, largeur_reelle, hauteur_reelle)

    # -- légende -------------------------------------------------------------

    def ajouter_legende(
        self,
        entrees,
        position: tuple[float, float] | None = None,
        largeur_mm: float = 62.0,
        titre: str | None = "Légende",
    ) -> tuple[float, float, float, float]:
        """Bloc encadré à fond blanc. Par défaut en haut à gauche de la zone."""
        entrees = [
            e if isinstance(e, EntreeLegende) else EntreeLegende(e[0], e[1])
            for e in entrees
        ]
        zone_x, zone_y, _, _ = self.zone_dessin()
        x_mm, y_mm = position or (zone_x + 3.0, zone_y + 3.0)

        marge = 2.2
        pas = 5.0
        hauteur_titre = 5.0 if titre else 0.0
        hauteur = 2 * marge + hauteur_titre + pas * len(entrees)

        self._habillage.append(
            f'<rect x="{_n(x_mm)}" y="{_n(y_mm)}" width="{_n(largeur_mm)}" '
            f'height="{_n(hauteur)}" fill="#ffffff" fill-opacity="0.92" '
            f'stroke="{NOIR}" stroke-width="0.25"/>'
        )
        curseur = y_mm + marge
        if titre:
            self.ajouter_texte(
                x_mm + marge, curseur + 3.0, titre,
                taille=TAILLE_CARTOUCHE, gras=True,
            )
            curseur += hauteur_titre
        for entree in entrees:
            haut = curseur + 1.0
            self._habillage.append(
                f'<rect x="{_n(x_mm + marge)}" y="{_n(haut)}" width="6" '
                f'height="3" {_style_attributs(entree.style)}/>'
            )
            self.ajouter_texte(
                x_mm + marge + 8.0, haut + 2.6, entree.libelle,
                taille=TAILLE_COURANTE,
            )
            curseur += pas
        return (x_mm, y_mm, largeur_mm, hauteur)

    # -- rendu ---------------------------------------------------------------

    def svg(self) -> str:
        if self.avec_cartouche and not self._cartouche_compose:
            self._composer_cartouche()
            self._cartouche_compose = True
        parties = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{_n(LARGEUR_MM)}mm" height="{_n(HAUTEUR_MM)}mm" '
            f'viewBox="0 0 {_n(LARGEUR_MM)} {_n(HAUTEUR_MM)}">',
            "<defs>",
            self._clip_zone(),
            *self._defs,
            "</defs>",
            f'<rect x="0" y="0" width="{_n(LARGEUR_MM)}" height="{_n(HAUTEUR_MM)}" '
            f'fill="#ffffff"/>',
            '<g clip-path="url(#zone-dessin)">',
            *self._fond,
            *self._carto,
            "</g>",
            *self._habillage,
            "</svg>",
        ]
        return "\n".join(parties)

    def rendre_pdf(self, chemin) -> Path:
        """Écrit la planche en PDF vectoriel de 420 x 297 mm."""
        try:
            import cairosvg
        except Exception as exc:  # pragma: no cover - dépend de l'environnement
            raise ErreurRendu(
                "CairoSVG indisponible : "
                f"{exc}. Sous Linux, installez les bibliothèques système listées "
                "dans packages.txt (libcairo2). Aucune planche n'est produite."
            ) from exc

        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        try:
            cairosvg.svg2pdf(
                bytestring=self.svg().encode("utf-8"), write_to=str(chemin)
            )
        except Exception as exc:
            raise ErreurRendu(
                f"Rendu PDF impossible pour la planche « {self.titre} » : {exc}"
            ) from exc
        return chemin

    def rendre_apercu_png(self, chemin, dpi: int = 72) -> Path:
        """Aperçu écran, sans valeur métrologique : ne pas imprimer."""
        import cairosvg

        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        cairosvg.svg2png(
            bytestring=self.svg().encode("utf-8"), write_to=str(chemin), dpi=dpi
        )
        return chemin

    # -- internes ------------------------------------------------------------

    def _clip_zone(self) -> str:
        x, y, largeur, hauteur = self.zone_dessin()
        return (
            '<clipPath id="zone-dessin">'
            f'<rect x="{_n(x)}" y="{_n(y)}" width="{_n(largeur)}" '
            f'height="{_n(hauteur)}"/></clipPath>'
        )

    def _element_texte(
        self, x_mm, y_mm, texte, taille, couleur=NOIR, ancre="start",
        gras=False, halo=False,
    ) -> str:
        commun = (
            f'x="{_n(x_mm)}" y="{_n(y_mm)}" font-family="{famille_active()}" '
            f'font-size="{_n(taille)}" text-anchor="{ancre}"'
            + (' font-weight="bold"' if gras else "")
        )
        contenu = escape(str(texte))
        elements = []
        if halo:
            elements.append(
                f'<text {commun} fill="none" stroke="#ffffff" stroke-width="0.6" '
                f'stroke-linejoin="round">{contenu}</text>'
            )
        elements.append(f'<text {commun} fill="{couleur}">{contenu}</text>')
        return "".join(elements)

    def _chemin(self, geom) -> str:
        """Géométrie shapely (Lambert 93) vers un attribut `d` de path SVG."""
        transformation = self._transformation()
        segments: list[str] = []

        def anneau(coords, fermer=True):
            points = transformation.points(coords)
            if not points:
                return
            debut = f"M {_n(points[0][0])} {_n(points[0][1])}"
            suite = " ".join(f"L {_n(x)} {_n(y)}" for x, y in points[1:])
            segments.append(f"{debut} {suite}" + (" Z" if fermer else ""))

        def visiter(g):
            type_geom = g.geom_type
            if type_geom == "Polygon":
                anneau(g.exterior.coords)
                for interieur in g.interiors:
                    anneau(interieur.coords)
            elif type_geom in ("MultiPolygon", "MultiLineString", "GeometryCollection"):
                for partie in g.geoms:
                    visiter(partie)
            elif type_geom == "LinearRing":
                anneau(g.coords)
            elif type_geom == "LineString":
                anneau(g.coords, fermer=False)
            else:
                raise TypeError(
                    f"Type de géométrie non tracé par ajouter_geometrie : {type_geom}"
                )

        if geom is None or geom.is_empty:
            return ""
        visiter(geom)
        return " ".join(segments)

    # -- cartouche -----------------------------------------------------------

    def _composer_cartouche(self) -> None:
        cadre_x, cadre_y, cadre_l, cadre_h = CADRE
        trait = Style(trait=NOIR, epaisseur_mm=0.35, remplissage="none")
        fin = Style(trait=NOIR, epaisseur_mm=0.25, remplissage="none")

        # Cadre extérieur
        self.ajouter_rectangle(cadre_x, cadre_y, cadre_l, cadre_h, trait)
        # Cartouche et bandeau
        self.ajouter_rectangle(cadre_x, Y_CARTOUCHE, cadre_l, CARTOUCHE_MM, trait)
        self.ajouter_rectangle(
            cadre_x, Y_BANDEAU, cadre_l, BANDEAU_MM,
            Style(trait=NOIR, epaisseur_mm=0.25, remplissage=GRIS_FOND),
        )

        cases = dict((nom, (x, largeur)) for nom, x, largeur in CASES_CARTOUCHE)
        for _, x, _largeur in CASES_CARTOUCHE[1:]:
            self.ajouter_ligne(x, Y_CARTOUCHE, x, Y_CARTOUCHE + CARTOUCHE_MM, fin)

        # 1. Logo UNITe
        x_logo, largeur_logo = cases["logo"]
        if LOGO_UNITE.exists():
            self.ajouter_image_mm(
                LOGO_UNITE, x_logo + 1.5, Y_CARTOUCHE + 1.2,
                largeur_logo - 3.0, CARTOUCHE_MM - 2.4,
            )

        # 2. Nom du projet et phase
        x_projet, largeur_projet = cases["projet"]
        self.ajouter_texte(
            x_projet + 2.5, Y_CARTOUCHE + 6.2, self.projet,
            taille=TAILLE_CARTOUCHE, gras=True, couleur=BLEU_UNITE,
        )
        self.ajouter_texte(
            x_projet + 2.5, Y_CARTOUCHE + 11.4, "PHASE : DP", taille=TAILLE_COURANTE,
        )

        # 3. Titre de la planche, centré
        x_titre, largeur_titre = cases["titre"]
        self.ajouter_texte(
            x_titre + largeur_titre / 2.0, Y_CARTOUCHE + 9.6, self.titre,
            taille=TAILLE_TITRE_CARTOUCHE, ancre="middle", gras=True,
            couleur=BLEU_UNITE,
        )

        # 4. Flèche nord (nord de la grille Lambert 93)
        x_nord, largeur_nord = cases["nord"]
        self._fleche_nord(x_nord, largeur_nord)

        # 5. Échelle, date, numéro
        valeurs = (
            ("echelle", "ÉCHELLE", formater_echelle(self.echelle) if self.echelle else "—"),
            ("date", "DATE", self.date),
            ("numero", "NUMÉRO", self.numero),
        )
        for nom, intitule, valeur in valeurs:
            x_case, largeur_case = cases[nom]
            centre = x_case + largeur_case / 2.0
            self.ajouter_texte(
                centre, Y_CARTOUCHE + 5.4, intitule,
                taille=TAILLE_ETIQUETTE, ancre="middle", couleur=GRIS,
            )
            self.ajouter_texte(
                centre, Y_CARTOUCHE + 11.4, str(valeur),
                taille=TAILLE_CARTOUCHE, ancre="middle", gras=True,
                couleur=BLEU_UNITE,
            )

        # Bandeau inférieur
        y_texte = Y_BANDEAU + 2.9
        self.ajouter_texte(
            cadre_x + 2.0, y_texte, f"UNITe — {self.projet} — {self.date}",
            taille=TAILLE_ETIQUETTE,
        )
        self.ajouter_texte(
            cadre_x + cadre_l - 2.0, y_texte, MENTION_BANDEAU,
            taille=TAILLE_ETIQUETTE, ancre="end",
        )

    def _fleche_nord(self, x_case: float, largeur_case: float) -> None:
        """Flèche orientée selon le nord de la grille Lambert 93.

        En Lambert 93 le nord de la grille diffère du nord géographique
        (convergence des méridiens, jusqu'à environ 3° en métropole). Les axes
        de la planche étant ceux du Lambert 93, la flèche pointe vers le haut de
        la feuille et n'affirme rien d'autre — d'où la mention « L93 ».
        """
        centre = x_case + largeur_case / 2.0
        self.ajouter_texte(
            centre, Y_CARTOUCHE + 5.4, "NORD (L93)",
            taille=TAILLE_ETIQUETTE, ancre="middle", couleur=GRIS,
        )

        axe = centre + 2.6
        pointe = Y_CARTOUCHE + 7.0
        base = Y_CARTOUCHE + 13.2
        echancrure = base - 1.8
        demi = 2.5
        self._habillage.append(
            f'<path d="M {_n(axe)} {_n(pointe)} '
            f'L {_n(axe + demi)} {_n(base)} '
            f'L {_n(axe)} {_n(echancrure)} '
            f'L {_n(axe - demi)} {_n(base)} Z" '
            f'fill="none" stroke="{BLEU_UNITE}" stroke-width="0.4" '
            f'stroke-linejoin="round"/>'
        )
        self.ajouter_texte(
            axe - 6.0, Y_CARTOUCHE + 12.4, "N",
            taille=11 * PT, ancre="middle", gras=True, couleur=BLEU_UNITE,
        )
