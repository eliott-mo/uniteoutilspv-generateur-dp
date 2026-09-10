# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 6 : DP 6, DP 7, DP 8 et leurs plans de repérage

> Lots 1, 2, 2bis et 4 livrés. L'application dépose déjà les photographies dans `projets/{nom}/DP_6|DP_7|DP_8/` mais n'en fait rien : elles sont jointes au dossier à la main. Ce lot les assemble et produit le **plan de repérage** qui manque.
>
> Lire `README.md` et `CLAUDE.md` avant de commencer : ce brief ne les répète pas. Il ne rediscute pas non plus le moteur `Planche` du lot 1, qui ne se touche pas.

---

## Objectif

Trois pièces photographiques, chacune sur planche A3 paysage, avec la **position de prise de vue reportée sur un plan de repérage** :

| Pièce | Titre CERFA | Composition | Planches |
|---|---|---|---|
| DP 6 | Insertions paysagères | un point de vue, **2 ou 3 images** | **1 à N**, une par point de vue |
| DP 7 | Photographie de l'environnement proche | **1 ou 2** photographies | une seule |
| DP 8 | Photographie du paysage lointain | **1 ou 2** photographies | une seule |

Le cas courant est **une** planche DP 6 : nous disposons rarement de plusieurs
photomontages. Le dossier de référence en porte deux parce que Massay en avait
deux, pas parce que la pièce en demande deux.

`dp_socle/dossier.py` les déclare aujourd'hui `mention="fournie"` : les basculer en `produite=True` et vérifier que le sommaire paginé et le contrôle de rang de `assemblage.py` suivent — c'est le même geste qu'au lot 4.

---

## Ce qui existe déjà, et qu'il faut aller lire

### Dans ce dépôt

| Brique | Où | Ce qu'elle donne |
|---|---|---|
| Plan de repérage à échelle choisie | `dp_socle/planches/dp4_ouvrages.py:727` `_zone_reperee`, `:792` `_cadre_autour`, `:850` `_plan_de_reperage` | le patron complet d'un encart de repérage : zone à couvrir, cadre mesuré sur le dessin, refus d'une échelle hors liste |
| Planche pleine page sur fond IGN | `dp_socle/planches/dp1_1_situation.py:22` | le patron le plus proche de ce qu'il faut ici : centrer, télécharger le fond, poser l'emprise, légender, rendre |
| Fonds cartographiques | `dp_socle/ign.py` — `COUCHE_PLAN`, `COUCHE_ORTHO`, `telecharger_fond`, `telecharger_parcelles` | Plan IGN v2 et ortho, en WMS-R, à l'échelle vraie |
| Emprise et reprojection | `dp_socle/geometrie.py`, `pyproj` déjà épinglé | WGS84 → Lambert 93 |

### Dans `git_unite/photos-geoloc` — l'outil de rapport photo des CDP

C'est **le** dépôt à piller. Il résout déjà, sur photos réelles, le problème de la position et de la direction de prise de vue. Son `README.md` fait 609 lignes et documente chaque piège rencontré.

| Fichier | Ce qu'il fait | Verdict |
|---|---|---|
| `lecture_exif.py` (106 lignes) | position GPS, date, cap EXIF, **incertitude annoncée par l'appareil** | **à reprendre tel quel** — ne dépend que de Pillow, déjà épinglé ici |
| `lecture_photo.py` | orchestre les deux cascades (position, cap) | patron à reprendre, pas le code |
| `ocr_position.py` | lit les coordonnées incrustées dans l'image | **à ne pas reprendre au lot 6** — voir D2 |
| `detection_cap.py` | lit le cône bleu de la vignette GPS Map Camera | **à ne pas reprendre au lot 6** — voir D2 |
| `emprise_site.py` | shapefile → WGS84 sans dépendance géospatiale | inutile ici, `geopandas` est déjà là |
| `generation_html.py:558` `extraire_donnees()` | relit le bloc JSON d'une carte déjà produite | **la meilleure entrée possible** — voir D0 |

### Dans `git_unite/photomontage` — le prototype de photomontage filaire

Prototype **non versionné** (aucun `.git`), mono-cas, sans `requirements.txt`. Rien à importer, mais deux choses à en tirer :

- le modèle sténopé `toCam` / `proj` / `ray` (`proto_photomontage.py:322-356`) et l'intersection sol (`:724-728`), si un jour on veut déduire la visée du contenu de l'image ;
- le tracé du **cône de vue** sur plan (`:574-581`) : axe en pointillés, deux bords à ±demi-champ, `demi_angle = atan(12 / focale_35mm)`, plus des cercles de distance à 100 / 200 / 300 / 400 m. C'est la symbolisation à reprendre.

