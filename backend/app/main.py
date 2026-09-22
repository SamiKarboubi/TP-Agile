from fastapi import FastAPI

app = FastAPI(
    title="Backend API",
    version="0.1.0",
)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return the service availability status."""
    return {"status": "ok"}
