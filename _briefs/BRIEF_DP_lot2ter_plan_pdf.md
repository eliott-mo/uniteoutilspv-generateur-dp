# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 2ter : import d'un plan projet PDF

> Lots 1, 2, 2bis, 4 et 5 livrés. Le lot 2 importe un DXF HelioScope, le lot 2bis un plan
> du BE interne. Ce lot ajoute un **troisième producteur du même contrat** : un plan projet
> au format PDF.
>
> Lire `README.md` et `CLAUDE.md` avant de commencer : ce brief ne les répète pas. Il ne
> rediscute ni le moteur `Planche` du lot 1, ni le contrat de sortie, qui ne se touche
> qu'aux conditions du § D6.

---

## Objectif

Produire, depuis un **plan projet PDF**, le même `sortie/{projet}/geometries.gpkg` et le
même `projet.json` que les lots 2 et 2bis, à `version_contrat` égale, distingués par
`origine = "plan_pdf"`. Le lot 4 doit continuer à lire une seule structure sans savoir
lequel des trois producteurs l'a écrite.

## Pourquoi ce lot existe

Il y a des projets sans plan BE et sans DXF complet. Le cas est arrivé sur
**Gannay-sur-Loire (03)**, en septembre 2026 : le chef de projet disposait d'un export
HelioScope qui ne porte **que les tables**, et d'un plan PDF qui porte tout le reste —
clôture, portail, haies, pistes, poste de livraison, local technique, réserve incendie.

Ce plan a été digitalisé à la main dans le dépôt `photomontage`, par trois scripts
mono-cas (`exemples/casxcas/lire_plan.py`, `caler_plan_sur_tables.py`,
`lire_ouvrages.py`, environ 525 lignes). Ils marchent, ils sont mesurés, et ils ne
survivront pas au projet suivant. Ce lot en fait une brique pérenne, ici, où elle sert
aussi bien le dossier DP que le photomontage.

---

## Ce qui existe déjà, et qu'il faut aller lire

### Dans ce dépôt

| Brique | Où | Ce qu'elle donne |
|---|---|---|
| Écriture du contrat | `dp_socle/import_be.py:2081` `NOM_GEOPACKAGE`, `:2087` `ORIGINE_*`, `:2099` `VERSION_CONTRAT` | le format pivot, ses couches et ses colonnes |
| Lecture du contrat | `dp_socle/contrat.py` | ce que le lot 4 exige, et ses refus nommés |
| Non-divergence | `tests/test_contrat_helioscope.py::test_les_deux_lots_ecrivent_le_meme_schema` | **le test qui interdit aux producteurs de partir chacun de leur côté** |
| Calage HelioScope | `dp_socle/helioscope.py` | le géoréférencement par la résolution de l'entité IMAGE, qui encode le zoom Web Mercator donc la latitude ; et son test d'intégrité sur la partie fractionnaire du zoom |
| Cotes d'ouvrages | `dp_socle/contrat.py:73` `Cote`, `:121` `decoder_cote` | `ordre_cotes` donne le sens de chaque nombre, jamais leur position |
| Erreurs nommées | `dp_socle/erreurs.py` | toutes dérivées de `ErreurDP` |

### Dans `git_unite/photomontage` — les trois scripts à reprendre

Prototype mono-cas. **Rien à importer tel quel**, mais tout à relire : les pièges y sont
documentés et mesurés.

| Fichier | Ce qu'il fait | Ce qu'il faut en garder |
|---|---|---|
| `exemples/casxcas/lire_plan.py` | rend le PDF à 300 DPI, relève les couleurs de légende, extrait les tracés | **le relevé des couleurs sur la pastille** (§ D1) |
| `exemples/casxcas/caler_plan_sur_tables.py` | mesure l'échelle sur le pas des rangées, recale par recouvrement | **l'échelle mesurée et non cherchée** (§ D3), le Jaccard (§ D4) |
| `exemples/casxcas/lire_ouvrages.py` | relève clôture, portail, ouvrages | **position et orientation seules** (§ D2) |

