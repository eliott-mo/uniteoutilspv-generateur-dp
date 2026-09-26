"""Valeurs standard UNITe que le contrat d'entrée ne porte pas.

Le tableau bilan donne le linéaire de clôture, le nombre de portails et leur
largeur. Il ne donne **aucune hauteur** — ni pour la clôture, ni pour le
portail — alors que les élévations de DP 4 et la coupe du terrain de DP 3 en
ont besoin.

Ces valeurs sont donc celles des clôtures et portails posés sur les centrales
UNITe. Elles ne viennent pas du dossier, et toute planche qui les emploie le
dit au rapport de génération : c'est une substitution, elle doit se voir.

**Corroboration.** Relevée le 04/09/2026 dans la légende du plan PDF du bureau
d'études pour Saint-Cyr : « Clôture à créer (2m) ». La hauteur est donc bien
celle-ci, et elle est même écrite sur le plan — mais en texte libre, que
l'import ne lit pas. C'est la bonne façon de combler ce manque le jour où on
s'y mettra : lire la légende du DXF plutôt que de garder une constante ici.
"""

from __future__ import annotations

from ..planche import nombre_fr

#: Hauteur d'une clôture de centrale, en mètres.
HAUTEUR_CLOTURE_M = 2.00
#: Hauteur d'un portail d'accès, alignée sur celle de la clôture.
HAUTEUR_PORTAIL_M = 2.00
#: Espacement des poteaux de clôture, en mètres.
ESPACEMENT_POTEAUX_M = 2.50

#: Passage à petite faune : ouverture ménagée au pied de la clôture. Élément
#: standard et attendu à l'instruction.
PASSAGE_FAUNE_LARGEUR_M = 0.15
PASSAGE_FAUNE_HAUTEUR_M = 0.15

#: Hauteurs conventionnelles de la végétation, en mètres.
#:
#: Ni le tableau bilan ni le DXF ne portent de hauteur pour une haie ou un
#: arbre. La coupe du terrain doit pourtant les montrer quand elle les
#: traverse : une haie de deux mètres devant une table en change la perception,
#: et c'est exactement ce qu'un instructeur regarde. Ces valeurs sont donc
#: conventionnelles — hauteur à la plantation pour une haie, port moyen d'un
#: arbre de haut-jet — et leur emploi est écrit au rapport.
HAUTEUR_HAIE_M = 2.00
HAUTEUR_ARBRE_M = 8.00

#: Largeurs conventionnelles de couronne, en mètres.
#:
#: Une zone légendée « arbres existants » ou « végétation » est un peuplement,
#: pas un sujet : elle contient autant d'arbres que sa largeur en porte. La
#: coupe la dessinait d'un seul houppier, ce qui donnait un arbre unique large
#: de cent mètres et haut de huit — relevé le 26/09/2026 sur la coupe de
#: Sarnois. Le port moyen d'un arbre de haut-jet fait les trois quarts de sa
#: hauteur ; une haie se lit à ses touffes, de la largeur de sa hauteur.
LARGEUR_ARBRE_M = 6.00
LARGEUR_HAIE_M = 2.00

MESSAGE_VEGETATION = (
    "Coupe du terrain : la végétation traversée est dessinée à des hauteurs "
    f"conventionnelles ({nombre_fr(HAUTEUR_HAIE_M)} m pour une haie, "
    f"{nombre_fr(HAUTEUR_ARBRE_M)} m pour un arbre), et une zone plus large "
    "qu'un sujet en porte autant qu'elle en contient : un arbre tous les "
    f"{nombre_fr(LARGEUR_ARBRE_M)} m, une touffe de haie tous les "
    f"{nombre_fr(LARGEUR_HAIE_M)} m. Ni le tableau bilan ni le plan ne portent "
    "de hauteur de végétation, ni le nombre de sujets d'une zone."
)

#: La hauteur de clôture et de portail ne se lit nulle part au contrat — le
#: tableau bilan ne donne que le linéaire, le nombre de portails et leur
#: largeur. Elle vaut **toujours 2,00 m** chez UNITe : confirmé à la relecture
#: du 05/09/2026, et c'est ce que porte aussi la légende du plan du bureau
#: d'études, « clôture à créer (2m) ».
#:
#: Ce n'est donc pas une substitution mais une constante de projet, et elle ne
#: s'écrit plus au rapport : un avertissement qui tombe sur tous les dossiers
#: sans jamais rien signaler apprend à ne plus les lire.
