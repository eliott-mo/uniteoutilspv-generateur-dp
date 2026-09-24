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
from streamlit_folium import st_folium

from dp_socle.environnement import dossiers_de_travail, etat_cairo, etat_travail, preparer_cairo

preparer_cairo()

# Le lot 2 (HelioScope) et le lot 2bis (plan BE) ont chacun leur aperçu, avec
# les mêmes noms de fonctions : ceux du lot 2bis sont renommés ici, plutôt que
# dans leur module, pour ne pas toucher au lot 2.
from dp_socle.planches.palette import EXCLUES
from dp_socle.planches.dp6_insertions import INTITULES as INTITULES_DP6
from dp_socle.planches.reperage_vues import OUVERTURE_CONE_DEG
from dp_socle.carte_photos import depuis_carte, image_de, lire_carte
from dp_socle.lecture_exif import MARQUE_SANS_POSITION, etat_heic, lire_metadonnees
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
    apercu_de_placement,
    apercu_de_visee,
    bornes_wgs84,
    clic_l93,
    en_wgs84,
    legende_presente,
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
with st.expander("🗂️ À rassembler avant de commencer", expanded=False):
    st.markdown(
        """**Obligatoire pour tout dossier**
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
""" 
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
            deja_ecrite = getattr(fichier, "chemin", None)
            if deja_ecrite is not None:
                # Versée d'un rapport : le fichier est déjà sur le disque, et
                # la réécrire par-dessus elle-même n'apporterait rien. Elle
                # n'est pas un dépôt et n'a pas de tampon à recopier — d'où
                # « '_PhotoReprise' object has no attribute 'getbuffer' » à la
                # génération (25/09/2026).
                #
                # Reconnue à son attribut plutôt qu'à sa classe : cette
                # fonction vit tout en haut du script, et `_PhotoReprise` est
                # déclarée bien plus bas, avec le reste de la saisie.
                if fichier is retenu:
                    couverture = Path(deja_ecrite)
                continue
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


#: Ce que la carte des prises de vue laisse de côté, et que celle de la coupe
#: garde.
#:
#: Les arbres existants sont 290 des 504 objets du plan de Sarnois, et 43 % des
#: 308 Ko que la carte envoie au navigateur à chaque exécution du script. Sur
#: l'orthophoto IGN, qui les montre déjà, ils n'aident pas à placer une
#: photographie.
#:
#: Mais ils ne se retirent **pas** de la carte de la coupe, et la nuance est
#: tout : `dp3_coupes` dessine à 8 m les arbres que la coupe traverse, et cette
#: hauteur fixe celle du bloc de la planche. Choisir par où passe la coupe sans
#: voir les arbres, ce serait choisir à l'aveugle ce qui sera dessiné — objection
#: du 19/09/2026, vérifiée dans `_vegetation_sur_le_profil`.
CATEGORIES_HORS_CARTE_DES_VUES = ("arbre_existant",)


def _couches_de_la_carte(plan, regler_la_coupe: bool):
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
    cle = "couches_carte" if regler_la_coupe else "couches_carte_sans_vegetation"
    couches = st.session_state.get(cle)
    if couches is not None:
        return couches
    ecartees = CATEGORIES_HORS_CARTE
    if not regler_la_coupe:
        ecartees = ecartees + CATEGORIES_HORS_CARTE_DES_VUES
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
    st.session_state[cle] = couches
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
    for controle in ecarts:
        st.warning(f"{controle.libelle} : {controle.message}", icon="⚠️")


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

with st.container():
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
    "placer_vue": (
        "📍 Placer",
        "📍 **Cliquez sur la carte** à l'emplacement réel de « {nom} ».",
        "#d81b8c",
    ),
    "viser_vue": (
        "🎯 Viser",
        "🎯 **Cliquez sur la carte** vers ce que regarde « {nom} ». La direction "
        "s'en déduit, et c'est elle qui fera dessiner le cône.",
        "#d81b8c",
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


def _poser_prise_sur_la_carte(
    carte, code: str, nom: str, vue: dict, visee: bool = False
) -> None:
    """Marqueur d'une prise de vue placée, et son cône si la direction est sûre.

    Le cône est un secteur de 50°, comme sur la planche et comme sur les
    marqueurs de `photos-geoloc` : le chef de projet doit reconnaître d'un coup
    d'œil ce qu'il retrouvera sur le dossier.

    `visee` désigne la photographie que le geste armé concerne. Elle passe en
    rose et grossit : « rien ne m'indique sur la carte quel point est concerné »
    (retour d'usage du 22/09/2026). Vingt-cinq points blancs identiques ne
    disent pas lequel attend le clic.
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
        location=(lat, lon),
        radius=9 if visee else 5,
        color=TEINTE_VISEE if visee else "#1a1a1a",
        weight=3 if visee else 2,
        fill=True,
        fillColor="#ffffff",
        fillOpacity=1.0,
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
            coupe, fichier_altimetrie=st.session_state.get("chemin_altimetrie_be")
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


def _carte_du_plan(import_be_courant, regler_la_coupe: bool) -> None:
    """La carte du plan : le plan importé, la coupe, et les prises de vue posées.

    Un seul composant de carte, appelé à un endroit ou à un autre selon
    l'avancement — jamais deux à l'écran. Avant la validation il vit dans la
    section 2, où la coupe se règle ; après, il descend sous les dépôts de
    photographies, où les prises de vue se placent.

    C'est ce que le parcours demandait : « il faudra d'abord la coupe, puis
    ensuite les photos » (retour d'usage du 19/09/2026). La validation
    libérait tout d'un coup — la coupe et les photographies — et le message
    « Tracez sur la carte » s'affichait avant qu'aucune carte n'existe.

    `plan` et `emprise_cloturee` sont relus de l'import plutôt que lus au
    module : une fonction qui lit un global écrit plus bas lève dans le
    navigateur et nulle part ailleurs, ce que `test_ordre_app` refuse.
    """
    plan = import_be_courant.plan
    emprise_cloturee = plan.polygone_cloture

    if not regler_la_coupe and _geste_arme() == "translation_coupe":
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
    if regler_la_coupe:
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
    else:
        # Plus un mot sur la coupe ici : elle est figée par la validation, et
        # continuer d'en parler « vient polluer le reste du process » (retour
        # d'usage du 22/09/2026). Cette carte ne sert plus qu'aux photographies.
        st.markdown("### Le plan, pour placer les prises de vue")
        st.caption(
            "Les arbres existants ne sont pas repris ici : l'ortho IGN les "
            "montre déjà, et ils ne servent qu'au tracé de la coupe. Ils "
            "restent sur la planche DP 2 et sur la coupe DP 3."
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
    elif _geste_arme() == "translation_coupe" and regler_la_coupe:
        st.info(GESTES_CARTE["translation_coupe"][1], icon="🖱️")
        if st.button("Annuler le déplacement", key="annuler_translation_coupe"):
            _desarmer_geste()
            st.rerun()
    elif regler_la_coupe and st.button(
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

    for style, collection in _couches_de_la_carte(plan, regler_la_coupe):
        folium.GeoJson(
            collection,
            style_function=lambda trait, style=style: _style_carte(style, trait),
            name=style.libelle,
        ).add_to(carte)

    # La coupe retenue, et elle seule. Le tracé d'origine était montré à côté,
    # en orange : le chef de projet qui traçait volontairement de travers voyait
    # son trait oblique persister et croyait que rien n'avait été redressé.
    #
    # Une fois la coupe figée, elle quitte la carte avec le reste de son
    # attirail : à ce moment-là le plan « ne sert plus qu'à gérer les photos ».
    if regler_la_coupe and st.session_state.coupe_be is not None:
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
    cible = _cible_du_geste() if _geste_arme() in ("placer_vue", "viser_vue") else None
    for code_piece, par_nom in _vues_photo().items():
        for nom_photo, vue in par_nom.items():
            if vue.get("x") is None:
                continue
            _poser_prise_sur_la_carte(
                carte, code_piece, nom_photo, vue,
                visee=cible == (code_piece, nom_photo),
            )

    # Le geste des prises de vue se montre comme celui de la coupe : ce qui se
    # posera suit la souris, et se fige au clic. Sans cela viser était aveugle —
    # « rien ne m'indique dans quelle direction je vise », et au clic « on a
    # l'impression que tout plante l'espace d'une seconde » (22/09/2026).
    if cible is not None:
        vue_ciblee = _vue_photo(*cible)
        if _geste_arme() == "viser_vue" and vue_ciblee.get("x") is not None:
            lat_vue, lon_vue = en_wgs84_point(vue_ciblee["x"], vue_ciblee["y"])
            apercu_de_visee(
                lat_vue, lon_vue, OUVERTURE_CONE_DEG, RAYON_VISEE_CARTE_M,
                TEINTE_VISEE,
                message_attente=f"Direction de « {cible[1]} » prise — "
                "mise à jour de la carte…",
            ).add_to(carte)
        elif _geste_arme() == "placer_vue":
            apercu_de_placement(
                TEINTE_VISEE,
                message_attente=f"Position de « {cible[1]} » prise — "
                "mise à jour de la carte…",
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
        + (" Noir : coupe A-A' retenue." if regler_la_coupe else "")
        + " Les modules ne sont pas dessinés ici — la silhouette des rangées dit "
        "la même chose et un plan en compte des milliers. Les couleurs du DXF ne "
        "sont pas reprises, les codes ACI y sont des couleurs de travail."
    )

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
            vue["cap_verifie"] = True
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

    if regler_la_coupe and st.session_state.coupe_be is None:
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
                coupe, fichier_altimetrie=st.session_state.get("chemin_altimetrie_be")
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
    commune: str, fichiers_emprise, fichier_export, fichier_pdf, fichier_altimetrie
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
        if any(f is not None for f in (fichier_export, fichier_pdf, fichier_altimetrie)):
            st.warning(
                f"Il manque {' et '.join(manquants)} : le bouton « Importer et "
                "caler le plan » n'apparaît qu'une fois les deux déposés. Le plan "
                "seul n'a pas d'échelle, l'export seul n'a que les tables.",
                icon="⚠️",
            )
        return

    chemin_export = _deposer(fichier_export, commune)
    chemin_pdf = _deposer(fichier_pdf, commune)
    chemin_altimetrie = _deposer(fichier_altimetrie, commune)
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
    if not st.button(
        "Importer et caler le plan",
        type="primary",
        width="stretch",
        disabled=bool(a_trancher),
    ):
        return
    st.session_state.coupe_be = None
    st.session_state.profil_be = None
    st.session_state["couches_carte"] = None
    st.session_state["couches_carte_sans_vegetation"] = None
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
    st.session_state.chemin_altimetrie_be = (
        str(chemin_altimetrie) if chemin_altimetrie else None
    )
    _reprendre_import_precedent(DOSSIER_SORTIE / nom_importe, resultat, emprise_cadastrale)
    _proposer_la_coupe(resultat)


def _oublier_la_carte_et_la_coupe(import_pdf) -> None:
    """Le plan a bougé : les couches de la carte et la coupe ne valent plus."""
    st.session_state["couches_carte"] = None
    st.session_state["couches_carte_sans_vegetation"] = None
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
        st.session_state["couches_carte_sans_vegetation"] = None


def _resumer_le_plan_pdf(import_pdf) -> None:
    """Ce sur quoi le dossier est engagé, quand le plan vient d'un PDF."""
    calage = import_pdf.calage
    plan = import_pdf.plan
    st.markdown("### Ce sur quoi le dossier est engagé")
    colonnes = st.columns(4)
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
    st.caption(
        f"« {import_pdf.lecture.source} », page {import_pdf.lecture.page}, calé sur "
        f"« {import_pdf.source_export} » : {calage.nb_rangees_plan} rangées relevées "
        f"sur le plan pour {calage.nb_rangees_dxf} dans le DXF. Il n'y a pas de "
        "tableau bilan : surfaces et puissance ne sont recoupées avec aucune "
        "déclaration."
    )
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

    # La carte, ici et pas plus bas, tant que le contrat n'est pas écrit : c'est
    # le moment où la coupe se règle, et la validation la fige. Elle redescend
    # sous les dépôts une fois l'import validé, pour les prises de vue — une
    # seule carte à l'écran à chaque instant, jamais deux.
    #
    # L'annonce au-dessus dit « Tracez sur la carte si vous voulez la déplacer » :
    # elle s'affichait alors qu'aucune carte n'existait encore, et rien ne
    # permettait d'agir (retour d'usage du 19/09/2026).
    # Et elle y reste tant que ce qui est à l'écran n'a pas été écrit : une
    # fois la première validation faite, un recalage ou un changement de couche
    # renvoyait la carte tout en bas, en section 3 bis, à deux écrans des
    # boutons de recalage (retour d'usage du 24/09/2026).
    carte_de_la_coupe = (
        not (DOSSIER_SORTIE / _nom_dossier(commune) / NOM_GEOPACKAGE).exists()
        or _etat_de_l_import(import_be_courant) != st.session_state.get("etat_ecrit")
    )
    if carte_de_la_coupe:
        _carte_du_plan(import_be_courant, regler_la_coupe=True)
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
        for depose in (
            fichier_dxf,
            fichier_tableau,
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


        if st.button("Importer et contrôler", type="primary", width="stretch"):
            st.session_state.coupe_be = None
            st.session_state.profil_be = None
            # Le plan change : les couches reprojetées de la carte ne valent
            # plus, et une carte qui garderait les anciennes serait pire que
            # lente — elle montrerait l'import précédent.
            st.session_state["couches_carte"] = None
            st.session_state["couches_carte_sans_vegetation"] = None
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

if not plan_du_be and commune.strip():
    _importer_le_plan_pdf(
        commune,
        fichiers_emprise,
        fichier_export_helioscope,
        fichier_plan_pdf,
        fichier_altimetrie,
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
        # changent ce que la carte, plus bas, doit montrer.
        _resumer_le_plan_pdf(import_be_courant)
        # La carte d'un plan PDF vient ici, sous le calage et les choix du plan,
        # et non sous les alertes : c'est sur elle que se lit l'effet d'un
        # recalage ou d'une correction, et les alertes la repoussaient à
        # plusieurs écrans des réglages (retour d'usage du 23/09/2026). Le plan
        # du BE, qui n'a ni calage ni choix à suivre, la garde plus bas.
        carte_de_la_coupe = _montrer_la_coupe(import_be_courant)
    plan = import_be_courant.plan
    emprise_cloturee = plan.polygone_cloture

    if tableau is not None:
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
                for message in a_lire:
                    st.warning(message, icon="⚠️")
        else:
            for message in a_lire:
                st.warning(message, icon="⚠️")
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
    elif st.button("Valider l'import et écrire la sortie", type="primary", width="stretch"):
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
                "Import validé, coupe A-A' figée. Les photographies et la "
                "génération du dossier s'ouvrent ci-dessous, et la carte a "
                "redescendu pour placer les prises de vue."
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
st.subheader("3. Ajout de photographies et photomontages")
st.caption(
    "Les photographies des pièces DP 6, DP 7 et DP 8. L'outil les conserve "
    "dans le dossier du projet et les pose sur ses planches ; la notice DP 11 "
    "se dépose plus bas, juste avant la génération."
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
#:
#: « Ne pas retenir » vient en tête **et fait le défaut**. Une pièce proposée
#: d'emblée retenait toutes les photographies du rapport : sur une visite qui en
#: compte vingt-cinq, les vingt-cinq partaient au dossier, et « choisir »
#: consistait à écarter les autres une par une — l'inverse du geste attendu
#: (retour d'usage du 17/09/2026). La pièce que la distance suggère est
#: maintenant affichée à côté de la liste, sans rien décider.
#: « DP 6 — image brute » nomme un **volet**, pas une pièce complète : une
#: insertion paysagère compare l'état actuel et le projet, et le photomontage
#: n'est pas dans un rapport de visite. Le libellé le dit, faute de quoi on
#: choisit DP 6, on place son point de vue, et la planche ne sort pas — c'est
#: arrivé le 22/09/2026.
AFFECTATIONS = (
    "Ne pas retenir",
    "DP 6 — image brute (photomontage à ajouter)",
    "DP 7",
    "DP 8",
)


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


#: Nombre de vignettes par ligne dans la galerie du rapport de visite.
VIGNETTES_PAR_LIGNE = 5

#: Largeur de la vignette qui montre la couverture retenue, en pixels. Elle est
#: là pour vérifier d'un coup d'œil laquelle monte en page de garde, pas pour
#: la juger : le tableau des photographies la montre déjà en grand.
LARGEUR_VIGNETTE_COUVERTURE_PX = 220


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
            # Un cap connu fait un cône, d'où qu'il vienne. La règle voulait
            # qu'un cap non **regardé** dans le rapport — EXIF brut, sans
            # calibration ni correction à la main — soit reposé ici : « si le
            # chef de projet a déjà fait l'effort de le placer dans sa carto
            # HTML, c'est désagréable d'avoir à le refaire » (26/09/2026). La
            # ligne dit d'où il vient, et il se corrige toujours en visant.
            "cap_confirme": vue_depuis_carte.cap_deg is not None,
            "cap_verifie": vue_depuis_carte.cap_confirme,
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


col_fichiers, col_rapport = st.columns(2)
with col_fichiers:
    st.markdown("**Depuis vos fichiers**")
    st.caption(
        "Les photographies de visite et les photomontages, toutes pièces "
        "confondues. Vous direz plus bas à quelle pièce chacune appartient."
    )
    fichiers_photos = st.file_uploader(
        "Photographies et photomontages",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
        key="photos_deposees",
        label_visibility="collapsed",
    )
with col_rapport:
    st.markdown("**Depuis un rapport de visite photos-geoloc**")
    st.caption(
        "La carte HTML de votre rapport : les prises de vue y sont déjà "
        "placées, et les directions corrigées sur fond satellite sont reprises "
        "telles quelles. Le rapport lui-même n'est pas conservé."
    )
    fichier_carte = st.file_uploader(
        "Carte du rapport de visite (.htm ou .html)",
        type=["htm", "html"],
        accept_multiple_files=False,
        key="carte_photos_geoloc",
        label_visibility="collapsed",
    )

if fichier_carte is not None and emprise_cloturee_du_projet() is not None:
    octets_carte = fichier_carte.getvalue()
    try:
        carte_rapport = _carte_photos_lue(octets_carte)
    except ErreurDP as erreur:
        st.error(f"{type(erreur).__name__} : {erreur}", icon="🚫")
    else:
        with st.expander(
            f"« {carte_rapport.titre} » — {len(carte_rapport.points)} prise(s) "
            "de vue : choisissez celles à verser au projet",
            expanded=True,
        ):
            st.caption(
                "Cochez les photographies à verser. Leur pièce se choisit "
                "ensuite dans le tableau, avec celles que vous avez déposées — "
                "la distance au site en propose une."
            )
            emprise_site = emprise_cloturee_du_projet()
            a_verser = {}
            # Cinq par ligne : la vignette sert à reconnaître une
            # photographie, pas à la juger, et une visite en compte vingt-cinq.
            for depart in range(0, len(carte_rapport.points), VIGNETTES_PAR_LIGNE):
                for colonne, point in zip(
                    st.columns(VIGNETTES_PAR_LIGNE),
                    carte_rapport.points[depart : depart + VIGNETTES_PAR_LIGNE],
                ):
                    with colonne:
                        vignette = _vignette_du_rapport(
                            octets_carte, point.rang_fichier
                        )
                        if vignette is not None:
                            st.image(vignette, width="stretch")
                        st.caption(f"**{point.numero}.** {point.nom}")
                        propose = _piece_proposee(point, emprise_site)
                        a_verser[point.identifiant] = (
                            propose
                            if st.checkbox(
                                "Verser",
                                key=f"verser_{point.identifiant}",
                                help="La photographie rejoint le tableau du "
                                "projet. Sa pièce s'y choisit, et se corrige.",
                            )
                            else AFFECTATIONS[0]
                        )
                        st.caption(f"↳ {propose} d'après sa distance au site")

            cochees = [c for c in a_verser.values() if c != AFFECTATIONS[0]]
            if st.button(
                f"Verser ces {len(cochees)} photographie(s) au projet"
                if cochees
                else "Verser les photographies cochées au projet",
                width="stretch",
                disabled=not cochees,
                help="Les images cochées sont copiées dans le dossier du "
                "projet, avec la position et la direction que le rapport leur "
                "donne. Le rapport lui-même n'est pas conservé.",
            ):
                reprises = _reprendre_du_rapport(
                    _nom_dossier(commune), octets_carte, carte_rapport, a_verser
                )
                if reprises:
                    st.success(
                        f"{reprises} photographie(s) versées au projet, avec "
                        "leur point de vue."
                    )
                    st.rerun()
                else:
                    st.info("Aucune photographie cochée : rien n'a été versé.")
elif fichier_carte is not None:
    st.warning(
        "Le plan du bureau d'études doit être importé avant de reprendre un "
        "rapport : sans emprise clôturée, rien ne distingue l'environnement "
        "proche du paysage lointain.",
        icon="⚠️",
    )
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
        # Voir la reprise d'un rapport : un cap connu fait un cône, et la ligne
        # dit qu'il sort de l'EXIF sans avoir été regardé. La boussole d'un
        # téléphone se trompe de 10 à 20°, ce que le chef de projet sait, et
        # viser reste à un clic.
        vue["cap_confirme"] = True
        vue["cap_verifie"] = False
    if metadonnees.avertissements:
        vue["exif_message"] = " ".join(metadonnees.avertissements)
        vue["exif_sans_position"] = any(
            MARQUE_SANS_POSITION in message
            for message in metadonnees.avertissements
        )


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
    if vue.get("cap_deg") is None:
        return f"{origine}, sans direction"
    direction = f"{origine}, visée {vue['cap_deg']:.0f}°"
    if vue.get("cap_verifie"):
        return direction
    # Le cône est dessiné quand même — c'est l'arbitrage du 26/09/2026 — mais
    # une direction qui n'a jamais été regardée reste une direction de boussole
    # de téléphone, à 10 ou 20° près. Le dire, et laisser viser.
    return f"{direction} d'après l'appareil, jamais vérifiée"


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


#: Part écartée sous laquelle il n'y a rien à déplacer : le rognage tient alors
#: à l'arrondi du pixel. Le seuil n'est pas zéro parce qu'un rapport se calcule
#: en flottants et tombe rarement juste.
RIEN_A_ROGNER = 0.005

#: Largeur de l'aperçu cliquable, en pixels. Assez grand pour qu'on voie ce que
#: le cadre retient, assez petit pour que l'image traverse vite.
LARGEUR_APERCU_PX = 460

#: Ce que la part écartée garde de sa luminosité sur l'aperçu. Assez sombre pour
#: que le cadre saute aux yeux, assez claire pour qu'on voie ce qu'on perd — et
#: c'est bien là-dessus qu'on décide de le perdre.
VOILE_HORS_CADRE = 0.35

#: Épaisseur du trait du cadre, en part de la plus petite dimension de l'aperçu.
TRAIT_DU_CADRE = 0.006


def _dessiner_le_cadre(source, rapport: float, cadrage: float):
    """L'image entière, la part gardée en clair, le reste assombri.

    « Il faudrait qu'on voie le cadre au bon format bouger sur l'image pour
    pouvoir sélectionner la partie que l'on garde » (retour d'usage du
    23/09/2026). L'aperçu ne montrait que le résultat du rognage : on voyait ce
    qui restait, jamais ce qu'on perdait ni de combien on pouvait encore
    glisser.

    Le cadre vient de `fenetre_de_cadrage`, la fonction même que la planche
    emploie : les deux ne peuvent pas diverger.
    """
    from dp_socle.planches.photographies import fenetre_de_cadrage
    from PIL import Image, ImageDraw

    image = source.convert("RGB")
    # Réduite d'abord, et de loin le geste qui compte. Le cadre se dessinait
    # sur l'image pleine — 4 032 px pour une photographie de visite — puis
    # Streamlit la renvoyait entière au navigateur, qui l'affichait à 460 px.
    # Mesuré le 26/09/2026 sur une photographie de 12 Mpx : 35 Mo transmis par
    # image et par exécution du script, contre 18 Ko une fois réduite. Avec six
    # photographies à l'écran, c'est ce qui figeait la page plusieurs secondes
    # à chaque geste.
    if image.width > LARGEUR_APERCU_PX:
        image.thumbnail((LARGEUR_APERCU_PX, image.height), Image.LANCZOS)
    boite, _ = fenetre_de_cadrage(image.size, rapport, (cadrage, cadrage))
    # La part écartée, assombrie sur place : composer une couche noire
    # semi-opaque puis remettre la fenêtre par-dessus coûte moins qu'un masque.
    voilee = Image.blend(image, Image.new("RGB", image.size, (0, 0, 0)),
                         1.0 - VOILE_HORS_CADRE)
    gauche, haut, droite, bas = (int(round(v)) for v in boite)
    voilee.paste(image.crop((gauche, haut, droite, bas)), (gauche, haut))

    trait = max(2, int(round(min(image.size) * TRAIT_DU_CADRE)))
    dessin = ImageDraw.Draw(voilee)
    dessin.rectangle(
        (gauche, haut, droite - 1, bas - 1), outline=(255, 255, 255), width=trait
    )
    return voilee


@st.cache_data(show_spinner=False, max_entries=24)
def _apercu_recadre(cle: tuple, octets: bytes, rapport: float, cadrage: float):
    """La vignette telle que la planche la portera, rognage compris.

    Bornée à vingt-quatre entrées : une image décodée pèse quelques mégaoctets,
    et le cache de Streamlit est global à toutes les sessions.
    """
    import io as _io

    from dp_socle.planches.photographies import fenetre_de_cadrage
    from PIL import Image

    with Image.open(_io.BytesIO(octets)) as source:
        image = _dessiner_le_cadre(source, rapport, cadrage)
        _, perte = fenetre_de_cadrage(source.size, rapport, (cadrage, cadrage))
    return image, perte



def _cadrage_depuis_le_clic(taille, rapport: float, clic: dict) -> float | None:
    """Le décalage qui centre le cadre sur le point cliqué, ou None si inutile.

    `taille` est celle de l'aperçu affiché, et `clic` porte ses coordonnées :
    le composant les rend dans l'image telle qu'elle est montrée, pas dans le
    fichier d'origine. Le rapport, lui, ne dépend pas de l'échelle.

    Le rognage ne touche qu'un axe — la largeur d'une photographie plus
    panoramique que son emplacement, sa hauteur sinon — et c'est sur celui-là
    que le clic agit. Un clic sur l'autre axe ne veut rien dire et ne change
    rien.
    """
    largeur, hauteur = taille
    if largeur / hauteur > rapport:
        gardee = hauteur * rapport
        libre = largeur - gardee
        position = clic.get("x")
    else:
        gardee = largeur / rapport
        libre = hauteur - gardee
        position = clic.get("y")
    if libre <= 0 or position is None:
        return None
    # `fenetre_de_cadrage` pose le bord de la fenêtre à `libre * (0,5 + cadrage)` :
    # pour que son milieu tombe sur le clic, il faut résoudre pour le cadrage.
    cadrage = (position - gardee / 2.0) / libre - 0.5
    return max(-0.5, min(0.5, cadrage))


def _apercu_cliquable(code: str, fichier, rapport: float, vue: dict) -> float | None:
    """L'aperçu avec son cadre, qui se replace là où l'on clique.

    Rend la part écartée, ou None si l'image ne s'ouvre pas.

    Le curseur qui servait avant demandait des essais-erreurs : on le bougeait,
    on attendait le rerun, et on découvrait où le cadre était allé. Ici le
    cadre va où l'on montre — un clic, un seul rerun (retour d'usage du
    24/09/2026).
    """
    from streamlit_image_coordinates import streamlit_image_coordinates

    try:
        octets = (
            Path(fichier.chemin).read_bytes()
            if isinstance(fichier, _PhotoReprise)
            else fichier.getvalue()
        )
        image, perte = _apercu_recadre(
            (fichier.name, len(octets)), octets, rapport, vue.get("cadrage", 0.0)
        )
    except (OSError, ValueError) as erreur:
        st.caption(f"⚠️ aperçu indisponible ({erreur})")
        return None

    if perte < RIEN_A_ROGNER:
        # Rien à déplacer : l'image ne se clique pas, et le dire vaut mieux
        # qu'offrir un geste sans effet.
        st.image(image, width="stretch")
        return perte

    clic = streamlit_image_coordinates(
        image,
        width=LARGEUR_APERCU_PX,
        key=f"cadre_{code}_{fichier.name}",
        cursor="crosshair",
        # PNG sans compression par défaut : 465 Ko pour une vignette que le
        # JPEG rend en 18 Ko, à l'œil identique sur un aperçu de cadrage.
        image_format="JPEG",
        jpeg_quality=80,
    )
    if clic is not None and clic != vue.get("dernier_clic_cadre"):
        # `streamlit_image_coordinates` rend le dernier clic tant que le
        # composant vit, et non « un clic vient d'avoir lieu » — le même piège
        # que `last_clicked` sur la carte. Sans cette mémoire, le cadrage se
        # rejouerait à chaque exécution du script.
        vue["dernier_clic_cadre"] = clic
        largeur_affichee = LARGEUR_APERCU_PX
        hauteur_affichee = largeur_affichee * image.height / image.width
        cadrage = _cadrage_depuis_le_clic(
            (largeur_affichee, hauteur_affichee), rapport, clic
        )
        if cadrage is not None and cadrage != vue.get("cadrage"):
            vue["cadrage"] = cadrage
            st.rerun()
    return perte


# ---------------------------------------------------------------------------
# Les photographies entrent ici, par deux portes et dans un seul tableau
# ---------------------------------------------------------------------------
#
# L'écran présentait deux blocs qui faisaient la même chose sans le dire : le
# rapport de visite avec une liste déroulante par vignette, les fichiers avec
# trois dépôts séparés — un par pièce. Même décision, deux gestes différents, et
# rien ne disait qu'on pouvait les combiner. Or une DP 6 a besoin des deux :
# l'image brute peut venir du rapport, le photomontage vient forcément du
# disque. « Pas très clair la différence entre l'ajout des photos avec le
# rapport HTML et l'ajout en simple clic-drop » (retour d'usage du 22/09/2026).
#
# Les deux portes versent donc dans le même tableau, où chaque photographie dit
# à quelle pièce elle appartient. Le contrat interne ne change pas : la suite de
# la page reçoit toujours un dict `{code de pièce: [fichiers]}`, composé ici à
# partir de ce que le chef de projet a choisi.

#: Ce qu'une photographie peut devenir. « À choisir » fait le défaut : une
#: pièce proposée d'emblée ferait partir au dossier ce qu'on n'a pas décidé.
SANS_PIECE = "À choisir"
PIECES_AU_CHOIX = (SANS_PIECE, "DP 6", "DP 7", "DP 8", "Ne pas retenir")

#: Nombre de photographies attendu par pièce : un minimum et un maximum. DP 6
#: décline deux ou trois volets d'un même point de vue ; DP 7 et DP 8 en portent
#: exactement deux, et leur planche a deux emplacements fixes.
COMPTE_ATTENDU = {"DP 6": (2, 3), "DP 7": (2, 2), "DP 8": (2, 2)}


def _pieces_choisies() -> dict:
    """La pièce de chaque photographie, par nom de fichier.

    En session : un choix doit survivre au redéploiement de la page, et le nom
    du fichier est le seul identifiant qui traverse les exécutions.
    """
    return st.session_state.setdefault("piece_de_la_photo", {})


def _piece_choisie(nom: str) -> str:
    return _pieces_choisies().get(nom, SANS_PIECE)


def _fichiers_repris() -> list:
    """Les photographies déjà versées d'un rapport, toutes pièces confondues.

    Elles n'ont pas de dépôt à l'écran — ce sont des fichiers déjà écrits — et
    rejoignent les autres dans le tableau commun : « rien ne les distingue une
    fois écrites ».
    """
    return [
        _PhotoReprise(nom, chemin)
        for par_nom in _photos_reprises().values()
        for nom, chemin in sorted(par_nom.items())
    ]


def _reprises_a_ranger() -> None:
    """Donne sa pièce à chaque photographie versée d'un rapport.

    Le versement la connaît déjà — c'est la case cochée dans la galerie — et
    la pose ici pour que le tableau commun la traite comme n'importe quelle
    autre. Une pièce déjà choisie à la main n'est pas écrasée : corriger une
    affectation ne doit pas être défait au prochain passage.
    """
    choisies = _pieces_choisies()
    for code, par_nom in _photos_reprises().items():
        for nom in par_nom:
            choisies.setdefault(nom, code)


def _sans_doublon(fichiers) -> list:
    """Une ligne par nom de fichier, la première rencontrée.

    Deux fichiers de même nom s'écrasent sur le disque, et le message qui le
    dit est juste au-dessus : le tableau n'a pas à en montrer deux lignes, dont
    les boutons porteraient les mêmes clés — Streamlit les refuse. Le cas se
    présente aussi quand une photographie versée d'un rapport est redéposée à
    la main.
    """
    vus = set()
    retenus = []
    for fichier in fichiers:
        if fichier.name in vus:
            continue
        vus.add(fichier.name)
        retenus.append(fichier)
    return retenus


def _photos_par_piece(fichiers) -> dict:
    """Les fichiers rangés par pièce, dans la forme que le reste de la page attend.

    Déposées et reprises d'un rapport s'y mêlent : rien ne les distingue une
    fois écrites, et ce qui suit n'a pas à savoir d'où elles viennent. Les PDF
    sont écartés — ils se joignent au dossier sans aller sur une planche.
    """
    par_piece = {code: [] for code in PIECES_PHOTOS}
    for fichier in fichiers or []:
        if fichier.name.lower().endswith(".pdf"):
            continue
        code = _piece_choisie(fichier.name)
        if code in par_piece:
            par_piece[code].append(fichier)
    return par_piece


def _compte_des_pieces(photos_par_piece: dict) -> list:
    """Où en est chaque pièce, dans l'ordre du dossier.

    Rend des triplets `(code, nombre, message)` — le message est vide quand le
    compte est bon. Le contrôle vivait en avertissements dispersés sous chaque
    pièce ; il se lit ici d'un coup, avant de descendre placer les prises de vue.
    """
    etat = []
    for code in PIECES_PHOTOS:
        nombre = len(photos_par_piece.get(code) or [])
        minimum, maximum = COMPTE_ATTENDU[code]
        if nombre < minimum:
            message = f"il en manque {minimum - nombre}"
        elif nombre > maximum:
            message = f"{nombre - maximum} de trop"
        else:
            message = ""
        etat.append((code, nombre, message))
    return etat


def _octets_de(fichier) -> bytes:
    """Le contenu d'une photographie, déposée ou déjà écrite sur le disque.

    Streamlit ne sait rien faire d'un `_PhotoReprise` : il attend des octets,
    un chemin ou une image Pillow. Lui passer l'objet levait
    « '_PhotoReprise' object has no attribute 'format' » dès qu'une
    photographie versée d'un rapport devait s'afficher (25/09/2026).
    """
    if isinstance(fichier, _PhotoReprise):
        return Path(fichier.chemin).read_bytes()
    return fichier.getvalue()


@st.cache_data(show_spinner=False, max_entries=24)
def _vignette_seule(cle: tuple, octets: bytes):
    """L'image réduite à la largeur de l'aperçu, sans cadre.

    Même motif que `_apercu_recadre` : transmettre la photographie entière au
    navigateur pour l'afficher à 460 px coûtait des mégaoctets par exécution du
    script (mesuré le 26/09/2026).
    """
    import io as _io

    from PIL import Image

    with Image.open(_io.BytesIO(octets)) as source:
        image = source.convert("RGB")
        if image.width > LARGEUR_APERCU_PX:
            image.thumbnail((LARGEUR_APERCU_PX, image.height), Image.LANCZOS)
    return image


def _montrer_l_image(fichier) -> None:
    """L'image telle quelle, tant qu'aucune pièce ne lui impose de format."""
    try:
        octets = _octets_de(fichier)
        st.image(_vignette_seule((fichier.name, len(octets)), octets))
    except (OSError, ValueError) as erreur:
        st.caption(f"⚠️ aperçu indisponible ({erreur})")


def _changer_de_piece(nom: str, avant: str, apres: str) -> None:
    """Déplace une photographie d'une pièce à l'autre, sans perdre son travail.

    Position, direction et cadrage sont attachés à la photographie, pas à la
    pièce : les reperdre en corrigeant une affectation ferait tout replacer.
    """
    _pieces_choisies()[nom] = apres
    if avant not in PIECES_PHOTOS:
        return
    vue = _vues_photo().get(avant, {}).pop(nom, None)
    if vue is not None and apres in PIECES_PHOTOS:
        _vues_photo().setdefault(apres, {})[nom] = vue


# ---------------------------------------------------------------------------
# Les prises de vue, saisies sur la carte de la section 2
# ---------------------------------------------------------------------------
#
# Le bloc se remplit ici, où les photographies viennent d'être déposées, mais
# s'affiche là-haut, sous la carte : c'est elle qui reçoit les clics. Un seul
# aller-retour, et toutes les prises se placent d'affilée.


def _ligne_de_choix(fichier, rapport: float, plusieurs_vues: bool) -> None:
    """Une photographie dans le tableau d'entrée : sa pièce, son cadre, son volet.

    Ce qui se décide ici tient à l'image seule. Le placement et la visée, qui
    demandent la carte, se font plus bas, sous elle.
    """
    # Le seuil de la planche, et non un second : deux seuils construits chacun
    # de leur côté finissent par diverger, la voirie l'a montré le 19/09/2026.
    from dp_socle.planches.photographies import ROGNAGE_SIGNALE

    code = _piece_choisie(fichier.name)
    vue = _vue_photo(code, fichier.name) if code in PIECES_PHOTOS else {}

    apercu, champs = st.columns([2, 4])
    with apercu:
        if code in PIECES_PHOTOS:
            perte = _apercu_cliquable(code, fichier, rapport, vue)
        else:
            # Sans pièce, pas de format d'emplacement : on montre l'image telle
            # qu'elle est, et le cadre arrivera avec la pièce.
            perte = None
            _montrer_l_image(fichier)
    with champs:
        st.write(f"**{fichier.name}**")
        choisie = st.selectbox(
            "Pièce",
            options=PIECES_AU_CHOIX,
            index=PIECES_AU_CHOIX.index(code)
            if code in PIECES_AU_CHOIX
            else 0,
            key=f"piece_de_{fichier.name}",
        )
        if choisie != code:
            _changer_de_piece(fichier.name, code, choisie)
            st.rerun()

        if code == "DP 6":
            vue["volet"] = st.selectbox(
                "Ce que l'image montre",
                options=list(range(len(INTITULES_DP6))),
                index=min(vue.get("volet", 0), len(INTITULES_DP6) - 1),
                format_func=lambda rang: f"{rang + 1}. {INTITULES_DP6[rang]}",
                key=f"volet_de_{fichier.name}",
            )
            if plusieurs_vues:
                vue["vue"] = st.selectbox(
                    "Point de vue",
                    options=[chr(ord("A") + i) for i in range(4)],
                    index=[chr(ord("A") + i) for i in range(4)].index(
                        vue.get("vue", "A")
                    ),
                    key=f"vue_de_{fichier.name}",
                    help="Une planche par point de vue. Les volets d'une même "
                    "vue partagent leur position : c'est la même prise.",
                )
            else:
                vue["vue"] = "A"

        if perte is not None and perte < RIEN_A_ROGNER:
            st.caption(
                "Rien à rogner : cette photographie a déjà le format de son "
                "emplacement. Elle partira entière."
            )
        elif perte is not None:
            st.caption(
                f"**Cliquez sur l'image** pour choisir ce que le cadre garde. "
                f"Il laisse de côté {perte:.0%} de la photographie"
                + (
                    " — c'est beaucoup. Une insertion paysagère se photographie "
                    "en paysage large."
                    if perte >= ROGNAGE_SIGNALE
                    else "."
                )
            )
        elif code == SANS_PIECE:
            st.caption(
                "Choisissez sa pièce : le cadre de la planche s'affichera "
                "alors sur l'image, et se réglera d'un clic."
            )



#: Nombre d'emplacements de chaque pièce photographique, qui fixe le format des
#: images : 3,11:1 pour les trois volets d'une DP 6, 1,92:1 pour les deux
#: photographies d'une DP 7 ou d'une DP 8. Ce sont les bandeaux du dossier de
#: référence, et ils ne dépendent pas de ce qu'on y dépose.
EMPLACEMENTS_DE_LA_PIECE = {"DP 6": 3, "DP 7": 2, "DP 8": 2}


@st.cache_data(show_spinner=False)
def _rapport_des_emplacements(code: str) -> float:
    """Largeur sur hauteur de l'emplacement que la planche donnera aux images.

    Le même calcul que `planches.photographies`, et par la même fonction : ce
    que l'écran montre est ce que la planche portera. Il ne dépend plus des
    images depuis le 23/09/2026 — voir l'en-tête de ce module-là pour ce que ce
    choix coûte et pourquoi il a été fait.

    Caché parce qu'il construit une planche vide pour lire sa zone de dessin, et
    que Streamlit rejoue le script à chaque interaction.
    """
    from dp_socle.planche import Planche
    from dp_socle.planches.photographies import rapport_de_l_emplacement

    return rapport_de_l_emplacement(
        Planche(titre="mesure", numero=code, projet="mesure", date="01/01/2026"),
        EMPLACEMENTS_DE_LA_PIECE[code],
    )






def _controler_le_compte(code: str, fichiers) -> None:
    """Dit, avant de générer, si DP 7 ou DP 8 n'a pas son compte.

    Les deux pièces portent **exactement deux** photographies, comme le dossier
    de référence : la planche a deux emplacements fixes, et une seule prise de
    vue y laisse un cadre vide — constaté sur une planche produite le
    23/09/2026. Le refus tombait à la génération ; il se dit ici, où la
    photographie manquante peut encore être déposée.
    """
    from dp_socle.planches.dp7_environnement_proche import PRISES_ATTENDUES

    places = [f for f in fichiers if _vue_photo(code, f.name).get("x") is not None]
    if len(places) == PRISES_ATTENDUES:
        return
    if not places:
        # Rien de placé : chaque ligne le dit déjà pour elle-même, et le
        # répéter ici ferait du bruit sur un écran qu'on vient d'ouvrir.
        return
    st.warning(
        f"**{code} : {len(places)} photographie(s) placée(s)**, pour "
        f"{PRISES_ATTENDUES} attendues. "
        + (
            "Déposez-en une seconde et placez-la."
            if len(places) < PRISES_ATTENDUES
            else "La planche n'a que deux emplacements : retirez le surplus."
        )
        + " **En l'état, la planche ne sera pas produite.**",
        icon="⚠️",
    )


def _controler_les_volets_dp6(fichiers) -> None:
    """Dit, avant de générer, quelles vues DP 6 n'iront pas au dossier.

    Une insertion paysagère compare l'état actuel et le projet : il faut donc
    **deux** images par vue, l'image brute et son photomontage. Une vue qui n'en
    a qu'une est refusée à la composition, jamais complétée en silence.

    Ce refus était juste, mais il tombait à la génération, au bout du parcours,
    dans le rapport : « DP 6 n'est pas dedans, j'avais pourtant choisi une image
    brute et ajouté un angle de prise de vue » (22/09/2026). Il se dit
    maintenant sous la carte, où la position qui manque peut être posée.

    **Sous la carte, et non dans le tableau d'entrée.** Ce qui se compte ici,
    ce sont les photographies *placées* — une vue n'entre au projet qu'avec son
    point de vue. Dans le tableau d'entrée, où rien n'est encore placé, le
    contrôle reprochait une vue incomplète à qui venait d'en déposer les deux
    images : « j'ai l'alerte alors que j'ai bien mis 2 photos pour DP 6 »
    (25/09/2026). Le compteur du tableau, lui, compte les images déposées.
    """
    par_vue = {}
    sans_position = {}
    for fichier in fichiers:
        vue = _vue_photo("DP 6", fichier.name)
        lettre = vue.get("vue", "A")
        par_vue.setdefault(lettre, []).append(fichier.name)
        # Seule l'image brute porte la position : les autres volets en
        # héritent, et n'ont rien à placer.
        if vue.get("volet", 0) == 0 and vue.get("x") is None:
            sans_position[lettre] = fichier.name

    if not par_vue:
        return
    for lettre, noms in sorted(par_vue.items()):
        volets = [_vue_photo("DP 6", nom).get("volet", 0) for nom in noms]
        doubles = sorted({v for v in volets if volets.count(v) > 1})
        if doubles:
            st.warning(
                f"**Vue {lettre} : deux photographies sur le même cadre** "
                + ", ".join(f"« {INTITULES_DP6[v]} »" for v in doubles)
                + ". La planche a un cadre par volet : l'une des deux en "
                "chasserait l'autre. Corrigez « Ce que l'image montre ».",
                icon="⚠️",
            )
        if lettre in sans_position:
            st.warning(
                f"**Vue {lettre} : son image brute n'est pas placée** "
                f"({sans_position[lettre]}). C'est elle qui porte le point de "
                "vue, dont les autres volets héritent : sans elle, la planche "
                "n'a rien à repérer. **En l'état, elle ne sera pas produite.**",
                icon="⚠️",
            )
        elif len(noms) == 1:
            st.warning(
                f"**Vue {lettre} : une seule photographie** "
                f"({noms[0]}). DP 6 compare l'état actuel et le projet — il "
                "faut au moins deux images pour cette vue : l'image brute et "
                "son photomontage. Déposez le photomontage en section 3, "
                f"placez-le, et donnez-lui la vue {lettre}. **En l'état, la "
                "planche ne sera pas produite.**",
                icon="⚠️",
            )
        elif len(noms) > len(INTITULES_DP6):
            st.warning(
                f"**Vue {lettre} : {len(noms)} photographies** pour une même "
                f"vue, alors que la pièce en décline {len(INTITULES_DP6)} au plus "
                f"({', '.join(INTITULES_DP6)}). Une vue de plus est une planche de "
                f"plus : donnez la lettre suivante aux images en trop.",
                icon="⚠️",
            )


def _ligne_de_prise(code: str, fichier) -> None:
    """Une photographie sous la carte : où elle est, ce qu'elle regarde.

    Ne reste ici que ce qui demande la carte. La pièce, le volet et le cadrage
    se décident en section 3, dans le tableau d'entrée, où l'on voit l'image en
    grand — « une partie choix des photos », puis le placement (retour d'usage
    du 22/09/2026).
    """
    vue = _vue_photo(code, fichier.name)
    if code == "DP 6" and vue.get("volet", 0) > 0:
        # Un photomontage n'a été nulle part : il montre le **même** point de
        # vue que l'image brute, dont il hérite position et direction. Lui
        # demander de se placer, c'est demander deux fois la même chose —
        # « elle hérite de la position de l'image brute » (26/09/2026).
        st.write(f"**{fichier.name}**")
        st.caption(
            f"↳ {INTITULES_DP6[vue['volet']].lower()} — hérite du point de vue "
            "de l'image brute de sa vue, puisque c'est la même prise."
        )
        return
    libelle, placer, viser = st.columns([4, 1, 1])
    with libelle:
        st.write(f"**{fichier.name}**")
        st.caption(_etat_de_la_prise(vue))
        # Le reproche de n'avoir pas de position se tait dès qu'elle est
        # posée : il s'affichait sous une ligne annonçant « placée sur la
        # carte, visée 215° » (retour d'usage du 24/09/2026). Les autres
        # avertissements de l'EXIF, eux, restent vrais quoi qu'on fasse.
        if vue.get("exif_message") and not (
            vue.get("exif_sans_position") and vue.get("x") is not None
        ):
            st.caption(f"⚠️ {vue['exif_message']}")
    with placer:
        if st.button("📍 Placer", key=f"placer_{code}_{fichier.name}",
                     width="stretch"):
            _armer_sur_photo("placer_vue", code, fichier.name)
            st.rerun()
        # Sous le bouton, et non dans la ligne d'état : « si une photo a déjà
        # été placée, alors l'écrire sous le bouton pour facilement
        # l'identifier » (retour d'usage du 24/09/2026).
        st.caption("✅ placée" if vue.get("x") is not None else "⬜ à placer")
    with viser:
        if st.button("🎯 Viser", key=f"viser_{code}_{fichier.name}",
                     disabled=vue.get("x") is None, width="stretch"):
            _armer_sur_photo("viser_vue", code, fichier.name)
            st.rerun()
        if vue.get("cap_deg") is None:
            st.caption("⬜ à viser")
        elif vue.get("cap_verifie"):
            st.caption(f"✅ visée {vue['cap_deg']:.0f}°")
        else:
            st.caption(f"✅ {vue['cap_deg']:.0f}° — de l'appareil")


def _saisir_les_prises_de_vue(photos_par_piece: dict) -> None:
    """Liste les photographies déposées, leur état, et les deux gestes.

    Affichée sous la carte, dans la section 3 bis : les photographies sont
    déposées juste au-dessus, et c'est là qu'on les place. Elle remplissait un
    conteneur réservé en section 2 tant que la carte y vivait — un aller-retour
    par photographie, que le déplacement de la carte a supprimé.
    """
    _oublier_les_photos_remplacees(photos_par_piece)
    st.markdown("### Les prises de vue des pièces photographiques")
    # Les photographies reprises d'un rapport comptent autant que les autres.
    # Ne compter que les dépôts faisait sortir ce bloc en annonçant « aucune
    # photographie » à un chef de projet qui venait d'en reprendre douze : ni
    # bouton pour les placer, ni curseur pour les recadrer (17/09/2026).
    par_piece = {
        code: list(photos_par_piece.get(code) or []) for code in PIECES_PHOTOS
    }
    if not any(par_piece.values()):
        st.caption(
            "Aucune photographie à placer. Ajoutez-en en section 3 — par vos "
            "fichiers ou par un rapport de visite — et donnez-leur une pièce."
        )
        return
    st.caption(
        "**📍 Placer** dit où est la photographie, **🎯 Viser** ce qu'elle "
        "regarde — les deux gestes de photos-geoloc, au même sens. Une "
        "direction non visée ne fait dessiner aucun cône : la boussole d'un "
        "téléphone se trompe de 10 à 20°, et le dossier ne porte que ce qui "
        "a été vérifié."
    )
    for code, fichiers in par_piece.items():
        if not fichiers:
            continue
        st.markdown(f"**{code}** — {piece(code).titre}")
        for fichier in fichiers:
            _ligne_de_prise(code, fichier)
        if code == "DP 6":
            _controler_les_volets_dp6(fichiers)
        else:
            _controler_le_compte(code, fichiers)


# Le tableau commun : ce que les deux portes ont versé, et la pièce de chacune.
_reprises_a_ranger()
photos_deposees = list(fichiers_photos or []) + _fichiers_repris()
toutes_les_photos = _sans_doublon(photos_deposees)
photos = _photos_par_piece(toutes_les_photos)
# Les PDF ne vont sur aucune planche, mais la page de garde doit savoir qu'on
# en a déposé un en DP 6 : sans cela elle rendrait son cadre tireté sans un mot.
pdfs_par_piece = {
    code: [
        f for f in photos_deposees
        if _piece_choisie(f.name) == code and f.name.lower().endswith(".pdf")
    ]
    for code in PIECES_PHOTOS
}

#: Les pièces où deux fichiers portent le même nom, avec les noms en cause.
#:
#: Ils s'écrasent sur le disque — la cible est nommée par le nom du fichier — et
#: le second est perdu sans un mot. Le chef de projet renomme, ou retire : ce
#: n'est pas à l'outil de choisir lequel des deux survit.
photos_en_double = {}
for code in PIECES_PHOTOS:
    noms_deposes = [
        fichier.name
        for fichier in photos_deposees
        if _piece_choisie(fichier.name) == code
    ]
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



if toutes_les_photos:
    st.markdown("### Les photographies du projet")
    st.caption(
        "Une ligne par photographie, d'où qu'elle vienne. Dites à quelle pièce "
        "chacune appartient, et cliquez sur l'image pour choisir ce que son "
        "cadre garde. Le placement et la direction se règlent plus bas, sur la "
        "carte."
    )
    compte = _compte_des_pieces(photos)
    colonnes_compte = st.columns(len(compte))
    for colonne, (code, nombre, manque) in zip(colonnes_compte, compte):
        minimum, maximum = COMPTE_ATTENDU[code]
        attendu = f"{minimum}" if minimum == maximum else f"{minimum} à {maximum}"
        colonne.metric(
            code,
            f"{nombre} / {attendu}",
            delta=manque or "au compte",
            delta_color="inverse" if manque else "off",
        )

    plusieurs_vues = len(photos["DP 6"]) > len(INTITULES_DP6)
    for fichier in toutes_les_photos:
        code = _piece_choisie(fichier.name)
        if not isinstance(fichier, _PhotoReprise) and code in PIECES_PHOTOS:
            _lire_exif_une_fois(code, fichier)
        rapport = (
            _rapport_des_emplacements(code) if code in PIECES_PHOTOS else 1.5
        )
        _ligne_de_choix(fichier, rapport, plusieurs_vues)
        st.divider()

else:
    st.caption(
        "Aucune photographie pour l'instant. Déposez vos fichiers, ou la carte "
        "d'un rapport de visite — les deux se retrouvent dans le même tableau."
    )

# La page de garde prend l'insertion paysagère : c'est la vue du projet fini,
# et c'est elle que le dossier de référence met en couverture. Une seule le
# plus souvent — on ne demande alors rien — mais le cas de plusieurs vues
# existe, et il faut pouvoir désigner celle qui monte en couverture.
insertions = list(photos["DP 6"])
pdfs_insertion = pdfs_par_piece["DP 6"]
image_garde = None
if len(insertions) == 1:
    image_garde = insertions[0]
elif len(insertions) > 1:
    noms = [fichier.name for fichier in insertions]
    retenu = st.radio(
        "Insertion paysagère à mettre en page de garde",
        options=noms,
        index=0,
        horizontal=True,
    )
    image_garde = insertions[noms.index(retenu)]

if image_garde is not None:
    # Une vignette, et seulement celle qui monte en couverture. La mosaïque de
    # toutes les insertions faisait doublon avec le tableau juste au-dessus,
    # qui les montre déjà en grand : « elle est énorme et ce n'est pas utile »
    # (retour d'usage du 25/09/2026).
    try:
        octets_garde = _octets_de(image_garde)
        st.image(
            _vignette_seule((image_garde.name, len(octets_garde)), octets_garde),
            caption=f"Page de garde : {image_garde.name}",
            width=LARGEUR_VIGNETTE_COUVERTURE_PX,
        )
    except (OSError, ValueError) as erreur:
        st.caption(f"⚠️ aperçu de la couverture indisponible ({erreur})")
elif not insertions:
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


st.divider()
st.subheader("3 bis. La carte : placer et viser les prises de vue")

# La carte sert deux gestes, à deux moments du parcours, et se tient donc à deux
# endroits — jamais aux deux à la fois.
#
# Ici, sous les dépôts, elle sert à placer les prises de vue. Tant qu'elle
# vivait dans la seule section 2, le chef de projet déposait ses photographies
# puis remontait pour les placer — un aller-retour par photographie, signalé à
# l'usage le 17/09/2026.
#
# Avant la validation, elle se tient dans la section 2, où la coupe se règle :
# « il faudra d'abord la coupe, puis ensuite les photos » (19/09/2026). La
# validation libérait tout d'un coup, et l'annonce « Tracez sur la carte »
# s'affichait alors qu'aucune carte n'existait.
#
# Les deux cartes ne portent pas tout à fait la même chose : celle de la coupe
# garde les arbres existants, que `dp3_coupes` dessine à 8 m quand la coupe les
# traverse ; celle des prises de vue les laisse — voir
# `CATEGORIES_HORS_CARTE_DES_VUES`.

if (
    import_be_courant is not None
    and commune.strip()
    and contrat_present
    and not carte_de_la_coupe
):
    _carte_du_plan(import_be_courant, regler_la_coupe=False)
    _saisir_les_prises_de_vue(photos)
elif import_be_courant is not None and commune.strip():
    st.caption(
        "La carte est plus haut, sous les réglages du plan : le calage ou les "
        "couches ont changé depuis la dernière validation, et c'est là qu'on en "
        "juge. Revalidez l'import pour qu'elle redescende ici, avec les prises "
        "de vue."
        if contrat_present
        else "La carte est plus haut, sous les contrôles croisés : c'est là que "
        "la coupe A-A' se règle, avant la validation. Elle redescend ici une "
        "fois l'import validé, pour placer les prises de vue."
    )
else:
    st.caption(
        "La carte s'ouvre une fois le plan du bureau d'études importé : c'est "
        "lui qui porte les tables, la clôture et l'emprise sur lesquelles se "
        "posent la coupe et les prises de vue."
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

#: Le type de chaque voirie, tranché en section 2 — au moment où l'alerte est
#: levée, et devant le croquis qui montre de quel objet il s'agit. Il se
#: demandait ici, à la toute fin : « on se demande un peu pourquoi cette
#: question arrive aussi tard » (retour d'usage du 17/09/2026).
voirie = st.session_state.get("voirie_tranchee")



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
        # Déposées et versées d'un rapport y sont déjà mêlées, et les PDF
        # écartés : `_photos_par_piece` est la seule source depuis le
        # 25/09/2026. Les réunir une seconde fois ici doublait chaque
        # photographie reprise.
        fichiers = list(photos_par_piece.get(code) or [])
        if not fichiers:
            continue
        dossier = DOSSIER_PROJETS / nom_projet / code.replace(" ", "_")
        groupes = {}
        for fichier in fichiers:
            vue = _vue_photo(code, fichier.name)
            # Pour DP 6, on regroupe avant de filtrer : les volets d'une même
            # vue **partagent** le point de vue de l'image brute, puisque c'est
            # la même prise. Un photomontage n'a été nulle part et n'a aucune
            # position à lui — l'écarter ici sortait la planche à un seul volet
            # (retour d'usage du 26/09/2026).
            if code != "DP 6" and vue.get("x") is None:
                continue
            cle = vue.get("vue", "A") if code == "DP 6" else fichier.name
            groupes.setdefault(cle, []).append((fichier, vue))

        prises = []
        for _, membres in sorted(groupes.items()):
            if code == "DP 6":
                # L'ordre des volets est celui que le chef de projet a choisi,
                # et non celui du dépôt : les cadres de la planche sont
                # « emplacement », « environnement », « mesures paysagères »,
                # dans cet ordre, et c'est le sélecteur qui le dit.
                membres.sort(key=lambda membre: membre[1].get("volet", 0))
                # Le point de vue est celui de l'image brute. Sans elle placée,
                # la vue n'a aucune position : elle ne se produit pas.
                if membres[0][1].get("x") is None:
                    continue
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
        # Le cadrage réglé sur la planche DP 6 vaut pour la couverture : c'est
        # la même photographie, et la couverture la montrait entière — donc en
        # portrait dans un cadre paysage (retour d'usage du 24/09/2026).
        cadrage_garde=(
            _vue_photo("DP 6", image_garde.name).get("cadrage", 0.0)
            if image_garde is not None
            else 0.0
        ),
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


