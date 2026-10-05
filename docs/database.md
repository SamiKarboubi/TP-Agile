# PostgreSQL : configuration, lancement et partage

## Ce qui est enregistré

MovieMatch utilise PostgreSQL 17 et `psycopg`, avec du SQL explicite. Il n'y a pas de
SQLAlchemy ni d'Alembic. Le navigateur appelle FastAPI ; seul FastAPI accède à PostgreSQL.

| Table | Colonnes | Rôle |
| --- | --- | --- |
| `users` | `id`, `username`, `password_hash`, `created_at` | Comptes ; username unique, normalisé en minuscules. |
| `sessions` | `token_hash`, `user_id`, `expires_at` | Empreintes SHA-256 des jetons aléatoires et expiration. |
| `favorites` | `user_id`, `movie_id`, `position` | IDs TMDB du compte et ordre d'ajout. |

`position` est un compteur généré par PostgreSQL. Il permet de retrouver les derniers favoris
sans enregistrer les fiches des films. Les fiches sont toujours récupérées via le MCP TMDB.
Les favoris visiteurs restent dans `sessionStorage` ; leur import à l'inscription est
enregistré avec le nouveau compte dans une seule transaction : tout réussit ou tout est annulé.

Le backend utilise `PostgresAccountStore` par défaut. `InMemoryAccountStore` sert uniquement
aux tests unitaires qui l'injectent explicitement ; une panne PostgreSQL ne déclenche jamais
un remplacement silencieux par un stockage temporaire.

Chaque opération ouvre une connexion courte. Le contexte Psycopg valide la transaction si
l'opération réussit, l'annule sinon, et ferme la connexion. Les valeurs passent en paramètres
SQL (`%s`), jamais par concaténation. Les opérations synchrones de base sont exécutées dans
des threads pour laisser FastAPI traiter les autres requêtes.

L'ajout et la suppression de favoris verrouillent la ligne de leur utilisateur pendant la
transaction. Deux onglets ou deux instances backend ne peuvent donc pas dépasser ensemble
la limite de 20 favoris. La clé primaire empêche les doublons, les clés étrangères relient
les données au compte et les suppriment si ce compte est supprimé en base.

## Un seul fichier de configuration : backend/.env

Depuis la racine, si ce fichier n'existe pas encore :

```powershell
Copy-Item backend/.env.example backend/.env
```

S'il existe déjà, conservez vos clés et ajoutez les variables manquantes, sans le remplacer.

Extrait à renseigner :

```dotenv
ANTHROPIC_API_KEY=VOTRE_CLE
TMDB_API_TOKEN=VOTRE_TOKEN
OMDB_API_KEY=VOTRE_CLE

DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=moviematch
DB_USER=moviematch_app
DB_PASSWORD='REMPLACER_PAR_UN_LONG_SECRET_ALEATOIRE'
DB_CONNECT_TIMEOUT_SECONDS=5

AUTH_COOKIE_SECURE=false
AUTH_SESSION_HOURS=24
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

GHCR_REPOSITORY=samikarboubi/tp-agile
IMAGE_TAG=latest
```

| Variable | Où elle sert |
| --- | --- |
| `DB_HOST` | Adresse PostgreSQL vue par le backend. `127.0.0.1` sur votre PC ; Compose impose `db` dans Docker. |
| `DB_PORT` | Port PostgreSQL. `5432` localement et entre conteneurs. |
| `DB_NAME` | Base à créer et à utiliser. |
| `DB_USER` | Compte technique de connexion à PostgreSQL, commun au backend. |
| `DB_PASSWORD` | Mot de passe de ce compte technique. Obligatoire, sans valeur par défaut. |
| `DB_CONNECT_TIMEOUT_SECONDS` | Délai maximal d'établissement d'une connexion, par défaut 5 secondes. |
| `AUTH_COOKIE_SECURE` | `false` en HTTP local ; `true` quand le site est servi en HTTPS. |
| `AUTH_SESSION_HOURS` | Durée maximale des sessions côté serveur et du cookie. |
| `CORS_ORIGINS` | Origines exactes du site autorisées pour les requêtes navigateur. |
| `GHCR_REPOSITORY` | Chemin du dépôt GHCR, en minuscules, sans `ghcr.io/`. |
| `IMAGE_TAG` | Tag commun au frontend et au backend, de préférence le SHA court publié par la CI. |

Les autres paramètres existants sont expliqués dans le README. Les clés API restent côté
backend ; OMDb est nécessaire pour les fonctionnalités de notes IMDb. Sans clés Claude/TMDB,
les comptes fonctionnent mais les recherches de films ne peuvent pas fonctionner normalement.

