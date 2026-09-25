# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 8 : une sortie PowerPoint à finaliser

> Lots 1, 2, 2bis, 2ter, 4, 5 et 6 livrés, lot 7 en brief. Le dossier sort
> aujourd'hui en un PDF assemblé, complet ou rien. Ce lot ajoute une **seconde
> sortie**, un `.pptx` que le chef de projet finit lui-même : les planches y
> sont déjà dessinées, les photographies restent à poser.
>
> Lire `README.md` et `CLAUDE.md` avant de commencer : ce brief ne les répète pas.

---

## Objectif

Demande du 25/09/2026. Le volet photographique est ce qui bloque un dossier :
il faut avoir choisi les prises de vue, les avoir géolocalisées, avoir posé
leurs cônes de visée — avant que l'outil produise quoi que ce soit. Or les
photomontages arrivent en retard, et les photographies de terrain se trient
mieux sur un écran qu'au clic dans un formulaire.

Le chef de projet veut donc **télécharger le dossier sans avoir traité les
photos** : page de garde, planches cartographiques, coupes, ouvrages et notice
déjà en place, et pour les pièces photographiques des cadres vides, un plan de
repérage déjà imprimé, et les repères de vue en formes libres à poser à la
main. Il finit dans PowerPoint, sur son poste, et exporte en PDF.

**C'est moins robuste, et c'est assumé.** Ce que l'outil garantit aujourd'hui —
un cône à la bonne position, au bon azimut, vérifié contre l'EXIF — devient la
responsabilité du chef de projet. « La localisation des cônes de vue ne sera pas
parfaite mais largement suffisante » (25/09/2026). Le lot ne doit pas faire
semblant du contraire : ce qui n'est plus vérifié doit être écrit, sur la diapo
et dans le rapport.

---

## Ce qui existe déjà, et qu'il faut aller lire

| Brique | Où | Ce qu'elle donne |
|---|---|---|
| Le moteur de planche | `dp_socle/planche.py:161` `Planche` | SVG composé à la main, 1 unité = 1 mm, A3 paysage 420 × 297. `svg()` l. 543, `rendre_pdf()` l. 568, `rendre_apercu_png(dpi)` l. 591 |
| Composition des planches photo | `dp_socle/planches/photographies.py:102` `composer` | colonne d'images de 229 mm à droite, repérage sur les 169 mm restants, blanc tournant de 4 mm |
| Géométrie des cadres | `photographies.py:333` `_poser_images`, `:442` `rapport_de_l_emplacement` | 2 emplacements → 128 mm de cadre, image 115,4 × 222 mm, **ratio 1,92:1** ; 3 emplacements → 84 mm, image 71,4 × 222 mm, **ratio 3,11:1** |
| Rognage | `photographies.py:415` `fenetre_de_cadrage` | remplit le cadre en rognant un seul axe, jamais de bande blanche ni de déformation |
| Cadrage du repérage | `dp_socle/planches/reperage_vues.py:147` `zone_de_reperage`, `:205` `plan_de_reperage` | choisit la plus grande échelle de `ECHELLES_REPERAGE_VUES` (l. 68) où tiennent emprise **et** points de vue |
| Repère et cône | `reperage_vues.py:340` `_tracer_repere`, `:314` `_tracer_cone` | disque de 2,4 mm, secteur de 50° et 8 mm — **en millimètres papier**, donc indépendants de l'échelle (`_rayon_terrain` l. 303) |
| Étiquette d'une vue | `reperage_vues.py:118` `repere_de_vue` | « Vue A » pour DP 6, « PC7-1 » / « PC8-2 » pour DP 7 et DP 8 |
| Les trois volets de DP 6 | `dp_socle/planches/dp6_insertions.py:41` `INTITULES` | image brute, photomontage, photomontage avec mesures paysagères |
| Assemblage et pagination | `dp_socle/assemblage.py:85` `generer_dossier`, `:218` `_verifier_numerotation` | le cartouche doit annoncer la page où la planche tombe, sinon `ErreurRendu` |
| Le sommaire | `dp_socle/planches/page_garde.py:230` `_bloc_sommaire`, `dp_socle/dossier.py:40` `PIECES` | une ligne par pièce, pages réelles, plage « 9-10 » pour une pièce multipage |
| Notice fournie | `dp_socle/planches/dp11_notice.py:250` `generer` | fusionne le PDF déposé **en vecteur** dans le cadre A3 |

