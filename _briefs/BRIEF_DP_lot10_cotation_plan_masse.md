# BRIEF DP, lot 10 : cotation du plan de masse

> Lots 1 à 9 livrés. La DP 2 dessine le plan de masse sans une seule cote. Ce
> lot lui ajoute celles que les instructeurs réclament, **peu nombreuses et
> choisies par règle**, et une planche de détail pour la zone technique quand
> elle ne se lit pas à l'échelle du plan.
>
> Lire `README.md` et `CLAUDE.md` avant de commencer : ce brief ne les répète
> pas. En particulier, les règles « aucun repli silencieux » et « vérifier
> plutôt que supposer » s'appliquent telles quelles.

---

## Objectif

Les demandes de pièces complémentaires reçues début novembre 2026 réclament une
DP 2 « cotée correctement » : distance aux limites séparatives, à la route,
distance des locaux de stockage et de batterie, écartement inter-rangées. La DP 2
n'en porte aucune aujourd'hui.

Le risque propre à ce lot n'est pas la cote absente. C'est **la cote juste en
apparence et fausse sur le fond** : une distance à la clôture présentée comme un
recul à la limite, un hangar pris pour une habitation, un inter-rangée qui
contredit la coupe. Ces trois pièges ont été mesurés sur Sarnois avant d'écrire
ce brief — voir « Ce qui est mesuré ».

Ce brief est l'entrée d'une conversation neuve, selon la règle du dépôt : le plan
d'abord, la construction ensuite.

## Les références

Dans `exemples/_hoch-references/`, qui n'est pas versionné :

- **Pontivy**, « Dossier DP - Pontivy », page 5 : la DP 2 au 1:1 000 porte une
  quinzaine de cotes sur le plan lui-même. Clôture → limites de parcelle tout
  autour, largeur des pistes, inter-rangée, emprise du poste et sa distance à la
  limite, distance aux bâtiments existants. Trait fin, une flèche à chaque bout,
  valeur posée le long du trait.
- **SPLE**, « 250912_PC _SPLE », pages 8 et 9 : la cotation part sur des
  planches dédiées, avec une couleur par famille, et la zone technique a son
  **zoom au 1:200** — emprise de chaque ouvrage, distances à la clôture, à la
  limite et à l'axe de la voie.

On reprend de HOCH le zoom de la zone technique et le style sobre de Pontivy.
On ne reprend **pas** les couleurs par famille : c'est la réponse de SPLE à une
soixantaine de cotes, et ce lot en pose une quinzaine (D8).

---

## Décisions

Prises avec le chef de projet le 03/11/2026.

**D1 — Peu de cotes, prises depuis les tables et les ouvrages permanents.** Six
familles, et rien d'autre :

| | Cote | Combien | Planche |
|---|---|---|---|
| C1 | tables → clôture → limite séparative, **en chaîne** sur un même trait | une par côté de clôture | DP 2 |
| C2 | tables → axe de la voie la plus proche | une | DP 2 |
| C3 | ouvrage permanent → ses voisins à moins de 30 m | une par voisin | DP 2 bis, ou DP 2 si elle s'y lit (D7) |
| C4 | clôture → habitation la plus proche | une | DP 2 |
| C5 | écartement entre deux rangées | une par valeur distincte | DP 2 |
| C6 | largeur de piste, prise en travers | une par piste | DP 2 |

La chaîne de C1 répond aux deux demandes à la fois. Le chef de projet demande
tables → clôture, l'instructeur demande tables → limite, et les deux tiennent
sur un seul trait :

```
tables           clôture          limite
  |<---- 9,0 m ---->|<--- 6,2 m --->|
```

Un **côté** est un tronçon droit de la clôture, long d'au moins 20 m. La sonde
simplifie la clôture à 1,5 m, puis fusionne les segments qui tournent de moins
de 25°. Ces trois réglages sont ceux de la sonde : ils n'ont été éprouvés sur
aucun autre site.

Les **voisins** d'un ouvrage (C3) sont les autres ouvrages permanents, la limite
séparative et l'axe de la voie. Les reculs du PLU visent les constructions, et
c'est ce que l'instructeur entend par « distance des locaux de stockage et de
batterie ». La clôture et les tables ne sont pas des voisins. Une paire qu'un
autre ouvrage sépare ne se cote pas. La règle est sans effet sur Sarnois à 30 m,
mais sans elle, trois conteneurs alignés donneraient la cote du premier au
troisième à travers le deuxième.

