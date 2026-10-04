# BRIEF DP, lot 9 : locaux techniques surélevés en zone inondable

> Lots 1 à 8 livrés. Les planches DP 4 dessinent les ouvrages posés au sol, sur
> leur socle. Ce lot leur ajoute le cas des **locaux techniques surélevés
> au-dessus des plus hautes eaux**, imposé par un PPRI.
>
> Lire `README.md` et `CLAUDE.md` avant de commencer : ce brief ne les répète
> pas. En particulier, les règles « aucun repli silencieux » et « vérifier
> plutôt que supposer » s'appliquent telles quelles.

---

## Objectif

Le cas qui l'a demandé, remonté le 02/10/2026 sur **Saint-Cyr-en-Val** : le PPRI
impose que les locaux techniques soient surélevés au-dessus de la cote des plus
hautes eaux connues. Sur ce projet la surélévation vaut **2,25 m**, et la notice
DP 11 la décrit déjà. Le DXF du bureau d'études, lui, ne la porte pas : il donne
une emprise au sol, et les planches DP 4 dessinent donc des postes posés à
terre, ce qui contredit le dossier qui les accompagne.

Une planche fausse qui s'affiche correctement est pire qu'une erreur bloquante
(règle du dépôt) : ici, la planche est fausse et personne ne le voit avant
l'instruction.

**Le lot a été réduit à l'examen du 04/10/2026**, et ce qu'il reste tient en une
phrase : *deux cotes relatives saisies, un dessin de plus sur les blocs DP 4.*
Ce qui en faisait un lot entier — le contrat, le photomontage, la coupe A-A' —
en est sorti par la décision D5. Voir « Ce que le lot ne touche pas ».

---

## La référence

`3.5. PC5_UNITe-Périgny-la-Rose_Dossier_Archi.pdf`, page 2 — planche HOCH
« PC 5-1 Poste de livraison : façade et coupe », du 26/05/2025, au 1:100. C'est
le modèle à suivre. Elle porte, sur les quatre élévations **et** sur la coupe :

- une **plateforme sur pilotis**, le poste posé dessus ;
- un **garde-corps** sur tout le pourtour de la plateforme ;
- un **escalier d'accès** latéral, avec son palier ;
- la **ligne PHEC** en pointillé bleu, légendée « PHEC (0,45 m) » et, en pied de
  cadre, « PHEC : Plus Hautes Eaux Connues » ;
- les cotes : surélévation (0,55 m à Périgny), hauteur du poste (3,0 m), et la
  hauteur totale (« max 5,0 m »).

**Mesure qui a tranché la saisie** : l'étiquette HOCH cote `PHEC (0,45 m)` pour
une surélévation de 0,55 m. Les deux sont des **hauteurs au-dessus du terrain
naturel**, pas des cotes NGF, et elles diffèrent de 10 cm — la revanche. À
Saint-Cyr la revanche est de 30 cm. C'est ce qui interdit de déduire l'une de
l'autre, et c'est aussi ce qui montre qu'aucun NGF n'est nécessaire.

Sur Saint-Cyr la surélévation est de 2,25 m, soit quatre fois celle de Périgny :
l'escalier y compte plus de marches, et la vérification à l'épreuve A3 est à
refaire — une volée qui tient à 0,55 m peut ne plus tenir à 2,25 m.

---

## Décisions

**D1 — Deux cotes saisies, toutes deux relatives au terrain naturel.** Le PPRI
est un document d'urbanisme : aucune API ne donne la cote des plus hautes eaux
en un point. Les valeurs sont donc **saisies**, et rejoignent `projet.json`,
format pivot du dépôt.

| Champ | Saint-Cyr | Rôle au dessin |
|---|---|---|
| Surélévation du plancher au-dessus du terrain naturel | 2,25 m | pilotis, assise de la plateforme, garde-corps, marches, pied des parois |
| Niveau des plus hautes eaux au-dessus du terrain naturel | 1,95 m | pointillé bleu et son étiquette |

La seconde est **facultative** : renseignée, elle trace la ligne PHEC comme
HOCH ; vide, il n'y a pas de pointillé et le reste est dessiné quand même. Le
chef de projet calcule ces deux hauteurs depuis les éléments de son dossier —
à Saint-Cyr, 97,75 − 95,50 et 97,45 − 95,50.