Aucune dépendance ne sait écrire du `.pptx` (`requirements.txt` : `openpyxl` est
en lecture seule, pour le tableau bilan). Il faudra ajouter **`python-pptx`**,
épinglé et justifié en commentaire.

---

## Décisions prises en amont

### D0 — Une planche part en image pleine page, jamais en formes

Retraduire le SVG des planches en formes DrawingML, ce serait un second moteur
de rendu : ses propres métriques de texte, sa propre justification, et les
aplats non rectangulaires qui sont aujourd'hui des milliers de traits de
balayage (`planches/primitives.py:215` `forme_pleine`). Une planche qui
s'afficherait autrement dans PowerPoint que dans le PDF est exactement la
planche fausse que personne ne détecte.

Le PPTX porte donc **la planche telle que le moteur la dessine**, en une seule
image posée pleine page — vectorielle si possible (voir D8), matricielle
sinon. Les deux sorties restent identiques par construction.

### D1 — Ce qui est éditable, et rien d'autre

Éditables, parce que le chef de projet en a besoin : **les légendes**, **la
table des matières** de la page de garde, **les intitulés des cadres photo**.
Déplaçables : les cadres photo, les repères et cônes de vue.

Tout le reste est dans l'image, et l'image est posée sur la **mise en page**
(slide layout), pas sur la diapo : elle n'y est ni sélectionnable ni
déplaçable. C'est ce qui protège l'échelle.

### D2 — L'échelle reste vraie, donc le cadrage se choisit avant l'export

Redimensionner le plan de repérage dans PowerPoint rendrait faux le
dénominateur écrit au cartouche. Interdit. Le cadrage se décide à la
génération :

- **DP 6 et DP 7** : cadrage fixe, **emprise + 150 m tout autour**, à la plus
  grande échelle de `ECHELLES_REPERAGE_VUES` qui le contient. Les prises de vue
  de ces deux pièces sont proches du site (25/09/2026). Aucun choix, aucun
  redimensionnement.
- **DP 8** : **trois diapos**, même contenu, trois échelles successives — celle
  de DP 7, puis les deux crans suivants de la liste. Le chef de projet garde
  celle où son point de vue tombe.
- Si l'emprise + 150 m ne tient pas au 1/10 000, on lève : une planche où le
  site n'occupe plus seize millimètres ne se sort pas en silence (c'est déjà la
  raison pour laquelle la liste s'arrête là, `reperage_vues.py:60-68`).

Il faut donc une fonction de cadrage qui ne connaît pas les points de vue — les
prises de vue n'existent pas encore au moment de l'export. C'est la conséquence
la plus profonde du lot : `zone_de_reperage` ne peut pas servir tel quel.

### D3 — Les diapos alternatives partagent le numéro de page de leur groupe

| Pièce | Diapos produites | Cadres photo |
|---|---|---|
| DP 6 | 2 alternatives | 2 cadres (brute + photomontage) **ou** 3 cadres (+ photomontage avec mesures paysagères) |
| DP 7 | 1 | 2 |
| DP 8 | 3 alternatives (trois échelles) | 2 |

Les alternatives portent **le même numéro de page** au cartouche, et le
sommaire n'en compte qu'une : supprimer les surnuméraires laisse une pagination
juste. Chaque diapo alternative porte un **bandeau rouge**, posé sur la diapo
et donc supprimable : « Trois cadrages au choix — n'en gardez qu'un, supprimez
les autres et ce bandeau avant d'exporter en PDF. »

Ce qui disparaît avec ce lot : `_verifier_numerotation` et `verifier_format`
(`assemblage.py:218` et `:439`) ne peuvent pas s'appliquer à un fichier que le
chef de projet édite. Le rapport doit le dire.

### D4 — Le ratio du cadre reste imposé par l'emplacement

Comme aujourd'hui : 1,92:1 à deux cadres, 3,11:1 à trois. Le chef de projet ne
doit pas avoir à recadrer à la main ; il faut le comportement « remplir en
rognant » de `fenetre_de_cadrage`. Le mécanisme reste à mesurer (voir plus bas).

