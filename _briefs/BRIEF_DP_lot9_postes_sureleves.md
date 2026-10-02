# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 9 : postes surélevés en zone inondable

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

---

## La référence

`3.5. PC5_UNITe-Périgny-la-Rose_Dossier_Archi.pdf`, page 2 — planche HOCH
« PC 5-1 Poste de livraison : façade et coupe », du 26/05/2025, au 1:100. C'est
le modèle à suivre. Elle porte, sur les quatre élévations **et** sur la coupe :

- une **plateforme sur pilotis**, le poste posé dessus ;
- un **garde-corps** sur tout le pourtour de la plateforme ;
- un **escalier d'accès** latéral, avec son palier ;
- la **ligne PHEC** en pointillé bleu, légendée « PHEC (0.45 m) » et, en pied de
  cadre, « PHEC : Plus Hautes Eaux Connues » ;
- les cotes : surélévation (0,55 m à Périgny), hauteur du poste (3,0 m), et la
  hauteur totale (« max 5,0 m »).

Sur Saint-Cyr la surélévation est de 2,25 m, soit quatre fois celle de Périgny :
l'escalier y compte plus de marches, et la vérification à l'épreuve A3 est à
refaire — une volée qui tient à 0,55 m peut ne plus tenir à 2,25 m.

---

## Décisions prises avec le chef de projet le 02/10/2026

**D1 — La hauteur vient du PPRI, donc du chef de projet.** Le PPRI est un
document d'urbanisme : aucune API ne donne la cote des plus hautes eaux en un
point. La surélévation est donc **saisie**, et rejoint `projet.json`, format
pivot du dépôt. Une correction se fait en changeant la valeur et en
régénérant.

À trancher à la construction : saisit-on la **surélévation** (2,25 m) ou la
**cote PHEC en NGF** (97,45 m) avec le terrain naturel (95,5 m), dont la
différence donne la surélévation ? La planche HOCH affiche la cote PHEC ; si on
ne saisit que la surélévation, l'étiquette « PHEC » ne peut pas porter de cote.

**D2 — Tous les locaux techniques, pas seulement les postes.** Postes de
livraison et de transformation, conteneurs BESS, local technique. À trancher :
les citernes (`bache_incendie`, `citerne_refroidissement`) sont des cuves
ancrées, pas des locaux — le chef de projet a dit « tous les locaux
techniques », ce qui les exclut en bonne lecture, mais la question mérite d'être
reposée sur un projet réel.

**D3 — Le dessin suit HOCH, escalier compris.** L'objection soulevée à l'examen
— le générateur ne sait pas de quel côté va l'escalier, et en placer un au
hasard serait inventer — a été écartée par le chef de projet : « si l'escalier
change, ça pourra se faire facilement en demandant une modification de
l'autorisation ». L'escalier est donc dessiné d'un côté choisi par convention,
et **la convention doit être écrite dans le code et dans le dossier** pour que
le bureau d'études sache ce qu'il regarde.

---

## Ce que le lot touche

- `dp_socle/planches/dp4_ouvrages.py` : `_bloc_poste` (plan de toiture, quatre
  élévations, coupe) et le bloc des conteneurs. Les hauteurs de vue, les cotes
  et le calcul d'échelle des blocs (`_echelles_des_blocs`) changent avec la
  surélévation — une vue plus haute de 2,25 m peut faire tomber la planche sous
  l'échelle qui la logeait.
- `dp_socle/projet.py` et `app.py` : la saisie et le report dans `projet.json`.
- `dp_socle/contrat.py` : à vérifier. La surélévation décrit l'ouvrage, pas sa
  géométrie au sol ; elle n'a pas à entrer dans le contrat si le lot 4 la lit de
  `projet.json`. Mais le dépôt voisin `photomontage` lit ce contrat, et un poste
  surélevé de 2,25 m **change ce qu'on voit** sur un photomontage. À trancher
  avec lui.
- `dp_socle/planches/dp3_coupes.py` : la coupe A-A' traverse le site et peut
  passer sur un poste. À vérifier.

---

## Ce qui est mesuré, et reste à mesurer

Mesuré le 02/10/2026 :

- Saint-Cyr-en-Val, surélévation **2,25 m**, cote PHEC **97,45 m NGF**, terrain
  naturel retenu **95,5 m**, plancher du poste **≥ 97,75 m NGF** (PHEC + 0,30),
  hauteur du local de l'ordre de **2,5 m** — tous relevés dans la notice DP 11
  du projet.
- Périgny-la-Rose, pour comparaison : surélévation 0,55 m, poste 3,0 m,
  hauteur totale annoncée « max 5,0 m ».

Reste à mesurer à la construction : la planche DP 4-1 de Saint-Cyr tient-elle
encore à son échelle avec 2,25 m de plus par vue, et la volée d'escalier est-elle
lisible à l'épreuve A3 ?

---

## Pièges connus

- **Le PPTX n'est pas modifiable à la main.** Ses diapositives sont vides : chaque
  planche est une image posée sur sa mise en page (mesuré le 02/10/2026 sur
  `PV-St-Cyr-en-Val-IND07_DP_a_finaliser`). Retoucher le PPT serait perdu à la
  prochaine génération. La correction vient du générateur, puis on régénère.
- **Le DXF ne porte pas la surélévation** et ne la portera pas : le bureau
  d'études livre une emprise au sol. Ce n'est pas un défaut d'import à corriger,
  c'est une donnée qui n'existe que dans le PPRI et la notice.
