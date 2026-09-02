# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 2 : import DXF HelioScope et calage

> À n'ouvrir qu'une fois le lot 1 (socle) livré et validé. Ce lot produit des géométries géoréférencées ; il ne dessine aucune planche.

## Contexte

Les chefs de projet UNITe réalisent le calepinage photovoltaïque sous **HelioScope**. Aujourd'hui ils en font une capture d'écran qu'ils annotent sous PowerPoint. On veut à la place exploiter l'export CAO de HelioScope, qui contient la géométrie vectorielle exacte.

Problème : **le DXF exporté par HelioScope ne contient aucune donnée de géolocalisation.** Le calepinage est dans un repère local. Une analyse préalable a établi comment le recaler ; ce brief en donne la recette, qui a été validée sur deux exports réels.

---

## Objectif

Un module `dp_socle/helioscope.py` qui, à partir d'un export CAO HelioScope (le ZIP contenant le `.dxf` et l'image de fond `.jpg`) et du shapefile d'emprise cadastrale, produit :

- les tables photovoltaïques en géométries **Lambert 93 (EPSG:2154)**
- la zone d'implantation, les reculs et les zones évitées, également en L93
- les paramètres du calepinage extraits du fichier
- un fichier de calage persistant, réutilisable sans refaire l'opération

---

## Recette de transformation — à implémenter telle quelle

Cette séquence a été validée sur deux designs distincts du même projet. **La recopier fidèlement**, sans réécriture ni simplification.

```
1. Lire l'entité IMAGE du DXF :
       res = image.u_pixel.x          # résolution au sol, m/px

2. Contrôle de rotation :
       image.v_pixel.x doit être ≈ 0  (< 1e-9)
   Sinon → refuser le fichier.

3. Déduire le niveau de zoom :
       K = 156543.03392804097
       z = floor(log2(K / res))

4. Déduire la latitude de référence :
       lat_centre = acos(res * 2**z / K)

5. Facteur d'échelle vers Web Mercator :
       k = 1 / cos(lat_centre)
       Mercator = origine_mercator + coordonnées_DXF * k
```

Le DXF est en **mètres sol réels**, orienté nord en haut. Seule la position de l'origine reste inconnue.

### Test d'intégrité obligatoire

La partie fractionnaire de `log2(K / res)` vaut mathématiquement `-log2(cos φ)`. Pour la France métropolitaine (latitudes 41° à 52°), elle est **toujours comprise entre 0,40 et 0,72**, et ne s'approche donc jamais d'un entier.

**Implémenter ce contrôle et refuser le fichier si la valeur sort de cette plage.** C'est ce qui garantit que le niveau de zoom n'a pas été mal identifié et que le fichier obéit bien au modèle. Sans lui, un fichier atypique produirait une implantation à l'échelle fausse d'un facteur 2, sans aucun signe visible.

---

## Calage de l'origine

Une seule inconnue subsiste : la longitude de l'origine. La latitude, elle, se déduit entièrement du fichier via la recette ci-dessus.

**Ne pas utiliser la « Location » affichée par HelioScope.** Vérifié sur un projet réel : elle est à 176 m au nord et 220 m à l'ouest de l'origine réelle du DXF. C'est un point arbitraire cliqué par le chef de projet à la création du dossier, sans valeur de référence.

### Pré-positionnement automatique

Ajuster par translation la zone d'implantation du DXF (calque `Field_Segments`) sur l'emprise cadastrale du shapefile, l'échelle et la rotation étant déjà connues.

Attention : la zone HelioScope est **tracée à la main** par le chef de projet et ne coïncide pas avec le parcellaire. Sur le cas testé, 25,05 ha contre 27,99 ha pour le cadastre. L'ajustement reste néanmoins bon à quelques mètres près, ce qui suffit pour un pré-positionnement. Ne pas présenter ce résultat comme définitif.

### Validation par l'utilisateur — obligatoire

Afficher la superposition sur ortho IGN et **exiger une validation explicite** avant de poursuivre. L'utilisateur doit pouvoir ajuster par glissement.

Comme la latitude est déjà verrouillée par le fichier, **ne proposer qu'un ajustement est-ouest**. Un seul degré de liberté : c'est nettement plus facile à régler à l'œil, et beaucoup plus difficile à rater. Ne pas offrir un déplacement libre en deux dimensions.

### Persistance

Enregistrer la longitude retenue dans le `projet.json`. Un dossier régénéré ne doit jamais redemander le calage.

---

## Contrôles à l'import

