# Générateur de dossier DP

Production interne des dossiers de déclaration préalable pour les centrales
photovoltaïques au sol de moins de 3 MWc.

Lots livrés : le **socle** (lot 1, moteur de planche et planches DP 1), le
**calepinage HelioScope** (lot 2, en réserve), l'**import du plan du bureau
d'études** (lot 2bis), les **planches du projet** (lot 4, DP 2 à DP 4) et la
**notice fournie** (lot 5, DP 11).

Le lot 1 couvre le moteur de planche et les trois planches cartographiques :

| Pièce | Contenu | Échelle |
|---|---|---|
| Page de garde | Titre, MOA/MOE, perspective, sommaire | — |
| DP 1-1 | Plan de situation du terrain | 1:10 000 |
| DP 1-2 | Photographie aérienne du terrain | 1:5 000 |
| DP 1-3 | Plan de cadastre | adaptative |

Sortie dans `sortie/{nom_projet}/` : un PDF par planche plus
`{nom_projet}_DP_complet.pdf`.

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

## L'application, dans l'ordre du travail

Une **liste de prérequis** ouvre la page : ce qu'il faut avoir sous la main, ce
qui est obligatoire et ce qui ne l'est pas. La découverte d'un fichier manquant
au milieu du parcours coûte un aller-retour au bureau d'études.

Puis quatre sections, qui **apparaissent au fur et à mesure** — chacune attend
que la précédente soit satisfaite. C'est ce qui empêche de lancer une génération
avant d'avoir importé le plan : le dossier obtenu s'arrêtait alors aux pièces
DP 1, quatre planches sur neuf, dans un PDF de 17 Mo d'apparence complète.
Techniquement, un `st.stop()` à chaque porte : Streamlit rejoue le script de
haut en bas, arrêter la lecture revient à ne pas afficher la suite.

1. **Métadonnées** — la commune, le code postal, l'emprise cadastrale. Le nom du
   projet et la date ne se saisissent pas : l'un est toujours « PV » suivi de la
   commune et de l'indice du tableau bilan, l'autre est le jour où le dossier est
   produit. Deux champs de moins à remplir, deux occasions de moins de se
   tromper.
2. **Plan du bureau d'études** — le DXF et le tableau bilan, leurs contrôles
   croisés et la ligne de coupe A-A'. C'est le gros de la saisie, et c'est pour
   cela qu'elle vient avant le bouton. **La coupe est proposée dès l'import** :
   perpendiculaire aux rangées, posée là où elle traverse le plus de tables.
   Qui la trouve bien placée n'a rien à tracer ; qui veut la déplacer trace un
   segment *globalement* perpendiculaire aux rangées, l'outil se chargeant du
   reste — il impose la direction exacte et ne retient du tracé que sa position.

   **Le tracé se fait sur le plan importé lui-même**, aux couleurs de la
   légende DP, sur l'ortho IGN. L'écran portait auparavant deux vues presque
   identiques — une carte à tracer qui ne montrait que les tables et la
   clôture, puis un aperçu statique de tout le plan : on traçait sans voir ce
   que la ligne allait couper, puis on descendait vérifier. Les modules sont
   les seuls écartés de la carte : la silhouette des rangées dit la même chose,
   et un plan en compte des milliers. Seule la coupe **retenue** est dessinée,
   jamais le tracé d'origine — le voir persister donnait à croire que rien
   n'avait été redressé.
3. **Pièces fournies** — ce que l'outil ne dessine pas. La **notice DP 11**
   ouvre la section : c'est la seule que l'outil intègre au dossier assemblé —
   voir « Notice DP 11 » plus bas. Elle est attendue de tout dossier déposable
   sans être exigée : sans elle le dossier sort quand même, et le rapport dit
   qu'il est incomplet. Viennent ensuite les photographies et photomontages, une ligne par
   pièce, DP 6, DP 7 et DP 8 : ce sont trois pièces distinctes, qui ne montrent
   pas la même chose et ne se rangent pas au même endroit du dossier, et les
   mélanger obligerait à les retrier à la main. L'insertion paysagère de DP 6
   monte en page de garde ; quand il y en a plusieurs, un bouton radio désigne
   laquelle.
4. **Génération** — le type des voiries si le plan en laisse d'indécises, puis le
   bouton. Il est en dernier parce que tout ce qu'il consomme est au-dessus de
   lui, et c'est là que le nom du projet est complet : l'indice ne se connaît
   qu'après l'import. Le dossier produit se **télécharge** — en une archive ZIP,
   ou en PDF assemblé seul. L'application tourne sur un serveur : `sortie/` y
   reste, hors de portée du chef de projet.

**Le dossier réduit aux seules pièces DP 1** — page de garde, situation,
photographie aérienne, cadastre — reste possible pour une étude amont, mais il
se demande : une case à cocher, qui dit ce à quoi on renonce. Il était obtenu
par simple inadvertance.

**L'indice fait partie du nom du dossier.** Sarnois a deux indices, qui diffèrent
par leur poste, leur citerne et leur zone de contention : sans l'indice au nom,
le second écrasait le premier dans `sortie/`. Le nom complet est affiché avant la
génération et rappelé après, avec le dossier obtenu.

Le **dépôt** des fichiers du bureau d'études, lui, ne porte pas l'indice :
`projets/{commune}/` reçoit le DXF, le tableau bilan, le PDF et le relevé
altimétrique. Ils y arrivent avant qu'on sache quel indice lire — c'est le
tableau déposé là qui en donne la liste — et le tableau porte de toute façon
tous les indices du projet. Un dépôt par commune, donc, et un dossier par
indice : `projets/{commune}-{indice}/` pour l'emprise, les photos et le
`projet.json` du lot 1, `sortie/{commune}-{indice}/` pour le contrat et les
planches.

Ces deux noms se composent par `_nom_depot()` et `_nom_dossier()`, appelés là où
le nom sert. Ce ne sont pas des variables posées en tête de script : Streamlit
rejoue `app.py` de haut en bas à chaque interaction, l'indice est choisi au
milieu de la section 2, et une variable serait en retard d'une exécution en tête
de script — ou absente en section 2 si on la composait en section 4, ce qui a
levé une `NameError` au dépôt du DXF le 09/09/2026.

**Les contrôles croisés sont repliés.** Une quinzaine de recoupements entre le
plan et le tableau, sur lesquels le chef de projet n'a pas la main : un écart se
traite avec le bureau d'études, sur ses fichiers. Seuls les **bloquants**
restent au premier plan, parce qu'ils arrêtent le dossier et qu'il faut savoir
lequel appeler. Le reste est consultable dans un dépliant.

**Ce que l'application refuse.** Elle ne devine pas et ne se rabat sur rien :

- importer sans commune — c'est elle qui nomme le dépôt et le dossier ;
- écrire la sortie quand la liste d'indices s'est écartée de l'import en
  mémoire, ce qui déposerait la géométrie d'un indice dans le dossier d'un
  autre ;
- générer sans emprise cadastrale, ou avec deux photographies de même nom dans
  une même pièce, la seconde écrasant la première sur le disque ;
- trancher à votre place le type d'une voirie que le plan laisse indécise.

Chacun de ces cas affiche ce qui manque et pourquoi. C'est la règle du dépôt :
une planche fausse qui s'affiche correctement est pire qu'un refus, parce que
personne ne la détecte avant l'instruction du dossier.

Les pièces photographiques DP 6, DP 7 et DP 8 sont assemblées au dossier depuis
le lot 6, avec le **report de la position de prise de vue sur un plan de
repérage** — voir « Les pièces photographiques » plus bas.

## Installation

```bash
pip install -r requirements.txt
```

Sous Linux, `packages.txt` fournit `libcairo2` et `fontconfig` (Streamlit
Community Cloud lit ce fichier à la racine du dépôt).

### Sous Windows

CairoSVG ne trouve pas `libcairo-2.dll` tout seul. En général vous n'avez rien à
faire : le générateur fouille les emplacements des logiciels qui embarquent
cairo — Tesseract-OCR, runtime GTK3, Inkscape, GIMP, MSYS2 — et **affiche en
tête de l'interface celui qu'il a retenu**. Rien n'est substitué : c'est bien la
bibliothèque demandée qui est chargée, seulement trouvée sans qu'on l'ait dit.

Si la DLL est ailleurs, désignez son dossier :

```bash
export DP_CAIRO_DLL_DIR="$LOCALAPPDATA/Programs/Tesseract-OCR"
```

Renseignée, la variable est prioritaire — et si elle pointe sur un dossier
inexistant ou sans `libcairo-2.dll`, le lancement échoue immédiatement plutôt
que de chercher ailleurs : une configuration explicite et fausse se corrige, elle
ne se contourne pas.

Si aucun cairo n'est trouvé, l'interface le dit **au démarrage**, en rouge, avec
la liste des dossiers fouillés. C'est un changement du 03/09/2026 : auparavant
l'échec ne survenait qu'au rendu de la première planche, après le téléchargement
de tous les fonds IGN, et le diagnostic typographique accusait la police alors
que la cause était la bibliothèque de rendu — sur un poste où Aptos était
pourtant installée.

Sur la cible de déploiement (Linux), tout ceci est inutile : `packages.txt`
fournit `libcairo2`.

### Où l'outil écrit, et pourquoi pas dans OneDrive

`projets/` reçoit les fichiers déposés, `sortie/` les dossiers assemblés. Tous
deux sont **relatifs au dossier courant** par défaut, ce que la cible de
déploiement attend, et `DP_DOSSIER_TRAVAIL` les déplace :

```bash
export DP_DOSSIER_TRAVAIL="$LOCALAPPDATA/UNITe/generateur-dp"
```

Un dossier de travail **synchronisé est signalé au démarrage**, comme l'état de
cairo. Le motif est mesuré : le 16/09/2026, en usage réel, un `PermissionError`
a interrompu une session — OneDrive tenait le DXF ouvert pendant qu'il le
téléversait, au moment où l'application le réécrivait. L'outil ne réécrit plus
un fichier inchangé, ce qui referme l'essentiel de la fenêtre, mais ces
fichiers-là n'ont rien à faire dans un espace synchronisé : volumineux,
régénérables, réécrits à chaque génération, ils se téléversent pour rien.

La détection lit les variables que le client Windows pose lui-même — `OneDrive`,
`OneDriveCommercial`, `OneDriveConsumer` — plutôt que de chercher « OneDrive »
dans le chemin, ce qui se tromperait sur un dossier local nommé ainsi.

### Photos HEIC

Le HEIC est le format par défaut des iPhone : un chef de projet qui dépose une
photo de visite en dépose un sans le savoir. `pillow-heif` est donc épinglé dans
`requirements.txt`, et `dp_socle/lecture_exif.py` enregistre son décodeur auprès
de Pillow à l'import. Rien à installer sur le poste : la roue embarque libheif,
et `packages.txt` reste inchangé — contrairement à `tesseract-ocr`, que le dépôt
voisin `photos-geoloc` doit y déclarer.

Son indisponibilité est un état d'environnement, annoncé au démarrage comme
celui de cairo. Le piège est mesuré : le 15/09/2026, `pillow-heif` était installé
sur le poste de développement **sans figurer dans `requirements.txt`**. Les HEIC
s'y lisaient donc, et auraient été refusés en production sans que rien ne
l'explique. Une dépendance qui marche par accident en développement est une
panne qui attend le déploiement.

## Utilisation

Interface :

```bash
streamlit run app.py
```

Ou directement, à partir du format pivot `projet.json` :

