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
  "libelle": "Centrale photovoltaïque de Bray-Saint-Aignan",
  "commune": "Bray-Saint-Aignan",
  "code_postal": "45460",
  "date": "2026-09-01",
  "emprise": "emprise.zip",
  "image_garde": "photomontage.jpg"
}
```

- `nom` est l'identifiant technique du dossier : il nomme le dossier de sortie
  et n'apparaît sur aucune planche.
- `libelle` est le nom du projet retenu par le chef de projet. C'est lui qui
  figure au cartouche et sur la page de garde. À défaut, `nom` est repris.
- `image_garde` est le photomontage de la page de garde. Il occupe la moitié
  gauche de la page ; sans lui, la place reste blanche plutôt que d'afficher un
  cadre vide.

Les chemins relatifs le sont par rapport au dossier du `projet.json`. Une
correction de dernière minute se fait en modifiant une valeur ici puis en
régénérant.

## Ce que portent les planches

**Cartouche.** Le titre porte le code de la pièce — « DP 1-3 : PLAN DE
CADASTRE » — et la case NUMÉRO le rang de la planche dans le dossier assemblé,
page de garde comprise : le plan de cadastre est la planche 4. `assemblage.py`
vérifie ce rang sur le PDF produit ; un cartouche qui annoncerait une planche 3
en page 4 lève une erreur. La flèche nord est
un contour vide au bleu des titres : elle indique le nord de la **grille**
Lambert 93, d'où la mention « NORD (L93) », et n'affirme rien sur le nord
géographique (la convergence des méridiens atteint 3° en métropole).

**Sommaire.** Il liste les onze pièces du dossier — la page de garde ne s'y
liste pas elle-même — y compris celles des lots suivants et les insertions
paysagères fournies : le dossier s'annonce complet dès maintenant. Les pièces
produites portent leur numéro de page réel, les autres un tiret. Tout vient de `dp_socle/dossier.py`, qui alimente aussi les
titres de cartouche — les deux ne peuvent pas diverger.

**Surfaces.** Deux nombres coexistent, et ils ne se recouvrent pas :

- la **surface de l'emprise** en légende (27,99 ha à Bray-Saint-Aignan) est
  l'aire du polygone fourni ;
- la **contenance** du tableau de DP 1-3 (276 270 m²) est la surface légale
  portée au cadastre, sommée sur les parcelles d'assiette.

L'écart est normal, et il va toujours dans le même sens : la contenance légale
est inférieure à la surface graphique. Sur Bray-Saint-Aignan, le rapport est de
0,987, et l'emprise dessinée coïncide à 4 m² près avec la somme des surfaces
graphiques des 27 parcelles — autrement dit tout l'écart vient de la contenance,
et rien du tracé. Le tableau affiche donc les deux valeurs, étiquetées, plutôt
que de laisser chercher l'erreur.

**Bâtiments.** Les emprises bâties du Parcellaire Express sont tracées en
hachures à 45°, comme sur un plan cadastral. Une emprise en secteur agricole
peut n'en contenir aucun : l'entrée de légende n'apparaît alors pas.

**Parcelles d'assiette.** Une parcelle recoupée par l'emprise à moins de 2 % de
sa surface est écartée : l'emprise et le Parcellaire Express ne viennent pas de
la même numérisation, et leurs limites se croisent en produisant des échardes de
quelques mètres carrés. Les parcelles écartées sont listées dans le rapport de
génération, jamais supprimées en silence.

## Typographie

Le corps de texte et le cartouche sont composés en **Aptos**, dont le TTF est
embarqué dans `dp_socle/ressources/polices/`.

### Comment CairoSVG choisit une police

Vérifié dans son code source : le rendu de texte appelle
`cairo_select_font_face`, l'API « toy » de cairo, et ne retient que **la
première** famille de l'attribut `font-family` (`.split(',')[0]`). Une chaîne de
repli CSS dans le SVG est donc décorative — c'est cairo qui substitue, en
silence. CairoSVG n'implémente pas non plus `@font-face` : référencer le chemin
du TTF dans le SVG n'a aucun effet.

`dp_socle.polices` choisit donc lui-même la famille écrite dans le SVG, parmi
celles que cairo résout vraiment, et le dit. La substitution est décidée et
nommée, jamais subie.

### Vérification

Le contrôle ne se contente pas de constater la présence du fichier : il compare
la chasse mesurée par cairo à celle calculée depuis le TTF embarqué. Un écart
signifie que cairo compose autre chose, et l'avertissement affiché en tête de
l'application nomme la police réellement utilisée.

### Installer Aptos selon la plateforme

- **Linux** (cible de déploiement) : cairo passe par FreeType et fontconfig. Le
  TTF est copié dans `~/.local/share/fonts` et le cache rafraîchi
  automatiquement au démarrage. Rien à faire.
- **Windows** : cairo 1.18 passe par **DirectWrite**, qui ne voit que les
  polices installées pour l'utilisateur ou la machine. `AddFontResourceEx`
  (polices privées GDI), `FcConfigAppFontAddFile` et `FONTCONFIG_FILE` ont été
  essayés et mesurés : aucun ne l'atteint. Sur un poste de développement
  Windows, **installez Aptos** : clic droit sur
  `dp_socle/ressources/polices/aptos.ttf` → « Installer ».

### Justification

SVG n'a pas de justification native, et CairoSVG n'implémente ni `textLength`
ni `lengthAdjust`. `Planche.ajouter_paragraphe` positionne donc chaque mot
individuellement, à partir des chasses mesurées par cairo lui-même
(`Planche.mesurer_texte`) : mesure et rendu passent par le même moteur, la
justification est exacte et non approchée. `tests/test_typographie.py` vérifie
que le bord droit des lignes justifiées tombe sur la largeur demandée.

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
- `tests/test_typographie.py` — mesure de texte et justification.
- `tests/test_dossier.py` — composition du dossier et numérotation des planches.

## Architecture

```
dp_socle/
├── echelle.py        conversions mm <-> m, TransformationL93  (unique et centralisée)
├── planche.py        moteur : gabarit A3, cartouche, SVG -> PDF vectoriel
├── dossier.py        composition du dossier : pièces, titres, numérotation
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
| WFS 2.0.0 | `https://data.geopf.fr/wfs/ows` | `CADASTRALPARCELS.PARCELLAIRE_EXPRESS:batiment` |

Le WMS-R limite les images à 5010 px de côté ; à 200 dpi, la zone de dessin A3
fait 3228 × 2110 px. Mesuré sur Bray-Saint-Aignan, la photographie aérienne pèse
5,9 Mo à 150 dpi, 10,6 Mo à 200 et 16,2 Mo à 250, pour une lisibilité
équivalente à l'impression : 200 dpi est le défaut. La barre latérale de l'application permet de reconfronter
les identifiants au GetCapabilities.

## Charte graphique

Il n'existe pas de charte formalisée. Les couleurs sont relevées sur les
plaquettes et supports de communication UNITe, et appliquées avec retenue — un
plan d'urbanisme n'est pas une plaquette :

| Usage | Couleur |
|---|---|
| Titres, libellés du cartouche | `#1C2445` bleu marine |
| Filet d'accent | `#89BA44` vert |
| Fond du bandeau | `#F7F6F5` gris clair |
| Logo | `#2287C8` bleu, `#20A44B` vert |

Les cadres, les limites parcellaires et les cotes restent en noir : ce sont des
pièces techniques.

## Hors périmètre de ce lot

Import DXF HelioScope (lot 2), saisie des pistes, postes et clôtures (lot 3),
DP 2 / DP 3 / DP 4 (lot 4), notice DP 11 (lot 5).
