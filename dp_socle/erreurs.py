"""Exceptions nommées du générateur DP.

Règle du lot : aucun repli silencieux. Chaque situation anormale lève une
exception explicite plutôt que de produire une planche fausse mais d'aspect
correct.
"""


class ErreurDP(Exception):
    """Base de toutes les erreurs du générateur."""


class ErreurEmprise(ErreurDP):
    """Le fichier d'emprise est illisible, vide ou dégénéré."""


class ErreurCRS(ErreurDP):
    """Le système de coordonnées du fichier d'emprise est absent ou refusé."""


class ErreurEchelle(ErreurDP):
    """Aucune échelle normalisée ne convient, ou échelle incohérente."""


class ErreurService(ErreurDP):
    """Un service IGN (WMS-R ou WFS) n'a pas répondu comme attendu."""


class ErreurPolice(ErreurDP):
    """La police de composition n'est pas disponible pour le moteur de rendu."""


class ErreurRendu(ErreurDP):
    """La conversion SVG vers PDF a échoué."""


class ErreurHelioScope(ErreurDP):
    """L'export HelioScope est illisible, incomplet ou ne suit pas le modèle."""


class ErreurModulesAbsents(ErreurHelioScope):
    """Le DXF ne porte aucun module : export réalisé trop tôt."""


class ErreurCalage(ErreurHelioScope):
    """Le calage géographique du DXF est impossible ou invalide."""


class ErreurImportBE(ErreurDP):
    """Les fichiers fournis par le bureau d'études sont illisibles ou incohérents."""


class ErreurGeoreferencement(ErreurImportBE):
    """Le DXF ne tombe pas dans les bornes du Lambert 93 métropolitain."""


class ErreurTableauBilan(ErreurImportBE):
    """Le tableau bilan est illisible, ou un paramètre attendu y est introuvable."""


class ErreurControleCroise(ErreurImportBE):
    """Un contrôle croisé bloquant entre le DXF et le tableau bilan a échoué."""


class ErreurCoupe(ErreurImportBE):
    """La ligne de coupe A-A' est absente, dégénérée ou impossible à corriger."""


class ErreurAltimetrie(ErreurService):
    """Le service altimétrique de la Géoplateforme n'a pas répondu comme attendu."""


class ErreurContrat(ErreurDP):
    """Le contrat d'entrée du lot 4 est absent, illisible ou d'une version non lue."""


class ErreurVoirieIndecise(ErreurContrat):
    """La couche `voirie` est peuplée sans que son type ait été tranché."""


class ErreurCoteOuvrage(ErreurContrat):
    """Un ouvrage à dessiner n'a pas de cote normalisée exploitable."""


class ErreurNotice(ErreurDP):
    """La notice DP 11 fournie est illisible, vide ou inexploitable à l'échelle."""


class ErreurComposition(ErreurDP):
    """Un dessin ne tient pas dans la place que la planche lui laisse."""


class ErreurPointDeVue(ErreurDP):
    """Un point de vue de photographie est inexploitable (lot 6)."""


class ErreurCartePhotos(ErreurPointDeVue):
    """La carte « photos-geoloc » déposée est illisible ou d'une version non lue."""


class ErreurPhotoIllisible(ErreurPointDeVue):
    """La photographie déposée ne s'ouvre pas, ou son format n'est pas pris en charge."""


class ErreurDepot(ErreurDP):
    """Un fichier déposé n'a pas pu être écrit dans le dossier du projet."""


class ErreurPlanPDF(ErreurDP):
    """Le plan projet PDF est illisible, ou ne porte pas ce qu'il faut lire (lot 2ter)."""


class ErreurLegendeIntrouvable(ErreurPlanPDF):
    """Un libellé attendu manque à la légende du plan, ou sa pastille est illisible."""


class ErreurEchelleIncoherente(ErreurPlanPDF):
    """L'échelle mesurée sur le pas des rangées contredit l'emprise des tables."""


class ErreurRecouvrementInsuffisant(ErreurPlanPDF):
    """Les tables du plan et celles du DXF ne se recouvrent pas assez une fois calées."""


class ErreurGabaritIndecis(ErreurPlanPDF):
    """Un ouvrage du plan n'a pas de dimension tranchée : variante ou largeur à choisir."""


class ErreurSortiePPTX(ErreurDP):
    """La sortie PowerPoint à finaliser n'a pas pu être écrite (lot 8)."""


class ErreurMontagePPTX(ErreurSortiePPTX):
    """Une propriété réglée dans le paquet OOXML ne s'y retrouve pas.

    `python-pptx` ne couvre pas tout, et Python accepte sans lever d'affecter
    un attribut qui n'existe pas : `fill.transparency = 0.45` ne faisait rien,
    et le cône de visée sortait magenta opaque par-dessus le plan (mesuré le
    25/09/2026). Ce qui s'écrit à la main se relit donc dans l'élément produit,
    et cette erreur est ce qui reste quand la relecture échoue.
    """
