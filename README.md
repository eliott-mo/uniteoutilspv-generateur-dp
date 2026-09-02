# Générateur de dossier DP — socle (lot 1) et calepinage HelioScope (lot 2)

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

**Sommaire.** Tableau à trois colonnes — code, intitulé, page — reprenant la
forme du sommaire des dossiers HOCH. Il liste les onze pièces du dossier, la
page de garde ne s'y listant pas elle-même, y compris celles des lots suivants
et les insertions paysagères fournies : le dossier s'annonce complet dès
maintenant. Les pièces produites portent leur numéro de page réel, les autres un
tiret. Une pièce tenant sur plusieurs planches s'affiche en plage, « 9-10 ».

**Photomontage.** Il occupe la moitié gauche de la page de garde, surmonté d'un
bandeau « VUE EN PERSPECTIVE DU PROJET » calé sur la largeur réelle de l'image.
Sans photomontage, ni bandeau ni cadre : une case titrée surmontant du vide se
remarquerait plus que du blanc. Tout vient de `dp_socle/dossier.py`, qui alimente aussi les
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
- `tests/test_helioscope.py` — import HelioScope : recette de calage, assemblage
  des contours, paramètres du calepinage, et **contrôle d'échelle vraie** —
  une longueur du DXF est comparée à la distance géodésique entre ses deux
  extrémités projetées.

Les tests du lot 2 s'appuient sur les deux exports réels de `exemples/` et se
mettent en `skip` si ces fichiers sont absents.

## Architecture

