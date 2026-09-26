# Générateur de dossier DP — conventions du dépôt

Production interne des dossiers de déclaration préalable pour les centrales
photovoltaïques au sol de moins de 3 MWc, chez UNITe. Voir `README.md` pour le
fonctionnement, ce fichier pour les conventions de travail.

## Découpage en lots

| Lot | Contenu | État |
|---|---|---|
| 1 | Moteur de planche, page de garde, DP 1-1, DP 1-2, DP 1-3 | livré |
| 2 | Import DXF HelioScope et calage géographique | livré, en réserve |
| 2bis | Import du plan du BE interne, contrôles croisés, coupe A-A' | livré |
| 2ter | Import d'un plan projet PDF, calé sur les tables d'un export HelioScope | livré |
| 3 | Saisie des pistes, postes, clôtures | remplacé par le lot 2bis |
| 4 | DP 2, DP 3, DP 4 | livré |
| 5 | Notice DP 11, fournie en PDF par le chef de projet | livré |
| 6 | DP 6, DP 7, DP 8 et leurs plans de repérage | livré ; saisie retirée de l'interface au lot 8 |
| 7 | Reprise d'un dossier produit, pour le compléter | à venir, brief écrit |
| 8 | Sortie PowerPoint à finaliser, pour le volet photographique | livré |

Le lot 2bis remplace les lots 2 et 3 pour les dossiers dont le BE interne
fournit le plan final. Le lot 2 reste en réserve pour les projets sans plan BE,
et produit depuis le 03/09/2026 **le même contrat de sortie** que le lot 2bis :
un `geometries.gpkg` et un `projet.json` dans `sortie/{projet}/`, à
`version_contrat` égale, distingués par leur champ `origine`. Le lot 2ter en
est le troisième producteur depuis le 23/09/2026 : un plan projet PDF, calé sur
les tables que le lot 2 a posées, en aval de lui et non à sa place. Le lot 4
lira une seule structure sans savoir de quel lot vient le dossier. Le test
`tests/test_contrat_helioscope.py::test_les_trois_producteurs_ecrivent_le_meme_schema`
est ce qui empêche les producteurs de repartir chacun de leur côté :
n'ajoutez une couche ou une colonne d'un côté qu'en la traitant des deux autres.

**Ce contrat a un consommateur hors du dépôt.** Le dépôt voisin `photomontage`
le lit depuis le 24/09/2026 (`photomontage/lecture_contrat.py`) et ne relit plus
aucun plan. Le test ci-dessus protège l'amont, pas l'aval : une couche retirée ou
renommée ici casse le photomontage sans que rien ne le dise. Le contrat
redescend avec le dossier, en archive, pour que le chef de projet puisse le
transmettre — voir `contrat.archiver_le_contrat`.

Les briefs sont dans `_briefs/`, versionnés : ce qui survit d'un lot terminé,
ce sont les écarts documentés entre le brief et ce que la mesure a montré, et on
ne peut les relire sans le texte d'origine.

**Une conversation par lot pour le construire, une conversation neuve pour toute
modification ultérieure.** Le dépôt est le dépôt de mémoire, pas la conversation :
`README.md`, les tests et les messages de commit sont écrits pour être lus à
froid. Reprendre une conversation ancienne fait raisonner sur un état du code qui
n'existe plus, ce qui se voit rarement tout de suite.

## Règles non négociables

**Aucun repli silencieux.** C'est la règle qui prime sur tout le reste. Une
planche fausse qui s'affiche correctement est pire qu'une erreur bloquante,
parce que personne ne la détecte avant l'instruction du dossier. Toute
substitution ou valeur par défaut appliquée en cours d'exécution doit produire
un message visible ou une exception nommée de `dp_socle/erreurs.py`. Pas de
`except: pass`, pas de valeur par défaut muette, pas de fond blanc de
remplacement quand un service ne répond pas.

**Vérifier plutôt que supposer.** Les identifiants de couches, les noms
d'attributs, le comportement des bibliothèques : confirmer par une requête ou
une lecture du code source avant de câbler, et noter la date de vérification en
commentaire. Plusieurs affirmations plausibles des briefs se sont révélées
fausses à la mesure.

