# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 6 : DP 6, DP 7, DP 8 et leurs plans de repérage

> Lots 1, 2, 2bis et 4 livrés. L'application dépose déjà les photographies dans `projets/{nom}/DP_6|DP_7|DP_8/` mais n'en fait rien : elles sont jointes au dossier à la main. Ce lot les assemble et produit le **plan de repérage** qui manque.
>
> Lire `README.md` et `CLAUDE.md` avant de commencer : ce brief ne les répète pas. Il ne rediscute pas non plus le moteur `Planche` du lot 1, qui ne se touche pas.

---

## Objectif

Trois pièces photographiques, chacune sur planche A3 paysage, avec la **position de prise de vue reportée sur un plan de repérage** :

| Pièce | Titre CERFA | Vues | Planches |
|---|---|---|---|
| DP 6 | Insertions paysagères | une par point de vue | une planche par vue |
| DP 7 | Photographie de l'environnement proche | plusieurs | une seule planche |
| DP 8 | Photographie du paysage lointain | plusieurs | une seule planche |

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

### Dans `git_unite/photomontage` — le prototype de photomontage filaire

Prototype **non versionné** (aucun `.git`), mono-cas, sans `requirements.txt`. Rien à importer, mais deux choses à en tirer :

- le modèle sténopé `toCam` / `proj` / `ray` (`proto_photomontage.py:322-356`) et l'intersection sol (`:724-728`), si un jour on veut déduire la visée du contenu de l'image ;
- le tracé du **cône de vue** sur plan (`:574-581`) : axe en pointillés, deux bords à ±demi-champ, `demi_angle = atan(12 / focale_35mm)`, plus des cercles de distance à 100 / 200 / 300 / 400 m. C'est la symbolisation à reprendre.

---

## Décisions prises en amont

Six points arbitrés avant rédaction. Ils ne sont pas à rediscuter ni à « améliorer ».

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

Un cap non confirmé ne part jamais au dossier sans que le rapport de génération le dise. Règle du dépôt : aucun repli silencieux.

### D2 — Ni OCR ni OpenCV dans ce lot

`photos-geoloc` embarque `pytesseract` (plus le paquet système `tesseract-ocr`) et `opencv-python-headless` pour deux replis : lire les coordonnées incrustées quand l'EXIF manque, et lire le cône bleu de la vignette GPS Map Camera.

Ces deux replis servent des photos de terrain prises au téléphone en visite. **Ce n'est pas notre cas d'entrée** : les pièces DP 6 à DP 8 arrivent d'un paysagiste ou du chef de projet lui-même, et le repli naturel est la désignation à la main sur la carte, que l'interface offre de toute façon (D1).

`CLAUDE.md` limite les dépendances au strict nécessaire. Deux dépendances lourdes, dont une système qui doit passer par `packages.txt` sur Streamlit Community Cloud, pour un repli qu'on a déjà autrement : non. Si la mesure montre plus tard que les CDP déposent des photos sans EXIF mais à bandeau incrusté, ce sera un lot à part, avec le besoin établi.

### D3 — Le point de vue d'une DP 6 est celui de sa photographie d'origine

Un photomontage est un **rendu** : il ne porte aucun EXIF, et n'en portera jamais. Sa position de prise de vue est celle de la photographie sur laquelle le paysagiste a travaillé.

Deux façons de la retrouver, à offrir dans cet ordre :

1. le chef de projet **désigne la photographie source** parmi celles de DP 7 — c'est le cas courant, le paysagiste travaillant sur une vue que le CDP lui a fournie ;
2. à défaut, il **place le point sur la carte** et oriente le cône.

Ne jamais demander de saisir des coordonnées à la main : c'est la saisie la plus fautive qui soit, et la carte est déjà là.

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

**Une planche DP 6 porte trois images du même point de vue**, et non une :

1. « Vue A : Emplacement du projet » — l'état actuel, l'emprise repérée ;
2. « Vue A : Projet dans son environnement » — le photomontage ;
3. « Vue A : Projet avec mesures paysagères » — le photomontage avec les haies.

C'est un **triptyque**, à demander comme tel au paysagiste. L'interface doit le réclamer par vue, pas comme trois fichiers indépendants — sinon le chef de projet en oublie un et personne ne le voit.

DP 7 et DP 8 portent deux images chacune sur une seule planche, avec des points de vue numérotés : `PC7-1`, `PC7-2`, `PC8-1`, `PC8-2`. Reprendre cette numérotation : les services instructeurs y sont habitués, c'est la raison qui a présidé au choix des intitulés dans `dp_socle/dossier.py`.

### D6 — La symbolisation du point de vue

Un repère numéroté à la position, et un cône de visée quand le cap est confirmé. Le prototype `photomontage` en donne le tracé : axe en pointillés, deux bords à `±atan(12 / focale_35mm)`, une longueur qui porte jusqu'au projet.

**Piège mesuré, à traiter dès la conception** — `photomontage/RESULTATS_validation.md:97-100` : GPS Map Camera rogne la photo en 9:16 alors que le capteur sort du 3:4. La règle « 24 mm = largeur » donne alors une focale en pixels fausse, et donc un demi-champ faux. Détecter le rognage par le rapport d'image et calculer sur le côté non rogné.

À défaut de focale connue, ne pas inventer un champ de vue : dessiner le repère seul, et le dire.

---

## Ce que le lot doit produire

1. `dp_socle/planches/dp6_insertions.py`, `dp7_environnement_proche.py`, `dp8_paysage_lointain.py`, sur le patron de `dp1_1_situation.py` et `dp4_ouvrages._plan_de_reperage`.
2. Un module commun de **points de vue** — lecture EXIF (reprise de `photos-geoloc/lecture_exif.py`), reprojection L93, cône de visée, symbolisation numérotée.
3. Dans `app.py`, section 3 : par pièce, la saisie des points de vue sur la **carte déjà présente en section 2** — celle qui porte le plan importé et sur laquelle la coupe se trace depuis le 10/09/2026. Ne pas en ajouter une deuxième : c'est le défaut qui vient d'être corrigé.
4. Le basculement des trois pièces en `produite=True` dans `dp_socle/dossier.py`, et l'assemblage qui suit.
5. Le contrat : les points de vue doivent survivre à un rechargement de page. Ils ont leur place dans `projet.json` du lot 1, à côté de `image_garde` — pas dans le contrat d'entrée du lot 4, qui décrit le plan du bureau d'études et rien d'autre.

---

## Critères de validation

Dans l'esprit du dépôt : **mesurer le PDF produit**, pas l'exécution.

1. **Échelle vraie.** Sur la planche DP 7 produite, la distance entre deux points de vue mesurée dans le flux de contenu du PDF correspond à leur distance terrain, à 0,5 % près. Même méthode que `tests/test_echelle_pdf.py`.
2. **Le cadre contient ce qu'il doit.** Le plan de repérage couvre l'emprise clôturée **et** tous les points de vue de sa pièce, marge comprise, à l'échelle retenue. C'est le contrôle qui a manqué au lot 4 et qu'il a fallu ajouter après coup.
3. **Aucun cap inventé.** Un point de vue sans cap confirmé donne un repère sans cône, et le rapport de génération le dit. Un test doit le vérifier sur un jeu sans EXIF.
4. **La planche DP 6 refuse un triptyque incomplet**, ou le signale sans le taire.
5. `tests/test_app_streamlit.py` suit le parcours : déposer les photos, placer un point de vue, générer, et retrouver les pièces dans l'archive téléchargée.

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
