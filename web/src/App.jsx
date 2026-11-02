import { useEffect, useMemo, useState } from "react";

const ONGLETS = [
  { id: "excel", num: "2", titre: "Excel 100 000 lignes" },
  { id: "churn", num: "5", titre: "Churn" },
  { id: "fraude", num: "6", titre: "Fraude" },
  { id: "reco", num: "7", titre: "Recommandation" },
  { id: "methode", num: "", titre: "Méthode" },
];

function useJson(f) {
  const [d, setD] = useState(null);
  useEffect(() => { fetch(f).then((r) => r.json()).then(setD).catch(() => setD({ erreur: true })); }, [f]);
  return d;
}

const pct = (x) => (x == null ? "—" : `${Math.round(x * 1000) / 10} %`);
const eur = (x) => (x == null ? "—" : `${Math.round(x).toLocaleString("fr-FR")} €`);
const nb = (x) => (x == null ? "—" : x.toLocaleString("fr-FR"));
const PRODUITS = { MRH: "Habitation", AUTO: "Auto", RC_VIE_PRIVEE: "RC vie privée", PREVOYANCE: "Prévoyance", EMPRUNTEUR: "Emprunteur" };

export default function App() {
  const init = (typeof location !== "undefined" && location.hash.slice(1)) || "excel";
  const [onglet, setOnglet] = useState(ONGLETS.some((o) => o.id === init) ? init : "excel");
  useEffect(() => { history.replaceState(null, "", `#${onglet}`); }, [onglet]);
  return (
    <div className="app">
      <header className="entete">
        <div>
          <h1>Découper avant de modéliser</h1>
          <p className="sous-titre">
            Quatre sujets sur un assureur fictif. Chaque fois, la même démarche : des cas concrets,
            une règle lisible par cas, la preuve affichée, et le silence quand le signal manque.
          </p>
        </div>
        <p className="bandeau">
          Données <strong>entièrement synthétiques</strong> : aucun client, contrat ni sinistre réel. Les mécanismes
          à retrouver ont été injectés volontairement, avec leur vérité terrain, pour mesurer ce que chaque règle attrape.
        </p>
        <nav className="onglets" role="tablist">
          {ONGLETS.map((o) => (
            <button key={o.id} role="tab" aria-selected={onglet === o.id}
                    className={onglet === o.id ? "actif" : ""} onClick={() => setOnglet(o.id)}>
              {o.num && <span className="num">{o.num}</span>}{o.titre}
            </button>
          ))}
        </nav>
      </header>
      {onglet === "excel" && <Excel />}
      {onglet === "churn" && <Churn />}
      {onglet === "fraude" && <Fraude />}
      {onglet === "reco" && <Reco />}
      {onglet === "methode" && <Methode />}
    </div>
  );
}

function Chargement({ d }) {
  if (!d) return <p className="vide">Chargement…</p>;
  if (d.erreur) return <p className="vide">Données introuvables : lancez <code>ads export</code>.</p>;
  return null;
}

/* ============================================================ SUJET 2 */

const TYPES = {
  agregation: "Agrégation → SQL", consultation: "Consultation d'une ligne → SQL",
  texte: "Texte libre → filtre SQL puis classement", hors_perimetre: "Hors périmètre",
};

