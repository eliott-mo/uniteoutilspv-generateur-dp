"""Interface minimale de saisie et de génération du dossier DP (lot 1 — socle).

Le formulaire écrit `projet.json`, qui reste le format pivot : une correction de
dernière minute se fait en modifiant ce fichier et en relançant la génération.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date as _date
from datetime import datetime
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

from dp_socle.environnement import dossiers_de_travail, etat_cairo, etat_travail, preparer_cairo

preparer_cairo()

# Le lot 2 (HelioScope) et le lot 2bis (plan BE) ont chacun leur aperçu, avec
# les mêmes noms de fonctions : ceux du lot 2bis sont renommés ici, plutôt que
# dans leur module, pour ne pas toucher au lot 2.
from dp_socle.planches.palette import EXCLUES
from dp_socle.apercu_be import (
    ORDRE_DESSIN,
    STYLES,
    URL_TUILES_ORTHO,
    apercu_au_survol,
    bornes_wgs84,
    clic_l93,
    en_wgs84,
    legende_presente,
)
from dp_socle.coupe import (
    controler_coherence,
    controler_terrain_embarque,
    corriger_ligne_coupe,
    coupe_enregistree,
    coupe_par_defaut,
    profil_terrain,
    reprendre_coupe,
    translater_ligne_coupe,
)
from dp_socle.contrat import (
    NOM_GEOPACKAGE,
    VOIRIES_ADMISES,
    archiver_le_contrat,
    decrire_voiries,
)
from dp_socle.erreurs import ErreurCoupe, ErreurDepot, ErreurDP
from dp_socle.import_be import (
    CALQUES_TERRAIN,
    CATEGORIES,
    calques_du_dxf,
    empreinte_charte,
    importer_be,
    lire_parametres,
)
from dp_socle.dossier import piece
from dp_socle.geometrie import charger_emprise
from dp_socle.ign import DPI_DEFAUT
from dp_socle.polices import etat_polices
from dp_socle.sortie_pptx import (
    FORMAT_HORODATAGE,
    generer_pptx,
    nom_telechargement,
)
from dp_socle.ajout_notice import ajouter_la_notice, lire_le_dossier
from dp_socle.import_be import SEUIL_DP_MWC
from dp_socle.planches import dp11_notice
from dp_socle.projet import Projet, identifiant_de_dossier, nom_de_projet
from dp_socle.tableau_bilan import indice_depuis_nom, indices_disponibles

#: Où l'outil écrit ses fichiers de travail. Relatifs au dossier courant par
#: défaut — ce que la cible de déploiement attend — et déplaçables par
#: `DP_DOSSIER_TRAVAIL` : sur un poste Windows, les sortir d'un dossier
#: synchronisé évite que OneDrive tienne un fichier ouvert pendant qu'on l'écrit.
DOSSIER_PROJETS, DOSSIER_SORTIE = dossiers_de_travail()

EXTENSIONS_SHAPEFILE = (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qmd")

#: Le picto de l'outil, devant son titre et dans l'onglet du navigateur : les
#: outils UNITe portent tous le leur, et le chef de projet qui en ouvre
#: plusieurs les distingue dans sa barre d'onglets avant d'avoir lu un mot.
PICTO = "🏗️"

st.set_page_config(
    page_title="Générateur de dossier DP", page_icon=PICTO, layout="wide"
)
st.title(f"{PICTO} Générateur de dossier DP")
st.caption(
    "Page de garde, DP 1-1 plan de situation, DP 1-2 photographie aérienne, "
    "DP 1-3 plan de cadastre. Fonds IGN Géoplateforme, Lambert 93, A3 paysage à "
    "l'échelle vraie."
)

# Les pièces d'entrée, en une ligne. Un volet déplié les détaillait jusqu'au
# 28/09/2026 ; personne ne le relisait, et il annonçait encore le relevé
# altimétrique et les photographies, dont le dépôt a été retiré au lot 8. Une
# ligne sous le titre se relit à chaque ouverture, donc se corrige.
st.caption(
    "À réunir avant de commencer : l'emprise cadastrale (ZIP du shapefile, "
    "`.prj` compris), le plan du BE en DXF et son tableau bilan au même "
    "indice — ou, sans plan BE, l'export HelioScope et le plan projet en PDF "
    "— et la notice DP 11 en PDF."
)


@st.cache_resource
def _etat_cairo():
    return etat_cairo()


@st.cache_resource
def _etat_polices():
    return etat_polices()


@st.cache_resource
def _etat_travail():
    return etat_travail()


# La bibliothèque de rendu se contrôle avant la police : sans cairo, aucune
# mesure de police n'est possible et le diagnostic typographique n'a plus de
# sens. Contrôlé ici plutôt qu'au rendu, pour ne pas échouer après le
# téléchargement de tous les fonds IGN.
cairo = _etat_cairo()
if not cairo.disponible:
    st.error(cairo.message, icon="🚫")

# L'état du décodeur HEIC ne se dit plus ici : l'outil ne lit plus de
# photographie. Il en lisait pour les pièces DP 6 à DP 8, dont le dépôt a été
# retiré le 26/09/2026 ; le décodeur reste épinglé et contrôlé dans
# `dp_socle/lecture_exif.py`, où un lot ultérieur le retrouvera.

# Un dossier de travail synchronisé se dit au démarrage, comme l'état de cairo :
# ce qui gêne doit se savoir avant de travailler.
travail = _etat_travail()
if travail.synchronise:
    st.warning(travail.message, icon="⚠️")

# La police ne se dit que lorsqu'elle manque. La confirmation verte était du
# bruit à chaque ouverture ; une substitution, elle, fausserait toutes les
# chasses du dossier et doit se voir avant de travailler.
etat = _etat_polices()
if not etat.disponible:
    st.warning(f"Police : {etat.message}", icon="⚠️")

def _en_puces(messages) -> str:
    """Les messages en liste markdown, une puce chacun."""
    return "\n".join(f"- {message}" for message in messages)


def _lister_les_avertissements(titre: str, messages) -> None:
    """Un seul bandeau jaune, puis les messages en liste sous lui.

    Un `st.warning` par message donnait autant de pavés jaunes à picto qu'il y
    avait de remarques — des dizaines sur un plan bavard. L'œil n'y distinguait
    plus la première de la dernière, et le jaune ne signalait plus rien puisqu'il
    était partout (retour d'usage du 26/09/2026). Le bandeau dit ce qui commence
    et combien il y en a ; les messages, en dessous, se lisent comme une liste.

    Une vraie liste à puces, et non des lignes séparées par des retours : en
    markdown, deux lignes qui se suivent forment un seul paragraphe, et les
    messages se seraient enchaînés bout à bout. Aucun n'a de retour à la ligne —
    ils sont écrits d'un tenant dans `import_be` et `sortie_pptx` —, chacun tient
    donc sur sa puce.
    """
    if not messages:
        return
    st.warning(f"**{titre}**", icon="⚠️")
    st.markdown(_en_puces(messages))


def _signaler_l_imprevu(erreur: Exception, pendant: str) -> None:
    """Rend lisible une erreur que l'outil n'avait pas prévue.

    Streamlit Community Cloud **masque** le message des exceptions non
    attrapées : le chef de projet ne voit que « The original error message is
    redacted », et la cause — un nom de calque, un fichier — reste dans des
    journaux auxquels il n'a pas accès. Constaté le 27/09/2026 sur un
    `AttributeError` qu'il a fallu aller chercher dans le tableau de bord pour
    comprendre qu'un contour de citerne se repliait sur lui-même.

    Le type et le message sont donc réécrits ici, **dans du texte à nous**, que
    la censure ne touche pas — `st.exception` la subit, lui, puisqu'il dépend
    de `client.showErrorDetails`. Il reste tout de même, pour le poste de
    développement où il affiche la trace complète.

    Ce n'est pas un rattrapage : rien n'est repris, rien n'est deviné, le
    dossier ne sort pas. C'est la règle du dépôt appliquée à ce qu'on n'a pas
    prévu — ce qui échoue doit se lire, et ici ça ne se lisait pas.

    `st.rerun()` et `st.stop()` traversent : leurs exceptions dérivent de
    `BaseException` et non d'`Exception` (vérifié sur Streamlit 1.57.0).

    L'incident reste visible d'`AppTest`, qui voit les éléments `st.exception`
    d'où qu'ils viennent : les quarante-et-un `assert not
    application.exception` de la suite continuent donc de protéger.
    """
    st.error(
        f"**L'outil s'est arrêté {pendant}, sur un cas qu'il ne sait pas "
        f"traiter.** {type(erreur).__name__} : {erreur}",
        icon="🚫",
    )
    st.caption(
        "Transmettez ce message **avec les fichiers d'entrée du projet** — le "
        "plan, le tableau bilan et l'emprise. Le message dit où ça s'est "
        "arrêté ; seuls les fichiers disent pourquoi."
    )
    with st.expander("Le détail technique"):
        st.exception(erreur)


# ---------------------------------------------------------------------------
# Le chemin court : verser la notice dans un dossier déjà fini (lot 7)
# ---------------------------------------------------------------------------
#
# En tête de page, et **avant** le `st.stop()` qui ferme tout tant que la
# commune et l'emprise ne sont pas renseignées : un chef de projet qui revient
# seulement poser sa notice n'a ni l'une ni l'autre sous la main. Ce n'est pas
# un choix de mise en page, c'est ce qui rend le chemin praticable.
#
# Replié par défaut : le parcours normal, d'une traite, reste le parcours.
with st.expander(
    "📄 Je souhaite juste ajouter la notice à mon dossier finalisé", expanded=False
):
    st.caption(
        "Pour un dossier **déjà généré et fini sur PowerPoint** — photographies "
        "posées, photomontage inséré, diapos surnuméraires supprimées — dont la "
        "notice n'était pas prête. Elle s'ajoute ici sans rien regénérer : votre "
        "travail est conservé."
    )
    _depot_dossier = st.file_uploader(
        "Le dossier fini (.pptx)", type=["pptx"], key="reprise_pptx"
    )
    _dossier_fini = None
    if _depot_dossier is not None:
        try:
            _dossier_fini = lire_le_dossier(_depot_dossier.getvalue())
        except ErreurDP as erreur:
            st.error(f"{type(erreur).__name__} : {erreur}", icon="🚫")

    if _dossier_fini is not None:
        _identite = _dossier_fini.identite
        st.success(
            f"**{_identite['libelle']}** — dossier du "
            f"{_date.fromisoformat(_identite['date']).strftime('%d/%m/%Y')}, "
            f"{_dossier_fini.nb_diapos} diapos. La notice prendra la page "
            f"{_dossier_fini.premiere_page_de_la_notice}.",
            icon="📄",
        )
        # La pagination est lue dans le fichier déposé, pas dans une mémoire du
        # serveur — qui n'en a aucune. Elle porte donc les diapos surnuméraires
        # que le chef de projet a déjà supprimées, et c'est elle qui fera le
        # sommaire.
        with st.expander("Ce que l'outil a lu dans votre dossier"):
            st.dataframe(
                [
                    {"Pièce": code or "—", "Titre": titre, "Page": page}
                    for code, titre, page in _dossier_fini.pagination()
                ],
                width="stretch",
                hide_index=True,
            )
        if _dossier_fini.porte_la_notice:
            st.warning(
                f"Ce dossier porte déjà une notice de "
                f"{_dossier_fini.pages_de_la_notice} page(s). Pour la remplacer, "
                "regénérez le dossier avec la bonne notice.",
                icon="⚠️",
            )
        else:
            _depot_notice = st.file_uploader(
                "La notice DP 11 (.pdf)", type=["pdf"], key="reprise_notice"
            )
            st.caption(
                f"Le dossier gardera sa date du "
                f"{_date.fromisoformat(_identite['date']).strftime('%d/%m/%Y')} : "
                "elle est dessinée dans le cartouche de chaque planche, et la "
                "changer sur la seule couverture donnerait un dossier dont la "
                "première page contredit les suivantes."
            )
            if _depot_notice is not None and st.button(
                "Ajouter la notice au dossier", type="primary", width="stretch"
            ):
                try:
                    with st.spinner(
                        "Rastérisation de la notice et remise à jour du sommaire…"
                    ):
                        _travail = DOSSIER_SORTIE / "_reprise"
                        _travail.mkdir(parents=True, exist_ok=True)
                        _notice = _travail / _depot_notice.name
                        _notice.write_bytes(_depot_notice.getvalue())
                        st.session_state["dossier_avec_notice"] = {
                            "octets": ajouter_la_notice(
                                _depot_dossier.getvalue(), _notice, _travail
                            ),
                            "libelle": _identite["libelle"],
                        }
                except ErreurDP as erreur:
                    st.session_state.pop("dossier_avec_notice", None)
                    st.error(f"{type(erreur).__name__} : {erreur}", icon="🚫")
                except Exception as erreur:
                    st.session_state.pop("dossier_avec_notice", None)
                    _signaler_l_imprevu(erreur, "pendant l'ajout de la notice")

    _complet = st.session_state.get("dossier_avec_notice")
    if _complet is not None:
        st.download_button(
            f"⬇️ Télécharger le dossier complété "
            f"({len(_complet['octets']) / (1024 * 1024):.1f} Mo, .pptx)",
            data=_complet["octets"],
            file_name=nom_telechargement(
                identifiant_de_dossier(_complet["libelle"]), datetime.now()
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            type="primary",
            on_click="ignore",
            width="stretch",
        )

# La barre latérale « Contrôles » a été retirée le 26/09/2026, au premier
# déploiement chez les chefs de projet. Elle portait trois choses, dont deux
# étaient de la plomberie — les deux identifiants de couches Géoplateforme et un
# bouton « Vérifier via GetCapabilities » — et c'était la première chose qu'on
# voyait en ouvrant l'outil.
#
# Le contrôle lui-même n'est pas perdu : `ign.verifier_couches()` s'appelle
# toujours, depuis un shell ou un test, le jour où l'IGN renomme une couche et
# où toutes les planches échouent d'un coup. C'est un diagnostic d'atelier, pas
# un écran de production.
#
# Le troisième réglage, le DPI des fonds raster, est désormais figé à
# `ign.DPI_DEFAUT` — 200 ppp, soit 3 228 x 2 110 px sur la zone de dessin d'un
# A3. Son propre texte d'aide disait que 250 « améliore peu à l'impression et
# alourdit le dossier de moitié » : un réglage dont une seule valeur est la
# bonne n'est pas un réglage, c'est une occasion de se tromper.


def _nom_depot(commune: str) -> str:
    """Dossier où atterrissent les fichiers téléversés par le chef de projet.

    Il ne porte **pas** l'indice, contrairement au dossier produit : le tableau
    bilan est déposé avant qu'on sache quel indice y lire — c'est lui qui en
    donne la liste — et il porte de toute façon tous les indices du projet. Un
    dépôt par commune, donc, et un dossier de sortie par indice.

    Vide sans commune, et sans valeur de repli : `projets/projet/` recevait
    sinon les plans de tous les projets encore sans nom, chacun écrasant les
    fichiers de même nom du précédent, en silence (relecture du 09/09/2026).
    """
    return identifiant_de_dossier(nom_de_projet(commune))


def _nom_dossier(commune: str) -> str:
    """Identifiant du dossier produit : la commune et l'indice **importé**.

    Une fonction, et non une variable posée en tête de script : l'indice est
    choisi au milieu de la section 2, et tout ce qui écrit dans `sortie/` vient
    après. Le composer plus haut le laissait en retard d'une exécution —
    Streamlit rejoue le script entier à chaque interaction — et le composer plus
    bas, en section 4, laissait la section 2 sans nom du tout : c'est la
    `NameError` du 09/09/2026, levée dès le dépôt du DXF.

    L'indice lu ici est celui que l'import a **réellement lu**, pas celui que la
    liste déroulante affiche. Les confondre suffisait à écrire la géométrie d'un
    indice dans le dossier d'un autre : changer la liste sans recliquer sur
    « Importer et contrôler » laissait l'import en place et déplaçait la cible.
    """
    indice = st.session_state.get("indice_tableau_bilan")
    return identifiant_de_dossier(nom_de_projet(commune, indice))


def _empreinte(fichier) -> tuple:
    """Ce qui distingue ce dépôt d'un autre, sans relire les octets.

    `file_id` est attribué par Streamlit à chaque fichier reçu : il change dès
    que le chef de projet en dépose un autre, même sous le même nom. La taille
    l'accompagne comme garde-fou, pour les versions qui n'en donneraient pas.
    """
    return (getattr(fichier, "file_id", None), getattr(fichier, "size", None))


#: Ce qu'un bouton dit quand il est grisé.
AIDE_DEJA_FAIT = (
    "Déjà fait sur ces données-là. Le bouton se rallume dès que quelque chose "
    "change au-dessus."
)


def _deja_fait(cle: str, signature) -> bool:
    """Vrai si ce bouton a déjà tourné sur exactement ces entrées.

    Un bouton qui reste actif après avoir servi invite à le recliquer, et le
    reclic refait une minute de travail pour un résultat identique — ou pire,
    laisse croire que le premier n'a pas pris (retour d'usage du 26/09/2026).

    Le critère n'est pas « ça a déjà été fait une fois » mais « ça a été fait
    sur **ces** entrées » : la signature porte tout ce qui changerait le
    résultat, et le bouton se rallume dès qu'une d'elles bouge. Un drapeau
    booléen aurait grisé le bouton pour de bon, y compris après un changement
    qui demandait justement de le recliquer.
    """
    return st.session_state.get(cle) == signature


def _retenir_ce_qui_a_servi(cle: str, signature) -> None:
    """Note ce sur quoi un bouton vient de tourner, pour qu'il se grise."""
    st.session_state[cle] = signature


