import pytest

from assurance_ds import churn, fraude, reco
from assurance_ds.data import generer
from assurance_ds.excel_rag import (QUESTIONS, SYSTEM_ROUTAGE, Interrogateur, comparer, dataframe_vers_duckdb,
                                    garde_sql, resoudre_valeurs)
from assurance_ds.llm import LLM


@pytest.fixture(scope="module")
def jeu():
    return generer(n_clients=3000, n_sinistres=20000, graine=3)


@pytest.fixture(scope="module")
def interro(jeu, tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "s.duckdb"
    dataframe_vers_duckdb(jeu.sinistres, db)
    return Interrogateur(db)


def test_generation_deterministe():
    a, b = generer(500, 2000, 1), generer(500, 2000, 1)
    assert a.sinistres.equals(b.sinistres)


# ------------------------------------------------------------------ sujet 2

def test_garde_sql(interro):
    cols = interro.colonnes
    assert garde_sql("SELECT count(*) FROM sinistres WHERE statut = 'refusé'", cols).ok
    assert not garde_sql("DROP TABLE sinistres", cols).ok
    assert not garde_sql("SELECT 1; DELETE FROM sinistres", cols).ok
    assert not garde_sql("SELECT montant_total FROM sinistres", cols).ok      # colonne inventée
    assert not garde_sql("SELECT * FROM read_parquet('x')", cols).ok
    assert garde_sql("SELECT * FROM sinistres", cols).sql.endswith("LIMIT 200")


def test_resolution_des_valeurs(interro):
    v = {(x["colonne"], x["valeur"]) for x in resoudre_valeurs("vols payés à Esch en voiture", interro.fiche)}
    assert {("garantie", "Vol"), ("statut", "réglé"), ("commune", "Esch-sur-Alzette"), ("produit", "AUTO")} <= v
    v = {(x["colonne"], x["valeur"]) for x in resoudre_valeurs("dégats des eaux refusés", interro.fiche)}
    assert {("garantie", "Dégât des eaux"), ("statut", "refusé")} <= v


def test_reponse_vide_dite(interro):
    r = interro.executer("SELECT * FROM sinistres WHERE commune = 'Paris'")
    assert r.n_lignes == 0 and any("vide" in a for a in r.alertes)


def test_routage_bout_en_bout_et_evaluation(interro):
    """Le modèle est rejoué : une bonne requête, une requête fausse, une colonne inventée."""
    bonne = QUESTIONS[0]
    replay = {
        bonne["question"]: {"type": "agregation", "sql": "SELECT count(*) FROM sinistres WHERE produit='AUTO' "
                            "AND statut='refusé' AND extract(year FROM date_declaration)=2025"},
        QUESTIONS[3]["question"]: {"type": "agregation", "sql": "SELECT motif_refus, count(*) FROM sinistres "
                                   "WHERE statut='refusé' GROUP BY 1"},   # oublie le filtre MRH
        QUESTIONS[7]["question"]: {"type": "agregation", "sql": "SELECT avg(note_satisfaction) FROM sinistres"},
    }
    it = interro
    it.llm = LLM("replay", replay)
    ref = it.executer(bonne["sql"])
    assert comparer(it.repondre(bonne["question"]), ref)
    assert not comparer(it.repondre(QUESTIONS[3]["question"]), it.executer(QUESTIONS[3]["sql"]))
    r = it.repondre(QUESTIONS[7]["question"])
    assert r.n_lignes == 0 and any("colonne inconnue" in a for a in r.alertes)
    it.llm = None


def test_recherche_texte_filtre_puis_classe(interro):
    r = interro.recherche_texte("garantie = 'Vol'", "vélo volé dans la cave")
    assert r.lignes and "vélo" in r.lignes[0][-2].lower()
    assert all(l[3] == "Vol" for l in r.lignes)


# ------------------------------------------------------------------ sujet 5

def test_churn_chaque_alerte_a_un_motif_un_fait_une_action(jeu):
    a = churn.alertes_conseiller(jeu)
    assert len(a) and a["fait"].str.len().gt(10).all() and a["action"].notna().all()
    assert set(a["motif"]) <= set(churn.ACTIONS)
    m = churn.mesurer(jeu)
    forts = [x for x in m["par_motif"] if x["fort"]]
    assert all(x["taux_depart_signales"] > 2 * m["taux_depart_moyen"] for x in forts)
    assert m["clients_non_signales"] > 0          # on se tait sur une partie des clients


# ------------------------------------------------------------------ sujet 6

def test_fraude_chaque_scenario_injecte_est_vu_par_son_signal(jeu):
    s = fraude.signaux(jeu.dossiers)
    attendu = {"date de survenance déplacée": "dates_incoherentes", "facture postérieure au sinistre": "facture_posterieure",
               "bien déjà indemnisé": "bien_deja_indemnise", "sinistre peu après la souscription": "souscription_recente"}
    for scen, sig in attendu.items():
        ids = set(jeu.dossiers.loc[jeu.dossiers["scenario_injecte"] == scen, "dossier_id"])
        vus = set(s.loc[s["signal"] == sig, "dossier_id"])
        assert ids and ids <= vus, scen
    assert s[["source_a", "source_b"]].notna().all().all()   # chaque signal cite ses deux pièces


def test_fraude_le_signal_faible_seul_n_est_pas_une_preuve(jeu):
    m = {x["cle"]: x for x in fraude.mesurer(jeu.dossiers)["par_signal"]}
    assert m["souscription_recente"]["taux_confirmation"] < 0.5        # beaucoup de dossiers honnêtes
    assert m["facture_posterieure"]["taux_confirmation"] > 0.8


# ------------------------------------------------------------------ sujet 7

def test_reco_jamais_deja_detenu_ni_ineligible(jeu):
    p, e = reco.recommander(jeu)
    c = reco.controler(jeu, p)
    assert c["deja_detenu"] == 0 and c["ineligibles"] == 0
    assert p["raison"].str.len().gt(10).all()
    assert p.groupby("client_id").size().max() <= 2
    assert (e["ecarte_car"].str.startswith("non souscriptible")).any()
