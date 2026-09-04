# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 4 : DP 2, DP 3 et DP 4

> Lots 1, 2 et 2bis livrés. Ce lot dessine les planches à partir du contrat commun, sans jamais savoir de quel lot vient le dossier. Lire `README.md` et `CLAUDE.md` avant de commencer : ce brief ne les répète pas.

---

## Objectif

Quatre planches A3 paysage, et le module `dp_socle/planches/` correspondant :

| Pièce | Contenu | Échelle |
|---|---|---|
| DP 2 | Plan de masse | adaptative |
| DP 3 | Coupe des tables + coupe du terrain | deux échelles adaptatives |
| DP 4-1 | Postes : plan, élévations, coupe + plan de repérage | adaptative |
| DP 4-2 | Clôture, portail, citerne + plan de repérage | adaptative |

Plus une DP 4-3 si le projet porte des ouvrages qui ne tiennent pas sur les deux premières.

`dp_socle/dossier.py` déclare déjà ces pièces comme non produites : les basculer, et vérifier que le sommaire paginé et le contrôle de rang de `assemblage.py` suivent.

---

## Entrées

Le contrat décrit dans `CONTRAT_LOT4.md` : `sortie/{projet}/geometries.gpkg` et `sortie/{projet}/projet.json`, `version_contrat` = 2. **Refuser une version de contrat supérieure** plutôt que de la lire à moitié.

S'y ajoutent, via `dp_socle/ign.py` déjà livré : le parcellaire et les bâtiments du WFS Parcellaire Express, les fonds WMS-R. Jamais le cadastre embarqué par le BE.

---

## Décisions prises en amont

Ces six points ont été arbitrés avant rédaction. Ils ne sont pas à rediscuter ni à « améliorer ».

### D1 — Le point bas : deux sources, deux usages

Le tableau bilan et le Z du DXF ne concordent pas, et l'écart n'est pas constant : 2,50 m déclaré contre 1,70 m mesuré à Saint-Cyr, 1,50 contre 1,29 à Sarnois. Ce n'est pas une erreur, les deux ne mesurent pas la même chose. Les valeurs déclarées sont des **engagements d'enveloppe** — le PDF de profil du BE écrit « 2.5m min » et « 4m max », des bornes sur tout le site. Le Z décrit une table particulière dans une représentation simplifiée.

| Dessin | Source | Pourquoi |
|---|---|---|
| Coupe des tables (grande échelle) | `parametres.structures.point_bas_m` et `point_haut_m` | c'est un dessin de type, et il doit coïncider avec ce qu'annoncera la notice DP 11 — une planche qui contredit sa propre notice est une faiblesse à l'instruction |
| Coupe du terrain (petite échelle) | `z_min` / `z_max` de la couche `tables_pv` | c'est une coupe de site : les tables sont posées sur le terrain réel, et 0,80 m y représente moins de 3 mm sur la feuille |

**Quand `z_reel` vaut faux** — c'est le cas de tout dossier d'origine `helioscope`, dont le DXF est plat — poser les tables sur le profil RGE ALTI en appliquant les hauteurs déclarées, et **écrire cette substitution dans le rapport de génération**. Ce n'est pas un repli silencieux : c'est le seul comportement possible, mais il doit se voir.

### D2 — Échelles adaptatives, et aucune exagération verticale

Aucune échelle n'est figée. HOCH dessine ses coupes au 1/50 et son plan de masse au 1/1000 ; le BE dessine au 1/80. Ni l'un ni l'autre par principe : c'est une contrainte d'encombrement, et nos projets ne ressemblent pas aux leurs. Le pas inter-rangées de Saint-Cyr est de 9,5 m contre 3 m aux Islettes — deux tables au 1/50 y occuperaient 380 mm, toute la largeur utile, sans place pour les cotes. De même, la coupe de Saint-Cyr fait 355 m : au 1/300 elle mesurerait 1,18 m.

Pour chaque dessin, retenir dans une liste normalisée la **plus grande échelle** qui fasse tenir le contenu utile plus ses cotes, et l'inscrire au cartouche :

| Dessin | Liste | Contenu à faire tenir |
|---|---|---|
| Plan de masse | 1/500, 1/1000, 1/2000, 1/2500, 1/5000 | l'emprise cadastrale plus 10 % de marge |
| Coupe des tables | 1/50, 1/80, 1/100, 1/200 | deux rangées complètes et leurs lignes de cote |
| Coupe du terrain | 1/200, 1/250, 1/300, 1/500, 1/750, 1/1000 | `ligne_coupe.longueur_m` |
| Ouvrages DP 4 | 1/50, 1/100, 1/200 | le plus grand ouvrage de la planche |
| Plan de repérage DP 4 | 1/200, 1/300, 1/500, 1/1000 | l'emprise clôturée |

