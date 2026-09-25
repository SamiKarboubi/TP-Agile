# Backend FastAPI

Consultez le [README principal](../README.md) pour les variables d'environnement, le MCP et le lancement complet de l'application.

Depuis la racine du projet :

```powershell
python -m venv backend/.venv
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend/requirements-dev.txt
Copy-Item backend/.env.example backend/.env
cd backend
uvicorn app.main:app --reload --port 8000
```

Renseignez les clés dans `backend/.env` avant une recherche réelle. L'API expose `/health`, `/docs`, `/api/config` et `/api/recommendations`. Le serveur `tmdb-mcp` est lancé automatiquement comme sous-processus au premier appel qui en a besoin.

Pour les tests :

```powershell
python -m pytest
```
