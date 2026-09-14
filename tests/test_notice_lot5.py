"""Notice DP 11, mesurée dans le PDF produit.

Le critère n'est pas « la fusion s'exécute » mais « la planche produite porte
la notice, entière, lisible et à sa page ». Deux mesures portent tout le lot :

- le **texte reste du texte** — extrait du PDF de sortie, pas regardé à
  l'écran. C'est ce qui distingue la fusion d'une rastérisation, et c'est
  indétectable à l'œil ;
- rien du PDF déposé ne descend **sous `Y_CARTOUCHE`** — mesuré sur la position
  réelle des textes dans la page produite, pas sur la transformation calculée.

Aucun service en ligne n'est demandé : la notice de synthèse est composée par
cairo, comme les planches, et le reste se mesure sur les fichiers écrits.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from dp_socle.echelle import formater_echelle
from dp_socle.erreurs import ErreurNotice, ErreurRendu
from dp_socle.planche import HAUTEUR_MM, Y_CARTOUCHE, Planche
from dp_socle.planches import dp11_notice
from dp_socle.planches.commun import Sortie
from dp_socle.projet import Projet

pytest.importorskip(
    "cairosvg", reason="CairoSVG et libcairo sont nécessaires pour produire le PDF"
)

MM_PAR_PT = 25.4 / 72.0

#: Corps du texte de la notice de synthèse, en millimètres de hauteur SVG.
#: 3,5 mm valent 9,92 pt : l'ordre de grandeur d'un corps de notice.
CORPS_MM = 3.5

#: Ordonnées du texte dans la notice de synthèse, en mm depuis son haut.
LIGNES_MM = (28.0, 43.0, 280.0)


def _page_svg(texte: str, largeur_mm: float, hauteur_mm: float) -> bytes:
    """Une page de notice : un fond blanc, et du texte jusqu'en bas de page.

    Le fond blanc n'est pas décoratif : c'est lui qui recouvrirait le filet du
    cadre si la notice était posée à fleur de la zone de dessin. La ligne basse
    à 280 mm sert à vérifier que le bas de la notice ne tombe pas dans le
    cartouche.
    """
    lignes = "".join(
        f'<text x="20" y="{y}" font-family="sans-serif" '
        f'font-size="{CORPS_MM}">{texte} — ligne {index + 1}</text>'
        for index, y in enumerate(LIGNES_MM)
        if y < hauteur_mm
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur_mm}mm" '
        f'height="{hauteur_mm}mm" viewBox="0 0 {largeur_mm} {hauteur_mm}">'
        f'<rect x="0" y="0" width="{largeur_mm}" height="{hauteur_mm}" '
        'fill="#ffffff"/>'
        f"{lignes}</svg>"
    ).encode("utf-8")


def notice_synthetique(
    chemin: Path, textes, largeur_mm: float = 210.0, hauteur_mm: float = 297.0
) -> Path:
    """Un PDF de notice, une page par texte, au format demandé."""
    import cairosvg

    ecrivain = PdfWriter()
    for texte in textes:
        rendu = cairosvg.svg2pdf(
            bytestring=_page_svg(texte, largeur_mm, hauteur_mm)
        )
        ecrivain.add_page(PdfReader(io.BytesIO(rendu)).pages[0])
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "wb") as fichier:
        ecrivain.write(fichier)
    return chemin


def _projet(tmp_path: Path, notice: Path | None = None) -> Projet:
    """Un projet minimal : rien de géographique n'est demandé à la notice."""
    emprise = tmp_path / "emprise.geojson"
    emprise.write_text("{}", encoding="utf-8")
    return Projet(
        nom="Essai",
        commune="Essai",
        code_postal="45000",
        date="2026-09-14",
        emprise=str(emprise),
        notice=str(notice) if notice else None,
    )


def _textes(chemin: Path, page: int = 0):
    """Les textes de la page, avec leur position et leur corps réels.

    Rend des couples (x_mm, y_mm depuis le haut de la feuille, corps_pt,
    texte). La matrice de texte et la matrice courante sont composées : un
    contenu fusionné vit sous une matrice d'échelle, et lire `tm` seul
    donnerait la position d'avant la fusion.
    """
    releve = []

    def visiteur(texte, cm, tm, police, corps):
        if not texte.strip():
            return
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        echelle = abs(tm[3] * cm[3]) or 1.0
        releve.append(
            (
                x * MM_PAR_PT,
                HAUTEUR_MM - y * MM_PAR_PT,
                corps * echelle,
                texte.strip(),
            )
        )

    PdfReader(str(chemin)).pages[page].extract_text(visitor_text=visiteur)
    return releve