```bash
python -c "from dp_socle.projet import Projet; from dp_socle.assemblage import generer_dossier; generer_dossier(Projet.charger('exemples/bray-saint-aignan-HELIO/projet.json'))"
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
  gauche de la page ; sans lui, un cadre tireté gris y tient la place et la
  nomme, « Photomontage à insérer ».

Les chemins relatifs le sont par rapport au dossier du `projet.json`. Une
correction de dernière minute se fait en modifiant une valeur ici puis en
régénérant.

## Ce que portent les planches

**Cartouche.** Le titre porte le code de la pièce — « DP 1-3 : PLAN DE
CADASTRE » — et la case NUMÉRO le rang de la planche dans le dossier assemblé,
page de garde comprise : le plan de cadastre est la planche 4. `assemblage.py`
vérifie ce rang sur le PDF produit ; un cartouche qui annoncerait une planche 3
en page 4 lève une erreur. Une pièce de plusieurs pages déclare les numéros de
ses cartouches et le contrôle les compare un à un à la pagination réelle — une
pièce qui s'étendrait sans le déclarer est refusée. La flèche nord est
un contour vide au bleu des titres : elle indique le nord de la **grille**
Lambert 93, d'où la mention « NORD (L93) », et n'affirme rien sur le nord
géographique (la convergence des méridiens atteint 3° en métropole).

**Sommaire.** Tableau à trois colonnes — code, intitulé, page — reprenant la
forme du sommaire des dossiers HOCH. Il liste les douze pièces du dossier, la
page de garde ne s'y listant pas elle-même, y compris les insertions paysagères
fournies : le dossier s'annonce complet dès maintenant. Les pièces produites
portent leur numéro de page réel, les autres un tiret. Une pièce tenant sur
plusieurs planches s'affiche en plage, « 9-10 » — c'est le cas de la notice
DP 11, seule pièce à pouvoir couvrir plusieurs pages.

Depuis le lot 4, les pièces produites ne sont plus toujours les mêmes : un projet
sans poste n'a pas de DP 4-1, un projet sans BESS ni local technique n'a pas de
DP 4-3, et un dossier dont le plan n'a pas été importé s'arrête au plan de
cadastre. Le rang de chaque planche se calcule donc sur les pièces **réellement
produites**, et `assemblage.py` continue de le vérifier sur le PDF assemblé.

**Photomontage.** Il occupe la moitié gauche de la page de garde, surmonté d'un
bandeau « VUE EN PERSPECTIVE DU PROJET » calé sur la largeur réelle de l'image.
Sans photomontage, un cadre tireté gris tient la place et la nomme
« Photomontage à insérer » : la moitié gauche laissée blanche se lisait comme
une composition ratée, et rien ne rappelait la pièce manquante. Tout vient de
`dp_socle/dossier.py`, qui alimente aussi les titres de cartouche — les deux ne
peuvent pas diverger.

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
- `tests/test_import_be.py` — lecture du DXF et du tableau bilan du BE, mesurées
  contre le relevé manuel du jeu Saint-Cyr-en-Val, plus les cas d'erreur :
  coordonnées hors des bornes L93, calque renommé avec une variante
  d'accentuation, calque qui n'existe qu'en `HATCH`, paramètre absent du
  tableau.
- `tests/test_coupe.py` — contrôles croisés, correction de perpendicularité de
  la coupe A-A', profil altimétrique et contrat de sortie GeoPackage.
- `tests/test_contrat_lot4.py` — lecture du contrat d'entrée du lot 4 : ce
  qu'il refuse, surtout. Un test **inverse volontairement** `ordre_cotes` pour
  que le jour où quelqu'un câblerait la position des dimensions au lieu de les
  lire, quelque chose casse : un poste de 12 x 3 m dessiné 3 x 12 se dessine
  parfaitement et ne se remarque pas.
- `tests/test_palette_dp.py` — les deux règles de la légende, mesurées : ce qui
  n'est pas dessiné n'y figure pas, et deux teintes qui peuvent se côtoyer
  restent séparées d'au moins 12 ΔE.
- `tests/test_primitives_lot4.py` — le repère local des coupes : isotropie,
  conversion passant par `dp_socle.echelle`, refus d'un dessin qui déborde de
  son cadre.
- `tests/test_planches_lot4.py` — **critères de validation n°1 et n°2**, mesurés
  dans le PDF produit : six échelles locales vérifiées à moins de 0,5 %, et
  l'isotropie contrôlée deux fois — sur deux segments perpendiculaires de même
  longueur, et sur un profil à 2 % qui doit se retrouver à 2 % dans le fichier.
  Ces deux-là ne demandent aucun service en ligne : ce sont ceux qui comptent le
  plus, et un `-m "not reseau"` ne doit pas les sauter.
- `tests/test_notice_lot5.py` — **critères de validation n°1 à n°7 du lot 5**,
  mesurés dans le PDF produit : trois pages fournies donnent trois planches de
  420 × 297 mm, le texte de la notice reste du texte après fusion, rien ne
  descend sous `Y_CARTOUCHE`, chaque page porte son propre numéro, le cartouche
  n'a ni nord ni échelle — et une planche composée sans rien préciser garde les
  deux, ce qui est la garantie que le paramètre est additif. Les refus y sont
  mesurés aussi : fichier qui n'est pas un PDF, PDF sans page, plan A1 déposé à
  la place de la notice. La notice de synthèse est composée par cairo : aucun
  service en ligne n'est demandé. Le **critère n°6** y figure aussi, sous deux
  angles : un dossier complet sans notice s'entend dire qu'il est incomplet, un
  dossier d'étude amont ne s'entend rien reprocher.
- `tests/test_app_streamlit.py` — l'application elle-même, jouée sans navigateur
  par `AppTest`, qui suit le parcours du chef de projet : cadrer le projet,
  déposer le plan, importer, valider, générer. Il contrôle l'ouverture des
  sections une à une, la coupe proposée dès l'import, et surtout les **refus** —
  changer d'indice sans réimporter, générer hors de portée d'une emprise,
  importer sans commune, déposer deux photos de même nom. C'est le seul contrôle
  qui exécute `app.py` ; les tests des modules ne le touchent pas, et une
  `NameError` y est restée invisible jusqu'à ce qu'un chef de projet la
  rencontre. Un relevé altimétrique de synthèse y est déposé à chaque fois,
  pour que le profil se lise dans un fichier plutôt que sur le RGE ALTI : seuls
  les tests qui produisent un vrai dossier sont marqués `reseau` : le
  téléchargement, le **critère n°8 du lot 5** — déposer la notice, générer, la
  retrouver dans l'archive ZIP — et la génération sans notice, qui doit aboutir
  à un dossier produit et à un rapport qui le dit incomplet.
- `tests/test_ordre_app.py` — l'ordre des noms dans `app.py`, relu dans l'arbre
  syntaxique. Streamlit rejoue le script de haut en bas : un nom écrit plus bas
  qu'il n'est lu lève dans le navigateur et nulle part ailleurs. Le contrôle
  refuse aussi qu'une fonction lise un global écrit plus bas que sa définition —
  ce qu'elle doit prendre en paramètre.

Les tests du lot 4 s'appuient sur un contrat **synthétique**
(`tests/contrat_synthetique.py`), dimensionné en nombres ronds — clôture de
200 x 120 m, poste de 12 x 3 m, coupe de 220 m sur une pente de 2 %. Les jeux
réels valent pour ce qu'ils montrent d'imprévu, mais on ne peut pas mesurer une
planche contre eux : leurs cotes ne sont connues que par ce que l'import en a lu.
Son GeoPackage est écrit par le producteur réel, `import_be.ecrire_geopackage` :
un fixture qui écrirait son propre schéma cesserait de tester le contrat le jour
où le contrat changerait.

Les tests du lot 2 s'appuient sur les deux exports réels de `exemples/` et se
mettent en `skip` si ces fichiers sont absents. Ceux des lots 2bis s'appuient
sur les fichiers de `exemples/saint-cyr-DXF/`, versionnés.

Les tests marqués `reseau` interrogent un service IGN en ligne — le seul moyen
de savoir si un point d'entrée ou un format de réponse a changé. Pour s'en
passer :

```bash
python -m pytest -q -m "not reseau"
```

## Architecture

```
dp_socle/
├── echelle.py        conversions mm <-> m, TransformationL93  (unique et centralisée)
├── planche.py        moteur : gabarit A3, cartouche, SVG -> PDF vectoriel
├── dossier.py        composition du dossier : pièces, titres, numérotation
├── geometrie.py      lecture d'emprise, CRS, union
├── helioscope.py     import DXF HelioScope, calage géographique, GeoJSON L93
├── import_be.py      import DXF du BE, contrôles croisés, sorties GeoPackage
├── tableau_bilan.py  lecture du tableau bilan Excel du BE
├── coupe.py          ligne de coupe A-A' et profil du terrain naturel
├── apercu_be.py      aperçu du plan importé, palette de la légende DP
├── contrat.py        lecture du contrat d'entrée du lot 4, cotes normalisées
├── ign.py            WMS-R et WFS Géoplateforme, EPSG:2154 natif
├── polices.py        installation et vérification d'Aptos
├── projet.py         modèle projet.json
├── assemblage.py     génération complète, sommaire paginé, PDF assemblé
├── environnement.py  chemin des DLL cairo sous Windows
├── erreurs.py        exceptions nommées
└── planches/
    ├── commun.py         cartouche et numérotation partagés
    ├── primitives.py     repère local des coupes, cotes, hachures, silhouette
    ├── palette.py        teintes et légende du dossier imprimé
    ├── page_garde.py     page de garde et sommaire paginé
    ├── dp1_1_situation.py, dp1_2_aerienne.py, dp1_3_cadastre.py
    ├── dp2_plan_masse.py plan de masse
    ├── dp3_coupes.py     coupe de type des tables et coupe du terrain
    └── dp4_ouvrages.py   postes, clôture, portail, citerne, équipements