**Aucune cote NGF, nulle part.** Ni saisie, ni dessinée, ni écrite aux
caractéristiques. C'est une décision du chef de projet du 04/10/2026, et sa
raison est la bonne : *« l'idée est surtout d'avoir une surélévation relative
sur le dessin pour l'autorisation d'urbanisme, pas d'avoir des NGF »*. Une cote
absolue sur la planche devrait s'accorder avec la topographie relevée — le
profil RGE ALTI de DP 3, le relevé du géomètre — et un désaccord de 50 cm entre
deux pièces du même dossier serait exactement la contradiction qu'on cherche à
éviter. En relatif il n'y a rien à accorder : voir D5.

**D2 — Tous les locaux techniques, pas seulement les postes.** `POSTES`
(`pdl_ptr`, `ptr`, `pdl`) et `CONTENEURS` (`bess`, `local_technique`). Les
citernes (`CITERNES`) sont des cuves ancrées, pas des locaux : le chef de projet
a dit « tous les locaux techniques », ce qui les exclut en bonne lecture. La
question mérite d'être reposée sur un projet réel qui en porte une en zone
inondable.

**D3 — Le dessin suit HOCH, escalier compris.** L'objection soulevée à l'examen
— le générateur ne sait pas de quel côté va l'escalier, et en placer un au
hasard serait inventer — a été écartée par le chef de projet : « si l'escalier
change, ça pourra se faire facilement en demandant une modification de
l'autorisation ». L'escalier est donc dessiné d'un côté choisi par convention,
et **la convention doit être écrite dans le code et dans le dossier** pour que
le bureau d'études sache ce qu'il regarde.

**D4 — Saisie discrète, constat au rapport.** Un volet replié dans la section 2,
sur les **deux** parcours d'import, titré en clair (« Locaux techniques
surélevés — PPRI »), champs vides par défaut. Un chef de projet non concerné lit
le titre et passe.

Le dépôt a déjà payé le pari du volet replié : celui des intitulés de légende
l'était, présenté comme un recours, et le commentaire de `_retoucher_la_legende`
dit ce qui s'est passé le 26/09/2026 — « le chef de projet passait dessus sans
le voir ». Il a fallu l'ouvrir d'office. La discrétion est donc tenable **à
l'entrée seulement**, et elle se paie par une ligne de constat au rapport de
génération quand rien n'est saisi : « Locaux techniques posés au sol : aucune
surélévation saisie. » Sans icône et sans alerte — le régime du rapport, qui
dit ce que l'outil a fait. Ajouter une alerte à 95 % des dossiers irait contre
l'allègement du 02/10/2026, qui a ramené les messages visibles de 23 à 14.

**D5 — Rien ne sort des planches DP 4.** La surélévation n'entre **pas** au
contrat, ne touche **pas** `dp3_coupes.py`, et n'est **jamais** recoupée avec
l'altimétrie ni avec le tableau bilan. Ce n'est pas un choix de commodité, c'est
ce qui rend D1 sûr : les blocs DP 4 tracent leur propre ligne de sol à `y = 0`
(`sol_hachure` à zéro, socle à partir de zéro), donc **la planche ne prétend à
aucune altitude** et il n'y a rien à contredire.

Conséquence assumée : le dépôt voisin `photomontage` continuera de monter ses
vues sur des locaux posés au sol. À rouvrir si un photomontage de projet en PPRI
se révèle faux à l'œil — mais c'est une décision qui se prend avec lui, pas ici.

**D6 — Un seul contrôle, interne aux deux nombres.** Si les deux sont
renseignées, la PHEC doit être sous le plancher ; sinon le dessin se contredit
lui-même. Rien d'autre : pas de plafond de vraisemblance inventé, pas de
contrôle de topographie.

---

## Ce que le lot touche

- `dp_socle/planches/dp4_ouvrages.py` : `_bloc_volume` (plan de toiture, quatre
  élévations, coupe) et `_bloc_conteneur`. Les hauteurs de vue, les cotes et le
  calcul d'échelle des blocs (`_echelles_des_blocs`) changent avec la
  surélévation — une vue plus haute de 2,25 m peut faire tomber la planche sous
  l'échelle qui la logeait.
