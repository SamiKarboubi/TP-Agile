# Movie Recommendation

Première version d’une application conversationnelle de recherche et de recommandation de films.
Les critères sont extraits par Claude, puis les résultats factuels proviennent de TMDB et d’OMDb
à travers le serveur MCP [`Grinv/tmdb-mcp`](https://github.com/Grinv/tmdb-mcp).

## Architecture

```text
Navigateur React
      │ POST /api/recommendations
      ▼
FastAPI
  ├── Claude : classification + extraction structurée des contraintes
  ├── moteur déterministe : résolution, filtrage et classement
  └── client MCP stdio ──► tmdb-mcp ──► TMDB + OMDb
```

Claude ne choisit jamais un film à partir de ses seules connaissances. Il produit un
`MovieSearchIntent` Pydantic qui distingue les contraintes obligatoires des préférences. Le backend
traduit ensuite cette intention en appels MCP vérifiables et ne retourne jamais plus de cinq films.

Le MCP est conservé comme sous-processus `stdio` du backend. Il est démarré au premier appel qui en
a besoin puis fermé avec FastAPI. Il n’expose pas de serveur HTTP séparé.

## Prérequis

- Python 3.13 ;
- Node.js 22 (le MCP requiert au minimum Node 20.11) ;
- npm ;
- un token TMDB v4 « API Read Access Token » ;
- une clé Anthropic ;
- une clé OMDb pour les notes IMDb, Rotten Tomatoes et Metacritic ;
- facultatif : Docker Desktop et Docker Compose.

## Variables d’environnement

Copier le fichier d’exemple :

```powershell
Copy-Item backend/.env.example backend/.env
```

Puis renseigner `backend/.env`. Aucun secret ne doit être envoyé au frontend ou ajouté à Git.

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Clé privée de l’API Anthropic. |
| `ANTHROPIC_MODEL` | Modèle Claude utilisé pour l’extraction structurée. |
| `ANTHROPIC_TIMEOUT_SECONDS` | Délai maximal d’un appel Claude. |
| `ANTHROPIC_MAX_RETRIES` | Nombre de nouvelles tentatives gérées par le SDK. |
| `TMDB_API_TOKEN` | Token de lecture v4 TMDB, obligatoire pour les données de films. |
| `OMDB_API_KEY` | Clé OMDb, nécessaire pour filtrer ou afficher les notes IMDb. |
| `TMDB_LANGUAGE` | Langue des titres, synopsis et genres, par défaut `fr-FR`. |
| `TMDB_REGION` | Région des certifications et providers, par défaut `FR`. |
| `TMDB_MCP_COMMAND` | Commande du MCP, `npx` en local et `tmdb-mcp` dans Docker. |
| `TMDB_MCP_ARGS` | Tableau JSON des arguments, par défaut `["-y","tmdb-mcp@0.11.0"]`. |
| `MCP_CALL_TIMEOUT_SECONDS` | Délai maximal d’un appel de tool MCP. |
| `MAX_USER_MESSAGE_LENGTH` | Limite validée par FastAPI et affichée par React, par défaut `200`. |
| `MAX_RECOMMENDATIONS` | Nombre maximal de films, limité à cinq. |
| `MOVIE_CANDIDATE_LIMIT` | Nombre maximal de candidats TMDB examinés, limité à vingt. |
| `DEFAULT_MIN_VOTES` | Nombre minimal de votes TMDB pour une demande « bien notée ». |
| `CORS_ORIGINS` | Origines frontend autorisées, séparées par des virgules. |

## Installation et lancement local

### Backend, Claude et MCP

Depuis la racine du projet :

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements-dev.txt
Set-Location backend
uvicorn app.main:app --reload --port 8000
```

FastAPI lance automatiquement le MCP avec `npx -y tmdb-mcp@0.11.0` au premier appel de
recommandation. Il lui transmet explicitement `TMDB_API_TOKEN`, `OMDB_API_KEY`, `TMDB_LANGUAGE` et
`TMDB_REGION`. Il n’est donc pas nécessaire d’ouvrir un troisième terminal pour le MCP.

Pour vérifier séparément que le paquet MCP peut démarrer, depuis un terminal où
`TMDB_API_TOKEN` est défini :

```powershell
npx -y tmdb-mcp@0.11.0
```

Le processus attend alors des messages MCP JSON-RPC sur son entrée standard ; l’absence d’interface
texte est normale. Utiliser `Ctrl+C` pour l’arrêter.

### Frontend

Dans un second terminal :

```powershell
Set-Location frontend
npm ci
npm run dev
```

Ouvrir <http://localhost:5173>. Vite transmet `/api` à <http://localhost:8000>.

### Docker Compose

Après avoir créé `backend/.env` :

```powershell
docker compose up --build
```

L’application est disponible sur <http://localhost:3000> et l’API sur
<http://localhost:8000>. Le conteneur backend embarque Node 22 et le paquet MCP épinglé.

## Fonctionnement du pipeline

1. FastAPI refuse les messages vides ou supérieurs à la limite configurée.
2. Claude effectue en un seul appel la classification film/hors sujet et l’extraction Pydantic.
3. Une requête hors sujet reçoit la réponse fixe configurée, sans appel TMDB/MCP.
4. Le backend résout genres, personnes, mots-clés, sociétés ou providers en identifiants TMDB.
5. `discover_movies`, `search_movies` ou les tools de similarité produisent des candidats.
6. Pour une contrainte IMDb, `get_movies(include_ratings=true)` enrichit les candidats via OMDb,
   puis le backend applique lui-même le filtre IMDb.
7. `get_movie` et `get_movie_credits` fournissent les détails, l’affiche, le casting et le
   réalisateur. Les contraintes obligatoires vérifiables sont contrôlées une seconde fois.
8. Au plus cinq films conformes sont renvoyés. Aucun résultat approximatif n’est ajouté.

`discover_movies.min_rating` correspond exclusivement à la moyenne TMDB. Le code ne l’utilise
jamais pour satisfaire une contrainte IMDb.

## Exemples

- `Un thriller après 2010 avec une note IMDb supérieure à 7.5.`
- `Un film avec Christian Bale de moins de 2 heures.`
- `Je veux quelque chose dans le style d’Interstellar.`

## Favoris de session

Le bouton cœur ajoute ou retire un film des favoris. Le navigateur conserve uniquement ses
identifiants TMDB dans `sessionStorage` (au plus 20 films par onglet). Après une actualisation,
l'onglet « Favoris » récupère les fiches via `POST /api/movies/lookup` avec un corps
`{"ids":[603,27205]}`. Le backend utilise le MCP TMDB existant pour reconstruire les fiches ;
aucun compte ni stockage serveur n'est nécessaire.

## Tests et qualité

```powershell
.\backend\.venv\Scripts\Activate.ps1
Set-Location backend
pytest

Set-Location ../frontend
npm run lint
npm run build
```

Les tests n’effectuent aucun véritable appel Claude, TMDB, OMDb ou MCP. Les services externes sont
simulés pour tester la validation, le garde-fou, le parsing, la limite de cinq films et le respect
des contraintes obligatoires.

## Limites de cette V1

- pas d’authentification, de profil, d’historique ou de base de données ;
- pas de streaming : la réponse est affichée après validation complète des résultats ;
- première page TMDB seulement, soit au plus vingt candidats ;
- les combinaisons « similaire à… » avec fournisseur, société ou mot-clé obligatoire sont
  recoupées avec cette première page de découverte et peuvent donc manquer un film pourtant valide ;
- les préférences sont conservées dans l’intention mais le classement V1 privilégie principalement
  l’ordre TMDB et les tris explicites ; elles ne deviennent jamais des exclusions silencieuses ;
- une note IMDb absente exclut le film lorsqu’une contrainte IMDb est obligatoire ;
- OMDb reste soumis à son quota et peut ne pas connaître certains titres ;
- `get_similar` peut être bruité ; le pipeline essaie d’abord `get_movie_recommendations`.
