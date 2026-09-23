"""Génération complète du dossier et assemblage du PDF final.

Le sommaire de la page de garde porte les numéros de page réels : les planches
sont donc produites d'abord, leurs pages comptées, puis la page de garde est
composée et le tout assemblé.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .contrat import Contrat, charger_contrat
from .erreurs import ErreurContrat, ErreurDP, ErreurRendu
from .dossier import codes_produits, numero_planche
from .planches.primitives import union_valide
from .geometrie import charger_emprise
from .ign import DPI_DEFAUT
from .planches import (
    dp1_1_situation,
    dp1_2_aerienne,
    dp1_3_cadastre,
    dp2_plan_masse,
    dp3_coupes,
    dp4_ouvrages,
    dp6_insertions,
    dp7_environnement_proche,
    dp8_paysage_lointain,
    dp11_notice,
    page_garde,
)
from .polices import EtatPolices, avertir_si_indisponible
from .projet import Projet

#: Dimensions attendues de chaque page, en points PostScript (A3 paysage).
LARGEUR_PT = 420.0 / 25.4 * 72.0
HAUTEUR_PT = 297.0 / 25.4 * 72.0
TOLERANCE_PT = 0.5

#: Taille visée pour le dossier assemblé.
TAILLE_MAX_MO = 25.0

#: Motif du nom du PDF assemblé.
#:
#: Le nom du projet y figure. Le fichier quitte presque toujours son dossier —
#: envoyé par courriel, déposé au guichet, relu à côté de deux autres indices du
#: même site — et trois « DP_complet.pdf » côte à côte ne se distinguent plus.
#: L'interface proposait déjà le téléchargement sous ce nom-là ; le fichier
#: écrit sur le disque porte désormais le même.
MOTIF_ASSEMBLAGE = "{nom}_DP_complet.pdf"


def nom_assemblage(projet: Projet) -> str:
    """Nom du PDF assemblé d'un projet."""
    return MOTIF_ASSEMBLAGE.format(nom=projet.nom)


@dataclass
class Rapport:
    """Compte rendu d'une génération, destiné à être affiché dans l'interface."""

    dossier: Path
    assemblage: Path
    planches: list = field(default_factory=list)
    sommaire: list = field(default_factory=list)
    taille_mo: float = 0.0
    etat_polices: EtatPolices | None = None
    avertissements: list = field(default_factory=list)
    #: Origine du contrat d'entrée employé, ou None si le dossier s'arrête au
    #: socle faute d'import.
    origine_contrat: str | None = None
    #: Ce que la notice DP 11 fournie a donné : nom du fichier, nombre de
    #: pages, formats lus et facteurs d'ajustement appliqués. None si aucune
    #: notice n'a été déposée.
    #:
    #: Annoncé même quand tout s'est bien passé (décision D2 du lot 5) : une
    #: notice réduite à 44 % parce qu'elle arrivait en A2 doit se voir avant
    #: l'instruction, et un rapport qui ne parle que des ennuis ne le dit pas.
    notice: dict | None = None