- `dp_socle/projet.py` et `app.py` : la saisie et le report dans `projet.json`.
- Le rapport de génération : la ligne de constat de D4.

## Ce que le lot ne touche pas

Tranché par D5, et écrit ici pour que la question ne se repose pas :
`dp_socle/contrat.py`, `dp_socle/planches/dp3_coupes.py`, `dp_socle/coupe.py`,
et le dépôt voisin `photomontage`.

---

## Ce qui est mesuré, et reste à mesurer

Mesuré le 02/10/2026, sur la notice DP 11 des projets :

- Saint-Cyr-en-Val : surélévation **2,25 m**, PHEC **1,95 m** au-dessus du
  terrain naturel (revanche 30 cm), hauteur du local de l'ordre de **2,5 m**.
  Les cotes NGF d'origine, qui ne servent plus à la saisie mais datent la
  mesure : PHEC 97,45 m, plancher ≥ 97,75 m, terrain naturel retenu 95,5 m.
- Périgny-la-Rose, pour comparaison : surélévation 0,55 m, PHEC 0,45 m
  (revanche 10 cm), poste 3,0 m, hauteur totale annoncée « max 5,0 m ».

Mesuré le 04/10/2026, à la construction, sur le contrat d'essai du dépôt
(`tests/test_surelevation_lot9.py` tient les deux résultats) :

- **l'échelle de DP 4-1 descend d'un cran sur Saint-Cyr.** Posé au sol, le
  poste sort au 1:100 ; avec la surélévation de Périgny (0,55 m) il y reste ;
  avec celle de Saint-Cyr (2,25 m) la planche passe au **1:200**. Cinq vues qui
  montent de 2,25 m font 112 mm de plus sur la colonne, et le panneau n'en a
  pas la place. Le 1:200 est une échelle permise et le cartouche l'annonce,
  donc la planche reste juste — mais elle n'est plus au 1:100 de HOCH, et la
  volée y a des marches d'environ 1,4 mm. À regarder sur l'épreuve A3 avant
  dépôt, et c'est le seul point du lot qui reste à juger à l'œil.
- **une valeur absurde est déjà refusée.** 22,5 m au lieu de 2,25 ne s'absorbe
  pas en écrasant l'échelle : `_echelles_des_blocs` lève `ErreurComposition`,
  la vue ne tenant plus dans le panneau même au 1:200. Aucun plafond de
  vraisemblance n'est donc à inventer, et c'était la bonne décision de ne pas
  en poser un d'avance.

---

## Pièges connus

- **Le PPTX n'est pas modifiable à la main.** Ses diapositives sont vides :
  chaque planche est une image posée sur sa mise en page (mesuré le 02/10/2026
  sur `PV-St-Cyr-en-Val-IND07_DP_a_finaliser`). Retoucher le PPT serait perdu à
  la prochaine génération. La correction vient du générateur, puis on régénère.
- **Pour Saint-Cyr, qui est à l'indice 07**, le chef de projet n'a pas à tout
  refaire : une planche entre dans le `.pptx` en une seule image pleine page
  (décision D0 du lot 8), et la surélévation n'ajoute ni ne retire aucune pièce,
  donc la pagination ne bouge pas. Il génère à côté et remplace la seule diapo
  DP 4-1 dans son dossier fini — son travail photographique est conservé.
- **Le DXF ne porte pas la surélévation** et ne la portera pas : le bureau
  d'études livre une emprise au sol. Ce n'est pas un défaut d'import à corriger,
  c'est une donnée qui n'existe que dans le PPRI et la notice.
- **Le tableau des gabarits n'existe que sur le parcours « plan projet PDF ».**
  Le volet « Les ouvrages du plan, aux cotes de leur gabarit » est propre au lot
  2ter ; le parcours DXF du bureau d'études — celui de Saint-Cyr — n'affiche que
  « Paramètres extraits du tableau bilan ». D'où le volet à part de D4, sur les
  deux parcours, plutôt qu'une colonne ajoutée à ce tableau.