Pour générer un secret aléatoire, avec Python installé :

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copiez le résultat dans `DB_PASSWORD`. Pour un secret contenant `$`, utilisez des apostrophes
dans le fichier `.env` afin d'éviter l'interpolation par Compose. Le format d'exemple est
destiné à Pydantic et Docker Compose ; leurs règles de lecture ne sont pas celles de toutes
les commandes `docker run --env-file`.

### Comment ces valeurs sont chargées

En local, `Settings` lit `.env` puis `backend/.env` selon le dossier de lancement ; les
variables de l'environnement du processus ont priorité. Nous utilisons `backend/.env` comme
fichier de référence. Le backend garde la configuration en mémoire et doit être redémarré
après un changement. `DB_PASSWORD` est un `SecretStr` pour masquer sa représentation dans
les affichages de configuration ; la vraie valeur est uniquement extraite pour la connexion.

Avec Docker Compose, il y a deux lectures :

1. `--env-file backend/.env` fournit les valeurs de `${DB_PASSWORD}`, `${DB_USER}`, etc. dans
   le YAML à Compose.
2. `env_file: ./backend/.env` fournit les variables au processus du conteneur backend.

Le YAML transmet explicitement les mêmes identifiants aux deux services et remplace
`DB_HOST` par `db`, `DB_PORT` par `5432`. Il impose aussi le MCP déjà installé dans l'image
(`tmdb-mcp`, arguments `[]`) : le backend Docker n'a pas besoin de `npx` au démarrage.
Une variable déjà définie dans le terminal peut prendre priorité sur l'interpolation Compose.

`127.0.0.1` désigne votre PC en IPv4. Cette valeur évite les délais observés sous Windows
lorsque `localhost` essaie d'abord une adresse IPv6 sur laquelle PostgreSQL n'est pas publié.

Le service PostgreSQL reçoit `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, dérivés des
variables `DB_*`. L'image officielle crée la base et le compte technique au premier démarrage
d'un volume vide. Le backend crée ensuite les tables grâce à `app/db/schema.sql`, inclus
dans son image. L'initialisation est répétable et ne supprime pas les données existantes.

`CREATE TABLE IF NOT EXISTS` crée des tables manquantes ; il ne transforme pas une table
existante. Une évolution future des colonnes demandera un script SQL de migration explicite.

### BACKEND_URL

Le frontend appelle `/api`. En développement, Vite transmet ces requêtes à
`http://localhost:8000`. Dans Docker, Nginx les transmet à `http://backend:8000`.
Il n'y a donc aucune variable `BACKEND_URL` ou `VITE_BACKEND_URL` à configurer actuellement.
Ces adresses concernent HTTP ; les variables `DB_*` concernent la connexion PostgreSQL.

### Secrets et identifiants

`DB_USER` est un compte PostgreSQL technique. Les usernames MovieMatch sont des lignes de
`users` : on ne crée pas de compte PostgreSQL par inscrit. Les mots de passe MovieMatch sont
hachés avec Argon2id ; le mot de passe technique PostgreSQL est fourni par la configuration.

Le vrai `.env` est ignoré par Git et exclu de l'image backend par `.dockerignore`. Seul
`.env.example` est versionné. Les secrets sont injectés au lancement, jamais pendant le build,
et ne vont jamais dans des variables frontend `VITE_*` ou dans le stockage du navigateur.
Évitez de partager la sortie de `docker compose config`, qui peut contenir les valeurs résolues.

Cette configuration est destinée au développement et aux tests locaux. `POSTGRES_USER`
crée un compte administrateur : pour un hébergement public, prévoyez un compte applicatif
aux droits limités, HTTPS, des sauvegardes et une injection des secrets par l'hébergeur.
Adminer et PostgreSQL sont publiés uniquement sur l'adresse locale `127.0.0.1`.

## Lancement local : tout dans Docker

Prérequis : Docker Desktop démarré et un `backend/.env` renseigné.
Depuis la racine du projet :

```powershell
docker compose --env-file backend/.env up --build -d
docker compose --env-file backend/.env ps
```

- Site : <http://localhost:3000>
- API / documentation : <http://localhost:8000/docs>
- Vérification backend + base : <http://localhost:8000/health>

Compose crée le réseau, PostgreSQL et son volume, attend que PostgreSQL soit prêt, démarre
le backend qui crée les tables, puis démarre le frontend quand le backend est sain.
Il n'est pas nécessaire de nommer les conteneurs manuellement.

Pour consulter les logs :

```powershell
docker compose --env-file backend/.env logs --tail 100 backend db
```

Pour arrêter :