function Excel() {
  const d = useJson("excel.json");
  const [i, setI] = useState(0);
  const [fiche, setFiche] = useState(false);
  if (!d || d.erreur) return <Chargement d={d} />;
  const c = d.cas[i];
  const r = c.resultat;
  return (
    <div className="grille-2">
      <aside>
        <h2 className="surtitre">Questions du jeu d'évaluation</h2>
        <ul className="liste">
          {d.cas.map((x, k) => (
            <li key={x.id}>
              <button className={k === i ? "item actif" : "item"} onClick={() => setI(k)}>
                <span className="item-titre">{x.question}</span>
                <span className="item-meta">{TYPES[x.type]}</span>
              </button>
            </li>
          ))}
        </ul>
        <p className="note">Source : <code>{d.source}</code>, chargé dans DuckDB avec des types propres (dates, montants).</p>
        <button className="lien" onClick={() => setFiche(!fiche)}>{fiche ? "Masquer" : "Voir"} la fiche de schéma ({d.fiche.length} colonnes)</button>
        {fiche && <Fiche fiche={d.fiche} />}
      </aside>
      <main>
        <blockquote className="question">{c.question}</blockquote>
        <div className="etapes-route">
          <div className="etape"><span className="etape-n">1</span><div>
            <h3>Valeurs reconnues dans la question</h3>
            {c.valeurs.length ? (
              <ul className="puces">{c.valeurs.map((v, k) => (
                <li key={k}><code>« {v.terme} »</code> → <strong>{v.colonne}</strong> = <code>{v.valeur}</code> <span className="item-meta">{v.methode}</span></li>
              ))}</ul>
            ) : <p className="note">Aucune : rien à rapprocher des valeurs des colonnes.</p>}
          </div></div>
          <div className="etape"><span className="etape-n">2</span><div>
            <h3>Routage : <span className="badge">{TYPES[c.type]}</span></h3>
            {c.type === "hors_perimetre" && <p>{c.explication}</p>}
          </div></div>
          {r && (
            <div className="etape"><span className="etape-n">3</span><div>
              <h3>Requête vérifiée puis exécutée</h3>
              <pre className="sql">{r.sql}</pre>
              <p className="note">Requête de référence du jeu d'évaluation. En production, c'est le modèle qui l'écrit à partir
                de la fiche de schéma ; elle passe par la même garde (lecture seule, colonnes connues, limite), et son résultat
                est comparé à celui-ci.</p>
            </div></div>
          )}
          {r && (
            <div className="etape"><span className="etape-n">4</span><div>
              <h3>Résultat : {nb(r.n_lignes)} ligne{r.n_lignes > 1 ? "s" : ""} · {r.duree_ms} ms</h3>
              {r.alertes.map((a, k) => <p key={k} className="alerte">{a}</p>)}
              <Tableau colonnes={r.colonnes} lignes={r.lignes} />
            </div></div>
          )}
          {!r && (
            <div className="etape"><span className="etape-n">3</span><div>
              <h3>Pas de requête</h3>
              <p className="alerte">La table ne permet pas de répondre. Le système le dit au lieu d'inventer une colonne.</p>
            </div></div>
          )}
        </div>
        <section className="bloc">
          <h3>Ce que la garde refuse</h3>
          <Tableau colonnes={["Requête proposée", "Motif du refus"]} lignes={d.refus.map((x) => [x.sql, x.erreurs.join(" ; ")])} />
        </section>
      </main>
    </div>
  );
}

function Fiche({ fiche }) {
  return (
    <ul className="fiche">
      {fiche.map((c) => (
        <li key={c.nom}>
          <code>{c.nom}</code> <span className="item-meta">{c.type}{c.taux_vide ? ` · vide à ${pct(c.taux_vide)}` : ""}</span>
          <div className="note">{c.description}</div>
          {c.valeurs && <div className="valeurs">{c.valeurs.slice(0, 12).join(" · ")}{c.valeurs.length > 12 ? " …" : ""}</div>}
          {c.min && <div className="valeurs">de {c.min} à {c.max}</div>}
        </li>
      ))}
    </ul>
  );
}