**D2 — Les ouvrages permanents, et eux seuls.** Ce sont les trois familles de la
DP 4 : `POSTES` (`pdl_ptr`, `ptr`, `pdl`), `CONTENEURS` (`bess`,
`local_technique`) et `CITERNES` (`bache_incendie`, `citerne_refroidissement`).
On les lit dans `dp4_ouvrages.py`, sans les recopier. Sont exclus la base vie et
le stockage de chantier, qui sont temporaires, ainsi que le bac d'équarrissage
et la contention, qui relèvent du pâturage. Les dépendances d'un ouvrage — bac
de rétention, zone de remise, aire d'aspiration, plateforme — ne se cotent pas
pour elles-mêmes. À rouvrir si une demande les vise.

**D3 — Un ouvrage, c'est ce qui se touche, pas un objet du plan.** Le BE dessine
le BESS de Sarnois en 84 objets et le PTR en 6. Les objets d'une même catégorie
qui se touchent forment un seul ouvrage. Conséquence mesurée, et assumée : les
deux conteneurs BESS de Sarnois sont dessinés **à l'intérieur** du contour de
leur aire, à 1 m de son bord, et aucune tolérance de regroupement ne les sépare,
de 5 cm à 2 m. L'aire BESS compte donc pour un ouvrage, et l'écart entre ses
conteneurs ne se cote pas : c'est l'affaire du dimensionnement BESS, pas du plan
de masse. À rouvrir si une demande du SDIS le vise.

**D4 — La limite séparative est celle du parcellaire IGN.** C'est l'union des
parcelles d'assiette retenues **par la règle de la DP 1-3**
(`PART_MIN_ASSIETTE`) : les deux pièces ne peuvent pas désigner deux terrains
différents. Ce n'est pas le fichier d'emprise du chef de projet. Sur Sarnois il
coïncide avec le parcellaire à 0,01 m près, mais le premier jeu d'essai de
Sarnois mordait sur dix parcelles voisines (commentaire de
`PART_PLEINE_ASSIETTE`). Les limites entre deux parcelles d'assiette ne sont pas
des limites séparatives : l'union les efface.

**D5 — Les habitations et les voies viennent de la BD TOPO, pas du cadastre.**

- C4 prend le bâtiment le plus proche dont `usage_1` vaut `Résidentiel`. Le
  cadastre ne dit pas l'usage : sur Sarnois, son bâtiment le plus proche est un
  hangar agricole, à 103 m, alors que l'habitation est à 166 m. Si un bâtiment
  d'usage `Indifférencié` est plus proche que cette habitation, le rapport le
  dit, avec sa distance. Il ne la remplace pas sur le plan. La recherche
  s'arrête à 1 000 m de la clôture, valeur de départ à confirmer. S'il n'y a
  aucune habitation dans ce rayon, la légende le dit : c'est un résultat, pas
  une anomalie.
- C2, et les voisins « voie » de C3, se mesurent jusqu'à l'axe d'un
  `troncon_de_route`. L'étiquette donne sa nature et, s'il existe, son numéro
  (`cpx_numero`). Les natures qui comptent restent à trancher à la construction :
  Sarnois porte un `Chemin` à 11,8 m des tables, plus près que la
  `Route à 1 chaussée` à 15,1 m. Les attributs `prive` et `acces_vehicule_leger`
  existent pour en décider. S'il n'y a aucune voie à moins de 300 m des tables,
  la légende le dit.
- Du côté de la voie, la chaîne de C1 s'arrête sur la limite du terrain,
  c'est-à-dire sur l'alignement. Avec C2, l'instructeur a les deux références :
  l'alignement et l'axe.