def _deja_ecrit(cible: Path, fichier) -> bool:
    """Vrai si ce fichier exact est déjà sur le disque, à cet endroit.

    L'existence est vérifiée à chaque fois, et non seulement la mémoire de
    session : un fichier effacé entre deux exécutions doit être réécrit, sans
    quoi la génération échouerait plus tard sur un chemin qui ne mène nulle part.
    """
    ecrits = st.session_state.setdefault("fichiers_deposes", {})
    return ecrits.get(str(cible)) == _empreinte(fichier) and cible.exists()


def _retenir_ecriture(cible: Path, fichier) -> None:
    st.session_state.setdefault("fichiers_deposes", {})[str(cible)] = _empreinte(
        fichier
    )


def _ecrire_depose(cible: Path, donnees) -> None:
    """Écrit un fichier déposé, en nommant la cause quand c'est impossible.

    Un `PermissionError` brut est une trace Python que le chef de projet ne peut
    pas interpréter : sous Windows, la cause est presque toujours un autre
    programme qui tient le fichier ouvert — OneDrive en cours de
    synchronisation, un antivirus, ou le logiciel qui a servi à produire le
    fichier.
    """
    try:
        cible.write_bytes(donnees)
    except PermissionError as erreur:
        raise ErreurDepot(
            f"Impossible d'écrire « {cible.name} » dans le dossier du projet : "
            "un autre programme le tient ouvert. Sous Windows, c'est le plus "
            "souvent OneDrive en cours de synchronisation, un antivirus, ou le "
            "logiciel qui a produit le fichier (AutoCAD, Excel). Fermez-le, "
            f"attendez la fin de la synchronisation, et redéposez. ({erreur})"
        ) from erreur
    except OSError as erreur:
        raise ErreurDepot(
            f"Impossible d'écrire « {cible.name} » dans le dossier du projet "
            f"({erreur})."
        ) from erreur


#: Nom de l'archive qui porte tout ce que le chef de projet doit emporter.
MOTIF_TOUT = "{nom}_DP_et_contrat_{horodatage}.zip"


def _tout_en_une_archive(pptx: bytes, nom_pptx: str, contrat: bytes) -> bytes:
    """Le dossier et le contrat en un seul téléchargement.

    Le contrat y entre **déplié**, et non comme un ZIP dans un ZIP : le
    destinataire ouvre une fois et trouve le dossier du contrat à côté du
    `.pptx`, prêt à être donné à l'outil de photomontage. Un ZIP imbriqué aurait
    demandé de savoir qu'il fallait l'ouvrir aussi.

    Le `.pptx` est déjà un ZIP, et le GeoPackage déjà compressé : `ZIP_STORED`
    évite de les recomprimer pour un gain nul. Le JSON du contrat, lui, est déjà
    déflaté dans l'archive qu'il vient de traverser.
    """
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(nom_pptx, pptx)
        with zipfile.ZipFile(io.BytesIO(contrat)) as recu:
            for membre in recu.infolist():
                archive.writestr(membre.filename, recu.read(membre))
    return tampon.getvalue()


def _enregistrer_notice(nom_projet: str, fichier) -> str | None:
    """Écrit la notice déposée dans `projets/{nom}/DP_11/`, et rend son chemin.

    Même patron que `_enregistrer_photos` : une pièce fournie, un sous-dossier
    à son code. La notice n'est pas une métadonnée du projet, c'est une pièce
    du dossier, et elle se range avec les autres pièces fournies.
    """
    if fichier is None:
        return None
    dossier = DOSSIER_PROJETS / nom_projet / "DP_11"
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / Path(fichier.name).name
    _ecrire_depose(cible, fichier.getbuffer())
    return str(cible)


def _enregistrer_fichiers(nom_projet: str, fichiers) -> Path | None:
    """Écrit les fichiers téléversés et renvoie le chemin d'emprise à utiliser."""
    if not fichiers:
        return None
    dossier = DOSSIER_PROJETS / nom_projet
    dossier.mkdir(parents=True, exist_ok=True)

    chemins = []
    for fichier in fichiers:
        cible = dossier / Path(fichier.name).name
        _ecrire_depose(cible, fichier.getbuffer())
        chemins.append(cible)

    zips = [c for c in chemins if c.suffix.lower() == ".zip"]
    if zips:
        return zips[0]
    shps = [c for c in chemins if c.suffix.lower() == ".shp"]
    if len(shps) == 1:
        return shps[0]
    if len(shps) > 1:
        st.error("Plusieurs fichiers .shp téléversés : n'en gardez qu'un.")
        return None
    st.error(
        "Aucun shapefile trouvé dans les fichiers téléversés. Téléversez soit un "
        "ZIP, soit l'ensemble .shp + .shx + .dbf + .prj."
    )
    return None


st.subheader("1. Infos générales")
# Champs vides, avec une invite grisée : les deux portaient la commune et le code
# postal de Bray-Saint-Aignan en valeur par défaut, restes du premier jeu
# d'essai. Une valeur préremplie est pire qu'un champ vide — elle se génère sans
# qu'on la relise, et un dossier au nom d'une autre commune que la sienne ne se
# détecte qu'à l'instruction.
colonne_gauche, colonne_droite = st.columns(2)
with colonne_gauche:
    commune = st.text_input("Commune", placeholder="Nom commune projet")
with colonne_droite:
    code_postal = st.text_input("Code postal", placeholder="Code postal projet")

# Le nom du projet et la date ne se saisissent pas : l'un est toujours « PV »
# suivi de la commune et de l'indice du tableau bilan, l'autre est le jour où le
# dossier est produit. Deux champs de moins à remplir, et deux occasions de
# moins de se tromper.
#
# L'indice n'est connu qu'après l'import du plan, en section 2 : le nom définitif
# se compose donc en section 4, juste avant de dessiner. Ce qui s'affiche ici est
# provisoire, et le dit.
date_projet = _date.today()
if commune.strip():
    st.caption(
        f"Projet **{nom_de_projet(commune)}**, daté du "
        f"{date_projet.strftime('%d/%m/%Y')}. L'indice du tableau bilan "
        "complétera le nom une fois le plan importé."
    )

fichiers_emprise = st.file_uploader(
    "Emprise cadastrale (ZIP du shapefile, ou .shp + .shx + .dbf + .prj)",
    type=[e.lstrip(".") for e in EXTENSIONS_SHAPEFILE] + ["zip"],
    accept_multiple_files=True,
    help="Le fichier .prj est obligatoire : sans lui le CRS est inconnu et la "
    "génération est refusée.",
)

# La notice se dépose avec les autres pièces d'entrée : c'est un fichier
# qu'on rassemble avant de commencer, au même titre que l'emprise ou le
# plan. Elle fermait le parcours, où « on la noyait à la fin » (retour
# d'usage du 26/09/2026) ; l'assemblage, lui, la met toujours en DP 11.
st.markdown("**Notice — attendue de tout dossier déposable**")
st.caption(
    "L'outil ne rédige pas la notice : il reprend le PDF déposé, page par page, "
    "sous le cadre et le cartouche du dossier, et la pagine au sommaire. Le "
    "texte y reste du texte. Le format est lu dans le fichier, rien n'est "
    "supposé : une A4 paysage, le cas courant, est agrandie au facteur 124 % "
    "pour remplir le cadre A3 ; une A4 portrait y est réduite à 88 %. Sous "
    f"{dp11_notice.FACTEUR_MINIMAL:.0%} — un plan A1 déposé ici par mégarde — "
    "la notice est refusée plutôt que rendue illisible."
)
fichier_notice = st.file_uploader(
    f"DP 11 — {piece('DP 11').titre}",
    type=["pdf"],
    accept_multiple_files=False,
    key="notice_dp11",
    help="Le PDF de la notice, dans le format où vous l'avez rédigée.",
)

# ---------------------------------------------------------------------------
# Rendu des contrôles, commun aux deux imports
# ---------------------------------------------------------------------------

def _formater(valeur, unite: str) -> str:
    """Valeur d'un contrôle croisé, lisible en tableau."""
    if valeur is None:
        return "—"
    if isinstance(valeur, float):
        texte = f"{valeur:,.2f}".replace(",", " ").replace(".", ",")
    else:
        texte = str(valeur)
    return f"{texte} {unite}".strip()


#: Icône par statut de contrôle. Écrit une fois et lu avec un défaut : un accès
#: direct au dictionnaire levait un KeyError dès qu'un statut nouveau
#: apparaissait — et « impossible » est arrivé avec l'alignement du lot 2.
ICONES_STATUT = {
    "ok": "✅",
    "avertissement": "⚠️",
    "bloquant": "🚫",
    "impossible": "∅",
}


def _icone(statut: str) -> str:
    return ICONES_STATUT.get(statut, "❔")


#: Opacité des remplissages sur la carte, plus basse que sur la planche.
#:
#: La planche DP 2 remplit à 235/255 : elle se lit sur papier, sans fond. Ici
#: l'ortho doit rester visible sous les géométries — c'est ce qui permet de
#: placer la coupe par rapport au terrain, aux haies et aux bâtiments voisins.
OPACITE_CARTE = 0.68

#: Les modules ne sont pas dessinés sur la carte.
#:
#: Ils redisent ce que la silhouette des rangées montre déjà, et un plan qui les
#: porte en compte des milliers : leur trame fait la lisibilité de la planche
#: imprimée, elle ne ferait ici que ralentir le navigateur au moment où le chef
#: de projet trace sa coupe.
#: Catégories que la carte de saisie ne dessine pas.
#:
#: Les modules parce qu'un plan en compte des milliers et que la silhouette des
#: rangées dit la même chose ; les installations de chantier et les contours
#: d'étude parce qu'ils ne vont pas sur la planche — `palette.EXCLUES` les
#: écarte comme temporaires ou comme contours d'étude. Les montrer ici laissait
#: croire qu'ils partiraient au dossier (retour d'usage du 17/09/2026) : la
#: carte de saisie montre ce que la planche portera, et rien d'autre.
CATEGORIES_HORS_CARTE = ("modules_pv",) + tuple(EXCLUES)


def _teinte(composantes) -> str:
    """Couleur CSS d'un triplet RVB de la palette DP."""
    rouge, vert, bleu = composantes
    return f"#{rouge:02x}{vert:02x}{bleu:02x}"


def _couches_de_la_carte(plan):
    """Les couches du plan en WGS 84, reprojetées une fois par import.

    Streamlit rejoue le script entier à chaque interaction. Sans ce cache, les
    504 objets du plan de Sarnois — dont 290 arbres existants — étaient
    reprojetés et resérialisés à chaque clic : mesuré le 19/09/2026, 0,80 s des
    1,25 s que coûtait la carte, pour un résultat rigoureusement identique.
    C'est ce qui figeait la page trois à quatre secondes à chaque geste.

    Le cache vit dans la session plutôt que dans `st.cache_data` : le plan
    n'est pas hachable, et surtout l'invalidation est ici évidente — le plan ne
    change qu'à l'import, qui remet les clés à None.
    """
    couches = st.session_state.get("couches_carte")
    if couches is not None:
        return couches
    ecartees = CATEGORIES_HORS_CARTE
    couches = []
    # Dans l'ordre de la planche : ce qui se recouvre se recouvre pareil ici.
    for categorie in ORDRE_DESSIN:
        if categorie in ecartees:
            continue
        style = STYLES.get(categorie)
        if style is None:
            continue
        collection = en_wgs84(plan.geometries(categorie))
        if not collection["features"]:
            continue
        couches.append((style, collection))
    st.session_state["couches_carte"] = couches
    return couches


#: Épaisseur d'un axe à aplat sur la carte, en pixels.
#:
#: Même règle que `palette.style_de` pour les planches : un linéaire d'une
#: catégorie à aplat se trace dans la teinte de l'aplat, sans remplissage. Une
#: haie du plan PDF (lot 2ter) est un axe : remplie, elle colorait l'aire entre
#: son tracé et sa corde — le navigateur ferme implicitement un chemin SVG
#: rempli —, et l'axe lui-même n'avait que l'épaisseur du filet, 2 px. Quatre
#: pixels, l'épaisseur de la clôture, la plus forte de la carte.
EPAISSEUR_AXE_CARTE_PX = 4

#: Types GeoJSON d'un axe.
AXES_GEOJSON = ("LineString", "MultiLineString")


def _style_carte(style, trait: dict | None = None) -> dict:
    """Style Leaflet d'un objet, aux couleurs de la légende DP.

    Les mêmes teintes que la planche produite : ce que le chef de projet voit
    ici est ce qu'il retrouvera sur DP 2, à l'opacité près. `trait` est
    l'entité GeoJSON que folium passe à sa fonction de style : un axe d'une
    catégorie à aplat s'y trace en trait, comme sur la planche.
    """
    geometrie = (trait or {}).get("geometry") or {}
    if style.remplissage is not None and geometrie.get("type") in AXES_GEOJSON:
        return {
            "color": _teinte(style.remplissage),
            "weight": max(style.epaisseur, EPAISSEUR_AXE_CARTE_PX),
            "fill": False,
            "fillOpacity": 0.0,
        }
    dessin = {
        "color": _teinte(style.filet),
        "weight": max(style.epaisseur, 1),
        "fill": False,
        "fillOpacity": 0.0,
    }
    if style.remplissage is not None:
        dessin["fill"] = True
        dessin["fillColor"] = _teinte(style.remplissage)
        dessin["fillOpacity"] = OPACITE_CARTE
    return dessin


#: Ce qui relève du fonctionnement normal de l'import, et se replie.
#:
#: Ces messages disent ce que l'import a écarté et pourquoi : calques de travail
#: du BE, fond cadastral remplacé par le WFS, annotations et cotations. Ils sont
#: utiles quand une catégorie manque au plan, et rien d'autre.
#:
#: Signalé à l'usage le 17/09/2026 : sur le plan de Sarnois, onze de ces messages
#: noyaient les quatre qui demandaient une action — dont deux écarts de surface
#: de 100 %. « Tellement qu'on n'a pas envie de les lire et qu'on passe à la
#: suite. » Un avertissement qu'on ne lit plus ne protège plus de rien.
#:
#: Le classement se fait sur le texte, ce qui est fragile — mais le repli est
#: sûr : un message dont la forme change n'est plus reconnu, et reste donc
#: **visible**. Jamais l'inverse.
MOTIFS_DE_ROUTINE = (
    "calque(s) écarté(s) —",
    "annotation(s) écartée(s)",
    "entité(s) sans calque écartée(s)",
)


#: La formule que les messages destinés au bureau d'études portent tous.
#:
#: Uniformisée dans `import_be.py` le 17/09/2026 pour que l'interface puisse les
#: rassembler sans deviner. Un chef de projet qui reçoit un plan incomplet doit
#: savoir **exactement quoi redemander**, sans trier lui-même une vingtaine de
#: remarques ni connaître le DXF : « comme je ne serai pas toujours là pour
#: vérifier les plans ».
MARQUEUR_BUREAU_ETUDES = "à demander au bureau d'études"


def _trier_les_avertissements(messages) -> tuple[list, list, list]:
    """Range les remarques en trois : pour le BE, à lire, fonctionnement normal.

    L'ordre d'examen compte : une demande au bureau d'études prime sur tout, y
    compris sur la forme d'un message de routine.
    """
    au_be, a_lire, routine = [], [], []
    for message in messages:
        if MARQUEUR_BUREAU_ETUDES in message:
            au_be.append(message)
        elif any(motif in message for motif in MOTIFS_DE_ROUTINE):
            routine.append(message)
        else:
            a_lire.append(message)
    return au_be, a_lire, routine


def _demande_au_be(message: str) -> str:
    """La demande seule, précédée de ce qu'elle concerne.

    C'est ce que le chef de projet recopie dans son message au bureau d'études :
    la phrase entière porterait un diagnostic d'outil dont le BE n'a que faire,
    mais la demande nue — « le contour de cet élément » — ne dirait pas de quel
    élément il s'agit. L'intitulé du message, jusqu'à son premier deux-points,
    nomme le calque ou la surface en cause.
    """
    _, _, demande = message.partition(MARQUEUR_BUREAU_ETUDES)
    demande = demande.lstrip(" :").strip()
    if not demande:
        return message
    intitule, separateur, _ = message.partition(" : ")
    return f"{intitule} — {demande}" if separateur else demande