# ---------------------------------------------------------------------------
# Critère n°1 — une page fournie, une planche A3 paysage
# ---------------------------------------------------------------------------


def test_trois_pages_donnent_trois_planches_a3(tmp_path):
    source = notice_synthetique(tmp_path / "notice.pdf", ["UNE", "DEUX", "TROIS"])
    sortie = dp11_notice.generer(
        _projet(tmp_path, source), source, tmp_path / "sortie", premier_numero=10
    )

    pages = PdfReader(str(sortie.chemin)).pages
    assert len(pages) == 3
    for page in pages:
        assert round(float(page.mediabox.width) * MM_PAR_PT, 1) == 420.0
        assert round(float(page.mediabox.height) * MM_PAR_PT, 1) == 297.0


# ---------------------------------------------------------------------------
# Critère n°2 — le texte de la notice reste du texte
# ---------------------------------------------------------------------------


def test_le_texte_de_la_notice_reste_du_texte(tmp_path):
    """Extraction, pas inspection visuelle : une rastérisation passerait l'œil.

    Le corps mesuré dans la planche vaut celui de la notice multiplié par le
    facteur d'ajustement — c'est la signature d'un texte transformé, là où une
    image n'aurait rendu aucun texte du tout.
    """
    source = notice_synthetique(tmp_path / "notice.pdf", ["ARTICLE PREMIER"])
    sortie = dp11_notice.generer(
        _projet(tmp_path, source), source, tmp_path / "sortie", premier_numero=10
    )

    textes = _textes(sortie.chemin)
    lignes = [t for t in textes if "ARTICLE PREMIER" in t[3]]
    assert len(lignes) == len(LIGNES_MM), textes

    facteur = sortie.details["notice"]["facteur_min"]
    corps_attendu = CORPS_MM / MM_PAR_PT * facteur
    for _, _, corps, _texte in lignes:
        assert corps == pytest.approx(corps_attendu, abs=0.1)


# ---------------------------------------------------------------------------
# Critère n°3 — la notice ne mord pas sur le cartouche
# ---------------------------------------------------------------------------


def test_la_notice_ne_descend_pas_sous_le_cartouche(tmp_path):
    """Y compris une notice dont le texte court jusqu'au bas de sa page.

    La ligne à 280 mm d'une A4 portrait est à 17 mm de son bord inférieur :
    posée sans précaution, elle tomberait au milieu du cartouche.
    """
    source = notice_synthetique(tmp_path / "notice.pdf", ["BAS DE PAGE"])
    sortie = dp11_notice.generer(
        _projet(tmp_path, source), source, tmp_path / "sortie", premier_numero=10
    )

    lignes = [t for t in _textes(sortie.chemin) if "BAS DE PAGE" in t[3]]
    assert lignes
    for _x, y_mm, _corps, texte in lignes:
        assert y_mm < Y_CARTOUCHE, (texte, y_mm)


def test_la_notice_ne_touche_pas_le_cadre(tmp_path):
    """Le blanc tournant du dossier vaut aussi pour une pièce fournie.

    Une page qui peint son propre fond blanc recouvrirait la moitié du filet du
    cadre, celui-ci étant centré sur la limite de la zone de dessin. Mesuré sur
    la hauteur, l'axe contraignant d'une A4 portrait : le contenu fusionné doit
    commencer sous le haut du cadre et finir au-dessus du cartouche.
    """
    source = notice_synthetique(tmp_path / "notice.pdf", ["CADRE"])
    planche_temoin = Planche(titre="T", numero="T", projet="T", date="14/09/2026")
    _x, y_zone, _l, hauteur_zone = dp11_notice.zone_utile(planche_temoin)

    sortie = dp11_notice.generer(
        _projet(tmp_path, source), source, tmp_path / "sortie", premier_numero=10
    )
    facteur = sortie.details["notice"]["facteur_min"]

    # La page A4 est contrainte en hauteur : son fond occupe exactement la
    # hauteur utile, dont les bornes se déduisent du facteur mesuré.
    haut_notice = y_zone + (hauteur_zone - 297.0 * facteur) / 2.0
    assert haut_notice > 5.0, "la notice couvre le filet haut du cadre"
    assert haut_notice + 297.0 * facteur < Y_CARTOUCHE, "la notice entre au cartouche"


