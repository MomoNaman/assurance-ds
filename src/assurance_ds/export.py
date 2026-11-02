"""Calcule tout une fois et écrit les JSON de l'interface (aucun serveur, aucune clé côté visiteur)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import churn, fraude, reco
from .data import AUJOURDHUI, generer
from .excel_rag import QUESTIONS, Interrogateur, dataframe_vers_duckdb, excel_vers_duckdb, garde_sql, resoudre_valeurs


def _ecrire(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, default=_conv), encoding="utf-8")


def _conv(x):
    if isinstance(x, pd.Timestamp):
        return x.strftime("%Y-%m-%d")
    if hasattr(x, "item"):
        return x.item()
    if isinstance(x, (set, tuple)):
        return list(x)
    return str(x)


def exporter(web: Path, db: Path, xlsx: Path, relire_excel: bool = True) -> None:
    jeu = generer()
    if relire_excel and xlsx.exists():
        n = excel_vers_duckdb(xlsx, db)
        source = f"{xlsx.name} ({n} lignes)"
    else:
        n = dataframe_vers_duckdb(jeu.sinistres, db)
        source = f"génération directe ({n} lignes)"

    # ---------------------------------------------------------------- sujet 2
    it = Interrogateur(db)
    cas = []
    for q in QUESTIONS:
        valeurs = resoudre_valeurs(q["question"], it.fiche)
        if q["type"] == "texte":
            r = it.recherche_texte(q["sql_filtre"], q["texte"], question=q["question"], valeurs=valeurs)
        elif q["type"] == "hors_perimetre":
            r = None
        else:
            r = it.executer(q["sql"], q["question"], q["type"], valeurs=valeurs, limite=50)
        cas.append({**q, "valeurs": valeurs, "resultat": (r.__dict__ | {"lignes": r.lignes[:25]}) if r else None})
    refus = [{"sql": s, "erreurs": garde_sql(s, it.colonnes).erreurs} for s in (
        "DELETE FROM sinistres WHERE statut = 'refusé'",
        "SELECT client_nom, montant_regle FROM sinistres",
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM contrats",
    )]
    _ecrire(web / "excel.json", {"source": source, "n_lignes": n, "fiche": it.fiche, "cas": cas, "refus": refus})

    # ---------------------------------------------------------------- sujet 5
    al = churn.alertes_conseiller(jeu)
    forts = al[al["fort"]].head(150)
    faibles = al[~al["fort"]].head(40)
    _ecrire(web / "churn.json", {"aujourdhui": AUJOURDHUI.strftime("%d/%m/%Y"), "mesures": churn.mesurer(jeu),
                                 "actions": churn.ACTIONS, "alertes": pd.concat([forts, faibles]).to_dict("records")})

    # ---------------------------------------------------------------- sujet 6
    f = fraude.file_gestionnaire(jeu.dossiers).head(120)
    sig = fraude.signaux(jeu.dossiers)
    sig = sig[sig["dossier_id"].isin(f["dossier_id"])]
    dossiers = []
    for r in f.itertuples():
        dossiers.append({
            "dossier_id": r.dossier_id, "contrat_id": r.contrat_id, "produit": r.produit, "garantie": r.garantie,
            "montant_estime": r.montant_estime, "date_survenance": r.date_survenance, "date_declaration": r.date_declaration,
            "canal": r.canal, "description": r.description, "n_signaux": r.n_signaux, "n_forts": int(r.n_forts),
            "signaux": sig[sig["dossier_id"] == r.dossier_id].drop(columns="dossier_id").to_dict("records"),
            "verite": {"fraude": int(r.fraude), "scenario": r.scenario_injecte},
        })
    _ecrire(web / "fraude.json", {"mesures": fraude.mesurer(jeu.dossiers), "signaux": fraude.SIGNAUX, "dossiers": dossiers})

    # ---------------------------------------------------------------- sujet 7
    props, ecartees = reco.recommander(jeu)
    fortes = props[props["force"] == "forte"].head(120)
    faibles = props[props["force"] == "faible"].head(30)
    _ecrire(web / "reco.json", {"controle": reco.controler(jeu, props),
                                "propositions": pd.concat([fortes, faibles]).to_dict("records"),
                                "ecartees": ecartees.groupby("ecarte_car").head(8).to_dict("records"),
                                "ecartees_par_motif": ecartees["ecarte_car"].value_counts().to_dict()})
    print(f"export : {web}/excel.json, churn.json, fraude.json, reco.json (source sujet 2 : {source})")
