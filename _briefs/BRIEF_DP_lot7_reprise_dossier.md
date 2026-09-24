# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 7 : reprise d'un dossier pour le compléter

> Lots 1, 2, 2bis, 2ter, 4, 5 et 6 livrés. Un dossier se génère aujourd'hui d'une
> traite : si une pièce manque, il faut tout refaire. Ce lot permet de **rouvrir
> un dossier déjà produit** pour y verser ce qui manquait.
>
> Lire `README.md` et `CLAUDE.md` avant de commencer : ce brief ne les répète pas.

---

## Objectif

Le cas d'usage qui l'a demandé (retour d'usage du 24/09/2026) : **les
photomontages sont produits en parallèle du dossier**, par une autre personne et
sur un autre calendrier. Le chef de projet veut préparer le dossier complet,
l'envoyer en relecture sans sa DP 6, et n'avoir plus qu'à y insérer le
photomontage quand il arrive — sans replacer les sept points de vue qu'il a
déjà posés.

Ce n'est pas propre à la DP 6 : une notice qui arrive en retard, une photo à
remplacer, une emprise corrigée posent le même problème.

---

## Ce qui existe déjà, et qu'il faut aller lire

**La mécanique est là ; c'est l'écran qui manque.** La génération ne lit jamais
le DXF : elle lit deux fichiers, tous deux sur le disque après le premier
passage.

| Fichier | Ce qu'il porte | Taille mesurée (Sarnois) |
|---|---|---|
| `projets/{nom}/projet.json` | emprise, notice, voirie, **et toutes les prises de vue** — position Lambert 93, cap, cadrage, origine | 4 Ko |
| `projets/{nom}/DP_6\|DP_7\|DP_8/` | les images elles-mêmes, **copiées** — plus de dépendance au poste | 5,4 Mo |
| `sortie/{nom}/geometries.gpkg` + `projet.json` | le plan du BE, déjà trié | 750 Ko |

Les deux dossiers portent le **même identifiant** : `nom = _nom_dossier(commune)`
(`app.py:3868`), et `generer_dossier` cherche le contrat dans
`sortie/{projet.nom}/`.

| Brique | Où | Ce qu'elle donne |
|---|---|---|
| Lecture d'un `Projet` | `dp_socle/projet.py:259` `charger()` | valide, résout les chemins relatifs, refuse une image disparue en le disant. **Écrite, jamais appelée par l'écran.** |
| Lecture du plan sans le DXF | `dp_socle/contrat.py:472` `charger_contrat()` | GeoPackage + `projet.json` de sortie → tout ce que les planches demandent |
| Reprise partielle déjà en place | `app.py:1602` `_reprendre_import_precedent` | reprend le tracé de coupe d'un import précédent : le patron à étendre |
| Photo déjà sur disque | `app.py:2980` `_PhotoReprise`, `app.py:2727` `_photos_reprises()` | la structure d'accueil existe — écrite pour le versement depuis un rapport HTML, elle vaut telle quelle ici |
| Écriture des photos | `app.py:311` `_enregistrer_photos`, `app.py:3914` `_photographies_du_projet` | le format exact à relire |

---

## Décisions prises en amont

### D0 — Un fichier de reprise téléchargé, pas un dossier qui attend sur le serveur

**Le serveur ne garde rien.** `projets/` et `sortie/` sont relatifs au dossier
courant (`dp_socle/environnement.py:182`), et la cible de déploiement
— Streamlit Community Cloud — réinitialise le conteneur à chaque mise en veille
ou redéploiement. Un chef de projet qui revient trois semaines plus tard ne
retrouvera rien.

La reprise passe donc par un **ZIP que le chef de projet télécharge et
conserve**, à côté de son dossier PDF, et redépose au second passage. Mesuré à
**~7 Mo** sur Sarnois, notice exclue.

### D1 — Ce que le ZIP contient

- `projet.json` du lot 1 ;
- les images de `DP_6/`, `DP_7/`, `DP_8/` ;
- l'emprise cadastrale (le ZIP du cadastre déposé en section 1) ;
- `geometries.gpkg` et le `projet.json` du contrat.

**Pas la notice DP 11** (décision du 24/09/2026) : 776 Ko sur Sarnois, et c'est
justement la pièce qu'on redépose volontiers — elle change plus souvent que le
plan.

### D2 — Le cartouche porte la date de la génération

Décision du 24/09/2026. Un dossier repris en novembre sort daté de novembre,
pas de sa date d'origine. C'est la date de ce qui est déposé qui compte.

Conséquence : le champ `date` de `projet.json` n'est pas repris tel quel, il est
réécrit. À vérifier sur les planches qui l'affichent.

### D3 — Régénération complète, pas sélective

Tentant de ne régénérer que la pièce ajoutée ; à ne pas faire. Le motif est
observé : `sortie/PV-Sarnois-IND10B/` porte aujourd'hui un
`DP_7_environnement_proche.pdf` de 21 h 59 et onze planches de 00 h 03. Ce
dossier est déjà mi-vieux mi-neuf et **rien ne le dit**. Industrialiser la
génération sélective généraliserait ce travers.

Le coût est le retéléchargement des fonds IGN, quelques minutes. Pour un dossier
qu'on ne dépose qu'une fois complet, le risque qu'une ortho IGN change
entre-temps est théorique.

### D4 — Un plan plus récent ne s'écrase pas en silence

Si le chef de projet a reçu un IND11 entre-temps, l'écran dit « ce dossier porte
le plan IND10B du 17/09 » et lui laisse le remplacer **explicitement**. Reprendre
le vieux plan sans le dire serait le repli silencieux que `CLAUDE.md` interdit.

Même règle pour toute pièce du ZIP plus ancienne que ce que l'écran propose.

### D5 — Le PDF n'est pas une entrée

Question posée le 24/09/2026 : le chef de projet redépose-t-il le PDF incomplet
qu'on lui a fourni ? Non. Le PDF porte le *dessin* des points de vue, pas leurs
coordonnées. On n'en revient pas à l'état de travail.

---

## À corriger avant tout : les chemins Windows dans `projet.json`

**Défaut mesuré le 24/09/2026, qui casse la reprise et probablement déjà le
déploiement.** Les chemins y sont écrits avec des antislashs :

```json
"images": ["projets\PV-SARNOIS-IND10B\DP_7\IMG_6945.jpg"]
```

Sous Linux, `PurePosixPath` n'y voit pas un chemin mais **un seul nom de
fichier** :

```python
PureWindowsPath(x).parts  # ('projets', 'PV-SARNOIS-IND10B', 'DP_7', 'IMG_6945.jpg')
PurePosixPath(x).parts    # ('projets\PV-SARNOIS-IND10B\DP_7\IMG_6945.jpg',)
```

`_resoudre_photographies` (`dp_socle/projet.py:325`) teste alors
`(base / image).exists()`, qui est faux, garde la chaîne telle quelle, et
`valider_photographies` lève « image introuvable ». Un `projet.json` écrit sous
Windows est illisible sous Linux.

Écrire les chemins en **relatif au dossier du `projet.json`, séparés par des
`/`** — `as_posix()` — et vérifier par un test qui relit un `projet.json` avec
`PurePosixPath`, sans quoi le défaut ne se verra pas davantage en
développement qu'aujourd'hui.

---

## Ce qu'il ne faut pas faire

- **Ne pas toucher au moteur `Planche` du lot 1**, ni aux planches du lot 6.
  Ce lot ajoute une entrée, il ne change pas ce qui est dessiné.
- **Ne pas inventer un second format pivot.** `projet.json` reste le format ;
  le ZIP n'est qu'un emballage de transport.
- **Ne pas rendre la reprise obligatoire** : le parcours d'aujourd'hui, d'une
  traite, reste le parcours normal.
