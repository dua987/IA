# main.py  — API FastAPI pour la Plateforme d’Affectation

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from pymongo import MongoClient
from bson import ObjectId

# ----------------------------------------------------
# 1) CONNEXION MONGODB
# ----------------------------------------------------
# Assure-toi que MongoDB tourne en local sur le port 27017
# et que la base "affectation_db" existe (elle sera créée
# automatiquement au premier insert si besoin).
client = MongoClient("mongodb://localhost:27017")
db = client["affectation_db"]
offres_collection = db["offres"]

# ----------------------------------------------------
# 2) MODÈLES Pydantic (entrées et sorties API)
# ----------------------------------------------------
class OffreCreate(BaseModel):
    entrepriseNom: str
    titre: str
    ville: Optional[str] = None
    description: str
    competences: Optional[List[str]] = []


class OffreOut(BaseModel):
    id: str
    entrepriseNom: str
    titre: str
    ville: Optional[str] = None
    description: str
    competences: List[str]
    nbCandidatures: int
    createdAt: str


# ----------------------------------------------------
# 3) UTILITAIRE : Convertir un document MongoDB → OffreOut
# ----------------------------------------------------
def mongo_to_offre(doc) -> OffreOut:
    return OffreOut(
        id=str(doc["_id"]),
        entrepriseNom=doc.get("entrepriseNom", ""),
        titre=doc.get("titre", ""),
        ville=doc.get("ville"),
        description=doc.get("description", ""),
        competences=doc.get("competences", []),
        nbCandidatures=doc.get("nbCandidatures", 0),
        createdAt=doc.get("createdAt", datetime.utcnow()).isoformat()
    )


# ----------------------------------------------------
# 4) FASTAPI + CORS
# ----------------------------------------------------
app = FastAPI(title="API Plateforme Affectation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # à restreindre plus tard (origines autorisées)
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route de test simple
@app.get("/")
def read_root():
    return {"message": "API Plateforme Affectation OK"}


# ----------------------------------------------------
# 5) ROUTES API OFFRES
# ----------------------------------------------------

# Lister toutes les offres (option : filtrer par entreprise)
@app.get("/api/offres", response_model=List[OffreOut])
def get_offres(entreprise: Optional[str] = None):
    filtre = {}
    if entreprise:
        filtre["entrepriseNom"] = entreprise

    docs = offres_collection.find(filtre).sort("createdAt", -1)
    return [mongo_to_offre(doc) for doc in docs]


# Ajouter une nouvelle offre
@app.post("/api/offres", response_model=OffreOut, status_code=201)
def create_offre(offre: OffreCreate):
    document = {
        "entrepriseNom": offre.entrepriseNom,
        "titre": offre.titre,
        "ville": offre.ville,
        "description": offre.description,
        "competences": offre.competences,
        "nbCandidatures": 0,
        "createdAt": datetime.utcnow()
    }
    result = offres_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return mongo_to_offre(document)


# Supprimer une offre par son ID
@app.delete("/api/offres/{id}")
def delete_offre(id: str):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    res = offres_collection.delete_one({"_id": oid})

    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Offre non trouvée")

    return {"message": "Offre supprimée"}


# ----------------------------------------------------
# 6) LANCER LE SERVEUR UVICORN (optionnel)
# ----------------------------------------------------
# Tu peux lancer l’API de deux façons :
# 1) python -m uvicorn main:app --reload
# 2) python main.py  (grâce au bloc ci-dessous)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
  