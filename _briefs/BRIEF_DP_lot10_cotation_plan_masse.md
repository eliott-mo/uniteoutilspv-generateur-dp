# BRIEF DP, lot 10 : cotation du plan de masse

> Lots 1 à 9 livrés. La DP 2 dessine le plan de masse sans une seule cote. Ce
> lot lui ajoute celles que les instructeurs réclament, **peu nombreuses et
> choisies par règle**, et une planche de détail pour la zone technique quand
> elle ne se lit pas à l'échelle du plan.
>
> Lire `README.md` et `CLAUDE.md` avant de commencer : ce brief ne les répète
> pas. En particulier, les règles « aucun repli silencieux » et « vérifier
> plutôt que supposer » s'appliquent telles quelles.
>
> Posé le 03/11/2026, repris les 07 et 08/11/2026. Entre-temps, une maquette a
> été relue par le chef de projet du lot, puis par les chefs de projet de
> Saint-Cyr-en-Val et d'Auzainvilliers, les deux projets qui ont reçu la
> demande de compléments, et confrontée au texte de ces deux demandes. Les
> décisions ci-dessous sont celles de ces relectures. Chacune porte sa date, et
> dit ce que la maquette a montré quand c'est la mesure qui a tranché.
>
> La maquette est versée à côté de ce brief, dans
> `_briefs/maquette_lot10_cotes_dp2.py`, sous son état du 08/11/2026 (v5). C'est une
> référence, pas du code à reprendre : elle remplace à l'exécution des fonctions
> du socle pour poser ses cotes sur la DP 2 du lot 4, et rien ne la teste. On y
> lit le détail de ce que les décisions résument — le placement des valeurs
> (`poser`), le voisinage relatif, les essais de la DP 2 — et, en commentaire,
> les pièges mesurés en chemin.

---

## Objectif

Les demandes de pièces complémentaires reçues début novembre 2026 réclament une
DP 2 « cotée correctement ». Leurs termes, relus le 08/11/2026 :

- **Auzainvilliers** : « DP02 - Un plan de masse coté dans les trois
  dimensions [Art. R. 431-36 b) du Code de l'urbanisme] ». Le plan doit donner
  les « distances avec les limites séparatives, avec la route, et des locaux de
  stockages et de batteries, écartement inter-rangées », et « matérialiser les
  éléments paysagers envisagés ».
- **Saint-Cyr-en-Val** : « Un plan de masse mentionnant précisément l'accès au
  site et les distances d'implantation des différentes constructions (local
  technique, poste de livraison, bâtiment, panneaux solaires) par rapport aux
  voies et emprise publiques et par rapport aux limites parcellaires ». Il doit
  aussi indiquer les angles de prise de vue des photographies, qui figurent
  également sur le plan de situation.

La DP 2 n'en porte aucune aujourd'hui.

Le risque propre à ce lot n'est pas la cote absente. C'est **la cote juste en
apparence et fausse sur le fond** : une distance à la clôture présentée comme un
recul à la limite, un hangar pris pour une habitation, un inter-rangée qui
contredit la coupe. Ces trois pièges ont été mesurés sur Sarnois avant d'écrire
ce brief — voir « Ce qui est mesuré ». Les relectures en ont ajouté deux :
- une valeur juste sous un libellé qui se lit de travers (C1, 07/11) ;
- une valeur fausse mesurée depuis un tracé simplifié de la clôture (C1,
  08/11).

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
soixantaine de cotes, et la maquette en pose de quinze à quarante par dossier,
réparties sur deux planches (D7, D8).

---

## Décisions

Prises avec le chef de projet du lot les 03 et 04/11/2026, sur la maquette.
Reprises le 07/11/2026 sur les retours des chefs de projet de Saint-Cyr-en-Val
et d'Auzainvilliers, puis le 08/11/2026 sur le texte des deux demandes.

### D1 — Peu de cotes, prises depuis les tables et les ouvrages permanents

Huit familles, et rien d'autre :

| | Cote | Combien | Planche |
|---|---|---|---|
| C1 | tables → limite parcellaire, à travers la clôture ; et, ailleurs sur le côté, clôture → limite parcellaire | par côté de clôture dont les tables sont à moins de 30 m : une cote des tables, et une de la clôture si elle est à plus de 0,5 m de la limite | DP 2 |
| C2 | la construction la plus proche → axe de la voie publique la plus proche | une, à toute distance | DP 2 |
| C3 | ouvrage permanent → ses voisins directs, et → la limite parcellaire | voisins directs à moins de 30 m ; limite à moins de 30 m, et toujours pour les batteries et le local de stockage | avec sa zone (D7) |
| C4 | clôture → habitation la plus proche | une | DP 2 |
| C5 | écartement entre deux rangées | une, à la valeur de la coupe | DP 2 |
| C6 | largeur de piste, prise en travers | une par largeur et par type de piste | DP 2 |
| C7 | batteries et citernes → table la plus proche | une par conteneur BESS et par citerne | avec sa zone (D7) |
| C8 | poste de livraison → axe de la voie publique la plus proche | une, en deçà de 30 m | avec sa zone (D7) |

Les hauteurs ne sont pas des cotes : elles sont dans la légende (D12).

**C1** (08/11). Les deux demandes visent la distance des constructions aux
limites, pas à la clôture : « par rapport aux limites parcellaires » à
Saint-Cyr, « avec les limites séparatives » à Auzainvilliers. Chaque côté de la
clôture reçoit donc deux cotes séparées, posées à deux endroits du côté :

```
« 6,6 m (tables – limite parcellaire) »     là où les tables sont au plus près
« 6,4 m (clôture – limite parcellaire) »    ailleurs, si l'écart dépasse 0,5 m
```

- **Tables → limite parcellaire** se mesure depuis la table la plus proche du
  côté, dans la direction de la clôture, jusqu'au premier croisement de la
  limite : la ligne traverse la clôture, et le libellé dit ses deux bouts.