```

L'API `Planche` sépare le repère papier (millimètres) du repère terrain
(Lambert 93) et ne suppose rien de cartographique. Le lot 4 s'en sert dans les
deux repères et **ne l'a pas modifiée** : les primitives qui lui manquaient se
construisent par-dessus.

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

La longitude est la seule inconnue du modèle : elle est réglée par superposition
sur l'emprise, puis validée à l'œil sur l'ortho IGN. La latitude, elle, se déduit
du fichier — mais à une dizaine de mètres près seulement (voir plus bas), d'où un
second réglage, **une correction nord-sud bornée à ±30 m**, à zéro par défaut.

Les deux réglages restent séparés plutôt que fondus en un glissement libre à deux
dimensions : chacun se juge sur un critère visuel simple, alors qu'un déplacement
libre laisse compenser l'erreur d'un axe par l'autre. La correction nord-sud est
stockée en **écart** (`correction_nord_sud_m`) et non en latitude corrigée, pour
que la valeur du fichier reste lisible et que toute retouche se voie. Avec
`longitude_calage`, elle est écrite dans `projet.json` : une régénération ne
redemande jamais le calage.

Au-delà de ±30 m — près de trois fois l'écart mesuré entre deux designs d'un même
projet — la correction est refusée : à cette distance ce n'est plus une retouche
mais le signe d'un calage faux, mauvais export ou mauvaise emprise, et le
rattraper à la main masquerait le problème.

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
| Pose | portrait ou paysage, déduite de la géométrie |
| Inclinaison | nom du bloc (`_25.0deg_`), recoupée avec la géométrie 3D |
| Orientation | `rotation` des INSERT |
| Rangées et pas | regroupement **dans le repère du calepinage** |

Le contour du module est un rectangle 3D incliné : la bbox 2D donne la projection
au sol (longueur × cos i), pas la longueur vraie du module. Sur le design 7676351,
1,303 × 2,161 au lieu de 1,303 × 2,384 — c'est la seconde qu'attend la notice
DP 11. L'inclinaison est lue dans le nom du bloc comme prévu, et **recoupée avec
l'angle mesuré sur la géométrie** : un désaccord de plus de 0,5° lève.

C'est le côté qui prend de la hauteur qui porte l'inclinaison, pas le plus long.
Les deux designs des Islettes le montrent — même panneau de 1,303 × 2,384 m à
25°, posé différemment :

| Design | Pose | Contour du bloc | Largeur | Rampant |
|---|---|---|---|---|
| 7676351 | portrait | (0,0,0) → (1,303, 0, 0) → (1,303, −2,161, −1,008) | 1,303 | 2,384 |
| 8102502 | paysage | (0,0,0) → (2,384, 0, 0) → (2,384, −1,181, −0,551) | 2,384 | 1,303 |

Chercher l'inclinaison sur le côté le plus long marche en portrait et renvoie 0°
en paysage. Le rampant est donc identifié par son dénivelé, et la pose déduite de
la géométrie est recoupée avec le suffixe du nom de bloc.

Compter les valeurs distinctes en Y des points d'insertion suppose des rangées
parallèles à l'axe X. Le design 7676351 est à 0,444° hors axe, et ce comptage y
donne 530 « rangées » pour 530 tables. On repasse donc dans le repère du
calepinage par rotation inverse avant de regrouper : 8 rangées, pas de 9,48 m.

### Précision de la latitude

Le brief annonçait deux designs d'un même projet concordant à 10⁻⁶ degré.
Mesuré le 2026-09-02 sur les deux designs des Islettes, ils diffèrent de
**9,9 × 10⁻⁵ degré, soit 11 m nord-sud** :

| Design | `res` | Latitude déduite |
|---|---|---|
| 7676351 | 0,1954518020063469 | 49,110690462 |
| 8102502 | 0,19545219342840345 | 49,110591106 |

`res` n'est pas quantifiée sur la rangée de tuiles : elle est calculée au point
de référence de chaque design, et ces points diffèrent. La latitude place donc
le projet à une dizaine de mètres près, pas au mètre. Un écart nord-sud résiduel
de cet ordre au pré-positionnement est normal et non suspect — constaté à
+8,6 m sur un design et −12,4 m sur l'autre, contre la même emprise.

C'est ce constat qui justifie le réglage nord-sud, que la recette d'origine
interdisait en supposant la latitude verrouillée. Sur le design 7676351, saisir
la correction de −8,6 m annoncée par le diagnostic fait passer le recouvrement
avec l'emprise de 80 % à 88 % — exactement ce que donnerait un recalage libre en
deux dimensions. Le pré-positionnement ne l'applique jamais de lui-même : il
annonce l'écart et laisse l'opérateur décider, parce qu'un écart corrigé
automatiquement ne dirait plus rien de la qualité du calage.

### Réglage du calage dans l'interface

Le calage se règle à deux curseurs, sur un aperçu ortho. Trois choix rendent
l'opération tenable, chacun tiré d'un essai raté le 03/09/2026 :

- **Le cadre de l'aperçu est figé** au pré-positionnement. Recalculé à chaque
  cran, il obligeait à redemander l'ortho au WMS : l'image disparaissait puis
  revenait à chaque mouvement, et juger un déplacement devenait impossible.
  L'ortho est donc téléchargée une fois et mise en cache ; seule la surcouche est
  redessinée. Corollaire assumé : poussé loin, le calepinage sort du cadre — ce
  qui est un signal utile, le pré-positionnement étant bon à quelques mètres.
- **Le remplissage et le filet des modules sont tracés séparément.**
  `ImageDraw.polygon` avec un `width` supérieur à 1 met 9,6 s pour les 1 590
  modules du design 7676351, contre 0,03 s pour le même contour en `line`
  (Pillow 12). Le redessin passe de 13 s à 1,4 s.
- **Les curseurs sont dans un `st.fragment`**, pour ne pas relancer tout le
  script — donc la relecture de l'emprise et le rendu des sections précédentes —
  à chaque cran.

Le sens de chaque curseur est écrit dans son intitulé (`◀ ouest · est ▶`,
`▼ sud · nord ▲`) et rappelé sous forme de phrase sous le curseur (« 12,5 m vers
l'est »). Le nord est en haut sur l'aperçu.

### Aperçu de calage

La validation du calage par l'utilisateur est obligatoire et ne peut pas se faire
sur des chiffres : `apercu_calage()` superpose le calepinage recalé à l'ortho
IGN. Ce n'est pas une planche — le dessin du dossier relève du lot 4 — mais
l'aperçu reprend la présentation du dossier de référence HOCH (modules dessinés
un par un, bleu-vert pâle cerné de bleu, contour noir autour de la rangée) pour
que ce qu'on valide ressemble à ce qu'on obtiendra.

Deux points ont dû être corrigés pour que l'azimut se lise correctement :

- `ImageDraw` ne fait pas d'anticrénelage. Une rangée à 0,44° de l'horizontale se
  rastérise en marches d'escalier, ce qui donne à lire un calepinage aligné
  nord-sud et décalé rangée par rangée — alors que l'azimut est correctement
  appliqué à la géométrie, dont tous les côtés sont à 90,4441°. L'aperçu est
  dessiné trois fois plus grand puis réduit.
- L'accroche appliquée avant fusion des modules était au millimètre, ce qui
  faisait osciller l'azimut des tables de ±0,027° : deux valeurs d'angle au lieu
  d'une sur le design 7676351. Ramenée au micromètre, elle recolle toujours et ne
  déforme plus rien.

HelioScope n'encode aucun groupement en structures : sur les deux designs des
Islettes, **tous** les écarts entre tables valent exactement une largeur de
module. Le contour noir cerne donc la rangée, seule entité que le fichier
permette de reconstituer — le découpage en tables de 3×9 du dossier HOCH est un
choix de structure, pas une donnée de l'export.

### Sorties — le contrat commun avec le lot 2bis

Depuis le 03/09/2026, le lot 2 écrit **exactement le contrat du lot 2bis** :
`sortie/{projet}/geometries.gpkg` et `sortie/{projet}/projet.json`, à
`version_contrat` égale, distingués par `origine` (`helioscope` contre
`import_be`). L'ancien chemin — cinq GeoJSON dans `sortie/{projet}/helioscope/`,
dont le CRS était porté par un membre `crs` que la spécification GeoJSON ne
prévoit pas — a été retiré : deux formats auraient obligé le lot 4 à les lire
tous les deux, ou à refuser les projets sans plan BE.

| Couche du contrat | Contenu HelioScope | Aussi produite par le lot 2bis |
|---|---|---|
| `tables_pv` | les **rangées** | oui |
| `modules_pv` | chaque module | non |
| `zone_implantation_pv` | zone tracée dans HelioScope | non |
| `recul_implantation` | reculs de la zone | non |
| `zone_evitee` | bâtiments, bassins, voiries | non |

Les colonnes sont les mêmes des deux côtés — `calque`, `categorie`, `z_reel`,
`z_min`, `z_max` — y compris celles que HelioScope ne peut pas remplir : le DXF
est plat, `z_reel` vaut donc `False` partout et les bornes restent nulles. Un
schéma qui changerait selon la provenance obligerait le lot 4 à savoir d'où
vient le fichier avant de le lire.

**`tables_pv` reçoit les rangées, pas les tables du DXF.** Une « table »
HelioScope est une colonne de 3 modules, 1,30 × 6,48 m, dont le grand côté est
*en travers* de la rangée. Mesuré le 03/09/2026 sur le design 7676351 :

| Entrée de `azimut_tables()` | Azimut rendu |
|---|---|
| couche `tables` brute | **−88,105°** |
| rangées regroupées | **+1,895°** |

Y brancher la ligne de coupe donnerait une coupe **parallèle** aux rangées au
lieu de perpendiculaire, sans anomalie visible sur la planche. Mettre les
rangées dans `tables_pv` fait que le calcul juste est celui qu'on obtient sans
rien savoir de la provenance du fichier.

Aucune couche n'est appariée à `cloture` ni à `portail` : la zone d'implantation
HelioScope est tracée à main levée et ne suit pas le parcellaire — 25,05 ha
contre 27,99 ha pour le cadastre à Bray-Saint-Aignan. En tirer une surface
clôturée ou un linéaire de clôture donnerait des chiffres faux dans le dossier
déposé.

### `orientation_deg` n'oriente pas la coupe

`calepinage.orientation_deg` s'écarte de 1,45° de l'azimut mesuré sur les
rangées. Ce n'est pas du bruit : mesuré le 03/09/2026, l'écart vaut **1,4507°,
et c'est exactement la convergence des méridiens du Lambert 93** au droit du
site — pyproj donne 1,4507°, résidu nul.

`orientation_deg` est la rotation des INSERT dans le repère du DXF, rapportée au
**nord géographique** ; la ligne de coupe se trace en Lambert 93, rapporté au
**nord de la grille**. La convergence est nulle sur le méridien 3° E et atteint
3° aux bords de la France métropolitaine. `azimut_rangees()` mesure donc sur la
géométrie projetée, comme le fait le lot 2bis.

### Ce que le lot 2 ne peut pas fournir

Le lot 2bis tire sa valeur d'avoir **deux sources qui peuvent se contredire** :
le plan du BE et son tableau bilan. L'import HelioScope n'en a qu'une. La
plupart des recoupements n'y ont donc pas d'objet, et les afficher en vert
laisserait croire à une vérification qui n'a pas eu lieu : un statut
`impossible`, marqué ∅ à l'écran, les distingue d'un contrôle réussi.

| Contrôle | Statut |
|---|---|
| Recoupement avec le tableau bilan | impossible — pas de seconde source |
| Cohérence altimétrique des tables | impossible — DXF plat |
| Surface clôturée, linéaire de clôture | impossible — pas de clôture |
| Implantation dans l'emprise cadastrale | **calculable** |

Le seul recoupement qui survit confronte le calepinage à une source extérieure,
le parcellaire. C'est la vraie perte de ce lot par rapport au 2bis, et elle est
dite dans les données comme à l'écran.

La coupe A-A' reste disponible, avec la même mécanique qu'au lot 2bis — tracé
sur carte, redressement perpendiculaire, profil RGE ALTI. Elle s'étend sur
l'**emprise cadastrale** du lot 1 : le lot 2bis étend la sienne à l'emprise
clôturée, que HelioScope ne donne pas, et la zone d'implantation n'est pas un
candidat défendable. Le profil du terrain reste levable, mais sans recoupement
possible avec l'altitude des tables.

**Aucune planche n'est produite** : le dessin relève du lot 4.

## Import du plan du bureau d'études (lot 2bis)

Pour les premiers dossiers, le BE interne fournit le plan final déjà
géoréférencé en Lambert 93 et un tableau bilan Excel. Il n'y a donc ni calage à
faire ni élément technique à saisir. Le travail est de **lire, normaliser et
recouper** ces deux fichiers avant de les transmettre au lot 4.

Ce lot **remplace les lots 2 et 3** pour ces dossiers ; l'import HelioScope
reste en réserve pour les projets sans plan BE.

Entrées : le DXF du plan BE et le tableau bilan `.xlsx` (obligatoires), le
shapefile d'emprise cadastrale du lot 1, éventuellement le PDF du plan BE pour
comparaison visuelle et un relevé altimétrique `.txt` de repli.

Le PDF de vue de profil du BE n'est pas une entrée et n'a pas à l'être : ses
quatre cotes (inclinaison, point bas, point haut, inter-table) figurent déjà au
tableau bilan, et la coupe DP 3 au 1/50 sera générée en paramétrique au lot 4.
Vérifié sur le fichier de référence, la coupe n'est pas non plus dans le DXF :
aucun calque de coupe, aucun texte, aucune cote, présentations vides.

### Lecture du DXF

**L'en-tête `$INSUNITS` n'est pas lu.** Sur le fichier de référence il vaut 4,
c'est-à-dire millimètres, alors que les coordonnées sont en mètres — un outil
qui le croirait diviserait tout le plan par mille. L'unité est déduite de
l'ordre de grandeur des coordonnées : le facteur retenu est celui qui place le
centre du dessin dans les bornes du Lambert 93 métropolitain (X entre 100 000 et
1 300 000, Y entre 6 000 000 et 7 200 000). Aucun facteur ne convient, ou
plusieurs conviennent : le fichier est refusé.

La correspondance calque → catégorie est **proposée puis confirmée** à l'écran.
La comparaison est tolérante : décomposition Unicode NFKD, repli de casse, et
suppression des tirets, espaces, underscores et apostrophes. Nécessaire, et pas
par excès de prudence : dans le fichier de référence l'apostrophe de « aire
d'aspiration » est devenue un tiret (`UNI_SDIS_Aire_d-aspiration`).

| Calque | Catégorie |
|---|---|
| `PVcase PV Modules (optimised)` | `tables_pv` |
| `UNI_Clôture` | `cloture` |
| `UNI_portail` | `portail` |
| `UNI_PDL` | `pdl_ptr` |
| `UNI_VRD_Plateforme` | `plateforme` |
| `UNI_VRD_Piste_lourde_existante` | `piste_lourde_existante` |
| `UNI_VRD_Piste_lourde_à_créer` | `piste_lourde_a_creer` |
| `UNI_SDIS_Bache_incendie` | `bache_incendie` |
| `UNI_SDIS_Aire_d-aspiration` | `aire_aspiration` |

Les plans de Sarnois ont montré que **la charte n'est pas figée d'un projet à
l'autre** : les mêmes objets y portent d'autres noms. Sont donc aussi appariés
`UNI_Cloture`, `UNI_Haies`, `UNI_Haies existantes`, `UNI_Local_Stockage`,
`UNI_VRD_Voirie`, `UNI_PDT`, `UNI_BESS_Batterie`, `UNI_BESS_Rétention` et
`UNI_Portail exploitant`.

Le vocabulaire s'est élargi aux objets réellement portés par ces plans :
installations de chantier (`base_vie`, `stockage_chantier`), éléments
agrivoltaïques (`limite_paddock`, `bac_equarrissage`, `espace_vert`) et
compléments d'aire de charge BESS (`citerne_refroidissement`, `zone_remise`),
tous comptés au tableau bilan.

**Trois types de poste, trois légendes.** Le tableau bilan compte séparément le
poste de livraison seul (9 × 3 m), le poste de transformation seul (10 × 3 m) et
le poste de livraison **et** de transformation (12 × 3 m). Les catégories `pdl`,
`ptr` et `pdl_ptr` les distinguent ; les confondre interdisait au lot 4 de les
dessiner différemment. Le poste de transformation d'une aire de charge BESS est
un PTR et hérite de sa légende.

Attention au nom du calque : `UNI_PDL` porte en fait un **PDL/PTR** sur les deux
projets de référence — le tableau y compte 1 PDL/PTR, 0 PDL et 0 PTR. C'est le
tableau qui tranche, pas le nom, et un projet portant un PDL seul demandera de
corriger l'appariement à l'écran.

Deux distinctions valent d'être notées, parce que les manquer produit des
mesures fausses : la **haie existante** n'est pas la haie plantée — l'une est un
état des lieux, l'autre un aménagement — et le **portail d'exploitation** n'est
pas le portail d'accès, que seul le tableau bilan compte. Les confondre donnait
4 portails au plan contre 1 au tableau, et faisait échouer un contrôle qui avait
raison de se plaindre.

`UNI_VRD_Voirie` est apparié à `voirie`, une catégorie qui dit son ignorance :
le calque ne précise pas si la piste est lourde ou légère, alors que le tableau
bilan sépare les deux. Le lot 4 doit trancher, pas supposer.

### Ce qui est écarté, et pourquoi

Le plan de Sarnois porte 55 calques. Sans tri, l'import produisait **71
avertissements**, et un écran d'avertissements que personne ne lit ne protège de
rien. Trois familles sont donc écartées d'office, **regroupées en une ligne
chacune** :

| Famille | Raison |
|---|---|
| `CAD_*` | fond cadastral du BE ; le dossier prend le sien du WFS IGN |
| `UNI_Legende`, `UNI_Echelle`, `UNI_Traits de cosntruction` | mobilier de dessin |
| couches de travail PVcase, maillage topographique, habillage décoratif | ni ouvrage ni mesure |
| `UNI_ZIP` | contour d'étude ; **seule la clôture délimite le projet au dossier** |
| `0` | calque de travail du BE, censé être vide à l'export |
| `UNI_PDL-PDT_Zone_Ombre` | étude d'ombrage |
| `VAL-PDL` | doublon du remplissage des plateformes |

`VAL-PDL` a demandé une mesure pour être identifié : ses deux boucles ont le
même centre et la même aire que celles de `UNI_VRD_Plateforme`, à 1 m² près
(81,8 contre 82,9 m², 94,4 contre 95,5 m²). Les importer dessinerait chaque
plateforme deux fois.

S'y ajoutent les **annotations** — textes, cotations, points, volumes — écartées
et comptées en une ligne plutôt qu'un avertissement par calque.

Écarter n'est pas ignorer en silence : chaque groupe est affiché, et tout calque
reste appariable à la main. Un calque vraiment inconnu, lui, garde son
avertissement propre — c'est là qu'une décision est attendue. Après tri, Sarnois
descend à 22 avertissements et Saint-Cyr reste à zéro.

Deux détails du tri méritent d'être dits. « cosntruction » est la faute de
frappe du fichier réel, reprise telle quelle : la normalisation efface les
accents et les séparateurs, pas les fautes. Et `GREY` et `Edges`, 1 594 et 195
entités qui noyaient la liste, sont l'habillage de blocs décoratifs — dont
« Sheep rs », le mouton des plans agrivoltaïques.

Trois pièges mesurés sur le fichier de référence :

- **les `HATCH` doublent les polylignes.** Les 13 remplissages du fichier
  redessinent exactement des contours déjà présents sur le même calque (aire
  identique au centième de m²). Ils sont écartés — mais un calque qui n'aurait
  *que* des `HATCH` perdrait son élément, et c'est signalé ;
- **les polylignes portent des arcs en bulge**, invisibles dans la liste des
  sommets et absents du brief. Les deux plateformes en portent. Sans
  discrétisation, celle du PDL sort à 133,8 m² au lieu de 131,4 ;
- **les tables sont des polylignes 3D**, avec des sommets qui peuvent se
  superposer en plan. Le dédoublonnage se fait sur (x, y) **en préservant
  l'ordre** ; un `set()` détruirait la géométrie.

`ezdxf.path.make_path` traite d'une seule main les bulges, les polylignes 3D,
les lignes et les arcs, en conservant Z. C'est ce qui évite de réimplémenter la
discrétisation à la main.

Les portails sont dessinés en cinq entités jointives (deux vantaux, leur
débattement en arcs, l'ouverture). Ils sont donc comptés par regroupement au
contact, à 5 cm près, et non en comptant les entités.

**L'azimut des tables se calcule sur la géométrie**, pas sur le tableau :
rectangle englobant orienté de chaque table, direction de son grand côté,
médiane sur l'ensemble. Sur le fichier de référence il vaut 0,0000°, soit des
rangées est-ouest. La médiane est prise après recalage sur la moyenne axiale :
sur des rangées nord-sud, des directions voisines sur le terrain tombent aux
deux bouts de ]-90, 90] et une médiane naïve rendrait la perpendiculaire.

### Lecture du tableau bilan

L'onglet des caractéristiques est en colonnes, une par indice de révision. Il
s'appelle `2. Caractéristiques du projet` en version 6 du tableau et `Projet`
en version 10 : les deux noms sont acceptés, un nom inconnu est refusé en
listant les onglets présents.

L'indice est **proposé** d'après le nom du DXF (`20260903_SCV_IND06`) et
**toujours confirmé** ; son absence du tableau est signalée en évidence.

Un indice peut porter un **suffixe alphabétique** : `IND10A` et `IND10B`
désignent deux variantes d'un même indice — à Sarnois, deux réductions du projet
passant sous les 3 MWc, qui diffèrent de 85 à 90 tables et de 4,87 à 3,48 ha.
Ne pas le reconnaître les écartait de l'en-tête sans rien dire, et l'outil
concluait que le plan était en avance sur le tableau alors que les colonnes
étaient là. La lettre ne doit être suivie d'aucun autre caractère
alphanumérique : sans cette garde, `IND06final` rendrait l'indice `IND06F`.

Les valeurs composites s'écrivent `13 / 26` en version 6 et `269 & 27` en
version 10 ; les deux formes sont reconnues. Là où elles portent un nombre de
tables, les contrôles portent sur le total, mais la chaîne d'origine est
conservée à côté — la décomposition en deux formats de table ne doit pas
disparaître dans la somme.

**Chaque paramètre est repéré par son libellé en colonne A, jamais par son
numéro de ligne.** Le fichier est déjà en version 6, la mise en page bouge, et
un accès par index produirait des valeurs fausses sans aucune erreur visible. Un
libellé qui apparaîtrait deux fois est refusé plutôt que lu au hasard.

Les convertisseurs sont tolérants sur la forme — `0°` avec le symbole degré,
`13 / 26` pour les deux longueurs de table, dates en `datetime` — et
**échouent explicitement** quand le motif ne correspond pas.

L'onglet `Dimensions postes et pieux` fournit les cotes normalisées pour la
génération paramétrique des DP 4 au lot 4. **L'ordre des cotes n'est pas le même
d'une section à l'autre** : « largeur x longueur x hauteur » pour le PTR,
« longueur x largeur x hauteur » pour le PDL/PTR. Il est conservé avec chaque
cote ; le lot 4 doit le lire, pas le supposer.

L'onglet `Standards UNITe` fournit les valeurs de référence du type de projet.
Elles sont **affichées en regard**, jamais opposées au projet : sur le fichier
de référence, quatre d'entre elles s'écartent du projet (format de table,
inter-table, hauteurs) sans que ce soit une anomalie. Un standard n'est pas une
contrainte.

### Contrôles croisés

C'est la valeur de ce lot. Le scénario d'erreur réaliste n'est pas le fichier
corrompu : c'est le plan mis à jour sans le tableau, ou l'inverse, que personne
ne remarque avant l'instruction du dossier.

| Contrôle | Tolérance | Si échec |
|---|---|---|
| Nombre de tables, DXF vs tableau | égalité stricte | bloquant |
| Nombre de portails, DXF vs tableau | égalité stricte | bloquant |
| Surface clôturée, polygone DXF vs tableau | 2 % | bloquant |
| Linéaire de clôture, DXF vs tableau | 2 % | avertissement |
| Surface projetée des modules vs aires de tables | 5 % | avertissement |
| Surface de voie lourde, dessinée vs déclarée | 5 % | avertissement |
| Surface de piste légère, dessinée vs déclarée | 5 % | avertissement |
| Inclinaison des rangées, mesurée vs déclarée | 2°, en valeur absolue | avertissement |
| Clôture contenue dans l'emprise cadastrale | 1 m² | avertissement |
| Puissance vs seuil de recevabilité en DP | saisie | avertissement |

Le seuil de 1 m² sur le débordement n'est pas arbitraire : sur le jeu de
référence, la clôture dépasse de **0,53 m²** de l'emprise cadastrale réelle.
C'est de l'imprécision de numérisation du parcellaire, pas un débordement — un
vrai débordement se compte en dizaines de m².

À noter sur l'export parcellaire du géoportail : il porte **deux fois le même
polygone**, géométriquement identiques, 4,5259 ha chacun. `charger_emprise` en
fait l'union et rend un seul polygone, ce qui évite d'en compter la surface deux
fois — mais si un jour un export contient deux parcelles *distinctes*, elles
seront unies de la même façon.

#### Les surfaces de piste

Le lot 4 annonce ces surfaces au dossier : elles doivent correspondre à ce que
la planche montre. La comparaison porte sur l'**union** des polygones et non sur
leur somme, pour qu'une aire de grutage posée sur la voie qu'elle élargit ne
compte pas deux fois sa partie commune. Une piste absente du plan *et* du
tableau n'appelle pas de contrôle.

La tolérance est de 5 %, plus lâche que celle de la clôture : le tableau calcule
ces surfaces en longueur × largeur là où le plan les dessine en polygones.

Sur les trois jeux de référence, le contrôle attrape deux choses différentes :

| | dessiné | déclaré | |
|---|---|---|---|
| Saint-Cyr | 3 362 m² | 3 365 m² | ✅ 0,1 % |
| Sarnois A | 1 280 m² | 1 538 m² | ⚠️ −16,8 % — aire de grutage **non dessinée** |
| Sarnois B | 1 551 m² | 1 423 m² | ⚠️ +9,0 % — voie lourde **plus large** que déclarée |
| pistes légères A et B | 3 424 / 2 446 m² | 3 424 / 2 447 m² | ✅ 0,0 % |

**Lire le tableau bilan a demandé un détour** : « Surface piste enherbée (m²) »
y apparaît **deux fois**, une fois en cours de section et une fois au total. Le
lecteur refusant par principe un libellé ambigu, le total se recompose depuis
les lignes « interne » et « externe », qui ne le sont pas. Une troisième ligne,
celle qui porte le libellé ambigu, n'est pas lue — si un projet y range sa piste
légère, ce contrôle le montrera plutôt que de le taire. « Surface piste lourde
(m²) », elle, n'apparaît qu'une fois et se lit directement.

#### Le champ « Azimut (°) » n'a pas de convention

Relevé sur trois dossiers le 03/09/2026 : `0°` pour un champ plein sud, donc
0 = sud ; `41° SE` avec la direction en toutes lettres ; `-24,5` sans direction
et de signe contraire pour une orientation de la même famille. Ailleurs encore,
le sud est noté 180, en azimut compas.

Le contrôle ne compare donc que **des valeurs absolues**, après avoir ramené les
deux angles dans ]-90, 90]. Le repliement absorbe l'origine — 0 ou 180 pour le
sud — et la valeur absolue absorbe le sens de comptage. Ce qui subsiste, de
combien les rangées s'écartent de l'est-ouest, est la seule grandeur que les
trois écritures expriment de la même façon.

Ce que ce contrôle ne voit pas, et qu'il faut savoir : **un plan monté en
miroir**, tables à -41° là où le tableau décrit +41°. L'attraper demanderait une
convention écrite au tableau, et il n'y en a pas. La cellule est affichée telle
qu'écrite à côté de la mesure, pour que la lecture reste possible à l'œil.

La cellule est d'ailleurs lue deux fois, en nombre et en texte : un
convertisseur numérique seul avalait le « SE » de `41° SE` sans rien dire.

Rien de tout cela n'atteint la coupe A-A', qui n'utilise que l'azimut mesuré sur
la géométrie.

**L'écriture des sorties est refusée tant qu'un contrôle bloquant subsiste.**
Produire le contrat d'interface du lot 4 à partir d'entrées qui se contredisent
reviendrait à fabriquer un dossier plausible et faux.

Le seuil de recevabilité en déclaration préalable **n'est pas codé en dur** :
c'est une règle d'urbanisme, qui change, et la figer dans le code reviendrait à
faire dire au générateur ce qu'il n'a pas à dire. Il est saisi par
l'utilisateur, et la puissance du projet est affichée en évidence dans tous les
cas, avec la phase et la date du tableau — le chef de projet doit voir sur quel
indice il engage le dossier.

### Ligne de coupe A-A'

**Sa direction vient des rangées, sa position du nombre de rangées traversées.**
Le tracé du chef de projet dit qu'il veut une coupe ; la géométrie dit où elle
apprend le plus. La coupe étant perpendiculaire aux rangées, la déplacer revient
à la faire glisser le long d'elles, et la recherche se fait sur la **moitié
centrale** de l'emprise : une coupe collée au bord du site ne montre ni terrain
ni tables, et un dossier ne se juge pas sur son coin. À nombre de rangées égal,
la position la plus centrale l'emporte — deux générations du même dossier coupent
ainsi au même endroit.

Le critère est celui du dessin, et il a fallu le mesurer pour s'en rendre compte.
Compter les tables avec `intersects` compte aussi celles qu'on effleure au coin :
mesuré le 05/09/2026 sur Sarnois, la position ainsi jugée optimale longeait le
bord d'une rangée, annonçait 15 tables et n'en coupait réellement que 5 — la
planche en montrait cinq, groupées sur un bout du profil. Une table ne compte
donc que si la ligne la traverse sur une longueur.

Le lot 2 (HelioScope) n'en bénéficie pas : ses tables sont en repère DXF local
quand le tracé et l'emprise sont en Lambert 93, et les confronter demanderait un
travail de calage. Sa coupe garde le point milieu du tracé, et sa façade le dit.

Elle n'existe ni dans le DXF ni dans le tableau : elle se pose sur une carte
interactive, sur fond d'ortho IGN, avec les tables et la clôture en
surimpression.

La direction vient de l'azimut mesuré sur les tables, perpendiculairement aux
rangées — une coupe de terrain n'a de sens que dans cette direction, et quelques
degrés d'oblique allongent toutes les distances lues sur la planche du facteur
1/cos θ, sans que rien ne le signale.

#### Déplacer la coupe : « Déplacer la coupe », puis un clic

Le bouton **« Déplacer la coupe »** arme la carte, une bannière annonce ce qu'on
attend, et le clic suivant fait glisser la coupe pour qu'elle passe par ce point,
**en gardant la perpendiculaire aux rangées**. Un rechargement par clic, celui du
bouton « Corriger » d'à côté. Pas de curseur d'angle ni de glissement continu :
dans Streamlit, chaque cran relancerait le script.

**Ce geste a été ajouté parce qu'il n'existait pas.** La coupe proposée à
l'import annonçait que le chef de projet « la déplace seulement si elle lui
déplaît », et rien ne permettait de la déplacer — mesuré dans le code le
14/09/2026. Retracer un segment appelait la correction avec les tables, qui
**recalcule entièrement la position** et repose la coupe exactement où elle
était : le tracé ne servait que de déclencheur, le geste était vide. Le seul
contournement, « Conserver la direction tracée », conservait aussi la direction —
donc l'oblique d'un tracé à main levée. La combinaison qui manquait est celle-ci :

| | direction | position |
|---|---|---|
| automatique | imposée ✔ | recalculée, le tracé est ignoré |
| manuel | tracée ✘ | tracée ✔ |
| **déplacer la coupe** | **imposée ✔** | **choisie ✔** |

Côté géométrie, rien de neuf à calculer : `translater_ligne_coupe` reçoit un
point au lieu d'un tracé, impose la perpendiculaire et étend à l'emprise. L'écart
de la coupe déplacée à la perpendiculaire aux rangées vaut **zéro** — c'est ce qui
la distingue du mode manuel, et c'est mesuré.

**Un clic hors de portée du site lève**, avec la distance du point au bord de
l'emprise, et la coupe précédente reste en place — contrairement au tracé, dont
l'échec l'effaçait. Le profil du terrain est effacé avant d'être redemandé : un
RGE ALTI muet laisse ainsi un trou visible, et non le relevé de la coupe d'avant
sous une ligne qui a bougé.

Le tracé polyligne **reste**, replié sous « Tracer la coupe à la main » : le mode
manuel en dépend.

La ligne est étendue à toute l'emprise clôturée avec 10 m de marge de chaque
côté. L'étendue se calcule en projetant les sommets de l'emprise sur la
direction de coupe, et non sur la diagonale de sa boîte englobante : une emprise
allongée en biais donnait sinon une coupe deux fois trop longue.

Un tracé à plus de 45° de la perpendiculaire attendue est corrigé quand même,
mais l'utilisateur en est averti : il a probablement voulu couper dans l'autre
sens. Un mode manuel conserve la direction tracée ; il est désactivé par défaut
et reste un choix explicite.

Sur le fichier de référence, les rangées étant est-ouest, la coupe ressort
strictement nord-sud.

**Une régénération ne redemande jamais le tracé.** Rouvrir un dossier qui a déjà
une sortie dans `sortie/{projet}/` reprend la coupe et le profil.

Ce qui est repris est le **tracé initial**, pas la ligne corrigée : la correction
dépend de l'azimut des tables et de l'emprise clôturée, qui changent si le BE
fournit un nouvel indice. Rejouer la correction sur le tracé d'origine redonne
une coupe juste ; recharger la ligne corrigée telle quelle la figerait sur un
plan qui n'existe plus, et elle ne serait plus perpendiculaire aux rangées.

**Ce qui se rejoue est le geste qui avait été fait, et non toujours le même.** La
sortie garde un champ `position_choisie` : une coupe déplacée à la main se rejoue
par une translation, pas par une correction. Rejouée comme un tracé, elle voyait
sa position recalculée sur le nombre de rangées traversées et reposée à
l'automatique — le choix du chef de projet perdu à la régénération suivante, et
annoncé de surcroît comme un déplacement dû au plan. La direction, elle, est bien
reprise du plan d'aujourd'hui : c'est la position seule qui est conservée.

Le point rejoué est le milieu de la ligne enregistrée, faute d'avoir gardé le
point cliqué lui-même. Les deux sont équivalents tant que le plan n'a pas tourné,
l'étendue se calculant à l'identique pour n'importe quel point de la ligne ; si
l'azimut a tourné de θ, la coupe glisse en plus de la demi-longueur fois sin θ, et
l'écart mesuré le dit. Les sorties écrites avant le 15/09/2026 n'ont pas ce champ
et rejouent la correction, comme avant — elles n'avaient pas de position choisie
à conserver.

**Une coupe qui ne rencontre pas le site est refusée.** Deux projets enregistrés
sous le même identifiant de dossier partagent leur dossier de sortie : rejouer
le tracé de l'un sur le plan de l'autre donnait une ligne à 185 km de là, avec
un profil du terrain d'apparence parfaitement normale relevé quelque part entre
les deux sites. Le déplacement était bien signalé, mais un avertissement ne
suffit pas quand le résultat se dessine sans anomalie. Le critère est
géométrique et sans seuil arbitraire : la ligne corrigée doit couper l'emprise
clôturée.

Le profil déjà relevé n'est réutilisé que si la ligne recalculée retombe au même
endroit, à 0,1 m près — bien en dessous du pas d'échantillonnage de 5 m. Sinon il
est relevé à nouveau, et le déplacement est annoncé. Le mode manuel est repris
avec le tracé.

Le `projet.json` du lot 1, qui porte le même nom dans `projets/`, est refusé à la
relecture sur son champ `origine` : y chercher une ligne de coupe ne rendrait
rien de bon. Une version de contrat plus récente que celle que l'outil sait lire
est refusée aussi, plutôt que reprise à moitié.

### Le clic armé sur la carte

Le mécanisme est écrit une fois pour tous les gestes de la carte : le lot 6 y
ajoutera le placement d'un point de vue et sa visée, en le reprenant plutôt qu'en
en écrivant un second. Un bouton arme un geste, une bannière annonce ce qu'on
attend, le clic suivant est consommé par ce geste, et l'armement s'annule.

Armer et désarmer relancent le script, sans quoi l'écran reste d'un tour en
retard sur lui-même : la bannière s'affichait sous un bouton qui proposait encore
de déplacer la coupe, sans moyen d'annuler, et l'inverse à l'annulation — une
bannière réclamant un clic que plus rien n'attendait.

**Un trait pointillé suit la souris tant que le geste est armé**, et montre où
la coupe se posera avant qu'on clique. Il est entièrement dessiné par Leaflet
dans le navigateur : rien ne remonte à Streamlit tant que le chef de projet n'a
pas cliqué. Le faire côté Python demanderait `return_on_hover`, qui relance le
script à chaque mouvement de souris — la carte se redessine, le plan se
recompose, et l'écran pédale.

Il repose sur une propriété mesurée le 15/09/2026 : **déplacer la coupe la
translate en bloc**. L'étendue se calcule en projetant les sommets de l'emprise
sur la direction de coupe *relativement au point de passage* ; déplacer ce point
perpendiculairement à la coupe ne change aucune de ces projections, et le segment
glisse sans tourner ni changer de longueur — vérifié exact au bit près. L'aperçu
est donc la coupe affichée, translatée jusqu'au curseur, et non une coupe
recalculée à chaque mouvement.

La translation se fait en pixels de carte, Web Mercator, quand la coupe se calcule
en Lambert 93. Le Web Mercator est conforme, donc le trait reste parallèle ;
l'écart au tracé réel a été mesuré sur Saint-Cyr à **1,3 cm au pire**, contre
45 cm pour un pixel de carte au zoom 18. L'aperçu ne ment pas sur l'endroit où la
coupe ira.

Ce qui se lirait comme un défaut et n'en est pas : **la coupe n'est pas verticale
à l'écran**, et le trait se décale donc un peu latéralement quand on survole de
haut en bas. C'est la convergence des méridiens — le nord de grille du Lambert 93
n'est pas le nord vrai auquel le Web Mercator s'aligne. Mesurée à Saint-Cyr :
0,745°, soit 8,5 px pour 650 px de survol vertical, relevés à 7 px dans le
navigateur (Leaflet arrondit au pixel entier). Une coupe perpendiculaire aux
rangées l'est aux rangées, pas au bord de l'écran.

Le trait part invisible, apparaît au premier mouvement, disparaît quand la souris
quitte la carte, et porte `interactive: false` — sans quoi il intercepterait le
clic qu'il annonce.

**Au clic, il se fige.** Streamlit met une à deux secondes à rejouer le script —
relevé du profil et contrôles de cohérence compris — et pendant ce temps la carte
affichée est encore l'ancienne. Un trait qui continuait d'y suivre la souris
donnait à croire que le clic n'avait pas pris ; le chef de projet recliquait, et
son second point était ignoré puisque le geste était déjà désarmé. Relevé à
l'usage le 15/09/2026.

Leaflet, lui, voit le clic tout de suite. Le trait se fige donc à cet instant,
devient plein et prend l'épaisseur d'une coupe retenue — ce n'est plus un aperçu,
c'est la coupe, que Streamlit n'a pas fini de redessiner — un bandeau annonce
« Coupe prise — relevé du profil du terrain… » et le curseur passe en `progress`.
Ni un survol ultérieur ni un second clic ne le déplacent. Vérifié dans un
navigateur sur la carte de Saint-Cyr.

**Le clic se consomme explicitement.** Vérifié le 15/09/2026 dans
`streamlit-folium` 0.27.2 : `last_clicked` est alimenté par l'événement `click` de
Leaflet, et **persiste** d'une exécution du script à la suivante tant que le
composant n'est pas remonté. Il dit où a eu lieu le dernier clic, pas qu'un clic
vient d'avoir lieu ; le lire sans mémoire ferait rejouer le même clic à chaque
interaction — un déplacement de coupe à chaque case cochée. Le dernier point vu
est donc retenu, **y compris quand aucun geste n'est armé** : sans cela, un clic
fait pour regarder le plan restait en réserve et armer un geste plus tard le
consommait aussitôt, la coupe sautant à un endroit cliqué bien avant.

Limite assumée : recliquer au pixel exact du clic précédent ne produit rien, le
composant n'envoyant pas de valeur inchangée. Le geste reste armé et le clic
suivant passe ; la coupe aurait de toute façon été la même.

**La carte ne remonte pas après une translation.** La clé porte un compteur qui
change à chaque coupe retenue par un *tracé*, pour chasser le trait Leaflet
résiduel qui se superposait sinon à la coupe redressée. Un clic ne laisse aucun
tracé résiduel : le compteur ne bouge pas, et le chef de projet garde son zoom.

**La carte ne relance plus le script pour un zoom.** `returned_objects` la
restreint aux trois valeurs que cet écran lit — `last_clicked`, `all_drawings`,
`last_active_drawing`. Sans cette restriction, le composant renvoyait aussi le
cadrage et le niveau de zoom, et déplacer la carte relançait tout. Mesuré dans son
bundle : la charge est filtrée sur cette liste, puis comparée à la précédente, et
`setComponentValue` n'est appelé que si elle a changé.

### Profil altimétrique

Récupéré automatiquement auprès du RGE ALTI de la Géoplateforme, échantillonné
tous les 5 m le long de la coupe corrigée.

Mesuré sur le service réel le 03/09/2026, et différent de ce qu'annonçait le
brief : ce n'est pas le nombre de points qui limite une requête mais **la
longueur de l'URL**. 200 points passent (URL de 4 736 caractères), 500 sont
refusés en HTTP 414 (11 636 caractères). Le POST répond 500 ou 400 sous ses deux
formes ; seul le GET fonctionne. Les requêtes ne sont pas parallélisées. Une
coupe de site tient en une requête : 355 m au pas de 5 m font 73 points.

Le contrôle de cohérence compare le profil au **bord bas** des tables voisines
de la coupe. Attention à ce qu'il mesure : le Z des tables est celui du plan des
modules, pas du sol. Sur le fichier de référence, le bord bas se tient 1,70 m
au-dessus du RGE ALTI en médiane (de 1,15 m à 2,00 m selon la table) — c'est la
garde au sol de la structure, pas une erreur. Le contrôle compare donc la
**médiane** des écarts au seuil de 2 m : ce qu'il cherche est un décalage de
référentiel altimétrique, qui se compte en dizaines de mètres, pas la valeur
zéro.

Un relevé altimétrique en TXT prend le pas sur l'appel automatique, quand le
service est indisponible. **Une seule forme est acceptée : trois colonnes
`X Y Z` en Lambert 93**, celle que produit l'outil interne. Le séparateur est
**déterminé une fois** sur la première ligne de données puis annoncé : la
virgule est à la fois séparateur de colonnes en CSV anglo-saxon et séparateur
décimal en français, et `0,0;0,0;100,00` compte trois colonnes, pas six. Une
ligne d'en-tête non numérique est sautée.

Une forme à deux colonnes « abscisse ; altitude » avait d'abord été acceptée,
écrite sans exemple à la main. Elle a été retirée : aucun outil du parc n'en
produit, et le lecteur ne devinait le format que sur le nombre de colonnes. Un
export `matricule ; altitude`, que tout géomètre peut fournir, était lu comme un
profil — altitudes justes, placées à des abscisses de 11 700 m sur une coupe de
250 m, donc toutes hors de la coupe et rabattues sur la première valeur. Un
profil plat, crédible, faux.

Trois colonnes ne suffisent pas non plus : encore faut-il que la dernière soit
une cote. Rien dans un fichier de nombres ne dit ce que chaque colonne signifie,
et le seul garde-fou possible est l'ordre de grandeur. Les altitudes doivent
tenir entre **−50 et 5 000 m**, du polder du Nord au mont Blanc. La fourchette
est large à dessein : elle ne valide pas un relevé, elle refuse un fichier dont
la troisième colonne n'en est pas une. Un export `X Y` sans altitude passait
sans rien dire et rendait un profil plat à 6 954 200 m.

**Un relevé à trois colonnes est un nuage, pas un profil.** Le fichier de
référence `exemples/rosnay-lhopital-topo/` porte 202 399 points sur une grille au
mètre couvrant 605 × 494 m. Seuls ceux d'un couloir de ±2 m autour de la coupe
sont retenus, et les altitudes de même abscisse y sont moyennées. Une coupe que
le nuage ne traverse pas est refusée, et un trou de plus de 10 m dans le couloir
est signalé.

Ce couloir n'est pas un raffinement : la première version projetait tout le
nuage sur la coupe puis triait par abscisse, si bien qu'à chaque abscisse c'était
le dernier point trié qui l'emportait, quelle que soit sa distance à la coupe.
Mesuré le 03/09/2026, le profil s'écartait du profil réel de 2,57 m, d'amplitude
3,14 m, pour un relief de 3,50 m — c'était du bruit, et rien ne le signalait. Le
filtre par boîte englobante préalable fait au passage tomber la lecture de 4,1 s
à 0,4 s.

#### Les altitudes portées par le DXF servent de contrôle, pas de source

Certains plans du BE embarquent leur propre terrain. Ceux de Sarnois en portent
**trois**, et ils ne disent pas la même chose. Comparés au RGE ALTI le
03/09/2026 :

| Source | écart médian | dispersion |
|---|---|---|
| `-TopoNiveau`, points cotés du géomètre | −0,13 m | 0,11 m |
| `PVcase Topographic Mesh`, bâti sur ces points | −0,14 m | 0,19 m |
| `PVcase Online Terrain` | **−0,80 m** | **0,04 m** |

La dernière ligne est la plus instructive : 4 cm de dispersion pour 80 cm
d'écart, c'est **le même terrain à un décalage constant près** — donc un autre
référentiel altimétrique, pas un relevé imprécis. Le nom du calque dit
probablement pourquoi : un modèle téléchargé, pas un levé de géomètre.

Le profil du dossier reste donc celui du **RGE ALTI**, référence altimétrique
nationale que l'instructeur peut vérifier, et les altitudes du DXF le
**contrôlent**. Chaque source est jugée séparément — les fusionner masquerait
précisément le désaccord qu'on veut voir — et l'écart est qualifié : une
dispersion faible autour d'une médiane non nulle est signalée comme un décalage
de référentiel, une dispersion large comme deux terrains différents.

Le seuil est de 25 cm : il laisse passer le levé du géomètre et attrape le
terrain téléchargé.

Ces points ne sont jamais dessinés, et leurs calques restent écartés du plan.

Ce relevé est un repli, pas une source à préférer. Sur le segment de contrôle, le
nuage du BE et le RGE ALTI s'accordent à ±0,10 m avec un écart-type de 0,02 m :
l'outil topographique interne rééchantillonne le RGE ALTI, il n'apporte pas une
mesure de terrain plus fine.

### Écran de validation

Rien ne se poursuit sans validation explicite. L'écran présente l'aperçu des
géométries sur fond d'ortho IGN, la correspondance des calques, les paramètres
extraits, le résultat des contrôles, la ligne corrigée superposée au tracé
initial, et le profil tracé avec sa dénivelée.

**Les couleurs du DXF ne sont pas héritées.** Les codes ACI y sont des couleurs
de travail CAO, non signifiantes : sur le fichier de référence, la clôture, le
PDL et les portails partagent la valeur 1. La palette est celle de la légende
DP, relevée au pixel le 03/09/2026 sur la planche DP 2 du dossier HOCH
« Les Islettes » : poste de livraison (127, 255, 191), citerne (63, 191, 191),
piste lourde (162, 162, 162), piste légère (215, 215, 215), haie (111, 170, 11),
clôture et portail en rouge franc, modules (151, 202, 202) cernés de bleu.
Les catégories absentes de cette planche — BESS, bac de rétention, local
technique — sont dérivées de la même famille, et signalées comme telles dans le
code.

L'ordre de dessin est explicite : surfaces de sol, puis ouvrages posés dessus,
puis tables, puis linéaires. Suivre l'ordre du dictionnaire faisait passer les
pistes par-dessus le poste de livraison, qui disparaissait de l'aperçu —
exactement ce que cette image sert à contrôler.

L'échelle verticale du profil est exagérée, l'exagération étant **mesurée sur
les axes réellement composés** et écrite sur la figure. Sans cela, 0,96 m de
dénivelée sur 355 m de coupe donnerait une ligne parfaitement plate.

### L'export trié, et ce qu'il a changé

Le BE a livré le 04/09/2026 des exports ne contenant que les éléments utiles.
L'effet est net :

| | export complet | export trié |
|---|---|---|
| Calques peuplés | 55 | 27 / 29 |
| Appariés | 20-21 | **23 / 25** |
| Écartés | 30-31 | **3** |
| À décider | 3-5 | **0** |
| Poids du fichier | 47-50 Mo | 15-16 Mo |

Il apporte surtout **la distinction des pistes**, qui manquait au lot 4 : la
légende du dossier de référence sépare piste lourde et piste légère, et le DXF
n'avait qu'un axe indifférencié. Mesurées contre le tableau bilan, les nouvelles
couches tombent juste — 1 280 m² relevés pour 1 280 déclarés en voie lourde
interne sur l'indice A, 3 424 pour 3 424 en piste légère, 2 446 pour 2 447 sur
l'indice B.

#### L'aire de grutage se dessine en voie lourde

Ce n'est pas un ouvrage distinct mais un **élargissement ponctuel de la voie
lourde** : le tableau bilan ne lui donne pas de ligne de surface propre, il la
compte en « supplément piste lourde », et la légende du dossier de référence n'a
pas cette entrée. Sa catégorie existe donc, mais elle porte le style et
l'intitulé de la voie lourde — deux catégories dessinées à l'identique
n'apparaissent qu'une fois en légende, leurs objets comptés ensemble.

Le BE ne dessine pas toujours son contour. Sur l'indice B de Sarnois, le calque
ne porte que **deux croix** : quatre segments dont chaque paire partage
exactement le même milieu et la même longueur. Ce sont les diagonales de deux
rectangles — un rectangle est le seul quadrilatère dont les diagonales se
coupent en leur milieu et ont même longueur — et l'enveloppe convexe de leurs
extrémités les restitue : 12,0 × 19,0 m et 12,0 × 15,0 m, la seconde étant
exactement l'aire « 12x15m » de la légende du plan. La part qui déborde de la
voie lourde vaut **263 m² pour 255 déclarés** au tableau, soit 3 %.

Cette reconstruction ne s'applique **qu'à défaut de polygone** : un contour
dessiné fait toujours foi. Elle reste une convention de dessin déduite d'un seul
fichier, et elle est signalée à chaque import pour que ça se voie. Le contrôle
des longueurs de diagonales est ce qui empêche deux traits quelconques se
croisant en leur milieu de passer pour une aire de grutage.

Les intitulés du contrat suivent désormais **la légende du plan du BE** plutôt
que les miens : « voie lourde », « piste légère », « aire de grutage »,
« arbres existants ». Le PDF du plan porte cette légende, et s'en servir évite
d'inventer un vocabulaire parallèle.

Deux conséquences sur la lecture du DXF :

- **les arbres existants sont des maillages 3D**, que `ezdxf.path` refuse — « Unsupported DXF type PolyMesh or PolyFaceMesh » — et sur lesquels l'import
  échouait. Ce qui se dessine d'un arbre sur un plan de masse étant son houppier
  vu du dessus, c'est l'enveloppe convexe des sommets qui est retenue : 292
  arbres sur l'indice A, de 0 à 70,7 m² chacun, 6,4 m² en médiane. Attention aux
  **enregistrements de face** du maillage, qui n'encodent que des indices : les
  compter comme des points donnait des houppiers de plusieurs millions de m² ;
- **le calque `0` est écarté d'office.** Le BE le confirme : c'est son calque de
  travail, censé être vide à l'export. Ce qui s'y trouve y est par oubli — sur
  l'indice A une zone de contention de 70 m², sur l'indice B des traits de
  construction. Il reste appariable à la main, ce qui a permis de récupérer la
  zone de contention sans faire rééditer le fichier.

### Ce que le pilotage de l'application sur Sarnois a corrigé

Les écrans avaient été éprouvés sur Saint-Cyr — 9 calques, 9 catégories. Sarnois
en porte 55 et 18, et le DXF pèse 47 Mo. Trois défauts n'apparaissaient qu'à
cette échelle :

- **L'aperçu plantait** sur une `GEOSException`. `cadre_apercu` unissait toutes
  les géométries pour en prendre les bornes, et l'union échoue sur le polygone
  auto-intersectant du calque « ESPACE VERT ». L'enveloppe se lit maintenant sur
  les bornes de chaque géométrie, ce qui est plus rapide et marche sur
  n'importe quelle forme. Une géométrie invalide est signalée à l'import : les
  surfaces qu'on en tire sont douteuses.
- **L'écran de correspondance alignait les 55 calques à plat**, obligeant à
  faire défiler le fond cadastral pour trouver ce qui compte. Il est désormais
  en trois blocs : appariés, à décider, écartés d'office repliés. Sur Sarnois :
  21, **3**, 31 — et les trois à décider sont exactement les trois questions
  en suspens avec le BE.
- **Le cache de l'écran servait un appariement périmé.** Sa clé portait le
  chemin et la taille du fichier, que l'élargissement de la charte ne change
  pas : l'écran présentait 34 calques « à décider » là où il n'en restait que 3.
  La clé porte maintenant une empreinte des tables d'appariement.

Un quatrième, trouvé au passage et plus grave, est décrit au paragraphe de la
ligne de coupe : un tracé repris d'un autre projet produisait un profil
d'apparence normale relevé à 185 km du site.

### Sorties — contrat d'interface avec le lot 4

```
sortie/{projet}/
    geometries.gpkg   GeoPackage EPSG:2154, une couche par catégorie,
                      dont la ligne de coupe corrigée
    projet.json       paramètres techniques, azimut des tables,
                      profil altimétrique le long de la coupe
