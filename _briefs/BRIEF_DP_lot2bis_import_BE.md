# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 2bis : import du plan BE interne

> À traiter après le lot 1 (socle), déjà livré. Ce lot **remplace les lots 2 et 3** (import HelioScope et saisie manuelle des éléments techniques), qui restent en réserve pour plus tard. Le lot 4 (dessin des planches DP 2 / 3 / 4) est inchangé et vient après celui-ci.

---

## Contexte

Pour les premiers dossiers, le bureau d'études interne d'UNITe fournit le plan final de chaque projet, déjà géoréférencé en Lambert 93, accompagné d'un tableau bilan Excel. Il n'y a donc ni calage géographique à faire, ni élément technique à saisir : tout est dans les fichiers.

Le travail consiste à **lire ces fichiers, les normaliser, et vérifier leur cohérence** avant de les transmettre à l'étape de dessin.

Ce lot ne produit aucune planche.

---

## Objectif

Un module `dp_socle/import_be.py` et les écrans Streamlit associés, qui transforment les entrées du BE en un jeu de données normalisé et validé, prêt pour le lot 4.

---

## Entrées

| Fichier | Statut | Contenu |
|---|---|---|
| DXF du plan BE | obligatoire | géométries en L93 |
| Tableau bilan `.xlsx` | obligatoire | paramètres techniques |
| Shapefile d'emprise cadastrale | obligatoire | déjà géré par le lot 1 |
| PDF du plan BE | optionnel | référence visuelle de contrôle |
| PDF de vue de profil | non fourni | **ne pas prévoir d'entrée pour ce fichier** (voir note) |

> **Note sur la vue de profil.** Le BE produit parfois un PDF de vue de profil des structures, mais pas systématiquement, et il n'apporte aucune donnée : ses quatre cotes (inclinaison, point bas, point haut, inter-table) figurent déjà dans le tableau bilan. La coupe DP 3 au 1/50 sera générée en paramétrique au lot 4. Ne pas construire de dépendance à ce fichier.
>
> **La coupe n'est pas non plus dans le DXF.** Vérifié sur le fichier de référence : aucun calque de coupe, aucun texte, aucune cote, présentations vides. Ne pas la chercher.

---

## Sorties — contrat d'interface avec le lot 4

```
sortie/{projet}/
    geometries.gpkg      # GeoPackage, EPSG:2154, une couche par catégorie
                         # (dont la ligne de coupe corrigée)
    projet.json          # paramètres techniques, azimut des tables,
                         # profil altimétrique le long de la coupe
```

**Utiliser un GeoPackage et non un GeoJSON.** La spécification GeoJSON impose le WGS84 ; y stocker du Lambert 93 est non conforme et se paie tôt ou tard par une reprojection silencieuse. Le GeoPackage porte le système de coordonnées explicitement.

Conserver la coordonnée Z là où elle existe (les tables en portent une, altitude réelle du terrain). Elle servira au lot 4 comme contrôle de cohérence avec le MNT.

---

## Étape A — Lecture du DXF

### Détection des unités

⚠️ **Ne jamais se fier à `$INSUNITS`.** Sur le fichier de référence, l'en-tête annonce des millimètres alors que les coordonnées sont en mètres. Un outil qui croirait l'en-tête diviserait tout le plan par mille.

Déduire l'unité de l'ordre de grandeur des coordonnées, et vérifier qu'elles tombent dans les bornes du Lambert 93 métropolitain (X entre 100 000 et 1 300 000 ; Y entre 6 000 000 et 7 200 000). Hors de ces bornes : **refuser le fichier** avec un message expliquant que le plan ne semble pas géoréférencé en L93.

### Correspondance des calques

Le BE applique une charte de nommage avec le préfixe `UNI_`. Prévoir une correspondance par défaut, présentée à l'utilisateur pour confirmation dans un écran dédié :

| Calque observé | Catégorie |
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

Catégories supplémentaires à prévoir, absentes du fichier de référence mais attendues sur d'autres projets : `local_technique`, `bess`, `bac_retention`, `haie`, `ligne_coupe`.