```powershell
docker compose --env-file backend/.env down
```

Cette commande conserve le volume PostgreSQL. Un redémarrage conserve les comptes, les favoris
et les sessions encore valides. Gardez le même dossier/nom de projet Compose pour réutiliser
le même volume. `down -v` supprime le volume et toutes les données : ne l'utilisez que pour une
réinitialisation volontaire d'une base de test. Un volume persistant ne remplace pas une sauvegarde.

## Lancement local : Python et React sur le PC

Prérequis supplémentaires : Python 3.13, Node.js 22 et npm.

1. Dans `backend/.env`, gardez `DB_HOST=127.0.0.1`, `DB_PORT=5432`, les identifiants et les clés API.
2. Démarrez seulement PostgreSQL :

   ```powershell
   docker compose --env-file backend/.env up -d db
   ```

3. Premier terminal, depuis la racine :

   ```powershell
   python -m venv backend/.venv
   .\backend\.venv\Scripts\Activate.ps1
   python -m pip install -r backend/requirements-dev.txt
   Set-Location backend
   python -m uvicorn app.main:app --reload --port 8000
   ```

4. Deuxième terminal, depuis la racine :

   ```powershell
   Set-Location frontend
   npm ci
   npm run dev
   ```

Ouvrez <http://localhost:5173>. Le backend démarre automatiquement le MCP au premier appel
nécessaire. `--reload` ne fait plus disparaître les comptes et favoris.
Évitez de lancer simultanément le backend Docker et le backend local sur le port 8000.

## Voir les données facilement avec Adminer

Depuis la racine :

```powershell
docker compose --env-file backend/.env --profile tools up -d adminer
```

Ouvrez <http://localhost:8080> et renseignez :

| Champ Adminer | Valeur |
| --- | --- |
| Système | PostgreSQL |
| Serveur | `db` |
| Utilisateur | Valeur de `DB_USER`, par défaut `moviematch_app` |
| Mot de passe | Valeur de `DB_PASSWORD` |
| Base de données | Valeur de `DB_NAME`, par défaut `moviematch` |

Adminer est dans Docker : son serveur est donc `db`, même si le backend tourne sur votre PC.
Cliquez sur une table puis « Sélectionner ». `users.password_hash` montre un hash Argon2id ;
`sessions.token_hash` montre une empreinte SHA-256. Les mots de passe et les jetons originaux
ne sont pas enregistrés. Adminer peut modifier les données : utilisez-le sur votre base de test.

Requête pratique dans « Commande SQL » pour voir les favoris avec leur propriétaire :

```sql
SELECT u.username, f.movie_id, f.position
FROM favorites f
JOIN users u ON u.id = f.user_id
ORDER BY u.username, f.position;
```

Autre possibilité : DBeaver avec hôte `localhost`, port `5432` et les mêmes identifiants.

## Un collègue utilise les images GHCR, sans compiler

Il lui faut Docker Desktop et les fichiers suivants ; le code source n'est pas nécessaire :

```text
MovieMatch/
├── docker-compose.ghcr.yml
└── backend/
    └── .env
```

Fournissez `docker-compose.ghcr.yml`, `backend/.env.example` et cette documentation. Il copie
l'exemple en `backend/.env`, choisit son propre `DB_PASSWORD`, renseigne les clés API et choisit
un tag qui contient cette nouvelle version du backend. Les anciennes images ne contiennent
pas le stockage PostgreSQL. Frontend et backend doivent utiliser le même tag publié.

```dotenv
GHCR_REPOSITORY=samikarboubi/tp-agile
IMAGE_TAG=LE_SHA_COURT_PUBLIE_PAR_LA_CI
```

Si les packages GHCR sont publics, aucun login n'est nécessaire pour les télécharger.
S'ils sont privés, le collègue doit avoir les droits de lecture et se connecter à GHCR :

```powershell
docker login ghcr.io -u SON_USERNAME_GITHUB
```

À l'invite du mot de passe, utiliser un personal access token GitHub **classic** autorisé à lire les packages
(`read:packages`), pas le mot de passe du compte GitHub. Un `docker login` sans `ghcr.io`
se connecte à Docker Hub et ne donne pas accès aux packages privés GHCR.

Depuis son dossier MovieMatch :

```powershell
docker compose --env-file backend/.env -f docker-compose.ghcr.yml pull
docker compose --env-file backend/.env -f docker-compose.ghcr.yml up -d
```

Le site est sur <http://localhost:3000>. PostgreSQL vient de Docker Hub ; les deux images de
l'application viennent de GHCR. Le backend crée les tables dans sa propre base locale.
Le collègue n'a besoin ni de Python/Node, ni de lancer un script SQL séparé.