**D6 — L'inter-rangée est celui de la coupe, ou le rapport le dit.** Sa valeur
vient de `resoudre_parametre(contrat, "inter_table_m", …)` de `dp3_coupes.py`,
la fonction même de la coupe, jamais d'une formule refaite à côté. Sur Sarnois,
trois chiffres coexistent : 5,0 m d'inter-table et 9,0 m de pas dans les
paramètres de structure, et 8 m dans les standards UNITe. La cote se pose entre
deux rangées dont l'écart mesuré vaut cette valeur. Si aucun écart du plan ne la
mesure, la cote dit ce que le plan mesure, et le rapport signale le désaccord
avec la coupe. Plaquer une valeur sur un écart qui ne la mesure pas, ce serait
exactement la planche fausse qui s'affiche correctement. Si le plan porte
plusieurs écarts distincts, chacun a sa cote.

**D7 — La zone technique a sa planche quand la DP 2 ne la lit pas.** Les trois
DP 2 de `sortie/` sortent au 1:2 000 : 3 m entre deux ouvrages y font 1,5 mm.
On ajoute donc une planche **DP 2 bis — Plan de masse : détail de la zone
technique**, sur le modèle de DP 1-3 bis : une pièce facultative de
`dossier.py`, produite seulement quand une cote C3 ne se lit pas sur la DP 2.
Le seuil de départ est de 10 mm de papier, et il se juge à l'épreuve. L'échelle
se choisit parmi 1:200, 1:500 et 1:1 000 : la plus grande à laquelle les
ouvrages et le bout de leurs cotes tiennent sur la planche. À Sarnois, la zone
fait 83 × 50 m et sort au 1:500. La DP 2 porte alors le cadre du détail, avec
son renvoi.

**D8 — Un seul style de cote, celui des primitives existantes.** C'est
`cote_oblique` de `primitives.py`, avec ses lignes d'attache et la valeur au
milieu. Le moteur ne tourne pas les textes : `Planche.ajouter_texte` n'a pas de
paramètre de rotation (vérifié le 03/11/2026). Les valeurs sont donc
horizontales, avec un halo, et le moteur n'est pas modifié pour autant — règle
du dépôt. Un `Dessin` dont l'origine est le centre L93 de la planche donne aux
primitives des coordonnées Lambert 93. Ce point se vérifie sur la première cote
mesurée dans le PDF, avant d'en poser d'autres.

**D9 — Ce qui n'est pas coté se dit.** La légende énonce la règle de sélection
en deux lignes : « Distances entre ouvrages cotées en deçà de 30 m » et
« Habitation la plus proche selon la BD TOPO (IGN) ». Elle dit aussi une absence,
quand il y en a une (D5). Une cote qui ne trouve pas sa place est nommée au
rapport. Elle n'est jamais retirée en silence.

**D10 — Rien à saisir, rien à changer au contrat.** Tout se calcule à la
génération, à partir du contrat et des services IGN, comme le parcellaire de la
DP 2. Le contrat ne gagne ni couche ni colonne : il a un lecteur hors du dépôt,
le photomontage. `Projet` ne gagne aucun champ. Les seuils et les réglages —
20 m, 30 m, 10 mm, ceux des côtés, les rayons de recherche — sont des constantes
commentées.

**D11 — Une source injoignable n'arrête pas la DP 2.** C'est la règle de la
phase de mise au point (README, « Ce qui deviendra bloquant »). Si la BD TOPO ne
répond pas, la DP 2 sort sans C2, sans C4 et sans les voisins « voie », et le
rapport le dit en clair. Le parcellaire garde son comportement actuel : sans
lui, rien ne se dessine. La BD TOPO rejoint la liste « Ce qui deviendra
bloquant ».

---

## Ce que le lot touche

- Un module de calcul des cotes, séparé du dessin pour se tester sans PDF :
  côtés, chaîne, regroupement, voisins, inter-rangée, largeur de piste.
- `dp_socle/planches/dp2_plan_masse.py` : la pose de C1, C2, C4, C5 et C6, celle
  de C3 quand elle s'y lit, et le cadre du détail.
- La planche DP 2 bis, et sa pièce dans `dp_socle/dossier.py`. DP 2 bis se
  traite partout où DP 1-3 bis l'est : `NUMERO_TABLEAU`, aux lignes 435 et 485
  de `sortie_pptx.py` le 03/11/2026.