⚠️ **Aucune exagération verticale sur les planches.** Le README en décrit une sur l'aperçu de contrôle du lot 2bis, avec raison : 0,96 m de dénivelée sur 355 m y serait invisible. Sur une planche qui déclare une échelle au cartouche, elle est interdite — une coupe dont les deux axes n'ont pas le même rapport n'est plus à l'échelle annoncée. Si le terrain est plat, la coupe est plate, et c'est ce qu'elle doit dire. Ne pas reprendre le code de l'aperçu par mimétisme.

### D3 — La légende se construit depuis ce qui a été dessiné

Le contrat porte 35 catégories, la légende de la planche HOCH en compte 10. L'écart ne se tranche pas une fois pour toutes : il se résout à chaque projet.

Règle : **une catégorie sans objet dessiné ne figure pas à la légende.** Elle est construite après le dessin, à partir des catégories effectivement tracées, dans l'ordre du rang de dessin du contrat.

Deux catégories partageant le même intitulé — `piste_lourde` et `aire_grutage`, toutes deux « Voie lourde » — ne produisent **qu'une entrée**. Dédoublonner sur l'intitulé, pas sur la catégorie.

Trois catégories sont exclues d'office, même dessinées :

| Exclue | Raison |
|---|---|
| `base_vie`, `stockage_chantier` | installations de chantier, temporaires — le dossier de référence n'en montre aucune |
| `zone_implantation_pv`, `recul_implantation` | contours d'étude ; seule la clôture délimite le projet au dossier |

Elles ne sont pas dessinées non plus.

Deux entrées viennent d'ailleurs que du contrat et doivent y figurer, comme chez HOCH : **« Limite de parcelle »** et **« Bâtiment »**, tirées du WFS IGN.

### D4 — Palette : les relevées font foi, les dérivées se justifient

Les 11 teintes marquées « relevée HOCH » au contrat sont relevées au pixel sur la planche DP 2 du dossier de référence. **Elles sont reprises telles quelles.** Ne pas les rejouer sur une autre inspiration : c'est le document que l'instructeur a l'habitude de voir.

Les 24 dérivées sont à valider, pas à recopier — la palette du contrat est celle d'une image de contrôle à l'écran. Critère : **deux catégories susceptibles d'apparaître sur la même planche doivent rester distinguables à la taille d'impression réelle**, sur une épreuve papier A3, pas sur un écran zoomé. Un poste de 12 × 3 m au 1/1000 fait 12 × 3 mm.

Là où UNITe a déjà une convention lisible sur ses annexes de demande d'examen au cas par cas — BESS, bac de rétention, local technique — s'en approcher si ça ne heurte aucune relevée. Le PDL en rouge, par exemple, est à écarter : la clôture est rouge chez HOCH et la collision serait pire que l'écart de convention.

### D5 — `voirie` bloque, elle ne se devine pas

La catégorie `voirie` existe parce qu'un calque du BE ne disait pas si la piste était lourde ou légère, alors que le tableau bilan sépare les deux et que la légende du dossier les distingue.

Si la couche `voirie` est peuplée, **refuser de dessiner** tant que le chef de projet n'a pas tranché, par un bouton radio sans valeur par défaut. Ne pas la rattacher à l'une ou l'autre, ne pas lui inventer une troisième teinte, ne pas la dessiner « en attendant ».

### D6 — `make_valid` avant toute union

Un polygone auto-intersectant existe dans les fichiers réels : le calque « ESPACE VERT » de Sarnois faisait échouer `unary_union` au lot 2bis. Appliquer `make_valid()` systématiquement avant toute union ou intersection, pas seulement là où ça a déjà planté.

---

## DP 2 — Plan de masse

Référence : `HOCH_DP2_plan_de_masse.png` et `HOCH_DP2_legende.png`.

**Cadrage** sur l'emprise cadastrale plus 10 % de marge, et non sur la clôture : le plan doit montrer le contexte parcellaire alentour, comme celui de HOCH.

**Contenu**, dans l'ordre de dessin du contrat :

