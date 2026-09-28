# BRIEF CLAUDE CODE — Générateur de dossier DP, lot 7 révisé : ajouter la notice à un dossier fini

> Remplace `BRIEF_DP_lot7_reprise_dossier.md`, écrit le 24/09/2026 et rendu
> caduc par le lot 8. Lire `README.md` et `CLAUDE.md` avant de commencer : ce
> brief ne les répète pas.

---

## Le besoin, tel que l'usage l'a formulé (27/09/2026)

Le chef de projet travaille en trois temps, et ce n'est pas un contournement :
c'est l'ordre naturel de son dossier.

1. **Il génère sans notice** — pour valider son plan au plus tôt et transmettre
   le GeoPackage à qui monte les photomontages ;
2. **il finit son `.pptx` à la main** — ses photographies dans les cadres, le
   photomontage reçu, les diapos surnuméraires supprimées — pendant que la
   notice se rédige en parallèle ;
3. **la notice n'arrive qu'à la fin.**

Aujourd'hui, il n'a d'autre choix que **tout régénérer et tout refaire**. Le
travail de l'étape 2 est perdu.

---

## Pourquoi le brief précédent est mort

`BRIEF_DP_lot7_reprise_dossier.md` posait une décision **D3 — régénération
complète, pas sélective**, au motif qu'un dossier mi-vieux mi-neuf ne se
signale pas.

Ce motif tenait le 24/09, quand la sortie était **un PDF que l'outil
assemblait** : régénérer ne coûtait que des téléchargements IGN.

Depuis le 26/09, la sortie est **un `.pptx` que le chef de projet finit
lui-même**. Régénérer ne coûte plus des minutes de réseau : cela **détruit son
travail**. D3 s'inverse, et pour une raison qui ne se devine pas — elle tient à
ce que la sortie est devenue.

Ce qui reste valable du brief précédent : **D0** (le serveur ne garde rien) et
la note sur les chemins de `projet.json`, corrigés le 24/09.

---

## Ce qui a été vérifié avant d'écrire ce brief (28/09/2026)

Tout ce qui suit est mesuré, pas supposé.

### Le fichier du chef de projet sait ce qu'il contient

Chaque diapo porte une **mise en page nommée d'après sa pièce**
(`sortie_pptx._poser_diapo` appelle `ooxml.nouvelle_mise_en_page(…,
diapo.libelle)`). Relevé sur le dossier de Sarnois, 20 diapos :

```
page  1  « Page de garde »        page 10  « DP 6 — 2 cadres »
page  2  « DP 1-1 »               page 11  « DP 6 — 3 cadres »
page  5  « DP 2 »                 page 13  « DP 8 au 1/5000 »
page  9  « DP 4-3 »               page 16  « DP 11, page 1 »
```

**Conséquence décisive** : la pagination se lit dans le fichier déposé, et elle
reflète donc les suppressions déjà faites par le chef de projet. Le serveur n'a
rien à retenir.

### La photo de couverture survit au redessin de la page de garde

Le fond d'une diapo est posé **sur la mise en page** (`ooxml.poser_fond`) ; la
réservation d'image est une forme **sur la diapo** (mesuré : la page de garde
porte 1 forme, les planches cartographiques 0). Échanger l'image de fond de la
mise en page « Page de garde » laisse donc intacte la photo que le chef de
projet y a déposée.

### L'identité du projet peut voyager dans le fichier

`core_properties` plafonne à **255 caractères par champ** (`python-pptx` lève
au-delà ; le `projet.json` entier fait 2 000 octets et ne passe pas). Mais la
page de garde ne demande que quatre valeurs :

```json
{"libelle": "PV SARNOIS IND10B", "commune": "SARNOIS",
 "code_postal": "45460", "date": "2026-09-17"}
```

**100 caractères**, écrits et relus à l'identique (vérifié). C'est tout ce
qu'il faut pour redessiner la page de garde — `page_garde.generer` ne lit rien
d'autre du projet, l'image de couverture étant une réservation dans cette voie.

---

## Décisions

### D1 — On ajoute, on ne régénère pas

Aucune planche n'est redessinée, sauf la page de garde, et pour une seule
raison : son sommaire.

### D2 — La date reste celle du dossier d'origine

Demandé au conditionnel le 27/09 : « la date pourrait être celle de l'ajout, si
possible ». **Ce n'est pas possible sans tout régénérer** : la date est dans le
cartouche de chaque planche, dessinée dans l'image. La changer sur la seule page
de garde donnerait un dossier dont la couverture contredit ses planches.

L'écran doit le dire : « le dossier gardera sa date du 17/09/2026 ».

### D3 — Le sommaire se recompose, il ne se rafistole pas

Ajouter la notice fait passer sa ligne de « — » à un numéro de page. Le sommaire
étant dans l'image, la page de garde est **redessinée** à partir de la
pagination lue dans le fichier, puis son image de fond est échangée.

Une variante a été envisagée et écartée : poser une zone de texte par-dessus
l'image, à l'emplacement calculé de la case. Moins de travail, mais un rustine
visible au premier changement de mise en page.

### D4 — Un dossier qui porte déjà une notice est refusé

Pas de seconde notice ajoutée en silence. Le message nomme ce qu'il a trouvé :
« ce dossier porte déjà une notice de 5 pages ». Remplacer une notice est un
autre besoin, qui viendra s'il se présente.

### D5 — Les dossiers produits avant ce lot ne peuvent pas en profiter

Ils ne portent pas l'identité du projet dans leurs propriétés. L'écran le dit
et renvoie au parcours normal, plutôt que de demander au chef de projet de
ressaisir commune, code postal et date — ce qui rouvrirait la porte à un
dossier dont la couverture ment.

### D6 — Un bouton en tête de page, hors du parcours

« Je souhaite juste ajouter la notice à mon dossier finalisé », avant la
section 1. Il ouvre deux dépôts — le `.pptx` fini, le PDF de la notice — et rend
un `.pptx`. Le parcours normal, d'une traite, n'est pas touché.

---

## À vérifier pendant la construction

**PowerPoint conserve-t-il `core_properties.comments` quand le chef de projet
enregistre ?** Écrit et relu par `python-pptx`, c'est vérifié. Un aller-retour
par PowerPoint lui-même ne l'est pas, et c'est ce que le fichier subira. Si la
propriété ne survit pas, D5 tombe et il faudra loger l'identité ailleurs — une
forme masquée sur la page de garde, que PowerPoint conserve à coup sûr.

**Tester avant de construire le reste.** Tout le lot en dépend.

---

## Ce qu'il ne faut pas faire

- **Ne pas toucher au moteur `Planche` du lot 1**, ni aux planches du lot 8 :
  ce lot ouvre une entrée, il ne change pas ce qui est dessiné.
- **Ne pas régénérer par confort.** Si une pièce manque autre que la notice, le
  parcours normal reste la réponse.
- **Ne pas déduire la pagination d'une mémoire du serveur.** Le fichier déposé
  fait foi — c'est lui qui porte les suppressions du chef de projet.