- **Clôture → limite parcellaire** se mesure perpendiculairement au côté,
  depuis la clôture réelle. On l'essaie au milieu du côté, puis à 35, 65, 20 et
  80 %. Elle se pose à au moins 20 mm de papier de la première cote, et, parmi
  les endroits qui conviennent, là où elle gêne le moins les autres cotes. Sur
  un côté plus court que ces 20 mm, elle ne se pose pas, et le rapport le dit.
  Quand la clôture est sur la limite, il n'y a pas de seconde cote : le dessin
  le montre.

Pourquoi deux cotes, et non plus la chaîne tables | clôture | limite du
03/11 : à 1:2 000, un écart de 1 m entre clôture et limite fait 0,5 mm de
papier. Les flèches de la petite cote se posaient à l'extérieur, sur celles de
la grande, et l'on ne savait plus quelle valeur allait où (relecture du 08/11).
Le 07/11, les libellés nommaient l'orientation de la limite (« limite
nord-ouest ») : retirée le 08/11, le plan montre de lui-même où est la limite.

Un **côté** est un tronçon droit de la clôture, long d'au moins 20 m : la
clôture simplifiée à 1,5 m, dont on fusionne les segments qui tournent de moins
de 25°. Ces réglages ont tenu sur Sarnois, Saint-Cyr et Auzainvilliers. Le
tracé simplifié **ne sert qu'à grouper et à orienter** : toute distance se
prend sur la clôture réelle. La maquette du 07/11 mesurait depuis lui, et
affichait à Saint-Cyr « 0,9 m » et « 1,0 m (clôture – limite) » là où la
clôture est sur la limite (0,00 m, relevé le 08/11). Un côté dont les tables
sont à plus de 30 m ne se cote pas, et le rapport le dit (03/11).

**C2** (08/11, après son retrait du 03/11). Saint-Cyr demande les distances
des constructions, panneaux compris, « par rapport aux voies et emprises
publiques ». Une cote part de la construction la plus proche — table ou
ouvrage permanent — jusqu'à l'axe de la voie publique la plus proche, à toute
distance ; hors du cadre, elle s'arrête au bord et le dit, comme celle de
l'habitation. Une voie est publique au sens de C8. L'axe se dessine sur 25 m de
part et d'autre du pied de la cote. Règles de la seconde relecture du 08/11 :

- **La cote est perpendiculaire à l'axe, et ses flèches le touchent.** Elle part
  de la face de la construction tournée vers la voie. La BD TOPO coupe une
  route à chaque carrefour : les tronçons publics se fondent en un réseau avant
  la mesure, sans quoi le bout d'un tronçon passerait pour le bout de la route.
- **Elle ne se superpose à aucune autre cote.** Une voie qui longe le terrain
  est parallèle à sa limite : sa cote partait du même point, dans la même
  direction, que la cote de la même construction à la limite. Elle se décale
  donc le long de la face, jusqu'à 4 mm de papier de toute cote parallèle, et
  le rapport dit la distance perdue. À Auzainvilliers : 11,6 m depuis la
  citerne incendie, au lieu de 11,0 m à son angle. La v4 réunissait les deux
  cotes en un libellé, « 5,5 m (limite parcellaire ; axe de la D18 à 11,0 m) »,
  mais ses flèches s'arrêtaient au bord de la route.
- **Une voie publique qui s'arrête avant le site n'a pas de perpendiculaire.**
  La cote va alors à son extrémité, et le dit : « 23,3 m (extrémité de la
  route) » à Saint-Cyr. La route empierrée publique y finit à l'angle
  nord-ouest du site. Les chemins qui longent le côté ouest passent sur des
  parcelles, sur toute une bande de ±6 m autour de leur axe (relevé le 08/11).

**C3.** Les **voisins directs** d'un ouvrage (04/11) sont ceux du graphe de
voisinage relatif. La paire i–j ne se cote pas quand un troisième ouvrage k est
plus proche des deux, c'est-à-dire quand max(d(i,k), d(j,k)) < d(i,j). Les deux
cotes qui passent par k situent déjà la paire ; chaque ouvrage garde son plus
proche voisin, et une zone reste d'un seul tenant. À Auzainvilliers, cela fait
9 cotes au lieu de 19 paires à moins de 30 m. S'ajoutent le seuil de 30 m et la
règle de la paire séparée : un ouvrage posé sur le segment interdit la cote, sans
quoi trois conteneurs alignés donneraient la cote du premier au troisième à
travers le deuxième.

La cote **à la limite** se pose en deçà de 30 m, quand aucun ouvrage n'est sur
le trajet. Les batteries (`bess`) et le local de stockage (`local_technique`)
se cotent jusqu'à la limite **toujours**, sans seuil et même par-dessus un autre
ouvrage (04/11) : c'est eux que l'instructeur nomme. À Auzainvilliers, aucun des
deux BESS n'en avait, l'un à 19,7 m derrière le PDL/PTR, l'autre à 30,9 m. Le
rapport dit pour chacun quelle règle commune il franchit. Le calque
`UNI_Local_Stockage` arrive en `local_technique` (`import_be.py`). Un ouvrage ne
se cote plus vers la voie (03/11), sauf le poste de livraison (C8).

**C6.** La largeur se prend en travers : des rayons partent du bord, à angle
droit, vers l'intérieur, et l'on garde leur médiane, qui écarte les bouts, les
virages et les élargissements. Une cote par largeur distincte, au demi-mètre
près, et par type de piste. Les pistes existantes comptent : à Saint-Cyr, elles
sont « à renforcer si nécessaire », donc des travaux du projet. Ne sont pas des
pistes (03/11) : une voirie qui porte le corps d'un ouvrage, qui est sa
plateforme — la maquette cotait 4,2 m sous un poste ; une bande de moins de 2 m
de large ; une surface de moins de trois fois le carré de sa largeur, qui est
une aire ; l'aire de grutage. Aucune cote ne relie une piste à la clôture
(03/11). Le libellé dit « (piste) » : sans lui, la largeur d'une piste qui
longe la clôture se lisait comme leur écart.