def generer_dossier(
    projet: Projet,
    dossier_sortie: str | Path = "sortie",
    dpi: int = DPI_DEFAUT,
) -> Rapport:
    """Produit les planches du socle, la page de garde et le PDF assemblé."""
    projet.valider()
    etat = avertir_si_indisponible()

    # La notice est contrôlée avant de dessiner quoi que ce soit, alors qu'elle
    # ne sera habillée qu'en fin de dossier : découvrir qu'elle est illisible
    # après le téléchargement de tous les fonds IGN coûte la génération
    # entière. Le dépôt a déjà payé un diagnostic tardif de ce genre sur cairo.
    if projet.chemin_notice is not None:
        dp11_notice.examiner(projet.chemin_notice)

    dossier = Path(dossier_sortie) / projet.nom
    dossier.mkdir(parents=True, exist_ok=True)

    emprise = charger_emprise(projet.chemin_emprise)
    avertissements = []
    if emprise.reprojetee:
        avertissements.append(
            f"Emprise reprojetée depuis {emprise.crs_source} vers EPSG:2154."
        )
    if emprise.nb_polygones > 1:
        avertissements.append(
            f"Emprise composée de {emprise.nb_polygones} polygones : "
            "l'union a été utilisée."
        )
    if not etat.disponible:
        avertissements.append(etat.message)

    # Les reprises du WMS-R sont émises en RuntimeWarning au plus près de la
    # requête ; on les remonte au rapport pour qu'elles atteignent l'interface
    # au lieu de finir dans la console.
    # Le contrat d'entrée du lot 4 vit dans le même dossier que les planches
    # produites : `sortie/{projet}/`. Son absence est un cas normal — c'est un
    # dossier dont le plan n'a pas encore été importé — et le dossier s'arrête
    # alors au socle, en le disant.
    contrat, message = _charger_contrat_eventuel(dossier, projet)
    if message:
        avertissements.append(message)

    with warnings.catch_warnings(record=True) as captees:
        warnings.simplefilter("always", RuntimeWarning)
        sorties = [
            dp1_1_situation.generer(projet, emprise, dossier, dpi=dpi),
            dp1_2_aerienne.generer(projet, emprise, dossier, dpi=dpi),
            dp1_3_cadastre.generer(projet, emprise, dossier),
        ]
        # Les planches du socle ont aussi des choses à dire : le contrôle du
        # découpage foncier vit dans DP 1-3, et son message n'atteignait pas le
        # rapport, qui ne collectait que celui des planches du lot 4.
        for sortie in sorties:
            avertissements.extend(sortie.details.get("avertissements", []))
        if contrat is not None:
            sorties.extend(
                _planches_lot4(projet, contrat, emprise, dossier, avertissements)
            )
            # Les pièces photographiques suivent les DP 4, dans l'ordre du
            # dossier. Elles vivent dans ce bloc parce qu'elles n'ont pas de sens
            # sans plan du bureau d'études : sans lui il n'y a pas d'emprise
            # clôturée à repérer, et pas de dossier non plus.
            sorties.extend(
                _planches_photographies(
                    projet, contrat, dossier, avertissements,
                    rang_depart=len(sorties) + 2,
                )
            )
        # La notice ferme le dossier : c'est la dernière pièce, et la seule qui
        # puisse couvrir plusieurs pages. Aucune pièce ne la suit, donc aucune
        # n'est décalée par son épaisseur.
        notice, message = _notice_eventuelle(
            projet, sorties, dossier, complet=contrat is not None
        )
        if message:
            avertissements.append(message)
        if notice is not None:
            sorties.append(notice)
            avertissements.extend(notice.details.get("avertissements", []))
    avertissements.extend(
        str(c.message) for c in captees if issubclass(c.category, RuntimeWarning)
    )
    # Le même constat vaut pour tout le dossier, mais chaque planche le fait
    # pour son compte : le rapport portait quatre fois la même phrase sur
    # l'emprise d'un poste, et devenait illisible à force de se répéter.
    avertissements[:] = list(dict.fromkeys(avertissements))

    # Numéros de page réels : la page de garde occupe la page 1.
    pages = {"": 1}
    sommaire = [{"numero": "—", "titre": "Page de garde", "page": 1}]
    page_courante = 2
    produites = codes_produits([s.numero for s in sorties])
    for sortie in sorties:
        # La case NUMÉRO du cartouche se vérifie sur les PDF produits : un
        # cartouche qui annonce une planche 3 sur une page 4 est le genre
        # d'erreur que personne ne rattrape. Le nombre de pages se compte donc
        # avant le contrôle, et non après.
        nb = _nb_pages(sortie.chemin)
        _verifier_numerotation(sortie, nb, page_courante, produites)
        pages[sortie.numero] = (page_courante, page_courante + nb - 1)
        sommaire.append(
            {"numero": sortie.numero, "titre": sortie.titre, "page": page_courante}
        )
        page_courante += nb

    garde = page_garde.generer(projet, dossier, pages=pages)
    ordre = [garde] + sorties

    assemblage = _assembler(ordre, dossier / nom_assemblage(projet))
    taille_mo = assemblage.stat().st_size / (1024 * 1024)
    if taille_mo > TAILLE_MAX_MO:
        message = (
            f"{assemblage.name} pèse {taille_mo:.1f} Mo, au-delà de la cible de "
            f"{TAILLE_MAX_MO:.0f} Mo. Réduisez le DPI des fonds raster."
        )
        avertissements.append(message)
        warnings.warn(message, RuntimeWarning, stacklevel=2)

    return Rapport(
        dossier=dossier,
        assemblage=assemblage,
        planches=ordre,
        sommaire=sommaire,
        taille_mo=taille_mo,
        etat_polices=etat,
        avertissements=avertissements,
        origine_contrat=contrat.origine if contrat is not None else None,
        notice=notice.details.get("notice") if notice is not None else None,
    )


