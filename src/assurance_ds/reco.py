"""Sujet 7 — recommandation : éligibilité d'abord, événement de vie ensuite, raison toujours affichée.

1. On écarte ce que le client détient déjà et ce qu'il ne peut pas souscrire
   (règles explicites, justes à 100 % : ce n'est pas le rôle d'un modèle).
2. On propose à partir d'événements de vie lisibles dans les données.
3. Chaque proposition porte sa raison, que le conseiller peut vérifier et écarter.
"""
from __future__ import annotations

import pandas as pd

from .data import AUJOURDHUI, Jeu

# produit -> (règle d'éligibilité, raison si inéligible)
ELIGIBILITE = {
    "MRH": (lambda c: c.residence == "résident", "la MRH couvre un logement au Luxembourg ; client frontalier"),
    "AUTO": (lambda c: True, ""),
    "RC_VIE_PRIVEE": (lambda c: True, ""),
    "PREVOYANCE": (lambda c: c.age < 62, "souscription fermée après 62 ans"),
    "EMPRUNTEUR": (lambda c: c.age <= 70, "souscription fermée après 70 ans"),
}

# déclencheur -> (champ date, produit proposé, formulation, poids)
DECLENCHEURS = [
    ("demenagement_date", "MRH", "Nouvelle adresse depuis {j} jours, pas de MRH chez nous", 3),
    ("nouveau_vehicule_date", "AUTO", "Nouveau véhicule déclaré il y a {j} jours, pas d'assurance auto chez nous", 3),
    ("emprunt_date", "EMPRUNTEUR", "Prêt immobilier signalé il y a {j} jours, pas d'assurance emprunteur chez nous", 3),
    ("naissance_date", "RC_VIE_PRIVEE", "Naissance il y a {j} jours : la RC vie privée couvre aussi les enfants", 2),
    ("naissance_date", "PREVOYANCE", "Naissance il y a {j} jours, aucune prévoyance : revenus du foyer non protégés", 2),
]


def recommander(jeu: Jeu, max_par_client: int = 2) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne (propositions, écartées) ; les écartées disent pourquoi, pour que le filtre se vérifie."""
    detenus = jeu.contrats.groupby("client_id")["produit"].apply(set).to_dict()
    props, ecartees = [], []
    for c in jeu.clients.itertuples():
        d = detenus.get(c.client_id, set())
        cands = []
        for champ, produit, phrase, poids in DECLENCHEURS:
            date = getattr(c, champ)
            if pd.isna(date):
                continue
            j = (AUJOURDHUI - date).days
            raison = phrase.format(j=j)
            if produit in d:
                ecartees.append((c.client_id, produit, raison, "déjà détenu"))
                continue
            ok, pourquoi = ELIGIBILITE[produit]
            if not ok(c):
                ecartees.append((c.client_id, produit, raison, f"non souscriptible : {pourquoi}"))
                continue
            cands.append((poids, -j, produit, raison, champ))
        # complément fréquent, signal faible : MRH sans RC vie privée
        if "MRH" in d and "RC_VIE_PRIVEE" not in d and not any(x[2] == "RC_VIE_PRIVEE" for x in cands):
            cands.append((1, 0, "RC_VIE_PRIVEE", "Assure son logement chez nous mais pas sa responsabilité civile", "complement"))
        vus = set()
        for poids, _, produit, raison, champ in sorted(cands, reverse=True):
            if produit in vus or len(vus) >= max_par_client:
                continue
            vus.add(produit)
            props.append({"client_id": c.client_id, "produit": produit, "raison": raison, "declencheur": champ,
                          "force": "forte" if poids >= 2 else "faible", "detenus": sorted(d), "age": int(c.age),
                          "residence": c.residence, "commune": c.commune})
    p = pd.DataFrame(props)
    e = pd.DataFrame(ecartees, columns=["client_id", "produit", "raison", "ecarte_car"])
    return p, e


def controler(jeu: Jeu, props: pd.DataFrame) -> dict:
    """Garde-fous vérifiés à chaque exécution : rien de déjà détenu, rien d'inéligible."""
    detenus = jeu.contrats.groupby("client_id")["produit"].apply(set).to_dict()
    cl = jeu.clients.set_index("client_id")
    deja = sum(r.produit in detenus.get(r.client_id, set()) for r in props.itertuples())
    inelig = sum(not ELIGIBILITE[r.produit][0](cl.loc[r.client_id]) for r in props.itertuples())
    return {"propositions": int(len(props)), "clients_concernes": int(props["client_id"].nunique()),
            "deja_detenu": int(deja), "ineligibles": int(inelig),
            "par_declencheur": props.groupby("declencheur").size().to_dict(),
            "fortes": int((props["force"] == "forte").sum())}
