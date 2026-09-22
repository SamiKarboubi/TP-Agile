# Backend

## Installation

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Démarrage

```powershell
uvicorn app.main:app --reload
```

L'API est disponible sur `http://127.0.0.1:8000`. La vérification de santé est exposée sur `/health` et la documentation interactive sur `/docs`.