def _recouper_les_voiries(import_be, tranche) -> None:
    """Rejoue le recoupement des surfaces, maintenant que le type est connu.

    Le contrôle se fait à l'import, où il ne peut pas conclure : sans lui, il
    restait suspendu pour toute la vie du dossier, et l'écart qu'il doit
    attraper — un plan mis à jour sans son tableau — passait inaperçu. Il se
    rejoue donc ici, dès le choix fait, et dit ce qu'il trouve.
    """
    from dp_socle.import_be import OK, controler_surfaces_de_voirie

    controles = controler_surfaces_de_voirie(
        import_be.plan, import_be.tableau.pistes, tranche
    )
    ecarts = [controle for controle in controles if controle.statut != OK]
    if not ecarts:
        st.success(
            "Surfaces de voirie recoupées avec le tableau bilan : elles "
            "concordent.",
            icon="✅",
        )
        return
    _lister_les_avertissements(
        f"{len(ecarts)} surface(s) de voirie ne concordent pas avec le tableau "
        "bilan",
        [f"**{controle.libelle}** : {controle.message}" for controle in ecarts],
    )


def _trancher_les_voiries(import_be) -> None:
    """Fait trancher le type des voiries, croquis à l'appui, dès l'import.

    Deux choses que l'usage a demandées le 17/09/2026. La question se pose ici,
    où l'alerte est levée, et non à la génération — « on fait tout le process
    puis on tranche à la toute fin ». Et un croquis situe chaque objet : « avec
    les infos données pour l'instant c'est très compliqué de savoir quelle
    section correspond à quoi ».

    Les objets sans surface ne sont pas proposés : un axe ou un bout de limite
    n'est ni lourd ni léger, il n'entre dans aucun calcul et ne va sur aucune
    planche. Ils restent au croquis, en gris, pour que le compte y soit.
    """
    from dp_socle.apercu_be import croquis_voiries, voiries_hors_cadre
    from dp_socle.contrat import VOIRIE_SANS_OBJET, decrire_geometries_voirie

    plan = import_be.plan
    objets = decrire_geometries_voirie(plan.geometries("voirie"))
    if not objets:
        st.session_state["voirie_tranchee"] = None
        return

    surfaciques = [o for o in objets if o["surfacique"]]
    st.warning(
        f"**{len(surfaciques)} voirie(s) à typer.** Le calque du bureau d'études "
        "ne dit pas si elles sont lourdes ou légères ; le tableau bilan sépare "
        "les deux et la légende du dossier les distingue. Sans ce choix, les "
        "planches ne sont pas dessinées.",
        icon="⚠️",
    )
    colonne_croquis, colonne_choix = st.columns([1, 2])
    with colonne_croquis:
        image = croquis_voiries(plan)
        if image is not None:
            st.image(image, width="stretch")
            st.caption(
                "Orange : à typer. Gris : sans surface, écarté du choix. "
                "Rouge : la clôture."
            )
    with colonne_choix:
        if not surfaciques:
            st.caption(
                "Aucun objet à typer : tous sont des linéaires sans surface, "
                "et n'iront sur aucune planche."
            )
        for objet in surfaciques:
            st.markdown(f"**Objet {objet['rang'] + 1}** — {objet['resume']}")
            st.radio(
                f"Type de l'objet {objet['rang'] + 1}",
                options=VOIRIES_ADMISES,
                format_func=lambda v: {
                    "piste_lourde": "Voie lourde",
                    "piste_legere": "Piste légère",
                }[v],
                index=None,
                horizontal=True,
                label_visibility="collapsed",
                key=f"voirie_{objet['rang']}",
            )
        if surfaciques:
            st.caption(
                "Une voie lourde fait cinq à six mètres de large, une piste "
                "légère trois à quatre."
            )

    ecartes = [o["rang"] + 1 for o in objets if not o["surfacique"]]
    if ecartes:
        st.caption(
            f"Objet(s) {', '.join(map(str, ecartes))} : linéaire(s) sans surface "
            "— un axe ou un bout de limite, pas une voie dessinée. Écarté(s) du "
            "choix, et d'aucune planche."
        )
    for rang, distance in voiries_hors_cadre(plan):
        st.caption(
            f"Objet {rang} : à {distance:.0f} m du site, hors du croquis. Un "
            "résidu de dessin, le plus souvent."
        )

    # La liste va au contrat dans l'ordre de la couche, un élément par objet :
    # les linéaires y prennent leur valeur convenue, les autres le choix fait.
    tranche = [
        VOIRIE_SANS_OBJET
        if not objet["surfacique"]
        else st.session_state.get(f"voirie_{objet['rang']}")
        for objet in objets
    ]
    complet = all(t is not None for t in tranche)
    st.session_state["voirie_tranchee"] = tranche if complet else None
    if complet:
        _recouper_les_voiries(import_be, tranche)



def _tableau_controles(controles) -> None:
    """Rend les contrôles croisés, quel que soit leur producteur."""
    st.dataframe(
        [
            {
                "": _icone(c.statut),
                "Contrôle": c.libelle,
                "Plan": _formater(c.valeur_dxf, c.unite),
                "Tableau": _formater(c.valeur_tableau, c.unite),
                "Tolérance": c.tolerance,
                "Commentaire": c.message,
            }
            for c in controles
        ],
        width="stretch",
        hide_index=True,
    )



# Le lot 2 — import du calepinage HelioScope — est en réserve : tous les
# dossiers passent aujourd'hui par le plan du bureau d'études interne. Sa
# section a été retirée de l'interface pour ne pas offrir deux entrées quand une
# seule sert. Le module `dp_socle/helioscope.py` et ses tests restent en place :
# c'est le chemin des projets sans plan BE, et il produit le même contrat.


# ---------------------------------------------------------------------------
# Lot 2bis — plan du bureau d'études interne
# ---------------------------------------------------------------------------

# `st.stop()` plutôt qu'un `if` enveloppant les six cents lignes qui suivent :
# Streamlit rejoue le script de haut en bas, arrêter la lecture revient à ne
# pas afficher la suite. Les sections apparaissent donc au fur et à mesure, et
# le chef de projet ne peut pas cliquer « Générer le dossier » avant d'avoir
# importé son plan — ce qui produisait un PDF de 17 Mo à quatre planches sur
# neuf, d'apparence complète.
if not (commune.strip() and fichiers_emprise):
    manquant = []
    if not commune.strip():
        manquant.append("la commune")
    if not fichiers_emprise:
        manquant.append("l'emprise cadastrale")
    st.info(
        f"Renseignez {' et '.join(manquant)} ci-dessus : l'import du plan du "
        "bureau d'études vient ensuite.",
        icon="⬆️",
    )
    st.stop()

st.divider()
#: Vrai quand la carte se tient dans cette section-ci, pour régler la coupe.
#:
#: Figé une fois pour toute l'exécution du script, et relu tel quel par la
#: section 3 bis. Recalculé là-bas, il aurait changé de valeur entre les deux :
#: le clic sur « Valider » écrit le contrat au milieu de la page, et la carte se
#: serait dessinée deux fois dans la même exécution — Streamlit refuse alors le
#: bouton « Déplacer la coupe », dont la clé serait en double.
carte_de_la_coupe = False

#: Les deux sources du plan, qui écrivent le même contrat (lot 2ter).
#:
#: Le plan du bureau d'études reste la source courante, et le choix par défaut.
#: Un projet sans plan du BE — un plan projet PDF sur un export HelioScope, le
#: cas de Gannay-sur-Loire en septembre 2026 — passe par la seconde. L'entrée
#: HelioScope seule avait été retirée le 07/09/2026 pour ne pas offrir deux
#: portes quand une seule servait ; elle revient ici avec son plan, parce que
#: l'export seul ne porte que les tables.
SOURCES_DU_PLAN = (
    "Plan du bureau d'études — DXF géoréférencé et tableau bilan",
    "Plan projet PDF sur un export HelioScope — sans plan du BE",
)
plan_du_be = st.session_state.get("source_plan", SOURCES_DU_PLAN[0]) == SOURCES_DU_PLAN[0]

if plan_du_be:
    st.subheader("2. Plan du bureau d'études")
    st.caption(
        "Import du DXF et du tableau bilan fournis par le BE, recoupement des "
        "deux, tracé de la ligne de coupe A-A' et profil du terrain. Produit "
        "`geometries.gpkg` et `projet.json` pour le dessin des planches ; ne "
        "dessine aucune planche."
    )
else:
    st.subheader("2. Plan projet PDF sur un export HelioScope")
    st.caption(
        "Les tables viennent de l'export HelioScope, placé en Lambert 93 ; le "
        "reste — clôture, portail, haies, pistes, postes — vient du plan PDF, "
        "calé sur ces tables. Produit le même `geometries.gpkg` et le même "
        "`projet.json` qu'un plan du bureau d'études ; ne dessine aucune planche."
    )
st.radio(
    "D'où vient le plan ?",
    SOURCES_DU_PLAN,
    key="source_plan",
    horizontal=True,
    help="Les deux sources produisent le même contrat, et les planches ne "
    "savent pas laquelle les a nourries. Un plan PDF seul ne suffit pas : ses "
    "formes ne sont pas à l'échelle, c'est l'export HelioScope qui la donne.",
)

for cle, defaut in (
    ("import_be", None),
    ("coupe_be", None),
    ("profil_be", None),
    ("correspondance_be", None),
):
    if cle not in st.session_state:
        st.session_state[cle] = defaut


fichier_dxf = fichier_tableau = None
fichier_export_helioscope = fichier_plan_pdf = None
if plan_du_be:
    colonne_dxf, colonne_tableau = st.columns(2)
    with colonne_dxf:
        fichier_dxf = st.file_uploader(
            "Plan BE (DXF géoréférencé en Lambert 93)",
            type=["dxf"],
            help="L'unité est déduite des coordonnées, jamais de l'en-tête "
            "$INSUNITS — sur les fichiers du BE il annonce des millimètres alors "
            "que le plan est en mètres. Un plan hors des bornes du Lambert 93 "
            "est refusé.",
        )
    with colonne_tableau:
        fichier_tableau = st.file_uploader(
            "Tableau bilan (.xlsx)",
            type=["xlsx"],
            help="Onglets lus : « 2. Caractéristiques du projet », « Dimensions "
            "postes et pieux », « Standards UNITe ».",
        )
else:
    colonne_export, colonne_plan_pdf = st.columns(2)
    with colonne_export:
        fichier_export_helioscope = st.file_uploader(
            "Export HelioScope (ZIP)",
            type=["zip"],
            help="Le ZIP téléchargé depuis HelioScope, ou le « Layout CAD » qu'il "
            "contient : le DXF du calepinage et son image de fond. C'est lui qui "
            "place les tables en Lambert 93, et le plan PDF avec elles.",
        )
    with colonne_plan_pdf:
        fichier_plan_pdf = st.file_uploader(
            "Plan projet (PDF)",
            type=["pdf"],
            help="Le plan monté sur une copie d'écran HelioScope, avec sa légende. "
            "Les couleurs se relèvent sur les pastilles de la légende ; les tables "
            "de la copie d'écran donnent l'échelle.",
        )

# Le dépôt d'un relevé altimétrique a été retiré le 26/09/2026 : le RGE ALTI a
# toujours répondu, et le champ ne servait qu'à s'en passer. `profil_terrain`
# garde son paramètre `fichier_altimetrie` — un relevé drone plus précis reste
# exploitable en ligne de commande, et `tests/test_coupe.py` le mesure.



def _deposer(fichier, commune: str) -> Path | None:
    """Écrit un fichier téléversé dans le dépôt du projet et rend son chemin.

    **Seulement s'il a changé.** Cette fonction est appelée dans le flux
    principal, donc à chaque exécution du script — c'est-à-dire à chaque clic,
    chaque case cochée, chaque déplacement de coupe. Elle réécrivait jusqu'ici
    le DXF et le classeur à chaque fois, soit plusieurs dizaines de mégaoctets
    pour rien.

    Le coût n'était pas le pire : signalé le 16/09/2026 en usage réel, un dossier
    de projets synchronisé par OneDrive faisait échouer l'écriture sur un
    `PermissionError`, le service tenant le fichier ouvert pendant qu'il le
    téléversait. Un fichier qui n'a pas changé ne se réécrit donc plus, et la
    fenêtre pendant laquelle la collision est possible se referme.
    """
    if fichier is None:
        return None
    dossier = DOSSIER_PROJETS / _nom_depot(commune)
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / Path(fichier.name).name
    if _deja_ecrit(cible, fichier):
        return cible
    _ecrire_depose(cible, fichier.getbuffer())
    _retenir_ecriture(cible, fichier)
    return cible


@st.cache_data(
    show_spinner="Lecture des calques du DXF… (une dizaine de secondes pour un "
    "plan de 50 Mo comme celui de Sarnois)"
)
def _calques_caches(chemin: str, taille: int, charte: str):
    """Calques du DXF, avec la catégorie proposée par la charte.

    `taille` fait partie de la clé : un DXF retéléversé sous le même nom doit
    être relu. `charte` aussi : sans elle, élargir la correspondance ne changeait
    rien à l'écran, qui continuait de servir l'appariement d'avant.
    """
    return calques_du_dxf(chemin)


#: Les gestes qui se font en cliquant sur la carte : le libellé du bouton qui
#: arme le geste, et ce que la bannière annonce une fois armé.
#:
#: Trois depuis le lot 6, qui a repris le mécanisme plutôt que d'en écrire un
#: second. Les deux derniers nomment la photographie visée : leur bannière est
#: un gabarit, complété par `_bandeau_geste`.
#:
#: « Placer » et « viser » sont les deux gestes de `photos-geoloc`, au même sens
#: et dans les mêmes termes — l'un désigne où est la photo, l'autre ce qu'elle
#: regarde. Le chef de projet les connaît déjà.
#: Libellé du bouton, texte du bandeau, et **couleur du liseré** dont la carte
#: s'entoure tant que le geste est armé.
#:
#: Le bandeau ne suffisait pas : « quand il faut viser pour changer un cap, c'est
#: toujours une main qui apparaît sur la carte, donc on ne comprend pas trop que
#: le mode visée est actif » (retour d'usage du 19/09/2026). Le curseur de
#: Leaflet reste celui du déplacement, et rien sur la carte ne dit qu'elle
#: attend un clic. La couleur est celle de ce que le geste pose — le noir de la
#: coupe, le rose des prises de vue — pour que le liseré désigne le geste et pas
#: seulement un état.
GESTES_CARTE = {
    "translation_coupe": (
        "Déplacer la coupe",
        "**Cliquez sur la carte** à l'endroit où la coupe doit passer. Le trait "
        "pointillé qui suit votre souris montre où elle se posera — elle reste "
        "perpendiculaire aux rangées, vous choisissez sa position et jamais sa "
        "direction.",
        "#000000",
    ),
}


def _signaler_le_geste(carte, geste: str) -> None:
    """Met la carte en réticule et l'entoure du liseré du geste armé.

    Le style s'injecte dans le document de la carte, et non dans la page : le
    composant `st_folium` vit dans un cadre isolé qu'aucune feuille de style de
    Streamlit n'atteint.

    Les trois classes sont nécessaires : Leaflet pose `grab` sur `.leaflet-grab`,
    `grabbing` pendant le déplacement, et son propre curseur sur les objets
    cliquables. Sans les trois, la main revient dès que la souris passe sur une
    table ou sur la clôture.
    """
    couleur = GESTES_CARTE[geste][2]
    carte.get_root().header.add_child(
        folium.Element(
            "<style>"
            ".leaflet-container,.leaflet-grab,.leaflet-interactive,"
            ".leaflet-dragging .leaflet-grab{cursor:crosshair !important}"
            f".leaflet-container{{box-shadow:inset 0 0 0 4px {couleur}}}"
            "</style>"
        )
    )


def _armer_geste(geste: str) -> None:
    """Arme un geste : le prochain clic sur la carte lui sera destiné."""
    st.session_state["geste_carte"] = geste


def _desarmer_geste() -> None:
    st.session_state["geste_carte"] = None


def _geste_arme() -> str | None:
    return st.session_state.get("geste_carte")




def _repere_clic(clic) -> tuple[float, float] | None:
    """Le clic réduit au millimètre, de quoi le reconnaître d'une exécution à l'autre."""
    return None if clic is None else (round(clic.x, 3), round(clic.y, 3))


def _clic_neuf(resultat_carte):
    """Le point cliqué depuis le dernier retenu, ou None. Lecture sans effet.

    `last_clicked` **persiste** d'une exécution du script à la suivante tant que
    le composant n'est pas remonté : il dit où a eu lieu le dernier clic, pas
    qu'un clic vient d'avoir lieu. Le lire sans mémoire ferait rejouer le même
    clic à chaque interaction — un déplacement de coupe à chaque case cochée.
    D'où la lecture pure ici et la mise à jour explicite par `_retenir_clic` :
    trois gestes armés côte à côte pourront la partager sans se voler le clic.

    Limite assumée : recliquer au pixel exact du clic précédent ne produit rien.
    Le composant n'envoie pas une valeur inchangée, donc Streamlit ne relance pas
    le script. Le geste reste armé et le clic suivant passe ; la coupe aurait de
    toute façon été la même.
    """
    clic = clic_l93(resultat_carte)
    if clic is None or _repere_clic(clic) == st.session_state.get("dernier_clic_carte"):
        return None
    return clic


