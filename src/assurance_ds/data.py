"""Données synthétiques d'un assureur fictif.

Tout est généré : aucun client, contrat ou sinistre réel. Les mécanismes que les
sujets doivent retrouver (motifs de départ, scénarios de fraude, événements de
vie) sont injectés volontairement, avec leur vérité terrain, pour pouvoir
mesurer ce que chaque règle attrape et ce qu'elle rate.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

AUJOURDHUI = pd.Timestamp("2026-10-31")

COMMUNES = {
    "Luxembourg": "Luxembourg", "Esch-sur-Alzette": "Esch-sur-Alzette", "Differdange": "Esch-sur-Alzette",
    "Dudelange": "Esch-sur-Alzette", "Pétange": "Esch-sur-Alzette", "Sanem": "Esch-sur-Alzette",
    "Hesperange": "Luxembourg", "Bettembourg": "Esch-sur-Alzette", "Schifflange": "Esch-sur-Alzette",
    "Käerjeng": "Capellen", "Mamer": "Capellen", "Strassen": "Luxembourg", "Bertrange": "Luxembourg",
    "Mersch": "Mersch", "Ettelbruck": "Diekirch", "Diekirch": "Diekirch", "Wiltz": "Wiltz",
    "Echternach": "Echternach", "Remich": "Remich", "Grevenmacher": "Grevenmacher",
}
PRODUITS = {  # produit -> (part des clients, prime moyenne)
    "MRH": (0.70, 420), "AUTO": (0.62, 980), "RC_VIE_PRIVEE": (0.48, 95),
    "PREVOYANCE": (0.15, 640), "EMPRUNTEUR": (0.10, 1150),
}
GARANTIES = {
    "MRH": ["Dégât des eaux", "Vol", "Incendie", "Bris de glace", "Tempête", "Dommages électriques"],
    "AUTO": ["Collision", "Bris de glace", "Vol du véhicule", "Vandalisme", "Catastrophe naturelle"],
    "RC_VIE_PRIVEE": ["Dommage causé à un tiers", "Dommage causé par un animal"],
    "PREVOYANCE": ["Incapacité de travail", "Hospitalisation"],
    "EMPRUNTEUR": ["Incapacité de travail", "Décès"],
}
DESCRIPTIONS = {
    "Dégât des eaux": ["Fuite sous l'évier de la cuisine, parquet gonflé", "Infiltration par la toiture après de fortes pluies",
                       "Débordement de la machine à laver, plafond du voisin taché", "Canalisation percée dans la salle de bain"],
    "Vol": ["Cambriolage avec effraction de la porte d'entrée, bijoux et ordinateur volés",
            "Vélo électrique volé dans la cave de l'immeuble", "Vol de matériel dans le garage, porte forcée"],
    "Incendie": ["Départ de feu dans la cuisine, hotte et placards brûlés", "Court-circuit, incendie dans le salon"],
    "Bris de glace": ["Baie vitrée fissurée par un choc", "Pare-brise fendu par un gravillon sur l'autoroute",
                      "Vitre de la porte-fenêtre cassée pendant un orage"],
    "Tempête": ["Tuiles arrachées par le vent, infiltration dans les combles", "Arbre tombé sur la clôture pendant la tempête"],
    "Dommages électriques": ["Surtension après la foudre, télévision et box hors service"],
    "Collision": ["Accrochage sur un parking, pare-choc arrière enfoncé", "Collision à un carrefour, tiers en tort",
                  "Choc contre un poteau en manœuvrant"],
    "Vol du véhicule": ["Véhicule volé sur la voie publique pendant la nuit"],
    "Vandalisme": ["Carrosserie rayée et rétroviseur arraché", "Pneus crevés sur le parking de la résidence"],
    "Catastrophe naturelle": ["Véhicule endommagé par la grêle", "Inondation du parking souterrain"],
    "Dommage causé à un tiers": ["Ballon dans la vitre du voisin", "Dégât des eaux chez le voisin du dessous"],
    "Dommage causé par un animal": ["Le chien a mordu un passant", "Le chat a renversé un objet chez un ami"],
    "Incapacité de travail": ["Arrêt de travail de trois mois après une opération", "Incapacité suite à une chute"],
    "Hospitalisation": ["Hospitalisation de cinq jours"],
    "Décès": ["Décès de l'assuré, demande de prise en charge du solde du prêt"],
}


@dataclass
class Jeu:
    clients: pd.DataFrame
    contrats: pd.DataFrame
    sinistres: pd.DataFrame
    dossiers: pd.DataFrame       # dossiers récents avec leurs pièces (sujet fraude)


def _dates(rng, debut, fin, n):
    d0, d1 = pd.Timestamp(debut).value // 10**9, pd.Timestamp(fin).value // 10**9
    return pd.to_datetime(rng.integers(d0, d1, n), unit="s").normalize()


def generer(n_clients: int = 12000, n_sinistres: int = 100_000, graine: int = 7) -> Jeu:
    rng = np.random.default_rng(graine)
    communes = list(COMMUNES)

    # ------------------------------------------------------------------ clients
    cl = pd.DataFrame({
        "client_id": [f"C{i:05d}" for i in range(1, n_clients + 1)],
        "age": rng.integers(19, 86, n_clients),
        "commune": rng.choice(communes, n_clients, p=_poids(len(communes), rng)),
        "residence": rng.choice(["résident", "frontalier"], n_clients, p=[0.78, 0.22]),
        "enfants": rng.choice([0, 1, 2, 3], n_clients, p=[0.45, 0.22, 0.23, 0.10]),
        "client_depuis": _dates(rng, "2006-01-01", "2026-06-30", n_clients),
    })
    cl["canton"] = cl["commune"].map(COMMUNES)
    # événements de vie récents (connus de l'assureur : changement d'adresse, déclaration, etc.)
    def evt(p, jours):
        m = rng.random(n_clients) < p
        dates = pd.Series(AUJOURDHUI - pd.to_timedelta(rng.integers(1, jours, n_clients), "D"))
        return dates.where(m)
    cl["demenagement_date"] = evt(0.08, 120)
    cl["naissance_date"] = evt(0.03, 180)
    cl["nouveau_vehicule_date"] = evt(0.05, 120)
    cl["emprunt_date"] = evt(0.035, 150)
    cl["contact_conseiller_date"] = evt(0.35, 365)

    # ----------------------------------------------------------------- contrats
    rows = []
    for _, c in cl.iterrows():
        for prod, (part, prime) in PRODUITS.items():
            p = part
            if prod == "MRH" and c.residence == "frontalier":
                p = 0.05                      # la MRH luxembourgeoise couvre un logement au Luxembourg
            if prod == "EMPRUNTEUR" and c.age > 70:
                p = 0.0
            if rng.random() < p:
                rows.append((c.client_id, prod, prime))
    ct = pd.DataFrame(rows, columns=["client_id", "produit", "prime_ref"])
    n = len(ct)
    ct.insert(0, "contrat_id", [f"P{i:06d}" for i in range(1, n + 1)])
    ct["date_effet"] = _dates(rng, "2012-01-01", "2026-09-30", n)
    ct["prime_precedente"] = (ct.pop("prime_ref") * rng.lognormal(0, 0.25, n)).round(0)
    hausse = rng.choice([0.0, 0.02, 0.04, 0.12, 0.22], n, p=[0.25, 0.35, 0.22, 0.12, 0.06])
    ct["prime_annuelle"] = (ct["prime_precedente"] * (1 + hausse)).round(0)
    # prochaine échéance = anniversaire de la date d'effet
    ech = ct["date_effet"].apply(lambda d: _prochain_anniv(d))
    ct["prochaine_echeance"] = ech
    ct["statut"] = "actif"

    # ---------------------------------------------------------------- sinistres
    poids_prod = ct["produit"].map({"MRH": 1.2, "AUTO": 1.6, "RC_VIE_PRIVEE": 0.4, "PREVOYANCE": 0.5, "EMPRUNTEUR": 0.2})
    idx = rng.choice(n, n_sinistres, p=(poids_prod / poids_prod.sum()).values)
    s = ct.iloc[idx][["contrat_id", "client_id", "produit", "date_effet"]].reset_index(drop=True)
    s["garantie"] = [rng.choice(GARANTIES[p]) for p in s["produit"]]
    debut = np.maximum(s["date_effet"].values.astype("datetime64[D]"), np.datetime64("2021-01-01"))
    span = (np.datetime64("2026-10-25") - debut).astype(int).clip(1)
    s["date_survenance"] = pd.to_datetime(debut) + pd.to_timedelta((rng.random(n_sinistres) * span).astype(int), "D")
    s["date_declaration"] = s["date_survenance"] + pd.to_timedelta(rng.geometric(0.35, n_sinistres) - 1, "D")
    base = {"Incendie": 9000, "Vol": 2500, "Dégât des eaux": 3200, "Tempête": 2800, "Collision": 2400,
            "Vol du véhicule": 14000, "Incapacité de travail": 6000, "Décès": 40000, "Hospitalisation": 3500}
    s["montant_estime"] = (s["garantie"].map(base).fillna(900) * rng.lognormal(0, 0.6, n_sinistres)).round(0)
    u = rng.random(n_sinistres)
    recent = s["date_declaration"] > AUJOURDHUI - pd.Timedelta(days=75)
    s["statut"] = np.select([recent & (u < 0.55), u < 0.08, u < 0.13], ["en cours", "refusé", "en expertise"], "réglé")
    motifs = ["exclusion contractuelle", "garantie non souscrite", "déclaration hors délai", "franchise supérieure au dommage"]
    s["motif_refus"] = np.where(s["statut"] == "refusé", rng.choice(motifs, n_sinistres), None)
    s["delai_reglement_jours"] = np.where(s["statut"] == "réglé", rng.gamma(2.0, 14, n_sinistres).round(0), np.nan)
    s["montant_regle"] = np.where(s["statut"] == "réglé", (s["montant_estime"] * rng.uniform(0.6, 1.0, n_sinistres)).round(0), np.nan)
    s["nb_relances_client"] = rng.poisson(np.where(s["delai_reglement_jours"].fillna(30) > 45, 2.2, 0.4))
    s["reclamation"] = (rng.random(n_sinistres) < np.where(s["statut"] == "refusé", 0.25, 0.03)).astype(int)
    s["canal"] = rng.choice(["web", "agence", "téléphone", "courtier"], n_sinistres, p=[0.4, 0.2, 0.25, 0.15])
    s["gestionnaire"] = rng.choice([f"G{i:02d}" for i in range(1, 26)], n_sinistres)
    s["description"] = [rng.choice(DESCRIPTIONS[g]) for g in s["garantie"]]
    s = s.merge(cl[["client_id", "commune", "canton"]], on="client_id", how="left")
    s = s.sort_values("date_declaration").reset_index(drop=True)
    s.insert(0, "sinistre_id", [f"S{i:06d}" for i in range(1, n_sinistres + 1)])
    s = s.drop(columns=["date_effet"])

    # ------------------------------------------------------- churn (vérité terrain)
    ct, cl = _simuler_departs(rng, cl, ct, s)
    # ---------------------------------------------------- dossiers et pièces (fraude)
    dossiers = _dossiers(rng, s, ct)
    return Jeu(cl, ct, s, dossiers)


def _poids(k, rng):
    w = rng.pareto(1.2, k) + 1
    w[0] *= 4
    return w / w.sum()


def _prochain_anniv(d: pd.Timestamp) -> pd.Timestamp:
    try:
        a = d.replace(year=AUJOURDHUI.year)
    except ValueError:                      # 29 février
        a = d.replace(year=AUJOURDHUI.year, day=28)
    return a if a > AUJOURDHUI else a + pd.DateOffset(years=1)


def _simuler_departs(rng, cl, ct, s):
    """Départ dans les 90 jours, tiré selon des motifs : c'est ce que les règles doivent retrouver."""
    sinistre_mal_vecu = s[(s["statut"] == "refusé") | (s["reclamation"] == 1)
                          | ((s["delai_reglement_jours"] > 50) & (s["nb_relances_client"] >= 2))]
    sinistre_mal_vecu = sinistre_mal_vecu[sinistre_mal_vecu["date_declaration"] > AUJOURDHUI - pd.Timedelta(days=365)]
    mal = set(sinistre_mal_vecu["contrat_id"])
    dem = cl.set_index("client_id")["demenagement_date"].notna()
    contact = cl.set_index("client_id")["contact_conseiller_date"] > AUJOURDHUI - pd.Timedelta(days=180)
    hausse = ct["prime_annuelle"] / ct["prime_precedente"] - 1
    ech = (ct["prochaine_echeance"] - AUJOURDHUI).dt.days
    p = np.full(len(ct), 0.015)
    motif = np.array([None] * len(ct), dtype=object)
    for cond, add, nom in [
        ((ech <= 75) & (hausse >= 0.10), 0.22, "hausse de prime"),
        (ct["contrat_id"].isin(mal), 0.18, "sinistre mal vécu"),
        (ct["client_id"].map(dem) & (ct["produit"] == "MRH"), 0.30, "déménagement"),
        ((ech <= 75) & ~ct["client_id"].map(contact), 0.04, "échéance sans contact"),
    ]:
        cond = cond.fillna(False).values
        p = np.where(cond, p + add, p)
        motif = np.where(cond & (motif == None), nom, motif)  # noqa: E711
    part = rng.random(len(ct)) < p
    ct["depart_90j"] = part.astype(int)                  # vérité terrain (inconnue des règles)
    ct["motif_reel"] = np.where(part, np.where(motif == None, "autre", motif), None)  # noqa: E711
    return ct, cl


