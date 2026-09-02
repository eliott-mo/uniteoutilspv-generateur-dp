"""Interface minimale de saisie et de génération du dossier DP (lot 1 — socle).

Le formulaire écrit `projet.json`, qui reste le format pivot : une correction de
dernière minute se fait en modifiant ce fichier et en relançant la génération.
"""

from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path

import streamlit as st

from dp_socle.environnement import preparer_cairo

preparer_cairo()

from dp_socle.assemblage import generer_dossier
from dp_socle.erreurs import ErreurDP
from dp_socle.geometrie import charger_emprise
from dp_socle.helioscope import (
    CORRECTION_NORD_SUD_MAX_M,
    apercu_calage,
    corriger_nord_sud,
    decaler_longitude,
    ecrire_geojson,
    parametres_json,
    prepositionner,
)
from dp_socle.helioscope import importer as importer_helioscope
from dp_socle.ign import COUCHE_ORTHO, COUCHE_PLAN, DPI_DEFAUT, verifier_couches
from dp_socle.polices import etat_polices
from dp_socle.projet import Projet

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
def _etat_polices():
    return etat_polices()


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
    nom = st.text_input(
        "Identifiant du dossier", value="ALR_45_Bray-Saint-Aignan",
        help="Sert à nommer le dossier de sortie. N'apparaît pas sur les planches.",
    )
    commune = st.text_input("Commune", value="Bray-Saint-Aignan")
with colonne_droite:
    code_postal = st.text_input("Code postal", value="45460")
    date_projet = st.date_input("Date du dossier", value=_date.today())

libelle = st.text_input(
    "Nom du projet au cartouche",
    value="",
    placeholder="Nom retenu par le chef de projet — à défaut, l'identifiant du dossier",
    help="C'est ce libellé qui figure dans le cartouche des planches et sur la "
    "page de garde.",
)

st.subheader("2. Fichiers")
fichiers_emprise = st.file_uploader(
    "Emprise (ZIP du shapefile, ou .shp + .shx + .dbf + .prj)",
    type=[e.lstrip(".") for e in EXTENSIONS_SHAPEFILE] + ["zip"],
    accept_multiple_files=True,
    help="Le fichier .prj est obligatoire : sans lui le CRS est inconnu et la "
    "génération est refusée.",
)
image_garde = st.file_uploader(
    "Photomontage de la page de garde (facultatif)",
    type=["jpg", "jpeg", "png"],
    help="Occupe la moitié gauche de la page de garde. Sans image, la place "
    "reste blanche plutôt que d'afficher un cadre vide.",
)

st.subheader("3. Génération")
colonne_json, colonne_generation = st.columns(2)

if "chemin_projet_json" not in st.session_state:
    st.session_state.chemin_projet_json = None


def _construire_projet() -> Projet | None:
    if not nom.strip():
        st.error("Le nom du projet est obligatoire.")
        return None
    chemin_emprise = _enregistrer_fichiers(nom.strip(), fichiers_emprise)
    if chemin_emprise is None:
        return None

    chemin_image = None
    if image_garde is not None:
        dossier = DOSSIER_PROJETS / nom.strip()
        dossier.mkdir(parents=True, exist_ok=True)
        chemin_image = dossier / Path(image_garde.name).name
        chemin_image.write_bytes(image_garde.getbuffer())

    return Projet(
        nom=nom.strip(),
        commune=commune.strip(),
        code_postal=code_postal.strip(),
        date=date_projet.isoformat(),
        emprise=str(chemin_emprise),
        image_garde=str(chemin_image) if chemin_image else None,
        libelle=libelle.strip() or None,
    )


