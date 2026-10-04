"""Modèle du fichier `projet.json`, format pivot du générateur.

Une correction de dernière minute se fait en modifiant une valeur du JSON puis
en régénérant, jamais en recommençant une saisie.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date as _date
from pathlib import Path

from .erreurs import ErreurDP

#: Maître d'ouvrage et maître d'œuvre du dossier.
MOA_NOM = "UNITe"
MOA_ADRESSE = "139 rue Vendôme"
MOA_VILLE = "69006 LYON"

CHAMPS_OBLIGATOIRES = ("nom", "commune", "code_postal", "date", "emprise")


#: Nom d'un projet, tel qu'il figure au cartouche et sur la page de garde.
#:
#: Il ne se saisit pas : il est toujours « PV » suivi de la commune, et de
#: l'indice du tableau bilan quand il est connu. Le champ qui le demandait
#: recopiait la commune neuf fois sur dix, et la dixième était une coquille
#: (relecture du 05/09/2026).
MOTIF_NOM_PROJET = "PV {commune}"


def nom_de_projet(commune: str, indice: str | None = None) -> str:
    """Nom du projet d'une commune, à son indice, vide sans commune.

    L'indice fait partie du nom, et pas seulement du tableau bilan. Deux indices
    d'un même projet sont deux dossiers — Sarnois en a deux, qui diffèrent par
    leur poste, leur citerne et leur zone de contention — et sans l'indice au
    nom, le second écrasait le premier dans `sortie/`.
    """
    commune = (commune or "").strip()
    if not commune:
        return ""
    nom = MOTIF_NOM_PROJET.format(commune=commune)
    indice = (indice or "").strip()
    return f"{nom} {indice}" if indice else nom


#: Caractères qu'un nom de dossier ne peut pas porter sous Windows.
_INTERDITS = r'<>:"/\|?*'


def identifiant_de_dossier(nom: str) -> str:
    """Nom de dossier sûr, tiré du nom de projet saisi.

    Le chef de projet ne saisit qu'un nom — celui qui figure au cartouche. Le
    système de fichiers, lui, refuse une partie des caractères qu'on met dans un
    nom de projet : « Saint-Cyr-en-Val (45) » passe, « Centrale PV : tranche 2 »
    non. Les caractères interdits deviennent des tirets, les espaces aussi, et
    les répétitions sont réduites.

    Rendre le nom tel quel quand il est déjà sûr : c'est le cas courant, et le
    dossier doit garder le nom qu'on lui a donné.
    """
    propre = "".join("-" if c in _INTERDITS or c.isspace() else c for c in nom.strip())
    while "--" in propre:
        propre = propre.replace("--", "-")
    return propre.strip("-. ")


@dataclass
class Projet:
    """Métadonnées d'un dossier de déclaration préalable."""

    nom: str
    commune: str
    code_postal: str
    date: str
    emprise: str
    image_garde: str | None = None
    #: Décalage du cadre sur l'image de couverture, dans [-0,5 ; 0,5], tel que
    #: le chef de projet l'a réglé sur la photographie. La page de garde a son
    #: propre format — 228 x 133,5 mm — mais garde la même part de l'image :
    #: elle montrait le cliché entier, en portrait dans un cadre paysage
    #: (retour d'usage du 24/09/2026).
    cadrage_garde: float = 0.0
    #: Nom du projet tel que le chef de projet veut le voir au cartouche et sur
    #: la page de garde. `nom` reste l'identifiant technique du dossier.
    libelle: str | None = None
    #: Export CAO HelioScope du calepinage (lot 2).
    helioscope: str | None = None
    #: Notice DP 11, fournie en PDF par le chef de projet (lot 5).
    #:
    #: Attendue de tout dossier déposable, mais **pas exigée par l'outil** tant
    #: que le dépôt est en mise au point : un contrôle bloquant empêcherait
    #: d'éprouver le reste de la chaîne (décision du 14/09/2026). Son absence
    #: est donc écrite au rapport, jamais levée. Un dossier d'étude amont,
    #: réduit aux pièces DP 1, n'en a de toute façon pas encore.
    notice: str | None = None
    #: Longitude de l'origine du repère DXF, en degrés, retenue au calage et
    #: validée par l'utilisateur. La latitude, elle, se déduit du fichier : elle
    #: n'a pas à être stockée. Une fois cette valeur écrite, une régénération ne
    #: redemande jamais le calage.
    longitude_calage: float | None = None
    #: Type retenu pour les voiries dont le calque du bureau d'études ne disait
    #: pas si elles étaient lourdes ou légères (décision D5 du lot 4).
    #:
    #: Une **liste**, un type par objet dans l'ordre de la couche : un projet a
    #: presque toujours de la voie lourde et de la piste légère, et le calque les
    #: mélange. Une chaîne, forme des dossiers antérieurs, vaut pour toute la
    #: couche.
    #:
    #: Sans valeur, une couche `voirie` peuplée bloque la génération des
    #: planches : le tableau bilan sépare les deux et la légende du dossier les
    #: distingue, aucune des deux n'est plus probable que l'autre. La décision
    #: est celle du chef de projet, et elle se conserve ici pour qu'une
    #: régénération ne la redemande pas.
    voirie: str | list | None = None
    #: Correction nord-sud saisie à la main, en mètres vers le nord, à partir de
    #: la latitude déduite du fichier. Stockée en écart plutôt qu'en latitude
    #: corrigée : la valeur du fichier reste lisible et la retouche se voit.
    correction_nord_sud_m: float | None = None
    #: Prises de vue des pièces photographiques (lot 6), par code de pièce :
    #: `{"DP 6": [prise, ...], "DP 7": [...], "DP 8": [...]}`.
    #:
    #: Elles vivent ici plutôt que dans le contrat d'entrée du lot 4, qui décrit
    #: le plan du bureau d'études et rien d'autre. C'est ce qui les fait survivre
    #: à un rechargement de page : placer un point de vue est un geste qu'on ne
    #: refait pas volontiers.
    #:
    #: Conservées en JSON pur, et converties à l'usage par `prises_de()` : un
    #: `Projet` doit rester sérialisable sans traitement particulier, et une
    #: dataclass imbriquée s'y serait invitée dans `asdict`.
    photographies: dict | None = None
    #: Intitulés de légende retouchés par le chef de projet, `{catégorie: texte}`.
    #:
    #: Nos intitulés sont ceux du dossier de référence, et ils conviennent presque
    #: toujours ; mais un projet peut avoir ses mots — une « piste lourde » que les
    #: autres pièces du dossier appellent une voie de desserte. Les corriger ici
    #: plutôt que dans le `.pptx` a une raison : la légende est dans l'image de la
    #: planche, et la rendre éditable dans PowerPoint demanderait de dessiner la
    #: planche sans elle (décision D1 du lot 8, non tenue). Une correction se fait
    #: donc avant de générer, et se conserve pour les régénérations suivantes.
    #:
    #: Les deux entrées qui ne viennent pas du contrat — le parcellaire et les
    #: bâtiments du WFS IGN — se renomment sous `palette.CLE_PARCELLE` et
    #: `palette.CLE_BATIMENT`.
    legendes: dict | None = None
    #: Surélévation du plancher des locaux techniques au-dessus du terrain
    #: naturel, en mètres, quand un PPRI l'impose (lot 9).
    #:
    #: **Une hauteur relative, jamais une cote NGF.** Les blocs DP 4 tracent
    #: leur propre ligne de sol à zéro : la planche ne prétend à aucune
    #: altitude, et il n'y a donc rien à accorder avec la topographie relevée —
    #: ni le profil RGE ALTI de DP 3, ni le relevé du géomètre. Une cote
    #: absolue, elle, devrait s'y accorder, et un désaccord de quelques
    #: décimètres entre deux pièces du même dossier est précisément ce que le
    #: dossier ne peut pas se permettre (décision du 04/10/2026).
    #:
    #: Vide, les locaux sont dessinés posés au sol et le rapport le dit.
    surelevation_locaux_m: float | None = None
    #: Niveau des plus hautes eaux connues au-dessus du terrain naturel, en
    #: mètres. **Facultatif** : renseigné, il trace le pointillé bleu et son
    #: étiquette, comme la planche HOCH de Périgny ; vide, le reste est dessiné
    #: quand même.
    #:
    #: Il ne se déduit pas de la surélévation : l'écart des deux est la
    #: revanche, et elle vaut 10 cm à Périgny pour 30 à Saint-Cyr.
    phec_locaux_m: float | None = None

    @property
    def libelle_affiche(self) -> str:
        return self.libelle.strip() if self.libelle and self.libelle.strip() else self.nom

    @property
    def chemin_emprise(self) -> Path:
        return Path(self.emprise)

    @property
    def chemin_image_garde(self) -> Path | None:
        return Path(self.image_garde) if self.image_garde else None

    @property
    def chemin_helioscope(self) -> Path | None:
        return Path(self.helioscope) if self.helioscope else None

    @property
    def chemin_notice(self) -> Path | None:
        return Path(self.notice) if self.notice else None

    @property
    def cale(self) -> bool:
        """Vrai si le calage est déjà fait et n'a pas à être redemandé."""
        return self.longitude_calage is not None

    def valider(self) -> None:
        for champ in CHAMPS_OBLIGATOIRES:
            valeur = getattr(self, champ, None)
            if not valeur or not str(valeur).strip():
                raise ErreurDP(
                    f"Champ obligatoire manquant dans projet.json : « {champ} »."
                )
        try:
            _date.fromisoformat(self.date)
        except ValueError as exc:
            raise ErreurDP(
                f"Date « {self.date} » invalide : format attendu AAAA-MM-JJ."
            ) from exc
        if not self.chemin_emprise.exists():
            raise ErreurDP(
                f"Fichier d'emprise introuvable : {self.emprise}"
            )
        chemin_garde = self.chemin_image_garde
        if chemin_garde is not None and not chemin_garde.exists():
            raise ErreurDP(
                f"Image de page de garde déclarée mais introuvable : {self.image_garde}. "
                "Laissez le champ vide si vous n'en avez pas."
            )
        chemin_hs = self.chemin_helioscope
        if chemin_hs is not None and not chemin_hs.exists():
            raise ErreurDP(
                f"Export HelioScope déclaré mais introuvable : {self.helioscope}."
            )
        self.valider_photographies()
        chemin_notice = self.chemin_notice
        if chemin_notice is not None and not chemin_notice.exists():
            raise ErreurDP(
                f"Notice DP 11 déclarée mais introuvable : {self.notice}. "
                "Laissez le champ vide si le dossier part sans notice."
            )
        if self.longitude_calage is not None:
            if self.helioscope is None:
                raise ErreurDP(
                    "longitude_calage est renseignée sans export HelioScope : "
                    "un calage sans calepinage n'a pas de sens."
                )
            # Bornes larges de la France métropolitaine, Corse comprise. Une
            # longitude hors plage signale un projet.json corrigé à la main de
            # travers ; mieux vaut refuser que produire un plan ailleurs.
            if not -5.5 <= self.longitude_calage <= 10.0:
                raise ErreurDP(
                    f"longitude_calage = {self.longitude_calage} hors de la France "
                    "métropolitaine (-5,5° à 10,0°). Refaites le calage."
                )
        self.valider_surelevation()
        if self.voirie is not None:
            # Le même ensemble que celui du contrat, et non une seconde liste :
            # « sans objet » n'était arrivé que dans `decrire_voiries`, et un
            # dossier trié se validait à l'écran puis refusait de se générer.
            from .contrat import VOIRIES_DU_CONTRAT

            # Une chaîne vaut pour toute la couche — c'est la forme des
            # `projet.json` écrits avant que le tri ne se fasse objet par objet,
            # et elle reste lisible. Une liste donne un type par objet.
            choix = [self.voirie] if isinstance(self.voirie, str) else self.voirie
            inconnus = sorted({c for c in choix if c not in VOIRIES_DU_CONTRAT})
            if inconnus:
                raise ErreurDP(
                    f"voirie = « {', '.join(map(str, inconnus))} » inconnu dans "
                    f"projet.json ; attendu parmi {', '.join(VOIRIES_DU_CONTRAT)}."
                )
        if self.correction_nord_sud_m is not None:
            if self.longitude_calage is None:
                raise ErreurDP(
                    "correction_nord_sud_m est renseignée sans calage est-ouest : "
                    "corriger la latitude d'une implantation non positionnée n'a "
                    "pas de sens."
                )
            # Même borne que `corriger_nord_sud`, redite ici parce qu'un
            # projet.json se corrige à la main et n'est pas relu par le module
            # de calage.
            if abs(self.correction_nord_sud_m) > 30.0:
                raise ErreurDP(
                    f"correction_nord_sud_m = {self.correction_nord_sud_m:+.1f} m, "
                    "au-delà des ±30 m admis. Une correction de cet ordre signale "
                    "un calage faux, pas une retouche."
                )

    def prises_de(self, code: str) -> list:
        """Les prises de vue d'une pièce photographique, converties depuis le JSON.

        Lève si le fichier décrit une prise inexploitable — sans position ou sans
        image : mieux vaut refuser que produire une planche muette sur ce qu'elle
        ignore.
        """
        from .points_de_vue import prise_depuis_json

        brutes = (self.photographies or {}).get(code) or []
        return [prise_depuis_json(brute) for brute in brutes]

    def date_francaise(self) -> str:
        return _date.fromisoformat(self.date).strftime("%d/%m/%Y")

    @classmethod
    def charger(cls, chemin: str | Path) -> "Projet":
        chemin = Path(chemin)
        if not chemin.exists():
            raise ErreurDP(f"projet.json introuvable : {chemin}")
        try:
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ErreurDP(f"projet.json illisible ({chemin}) : {exc}") from exc

        inconnus = set(donnees) - set(cls.__dataclass_fields__)
        if inconnus:
            raise ErreurDP(
                f"Champs inconnus dans projet.json : {', '.join(sorted(inconnus))}."
            )
        manquants = [c for c in CHAMPS_OBLIGATOIRES if c not in donnees]
        if manquants:
            raise ErreurDP(
                f"Champs absents de projet.json : {', '.join(manquants)}."
            )

        # Les chemins relatifs le sont par rapport au dossier du projet.json.
        base = chemin.parent
        for champ in ("emprise", "image_garde", "helioscope", "notice"):
            valeur = donnees.get(champ)
            if valeur:
                donnees[champ] = _chemin_resolu(valeur, base)
        _resoudre_photographies(donnees.get("photographies"), base)

        projet = cls(**donnees)
        projet.valider()
        return projet

    def valider_photographies(self) -> None:
        """Contrôle que chaque prise de vue est exploitable, et le dit sinon.

        Appelée par `valider()`. Les images sont contrôlées ici plutôt qu'à la
        composition : une planche qui échoue après le téléchargement des fonds
        IGN fait perdre la génération entière, et la règle du dépôt veut qu'un
        manque se signale au plus tôt.
        """
        for code, brutes in (self.photographies or {}).items():
            if not isinstance(brutes, list):
                raise ErreurDP(
                    f"projet.json : « {code} » ne décrit pas une liste de prises "
                    "de vue."
                )
            for rang, prise in enumerate(self.prises_de(code), start=1):
                for image in prise.images:
                    if not Path(image).exists():
                        raise ErreurDP(
                            f"{code}, prise {rang} : image introuvable "
                            f"({image}). Redéposez-la, ou retirez la prise."
                        )

    def valider_surelevation(self) -> None:
        """Contrôle la cohérence interne des deux cotes de surélévation.

        Un seul contrôle, et il ne porte que sur les deux nombres saisis : la
        PHEC doit être sous le plancher, sinon le dessin se contredit lui-même
        — un pointillé d'eau au-dessus d'un plancher qu'il est censé épargner.

        Rien d'autre n'est contrôlé. Pas de recoupement avec l'altimétrie :
        ces hauteurs sont relatives au terrain naturel et la planche ne
        prétend à aucune altitude (décision D5). Pas de plafond de
        vraisemblance non plus : il serait inventé, et `_echelles_des_blocs`
        refuse déjà ce qui ne tient pas sur la planche.
        """
        for champ in ("surelevation_locaux_m", "phec_locaux_m"):
            valeur = getattr(self, champ)
            if valeur is None:
                continue
            if not isinstance(valeur, (int, float)) or isinstance(valeur, bool):
                raise ErreurDP(
                    f"projet.json : « {champ} » doit être une hauteur en mètres, "
                    f"pas {valeur!r}."
                )
            if valeur <= 0:
                raise ErreurDP(
                    f"projet.json : « {champ} » vaut {valeur}. C'est une hauteur "
                    "au-dessus du terrain naturel : laissez le champ vide si "
                    "l'ouvrage est posé au sol."
                )
        if self.phec_locaux_m is None:
            return
        if self.surelevation_locaux_m is None:
            raise ErreurDP(
                "projet.json : le niveau des plus hautes eaux est renseigné "
                f"({self.phec_locaux_m} m) sans surélévation du plancher. "
                "L'un ne se déduit pas de l'autre — leur écart est la revanche "
                "du PPRI, 10 cm sur un projet et 30 sur un autre."
            )
        if self.phec_locaux_m >= self.surelevation_locaux_m:
            raise ErreurDP(
                f"projet.json : les plus hautes eaux ({self.phec_locaux_m} m) "
                f"atteignent ou dépassent le plancher des locaux "
                f"({self.surelevation_locaux_m} m). Le dessin se contredirait "
                "lui-même ; vérifiez les deux hauteurs dans la notice."
            )

    def ecrire(self, chemin: str | Path) -> Path:
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        donnees = {c: v for c, v in asdict(self).items() if v is not None}
        _declarer_les_chemins(donnees, chemin.parent)
        chemin.write_text(
            json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return chemin


#: Champs de `projet.json` qui désignent un fichier. Les images des prises de
#: vue sont traitées à part : elles vivent d'un cran plus bas dans la structure.
CHAMPS_FICHIERS = ("emprise", "image_garde", "helioscope", "notice")


def _chemin_declare(valeur: str, base: Path) -> str:
    """Le chemin tel qu'il s'écrit : relatif au `projet.json`, en barres obliques.

    `str(Path)` rend des antislashs sous Windows, et Linux n'y voit pas des
    séparateurs mais des caractères ordinaires du nom — `PurePosixPath` lit
    « DP_7\\vue.jpg » comme le nom d'un seul fichier. Un `projet.json` écrit
    sous Windows était donc illisible sur la cible de déploiement, et la
    validation levait « image introuvable » sur un fichier bien présent
    (mesuré le 24/09/2026).

    Relatif au dossier du fichier, et non au dossier de lancement : c'est ce qui
    laisse déplacer un dossier de projet, et déplier ailleurs le ZIP de reprise.
    Un chemin qui sort du dossier reste absolu — il n'y a rien de mieux à en
    faire — mais passe lui aussi en barres obliques.
    """
    chemin = Path(valeur)
    try:
        return chemin.resolve().relative_to(base.resolve()).as_posix()
    except (ValueError, OSError):
        return chemin.as_posix()


def _chemin_resolu(valeur: str, base: Path) -> str:
    r"""Le chemin absolu d'un fichier déclaré, relatif au dossier du `projet.json`.

    Aucune tolérance aux antislashs ici, et c'est délibéré : les `projet.json`
    écrits avant le 24/09/2026 portent des chemins relatifs au dossier de
    **lancement** (« projets\X\DP_7\vue.jpg »), que convertir ne suffirait pas
    à résoudre depuis le dossier du fichier. Ils continuent de se relire là où
    ils ont été écrits, par ce même dossier de lancement, et repassent au format
    portable à la première réécriture. Ajouter une conversion aurait couvert un
    cas que rien ne produit, et pérennisé la résolution par le dossier courant.
    """
    if Path(valeur).is_absolute():
        return valeur
    candidat = (base / valeur).resolve()
    if candidat.exists():
        return str(candidat)
    # Inchangé : `valider()` dira lequel manque, avec son nom tel qu'il est écrit.
    return valeur


def _declarer_les_chemins(donnees: dict, base: Path) -> None:
    """Réécrit en place les chemins du dictionnaire sérialisé.

    Sur la copie que produit `asdict`, et non sur le `Projet` : l'objet en
    mémoire garde les chemins absolus dont le reste de l'application se sert.
    """
    for champ in CHAMPS_FICHIERS:
        valeur = donnees.get(champ)
        if valeur:
            donnees[champ] = _chemin_declare(valeur, base)
    for prises in (donnees.get("photographies") or {}).values():
        for prise in prises:
            prise["images"] = [
                _chemin_declare(image, base) if image else image
                for image in prise.get("images") or []
            ]


def _resoudre_photographies(photographies, base: Path) -> None:
    """Rend absolus les chemins d'images, relatifs au dossier du projet.json.

    Sur place : `charger` construit le `Projet` depuis ce même dictionnaire.
    """
    if not isinstance(photographies, dict):
        return
    for prises in photographies.values():
        if not isinstance(prises, list):
            continue
        for prise in prises:
            images = prise.get("images") if isinstance(prise, dict) else None
            if not images:
                continue
            prise["images"] = [
                _chemin_resolu(image, base) if image else image for image in images
            ]
