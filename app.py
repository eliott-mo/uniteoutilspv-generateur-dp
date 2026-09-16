"""Interface minimale de saisie et de génération du dossier DP (lot 1 — socle).

Le formulaire écrit `projet.json`, qui reste le format pivot : une correction de
dernière minute se fait en modifiant ce fichier et en relançant la génération.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date as _date
from dataclasses import dataclass
from pathlib import Path

import folium
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from dp_socle.environnement import dossiers_de_travail, etat_cairo, etat_travail, preparer_cairo

preparer_cairo()

# Le lot 2 (HelioScope) et le lot 2bis (plan BE) ont chacun leur aperçu, avec
# les mêmes noms de fonctions : ceux du lot 2bis sont renommés ici, plutôt que
# dans leur module, pour ne pas toucher au lot 2.
from dp_socle.planches.reperage_vues import OUVERTURE_CONE_DEG
from dp_socle.carte_photos import depuis_carte, image_de, lire_carte
from dp_socle.lecture_exif import etat_heic, lire_metadonnees
from dp_socle.points_de_vue import (
    ORIGINE_CARTE,
    ORIGINE_EXIF,
    ORIGINE_MAIN,
    SEUIL_PRECISION_M,
    cap_vers,
    vers_l93,
)
from dp_socle.apercu_be import (
    en_wgs84_point,
    ORDRE_DESSIN,
    STYLES,
    URL_TUILES_ORTHO,
    apercu_au_survol,
    bornes_wgs84,
    clic_l93,
    en_wgs84,
    legende_presente,
    trace_l93,
)
from dp_socle.assemblage import generer_dossier
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
from dp_socle.contrat import NOM_GEOPACKAGE, VOIRIES_ADMISES, decrire_voiries
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
from dp_socle.ign import COUCHE_ORTHO, COUCHE_PLAN, DPI_DEFAUT, verifier_couches
from dp_socle.polices import etat_polices
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

st.set_page_config(page_title="Générateur de dossier DP", page_icon="📄", layout="wide")
st.title("Générateur de dossier DP")
st.caption(
    "Page de garde, DP 1-1 plan de situation, DP 1-2 photographie aérienne, "
    "DP 1-3 plan de cadastre. Fonds IGN Géoplateforme, Lambert 93, A3 paysage à "
    "l'échelle vraie."
)

# Les quatre sections n'apparaissent qu'au fur et à mesure : rassembler les
# fichiers d'abord évite de découvrir en cours de route qu'il en manque un, et
# de repartir avec un dossier incomplet.
st.info(
    """**À rassembler avant de commencer.**

**Obligatoire pour tout dossier**
- **Emprise cadastrale** — le shapefile du géomètre : `.shp` + `.shx` + `.dbf`
  + `.prj`, ou le ZIP qui les contient. Le `.prj` en fait partie : sans lui, le
  système de coordonnées est inconnu et la génération est refusée.

**Obligatoire pour les planches DP 2, DP 3 et DP 4** — plan de masse, coupes et
ouvrages techniques, c'est-à-dire l'essentiel du dossier
- **Plan du bureau d'études** — le DXF exporté d'AutoCAD, géoréférencé en
  Lambert 93.
- **Tableau bilan** — le `.xlsx` du bureau d'études, **au même indice que le
  plan**. C'est lui qui engage les surfaces et les puissances déclarées.

**Attendu de tout dossier déposable**
- **Notice DP 11** — le PDF que vous avez rédigé. L'outil ne l'écrit pas : il
  l'habille du cadre et du cartouche du dossier, et la pagine avec les autres
  pièces. Il ne l'exige pas encore — le dossier sort sans elle et le rapport le
  signale — mais un dossier déposé sans notice est incomplet.

**Facultatif**
- **Relevé altimétrique** — `.txt` ou `.csv`, trois colonnes « X Y Z » en
  Lambert 93. Il remplace le RGE ALTI, plus précis qu'un relevé national.
- **Plan du BE en PDF** — pour comparer l'aperçu à ce que le BE a dessiné.
- **Photographies** — DP 6 insertion paysagère (en JPG ou PNG si elle doit
  monter en page de garde), DP 7 environnement proche, DP 8 paysage lointain.
""",
    icon="🗂️",
)


@st.cache_resource
def _etat_cairo():
    return etat_cairo()


@st.cache_resource
def _etat_polices():
    return etat_polices()


@st.cache_resource
def _etat_heic():
    return etat_heic()


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

# Le HEIC est le format par défaut des iPhone : une photographie de visite en
# est un sans que le chef de projet le sache. Son absence se dit ici, et non au
# dépôt — la règle du dépôt veut qu'une erreur d'environnement se signale avant
# de travailler, et désigne sa vraie cause.
heic = _etat_heic()
if not heic.disponible:
    st.warning(f"Photos HEIC : {heic.message}", icon="⚠️")

# Un dossier de travail synchronisé se dit au démarrage, comme l'état de cairo :
# ce qui gêne doit se savoir avant de travailler.
travail = _etat_travail()
if travail.synchronise:
    st.warning(travail.message, icon="⚠️")

etat = _etat_polices()
if etat.disponible:
    st.caption(f"✅ {etat.message}")
else:
    st.warning(f"Police : {etat.message}", icon="⚠️")

with st.sidebar:
    st.header("Contrôles")
    st.write("Couches Géoplateforme câblées :")
    st.code(f"{COUCHE_PLAN}\n{COUCHE_ORTHO}", language="text")
    if st.button("Vérifier via GetCapabilities", width="stretch"):
        try:
            resultat = verifier_couches()
        except ErreurDP as erreur:
            st.error(str(erreur))
        else:
            for couche, presente in resultat.items():
                (st.success if presente else st.error)(
                    f"{couche} : {'présente' if presente else 'ABSENTE'}"
                )
    st.divider()
    dpi = st.number_input(
        "DPI des fonds raster", min_value=100, max_value=400, value=DPI_DEFAUT, step=25,
        help="200 dpi en A3 donne 3228 x 2110 px sur la zone de dessin. "
        "250 dpi améliore peu à l'impression et alourdit le dossier de moitié.",
    )


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


def _archive_du_dossier(rapport) -> bytes:
    """Le dossier complet en une archive ZIP, prête à être téléchargée.

    Le chef de projet travaille sur une application distante : le dossier
    `sortie/` vit sur le serveur et lui reste inaccessible. Lui annoncer un
    chemin qu'il ne peut pas ouvrir ne servait à rien, et neuf boutons de
    téléchargement — un par planche — chargeaient neuf PDF en mémoire pour lui
    faire faire neuf clics.

    L'archive porte le PDF assemblé et les planches séparées, à plat. Les PDF
    sont déjà compressés : `ZIP_STORED` évite de les recompresser pour rien,
    et l'archive pèse donc le poids du dossier.
    """
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.write(rapport.assemblage, arcname=rapport.assemblage.name)
        for sortie in rapport.planches:
            chemin = Path(sortie.chemin)
            archive.write(chemin, arcname=f"planches/{chemin.name}")
    return tampon.getvalue()


def _empreinte(fichier) -> tuple:
    """Ce qui distingue ce dépôt d'un autre, sans relire les octets.

    `file_id` est attribué par Streamlit à chaque fichier reçu : il change dès
    que le chef de projet en dépose un autre, même sous le même nom. La taille
    l'accompagne comme garde-fou, pour les versions qui n'en donneraient pas.
    """
    return (getattr(fichier, "file_id", None), getattr(fichier, "size", None))


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


def _enregistrer_photos(nom_projet: str, par_piece: dict, retenu) -> str | None:
    """Écrit les photographies du projet, une pièce par sous-dossier.

    Rend le chemin de l'insertion paysagère retenue pour la page de garde. Les
    autres sont conservées telles quelles : elles constituent les pièces DP 6 à
    DP 8, jointes au dossier à la main pour l'instant.

    La couverture se reconnaît à l'**objet** déposé, et non à son nom. Comparer
    les noms, sur les trois pièces à la fois, suffisait à ce qu'une photo de
    DP 7 ou DP 8 appelée comme l'insertion retenue prenne sa place en page de
    garde — le dossier partait alors avec une photo de l'existant en couverture
    au lieu du projet fini (relecture du 09/09/2026).
    """
    couverture = None
    for code, fichiers in (par_piece or {}).items():
        if not fichiers:
            continue
        dossier = DOSSIER_PROJETS / nom_projet / code.replace(" ", "_")
        dossier.mkdir(parents=True, exist_ok=True)
        for fichier in fichiers:
            cible = dossier / Path(fichier.name).name
            _ecrire_depose(cible, fichier.getbuffer())
            if fichier is retenu:
                couverture = cible
    return str(couverture) if couverture else None


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


st.subheader("1. Métadonnées du projet")
colonne_gauche, colonne_droite = st.columns(2)
with colonne_gauche:
    commune = st.text_input("Commune", value="Bray-Saint-Aignan")
with colonne_droite:
    code_postal = st.text_input("Code postal", value="45460")

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
CATEGORIES_HORS_CARTE = ("modules_pv",)


def _teinte(composantes) -> str:
    """Couleur CSS d'un triplet RVB de la palette DP."""
    rouge, vert, bleu = composantes
    return f"#{rouge:02x}{vert:02x}{bleu:02x}"


