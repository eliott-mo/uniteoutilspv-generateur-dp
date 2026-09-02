# Polices embarquées

`aptos.ttf` est versionné ici parce que le déploiement en dépend : sur Streamlit
Community Cloud, le fichier doit être présent dans le dépôt pour être installé
dans fontconfig au démarrage. Sans lui, les planches sortent dans une police de
substitution.

Aptos est une police Microsoft distribuée avec Microsoft 365. Sa redistribution
n'est pas libre : **ce dépôt doit rester privé**.

Il manque `aptos-bold.ttf`. En son absence, cairo graisse Aptos Regular
artificiellement pour les textes en gras du cartouche — lisible, mais moins
propre que la vraie graisse. Déposez le fichier ici si vous l'avez.

`dp_socle/polices.py` vérifie au démarrage que cairo compose bien avec Aptos, en
comparant la chasse mesurée à celle calculée depuis ce TTF. Un écart déclenche un
avertissement visible dans l'interface.