def _verifier_numerotation(sortie, nb_pages: int, premiere_page: int, produites) -> None:
    """Le cartouche de chaque page annonce-t-il la page où elle tombe ?

    Depuis le lot 5, une pièce peut couvrir plusieurs pages : comparer un
    numéro unique ne suffit plus. Une pièce qui s'étend déclare les numéros de
    ses cartouches dans `Sortie.numeros`, et ils doivent suivre la pagination
    page par page — c'est la décision D3, tranchée par le dossier de référence
    où la notice de Massay porte NUMERO 16 puis NUMERO 17.
    """
    if sortie.numeros:
        attendus = tuple(range(premiere_page, premiere_page + nb_pages))
        if tuple(sortie.numeros) != attendus:
            raise ErreurRendu(
                f"{sortie.numero} : les cartouches annoncent les planches "
                f"{', '.join(str(n) for n in sortie.numeros)} mais la pièce "
                f"occupe les pages {', '.join(str(n) for n in attendus)} du "
                "dossier assemblé."
            )
        return
    if nb_pages != 1:
        raise ErreurRendu(
            f"{sortie.numero} : {nb_pages} pages produites pour une pièce qui "
            "n'annonce qu'un numéro de cartouche. Une pièce qui s'étend sur "
            "plusieurs pages doit déclarer les numéros de ses cartouches."
        )
    attendu = numero_planche(sortie.numero, produites)
    if attendu != premiere_page:
        raise ErreurRendu(
            f"{sortie.numero} : le cartouche annonce la planche {attendu} "
            f"mais la pièce tombe en page {premiere_page} du dossier assemblé."
        )


def _notice_eventuelle(projet: Projet, sorties, dossier: Path, complet: bool = True):
    """La pièce DP 11, si une notice a été déposée, et ce qu'il faut en dire.

    Son absence **n'arrête pas** la génération. La notice est attendue de tout
    dossier déposable, mais l'outil ne l'exige pas : tant que le dépôt est en
    phase de mise au point, un contrôle bloquant empêcherait d'éprouver le
    reste de la chaîne (décision du 14/09/2026). Ce qui manque est écrit au
    rapport, qui est le seul endroit où le chef de projet peut s'en apercevoir
    avant le dépôt — et `complet` sert à ne pas reprocher sa notice à un
    dossier d'étude amont, qui ne l'a pas encore écrite.

    Le rang de sa première page se **compte** sur les PDF déjà produits plutôt
    que de se déduire du nombre de pièces : le jour où l'une d'elles s'étendra
    à son tour, la notice suivra sans qu'on ait à y penser.
    """
    chemin = projet.chemin_notice
    if chemin is None and not complet:
        return None, (
            "Aucune notice DP 11 : ce dossier d'étude amont est produit sans "
            "elle. Un dossier déposable en porte une, habillée du cadre et du "
            "cartouche et paginée avec les autres pièces."
        )
    if chemin is None:
        return None, (
            "Aucune notice DP 11 : le dossier est produit sans elle, mais il "
            "est incomplet pour le dépôt. Déposez le PDF de la notice pour "
            "qu'elle soit habillée du cadre et du cartouche et paginée avec "
            "les autres pièces."
        )
    # La page de garde occupe la page 1, les pièces déjà produites la suivent,
    # et la notice commence à la page d'après.
    deja_paginees = 1 + sum(_nb_pages(Path(s.chemin)) for s in sorties)
    premiere_page = deja_paginees + 1
    return (
        dp11_notice.generer(projet, chemin, dossier, premier_numero=premiere_page),
        None,
    )