⚠️ **Correspondance tolérante obligatoire.** Les noms contiennent des accents et des caractères substitués — l'apostrophe de « aire d'aspiration » est devenue un tiret. Normaliser en Unicode NFKD, replier la casse, et traiter tirets, espaces et underscores comme équivalents. Ne pas comparer des chaînes brutes.

Les calques `PVcase PV Modules (full frames)` et `(detailed)` existent mais sont vides : ignorer les calques sans entité, sans message d'erreur.

### Types d'entités

Gérer `LWPOLYLINE`, `POLYLINE`, `LINE`, `ARC`. Les arcs servent au dessin des portails et doivent être discrétisés en polylignes.

**Ignorer les entités `HATCH`** : ce sont des remplissages qui doublent une polyligne déjà présente. En revanche, **si un calque ne contient que des `HATCH` et aucune autre entité, émettre un avertissement** — cela signifierait qu'un élément n'existe que sous forme de remplissage et serait perdu.

Les `POLYLINE` peuvent être extrudées en 3D, avec des sommets dupliqués. Dédoublonner sur (x, y) **en préservant l'ordre** : un `set()` détruirait la géométrie.

### Azimut des tables

Calculer l'orientation des tables depuis la géométrie, et non depuis le tableau : pour chaque table, prendre le rectangle englobant orienté (`minimum_rotated_rectangle`) et retenir la direction de son grand côté. Prendre la médiane sur l'ensemble des tables.

Sur le fichier de référence, cet azimut vaut 0°, c'est-à-dire des rangées orientées est-ouest.

Cette valeur est nécessaire à l'étape D. La recouper avec l'azimut déclaré dans le tableau bilan, et avertir en cas d'écart supérieur à 2°.

---

## Étape B — Lecture du tableau bilan

### Sélection de l'indice

L'onglet `2. Caractéristiques du projet` est organisé en colonnes, une par indice de révision : le libellé en colonne A, puis une colonne par indice (`IND05` en B, `IND06` en C…). La ligne 1 porte le nom du projet en A1 et les indices dans les colonnes suivantes.

Le nom du fichier DXF contient l'indice (`20260903_SCV_IND06.dxf`). **Proposer l'appariement automatiquement, mais toujours le faire confirmer** par l'utilisateur, et signaler visiblement si l'indice du DXF est absent du tableau.

### Repérage des lignes

⚠️ **Repérer chaque paramètre par son libellé en colonne A, jamais par son numéro de ligne.** Le fichier est déjà en version 6 : la mise en page bouge d'une version à l'autre. Un accès par index produirait des valeurs fausses sans aucune erreur visible.

Appliquer la même normalisation tolérante que pour les calques.

### Paramètres à extraire

Depuis `2. Caractéristiques du projet` :

- **Généralités** : phase, date, type de projet, surface clôturée (ha), linéaire de clôture (m), nombre de portails, largeur des portails (m)
- **Structures** : type, format de table, inclinaison (°), azimut (°), nombre de tables, inter-table (m), pitch (m), **point bas (m)**, **point haut (m)**, nombre de modules en rampant, en longueur, par table, type de fondation, nombre de pieux
- **Modules** : format, puissance unitaire (Wc), surface unitaire (m²), nombre installé, GCR, surface modules (m²), surface projetée au sol (m²), puissance projet (MWc)
- **Postes et locaux** : nombre et surface des PDL, PTR, PDL/PTR et de leurs plateformes ; conteneurs BESS ; citerne de refroidissement ; bac de rétention ; local de stockage matériel

Les hauteurs point bas et point haut alimentent directement la coupe DP 3 au 1/50.