def _style_carte(style) -> dict:
    """Style Leaflet d'une catégorie, aux couleurs de la légende DP.

    Les mêmes teintes que la planche produite : ce que le chef de projet voit
    ici est ce qu'il retrouvera sur DP 2, à l'opacité près.
    """
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
st.subheader("2. Plan du bureau d'études")
st.caption(
    "Import du DXF et du tableau bilan fournis par le BE, recoupement des deux, "
    "tracé de la ligne de coupe A-A' et profil du terrain. Produit "
    "`geometries.gpkg` et `projet.json` pour le dessin des planches ; ne dessine "
    "aucune planche."
)

for cle, defaut in (
    ("import_be", None),
    ("coupe_be", None),
    ("profil_be", None),
    ("correspondance_be", None),
):
    if cle not in st.session_state:
        st.session_state[cle] = defaut


colonne_dxf, colonne_tableau = st.columns(2)
with colonne_dxf:
    fichier_dxf = st.file_uploader(
        "Plan BE (DXF géoréférencé en Lambert 93)",
        type=["dxf"],
        help="L'unité est déduite des coordonnées, jamais de l'en-tête $INSUNITS "
        "— sur les fichiers du BE il annonce des millimètres alors que le plan "
        "est en mètres. Un plan hors des bornes du Lambert 93 est refusé.",
    )
with colonne_tableau:
    fichier_tableau = st.file_uploader(
        "Tableau bilan (.xlsx)",
        type=["xlsx"],
        help="Onglets lus : « 2. Caractéristiques du projet », « Dimensions "
        "postes et pieux », « Standards UNITe ».",
    )

colonne_pdf, colonne_alti = st.columns(2)
with colonne_pdf:
    fichier_pdf_be = st.file_uploader(
        "Plan BE en PDF (facultatif)",
        type=["pdf"],
        help="Sert uniquement de référence visuelle pour comparer l'aperçu à ce "
        "que le BE a dessiné. Aucune donnée n'en est extraite.",
    )
with colonne_alti:
    fichier_altimetrie = st.file_uploader(
        "Relevé altimétrique (.txt, facultatif)",
        type=["txt", "csv"],
        help="Repli quand le RGE ALTI est indisponible, ou relevé drone plus "
        "précis. **Trois colonnes « X Y Z » en Lambert 93**, et elles seules : "
        "la forme à deux colonnes a été retirée le 03/09/2026, rien n'y "
        "distinguant une abscisse d'un matricule. Ce fichier prend le pas sur "
        "l'appel automatique.",
    )



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


@st.cache_data(show_spinner="Lecture des calques du DXF…")
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
GESTES_CARTE = {
    "translation_coupe": (
        "Déplacer la coupe",
        "**Cliquez sur la carte** à l'endroit où la coupe doit passer. Le trait "
        "pointillé qui suit votre souris montre où elle se posera — elle reste "
        "perpendiculaire aux rangées, vous choisissez sa position et jamais sa "
        "direction.",
    ),
    "placer_vue": (
        "📍 Placer",
        "📍 **Cliquez sur la carte** à l'emplacement réel de « {nom} ».",
    ),
    "viser_vue": (
        "🎯 Viser",
        "🎯 **Cliquez sur la carte** vers ce que regarde « {nom} ». La direction "
        "s'en déduit, et c'est elle qui fera dessiner le cône.",
    ),
}


def _armer_geste(geste: str) -> None:
    """Arme un geste : le prochain clic sur la carte lui sera destiné."""
    st.session_state["geste_carte"] = geste


def _desarmer_geste() -> None:
    st.session_state["geste_carte"] = None


def _geste_arme() -> str | None:
    return st.session_state.get("geste_carte")


def _vues_photo() -> dict:
    """Les prises de vue en cours de saisie, par pièce puis par nom de fichier.

    En session et non dans les widgets : un point placé doit survivre au
    redéploiement de la page, et le nom du fichier est le seul identifiant qui
    traverse les exécutions — l'objet déposé, lui, est reconstruit à chaque fois.
    """
    return st.session_state.setdefault("vues_photo", {})


def _vue_photo(code: str, nom: str) -> dict:
    return _vues_photo().setdefault(code, {}).setdefault(nom, {})


def _cible_du_geste() -> tuple:
    """(code de pièce, nom de fichier) que le geste armé concerne."""
    return st.session_state.get("cible_vue") or (None, None)


def _armer_sur_photo(geste: str, code: str, nom: str) -> None:
    st.session_state["cible_vue"] = (code, nom)
    _armer_geste(geste)


def _bandeau_geste(geste: str) -> str:
    """Le texte de la bannière, complété du nom de la photographie visée."""
    return GESTES_CARTE[geste][1].format(nom=_cible_du_geste()[1] or "")


#: Portée du cône sur la carte de saisie, en mètres. Sur la planche le symbole a
#: une taille en millimètres ; ici la carte se zoome librement, et une taille
#: terrain est le seul repère stable.
RAYON_VISEE_CARTE_M = 60.0
TEINTE_VISEE = "#d81b8c"


def _secteur_de_visee(x: float, y: float, cap_deg: float):
    """Le cône de visée en Lambert 93, à une taille lisible sur la carte."""
    from math import cos, radians, sin

    from shapely.geometry import Polygon

    axe = (90.0 - cap_deg) % 360.0
    demi = OUVERTURE_CONE_DEG / 2.0
    sommets = [(x, y)]
    pas = int(OUVERTURE_CONE_DEG)
    for i in range(pas + 1):
        angle = radians(axe - demi + OUVERTURE_CONE_DEG * i / pas)
        sommets.append(
            (x + RAYON_VISEE_CARTE_M * cos(angle), y + RAYON_VISEE_CARTE_M * sin(angle))
        )
    return Polygon(sommets)