**Divergence à signaler.** Aujourd'hui, une DP 6 à deux volets garde **trois**
emplacements, le troisième vide, pour que la géométrie ne change pas d'un
dossier à l'autre (`dp6_insertions.py:100-107`). La diapo à deux cadres rompt
cette règle : ses deux images font 115,4 mm de haut au lieu de 71,4. À trancher
plus tard — aligner la voie PDF, ou assumer deux géométries — mais pas dans ce
lot.

### D5 — Le repère et le cône sont des formes natives

Un ovale de 2,4 mm de rayon et un secteur de 50° et 8 mm de rayon, groupés,
étiquetés du repère de la vue. Ces tailles sont en millimètres **papier** : le
groupe a le même encombrement quelle que soit l'échelle du repérage, ce qui
évite de le redimensionner et donc de mentir.

Posés au **centre du panneau de repérage**, pas en marge : un cône oublié doit
se voir. Le même repère figure sur le cône **et** sur l'intitulé du cadre photo
correspondant — c'est tout ce qui force encore l'appariement.

### D6 — La notice DP 11 est rastérisée

Un PPTX ne sait pas embarquer une page PDF. La notice y devient une image, page
par page : son texte cesse d'être du texte, il ne sera plus ni sélectionnable ni
cherchable dans le PDF final. Accepté le 25/09/2026. En **PNG** et non en JPEG :
du texte noir sur blanc y pèse quelques dizaines de kilo-octets et le JPEG le
baverait.

### D7 — La police reste Aptos

Vérifié à l'écran le 25/09/2026 : Aptos est rendue correctement sur le poste du
chef de projet — c'est la police par défaut de Microsoft 365 depuis 2024. Rien
à changer, et pas de Calibri de repli : du Calibri éditable à côté d'un Aptos
rastérisé sur la même planche se verrait.

### D8 — La planche part en SVG, texte en tracés

**C'est la voie retenue**, éprouvée à l'écran le 25/09/2026 et confirmée le
même jour : « cartouche identique sur les deux planches ». Le chef de projet
ajoute ses photos hors Streamlit, le fichier n'a donc pas de limite de
téléversement à respecter ; et le vectoriel lève le plafond de résolution
décrit plus bas, tout en pesant moins que le matriciel.

Le montage : un `asvg:svgBlip` posé à côté du PNG de repli dans le `a:blip`,
que PowerPoint 2016 et suivants affichent en vectoriel. Le SVG est celui que
`Planche.svg()` produit, **repassé par cairo** (`cairosvg.svg2svg`) pour que
son texte devienne des tracés de glyphes : zéro `<text>` en sortie, donc plus
rien que PowerPoint puisse composer de travers, et une mise en page qui reste
celle du PDF puisque c'est le même moteur qui la calcule. Le PNG de repli, lui,
se rend à 3 308 × 2 339 px, taille de pixel imposée — pas par
`rendre_apercu_png`, dont la docstring dit « sans valeur métrologique : ne pas
imprimer ».

Poids sur le plan de masse de Sarnois : 0,20 Mo en SVG à texte vivant,
**0,36 Mo en tracés**, contre 0,53 Mo pour le PNG à 200 dpi. Fidélité de la
conversion, mesurée en rendant les deux SVG à 3 308 px et en les comparant
pixel à pixel : **0,17 % des pixels s'écartent de plus de 8/255**, écart moyen
0,09/255 — le crénelage des contours, rien d'autre.

Ce que la voie vectorielle coûte : le texte de la planche cesse d'être du
texte, comme il l'était déjà en matriciel. Ce qu'elle rapporte : la netteté à
tout grossissement, et un fichier plus léger.

**Mais pas pour toutes les planches.** Une planche à fond IGN porte un raster
incorporé, que `svg2svg` ré-encode en PNG sans perte. Mesuré sur une planche au
1/5 000 chargée d'une ortho de 2 481 × 1 754 px : le SVG passe de **1,03 Mo à
6,89 Mo**, sept fois, quand la même planche en JPEG q88 à 200 dpi ne pèse que
**1,16 Mo**. Le vectoriel ne paie que là où le contenu est vectoriel.

La règle est donc :

| Planche | Voie | Pourquoi |
|---|---|---|
| DP 2, DP 3, DP 4, page de garde | **SVG en tracés** | tout y est vectoriel, et le trait y gagne |
| DP 1-1, DP 1-2, DP 6, DP 7, DP 8 | **JPEG q88 à 200 dpi** | le fond IGN domine la planche ; le vectoriser ne fait que réencoder une photographie |
| DP 11 | PNG à 200 dpi | du texte noir sur blanc (voir D6) |