---

## Décisions prises en amont

Dix points arbitrés avant rédaction. Ils ne sont pas à rediscuter ni à « améliorer ».

### D0 — La carte de `photos-geoloc` est une entrée de premier choix

Les photographies de DP 7 et DP 8 sont souvent celles d'une **visite de site du
chef de projet**. Or il en fait déjà un rapport, avec `photos-geoloc` — et il y
a déjà fait, à l'œil et sur fond satellite, exactement le travail que D1 lui
demanderait de refaire : placer chaque prise de vue et corriger sa direction.

La carte HTML produite est un format d'échange documenté et versionné. Son bloc
`<script id="donnees-carte" type="application/json">` **fait foi** — pas le DOM
— et `generation_html.py:558` `extraire_donnees()` le relit. Chaque point y
porte, entre autres :

```
"lat", "lon"        position portée sur la carte, valeur DÉDUITE
                    (lat_manuel si replacée à la main, sinon lat_brut)
"cap"               direction portée sur la carte, valeur DÉDUITE
                    (cap_manuel si figé, sinon cap_brut + offset, sinon null)
"precision_m"       incertitude GPS annoncée, ou null
"image"             la photo en base64
"nom", "commentaire", "ordre", "masque"
"emprise"           le périmètre du projet, s'il a été déposé
```

`cap` et `lat`/`lon` sont **redondants et réécrits à chaque enregistrement**
précisément pour que les lecteurs du fichier n'aient pas à refaire le calcul.
Nous sommes ce lecteur.

**Donc : accepter le dépôt d'une carte `photos-geoloc` comme source des points
de vue.** Le chef de projet ne replace rien, ne réoriente rien, et ce qu'il a
validé sur le fond satellite fait autorité. Le dépôt de photos une par une
reste offert — toutes les visites ne passent pas par l'outil — mais c'est le
chemin long.

Deux garde-fous : lire la `version` du bloc et **refuser une version plus
récente** que celle qu'on connaît plutôt que de la lire à moitié — c'est déjà la
règle du contrat d'entrée du lot 4 ; et écarter les points `masque: true`, qui
sont en corbeille.

**Un point replacé à la main vaut un point mesuré.** La carte distingue et
compte les photos repositionnées, parce que sur un rapport de visite qui fait
foi, déplacer une photo touche à ce qui est attesté. Pour notre usage, la
question a été tranchée le 10/09/2026 : **le choix est assumé**, une position
replacée par le chef de projet part au dossier comme une autre. Ne rien en faire
de particulier — ni avertissement, ni mention sur la planche. Le rapport de
génération peut dire d'où vient chaque point de vue ; c'est une information, pas
une alerte.

#### Perspective — et pourquoi elle n'est pas une dépendance

`photos-geoloc` écarte aujourd'hui une photo sans position : `analyser()`
(`app.py:160-193`) n'en garde que le nom et le motif, l'image est perdue. Une
évolution est envisagée de son côté : **forcer l'insertion d'une photo non
géoréférencée**, à charge pour le chef de projet de la placer lui-même. Le
travail de géolocalisation resterait alors entièrement dans l'outil dont c'est le
métier, et ce lot n'aurait plus qu'une seule entrée à connaître.

La carte a déjà tout l'outillage : **📍 Replacer** pose une position d'un clic,
**🎯 Viser** donne la direction, un bouton rend à l'origine, et la corbeille
prouve que la page sait tenir un point présent dans le fichier mais absent de la
carte (`generation_html.py:700` : `visibles = [point for point in points if not
point.get("masque")]`). Ce qui manque est la porte d'entrée, plus un état « à
placer » sur le modèle de la corbeille, plus une montée de format.

**Ne pas attendre cette évolution.** Elle vit dans un autre dépôt, elle a sa
propre conversation, et les rapports déjà produits resteront au format courant.
Le dépôt photo par photo doit donc marcher de bout en bout dans ce lot-ci. Il
gardera d'ailleurs son utilité : l'image brute d'une DP 6 n'a pas toujours été
une photo de visite — un paysagiste travaille parfois sur une vue qu'il a prise
lui-même.

Ce que ce lot doit en revanche prévoir : lire **v5 et v6** le jour venu, et
refuser au-dessus. Les deux dépôts ont désormais un contrat, à traiter avec la
discipline de celui du lot 4 — format documenté, champ de version, refus de ce
qu'on ne connaît pas.

