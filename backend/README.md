# Backend FastAPI

Consultez le [README principal](../README.md) pour les variables d'environnement, le MCP et le lancement complet de l'application.
Le [guide PostgreSQL](../docs/database.md) détaille la configuration, Adminer et les images GHCR.

Depuis la racine du projet :

```powershell
Copy-Item backend/.env.example backend/.env
# Renseigner les clés et DB_PASSWORD avant les commandes suivantes.
docker compose --env-file backend/.env up -d db
python -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend/requirements-dev.txt
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

Renseignez les clés dans `backend/.env` avant une recherche réelle. L'API expose `/health`, `/docs`, `/api/config` et `/api/recommendations`. Le serveur `tmdb-mcp` est lancé automatiquement comme sous-processus au premier appel qui en a besoin.
Ne remplacez pas un `.env` existant ; ajoutez les variables manquantes. Le backend crée les
tables PostgreSQL au démarrage et refuse de démarrer sans `DB_PASSWORD` ou sans accès à la base.

Pour les tests :

```powershell
python -m pytest
```