1. Parcellaire du WFS IGN en filet fin noir, avec les **numéros de parcelle** — la mécanique d'étiquetage de DP 1-3 est déjà écrite, la réutiliser
2. Bâtiments en hachures à 45°, comme sur DP 1-3
3. Les catégories du GeoPackage, hors exclusions de D3
4. La ligne de coupe, en trait d'axe, avec ses repères **A** et **A'** aux extrémités : lettre et triangle plein orienté vers la coupe, comme chez HOCH
5. Le bloc de légende, construit selon D3

**Pas de fond raster.** Le plan de masse de référence est sur fond blanc ; une ortho écraserait la lecture des ouvrages.

---

## DP 3 — Coupes

Une seule planche portant deux dessins superposés, chacun avec sa mention d'échelle propre à droite — le cartouche ne peut en annoncer qu'une, il porte celle de la coupe des tables et la coupe du terrain porte la sienne en clair.

### Moitié haute — coupe des tables

Dessin paramétrique, aucune géométrie lue du GeoPackage. Trois rangées consécutives vues en profil, sur un sol hachuré.

Paramètres, tous depuis `projet.json` :

- `structures.inclinaison_deg`
- `structures.point_bas_m`, `point_haut_m` (voir D1)
- `structures.distance_inter_table` et le pas
- `modules.format_module` pour la longueur de rampant

Cotes à porter, comme sur le PDF de profil du BE : hauteur point haut, hauteur point bas, inter-table, pas, angle d'inclinaison. Plus une **silhouette humaine** à l'échelle, comme sur le dossier de référence et sur le profil du BE — c'est ce qui donne l'échelle à l'instructeur.

### Moitié basse — coupe du terrain

- Profil du terrain naturel depuis `profil_terrain.points`, en trait plein, sol hachuré en dessous
- Tables posées dessus, à leur abscisse réelle le long de la coupe, avec leur hauteur selon D1
- Ouvrages traversés par la coupe s'il y en a
- **Limites de parcelles traversées**, en trait vertical avec la mention « Limite de parcelle », et le **numéro de chaque parcelle** entre deux limites — c'est ce que fait HOCH avec ses AD 211 / AD 212 / AD 213. Croiser `ligne_coupe` avec le parcellaire du WFS
- Les repères **A** et **A'** aux extrémités

---

## DP 4 — Ouvrages techniques

Référence : les planches 7 et 8 du dossier HOCH.

### Composition commune

Chaque planche DP 4 est partagée en deux : un **plan de repérage** à gauche, les **dessins d'ouvrages** à droite.

Le plan de repérage montre l'emprise clôturée avec ses ouvrages, à échelle adaptative, et porte sa propre mention d'échelle.

⚠️ HOCH y annote les objets par des **lignes de rappel** vers des libellés placés autour du dessin. **Ne pas reproduire ce procédé** : le placement automatique de libellés sans chevauchement est un problème de mise en page non résolu, et un libellé mal posé sur une planche déposée coûte plus cher que le confort qu'il apporte. Utiliser le bloc de légende standard (`Planche.ajouter_legende`), qui porte exactement la même information sans risque.

### Répartition

| Planche | Ouvrages |
|---|---|
| DP 4-1 | Postes : `pdl_ptr`, `ptr`, `pdl` — un bloc par type présent |
| DP 4-2 | `cloture`, `portail`, `bache_incendie` |
| DP 4-3, si nécessaire | `bess`, `local_technique`, `bac_retention`, `citerne_refroidissement`, `aire_aspiration` |

**Un ouvrage absent du projet n'a pas de bloc**, et la planche se recompose sur ce qui reste. Si DP 4-2 n'a que la clôture et le portail, les deux blocs occupent la place.

### Dessins par ouvrage

Pour un poste, en reprenant la présentation du dossier de référence : **plan de toiture**, **quatre élévations** (deux longs pans, deux pignons), et une **coupe** avec silhouette humaine.

Pour la clôture : une élévation cotée, avec le grillage figuré et les annotations de type — dont le **passage à petite faune**, qui est un élément standard et attendu à l'instruction.

Pour le portail : une coupe et une élévation, largeur depuis `parametres.generalites`.

Pour la citerne : vue de dessus et vue de face, plus un **bloc de caractéristiques en texte** (volume, hauteur hors sol, longueur, largeur), comme chez HOCH.

### Les cotes viennent de `cotes_normalisees`

⚠️ **`ordre_cotes` change d'un ouvrage à l'autre** : « largeur x longueur x hauteur » pour le PTR, « longueur x largeur x hauteur » pour le PDL/PTR. Il est porté avec chaque cote dans `projet.json`. **Le lire, jamais le supposer** — inverser longueur et largeur donne un poste de 3 × 12 m au lieu de 12 × 3, ce qui se dessine parfaitement et se voit mal.