### D1 — La position se lit, le cap se propose et se confirme

**La position GPS de l'EXIF est fiable** et n'a jamais été prise en défaut sur les deux dépôts. Elle se lit, et l'incertitude que l'appareil annonce (`GPSHPositioningError`) se lit avec : au-delà de `SEUIL_PRECISION_M = 20` m, `photos-geoloc` signale la photo sans jamais l'écarter — « à l'échelle d'une visite de site, 100 m ne voulait plus rien dire (on change de parcelle) ». Un cas réel y a placé une photo à 4 km de son emplacement.

**Le cap, lui, ne se croit pas.** Mesuré deux fois, indépendamment :

- `photos-geoloc/detection_cap.py:18-20` — « La précision est celle de la boussole du téléphone, soit ±10 à 20°. C'est suffisant pour comprendre l'orientation d'une photo, pas pour du relevé. »
- `photos-geoloc/README.md` — « Un téléphone mal calibré décale toutes les directions du même angle (couramment 30 à 40°). »
- `photomontage/RESULTATS_validation.md:97-103` — cap annoncé 321,6°, cap réel 336,5°, soit **15° d'erreur**, établi par recoupement sur deux éoliennes identifiées dans OpenStreetMap.

La doctrine de `photos-geoloc` est la bonne et se reprend : **l'outil ne fournit que des directions brutes**, et la correction se fait à l'œil, sur fond satellite, parce qu'« un décalage de boussole ne se juge qu'en voyant les cônes sur le fond satellite, en vérifiant s'ils pointent vers les bons éléments du paysage ».

Concrètement, dans notre section 3 :

1. le cap EXIF, s'il existe, propose une orientation — **annoncée comme une proposition**, avec sa provenance ;
2. le chef de projet fait pivoter le cône sur la carte jusqu'à ce qu'il pointe ce que la photo montre ;
3. sans cap et sans confirmation, **la planche se dessine sans cône**, avec le seul repère numéroté. Ce n'est pas un manque, c'est le cas normal d'un drone ; `photos-geoloc` le traite déjà ainsi.

Cette confirmation ne se redemande **pas** pour un point de vue venu d'une carte
`photos-geoloc` (D0) : elle y a déjà eu lieu, sur un fond satellite, ce qui est
précisément la bonne façon de la faire.

Un cap non confirmé ne part jamais au dossier sans que le rapport de génération le dise. Règle du dépôt : aucun repli silencieux.

### D2 — Ni OCR ni OpenCV dans ce lot

`photos-geoloc` embarque `pytesseract` (plus le paquet système `tesseract-ocr`) et `opencv-python-headless` pour deux replis : lire les coordonnées incrustées quand l'EXIF manque, et lire le cône bleu de la vignette GPS Map Camera.

Ces deux replis servent des photos de terrain prises au téléphone en visite —
et c'est bien de cela qu'il s'agira souvent ici. L'argument n'est donc **pas**
que le cas ne se présente pas.

Il est que **ce travail est déjà fait ailleurs**. Un chef de projet qui a des
photos de visite a un rapport `photos-geoloc`, et D0 en fait une entrée directe :
l'OCR y a déjà tourné, la vignette y a déjà été lue, la direction y a déjà été
calibrée. Reprendre ici les deux détections, ce serait maintenir la même chose à
deux endroits, et la voir diverger.

`CLAUDE.md` limite les dépendances au strict nécessaire. Deux dépendances
lourdes, dont une système qui doit passer par `packages.txt` sur Streamlit
Community Cloud, pour refaire ce qui arrive déjà résolu : non. Le repli de ce
dépôt reste l'EXIF, puis la désignation sur la carte.

Si la mesure montre que des CDP déposent ici des photos sans EXIF **et** sans
être passés par `photos-geoloc`, le bon geste sera de les y renvoyer, ou de
traiter le sujet dans un lot à part — pas d'ajouter la détection en catimini.

### D3 — Le point de vue d'une DP 6 est celui de son image brute

Un photomontage est un **rendu** : il ne porte aucun EXIF, et n'en portera
jamais. Sa position de prise de vue est celle de la **photographie d'origine**,
celle sur laquelle il a été composé — et cette photographie-là, la planche la
porte de toute façon (D5, image (i)).

C'est donc d'elle que la position se lit, sans rien demander de plus. Les
photographies ne viennent pas nécessairement d'un paysagiste : ce sont souvent
des photos de visite de site prises par le chef de projet, ce qui rend l'EXIF
plus probable, pas moins.

