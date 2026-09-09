"""Interface minimale de saisie et de génération du dossier DP (lot 1 — socle).

Le formulaire écrit `projet.json`, qui reste le format pivot : une correction de
dernière minute se fait en modifiant ce fichier et en relançant la génération.
"""

from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path

import folium
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from dp_socle.environnement import etat_cairo, preparer_cairo

preparer_cairo()

# Le lot 2 (HelioScope) et le lot 2bis (plan BE) ont chacun leur aperçu, avec
# les mêmes noms de fonctions : ceux du lot 2bis sont renommés ici, plutôt que
# dans leur module, pour ne pas toucher au lot 2.
from dp_socle.apercu_be import (
    URL_TUILES_ORTHO,
    apercu_plan,
    bornes_wgs84,
    en_wgs84,
    figure_profil,
    legende_presente,
    trace_l93,
)
from dp_socle.apercu_be import cadre_apercu as cadre_apercu_be
from dp_socle.apercu_be import fond_apercu as fond_apercu_be
from dp_socle.assemblage import generer_dossier
from dp_socle.coupe import (
    controler_coherence,
    controler_terrain_embarque,
    corriger_ligne_coupe,
    coupe_enregistree,
    profil_terrain,
    reprendre_coupe,
)
from dp_socle.contrat import VOIRIES_ADMISES, decrire_voiries
from dp_socle.erreurs import ErreurCoupe, ErreurDP
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
from dp_socle.projet import Projet, identifiant_de_dossier, nom_de_projet
from dp_socle.tableau_bilan import indice_depuis_nom, indices_disponibles

DOSSIER_PROJETS = Path("projets")
DOSSIER_SORTIE = Path("sortie")

