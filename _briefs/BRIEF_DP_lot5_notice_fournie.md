# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 5 : la notice DP 11 fournie

> Lots 1, 2, 2bis et 4 livrés. Ce lot **n'écrit pas** la notice : le chef de
> projet la fournit en PDF, l'outil l'intègre au dossier sous l'habillage des
> autres pièces. La mise en forme automatique de la notice est remise à plus
> tard — décision du 14/09/2026, « trop tôt pour l'envisager ».
>
> Lire `README.md` et `CLAUDE.md` avant de commencer : ce brief ne les répète
> pas.

---

## Objectif

Une pièce de plus au dossier, **DP 11 Notice**, produite à partir d'un PDF
déposé :

| Entrée | Sortie |
|---|---|
| un PDF de N pages, déposé par le chef de projet | N planches A3 paysage portant le cadre et le cartouche du dossier, et le contenu fourni à l'intérieur |

`dp_socle/dossier.py:60` déclare aujourd'hui `Piece("DP 11", "Notice",
mention="lot 5")` : la basculer en `produite=True`, et vérifier que le sommaire
paginé et le contrôle de rang de `assemblage.py` suivent — c'est le geste du
lot 4, avec une difficulté de plus (D3).

---

## Ce qui a été mesuré avant d'écrire ce brief

Le 14/09/2026, sur une notice A4 portrait de synthèse et une planche réelle.
**Le geste marche**, et voici ses chiffres :

| Mesure | Valeur |
|---|---|
| Zone de dessin d'une planche à cartouche | **410 × 268 mm**, à (5, 5) |
| A4 portrait ajusté à cette zone | facteur **0,9024** → 189 × 268 mm |
| Blanc restant de part et d'autre | **110 mm de chaque côté** |
| Format des pages produites | 420 × 297 mm, conforme |
| Texte de la notice après fusion | **resté vectoriel** — retrouvé par extraction à y = 28 mm et 43 mm, donc sélectionnable et indexable |
| Cartouche après fusion | intact, 11 blocs sous 270 mm |

Le script de mesure est reproductible ; il pose une notice A4 dans le cadre avec
`pypdf.Transformation().scale(f, f).translate(gauche, bas)` et relit le résultat
avec PyMuPDF. **Piège rencontré** : `preparer_cairo()` doit être appelé avant
d'importer `Planche`, sinon `rendre_pdf` lève `ErreurRendu` sur cairo — c'est
`app.py` qui s'en charge d'ordinaire.

---

## Ce qui existe déjà, et qu'il faut aller lire

| Brique | Où | Ce qu'elle donne |
|---|---|---|
| Gabarit A3, cadre, cartouche | `dp_socle/planche.py:37-64` ; `zone_dessin()` l. 185-189 | la planche vide, et la zone utile au millimètre |
| Fusion de pages PDF | `pypdf` 6.16.2, déjà épinglé — `merge_transformed_page`, `Transformation` | poser un PDF fourni dans le cadre, **sans rasteriser** |
| Pagination multi-pages | `dp_socle/assemblage.py:153-158` — `nb = _nb_pages(...)`, `pages[...] = (debut, debut + nb - 1)` | une pièce qui tient sur plusieurs pages est **déjà** prévue |
| Dépôt de fichiers dans l'application | `app.py` `_deposer`, `_enregistrer_photos` | le patron du dépôt et de l'écriture dans `projets/{nom}/` |

---

## Décisions prises en amont

### D1 — Une page fournie donne une page du dossier

Ajuster chaque page du PDF à la zone de dessin, **au plus grand facteur qui la
fasse tenir**, centrée. Une page fournie, une page de dossier.

Ne pas chercher à loger deux pages A4 côte à côte : elles tiendraient
(2 × 189 = 378 mm pour 410 disponibles), mais la pagination de la notice cesserait
alors de correspondre à celle du dossier, et le sommaire pointe une page. Le
blanc latéral est le prix d'un dossier homogène en A3 paysage.

C'est réversible si l'usage montre que le blanc gêne : la décision tient au
sommaire, pas à la technique.

### D2 — Le format fourni ne se suppose pas, il se lit

Ne rien câbler sur A4 portrait. Lire `mediabox` de chaque page et calculer le
facteur d'ajustement. Une notice déjà produite en A3 paysage passera au facteur
1, sans que rien ne paraisse.

**Et le dire** : le rapport de génération annonce le format détecté, le facteur
appliqué et le nombre de pages. Une notice réduite à 40 % parce qu'elle arrive en
A2 est exactement le genre de chose qui doit se voir avant l'instruction, pas
après.

Refuser en revanche, avec une exception nommée de `dp_socle/erreurs.py` :

- un fichier qui n'est pas un PDF lisible ;
- un PDF **sans page** ;
- un PDF dont une page est si grande que le facteur tombe sous un seuil à fixer à
  la mesure — une notice illisible n'est pas une notice.

### D3 — Le cartouche annonce le numéro de **page**, pas celui de la pièce

C'est la difficulté de ce lot, et elle est réelle.

`assemblage.py:147-152` lève `ErreurRendu` quand le cartouche annonce une planche
et que la pièce tombe sur une autre page — garde-fou écrit au lot 4, et
`numero_planche()` « suppose une page par pièce ».

Le dossier de référence tranche : Massay porte sa notice sur deux pages A3, et
leurs cartouches annoncent **NUMERO 16** puis **NUMERO 17**. Chaque page porte
son propre numéro.

Il faut donc que le générateur de la notice sache, pour chacune de ses pages, le
rang qu'elle occupera dans le dossier assemblé. La notice étant la **dernière**
pièce, aucune pièce suivante n'est décalée : le problème est borné. Mais le
contrôle de rang doit apprendre qu'une pièce peut couvrir plusieurs pages, au
lieu de comparer un numéro unique.

### D4 — La notice se dépose dans la section 3

Elle n'est ni une métadonnée, ni un plan, ni une génération : elle est une pièce
fournie, comme les photographies. La section 3 s'intitule aujourd'hui
« Photographies et photomontages » ; elle devient l'endroit où l'on dépose **ce
que l'outil ne dessine pas**, et son titre doit le dire.

Le fichier suit le chemin de tout dépôt : `projets/{nom}/DP_11/`, écrit par le
même patron que `_enregistrer_photos`.

La notice est **facultative** : un dossier sans elle reste produit, et le rapport
dit qu'elle manque. C'est le comportement de `_charger_contrat_eventuel` pour le
plan, et il vaut ici pour la même raison — un dossier d'étude amont n'a pas de
notice.

### D5 — Le poids se surveille

Une notice de dix pages avec des photographies pèse vite. `assemblage.py` porte
déjà un contrôle de taille du dossier assemblé (`TAILLE_MAX_MO`) qui produira son
avertissement, et c'est suffisant : ne pas ajouter de seuil propre à la notice
sans l'avoir mesuré.

Rappel du contexte : 690 Mo garantis sur Streamlit Community Cloud, et la
génération culmine déjà à 367 Mo mesurés — 523 à 300 dpi.

---

## Le point qui demande un arbitrage

**Le cartouche d'une planche de notice porte une flèche nord et une case
d'échelle.** `planche.py:700-702` dessine `_fleche_nord()` **sans condition**, et
l. 706 affiche `"—"` dans la case d'échelle quand `echelle is None`.

Sur une notice, l'un et l'autre ne veulent rien dire. Le dossier de référence le
confirme : les pages 16 et 17 de Massay portent `Massay`, `PHASE: DPC`,
`NUMERO`, `DATE:` et `DPC 4 Notice` — **ni ÉCHELLE, ni NORD**, là où la page 2 du
même dossier porte `ECHELLE 1 : 10 000`.

Or `CLAUDE.md` est explicite : « les lots suivants ne touchent pas au moteur
`Planche` du lot 1 ». Trois voies, aucune gratuite :

1. **Accepter** la flèche nord et le tiret sur les pages de notice. Coût nul,
   mais l'écart au dossier de référence est visible, et un lecteur peut se
   demander ce que le nord vient faire là.
2. **Ajouter un paramètre** à `Planche` — par exemple `avec_reperes=False` —
   additif, par défaut sans effet sur les planches existantes. C'est la solution
   propre, et la seule qui garde un seul cartouche dans le dépôt. Mais elle
   **touche le moteur du lot 1**, ce que la règle interdit : il faut une
   autorisation explicite.
3. **Composer un cartouche réduit** dans le module du lot 5, avec
   `avec_cartouche=False` et les primitives publiques (`ajouter_rectangle`,
   `ajouter_texte`, `ajouter_ligne`). Respecte la règle à la lettre, mais
   **duplique la géométrie du cartouche** — deux cartouches à maintenir, qui
   divergeront le jour où l'un des deux bougera.

**Recommandation : la voie 2**, avec l'autorisation explicite du chef de projet
notée ici. Un paramètre additif dont la valeur par défaut ne change rien n'est
pas le refactoring opportuniste que la règle cherche à empêcher, et la voie 3
crée exactement le genre de divergence que ce dépôt passe son temps à éviter.

*(À compléter par la décision une fois prise.)*

---

## Critères de validation

Mesurés sur le PDF produit, jamais sur les valeurs intermédiaires.

1. Une notice A4 de trois pages donne **trois planches A3 paysage** de 420 × 297 mm.
2. Le **texte de la notice reste du texte** dans le PDF assemblé — extraction, pas
   inspection visuelle. C'est ce qui distingue cette solution d'une rasterisation.
3. Le contenu fourni **ne mord pas sur le cartouche** : rien du PDF déposé ne
   dépasse sous `Y_CARTOUCHE`.
4. Le **sommaire de la page de garde** annonce la bonne page de début, et le
   contrôle de rang de `assemblage.py` ne lève pas.
5. Chaque page de notice porte **son propre numéro** au cartouche.
6. Un dossier **sans** notice se produit quand même, et le rapport le dit.
7. Un PDF illisible, vide, ou réduit sous le seuil est **refusé par une exception
   nommée**, pas absorbé.
8. `tests/test_app_streamlit.py` suit le parcours : déposer la notice, générer,
   et la retrouver dans l'archive téléchargée.

---

## Ce que ce lot ne fait pas

La **mise en forme** de la notice par l'outil — composition du texte, reprise des
valeurs du tableau bilan, cohérence avec les planches. C'est le lot 5 tel qu'il
était prévu à l'origine, et il reste à faire un jour.

Le dépôt s'y prépare déjà sans le savoir : les hauteurs `point_bas_m` et
`point_haut_m` sont dessinées sur DP 3 **parce que** c'est ce que la notice
annoncera, l'inclinaison des tables est recoupée pour la même raison, et les
surfaces déclarées sont celles que la notice reprendra. Le jour venu, ces valeurs
seront prêtes et sourcées.