Ordre à respecter :

1. l'EXIF de l'**image brute** de la vue, ou son point dans une carte
   `photos-geoloc` (D0) ;
2. à défaut, le chef de projet **place le point sur la carte** et oriente le
   cône.

Ne jamais demander de saisir des coordonnées à la main : c'est la saisie la plus
fautive qui soit, et la carte est déjà là.

### D4 — Les échelles, relevées sur le dossier de référence

Mesuré le 10/09/2026 sur `exemples/_hoch-references/250417 - Dossier DP - MASSAY - V1.pdf` :

| Planche | Pièce | Échelle du plan de repérage |
|---|---|---|
| p. 12, 13 | DPC 6 Insertions paysagères | **1 : 1 500** |
| p. 14 | DPC 7 Photographies de l'environnement proche | **1 : 2 500** |
| p. 15 | DPC 8 Photographies du paysage lointain | **1 : 6 500** |

Le 1/6 500 n'est pas une échelle normalisée : HOCH cadre sur son contenu, pas sur une liste. **Nous restons sur une liste**, conformément à la décision D2 du lot 4 — retenir la plus grande échelle qui fasse tenir le contenu utile, et l'inscrire au cartouche. Liste à retenir, à valider au premier dossier réel :

```
1/1000, 1/1500, 1/2000, 1/2500, 1/5000, 1/7500, 1/10000
```

Le contenu à faire tenir n'est pas le même selon la pièce : l'emprise clôturée plus les points de vue pour DP 6 et DP 7 ; l'emprise plus des points de vue qui peuvent être à plusieurs kilomètres pour DP 8. C'est le cadre **dessiné**, marge comprise, qui décide — la même méthode que `_cadre_autour` du lot 4, qui a servi à corriger trois défauts de cadrage sur les plans de repérage DP 4.

### D5 — La mise en page, relevée elle aussi

Même dossier, même date. A3 paysage, 1191 × 842 pt, notre format.

- **Colonne de droite** : les images, `229 × 113 mm`, calées à `x = 179 mm`, empilées avec ~92 mm de pas.
- **Colonne de gauche** : le plan de repérage et le cartouche, dans les ~175 mm restants.
- Le plan de repérage de Massay est **vectoriel** (1 150 tracés sur la DP 7, 1 624 sur la DP 8) et porte les lieux-dits. Notre équivalent est le Plan IGN v2 raster que `ign.telecharger_fond` sait chercher : il porte les mêmes toponymes.

**Une planche DP 6 porte le même point de vue plusieurs fois**, dans cet ordre :

| | Image | Obligatoire ? |
|---|---|---|
| (i) | l'**image brute** — l'état actuel, le projet absent | oui |
| (ii) | la **même image avec le photomontage** | oui |
| (iii) | le **même photomontage avec l'aménagement paysager** | **facultatif** |

Le troisième volet n'existe que s'il y a des mesures paysagères, et tous les
projets n'en portent pas. Une planche DP 6 compte donc **2 ou 3 images**, jamais
une seule : c'est la comparaison avant/après qui fait la pièce, et une image
seule ne dit rien.

Le dossier de référence intitule ces trois volets « Emplacement du projet »,
« Projet dans son environnement » et « Projet avec mesures paysagères ». Les
reprendre.

DP 7 et DP 8 portent **une ou deux** photographies chacune, sur une seule
planche, avec des points de vue numérotés : `PC7-1`, `PC7-2`, `PC8-1`, `PC8-2`.
Reprendre cette numérotation — les services instructeurs y sont habitués, c'est
la raison qui a présidé au choix des intitulés dans `dp_socle/dossier.py`.

**La colonne d'images se compose, elle ne se calque pas.** Deux images ne
s'empilent pas comme trois, et une seule photographie de DP 7 n'occupe pas la
demi-planche d'un couple. `dp_socle/planches/primitives.py` porte déjà
`repartir_hauteurs()`, écrit au lot 4 pour exactement ce problème — uniformiser
le vide entre des sous-cadres de contenus inégaux. Les 229 × 113 mm relevés
ci-dessus sont donc une **mesure de référence, pas une constante à câbler** : ils
disent le rapport de forme visé et la largeur de la colonne, pas la hauteur à
imposer.

### D6 — La symbolisation du point de vue