def _retenir_clic(clic) -> None:
    """Retient ce clic comme vu : il ne déclenchera plus rien.

    Appelé aussi quand aucun geste n'est armé. Sans cela, un clic fait pour
    regarder le plan restait en réserve, et armer un geste plus tard le
    consommait aussitôt : la coupe sautait à un endroit cliqué cinq minutes
    avant, sans que le chef de projet ait cliqué.
    """
    st.session_state["dernier_clic_carte"] = _repere_clic(clic)


def _mettre_a_jour_le_contrat(import_be) -> None:
    """Réécrit le contrat de sortie quand il existe déjà, coupe et profil compris.

    La carte vit désormais après le bouton « Valider l'import » (section 3 bis,
    17/09/2026) : une coupe déplacée ensuite ne serait plus dans le contrat, et
    la planche DP 3 sortirait avec la coupe d'avant — juste d'aspect, fausse de
    fait. C'est exactement le genre de planche que ce dépôt refuse.

    N'écrit rien tant que le chef de projet n'a pas validé : avant cela, il
    règle son import et le contrat n'a pas à exister.
    """
    dossier = DOSSIER_SORTIE / _nom_dossier(commune)
    if not (dossier / NOM_GEOPACKAGE).exists():
        return
    try:
        import_be.ecrire(dossier)
    except ErreurDP as erreur:
        st.error(
            f"La coupe a été déplacée, mais le contrat n'a pas pu être réécrit "
            f"({erreur}). Revalidez l'import avant de générer, sans quoi la "
            "planche DP 3 porterait la coupe précédente.",
            icon="🚫",
        )

def _relever_et_controler(coupe, import_be, plan, origine: str) -> None:
    """Retient la coupe, relève son profil et rejoue les contrôles de cohérence.

    Les deux gestes qui décident de la coupe — tracer puis corriger, ou cliquer
    pour la déplacer — enchaînent exactement la même suite. Une coupe retenue
    sous le profil de la précédente donnerait une planche DP 3 fausse et
    d'apparence normale : le profil est donc effacé avant d'être redemandé, pour
    qu'un RGE ALTI muet laisse un trou visible et non l'ancien relevé.
    """
    st.session_state.coupe_be = coupe
    st.session_state["origine_coupe"] = origine
    import_be.ligne_coupe = coupe
    st.session_state.profil_be = None
    import_be.profil = None
    import_be.coherence = None
    import_be.terrain_be = []
    with st.spinner("Interrogation du RGE ALTI…"):
        st.session_state.profil_be = profil_terrain(
            coupe
        )
    import_be.profil = st.session_state.profil_be
    import_be.coherence = controler_coherence(
        st.session_state.profil_be, coupe, plan.tables
    )
    import_be.terrain_be = controler_terrain_embarque(
        st.session_state.profil_be, coupe, plan.points_terrain, CALQUES_TERRAIN
    )
    _mettre_a_jour_le_contrat(import_be)


def _proposer_la_coupe(import_be) -> None:
    """Place la coupe par défaut et relève son profil, dès l'import.

    Le chef de projet n'a plus à tracer pour avancer : il regarde où la coupe
    s'est posée et il la déplace seulement si elle lui déplaît. C'est un gain
    net, la position tracée n'ayant jamais servi qu'à choisir l'endroit — la
    direction, elle, a toujours été imposée par les rangées.

    Rien de muet ici : un plan sans table, ou un RGE ALTI qui ne répond pas,
    laisse la coupe ou le profil à `None` et le dit à l'écran. Le chef de projet
    trace alors lui-même, comme avant.
    """
    if st.session_state.coupe_be is not None:
        # Une coupe reprise d'un import précédent a la priorité : elle porte le
        # choix déjà fait sur ce projet, que le nôtre écraserait.
        st.session_state["origine_coupe"] = "reprise"
        return
    try:
        coupe = coupe_par_defaut(
            import_be.plan.azimut_tables_deg,
            import_be.plan.polygone_cloture,
            import_be.plan.tables,
        )
    except ErreurDP as erreur:
        st.warning(
            f"Aucune coupe n'a pu être proposée ({erreur}). Tracez-la sur la "
            "carte.",
            icon="⚠️",
        )
        return
    st.session_state.coupe_be = coupe
    st.session_state["origine_coupe"] = "defaut"
    import_be.ligne_coupe = coupe
    try:
        with st.spinner("Relevé du profil du terrain…"):
            st.session_state.profil_be = profil_terrain(
                coupe
            )
    except ErreurDP as erreur:
        st.warning(
            f"Coupe proposée, mais le profil du terrain n'a pas pu être relevé "
            f"({erreur}). Relancez-le avec « Corriger et relever le profil ».",
            icon="⚠️",
        )
        return
    import_be.profil = st.session_state.profil_be
    import_be.coherence = controler_coherence(
        st.session_state.profil_be, coupe, import_be.plan.tables
    )
    import_be.terrain_be = controler_terrain_embarque(
        st.session_state.profil_be,
        coupe,
        import_be.plan.points_terrain,
        CALQUES_TERRAIN,
    )


def _carte_du_plan(import_be_courant, avec_la_coupe: bool) -> None:
    """La carte du plan : le plan importé, et la ligne de coupe qui se pose dessus.

    Deux états, et un seul composant de carte — jamais deux à l'écran. Tant que
    l'import n'est pas validé, la coupe s'y règle. Une fois validé, elle est figée
    et la carte reste, en lecture seule : c'est là que le chef de projet vérifie
    le plan et sa légende avant de générer, et la lui retirer à la validation
    l'aveuglait au moment où il en a le plus besoin.

    Elle servait aussi à placer et viser les prises de vue, sous les dépôts de
    photographies ; ces sections ont été retirées le 26/09/2026, le volet
    photographique se traitant désormais dans le `.pptx` du lot 8.

    `plan` et `emprise_cloturee` sont relus de l'import plutôt que lus au
    module : une fonction qui lit un global écrit plus bas lève dans le
    navigateur et nulle part ailleurs, ce que `test_ordre_app` refuse.
    """
    plan = import_be_courant.plan
    emprise_cloturee = plan.polygone_cloture

    if not avec_la_coupe and _geste_arme() == "translation_coupe":
        # Armé avant la validation, puis validé : le geste n'a plus de bouton
        # pour l'annuler et sa bannière réclamerait un clic que rien n'attend.
        _desarmer_geste()

    # -----------------------------------------------------------------------
    # Le plan importé, et la coupe qui se pose dessus
    # -----------------------------------------------------------------------
    #
    # Une seule carte, et non un aperçu statique suivi d'une carte à tracer :
    # les deux montraient presque la même chose, et le chef de projet plaçait sa
    # coupe sur des tables et une clôture sans voir ce qu'elle allait couper. Il
    # procédait par essai-erreur — tracer, corriger, descendre lire l'aperçu,
    # remonter. Ici il la pose sur le plan lui-même, aux couleurs de la planche.
    if not avec_la_coupe:
        # Plus un mot sur la coupe ici : elle est figée par la validation, et
        # continuer d'en parler « vient polluer le reste du process » (retour
        # d'usage du 22/09/2026). Ce qui reste est la vérification du plan.
        st.markdown("### Le plan importé, pour vérification")
        st.caption(
            "Ce que les planches porteront, aux couleurs de la légende DP. La "
            "coupe A-A' est figée par la validation ; pour la reprendre, "
            "revalidez l'import."
        )
    else:
        st.markdown("### Le plan importé, et la ligne de coupe A-A'")
        st.caption(
            "**Une coupe est déjà proposée** : elle est perpendiculaire aux "
            "rangées et posée là où elle traverse le plus de tables. Si elle "
            "vous convient, il n'y a rien à faire.\n\n"
            "Pour la déplacer, cliquez sur **« Déplacer la coupe »** puis sur "
            "la carte : elle glissera pour passer par ce point, en gardant la "
            "direction imposée par les rangées (azimut des tables mesuré à "
            f"{plan.azimut_tables_deg:.2f}° depuis l'est, plus 90°) et son "
            "étendue à toute l'emprise clôturée avec 10 m de marge."
        )

    # Le clic armé, et le tracé replié dessous en contournement. Tracer ne
    # déplaçait rien : en automatique la position est recalculée par
    # `position_de_coupe` et la coupe repose là où elle était, le tracé ne servant
    # que de déclencheur. Le seul moyen d'imposer une position était de conserver
    # la direction tracée — donc une oblique, qui allonge toutes les distances
    # lues sur la planche.
    #
    # Armer et désarmer relancent le script. Sans cela l'écran restait d'un tour
    # en retard sur lui-même : la bannière s'affichait sous un bouton qui
    # proposait encore de déplacer la coupe, sans moyen d'annuler, et l'inverse à
    # l'annulation — la bannière réclamait un clic que plus rien n'attendait.
    if _geste_arme() == "translation_coupe" and avec_la_coupe:
        st.info(GESTES_CARTE["translation_coupe"][1], icon="🖱️")
        if st.button("Annuler le déplacement", key="annuler_translation_coupe"):
            _desarmer_geste()
            st.rerun()
    elif avec_la_coupe and st.button(
        GESTES_CARTE["translation_coupe"][0],
        key="armer_translation_coupe",
        width="stretch",
    ):
        _armer_geste("translation_coupe")
        st.rerun()

    carte = folium.Map(tiles=None, control_scale=True)
    folium.TileLayer(
        tiles=URL_TUILES_ORTHO,
        attr="IGN — Géoplateforme",
        name="Ortho IGN",
        max_zoom=21,
    ).add_to(carte)

    # L'emprise cadastrale sous le reste : c'est le cadre foncier, pas un objet
    # du projet.
    emprise_cadastrale = st.session_state.get("emprise_cadastrale_be")
    if emprise_cadastrale is not None:
        folium.GeoJson(
            en_wgs84([emprise_cadastrale]),
            style_function=lambda _trait: {
                "color": "#ffd700",
                "weight": 3,
                "fill": False,
            },
            name="Emprise cadastrale",
        ).add_to(carte)

    for style, collection in _couches_de_la_carte(plan):
        folium.GeoJson(
            collection,
            style_function=lambda trait, style=style: _style_carte(style, trait),
            name=style.libelle,
        ).add_to(carte)

    # La coupe retenue, et elle seule. Le tracé d'origine était montré à côté,
    # en orange : le chef de projet qui traçait volontairement de travers voyait
    # son trait oblique persister et croyait que rien n'avait été redressé.
    #
    # La coupe retenue reste dessinée après la validation, elle. Elle la quittait
    # jusqu'au 26/09/2026, quand la carte d'après-validation ne servait plus qu'aux
    # prises de vue ; elle sert maintenant à vérifier le plan, et par où passe la
    # coupe est précisément ce qui décide de la planche DP 3.
    if st.session_state.coupe_be is not None:
        folium.GeoJson(
            en_wgs84([st.session_state.coupe_be.geometrie]),
            style_function=lambda _trait: {"color": "#000000", "weight": 4},
            name="Coupe A-A'",
        ).add_to(carte)

    # Le trait d'aperçu, et seulement quand le geste est armé : une ligne qui
    # suivrait la souris en permanence serait du bruit. Tout se passe dans le
    # navigateur — aucun rechargement, contrairement à `return_on_hover` qui
    # relancerait le script à chaque mouvement de souris. Voir `apercu_au_survol`.
    if _geste_arme() == "translation_coupe":
        # `representative_point` plutôt que le centroïde : shapely le garantit
        # **dans** le polygone, quand le centroïde d'une emprise concave peut en
        # sortir — et une coupe qui n'y passe pas est refusée. Le cas ne se
        # présente qu'avant toute coupe retenue ; d'ordinaire c'est celle de
        # l'écran qui sert de référence, et l'aperçu lui est exactement parallèle.
        apercu_au_survol(
            st.session_state.coupe_be.geometrie
            if st.session_state.coupe_be is not None
            else translater_ligne_coupe(
                emprise_cloturee.representative_point(),
                plan.azimut_tables_deg,
                emprise_cloturee,
            ).geometrie
        ).add_to(carte)

    sud, ouest, nord, est = bornes_wgs84(emprise_cloturee)
    carte.fit_bounds([[sud, ouest], [nord, est]])

    if _geste_arme() is not None:
        _signaler_le_geste(carte, _geste_arme())

    # La clé porte un compteur : elle change à chaque coupe retenue, ce qui
    # remonte la carte à neuf. Sans cela le trait tracé par le chef de projet
    # restait affiché par Leaflet, par-dessus la coupe redressée, et le bouton
    # « Corriger » se represéntait indéfiniment.
    resultat_carte = st_folium(
        carte,
        width=None,
        height=560,
        # Clé stable : la carte ne se remonte jamais, et garde donc le zoom et
        # le cadrage du chef de projet. Elle portait un compteur tant que le
        # tracé polyligne existait — il fallait chasser le trait Leaflet
        # résiduel qui se superposait à la coupe redressée. Le tracé retiré, ce
        # trait n'existe plus, et le compteur non plus.
        key="carte_coupe_be",
        # Les trois seules valeurs que cet écran lise. Sans cette restriction le
        # composant renvoyait aussi le cadrage et le niveau de zoom, et déplacer
        # la carte ou zoomer relançait le script. Mesuré le 15/09/2026 dans son
        # bundle : la charge est filtrée sur cette liste, puis comparée à la
        # précédente, et `setComponentValue` n'est appelé que si elle a changé.
        # Le tracé polyligne a été retiré le 17/09/2026 : la carte ne rend plus
        # que le clic, seul geste qui décide encore de la coupe.
        returned_objects=["last_clicked"],
    )
    clic = _clic_neuf(resultat_carte)

    st.caption(
        "Couleurs de la légende DP, relevées sur la planche DP 2 du dossier de "
        "référence HOCH « Les Islettes » : "
        + " · ".join(
            f"{style.libelle} ({nombre})"
            for _, style, nombre in legende_presente(plan)
        )
        + ". Jaune : emprise cadastrale."
        + " Noir : coupe A-A' retenue."
        + " Les modules ne sont pas dessinés ici — la silhouette des rangées dit "
        "la même chose et un plan en compte des milliers. Les couleurs du DXF ne "
        "sont pas reprises, les codes ACI y sont des couleurs de travail."
    )

    if _geste_arme() is None:
        # Aucun geste attendu : ce clic-là ne l'était pas non plus. Le retenir
        # l'empêche d'être consommé par le prochain geste armé, ce qui faisait
        # sauter la coupe à un endroit cliqué bien avant, sans nouveau clic.
        _retenir_clic(clic)
    elif _geste_arme() == "translation_coupe" and clic is not None:
        _retenir_clic(clic)
        _desarmer_geste()
        try:
            _relever_et_controler(
                translater_ligne_coupe(
                    clic, plan.azimut_tables_deg, emprise_cloturee
                ),
                import_be_courant,
                plan,
                "deplacee",
            )
        except ErreurDP as erreur:
            # La coupe précédente reste en place, contrairement au tracé qui
            # l'efface : un clic tombé trop loin du site ne doit pas faire perdre
            # la coupe qui était retenue.
            st.error(f"{type(erreur).__name__} : {erreur}")
        else:
            # La carte a déjà été dessinée avec l'ancienne coupe : il faut
            # rejouer le script pour la voir bouger. Un rechargement par clic,
            # celui du bouton « Corriger » d'à côté. La clé de la carte, elle,
            # ne change pas — un clic ne laisse aucun tracé Leaflet résiduel à
            # chasser, et la remonter ferait perdre son zoom au chef de projet.
            st.rerun()

    if avec_la_coupe and st.session_state.coupe_be is None:
        st.info(
            "Aucune coupe retenue : cliquez sur « Déplacer la coupe » puis sur "
            "la carte, à l'endroit où elle doit traverser les rangées."
        )



