# MovieMatch

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
  ├── comptes, sessions, favoris ──► PostgreSQL
  └── client MCP stdio ──► tmdb-mcp ──► TMDB + OMDb
```

Claude ne choisit jamais un film à partir de ses seules connaissances. Il produit un
`MovieSearchIntent` Pydantic qui distingue les contraintes obligatoires des préférences. Le backend
traduit ensuite cette intention en appels MCP vérifiables et ne retourne jamais plus de sept films.

Le MCP est conservé comme sous-processus `stdio` du backend. Il est démarré au premier appel qui en
a besoin puis fermé avec FastAPI. Il n’expose pas de serveur HTTP séparé.

## Prérequis

- Python 3.13 ;
- Node.js 22 (le MCP requiert au minimum Node 20.11) ;
- npm ;
- un token TMDB v4 « API Read Access Token » ;
- une clé Anthropic ;
- une clé OMDb pour les notes IMDb, Rotten Tomatoes et Metacritic ;
- PostgreSQL 17, lancé simplement avec Docker Desktop et Docker Compose.

## Variables d’environnement

Copier le fichier d’exemple :

```powershell
Copy-Item backend/.env.example backend/.env
```

Puis renseigner `backend/.env`. Aucun secret ne doit être envoyé au frontend ou ajouté à Git.
Si ce fichier existe déjà, ajouter les variables manquantes sans remplacer les clés existantes.
Renseigner notamment `DB_PASSWORD`, obligatoire. Voir le
[guide PostgreSQL, environnement, Adminer et partage GHCR](docs/database.md).

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
| `MAX_RECOMMENDATIONS` | Nombre maximal de films, fixé à sept par défaut et limité à sept. |
| `MOVIE_CANDIDATE_LIMIT` | Nombre maximal de candidats TMDB examinés, limité à vingt. |
| `DEFAULT_MIN_VOTES` | Nombre minimal de votes TMDB pour une demande « bien notée ». |
| `CORS_ORIGINS` | Origines frontend autorisées, séparées par des virgules. |
| `AUTH_COOKIE_SECURE` | `false` pour les tests HTTP locaux ; `true` pour un déploiement HTTPS. |
| `AUTH_SESSION_HOURS` | Durée d'une session de connexion, par défaut `24`. |
| `DB_HOST` | `127.0.0.1` pour un backend sur le PC ; Compose impose `db` dans Docker. |
| `DB_PORT` | Port PostgreSQL, par défaut `5432`. |
| `DB_NAME` | Nom de la base, par défaut `moviematch`. |
| `DB_USER` | Compte PostgreSQL technique, par défaut `moviematch_app`. |
| `DB_PASSWORD` | Mot de passe PostgreSQL obligatoire, à choisir et garder secret. |
| `DB_CONNECT_TIMEOUT_SECONDS` | Délai de connexion PostgreSQL, par défaut `5`. |
| `GHCR_REPOSITORY` | Dépôt des images, par défaut `samikarboubi/tp-agile`. |
| `IMAGE_TAG` | Tag commun des images GHCR, idéalement le SHA court d'un push validé. |

## Installation et lancement local

### Backend, Claude et MCP

Depuis la racine du projet :

```powershell
docker compose --env-file backend/.env up -d db
python -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend/requirements-dev.txt
Set-Location backend
python -m uvicorn app.main:app --reload --port 8000
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
docker compose --env-file backend/.env up --build -d
```

L’application est disponible sur <http://localhost:3000> et l’API sur
<http://localhost:8000>. Le conteneur backend embarque Node 22 et le paquet MCP épinglé.
PostgreSQL et ses tables démarrent automatiquement ; les données restent dans un volume nommé.

Pour consulter les données dans le navigateur :

```powershell
docker compose --env-file backend/.env --profile tools up -d adminer
```

Ouvrir <http://localhost:8080>, choisir PostgreSQL, serveur `db`, et utiliser `DB_USER`,
`DB_PASSWORD`, `DB_NAME`. Les images GHCR se lancent sans compiler avec le fichier autonome :

```powershell
docker compose --env-file backend/.env -f docker-compose.ghcr.yml pull
docker compose --env-file backend/.env -f docker-compose.ghcr.yml up -d
```

Voir [le guide complet](docs/database.md) pour les identifiants, le partage à un collègue,
la persistance, les sauvegardes et le dépannage. Les anciens tags backend en mémoire ne
contiennent pas cette fonctionnalité : publier une nouvelle version avant de les utiliser.

## Fonctionnement du pipeline

1. FastAPI refuse les messages vides ou supérieurs à la limite configurée.
2. Le backend récupère les genres disponibles avec `get_movie_genres` via le MCP, puis conserve
   cette liste en mémoire jusqu'au redémarrage. Claude reçoit les noms exacts dans son prompt
   et dans les valeurs autorisées de son schéma Pydantic. Il extrait zéro, un ou plusieurs genres,
   y compris les genres exclus ; un genre inventé est refusé. La classification film/hors sujet
   et l'extraction des autres contraintes restent réalisées dans le même appel Claude.
3. Une requête hors sujet reçoit la réponse fixe configurée, sans recherche de films.
4. Le backend résout genres, personnes, mots-clés, sociétés ou providers en identifiants TMDB.
5. `discover_movies`, `search_movies` ou les tools de similarité produisent des candidats.
6. Pour une contrainte IMDb, `get_movies(include_ratings=true)` enrichit les candidats via OMDb,
   puis le backend applique lui-même le filtre IMDb.
7. `get_movie` et `get_movie_credits` fournissent les détails, l’affiche, le casting et le
   réalisateur. Les contraintes obligatoires vérifiables sont contrôlées une seconde fois.
8. Si des favoris sont présents, `get_similar` donne la priorité aux candidats proches des dix
   favoris les plus récents. Il n'ajoute aucun candidat et ne remplace aucun filtre obligatoire.
9. Au plus sept films conformes sont renvoyés. Aucun résultat approximatif n’est ajouté.

`discover_movies.min_rating` correspond exclusivement à la moyenne TMDB. Le code ne l’utilise
jamais pour satisfaire une contrainte IMDb.

## Exemples

- `Un thriller après 2010 avec une note IMDb supérieure à 7.5.`
- `Un film avec Christian Bale de moins de 2 heures.`
- `Je veux quelque chose dans le style d’Interstellar.`

## Comptes et favoris

Le bouton cœur ajoute ou retire un film des favoris. Pour un visiteur, le navigateur conserve
uniquement les identifiants TMDB dans `sessionStorage` (au plus 20 films par onglet). Après une actualisation,
l'onglet « Favoris » récupère les fiches via `POST /api/movies/lookup` avec un corps
`{"ids":[603,27205]}`. Le backend utilise le MCP TMDB existant pour reconstruire les fiches ;
les fiches sont reconstruites via le MCP.

« Mon compte » permet de s'inscrire avec un username unique et un mot de passe, de se connecter
et de se déconnecter. L'inscription et la connexion importent automatiquement les favoris visiteurs et ouvrent une
session. Les comptes, sessions et favoris connectés sont conservés **dans PostgreSQL** :
un redémarrage du backend les conserve. Les favoris visiteurs restent dans leur onglet.
La fusion évite les doublons. Si le compte atteint 20 favoris, les IDs non transférés restent
dans la session visiteur ; un message l'indique. Une authentification refusée ne transfère rien.
À l'inscription, chaque condition du mot de passe est affichée et vérifiée pendant la saisie.

Pour un utilisateur connecté, les favoris proviennent du backend. Pour un visiteur, chaque
recherche envoie les identifiants de l'onglet à `POST /api/recommendations`.
Le backend utilise uniquement les dix derniers pour limiter les appels MCP. La similarité
réordonne les candidats déjà trouvés ; elle ne suffit jamais à faire apparaître un film qui ne
correspond pas à la recherche.

Voir [l'explication complète de l'architecture et de la sécurité](docs/authentication.md).

## Sélection de bienvenue

À la première ouverture de la session de l'onglet, une interface présente cinq films au hasard.
Le visiteur peut les ajouter ou les retirer de ses favoris et accéder au site à tout moment
avec « Passer cette étape » ou « Continuer vers MovieMatch », même si le catalogue est indisponible.
Les utilisateurs déjà connectés enregistrent directement leurs choix dans leur compte.

`GET /api/movies/random` utilise uniquement `discover_movies` du MCP : une page tirée au hasard
parmi les cinq premières pages de films populaires, puis cinq films distincts tirés au hasard
dans cette page. `include_adult=false` exclut les films adultes ; le seuil de votes configuré
est conservé. Il s'agit donc d'un tirage parmi ces résultats populaires, pas parmi tout TMDB.
Les cartes d'accueil utilisent les résumés (titre, année, affiche), sans les appels coûteux
de casting, plateformes et bandes-annonces. L'onglet Favoris retrouve ensuite les fiches complètes.

`moviematch:welcome-dismissed` dans `sessionStorage` mémorise la fermeture de cet écran pour
éviter de le réafficher à chaque actualisation ou changement de compte pendant la même session.

## Tests et qualité

```powershell
.\backend\.venv\Scripts\Activate.ps1
Set-Location backend
python -m pytest