---

## Décisions prises en amont

Sept points arbitrés, tous issus d'une mesure faite sur Gannay. Ils ne sont pas à
rediscuter ni à « améliorer ».

### D1 — Les couleurs de la légende se relèvent, elles ne se supposent pas

Le plan porte une légende : une pastille de couleur, puis un libellé. Il faut relever la
couleur **sur la pastille qui précède chaque libellé**, et non écrire en dur une table de
correspondance.

Mesuré à Gannay : un aplat supposé se trompe. Le violet du plan n'était pas le violet
attendu, et la clôture partait dans la mauvaise couche sans que rien ne le signale.

### D2 — Les formes du PDF ne sont pas à l'échelle

C'est l'instruction explicite du chef de projet, du 21/09/2026 :

> « Les formes sur le PDF ne servent qu'à localiser et représenter les éléments
> graphiquement sur le plan, mais ne sont pas nécessairement à l'échelle. »

On ne retient donc d'un **ouvrage** (poste, local, citerne, portail) que sa **position** et
son **orientation**. Ses dimensions viennent des gabarits UNITe, exactement comme au
lot 2bis. Un rectangle de « poste combiné » dessiné 3 × 12 au lieu de 12 × 3 se dessinerait
parfaitement et ne se verrait jamais.

Les **tracés** — clôture, haies, pistes — sont une autre affaire : leur géométrie est
signifiante, on la garde. À Gannay la clôture faisait 61 sommets pour 667 m.

### D3 — L'échelle se mesure sur les tables, elle ne se cherche pas

Une recherche d'échelle par optimisation est partie aux bornes de son intervalle sur
Gannay. Ce qui a marché tient en une phrase : **les rangées de panneaux du plan ont un pas
connu**, celui du DXF. Mesuré, ce pas valait **71,40 px ± 0,17** pour un entraxe réel de
**10,93 m**, soit **0,1531 m/px** — une incertitude de deux pour mille, sans aucune
optimisation.

Le plan PDF **doit donc porter les tables** pour être calable. S'il n'en porte pas, le lot
lève : il n'y a pas d'échelle à trouver ailleurs.

### D4 — Le recalage se fait par recouvrement, pas par corrélation d'image

Une fois l'échelle connue, la translation se trouve en maximisant le **recouvrement de
Jaccard** entre le damier des tables du plan et celui du DXF. Mesuré à Gannay : **88,3 %**.

La corrélation croisée sur l'image entière, elle, sert au calage du **fond** HelioScope sur
l'orthophoto IGN, pas ici. Et quand elle sert, elle doit être **contrainte au domaine des
décalages valides** : sans cette contrainte, le pic est sorti à dx = −500 px sur Gannay,
hors de toute translation possible.

### D5 — Ce lot est EN AVAL du lot 2, pas à sa place

Le géoréférencement vient des tables, donc du lot 2. L'enchaînement est :

1. le lot 2 lit le DXF HelioScope et pose les tables en Lambert 93 ;
2. **le lot 2ter** cale le plan PDF sur ces tables et en tire tout le reste ;
3. les deux écrivent dans le même contrat.

Un plan PDF seul, sans DXF de tables, n'est pas traitable par ce lot. C'est une limite
assumée, pas un manque à combler.

### D6 — Même contrat, même version, `origine = "plan_pdf"`

Ajouter `ORIGINE_PLAN_PDF = "plan_pdf"` à `ORIGINES` dans `import_be.py`, et étendre
`tests/test_contrat_helioscope.py` pour qu'il vérifie les **trois** producteurs et non
deux. C'est ce test qui fait tenir l'ensemble : une couche ou une colonne ajoutée d'un
côté doit l'être des trois.

`version_contrat` ne change pas. Si ce lot avait besoin d'une couche nouvelle, il faudrait
la traiter chez les deux autres producteurs dans le même mouvement — et alors seulement
incrémenter.

### D7 — Aucun repli silencieux, et trois refus nommés au minimum