Une planche matricielle n'a pas le défaut de chasse du texte : il n'y a pas de
texte à composer. Le remède de `svg2svg` ne sert qu'à la voie vectorielle.

#### Le plafond matriciel, pour mémoire

**Mesuré le 25/09/2026** sur un PDF réellement exporté depuis PowerPoint
(« Enregistrer au format PDF », qualité standard) à partir d'une sonde portant
la même planche à 200, 300 et 400 dpi : **les trois pages en ressortent à
3 308 × 2 339 px, soit exactement 200 dpi**, pour 0,66 à 0,68 Mo chacune. Ce
que l'on met au-delà de 200 dpi est jeté à l'export, et ne coûte que du poids.
C'est pourquoi le matriciel, là où il subsiste, se rend à 200 dpi et pas plus,
et c'est la raison d'être de la voie vectorielle.

Deux réglages du poste à connaître, relevés à l'écran : « Ne pas compresser
les images dans un fichier » est coché par défaut — c'est lui qui protège le
fichier `.pptx` à l'enregistrement —, mais la « Résolution par défaut » d'à
côté est à **96 ppp**. Décoché, ce réglage détruirait les plans : la consigne
aux chefs de projet doit dire de le laisser coché.

### D9 — Le fichier se nomme pour ce qu'il est

`{nom}_DP_a_finaliser.pptx`. Pas de diapo d'introduction, qui décalerait la
pagination : les consignes tiennent dans les bandeaux rouges des diapos
alternatives et dans le texte du bouton de téléchargement.

---

## Ce que la sonde du 25/09/2026 a déjà mesuré

Une sonde a été construite sur le dossier `sortie/PV-Sarnois-IND10B` — deux
diapos, les fonds de DP 7 et DP 2 rastérisés — et relue avec `python-pptx`.
Quatre choses sont acquises ; elles n'ont plus à être cherchées.

- **`python-pptx` sait poser une image sur une mise en page**, contrairement à
  ce que son API laisse croire : `partie.get_or_add_image_part(fichier)` rend un
  `rId` valable pour la mise en page, et `shapes._spTree.add_pic(...)` l'y
  déclare. **Aucun modèle `.pptx` n'est nécessaire pour le fond.** Passer par
  une diapo jetable, en revanche, ne marche pas : l'élément copié garde le
  `r:embed` de la diapo, et l'image se perd avec elle.
- **`fill.transparency` est un attribut qui n'existe pas.** Python l'accepte
  sans lever, et le cône sortait magenta opaque par-dessus le plan. L'alpha
  s'écrit à la main : `<a:alpha val="55000"/>` dans le `a:solidFill`. C'est le
  genre de repli silencieux que la charte interdit — à surveiller partout où
  l'on règle une propriété que `python-pptx` ne couvre pas.
- **Un groupe tourne autour du centre de son cadre.** Un groupe « rond + cône »
  a son cadre décalé du côté du cône : viser ferait glisser le repère hors du
  point de vue. Un carré transparent de `2 × RAYON_CONE_MM` centré sur le
  repère remet le pivot au bon endroit. Mesuré : le groupe fait alors
  16 × 16 mm, centré sur le point.
- **Les cotes et le poids.** Les cadres photo d'une planche à deux emplacements
  tombent à (185,5 ; 18,1) et (185,5 ; 150,1), 222 × 115,4 mm, rapport
  1,924:1 — identiques à ce que `rapport_de_l_emplacement` annonce. Une planche
  A3 rastérisée à 200 dpi fait 3 308 × 2 339 px, soit 0,5 Mo pour une DP 7 et
  0,9 Mo pour une DP 2 en JPEG q88 : une quinzaine de diapos tiennent dans 10 à
  15 Mo avant les photographies.

### Ce que la sonde a montré à l'écran, le 25/09/2026

- **Le fond posé sur la mise en page est bien hors d'atteinte** : le chef de
  projet ne peut ni le sélectionner ni le déplacer. Le montage tient.