function Tableau({ colonnes, lignes }) {
  if (!lignes?.length) return null;
  return (
    <div className="tableau-wrap">
      <table className="tableau">
        <thead><tr>{colonnes.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{lignes.map((l, k) => <tr key={k}>{l.map((x, j) => <td key={j}>{x == null ? <span className="nul">vide</span> : String(x)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

/* ============================================================ SUJET 5 */

function Churn() {
  const d = useJson("churn.json");
  const [motif, setMotif] = useState(null);
  const [faibles, setFaibles] = useState(false);
  const liste = useMemo(() => (d && !d.erreur ? d.alertes.filter((a) => (faibles || a.fort) && (!motif || a.motif === motif)) : []), [d, motif, faibles]);
  if (!d || d.erreur) return <Chargement d={d} />;
  const m = d.mesures;
  return (
    <div>
      <section className="cartes">
        {m.par_motif.map((x) => (
          <button key={x.motif} className={`carte ${motif === x.motif ? "actif" : ""} ${x.fort ? "" : "faible"}`}
                  onClick={() => setMotif(motif === x.motif ? null : x.motif)}>
            <span className="carte-titre">{x.motif}</span>
            <span className="carte-chiffre">× {x.fois_le_taux_moyen}</span>
            <span className="carte-note">taux de départ des {nb(x.contrats_signales)} contrats signalés : {pct(x.taux_depart_signales)}
              {" "}(moyenne {pct(m.taux_depart_moyen)}){!x.fort && " · signal faible"}</span>
          </button>
        ))}
        <div className="carte silence">
          <span className="carte-titre">Sur qui on se tait</span>
          <span className="carte-chiffre">{nb(m.clients_non_signales)}</span>
          <span className="carte-note">clients sans motif identifiable. {nb(m.departs_sans_motif_visible)} partiront quand même
            (taux {pct(m.taux_depart_non_signales)}) : sans motif, il n'y a rien à leur dire.</span>
        </div>
      </section>
      <div className="barre-filtres">
        <span>{nb(liste.length)} clients affichés{motif ? ` · motif « ${motif} »` : ""} (au {d.aujourdhui})</span>
        <label><input type="checkbox" checked={faibles} onChange={(e) => setFaibles(e.target.checked)} /> montrer aussi les signaux faibles seuls</label>
      </div>
      <ul className="fiches-client">
        {liste.slice(0, 60).map((a) => (
          <li key={a.client_id} className={`fiche-client ${a.fort ? "" : "faible"}`}>
            <header>
              <strong>{a.client_id}</strong>
              <span className="badge">{a.motif}</span>
              <span className="item-meta">{eur(a.prime_totale)} de primes · détient {a.detenus.map((p) => PRODUITS[p]).join(", ")}</span>
            </header>
            <p className="fait">{a.fait}</p>
            <p className="action"><span>À proposer</span>{a.action}</p>
            {a.autres_faits.length > 0 && <p className="item-meta">Aussi : {a.autres_faits.join(" · ")}</p>}
          </li>
        ))}
      </ul>
      <p className="note">Les taux de départ sont mesurés sur la simulation, construite autour de ces motifs. En vrai, la seule
        mesure qui compte est la rétention des clients contactés comparée à un groupe témoin non contacté.</p>
    </div>
  );
}

/* ============================================================ SUJET 6 */

function Fraude() {
  const d = useJson("fraude.json");
  const [i, setI] = useState(0);
  const [verite, setVerite] = useState(false);
  if (!d || d.erreur) return <Chargement d={d} />;
  const m = d.mesures;
  const x = d.dossiers[i];
  return (
    <div>
      <section className="bloc">
        <h3>Scénario : le sinistre arrangé autour de la souscription</h3>
        <p className="note">Contrat souscrit juste avant le sinistre, ou date déplacée pour entrer dans la garantie. Chaque trace est
          une comparaison entre deux pièces ; le taux de confirmation dit ce que vaut chaque signal seul.</p>
        <Tableau colonnes={["Signal", "Force", "Dossiers", "Confirmés", "Taux de confirmation"]}
                 lignes={m.par_signal.map((s) => [s.signal, s.fort ? "fort" : "faible", s.declenche, s.confirmes, pct(s.taux_confirmation)])} />
        <p className="note">{nb(m.dossiers)} dossiers récents, {m.fraudes_injectees} fraudes injectées, {m.dossiers_signales} dossiers signalés.
          Avec deux signaux ou plus, {pct(m.precision_deux_signaux_ou_plus)} sont confirmés. Un sinistre peu après la souscription,
          seul, ne prouve rien : la plupart sont honnêtes.</p>
      </section>
      <div className="grille-2">
        <aside>
          <h2 className="surtitre">File du gestionnaire</h2>
          <ul className="liste">
            {d.dossiers.slice(0, 40).map((y, k) => (
              <li key={y.dossier_id}>
                <button className={k === i ? "item actif" : "item"} onClick={() => setI(k)}>
                  <span className="item-titre">{y.dossier_id} · {y.garantie}</span>
                  <span className="item-meta">{y.n_signaux} signa{y.n_signaux > 1 ? "ux" : "l"} dont {y.n_forts} fort{y.n_forts > 1 ? "s" : ""} · {eur(y.montant_estime)}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <main>
          <h2 className="titre-dossier">Dossier {x.dossier_id}</h2>
          <p className="item-meta">{PRODUITS[x.produit]} · {x.garantie} · survenu le {x.date_survenance} · déclaré le {x.date_declaration} · {x.canal} · {eur(x.montant_estime)}</p>
          <blockquote className="question">{x.description}</blockquote>
          {x.signaux.map((s, k) => {
            const meta = d.signaux[s.signal];
            return (
              <section key={k} className={`signal ${meta.fort ? "fort" : ""}`}>
                <h3>{meta.libelle} {meta.fort && <span className="badge">fort</span>}</h3>
                <div className="comparaison">
                  <div><p>{s.valeur_a}</p><span className="source">{s.source_a}</span></div>
                  <div className="vs">{["dates_incoherentes", "facture_posterieure", "bien_deja_indemnise"].includes(s.signal) ? "≠" : "→"}</div>
                  <div><p>{s.valeur_b}</p><span className="source">{s.source_b}</span></div>
                </div>
                <p className="action"><span>Décision</span>{meta.decision}</p>
              </section>
            );
          })}
          <p className="note">Trois issues possibles : demander une pièce, missionner un expert, ou classer en justifiant.
            Aucun score : le gestionnaire voit ce qu'il doit vérifier.</p>
          <button className="lien" onClick={() => setVerite(!verite)}>{verite ? "Masquer" : "Révéler"} la vérité terrain (simulation)</button>
          {verite && <p className={x.verite.fraude ? "alerte" : "note"}>{x.verite.fraude ? `Fraude injectée : ${x.verite.scenario}` : "Dossier honnête : les signaux sont des coïncidences."}</p>}
        </main>
      </div>
    </div>
  );
}

/* ============================================================ SUJET 7 */

function Reco() {
  const d = useJson("reco.json");
  const [faibles, setFaibles] = useState(false);
  if (!d || d.erreur) return <Chargement d={d} />;
  const c = d.controle;
  const liste = d.propositions.filter((p) => faibles || p.force === "forte");
  return (
    <div>
      <section className="cartes">
        <div className="carte"><span className="carte-titre">Propositions</span><span className="carte-chiffre">{nb(c.propositions)}</span>
          <span className="carte-note">pour {nb(c.clients_concernes)} clients, deux au plus par client, dont {nb(c.fortes)} fondées sur un événement de vie</span></div>
        <div className="carte ok"><span className="carte-titre">Déjà détenu</span><span className="carte-chiffre">{c.deja_detenu}</span>
          <span className="carte-note">vérifié à chaque exécution : jamais proposer ce que le client a déjà</span></div>
        <div className="carte ok"><span className="carte-titre">Non souscriptible</span><span className="carte-chiffre">{c.ineligibles}</span>
          <span className="carte-note">règles d'éligibilité explicites, appliquées avant tout classement</span></div>
      </section>
      <div className="barre-filtres">
        <span>{nb(liste.length)} propositions affichées</span>
        <label><input type="checkbox" checked={faibles} onChange={(e) => setFaibles(e.target.checked)} /> montrer aussi les compléments sans événement (signal faible)</label>
      </div>
      <ul className="fiches-client">
        {liste.slice(0, 60).map((p, k) => (
          <li key={k} className={`fiche-client ${p.force === "forte" ? "" : "faible"}`}>
            <header>
              <strong>{p.client_id}</strong>
              <span className="badge">{PRODUITS[p.produit]}</span>
              <span className="item-meta">{p.age} ans · {p.residence} · {p.commune} · détient {p.detenus.length ? p.detenus.map((x) => PRODUITS[x]).join(", ") : "rien d'autre"}</span>
            </header>
            <p className="fait"><span className="pourquoi">Pourquoi</span>{p.raison}</p>
          </li>
        ))}
      </ul>
      <section className="bloc">
        <h3>Ce qui a été écarté, et pourquoi</h3>
        <Tableau colonnes={["Motif", "Nombre"]} lignes={Object.entries(d.ecartees_par_motif)} />
        <Tableau colonnes={["Client", "Produit", "Événement", "Écarté car"]}
                 lignes={d.ecartees.slice(0, 12).map((e) => [e.client_id, PRODUITS[e.produit], e.raison, e.ecarte_car])} />
      </section>
    </div>
  );
}

/* ============================================================ MÉTHODE */

function Methode() {
  return (
    <article className="methode">
      <h2>La même démarche, quatre fois</h2>
      <p>Un modèle compliqué tout de suite est l'erreur la plus fréquente. Ici, chaque sujet est découpé en cas concrets ;
        chaque cas a sa trace dans les données, sa règle lisible, la preuve affichée et la décision qu'il appelle.
        Un modèle ne viendrait qu'ensuite, à l'intérieur d'un cas, pour prioriser.</p>
      <h3>2 · Un fichier Excel de 100 000 lignes</h3>
      <p>Pas de vecteurs sur les lignes : un tableau sait déjà compter. L'Excel est chargé dans DuckDB avec des types propres ;
        une fiche de schéma (libellé métier, valeurs, taux de vide) est ce que le modèle lit ; les mots de la question sont
        rapprochés des vraies valeurs (« Esch » → Esch-sur-Alzette) ; la question est routée (agrégation, consultation, texte
        libre, hors périmètre) ; la requête passe une garde (lecture seule, colonnes connues, limite) ; le résultat est montré
        avec la requête et le nombre de lignes. La recherche textuelle ne s'applique qu'à la description, après les filtres.
        Un jeu de questions avec leur résultat attendu sert à évaluer chaque changement.</p>
      <h3>5 · Churn</h3>
      <p>Quatre motifs (déménagement, hausse de prime, sinistre mal vécu, échéance sans contact), chacun avec le fait qui le
        déclenche et l'action à proposer. Les clients sans motif ne sont pas signalés.</p>
      <h3>6 · Fraude</h3>
      <p>Un scénario développé : le sinistre arrangé autour de la souscription. Cinq signaux, chacun comparant deux pièces ;
        le gestionnaire voit les deux valeurs et leur source, et une décision possible par signal. Le taux de confirmation de
        chaque signal est suivi : un signal qui ne confirme jamais est retiré.</p>
      <h3>7 · Recommandation</h3>
      <p>D'abord les règles : rien de déjà détenu, rien d'inéligible. Ensuite des événements de vie (nouvelle adresse, véhicule,
        naissance, prêt). Chaque proposition porte sa raison ; le conseiller peut la vérifier et l'écarter.</p>
      <p className="limite">Les données sont synthétiques et les mécanismes y ont été injectés : les chiffres montrent que le
        découpage fonctionne, pas ce qu'il donnerait sur un vrai portefeuille. Sur de vraies données, la mesure serait un groupe
        témoin (churn, recommandation) et le résultat des enquêtes (fraude).</p>
    </article>
  );
}
