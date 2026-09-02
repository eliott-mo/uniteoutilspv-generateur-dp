# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 1 : socle

## Contexte

UNITe (développeur PV) doit déposer une trentaine de Déclarations Préalables pour des centrales photovoltaïques au sol de moins de 3 MWc. Ces dossiers étaient jusqu'ici sous-traités à une agence d'architecture (le recours à un architecte n'est pas obligatoire en DP). L'objectif est de les produire en interne.

Le dossier type comporte 8 planches A3 paysage plus une notice descriptive :

| Pièce | Contenu |
|---|---|
| Page de garde | Titre, MOA/MOE, photomontage, sommaire |
| DP 1-1 | Plan de situation 1:10 000 |
| DP 1-2 | Photo aérienne 1:5 000 |
| DP 1-3 | Plan de cadastre |
| DP 2 | Plan de masse |
| DP 3 | Coupes 1:50 et 1:300 |
| DP 4-1 / 4-2 | Postes, citerne, clôture, portails |
| DP 6/7/8 | Insertions paysagères (fournies, non générées) |
| DP 11 | Notice descriptive |

**Ce brief ne couvre que le socle** : le moteur de planche et les trois planches cartographiques. Voir « Hors périmètre » en fin de document.

---

## Objectif

Un package Python `dp_socle/` accompagné d'une application Streamlit minimale, produisant à partir d'un shapefile d'emprise et de quelques métadonnées projet :

- la page de garde
- DP 1-1 Plan de situation 1:10 000
- DP 1-2 Photo aérienne 1:5 000
- DP 1-3 Plan de cadastre
- le PDF assemblé

---

## Contraintes non négociables

1. **L'échelle doit être vraie à l'impression A3** (420 × 297 mm). Aucun ajustement automatique à la page, aucun redimensionnement après génération. Le calcul millimètres → mètres est explicite, isolé dans une fonction, et couvert par un test.
2. Sortie **PDF vectoriel** pour tout ce qui n'est pas fond raster.
3. Tout le traitement géométrique en **Lambert 93 (EPSG:2154)**.
4. **Aucune imagerie Google.** Sources IGN exclusivement.

---

## Architecture imposée

### Moteur de planche : composition SVG → PDF

Un gabarit SVG A3 paysage rempli programmatiquement, converti en PDF vectoriel via `cairosvg`.

Raison de ce choix : quatre des huit planches finales ne sont pas cartographiques (coupes, plans techniques). Un moteur unique évite d'avoir à maintenir deux chaînes graphiques distinctes.

API attendue, à concevoir pour être réutilisée par les lots suivants :

```python
class Planche:
    def __init__(self, titre, numero, projet, date, echelle=None)
    def zone_dessin(self) -> (x_mm, y_mm, w_mm, h_mm)
    def definir_echelle(self, denominateur)          # ex. 10000
    def emprise_terrain(self) -> bbox L93            # déduite de l'échelle + zone de dessin
    def ajouter_fond_raster(self, image, bbox_l93)
    def ajouter_geometrie(self, geom, style)         # shapely, en L93
    def ajouter_etiquettes(self, points, textes, style)
    def ajouter_legende(self, entrees, position)
    def rendre_pdf(self, chemin)
```

Le passage L93 → coordonnées SVG doit être une transformation unique et centralisée, dérivée de l'échelle. Ne pas la recalculer localement dans chaque fonction de dessin.

### Fonds cartographiques : WMS-R Géoplateforme en EPSG:2154

Utiliser `https://data.geopf.fr/wms-r/wms` avec `CRS=EPSG:2154`, la `BBOX` exacte calculée depuis l'échelle, et `WIDTH`/`HEIGHT` correspondant au DPI cible.

C'est important : cela évite tout mosaïquage de tuiles et toute reprojection. L'image revient directement à l'emprise et à l'échelle voulues. Ne pas partir sur du WMTS Web Mercator qu'il faudrait reprojeter.

Couches pressenties, **à vérifier via GetCapabilities au moment de l'implémentation** plutôt que de me faire confiance :

- Plan de situation : `GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2`
- Photo aérienne : `ORTHOIMAGERY.ORTHOPHOTOS`

DPI cible : 250 à A3. Cela donne environ 4134 × 2923 px pleine page ; ne demander que la zone de dessin.

### Cadastre

WFS Géoplateforme, couche parcellaire express (nom exact à confirmer via GetCapabilities). Récupérer les parcelles intersectant l'emprise élargie d'un tampon, tracer les limites en vectoriel, étiqueter les numéros de parcelle, et extraire section / numéro / contenance pour le tableau récapitulatif.

L'échelle de DP 1-3 est adaptative : choisir dans une liste de valeurs normalisées (1:500, 1:1000, 1:2000, 1:5000) la plus grande qui fasse tenir l'emprise plus 20 % de marge dans la zone de dessin.

---

## Spécification du gabarit A3

Format 420 × 297 mm.

- Cadre extérieur, marge 5 mm
- Cartouche en pied, hauteur 15 mm, pleine largeur
- Zone de dessin : le reste
- Bloc légende : encadré à fond blanc, en haut à gauche par défaut, position et dimensions paramétrables

### Cartouche

De gauche à droite :

1. Logo UNITe (~35 mm)
2. Nom du projet, et en dessous `PHASE: DP`
3. Titre de la planche, centré, dans une case large
4. Flèche nord
5. Trois cases : `ECHELLE`, `DATE`, `NUMERO`

Bandeau inférieur fin : à gauche `UNITe — {projet} — {date}`, à droite `Ceci n'est pas un plan d'exécution`.

**Interdictions :** aucune mention « maître d'œuvre » assortie d'un numéro d'inscription à l'ordre des architectes, aucune case de signature d'architecte. Le dossier ne doit pas se présenter comme un dossier d'architecte.

### Page de garde

- Logo UNITe
- `DÉCLARATION PRÉALABLE` / `PROJET DE CENTRALE PHOTOVOLTAÏQUE AU SOL` / `{COMMUNE} {CODE_POSTAL}`
- Bloc Maître d'ouvrage et Maître d'œuvre : UNITe, 139 rue Vendôme, 69006 LYON
- Emplacement pour une image de perspective (fournie en entrée, optionnelle — si absente, réserver la place proprement sans bloc vide disgracieux)
- Sommaire généré automatiquement, avec les numéros de page réels après assemblage

### Typographie

Corps de texte et cartouche en **Aptos**, justifié pour les blocs de texte suivis.

⚠️ Aptos est une police Microsoft, absente des environnements Linux et de Streamlit Community Cloud. **Embarquer le fichier TTF dans le dépôt** et le référencer explicitement dans le SVG. Prévoir une police de repli déclarée, et un message d'avertissement au démarrage si la police n'est pas trouvée — pas un repli silencieux, qui produirait des planches à la mise en page décalée sans que personne ne le voie.

---

## Entrées

Un fichier `projet.json` :

```json
{
  "nom": "ALR_45_Bray-Saint-Aignan",
  "commune": "Bray-Saint-Aignan",
  "code_postal": "45460",
  "date": "2026-09-01",
  "emprise": "chemin/vers/emprise.zip",
  "image_garde": "chemin/vers/perspective.jpg"
}
```

L'application Streamlit doit permettre de saisir ces champs et de téléverser les fichiers, puis d'écrire ce JSON. Le JSON est le format pivot : une correction de dernière minute doit se faire en modifiant une valeur et en régénérant, pas en recommençant la saisie.

---

## Sorties

Dans `sortie/{nom_projet}/` : un PDF par planche, plus `DP_complet.pdf` assemblé dans l'ordre du sommaire.

---

## Pièges identifiés

- L'emprise peut contenir plusieurs polygones → traiter l'union, pas seulement le premier
- Le shapefile arrive généralement en ZIP → gérer les deux cas
- **Vérifier le CRS du shapefile et reprojeter si nécessaire. Ne pas supposer qu'il est en 2154.** Si le `.prj` est absent, refuser explicitement plutôt que de deviner
- En Lambert 93, le nord de la grille diffère du nord géographique (convergence des méridiens, jusqu'à environ 3° en métropole). Pour une DP, orienter la flèche selon le nord de la grille, et ne rien affirmer d'autre
- Toujours `.convert("RGB")` avant conversion PDF via PIL — critique pour la mémoire
- Demander le fond WMS exactement à la bbox de la zone de dessin à l'échelle voulue, et non plus large puis recadré : le recadrage réintroduit une erreur d'échelle
- Le dossier de référence de l'agence pèse 132 Mo à cause d'une image non compressée. Contrôler le DPI et viser moins de 25 Mo pour l'assemblage complet

---

## Critères de validation

1. **Test automatique d'échelle** : générer une planche à 1:10 000, y placer un segment de longueur terrain connue, mesurer sa longueur dans le PDF produit. Écart attendu inférieur à 0,5 %. Ce test doit exister et passer.
2. Générer le dossier complet pour Bray-Saint-Aignan et le comparer visuellement au dossier de référence de l'agence.
3. `DP_complet.pdf` inférieur à 25 Mo.
4. Aucun avertissement de dépendance à l'exécution.

---

## Règles de travail

### Portée des modifications

- **Un problème à la fois.** Pas de refactoring opportuniste, pas d'amélioration non demandée.
- **Ne pas toucher aux sections non concernées** par la tâche en cours, même si elles semblent perfectibles.
- Commit après chaque étape validée, avec un message décrivant ce qui a été fait.

### Aucun repli silencieux

C'est la règle la plus importante de ce lot. Une planche fausse qui s'affiche correctement est pire qu'une erreur bloquante, parce que personne ne la détecte avant l'instruction du dossier.

Toute substitution ou valeur par défaut appliquée en cours d'exécution doit produire un message visible dans l'interface :

- police introuvable → avertissement explicite, pas de repli muet
- couche WMS/WFS qui ne répond pas → erreur, pas de fond blanc silencieux
- CRS du shapefile absent ou inattendu → refus explicite, pas de supposition
- géométrie vide ou dégénérée → erreur nommée

### Vérifier plutôt que supposer

- Les identifiants de couches Géoplateforme donnés dans ce brief sont indicatifs. **Les confirmer via GetCapabilities** avant de les câbler.
- Ne pas écrire de code réseau non testé. Si une API ne se comporte pas comme décrit ici, le signaler plutôt que de contourner.

### Tester réellement le rendu

Le critère n'est pas « le code s'exécute sans erreur » mais « le PDF produit est correct ». Ouvrir les PDF générés, mesurer, comparer. Le test d'échelle décrit plus bas doit être un test réel sur le fichier de sortie, pas sur les valeurs intermédiaires.

### Contraintes d'environnement

- Déploiement visé : Streamlit Community Cloud, dépôt GitHub.
- **Épingler les versions dans `requirements.txt`.** Des incompatibilités Starlette/Streamlit ont déjà provoqué des plantages au déploiement sur d'autres outils de ce parc.
- `cairosvg` nécessite des bibliothèques système (`libcairo2` et dépendances). Elles doivent figurer dans un `packages.txt` **placé à la racine du dépôt, avec des fins de ligne LF et non CRLF** — sinon Streamlit Cloud l'ignore silencieusement.
- Streamlit : utiliser le paramètre `width` et **non `use_container_width`**, qui est déprécié. Ne pas introduire d'appels à l'ancienne API dans du code neuf.
- Limiter les dépendances au strict nécessaire : `streamlit`, `shapely`, `geopandas` ou `pyshp`, `pyproj`, `cairosvg`, `pypdf`, `Pillow`, `requests`. Toute dépendance supplémentaire doit être justifiée.

---

## Hors périmètre — ne pas commencer

- Import DXF HelioScope et calage géographique (lot 2)
- Saisie des pistes, postes, clôtures (lot 3)
- DP 2, DP 3, DP 4 (lot 4)
- Traitement de la notice DP 11 (lot 5)
- Interface Streamlit élaborée : un formulaire simple et un bouton suffisent à ce stade

Concevoir néanmoins l'API `Planche` en gardant ces lots à l'esprit, pour qu'ils s'y branchent sans refonte.
