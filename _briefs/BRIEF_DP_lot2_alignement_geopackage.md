# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 2 : alignement sur le contrat GeoPackage du lot 2bis

> À traiter **dans la conversation dédiée au lot 2**. Le lot 2bis est livré, éprouvé sur le jeu Saint-Cyr-en-Val, et c'est lui qui définit désormais le contrat d'entrée du lot 4. Ce brief ne rouvre ni le calage géographique ni la lecture du DXF HelioScope : ils fonctionnent et ne doivent pas être touchés.

---

## Contexte

`CLAUDE.md` dit que le lot 2 « devra produire le même GeoPackage que le lot 2bis ». Ce n'est pas le cas aujourd'hui : le lot 2 écrit cinq GeoJSON dans `sortie/{projet}/helioscope/`, quand le lot 2bis écrit un GeoPackage et un `projet.json` versionné dans `sortie/{projet}/`.

Tant que le lot 4 n'existe pas, la divergence ne coûte rien. Le jour où il existera, il devra soit lire deux formats, soit refuser les projets sans plan BE. Aligner maintenant est moins cher que plus tard, et c'est surtout maintenant que la mémoire du lot 2bis est fraîche dans le dépôt.

Le lot 2 reste en réserve : il sert aux projets pour lesquels le BE interne ne fournit pas de plan final.

---

## Objectif

Faire du lot 2 un producteur du **même contrat de sortie** que le lot 2bis, en disant explicitement ce qu'il ne peut pas fournir plutôt qu'en le laissant vide.

Le lot 4 doit pouvoir lire une sortie sans savoir de quel lot elle vient — sauf là où la différence est réelle, et alors elle doit être lisible dans les données.

---

## Ce que produit chaque lot aujourd'hui

Relevé le 03/09/2026 sur le code en place.

| | Lot 2 (HelioScope) | Lot 2bis (plan BE) |
|---|---|---|
| Format | 5 fichiers GeoJSON | 1 GeoPackage |
| Emplacement | `sortie/{projet}/helioscope/` | `sortie/{projet}/` |
| CRS | EPSG:2154, déclaré en membre `crs` non standard | EPSG:2154, porté par le format |
| Couches | `tables`, `modules`, `zone_implantation`, `reculs`, `zones_evitees` | une par catégorie de `CATEGORIES` + `ligne_coupe` |
| Attributs | `id` seul | `calque`, `categorie`, `z_reel`, `z_min`, `z_max` |
| Z | aucun (DXF HelioScope plat) | conservé là où le DXF en porte |
| Paramètres | `parametres_json()` écrit dans le `projet.json` **du lot 1** | `projet.json` propre dans `sortie/`, avec `version_contrat` et `origine` |
| Ligne de coupe | absente | présente, corrigée, avec profil du terrain |

---

## Le piège principal — mesuré, à ne pas contourner

**Une « table » du lot 2 et une table du lot 2bis ne désignent pas la même chose**, et leur géométrie est orientée à 90° l'une de l'autre.

Mesuré sur le design 7676351 (Les Islettes) et sur `20260903_SCV_IND06.dxf` :

| | dimensions | grand côté |
|---|---|---|
| « table » HelioScope brute | 1,30 × 6,48 m | **en travers** de la rangée (colonne de 3 modules portrait) |
| rangée HelioScope regroupée | 6,48 × 48,22 m | le long de la rangée |
| table du plan BE | 4,62 × 14,98 m | le long de la rangée |

Conséquence directe sur `azimut_tables()` du lot 2bis, appliqué tel quel :

| entrée | azimut rendu |
|---|---|
| couche `tables` brute du lot 2 | **−88,105°** |
| rangées regroupées par `unary_union` | **+1,895°** |
| `calepinage.orientation_deg` | −179,556°, soit **+0,444°** dans ]−90, 90] |

Autrement dit : **brancher la ligne de coupe du lot 2bis sur la couche `tables` du lot 2 donnerait une coupe parallèle aux rangées au lieu de perpendiculaire.** Elle se dessinerait sans anomalie visible et serait fausse — exactement le mode d'échec que le dépôt refuse.

`calepinage.orientation_deg` n'est pas non plus utilisable en l'état : il s'écarte de 1,45° de la direction mesurée sur les rangées, et sa convention n'est écrite nulle part.

**Travail attendu** : établir par la mesure ce que `orientation_deg` décrit, le noter en commentaire avec sa date de vérification, et décider laquelle des trois valeurs oriente la coupe. Si c'est le regroupement en rangées, il existe déjà — `apercu_calage` s'en sert pour cerner les rangées — et il faut le sortir dans une fonction nommée plutôt que le refaire.

---

## Travail attendu

### 1. Correspondance des couches

Le lot 2bis nomme ses couches d'après un contrat, `CATEGORIES` dans `dp_socle/import_be.py`. Décider, et documenter, à quoi correspond chaque couche du lot 2 :

- `tables` → `tables_pv` semble évident et ne l'est pas, vu le piège ci-dessus. Trancher entre la couche brute et les rangées regroupées, en disant pourquoi.
- `modules` n'a **pas d'équivalent** dans le contrat 2bis : le plan du BE ne donne que les contours de table. Le README du lot 2 dit pourtant que « la couche `modules` est celle que dessine un plan de masse lisible ». Deux options, à trancher explicitement plutôt qu'à subir : ajouter une catégorie `modules_pv` au contrat commun, ou l'écarter et accepter que les deux lots ne dessinent pas au même niveau de détail.
- `zone_implantation`, `reculs`, `zones_evitees` n'ont pas d'équivalent non plus. Le README du lot 2 est net : la zone HelioScope « est tracée à la main et ne suit pas le parcellaire ». **Ne surtout pas l'apparier à `cloture`** — la surface clôturée et le linéaire de clôture du dossier en dépendraient, et seraient faux.