```

**GeoPackage et non GeoJSON** : la spécification GeoJSON impose le WGS84, et y
stocker du Lambert 93 est non conforme — cela se paie tôt ou tard par une
reprojection silencieuse chez le lecteur. Le GeoPackage porte son système de
coordonnées explicitement.

La coordonnée Z est conservée telle que le DXF la porte, et la colonne `z_reel`
dit si elle décrit le terrain (les tables) ou seulement l'élévation d'une
polyligne 2D (tout le reste sur le fichier de référence). Le champ
`version_contrat` permettra au lot 4 de refuser une sortie qu'il ne sait pas
lire ; le lot 2 en réserve devra produire exactement le même format.

⚠️ Ce `projet.json` **n'est pas celui du lot 1**. Celui du lot 1 vit dans
`projets/{nom}/` et décrit les métadonnées du dossier ; celui-ci vit dans
`sortie/{nom}/` et est la sortie de l'import BE. Son champ `origine` vaut
`import_be` et les distingue à la lecture.

**Aucune planche n'est produite** : le dessin relève du lot 4.

### Valeurs mesurées sur le jeu de référence

Projet Saint-Cyr-en-Val, `20260903_SCV_IND06.dxf`,
`20260825_SCV_Tableau_Bilan_V6.xlsx` et l'export parcellaire
`phu_45590_…geoperso…`, tous versionnés dans `exemples/saint-cyr-DXF/`. C'est le
seul jeu où toutes les pièces d'entrée sont présentes : un test vérifie qu'il ne
lève ni contrôle bloquant ni avertissement.

| Grandeur | Tableau | DXF |
|---|---|---|
| Tables | 96 | 96 |
| Modules | 4 628 | — |
| Surface clôturée | 4,52 ha | 4,5216 ha |
| Linéaire de clôture | 875 m | 871,88 m |
| Portails | 3 | 3 |
| Inclinaison / azimut | 15° / 0° | azimut 0,0000° |
| Point bas / point haut | 2,5 m / 4,0 m | — |
| Puissance | 2,93878 MWc | — |
| Emprise cadastrale | — | 4,5259 ha, clôture débordant de 0,53 m² |

## Planches du projet (lot 4)

DP 2, DP 3 et les DP 4 se dessinent depuis le **contrat d'entrée** —
`sortie/{projet}/geometries.gpkg` et `sortie/{projet}/projet.json` — sans savoir
lequel des deux lots l'a écrit. Le champ `origine` ne sert qu'à deux choses : le
dire au rapport, et savoir que le Z d'un dossier HelioScope ne décrit pas le
terrain.

Un contrat absent est un cas normal : le dossier s'arrête alors au plan de
cadastre et le rapport le dit. Un contrat présent mais refusé — version plus
récente que ce que l'outil lit, couche `voirie` dont personne n'a tranché le
type — fait échouer la génération : produire un dossier amputé de ses quatre
planches principales sans que rien ne l'explique serait pire.

### Deux repères, et un troisième qui n'existe pas

Le plan de masse et les plans de repérage sont **cartographiques** : ils passent
par la transformation Lambert 93 du lot 1. Les coupes et les dessins d'ouvrages
ne le sont pas : ils se composent en millimètres de papier, dans un repère local
(`dp_socle/planches/primitives.py`) qui a sa propre échelle.

Ce repère ne porte **qu'un facteur d'échelle pour ses deux axes**. Ce n'est pas
une consigne, c'est la structure : il n'y a pas moyen d'écrire une exagération
verticale. L'aperçu de contrôle du lot 2bis en applique une, avec raison — 0,96 m
de dénivelée sur 355 m y serait invisible — mais une planche qui déclare une
échelle à son cartouche ne le peut pas. Si le terrain est plat, la coupe est
plate, et c'est ce qu'elle doit dire.

Le moteur `Planche` n'a pas été modifié. Il ne trace, en millimètres, que des
lignes et des rectangles ; la silhouette humaine et les triangles des repères de
coupe sont **remplis par balayage**, en traits jointifs. La voie évidente —
déclarer la forme en `<pattern>` et la peindre par un rectangle, comme le fait la
hachure des bâtiments de DP 1-3 — a été essayée et écartée le 04/09/2026 : cairo
pixellise les motifs, et une silhouette de 35 mm en ressortait floue sur un
aperçu à 600 dpi. Un aplat de 20 mm passait, un de 3 mm était illisible : c'est
la taille du carreau qui décidait.

### Échelles adaptatives

Aucune échelle n'est figée. Le pas inter-rangées de Saint-Cyr est de 9,5 m contre
3 m aux Islettes, et la coupe de Saint-Cyr fait 355 m : au 1/300 elle mesurerait
1,18 m. Chaque dessin retient la **plus grande échelle** d'une liste normalisée
qui fasse tenir son contenu utile, et l'inscrit — au cartouche pour le dessin
principal, en clair à côté de lui pour les autres.

| Dessin | Liste | Contenu à faire tenir |
|---|---|---|
| Plan de masse | 1/500 à 1/5 000 | l'emprise cadastrale + 10 % |
| Coupe des tables | 1/50 à 1/200 | deux rangées complètes et leurs cotes |
| Coupe du terrain | 1/200 à 1/1 000 | la longueur de la coupe |
| Ouvrages DP 4 | 1/100, sinon 1/200 | **chaque** ouvrage, dans son cadre |
| Plan de repérage DP 4 | 1/300 à 1/1 000, **prolongée** | la zone concernée |

La dernière ligne est un écart au cadrage retenu, et il est mesuré. L'emprise
clôturée de Sarnois fait 327 x 264 m, soit 327 x 264 mm au 1/1 000, quand la zone
de dessin d'un A3 entier en mesure 410 x 268 : le plan de repérage remplirait la
planche à lui seul, et il ne resterait rien pour les dessins d'ouvrages que la
même planche doit porter. Aucune des échelles prévues ne tient dans un demi-A3
pour un site de 5 ha, qui est la taille courante de nos projets. La liste est donc
prolongée jusqu'au 1/5 000, et **tout dépassement est écrit au rapport**.

L'écart joue aussi dans l'autre sens : le 1/200 du brief est écarté. À cette
échelle le cadre serre les ouvrages de si près qu'on ne les situe plus dans le
site, et le zoom cesse d'être un plan de repérage — c'est un retour de relecture
du 04/09/2026. La plus grande échelle admise est le 1/300.

Les marges de mise en page sont serrées à dessein. Les échelles vont du simple au
double : trois millimètres de trop sur une planche DP 4 faisaient passer tous ses
ouvrages du 1/100 au 1/200, où le passage à petite faune de la clôture mesurait
moins d'un millimètre.

### Un blanc tournant, et le vide partagé entre les cadres

Les planches DP 3 et DP 4 sont structurées en sous-cadres, comme celles du
dossier de référence : un par coupe, un par ouvrage, un pour le plan de repérage,
chacun portant son titre et son échelle. Une seule valeur de marge les sépare —
le **blanc tournant** de `primitives.BLANC_TOURNANT_MM` — entre le cadre de la
planche et son contenu comme entre deux cadres voisins. Une marge qui change d'un
bloc à l'autre se remarque plus qu'elle ne sert.

Reste à décider ce que chaque cadre mesure. Le dimensionner sur son contenu et
donner le reste au suivant produit des cadres disproportionnés : celui du haut
plein à ras bord, celui du bas gardant une demi-feuille blanche. Les cadres sont
donc d'abord mesurés à vide, puis `primitives.repartir_hauteurs` partage le blanc
restant **à parts égales** entre eux, et chaque dessin est centré dans le cadre
qu'il reçoit. Les cadres n'ont pas la même taille — leurs contenus non plus —
mais ils respirent de la même façon.

### La page de garde tient la place du photomontage

Sans image de couverture, la moitié gauche de la page restait blanche et se
lisait comme une composition ratée. Un cadre tireté gris y tient désormais la
place, sous sa case titrée « VUE EN PERSPECTIVE DU PROJET » et portant la
mention « Photomontage à insérer » : le lecteur voit qu'il manque une pièce, et
le chef de projet sait laquelle.

### DP 2 — Plan de masse

Cadré sur l'**emprise cadastrale plus 10 %**, et non sur la clôture : le plan
doit montrer le contexte parcellaire alentour, comme celui du dossier de
référence. Une planche cadrée sur la seule clôture donnerait un projet posé dans
le vide.

Parcellaire et bâtiments viennent du WFS IGN, jamais du DXF ; les numéros de
parcelle reprennent la mécanique de DP 1-3, seuil de lisibilité compris. Pas de
fond raster : le plan de masse de référence est sur fond blanc, et une ortho
écraserait la lecture des ouvrages — c'est DP 1-2 qui porte la photo aérienne.

Un objet du plan qui tombe hors du cadre est **signalé**. Le contenu
cartographique est découpé sur la zone de dessin : il disparaîtrait sans rien
dire, et c'est le genre d'absence que personne ne rattrape à la relecture.

### DP 3 — Deux coupes, deux échelles, deux sources de hauteur

Une planche, deux dessins superposés. Le cartouche ne peut annoncer qu'une
échelle : il porte celle de la coupe des tables, et la coupe du terrain porte la
sienne en clair.

Les deux ne lisent pas les mêmes hauteurs, et c'est délibéré :

- la **coupe des tables** est un dessin de type. Elle prend `point_bas_m` et
  `point_haut_m` du tableau bilan, qui sont ce qu'annoncera la notice DP 11 —
  une planche qui contredit sa propre notice est une faiblesse à l'instruction ;
- la **coupe du terrain** est une coupe de site. Elle prend le Z du GeoPackage,
  qui décrit chaque table là où elle est posée. L'écart entre les deux sources
  n'est pas constant — 2,50 m déclarés contre 1,70 m mesurés à Saint-Cyr, 1,50
  contre 1,29 à Sarnois — mais à cette échelle 0,80 m fait moins de 3 mm.

Le rampant n'est pas lu mais **déduit** des deux hauteurs et de l'inclinaison :
`format_module` est une désignation commerciale (« G12R »), pas une dimension. Il
est ensuite recoupé deux fois, par la longueur de module qu'il implique et par le
pas déclaré, qui doit valoir l'inter-table plus la projection du rampant.

#### Ce que ce recoupement a montré sur Saint-Cyr

| Source des hauteurs | rampant | par module | pas attendu / déclaré |
|---|---|---|---|
| `structures` : 2,50 et 4,00 m | 5,80 m | **2,90 m** | 10,50 / 9,50 m |
| `standards_unite` : 1,10 et 2,34 m | 4,79 m | 2,39 m | 9,53 / 9,50 m |

Un module G12R mesure 2,384 m. La seconde ligne referme la géométrie à 3 cm
près ; la première donne un module de 2,90 m et manque le pas d'un mètre.

Les deux hauteurs déclarées ne décrivent donc **pas une table** : ce sont des
bornes d'enveloppe sur tout le site, comme le dit le PDF de profil du bureau
d'études avec ses « 2.5m min » et « 4m max ». Le dessin reste aux valeurs
déclarées, que la notice reprendra, et le rapport dit d'où vient l'écart au lieu
de laisser le chercher. C'est une chose à reprendre avec le bureau d'études, pas
un défaut du dessin.

#### Ce qu'un dossier HelioScope ne porte pas

Un export HelioScope ne décrit **aucune garde au sol** : son DXF est plat et le
tableau bilan n'existe pas. Chaque paramètre est donc cherché là où il peut se
trouver — l'inclinaison et le pas se mesurent sur le calepinage — et les deux
hauteurs retombent sur le standard UNITe. Tout recours à autre chose que la
source principale est écrit au rapport : ce n'est pas la même chose de lire une
inclinaison au tableau bilan du projet et de la mesurer sur un calepinage.

De même, quand le Z des tables ne porte pas d'altitude de terrain, les tables de
la coupe du terrain sont posées sur le profil RGE ALTI en leur appliquant les
hauteurs déclarées. C'est le seul comportement possible, mais il se voit.

#### Les deux hauteurs sont un gabarit, pas une géométrie

C'est l'erreur qui a coûté le plus de détours. Le tableau bilan porte un « Point
bas (m) » et un « Point haut (m) » — onglet « 2. Caractéristiques du projet »,
colonne de l'indice. On les lisait comme les deux extrémités d'une table, ce qui
donnait sur Saint-Cyr un rampant de (4,00 − 2,50)/sin 15° = 5,80 m, soit 2,90 m
par module pour deux modules : une longueur qui n'existe pas, et un pas de
10,50 m contre 9,50 m portés au même tableau.

**Ce sont des bornes d'autorisation.** Le point bas est un minimum garanti au
service instructeur — la structure ne descendra pas plus bas — et le point haut
un maximum, qui prend un peu de marge pour une modification de structure ou la
micro-topographie du terrain. Rien n'oblige une table à toucher les deux, et
l'inclinaison fixe n'entre pas en contradiction avec elles : elle fixe l'écart
entre les deux bords d'une table, pas la position de la table dans le gabarit.

Le rampant se mesure donc sur les **tables du plan** — largeur au sol médiane
divisée par le cosinus de l'inclinaison. Mesuré le 05/09/2026 : 4,784 m sur les
trois dossiers d'essai, soit deux modules de 2,392 m quand un G12R en mesure
2,384 au catalogue. Le pas qui s'en déduit referme le pas déclaré à 2 cm près,
sur Saint-Cyr comme sur Sarnois, et l'avertissement qui tombait sur tous les
dossiers a disparu.

La coupe de principe porte alors ce que le dossier engage :

- le point bas coté « 2,50 m **min** » ;
- le point haut de la table dessinée, à sa géométrie réelle — 3,74 m ;
- le maximum en **trait d'axe au-dessus des tables**, coté « 4,00 m max ». Un
  gabarit se lit comme une limite, pas comme une cote de la table.

Et le contrôle s'inverse : si la table dessinée perce le gabarit, ce n'est plus
une incohérence de tableau mais un dépassement d'autorisation, et le rapport le
dit en ces termes.

### DP 4 — Ouvrages techniques

Chaque planche est partagée en deux : le plan de repérage à gauche, les dessins
d'ouvrages à droite. Un ouvrage absent du projet n'a pas de bloc, et la planche
se recompose sur ce qui reste ; une planche dont aucun ouvrage n'est au contrat
n'est pas produite, et le rang des suivantes suit.

Le plan de repérage porte le **parcellaire IGN** sous les ouvrages. Sans lui le
zoom flottait au milieu de nulle part, sans rien pour situer les ouvrages dans le
foncier ; c'est le fond du plan de repérage du dossier de référence. Une panne du
service n'empêche pas de produire la planche — les ouvrages viennent du contrat —
mais elle s'écrit au rapport.

Un ouvrage présent en plusieurs exemplaires n'est repéré que sur **un** d'entre
eux, le plus grand. Mesuré le 05/09/2026 sur Sarnois : ses deux citernes sont aux
deux bouts du site, et les englober toutes les deux ramenait le zoom au plan de
masse entier, au 1/2 000. Les élévations décrivent un ouvrage type, identique
d'un exemplaire à l'autre ; les situer tous est le travail du plan de masse.

La même règle vaut pour des ouvrages **différents** dispersés d'un bout à l'autre
du site : la planche en situe un seul, à titre d'exemple, et le nomme au rapport.
Le critère porte sur le cadre **tracé**, marge comprise, et non sur la zone nue —
les trois ouvrages de la DP 4-3 de Sarnois indice A tiennent dans 114 x 29 m,
soit un tiers du site, mais la marge portait le cadre à 239 x 154 m et la planche
sortait au 1/2 000 pour des ouvrages de 6 m.

Un **portail** commande le cadrage, une clôture non : le premier est un ouvrage
de 7 m à un endroit précis, la seconde ceint le site. Classé parmi les ouvrages
étendus, le portail laissait la DP 4-2 de Sarnois indice A — qui ne porte ni
citerne ni poste — se cadrer sur les 327 m du site, au 1/5 000.

| Planche | Ouvrages |
|---|---|
| DP 4-1 | `pdl_ptr`, `ptr`, `pdl` — plan de toiture, quatre élévations, coupe |
| DP 4-2 | `cloture`, `portail`, `bache_incendie` |
| DP 4-3 | `bess`, `local_technique`, `citerne_refroidissement` |

La liste est celle arrêtée à la relecture du 04/09/2026 : postes de livraison, de
transformation et combiné, clôture et portail, citernes, local de stockage,
conteneur BESS. Ce sont les seuls ouvrages dont une façade apprenne quelque chose
à l'instruction. L'aire d'aspiration et le bac de rétention en sont sortis — le
premier est un revêtement de sol sans élévation, le second une cuvette au sol ;
tous deux restent tracés sur le plan de masse et sur le plan de repérage, ils
disparaissent des façades et pas du dossier. Le transformateur de la batterie
n'aura son bloc que le jour où le contrat le distinguera de celui du parc : aucune
catégorie ne les sépare aujourd'hui.

Une citerne n'a droit qu'à une planche de façade. Décidé le 05/09/2026 : dès
qu'une citerne incendie est décrite, la citerne de refroidissement n'a pas la
sienne — même cuve, mêmes congés, même vue de face, à la cote près, et les cotes
sont au bloc de caractéristiques. Les deux restent dessinées et repérées au plan
de masse, et l'ouvrage écarté est nommé au rapport.

Chaque ouvrage se dessine ensuite pour ce qu'il est, sur le modèle du dossier de
référence :

- les **postes** reçoivent le traitement complet — plan de toiture, quatre
  élévations, coupe : ce sont les seuls ouvrages bâtis du site ;
- le **BESS** et le **local de stockage** sont des conteneurs maritimes. Tôle
  nervurée, longerons haut et bas, portes à barres de condamnation sur le
  pignon, pose sur plots de 0,3 à 0,5 m. Dessinés en rectangles pleins, un
  conteneur et un bac de rétention sortaient identiques ;
- les **citernes** ont une cuve à congés en plan, portant son trop-plein et ses
  trappes de visite, et une vue de face bombée. Une citerne dessinée au carré se
  lisait comme un bac ;
- la **clôture** est un grillage à moutons à grosse maille, et le **portail** en
  est l'interruption : deux vantaux barreaudés entre leurs poteaux, pris dans le
  grillage courant montré de part et d'autre.

Mesuré sur Sarnois le 04/09/2026 : à sept vues par ouvrage, les cinq équipements
de sa DP 4-3 faisaient 21 vues qui ne tenaient pas sur la planche, même au 1/200.
Seuls les postes en reçoivent donc autant.

**La maille du grillage est en mètres, pas en millimètres de papier.** Elle était
un figuré, et changeait donc de finesse avec l'échelle de la planche : mesuré le
05/09/2026, le même grillage sortait à 8 cm de maille sur une planche au 1/100 et
à 16 cm sur une planche au 1/200. Une maille est une dimension d'ouvrage.

**Une élévation porte le RAL, un plan porte la couleur de repérage.** Postes,
clôture, portail, conteneurs et citernes sont livrés en teinte de catalogue : sur
leur dessin de façade ils sont donc dessinés en RAL 6003, et sur les plans à la
couleur qui les repère. C'est ce que fait le dossier de référence, dont la
citerne est cyan sur le plan de repérage et olive sur sa vue de face. Relevé le
05/09/2026 : la nôtre sortait au cyan de la légende sous une ligne de
caractéristiques annonçant « teinte RAL 6003 » — le dessin contredisait sa
propre légende.

#### Une échelle par ouvrage, le 1/100 par défaut

Écart assumé à D2, décidé le 05/09/2026. D2 posait **une** échelle par planche,
calée sur son plus grand ouvrage : la citerne de 11,7 m tirait alors tout le
reste au 1/200, où un conteneur de 6 m mesurait 30 mm et un panneau de clôture
devenait illisible.

Chaque ouvrage reçoit donc le 1/100 du dossier de référence — ses cartouches
portent tous « 1 : 100 » — et n'en descend que s'il n'y tient pas ; si la colonne
déborde encore en hauteur, c'est l'ouvrage le plus encombrant qui redescend, et
lui seul. Le 1/50 reste dans la liste mais n'est jamais choisi automatiquement :
un panneau de clôture de 7,50 m y ferait 150 mm et écraserait ses voisins.

Chaque sous-cadre porte son échelle en clair, et le cartouche celle du plus grand
nombre de cadres. Là encore c'est la présentation du dossier de référence, dont
le plan de repérage est au 1/500 quand ses élévations sont au 1/100.

Un ouvrage dont le tableau bilan ne porte pas de hauteur se dessine en plan et
rien de plus : plutôt que d'inventer une cote, la vue en plan le décrit avec les
deux dimensions dont on dispose, et sa ligne de caractéristiques annonce qu'il
n'a pas d'élévation.

**Les lignes de rappel du dossier de référence ne sont pas reprises.** Placer
automatiquement des libellés sans chevauchement est un problème de mise en page
non résolu, et un libellé mal posé sur une planche déposée coûte plus cher que le
confort qu'il apporte. Le bloc de légende standard porte la même information.

#### Ce que le contrat ne porte pas

La **hauteur de clôture et de portail** n'est nulle part : le tableau bilan donne
le linéaire, le nombre de portails et leur largeur, jamais une hauteur. Les
élévations sont dessinées à la valeur standard UNITe de 2,00 m, et chaque planche
qui l'emploie le dit au rapport. C'est un manque du contrat, à combler des deux
côtés à la fois — donc une décision, pas un correctif de ce lot.

### La légende montre ce que le plan dessine

Chaque catégorie porte son symbole, et le symbole doit être celui du plan.
Trois l'ont changé à la relecture du 05/09/2026 :

- la **clôture** est un simple trait rouge, parce qu'au plan elle *est* un
  trait rouge continu. Le grillage sur poteaux qu'elle portait promettait un
  figuré que la planche ne dessine nulle part ;
- le **portail** est le symbole de plan du dossier de référence — les deux
  vantaux et leurs arcs de débattement — et c'est exactement ce que le calque
  du bureau d'études porte ;
- la **haie plantée** est une bande, parce qu'au plan c'est une bande continue
  de deux mètres. Le houppier bosselé reste aux arbres et aux haies existantes,
  dont les géométries sont effectivement lobées.

### La légende se construit depuis ce qui a été dessiné

Le contrat porte 35 catégories, la légende de la planche de référence en compte
10. L'écart ne se tranche pas une fois pour toutes : il se résout à chaque projet.

Une catégorie sans objet dessiné n'y figure pas. Deux catégories partageant le
même intitulé n'y font qu'une entrée — le dédoublonnage se fait sur l'intitulé,
pas sur la catégorie : `piste_lourde` et `aire_grutage` sont toutes deux « Voie
lourde », `tables_pv` et `modules_pv` sont le même ouvrage à deux niveaux de
détail. L'ordre est celui du rang de dessin du contrat, pour que la légende se
relise dans l'ordre du plan.

Quatre catégories sont exclues d'office, même présentes : la base vie et le
stockage de chantier, qui sont temporaires et que le dossier de référence ne
montre pas ; la zone d'implantation et le recul, qui sont des contours d'étude —
seule la clôture délimite le projet à l'instruction. Deux entrées viennent
d'ailleurs que du contrat et y figurent comme chez HOCH : « Limite de parcelle »
et « Bâtiment », tirées du WFS IGN. La seconde n'apparaît que s'il tombe un
bâtiment dans le cadre : la requête déborde d'un tampon pour tracer les limites
jusqu'au bord, et en tirer une entrée ferait annoncer un objet que la planche ne
montre pas.

Mesuré sur les deux indices de Sarnois, qui sont deux variantes d'un même
projet : l'indice A porte un poste de livraison/transformation, l'indice B un
poste de transformation, une citerne incendie et une zone de contention. Leurs
légendes comptent 18 et 20 entrées, et diffèrent exactement de ces ouvrages.

### La palette : les relevées font foi, les dérivées se mesurent

`dp_socle/planches/palette.py`, à ne pas confondre avec `apercu_be.STYLES` qui est
la palette de l'image de contrôle à l'écran. Les deux n'ont pas les mêmes
contraintes : à l'écran on zoome, sur une épreuve A3 un poste de 12 x 3 m au
1/1 000 fait 12 x 3 mm.

Les teintes relevées au pixel sur la planche DP 2 du dossier HOCH sont reprises
telles quelles : c'est le document que l'instructeur a l'habitude de voir.

**Une exception, décidée à la relecture du 05/09/2026 : les gris de sol.** Le
document de référence donne le même gris 215 à la plateforme et à la piste
légère, et le même gris 162 à toutes les voies lourdes. Sur nos planches ces
surfaces se touchent constamment — une plateforme de poste est toujours au bord
d'une piste — et la légende annonçait trois entrées que l'œil ne pouvait pas
séparer. Les trois gris s'étagent donc maintenant dans l'ordre de la portance,
en gardant la famille du document : plateforme `#e4e4e4`, piste légère
`#bdbdbd`, voie lourde `#979797`, séparés d'au moins 12 ΔE deux à deux.

