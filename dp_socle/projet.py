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


@dataclass
class Projet:
    """Métadonnées d'un dossier de déclaration préalable."""

    nom: str
    commune: str
    code_postal: str
    date: str
    emprise: str
    image_garde: str | None = None

    @property
    def chemin_emprise(self) -> Path:
        return Path(self.emprise)

    @property
    def chemin_image_garde(self) -> Path | None:
        return Path(self.image_garde) if self.image_garde else None

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
        for champ in ("emprise", "image_garde"):
            valeur = donnees.get(champ)
            if valeur and not Path(valeur).is_absolute():
                candidat = (base / valeur).resolve()
                if candidat.exists():
                    donnees[champ] = str(candidat)

        projet = cls(**donnees)
        projet.valider()
        return projet

    def ecrire(self, chemin: str | Path) -> Path:
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        donnees = {c: v for c, v in asdict(self).items() if v is not None}
        chemin.write_text(
            json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return chemin