Conformément à la règle qui prime dans `CLAUDE.md`. Au moins :

- `ErreurLegendeIntrouvable` — un libellé attendu n'est pas dans la légende, ou sa
  pastille n'est pas lisible ;
- `ErreurEchelleIncoherente` — l'échelle mesurée sur le pas des rangées s'écarte de plus
  de 2 % de celle qu'implique l'emprise des tables ;
- `ErreurRecouvrementInsuffisant` — le Jaccard du recalage tombe sous 0,70.

Une couche qui sort **vide** alors que son libellé figure à la légende est aussi une
anomalie, pas un résultat : elle doit au minimum produire un avertissement visible.

### D8 — La correction de plan se déclare, elle ne se fait pas toute seule

Cas réel de Gannay : le poste de livraison était dessiné à 7,7 m en retrait de la clôture,
alors qu'il en tient lieu sur sa longueur — la clôture s'arrête à son bord gauche et
reprend à son bord droit. Le chef de projet l'a fait corriger.

C'est une **correction du plan**, pas une lecture. Le lot peut l'offrir, jamais l'appliquer
d'autorité, et toute correction appliquée doit figurer dans `projet.json` avec sa raison.

---

## Une dépendance à coordonner : la focale EXIF

Le photomontage a besoin, pour chaque photo géolocalisée, de la **focale** — champ EXIF
`FocalLengthIn35mmFilm` (tag 41989). `dp_socle/lecture_exif.py` lit aujourd'hui la
position, la date et le cap, mais **pas la focale**.

Sans elle, la pose n'est pas déterminée : mesuré à Gannay, l'emprise latérale de la nappe
varie de ±15 % entre 22 et 30 mm équivalents. Sur un photomontage d'étude d'impact, c'est
une donnée opposable.

Il faut donc l'ajouter, **et refuser bruyamment quand elle manque** — c'est exactement le
patron « aucun repli silencieux » du dépôt, et c'est le seul endroit où le rappel peut
vivre sans dépendre de la mémoire de qui dépose les fichiers.

⚠️ **`lecture_exif.py` est en cours de reprise par le lot 6.** Ne pas le modifier depuis ce
lot : signaler le besoin, et laisser le lot 6 l'intégrer. Le lot 2ter n'en dépend pas pour
fonctionner.

---

## Travail attendu, dans cet ordre

1. **`dp_socle/plan_pdf.py`** — rendu du PDF à 300 DPI, lecture de la légende, extraction
   des tracés et des ouvrages par couleur. Aucun dessin : ce lot produit de la géométrie.
2. **Le calage** — échelle sur le pas des rangées (D3), translation par Jaccard (D4),
   contre les tables posées par le lot 2.
3. **L'écriture du contrat** — `origine = "plan_pdf"`, `ORIGINES` étendu, et le test de
   non-divergence porté à trois producteurs (D6).
4. **Les refus nommés** dans `erreurs.py` (D7).
5. **`app.py`** — le dépôt d'un plan PDF à côté du DXF HelioScope, dans la section
   d'import. ⚠️ Le lot 6 travaille sur la **section 3** du même fichier : se limiter
   strictement à la section d'import, et ne pas toucher à la carte de la section 2.
6. **Un test qui mesure le RÉSULTAT**, pas l'exécution, sur le plan de Gannay : échelle à
   0,1531 m/px ± 2 ‰, Jaccard ≥ 0,85, clôture fermée de 667 m ± 1 %.

## Dépendances

Un lecteur de PDF est à ajouter à `requirements.txt`, version épinglée et justifiée par un
commentaire. ⚠️ Le lot 6 touche aussi ce fichier : ajouter une ligne, ne pas réordonner.

## Jeu d'essai

`git_unite/photomontage/exemples/casxcas/` porte le cas complet : le PDF du plan projet, le
DXF HelioScope `helioscope_design_10465241.dxf`, son fond `design_10465241_baseimage.jpg`,
et les trois scripts qui ont servi de prototype.
