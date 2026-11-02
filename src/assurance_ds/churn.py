"""Sujet 5 — churn : un motif, un fait, une action ; et le silence quand il n'y a pas de motif.

Pas de score global. Chaque motif est une règle lisible, avec le fait qui la
déclenche (vérifiable dans le dossier) et l'action que le conseiller peut
proposer. Un client sans motif identifiable n'est pas signalé : un score sans
raison ne donne rien à dire au client.
"""
from __future__ import annotations

import pandas as pd

from .data import AUJOURDHUI, Jeu

ACTIONS = {
    "hausse de prime": "Expliquer la hausse avant l'échéance ; proposer une franchise plus haute ou un regroupement de contrats.",
    "sinistre mal vécu": "Rappel par le gestionnaire du sinistre : expliquer la décision, faire le point sur ce qui reste ouvert.",
    "déménagement": "Adapter la MRH au nouveau logement plutôt que la laisser résilier : nouvelle adresse, surface, capital.",
    "échéance sans contact": "Revue du contrat avant l'échéance : garanties encore adaptées, besoins nouveaux.",
}
ORDRE = ["déménagement", "hausse de prime", "sinistre mal vécu", "échéance sans contact"]


def _fmt(d) -> str:
    return pd.Timestamp(d).strftime("%d/%m/%Y")


def detecter(jeu: Jeu, horizon_echeance: int = 75) -> pd.DataFrame:
    """Une ligne par (contrat, motif) déclenché, avec le fait qui le prouve."""
    ct = jeu.contrats.merge(jeu.clients, on="client_id")
    ech = (ct["prochaine_echeance"] - AUJOURDHUI).dt.days
    hausse = ct["prime_annuelle"] / ct["prime_precedente"] - 1
    out = []

    m = (ech <= horizon_echeance) & (hausse >= 0.10)
    for _, r in ct[m].iterrows():
        h = r.prime_annuelle / r.prime_precedente - 1
        out.append((r.contrat_id, "hausse de prime",
                    f"Prime {r.produit} +{h:.0%} ({r.prime_precedente:.0f} → {r.prime_annuelle:.0f} €) à l'échéance du {_fmt(r.prochaine_echeance)}"))

    s = jeu.sinistres
    s = s[s["date_declaration"] > AUJOURDHUI - pd.Timedelta(days=365)]
    # un refus, une réclamation, ou un règlement long ET relancé : pas chaque sinistre un peu lent
    mal = s[(s["statut"] == "refusé") | (s["reclamation"] == 1)
            | ((s["delai_reglement_jours"] > 60) & (s["nb_relances_client"] >= 2))]
    mal = mal.sort_values("date_declaration").groupby("contrat_id").tail(1)
    for _, r in mal.iterrows():
        if r.statut == "refusé":
            fait = f"Sinistre {r.sinistre_id} ({r.garantie}) refusé — {r.motif_refus}"
        elif r.reclamation:
            fait = f"Réclamation sur le sinistre {r.sinistre_id} ({r.garantie})"
        else:
            fait = (f"Sinistre {r.sinistre_id} réglé en {r.delai_reglement_jours:.0f} jours, "
                    f"après {r.nb_relances_client} relances du client")
        out.append((r.contrat_id, "sinistre mal vécu", fait + f", déclaré le {_fmt(r.date_declaration)}"))

    m = ct["demenagement_date"].notna() & (ct["produit"] == "MRH")
    for _, r in ct[m].iterrows():
        out.append((r.contrat_id, "déménagement", f"Changement d'adresse enregistré le {_fmt(r.demenagement_date)}"))

    recent = ct["contact_conseiller_date"] > AUJOURDHUI - pd.Timedelta(days=180)
    m = (ech <= horizon_echeance) & ~recent
    for _, r in ct[m].iterrows():
        out.append((r.contrat_id, "échéance sans contact",
                    f"Échéance {r.produit} le {_fmt(r.prochaine_echeance)}, aucun contact depuis plus de 6 mois"))
    return pd.DataFrame(out, columns=["contrat_id", "motif", "fait"])


def alertes_conseiller(jeu: Jeu) -> pd.DataFrame:
    """Une ligne par client : le motif le plus actionnable, ses faits, l'action, ce qu'il détient."""
    d = detecter(jeu).merge(jeu.contrats[["contrat_id", "client_id", "produit", "prime_annuelle", "prochaine_echeance"]], on="contrat_id")
    d["rang"] = d["motif"].map({m: i for i, m in enumerate(ORDRE)})
    detenus = jeu.contrats.groupby("client_id")["produit"].apply(lambda x: sorted(set(x)))
    prime_tot = jeu.contrats.groupby("client_id")["prime_annuelle"].sum()
    lignes = []
    for cid, g in d.sort_values(["rang"]).groupby("client_id", sort=False):
        top = g.iloc[0]
        autres = g[g["motif"] != top.motif]["motif"].unique().tolist()
        lignes.append({
            "client_id": cid, "motif": top.motif, "produit": top.produit, "fait": top.fait,
            "autres_faits": g["fait"].tolist()[1:4], "autres_motifs": autres,
            "action": ACTIONS[top.motif], "detenus": detenus[cid], "prime_totale": float(prime_tot[cid]),
            "echeance": _fmt(top.prochaine_echeance), "fort": top.motif != "échéance sans contact",
        })
    a = pd.DataFrame(lignes)
    a["ordre"] = a["motif"].map({m: i for i, m in enumerate(ORDRE)})
    return a.sort_values(["ordre", "prime_totale"], ascending=[True, False]).drop(columns="ordre").reset_index(drop=True)


def mesurer(jeu: Jeu) -> dict:
    """Ce que chaque règle attrape, contre la vérité terrain simulée. En vrai : un groupe témoin non contacté."""
    d = detecter(jeu)
    ct = jeu.contrats
    base = ct["depart_90j"].mean()
    res = []
    for motif in ORDRE:
        ids = set(d.loc[d["motif"] == motif, "contrat_id"])
        sel = ct[ct["contrat_id"].isin(ids)]
        res.append({"motif": motif, "contrats_signales": len(sel), "fort": motif != "échéance sans contact",
                    "taux_depart_signales": round(sel["depart_90j"].mean(), 3) if len(sel) else None,
                    "fois_le_taux_moyen": round(sel["depart_90j"].mean() / base, 1) if len(sel) else None})
    signales = set(d["contrat_id"])
    non = ct[~ct["contrat_id"].isin(signales)]
    alertes = alertes_conseiller(jeu)
    return {"taux_depart_moyen": round(base, 3), "par_motif": res,
            "clients_motif_fort": int(alertes["fort"].sum()), "clients_signal_faible_seul": int((~alertes["fort"]).sum()),
            "departs_sans_motif_visible": int(ct[(ct["depart_90j"] == 1) & ~ct["contrat_id"].isin(signales)].shape[0]),
            "taux_depart_non_signales": round(non["depart_90j"].mean(), 3),
            "clients_non_signales": int(jeu.clients.shape[0] - d.merge(ct, on="contrat_id")["client_id"].nunique())}
