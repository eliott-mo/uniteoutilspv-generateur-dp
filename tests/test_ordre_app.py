"""L'ordre des noms dans `app.py`, que Python ne contrôle qu'à l'exécution.

Streamlit rejoue `app.py` de haut en bas à chaque interaction. Un nom lu plus
haut qu'il n'est écrit ne se voit donc ni à l'import ni aux tests des modules :
il lève une `NameError` dans le navigateur, au moment précis où le chef de
projet dépose son fichier. C'est arrivé le 09/09/2026, après la réorganisation
des sections : `nom` était composé en section 4 et lu en section 2.

Ce test relit l'arbre syntaxique du script et refuse toute lecture de niveau
module qui précède l'écriture correspondante. Il ne remplace pas l'exécution —
il attrape la seule classe d'erreur que la réorganisation des sections
introduit, et qu'aucun autre test ne voit.
"""
import ast
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent

#: Portées propres : ce qui y est lié n'appartient pas au module.
PORTEES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ClassDef,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _lier(cible, bindings, ligne):
    """Note la première ligne où un nom de niveau module est écrit."""
    for petit in ast.walk(cible):
        if isinstance(petit, ast.Name) and isinstance(petit.ctx, (ast.Store, ast.Del)):
            bindings.setdefault(petit.id, ligne)