Un repère numéroté à la position, et un cône de visée quand le cap est confirmé. Le prototype `photomontage` en donne le tracé : axe en pointillés, deux bords à `±atan(12 / focale_35mm)`, une longueur qui porte jusqu'au projet.

**Piège mesuré, à traiter dès la conception** — `photomontage/RESULTATS_validation.md:97-100` : GPS Map Camera rogne la photo en 9:16 alors que le capteur sort du 3:4. La règle « 24 mm = largeur » donne alors une focale en pixels fausse, et donc un demi-champ faux. Détecter le rognage par le rapport d'image et calculer sur le côté non rogné.

À défaut de focale connue, ne pas inventer un champ de vue : dessiner le repère seul, et le dire.

### D7 — Les photos du rapport s'affectent sur vignettes, pas sur numéros

Un rapport de visite porte des dizaines de points ; une pièce DP en demande une
ou deux. Il faut donc choisir, et **un numéro seul ne dit pas ce qu'une photo
montre**.

Une **galerie de vignettes**, donc, chacune portant le numéro qu'elle a sur la
carte du rapport — `generation_html.py:1169` trie les points visibles par
`ordre`, et c'est ce rang que le chef de projet a vu sur ses marqueurs. C'est son
seul repère commun entre les deux écrans : le lui retirer l'obligerait à
rouvrir sa carte à côté.

Sous chaque vignette, une liste d'affectation, **proposée puis corrigée** :

> `(ignorer)` · `DP 7` · `DP 8` · `DP 6 — vue 1, image brute` · …

La proposition se calcule. DP 7 est « l'environnement **proche** », DP 8 « le
paysage **lointain** » : c'est une distance, et nous avons l'emprise des deux
côtés — la nôtre en section 1, celle du rapport dans son bloc JSON. Chaque point
de vue se range donc seul, et le chef de projet ne corrige que ce qui n'est pas
évident.

C'est le geste de la **correspondance des calques** de la section 2 : proposée
par la charte de nommage, modifiable, et ce qui reste sur « (ignorer) » n'entre
pas. Même idiome, déjà éprouvé dans cette application, déjà connu du chef de
projet. Ne pas en inventer un autre.

Trois règles qui suivent :

- les points `masque: true` ne sont pas proposés — ils sont en corbeille ;
- un point sans cap donne un repère sans cône, sans que ce soit une erreur ;
- la numérotation du dossier repart par pièce — `PC7-1`, `PC7-2` — sans reprendre
  celle du rapport, qui compte tous les points de la visite et n'a pas le même
  sens dans le dossier.

**Le rapport ne fournit jamais un photomontage.** Un photomontage est un rendu :
il n'est allé sur aucune visite. Le rapport donne les photographies de DP 7,
celles de DP 8, et l'**image brute** d'une vue de DP 6 — le volet (i) de D5. Les
volets (ii) et (iii) viennent du prestataire et se déposent à part.

### D8 — Le rapport est une importation, pas un stockage

L'application tourne sur Streamlit Community Cloud : 690 Mo garantis, 2,7 Go au
maximum, et la génération d'un dossier culmine déjà à 367 Mo mesurés — 523 Mo à
300 dpi. Une carte de quarante photos pèse une vingtaine de mégaoctets de base64.
Il n'est donc pas question de la garder en session.

La règle :

1. lire le fichier **une fois**, en extraire le bloc JSON et n'en garder que les
   **métadonnées** — `id`, `nom`, `ordre`, `lat`, `lon`, `cap`, `precision_m` ;
2. ne décoder les images qu'à la demande, en **vignettes réduites** pour la
   galerie ;
3. à l'affectation, écrire les seules photos retenues dans
   `projets/{nom}/DP_6|DP_7|DP_8/`, comme n'importe quelle photo déposée ;
4. **oublier le rapport.** Il ne survit pas à l'affectation.

Le dossier ne voit donc jamais qu'un chemin de fichier, celui qu'il connaît
déjà. Pas de second chemin de traitement selon la provenance, et rien de lourd
qui traîne en session.

`photos-geoloc` a rencontré ce problème avant nous et l'a mesuré : voir ses
commits `0edafc7` « Lire la carte deposee en octets, sans jamais la decoder »,
`79fd5ef` « Ecrire le gabarit en ASCII : quatre fois moins de memoire par
carte », `cf21784` « Borner le cache des apercus et ramasser les dossiers
abandonnes ». **Lire ces trois-là avant d'écrire la lecture du fichier** : les
techniques y sont établies sur mesure, pas sur intuition.

### D9 — Une photo hors rapport se place d'un trait sur la carte

