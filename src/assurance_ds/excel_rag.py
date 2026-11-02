"""Sujet 2 — interroger un fichier Excel de 100 000 lignes.

On ne vectorise pas les lignes. Un tableau est déjà structuré : la plupart des
questions sont des agrégations, des filtres ou la recherche d'une ligne, et une
recherche par similarité ne sait ni compter, ni sommer, ni garantir qu'elle a
tout trouvé. La chaîne est donc :

  Excel ─► DuckDB typé ─► fiche de schéma ─► résolution des valeurs ─► routage
        ─► SQL vérifié (lecture seule, colonnes connues, limite) ─► résultat montré
           avec la requête et le nombre de lignes

La recherche textuelle n'intervient que sur la colonne de texte libre
(`description`), et toujours après les filtres structurés.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

import duckdb
import pandas as pd

from .llm import LLM, LLMError

TABLE = "sinistres"

# Ce qu'un gestionnaire dirait de chaque colonne : c'est ce que le modèle lit, pas les données.
DICTIONNAIRE = {
    "sinistre_id": "Identifiant du sinistre (S + 6 chiffres)",
    "contrat_id": "Contrat concerné (P + 6 chiffres)",
    "client_id": "Client (C + 5 chiffres)",
    "produit": "Produit d'assurance : MRH (habitation), AUTO, RC_VIE_PRIVEE, PREVOYANCE, EMPRUNTEUR",
    "garantie": "Garantie mise en jeu (vol, dégât des eaux, collision…)",
    "date_survenance": "Date à laquelle le sinistre s'est produit",
    "date_declaration": "Date à laquelle le client l'a déclaré",
    "montant_estime": "Montant estimé du dommage, en euros",
    "statut": "Où en est le dossier : en cours, en expertise, réglé, refusé",
    "motif_refus": "Raison du refus, renseignée seulement si statut = refusé",
    "delai_reglement_jours": "Jours entre la déclaration et le règlement, renseigné seulement si réglé",
    "montant_regle": "Montant payé, en euros, renseigné seulement si réglé",
    "nb_relances_client": "Nombre de relances du client pendant la gestion",
    "reclamation": "1 si le client a déposé une réclamation, 0 sinon",
    "canal": "Canal de déclaration : web, agence, téléphone, courtier",
    "gestionnaire": "Code du gestionnaire (G01 à G25)",
    "description": "Texte libre saisi à la déclaration",
    "commune": "Commune du client",
    "canton": "Canton du client",
}

# vocabulaire de l'utilisateur -> valeur réelle d'une colonne
SYNONYMES = {
    "habitation": ("produit", "MRH"), "multirisque": ("produit", "MRH"), "maison": ("produit", "MRH"),
    "voiture": ("produit", "AUTO"), "automobile": ("produit", "AUTO"), "auto": ("produit", "AUTO"),
    "responsabilite civile": ("produit", "RC_VIE_PRIVEE"), "rc": ("produit", "RC_VIE_PRIVEE"),
    "pret": ("produit", "EMPRUNTEUR"), "emprunteur": ("produit", "EMPRUNTEUR"),
    "refuse": ("statut", "refusé"), "refus": ("statut", "refusé"), "regle": ("statut", "réglé"),
    "paye": ("statut", "réglé"), "ouvert": ("statut", "en cours"), "expertise": ("statut", "en expertise"),
    "fuite": ("garantie", "Dégât des eaux"), "inondation": ("garantie", "Catastrophe naturelle"),
    "pare-brise": ("garantie", "Bris de glace"), "cambriolage": ("garantie", "Vol"),
    "esch": ("commune", "Esch-sur-Alzette"), "la capitale": ("commune", "Luxembourg"),
}


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s).lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9_\- ]+", " ", s).strip()


# ------------------------------------------------------------------ chargement

def excel_vers_duckdb(xlsx: str | Path, db: str | Path) -> int:
    """Charge l'Excel dans DuckDB avec des types propres (dates, montants, entiers)."""
    df = pd.read_excel(xlsx, engine="openpyxl")
    return dataframe_vers_duckdb(df, db)