Depuis `Dimensions postes et pieux`, charger la table des cotes normalisées (PDL/PTR 12 × 3 × 3 m, PTR 10 × 3 × 3 m, conteneur BESS 6 × 3 × 3 m, citerne incendie selon volume, aire d'aspiration 8 × 4 m, local de stockage selon puissance). Elle servira au lot 4 pour générer les planches DP 4 en paramétrique.

Depuis `Standards UNITe`, charger les valeurs de référence par type de projet, à utiliser comme contrôle de vraisemblance.

### Parsing

Certaines valeurs sont composites ou typées de façon irrégulière : `13 / 26` pour les deux longueurs de table, `0°` avec le symbole degré, des dates en `datetime`. Écrire des convertisseurs tolérants — et **échouer explicitement si le motif ne correspond pas**, plutôt que de retourner une valeur par défaut.

---

## Étape C — Contrôles croisés

C'est le cœur de la valeur ajoutée de ce lot. Le scénario d'erreur réaliste n'est pas un fichier corrompu, c'est un plan mis à jour sans que le tableau le soit, ou l'inverse. Personne ne s'en aperçoit avant le dépôt.

| Contrôle | Tolérance | Si échec |
|---|---|---|
| Nombre de tables : DXF vs tableau | égalité stricte | bloquant |
| Nombre de portails : DXF vs tableau | égalité stricte | bloquant |
| Surface clôturée : polygone DXF vs tableau | 2 % | bloquant |
| Linéaire de clôture : DXF vs tableau | 2 % | avertissement |
| Surface projetée des modules vs somme des aires de tables | 5 % | avertissement |
| Emprise clôturée contenue dans l'emprise cadastrale du SHP | — | avertissement |
| Puissance projet vs seuil de recevabilité en DP | seuil paramétrable | avertissement mis en évidence |

Le dernier point : ne pas coder en dur une règle d'urbanisme. Rendre le seuil configurable, avec la valeur fournie par l'utilisateur, et se contenter d'afficher la puissance de façon très visible au moment de la génération.

Afficher également la **phase** et la **date** lues dans le tableau, pour information — le chef de projet doit voir sur quel indice il engage le dossier.

---

## Étape D — Ligne de coupe A-A'

Nécessaire pour la coupe DP 3 au 1/300. Elle n'existe ni dans le DXF ni ailleurs : elle doit être tracée.

1. Le chef de projet trace la ligne sur une carte interactive, sur fond d'ortho IGN, avec les tables et la clôture affichées en surimpression.
2. **Le tracé est corrigé automatiquement pour être perpendiculaire aux tables** (voir ci-dessous).
3. La ligne corrigée est affichée par-dessus le tracé initial, pour que l'utilisateur voie ce qui a été ajusté.
4. Elle est enregistrée dans le GeoPackage et dans `projet.json`. Une régénération ne redemande jamais le tracé.

### Correction de perpendicularité — obligatoire

Une coupe de terrain n'a de sens que perpendiculairement aux rangées : c'est la direction dans laquelle le terrain fait varier la hauteur des tables. Un tracé à main levée sera toujours approximatif, et une coupe légèrement oblique fausse les distances lues sur la planche.

Procédure :

1. Récupérer l'azimut des tables calculé à l'étape A.
2. Conserver le **point milieu** du tracé de l'utilisateur : c'est ce qui exprime son intention, pas la direction.
3. Réorienter le segment perpendiculairement à l'azimut des tables, en conservant ce point milieu.
4. Étendre la ligne pour qu'elle traverse entièrement l'emprise clôturée, avec une marge de 10 m de chaque côté.

Sur le fichier de référence, les tables étant orientées est-ouest, la coupe est donc nord-sud.

Si l'utilisateur trace un segment à plus de 45° de la perpendiculaire attendue, l'avertir explicitement : il a probablement voulu couper dans l'autre sens, ou s'est trompé de repère. Corriger malgré tout, mais ne pas le faire en silence.

Prévoir enfin un mode manuel de contournement, désactivé par défaut, pour les cas où la perpendicularité ne conviendrait pas. Il doit être un choix explicite, pas une option offerte par défaut.

---

## Étape E — Profil altimétrique du terrain

La coupe DP 3 au 1/300 nécessite le profil du terrain naturel le long de la ligne A-A'.

**Récupération automatique**, sans intervention du chef de projet : interroger l'API altimétrique de la Géoplateforme IGN (RGE ALTI) le long de la ligne de coupe.

- Échantillonner tous les 5 m, ce qui donne quelques dizaines à quelques centaines de points pour une coupe de site.
- L'API accepte une liste de points en une requête, avec un plafond de l'ordre de 2 000 points et une limitation de débit d'environ 5 requêtes par seconde. Une coupe tient donc largement en une ou deux requêtes : **découper la demande si nécessaire, et ne pas paralléliser.**
- Vérifier le point d'entrée exact et le format de réponse au moment de l'implémentation plutôt que de se fier à ce brief.
- Les altitudes reviennent en NGF, cohérentes avec les Z portés par les tables du DXF.

**Contrôle de cohérence** : comparer le profil obtenu aux altitudes des tables du DXF, aux endroits où la ligne de coupe passe à proximité d'une table. Un écart systématique supérieur à 2 m signale un problème de référentiel altimétrique et doit être signalé.

**Solution de repli** : accepter en entrée optionnelle un fichier TXT d'altimétrie produit par l'outil interne d'extraction topographique existant, qui prend alors le pas sur l'appel automatique. Utile en cas d'indisponibilité de l'API, ou lorsqu'un relevé drone plus précis existe.

Enregistrer le profil (abscisse curviligne, altitude) dans `projet.json`.

---

## Étape F — Écran de validation

Avant de conclure, présenter :

- l'aperçu des géométries importées sur fond d'ortho IGN, avec les couleurs de la légende DP
- la correspondance des calques, modifiable
- le tableau des paramètres extraits
- le résultat des contrôles croisés
- la ligne de coupe corrigée, superposée au tracé initial
- le profil altimétrique tracé, avec sa dénivelée totale
- si le PDF de référence du BE a été fourni, un accès pour comparaison visuelle

Rien ne se poursuit sans validation explicite.

⚠️ **Ne pas hériter des couleurs du DXF.** Les codes ACI y sont des couleurs de travail CAO, non signifiantes : clôture, PDL et portails partagent la même valeur. La palette de la légende DP est définie par notre outil.

---

## Règles de travail

- **Un problème à la fois.** Pas de refactoring opportuniste, pas de modification de sections non concernées. Le moteur `Planche` livré au lot 1 ne doit pas être touché — ce lot ne dessine rien.
- **Aucun repli silencieux.** Toute valeur par défaut, substitution ou correspondance approximative appliquée en cours d'exécution doit produire un message visible. Sur ce lot, une erreur produit un dossier plausible mais faux : c'est le pire des cas.
- **Ne pas assouplir les contrôles croisés** pour faire passer un fichier. S'ils échouent, c'est l'entrée qui est en cause.
- Commit après chaque étape validée.
- Respecter les contraintes d'environnement du lot 1 : versions épinglées dans `requirements.txt`, `packages.txt` à la racine en fins de ligne LF, paramètre `width` et non `use_container_width`.

---

## Critères de validation

Jeu de test : `20260903_SCV_IND06.dxf` et `20260825_SCV_Tableau_Bilan_V6.xlsx`, projet Saint-Cyr-en-Val.

Valeurs attendues, vérifiées manuellement sur les deux fichiers :

| Grandeur | Valeur |
|---|---|
| Tables importées | 96 |
| Modules (tableau) | 4 628 |
| Surface clôturée | 4,52 ha (tableau) / 4,522 ha (DXF) |
| Linéaire de clôture | 875 m (tableau) / 871,9 m (DXF) |
| Portails | 3 |
| Inclinaison / azimut | 15° / 0° |
| Point bas / point haut | 2,5 m / 4,0 m |
| Puissance | 2,93878 MWc |

Tests supplémentaires attendus :

1. Un DXF dont les coordonnées sortent des bornes L93 est refusé.
2. Un DXF dont le calque clôture est renommé avec une variante d'accentuation est tout de même reconnu.
3. Un tableau où le nombre de tables est modifié déclenche le contrôle croisé bloquant.
4. Le fichier `.gpkg` produit se relit avec son système de coordonnées correct.
5. L'azimut des tables calculé sur le fichier de référence vaut 0° à 1° près.
6. Une ligne de coupe tracée volontairement de travers ressort strictement nord-sud, son point milieu conservé, et traverse toute l'emprise clôturée.
7. Le profil altimétrique est récupéré en une ou deux requêtes, et ses altitudes concordent avec les Z des tables du DXF à moins de 2 m.

---

## Hors périmètre — ne pas commencer

- Le dessin des planches DP 2, DP 3 et DP 4 (lot 4)
- Le traitement de la notice DP 11 (lot 5)
- L'import HelioScope et le calage géographique (lot 2, en réserve)

Concevoir la sortie GeoPackage comme un contrat stable : le lot 2 en réserve devra pouvoir produire exactement le même format.