- **Une image simplement posée ne garde pas son cadre.** « Clic droit >
  Remplacer l'image : la forme de la boîte change pour s'adapter à la forme de
  l'image. » Une photographie en portrait a étiré le cadre. Il faut donc des
  **réservations d'image**, que PowerPoint remplit en rognant — et
  `python-pptx` sait les écrire dans la mise en page, toujours sans modèle
  fabriqué à la main : la diapo en hérite comme de vraies réservations, avec
  `insert_picture`.
- **Un bandeau posé sur la diapo se supprime sans toucher au fond.** Le montage
  des diapos alternatives tient.
- **Rien de ce qui est dans l'image n'est éditable**, et cela vaut aussi pour ce
  que D1 promet : la légende d'une planche et les intitulés des cadres photo
  sont dans le fond. Pour les rendre éditables, il faut **dessiner la planche
  sans eux** et les reconstruire en objets PowerPoint — un rectangle de teinte
  et une ligne de texte par entrée de légende, une zone de texte par cadre. Le
  sommaire de la page de garde est dans le même cas.
- **L'étiquette d'un repère se dissocie mal du cône.** Hors du groupe, elle
  reste droite mais il faut penser à la déplacer avec lui — « pas dramatique »,
  mais évitable : l'attribut `upright` du corps de texte garde le texte
  horizontal dans un groupe qui tourne. À confirmer.
- **Le poids par résolution**, planche DP 2 de Sarnois en JPEG q88 :
  0,9 Mo à 200 dpi (3 308 × 2 339 px), 1,6 Mo à 300 dpi, 2,4 Mo à 400 dpi. Le
  rendu à 200 dpi est jugé « ok mais pas exceptionnel » — et c'est ce que
  l'export rend, voir D8.
- **Le verrou tient** : `a:spLocks noMove="1" noResize="1"`, posé sur la forme
  de la **diapo** et non sur celle de la mise en page, empêche bien de déplacer
  un cadre. Les titres de cadre, laissés libres, se déplaçaient : ils se
  verrouillent de même.
- **La réservation d'image fait ce qu'il faut** : « l'insertion d'une photo
  avec le bouton Insérer une image ne fait apparaître que ce qui peut
  apparaître en respectant le format de la réservation ». Le recadrage se
  corrige ensuite à la main, par « Rogner » — ce qui remplace le `cadrage` en
  deux fractions de `fenetre_de_cadrage`, que le chef de projet n'a plus à
  saisir à l'écran.
- **`upright` ne suffit pas seul** : l'étiquette reste droite tant que le
  groupe tourne peu, mais de côté elle se replie à une lettre par ligne — la
  boîte, elle, tourne, et le texte horizontal n'y tient plus. `wrap="none"`
  sur le corps de texte l'en empêche : confirmé le 25/09/2026, « le texte
  reste bien horizontal dans toutes les positions ».
- **Le plafond de PowerPoint** : *Fichier > Options > Options avancées > Taille
  et qualité de l'image* compresse par défaut les images à **220 ppp** à
  l'enregistrement. Au-delà, la résolution supplémentaire est perdue dès que le
  chef de projet enregistre, sauf à cocher « Ne pas compresser les images dans
  le fichier ». À mesurer sur un PDF réellement exporté avant de choisir.

---

## Ce qu'il faut mesurer avant de câbler

Les cinq comportements de PowerPoint dont dépendait le montage ont été relevés
à l'écran les 25 et 26/09/2026, sur cinq sondes successives, et **sont tous
acquis** : la réservation d'image rogne au format du cadre, `a:spLocks` tient,
`upright` avec `wrap="none"` garde l'étiquette droite à tous les angles, le
fond posé sur la mise en page est hors d'atteinte, et le SVG à texte en tracés
rend un cartouche identique à celui du PDF. Chaque constat est détaillé
ci-dessus, avec ce qu'il a coûté de découvrir.

Il ne reste rien à mesurer avant de câbler : le poids du SVG d'une planche à
fond IGN, dernière inconnue, a été relevé depuis le dépôt et tranché en D8 —
sept fois le fichier, d'où les deux voies.

Ce qui restera à vérifier **après** le premier export complet, et qu'aucune
sonde ne couvre : qu'un dossier entier s'ouvre, s'édite et s'exporte sans
accroc, et que la pagination du sommaire tombe juste une fois les diapos
surnuméraires supprimées.

---

## Les incantations que les sondes ont écrites