def _dossiers(rng, s, ct, n=3000):
    """Dossiers déclarés récemment, avec les champs lus dans les pièces. Scénarios de fraude injectés."""
    pool = s[(s["date_declaration"] > AUJOURDHUI - pd.Timedelta(days=150)) & s["produit"].isin(["MRH", "AUTO"])]
    d = pool.sample(min(n, len(pool)), random_state=11).reset_index(drop=True)
    d = d.merge(ct[["contrat_id", "date_effet"]], on="contrat_id")
    m = len(d)
    d["date_survenance_expert"] = d["date_survenance"]
    d["date_facture_bien"] = d["date_survenance"] - pd.to_timedelta(rng.integers(90, 2000, m), "D")
    d["plainte_deposee"] = np.where(d["garantie"].str.contains("Vol"), (rng.random(m) < 0.93).astype(int), -1)
    d["photos_jointes"] = (rng.random(m) < 0.9).astype(int)
    d["iban"] = [f"LU{rng.integers(10**15, 10**16)}" for _ in range(m)]
    d["bien_reference"] = [f"B{rng.integers(10**7, 10**8)}" for _ in range(m)]
    d["fraude"] = 0
    d["scenario_injecte"] = None

    reserves: set[int] = set()        # dossiers d'origine d'un doublon : on n'y touche plus

    def injecter(k, nom, fn):
        cand = np.array([i for i in d.index[(d["fraude"] == 0)] if i not in reserves])
        ix = rng.choice(cand, k, replace=False)
        for i in ix:
            fn(i)
        d.loc[ix, "fraude"] = 1
        d.loc[ix, "scenario_injecte"] = nom

    def precoce(i):          # contrat souscrit juste avant le sinistre
        d.at[i, "date_effet"] = d.at[i, "date_survenance"] - pd.Timedelta(days=int(rng.integers(2, 25)))
        d.at[i, "montant_estime"] = d.at[i, "montant_estime"] * 2.2

    def date_deplacee(i):    # date déclarée déplacée pour entrer dans la garantie
        d.at[i, "date_survenance_expert"] = d.at[i, "date_survenance"] - pd.Timedelta(days=int(rng.integers(6, 40)))

    def facture_post(i):     # facture du bien postérieure au sinistre
        d.at[i, "date_facture_bien"] = d.at[i, "date_survenance"] + pd.Timedelta(days=int(rng.integers(2, 30)))

    def doublon(i):          # même bien déjà indemnisé sur un autre dossier
        j = int(rng.choice([x for x in d.index[d["fraude"] == 0] if x != i and x not in reserves]))
        reserves.add(j)
        d.at[i, "bien_reference"] = d.at[j, "bien_reference"]
        d.at[i, "iban"] = d.at[j, "iban"]

    injecter(35, "sinistre peu après la souscription", precoce)
    injecter(30, "date de survenance déplacée", date_deplacee)
    injecter(20, "facture postérieure au sinistre", facture_post)
    injecter(15, "bien déjà indemnisé", doublon)
    # bruit : des dossiers honnêtes qui déclenchent aussi des signaux
    honn = d.index[d["fraude"] == 0].to_numpy()
    for i in rng.choice(honn, 60, replace=False):
        d.at[i, "date_effet"] = d.at[i, "date_survenance"] - pd.Timedelta(days=int(rng.integers(2, 29)))
    for i in rng.choice(honn, 12, replace=False):   # l'expert note une date approximative
        d.at[i, "date_survenance_expert"] = d.at[i, "date_survenance"] - pd.Timedelta(days=int(rng.integers(3, 8)))
    vols = d.index[(d["fraude"] == 0) & (d["plainte_deposee"] == 1)].to_numpy()
    d.loc[rng.choice(vols, min(10, len(vols)), replace=False), "plainte_deposee"] = 0
    d.insert(0, "dossier_id", [f"D{i:05d}" for i in range(1, m + 1)])
    return d