EXTENSIONS_SHAPEFILE = (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qmd")

st.set_page_config(page_title="Générateur de dossier DP", page_icon="📄", layout="wide")
st.title("Générateur de dossier DP")
st.caption(
    "Page de garde, DP 1-1 plan de situation, DP 1-2 photographie aérienne, "
    "DP 1-3 plan de cadastre. Fonds IGN Géoplateforme, Lambert 93, A3 paysage à "
    "l'échelle vraie."
)


@st.cache_resource
def _etat_cairo():
    return etat_cairo()


@st.cache_resource
def _etat_polices():
    return etat_polices()


# La bibliothèque de rendu se contrôle avant la police : sans cairo, aucune
# mesure de police n'est possible et le diagnostic typographique n'a plus de
# sens. Contrôlé ici plutôt qu'au rendu, pour ne pas échouer après le
# téléchargement de tous les fonds IGN.
cairo = _etat_cairo()
if not cairo.disponible:
    st.error(cairo.message, icon="🚫")

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
            cible.write_bytes(fichier.getbuffer())
            if fichier is retenu:
                couverture = cible
    return str(couverture) if couverture else None


def _enregistrer_fichiers(nom_projet: str, fichiers) -> Path | None:
    """Écrit les fichiers téléversés et renvoie le chemin d'emprise à utiliser."""
    if not fichiers:
        return None
    dossier = DOSSIER_PROJETS / nom_projet
    dossier.mkdir(parents=True, exist_ok=True)

    chemins = []
    for fichier in fichiers:
        cible = dossier / Path(fichier.name).name
        cible.write_bytes(fichier.getbuffer())
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
    ("cadre_apercu_be", None),
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
    """Écrit un fichier téléversé dans le dépôt du projet et rend son chemin."""
    if fichier is None:
        return None
    dossier = DOSSIER_PROJETS / _nom_depot(commune)
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / Path(fichier.name).name
    cible.write_bytes(fichier.getbuffer())
    return cible


@st.cache_data(show_spinner="Lecture des calques du DXF…")
def _calques_caches(chemin: str, taille: int, charte: str):
    """Calques du DXF, avec la catégorie proposée par la charte.

    `taille` fait partie de la clé : un DXF retéléversé sous le même nom doit
    être relu. `charte` aussi : sans elle, élargir la correspondance ne changeait
    rien à l'écran, qui continuait de servir l'appariement d'avant.
    """
    return calques_du_dxf(chemin)


@st.cache_data(show_spinner="Téléchargement de l'ortho IGN…")
def _fond_be_cache(cadre: tuple, largeur_px: int = 1100):
    return fond_apercu_be(cadre, largeur_px=largeur_px)


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
            # Le cadre aussi : il n'était calculé qu'une fois par session, et le
            # second projet importé se dessinait dans le cadre et sur l'ortho du
            # premier — un aperçu faux, à l'endroit précis où le chef de projet
            # vérifie que l'import a bien lu son plan.
            st.session_state.cadre_apercu_be = None
            emprise_cadastrale = None
            # Le nom se compose ici avec l'indice qu'on est en train
            # d'importer : `_nom_dossier` porte encore celui de l'import
            # précédent, et le premier import n'en a aucun.
            nom_importe = identifiant_de_dossier(nom_de_projet(commune, indice))
            chemin_emprise = _enregistrer_fichiers(nom_importe, fichiers_emprise)
            if chemin_emprise is not None:
                emprise_cadastrale = charger_emprise(chemin_emprise).geometrie
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
    except ErreurDP as erreur:
        st.error(f"{type(erreur).__name__} : {erreur}")


import_be_courant = st.session_state.import_be
# La commune conditionne tout ce qui suit : les contrôles s'affichent, mais la
# validation écrit, et sans commune elle n'a pas de dossier où écrire.
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

    st.markdown("### Contrôles croisés")
    _tableau_controles(import_be_courant.controles)
    for controle in import_be_courant.bloquants:
        st.error(f"{controle.libelle} — {controle.message}", icon="🚫")
    # Réservé ici, rempli une fois la coupe traitée. `avertissements` compte
    # ceux de la ligne de coupe, du profil et des contrôles de terrain, qui ne
    # sont produits que deux cents lignes plus bas : les rendre à cet endroit du
    # script les montrait avec une exécution de retard, et le chef de projet qui
    # trace sa coupe puis valide dans la foulée ne les voyait jamais.
    emplacement_avertissements = st.container()

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
    # Ligne de coupe A-A'
    # -----------------------------------------------------------------------
    st.markdown("### Ligne de coupe A-A'")
    st.caption(
        "Tracez un segment là où la coupe doit passer. Seul son **point milieu** "
        "est retenu : la direction vient de l'azimut mesuré sur les tables "
        f"({plan.azimut_tables_deg:.2f}° depuis l'est), et la ligne est étendue "
        "à toute l'emprise clôturée avec 10 m de marge."
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
    for couche, style in (
        ("tables_pv", {"color": "#0000ff", "weight": 1, "fillColor": "#97caca"}),
        ("cloture", {"color": "#ff0000", "weight": 3, "fill": False}),
    ):
        collection = en_wgs84(plan.geometries(couche))
        if collection["features"]:
            folium.GeoJson(
                collection,
                style_function=lambda _trait, style=style: style,
                name=couche,
            ).add_to(carte)
    # La coupe déjà retenue est montrée sur la carte : sans elle, l'écran
    # inviterait à retracer ce qui existe déjà.
    if st.session_state.coupe_be is not None:
        for geometrie, couleur in (
            (st.session_state.coupe_be.trace_initial, "#ff8c00"),
            (st.session_state.coupe_be.geometrie, "#000000"),
        ):
            folium.GeoJson(
                en_wgs84([geometrie]),
                style_function=lambda _trait, couleur=couleur: {
                    "color": couleur,
                    "weight": 4,
                },
                name="coupe",
            ).add_to(carte)
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

    resultat_carte = st_folium(carte, width=None, height=520, key="carte_coupe_be")
    trace = trace_l93(resultat_carte)

    if trace is not None and st.button("Corriger et relever le profil", width="stretch"):
        try:
            coupe = corriger_ligne_coupe(
                trace, plan.azimut_tables_deg, emprise_cloturee, manuel=manuel,
                tables=plan.tables,
            )
            st.session_state.coupe_be = coupe
            with st.spinner("Interrogation du RGE ALTI…"):
                st.session_state.profil_be = profil_terrain(
                    coupe,
                    fichier_altimetrie=st.session_state.get("chemin_altimetrie_be"),
                )
            import_be_courant.ligne_coupe = coupe
            import_be_courant.profil = st.session_state.profil_be
            import_be_courant.coherence = controler_coherence(
                st.session_state.profil_be, coupe, plan.tables
            )
            import_be_courant.terrain_be = controler_terrain_embarque(
                st.session_state.profil_be, coupe, plan.points_terrain, CALQUES_TERRAIN
            )
        except ErreurDP as erreur:
            st.session_state.coupe_be = None
            st.error(f"{type(erreur).__name__} : {erreur}")
    elif trace is None and st.session_state.coupe_be is None:
        st.info(
            "Aucun tracé sur la carte : utilisez l'outil ligne (icône polyligne) "
            "à gauche de la carte."
        )
    elif trace is None:
        st.caption(
            "Coupe déjà retenue, montrée sur la carte en noir avec le tracé "
            "d'origine en orange. Tracez une nouvelle ligne pour la remplacer."
        )

    with emplacement_avertissements:
        for message in import_be_courant.avertissements:
            st.warning(message, icon="⚠️")

    # -----------------------------------------------------------------------
    # Aperçu et validation
    # -----------------------------------------------------------------------
    st.markdown("### Aperçu des géométries importées")
    try:
        emprise_cadastrale = st.session_state.get("emprise_cadastrale_be")
        if st.session_state.cadre_apercu_be is None:
            st.session_state.cadre_apercu_be = cadre_apercu_be(plan, emprise_cadastrale)
        image = apercu_plan(
            plan,
            ligne_coupe=st.session_state.coupe_be,
            emprise_cadastrale=emprise_cadastrale,
            fond=_fond_be_cache(st.session_state.cadre_apercu_be),
            cadre=st.session_state.cadre_apercu_be,
        )
        st.image(image, width="stretch")
        st.caption(
            "Couleurs de la légende DP, relevées sur la planche DP 2 du dossier "
            "de référence HOCH « Les Islettes » : "
            + " · ".join(
                f"{style.libelle} ({nombre})"
                for _, style, nombre in legende_presente(plan)
            )
            + ". Jaune : emprise cadastrale. Orange : tracé initial de la coupe. "
            "Noir : coupe corrigée. Les couleurs du DXF ne sont pas reprises, "
            "les codes ACI y sont des couleurs de travail."
        )
    except ErreurDP as erreur:
        st.error(f"{type(erreur).__name__} : {erreur}")

    coupe = st.session_state.coupe_be
    profil = st.session_state.profil_be
    if coupe is not None:
        colonnes = st.columns(3)
        colonnes[0].metric("Longueur de la coupe", f"{coupe.longueur_m:.0f} m")
        colonnes[1].metric(
            "Écart redressé", f"{coupe.ecart_initial_deg:.1f}°",
            help="Angle entre le tracé initial et la perpendiculaire aux rangées.",
        )
        colonnes[2].metric(
            "Azimut de la coupe", f"{coupe.azimut_coupe_deg:.2f}° depuis l'est"
        )

    if profil is not None:
        st.image(figure_profil(profil), width="stretch")
        colonnes = st.columns(3)
        colonnes[0].metric("Dénivelée totale", f"{profil.denivelee_m:.2f} m")
        colonnes[1].metric("Altitude mini", f"{profil.altitude_min_m:.2f} m NGF")
        colonnes[2].metric("Altitude maxi", f"{profil.altitude_max_m:.2f} m NGF")
        st.caption(f"Source du profil : {profil.origine}.")
        coherence = import_be_courant.coherence
        if coherence is not None:
            (st.success if coherence.conforme else st.warning)(
                coherence.message, icon="📐" if coherence.conforme else "⚠️"
            )
        for controle in import_be_courant.terrain_be:
            (st.success if controle.conforme else st.warning)(
                controle.message, icon="📐" if controle.conforme else "⚠️"
            )
        if import_be_courant.terrain_be:
            st.caption(
                "Le profil du dossier reste celui du RGE ALTI, référence "
                "altimétrique nationale que l'instructeur peut vérifier. Les "
                "altitudes portées par le DXF le contrôlent, elles ne le "
                "remplacent pas."
            )

    st.markdown("### Validation")
    if indice_choisi is not None and indice_choisi != tableau.indice:
        st.error(
            f"La liste affiche l'indice {indice_choisi}, l'import en mémoire "
            f"est celui de {tableau.indice}. Écrire maintenant déposerait la "
            f"géométrie de {tableau.indice} dans `sortie/"
            f"{identifiant_de_dossier(nom_de_projet(commune, indice_choisi))}/`, "
            f"en écrasant ce qui s'y trouve. Recliquez sur « Importer et "
            f"contrôler ».",
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
            "Tracez et corrigez la ligne de coupe avant de valider : le lot 4 en "
            "a besoin pour la coupe DP 3."
        )
    elif st.button("Valider l'import et écrire la sortie", type="primary", width="stretch"):
        try:
            dossier_sortie = DOSSIER_SORTIE / _nom_dossier(commune)
            gpkg, parametres = import_be_courant.ecrire(dossier_sortie)
            st.success(
                f"Import validé. {gpkg} et {parametres} écrits — c'est le contrat "
                "d'entrée du lot 4."
            )
            with open(gpkg, "rb") as fichier:
                st.download_button(
                    "Télécharger geometries.gpkg",
                    data=fichier.read(),
                    file_name=f"{_nom_dossier(commune)}_geometries.gpkg",
                    mime="application/geopackage+sqlite3",
                    width="stretch",
                )
            st.code(
                json.dumps(
                    json.loads(parametres.read_text(encoding="utf-8")),
                    ensure_ascii=False,
                    indent=2,
                )[:4000],
                language="json",
            )
        except ErreurDP as erreur:
            st.error(f"{type(erreur).__name__} : {erreur}")


# ---------------------------------------------------------------------------
# Photographies et photomontages — DP 6, DP 7, DP 8
# ---------------------------------------------------------------------------

#: Les trois pièces photographiques du dossier, dans l'ordre du CERFA.
#:
#: Une ligne chacune, et non un dépôt commun : ce sont trois pièces distinctes,
#: qui ne montrent pas la même chose et ne se rangent pas au même endroit du
#: dossier. Les mélanger obligerait à les retrier à la main au moment de
#: constituer le dépôt.
PIECES_PHOTOS = ("DP 6", "DP 7", "DP 8")

st.divider()
st.subheader("3. Photographies et photomontages")
st.caption(
    "Une ligne par pièce. Elles sont conservées dans le dossier du projet ; leur "
    "assemblage au dossier et le **report de la position de prise de vue sur un "
    "plan de repérage** restent à construire — le dossier de référence en met un "
    "par vue, au 1/1 500 et au 1/2 500."
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
    # Par rangées de quatre, et non les quatre premières : la vignette manquante
    # pouvait être celle de la couverture, la seule qu'on ait besoin de voir.
    for depart in range(0, len(insertions), 4):
        rangee = insertions[depart : depart + 4]
        for colonne, fichier in zip(st.columns(len(rangee)), rangee):
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
    st.markdown(f"Projet **{libelle}** — dossier `sortie/{nom}/`")
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

    return Projet(
        nom=nom,
        commune=commune.strip(),
        code_postal=code_postal.strip(),
        date=date_projet.isoformat(),
        emprise=str(chemin_emprise),
        image_garde=chemin_image,
        libelle=libelle or None,
        voirie=voirie,
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
            st.info(
                f"Emprise : {emprise.nb_polygones} polygone(s), "
                f"{emprise.surface_m2 / 10_000:.2f} ha, CRS source {emprise.crs_source}."
            )
            with st.spinner("Téléchargement des fonds IGN et composition des planches…"):
                rapport = generer_dossier(projet, DOSSIER_SORTIE, dpi=int(dpi))

            if rapport.origine_contrat:
                st.caption(
                    f"Planches DP 2 à DP 4 dessinées depuis le contrat d'entrée "
                    f"« {rapport.origine_contrat} » de {rapport.dossier}."
                )

            for message in rapport.avertissements:
                st.warning(message, icon="⚠️")

            st.success(
                f"**{projet.libelle_affiche}** — {rapport.assemblage.name}, "
                f"{rapport.taille_mo:.1f} Mo, {len(rapport.planches)} planches. "
                f"Dossier : `{rapport.dossier}/`."
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
            with open(rapport.assemblage, "rb") as fichier:
                st.download_button(
                    f"Télécharger {rapport.assemblage.name}",
                    data=fichier.read(),
                    file_name=rapport.assemblage.name,
                    mime="application/pdf",
                    width="stretch",
                )
            for sortie in rapport.planches:
                chemin = Path(sortie.chemin)
                with open(chemin, "rb") as fichier:
                    st.download_button(
                        f"{sortie.numero} — {chemin.name}",
                        data=fichier.read(),
                        file_name=chemin.name,
                        mime="application/pdf",
                        key=f"dl_{sortie.numero}",
                    )
    except ErreurDP as erreur:
        st.error(f"{type(erreur).__name__} : {erreur}")