Pour ouvrir Adminer :

```powershell
docker compose --env-file backend/.env -f docker-compose.ghcr.yml --profile tools up -d adminer
```

Pour arrêter ou consulter les logs, utilisez les mêmes options `--env-file` et `-f` :

```powershell
docker compose --env-file backend/.env -f docker-compose.ghcr.yml logs --tail 100 backend db
docker compose --env-file backend/.env -f docker-compose.ghcr.yml down
```

Chaque collègue possède sa propre base et son volume. Les images transportent le code et le
schéma, pas vos comptes ni vos favoris. Pour partager les mêmes données, il faut soit un export
de test, soit une instance commune du projet hébergée ; télécharger les mêmes images ne partage
pas automatiquement une base.

## Changer le mot de passe PostgreSQL et sauvegarder

Changer `DB_PASSWORD` dans `.env` ne modifie pas un compte PostgreSQL déjà créé.
Pour une rotation, ouvrez `psql` avec le username actuel (adaptez-le si nécessaire) :

```powershell
docker compose --env-file backend/.env exec db psql -U moviematch_app -d moviematch
```

Dans `psql` :

```text
\password moviematch_app
\q
```

La commande demande le nouveau mot de passe sans l'écrire dans la commande SQL. Mettez ensuite
la même valeur dans `backend/.env` et recréez les services pour actualiser leur environnement :

```powershell
docker compose --env-file backend/.env up -d --force-recreate db backend
```

Avec les images GHCR, ajoutez `-f docker-compose.ghcr.yml` aux commandes Compose.

Pour un export de test simple, utilisez Adminer → « Exporter » → SQL, avec structure et données.
Conservez le fichier dans `.db-backups/` (ignoré par Git). Il contient les données de comptes :
partagez seulement des comptes fictifs et des favoris de test. Un export ne contient pas la
configuration `.env` et ne remplace pas une stratégie de sauvegarde automatisée pour une base publique.

## Tests et dépannage

Les tests unitaires gardent un stockage mémoire isolé et des services de films simulés.
La CI démarre aussi PostgreSQL et exécute les tests d'intégration. Ceux-ci créent un schéma
aléatoire par test et ne suppriment que ce schéma, pas les tables de votre application.

Pour les exécuter localement sur une base de test dédiée, définissez `TEST_DB_HOST`,
`TEST_DB_PORT`, `TEST_DB_NAME`, `TEST_DB_USER`, `TEST_DB_PASSWORD`, puis lancez :

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -q
```

Sans `TEST_DB_PASSWORD`, seuls les tests nécessitant une vraie base sont ignorés. La CI fournit
toujours cette variable et teste la persistance après recréation de l'application, l'import
transactionnel, l'unicité concurrente, la limite de favoris concurrente et les sessions.

| Problème | À vérifier |
| --- | --- |
| `DB_PASSWORD` manquant | Renseigner le fichier et utiliser `--env-file backend/.env`. |
| Port déjà utilisé | Arrêter le précédent service occupant 5432, 8000, 3000 ou 8080. Ne pas lancer les deux versions du projet simultanément. |
| Authentification PostgreSQL refusée | Identifiants identiques côté backend et base ; un ancien volume garde son ancien mot de passe. |
| Backend Docker contacte `localhost` | Utiliser nos fichiers Compose, qui imposent `DB_HOST=db`. |
| Réponse 503 | PostgreSQL est inaccessible ; consulter les logs et la santé du service `db`. |
| Cookies absents en HTTP local | `AUTH_COOKIE_SECURE=false`. |
| Refus d'origine avec un autre domaine/port | Ajouter l'origine exacte dans `CORS_ORIGINS`, puis redémarrer le backend. |
| Anciennes données semblent disparues | Vérifier le nom de projet Compose et le volume utilisé ; un nouveau dossier peut créer un autre volume. |
| Tables absentes avec GHCR | Vérifier que le tag backend inclut cette implémentation PostgreSQL. |

Les comptes de l'ancienne version étaient uniquement en mémoire : ils ne sont pas automatiquement
migrés après arrêt de cet ancien backend. Les favoris visiteurs encore dans l'onglet peuvent
toujours être importés à la création d'un nouveau compte.

## Références

- [Image officielle PostgreSQL](https://hub.docker.com/_/postgres)
- [Variables et interpolation Compose](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
- [Réseau Compose](https://docs.docker.com/compose/how-tos/networking/)
- [Transactions Psycopg](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
- [Paramètres SQL Psycopg](https://www.psycopg.org/psycopg3/docs/basic/params.html)
- [Authentification et téléchargement GHCR](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