with colonne_json:
    if st.button("Écrire projet.json", width="stretch"):
        try:
            projet = _construire_projet()
            if projet is not None:
                projet.valider()
                chemin = projet.ecrire(DOSSIER_PROJETS / projet.nom / "projet.json")
                st.session_state.chemin_projet_json = str(chemin)
                st.success(f"Écrit : {chemin}")
                st.code(
                    json.dumps(
                        json.loads(chemin.read_text(encoding="utf-8")),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    language="json",
                )
        except ErreurDP as erreur:
            st.error(str(erreur))

with colonne_generation:
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

            for message in rapport.avertissements:
                st.warning(message, icon="⚠️")

            st.success(
                f"{rapport.assemblage} — {rapport.taille_mo:.1f} Mo, "
                f"{len(rapport.planches)} planches."
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
                    "Télécharger DP_complet.pdf",
                    data=fichier.read(),
                    file_name=f"{projet.nom}_DP_complet.pdf",
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


# ---------------------------------------------------------------------------
# Lot 2 — calepinage HelioScope
# ---------------------------------------------------------------------------

st.divider()
st.subheader("4. Calepinage HelioScope")
st.caption(
    "Import de l'export CAO HelioScope et calage géographique. Produit les "
    "géométries en Lambert 93 et les paramètres du calepinage ; ne dessine "
    "aucune planche."
)

export_helioscope = st.file_uploader(
    "Export HelioScope (le ZIP complet téléchargé depuis HelioScope)",
    type=["zip"],
    help="Celui qui contient le « Layout CAD ». Si le calque Modules est vide, "
    "l'export a été fait avant la fin de la section électrique et sera refusé.",
)

for cle, defaut in (
    ("implantation", None),
    ("calage_valide", False),
    ("decalage_est_ouest", 0.0),
    ("correction_nord_sud", 0.0),
):
    if cle not in st.session_state:
        st.session_state[cle] = defaut


def _emprise_courante():
    """Emprise du projet, depuis les fichiers téléversés plus haut."""
    chemin = _enregistrer_fichiers(nom.strip() or "projet", fichiers_emprise)
    return charger_emprise(chemin) if chemin else None


if export_helioscope is not None:
    dossier = DOSSIER_PROJETS / (nom.strip() or "projet")
    dossier.mkdir(parents=True, exist_ok=True)
    chemin_export = dossier / Path(export_helioscope.name).name
    chemin_export.write_bytes(export_helioscope.getbuffer())

    if st.button("Importer et pré-positionner", width="stretch"):
        st.session_state.calage_valide = False
        st.session_state.decalage_est_ouest = 0.0
        st.session_state.correction_nord_sud = 0.0
        try:
            emprise = _emprise_courante()
            if emprise is None:
                st.error(
                    "Téléversez d'abord l'emprise du projet : le calage se fait "
                    "par superposition sur elle."
                )
            else:
                implantation = importer_helioscope(chemin_export)
                diagnostic = prepositionner(implantation, emprise.geometrie)
                st.session_state.implantation = implantation
                st.session_state.chemin_export = str(chemin_export)
                st.session_state.diagnostic = diagnostic
        except ErreurDP as erreur:
            st.session_state.implantation = None
            st.error(f"{type(erreur).__name__} : {erreur}")

implantation = st.session_state.implantation
if implantation is not None:
    calepinage = implantation.calepinage
    module = calepinage.module
    colonnes = st.columns(4)
    colonnes[0].metric("Modules", f"{calepinage.nb_modules:,}".replace(",", " "))
    colonnes[1].metric("Inclinaison", f"{module.inclinaison_deg:g}°")
    colonnes[2].metric("Rangées", calepinage.nb_rangees)
    colonnes[3].metric("Pas inter-rangées", f"{calepinage.pas_rangees_m:.2f} m")

    st.caption(
        f"Design {implantation.identifiant_design} — {calepinage.nb_tables} tables "
        f"de {calepinage.nb_modules_par_table} modules de "
        f"{module.largeur_m:.3f} × {module.longueur_m:.3f} m, pas inter-table "
        f"{calepinage.pas_tables_m:.2f} m, orientation "
        f"{calepinage.orientation_deg:.2f}°. Latitude déduite du fichier : "
        f"{implantation.calage.latitude_origine:.6f}° (zoom {implantation.calage.zoom}, "
        f"fraction {implantation.calage.fraction_zoom:.4f})."
    )
    for message in implantation.avertissements:
        st.warning(message, icon="⚠️")
    st.info(st.session_state.diagnostic.message)

    st.markdown(
        "**Validation du calage — obligatoire.** Deux réglages indépendants, à "
        "faire l'un après l'autre plutôt qu'en glissant l'implantation à vue : "
        "chacun se juge sur un critère simple, alors qu'un déplacement libre "
        "laisse compenser l'erreur d'un axe par l'autre."
    )
    colonne_eo, colonne_ns = st.columns(2)
    with colonne_eo:
        decalage = st.slider(
            "Décalage est-ouest (m)",
            min_value=-150.0,
            max_value=150.0,
            value=float(st.session_state.decalage_est_ouest),
            step=0.5,
            help="Réglage principal : la longitude est la seule inconnue du "
            "modèle de calage.",
        )
    with colonne_ns:
        correction = st.slider(
            "Correction nord-sud (m)",
            min_value=-CORRECTION_NORD_SUD_MAX_M,
            max_value=CORRECTION_NORD_SUD_MAX_M,
            value=float(st.session_state.correction_nord_sud),
            step=0.5,
            help="Retouche de la latitude déduite du fichier, qui n'est bonne "
            "qu'à une dizaine de mètres. Laissez à 0 si l'implantation tombe "
            "juste : toute valeur saisie est conservée dans projet.json.",
        )
    if correction:
        st.caption(
            f"Latitude retouchée de {correction:+.1f} m par rapport à celle "
            f"déduite du fichier ({implantation.calage.latitude_origine:.6f}°)."
        )
    try:
        if decalage != st.session_state.decalage_est_ouest:
            decaler_longitude(
                implantation.calage, decalage - st.session_state.decalage_est_ouest
            )
            st.session_state.decalage_est_ouest = decalage
            st.session_state.calage_valide = False
        if correction != st.session_state.correction_nord_sud:
            corriger_nord_sud(implantation.calage, correction)
            st.session_state.correction_nord_sud = correction
            st.session_state.calage_valide = False

        emprise = _emprise_courante()
        with st.spinner("Téléchargement de l'ortho IGN…"):
            apercu = apercu_calage(implantation, emprise.geometrie)
        st.image(apercu, width="stretch")
        st.caption(
            "Rouge : zone d'implantation HelioScope. Jaune : emprise fournie. "
            "Bleu : tables. La zone HelioScope est tracée à la main et ne suit "
            "pas le parcellaire : c'est la position des tables sur le terrain "
            "qui fait foi."
        )

        if st.button("Valider ce calage", type="primary", width="stretch"):
            st.session_state.calage_valide = True

        if st.session_state.calage_valide:
            projet = _construire_projet()
            if projet is not None:
                projet.helioscope = st.session_state.chemin_export
                projet.longitude_calage = implantation.calage.longitude_origine
                projet.correction_nord_sud_m = (
                    implantation.calage.correction_nord_sud_m or None
                )
                projet.valider()
                chemin = projet.ecrire(DOSSIER_PROJETS / projet.nom / "projet.json")
                dossier_geo = DOSSIER_SORTIE / projet.nom / "helioscope"
                fichiers = ecrire_geojson(implantation, dossier_geo)
                st.success(
                    f"Calage enregistré dans {chemin} "
                    f"(longitude {projet.longitude_calage:.8f}°, correction "
                    f"nord-sud {implantation.calage.correction_nord_sud_m:+.1f} m). "
                    f"{len(fichiers)} couches écrites dans {dossier_geo}."
                )
                st.code(
                    json.dumps(
                        parametres_json(implantation), ensure_ascii=False, indent=2
                    ),
                    language="json",
                )
    except ErreurDP as erreur:
        st.error(f"{type(erreur).__name__} : {erreur}")