```
dp_socle/
├── echelle.py        conversions mm <-> m, TransformationL93  (unique et centralisée)
├── planche.py        moteur : gabarit A3, cartouche, SVG -> PDF vectoriel
├── dossier.py        composition du dossier : pièces, titres, numérotation
├── geometrie.py      lecture d'emprise, CRS, union
├── helioscope.py     import DXF HelioScope, calage géographique, GeoJSON L93
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

## Comparaison au dossier de référence

Le critère de validation n°2 du brief demande de comparer le dossier produit à
celui de l'agence. La référence est le dossier HOCH « Les Islettes (55) » du
25/04/2024, 17 planches A3.

Repris de leur dossier :

- la numérotation des planches, page de garde comprise, qui met le plan de
  cadastre en planche 4 ;
- les intitulés des onze pièces, `dp_socle/dossier.py` ;
- le sommaire en tableau à trois colonnes ;
- les bâtiments hachurés sur le plan de cadastre ;
- le bandeau de légende au-dessus du photomontage.

Écarts assumés :

- **l'emprise est remplie à 15 %** sur nos planches, alors qu'ils la tracent en
  simple filet. Au 1:10 000 un terrain de 28 ha fait 5 cm² sur la feuille : un
  aplat léger le rend repérable au premier coup d'œil ;
- **aucune signature ni numéro d'inscription à l'ordre des architectes**, que
  leur page de garde et leurs cartouches portent. Le brief l'interdit : le
  dossier ne doit pas se présenter comme un dossier d'architecte ;
- leurs pages mesurent 420,2 mm au lieu de 420,0. Les nôtres sont exactes.

Leur dossier complet de 17 planches pèse 126 Mo, pour une image non compressée.
Nos quatre planches en pèsent 17,7 : à ce rythme le dossier complet restera sous
la cible de 25 Mo.

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

## Import HelioScope (lot 2)

Le DXF exporté par HelioScope ne porte **aucune donnée de géolocalisation** : le
calepinage est dans un repère local, en mètres sol réels, orienté nord en haut.
Ce qui permet de le recaler, c'est l'entité IMAGE du fond de plan, dont la
résolution encode le niveau de zoom Web Mercator et donc la latitude.

```
res = image.u_pixel.x                     résolution au sol, m/px
z   = floor(log2(K / res))                K = 156543.03392804097
lat = acos(res * 2**z / K)                latitude de l'origine du DXF
```

La latitude est donc entièrement déterminée par le fichier. **La seule inconnue
est la longitude**, réglée par superposition sur l'emprise puis validée à l'œil
sur l'ortho IGN, avec un unique degré de liberté est-ouest. La valeur retenue est
écrite dans `projet.json` (`longitude_calage`) : une régénération ne redemande
jamais le calage.

La « Location » affichée par HelioScope n'est pas utilisable : vérifié sur
Bray-Saint-Aignan, elle est à 176 m au nord et 220 m à l'ouest de l'origine
réelle du DXF.

### Test d'intégrité du zoom

La partie fractionnaire de `log2(K/res)` vaut `-log2(cos φ)` : entre 0,40 et 0,72
pour la France métropolitaine. Un fichier hors de cette plage est refusé.

Ce que ce test garantit, c'est que le `floor` du niveau de zoom est **sans
ambiguïté** : rester loin des entiers empêche `z` de basculer d'une unité, ce qui
donnerait une échelle fausse d'un facteur 2. Il ne détecte pas, et n'a pas à
détecter, une erreur d'un facteur 2 sur `res` elle-même : la partie fractionnaire
est invariante par multiplication par une puissance de 2, le zoom absorbe
exactement le facteur et la latitude comme l'échelle sortent inchangées. Sa
sensibilité est modeste — sur le design de référence, il ne se déclenche
qu'au-delà de -7,3 % ou +15,8 % sur `res`.

### Placement : pourquoi pas le Web Mercator

La recette d'origine place le calepinage par `Mercator = origine + DXF * k`, avec
`k = 1/cos φ`. Ce facteur est celui de la **sphère** Web Mercator, alors qu'un
mètre sol vaut `a/(N·cos φ)` en abscisse et `a/M` en ordonnée sur l'ellipsoïde.
Comme N ≠ M, aucun facteur isotrope ne convient. Mesuré le 2026-09-02 sur le
design 7676351, distances géodésiques vraies contre distances DXF :

| Placement | Est-ouest | Nord-sud |
|---|---|---|
| Web Mercator, `k = 1/cos φ` | +1918 ppm | −976 ppm |
| Transverse Mercator local | 0 ppm | 0 ppm |

Soit 1,34 m d'étirement est-ouest à l'échelle du site de Bray-Saint-Aignan
(700 m). Le repère DXF étant déjà un repère métrique local orienté nord, une
projection transverse Mercator centrée sur son origine le décrit exactement : le
passage est l'identité, et il ne reste qu'à reprojeter en Lambert 93. Les étapes
qui déduisent le zoom et la latitude sont, elles, conservées telles quelles.

### Structure du DXF

| Calque | Représentation | Traitement |
|---|---|---|
| `Field_Segments` | `AcDbPolyFaceMesh` | assemblage des arêtes |
| `Keepouts` | `AcDbPolyFaceMesh` | assemblage des arêtes |
| `Field_Segment_Setback` | `AcDb3dPolyline` | un anneau par entité |
| `Modules` | INSERT vers `fs_*_full` | résolution des blocs imbriqués |

Deux pièges mesurés, tous deux capables de fausser un plan sans se voir :

- Les polyface meshes se terminent par des **enregistrements de face** (drapeau
  128 sans le bit 64) tous situés en (0, 0, 0). Les garder ajoute un sommet
  parasite à l'origine : la zone d'implantation des Islettes tombe de 0,887 ha à
  0,719 ha. Les sommets restants sont ceux d'un mur extrudé, chaque coin apparaît
  deux fois : on dédoublonne sur (x, y) **en préservant l'ordre**.
- Une zone n'est pas toujours un maillage. À Bray-Saint-Aignan, les zones évitées
  sont éclatées en 29 panneaux dont 23 n'ont que deux sommets distincts : prendre
  chaque entité pour un polygone en perdrait 23 sur 29. Les reculs, eux, sont des
  anneaux complets qui se recouvrent — les polygoniser en ferait 121 au lieu de
  30. D'où la distinction par type de représentation, lue dans le DXF et non
  devinée d'après le nom du calque.

### Paramètres extraits

| Paramètre | Source |
|---|---|
| Nombre de modules | INSERT × modules par bloc table |
| Dimensions du module | arêtes **3D** du bloc, pas la bbox 2D |
| Inclinaison | nom du bloc (`_25.0deg_`), recoupée avec la géométrie 3D |
| Orientation | `rotation` des INSERT |
| Rangées et pas | regroupement **dans le repère du calepinage** |

Le contour du module est un rectangle 3D incliné : la bbox 2D donne la projection
au sol (longueur × cos i), pas la longueur vraie du module. Sur le design 7676351,
1,303 × 2,161 au lieu de 1,303 × 2,384 — c'est la seconde qu'attend la notice
DP 11. L'inclinaison est lue dans le nom du bloc comme prévu, et **recoupée avec
l'angle mesuré sur la géométrie** : un désaccord de plus de 0,5° lève.

Compter les valeurs distinctes en Y des points d'insertion suppose des rangées
parallèles à l'axe X. Le design 7676351 est à 0,444° hors axe, et ce comptage y
donne 530 « rangées » pour 530 tables. On repasse donc dans le repère du
calepinage par rotation inverse avant de regrouper : 8 rangées, pas de 9,48 m.

### Sorties

Un GeoJSON par couche en EPSG:2154 — `tables`, `zone_implantation`, `reculs`,
`zones_evitees` — plus les paramètres du calepinage et la longitude de calage
dans `projet.json`. **Aucune planche n'est produite** : le dessin relève du lot 4.

## Hors périmètre de ce lot

Saisie des pistes, postes et clôtures (lot 3), DP 2 / DP 3 / DP 4 (lot 4),
notice DP 11 (lot 5).