**Une erreur d'environnement se signale au démarrage, pas au dernier
moment.** Sans cairo, la génération échouait après le téléchargement de tous les
fonds IGN, et le diagnostic accusait la police alors que la cause était la
bibliothèque de rendu. Ce qui bloque doit être dit avant de travailler, et
désigner la vraie cause.

**Tester le résultat, pas l'exécution.** Le critère n'est pas « le code tourne »
mais « le PDF produit est correct ». `tests/test_echelle_pdf.py` mesure un
segment dans le flux de contenu du PDF de sortie, pas dans les valeurs
intermédiaires. Suivre ce modèle.

**Un problème à la fois.** Pas de refactoring opportuniste, pas de modification
de sections non concernées. En particulier, les lots suivants ne touchent pas au
moteur `Planche` du lot 1.

**Commit après chaque étape validée**, message en français décrivant ce qui a
été fait et pourquoi.

## Conventions de code

- Tout en français : noms de modules, de fonctions, de variables, docstrings,
  commentaires, messages d'erreur. Accents compris.
- Exceptions nommées dans `dp_socle/erreurs.py`, toutes dérivées de `ErreurDP`.
- Les commentaires expliquent *pourquoi*, pas *quoi* — souvent un piège
  rencontré et mesuré.
- Dépendances limitées au strict nécessaire, versions épinglées dans
  `requirements.txt`, toute ajout justifié par un commentaire dans le fichier.

## Pièges de l'environnement

- **Windows, cairo** : CairoSVG ne trouve pas `libcairo-2.dll` seul.
  `dp_socle/environnement.py` fouille les emplacements connus (Tesseract, GTK,
  Inkscape, GIMP, msys2) et dit lequel il retient. `DP_CAIRO_DLL_DIR` reste
  prioritaire si la DLL est ailleurs ; renseignée mais fausse, elle lève.
  Inutile sous Linux.
- **Le poste de développement n'est pas la cible.** On développe sous Windows,
  on déploie sous Linux, et deux défauts sont tombés en production le
  26/09/2026 que la suite verte sur Windows ne pouvait pas voir : des métriques
  de police crénées par FreeType et ignorées par DirectWrite, et un import non
  déclaré dans `requirements.txt`. `.github/workflows/tests.yml` rejoue donc la
  suite sur `ubuntu-latest` à chaque poussée. Un vert local ne suffit plus à
  dire qu'un lot est livrable.
- **Console Windows** : préfixer les commandes Python par
  `PYTHONIOENCODING=utf-8`, sinon les accents lèvent une `UnicodeEncodeError` à
  l'affichage.
- **Police Aptos** : cairo passe par DirectWrite sous Windows et ne voit que les
  polices installées sur le poste. Le TTF embarqué ne suffit pas en
  développement, il faut l'installer. Voir `dp_socle/polices.py`.
- **Fins de ligne** : `.gitattributes` force le LF. Un `packages.txt` en CRLF est
  ignoré silencieusement par Streamlit Community Cloud.
- **Streamlit** : utiliser le paramètre `width`, jamais `use_container_width`.
- **PIL** : `.convert("RGB")` avant toute conversion PDF, et aplatir sur blanc
  les images à canal alpha — un `convert("RGB")` direct remplit de noir.

## Repères

- Tout le traitement géométrique en **Lambert 93 (EPSG:2154)**.
- L'échelle doit être vraie à l'impression A3, sans ajustement à la page. La
  conversion millimètres/mètres est isolée dans `dp_socle/echelle.py` et ne doit
  être refaite nulle part ailleurs.
- Fonds cartographiques **IGN exclusivement**, jamais Google.
- Le dossier ne se présente pas comme un dossier d'architecte : ni mention
  d'ordre des architectes, ni case de signature.
- `projet.json` est le format pivot : une correction se fait en modifiant une
  valeur et en régénérant.

## Commandes

```bash
python -m pytest -q
streamlit run app.py
```

Le dossier de référence de l'agence, pour comparaison visuelle, est le dossier
HOCH « Les Islettes (55) » du 25/04/2024.
