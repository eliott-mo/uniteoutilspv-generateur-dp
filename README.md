# Générateur de dossier DP — socle (lot 1)

Production interne des dossiers de déclaration préalable pour les centrales
photovoltaïques au sol de moins de 3 MWc.

Ce lot couvre le **moteur de planche** et les **trois planches
cartographiques** :

| Pièce | Contenu | Échelle |
|---|---|---|
| Page de garde | Titre, MOA/MOE, perspective, sommaire | — |
| DP 1-1 | Plan de situation du terrain | 1:10 000 |
| DP 1-2 | Photographie aérienne du terrain | 1:5 000 |
| DP 1-3 | Plan de cadastre | adaptative |

Sortie dans `sortie/{nom_projet}/` : un PDF par planche plus `DP_complet.pdf`.

## Principes

- **L'échelle est vraie à l'impression A3** (420 × 297 mm). Aucun ajustement à
  la page. Le calcul millimètres ↔ mètres est isolé dans `dp_socle/echelle.py`
  et couvert par un test qui **mesure le PDF produit**, pas les valeurs
  intermédiaires.
- **PDF vectoriel** pour tout ce qui n'est pas fond raster.
- Tout le traitement géométrique en **Lambert 93 (EPSG:2154)**.
- **Fonds IGN exclusivement**, via WMS-R Géoplateforme en EPSG:2154 natif, à la
  bbox exacte de la zone de dessin. Aucune tuile, aucune reprojection, aucun
  recadrage — trois sources classiques d'erreur d'échelle.
- **Aucun repli silencieux.** Police introuvable, couche indisponible, CRS
  absent, géométrie dégénérée : chacun produit un message visible ou une
  exception nommée (`dp_socle/erreurs.py`).

## Installation

```bash
pip install -r requirements.txt
```

Sous Linux, `packages.txt` fournit `libcairo2` et `fontconfig` (Streamlit
Community Cloud lit ce fichier à la racine du dépôt).

### Sous Windows

CairoSVG ne trouve pas `libcairo-2.dll` tout seul. Indiquez un dossier qui la
contient, avec ses dépendances, via la variable d'environnement
`DP_CAIRO_DLL_DIR` :

```bash
export DP_CAIRO_DLL_DIR="$LOCALAPPDATA/Programs/Tesseract-OCR"
```

Ce dossier convient s'il provient d'une installation Tesseract construite avec
MSYS2 ; sinon, tout runtime GTK/cairo fait l'affaire. Sur la cible de
déploiement (Linux), cette variable est inutile.

## Utilisation

Interface :

```bash
streamlit run app.py
```

Ou directement, à partir du format pivot `projet.json` :

```bash
python -c "from dp_socle.projet import Projet; from dp_socle.assemblage import generer_dossier; generer_dossier(Projet.charger('exemples/bray-saint-aignan/projet.json'))"
```

### `projet.json`

```json
{
  "nom": "ALR_45_Bray-Saint-Aignan",
  "commune": "Bray-Saint-Aignan",
  "code_postal": "45460",
  "date": "2026-09-01",
  "emprise": "emprise.zip",
  "image_garde": "perspective.jpg"
}
```

Les chemins relatifs le sont par rapport au dossier du `projet.json`.
`image_garde` est facultatif. Une correction de dernière minute se fait en
modifiant une valeur ici puis en régénérant.

## Police

Le corps de texte et le cartouche sont composés en **Aptos**.

CairoSVG rend le texte via l'API « toy » de cairo (`cairo_select_font_face`),
qui résout les polices **par nom de famille auprès du système** : fontconfig
sous Linux, GDI sous Windows. CairoSVG n'implémente pas `@font-face`, donc
référencer un chemin de TTF dans le SVG n'aurait aucun effet.

Le fichier `Aptos.ttf` doit donc être déposé dans
`dp_socle/ressources/polices/`. Au démarrage, `dp_socle.polices` l'installe
dans le système de polices de la plateforme, puis **vérifie réellement** que
cairo résout la famille demandée, en comparant les métriques obtenues avec
celles d'une famille inexistante. Si la vérification échoue, un avertissement
explicite est affiché dans l'interface et sur la sortie d'erreur : la chaîne de
repli déclarée (`Carlito, Calibri, DejaVu Sans, sans-serif`) a des métriques
différentes et décalerait la mise en page.

## Tests

```bash
python -m pytest -q
```

- `tests/test_echelle.py` — conversions millimètres ↔ mètres, transformation
  Lambert 93 → SVG, choix d'échelle adaptative.
- `tests/test_echelle_pdf.py` — **critère de validation n°1** : une planche au
  1:10 000 contenant un segment de longueur terrain connue est générée, puis le
  segment est mesuré dans le flux de contenu du PDF produit. Écart admis 0,5 %.
- `tests/test_geometrie.py` — ZIP, union multi-polygones, reprojection, refus
  explicite en l'absence de `.prj`.

## Architecture

```
dp_socle/
├── echelle.py        conversions mm <-> m, TransformationL93  (unique et centralisée)
├── planche.py        moteur : gabarit A3, cartouche, SVG -> PDF vectoriel
├── geometrie.py      lecture d'emprise, CRS, union
├── ign.py            WMS-R et WFS Géoplateforme, EPSG:2154 natif
├── polices.py        installation et vérification d'Aptos
├── projet.py         modèle projet.json
├── assemblage.py     génération complète, sommaire paginé, PDF assemblé
├── environnement.py  chemin des DLL cairo sous Windows
├── erreurs.py        exceptions nommées
└── planches/         page de garde, DP 1-1, DP 1-2, DP 1-3
```

L'API `Planche` est conçue pour les lots suivants (coupes, plans techniques) :
elle sépare le repère papier (millimètres) du repère terrain (Lambert 93) et ne
suppose rien de cartographique.

## Services IGN

Identifiants confirmés par GetCapabilities le 2026-09-01 :

| Service | Endpoint | Couche |
|---|---|---|
| WMS-R 1.3.0 | `https://data.geopf.fr/wms-r/wms` | `GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2` |
| WMS-R 1.3.0 | `https://data.geopf.fr/wms-r/wms` | `ORTHOIMAGERY.ORTHOPHOTOS` |
| WFS 2.0.0 | `https://data.geopf.fr/wfs/ows` | `CADASTRALPARCELS.PARCELLAIRE_EXPRESS:parcelle` |

Le WMS-R limite les images à 5010 px de côté ; à 250 dpi, la zone de dessin A3
fait 4035 × 2638 px. La barre latérale de l'application permet de reconfronter
les identifiants au GetCapabilities.

## Hors périmètre de ce lot

Import DXF HelioScope (lot 2), saisie des pistes, postes et clôtures (lot 3),
DP 2 / DP 3 / DP 4 (lot 4), notice DP 11 (lot 5).