Ce qui reste délibérément identique, c'est ce qui est **la même matière** : une
voie lourde existante, une voie lourde à créer et une aire de grutage sont la
même grave compactée sous trois statuts. Elles partagent leur teinte, leur
filet et leur intitulé portent la distinction, et le champ `matiere` de
`StyleDP` les sort du critère d'écart — les séparer ferait croire à trois
revêtements là où il n'y en a qu'un.

Les dérivées, elles, sont refaites sur un critère mesuré :
`tests/test_palette_dp.py` vérifie que deux catégories pouvant se retrouver sur la
même planche restent séparées d'au moins 12 unités ΔE (CIE76). Trois d'entre
elles se confondaient avec une teinte relevée et ont été déplacées : la zone
évitée, l'aire d'aspiration et le local technique, à qui le contrat donnait le
vert du poste de livraison alors que les deux se côtoient sur le même plan.

**Réserve.** La convention UNITe des annexes de demande d'examen au cas par cas —
BESS, bac de rétention, local technique — n'a pas pu être consultée : ces annexes
ne sont pas dans le dépôt. L'orangé du BESS, seul indice disponible, vient du
contrat et est conservé ; les deux autres sont construites sur le seul critère
mesurable ici. À reprendre sur pièce.

### Le poste est reconnu, pas reconstruit