Toute catégorie ajoutée au contrat doit l'être dans `CATEGORIES`, avec son style dans `dp_socle/apercu_be.py` et sa place dans `ORDRE_DESSIN`.

### 2. Écriture du GeoPackage

Réutiliser `import_be.ecrire_geopackage` plutôt que d'en écrire un second. Il prend un `PlanBE` ; il faudra soit l'assouplir pour accepter une liste d'`EntiteBE`, soit construire un `PlanBE` depuis une implantation HelioScope. La première voie est probablement plus honnête : un `PlanBE` porte `unite`, `facteur_unite`, `calques_ignores`, qui ne veulent rien dire pour HelioScope.

Les attributs `z_reel`, `z_min`, `z_max` restent dans le schéma, à `False` et `None` : le DXF HelioScope est plat, vérifié sur les deux exports des Islettes. Ne pas les supprimer — un schéma qui change selon la provenance oblige le lot 4 à savoir d'où vient le fichier.

### 3. `projet.json` de sortie

Écrire le même fichier que le lot 2bis, dans `sortie/{projet}/`, avec :

- `version_contrat` égal à `VERSION_CONTRAT` ;
- `origine` valant `"helioscope"` et non `"import_be"` ;
- les paramètres du calepinage et du calage, là où le lot 2bis met ceux du tableau bilan.

**`import_be.lire_parametres()` refuse aujourd'hui toute origine autre que `"import_be"`.** C'est délibéré — le `projet.json` du lot 1 porte le même nom dans `projets/` — mais il faudra l'ouvrir aux deux origines connues, et continuer à refuser les autres.

Le `projet.json` du lot 1, dans `projets/{projet}/`, garde son rôle actuel : métadonnées du dossier, chemin de l'export, longitude de calage. Ne pas y toucher.

### 4. Ce que le lot 2 ne peut pas fournir

À dire dans les données et à l'écran, pas à laisser vide.

- **Aucun tableau bilan.** Les contrôles croisés de l'étape C du lot 2bis tombent tous, sauf le débordement hors de l'emprise cadastrale. C'est la vraie perte de cet alignement : le lot 2bis tirait sa valeur d'avoir deux sources qui se contredisent, le lot 2 n'en a qu'une. Le dire franchement dans le `projet.json` et à l'écran ; ne pas fabriquer des contrôles qui comparent une valeur à elle-même.
- **Aucune altitude.** `controler_coherence` a besoin du Z des tables et ne peut pas tourner. Le profil du terrain reste disponible par le RGE ALTI, mais sans recoupement possible. Le signaler explicitement.
- **Aucune clôture.** Voir plus haut. La ligne de coupe du lot 2bis s'étend à l'emprise clôturée : décider sur quoi elle s'étend ici — l'emprise cadastrale du lot 1 est le candidat le plus défendable, la zone HelioScope ne l'est pas.

### 5. Ligne de coupe

Rendre la coupe A-A' disponible pour les projets du lot 2, avec la même mécanique : tracé sur carte, correction de perpendicularité, profil RGE ALTI, reprise d'un import précédent.

Tout est déjà dans `dp_socle/coupe.py` et paramétrable — `corriger_ligne_coupe` prend un azimut et une emprise, sans rien supposer de leur provenance. L'essentiel du travail est de leur passer les bonnes valeurs, ce qui renvoie au piège d'orientation ci-dessus.

---

## Règles de travail

Les règles de `CLAUDE.md` s'appliquent, en particulier :

- **Aucun repli silencieux.** Une couche vide, un attribut à `None`, un contrôle impossible : chacun se signale.
- **Vérifier plutôt que supposer.** Ce brief contient déjà une affirmation fausse en puissance : que `tables` du lot 2 correspond à `tables_pv`. Elle a été mesurée et infirmée. Traiter le reste avec la même méfiance.
- **Ne pas toucher au calage géographique ni à la lecture du DXF HelioScope.** Ils sont livrés et éprouvés. Ce lot ne change que la sortie.
- **Ne pas toucher au lot 2bis** au-delà de ce que l'ouverture du contrat impose : `CATEGORIES`, `lire_parametres`, et l'assouplissement de `ecrire_geopackage`. Toute modification de `import_be.py` doit laisser les 173 tests actuels au vert.
- Commit après chaque étape validée, message en français.

---

## Critères de validation

1. Un export HelioScope des Islettes produit `sortie/{projet}/geometries.gpkg` et `sortie/{projet}/projet.json`.
2. Le GeoPackage se relit en EPSG:2154, avec les mêmes noms de colonnes que celui du lot 2bis.
3. `import_be.lire_parametres()` lit le `projet.json` du lot 2 sans erreur, et refuse toujours celui du lot 1.
4. Un test compare le **schéma** des deux sorties — noms de couches connus, colonnes, CRS — et échoue si l'une diverge. C'est ce test qui empêchera les deux formats de repartir chacun de leur côté.
5. La ligne de coupe d'un projet HelioScope ressort **perpendiculaire aux rangées**, vérifié sur la géométrie et non sur une valeur déclarée. Sur Les Islettes, les rangées mesurent +1,895° : la coupe doit sortir à +91,895°, à moins d'un degré près.
6. Les contrôles impossibles faute de tableau bilan apparaissent à l'écran comme impossibles, et non comme réussis.
7. Les 173 tests existants restent au vert.

---

## Hors périmètre — ne pas commencer

- Le dessin des planches, qui reste le lot 4.
- Toute reprise du calage géographique, du pré-positionnement ou de la lecture du DXF HelioScope.
- La migration des sorties déjà écrites : elles se régénèrent.