- `dp_socle/ign.py` : les téléchargements BD TOPO. `_interroger_wfs` sert tel
  quel sur `BDTOPO_V3:troncon_de_route` et `BDTOPO_V3:batiment` (vérifié le
  03/11/2026), même si sa docstring ne parle que du Parcellaire Express.
- La légende de la DP 2 (D9), le rapport (D3, D5, D6, D9, D11) et le
  `README.md`.

## Ce que le lot ne touche pas

Le moteur `Planche` (D8). `dp_socle/contrat.py` et les trois producteurs (D10).
`dp3_coupes.py`, qu'on lit sans le modifier (D6). Les planches DP 4, qui cotent
déjà les dimensions des ouvrages. Le dépôt `photomontage`.

Hors périmètre, à rouvrir si une demande les cite : l'écart entre le BESS et les
tables, la largeur des portails, la distance aux boisements, les cotes NGF.

---

## Ce qui est mesuré

Mesuré le 03/11/2026 sur `sortie/PV-Sarnois-IND10B` et son emprise
(`exemples/sarnois-2-DXF/jma_60_sarnois-geoperso-2-15_09_2026_10_53.zip`), avec
une sonde jetable restée hors du dépôt.

| Grandeur | Sarnois IND10B |
|---|---|
| Clôture | 738 m de long, 207 × 278 m d'encombrement |
| Terrain d'assiette | parcelle ZA 0058, 3,695 ha ; le fichier d'emprise la suit à 0,01 m près |
| Clôture → limite | médiane 2,3 m, maximum 11,9 m ; moins de 1 m sur 44 % du linéaire |
| Côtés (C1) | 6. Tables → clôture : de 7,4 à 10,5 m, sauf 48,4 m sur le côté de 28 m qui longe la zone technique. Clôture → limite : de 0,4 à 13,4 m, dans l'axe de la chaîne, donc parfois en biais — d'où 13,4 m pour un écart maximal de 11,9 m |
| Ouvrages | 8 en tout, dont 3 que D2 écarte (base vie, stockage de chantier, bac d'équarrissage) ; avec eux, 7 paires à moins de 30 m, 5 à moins de 20 m et 11 à moins de 50 m. Le compte sans eux reste à faire |
| Emprise de la zone technique | 83 × 50 m pour les ouvrages permanents ; 162 × 308 m avec les trois autres |
| Ouvrage → limite | PDL/PTR 0,4 m, local technique 11,1 m, BESS 15,5 m |
| Regroupement (D3) | BESS : 84 objets, dont 80 sans surface ; deux conteneurs de 18,2 m² (6 × 3 m au catalogue), dans un contour de 48,3 m², à 1 m de son bord. PTR : 6 objets, dont un de 30,0 m² (10 × 3 m au catalogue) dans un contour de 82,9 m² |
| Voies (BD TOPO) | `Chemin` à 11,8 m des tables et à 3,0 m des ouvrages ; `Route à 1 chaussée` de 4 m de large, à 15,1 m des tables ; « Rue des Bouleaux » à 205 m |
| Bâtiments | au cadastre, le plus proche est à 103 m : une construction légère de 782 m². La BD TOPO donne le même bâtiment, d'usage `Agricole`. Première habitation à 166 m ; 144 bâtiments `Indifférencié` sur 347 |
| Cadre de la DP 2 | au 1:2 000, 820 × 536 m ; 307 m de marge à l'est et à l'ouest, 129 m au nord et au sud : l'habitation y tient |
| Inter-rangée | inter-table 5,0 m et pas 9,0 m dans les paramètres de structure ; 8 m dans les standards UNITe |
| Pistes | aucune à mesurer : deux linéaires de 4 m et une surface de 12 × 3 m |

Attributs vérifiés sur le WFS de la Géoplateforme le 03/11/2026 :

- `BDTOPO_V3:troncon_de_route` : `nature`, `importance`, `largeur_de_chaussee`,
  `cpx_numero`, `cpx_classement_administratif`, `cpx_toponyme_route_nommee`,
  `nom_voie_ban_gauche`, `nom_voie_ban_droite`, `prive`, `acces_vehicule_leger`
  et `urbain`, parmi d'autres.
- `BDTOPO_V3:batiment` : `usage_1`, `usage_2`, `nature`, `nombre_de_logements`,
  `hauteur` et `construction_legere`. Valeurs d'`usage_1` vues à Sarnois :
  `Résidentiel`, `Indifférencié`, `Annexe`, `Agricole`, `Commercial et
  services`, `Religieux`.

## Ce qui reste à mesurer

- Les réglages des côtés (1,5 m, 25°, 20 m), sur deux ou trois autres sites :
  Bray-Saint-Aignan IND10B, Chaumont-sur-Aire, Les Islettes.
- La position de la chaîne C1. Elle se pose là où les tables sont au plus près
  du côté. Si, sur ce même côté, la distance tables → limite est plus courte
  ailleurs, de plus de 0,5 m, il faut le dire : c'est cette distance-là que
  vérifie l'instructeur.
- Une cote plus courte que ses flèches. La convention du dessin technique met
  alors les flèches à l'extérieur. Le PDL de Sarnois est à 0,4 m de la limite.
- Une limite ou une habitation hors du cadre de la DP 2. C'est le cas de
  Boisné-La Tude, dont l'emprise fait plusieurs fois le projet (docstring de
  `_ce_que_la_planche_cadre`). La cote s'arrête alors au bord du cadre, avec sa
  valeur.