Un calque de poste ne porte pas que le poste. Mesuré le 05/09/2026 sur les trois
dossiers d'essai :

| Dossier | Calque | Ce qu'il porte |
|---|---|---|
| Saint-Cyr | `pdl_ptr` | **12,00 x 3,00 m**, plus deux bandes de 12 x 1,50 et 12 x 1,00 |
| Sarnois A | `pdl_ptr` | un seul 10,00 x 3,00 m |
| Sarnois B | `ptr` | **10,00 x 3,00 m**, plus deux patatoïdes de 41 et 83 m² et deux plots |

Ce qui entoure le poste est la **terre remise autour de lui** : un poste
préfabriqué a son seuil de porte cinquante à soixante-dix centimètres au-dessus
de sa semelle, et le talus comble la différence. Dessiné de la couleur du poste,
il lui donnait une emprise deux fois trop large — 12 x 5,50 m à Saint-Cyr pour
un poste de 12 x 3, quand l'élévation de DP 4 le dessine à ses cotes de
catalogue.

Le poste est donc **reconnu à ses cotes** plutôt que reconstruit : il est déjà
là, au centimètre, sur deux des trois dossiers. Ce qui l'entoure rejoint la
plateforme, où il se lit comme le sol remanié qu'il est, et le rapport le dit.
Il garde le gris de plateforme, sans teinte ni entrée de légende propres
(décidé le 05/09/2026) : c'est du sol, et une onzième entrée de légende pour un
talus de quelques dizaines de centimètres coûterait plus qu'elle n'apprend.