# ---------------------------------------------------------------------------
# Critère n°5 — chaque page porte son propre numéro
# ---------------------------------------------------------------------------


def test_chaque_page_porte_son_numero(tmp_path):
    """Décision D3 : Massay porte NUMERO 16 puis NUMERO 17 sur sa notice."""
    source = notice_synthetique(tmp_path / "notice.pdf", ["UNE", "DEUX", "TROIS"])
    sortie = dp11_notice.generer(
        _projet(tmp_path, source), source, tmp_path / "sortie", premier_numero=16
    )

    assert sortie.numeros == (16, 17, 18)
    for index, attendu in enumerate(sortie.numeros):
        textes = [t[3] for t in _textes(sortie.chemin, page=index)]
        assert "NUMÉRO" in textes
        assert str(attendu) in textes, (index, textes)


def test_le_cartouche_de_la_notice_n_a_ni_nord_ni_echelle(tmp_path):
    """Décision D6, et le dossier de référence : ni ÉCHELLE, ni NORD.

    Le reste du cartouche ne bouge pas : c'est lui que le chef de projet veut
    voir, et c'est l'habillage commun du dossier.
    """
    source = notice_synthetique(tmp_path / "notice.pdf", ["UNE"])
    sortie = dp11_notice.generer(
        _projet(tmp_path, source), source, tmp_path / "sortie", premier_numero=10
    )

    textes = [t[3] for t in _textes(sortie.chemin)]
    assert "ÉCHELLE" not in textes
    assert not any("NORD" in t for t in textes), textes
    for attendu in ("PHASE : DP", "DATE", "NUMÉRO", "DP 11 : NOTICE"):
        assert attendu in textes, (attendu, textes)


def test_les_planches_cartographiques_gardent_leurs_reperes():
    """La garantie de l'exception : le défaut reproduit le comportement actuel.

    Composée sans rien préciser, une planche porte toujours sa flèche nord et
    sa case ÉCHELLE — sans quoi le paramètre ne serait pas additif.
    """
    svg = Planche(
        titre="TÉMOIN", numero="2", projet="Essai", date="14/09/2026", echelle=5000
    ).svg()
    assert "NORD (L93)" in svg
    assert "ÉCHELLE" in svg
    assert formater_echelle(5000) in svg


# ---------------------------------------------------------------------------
# Critère n°7 — ce qui n'est pas une notice est refusé, pas absorbé
# ---------------------------------------------------------------------------


def test_un_fichier_qui_n_est_pas_un_pdf_est_refuse(tmp_path):
    faux = tmp_path / "notice.pdf"
    faux.write_bytes(b"Ceci n'est pas un PDF, c'est un document Word renomme.")
    with pytest.raises(ErreurNotice, match="illisible"):
        dp11_notice.generer(
            _projet(tmp_path, faux), faux, tmp_path / "sortie", premier_numero=10
        )


def test_un_pdf_sans_page_est_refuse(tmp_path):
    vide = tmp_path / "notice.pdf"
    with open(vide, "wb") as fichier:
        PdfWriter().write(fichier)
    with pytest.raises(ErreurNotice, match="aucune page"):
        dp11_notice.generer(
            _projet(tmp_path, vide), vide, tmp_path / "sortie", premier_numero=10
        )


def test_une_notice_introuvable_est_refusee(tmp_path):
    absente = tmp_path / "jamais_deposee.pdf"
    with pytest.raises(ErreurNotice, match="introuvable"):
        dp11_notice.generer(
            _projet(tmp_path), absente, tmp_path / "sortie", premier_numero=10
        )


def test_un_plan_a1_depose_a_la_place_de_la_notice_est_refuse(tmp_path):
    """0,31 de facteur : le corps de texte tomberait sous 3,5 pt."""
    source = notice_synthetique(tmp_path / "notice.pdf", ["PLAN"], 594.0, 841.0)
    with pytest.raises(ErreurNotice, match="sous le minimum"):
        dp11_notice.generer(
            _projet(tmp_path, source), source, tmp_path / "sortie", premier_numero=10
        )


