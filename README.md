# Découper avant de modéliser

Quatre sujets sur un assureur fictif : interroger un Excel de 100 000 lignes (sujet 2), le churn (5),
la fraude (6) et la recommandation (7). Chaque fois la même démarche : des **cas concrets**, une
**règle lisible** par cas, **la preuve affichée**, et **le silence** quand le signal manque. Un modèle
ne viendrait qu'ensuite, à l'intérieur d'un cas, pour prioriser.

Toutes les données sont **synthétiques** (`data.py`) : aucun client, contrat ni sinistre réel. Les
mécanismes à retrouver y sont injectés avec leur vérité terrain, pour mesurer ce que chaque règle
attrape et ce qu'elle rate.

## Sujet 2 — un fichier Excel de 100 000 lignes

Pas de vecteurs sur les lignes : un tableau sait déjà compter, sommer et filtrer.

```
Excel ─► DuckDB typé ─► fiche de schéma ─► résolution des valeurs ─► routage ─► garde SQL ─► résultat + requête
```

- **Fiche de schéma** : libellé métier, type, taux de vide, valeurs des colonnes catégorielles. C'est ce que lit le modèle, jamais les données.
- **Résolution des valeurs** : « vols à Esch payés » → `garantie = 'Vol'`, `commune = 'Esch-sur-Alzette'`, `statut = 'réglé'` (exact, synonymes, approché, pluriels).
- **Routage** (LLM) : agrégation, consultation d'une ligne, texte libre, hors périmètre.
- **Garde** : une seule instruction SELECT, table et colonnes connues, aucun accès fichier, limite de lignes, connexion en lecture seule.
- **Texte libre** : filtre SQL d'abord, classement TF-IDF ensuite, sur la seule colonne `description`.
- **Réponse** : la requête, le nombre de lignes, le résultat ; une réponse vide est dite vide.
- **Évaluation** : 8 questions avec leur requête de référence ; une requête du modèle est juste si son résultat est égal.

## Sujet 5 — churn

Quatre motifs, chacun avec le fait qui le déclenche et l'action à proposer : déménagement, hausse de
prime à l'échéance, sinistre mal vécu (refus, réclamation, règlement long et relancé), échéance sans
contact (signal faible, masqué par défaut). **Les clients sans motif ne sont pas signalés.**

## Sujet 6 — fraude

Un scénario : le sinistre arrangé autour de la souscription. Cinq signaux, chacun comparant deux pièces
avec leur source (date d'effet / date du sinistre, déclaration / expertise, facture / sinistre, plainte,
bien ou IBAN déjà vu). Le gestionnaire voit les deux valeurs et une décision par signal, pas un score.
Le taux de confirmation de chaque signal est mesuré : seul, « peu après la souscription » ne prouve rien.

## Sujet 7 — recommandation

D'abord les règles : rien de déjà détenu, rien d'inéligible (vérifié à chaque exécution, `controler`).
Ensuite des événements de vie : nouvelle adresse, véhicule, naissance, prêt. Chaque proposition porte sa
raison, et les propositions écartées disent pourquoi.

## Utilisation

```bash
pip install -e ".[dev]"
pytest -q                 # 10 tests
ads generer               # data/sinistres_100k.xlsx (≈ 10 Mo), puis chargement DuckDB depuis l'Excel
ads sql "SELECT canton, count(*) FROM sinistres GROUP BY 1"
LLM_API_KEY=... ads excel "Combien de sinistres auto refusés en 2025 ?"
ads export                # web/public/*.json
cd web && npm install && npm run build && cp -r dist/* ../docs/
```

Le site est **déjà construit dans `docs/`** : GitHub Pages → *Deploy from a branch* → `main` / `docs`.

## Limites

Les mécanismes sont injectés : les chiffres montrent que le découpage fonctionne, pas ce qu'il donnerait
sur un vrai portefeuille. Sur de vraies données, la mesure serait un groupe témoin (churn,
recommandation) et le résultat des enquêtes (fraude).