**C7** (07/11). Les conteneurs BESS, la citerne de refroidissement et la citerne
incendie se cotent jusqu'à la table la plus proche : c'est ce que regarde le
SDIS, le risque d'un côté, la défense de l'autre. La relecture d'Auzainvilliers
le demandait pour le BESS sud et les deux citernes ; la règle prend tous les
conteneurs. Comme pour une paire d'ouvrages, la cote ne se pose pas quand un
autre ouvrage est sur le segment : il porte déjà la distance qui compte, et le
rapport le dit. Mesuré à Auzainvilliers : citerne de refroidissement 5,66 m,
BESS sud 8,26 m, BESS nord 28,29 m, citerne incendie 6,55 m. La relecture
annonçait 8,9 m pour la citerne de refroidissement. C'est la distance à la table
au nord-ouest (8,89 m), quand la plus proche est au sud (5,66 m) : voir « Ce qui
reste à mesurer ».

**C8** (07/11). Le poste de livraison (`pdl`, `pdl_ptr`) se cote jusqu'à l'axe
de la voie **publique** la plus proche, en deçà de 30 m. C'est la relecture de
Saint-Cyr qui l'a demandé, en notant la limite de son propre cas : « on n'a pas
cette route au cadastre ». La BD TOPO ne dit pas à qui appartient une voie, le
cadastre si : le domaine public n'est pas cadastré. Un `troncon_de_route` est
donc tenu pour public quand, sur les 50 m qui entourent le poste, la moitié au
moins de son tracé passe hors des parcelles cadastrales, et hors de la clôture.
Mesuré le 07/11 :

- à Saint-Cyr, le tronçon le plus proche du PDL/PTR est un chemin à 89 % dans
  la clôture (5,2 m) ; viennent ensuite une route empierrée et un chemin posés
  sur des parcelles (6,3 et 7,5 m). La première voie publique est à 108 m. Pas
  de cote, et le rapport nomme ce qu'il a écarté ;
- à Auzainvilliers, la D18 passe à 12,2 m, entièrement hors des parcelles.
  Elle se mesure comme C2, perpendiculairement à l'axe, et ne se superpose pas
  à la cote du poste à la limite (4,7 m) : « 12,2 m (axe de la D18) » (08/11).

L'axe se dessine sur 25 m de part et d'autre du pied de la cote. L'étiquette
donne le numéro de la voie (`cpx_numero`) quand elle en a un, sa nature sinon.
Quand C8 et C2 partent du même poste vers la même voie, seule C2 se pose.

### D2 — Les ouvrages permanents, et eux seuls (03/11)

Ce sont d'abord les trois familles de la DP 4 : `POSTES` (`pdl_ptr`, `ptr`,
`pdl`), `CONTENEURS` (`bess`, `local_technique`) et `CITERNES`
(`bache_incendie`, `citerne_refroidissement`), lues dans `dp4_ouvrages.py` sans
les recopier. **S'y ajoutent depuis le 04/11 le bac de rétention et la zone de
remise.** La première maquette n'en cotait aucun, et la relecture a demandé
pourquoi rien ne situait le bac parmi les ouvrages qui l'entourent. Le
catalogue leur donne une hauteur, 2,3 m et 3 m : ce sont des constructions.
Restent exclus la base vie et le stockage de chantier, qui sont temporaires, le
bac d'équarrissage et la contention, qui relèvent du pâturage, ainsi que l'aire
d'aspiration et la plateforme, qui sont des sols.

### D3 — Un ouvrage se mesure sur son corps, aux cotes du catalogue (03/11)

Le corps est l'objet du calque qui a les dimensions du catalogue : le poste,
jamais sa plateforme ni le contour qui l'entoure. Depuis le 08/11/2026, c'est
`palette.separer_les_corps` qui le reconnaît, à 5 % près, pour les postes comme
pour les conteneurs ; le lot 10 prend les corps que `objets_a_dessiner` lui
rend, et ne refait pas cette reconnaissance. La maquette tolérait 15 %, mais les
corps mesurés sont à moins de 1 % du catalogue. Ce qui entoure le corps se
dessine en plateforme, comme la terre remise autour d'un poste. À
Auzainvilliers, chaque conteneur BESS de
6 × 3 m est posé sur un aplat plein de 6,0 × 8,1 m de la même couleur, qui le
cachait : la cote prise sur le conteneur s'arrêtait au milieu de l'orange, et la
DP 2 montrait un BESS de 48 m² quand la DP 4 le dessine à 18 m². L'aplat se
dessine donc en plateforme (04/11). C'est la plateforme des batteries que le
tableau bilan déclare : « Surface plateforme batteries », 100 m² pour deux
conteneurs à Auzainvilliers et 50 m² pour un à Sarnois, pour des aplats de
48,3 m². La question posée au bureau d'études le 04/11, dalle ou aire dégagée,
est retirée du rapport (08/11).

Les corps d'une même catégorie qui se touchent, à 2,5 cm près, forment un seul
ouvrage. Un corps que le bureau d'études a dessiné deux fois compte une fois.
Un ouvrage sans aucun objet aux cotes du catalogue se mesure sur tout son
dessin, et le rapport le dit. Un ouvrage sans surface à mesurer — une citerne
arrivée en collection de géométries, un contour resté ouvert — se dit au
rapport. Il ne sort jamais des cotes en silence : la citerne de refroidissement
d'Auzainvilliers l'a fait dans une version de la maquette.

Le brief du 03/11 voyait à Sarnois deux conteneurs BESS dans une même aire.
C'est un seul conteneur, dessiné deux fois à l'identique — différence
symétrique nulle, vérifié le 08/11/2026 —, et le tableau bilan en déclare un :
un seul ouvrage, mesuré sur son corps.

### D4 — La limite est celle du parcellaire IGN

C'est l'union des parcelles d'assiette retenues **par la règle de la DP 1-3**
(`PART_MIN_ASSIETTE`) : les deux pièces ne peuvent pas désigner deux terrains
différents. Ce n'est pas le fichier d'emprise du chef de projet. Sur Sarnois il
coïncide avec le parcellaire à 0,01 m près, mais le premier jeu d'essai de
Sarnois mordait sur dix parcelles voisines (commentaire de
`PART_PLEINE_ASSIETTE`). Les limites entre deux parcelles d'assiette ne sont pas
des limites séparatives : l'union les efface.

