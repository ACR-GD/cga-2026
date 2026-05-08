# CGA 2026 Explorer

Site web Flask pour explorer les nominations des Canadian Game Awards 2026, enrichir les fiches publiques (jeux/studios), et sortir des statistiques.

## Fonctionnalites

- Import structure des categories et nomines 2026
- Base SQLite normalisee pour jeux, studios, categories, personnes et nominations
- Enrichissement public automatique:
  - resume Wikipedia (quand disponible)
  - lien de recherche trailer YouTube
  - lien de recherche Metacritic
  - overrides manuels pour forcer logos/illustrations officiels
- Pages web:
  - accueil + KPIs
  - recherche/listes jeux
  - fiches jeu
  - recherche/listes studios
  - fiches studio
  - page stats

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Initialisation des donnees

```bash
python db.py
python load_nominees.py
python enrich_public_data.py
```

## Sync metadata API (V2)

Pour enrichir automatiquement sans saisie manuelle:

1. Duplique `.env.example` en `.env`
2. Renseigne:
   - `YOUTUBE_API_KEY`
   - `IGDB_CLIENT_ID`
   - `IGDB_CLIENT_SECRET`
3. Lance:

```bash
python sync_all_metadata.py
```

Le script met a jour automatiquement:
- trailer YouTube direct (video id)
- illustrations jeux (cover IGDB)
- descriptions (IGDB fallback)
- score/lien Metacritic (quand dispo)
- logos studios (via companies IGDB)

### Obtenir les credentials IGDB

1. Cree une application sur [Twitch Developer Console](https://dev.twitch.tv/console/apps)
2. Recupere `Client ID` et `Client Secret`
3. Renseigne ces valeurs dans `.env` comme `IGDB_CLIENT_ID` et `IGDB_CLIENT_SECRET`
4. Le script genere automatiquement le token OAuth Twitch (client credentials) a chaque sync

### Ajouter illustrations officielles et logos

Edite `data/manual_overrides.json` et renseigne:

- `games.<Titre>.cover_image_url`
- `games.<Titre>.description`
- `studios.<Nom>.logo_image_url`

Puis relance:

```bash
python enrich_public_data.py
```

## Lancer le site

```bash
flask --app app run --debug
```

Le site sera disponible sur `http://127.0.0.1:5000`.

## Mise en ligne

Tu peux deployer tel quel sur:

- [Render](https://render.com/) (Web Service Python)
- [Railway](https://railway.app/)
- [Fly.io](https://fly.io/)

### Conseils prod

- passer a Postgres pour multi-utilisateurs
- ajouter cache d'enrichissement (table `enrichment_jobs`)
- brancher des APIs officielles (YouTube Data API, IGDB, OpenCritic, etc.)
- scheduler quotidien pour rafraichir metadonnees

## Evolutions recommandees

- Ajouter table `awards` pour editions multi-annees
- Ajouter systeme de gagnants (`is_winner`)
- API JSON (`/api/games`, `/api/stats`)
- moteur de recherche full-text (SQLite FTS5 ou Postgres + trigram)
