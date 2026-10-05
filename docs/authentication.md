# Comptes et favoris MovieMatch : version en mémoire

Cette version permet de tester l'inscription, la connexion, la déconnexion et des favoris
associés à un compte. Tous les comptes, les sessions et les favoris connectés disparaissent
au redémarrage du backend. Il faut garder une seule instance et un seul processus/worker.
Les favoris visiteurs restent dans le `sessionStorage` de leur onglet.

## Organisation du backend

`schemas/accounts.py` définit les données reçues et renvoyées par les routes. Pydantic vérifie
les longueurs, les usernames et les IDs avant l'exécution de la logique. Les champs inconnus
sont refusés : le client ne peut pas fournir lui-même un `user_id` à l'inscription.

`services/account_store.py` contient les données temporaires et les opérations de stockage.
Il conserve quatre dictionnaires : utilisateurs par ID, correspondance username/ID,
sessions par empreinte de jeton, favoris par ID utilisateur. Il renvoie des copies des listes
de favoris pour éviter de modifier accidentellement les données internes.

L'objet utilisateur a exactement les champs suivants :

| Champ | Utilisation |
| --- | --- |
| `id` | UUID généré par le backend pour identifier le compte. |
| `username` | Nom de connexion normalisé en minuscules, unique. |
| `password_hash` | Mot de passe haché avec Argon2id. |
| `created_at` | Date de création en UTC. |

`services/auth_service.py` hache et vérifie les mots de passe, crée les jetons, retrouve les
sessions et applique la limite de tentatives. Il appelle le composant de stockage.

`api/accounts.py` expose les routes, définit le cookie et vérifie les droits et l'origine des
requêtes. La réponse publique contient `id`, `username`, `created_at`, mais jamais le hash du
mot de passe ou le jeton.

`main.py` crée un stockage et un service d'authentification pour chaque instance de l'application.
Le stockage n'est pas un dictionnaire global partagé entre les applications de test.

Cette séparation permettra plus tard de remplacer les opérations du stockage par des accès
à une base. Aucune dépendance SQLAlchemy, aucun schéma SQL et aucune migration Alembic n'ont
été ajoutés.

## Username et mot de passe

Un username comporte 3 à 32 caractères : lettres ASCII, chiffres, `_`, `-` ou `.`.
Les espaces aux extrémités sont supprimés et le nom est converti en minuscules :
`Alice`, `ALICE` et ` alice ` désignent le même username. L'unicité est vérifiée lors de
l'insertion, sous un verrou, même si deux inscriptions arrivent simultanément.

Le mot de passe d'inscription comporte 12 à 128 caractères. Il est conservé tel que saisi
pour le hachage, y compris les espaces. La bibliothèque `argon2-cffi` crée un hash Argon2id
avec ses paramètres par défaut et un sel aléatoire. Deux utilisateurs ayant le même mot de
passe ont donc des hashes différents.

La vérification utilise `PasswordHasher.verify`, sans déchiffrer le hash et sans écrire
de fonction de cryptographie maison. Le hachage et la vérification passent par
`asyncio.to_thread` pour ne pas bloquer la boucle asynchrone de FastAPI.

Pour un compte inexistant, une vérification est aussi effectuée sur un hash fictif.
Le message de connexion reste « Nom d'utilisateur ou mot de passe incorrect », que le
username existe ou non. L'inscription renvoie un conflit explicite pour un username déjà
utilisé, afin de permettre à l'utilisateur d'en choisir un autre.

## Inscription et import des favoris

1. Le visiteur ajoute des films : seuls leurs IDs sont enregistrés dans `sessionStorage`.
2. Le formulaire envoie username, mot de passe et `favorite_ids` à `/api/auth/signup`.
3. Le backend valide les données et hache le mot de passe.
4. Le stockage crée le compte et sa liste de favoris dans la même section protégée par le
   verrou. Les IDs sont dédupliqués en conservant leur ordre ; la liste est limitée à 20.