Sur la planche, elle s'appelle « limite parcellaire », sans orientation (08/11),
et le pied la définit comme celle du terrain d'assiette. « Séparative » est le
mot de l'instructeur d'Auzainvilliers, mais il serait faux du côté de la route,
où la limite est l'alignement ; « parcellaire » est celui de Saint-Cyr.

### D5 — Les habitations et les voies viennent de la BD TOPO, pas du cadastre

- C4 prend le bâtiment le plus proche dont `usage_1` vaut `Résidentiel`. Le
  cadastre ne dit pas l'usage : sur Sarnois, son bâtiment le plus proche est un
  hangar agricole, à 103 m, alors que l'habitation est à 166 m. Si un bâtiment
  d'usage `Indifférencié` est plus proche que cette habitation, le rapport le
  dit, avec sa distance. Il ne la remplace pas sur le plan. La recherche
  s'arrête à 1 000 m de la clôture. S'il n'y a aucune habitation dans ce rayon,
  la légende le dit : c'est un résultat, pas une anomalie. Hors du cadre de la
  DP 2, la cote s'arrête au bord du cadre et le dit : « 948 m (habitation la
  plus proche, hors cadre) » à Auzainvilliers.
- Les voies servent à C2 et à C8 (08/11), avec le cadastre pour dire
  lesquelles sont publiques. La recherche va à 300 m de la clôture, et écarte
  d'office les `Sentier`, `Escalier` et `Piste cyclable`. S'il n'y a aucune
  voie publique dans ce rayon, le rapport le dit.

### D6 — L'inter-rangée est celui de la coupe, ou le rapport le dit

Sa valeur vient de `resoudre_parametre(contrat, "inter_table_m", …)` de
`dp3_coupes.py`, la fonction même de la coupe, jamais d'une formule refaite à
côté. Sur Sarnois, trois chiffres coexistent : 5,0 m d'inter-table et 9,0 m de
pas dans les paramètres de structure, et 8 m dans les standards UNITe. La cote se
pose **une fois** (03/11), sur l'écart mesuré qui vaut la coupe à 0,15 m près,
le plus proche du centre du champ. Si aucun écart du plan ne la mesure, il n'y a
pas de cote, et le rapport signale le désaccord avec la coupe. Plaquer une
valeur sur un écart qui ne la mesure pas, ce serait exactement la planche fausse
qui s'affiche correctement.

La relecture du 07/11 l'a confirmé à rebours. À Saint-Cyr, elle attendait 4,5 m
et lisait 4,9 m. La maquette tournait sur l'indice IND06 (tableau bilan V6 :
4,9 m ; plan : 4,91 m), alors que le dossier déposé est l'IND07 (tableau V7 :
4,5 m ; plan : 4,51 m). Coupe et plan de masse concordent dans chaque indice :
c'est la relecture qui comparait deux indices.

### D7 — La zone technique part sur sa planche quand la DP 2 la lit mal (04/11)