def _reprendre_import_precedent(dossier: Path, import_be, emprise_cadastrale) -> None:
    """Recharge le tracé de coupe laissé par un import précédent, s'il y en a un.

    Le brief est explicite : une régénération ne redemande jamais le tracé.
    C'est le tracé **initial** qui est repris, pas la ligne corrigée — la
    correction est rejouée sur le plan d'aujourd'hui, qui peut avoir tourné
    depuis. Le profil déjà relevé n'est réutilisé que si la ligne recalculée
    tombe au même endroit ; sinon il est redemandé au RGE ALTI.
    """
    st.session_state.coupe_be = None
    st.session_state.profil_be = None

    enregistree = coupe_enregistree(lire_parametres(dossier))
    if enregistree is None:
        return

    plan = import_be.plan
    emprise_cloturee = plan.polygone_cloture
    if emprise_cloturee is None:
        st.warning(
            "Un tracé de coupe existe dans la sortie précédente, mais le plan "
            "importé n'a pas de contour de clôture : il ne peut pas être repris.",
            icon="⚠️",
        )
        return

    try:
        coupe, profil_reutilisable = reprendre_coupe(
            enregistree, plan.azimut_tables_deg, emprise_cloturee,
            tables=plan.tables,
        )
    except ErreurCoupe as erreur:
        # Le dossier de sortie porte le tracé d'un autre projet : on ne le
        # reprend pas, et on le dit plutôt que de repartir en silence.
        st.warning(
            f"Tracé de coupe de la sortie précédente non repris — {erreur} "
            "Il venait probablement d'un autre projet enregistré sous le même "
            "identifiant de dossier.",
            icon="⚠️",
        )
        return
    st.session_state.coupe_be = coupe
    import_be.ligne_coupe = coupe

    if profil_reutilisable and enregistree.profil is not None:
        st.session_state.profil_be = enregistree.profil
    else:
        with st.spinner("Relevé du profil du terrain…"):
            st.session_state.profil_be = profil_terrain(
                coupe
            )
    import_be.profil = st.session_state.profil_be
    import_be.coherence = controler_coherence(
        st.session_state.profil_be, coupe, plan.tables
    )
    import_be.terrain_be = controler_terrain_embarque(
        st.session_state.profil_be, coupe, plan.points_terrain, CALQUES_TERRAIN
    )

# ---------------------------------------------------------------------------
# Lot 2ter — un plan projet PDF sur un export HelioScope
# ---------------------------------------------------------------------------

#: Ce qu'un libellé de la légende du plan peut recevoir. Ni `voirie`, ni les
#: tables : le plan ne donne d'une piste que son axe, et une voirie sans surface
#: ne va sur aucune planche — lourde ou légère se tranche donc ici, sur le
#: libellé ; les tables, elles, viennent de l'export HelioScope.
CATEGORIES_DE_LEGENDE = tuple(
    c for c in CATEGORIES if c not in ("voirie", "ligne_coupe", "tables_pv", "modules_pv")
)


@st.cache_data(show_spinner="Lecture de la légende du plan…", max_entries=4)
def _legende_du_plan(chemin: str, taille: int):
    """Libellé, couleur relevée et catégorie proposée de chaque entrée.

    `taille` fait partie de la clé : un plan redéposé sous le même nom doit être
    relu.
    """
    from dp_socle.plan_pdf import lire_legende

    return [
        (e.libelle, e.couleur, e.categorie, e.a_trancher) for e in lire_legende(chemin)
    ]


def _correspondance_de_la_legende(chemin_pdf: Path) -> tuple[dict, list]:
    """Fait confirmer la catégorie de chaque libellé, avant l'import.

    Comme les calques du bureau d'études : proposée d'après les libellés connus,
    modifiable, et un libellé laissé sur « (ignorer) » n'est pas importé. Les
    libellés changent d'un plan à l'autre — « Réserve incendie » ici, « Citerne
    incendie » là —, et deux de ceux de Bray ne disent pas si la piste est
    lourde ou légère.

    Ceux-là n'ont pas de choix d'office : « (ignorer) », proposé par défaut,
    faisait disparaître les pistes de Bray sans que personne l'ait décidé
    (retour d'usage du 24/09/2026). Rend la correspondance, et les libellés
    encore à trancher avec la raison de chacun.
    """
    from dp_socle.plan_pdf import CATEGORIES_IMPORTABLES

    entrees = _legende_du_plan(str(chemin_pdf), chemin_pdf.stat().st_size)
    # Seulement ce qu'un plan PDF sait importer : une autre catégorie, choisie
    # ici, ne sortait pas du plan, et rien ne le disait (24/09/2026).
    options = ["(ignorer)"] + [c for c in CATEGORIES_DE_LEGENDE if c in CATEGORIES_IMPORTABLES]
    a_decider = [e for e in entrees if e[2] is None]
    choix, a_trancher_encore = {}, []
    with st.expander(
        f"La légende du plan — {len(entrees)} entrée(s)"
        + (f", dont {len(a_decider)} à apparier" if a_decider else "")
        + " — modifiable",
        expanded=bool(a_decider),
    ):
        st.caption(
            "Chaque couleur est relevée sur la pastille qui précède son libellé : "
            "rien n'est supposé. Une forme de la carte va à la pastille dont elle "
            "porte la couleur."
        )
        for rang, (libelle, couleur, categorie, a_trancher) in enumerate(entrees):
            colonne_teinte, colonne_libelle, colonne_categorie = st.columns([1, 6, 4])
            with colonne_teinte:
                st.color_picker(
                    "Couleur",
                    value="#{:02x}{:02x}{:02x}".format(*couleur),
                    disabled=True,
                    key=f"teinte_legende_{rang}_{libelle}",
                    label_visibility="collapsed",
                )
            with colonne_libelle:
                st.markdown(f"**{libelle}**" + (f" — {a_trancher}" if a_trancher else ""))
            with colonne_categorie:
                retenue = st.selectbox(
                    "Catégorie",
                    options,
                    index=(
                        None
                        if a_trancher
                        else options.index(categorie) if categorie in options else 0
                    ),
                    placeholder="à choisir",
                    key=f"categorie_legende_{rang}_{libelle}",
                    label_visibility="collapsed",
                )
            if retenue is None:
                a_trancher_encore.append((libelle, a_trancher))
            choix[libelle] = None if retenue in (None, "(ignorer)") else retenue
    return choix, a_trancher_encore


def _importer_le_plan_pdf(
    commune: str, fichiers_emprise, fichier_export, fichier_pdf
) -> None:
    """Dépose l'export et le plan, fait confirmer la légende, importe et cale."""
    from dp_socle.plan_pdf import importer_plan_pdf

    if fichier_export is None or fichier_pdf is None:
        manquants = [
            libelle
            for libelle, fichier in (
                ("l'**export HelioScope (ZIP)**", fichier_export),
                ("le **plan projet (PDF)**", fichier_pdf),
            )
            if fichier is None
        ]
        if any(f is not None for f in (fichier_export, fichier_pdf)):
            st.warning(
                f"Il manque {' et '.join(manquants)} : le bouton « Importer et "
                "caler le plan » n'apparaît qu'une fois les deux déposés. Le plan "
                "seul n'a pas d'échelle, l'export seul n'a que les tables.",
                icon="⚠️",
            )
        return

    chemin_export = _deposer(fichier_export, commune)
    chemin_pdf = _deposer(fichier_pdf, commune)
    try:
        correspondance, a_trancher = _correspondance_de_la_legende(chemin_pdf)
    except ErreurDP as erreur:
        st.error(f"{type(erreur).__name__} : {erreur}")
        return

    if a_trancher:
        st.warning(
            "Tranchez d'abord, dans la légende : "
            + " ; ".join(f"« {libelle} », {raison}" for libelle, raison in a_trancher)
            + ". « (ignorer) » l'écarte de l'import, en le disant.",
            icon="⚠️",
        )
    # La correspondance de la légende fait partie de ce qui change le résultat,
    # donc de la signature. Sans elle, le chef de projet qui corrigeait
    # l'appariement d'un libellé après l'import trouvait le bouton grisé : sa
    # correction ne pouvait pas prendre, et le dossier gardait le premier
    # choix. Relevé le 30/09/2026 sur Gannay — « pas de différenciation des
    # haies malgré la modification dans la légende du plan ».
    source_pdf = (
        _empreinte(fichier_export),
        _empreinte(fichier_pdf),
        tuple(sorted((correspondance or {}).items())),
    )
    deja = _deja_fait("import_pdf_fait", source_pdf)
    if not st.button(
        "Importer et caler le plan",
        type="primary",
        width="stretch",
        disabled=bool(a_trancher) or deja,
        help=AIDE_DEJA_FAIT if deja else None,
    ):
        return
    _retenir_ce_qui_a_servi("import_pdf_fait", source_pdf)
    st.session_state.coupe_be = None
    st.session_state.profil_be = None
    st.session_state["couches_carte"] = None
    st.session_state["origine_coupe"] = None
    # Pas d'indice : il vient du tableau bilan, et il n'y en a pas.
    nom_importe = identifiant_de_dossier(nom_de_projet(commune))
    chemin_emprise = _enregistrer_fichiers(nom_importe, fichiers_emprise)
    emprise_cadastrale = (
        charger_emprise(chemin_emprise).geometrie if chemin_emprise is not None else None
    )
    try:
        with st.spinner(
            "Lecture de l'export HelioScope et du plan, calage du plan sur les "
            "tables… (une dizaine de secondes)"
        ):
            resultat = importer_plan_pdf(
                chemin_pdf,
                chemin_export,
                emprise_cadastrale=emprise_cadastrale,
                correspondance=correspondance,
            )
    except ErreurDP as erreur:
        st.error(f"{type(erreur).__name__} : {erreur}")
        return
    st.session_state.import_be = resultat
    st.session_state["indice_tableau_bilan"] = None
    st.session_state.emprise_cadastrale_be = emprise_cadastrale
    _reprendre_import_precedent(DOSSIER_SORTIE / nom_importe, resultat, emprise_cadastrale)
    _proposer_la_coupe(resultat)
    # Même raison qu'au plan BE : le bouton s'est rendu avant ce bloc.
    st.rerun()


def _oublier_la_carte_et_la_coupe(import_pdf) -> None:
    """Le plan a bougé : les couches de la carte et la coupe ne valent plus."""
    st.session_state["couches_carte"] = None
    st.session_state.coupe_be = None
    st.session_state.profil_be = None
    import_pdf.ligne_coupe = None
    import_pdf.profil = None


def _regler_le_calage(import_pdf) -> None:
    """Le placement en Lambert 93, réglé à l'œil sur l'ortho de la carte.

    C'est le calage du lot 2 : la latitude déduite du fichier est bonne à
    quelques mètres, la longitude pré-positionnée sur l'emprise cadastrale,
    qui ne suit pas la zone HelioScope, l'est moins.
    Le plan PDF suit les tables — il est calé sur elles dans le repère du DXF —,
    et le régler ne demande donc pas de le recaler.
    """
    from dp_socle.helioscope import (
        CORRECTION_NORD_SUD_MAX_M,
        TOLERANCE_CALAGE_M,
        corriger_nord_sud,
        decaler_longitude,
    )

    calage = import_pdf.implantation.calage
    if import_pdf.prepositionnement is not None:
        st.caption(import_pdf.prepositionnement.message)
    # Le calage sur l'ortho mesure ce que l'œil réglait : l'image de fond de
    # l'export est une photographie aérienne du site, qui se cherche dans
    # l'ortho IGN. Ce qu'il a fait reste affiché tant que le calage n'a pas
    # bougé depuis.
    if st.button(
        "Caler sur l'ortho",
        key="caler_sur_ortho_plan_pdf",
        help="Cherche l'image de fond de l'export HelioScope dans l'ortho IGN, à "
        "220 m près autour du placement actuel, et recale d'autant les deux "
        "réglages ci-dessous. Refuse, sans rien changer, si l'image ne s'y "
        "reconnaît pas nettement : le réglage à l'œil reste alors possible.",
    ):
        from dp_socle.calage_ortho import caler_sur_ortho

        try:
            with st.spinner("Recherche du fond HelioScope dans l'ortho IGN…"):
                mesure = caler_sur_ortho(import_pdf.implantation)
        except ErreurDP as erreur:
            st.error(f"{type(erreur).__name__} : {erreur}")
        else:
            st.session_state["calage_ortho_plan_pdf"] = (
                (calage.longitude_origine, calage.correction_nord_sud_m),
                mesure.message,
            )
            _oublier_la_carte_et_la_coupe(import_pdf)
            _proposer_la_coupe(import_pdf)
            st.rerun()
    derniere = st.session_state.get("calage_ortho_plan_pdf")
    if derniere and derniere[0] == (calage.longitude_origine, calage.correction_nord_sud_m):
        st.success(derniere[1], icon="🛰️")
    with st.form("calage_plan_pdf"):
        st.markdown(
            "**Placement sur l'ortho** — la clôture et les tables doivent tomber "
            "sur le terrain de la carte ci-dessous. Les deux valeurs sont "
            "comptées depuis le placement de départ, et non d'un clic à l'autre : "
            "ajustez celle qui est affichée pour vous en approcher."
        )
        colonne_est, colonne_nord = st.columns(2)
        # Le champ est-ouest repartait de zéro à chaque passe, alors que celui
        # d'à côté porte une valeur absolue : rien ne disait si sa valeur était
        # le déplacement total ou celui qui restait à faire (retour d'usage du
        # 24/09/2026). Les deux sont maintenant comptés depuis le départ.
        decalage = colonne_est.number_input(
            "Décalage vers l'est (m) — négatif vers l'ouest",
            value=float(calage.decalage_est_m),
            step=1.0,
            format="%.1f",
            help="Le déplacement **total** depuis le pré-positionnement sur "
            "l'emprise, et non ce qu'il reste à faire. « Caler sur l'ortho » "
            "l'inscrit ici, et il s'affine ensuite mètre par mètre.",
        )
        correction = colonne_nord.number_input(
            f"Correction nord-sud (m) — positive vers le nord, ±{CORRECTION_NORD_SUD_MAX_M:.0f} m",
            min_value=-CORRECTION_NORD_SUD_MAX_M,
            max_value=CORRECTION_NORD_SUD_MAX_M,
            value=float(calage.correction_nord_sud_m),
            step=1.0,
            format="%.1f",
            help="Le déplacement **total** depuis la latitude déduite du "
            "fichier, comme le décalage vers l'est l'est depuis le "
            "pré-positionnement.",
        )
        if st.form_submit_button("Recaler"):
            try:
                # Les deux champs portent une valeur absolue ; `decaler_longitude`
                # déplace : c'est l'écart au placement courant qu'il reçoit.
                ecart = decalage - calage.decalage_est_m
                if abs(ecart) > TOLERANCE_CALAGE_M:
                    decaler_longitude(calage, ecart)
                corriger_nord_sud(calage, correction)
            except ErreurDP as erreur:
                st.error(f"{type(erreur).__name__} : {erreur}")
                return
            _oublier_la_carte_et_la_coupe(import_pdf)
            _proposer_la_coupe(import_pdf)
            st.rerun()


def _trancher_les_ouvrages(import_pdf) -> None:
    """Ce que le plan ne dit pas de ses ouvrages, et la correction qu'il appelle.

    Aucune valeur par défaut : un volume de citerne ou une largeur de portail
    supposés se dessineraient parfaitement et ne se verraient jamais. La
    correction du poste (décision D8) se propose et ne s'applique que cochée.
    """
    from dp_socle.plan_pdf import VOLUMES_CITERNE_M3, ChoixDuPlan, cote_lue

    lecture = import_pdf.lecture

    def lues(categorie: str, cle: str) -> dict:
        """La cote que porte chaque entrée de légende dessinée au plan, ou None."""
        return {
            e.libelle: cote_lue(e.libelle, e.categorie).get(cle)
            for e in lecture.entree(categorie)
            if any(x.entree is e for x in lecture.elements)
        }

    # Un recalage relance le script par `st.rerun()`, qui s'arrête avant ces
    # champs : Streamlit oublie la valeur d'un widget qu'une exécution n'a pas
    # rendu, et il fallait tout retrancher à chaque passe de calage (mesuré le
    # 24/09/2026). Ce qui a déjà été tranché vit dans `choix`, et c'est lui qui
    # les réamorce.
    tranche = import_pdf.choix

    # Le volume et la largeur se portent en légende (instruction du chef de
    # projet du 23/09/2026) : lus, ils se montrent ; absents, ils se choisissent
    # ici, et l'écran dit où ils auraient dû être.
    volume = largeur = None
    volumes = lues("bache_incendie", "volume_citerne_m3")
    if volumes and all(v in VOLUMES_CITERNE_M3 for v in volumes.values()):
        st.caption(
            "Volume de la réserve incendie lu à la légende : "
            + ", ".join(f"« {l} »" for l in volumes)
            + "."
        )
    elif volumes:
        volume = st.selectbox(
            "Volume de la réserve incendie (m³)",
            VOLUMES_CITERNE_M3,
            index=(
                VOLUMES_CITERNE_M3.index(tranche.volume_citerne_m3)
                if tranche.volume_citerne_m3 in VOLUMES_CITERNE_M3
                else None
            ),
            placeholder="à choisir — la légende ne le dit pas",
            key="volume_citerne_plan_pdf",
            help="Le catalogue UNITe en compte quatre, de 7,95 x 4,44 m à "
            "10,4 x 18,5 m. Le plan situe la réserve, il ne la dimensionne pas.",
        )
        st.caption(
            "Le volume se porte dans la légende du plan — « Réserve incendie "
            "120 m³ » — et l'import le lit alors ; à défaut, il se choisit ici."
        )
    largeurs = lues("portail", "largeur_portail_m")
    if largeurs and all(v is not None for v in largeurs.values()):
        st.caption(
            "Largeur du portail lue à la légende : "
            + ", ".join(f"« {l} »" for l in largeurs)
            + "."
        )
    elif largeurs:
        largeur = st.number_input(
            "Largeur du portail (m)",
            min_value=1.0,
            max_value=20.0,
            value=tranche.largeur_portail_m,
            step=0.5,
            placeholder="à saisir — la légende ne la dit pas",
            key="largeur_portail_plan_pdf",
            help="Aucun gabarit UNITe ne la donne ; les tableaux bilan de "
            "Saint-Cyr et de Sarnois disent 7 m.",
        )
        st.caption(
            "La largeur se porte dans la légende du plan — « Portail 7 m » — et "
            "l'import la lit alors ; à défaut, elle se saisit ici."
        )
    corrections = []
    for correction in import_pdf.corrections_proposees:
        if st.checkbox(
            f"{correction.intitule} — correction du plan",
            value=correction.identifiant in tranche.corrections,
            key=f"correction_plan_{correction.identifiant}",
        ):
            corrections.append(correction.identifiant)
        st.caption(correction.raison)
    choix = ChoixDuPlan(
        volume_citerne_m3=volume,
        largeur_portail_m=largeur,
        corrections=tuple(corrections),
    )
    if choix.cle() != import_pdf.choix.cle():
        import_pdf.changer_de_choix(choix)
        st.session_state["couches_carte"] = None


