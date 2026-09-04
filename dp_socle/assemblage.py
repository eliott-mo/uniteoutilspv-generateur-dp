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
from .geometrie import charger_emprise
from .ign import DPI_DEFAUT
from .planches import (
    dp1_1_situation,
    dp1_2_aerienne,
    dp1_3_cadastre,
    dp2_plan_masse,
    dp3_coupes,
    dp4_ouvrages,
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

NOM_ASSEMBLAGE = "DP_complet.pdf"


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


def generer_dossier(
    projet: Projet,
    dossier_sortie: str | Path = "sortie",
    dpi: int = DPI_DEFAUT,
) -> Rapport:
    """Produit les planches du socle, la page de garde et le PDF assemblé."""
    projet.valider()
    etat = avertir_si_indisponible()

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
        if contrat is not None:
            sorties.extend(
                _planches_lot4(projet, contrat, emprise, dossier, avertissements)
            )
    avertissements.extend(
        str(c.message) for c in captees if issubclass(c.category, RuntimeWarning)
    )

    # Numéros de page réels : la page de garde occupe la page 1.
    pages = {"": 1}
    sommaire = [{"numero": "—", "titre": "Page de garde", "page": 1}]
    page_courante = 2
    produites = codes_produits([s.numero for s in sorties])
    for sortie in sorties:
        # La case NUMÉRO du cartouche a été composée à partir de
        # dossier.numero_planche(), qui suppose une page par pièce. On le
        # vérifie sur les PDF produits : un cartouche qui annonce une planche 3
        # sur une page 4 est le genre d'erreur que personne ne rattrape.
        #
        # Le rang est calculé sur les pièces réellement produites : depuis le
        # lot 4 elles ne sont plus toujours les mêmes, un projet sans poste
        # n'ayant pas de DP 4-1.
        attendu = numero_planche(sortie.numero, produites)
        if attendu != page_courante:
            raise ErreurRendu(
                f"{sortie.numero} : le cartouche annonce la planche {attendu} "
                f"mais la pièce tombe en page {page_courante} du dossier assemblé."
            )
        nb = _nb_pages(sortie.chemin)
        pages[sortie.numero] = (page_courante, page_courante + nb - 1)
        sommaire.append(
            {"numero": sortie.numero, "titre": sortie.titre, "page": page_courante}
        )
        page_courante += nb

    garde = page_garde.generer(projet, dossier, pages=pages)
    ordre = [garde] + sorties

    assemblage = _assembler(ordre, dossier / NOM_ASSEMBLAGE)
    taille_mo = assemblage.stat().st_size / (1024 * 1024)
    if taille_mo > TAILLE_MAX_MO:
        message = (
            f"{NOM_ASSEMBLAGE} pèse {taille_mo:.1f} Mo, au-delà de la cible de "
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