Cinq recettes trouvées à tâtons les 25 et 26/09/2026, et qui n'ont pas à être
retrouvées. `python-pptx` 1.0.2, testées sur un fichier réellement ouvert dans
PowerPoint.

**Une image sur la mise en page.** Son API ne l'offre que sur une diapo ; la
passer par une diapo jetable échoue, l'élément copié gardant le `r:embed` de
la diapo.

```python
image, rId = mise_en_page.part.get_or_add_image_part(str(fond))
formes = mise_en_page.shapes
formes._spTree.add_pic(formes._next_shape_id, "Fond de planche", image.desc,
                       rId, 0, 0, Mm(420), Mm(297))
```

**Une réservation d'image**, que la diapo héritera et que PowerPoint remplit en
rognant. `python-pptx` n'en crée pas : le `p:sp` s'écrit à la main dans la mise
en page, avec `<p:ph type="pic" idx="N"/>`, un `a:xfrm` et un `a:prstGeom`. La
diapo créée ensuite la porte comme une vraie `PicturePlaceholder`.

**Le verrou** se pose sur la forme de la **diapo**, pas sur celle de la mise en
page — le clonage ne reprend que l'identifiant et le type :
`<a:spLocks noMove="1" noResize="1"/>` dans le `p:cNvSpPr`.

**L'étiquette d'un repère** reste droite avec `upright="1"` **et**
`wrap="none"` sur le `a:bodyPr` — le premier seul la replie à une lettre par
ligne dès que le groupe tourne de côté. Et le groupe tourne autour du centre de
son cadre : un carré transparent de `2 × RAYON_CONE_MM` centré sur le repère
remet le pivot au bon endroit.

**La planche vectorielle** voyage dans une extension du `a:blip`, à côté du PNG
de repli, et sa partie se déclare à la main :

```python
partie_svg = Part(PackURI("/ppt/media/planche.svg"), "image/svg+xml",
                  diapo.part.package, svg_en_traces)
rId_svg = diapo.part.relate_to(partie_svg, RT.IMAGE)
# dans le <a:blip r:embed="{rId_png}"> :
#   <a:extLst><a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}">
#     <asvg:svgBlip xmlns:asvg="http://schemas.microsoft.com/office/drawing/2016/SVG/main"
#                   r:embed="{rId_svg}"/>
#   </a:ext></a:extLst>
```

**Et un piège** : `fill.transparency = 0.45` n'existe pas dans `python-pptx`.
Python l'accepte sans lever et ne fait rien. L'alpha s'écrit à la main,
`<a:alpha val="55000"/>` dans le `a:solidFill`. Partout où l'on règle une
propriété que la bibliothèque ne couvre pas, vérifier que le fichier produit la
porte — sans quoi c'est un repli silencieux.

---

## Comment l'éprouver

« Tester le résultat, pas l'exécution » : le critère n'est pas que le `.pptx`
s'écrive, mais qu'il porte les bonnes géométries. Le fichier produit se relit
avec `python-pptx`, et les tests mesurent, en EMU convertis en millimètres :

- la taille de diapo, 420 × 297 mm ;
- le nombre de diapos et leur ordre, pour un dossier de référence ;
- la position et le ratio de chaque cadre photo, contre
  `rapport_de_l_emplacement` ;
- la présence d'un groupe repère + cône par vue attendue, à 2,4 et 8 mm ;
- le dénominateur écrit au cartouche de chaque diapo de repérage, contre le
  cadrage calculé ;
- l'égalité des numéros de page des diapos alternatives, et le sommaire qui
  n'en compte qu'une.

Rien de tout cela ne prouve que PowerPoint l'ouvre correctement : c'est l'objet
de la liste ci-dessus, qui se refait à chaque changement du modèle.

---

## Ce qu'il ne faut pas faire

- **Toucher au moteur `Planche`.** Le lot s'en sert, il ne le modifie pas.
- **Redessiner une planche en formes PowerPoint.** Voir D0.
- **Rendre éditable ce qui porte une mesure** : échelle, cotes, cartouche hors
  sommaire. Un chiffre qu'on peut retoucher sans que la géométrie suive est un
  dossier faux qui s'affiche correctement.
- **Laisser redimensionner un plan.** Voir D2.
- **Remplacer la sortie PDF.** Les deux coexistent ; c'est la voie PDF qui
  reste la sortie vérifiée de bout en bout.