def _poser_prise_sur_la_carte(carte, code: str, nom: str, vue: dict) -> None:
    """Marqueur d'une prise de vue placée, et son cône si la direction est sûre.

    Le cône est un secteur de 50°, comme sur la planche et comme sur les
    marqueurs de `photos-geoloc` : le chef de projet doit reconnaître d'un coup
    d'œil ce qu'il retrouvera sur le dossier.
    """
    from shapely.geometry import Point, Polygon

    lat, lon = en_wgs84_point(vue["x"], vue["y"])
    cap = vue.get("cap_deg")
    if cap is not None and vue.get("cap_confirme"):
        folium.GeoJson(
            en_wgs84([_secteur_de_visee(vue["x"], vue["y"], cap)]),
            style_function=lambda _t: {
                "color": TEINTE_VISEE, "weight": 1, "fillColor": TEINTE_VISEE,
                "fillOpacity": 0.55,
            },
            name=f"{code} — {nom}",
        ).add_to(carte)
    folium.CircleMarker(
        location=(lat, lon), radius=5, color="#1a1a1a", weight=2,
        fill=True, fillColor="#ffffff", fillOpacity=1.0,
        tooltip=f"{code} — {nom}",
    ).add_to(carte)


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
            coupe, fichier_altimetrie=st.session_state.get("chemin_altimetrie_be")
        )
    import_be.profil = st.session_state.profil_be
    import_be.coherence = controler_coherence(
        st.session_state.profil_be, coupe, plan.tables
    )
    import_be.terrain_be = controler_terrain_embarque(
        st.session_state.profil_be, coupe, plan.points_terrain, CALQUES_TERRAIN
    )


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
                coupe, fichier_altimetrie=st.session_state.get("chemin_altimetrie_be")
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
    st.session_state.manuel_be = enregistree.manuel
    import_be.ligne_coupe = coupe

    if profil_reutilisable and enregistree.profil is not None:
        st.session_state.profil_be = enregistree.profil
    else:
        with st.spinner("Relevé du profil du terrain…"):
            st.session_state.profil_be = profil_terrain(
                coupe, fichier_altimetrie=st.session_state.get("chemin_altimetrie_be")
            )
    import_be.profil = st.session_state.profil_be
    import_be.coherence = controler_coherence(
        st.session_state.profil_be, coupe, plan.tables
    )
    import_be.terrain_be = controler_terrain_embarque(
        st.session_state.profil_be, coupe, plan.points_terrain, CALQUES_TERRAIN
    )

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
    commune.strip()
    and _requis_manquants
    # Seulement une fois qu'un premier fichier est là : réclamer les deux à
    # l'ouverture de la section, alors que la liste des prérequis est encore à
    # l'écran, serait du bruit.
    and any(
        depose is not None
        for depose in (
            fichier_dxf,
            fichier_tableau,
            fichier_pdf_be,
            fichier_altimetrie,
        )
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
    chemin_pdf_be = _deposer(fichier_pdf_be, commune)
    chemin_altimetrie = _deposer(fichier_altimetrie, commune)

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

        with st.expander("Correspondance des calques — modifiable", expanded=False):
            st.caption(
                "Proposée d'après la charte de nommage `UNI_` du BE, en ignorant "
                "accents, tirets, espaces et underscores. Un calque laissé sur "
                "« (ignorer) » n'est pas importé, et l'élément n'apparaîtra sur "
                "aucune planche."
            )
            calques = _calques_caches(
                str(chemin_dxf), chemin_dxf.stat().st_size, empreinte_charte()
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


        if st.button("Importer et contrôler", type="primary", width="stretch"):
            st.session_state.coupe_be = None
            st.session_state.profil_be = None
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
            st.session_state.chemin_pdf_be = (
                str(chemin_pdf_be) if chemin_pdf_be else None
            )
            st.session_state.chemin_altimetrie_be = (
                str(chemin_altimetrie) if chemin_altimetrie else None
            )
            _reprendre_import_precedent(
                DOSSIER_SORTIE / nom_importe,
                st.session_state.import_be,
                emprise_cadastrale,
            )
            _proposer_la_coupe(st.session_state.import_be)
    except ErreurDP as erreur:
        st.error(f"{type(erreur).__name__} : {erreur}")


import_be_courant = st.session_state.import_be
# La commune conditionne tout ce qui suit : les contrôles s'affichent, mais la
# validation écrit, et sans commune elle n'a pas de dossier où écrire.
#: Rempli par la section 2 quand la carte existe, lu par la section 3. À `None`,
#: il n'y a pas de plan du bureau d'études — donc pas de carte, pas d'emprise
#: clôturée, et pas de pièce photographique qui ait un sens.
emplacement_prises_de_vue = None

if import_be_courant is not None and commune.strip():
    plan = import_be_courant.plan
    tableau = import_be_courant.tableau
    emprise_cloturee = plan.polygone_cloture

    st.markdown("### Ce sur quoi le dossier est engagé")
    colonnes = st.columns(4)
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
        "recoupements entre le plan et le tableau)"
    ):
        st.caption(
            "Ce que le plan porte, ce que le tableau déclare, et l'écart admis. "
            "Rien à corriger ici : un écart se traite avec le bureau d'études, "
            "sur ses fichiers."
        )
        _tableau_controles(import_be_courant.controles)

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
            st.markdown("**Cotes normalisées** — pour la génération des DP 4 au lot 4.")
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

    if st.session_state.get("chemin_pdf_be"):
        with open(st.session_state["chemin_pdf_be"], "rb") as fichier:
            st.download_button(
                "Ouvrir le plan PDF du BE pour comparaison visuelle",
                data=fichier.read(),
                file_name=Path(st.session_state["chemin_pdf_be"]).name,
                mime="application/pdf",
                width="stretch",
            )

    # -----------------------------------------------------------------------
    # Le plan importé, et la coupe qui se pose dessus
    # -----------------------------------------------------------------------
    #
    # Une seule carte, et non un aperçu statique suivi d'une carte à tracer :
    # les deux montraient presque la même chose, et le chef de projet plaçait sa
    # coupe sur des tables et une clôture sans voir ce qu'elle allait couper. Il
    # procédait par essai-erreur — tracer, corriger, descendre lire l'aperçu,
    # remonter. Ici il la pose sur le plan lui-même, aux couleurs de la planche.
    st.markdown("### Le plan importé, et la ligne de coupe A-A'")
    st.caption(
        "**Une coupe est déjà proposée** : elle est perpendiculaire aux rangées "
        "et posée là où elle traverse le plus de tables. Si elle vous convient, "
        "il n'y a rien à faire.\n\n"
        "Pour la déplacer, cliquez sur **« Déplacer la coupe »** puis sur la "
        "carte : elle glissera pour passer par ce point, en gardant la direction "
        "imposée par les rangées (azimut des tables mesuré à "
        f"{plan.azimut_tables_deg:.2f}° depuis l'est, plus 90°) et son étendue à "
        "toute l'emprise clôturée avec 10 m de marge."
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
    if _geste_arme() in ("placer_vue", "viser_vue"):
        # La bannière des prises de vue s'affiche ici, au-dessus de la carte, et
        # non près du bouton qui l'a armée : c'est la carte qui attend le clic,
        # et le bouton vit plus bas, dans la section des pièces fournies.
        st.info(_bandeau_geste(_geste_arme()), icon="🖱️")
        if st.button("Annuler", key="annuler_geste_vue"):
            _desarmer_geste()
            st.rerun()
    elif _geste_arme() == "translation_coupe":
        st.info(GESTES_CARTE["translation_coupe"][1], icon="🖱️")
        if st.button("Annuler le déplacement", key="annuler_translation_coupe"):
            _desarmer_geste()
            st.rerun()
    elif st.button(
        GESTES_CARTE["translation_coupe"][0],
        key="armer_translation_coupe",
        width="stretch",
    ):
        _armer_geste("translation_coupe")
        st.rerun()

    with st.expander("Tracer la coupe à la main (contournement)"):
        st.caption(
            "L'outil polyligne, à gauche de la carte, reste disponible. En "
            "automatique il ne sert qu'à demander une coupe : sa position est "
            "recalculée sur le nombre de rangées traversées, et le tracé n'est "
            "pas conservé. Cochez la case pour qu'il soit pris tel quel, "
            "direction comprise."
        )
        manuel = st.checkbox(
            "Conserver la direction tracée (contournement)",
            value=False,
            key="manuel_be",
            help="À n'utiliser que si la perpendiculaire aux rangées ne convient "
            "pas. Une coupe oblique allonge toutes les distances qu'on y lit.",
        )

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

    # Dans l'ordre de la planche : ce qui se recouvre se recouvre pareil ici.
    for categorie in ORDRE_DESSIN:
        if categorie in CATEGORIES_HORS_CARTE:
            continue
        style = STYLES.get(categorie)
        if style is None:
            continue
        collection = en_wgs84(plan.geometries(categorie))
        if not collection["features"]:
            continue
        folium.GeoJson(
            collection,
            style_function=lambda _trait, style=style: _style_carte(style),
            name=style.libelle,
        ).add_to(carte)

    # La coupe retenue, et elle seule. Le tracé d'origine était montré à côté,
    # en orange : le chef de projet qui traçait volontairement de travers voyait
    # son trait oblique persister et croyait que rien n'avait été redressé.
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

    # Les prises de vue déjà placées, pour que le chef de projet voie ce qu'il a
    # posé — et les corrige au besoin. Même symbole que sur la planche : un
    # repère, et un cône seulement quand la direction est confirmée.
    for code_piece, par_nom in _vues_photo().items():
        for nom_photo, vue in par_nom.items():
            if vue.get("x") is None:
                continue
            _poser_prise_sur_la_carte(carte, code_piece, nom_photo, vue)

    sud, ouest, nord, est = bornes_wgs84(emprise_cloturee)
    carte.fit_bounds([[sud, ouest], [nord, est]])
    Draw(
        export=False,
        draw_options={
            "polyline": {"shapeOptions": {"color": "#ff8c00", "weight": 4}},
            "polygon": False,
            "rectangle": False,
            "circle": False,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": False, "remove": True},
    ).add_to(carte)

    # La clé porte un compteur : elle change à chaque coupe retenue, ce qui
    # remonte la carte à neuf. Sans cela le trait tracé par le chef de projet
    # restait affiché par Leaflet, par-dessus la coupe redressée, et le bouton
    # « Corriger » se represéntait indéfiniment.
    resultat_carte = st_folium(
        carte,
        width=None,
        height=560,
        key=f"carte_coupe_be_{st.session_state.get('tour_carte', 0)}",
        # Les trois seules valeurs que cet écran lise. Sans cette restriction le
        # composant renvoyait aussi le cadrage et le niveau de zoom, et déplacer
        # la carte ou zoomer relançait le script. Mesuré le 15/09/2026 dans son
        # bundle : la charge est filtrée sur cette liste, puis comparée à la
        # précédente, et `setComponentValue` n'est appelé que si elle a changé.
        returned_objects=["last_clicked", "all_drawings", "last_active_drawing"],
    )
    trace = trace_l93(resultat_carte)
    clic = _clic_neuf(resultat_carte)

    st.caption(
        "Couleurs de la légende DP, relevées sur la planche DP 2 du dossier de "
        "référence HOCH « Les Islettes » : "
        + " · ".join(
            f"{style.libelle} ({nombre})"
            for _, style, nombre in legende_presente(plan)
        )
        + ". Jaune : emprise cadastrale. Noir : coupe A-A' retenue. Les modules "
        "ne sont pas dessinés ici — la silhouette des rangées dit la même chose "
        "et un plan en compte des milliers. Les couleurs du DXF ne sont pas "
        "reprises, les codes ACI y sont des couleurs de travail."
    )

    # Réservé ici, rempli par la section 3 : les photographies se déposent plus
    # bas, mais c'est sur cette carte qu'elles se placent. Un aller-retour au
    # lieu d'un par photographie.
    emplacement_prises_de_vue = st.container()

    if _geste_arme() is None:
        # Aucun geste attendu : ce clic-là ne l'était pas non plus. Le retenir
        # l'empêche d'être consommé par le prochain geste armé, ce qui faisait
        # sauter la coupe à un endroit cliqué bien avant, sans nouveau clic.
        _retenir_clic(clic)
    elif _geste_arme() in ("placer_vue", "viser_vue") and clic is not None:
        _retenir_clic(clic)
        code, nom = _cible_du_geste()
        vue = _vue_photo(code, nom)
        if _geste_arme() == "placer_vue":
            vue["x"], vue["y"] = clic.x, clic.y
            vue["origine_position"] = ORIGINE_MAIN
        elif vue.get("x") is None:
            # Viser avant d'avoir placé ne veut rien dire : le cap se mesure
            # depuis la position de la photographie, pas depuis rien.
            st.warning(
                f"« {nom} » n'a pas encore de position : placez-la avant de "
                "viser ce qu'elle regarde.",
                icon="⚠️",
            )
        else:
            vue["cap_deg"] = cap_vers(vue["x"], vue["y"], clic.x, clic.y)
            vue["origine_cap"] = ORIGINE_MAIN
            vue["cap_confirme"] = True
        _desarmer_geste()
        st.rerun()
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

    if trace is not None and st.button("Corriger et relever le profil", width="stretch"):
        try:
            _relever_et_controler(
                corriger_ligne_coupe(
                    trace, plan.azimut_tables_deg, emprise_cloturee, manuel=manuel,
                    tables=plan.tables,
                ),
                import_be_courant,
                plan,
                "tracee",
            )
            st.session_state["tour_carte"] = st.session_state.get("tour_carte", 0) + 1
            st.rerun()
        except ErreurDP as erreur:
            st.session_state.coupe_be = None
            st.error(f"{type(erreur).__name__} : {erreur}")
    elif trace is None and st.session_state.coupe_be is None:
        st.info(
            "Aucune coupe retenue : cliquez sur « Déplacer la coupe » puis sur "
            "la carte, à l'endroit où elle doit traverser les rangées."
        )

    with emplacement_avertissements:
        for message in import_be_courant.avertissements:
            st.warning(message, icon="⚠️")

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

    st.markdown("### Validation")
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
    elif coupe is None:
        st.info(
            "Placez la ligne de coupe avant de valider : le lot 4 en a besoin "
            "pour la coupe DP 3."
        )
    elif st.button("Valider l'import et écrire la sortie", type="primary", width="stretch"):
        try:
            import_be_courant.ecrire(DOSSIER_SORTIE / _nom_dossier(commune))
            st.success(
                "Import validé. Les photographies et la génération du dossier "
                "s'ouvrent ci-dessous.",
                icon="✅",
            )
        except ErreurDP as erreur:
            st.error(f"{type(erreur).__name__} : {erreur}")


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
            "Ce que le lot 4 lira pour dessiner DP 2, DP 3 et DP 4. Rien à en "
            "faire pour monter le dossier : c'est de quoi contrôler l'import "
            "dans un SIG, ou joindre à une question au bureau d'études."
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
if not contrat_present:
    st.divider()
    st.info(
        "**Validez l'import ci-dessus pour continuer.** Les photographies et la "
        "génération viennent ensuite. Sans plan validé, le dossier s'arrêterait "
        "à la page de garde et aux pièces DP 1 — sans le plan de masse DP 2, les "
        "coupes DP 3 ni les ouvrages techniques DP 4.",
        icon="⬆️",
    )
    # La capacité existe et reste offerte, mais elle se demande : c'est un
    # dossier d'étude amont, pas un dossier déposable, et l'obtenir par
    # inadvertance donnait un PDF de 17 Mo d'apparence complète.
    socle_seul = st.checkbox(
        "Je veux seulement les pièces DP 1 — page de garde, plan de situation, "
        "photographie aérienne, plan de cadastre",
        value=False,
        key="socle_seul",
        help="Pour une étude amont, avant que le bureau d'études ait livré son "
        "plan. Le dossier obtenu n'est pas déposable en l'état.",
    )
    if not socle_seul:
        st.stop()

#: Les trois pièces photographiques du dossier, dans l'ordre du CERFA.
#:
#: Une ligne chacune, et non un dépôt commun : ce sont trois pièces distinctes,
#: qui ne montrent pas la même chose et ne se rangent pas au même endroit du
#: dossier. Les mélanger obligerait à les retrier à la main au moment de
#: constituer le dépôt.
PIECES_PHOTOS = ("DP 6", "DP 7", "DP 8")

st.divider()
st.subheader("3. Pièces fournies")
st.caption(
    "Ce que l'outil ne dessine pas : la notice DP 11, qu'il intègre au dossier, "
    "puis les photographies et photomontages, qu'il conserve sans les assembler."
)

# La notice ouvre la section : c'est la seule pièce obligatoire qu'on y dépose,
# et la seule que l'outil intègre au dossier assemblé — chacune de ses pages
# devient une planche, sous le cadre et le cartouche communs. C'est le lot 5.
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

# ---------------------------------------------------------------------------
# Reprendre un rapport de visite photos-geoloc
# ---------------------------------------------------------------------------
#
# C'est l'entrée de premier choix : le chef de projet qui a visité le site en a
# fait un rapport, et il y a déjà placé chaque prise de vue — parfois corrigé sa
# direction sur fond satellite, ce qui est la bonne façon de le faire. Reprendre
# ce travail vaut mieux que de le lui faire refaire ici, sur un fond moins
# lisible.
#
# Le rapport est une **importation, pas un stockage** : il est lu une fois, on
# n'en garde que les métadonnées, les vignettes ne sont décodées qu'à la
# demande, et seules les photographies retenues sont écrites sur le disque du
# projet. Après quoi le dossier ne voit que des chemins de fichiers, comme pour
# n'importe quelle photo déposée — pas de second chemin de traitement.

#: Distance à l'emprise au-delà de laquelle une prise de vue est proposée en
#: DP 8 plutôt qu'en DP 7. DP 7 est « l'environnement proche », DP 8 « le
#: paysage lointain » : c'est une distance, et nous avons l'emprise.
#:
#: 500 m est cohérent avec le dossier de référence, dont la DP 7 est au 1/2 500
#: et la DP 8 au 1/6 500. Ce n'est qu'une **proposition** : le chef de projet
#: corrige d'une liste déroulante ce qui ne lui convient pas, comme il le fait
#: pour la correspondance des calques en section 2.
DISTANCE_PAYSAGE_LOINTAIN_M = 500.0

#: Ce qu'une photographie du rapport peut devenir, dans l'ordre de la liste.
AFFECTATIONS = ("(ignorer)", "DP 7", "DP 8", "DP 6 — image brute")


@st.cache_data(show_spinner=False, max_entries=2)
def _carte_photos_lue(octets: bytes):
    """La carte déposée, lue une fois plutôt qu'à chaque interaction.

    Streamlit relit un fichier déposé à chaque exécution du script : sans ce
    cache, les 18 Mo d'un rapport seraient réanalysés à chaque case cochée. Le
    cache est **borné à deux entrées** — il est global à toutes les sessions, et
    un cache non borné de cartes entières est exactement ce qui a fait couper le
    dépôt voisin par son hébergeur.
    """
    return lire_carte(octets)


@st.cache_data(show_spinner=False, max_entries=40)
def _vignette_du_rapport(octets: bytes, rang_fichier: int):
    """Une vignette de la galerie, décodée seule et réduite.

    Bornée elle aussi : une image décodée pèse quelques mégaoctets, et le cache
    de Streamlit ne redescend qu'au redémarrage.
    """
    return image_de(octets, rang_fichier)


def _piece_proposee(point, emprise_cloturee) -> str:
    """DP 7 ou DP 8, selon la distance de la prise de vue au site.

    Chaque point se range donc seul, et le chef de projet ne corrige que ce qui
    n'est pas évident.
    """
    from shapely.geometry import Point

    x, y = vers_l93(point.lat, point.lon)
    distance = Point(x, y).distance(emprise_cloturee)
    return "DP 8" if distance > DISTANCE_PAYSAGE_LOINTAIN_M else "DP 7"


def _photos_reprises() -> dict:
    """Les photographies tirées d'un rapport, par pièce puis par nom de fichier.

    Elles vivent en session parce qu'elles n'ont pas de dépôt à l'écran : ce
    sont des fichiers déjà écrits, que la génération retrouvera par leur chemin.
    """
    return st.session_state.setdefault("photos_reprises", {})


def _reprendre_du_rapport(nom_projet: str, octets: bytes, carte, choix: dict) -> int:
    """Écrit les photographies retenues et pose leur point de vue. Rend le compte.

    C'est ici que le rapport cesse d'exister pour le dossier : ses images
    deviennent des fichiers du projet, et leurs points de vue rejoignent ceux
    qu'on place à la main. Rien ne distingue ensuite les deux provenances, sauf
    le rapport de génération qui peut le dire.
    """
    reprises = 0
    for point in carte.points:
        code = choix.get(point.identifiant)
        if not code or code == AFFECTATIONS[0]:
            continue
        piece_cible = "DP 6" if code.startswith("DP 6") else code
        image = _vignette_du_rapport(octets, point.rang_fichier)
        if image is None:
            st.warning(
                f"Le point {point.numero} « {point.nom} » n'a pas d'image dans "
                "le rapport : il est ignoré.",
                icon="⚠️",
            )
            continue
        dossier = DOSSIER_PROJETS / nom_projet / piece_cible.replace(" ", "_")
        dossier.mkdir(parents=True, exist_ok=True)
        cible = dossier / f"{Path(point.nom).stem}.jpg"
        image.save(cible, "JPEG", quality=90, optimize=True)

        vue_depuis_carte = depuis_carte(point)
        vue = _vue_photo(piece_cible, cible.name)
        vue.update({
            "x": vue_depuis_carte.x,
            "y": vue_depuis_carte.y,
            "origine_position": ORIGINE_CARTE,
            "cap_deg": vue_depuis_carte.cap_deg,
            "origine_cap": vue_depuis_carte.origine_cap,
            "cap_confirme": vue_depuis_carte.cap_confirme,
            "precision_m": vue_depuis_carte.precision_m,
            "exif_lu": True,
        })
        _photos_reprises().setdefault(piece_cible, {})[cible.name] = str(cible)
        reprises += 1
    return reprises


def emprise_cloturee_du_projet():
    """L'emprise clôturée du plan importé, ou `None` s'il n'y en a pas.

    La section 3 en a besoin pour proposer une pièce à chaque prise de vue, et
    elle vit dans l'import du bureau d'études, deux sections plus haut.
    """
    import_be = st.session_state.get("import_be")
    if import_be is None or import_be.plan is None:
        return None
    return import_be.plan.polygone_cloture


st.markdown("**Rapport de visite photos-geoloc** — la voie courte")
st.caption(
    "Déposez la carte HTML de votre rapport de visite : les prises de vue y "
    "sont déjà placées, et les directions que vous y avez corrigées sur fond "
    "satellite sont reprises telles quelles. Les photographies retenues sont "
    "écrites dans le dossier du projet ; le rapport, lui, n'est pas conservé."
)
fichier_carte = st.file_uploader(
    "Carte du rapport de visite (.htm ou .html)",
    type=["htm", "html"],
    accept_multiple_files=False,
    key="carte_photos_geoloc",
)

if fichier_carte is not None and emprise_cloturee_du_projet() is not None:
    octets_carte = fichier_carte.getvalue()
    try:
        carte_rapport = _carte_photos_lue(octets_carte)
    except ErreurDP as erreur:
        st.error(f"{type(erreur).__name__} : {erreur}", icon="🚫")
    else:
        st.caption(
            f"« {carte_rapport.titre} » — {len(carte_rapport.points)} prise(s) de "
            f"vue, format v{carte_rapport.version}"
            + (f", {carte_rapport.masques} en corbeille" if carte_rapport.masques else "")
        )
        for message in carte_rapport.avertissements:
            st.warning(message, icon="⚠️")

        emprise_site = emprise_cloturee_du_projet()
        choix_affectation = {}
        # Une galerie de vignettes, et non une liste de numéros : un numéro seul
        # ne dit pas ce qu'une photographie montre. Chacune porte le numéro
        # qu'elle a sur les marqueurs du rapport — le seul repère commun entre
        # les deux écrans, et il est stable.
        for depart in range(0, len(carte_rapport.points), 4):
            for colonne, point in zip(
                st.columns(4), carte_rapport.points[depart : depart + 4]
            ):
                with colonne:
                    vignette = _vignette_du_rapport(octets_carte, point.rang_fichier)
                    if vignette is not None:
                        st.image(vignette, width="stretch")
                    st.caption(f"**{point.numero}.** {point.nom}")
                    propose = _piece_proposee(point, emprise_site)
                    choix_affectation[point.identifiant] = st.selectbox(
                        "Affectation",
                        options=AFFECTATIONS,
                        index=AFFECTATIONS.index(propose),
                        key=f"affectation_{point.identifiant}",
                        label_visibility="collapsed",
                    )

        if st.button("Reprendre les photographies retenues", width="stretch"):
            reprises = _reprendre_du_rapport(
                _nom_dossier(commune), octets_carte, carte_rapport,
                choix_affectation,
            )
            if reprises:
                st.success(
                    f"{reprises} photographie(s) reprises du rapport, avec leur "
                    "point de vue. Vérifiez-les sur la carte de la section 2."
                )
                st.rerun()
            else:
                st.info("Aucune photographie retenue : rien n'a été repris.")
elif fichier_carte is not None:
    st.warning(
        "Le plan du bureau d'études doit être importé avant de reprendre un "
        "rapport : sans emprise clôturée, rien ne distingue l'environnement "
        "proche du paysage lointain.",
        icon="⚠️",
    )

st.divider()
st.markdown("**Photographies et photomontages**")
st.caption(
    "Elles sont conservées dans le dossier du projet ; leur assemblage au "
    "dossier et le **report de la position de prise de vue sur un plan de "
    "repérage** restent à construire — le dossier de référence en met un par "
    "vue, au 1/1 500 et au 1/2 500."
)

photos = {}
for code in PIECES_PHOTOS:
    photos[code] = st.file_uploader(
        f"{code} — {piece(code).titre}",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
        key=f"photos_{code.replace(' ', '_')}",
    )

# La page de garde prend l'insertion paysagère : c'est la vue du projet fini,
# et c'est elle que le dossier de référence met en couverture. Une seule le
# plus souvent — on ne demande alors rien — mais le cas de plusieurs vues
# existe, et il faut pouvoir désigner celle qui monte en couverture.
insertions = [f for f in photos["DP 6"] if not f.name.lower().endswith(".pdf")]
pdfs_insertion = [f for f in photos["DP 6"] if f.name.lower().endswith(".pdf")]
image_garde = None
if len(insertions) == 1:
    image_garde = insertions[0]
    st.caption(f"Page de garde : {image_garde.name}.")
elif len(insertions) > 1:
    noms = [fichier.name for fichier in insertions]
    retenu = st.radio(
        "Insertion paysagère à mettre en page de garde",
        options=noms,
        index=0,
        horizontal=True,
    )
    image_garde = insertions[noms.index(retenu)]

if insertions:
    # Deux par rangée, et toutes : une seule insertion prenait la largeur entière
    # de la page pour une vignette de contrôle, et au-delà de quatre la vignette
    # manquante pouvait être celle de la couverture.
    par_rangee = 2 if len(insertions) <= 2 else 4
    for depart in range(0, len(insertions), par_rangee):
        rangee = insertions[depart : depart + par_rangee]
        colonnes = st.columns(par_rangee)
        for colonne, fichier in zip(colonnes, rangee):
            with colonne:
                st.image(
                    fichier,
                    caption=("couverture — " if image_garde is fichier else "")
                    + fichier.name,
                    width="stretch",
                )
else:
    if pdfs_insertion:
        st.warning(
            "L'insertion paysagère déposée est un PDF : la page de garde attend "
            "une image et gardera son cadre tireté. Déposez aussi le JPG ou le "
            "PNG de la vue.",
            icon="⚠️",
        )
    st.caption(
        "Sans insertion paysagère, un cadre tireté tient la place en page de "
        "garde et la nomme."
    )

# ---------------------------------------------------------------------------
# Les prises de vue, saisies sur la carte de la section 2
# ---------------------------------------------------------------------------
#
# Le bloc se remplit ici, où les photographies viennent d'être déposées, mais
# s'affiche là-haut, sous la carte : c'est elle qui reçoit les clics. Un seul
# aller-retour, et toutes les prises se placent d'affilée.


def _lire_exif_une_fois(code: str, fichier) -> None:
    """Pré-remplit la prise de vue avec ce que la photographie sait d'elle-même.

    Une photographie de visite porte souvent sa position : la redemander au chef
    de projet serait lui faire saisir ce que le fichier contient déjà. Le cap,
    lui, n'est qu'une **proposition** — la boussole d'un téléphone se trompe de
    10 à 20°, et il ne fera dessiner aucun cône tant qu'il n'aura pas été visé.

    Lu une seule fois par photographie, et non à chaque exécution du script :
    Streamlit en relance une à chaque interaction, et l'EXIF d'une photo de
    12 Mpx n'est pas gratuit. Le drapeau reste posé même quand la lecture échoue,
    sans quoi une photographie illisible serait rouverte indéfiniment.
    """
    vue = _vue_photo(code, fichier.name)
    if vue.get("exif_lu"):
        return
    vue["exif_lu"] = True
    try:
        metadonnees = lire_metadonnees(fichier, nom=fichier.name)
    except ErreurDP as erreur:
        vue["exif_message"] = str(erreur)
        return
    finally:
        # Le flux du dépôt est partagé avec le reste de la page : le rembobiner
        # évite que la vignette ou l'écriture sur disque ne lisent zéro octet.
        fichier.seek(0)

    if metadonnees.geolocalisee:
        vue["x"], vue["y"] = vers_l93(metadonnees.lat, metadonnees.lon)
        vue["origine_position"] = ORIGINE_EXIF
        vue["precision_m"] = metadonnees.precision_m
    if metadonnees.cap_deg is not None:
        vue["cap_deg"] = metadonnees.cap_deg
        vue["origine_cap"] = ORIGINE_EXIF
        vue["cap_confirme"] = False
    if metadonnees.avertissements:
        vue["exif_message"] = " ".join(metadonnees.avertissements)


@dataclass(frozen=True)
class _PhotoReprise:
    """Une photographie déjà écrite sur le disque, tirée d'un rapport.

    Elle se présente comme un fichier déposé — `name` et de quoi l'afficher —
    pour que la galerie des prises de vue n'ait pas à distinguer les deux
    provenances. Le reste du dossier ne les distingue pas non plus.
    """

    name: str
    chemin: str

    def __str__(self) -> str:
        return self.chemin


def _etat_de_la_prise(vue: dict) -> str:
    """Ce qui manque à une prise de vue, dit en clair — et d'où vient ce qu'on a."""
    if vue.get("x") is None:
        return "à placer sur la carte"
    origine = (
        "placée d'après l'EXIF"
        if vue.get("origine_position") == ORIGINE_EXIF
        else "placée sur la carte"
    )
    if vue.get("precision_m") and vue["precision_m"] > SEUIL_PRECISION_M:
        origine += f" — incertitude annoncée {vue['precision_m']:.0f} m"
    if vue.get("cap_confirme"):
        return f"{origine}, visée {vue['cap_deg']:.0f}°"
    if vue.get("cap_deg") is not None:
        return (
            f"{origine} — direction EXIF de {vue['cap_deg']:.0f}° **proposée**, "
            "à confirmer en visant : aucun cône sans cela"
        )
    return f"{origine}, sans direction"


def _oublier_les_photos_remplacees(photos_par_piece: dict) -> None:
    """Écarte les prises dont la photographie a été remplacée par une autre.

    Une pièce **dont le dépôt est vide** n'est pas nettoyée, et c'est délibéré :
    on ne peut pas distinguer un retrait volontaire d'un dépôt momentanément
    vide. Mesuré le 16/09/2026 sous `AppTest` : un `file_uploader` alimenté par
    le harnais perd sa valeur après un `st.rerun()` programmatique, et le
    nettoyage effaçait alors le point de vue qui venait d'être placé — deux
    lignes plus haut dans le même script.

    Rien ne se perd à cette prudence : `_photographies_du_projet` part des
    fichiers déposés, pas des points de vue. Une prise sans photographie
    n'entre dans aucune pièce, et ne peut donc pas y poser de repère fantôme.
    """
    for code, par_nom in list(_vues_photo().items()):
        deposes = {f.name for f in photos_par_piece.get(code) or []}
        # Une photographie reprise d'un rapport n'a pas de dépôt à l'écran : son
        # fichier est déjà écrit, et elle ne doit pas être prise pour retirée.
        deposes |= set(_photos_reprises().get(code) or {})
        if not deposes:
            continue
        for nom in list(par_nom):
            if nom not in deposes:
                del par_nom[nom]


def _ligne_de_prise(code: str, fichier) -> None:
    """Une photographie : sa vignette, son état, et ses deux boutons."""
    vue = _vue_photo(code, fichier.name)
    vignette, libelle, bouton_placer, bouton_viser = st.columns([1, 3, 1, 1])
    with vignette:
        if not fichier.name.lower().endswith(".pdf"):
            st.image(
                fichier.chemin if isinstance(fichier, _PhotoReprise) else fichier,
                width=90,
            )
    with libelle:
        st.write(f"{fichier.name}")
        st.caption(_etat_de_la_prise(vue))
        if vue.get("exif_message"):
            st.caption(f"⚠️ {vue['exif_message']}")
        if code == "DP 6":
            # Les volets d'une même vue partagent un point de vue : c'est la
            # même prise (D3). Le sélecteur dit lesquels vont ensemble, et
            # l'ordre de dépôt donne l'ordre des volets.
            vue["vue"] = st.selectbox(
                "Vue",
                options=[chr(ord("A") + i) for i in range(4)],
                index=[chr(ord("A") + i) for i in range(4)].index(
                    vue.get("vue", "A")
                ),
                key=f"vue_de_{code}_{fichier.name}",
                label_visibility="collapsed",
            )
        # Un seul curseur pour les deux axes : le rognage n'en touche qu'un —
        # la largeur d'une photographie plus panoramique que son emplacement, sa
        # hauteur sinon — et donner la même valeur aux deux laisse le réglage
        # agir sur celui qui compte, sans demander au chef de projet de deviner
        # lequel c'est.
        cadrage = st.slider(
            "Recadrage",
            min_value=-50, max_value=50, value=int(vue.get("cadrage", 0.0) * 100),
            step=5, format="%d %%",
            key=f"cadrage_{code}_{fichier.name}",
            help="La photographie est rognée pour remplir son emplacement. "
            "Déplacez ce curseur si le rognage retire ce qu'il fallait montrer : "
            "vers la gauche pour garder le haut ou la gauche de l'image, vers la "
            "droite pour l'inverse.",
        )
        vue["cadrage"] = cadrage / 100.0

    with bouton_placer:
        if st.button("📍 Placer", key=f"placer_{code}_{fichier.name}"):
            _armer_sur_photo("placer_vue", code, fichier.name)
            st.rerun()
    with bouton_viser:
        if st.button("🎯 Viser", key=f"viser_{code}_{fichier.name}",
                     disabled=vue.get("x") is None):
            _armer_sur_photo("viser_vue", code, fichier.name)
            st.rerun()


def _saisir_les_prises_de_vue(emplacement, photos_par_piece: dict) -> None:
    """Liste les photographies déposées, leur état, et les deux gestes."""
    _oublier_les_photos_remplacees(photos_par_piece)
    if emplacement is None:
        return
    with emplacement:
        st.markdown("### Les prises de vue des pièces photographiques")
        total = sum(len(f or []) for f in photos_par_piece.values())
        if not total:
            st.caption(
                "Aucune photographie déposée. Déposez-les en section 3, puis "
                "revenez ici pour placer chaque prise de vue sur la carte."
            )
            return
        st.caption(
            "**📍 Placer** dit où est la photographie, **🎯 Viser** ce qu'elle "
            "regarde — les deux gestes de photos-geoloc, au même sens. Une "
            "direction non visée ne fait dessiner aucun cône : la boussole d'un "
            "téléphone se trompe de 10 à 20°, et le dossier ne porte que ce qui "
            "a été vérifié."
        )
        for code in PIECES_PHOTOS:
            fichiers = photos_par_piece.get(code) or []
            reprises = _photos_reprises().get(code) or {}
            if not fichiers and not reprises:
                continue
            st.markdown(f"**{code}** — {piece(code).titre}")
            for fichier in fichiers:
                if not fichier.name.lower().endswith(".pdf"):
                    _lire_exif_une_fois(code, fichier)
                _ligne_de_prise(code, fichier)
            for nom, chemin in sorted(reprises.items()):
                _ligne_de_prise(code, _PhotoReprise(nom, chemin))


_saisir_les_prises_de_vue(emplacement_prises_de_vue, photos)


#: Les pièces où deux fichiers portent le même nom, avec les noms en cause.
#:
#: Ils s'écrasent sur le disque — la cible est nommée par le nom du fichier — et
#: le second est perdu sans un mot. Le chef de projet renomme, ou retire : ce
#: n'est pas à l'outil de choisir lequel des deux survit.
photos_en_double = {}
for code, fichiers in photos.items():
    noms_deposes = [fichier.name for fichier in fichiers or []]
    doubles = sorted({nom for nom in noms_deposes if noms_deposes.count(nom) > 1})
    if doubles:
        photos_en_double[code] = doubles
for code, doubles in photos_en_double.items():
    st.error(
        f"{code} : deux fichiers portent le même nom ({', '.join(doubles)}). "
        "Le second écraserait le premier dans le dossier du projet — renommez-en "
        "un avant de générer.",
        icon="🚫",
    )


st.divider()
st.subheader("4. Génération")

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

#: Décision D5 du lot 4 : quand un calque du bureau d'études ne disait pas si
#: une voirie était lourde ou légère, le chef de projet tranche — **objet par
#: objet**, parce qu'un projet a presque toujours les deux et que le calque les
#: mélange. Aucune valeur par défaut : le tableau bilan sépare les deux, la
#: légende du dossier les distingue, et aucune des deux n'est plus probable que
#: l'autre. Tant qu'un objet n'est pas tranché, les planches ne sont pas
#: dessinées.
_voiries = decrire_voiries(DOSSIER_SORTIE / nom) if nom else []
voirie = None
if _voiries:
    st.warning(
        f"Le plan importé porte {len(_voiries)} objet(s) sur le calque "
        "« voirie » dont le type n'était pas précisé. Le tableau bilan sépare la "
        "voie lourde de la piste légère, et la légende du dossier les "
        "distingue : tranchez avant de dessiner.",
        icon="⚠️",
    )
    st.caption(
        "Un objet à la fois : un projet a presque toujours les deux. La largeur "
        "moyenne aide à les séparer — une voie lourde fait cinq à six mètres, "
        "une piste légère trois à quatre."
    )
    choix = []
    for objet in _voiries:
        colonne_mesure, colonne_choix = st.columns([1, 2])
        with colonne_mesure:
            st.markdown(f"**Objet {objet['rang'] + 1}** — {objet['resume']}")
        with colonne_choix:
            choix.append(
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
            )
    # Aucune valeur par défaut, et rien de partiel : tant qu'un objet n'est pas
    # tranché, le contrat refuse — c'est une décision de projet, pas un réglage.
    voirie = choix if all(c is not None for c in choix) else None



def _photographies_du_projet(nom_projet: str, photos_par_piece: dict) -> dict:
    """Les prises de vue au format de `projet.json`, prêtes à être écrites.

    Les chemins sont ceux où `_enregistrer_photos` vient d'écrire les fichiers :
    le dossier du projet, une pièce par sous-dossier. Une photographie sans point
    de vue placé n'entre pas — la pièce le dira au rapport de génération plutôt
    que de porter un repère posé nulle part.

    Pour DP 6, les volets d'une même vue sont regroupés : ils partagent le point
    de vue de leur première image, puisque c'est la même prise.
    """
    from dp_socle.points_de_vue import PriseDeVue, place_a_la_main, prise_en_json

    photographies = {}
    for code in PIECES_PHOTOS:
        fichiers = [
            f for f in (photos_par_piece.get(code) or [])
            if not f.name.lower().endswith(".pdf")
        ]
        fichiers += [
            _PhotoReprise(nom, chemin)
            for nom, chemin in sorted((_photos_reprises().get(code) or {}).items())
        ]
        if not fichiers:
            continue
        dossier = DOSSIER_PROJETS / nom_projet / code.replace(" ", "_")
        groupes = {}
        for fichier in fichiers:
            vue = _vue_photo(code, fichier.name)
            if vue.get("x") is None:
                continue
            cle = vue.get("vue", "A") if code == "DP 6" else fichier.name
            groupes.setdefault(cle, []).append((fichier, vue))

        prises = []
        for _, membres in sorted(groupes.items()):
            premier = membres[0][1]
            prises.append(
                prise_en_json(
                    PriseDeVue(
                        point_de_vue=place_a_la_main(
                            membres[0][0].name, premier["x"], premier["y"],
                            premier.get("cap_deg")
                            if premier.get("cap_confirme") else None,
                        ),
                        images=tuple(
                            str(dossier / Path(f.name).name) for f, _ in membres
                        ),
                        cadrages=tuple(
                            (v.get("cadrage", 0.0), v.get("cadrage", 0.0))
                            for _, v in membres
                        ),
                    )
                )
            )
        if prises:
            photographies[code] = prises
    return photographies


def _construire_projet() -> Projet | None:
    if not commune.strip():
        st.error("La commune est obligatoire : c'est elle qui nomme le projet.")
        return None
    if photos_en_double:
        st.error(
            "Deux photographies portent le même nom dans "
            f"{', '.join(photos_en_double)} : l'une écraserait l'autre. "
            "Renommez-en une en section 3."
        )
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

    chemin_image = _enregistrer_photos(nom, photos, image_garde)
    photographies = _photographies_du_projet(nom, photos)
    chemin_notice = _enregistrer_notice(nom, fichier_notice)

    return Projet(
        nom=nom,
        commune=commune.strip(),
        code_postal=code_postal.strip(),
        date=date_projet.isoformat(),
        emprise=str(chemin_emprise),
        image_garde=chemin_image,
        libelle=libelle or None,
        voirie=voirie,
        notice=chemin_notice,
        photographies=photographies or None,
    )


# Un seul bouton. Le second, « Écrire projet.json », n'écrivait que le fichier
# de métadonnées du lot 1 — que celui-ci écrit de toute façon avant de dessiner —
# et se confondait avec le `projet.json` du contrat d'entrée, qui est un autre
# fichier, dans un autre dossier, produit par l'import du plan BE.
lancer = st.button("Générer le dossier", type="primary", width="stretch")

if lancer:
    try:
        projet = _construire_projet()
        if projet is not None:
            projet.valider()
            projet.ecrire(DOSSIER_PROJETS / projet.nom / "projet.json")
            emprise = charger_emprise(projet.chemin_emprise)
            with st.spinner("Téléchargement des fonds IGN et composition des planches…"):
                rapport = generer_dossier(projet, DOSSIER_SORTIE, dpi=int(dpi))
            # Conservé en session, et non affiché dans la foulée : tout clic sur
            # un bouton de téléchargement rejoue le script, `lancer` retombe à
            # faux, et le compte rendu — les autres boutons compris — disparaît
            # de l'écran. Le chef de projet ne pouvait donc télécharger qu'un
            # seul fichier, puis devait tout regénérer.
            st.session_state["dossier_genere"] = {
                "nom": projet.nom,
                "libelle": projet.libelle_affiche,
                "emprise": (
                    emprise.nb_polygones,
                    emprise.surface_m2 / 10_000,
                    emprise.crs_source,
                ),
                "rapport": rapport,
                "archive": _archive_du_dossier(rapport),
            }
    except ErreurDP as erreur:
        st.session_state.pop("dossier_genere", None)
        st.error(f"{type(erreur).__name__} : {erreur}")


# Le compte rendu du dernier dossier produit, tant qu'il décrit bien le projet
# affiché : changer de commune ou d'indice le rendrait mensonger.
_genere = st.session_state.get("dossier_genere")
if _genere is not None and _genere["nom"] == nom:
    rapport = _genere["rapport"]
    polygones, hectares, crs = _genere["emprise"]
    st.divider()
    st.success(
        f"**{_genere['libelle']}** — {len(rapport.planches)} planches, "
        f"{rapport.taille_mo:.1f} Mo. Téléchargez-le ci-dessous : l'application "
        "tourne sur un serveur, les fichiers n'y restent pas à votre disposition."
    )

    # `on_click="ignore"` : sans lui, Streamlit rejoue le script entier pour
    # livrer un fichier — c'est son défaut, documenté. Le compte rendu survit
    # désormais à cette réexécution, mais la provoquer pour rien reste un
    # aller-retour serveur à chaque téléchargement.
    colonne_dossier, colonne_pdf = st.columns(2)
    with colonne_dossier:
        st.download_button(
            f"⬇️ Le dossier complet ({len(rapport.planches)} planches, ZIP)",
            data=_genere["archive"],
            file_name=f"{_genere['nom']}_DP.zip",
            mime="application/zip",
            type="primary",
            on_click="ignore",
            width="stretch",
        )
    with colonne_pdf:
        with open(rapport.assemblage, "rb") as fichier:
            st.download_button(
                f"⬇️ Le PDF assemblé seul ({rapport.taille_mo:.1f} Mo)",
                data=fichier.read(),
                file_name=rapport.assemblage.name,
                mime="application/pdf",
                on_click="ignore",
                width="stretch",
            )

    for message in rapport.avertissements:
        st.warning(message, icon="⚠️")

    # Annoncé même quand tout va bien (décision D2 du lot 5) : une notice
    # réduite de moitié parce qu'elle arrivait en A2 doit se voir avant
    # l'instruction, et un rapport qui ne parle que des ennuis ne le dirait pas.
    if rapport.notice:
        _notice = rapport.notice
        st.caption(
            f"Notice DP 11 : {_notice['source']}, {_notice['pages']} page(s) en "
            f"{', '.join(_notice['formats'])}, ajustée au facteur "
            f"{_notice['facteur_min']:.0%}"
            + (
                f" à {_notice['facteur_max']:.0%}."
                if _notice["facteur_max"] != _notice["facteur_min"]
                else "."
            )
        )
    st.caption(
        f"Emprise : {polygones} polygone(s), {hectares:.2f} ha, CRS source {crs}."
        + (
            f" Planches DP 2 à DP 4 dessinées depuis le contrat d'entrée "
            f"« {rapport.origine_contrat} »."
            if rapport.origine_contrat
            else ""
        )
    )
    st.dataframe(
        [
            {
                "Pièce": entree["numero"],
                "Titre": entree["titre"],
                "Page": entree["page"],
            }
            for entree in rapport.sommaire
        ],
        width="stretch",
        hide_index=True,
    )