Une **zone** est un ensemble d'ouvrages que des cotes C3 relient ; leurs cotes
C7 et C8 la suivent. Elle part sur une planche **DP 2 bis — Plan de masse :
détail de la zone technique** (ter, quater… s'il y en a plusieurs) dès qu'une de
ces trois choses est vraie :

- une de ses cotes fait moins de 3 mm de papier sur la DP 2 (10 mm dans le
  brief du 03/11) ;
- une de ses valeurs n'a pas de place nette : posée au mieux faute de place, ou
  posée sur un ouvrage ou en travers de la clôture ;
- une de ses cotes passe sous la légende.

Les deux derniers cas ne se voient qu'en dessinant. La DP 2 est donc essayée,
les zones fautives partent, puis elle est refaite sans elles, jusqu'à ce que
plus aucune zone ne bouge : retirer une zone libère de la place, mais pose un
cadre, et la légende peut changer de coin. Mesuré le 07/11 :

- à Saint-Cyr IND07, la zone de la plus courte cote (0,8 mm au 1:2 000) part au
  1:200 ;
- à Auzainvilliers, au 1:1 000, la zone principale (18 cotes) part au 1:500
  dès le premier essai, et la DP 2 est refaite sans elle ; celle de la citerne
  incendie et du local technique reste sur la DP 2.

L'échelle se choisit parmi 1:200, 1:500 et 1:1 000 : la plus grande à laquelle
les ouvrages de la zone et le bout de leurs cotes tiennent sur la planche. Sur
la DP 2, le **cadre** du détail entoure les ouvrages de la zone, à 3 mm près, et
non toute la planche de détail : au 1:500, celle-ci couvrait la moitié
d'Auzainvilliers (04/11). Son renvoi, « Détail de la zone technique : DP 2 bis »,
s'écrit après la légende, hors de la clôture, des ouvrages et des cotes. La
planche est une pièce facultative de `dossier.py`, sur le modèle de DP 1-3 bis.

### D8 — Une valeur se lit avec sa ligne, même quand les cotes se serrent (03/11)

Le style a changé depuis le brief du 03/11, qui reprenait `cote_oblique` et ses
traits d'attache. La relecture a demandé de petites flèches, et signalé que
« quand il y a beaucoup d'éléments, on peut avoir des difficultés à identifier à
quelle flèche est attribuée la valeur » : posée à côté de sa ligne, une valeur
s'attribuait à la plus proche, qui n'était pas toujours la sienne. La maquette
applique donc la **méthode 2 de l'ISO 129**, la cotation unidirectionnelle :

- le texte reste horizontal, avec un halo : `Planche.ajouter_texte` n'a pas de
  rotation (vérifié le 03/11), et le moteur ne change pas (règle du dépôt) ;
- la valeur **interrompt sa propre ligne**, de préférence en son milieu : elle
  n'appartient alors qu'à la ligne qui la traverse ;
- une ligne trop courte porte sa valeur sur son prolongement, au-delà d'une
  extrémité libre — la maquette sait encore traiter une chaîne, dont seules les
  extrémités extérieures le sont, mais C1 n'en pose plus depuis le 08/11 ;
  à défaut, un renvoi la relie au milieu de sa ligne ;
- les flèches sont pleines, de 1,6 mm de long ; une ligne plus courte que deux
  flèches et 0,6 mm les porte dehors, pointes vers l'intérieur ;
- la ligne est en `TRAIT_COTE`, la valeur en `TAILLE_COTE`, de `primitives.py`.

Le placement a deux sortes de contraintes. Sont interdits : sortir du cadre,
chevaucher une autre étiquette ou le pied, couper la ligne d'une autre cote ou
la ligne de coupe, prolonger une ligne ou tirer un renvoi à travers un ouvrage.
Prolongée à travers le local mesuré, une ligne se lisait jusqu'à son autre face
(Auzainvilliers, 03/11). Sont à éviter : poser la valeur sur un ouvrage, en
travers de la clôture ou d'un cadre de détail. On retient la place qui en touche
le moins, et un renvoi compte pour une gêne de plus. Les cotes les plus courtes
se placent d'abord : elles ont le moins de choix. Faute de toute place, la
valeur est posée au mieux, et le rapport le dit.

La seconde relecture du 08/11 y ajoute trois règles, pour qu'une valeur ne
recouvre rien d'important :
- la valeur d'une cote vers la limite parcellaire (C1, et C3 vers la limite)
  se pose de préférence au-delà de la limite, hors de la centrale : toute
  autre place compte une gêne de plus ;
- un numéro de parcelle est interdit, comme une autre valeur : les numéros sont
  posés avant les cotes, et leur place se relève à ce moment ;
- les tables sont à éviter, mais une valeur posée dessus reste lisible, et ne
  fait pas partir une zone en détail (D7).

La maquette passe ses points en Lambert 93 à `Planche.ajouter_geometrie`, qui
les projette. La première cote se mesure dans le PDF avant qu'on en pose une
autre.

### D9 — Ce qui n'est pas coté se dit

La légende gagne « Cote, en mètres », et « Axe de voie (BD TOPO, IGN) » quand
C2 ou C8 en dessine un. Le pied énonce les règles, une ligne par idée (07/11 :
d'un seul tenant, la phrase dépassait 200 mm) :

- sur la DP 2 : « Cotes en mètres, mesurées en Lambert 93. Limite
  parcellaire : celle du terrain d'assiette (parcellaire IGN). Voie publique et
  habitation la plus proche selon la BD TOPO (IGN). » puis « Constructions en
  légende : longueur × largeur, h : hauteur (catalogue UNITe ; tables : hauteur
  maximale du tableau bilan). » (08/11) ;
- sur la planche qui porte des cotes d'ouvrages : « Distances entre ouvrages
  permanents voisins, et à la limite parcellaire, cotées en deçà de 30 m ;
  batteries et locaux de stockage cotés à la limite parcellaire à toute
  distance. » puis « Batteries et citernes cotées jusqu'à la table la plus
  proche ; poste de livraison coté jusqu'à l'axe de la voie publique la plus
  proche, en deçà de 30 m. »

La légende ne recouvre ni le pied, ni une cote, ni un cadre de détail. Quand
aucun coin ne la reçoit sur une colonne, elle passe sur deux, deux fois moins
haute (08/11) : sur la DP 2 d'Auzainvilliers, ses vingt entrées couvraient le
haut du cadre du détail. Faute de coin même en deux colonnes, elle va au coin le
moins dessiné, et le rapport le dit. Une absence se dit en légende (D5). Une cote qui ne trouve
pas sa place, ou qu'une règle écarte, est nommée au rapport avec sa raison. Elle
n'est jamais retirée en silence.

### D10 — Rien à saisir, rien à changer au contrat

Tout se calcule à la génération, à partir du contrat et des services IGN, comme
le parcellaire de la DP 2. C2 et C8 demandent en plus le parcellaire à 350 m
autour des constructions, au même service, pour dire quelles voies sont
publiques. Le contrat ne gagne ni couche ni colonne :
il a un lecteur hors du dépôt, le photomontage. `Projet` ne gagne aucun champ.
Les seuils et les réglages — 20 m, 30 m, 3 mm, 0,5 m, ceux des côtés, les rayons
de recherche — sont des constantes commentées.

### D11 — Une source injoignable n'arrête pas la DP 2

C'est la règle de la phase de mise au point (README, « Ce qui deviendra
bloquant »). Si la BD TOPO ne répond pas, ou si sa réponse atteint le plafond de
lecture (`ErreurPlafondWFS`, qui dérive d'`ErreurService`), la DP 2 sort sans
C2, C4 ni C8, et le rapport le dit en clair. Le parcellaire du terrain garde son
comportement actuel : sans lui, rien ne se dessine. Le parcellaire autour des
constructions, qui ne sert qu'à C2 et C8, se traite comme la BD TOPO. La BD TOPO
rejoint la liste « Ce qui deviendra bloquant ».

### D12 — Les trois dimensions, en légende (08/11)

Auzainvilliers demande un plan « coté dans les trois dimensions » : c'est
l'article R. 431-36 b) du code de l'urbanisme, et la troisième dimension est la
hauteur. Elle n'est pas cotée sur le plan, où elle chargerait des zones déjà
serrées : chaque construction la porte dans son entrée de légende, avec son
emprise.

```
Poste de livraison / transformation (12 × 3 m, h 3 m)
Bac de rétention (17,5 × 3 m, h 2,3 m)
Panneaux photovoltaïques (hauteur maximale 4 m)
```

- **Ouvrages permanents** (D2) : longueur, largeur et hauteur du catalogue,
  celles que dessinent les élévations de la DP 4. La variante d'une famille qui
  en a plusieurs (citerne incendie, local de stockage) se choisit sur la
  surface du corps. Deux variantes d'une même famille sur un plan se disent au
  rapport : la légende n'a qu'une entrée par famille.
- **Tables** : la hauteur maximale de la coupe, `point_haut_max_m` de
  `geometrie_table` — le maximum déclaré au tableau bilan, que la notice
  annonce (D6) —, et la hauteur dessinée à défaut.
- La légende n'a pas de retour à la ligne, et sa largeur est fixe
  (`LARGEUR_LEGENDE_MM`, 82 mm) : elle s'élargit à l'intitulé le plus long
  plutôt que de le laisser déborder.

### Hors périmètre, et ce qui reste ouvert (08/11)

- **Les angles de prise de vue des photographies**, que Saint-Cyr demande sur
  le plan de masse et sur le plan de situation : les chefs de projet les
  ajoutent à la main, dans la sortie PowerPoint.
- **L'accès au site**, que Saint-Cyr demande aussi : pas tranché. Le portail et
  les pistes sont dessinés ; le chemin depuis la voie publique et une mention
  « Accès » restent à décider.

---

## Ce que le lot touche

- Un module de calcul des cotes, séparé du dessin pour se tester sans PDF :
  côtés, cotes tables → limite et clôture → limite, corps des ouvrages,
  voisinage relatif, inter-rangée, largeur de piste, table la plus proche, voie
  publique et cote perpendiculaire à son axe ou à son extrémité, décalage le
  long d'une face pour ne pas superposer deux cotes, dimensions et
  hauteurs de la légende.
- `dp_socle/planches/dp2_plan_masse.py` : la pose de C1, C2, C4, C5 et C6, celle
  des zones qui restent sur la DP 2, les cadres de détail et leurs renvois, la
  légende placée hors des cotes et des cadres, ses intitulés avec dimensions et
  sa largeur ajustée (D12), le pied.
- La planche DP 2 bis (ter…) et sa pièce dans `dp_socle/dossier.py`. DP 2 bis se
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

`palette.objets_a_dessiner` non plus : séparer chaque corps de ce qui l'entoure,
pour plusieurs postes et pour les conteneurs (D3), change aussi les plans de
repérage de la DP 4 et le volet photographique. C'était un préalable, traité à
part le 08/11/2026 (« Pièges connus »).

Hors périmètre, à rouvrir si une demande les cite : la largeur des portails, la
distance aux boisements, les cotes NGF.

---

## Ce qui est mesuré

### Sarnois, le 03/11/2026

Mesuré sur `sortie/PV-Sarnois-IND10B` et son emprise
(`exemples/sarnois-2-DXF/jma_60_sarnois-geoperso-2-15_09_2026_10_53.zip`), avec
une sonde jetable restée hors du dépôt. La ligne « Ouvrages » est antérieure
aux décisions D2 et D3 du 04/11 : à remesurer. La ligne « Regroupement » a été
relue le 08/11.

| Grandeur | Sarnois IND10B |
|---|---|
| Clôture | 738 m de long, 207 × 278 m d'encombrement |
| Terrain d'assiette | parcelle ZA 0058, 3,695 ha ; le fichier d'emprise la suit à 0,01 m près |
| Clôture → limite | médiane 2,3 m, maximum 11,9 m ; moins de 1 m sur 44 % du linéaire |
| Côtés (C1) | 6. Tables → clôture : de 7,4 à 10,5 m, sauf 48,4 m sur le côté de 28 m qui longe la zone technique. Clôture → limite : de 0,4 à 13,4 m, dans l'axe de la chaîne, donc parfois en biais — d'où 13,4 m pour un écart maximal de 11,9 m |
| Ouvrages | 8 en tout, dont 3 que D2 écarte (base vie, stockage de chantier, bac d'équarrissage) ; avec eux, 7 paires à moins de 30 m, 5 à moins de 20 m et 11 à moins de 50 m |
| Emprise de la zone technique | 83 × 50 m pour les ouvrages permanents ; 162 × 308 m avec les trois autres |
| Ouvrage → limite | PDL/PTR 0,4 m, local technique 11,1 m, BESS 15,5 m |
| Regroupement (D3) | BESS : 84 objets, dont 80 sans surface ; un conteneur de 18,2 m² (6 × 3 m au catalogue), dessiné deux fois à l'identique (relu le 08/11), dans un contour de 48,3 m², à 1 m de son bord. PTR : 6 objets, dont un de 30,0 m² (10 × 3 m au catalogue) dans un contour de 82,9 m² |
| Voies (BD TOPO) | `Chemin` à 11,8 m des tables et à 3,0 m des ouvrages ; `Route à 1 chaussée` de 4 m de large, à 15,1 m des tables ; « Rue des Bouleaux » à 205 m |
| Bâtiments | au cadastre, le plus proche est à 103 m : une construction légère de 782 m². La BD TOPO donne le même bâtiment, d'usage `Agricole`. Première habitation à 166 m ; 144 bâtiments `Indifférencié` sur 347 |
| Cadre de la DP 2 | au 1:2 000, 820 × 536 m ; 307 m de marge à l'est et à l'ouest, 129 m au nord et au sud : l'habitation y tient |
| Inter-rangée | inter-table 5,0 m et pas 9,0 m dans les paramètres de structure ; 8 m dans les standards UNITe |
| Pistes | aucune à mesurer : deux linéaires de 4 m et une surface de 12 × 3 m |

### Saint-Cyr-en-Val et Auzainvilliers, les 07 et 08/11/2026

Mesuré avec `maquette_lot10_cotes_dp2.py` dans son état versé (v4, 08/11), sur
des contrats refaits par `importer_be` à partir des fichiers du bureau d'études,
comme l'application le fait, sans ligne de coupe.

| Grandeur | Saint-Cyr-en-Val IND07 | Auzainvilliers IND03 |
|---|---|---|
| Fichiers | plan du 25/09/2026, tableau bilan V7 | DXF enregistré le 01/10/2026, tableau bilan V3 enregistré le 09/10 ; calque 0 apparié en PTR (« Pièges connus ») |
| DP 2 | 1:2 000, un essai | 1:1 000, deux essais |
| Clôture → limite, sur la clôture réelle | 0,00 m tout autour, sauf un point à 1,03 m | de 0 m (côté nord, le long de la D18) à 16,5 m |
| C1, tables → limite parcellaire | 4 côtés : 15,7, 6,6, 5,7 et 6,8 m | 6 côtés : de 11,4 à 25,2 m |
| C1, clôture → limite parcellaire | aucune : la clôture est sur la limite | 3 cotes, 6,0, 6,4 et 12,8 m ; deux côtés trop courts n'en reçoivent pas |
| C2 | « 23,3 m (extrémité de la route) » : la route empierrée publique s'arrête à l'angle nord-ouest du site | « 11,6 m (axe de la D18) », perpendiculaire, depuis la citerne incendie, décalée de sa cote à la limite (11,0 m à l'angle) |
| C4 | 119 m ; deux bâtiments `Indifférencié` plus proches, le premier à 85 m | 948 m, hors cadre |
| C5 | 4,5 m au tableau, 4,51 m au plan (IND06 : 4,9 et 4,91 m) | 3,5 m |
| C6 | piste lourde existante 4,4 m ; piste légère 3,5 m | 3,5 m, piste existante et piste à créer |
| Ouvrages (D2) | 3 : PDL/PTR, local technique, citerne incendie | 10 : PDL/PTR, deux PTR, deux BESS, local technique, deux citernes, bac de rétention, zone de remise |
| C3 | 2 paires gardées sur 3 ; 3 cotes à la limite | 9 paires gardées sur 19 ; 8 cotes à la limite ; PTR des batteries ↔ bac de rétention 4,8 m |
| C7 | citerne incendie 19,5 m | citerne de refroidissement 5,7 m ; BESS sud 8,3 m ; BESS nord 28,3 m ; citerne incendie 6,5 m |
| C8 | non cotée : voie publique à 108 m ; plus près, un chemin dans la clôture (5,2 m), puis des voies posées sur des parcelles (6,3 et 7,5 m) | « 12,2 m (axe de la D18) », perpendiculaire, à part de « 4,7 m (limite parcellaire) » |
| Légende (D12) | PDL/PTR 12 × 3 m, h 3 m ; local technique 6 × 3 m, h 3 m ; citerne incendie 8,1 × 7,4 m, h 1,5 m ; tables, hauteur maximale 4 m | 9 entrées dimensionnées ; tables, hauteur maximale 3 m ; l'intitulé le plus long, celui du PDL/PTR, tient en 79 mm des 82 de la légende ; sur la DP 2, deux colonnes |
| Planche de détail | DP 2 bis au 1:200, 6 cotes | DP 2 bis au 1:500, 17 cotes ; la zone ouest (4 cotes) reste sur la DP 2 |

Attributs vérifiés sur le WFS de la Géoplateforme le 03/11/2026 :

- `BDTOPO_V3:troncon_de_route` : `nature`, `importance`, `largeur_de_chaussee`,
  `cpx_numero`, `cpx_classement_administratif`, `cpx_toponyme_route_nommee`,
  `nom_voie_ban_gauche`, `nom_voie_ban_droite`, `prive`, `acces_vehicule_leger`
  et `urbain`, parmi d'autres. `prive` vaut faux sur les deux chemins de
  Saint-Cyr qui passent sur des parcelles (07/11) : il ne suffit pas à dire
  qu'une voie est publique.
- `BDTOPO_V3:batiment` : `usage_1`, `usage_2`, `nature`, `nombre_de_logements`,
  `hauteur` et `construction_legere`. Valeurs d'`usage_1` vues à Sarnois :
  `Résidentiel`, `Indifférencié`, `Annexe`, `Agricole`, `Commercial et
  services`, `Religieux`.

## Ce qui reste à mesurer

- **Sarnois sous les règles des 04, 07 et 08/11** : les paires d'ouvrages avec
  le bac de rétention et la zone de remise (D2), les cotes C7, et C1 sur une
  clôture qui s'écarte de la limite (de 0,4 à 13,4 m le 03/11, mesure à
  refaire sur la clôture réelle).
- **La seconde cote de C1** : l'écart de 20 mm de papier avec la première, et
  les cinq endroits essayés le long du côté. À Auzainvilliers, deux côtés trop
  courts n'ont pas reçu de cote clôture → limite, alors que l'écart y atteint
  5,6 à 16,5 m.
- **C2 sur un site sans voie publique à 300 m**, et sur un site où la voie la
  plus proche n'est pas parallèle à la limite.
- **La citerne de refroidissement d'Auzainvilliers** : 5,66 m à la table la plus
  proche, au sud, quand la relecture annonçait 8,9 m, la distance à la table au
  nord-ouest. Si c'est une table précise que le SDIS regarde, la règle n'est
  pas « la plus proche ». À trancher avec le chef de projet.
- **Le BESS nord d'Auzainvilliers** reçoit sa cote C7 (28,3 m), alors que la
  relecture ne la demandait que pour le BESS sud.
- **Le critère du domaine public (C2, C8)**, la moitié du tracé hors des
  parcelles sur 50 m, et le seuil de 30 m de C8, sur d'autres sites.
- Les réglages des côtés (1,5 m, 25°, 20 m), sur Bray-Saint-Aignan IND10B,
  Chaumont-sur-Aire et Les Islettes.
- La position de la cote tables → limite. Elle se pose là où les tables sont au
  plus près du côté. Si, sur ce même côté, la distance tables → limite est plus
  courte ailleurs, de plus de 0,5 m, il faut le dire : c'est cette distance-là
  que vérifie l'instructeur.
- Une limite hors du cadre de la DP 2, comme à Boisné-La Tude, dont l'emprise
  fait plusieurs fois le projet (docstring de `_ce_que_la_planche_cadre`). La
  maquette arrête la cote au bord du cadre et le dit, mais seule l'habitation
  l'a éprouvé.
- Les pistes de La Bruère-sur-Loir (deux pistes et une aire de retournement de
  189 m², relevé du 15/10/2026) et de Chaumont-sur-Aire (voirie lourde et voirie
  légère).
- **La légende sur deux colonnes**, éprouvée sur la seule DP 2 d'Auzainvilliers
  (08/11) : elle y libère le cadre du détail. À voir sur un site où même deux
  colonnes ne trouvent pas de coin.
- **L'angle nord-ouest de la DP 2 d'Auzainvilliers**, où se serrent sept cotes
  sur 40 m : citerne incendie, local de stockage, voie publique, tables et
  clôture. Il se lit sur l'épreuve, mais c'est la zone la plus chargée des deux
  sites.
- La lisibilité sur l'épreuve A3, face à la trame des tables et aux numéros de
  parcelle.

## Ordre de construction

Une étape par commit, et la CI Linux lue après chaque poussée :

0. Les préalables, hors de ce lot, tous deux faits : `_interroger_wfs` lève
   `ErreurPlafondWFS` au lieu de tronquer (03/11/2026, `8d9adca`) ; `palette`
   sépare chaque corps de ce qui l'entoure, et l'import dit ce que porte un
   calque écarté (08/11/2026, de `e633464` à `3807122`).
1. Le module de calcul et ses tests, sur des cas construits et sur les mesures
   ci-dessus.
2. C1, C5 et C6 sur la DP 2 : contrat et parcellaire seulement, sans BD TOPO.
   La première cote se mesure dans le PDF avant qu'on en pose une autre (D8).
3. C2, C4 et C8, avec la BD TOPO, et le comportement de D11.
4. C3, C7 et les planches de détail : zones, essais, cadres, renvois.
5. La légende (D12) et le pied, le `README.md`, puis l'épreuve A3 sur Sarnois,
   Saint-Cyr IND07 et Auzainvilliers IND03.

## Comment le tester

Sur le modèle de `tests/test_echelle_pdf.py` et de ses outils
(`tests/mesure_pdf.py`), chaque famille se vérifie **dans le PDF produit**. On
retrouve le trait de cote dans le flux de contenu. Sa longueur papier, ramenée à
l'échelle, doit égaler la distance Lambert 93 à 0,5 % près, et son texte doit
être `nombre_fr` de cette distance, avec son libellé. Un test vérifie que
l'inter-rangée de la DP 2 et celui de la coupe sont le même nombre, sur le même
contrat.

Le module de calcul se teste sur des cas construits :
- une clôture en retrait de la limite, et une clôture posée dessus mais tracée
  en arrondis, qu'une simplification à 1,5 m écarte de la limite : sa cote
  clôture → limite doit valoir zéro et ne pas se poser ;
- un côté trop court pour deux cotes ;
- trois conteneurs alignés ;
- un hangar plus proche qu'une maison ;
- un BESS dont la table la plus proche est derrière un autre ouvrage ;
- un poste de livraison près d'un chemin dans la clôture, d'un chemin sur une
  parcelle et d'une route hors parcelles ;
- une voie parallèle à la limite, dont l'axe se dit dans la cote à la limite ;
- une zone qui part en détail par sa cote de 2 mm, et une autre par sa valeur
  posée sur un ouvrage ;
- une famille à variantes dans la légende.

La BD TOPO est simulée dans la suite courante, et interrogée pour de vrai dans
la suite réseau.

## Pièges connus

- **Un poste par catégorie** — corrigé le 08/11/2026. `palette.emprise_de_poste`
  gardait le plus grand des objets aux cotes du catalogue, et dessinait les
  autres en plateforme sous le nom de « terre remise ». Avec deux PTR, le
  principal et celui des batteries, l'un des deux passait en gris : mesuré le
  07/11 à Auzainvilliers, en appariant à la main le calque 0 au PTR. Les
  conteneurs n'étaient pas séparés de leur aplat (D3). `separer_les_corps`
  reconnaît maintenant chaque corps, pour toutes les planches qui lisent
  `objets_a_dessiner`. Le contrôle de surface déclarée accepte depuis les deux
  lectures du tableau, le poste seul (Auzainvilliers) ou le poste et ses abords
  (Saint-Cyr), et compare le nombre de postes : à Auzainvilliers, il dit deux
  PTR au plan pour un au tableau, en rappelant que le catalogue range celui des
  batteries dans la section BESS.
- **Un ouvrage dessiné sur le calque 0.** À Auzainvilliers, le corps du PTR des
  batteries, 10,00 × 3,00 m, est la seule entité du calque 0, que l'import écarte
  d'office ; le calque `UNI_BESS_PTR` est vide. Depuis le 08/11/2026, le message
  d'import dit ce que porte un calque écarté et l'ouvrage du catalogue qu'il
  rappelle, et l'écran de correspondance permet d'apparier le calque 0 au PTR.
  Un calque écarté qui porte un rectangle aux cotes d'un ouvrage sort du groupe
  replié, sous forme de question. Sur les DXF complets de Sarnois, la vignette de
  légende de l'aire d'aspiration en sort aussi : c'est un faux ami connu.
- **Le côté simplifié n'est pas la clôture.** Simplifiée à 1,5 m pour être
  découpée en côtés, la clôture s'écarte d'autant de son tracé, et plus encore
  dans les courbes. La maquette du 07/11 mesurait depuis le côté simplifié, et
  annonçait à Saint-Cyr des écarts clôture → limite de 0,9 et 1,0 m, quand la
  clôture réelle est sur la limite (0,00 m, relevé le 08/11). Le côté donne une
  direction ; les distances se prennent sur la clôture réelle.
- **La BD TOPO coupe les routes à chaque carrefour.** Le bout d'un tronçon n'est
  pas le bout de la route : les tronçons publics se fondent en un réseau avant
  toute mesure perpendiculaire (C2, C8). Une voie publique qui s'arrête vraiment
  avant le site — Saint-Cyr — n'a pas de perpendiculaire, et la cote le dit.
- **La BD TOPO porte aussi les chemins du site.** Un chemin dans la clôture est
  un `troncon_de_route` comme un autre : à Saint-Cyr, c'est la « voie » la plus
  proche du PDL/PTR, à 5,2 m et à 89 % dans la clôture (C8).
- **Relire sur l'indice déposé.** Une maquette relue sur un autre indice que
  celui du dossier fait accuser l'outil : Saint-Cyr, IND06 contre IND07 (D6).
- **Les métriques de texte diffèrent entre Windows et Linux** (26/09/2026). La
  place d'une étiquette se mesure avec `chasse_cairo` de `polices.py`, comme
  partout ailleurs, et c'est la CI Linux qui tranche.
- **Les références HOCH ne sont pas versionnées.** `exemples/_hoch-references/`
  n'existe que sur le poste.
- **Un site ne suffit pas.** Sarnois n'a pas de piste à mesurer, et ses ouvrages
  sont tous dans un même coin. Saint-Cyr et Auzainvilliers ont servi de deuxième
  et troisième sites ; un quatrième, avec une zone technique éclatée, dirait si
  D7 tient avec plusieurs planches de détail.