5. Le backend crée une session et renvoie le cookie ainsi que le compte public et ses IDs.
6. Seulement après cette réussite, React efface la liste visiteur de `sessionStorage` et
   utilise les favoris du compte. Une inscription refusée conserve les favoris visiteurs.

L'import ne demande aucune information de film au MCP et n'enregistre aucune fiche complète.
Le chargement ultérieur des cartes utilise toujours `/api/movies/lookup`.

Une connexion à un compte existant récupère sa propre liste. Elle n'importe pas automatiquement
les favoris visiteurs. Ceux-ci restent disponibles en mode visiteur après déconnexion, s'ils
n'ont pas déjà été transférés par une inscription réussie.

## Jeton et session

Après une inscription ou une connexion réussie, `secrets.token_urlsafe(32)` crée un jeton à
partir de 32 octets aléatoires, soit 256 bits. Ce jeton opaque ne contient aucune donnée
utilisateur. Il sert de clé d'accès à une session côté backend.

Le backend conserve uniquement son empreinte SHA-256, avec l'ID utilisateur et l'expiration.
À chaque requête authentifiée, il calcule l'empreinte du jeton reçu, retrouve la session et
contrôle sa date d'expiration. SHA-256 convient ici à un jeton aléatoire de forte entropie ;
les mots de passe humains utilisent Argon2id.

Le jeton original est transmis uniquement dans le cookie `moviematch_session` :

| Attribut | Effet |
| --- | --- |
| `HttpOnly` | Le code JavaScript du frontend ne peut pas lire le jeton. |
| `SameSite=Lax` | Limite l'envoi du cookie lors de certaines requêtes depuis d'autres sites. |
| `Path=/api` | Restreint l'envoi aux chemins de l'API sur cet hôte. |
| `Max-Age=86400` par défaut | Le navigateur conserve le cookie au maximum 24 heures. |
| `Secure` avec `AUTH_COOKIE_SECURE=true` | Le cookie est envoyé uniquement par HTTPS. |

Le serveur contrôle l'expiration indépendamment du navigateur. Modifier une date côté client
ne prolonge donc pas la session. Les sessions expirées sont retirées lors de leur utilisation
et lors de la création d'une nouvelle session.

Une connexion réussie supprime la session associée au cookie précédent et crée un nouveau
jeton. Une déconnexion supprime la session côté backend et efface le cookie avec le même chemin.
Un ancien jeton ne permet alors plus d'accéder aux favoris. Les sessions ouvertes dans d'autres
navigateurs restent indépendantes.

## Protection des requêtes et des favoris

Toutes les modifications de comptes/sessions/favoris exigent `X-MovieMatch-Request: 1`.
Cet en-tête n'est pas un secret : il sert à empêcher un formulaire HTML externe de provoquer
une action avec le cookie de la victime. Un script d'un autre site doit obtenir un accord
CORS avant de pouvoir envoyer cet en-tête.

Le backend vérifie aussi `Origin` lorsqu'il est présent. Il accepte uniquement son origine
et les origines exactes configurées dans `CORS_ORIGINS`. Il n'autorise pas `*` avec les cookies.
Les clients non navigateurs peuvent envoyer l'en-tête sans `Origin`, mais ils doivent toujours
fournir une session valide pour les données privées.

Le propriétaire des favoris vient toujours de la session. Les routes d'ajout et de suppression
ne reçoivent pas d'identifiant de propriétaire. `X-MovieMatch-User` sert seulement à détecter
un onglet encore affiché sur un ancien compte alors qu'un autre onglet a changé la connexion.
Un ID différent du compte de la session provoque un refus ; cet en-tête ne donne aucun droit.

Le backend autorise au maximum dix tentatives de connexion/inscription par minute et par
adresse cliente observée. Cette limitation est en mémoire. Derrière un proxy qui masque les
adresses clientes, plusieurs visiteurs peuvent partager cette limite ; le déploiement devra
configurer les proxies de confiance avant d'utiliser une limite par visiteur à grande échelle.

