# Générateur de dossier DP — conventions du dépôt

Production interne des dossiers de déclaration préalable pour les centrales
photovoltaïques au sol de moins de 3 MWc, chez UNITe. Voir `README.md` pour le
fonctionnement, ce fichier pour les conventions de travail.

## Découpage en lots

| Lot | Contenu | État |
|---|---|---|
| 1 | Moteur de planche, page de garde, DP 1-1, DP 1-2, DP 1-3 | livré |
| 2 | Import DXF HelioScope et calage géographique | en cours |
| 3 | Saisie des pistes, postes, clôtures | à venir |
| 4 | DP 2, DP 3, DP 4 | à venir |
| 5 | Notice DP 11 | à venir |

Les briefs sont dans `_briefs/`, non versionnés.

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

- **Windows, cairo** : CairoSVG ne trouve pas `libcairo-2.dll` seul. Exporter
  `DP_CAIRO_DLL_DIR="$LOCALAPPDATA/Programs/Tesseract-OCR"` avant de lancer les
  tests ou l'application. Inutile sous Linux.
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