Si un ouvrage dessiné n'a pas de cote normalisée, échouer explicitement plutôt que de le dimensionner d'après sa géométrie du plan : le GeoPackage donne son emprise au sol, jamais sa hauteur.

---

## Primitives partagées

Plusieurs éléments reviennent sur trois planches. Les écrire une fois, dans un module dédié, et non les recopier :

- **Silhouette humaine** à l'échelle (coupe des tables, coupe de poste, élévation de portail)
- **Ligne de cote** avec extrémités, cote centrée et report hors dessin quand la place manque
- **Hachure de sol** sous une élévation ou une coupe
- **Repère de coupe** A / A' : lettre et triangle plein
- **Mention d'échelle** en clair pour les dessins qui ne sont pas celui du cartouche

Ces primitives se composent avec l'API `Planche` existante. **Ne pas modifier `dp_socle/planche.py`.** Si une primitive semble manquer au moteur, elle se construit par-dessus — et si elle ne le peut vraiment pas, le signaler plutôt que de toucher au lot 1.

Attention au repère : `ajouter_geometrie`, `ajouter_fond_raster` et `ajouter_etiquettes` travaillent en Lambert 93 ; `ajouter_texte`, `ajouter_rectangle`, `ajouter_ligne`, `ajouter_image_mm` et `ajouter_legende` travaillent en millimètres papier. Les coupes et les dessins d'ouvrages **ne sont pas cartographiques** : ils se composent en millimètres, avec leur propre facteur d'échelle local. Ne pas détourner la transformation L93 pour les dessiner.

---

## Règles de travail

Celles de `CLAUDE.md` s'appliquent intégralement. Trois s'appliquent avec une acuité particulière ici :

**Aucun repli silencieux.** Sur ce lot, l'erreur produit une planche parfaitement présentable et fausse. Une cote inversée, une échelle non respectée, une catégorie oubliée : rien ne se voit. Toute valeur manquante, toute substitution, tout ouvrage non dessiné faute de données doit lever ou apparaître au rapport de génération.

**Tester le résultat, pas l'exécution.** `tests/test_echelle_pdf.py` mesure un segment dans le flux de contenu du PDF produit. Les coupes ont leur propre échelle locale, distincte de celle du cartouche : elles demandent le même traitement, mesurées sur le PDF.

**Un problème à la fois.** Ne pas toucher au moteur `Planche`, ni à `import_be.py`, ni à `helioscope.py`. Si le contrat manque de quelque chose, le dire — l'ajouter des deux côtés à la fois est une décision, pas un correctif, et `test_les_deux_lots_ecrivent_le_meme_schema` est là pour l'empêcher de se faire à moitié.

---

## Critères de validation

Trois jeux réels dans `exemples/` : Saint-Cyr (9 calques, propre), Sarnois A et B (exports triés, deux variantes d'un même indice). Plus un dossier d'origine `helioscope` pour vérifier que le lot 4 ne suppose rien de la provenance.

1. **Échelle vraie**, mesurée dans le PDF produit, sur chacune des échelles déclarées : celle du cartouche et celles portées en clair sur les coupes. Écart admis 0,5 %.
2. **Isotropie des coupes** : sur la coupe du terrain, un mètre vertical et un mètre horizontal mesurent la même longueur dans le PDF.
3. **Saint-Cyr** produit ses quatre planches sans avertissement.
4. **Sarnois A et B** produisent des planches dont les légendes diffèrent, chacune ne portant que les catégories réellement dessinées.
5. Un dossier **`helioscope`** produit DP 2 et DP 3, avec au rapport la mention de la substitution du D1.
6. Une couche `voirie` peuplée **bloque** la génération.
7. Les cotes de poste tirées de `cotes_normalisees` sont conformes à `ordre_cotes` — un test qui inverse volontairement l'ordre doit faire échouer la comparaison.
8. Le dossier complet reste **sous 25 Mo**.
9. La numérotation et le sommaire de `assemblage.py` restent cohérents après bascule des pièces DP 2, DP 3 et DP 4 en « produites ».

---

## Hors périmètre

- La notice DP 11 (lot 5)
- Les insertions paysagères DP 6 / 7 / 8, fournies en PDF et simplement assemblées
- Toute modification du contrat, du moteur `Planche`, ou des lots 2 et 2bis