def _resumer_le_plan_pdf(import_pdf) -> None:
    """Ce sur quoi le dossier est engagé, quand le plan vient d'un PDF."""
    calage = import_pdf.calage
    plan = import_pdf.plan
    engagement = st.expander("Ce sur quoi le dossier est engagé")
    colonnes = engagement.columns(4)
    colonnes[0].metric("Rangées de tables", f"{plan.nb_tables}")
    colonnes[1].metric(
        "Échelle du plan",
        f"{calage.m_par_px_reference:.4f} m/px".replace(".", ","),
        help="À 300 dpi, mesurée sur le pas des rangées : "
        f"{calage.pas_dxf_m:.3f} m dans le DXF.".replace(".", ","),
    )
    colonnes[2].metric(
        "Recouvrement des tables", f"{calage.recouvrement:.1%}".replace(".", ",")
    )
    surface = plan.surface_cloturee_m2
    colonnes[3].metric(
        "Surface clôturée",
        f"{surface / 1e4:.2f} ha".replace(".", ",") if surface else "—",
    )
    engagement.caption(
        f"« {import_pdf.lecture.source} », page {import_pdf.lecture.page}, calé sur "
        f"« {import_pdf.source_export} » : {calage.nb_rangees_plan} rangées relevées "
        f"sur le plan pour {calage.nb_rangees_dxf} dans le DXF. Il n'y a pas de "
        "tableau bilan : surfaces et puissance ne sont recoupées avec aucune "
        "déclaration."
    )


def _regler_et_trancher_le_plan_pdf(import_pdf) -> None:
    """Le calage, les choix du plan et ses ouvrages — la colonne de gauche.

    Séparé du résumé parce qu'il se tient dans une colonne à côté de la carte,
    quand les mesures qui engagent le dossier, elles, gardent toute la largeur.
    """
    _regler_le_calage(import_pdf)
    lecture = import_pdf.lecture
    if (
        lecture.elements_de("bache_incendie")
        or lecture.elements_de("portail")
        or import_pdf.corrections_proposees
    ):
        st.markdown("**Ce que le plan ne dit pas de ses ouvrages**")
        _trancher_les_ouvrages(import_pdf)
    with st.expander("Les ouvrages du plan, aux cotes de leur gabarit"):
        st.caption(
            "Le plan situe et oriente chaque ouvrage ; ses formes ne sont pas à "
            "l'échelle. Les dimensions viennent du classeur des gabarits UNITe."
        )
        st.dataframe(
            [
                {
                    "Ouvrage": o.libelle,
                    "Gabarit": o.gabarit or "à trancher",
                    "Au dossier (m)": (
                        f"{o.longueur_m:g} x {o.largeur_m:g}" if o.longueur_m else "—"
                    ),
                    "Dessiné au plan (m)": "{:.1f} x {:.1f}".format(*o.dessine_m),
                    "Orientation": o.orientation,
                }
                for o in import_pdf.construction.ouvrages
            ],
            width="stretch",
            hide_index=True,
        )


def _etat_de_l_import(import_courant):
    """Ce qui, réglé à l'écran, change les géométries écrites.

    Rien — `None` — pour un plan du bureau d'études, qui n'a ni calage ni
    couche à régler une fois importé : son écran ne change plus après l'import.
    """
    return getattr(import_courant, "etat", None)


def _cle_de_legende(libelle: str) -> str:
    """Clé de session du champ d'un intitulé.

    Le nom du dépôt en fait partie. Sans lui, une correction faite sur un projet
    suivait le chef de projet quand il en ouvrait un autre : Streamlit garde la
    valeur d'un champ tant que sa clé ne change pas, et l'intitulé de « Voie
    lourde » est le même d'un dossier à l'autre. Le second projet aurait hérité
    des mots du premier sans rien en dire.
    """
    return f"legende_{_nom_depot(commune)}_{libelle}"

def _entrees_de_legende(plan) -> list:
    """Les entrées de légende du plan importé : intitulé par défaut, et ce qu'elles couvrent.

    Une entrée par **intitulé**, et non par catégorie : deux catégories peuvent
    délibérément partager le même — « Voie lourde » couvre la piste lourde et
    l'aire de grutage, qui sont la même grave compactée — et la planche n'en fait
    qu'une ligne (décision D3 du lot 4). En montrer deux champs laisserait croire
    qu'on peut les nommer séparément, et renommer l'un des deux scinderait la
    ligne en silence.

    Rend `[(intitulé, (catégories,), nombre d'objets)]`, dans l'ordre du dessin :
    c'est celui de la légende imprimée.
    """
    from dp_socle.planches.palette import EXCLUES as EXCLUES_DP
    from dp_socle.planches.palette import SANS_STYLE, STYLES as STYLES_DP

    entrees: dict[str, list] = {}
    for categorie, fiche in sorted(STYLES_DP.items(), key=lambda p: p[1].rang):
        if categorie in EXCLUES_DP or categorie in SANS_STYLE:
            continue
        nombre = len(plan.par_categorie(categorie))
        if not nombre:
            continue
        groupe = entrees.setdefault(fiche.libelle, [fiche.libelle, [], 0])
        groupe[1].append(categorie)
        groupe[2] += nombre
    return [(libelle, tuple(cats), nombre) for libelle, cats, nombre in entrees.values()]

def _retoucher_la_legende(plan) -> None:
    """Laisse corriger les intitulés de légende avant de générer.

    Nos intitulés sont ceux du dossier de référence et conviennent presque
    toujours ; mais un projet peut avoir ses mots, et la légende est **dans
    l'image** de la planche — la rendre éditable dans le `.pptx` demanderait de
    dessiner la planche sans elle. La retouche se fait donc ici, et elle part au
    plan de masse DP 2 et aux plans de repérage des DP 4.

    **Ouvert et annoncé**, depuis que la validation en demande la relecture
    (26/09/2026). Il était replié, et présenté comme un recours : le chef de
    projet passait dessus sans le voir, puis butait sur une case à cocher qui
    lui réclamait d'avoir lu ce qu'il n'avait pas ouvert. L'annonce est en clair
    au-dessus, et le dépliant s'ouvre de lui-même.
    """
    entrees = _entrees_de_legende(plan)
    if not entrees:
        return
    st.info(
        "**Légende à relire et à valider avant de poursuivre.** Ces intitulés "
        "seront écrits tels quels sur le plan de masse DP 2 et sur les plans de "
        "repérage des DP 4.",
        icon="📋",
    )
    with st.expander("Les intitulés de la légende — à relire", expanded=True):
        st.caption(
            "Les intitulés sont ceux du dossier de référence HOCH ; corrigez-les "
            "si le dossier emploie d'autres mots. Ils ne se retouchent pas dans "
            "le PowerPoint : la légende est dessinée dans la planche."
        )
        for libelle, categories, nombre in entrees:
            st.text_input(
                f"{libelle} — {nombre} objet(s)",
                value=libelle,
                key=_cle_de_legende(libelle),
                help="Vide, l'intitulé d'origine est conservé."
                + (
                    f" Couvre {len(categories)} catégories du plan "
                    f"({', '.join(categories)}) : elles ne font qu'une ligne."
                    if len(categories) > 1
                    else ""
                ),
            )

def _legendes_retouchees(plan) -> dict:
    """Les intitulés corrigés, par catégorie, tels que `palette` les attend.

    Une saisie identique à l'intitulé d'origine n'est pas retenue : le dossier
    n'a pas à porter une correction qui ne corrige rien, et `projet.json` reste
    lisible. Un champ vidé n'est pas une correction non plus — c'est un
    renoncement, et l'intitulé d'origine reprend sa place.
    """
    retouches = {}
    for libelle, categories, _nombre in _entrees_de_legende(plan):
        saisi = str(st.session_state.get(_cle_de_legende(libelle), "")).strip()
        if not saisi or saisi == libelle:
            continue
        for categorie in categories:
            retouches[categorie] = saisi
    return retouches


def _cle_de_relecture(plan) -> str:
    """Clé de la case « j'ai relu la légende », propre au dépôt et à sa légende.

    Les intitulés en font partie : corriger l'un d'eux décoche la case, et la
    relecture se redemande. Sans cela, le chef de projet aurait pu valider une
    légende qu'il a changée après l'avoir relue.
    """
    entrees = "|".join(libelle for libelle, _cats, _n in _entrees_de_legende(plan))
    retouches = "|".join(
        f"{cle}={valeur}" for cle, valeur in sorted(_legendes_retouchees(plan).items())
    )
    return f"legende_relue_{_nom_depot(commune)}_{hash((entrees, retouches))}"


def _legende_relue(plan) -> bool:
    """La case de relecture de la légende, et son état.

    Elle est posée ici, dans la section de validation, et non sous les champs de
    la légende : c'est au moment de valider qu'on s'engage, et une case cochée
    trois écrans plus haut ne serait pas un engagement mais un réflexe.
    """
    return st.checkbox(
        "J'ai relu la légende et je la valide",
        key=_cle_de_relecture(plan),
        help="Les intitulés partent tels quels sur le plan de masse DP 2 et sur "
        "les plans de repérage des DP 4. Ils sont dessinés dans la planche : "
        "après la génération, seule une régénération les change.",
    )


def _validation_deja_faite(import_courant) -> bool:
    """Vrai si le contrat écrit correspond exactement à ce qui est à l'écran.

    Même critère que celui qui fige la coupe : ce n'est pas « un contrat
    existe » mais « le contrat écrit est celui de cet écran-ci ». Un recalage ou
    un changement de couche rallume donc le bouton, et c'est ce qu'il faut — le
    contrat sur le disque ne décrirait plus ce qu'on regarde.
    """
    return (
        DOSSIER_SORTIE / _nom_dossier(commune) / NOM_GEOPACKAGE
    ).exists() and _etat_de_l_import(import_courant) == st.session_state.get(
        "etat_ecrit"
    )


def _montrer_la_coupe(import_be_courant) -> bool:
    """L'annonce de la coupe retenue, puis la carte où elle se règle.

    La carte ne s'affiche ici que tant que le contrat n'est pas écrit, et la
    fonction rend `True` quand elle l'affiche. Appelée sous les choix d'un
    plan PDF, sous les alertes d'un plan du BE : un bloc réellement déplacé,
    et non un conteneur réservé puis rempli plus bas, dont `AppTest` garde
    les enfants d'une exécution à l'autre quand un `st.rerun()` les enchaîne.
    """
    coupe = st.session_state.coupe_be
    profil = st.session_state.profil_be
    # Une ligne, et rien de plus. La figure du profil était tracée sans respecter
    # le rapport entre les abscisses et les altitudes — 350 m de long pour 3 m de
    # dénivelée — et donnait à lire une colline là où le terrain est plat. Ses
    # chiffres n'engagent rien : ce qui compte, la cohérence de la pente et le
    # contrôle des altitudes du DXF, remonte déjà en avertissement quand il
    # cloche. La coupe se juge sur la carte et sur la planche DP 3.
    if coupe is not None:
        origine_profil = (
            f", profil relevé sur {profil.origine}" if profil is not None else ""
        )
        annonces = {
            "defaut": (
                "**Coupe par défaut** : perpendiculaire aux rangées, posée là "
                f"où elle traverse le plus de tables{origine_profil}. Tracez sur "
                "la carte si vous voulez la déplacer."
            ),
            "deplacee": (
                "**Coupe déplacée** : elle passe par le point que vous avez "
                "cliqué, perpendiculairement aux rangées"
                f"{origine_profil}. Recliquez sur « Déplacer la coupe » pour la "
                "reposer ailleurs."
            ),
            "tracee": (
                "**Coupe personnalisée** : redressée perpendiculairement aux "
                f"rangées à partir de votre tracé{origine_profil}."
            ),
            "reprise": (
                "**Coupe reprise de l'import précédent** de ce projet, telle "
                f"qu'elle avait été retenue{origine_profil}. Tracez sur la carte "
                "si vous voulez la déplacer."
            ),
        }
        st.success(
            annonces.get(st.session_state.get("origine_coupe"), annonces["tracee"]),
            icon="📐",
        )

    # La coupe se règle tant que ce qui est à l'écran n'a pas été écrit. Ce n'est
    # pas « tant que le contrat n'existe pas » : après une première validation, un
    # recalage ou un changement de couche remet la coupe en jeu, et la figer
    # aurait laissé le chef de projet avec une coupe relevée sur un autre calage
    # (retour d'usage du 24/09/2026).
    #
    # La carte, elle, ne bouge plus : elle vivait ici avant la validation puis
    # descendait en section 3 bis pour les prises de vue, section retirée le
    # 26/09/2026. Elle reste donc en place, et passe en lecture seule.
    carte_de_la_coupe = (
        not (DOSSIER_SORTIE / _nom_dossier(commune) / NOM_GEOPACKAGE).exists()
        or _etat_de_l_import(import_be_courant) != st.session_state.get("etat_ecrit")
    )
    # La carte reste à l'écran dans les deux cas, et ne descend plus : avant la
    # validation pour régler la coupe, après pour vérifier le plan et sa légende.
    _carte_du_plan(import_be_courant, avec_la_coupe=carte_de_la_coupe)
    _retoucher_la_legende(import_be_courant.plan)
    return carte_de_la_coupe



#: L'indice affiché par la liste déroulante, pour cette exécution seulement.
#:
#: Il n'est pas encore celui de l'import : tant qu'on n'a pas recliqué sur
#: « Importer et contrôler », l'import en mémoire est celui de l'indice
#: précédent. Les confondre écrivait sa géométrie dans le dossier du nouvel
#: indice, en écrasant ce qui s'y trouvait — l'écrasement même que l'indice au
#: nom devait empêcher (relecture du 09/09/2026).
indice_choisi = None

if not commune.strip() and (fichier_dxf is not None or fichier_tableau is not None):
    st.error(
        "Saisissez la commune en section 1 avant d'importer : c'est elle qui "
        "nomme le dépôt et le dossier de sortie. Sans elle, les plans de tous "
        "les projets encore sans nom atterrissaient dans le même "
        "`projets/projet/`, et s'y écrasaient.",
        icon="🚫",
    )

# Ce qui bloque se dit ici, et non trois écrans plus bas. Un tableau bilan déposé
# sans le DXF ne faisait apparaître ni la liste des indices, ni le bouton
# d'import, ni la carte : la section restait vide et la page enchaînait sur
# « Validez l'import ci-dessus pour continuer », qui désigne un import qui
# n'existe pas et un écran où il n'y a rien à cliquer. Relevé le 15/09/2026 par
# le chef de projet, qui s'est trouvé sans rien à valider ni rien pour le dire.
_requis_manquants = [
    libelle
    for libelle, fichier in (
        ("le **plan BE (DXF)**", fichier_dxf),
        ("le **tableau bilan (.xlsx)**", fichier_tableau),
    )
    if fichier is None
]
if (
    plan_du_be
    and commune.strip()
    and _requis_manquants
    # Seulement une fois qu'un premier fichier est là : réclamer les deux à
    # l'ouverture de la section, alors que la liste des prérequis est encore à
    # l'écran, serait du bruit.
    and any(
        depose is not None
        for depose in (fichier_dxf, fichier_tableau)
    )
):
    st.warning(
        f"Il manque {' et '.join(_requis_manquants)} : le bouton "
        "« Importer et contrôler » n'apparaît qu'une fois les deux déposés. Ils "
        "sont obligatoires tous les deux et doivent porter le même indice — "
        "c'est leur recoupement qui engage les surfaces et les puissances "
        "déclarées.",
        icon="⚠️",
    )

