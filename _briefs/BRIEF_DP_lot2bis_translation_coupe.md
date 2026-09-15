# BRIEF — Déplacer la ligne de coupe A-A' au lieu de la retracer

> Modification du **lot 2bis** (import du plan BE, coupe A-A'), postérieure à sa
> livraison. La coupe appartient au lot 2bis et non au lot 4, même si les deux
> se rejoignent sur la planche DP 3.
>
> Lire `README.md` et `CLAUDE.md` avant de commencer. Écrit le 14/09/2026 depuis
> la conversation du lot 6, qui touche à la même carte — voir la coordination en
> fin de brief, elle n'est pas facultative.

---

## Le constat, mesuré dans le code le 14/09/2026

`_proposer_la_coupe` (`app.py:518`) pose déjà une coupe par défaut dès l'import,
perpendiculaire aux rangées et posée là où elle traverse le plus de tables. Sa
docstring annonce que le chef de projet « la déplace seulement si elle lui
déplaît ».

**Or il n'existe aucun moyen de la déplacer.** Retracer un segment appelle
`corriger_ligne_coupe(..., tables=plan.tables)`, qui en mode automatique
**recalcule entièrement la position** par `position_de_coupe()`
(`dp_socle/coupe.py:310-315`) et repose la coupe exactement où elle était. Le
tracé ne sert que de déclencheur : le geste est vide.

Le seul contournement est la case « Conserver la direction tracée », qui
conserve **aussi** la direction — donc une coupe oblique, dont les
avertissements du module disent eux-mêmes qu'elle allonge toutes les distances
qu'on y lit.

Ce qui manque est une combinaison qui n'existe pas :

| | direction | position |
|---|---|---|
| `manuel=False` | imposée ✔ | recalculée, le tracé est ignoré |
| `manuel=True` | tracée ✘ | tracée ✔ |
| **ce qui manque** | **imposée ✔** | **choisie par le chef de projet ✔** |

---

## Ce qu'il faut produire

Un **clic armé** sur la carte de la section 2, sur l'idiome de `photos-geoloc`
que les chefs de projet connaissent déjà : un bouton « Déplacer la coupe » arme
la carte, une bannière annonce ce qu'on attend, et le clic suivant translate la
coupe pour qu'elle passe par ce point, **en gardant la perpendiculaire aux
rangées**.

Vérifié le 14/09/2026 : `st_folium` renvoie `last_clicked`
(`streamlit_folium/__init__.py:347`, version 0.27.2 épinglée). Un clic simple
suffit, aucun outil de dessin n'est nécessaire.

Côté géométrie, tout existe : il s'agit d'une variante de `corriger_ligne_coupe`
qui reçoit un `Point` au lieu d'une `LineString`, impose la perpendiculaire et
étend par `_etendre()`. Rien de neuf à calculer.

Coût : **un rechargement par clic**, soit exactement celui du bouton « Corriger
et relever le profil » d'aujourd'hui. Pas de curseur d'angle ni de glissement
continu — dans Streamlit, chaque cran relancerait le script.

## Ce que ce chantier ne change pas

- Le tracé polyligne **reste**, comme contournement : le mode manuel en dépend.
- La proposition automatique reste la valeur par défaut, et garde la priorité
  d'une coupe reprise d'un import précédent.
- `position_de_coupe()` n'est pas touchée.
- Le profil du terrain se relève après translation, comme il le fait
  aujourd'hui après un tracé.

---

## Coordination avec le lot 6 — à lire avant d'écrire une ligne

Le lot 6 (photographies DP 6/7/8 et plans de repérage), en cours dans une autre
conversation, ajoute sur **la même carte** deux clics armés : placer un point de
vue, et viser ce qu'il regarde. Même mécanisme, même zone d'`app.py`. Sans
partage explicite, les deux chantiers écrivent deux fois la même chose et
entrent en conflit.

Le partage retenu :

1. **Ce chantier pose le mécanisme de clic armé** — l'armement en session, la
   bannière qui dit ce qu'on attend, la consommation du clic, l'annulation. Il a
   le périmètre le plus petit : un seul usage, un seul bouton.
2. Le lot 6 le **reprend tel quel** pour ses deux gestes, sans le réécrire.
3. Le lot 6 ne touche pas à `app.py` tant que ce chantier n'a pas abouti. Il
   travaille en attendant sur son module de points de vue, qui n'en dépend pas.
4. Le lot 6 envisage de **déplacer la carte** plus bas dans la page, après le
   dépôt des pièces. À faire après ce chantier, jamais pendant.

## Deux gains gratuits, et un piège

- `returned_objects` n'est pas passé à `st_folium` aujourd'hui : la carte
  relance le script sur **toute** interaction, y compris un simple déplacement
  ou un zoom. Le restreindre à ce qui sert vraiment supprime ces rechargements
  parasites. À mesurer, pas à supposer.
- La clé `carte_coupe_be_{tour_carte}` remonte la carte à neuf à chaque coupe
  retenue, et le chef de projet y perd son zoom. Elle existe parce qu'un tracé
  Leaflet résiduel se superposait à la coupe redressée — un clic ne laisse aucun
  tracé résiduel, donc cette remontée n'a pas lieu d'être pour une translation.
  Vérifier plutôt que supposer.
- Règle du dépôt, aucun repli silencieux : un clic hors du site doit lever.
  `corriger_ligne_coupe` porte déjà le message qu'il faut — la coupe obtenue ne
  traverse pas l'emprise clôturée, et elle le dit avec la distance.

## Validation

Mesurer le résultat, pas l'exécution :

1. Après translation, l'écart de la coupe à la perpendiculaire aux rangées vaut
   **zéro** — c'est ce qui distingue ce geste du mode manuel.
2. La coupe passe bien par le point cliqué, à la tolérance de reprojection près.
3. Un clic hors du site est refusé avec le message existant, et la coupe
   précédente reste en place.
4. Le profil du terrain est relevé sur la nouvelle position, et les contrôles de
   cohérence rejoués.
5. `tests/test_coupe.py`, `tests/test_ordre_app.py` et
   `tests/test_app_streamlit.py` passent.

## Hors périmètre

- Les points de vue des photographies : c'est le lot 6.
- Le déplacement de la carte dans la page : le lot 6, après.
- La refonte de la navigation en étapes validées : ni l'un ni l'autre.

---

## Ce que la mesure a montré — écrit le 15/09/2026, chantier livré

Le brief tenait sur l'essentiel : `last_clicked` suffit, la géométrie n'avait
rien de neuf à calculer, et la carte n'a pas besoin d'être remontée. Quatre
choses lui manquaient.

### Le brief a manqué la reprise : une coupe déplacée était perdue à la régénération

Le brief écrit que « la proposition automatique reste la valeur par défaut, et
garde la priorité d'une coupe reprise d'un import précédent ». Il n'a pas vu que
la coupe **déplacée** n'était pas reprise du tout. La sortie ne garde que le
`trace_initial`, et `reprendre_coupe` le repassait par `corriger_ligne_coupe` avec
les tables — donc par `position_de_coupe`, qui recalcule la position et repose la
coupe automatique. Le chef de projet déplaçait sa coupe, validait, et la
retrouvait au milieu à la régénération suivante ; l'écran annonçait de surcroît le
déplacement comme un effet du plan (« l'azimut des tables ou l'emprise clôturée
ont changé depuis »), ce qui était faux et détournait le diagnostic.

Sans ce correctif, le geste ne marchait que jusqu'au premier réimport : c'est le
chantier, pas un supplément. La sortie porte donc `position_choisie`, écrit des
**deux côtés** du contrat commun, et `reprendre_coupe` rejoue une translation
quand le champ est vrai. Les sorties écrites avant cette date ne l'ont pas et
rejouent la correction, comme avant — elles n'avaient pas de position choisie à
conserver.

Le point rejoué est le milieu de la ligne enregistrée, faute d'avoir gardé le
point cliqué. C'est exact tant que le plan n'a pas tourné, parce que `_etendre`
rend la **même ligne pour n'importe quel point de cette ligne** : les projections
des sommets de l'emprise se décalent de la même quantité que l'origine. Cette
propriété, non énoncée au brief, est ce qui a permis de ne pas ajouter un second
champ au contrat.

### Un clic d'avant l'armement était consommé par le geste

`last_clicked` persiste d'une exécution du script à la suivante. Le brief note
qu'il faut consommer le clic ; il ne dit pas qu'il faut aussi le retenir **quand
aucun geste n'est armé**. Sans cela, un clic fait pour regarder le plan restait en
réserve, et le bouton « Déplacer la coupe » le consommait aussitôt : la coupe
sautait à un endroit cliqué bien avant, sans que personne ait cliqué depuis.

### Armer coûte aussi un rechargement

Le brief compte « un rechargement par clic ». Il en faut un de plus à l'armement
et un à l'annulation : sans eux l'écran reste d'un tour en retard sur lui-même —
la bannière s'affiche sous un bouton qui propose encore de déplacer la coupe et
sans moyen d'annuler, et à l'inverse la bannière réclame un clic que plus rien
n'attend. Coût négligeable, mais le brief ne l'avait pas vu.

### Le message de refus était presque celui qu'il fallait

Le brief dit que `corriger_ligne_coupe` « porte déjà le message qu'il faut ». La
distance, oui. Mais sa consigne de sortie parlait de tracer, et son
`.replace(",", " ")` — qui corrige le séparateur de milliers du format `,.0f` —
s'appliquait à la phrase entière : toute virgule d'une nouvelle consigne aurait
été mangée. Le contrôle est devenu commun (`_verifier_traverse`), la consigne est
passée en paramètre, et seul le nombre est reformaté.

### Ce qui s'est vérifié comme annoncé

- `st_folium` 0.27.2 expose bien `last_clicked`, alimenté par l'événement `click`
  de Leaflet. Un clic simple suffit, aucun outil de dessin n'est nécessaire.
- `returned_objects` supprime bien les rechargements parasites : son bundle filtre
  la charge sur cette liste, la compare à la précédente, et n'appelle
  `setComponentValue` que si elle a changé. Déplacer la carte ou zoomer ne relance
  donc plus le script.
- La carte n'a pas à être remontée pour une translation : le compteur de clé reste
  celui du tracé, et le zoom est conservé.

Limite assumée, non prévue au brief : recliquer au **pixel exact** du clic
précédent ne produit rien, le composant n'envoyant pas de valeur inchangée. Le
geste reste armé, le clic suivant passe, et la coupe aurait de toute façon été la
même.

### Le brief écartait le retour au survol ; il ne coûtait rien

« Pas de curseur d'angle ni de glissement continu — dans Streamlit, chaque cran
relancerait le script. » Le raisonnement est juste, mais il ne vaut que côté
Python. Un trait dessiné par Leaflet dans le navigateur ne relance rien du tout :
rien ne remonte à Streamlit tant que le chef de projet n'a pas cliqué.

Le trait d'aperçu qui suit la souris a donc été ajouté après coup, à la demande du
chef de projet, et il repose sur une propriété que le brief n'énonçait pas :
déplacer la coupe la **translate en bloc**, exactement. L'aperçu est la coupe
affichée translatée jusqu'au curseur, pas une coupe recalculée à chaque
mouvement. Écart au tracé réel mesuré à 1,3 cm, contre 45 cm pour un pixel de
carte au zoom 18.

Deux choses relevées seulement à l'usage, et qu'aucun test ne voyait :

- **Le trait devait se figer au clic.** Streamlit met une à deux secondes à
  rejouer le script, et pendant ce temps la carte affichée est encore l'ancienne.
  Un trait qui continuait d'y suivre la souris faisait croire que le clic n'avait
  pas pris — et recliquer n'arrangeait rien, le second point étant ignoré puisque
  le geste est désarmé dès le premier. Leaflet voit le clic tout de suite : le
  trait s'y fige, devient plein, et un bandeau annonce le relevé en cours.
- **La coupe n'est pas verticale à l'écran**, ce qui se lit comme un glissement
  parasite du trait quand on survole de haut en bas. C'est la convergence des
  méridiens : 0,745° à Saint-Cyr, le nord de grille du Lambert 93 n'étant pas le
  nord vrai auquel le Web Mercator s'aligne.

Ce qui manquait aux tests, ici, c'est qu'aucun n'exécute de JavaScript. La carte a
donc été rendue en page autonome et pilotée dans un navigateur — c'est là, et là
seulement, que ces deux points se sont vus.

### Comment le geste est mesuré

`AppTest` ne joue pas le contenu d'un composant `st_folium` : il en rend les
valeurs par défaut, `last_clicked` à None. Le composant est donc remplacé le temps
de deux tests, et **tout le reste du chemin est celui de l'application** —
armement, consommation du clic, translation, relevé du profil, contrôles. C'est ce
qui mesure les points 2, 3 et 4 de la validation au niveau de l'écran, et non
seulement au niveau de la géométrie.