Faute d'objet aux cotes du catalogue — Sarnois indice A porte un 10 x 3 là où le
tableau déclare un PDL/PTR de 12 x 3 — rien n'est reconstruit : le plan se
dessine tel quel. Le recoupement avec la surface déclarée porte, lui, sur le
calque entier dans tous les cas : c'est bien poste **et** abords que le tableau
compte, et Saint-Cyr y déclare 66 m² pour 36 m² de poste.

### Un contour ouvert n'est pas un trait

Mesuré le 05/09/2026 sur Sarnois : la citerne de refroidissement arrive au
contrat en **onze objets** — un petit polygone et dix polylignes ouvertes, les
quatre côtés et les quatre congés d'un rectangle à angles arrondis que la CAO a
exportés séparément. Une polyligne ne se remplit pas : l'ouvrage sortait en
contour bleu sur une planche dont la légende annonçait un aplat.

`palette.fermer_les_contours` recoud ces polylignes et les ferme en surfaces,
avec deux garde-fous mesurés le même jour :

- seules les catégories **dessinées en aplat** y passent. Le portail est un
  linéaire, et ses deux arcs de débattement se referment parfaitement en deux
  surfaces de 9,6 m² qui n'existent pas ;
- les côtés ne se touchent pas au point près : sans recollement à 1 cm la
  citerne ne se referme pas du tout, à 20 cm elle se referme en six morceaux.
  Les 108,7 m² obtenus à 1 cm valent les 108,8 m² du tableau bilan.

Ce qui reste ouvert est dessiné tel quel, et la recomposition est écrite au
rapport : ce n'est pas la géométrie du calque.

### Une emprise de projet épouse le parcellaire

L'emprise est une **donnée d'entrée** : c'est le shapefile que le chef de projet
fournit, et les planches la dessinent telle quelle. Rien ne vérifiait qu'elle
correspondait au foncier. Mesuré le 05/09/2026 : le premier jeu d'essai de
Sarnois portait une emprise de 8,51 ha qui mordait sur dix parcelles voisines
alors que le projet tient sur la seule ZA 0057, et la planche l'a dessinée sans
broncher — le tableau annonçait 27,96 ha de contenance pour 8,51 ha d'emprise.

Une emprise de projet est un découpage foncier : elle suit les limites
cadastrales, elle ne les traverse pas. DP 1-3 signale donc au rapport toute
parcelle recoupée entre 2 % et 98 % de sa surface. En deçà c'est une écharde de
calage, au-delà la parcelle est prise entière ; entre les deux, c'est le fichier
d'emprise qu'il faut reprendre.

### `voirie` bloque, elle ne se devine pas

La catégorie `voirie` existe parce qu'un calque du bureau d'études ne disait pas
si la piste était lourde ou légère, alors que le tableau bilan sépare les deux et
que la légende du dossier les distingue. Une couche `voirie` peuplée **refuse** de
dessiner tant que le chef de projet n'a pas tranché, sans valeur par défaut. La
décision se conserve dans le `projet.json` du lot 1, le format pivot, pour qu'une
régénération ne la redemande pas.

Le tri se fait **objet par objet**, et non d'un seul choix pour toute la couche :
un projet a presque toujours de la voie lourde *et* de la piste légère, et le
calque les mélange sans les nommer. `projet.json` porte donc une liste, un type
par objet dans l'ordre de la couche ; une chaîne, forme des dossiers antérieurs,
vaut pour toute la couche. Le nombre de choix doit valoir le nombre d'objets — un
plan réimporté qui en porterait un de plus décalerait tout le reste, et le
contrat refuse plutôt que de décaler. L'interface donne à chaque objet sa surface,
sa longueur et sa largeur moyenne : une voie lourde fait cinq à six mètres de
large, une piste légère trois à quatre.