def test_une_notice_a2_passe_mais_le_rapport_le_dit(tmp_path):
    """Décision D2 : la réduction se voit avant l'instruction, pas après."""
    source = notice_synthetique(tmp_path / "notice.pdf", ["NOTICE"], 420.0, 594.0)
    sortie = dp11_notice.generer(
        _projet(tmp_path, source), source, tmp_path / "sortie", premier_numero=10
    )

    assert sortie.details["notice"]["facteur_min"] == pytest.approx(0.438, abs=0.005)
    avertissements = sortie.details["avertissements"]
    assert any("réduite au facteur" in message for message in avertissements)


# ---------------------------------------------------------------------------
# Ce que le rapport annonce d'une notice acceptée (décision D2)
# ---------------------------------------------------------------------------


def test_le_rapport_annonce_le_format_lu_et_le_facteur(tmp_path):
    source = notice_synthetique(tmp_path / "notice.pdf", ["UNE", "DEUX"])
    sortie = dp11_notice.generer(
        _projet(tmp_path, source), source, tmp_path / "sortie", premier_numero=10
    )

    lu = sortie.details["notice"]
    assert lu["source"] == "notice.pdf"
    assert lu["pages"] == 2
    assert lu["formats"] == ["A4 portrait (210 × 297 mm)"]
    assert lu["facteur_min"] == pytest.approx(0.8754, abs=0.0005)
    assert sortie.details["avertissements"] == []


def test_le_format_lu_ne_se_suppose_pas(tmp_path):
    """Décision D2 : lire `mediabox`, ne rien câbler sur A4 portrait."""
    source = notice_synthetique(tmp_path / "notice.pdf", ["UNE"], 420.0, 297.0)
    sortie = dp11_notice.generer(
        _projet(tmp_path, source), source, tmp_path / "sortie", premier_numero=10
    )
    assert sortie.details["notice"]["formats"] == ["A3 paysage (420 × 297 mm)"]


def test_une_page_couchee_est_redressee(tmp_path):
    """`/Rotate 90` n'est pas appliqué par la fusion : il faut le reporter.

    Sans le report, une notice exportée en portrait mais déclarée pivotée se
    serait retrouvée couchée dans le cadre — et à un facteur calculé sur les
    mauvaises dimensions.
    """
    source = notice_synthetique(tmp_path / "notice.pdf", ["COUCHEE"])
    lecteur = PdfReader(str(source))
    ecrivain = PdfWriter()
    page = lecteur.pages[0]
    page.rotation = 90
    ecrivain.add_page(page)
    pivotee = tmp_path / "notice_pivotee.pdf"
    with open(pivotee, "wb") as fichier:
        ecrivain.write(fichier)

    sortie = dp11_notice.generer(
        _projet(tmp_path, pivotee), pivotee, tmp_path / "sortie", premier_numero=10
    )
    # Une A4 portrait pivotée d'un quart de tour est une A4 paysage, et elle
    # s'ajuste alors sur la largeur : le format lu doit le dire.
    assert sortie.details["notice"]["formats"] == ["A4 paysage (297 × 210 mm)"]


# ---------------------------------------------------------------------------
# Critère n°4 — le contrôle de rang apprend qu'une pièce couvre des pages
# ---------------------------------------------------------------------------


def test_le_controle_de_rang_suit_une_piece_de_plusieurs_pages():
    from dp_socle.assemblage import _verifier_numerotation
    from dp_socle.dossier import codes_produits

    produites = codes_produits(["DP 1-1", "DP 1-2", "DP 1-3", "DP 11"])
    piece = Sortie(numero="DP 11", titre="Notice", chemin="x", numeros=(5, 6, 7))

    _verifier_numerotation(piece, nb_pages=3, premiere_page=5, produites=produites)

    with pytest.raises(ErreurRendu, match="occupe les pages"):
        _verifier_numerotation(
            piece, nb_pages=3, premiere_page=6, produites=produites
        )


def test_une_piece_qui_s_etend_sans_le_declarer_est_refusee():
    """Le garde-fou du lot 4, conservé : deux pages pour un seul numéro.

    C'est ce qui arriverait si une planche du socle se mettait un jour à
    déborder sans que sa numérotation le sache — le dossier partirait avec un
    cartouche faux sur toutes les pièces suivantes.
    """
    from dp_socle.assemblage import _verifier_numerotation
    from dp_socle.dossier import codes_produits

    produites = codes_produits(["DP 1-1"])
    piece = Sortie(numero="DP 1-1", titre="Plan de situation", chemin="x")
    with pytest.raises(ErreurRendu, match="2 pages produites"):
        _verifier_numerotation(
            piece, nb_pages=2, premiere_page=2, produites=produites
        )
