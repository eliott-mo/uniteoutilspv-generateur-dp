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
from dp_socle.ign import COUCHE_ORTHO, COUCHE_PLAN, DPI_DEFAUT, verifier_couches
from dp_socle.polices import etat_polices
from dp_socle.projet import Projet

DOSSIER_PROJETS = Path("projets")
DOSSIER_SORTIE = Path("sortie")

EXTENSIONS_SHAPEFILE = (".shp", ".shx", ".dbf", ".prj", ".cpg", ".qmd")

st.set_page_config(page_title="Générateur de dossier DP", page_icon="📄", layout="wide")
st.title("Générateur de dossier DP — socle")
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