def _charger_contrat_eventuel(dossier: Path, projet: Projet):
    """Contrat d'entrée du lot 4, s'il y en a un, et ce qu'il faut en dire.

    Un contrat absent est normal : le dossier s'arrête alors au socle. Un
    contrat présent mais refusé — version trop récente, voirie non tranchée —
    ne l'est pas, et l'erreur remonte : produire un dossier amputé de ses
    quatre planches principales sans que rien ne l'explique serait pire.
    """
    try:
        return charger_contrat(dossier, voirie=projet.voirie), None
    except ErreurContrat as exc:
        if "Aucun contrat" in str(exc):
            return None, (
                "Aucun plan importé pour ce projet : le dossier s'arrête au "
                "plan de cadastre. Importez le plan du bureau d'études ou "
                "l'export HelioScope pour produire DP 2, DP 3 et DP 4."
            )
        raise


def _planches_lot4(projet, contrat: Contrat, emprise, dossier, avertissements):
    """DP 2, DP 3 et les DP 4, dans l'ordre du dossier.

    Chaque planche non produite l'est pour une raison écrite au rapport. Le
    rang des planches suivantes se calcule ensuite sur ce qui a réellement été
    produit : c'est `codes_produits` qui s'en charge, une fois la liste connue.
    """
    sorties = []
    rang = 5  # page de garde, DP 1-1, DP 1-2, DP 1-3, puis DP 2.

    sorties.append(
        dp2_plan_masse.generer(projet, contrat, emprise, dossier, numero=str(rang))
    )
    avertissements.extend(sorties[-1].details.get("avertissements", []))
    rang += 1

    if contrat.profil and (contrat.profil.get("points") or []):
        sorties.append(
            dp3_coupes.generer(projet, contrat, dossier, numero=str(rang))
        )
        avertissements.extend(sorties[-1].details.get("avertissements", []))
        rang += 1
    else:
        avertissements.append(
            "Aucun profil de terrain au contrat : DP 3 n'est pas produite. "
            "Tracez la ligne de coupe A-A' et relevez le profil à l'import."
        )

    avertissements.extend(dp4_ouvrages.ouvrages_ecartes(contrat))
    for code in dp4_ouvrages.planches_necessaires(contrat):
        try:
            sortie = dp4_ouvrages.generer(
                projet, contrat, dossier, code, numero=str(rang)
            )
        except ErreurDP as exc:
            avertissements.append(f"{code} n'est pas produite : {exc}")
            continue
        sorties.append(sortie)
        avertissements.extend(sortie.details.get("avertissements", []))
        rang += 1
    return sorties


#: Les pièces photographiques, dans l'ordre du dossier, et ce qui les produit.
#:
#: DP 6 rend **une planche par prise de vue** — un point de vue, ses deux ou
#: trois volets — là où DP 7 et DP 8 rassemblent leurs prises sur une planche
#: unique. C'est la seule différence entre les trois, et elle tient dans ce
#: tableau.
_PIECES_PHOTO = (
    ("DP 6", dp6_insertions, True),
    ("DP 7", dp7_environnement_proche, False),
    ("DP 8", dp8_paysage_lointain, False),
)