# ---------------------------------------------------------------------------
# La notice est obligatoire, sauf pour un dossier d'étude amont
# ---------------------------------------------------------------------------
#
# Le critère n°6 du brief disait l'inverse — « un dossier sans notice se
# produit quand même » — et la décision D4 avec lui. Le chef de projet a
# tranché le 14/09/2026 : la notice n'est pas facultative. Seul le dossier
# réduit au socle, produit sans plan du bureau d'études et annoncé comme non
# déposable, s'en passe : sa notice n'est pas encore écrite.


def test_un_dossier_d_etude_amont_se_produit_sans_notice(tmp_path):
    from dp_socle.assemblage import _notice_eventuelle

    sortie, message = _notice_eventuelle(_projet(tmp_path), [], tmp_path)

    assert sortie is None
    assert "étude amont" in message


def test_un_dossier_complet_sans_notice_est_refuse(tmp_path, monkeypatch):
    """Et refusé **avant** de télécharger le moindre fond IGN.

    Le refus tombe entre le chargement du contrat d'entrée et la première
    planche : `dp1_1_situation.generer` est remplacé par une sentinelle qui
    échouerait si on allait jusque-là.
    """
    import dp_socle.assemblage as assemblage

    def jamais(*args, **kwargs):  # pragma: no cover - ne doit pas être atteint
        raise AssertionError("une planche a été dessinée malgré l'absence de notice")

    monkeypatch.setattr(assemblage.dp1_1_situation, "generer", jamais)
    monkeypatch.setattr(
        assemblage, "charger_emprise", lambda _chemin: _EmpriseFactice()
    )
    monkeypatch.setattr(
        assemblage,
        "_charger_contrat_eventuel",
        lambda _dossier, _projet: (_ContratFactice(), None),
    )

    projet = _projet(tmp_path)
    projet.emprise = str(tmp_path / "emprise.geojson")
    with pytest.raises(ErreurNotice, match="obligatoire"):
        assemblage.generer_dossier(projet, tmp_path / "sortie")


class _EmpriseFactice:
    reprojetee = False
    nb_polygones = 1
    crs_source = "EPSG:2154"


class _ContratFactice:
    origine = "import_be"
    profil = None


def test_la_notice_est_controlee_avant_de_dessiner(tmp_path):
    """Une notice illisible ne se découvre pas après les fonds IGN.

    `examiner` refuse sans rien écrire : c'est ce que `generer_dossier` appelle
    au démarrage, avant la première requête au WMS-R.
    """
    faux = tmp_path / "notice.pdf"
    faux.write_bytes(b"Ceci n'est pas un PDF.")
    with pytest.raises(ErreurNotice, match="illisible"):
        dp11_notice.examiner(faux)

    trop_grand = notice_synthetique(tmp_path / "plan.pdf", ["PLAN"], 594.0, 841.0)
    with pytest.raises(ErreurNotice, match="sous le minimum"):
        dp11_notice.examiner(trop_grand)

    assert not list(tmp_path.glob("**/DP_11_notice.pdf"))


def test_le_rang_de_la_notice_se_compte_sur_les_pages_produites(tmp_path):
    """Et non sur le nombre de pièces : une pièce qui s'étendra la décalera.

    La page de garde occupe la page 1, d'où le décompte qui commence à 1.
    """
    from dp_socle.assemblage import _notice_eventuelle

    source = notice_synthetique(tmp_path / "notice.pdf", ["UNE", "DEUX"])
    deux_pages = notice_synthetique(tmp_path / "ailleurs.pdf", ["A", "B"])
    precedentes = [
        Sortie(numero="DP 1-1", titre="Situation", chemin=source.parent / "x.pdf"),
    ]
    # Une pièce précédente de deux pages : la notice commence deux rangs plus
    # loin, sans que personne ait à le lui dire.
    precedentes[0] = Sortie(
        numero="DP 1-1", titre="Situation", chemin=deux_pages, numeros=(2, 3)
    )
    sortie, message = _notice_eventuelle(
        _projet(tmp_path, source), precedentes, tmp_path / "sortie"
    )

    assert message is None
    assert sortie.numeros == (4, 5)
