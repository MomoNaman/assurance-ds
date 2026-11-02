"""Sujet 6 — fraude : des scénarios nommés, chacun avec sa trace, sa preuve et sa décision.

Scénario principal : le sinistre « arrangé » autour de la souscription (souscrit
juste avant, ou date déplacée pour entrer dans la garantie). Chaque signal est une
comparaison de champs lus dans des pièces différentes, avec leur source. Le
gestionnaire voit les incohérences et les pièces manquantes, pas un score.
"""
from __future__ import annotations

import pandas as pd

SIGNAUX = {
    "souscription_recente": {
        "libelle": "Sinistre peu après la souscription",
        "decision": "Vérifier l'antériorité : date d'achat du bien, photos datées, déclaration de risque à la souscription.",
        "fort": False},
    "dates_incoherentes": {
        "libelle": "Date de survenance différente entre déclaration et expertise",
        "decision": "Demander à l'assuré d'expliquer l'écart ; confronter avec un élément daté (plainte, facture de réparation).",
        "fort": True},
    "facture_posterieure": {
        "libelle": "Facture du bien postérieure au sinistre",
        "decision": "Demander la preuve de possession avant le sinistre ; bloquer le règlement en attendant.",
        "fort": True},
    "plainte_manquante": {
        "libelle": "Vol sans dépôt de plainte",
        "decision": "Demander le récépissé de plainte : pièce obligatoire pour un vol, le règlement en dépend.",
        "fort": False},
    "bien_deja_indemnise": {
        "libelle": "Même bien ou même IBAN sur un autre dossier",
        "decision": "Ouvrir les deux dossiers côte à côte ; missionner un expert si le bien est le même.",
        "fort": True},
}


def _d(x) -> str:
    return pd.Timestamp(x).strftime("%d/%m/%Y")


def signaux(dossiers: pd.DataFrame, jours_souscription: int = 30) -> pd.DataFrame:
    """Une ligne par signal déclenché, avec les deux valeurs comparées et leur source."""
    d = dossiers
    out = []
    ecart = (d["date_survenance"] - d["date_effet"]).dt.days
    for i in d.index[(ecart >= 0) & (ecart < jours_souscription)]:
        r = d.loc[i]
        out.append((r.dossier_id, "souscription_recente",
                    f"Contrat en vigueur depuis le {_d(r.date_effet)}", "conditions particulières",
                    f"Sinistre le {_d(r.date_survenance)}, {ecart[i]} jours plus tard", "déclaration de sinistre"))
    diff = (d["date_survenance"] - d["date_survenance_expert"]).dt.days.abs()
    for i in d.index[diff > 2]:
        r = d.loc[i]
        out.append((r.dossier_id, "dates_incoherentes", f"Survenance déclarée : {_d(r.date_survenance)}",
                    "déclaration de sinistre, p. 1", f"Survenance constatée : {_d(r.date_survenance_expert)}", "rapport d'expertise, p. 2"))
    for i in d.index[d["date_facture_bien"] > d["date_survenance"]]:
        r = d.loc[i]
        out.append((r.dossier_id, "facture_posterieure", f"Facture d'achat du {_d(r.date_facture_bien)}", "facture jointe",
                    f"Sinistre déclaré le {_d(r.date_survenance)}", "déclaration de sinistre"))
    for i in d.index[d["plainte_deposee"] == 0]:
        r = d.loc[i]
        out.append((r.dossier_id, "plainte_manquante", f"Garantie mise en jeu : {r.garantie}", "déclaration de sinistre",
                    "Aucun récépissé de plainte dans le dossier", "liste des pièces"))
    for col, lib in (("bien_reference", "bien"), ("iban", "IBAN")):
        dup = d[d.duplicated(col, keep=False)]
        for _, g in dup.groupby(col):
            for i in g.index:
                r = d.loc[i]
                autres = ", ".join(x for x in g["dossier_id"] if x != r.dossier_id)
                out.append((r.dossier_id, "bien_deja_indemnise", f"{lib.capitalize()} {r[col]}", "pièces du dossier",
                            f"Même {lib} sur le dossier {autres}", "historique des dossiers"))
    s = pd.DataFrame(out, columns=["dossier_id", "signal", "valeur_a", "source_a", "valeur_b", "source_b"])
    return s.drop_duplicates(["dossier_id", "signal"])


def file_gestionnaire(dossiers: pd.DataFrame) -> pd.DataFrame:
    """Dossiers à regarder : d'abord ceux qui cumulent des signaux forts, puis par montant."""
    s = signaux(dossiers)
    s["fort"] = s["signal"].map(lambda x: SIGNAUX[x]["fort"])
    agg = s.groupby("dossier_id").agg(n_signaux=("signal", "size"), n_forts=("fort", "sum"),
                                      signaux=("signal", list)).reset_index()
    f = agg.merge(dossiers, on="dossier_id")
    f["priorite"] = f["n_forts"] * 2 + f["n_signaux"]
    return f.sort_values(["priorite", "montant_estime"], ascending=False).reset_index(drop=True)


def mesurer(dossiers: pd.DataFrame) -> dict:
    """Taux de confirmation de chaque signal (vérité terrain simulée). En vrai : le résultat des enquêtes."""
    s = signaux(dossiers)
    lab = dossiers.set_index("dossier_id")["fraude"]
    res = []
    for k, meta in SIGNAUX.items():
        ids = s.loc[s["signal"] == k, "dossier_id"].unique()
        conf = lab.loc[ids].mean() if len(ids) else None
        res.append({"signal": meta["libelle"], "cle": k, "declenche": int(len(ids)),
                    "confirmes": int(lab.loc[ids].sum()) if len(ids) else 0,
                    "taux_confirmation": round(float(conf), 3) if conf is not None else None, "fort": meta["fort"]})
    f = file_gestionnaire(dossiers)
    n_fraudes = int(lab.sum())
    attrapes = int(lab.loc[f["dossier_id"]].sum())
    deux_plus = f[f["n_signaux"] >= 2]
    return {"dossiers": int(len(dossiers)), "fraudes_injectees": n_fraudes, "dossiers_signales": int(len(f)),
            "fraudes_signalees": attrapes, "par_signal": res,
            "precision_deux_signaux_ou_plus": round(float(lab.loc[deux_plus["dossier_id"]].mean()), 3) if len(deux_plus) else None,
            "fraudes_non_vues": int(n_fraudes - attrapes)}