Le fichier doit être inspecté avant tout traitement, et les anomalies signalées explicitement — jamais contournées.

| Contrôle | Comportement si échec |
|---|---|
| Présence d'entités sur le calque `Modules` | **Erreur bloquante** avec message explicite (voir ci-dessous) |
| `v_pixel.x` ≈ 0 | Refus du fichier |
| Partie fractionnaire du zoom dans [0,40 ; 0,72] | Refus du fichier |
| Présence de `Keepouts` | Simple information, l'absence est normale |
| `$INSUNITS` = 6 (mètres) | Avertissement si différent |

Le cas « modules absents » est le plus fréquent et le plus piégeux : **un export réalisé avant la finalisation de la section électrique sort sans aucun module**, tout en paraissant valide (la zone, les reculs et les zones évitées sont bien là). Cela s'est produit sur le premier export de test. Le message doit indiquer précisément quoi faire : *terminer la section électrique dans HelioScope, faire Save & Exit, puis réexporter.*

---

## Structure attendue du DXF

Observée sur les fichiers de référence :

| Calque | Contenu |
|---|---|
| `Field_Segments` | 1 polyligne, la zone d'implantation tracée à la main |
| `Field_Segment_Setback` | polylignes de recul (autour de la zone et de chaque zone évitée) |
| `Keepouts` | zones évitées (bâtiments, bassins, voiries) — peut être vide |
| `Modules` | INSERT référençant un bloc `fs_*_full`, lui-même composé de blocs module |

Les polylignes sont des **murs extrudés** : chaque sommet apparaît deux fois, en Z=0 et en Z=hauteur. Dédoublonner sur (x, y) en préservant l'ordre — un `set()` casserait la géométrie.

Chaque INSERT du calque `Modules` référence une table complète. Sur le cas de référence : 1 532 tables de 3 modules, soit 4 596 modules.

---

## Paramètres à extraire

Ces valeurs alimenteront la coupe DP 3 et le tableau de la notice DP 11. Les extraire du fichier garantit la cohérence entre le plan, la coupe et le texte.

| Paramètre | Source |
|---|---|
| Nombre de modules | nombre d'INSERT × nombre de modules par bloc table |
| Dimensions du module | bbox du bloc module |
| **Inclinaison** | **contenue dans le nom du bloc**, ex. `module_characterization_128666_15.0deg_portrait` |
| Orientation | `rotation` des INSERT |
| Nombre de rangées | valeurs distinctes en Y des INSERT |
| Pas inter-rangées | médiane des écarts en Y |
| Pas inter-table | médiane des écarts en X |

Extraire l'inclinaison du nom de bloc par expression régulière, et **échouer explicitement si le motif ne correspond pas** plutôt que de retourner une valeur par défaut.

---

## Sorties

- Un GeoJSON en EPSG:2154 par couche : `tables`, `zone_implantation`, `reculs`, `zones_evitees`
- Un dictionnaire de paramètres, sérialisé dans `projet.json`
- La longitude de calage, dans `projet.json`

**Ne pas produire de planche.** Le dessin relève du lot 4.

---

## Règles de travail

Identiques au lot 1, et rappelées ici car elles s'appliquent particulièrement à ce lot :

- **Un problème à la fois**, pas de refactoring opportuniste, pas de modification de sections non concernées. Le moteur `Planche` livré au lot 1 ne doit pas être touché.
- **Aucun repli silencieux.** Sur ce lot, une erreur de calage produit une implantation décalée ou à la mauvaise échelle qui reste visuellement plausible. Toute anomalie doit bloquer ou avertir visiblement.
- **Ne pas réécrire la recette de transformation** ni le test d'intégrité pour les rendre « plus élégants ». Ils sont issus d'une validation empirique et chaque terme compte.
- Commit après chaque étape validée.

---

## Critères de validation

1. Le fichier de test `helioscope_design_10482797.dxf` donne : 4 596 modules, inclinaison 15°, 17 rangées, pas inter-rangées 10,93 m, pas inter-table 1,15 m.
2. La latitude d'origine calculée vaut **47,842937** — les deux designs du projet Bray-Saint-Aignan doivent donner la même valeur à 10⁻⁶ degré près.
3. Superposée à l'ortho IGN, la zone d'implantation recalée coïncide avec le terrain à quelques mètres près.
4. Un fichier sans modules est refusé avec le message d'action approprié.
5. Un `res` artificiellement modifié d'un facteur 2 déclenche le test d'intégrité.
