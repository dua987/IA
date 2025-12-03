# app/main.py  — Point d’entrée de l’API Plateforme d’Affectation

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import entreprise_offres

app = FastAPI(title="API Plateforme Affectation")

# CORS pour autoriser ton frontend (HTML)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # à restreindre plus tard
    allow_methods=["*"],
    allow_headers=["*"],
)


# Route de test simple
@app.get("/")
def read_root():
    return {"message": "API Plateforme Affectation OK"}


# Inclusion des routes /api/offres
app.include_router(entreprise_offres.router)


# Lancer le serveur en local si on fait : python -m app.main
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