if commune.strip() and fichier_dxf is not None and fichier_tableau is not None:
    chemin_dxf = _deposer(fichier_dxf, commune)
    chemin_tableau = _deposer(fichier_tableau, commune)

    try:
        indices = indices_disponibles(chemin_tableau)
        propose = indice_depuis_nom(fichier_dxf.name)

        st.markdown("**Indice de révision — à confirmer.**")
        if propose is None:
            st.warning(
                f"Le nom « {fichier_dxf.name} » ne porte pas d'indice de "
                "révision : choisissez-le à la main.",
                icon="⚠️",
            )
        elif propose not in indices:
            st.error(
                f"Le DXF annonce l'indice {propose}, absent du tableau bilan "
                f"(indices présents : {', '.join(indices)}). Le plan et le "
                "tableau ne sont probablement pas de la même version.",
                icon="🚫",
            )
        # Une proposition, pas encore une décision : c'est l'import qui
        # tranche, plus bas, et c'est lui qui nomme le dossier de sortie.
        indice = st.selectbox(
            "Colonne du tableau bilan à lire",
            indices,
            index=indices.index(propose) if propose in indices else len(indices) - 1,
            help="Le nom du DXF sert à proposer l'indice ; la confirmation reste "
            "obligatoire, un export peut être renommé.",
        )
        indice_choisi = indice

        # Hors de l'expander, et non dedans : Streamlit rend le spinner à
        # l'endroit de l'appel, et un spinner dans un panneau replié ne se voit
        # pas. Le plan de Sarnois demande 13 s de lecture — pendant lesquelles
        # rien ne bougeait à l'écran et le bouton « Importer et contrôler »
        # n'était pas encore apparu : « je me suis demandé si ça n'avait pas
        # planté » (retour d'usage du 19/09/2026).
        calques = _calques_caches(
            str(chemin_dxf), chemin_dxf.stat().st_size, empreinte_charte()
        )
        with st.expander("Correspondance des calques — modifiable", expanded=False):
            st.caption(
                "Proposée d'après la charte de nommage `UNI_` du BE, en ignorant "
                "accents, tirets, espaces et underscores. Un calque laissé sur "
                "« (ignorer) » n'est pas importé, et l'élément n'apparaîtra sur "
                "aucune planche."
            )
            choix = {}
            options = ["(ignorer)"] + list(CATEGORIES)

            # Trois blocs plutôt qu'une liste à plat. Le plan de Sarnois porte
            # 55 calques dont 12 appariés et une trentaine écartés d'office :
            # les aligner tous demandait de faire défiler le fond cadastral et
            # le mobilier de dessin pour trouver les huit qui comptent.
            apparies = [c for c in calques if c.categorie_proposee]
            a_decider = [
                c for c in calques if not c.categorie_proposee and not c.motif_ecart
            ]
            ecartes = [
                c for c in calques if not c.categorie_proposee and c.motif_ecart
            ]

            def _ligne_calque(calque, aide=""):
                colonne_nom, colonne_categorie = st.columns([2, 1])
                with colonne_nom:
                    detail = f"{calque.nb_entites} entité(s)"
                    if calque.nb_hatch:
                        detail += f", {calque.nb_hatch} remplissage(s) ignoré(s)"
                    if aide:
                        detail += f" — {aide}"
                    st.text_input(
                        "Calque",
                        value=f"{calque.nom} — {detail}",
                        disabled=True,
                        key=f"be_calque_{calque.nom}",
                        label_visibility="collapsed",
                    )
                with colonne_categorie:
                    defaut = calque.categorie_proposee or "(ignorer)"
                    retenu = st.selectbox(
                        "Catégorie",
                        options,
                        index=options.index(defaut),
                        key=f"be_categorie_{calque.nom}",
                        label_visibility="collapsed",
                    )
                if retenu != "(ignorer)":
                    choix[calque.nom] = retenu

            if apparies:
                st.markdown(f"**Appariés ({len(apparies)})**")
                for calque in apparies:
                    _ligne_calque(calque)
            if a_decider:
                st.markdown(
                    f"**À décider ({len(a_decider)})** — inconnus de la charte, "
                    "leur contenu n'est pas importé tant qu'ils restent sur "
                    "« (ignorer) »."
                )
                for calque in a_decider:
                    _ligne_calque(calque)
            if ecartes:
                with st.expander(
                    f"Écartés d'office ({len(ecartes)}) — repliés, appariables "
                    "quand même",
                    expanded=False,
                ):
                    for calque in ecartes:
                        _ligne_calque(calque, aide=calque.motif_ecart)
            st.session_state.correspondance_be = choix


        # Même raison qu'au plan PDF : la correspondance des calques change le
        # résultat, donc elle est dans la signature. Sans elle, apparier un
        # calque après coup laissait le bouton grisé et l'import inchangé.
        _source_be = (
            _empreinte(fichier_dxf),
            _empreinte(fichier_tableau),
            indice,
            tuple(sorted((st.session_state.correspondance_be or {}).items())),
        )
        if st.button(
            "Importer et contrôler",
            type="primary",
            width="stretch",
            disabled=_deja_fait("import_be_fait", _source_be),
            help=AIDE_DEJA_FAIT if _deja_fait("import_be_fait", _source_be) else None,
        ):
            _retenir_ce_qui_a_servi("import_be_fait", _source_be)
            st.session_state.coupe_be = None
            st.session_state.profil_be = None
            # Le plan change : les couches reprojetées de la carte ne valent
            # plus, et une carte qui garderait les anciennes serait pire que
            # lente — elle montrerait l'import précédent.
            st.session_state["couches_carte"] = None
            emprise_cadastrale = None
            # Le nom se compose ici avec l'indice qu'on est en train
            # d'importer : `_nom_dossier` porte encore celui de l'import
            # précédent, et le premier import n'en a aucun.
            nom_importe = identifiant_de_dossier(nom_de_projet(commune, indice))
            chemin_emprise = _enregistrer_fichiers(nom_importe, fichiers_emprise)
            if chemin_emprise is not None:
                emprise_cadastrale = charger_emprise(chemin_emprise).geometrie
            st.session_state["origine_coupe"] = None
            st.session_state.import_be = importer_be(
                chemin_dxf,
                chemin_tableau,
                indice,
                correspondance=st.session_state.correspondance_be or None,
                emprise_cadastrale=emprise_cadastrale,
                seuil_puissance_mwc=SEUIL_DP_MWC,
            )
            # Ce que l'import a lu, et non ce que la liste affiche : à partir
            # d'ici, c'est cet indice qui nomme le dossier.
            st.session_state["indice_tableau_bilan"] = (
                st.session_state.import_be.tableau.indice
            )
            st.session_state.emprise_cadastrale_be = emprise_cadastrale
            # Avant la reprise de coupe, et non après : c'est elle qui relit le
            # relevé altimétrique dans l'état de session. Écrits après, ils
            # n'arrivaient qu'au deuxième import, et le premier retombait sur le
            # RGE ALTI en silence — alors que l'aide du champ annonce l'inverse.
            _reprendre_import_precedent(
                DOSSIER_SORTIE / nom_importe,
                st.session_state.import_be,
                emprise_cadastrale,
            )
            _proposer_la_coupe(st.session_state.import_be)
            # Rejoué aussitôt : le bouton s'est rendu **avant** que ce bloc ne
            # tourne, donc encore actif, et il le serait resté à l'écran jusqu'au
            # prochain geste. La page se refait avec l'import en session, ce qui
            # la grise tout de suite — et ne recoûte rien, l'import étant fait.
            st.rerun()
    except ErreurDP as erreur:
        st.error(f"{type(erreur).__name__} : {erreur}")
    except Exception as erreur:
        _signaler_l_imprevu(erreur, "pendant l'import du plan")

if not plan_du_be and commune.strip():
    _importer_le_plan_pdf(
        commune,
        fichiers_emprise,
        fichier_export_helioscope,
        fichier_plan_pdf,
    )


import_be_courant = st.session_state.import_be
# Un import de l'autre source ne vaut pas pour celle-ci : l'afficher sous un
# titre qui n'est pas le sien laisserait croire qu'il vient de ces fichiers-là.
# Un plan PDF est le seul import sans tableau bilan.
if (
    import_be_courant is not None
    and (getattr(import_be_courant, "tableau", None) is None) == plan_du_be
):
    import_be_courant = None
# La commune conditionne tout ce qui suit : les contrôles s'affichent, mais la
# validation écrit, et sans commune elle n'a pas de dossier où écrire.
if import_be_courant is not None and commune.strip():
    tableau = getattr(import_be_courant, "tableau", None)
    if tableau is None:
        # Avant de lire le plan : les ouvrages tranchés et le calage réglé
        # changent ce que la carte doit montrer.
        _resumer_le_plan_pdf(import_be_courant)
        # Les réglages à gauche, la carte à droite, côte à côte. L'un sous
        # l'autre, il fallait défiler dans les deux sens pour juger de l'effet
        # d'un recalage ou d'une correction : la carte était d'abord sous les
        # alertes (23/09/2026), puis directement sous les réglages (24/09/2026),
        # et il restait un aller-retour (25/09/2026). Côte à côte, il n'y en a
        # plus. Le plan du BE, qui n'a ni calage ni choix à suivre, garde sa
        # carte plus bas, sur toute la largeur.
        colonne_reglages, colonne_carte = st.columns([1.0, 1.25], gap="medium")
        with colonne_reglages:
            _regler_et_trancher_le_plan_pdf(import_be_courant)
        with colonne_carte:
            carte_de_la_coupe = _montrer_la_coupe(import_be_courant)
    plan = import_be_courant.plan
    emprise_cloturee = plan.polygone_cloture

    if tableau is not None:
        engagement = st.expander("Ce sur quoi le dossier est engagé")
        colonnes = engagement.columns(4)
        colonnes[0].metric("Phase", tableau.generalites["phase"])
        colonnes[1].metric(
            "Date du tableau", tableau.generalites["date"].strftime("%d/%m/%Y")
        )
        colonnes[2].metric("Indice", tableau.indice)
        colonnes[3].metric(
            "Puissance", f"{tableau.modules['puissance_mwc']:.5f} MWc".replace(".", ",")
        )

    # Les bloquants d'abord, seuls, et rien d'autre au premier plan : ce sont
    # les seuls contrôles sur lesquels le chef de projet ait quelque chose à
    # faire — appeler le bureau d'études. Le tableau complet des recoupements
    # plan/tableau, lui, est une quinzaine de lignes qu'il ne peut pas corriger
    # et qui noyaient l'écran ; il reste consultable, replié.
    for controle in import_be_courant.bloquants:
        st.error(f"{controle.libelle} — {controle.message}", icon="🚫")
    # Réservé ici, rempli une fois la coupe traitée. `avertissements` compte
    # ceux de la ligne de coupe, du profil et des contrôles de terrain, qui ne
    # sont produits que deux cents lignes plus bas : les rendre à cet endroit du
    # script les montrait avec une exécution de retard, et le chef de projet qui
    # trace sa coupe puis valide dans la foulée ne les voyait jamais.
    emplacement_avertissements = st.container()

    with st.expander(
        f"Le détail des contrôles croisés ({len(import_be_courant.controles)} "
        + (
            "recoupements entre le plan et le tableau)"
            if tableau is not None
            else "recoupements entre le plan, le calepinage et le foncier)"
        )
    ):
        st.caption(
            "Ce que le plan porte, ce que le tableau déclare, et l'écart admis. "
            "Rien à corriger ici : un écart se traite avec le bureau d'études, "
            "sur ses fichiers."
            if tableau is not None
            else "Ce que le plan PDF et l'export HelioScope permettent de "
            "recouper, et ce qu'ils ne permettent pas : sans tableau bilan, "
            "aucune déclaration ne les confronte."
        )
        _tableau_controles(import_be_courant.controles)

    if tableau is not None:
        with st.expander("Paramètres extraits du tableau bilan"):
            for titre, valeurs in (
                ("Généralités", tableau.generalites),
                ("Structures", tableau.structures),
                ("Modules", tableau.modules),
                ("Postes et locaux", tableau.postes),
            ):
                st.markdown(f"**{titre}**")
                st.dataframe(
                    [
                        {"Paramètre": cle, "Valeur": str(valeur)}
                        for cle, valeur in valeurs.items()
                    ],
                    width="stretch",
                    hide_index=True,
                )
            if tableau.standards:
                st.markdown(
                    f"**Standards UNITe pour « {tableau.generalites['type_projet']} »** "
                    "— repère de vraisemblance, pas une contrainte."
                )
                st.dataframe(
                    [
                        {"Référence": cle, "Standard": str(valeur)}
                        for cle, valeur in tableau.standards.items()
                    ],
                    width="stretch",
                    hide_index=True,
                )
            if tableau.cotes:
                st.markdown(
                    "**Cotes normalisées** — pour la génération des DP 4 au lot 4."
                )
                st.dataframe(
                    [
                        {
                            "Ouvrage": cote.ouvrage,
                            "Dimensions": cote.dimensions,
                            "Ordre des cotes": cote.ordre_cotes,
                            "Surface (m²)": cote.surface_m2,
                            "Plateforme (m²)": cote.surface_plateforme_m2,
                        }
                        for cote in tableau.cotes
                    ],
                    width="stretch",
                    hide_index=True,
                )

    with emplacement_avertissements:
        au_be, a_lire, routine = _trier_les_avertissements(
            import_be_courant.avertissements
        )
        if au_be:
            st.error(
                f"**{len(au_be)} point(s) à demander au bureau d'études** avant "
                "que ce plan donne un dossier complet. Ce qui suit se recopie "
                "tel quel dans votre message.",
                icon="📋",
            )
            demandes = dict.fromkeys(_demande_au_be(m) for m in au_be)
            st.code("\n".join(f"- {d}" for d in demandes), language="text")
            with st.expander("Pourquoi ces demandes — le détail de chaque constat"):
                for message in au_be:
                    st.caption(f"· {message}")

        _trancher_les_voiries(import_be_courant)
        # Une fois l'import validé, ces remarques ont été lues : elles se
        # replient pour que la carte, qui vient après, ne soit plus à deux
        # écrans de défilement (retour d'usage du 17/09/2026). Elles restent
        # dépliées tant que l'import n'est pas validé — c'est le moment où
        # elles servent.
        deja_valide = (
            DOSSIER_SORTIE / _nom_dossier(commune) / NOM_GEOPACKAGE
        ).exists()
        if a_lire and deja_valide:
            with st.expander(f"Les remarques de l'import ({len(a_lire)})"):
                # Le titre du dépliant annonce déjà la liste : un bandeau de
                # plus, à l'intérieur, ne dirait rien qu'il ne dise.
                st.markdown(_en_puces(a_lire))
        else:
            _lister_les_avertissements(
                f"{len(a_lire)} remarque(s) sur l'import, à lire avant de "
                "valider",
                a_lire,
            )
        if routine:
            with st.expander(
                f"Ce que l'import a écarté, comme prévu ({len(routine)} message(s))"
            ):
                st.caption(
                    "Calques de travail du BE, fond cadastral remplacé par le "
                    "WFS IGN, annotations, cotations : rien de tout cela ne va "
                    "sur une planche. Ces messages disent ce qui a été laissé de "
                    "côté, et pourquoi — à lire si une catégorie manque au plan."
                )
                for message in routine:
                    st.caption(f"· {message}")

    coupe = st.session_state.coupe_be
    if tableau is not None:
        carte_de_la_coupe = _montrer_la_coupe(import_be_courant)

    st.markdown("### Validation")
    # La case est rendue **avant** la chaîne de refus, et non dans une de ses
    # branches : posée dans un `elif`, elle disparaissait dès qu'on la cochait —
    # la branche suivante prenait la main — et on ne pouvait plus la décocher.
    legende_relue = _legende_relue(import_be_courant.plan)
    if indice_choisi is not None and indice_choisi != tableau.indice:
        st.error(
            f"La liste affiche l'indice {indice_choisi}, l'import en mémoire "
            f"est celui de {tableau.indice}. Écrire maintenant donnerait au "
            f"dossier « {nom_de_projet(commune, indice_choisi)} » la géométrie "
            f"de {tableau.indice}, en écrasant ce qu'il contenait. Recliquez sur "
            "« Importer et contrôler ».",
            icon="🚫",
        )
    elif import_be_courant.bloquants:
        st.error(
            "Des contrôles croisés bloquants subsistent : corrigez les fichiers "
            "d'entrée. Les assouplir reviendrait à déposer un dossier faux.",
            icon="🚫",
        )
    elif getattr(import_be_courant, "decisions_manquantes", None):
        # Un plan PDF situe ses ouvrages sans les dimensionner : ce qu'il ne dit
        # pas se tranche plus haut, et l'écriture le refuserait de toute façon.
        st.warning(
            "Tranchez d'abord, plus haut, "
            f"{' et '.join(import_be_courant.decisions_manquantes)} : le plan "
            "ne les donne pas, et les supposer dessinerait un ouvrage faux de "
            "taille.",
            icon="⚠️",
        )
    elif coupe is None:
        st.info(
            "Placez la ligne de coupe avant de valider : le lot 4 en a besoin "
            "pour la coupe DP 3."
        )
    elif not legende_relue:
        # La légende part telle quelle sur DP 2 et sur les plans de repérage des
        # DP 4, et elle est dessinée **dans** la planche : une fois le dossier
        # produit, elle ne se retouche plus. La faire relire ici est le seul
        # moment où la corriger coûte un champ de texte plutôt qu'une
        # régénération (demande du 26/09/2026).
        st.info(
            "Relisez les intitulés de la légende ci-dessus, puis cochez la case "
            "pour débloquer la validation. Ils seront écrits tels quels sur les "
            "planches, et ne se retouchent pas dans le PowerPoint."
        )
    elif st.button(
        "Le plan est prêt, je valide",
        type="primary",
        width="stretch",
        disabled=_validation_deja_faite(import_be_courant),
        help=(
            AIDE_DEJA_FAIT
            if _validation_deja_faite(import_be_courant)
            else "Écrit le contrat que les planches liront, et fige la coupe A-A'."
        ),
    ):
        try:
            import_be_courant.ecrire(DOSSIER_SORTIE / _nom_dossier(commune))
        except ErreurDP as erreur:
            st.error(f"{type(erreur).__name__} : {erreur}")
        else:
            # Ce qui vient d'être écrit : la carte ne redescend que tant que
            # l'écran ne s'en écarte pas.
            st.session_state["etat_ecrit"] = _etat_de_l_import(import_be_courant)
            # Rejoué aussitôt : la carte change de place à la validation, et
            # sans cette relance la page finissait son exécution avec la carte
            # encore en haut, sous une annonce disant qu'elle était descendue.
            # L'annonce passe par la session, sinon la relance l'emporterait.
            st.session_state["annonce_validation"] = (
                "Import validé, coupe A-A' figée."
            )
            st.rerun()

    annonce = st.session_state.pop("annonce_validation", None)
    if annonce:
        st.success(annonce, icon="✅")


