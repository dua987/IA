# app/routers/entreprise_offres.py

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from ..db import offres_collection
from ..schemas import OffreCreate, OffreOut

router = APIRouter(
    prefix="/api/offres",
    tags=["offres"],
)


# Utilitaire : convertir un document MongoDB -> OffreOut
def mongo_to_offre(doc) -> OffreOut:
    return OffreOut(
        id=str(doc["_id"]),
        entrepriseNom=doc.get("entrepriseNom", ""),
        titre=doc.get("titre", ""),
        ville=doc.get("ville"),
        description=doc.get("description", ""),
        competences=doc.get("competences", []),
        nbCandidatures=doc.get("nbCandidatures", 0),
        createdAt=doc.get("createdAt", datetime.utcnow()).isoformat(),
    )


# Lister toutes les offres (option : filtrer par entreprise)
@router.get("", response_model=List[OffreOut])
def get_offres(entreprise: Optional[str] = None):
    filtre = {}
    if entreprise:
        filtre["entrepriseNom"] = entreprise

    docs = offres_collection.find(filtre).sort("createdAt", -1)
    return [mongo_to_offre(doc) for doc in docs]


# Ajouter une nouvelle offre
@router.post("", response_model=OffreOut, status_code=201)
def create_offre(offre: OffreCreate):
    document = {
        "entrepriseNom": offre.entrepriseNom,
        "titre": offre.titre,
        "ville": offre.ville,
        "description": offre.description,
        "competences": offre.competences,
        "nbCandidatures": 0,
        "createdAt": datetime.utcnow(),
    }
    result = offres_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return mongo_to_offre(document)


# Supprimer une offre par son ID
@router.delete("/{id}")
def delete_offre(id: str):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    res = offres_collection.delete_one({"_id": oid})

    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Offre non trouvée")

    return {"message": "Offre supprimée"}