def _planches_photographies(projet, contrat, dossier, avertissements, rang_depart):
    """DP 6, DP 7 et DP 8, pour les prises de vue enregistrées au projet.

    Une pièce sans prise de vue n'est pas produite, et le rapport le dit : c'est
    une pièce du dossier déposable, et son absence doit se voir avant
    l'instruction, pas pendant.
    """
    emprise_cloturee = union_valide(contrat.geometries("cloture"))
    if emprise_cloturee is None or emprise_cloturee.is_empty:
        avertissements.append(
            "Aucune clôture au contrat : les plans de repérage des pièces "
            "photographiques n'ont pas d'emprise à montrer, et DP 6, DP 7 et "
            "DP 8 ne sont pas produites."
        )
        return []

    sorties = []
    rang = rang_depart
    for code, module, une_planche_par_prise in _PIECES_PHOTO:
        prises = projet.prises_de(code)
        if not prises:
            avertissements.append(
                f"{code} n'est pas produite : aucune prise de vue enregistrée. "
                "Déposez les photographies et placez leur point de vue — la "
                "pièce est attendue de tout dossier déposable."
            )
            continue
        lots = (
            [([prise], rang_prise) for rang_prise, prise in enumerate(prises, 1)]
            if une_planche_par_prise
            else [(prises, 1)]
        )
        for lot, rang_prise in lots:
            try:
                sortie = _generer_piece_photo(
                    module, projet, lot, emprise_cloturee, dossier, code,
                    rang_prise, str(rang), contrat,
                )
            except ErreurDP as exc:
                avertissements.append(f"{code} n'est pas produite : {exc}")
                continue
            sorties.append(sortie)
            avertissements.extend(sortie.details.get("avertissements", []))
            rang += 1
    return sorties


def _generer_piece_photo(module, projet, prises, emprise, dossier, code,
                         rang_prise, numero, contrat):
    """Appelle la pièce avec la forme d'arguments qu'elle attend.

    `contrat` porte le plan de masse que le plan de repérage dessine sous les
    repères : les mêmes objets que DP 2, par le même point d'entrée.
    """
    if code == "DP 6":
        prise = prises[0]
        return module.generer(
            projet, prise.point_de_vue, prise.images, emprise, dossier,
            contrat=contrat, rang=rang_prise, numero=numero,
            cadrages=[prise.cadrage_de(i) for i in range(len(prise.images))],
        )
    return module.generer(
        projet,
        [(prise.point_de_vue, prise.images[0]) for prise in prises],
        emprise, dossier, contrat=contrat, numero=numero,
        cadrages=[prise.cadrage_de(0) for prise in prises],
    )


def _nb_pages(chemin: Path) -> int:
    return len(PdfReader(str(chemin)).pages)


def verifier_format(chemin: Path) -> None:
    """Vérifie que chaque page mesure bien 420 x 297 mm.

    C'est le garde-fou contre un redimensionnement accidentel : une page qui
    n'est pas à ce format ne peut pas être à l'échelle annoncée.
    """
    lecteur = PdfReader(str(chemin))
    for index, page in enumerate(lecteur.pages, start=1):
        largeur = float(page.mediabox.width)
        hauteur = float(page.mediabox.height)
        if (
            abs(largeur - LARGEUR_PT) > TOLERANCE_PT
            or abs(hauteur - HAUTEUR_PT) > TOLERANCE_PT
        ):
            raise ErreurRendu(
                f"{chemin.name}, page {index} : format {largeur:.1f} x {hauteur:.1f} pt "
                f"au lieu de {LARGEUR_PT:.1f} x {HAUTEUR_PT:.1f} pt (A3 paysage). "
                "L'échelle du plan n'est pas garantie."
            )


def _assembler(sorties, destination: Path) -> Path:
    ecrivain = PdfWriter()
    for sortie in sorties:
        chemin = Path(sortie.chemin)
        verifier_format(chemin)
        for page in PdfReader(str(chemin)).pages:
            ecrivain.add_page(page)
    ecrivain.compress_identical_objects()
    with open(destination, "wb") as fichier:
        ecrivain.write(fichier)
    verifier_format(destination)
    return destination