def _parcourir(noeud, bindings, lectures, au_module=True):
    """Collecte écritures et lectures du seul niveau module.

    Les portées propres — fonctions, lambdas, classes, compréhensions — sont
    élaguées : leurs noms locaux ne sont pas ceux du module, et les confondre
    faisait remonter `calque` ou `nombre` comme des lectures anticipées.
    """
    for enfant in ast.iter_child_nodes(noeud):
        if isinstance(enfant, PORTEES):
            if isinstance(enfant, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bindings.setdefault(enfant.name, enfant.lineno)
                for decorateur in enfant.decorator_list:
                    _parcourir(decorateur, bindings, lectures)
                    if isinstance(decorateur, ast.Name):
                        lectures.append((decorateur.lineno, decorateur.id))
            continue
        if isinstance(enfant, (ast.Import, ast.ImportFrom)):
            for alias in enfant.names:
                bindings.setdefault(
                    (alias.asname or alias.name).split(".")[0], enfant.lineno
                )
            continue
        if isinstance(enfant, ast.ExceptHandler) and enfant.name:
            bindings.setdefault(enfant.name, enfant.lineno)
        if isinstance(enfant, ast.Name):
            if isinstance(enfant.ctx, ast.Load):
                lectures.append((enfant.lineno, enfant.id))
            else:
                bindings.setdefault(enfant.id, enfant.lineno)
            continue
        if isinstance(enfant, ast.withitem) and enfant.optional_vars is not None:
            _lier(enfant.optional_vars, bindings, enfant.context_expr.lineno)
        _parcourir(enfant, bindings, lectures)


def _lectures_anticipees(source: str) -> list:
    """Les couples (ligne, nom) lus au niveau module avant d'y être écrits."""
    bindings, lectures = {}, []
    _parcourir(ast.parse(source), bindings, lectures)
    fautes = []
    for ligne, nom in lectures:
        ecriture = bindings.get(nom)
        if ecriture is not None and ecriture > ligne:
            fautes.append((ligne, nom, ecriture))
    return sorted(set(fautes))


def test_aucun_nom_lu_avant_d_etre_ecrit():
    """`app.py` se déroule de haut en bas sans rencontrer de nom manquant."""
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    fautes = _lectures_anticipees(source)
    assert not fautes, "\n".join(
        f"ligne {ligne} : « {nom} » n'est écrit qu'à la ligne {ecriture}"
        for ligne, nom, ecriture in fautes
    )


def test_le_controle_voit_la_faute_qu_il_est_censé_voir():
    """Le contrôle attrape bien un nom lu trop tôt, sinon il ne prouve rien."""
    fautes = _lectures_anticipees(
        "import streamlit as st\n"
        "if st.button('x'):\n"
        "    st.write(nom)\n"
        "nom = 'PV Sarnois'\n"
    )
    assert fautes == [(3, "nom", 4)]


def test_le_controle_ne_confond_pas_une_variable_locale():
    """Un nom local à une fonction ou à une compréhension n'est pas du module."""
    assert not _lectures_anticipees(
        "def f():\n"
        "    return calque.nom\n"
        "total = sum(n for n in (1, 2))\n"
        "calque = f\n"
    )


@pytest.mark.parametrize("nom_du_dossier", ["_nom_depot", "_nom_dossier"])
def test_le_nom_se_calcule_a_l_appel(nom_du_dossier):
    """Les deux noms de dossier sont des fonctions, pas des variables posées.

    Une variable en tête de script serait en retard d'une exécution — l'indice
    est choisi au milieu de la section 2 — et en bas de script laisserait la
    section 2 sans nom. Une fonction, appelée là où le nom sert, est juste aux
    deux endroits.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    definitions = [
        n
        for n in arbre.body
        if isinstance(n, ast.FunctionDef) and n.name == nom_du_dossier
    ]
    assert len(definitions) == 1, f"{nom_du_dossier} doit être défini une fois"
    # La commune est passée, pas lue dans les globaux : c'est ce qui rend
    # l'ordre des sections indifférent.
    assert [a.arg for a in definitions[0].args.args] == ["commune"]


def _locaux(fonction) -> set:
    """Les noms liés dans une fonction : paramètres, affectations, imports."""
    noms = set()
    arguments = fonction.args
    for groupe in (arguments.posonlyargs, arguments.args, arguments.kwonlyargs):
        noms.update(a.arg for a in groupe)
    for special in (arguments.vararg, arguments.kwarg):
        if special is not None:
            noms.add(special.arg)
    for petit in ast.walk(fonction):
        if petit is fonction:
            continue
        if isinstance(petit, ast.Name) and isinstance(petit.ctx, (ast.Store, ast.Del)):
            noms.add(petit.id)
        elif isinstance(petit, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Une fonction imbriquée lie son nom et ses paramètres : `_ligne_calque`
            # et son `calque` ne sont pas des globaux du script.
            noms.add(petit.name)
            noms.update(a.arg for a in petit.args.args)
        elif isinstance(petit, ast.ClassDef):
            noms.add(petit.name)
        elif isinstance(petit, ast.Lambda):
            noms.update(a.arg for a in petit.args.args)
        elif isinstance(petit, (ast.Import, ast.ImportFrom)):
            for alias in petit.names:
                noms.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(petit, ast.ExceptHandler) and petit.name:
            noms.add(petit.name)
    return noms


def test_aucune_fonction_ne_lit_un_global_ecrit_plus_bas_qu_elle():
    """Une fonction prend ce dont elle a besoin en paramètre.

    `_deposer` lisait le global `nom`, écrit six cents lignes plus bas : à
    l'import du plan, il n'existait pas encore. Le lire en paramètre rend
    l'ordre des sections indifférent, et rend la faute visible ici plutôt que
    dans le navigateur du chef de projet.
    """
    source = (RACINE / "app.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    bindings, lectures = {}, []
    _parcourir(arbre, bindings, lectures)

    fautes = []
    for noeud in arbre.body:
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        locaux = _locaux(noeud)
        for petit in ast.walk(noeud):
            if not (isinstance(petit, ast.Name) and isinstance(petit.ctx, ast.Load)):
                continue
            if petit.id in locaux:
                continue
            ecriture = bindings.get(petit.id)
            if ecriture is not None and ecriture > noeud.lineno:
                fautes.append((noeud.name, petit.id, ecriture))

    assert not fautes, "\n".join(
        f"{nom_fonction} (ligne du def antérieure) lit le global « {nom} », "
        f"écrit ligne {ecriture}"
        for nom_fonction, nom, ecriture in sorted(set(fautes))
    )