def dataframe_vers_duckdb(df: pd.DataFrame, db: str | Path) -> int:
    df = df.copy()
    for c in df.columns:
        if c.startswith("date_"):
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db))
    con.execute(f"DROP TABLE IF EXISTS {TABLE}")
    con.register("df", df)
    con.execute(f"CREATE TABLE {TABLE} AS SELECT * FROM df")
    n = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    con.close()
    return n


# -------------------------------------------------------------- fiche de schéma

def fiche_schema(con: duckdb.DuckDBPyConnection, max_valeurs: int = 30) -> list[dict]:
    cols = con.execute(f"DESCRIBE {TABLE}").fetchall()
    n = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    fiche = []
    for nom, typ, *_ in cols:
        q = f'"{nom}"'
        nulls, distincts = con.execute(f"SELECT count(*) - count({q}), count(DISTINCT {q}) FROM {TABLE}").fetchone()
        col = {"nom": nom, "type": typ, "description": DICTIONNAIRE.get(nom, ""),
               "taux_vide": round(nulls / n, 3), "n_distincts": distincts}
        if typ in ("VARCHAR",) and distincts <= max_valeurs:
            col["valeurs"] = [r[0] for r in con.execute(
                f"SELECT {q}, count(*) c FROM {TABLE} WHERE {q} IS NOT NULL GROUP BY 1 ORDER BY c DESC").fetchall()]
        elif typ not in ("VARCHAR",):
            mn, mx = con.execute(f"SELECT min({q}), max({q}) FROM {TABLE}").fetchone()
            col["min"], col["max"] = str(mn), str(mx)
        else:
            col["exemples"] = [r[0] for r in con.execute(f"SELECT DISTINCT {q} FROM {TABLE} LIMIT 3").fetchall()]
        fiche.append(col)
    return fiche


def fiche_texte(fiche: list[dict]) -> str:
    lignes = []
    for c in fiche:
        info = c.get("valeurs") or (f"de {c['min']} à {c['max']}" if "min" in c else f"ex. {c.get('exemples')}")
        vide = f", vide à {c['taux_vide']:.0%}" if c["taux_vide"] else ""
        lignes.append(f"- {c['nom']} ({c['type']}{vide}) : {c['description']}. Valeurs : {info}")
    return "\n".join(lignes)


# ------------------------------------------------------- résolution des valeurs

def resoudre_valeurs(question: str, fiche: list[dict], seuil: float = 0.86) -> list[dict]:
    """Relie les mots de la question aux valeurs réelles des colonnes (« Esch » -> « Esch-sur-Alzette »)."""
    # pluriels ramenés au singulier (« vols » -> « vol », « dégâts » -> « dégât »)
    brut = _norm(question)
    sing = " ".join(re.sub(r"(?<=[a-z]{3})[sx]$", "", m) for m in brut.split())
    q = brut + " , " + sing
    mots = sing.split()
    trouvees: dict[tuple, dict] = {}
    for terme, (col, val) in SYNONYMES.items():
        if re.search(r"\b" + re.escape(terme) + r"\b", q):
            trouvees[(col, val)] = {"colonne": col, "valeur": val, "terme": terme, "methode": "synonyme"}
    for c in fiche:
        for v in c.get("valeurs", []):
            nv = _norm(v)
            if not nv:
                continue
            if re.search(r"\b" + re.escape(nv) + r"\b", q):
                trouvees[(c["nom"], v)] = {"colonne": c["nom"], "valeur": v, "terme": nv, "methode": "exacte"}
                continue
            k = len(nv.split())
            for i in range(len(mots) - k + 1):
                cand = " ".join(mots[i:i + k])
                r = SequenceMatcher(None, cand, nv).ratio()
                if r >= seuil and len(cand) >= 4:
                    trouvees.setdefault((c["nom"], v), {"colonne": c["nom"], "valeur": v, "terme": cand,
                                                        "methode": f"approchée ({r:.0%})"})
    return list(trouvees.values())


# ----------------------------------------------------------------- garde SQL