Set-Location ../frontend
npm test
npm run lint
npm run build
```

Les tests n’effectuent aucun véritable appel Claude, TMDB, OMDb ou MCP. Les services externes sont
simulés pour tester la validation, le garde-fou, le parsing, la limite de sept films et le respect
des contraintes obligatoires, ainsi que les comptes, les sessions et l'isolation des favoris.
Les tests PostgreSQL utilisent une base dédiée configurée par les variables `TEST_DB_*`.
Ils sont exécutés en CI ; localement ils sont ignorés si `TEST_DB_PASSWORD` est absent.
Les nouveaux tests vérifient aussi les messages de validation précis, la fusion des favoris
à la connexion, les fusions concurrentes en PostgreSQL, les genres autorisés transmis à Claude
et les cinq films distincts de la sélection de bienvenue. Le frontend teste ses critères de
mot de passe et l'envoi des favoris visiteurs à l'inscription comme à la connexion.

## Limites de cette V1

- configuration Docker prévue pour les tests locaux ; un hébergement public demande HTTPS,
  un compte PostgreSQL aux droits limités et une stratégie de sauvegarde ;
- pas de récupération de mot de passe ni de validation externe d'identité dans cette version ;
- pas de streaming : la réponse est affichée après validation complète des résultats ;
- première page TMDB seulement, soit au plus vingt candidats ;
- les combinaisons « similaire à… » avec fournisseur, société ou mot-clé obligatoire sont
  recoupées avec cette première page de découverte et peuvent donc manquer un film pourtant valide ;
- les préférences sont conservées dans l’intention mais le classement V1 privilégie principalement
  l’ordre TMDB et les tris explicites ; elles ne deviennent jamais des exclusions silencieuses ;
- une note IMDb absente exclut le film lorsqu’une contrainte IMDb est obligatoire ;
- OMDb reste soumis à son quota et peut ne pas connaître certains titres ;
- `get_similar` peut être bruité ; le pipeline essaie d’abord `get_movie_recommendations`.