- Les pistes, sur un projet qui en porte : La Bruère-sur-Loir (deux pistes et une
  aire de retournement de 189 m², relevé du 15/10/2026), Chaumont-sur-Aire
  (voirie lourde et voirie légère).
- La lisibilité, sur l'épreuve A3, face à la trame des tables, aux numéros de
  parcelle et à la légende.

## Ordre de construction

Une étape par commit, et la CI Linux lue après chaque poussée :

1. `_interroger_wfs` refuse de tronquer en silence (voir « Pièges connus »),
   si ce n'est pas déjà fait.
2. Le module de calcul et ses tests, sur des cas construits et sur les mesures
   de Sarnois ci-dessus.
3. C1, C5 et C6 sur la DP 2 : contrat et parcellaire seulement, sans BD TOPO.
   La première cote se mesure dans le PDF avant qu'on en pose une autre (D8).
4. C2 et C4, avec la BD TOPO, et le comportement de D11.
5. C3 et la DP 2 bis.
6. La légende, le `README.md`, puis l'épreuve A3 sur Sarnois et sur un deuxième
   site.

## Comment le tester

Sur le modèle de `tests/test_echelle_pdf.py` et de ses outils
(`tests/mesure_pdf.py`), chaque famille se vérifie **dans le PDF produit**. On
retrouve le trait de cote dans le flux de contenu. Sa longueur papier, ramenée à
l'échelle, doit égaler la distance Lambert 93 à 0,5 % près, et son texte doit
être `nombre_fr` de cette distance. Un test vérifie que l'inter-rangée de la
DP 2 et celui de la coupe sont le même nombre, sur le même contrat.

Le module de calcul se teste sur des cas construits : une clôture en retrait de
la limite, trois conteneurs alignés, un hangar plus proche qu'une maison. La BD
TOPO est simulée dans la suite courante, et interrogée pour de vrai dans la
suite réseau.

## Pièges connus

- **`_interroger_wfs` s'arrête à `maximum` sans le dire.** Au-delà de 5 000
  entités, la boucle rend les 5 000 premières, sans aucun message. Le
  parcellaire d'un plan de masse n'atteint pas ce nombre. Les bâtiments à un
  kilomètre d'un bourg peuvent l'atteindre, et l'habitation la plus proche
  serait alors peut-être celle qui manque. La troncature doit lever une erreur
  nommée avant que C4 s'appuie sur la fonction. C'est un problème à part
  entière : à corriger avant ce lot, ou dans sa première étape.
- **Les métriques de texte diffèrent entre Windows et Linux** (26/09/2026). La
  place d'une étiquette se mesure avec `chasse_cairo` de `polices.py`, comme
  partout ailleurs, et c'est la CI Linux qui tranche.
- **Les références HOCH ne sont pas versionnées.** `exemples/_hoch-references/`
  n'existe que sur le poste.
- **Sarnois ne suffit pas.** Il n'a pas de piste à mesurer, et ses ouvrages sont
  tous dans un même coin. Il faut un deuxième site d'essai avant de dire que la
  DP 2 bis est juste.