Il faut pouvoir ajouter une photo que le rapport ne contient pas. Ce n'est pas un
cas marginal, c'est le cas normal de DP 6 : le photomontage n'a jamais été sur le
terrain, et l'image brute peut venir d'ailleurs qu'une visite.

Le geste existe déjà dans l'application. La carte de la section 2 porte
`folium.plugins.Draw`, aujourd'hui restreint à la polyligne pour la coupe A-A'.
Or **un trait donne exactement les deux valeurs qu'un point de vue demande** :
son origine est la position, sa direction est le cap. Une seule geste pour les
deux, sur le plan importé, aux couleurs de la planche.

C'est aussi, mot pour mot, le geste que `photos-geoloc` appelle **🎯 Viser** — le
chef de projet le connaît, et il désigne là-bas la même chose : non pas où est la
photo, mais ce qu'elle regarde.

Pour DP 6, un seul trait sert toute la vue : les volets (ii) et (iii) héritent du
point de vue du volet (i), puisque c'est la même prise de vue (D3).

Ne pas offrir de saisie de coordonnées. Jamais.

---

## Ce que le lot doit produire

1. `dp_socle/planches/dp6_insertions.py`, `dp7_environnement_proche.py`, `dp8_paysage_lointain.py`, sur le patron de `dp1_1_situation.py` et `dp4_ouvrages._plan_de_reperage`.
2. Un module commun de **points de vue** — lecture d'une carte `photos-geoloc` (D0), lecture EXIF (reprise de `photos-geoloc/lecture_exif.py`), reprojection L93, cône de visée, symbolisation numérotée.
3. Dans `app.py`, section 3 : par pièce, la saisie des points de vue sur la **carte déjà présente en section 2** — celle qui porte le plan importé et sur laquelle la coupe se trace depuis le 10/09/2026. Ne pas en ajouter une deuxième : c'est le défaut qui vient d'être corrigé.
4. Le basculement des trois pièces en `produite=True` dans `dp_socle/dossier.py`, et l'assemblage qui suit.
5. Le contrat : les points de vue doivent survivre à un rechargement de page. Ils ont leur place dans `projet.json` du lot 1, à côté de `image_garde` — pas dans le contrat d'entrée du lot 4, qui décrit le plan du bureau d'études et rien d'autre.

---

## Critères de validation

Dans l'esprit du dépôt : **mesurer le PDF produit**, pas l'exécution.

1. **Échelle vraie.** Sur la planche DP 7 produite, la distance entre deux points de vue mesurée dans le flux de contenu du PDF correspond à leur distance terrain, à 0,5 % près. Même méthode que `tests/test_echelle_pdf.py`.
2. **Le cadre contient ce qu'il doit.** Le plan de repérage couvre l'emprise clôturée **et** tous les points de vue de sa pièce, marge comprise, à l'échelle retenue. C'est le contrôle qui a manqué au lot 4 et qu'il a fallu ajouter après coup.
3. **Aucun cap inventé.** Un point de vue sans cap confirmé donne un repère sans cône, et le rapport de génération le dit. Un test doit le vérifier sur un jeu sans EXIF.
4. **La planche DP 6 refuse une vue à une seule image** : sans le couple
   brut / photomontage, la pièce ne compare rien. Le troisième volet, lui,
   s'omet sans un mot — son absence est normale.
5. **Une carte `photos-geoloc` d'une version plus récente est refusée**, pas lue
   à moitié.
6. `tests/test_app_streamlit.py` suit le parcours : déposer les photos, placer un point de vue, générer, et retrouver les pièces dans l'archive téléchargée.

---

## Jeux de référence

- `exemples/_hoch-references/250417 - Dossier DP - MASSAY - V1.pdf` — pages 12 à 15, la référence visuelle de ce lot.
- `exemples/saint-cyr-DXF/` — le seul jeu complet versionné, pour le plan et l'emprise.
- `git_unite/photos-geoloc/Photos validation/` — des photographies réelles avec EXIF, pour éprouver la lecture.

---

## Ce qui n'est pas dans ce lot

- Produire des photomontages. Le rendu 3D reste externe ; le prototype `photomontage` sert à valider une géométrie, pas à fabriquer une pièce.
- Déduire la visée du contenu de l'image. La mécanique existe (`proto_photomontage.py:346-354`), elle demande des amers identifiés à la main. Hors sujet tant que le chef de projet peut orienter un cône à l'œil.
- La notice DP 11, qui reste le lot 5.