## Notice DP 11 (lot 5)

L'outil **n'écrit pas** la notice : le chef de projet la rédige et la dépose en
PDF, l'outil l'habille. Chaque page du fichier déposé devient une planche A3
paysage portant le cadre et le cartouche du dossier, et la pièce se feuillette
comme les autres. La mise en forme automatique de la notice reste à faire un
jour ; elle n'est pas dans ce lot.

**Posée, pas rastérisée.** La page fournie est fusionnée telle quelle
(`pypdf.PageObject.merge_transformed_page`) : son texte reste du texte dans le
dossier assemblé, sélectionnable et indexable par le service instructeur.
`tests/test_notice_lot5.py` le mesure par extraction sur le PDF produit — le
corps lu dans la planche vaut celui de la notice multiplié par le facteur
d'ajustement, ce qu'une image n'aurait pas donné.

### Une page fournie, une page de dossier

Chaque page est ajustée au plus grand facteur qui la fasse tenir, centrée. Deux
A4 côte à côte tiendraient (2 × 184 mm pour 402 disponibles), mais la pagination
de la notice cesserait de correspondre à celle du dossier, et le sommaire pointe
une page. Le blanc latéral est le prix d'un dossier homogène en A3 paysage.

Le format ne se suppose pas, il **se lit** : `mediabox` de chaque page, rotation
déclarée comprise. Le rapport de génération annonce le format détecté, le
nombre de pages et le facteur appliqué, même quand tout va bien — une notice
réduite de moitié parce qu'elle arrivait en A2 doit se voir avant l'instruction,
et un rapport qui ne parle que des ennuis ne le dirait pas.

### Ce que la mesure a corrigé au brief

La zone de dessin d'une planche à cartouche vaut 410 × 268 mm à (5, 5), mais la
notice n'y est pas posée à fleur : elle garde le **blanc tournant de 4 mm** des
planches du lot 4, soit 402 × 260 mm utiles. Posée à fleur, une page qui peint
son propre fond blanc — ce que font les exports d'Illustrator et les pages
scannées — recouvrait la moitié du filet du cadre sur sa largeur, le filet étant
centré sur la limite de la zone.

Les facteurs mesurés le 14/09/2026, qui fixent aussi les seuils :

| Format déposé | Facteur | Sort |
|---|---|---|
| **A4 paysage** (le cas courant) | **1,238** | **intégrée, agrandie, 26 mm de blanc de chaque côté** |
| A4 portrait | 0,875 | intégrée, 113 mm de blanc de chaque côté |
| A3 paysage | 0,875 | intégrée — et non au facteur 1 : 420 × 297 ne tient pas dans 402 × 260 |
| A3 portrait | 0,619 | intégrée |
| A2 portrait | 0,438 | intégrée, **signalée au rapport** |
| A1 portrait | 0,309 | **refusée** |
| A0 portrait | 0,219 | **refusée** |

Le seuil de refus est à 0,40 : il laisse passer tout ce qui est une notice,
jusqu'au A2 réduit de plus de moitié mais encore lisible, et arrête ce qui n'en
est pas — un plan A1 ou A0 déposé par mégarde dans la case de la notice, dont le
corps de texte tomberait sous 3,5 pt. Le seuil d'alerte est à 0,60, le facteur
sous lequel un corps de 10 pt descend sous 6 pt. Sont également refusés, par
`ErreurNotice` : un fichier qui n'est pas un PDF lisible, un PDF chiffré, un PDF
sans page.

### Un cartouche sans nord ni échelle

Sur une notice, la flèche nord et la case ÉCHELLE ne veulent rien dire, et le
dossier de référence n'en porte aucune : les pages 16 et 17 de Massay portent
`Massay`, `PHASE: DPC`, `NUMERO`, `DATE:` et `DPC 4 Notice`, là où la page 2 du
même dossier porte `ECHELLE 1 : 10 000`.

D'où un paramètre **additif** sur `Planche`, `reperes_cartographiques`, autorisé
par exception à la règle qui interdit aux lots suivants de toucher au moteur du
lot 1. Il nomme ce qu'il retire — des repères cartographiques — et non le lot
qui le demande : la page de garde pourrait en avoir l'usage. À faux, ni la
flèche, ni la case, ni les filets qui la délimitent, la case du titre s'étendant
à leur place : deux compartiments vides se liraient comme une échelle qu'on a
oublié de renseigner. Vrai par défaut, et aucune planche existante ne change
d'aspect.

### Chaque page porte son propre numéro

Le cartouche annonce le numéro de **page**, pas celui de la pièce : Massay porte
sa notice sur deux pages, dont les cartouches annoncent NUMERO 16 puis
NUMERO 17. Le contrôle de rang de `assemblage.py` a donc appris qu'une pièce
peut couvrir plusieurs pages : une pièce qui s'étend déclare les numéros de ses
cartouches (`Sortie.numeros`) et ils sont comparés un à un à la pagination
réelle du dossier assemblé. Une pièce d'une seule page garde le contrôle du
lot 4 ; une pièce qui produirait deux pages sans déclarer ses numéros est
refusée.

Le rang de la première page de la notice se **compte** sur les PDF déjà
produits, et ne se déduit pas du nombre de pièces : le jour où une autre pièce
s'étendra, la notice suivra sans qu'on ait à y penser. La notice étant la
dernière pièce, aucune n'est décalée par son épaisseur.

### Où elle se dépose, et ce qui se passe sans elle

En section 3, qu'elle ouvre : `projets/{nom}/DP_11/`, par le même patron que
`_enregistrer_photos`.

Elle est **attendue de tout dossier déposable, et pas exigée par l'outil**. Un
dossier déposé sans notice est incomplet — c'est ce que dit la décision du
14/09/2026 qui a corrigé D4 — mais rien ne bloque : tant que le dépôt est en
mise au point, un contrôle bloquant sur une pièce manquante empêcherait
d'éprouver le reste de la chaîne. Le dossier sort donc sans elle, et son absence
est écrite au **rapport de génération**, qui devient le seul garde-fou : c'est
là, et nulle part ailleurs, que le chef de projet peut s'apercevoir que la pièce
manque avant de déposer.

Le message distingue deux cas, parce qu'un rapport qui répète ce qu'on sait déjà
cesse d'être lu. Un dossier complet s'entend dire qu'il est « incomplet pour le
dépôt ». Un **dossier d'étude amont**, réduit aux pièces DP 1 et produit sans
plan du bureau d'études, ne s'entend rien reprocher : il est déjà annoncé comme
non déposable, et sa notice n'est pas encore écrite. C'est la présence du
contrat d'entrée qui fait la différence, et `assemblage` est le seul à la
connaître.

### Ce qui deviendra bloquant

Les pièces attendues d'un dossier déposable seront passées en obligatoire
**quand la chaîne sera éprouvée** — décision du 14/09/2026, à reprendre à la fin
de la mise au point. La notice DP 11 est la première de cette liste : le
contrôle existait, il a été retiré, et le rétablir tient en deux endroits — un
refus dans `generer_dossier` après le chargement du contrat, et un dans
`_construire_projet` côté application. Aujourd'hui, les seuls refus sont ceux
sans lesquels rien ne peut être dessiné : l'emprise cadastrale absente, une
voirie dont le type n'est pas tranché, deux photographies de même nom qui
s'écraseraient.

### Le format déposé, en pratique

La notice est fournie en **A4 paysage**. Elle est donc *agrandie* au facteur
1,238 pour remplir le cadre : 367,7 × 260 mm, 26 mm de blanc de chaque côté, et
un corps de 10 pt qui s'imprime à 12,4 pt. C'est la règle D1 appliquée telle
quelle — « au plus grand facteur qui la fasse tenir » — et le chef de projet l'a
confirmée le 14/09/2026, contre la variante qui aurait plafonné le facteur à 1
et laissé 61,5 mm de blanc de chaque côté.

À noter, pour qui reprendrait la question : la règle D1 a été écrite en
supposant de l'A4 portrait, où le facteur est toujours inférieur à 1. Le cas de
l'agrandissement n'y avait pas été envisagé. Et la mesure de l'étendue de
l'encre des pages 16 et 17 de Massay **n'a pas permis de vérifier** que le
dossier de référence remplit la feuille : les trois pages testées, plan de
situation compris, rendent la même étendue bord à bord.

## Les pièces photographiques (lot 6)

DP 6, DP 7 et DP 8 portent chacune des photographies à droite et un **plan de
repérage** à gauche, qui dit d'où chaque vue a été prise et — quand la direction
est vérifiée — ce qu'elle regarde. L'outil ne fabrique pas les images : il les
assemble, les repère et les pagine.

| Pièce | Ce qu'elle porte | Planches |
|---|---|---|
| DP 6 | un point de vue, 2 ou 3 volets | une par vue, « Vue A », « Vue B » |
| DP 7 | 1 ou 2 photographies proches | une seule, « PC7-1 », « PC7-2 » |
| DP 8 | 1 ou 2 photographies lointaines | une seule, « PC8-1 », « PC8-2 » |

Relevé le 15/09/2026 sur le dossier de référence : DP 6 nomme ses vues par
lettres, DP 7 et DP 8 numérotent leurs points. La numérotation repart de 1 à
chaque pièce.

### Le cap ne se croit pas, la position se lit

La position GPS d'une photographie n'a jamais été prise en défaut. Le cap, si :
la boussole d'un téléphone donne ±10 à 20°, et mal calibrée elle décale toutes
les directions du même angle. Une validation du dépôt `photomontage` a relevé
15° d'erreur sur un cap annoncé, par recoupement sur deux éoliennes
identifiées.

Un cap EXIF **propose** donc une orientation ; il ne fait autorité qu'une fois
vérifié sur fond satellite. Sans direction confirmée, la planche porte le repère
numéroté **sans cône** — ce n'est pas un manque, c'est le cas normal d'une vue
de drone.

Un rapport `photos-geoloc` déposé fait gagner ce travail, mais **seulement pour
ce qui y a été corrigé**. Mesuré le 15/09/2026 sur « Rapport Photo SARNOIS » :
25 points, calibration nulle, aucune direction figée — le chef de projet avait
produit son rapport sans toucher aux caps. Une direction figée à la main ou
reprise par une calibration globale part confirmée ; une direction jamais
regardée reste une proposition.

### Le cône est un symbole, pas un champ de vue

Secteur de 50° et taille fixe, repris du marqueur de `photos-geoloc` pour que le
chef de projet voie le même symbole des deux côtés. Il dit d'où l'on regarde et
vers où, pas jusqu'où ni sur quelle largeur.

Le dossier de référence, lui, n'en porte aucun : mesuré dans le flux vectoriel
de sa DP 7, il n'y a autour de « PC7-1 » que trois points de tracé formant un
segment de 8 pt. Le cône est donc un ajout volontaire, qui dit ce qu'une
étiquette seule ne dit pas.

### Des emplacements identiques, et la photo qui s'y ajuste

Chaque pièce fixe son nombre d'emplacements — trois pour DP 6, deux pour DP 7 et
DP 8 — tous de mêmes dimensions, et la photographie est **rognée** pour remplir
le sien, jamais déformée ni bordée de blanc. Un emplacement vide ne redistribue
rien : une DP 6 sans mesures paysagères garde la géométrie d'une DP 6 complète,
et deux dossiers voisins se comparent.

Le format n'est pas absolu, et c'est une mesure qui l'a décidé : trois
emplacements sur une A3 paysage imposeraient du 3,11:1, où une photographie
d'iPhone perdrait 57 % de sa hauteur — le ciel et le premier plan, c'est-à-dire
ce que la pièce doit montrer. Le format retenu est le **rapport médian des
images de la planche** : les emplacements restent identiques entre eux, et des
photographies qui partagent déjà un rapport ne sont pas rognées du tout. Au-delà
de 12 %, le rapport de génération nomme la photographie et ce qui lui a été
retiré.

### Reprendre un rapport de visite

Le chemin court, et le meilleur : le chef de projet dépose la carte HTML de son
rapport `photos-geoloc`, et une galerie de vignettes s'ouvre. Chacune porte le
numéro qu'elle a sur les marqueurs du rapport — le seul repère commun entre les
deux écrans — et une affectation déjà proposée : DP 7 en deçà de 500 m du site,
DP 8 au-delà, cohérent avec le dossier de référence dont la DP 7 est au 1/2 500
et la DP 8 au 1/6 500. Le chef de projet ne corrige que ce qui n'est pas évident.

Les photographies retenues sont écrites dans le dossier du projet avec leur
point de vue. Après quoi le rapport n'existe plus pour le dossier : rien ne
distingue une photographie qui en vient d'une photographie déposée à la main.

**Le rapport est une importation, pas un stockage.** Une carte de quarante photos
pèse une vingtaine de mégaoctets de base64, et Streamlit relit un fichier déposé
à chaque exécution du script. La carte n'est donc lue qu'une fois, dans un cache
**borné à deux entrées** — il est global à toutes les sessions, et un cache non
borné de cartes entières est ce qui a fait couper le dépôt voisin par son
hébergeur. Les vignettes se décodent une par une, sans parser le bloc : mesuré le
16/09/2026 sur un rapport réel de 17,8 Mo, une vignette coûte 4,4 Mo de pic.

### L'EXIF, lu au dépôt

Une photographie déposée seule est lue une fois : si elle porte sa position, elle
se place seule sur la carte. Son cap, lui, n'est qu'une **proposition** annoncée
comme telle, et ne fera dessiner aucun cône tant qu'il n'aura pas été visé.

La lecture accepte le fichier déposé sans écrire de fichier temporaire : recopier
plusieurs mégaoctets à chaque interaction aurait coûté cher pour rien.

### L'échelle du repérage

| Contenu à faire tenir | Liste |
|---|---|
| toutes les prises de vue + le centre du site | 1/1 000 à 1/10 000 |

L'emprise complète est visée d'abord ; quand elle ne tient pas, c'est elle qui
cède et non l'échelle — le lecteur qui veut voir le site entier a DP 2. Ce qui
reste impératif est que toutes les prises de vue tiennent, sans quoi la planche
ne repère rien.

La liste s'arrête au 1/10 000, qui couvre 1,68 km dans la colonne de gauche.
Elle avait été prolongée au 1/20 000 sur la foi du brief, qui annonçait des
points de vue « à plusieurs kilomètres » pour DP 8 ; l'usage réel le dément
(16/09/2026) — quelques centaines de mètres, un gros kilomètre au plus.

`tests/test_echelle_reperage_pdf.py` mesure l'échelle dans le flux de contenu du
PDF produit, sur la largeur de l'emprise et sur la distance entre deux repères,
à 0,5 % près.

## Hors périmètre de ces lots

La **composition** de la notice DP 11 — l'écriture du texte par l'outil, la
reprise des valeurs du tableau bilan, le recoupement avec les planches. Le lot 5
n'intègre que le PDF fourni. Les insertions paysagères DP 6, DP 7 et DP 8 sont
fournies en PDF et simplement assemblées. L'import HelioScope et le calage
géographique (lot 2) restent en réserve pour les projets sans plan BE ; la saisie
manuelle des éléments techniques (lot 3) est remplacée par le lot 2bis.