Les réponses contenant le compte ou la liste de favoris utilisent `Cache-Control: no-store`.
Le code ne journalise pas les mots de passe ou les jetons.

## Frontend

`api.js` centralise les appels à `/api`, les en-têtes des actions, les cookies et les erreurs.
Le frontend utilise le même domaine que l'API grâce au proxy Vite ou Nginx. Le proxy Nginx
préserve maintenant le port du header `Host`, utile pour contrôler l'origine en local.

`useAccount.js` gère l'utilisateur, ses IDs de favoris et les actions. Au chargement et au
retour sur l'onglet, il appelle `/api/auth/me`. Il conserve les informations publiques en
mémoire React. Aucun jeton ni mot de passe n'est placé dans le stockage du navigateur.

Les modifications de favoris connectés attendent la réussite de l'API avant de modifier
l'affichage. Les actions sont désactivées pendant une modification pour éviter les requêtes
contradictoires. En cas de session expirée, le frontend vérifie à nouveau le compte.

`AccountPanel.jsx` contient les formulaires d'inscription et de connexion et le bouton de
déconnexion. Le champ mot de passe est vidé après l'envoi. Les formulaires disposent de labels,
des attributs autocomplete appropriés et des contraintes cohérentes avec le backend.

`App.jsx` affiche les vues Découvrir, Favoris et Mon compte. Le composant de contenu est
recréé lorsqu'on change de compte : cela efface la conversation et le cache des fiches du
compte précédent. Les requêtes de fiches devenues inutiles sont annulées. Une réponse de
recherche issue de l'ancien compte ne doit pas être ajoutée à la nouvelle conversation.

Pour les recommandations connectées, le backend utilise ses propres favoris et ignore la
liste de personnalisation fournie par le navigateur. Le classement sur les dix favoris
récents et la limite de sept films sont conservés.

## Routes

| Méthode et chemin | Corps / réponse |
| --- | --- |
| `POST /api/auth/signup` | Reçoit username, password, favorite_ids ; renvoie user et favorite_ids, pose le cookie. |
| `POST /api/auth/login` | Reçoit username et password ; renvoie user et favorite_ids, pose le cookie. |
| `GET /api/auth/me` | Renvoie user et favorite_ids, ou user=null pour un visiteur. |
| `POST /api/auth/logout` | Révoque la session et efface le cookie ; réponse 204. |
| `GET /api/favorites` | Renvoie les IDs du compte connecté. |
| `PUT /api/favorites/{movie_id}` | Ajoute un ID ; l'ajout répété reste sans doublon. |
| `DELETE /api/favorites/{movie_id}` | Retire un ID ; une suppression répétée reste sans effet supplémentaire. |

## Lancement et test manuel

Installer les dépendances backend mises à jour puis lancer comme précédemment. En Docker,
reconstruire les images : `docker compose up --build`. Aucun service de base n'est nécessaire.

Dans `backend/.env`, les valeurs par défaut conviennent à HTTP local :

```dotenv
AUTH_COOKIE_SECURE=false
AUTH_SESSION_HOURS=24
```

Pour un déploiement HTTPS, configurer `AUTH_COOKIE_SECURE=true` et les origines réelles.
Un backend redémarré ou rechargé par `--reload` perd les comptes et les sessions.

Parcours conseillé : ajouter deux favoris en visiteur, actualiser, créer un compte, vérifier
leur présence, retirer un film, se déconnecter puis se reconnecter. Créer un second compte
permet de vérifier l'isolation. Arrêter puis relancer le backend confirme la nature temporaire
du stockage.

Les tests backend couvrent la validation, les doublons, l'import, les jetons, les cookies,
les expirations, la révocation, les origines, la limite de tentatives, les favoris et
deux inscriptions concurrentes. Ils utilisent des services de films simulés.

## Références

- [API argon2-cffi](https://argon2-cffi.readthedocs.io/en/stable/api.html)
- [Gestion des sessions OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [Protection CSRF pour les API OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