_INTERDITS = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|detach|copy|pragma|install|load|export|"
                        r"import|call|set|read_csv|read_parquet|read_json|glob|httpfs|system)\b", re.I)
_MOTS_SQL = set("""select from where and or not in is null as group by order having limit offset count sum avg min max
distinct case when then else end like ilike between asc desc on join left inner with round cast date interval
year month day extract strftime coalesce over partition percentile_cont within quantile_cont median filter true false
date_diff date_trunc current_date nullif lower upper length string_agg list any all exists union""".split())


@dataclass
class Verdict:
    ok: bool
    sql: str
    erreurs: list[str] = field(default_factory=list)


def garde_sql(sql: str, colonnes: set[str], limite: int = 200) -> Verdict:
    s = sql.strip().rstrip(";").strip()
    err = []
    if ";" in s:
        err.append("plusieurs instructions")
    if not re.match(r"^(select|with)\b", s, re.I):
        err.append("seules les requêtes SELECT sont autorisées")
    if _INTERDITS.search(re.sub(r"'[^']*'", "''", s)):
        err.append("mot-clé interdit")
    sans_extract = re.sub(r"\b(extract|trim|substring)\s*\([^)]*\)", "f()", re.sub(r"'[^']*'", "''", s), flags=re.I)
    tables = {t.lower() for t in re.findall(r"\b(?:from|join)\s+([a-zA-Z_][\w]*)", sans_extract, re.I)}
    ctes = {t.lower() for t in re.findall(r"\b([a-zA-Z_]\w*)\s+as\s*\(", s, re.I)}
    autres = tables - {TABLE} - ctes
    if autres:
        err.append(f"table inconnue : {', '.join(sorted(autres))}")
    sans_chaines = re.sub(r"'[^']*'", " ", s)
    alias = {a.lower() for a in re.findall(r"\bas\s+([a-zA-Z_]\w*)", sans_chaines, re.I)}
    idents = {i.lower() for i in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", sans_chaines)}
    inconnus = sorted(i for i in idents - _MOTS_SQL - {c.lower() for c in colonnes} - alias - ctes - {TABLE}
                      if "_" in i and not i.isdigit())
    if inconnus:
        err.append(f"colonne inconnue : {', '.join(inconnus)}")
    if err:
        return Verdict(False, s, err)
    return Verdict(True, f"SELECT * FROM ({s}) AS q LIMIT {limite}")


# --------------------------------------------------------------- routage (LLM)

SYSTEM_ROUTAGE = """Tu aides à interroger une table DuckDB nommée `sinistres` (une ligne par sinistre). \
Tu ne vois jamais les données, seulement la fiche de schéma ci-dessous et les valeurs déjà reconnues dans la \
question. Classe la question puis écris la requête.

Types :
- "agregation" : un nombre, une somme, une moyenne, un classement -> une requête SQL qui calcule.
- "consultation" : une ou quelques lignes précises -> une requête SQL qui filtre et renvoie les colonnes utiles.
- "texte" : la question porte sur le contenu de la description libre -> "sql_filtre" avec seulement la clause \
WHERE structurée (ou "" si aucune), et "texte" avec les mots à chercher dans la description.
- "hors_perimetre" : la table ne permet pas de répondre (dis pourquoi dans "explication").

Règles : SQL DuckDB, une seule instruction SELECT, uniquement les colonnes de la fiche, valeurs exactes de la \
fiche (respecte accents et majuscules). Une colonne vide pour certains statuts se filtre explicitement. \
N'invente pas de colonne : si l'information n'existe pas, c'est "hors_perimetre".
JSON : {"type": "...", "sql": "...", "sql_filtre": "...", "texte": "...", "explication": "une phrase"}"""


def prompt_routage(question: str, fiche: list[dict], valeurs: list[dict]) -> str:
    v = "\n".join(f"- « {x['terme']} » -> {x['colonne']} = '{x['valeur']}'" for x in valeurs) or "(aucune)"
    return f"Fiche de schéma :\n{fiche_texte(fiche)}\n\nValeurs reconnues :\n{v}\n\nQuestion : {question}"


# ----------------------------------------------------------------- exécution

@dataclass
class Reponse:
    question: str
    type: str
    explication: str
    valeurs: list[dict]
    sql: str | None
    colonnes: list[str] = field(default_factory=list)
    lignes: list[list] = field(default_factory=list)
    n_lignes: int = 0
    tronque: bool = False
    duree_ms: float = 0
    alertes: list[str] = field(default_factory=list)


class Interrogateur:
    def __init__(self, db: str | Path, llm: LLM | None = None):
        self.con = duckdb.connect(str(db), read_only=True)
        self.fiche = fiche_schema(self.con)
        self.colonnes = {c["nom"] for c in self.fiche}
        self.llm = llm

    def executer(self, sql: str, question: str = "", type_: str = "agregation", explication: str = "",
                 valeurs: list[dict] | None = None, limite: int = 200) -> Reponse:
        rep = Reponse(question, type_, explication, valeurs or [], sql)
        v = garde_sql(sql, self.colonnes, limite)
        if not v.ok:
            rep.alertes += [f"Requête refusée : {e}" for e in v.erreurs]
            return rep
        t = time.perf_counter()
        try:
            total = self.con.execute(f"SELECT count(*) FROM ({sql.strip().rstrip(';')}) AS q").fetchone()[0]
            res = self.con.execute(v.sql)
        except duckdb.Error as e:
            rep.alertes.append(f"Erreur d'exécution : {str(e).splitlines()[0]}")
            return rep
        rep.colonnes = [d[0] for d in res.description]
        rep.lignes = [[_jsonable(x) for x in r] for r in res.fetchall()]
        rep.duree_ms = round((time.perf_counter() - t) * 1000, 1)
        rep.n_lignes, rep.tronque = total, total > limite
        if total == 0:
            rep.alertes.append("Aucune ligne ne correspond. La réponse est vide : rien n'est complété.")
        elif type_ == "agregation" and all(x is None for x in rep.lignes[0]):
            rep.alertes.append("Le calcul ne porte sur aucune valeur renseignée.")
        if rep.tronque:
            rep.alertes.append(f"{total} lignes correspondent ; seules les {limite} premières sont montrées.")
        return rep

    def recherche_texte(self, filtre: str, texte: str, k: int = 20, question: str = "",
                        valeurs: list[dict] | None = None) -> Reponse:
        """Filtre d'abord (SQL), classe ensuite (TF-IDF sur la description des lignes retenues)."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        where = f" WHERE {filtre}" if filtre.strip() else ""
        sql = f"SELECT sinistre_id, date_survenance, produit, garantie, statut, montant_estime, description FROM {TABLE}{where}"
        rep = self.executer(sql, question, "texte", f"recherche de « {texte} » dans la description", valeurs, limite=10**6)
        if rep.alertes and not rep.lignes:
            return rep
        df = pd.DataFrame(rep.lignes, columns=rep.colonnes)
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), strip_accents="unicode", lowercase=True)
        descs = df["description"].fillna("")
        uniques = descs.unique()
        m = vec.fit_transform(list(uniques) + [texte])
        scores = (m[:-1] @ m[-1].T).toarray().ravel()
        score_par_desc = dict(zip(uniques, scores))
        df["score"] = descs.map(score_par_desc).round(3)
        df = df[df["score"] >= 0.3].sort_values(["score", "date_survenance"], ascending=[False, False])
        rep.n_lignes = len(df)
        rep.tronque = len(df) > k
        rep.colonnes = list(df.columns)
        rep.lignes = df.head(k).values.tolist()
        rep.sql = sql + f"  -- puis classement TF-IDF sur « {texte} »"
        rep.alertes = [] if len(df) else ["Aucune description ne correspond au texte cherché."]
        if rep.tronque:
            rep.alertes.append(f"{len(df)} lignes correspondent ; les {k} plus proches sont montrées.")
        return rep

    def repondre(self, question: str) -> Reponse:
        valeurs = resoudre_valeurs(question, self.fiche)
        if self.llm is None:
            return Reponse(question, "non_route", "Routage indisponible sans modèle.", valeurs, None,
                           alertes=["Aucun modèle configuré (LLM_API_KEY)."])
        try:
            r = self.llm.json(SYSTEM_ROUTAGE, prompt_routage(question, self.fiche, valeurs))
        except LLMError as e:
            return Reponse(question, "erreur", str(e), valeurs, None, alertes=[str(e)])
        t = r.get("type", "hors_perimetre")
        if t == "hors_perimetre":
            return Reponse(question, t, r.get("explication", ""), valeurs, None,
                           alertes=["La table ne permet pas de répondre à cette question."])
        if t == "texte":
            return self.recherche_texte(r.get("sql_filtre", ""), r.get("texte", question), question=question, valeurs=valeurs)
        return self.executer(r.get("sql", ""), question, t, r.get("explication", ""), valeurs,
                             limite=50 if t == "consultation" else 200)


def _jsonable(x):
    if x is None:
        return None
    if hasattr(x, "isoformat"):
        return x.isoformat()
    if isinstance(x, float):
        return round(x, 2)
    return x if isinstance(x, (int, str, bool)) else str(x)


# ---------------------------------------------------------- jeu d'évaluation

QUESTIONS = [
    {"id": "q1", "question": "Combien de sinistres auto ont été refusés en 2025 ?", "type": "agregation",
     "sql": "SELECT count(*) AS nb FROM sinistres WHERE produit = 'AUTO' AND statut = 'refusé' AND year(date_declaration) = 2025"},
    {"id": "q2", "question": "Quel est le délai moyen de règlement des dégâts des eaux, par canton ?", "type": "agregation",
     "sql": "SELECT canton, round(avg(delai_reglement_jours), 1) AS delai_moyen_jours, count(*) AS nb_regles FROM sinistres "
            "WHERE garantie = 'Dégât des eaux' AND statut = 'réglé' GROUP BY canton ORDER BY delai_moyen_jours DESC"},
    {"id": "q3", "question": "Montre-moi le sinistre S045120", "type": "consultation",
     "sql": "SELECT * FROM sinistres WHERE sinistre_id = 'S045120'"},
    {"id": "q4", "question": "Quels sont les motifs de refus les plus fréquents en habitation ?", "type": "agregation",
     "sql": "SELECT motif_refus, count(*) AS nb FROM sinistres WHERE produit = 'MRH' AND statut = 'refusé' "
            "GROUP BY motif_refus ORDER BY nb DESC"},
    {"id": "q5", "question": "Combien a-t-on payé pour des vols à Esch en 2026 ?", "type": "agregation",
     "sql": "SELECT count(*) AS nb_regles, sum(montant_regle) AS total_paye_eur FROM sinistres WHERE garantie = 'Vol' "
            "AND commune = 'Esch-sur-Alzette' AND statut = 'réglé' AND year(date_declaration) = 2026"},
    {"id": "q6", "question": "Quels gestionnaires ont le plus de dossiers avec réclamation cette année ?", "type": "agregation",
     "sql": "SELECT gestionnaire, count(*) AS nb_reclamations FROM sinistres WHERE reclamation = 1 "
            "AND year(date_declaration) = 2026 GROUP BY gestionnaire ORDER BY nb_reclamations DESC LIMIT 5"},
    {"id": "q7", "question": "Retrouve les vols de vélo dans une cave déclarés en 2026", "type": "texte",
     "sql_filtre": "garantie = 'Vol' AND year(date_declaration) = 2026", "texte": "vélo volé dans la cave"},
    {"id": "q8", "question": "Quel est le taux de satisfaction des clients après règlement ?", "type": "hors_perimetre",
     "explication": "La table ne contient aucune mesure de satisfaction ; les réclamations et relances en sont un indice partiel, pas une mesure."},
]


def comparer(a: Reponse, b: Reponse) -> bool:
    """Deux réponses sont équivalentes si leurs résultats sont égaux (ordre des lignes ignoré, valeurs arrondies)."""
    def norm(r):
        return sorted(tuple(round(x, 1) if isinstance(x, float) else x for x in l) for l in r.lignes)
    return a.n_lignes == b.n_lignes and norm(a) == norm(b)