# ---------------------------------------------------------------------------
# Photographies et photomontages — DP 6, DP 7, DP 8
# ---------------------------------------------------------------------------

# Le contrat sur le disque, et non l'import en mémoire : c'est lui que la
# génération lira, et lui seul décide de ce que le dossier contiendra.
_dossier_contrat = DOSSIER_SORTIE / _nom_dossier(commune)
contrat_present = (_dossier_contrat / NOM_GEOPACKAGE).exists()
if contrat_present:
    # Hors du clic sur « Valider » : ce bloc y disparaissait à la première
    # réexécution du script, et le téléchargement du GeoPackage avec lui.
    with st.expander("Le contrat d'entrée écrit — pour vérification"):
        st.caption(
            "Ce que les planches DP 2, DP 3 et DP 4 dessineront : de quoi "
            "contrôler l'import dans un SIG, ou joindre à une question au bureau "
            "d'études. Pour le **transmettre** — au photomontage, par exemple — "
            "prenez plutôt l'archive complète proposée après la génération : "
            "elle porte aussi les paramètres du projet, que l'aperçu ci-dessous "
            "ne fait qu'extraire."
        )
        with open(_dossier_contrat / NOM_GEOPACKAGE, "rb") as fichier:
            st.download_button(
                "⬇️ Les géométries importées (GeoPackage)",
                data=fichier.read(),
                file_name=f"{_nom_dossier(commune)}_geometries.gpkg",
                mime="application/geopackage+sqlite3",
                on_click="ignore",
                width="stretch",
            )
        _parametres = _dossier_contrat / "projet.json"
        if _parametres.exists():
            st.code(
                json.dumps(
                    json.loads(_parametres.read_text(encoding="utf-8")),
                    ensure_ascii=False,
                    indent=2,
                )[:4000],
                language="json",
            )
            st.caption("Extrait : les 4 000 premiers caractères.")
# Le dossier réduit aux seules pièces DP 1 ne se demande plus ici : la case qui
# l'offrait a été retirée le 26/09/2026. Elle datait du lot 1, quand le plan du
# bureau d'études n'était pas encore importable ; elle n'a plus d'usage, et ce
# qu'elle annonçait — « les photographies et la génération viennent ensuite » —
# désignait des sections qui n'existent plus.
#
# La capacité, elle, reste dans `sortie_pptx.generer_pptx` : appelé sans contrat,
# il produit la page de garde et les pièces DP 1 en le disant au rapport. C'est
# l'interface qui n'y mène plus, pas l'outil qui ne sait plus le faire.
if not contrat_present:
    st.divider()
    st.info("**Validez l'import ci-dessus pour continuer.**", icon="⬆️")
    st.stop()

# Les sections « 3. Ajout de photographies et photomontages » et « 3 bis. La
# carte : placer et viser les prises de vue » ont été retirées le 26/09/2026.
#
# Le volet photographique se traite désormais hors de l'outil, dans le `.pptx`
# du lot 8 : cadres vides, plan de repérage déjà imprimé, repères de vue en
# formes libres à poser. Deux raisons, dans cet ordre. Le travail y est plus
# souple — les photographies se trient mieux sur un écran qu'au clic dans un
# formulaire, et les photomontages arrivent en retard. Et ces deux sections
# faisaient ramer l'application : une carte Leaflet, des vignettes décodées à
# chaque exécution et un composant de cadrage au clic, rejoués de haut en bas à
# la moindre interaction.
#
# Ce qui disparaît avec elles, et qu'il faut savoir : l'outil ne vérifie plus la
# position des cônes de vue contre l'EXIF des photographies. C'est le chef de
# projet qui les pose, « pas parfaitement mais largement suffisamment »
# (25/09/2026). Le rapport de génération le dit à chaque dossier.
#
# Rien n'est perdu côté socle : `dp_socle/points_de_vue.py`,
# `dp_socle/carte_photos.py` et les planches DP 6 à DP 8 du lot 6 restent en
# place, et c'est sur elles que le `.pptx` compose ses planches photographiques.

if fichier_notice is None and contrat_present:
    # Pas de refus : le dépôt est en phase de mise au point, et bloquer sur une
    # pièce manquante empêcherait d'éprouver le reste de la chaîne (décision du
    # 14/09/2026). Le dossier sort quand même, et il le dit — ici, et au
    # rapport de génération.
    st.warning(
        "Aucune notice DP 11 déposée : le dossier sera produit sans elle, et "
        "il sera **incomplet pour le dépôt**. L'outil ne l'exige pas encore.",
        icon="⚠️",
    )


st.divider()
st.subheader("3. Génération")

# L'indice vient de la section 2, qui s'exécute avant celle-ci : le nom est donc
# complet ici. La section 2 le compose de la même façon, par `_nom_dossier()`,
# et écrit donc bien dans le dossier que celle-ci va lire.
indice_retenu = st.session_state.get("indice_tableau_bilan")
libelle = nom_de_projet(commune, indice_retenu)
nom = _nom_dossier(commune) if commune.strip() else ""
if nom:
    st.markdown(f"Dossier à produire : **{libelle}**")
    if not indice_retenu:
        st.caption(
            "Le plan du bureau d'études n'a pas été importé : le nom ne porte "
            "pas encore d'indice, et un second indice du même projet écraserait "
            "ce dossier."
        )

#: Le type de chaque voirie, tranché en section 2 — au moment où l'alerte est
#: levée, et devant le croquis qui montre de quel objet il s'agit. Il se
#: demandait ici, à la toute fin : « on se demande un peu pourquoi cette
#: question arrive aussi tard » (retour d'usage du 17/09/2026).
voirie = st.session_state.get("voirie_tranchee")



def _construire_projet() -> Projet | None:
    if not commune.strip():
        st.error("La commune est obligatoire : c'est elle qui nomme le projet.")
        return None
    if not fichiers_emprise:
        # Sans ce message, le clic était absorbé sans rien produire : ni
        # planche, ni erreur, l'écran inchangé. `_enregistrer_fichiers` rendait
        # `None` sans un mot quand la liste était vide.
        st.error(
            "L'emprise cadastrale est obligatoire : c'est elle qui cadre "
            "toutes les planches. Déposez-la en section 1."
        )
        return None
    chemin_emprise = _enregistrer_fichiers(nom, fichiers_emprise)
    if chemin_emprise is None:
        return None

    chemin_notice = _enregistrer_notice(nom, fichier_notice)

    return Projet(
        nom=nom,
        commune=commune.strip(),
        code_postal=code_postal.strip(),
        date=date_projet.isoformat(),
        emprise=str(chemin_emprise),
        # Ni photomontage de couverture ni photographies : elles ne se déposent
        # plus dans l'outil. La page de garde garde son cadre annoncé
        # « Photomontage à insérer », qui devient une réservation d'image dans le
        # `.pptx` (`page_garde.zone_image`), et les pièces DP 6 à DP 8 y sortent
        # avec des cadres vides.
        libelle=libelle or None,
        voirie=voirie,
        notice=chemin_notice,
        # Les intitulés de légende que le chef de projet a corrigés en section 2,
        # s'il en a corrigé. Ils partent au plan de masse DP 2 et aux plans de
        # repérage des DP 4, où la légende est dessinée dans la planche.
        legendes=(
            _legendes_retouchees(import_be_courant.plan) or None
            if import_be_courant is not None
            else None
        ),
    )


# Un seul bouton, et une seule sortie : le `.pptx` à finaliser.
#
# Le bouton « Écrire projet.json » avait été retiré le premier : il n'écrivait que
# le fichier de métadonnées du lot 1 — que la génération écrit de toute façon
# avant de dessiner — et se confondait avec le `projet.json` du contrat d'entrée,
# qui est un autre fichier, dans un autre dossier.
#
# Le bouton du PDF assemblé a été retiré le 26/09/2026, avec les sections
# photographiques. Ce n'est pas un renoncement à la voie PDF, qui reste la sortie
# vérifiée de bout en bout et reste sous tests (`dp_socle.assemblage`) : c'est
# qu'elle ne peut plus être juste depuis ici. Sans dépôt de photographies, elle
# produirait un dossier amputé de DP 6, DP 7 et DP 8 — sept planches sur dix,
# d'apparence complète. Un dossier faux qui s'affiche correctement est ce que ce
# dépôt refuse avant tout.
#
# Ce que cela coûte, et que le rapport de génération redit à chaque dossier : les
# deux contrôles de la voie PDF ne s'appliquent plus, ni la vérification que
# chaque cartouche annonce la page où il tombe, ni celle du format 420 x 297 mm.
# Le chef de projet les tient à partir du téléchargement.
# Ce sur quoi la génération tourne. Le bouton se grise quand le dossier en
# session a été produit sur exactement ces entrées-là, et se rallume dès que
# l'une bouge — une légende récrite, une notice remplacée, un recalage. Un
# drapeau booléen aurait grisé le bouton même après un changement qui demandait
# justement de regénérer.
_entrees_generation = (
    nom,
    _empreinte(fichier_notice),
    tuple(sorted(
        (_legendes_retouchees(import_be_courant.plan) or {}).items()
    )) if import_be_courant is not None else (),
    str(voirie),
    st.session_state.get("etat_ecrit"),
)
_generation_faite = _deja_fait("generation_faite", _entrees_generation)
lancer_pptx = st.button(
    "Générer le dossier (à finaliser sur PowerPoint puis à exporter en PDF)",
    type="primary",
    width="stretch",
    disabled=_generation_faite,
    help=AIDE_DEJA_FAIT if _generation_faite else None,
)

if lancer_pptx:
    try:
        projet = _construire_projet()
        if projet is not None:
            projet.valider()
            projet.ecrire(DOSSIER_PROJETS / projet.nom / "projet.json")
            with st.spinner(
                "Téléchargement des fonds IGN, composition des planches et "
                "montage des diapos…"
            ):
                rapport_pptx = generer_pptx(projet, DOSSIER_SORTIE, dpi=DPI_DEFAUT)
            _retenir_ce_qui_a_servi("generation_faite", _entrees_generation)
            st.session_state["pptx_genere"] = {
                "nom": projet.nom,
                "libelle": projet.libelle_affiche,
                "rapport": rapport_pptx,
            }
            # Rejoué, comme les imports : le bouton s'était rendu avant la
            # génération et serait resté actif sous le compte rendu du dossier
            # qu'il venait de produire. Les téléchargements, eux, ne rejouent
            # pas le script — le bouton serait donc resté allumé longtemps.
            st.rerun()
    except ErreurDP as erreur:
        st.session_state.pop("pptx_genere", None)
        st.error(f"{type(erreur).__name__} : {erreur}")
    except Exception as erreur:
        st.session_state.pop("pptx_genere", None)
        _signaler_l_imprevu(erreur, "pendant la génération du dossier")


# Le compte rendu de la sortie PowerPoint, au même régime que celui du PDF : il
# survit au rejeu que provoque chaque téléchargement, et il disparaît si le projet
# affiché change.
_genere_pptx = st.session_state.get("pptx_genere")
if _genere_pptx is not None and _genere_pptx["nom"] == nom:
    rapport_pptx = _genere_pptx["rapport"]
    st.divider()
    st.success(
        f"**{_genere_pptx['libelle']}** — {len(rapport_pptx.diapos)} diapos, "
        f"{rapport_pptx.taille_mo:.1f} Mo. Les planches y sont dessinées, les "
        "photographies restent à poser."
    )
    # Un seul téléchargement depuis le 28/09/2026. Le `.pptx` seul et le contrat
    # seul étaient offerts à côté du groupé : trois boutons pour un geste, et
    # l'un d'eux — le plus évident, le dossier — laissait le contrat derrière.
    # Ce que l'oubli coûte : le serveur ne garde rien, et le contrat perdu se
    # repaie par une génération entière.
    #
    # Ce que la fusion coûte en retour, et qu'elle assume : il faut dézipper
    # pour ouvrir le `.pptx`. Un clic de plus à chaque dossier contre une
    # régénération complète de temps en temps.
    _horodatage = rapport_pptx.produit_le.strftime(FORMAT_HORODATAGE)
    _contrat_emporte = archiver_le_contrat(
        rapport_pptx.dossier, _genere_pptx["nom"]
    )
    _pptx = rapport_pptx.fichier.read_bytes()
    _nom_pptx = nom_telechargement(_genere_pptx["nom"], rapport_pptx.produit_le)

    if _contrat_emporte is not None:
        st.download_button(
            f"⬇️ Télécharger le dossier et son contrat "
            f"({(len(_pptx) + len(_contrat_emporte)) / (1024 * 1024):.1f} Mo, ZIP)",
            data=_tout_en_une_archive(_pptx, _nom_pptx, _contrat_emporte),
            file_name=MOTIF_TOUT.format(
                nom=_genere_pptx["nom"], horodatage=_horodatage
            ),
            mime="application/zip",
            type="primary",
            help=(
                "L'archive porte le `.pptx` et, à côté de lui, le contrat du "
                "dossier. Dans le PowerPoint : déposez vos photographies dans "
                "les cadres vides, déplacez et orientez les repères de vue, "
                "puis supprimez les diapos surnuméraires et leurs bandeaux "
                "rouges avant d'exporter en PDF. Le contrat, lui, est à "
                "transmettre pour faire monter les photomontages — c'est la "
                "géométrie exacte de ce dossier-ci."
            ),
            on_click="ignore",
            width="stretch",
        )
        st.caption(
            "Le dossier et le contrat descendent ensemble : le serveur ne garde "
            "rien, et ce qui n'est pas emporté maintenant se repaie par une "
            "génération entière."
        )
    else:
        # Sans contrat, il n'y a rien à grouper — mais le dire, plutôt que de
        # laisser croire que le dossier descend complet.
        st.warning(
            "**Aucun contrat à joindre au dossier.** Le `.pptx` descend seul : "
            "les photomontages ne pourront pas être montés sur la géométrie de "
            "ce dossier sans lui.",
            icon="⚠️",
        )
        st.download_button(
            f"⬇️ Télécharger le dossier seul ({rapport_pptx.taille_mo:.1f} Mo, .pptx)",
            data=_pptx,
            file_name=_nom_pptx,
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
            type="primary",
            on_click="ignore",
            width="stretch",
        )

    _lister_les_avertissements(
        f"{len(rapport_pptx.avertissements)} point(s) à savoir avant de "
        "finaliser le dossier",
        rapport_pptx.avertissements,
    )

    st.dataframe(
        [
            {
                "Diapo": rang,
                "Pièce": diapo.code or "—",
                "Planche": diapo.libelle,
                "Page": diapo.numero,
                "Cadres": diapo.cadres,
                "Rendu": diapo.voie,
                "Mo": round(diapo.octets / 1e6, 2),
            }
            for rang, diapo in enumerate(rapport_pptx.diapos, start=1)
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption(
        "Une même page portée par plusieurs diapos est un choix à faire : gardez "
        "celle qui convient et supprimez les autres, la pagination du sommaire "
        "est calculée pour cela."
    )
