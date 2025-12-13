# main.py  — API FastAPI pour l'Interface Stagiaire (Plateforme d'Affectation)

from fastapi import FastAPI, HTTPException, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from pymongo import MongoClient
import gridfs
from bson import ObjectId
import io

# ----------------------------------------------------
# 1) CONNEXION MONGODB + GridFS
# ----------------------------------------------------
# Assure-toi que MongoDB tourne en local sur le port 27017
client = MongoClient("mongodb://localhost:27017")
db = client["affectation_db"]

# Collections
offres_collection = db["offres"]          # réutilise ta collection d'offres
stagiaires_collection = db["stagiaires"]
candidatures_collection = db["candidatures"]

# GridFS pour stocker les CV (fichiers binaires)
fs = gridfs.GridFS(db)

# ----------------------------------------------------
# 2) MODÈLES Pydantic (entrées et sorties API)
# ----------------------------------------------------
class StagiaireCreate(BaseModel):
    nom: str
    prenom: Optional[str] = None
    email: str
    filiere: Optional[str] = None
    niveau: Optional[str] = None
    ville: Optional[str] = None
    competences: Optional[List[str]] = []     # ex: ["Python","SQL"]
    cv_text: Optional[str] = None             # (optionnel) texte extrait du CV


class StagiaireOut(BaseModel):
    id: str
    nom: str
    prenom: Optional[str] = None
    email: str
    filiere: Optional[str]
    niveau: Optional[str]
    ville: Optional[str]
    competences: List[str]
    cvUrl: Optional[str]
    createdAt: str


class StagiaireUpdate(BaseModel):
    filiere: Optional[str] = None
    niveau: Optional[str] = None
    ville: Optional[str] = None
    competences: Optional[List[str]] = None
    cv_text: Optional[str] = None


class CandidatureCreate(BaseModel):
    stagiaireId: str
    offreId: str
    message: Optional[str] = None


class OffreOut(BaseModel):
    id: str
    entrepriseNom: Optional[str] = None
    titre: str
    ville: Optional[str] = None
    description: str
    competences: List[str]
    nbCandidatures: int
    createdAt: str


# ----------------------------------------------------
# 3) UTILITAIRE : Convertir un document MongoDB → Pydantic
# ----------------------------------------------------
def mongo_to_stagiaire(doc) -> StagiaireOut:
    return StagiaireOut(
        id=str(doc["_id"]),
        nom=doc.get("nom", ""),
        prenom=doc.get("prenom"),
        email=doc.get("email", ""),
        filiere=doc.get("filiere"),
        niveau=doc.get("niveau"),
        ville=doc.get("ville"),
        competences=doc.get("competences", []),
        cvUrl=(f"/api/stagiaires/{str(doc['_id'])}/cv" if doc.get("cvId") else None),
        createdAt=doc.get("createdAt", datetime.utcnow()).isoformat()
    )


def mongo_to_offre(doc) -> OffreOut:
    return OffreOut(
        id=str(doc["_id"]),
        entrepriseNom=doc.get("entrepriseNom"),
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
app = FastAPI(title="API Stagiaire — Plateforme d'Affectation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # à restreindre en production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route de test simple
@app.get("/")
def read_root():
    return {"message": "API Stagiaire OK"}


# ----------------------------------------------------
# 5) ROUTES STAGIAIRES (CRUD)
# ----------------------------------------------------

# Créer un profil stagiaire
@app.post("/api/stagiaires", response_model=StagiaireOut, status_code=201)
def create_stagiaire(stagiaire: StagiaireCreate):
    # vérification simple email unique
    if stagiaires_collection.find_one({"email": stagiaire.email}):
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    document = stagiaire.dict()
    document["createdAt"] = datetime.utcnow()
    # pas de mot de passe ici (ajoute auth plus tard si souhaité)
    result = stagiaires_collection.insert_one(document)
    document["_id"] = result.inserted_id
    return mongo_to_stagiaire(document)


# Récupérer un stagiaire par id
@app.get("/api/stagiaires/{id}", response_model=StagiaireOut)
def get_stagiaire(id: str):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    doc = stagiaires_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Stagiaire non trouvé")

    return mongo_to_stagiaire(doc)


# Mettre à jour le profil d'un stagiaire
@app.put("/api/stagiaires/{id}", response_model=StagiaireOut)
def update_stagiaire(id: str, update: StagiaireUpdate):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour")

    stagiaires_collection.update_one({"_id": oid}, {"$set": update_data})
    doc = stagiaires_collection.find_one({"_id": oid})
    return mongo_to_stagiaire(doc)


# Lister tous les stagiaires (optionnel, admin)
@app.get("/api/stagiaires", response_model=List[StagiaireOut])
def list_stagiaires():
    docs = stagiaires_collection.find().sort("createdAt", -1)
    return [mongo_to_stagiaire(doc) for doc in docs]


# ----------------------------------------------------
# 6) UPLOAD / DOWNLOAD CV (GridFS)
# ----------------------------------------------------

# Upload CV (PDF) pour un stagiaire
@app.post("/api/stagiaires/{id}/upload-cv")
def upload_cv(id: str, file: UploadFile = File(...)):
    """
    Upload un CV (PDF ou autre) et stocke dans GridFS.
    Remplace l'ancien CV s'il existe.
    """
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    stagiaire = stagiaires_collection.find_one({"_id": oid})
    if not stagiaire:
        raise HTTPException(status_code=404, detail="Stagiaire non trouvé")

    # supprimer ancien CV si existant
    old_cv_id = stagiaire.get("cvId")
    if old_cv_id:
        try:
            fs.delete(ObjectId(old_cv_id))
        except Exception:
            # ignore si déjà supprimé
            pass

    # lire le contenu et insérer dans GridFS
    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Fichier vide")

    cv_id = fs.put(content, filename=file.filename, contentType=file.content_type)
    stagiaires_collection.update_one({"_id": oid}, {"$set": {"cvId": str(cv_id), "cvFilename": file.filename}})

    return {"message": "CV uploaded", "cvId": str(cv_id), "cvFilename": file.filename}


# Télécharger le CV (retourne le fichier binaire)
@app.get("/api/stagiaires/{id}/cv")
def download_cv(id: str):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    stagiaire = stagiaires_collection.find_one({"_id": oid})
    if not stagiaire:
        raise HTTPException(status_code=404, detail="Stagiaire non trouvé")

    cv_id = stagiaire.get("cvId")
    if not cv_id:
        raise HTTPException(status_code=404, detail="Aucun CV pour ce stagiaire")

    try:
        grid_out = fs.get(ObjectId(cv_id))
        content = grid_out.read()
        headers = {"Content-Disposition": f'attachment; filename="{stagiaire.get("cvFilename","cv")}"'}
        return Response(content, media_type=grid_out.contentType or "application/octet-stream", headers=headers)
    except Exception:
        raise HTTPException(status_code=500, detail="Erreur lors de la lecture du CV")


# ----------------------------------------------------
# 7) ROUTES OFFRES (lecture pour stagiaire)
# ----------------------------------------------------

# Lister toutes les offres (filtrage possible par ville / compétence)
@app.get("/api/offres", response_model=List[OffreOut])
def get_offres(ville: Optional[str] = None, competence: Optional[str] = None):
    filtre = {}
    if ville:
        filtre["ville"] = ville
    if competence:
        filtre["competences"] = {"$in": [competence]}

    docs = offres_collection.find(filtre).sort("createdAt", -1)
    return [mongo_to_offre(doc) for doc in docs]


# Détail d'une offre
@app.get("/api/offres/{id}", response_model=OffreOut)
def get_offre(id: str):
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")
    doc = offres_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Offre non trouvée")
    return mongo_to_offre(doc)


# ----------------------------------------------------
# 8) MATCHING SIMPLE (par compétences) & RECOMMANDATIONS
# ----------------------------------------------------

@app.get("/api/stagiaires/{id}/recommandations", response_model=List[OffreOut])
def recommend_offres(id: str, top: int = 10):
    """
    Recommandation simple : on récupère les compétences du stagiaire
    et on retourne les offres contenant au moins une compétence commune.
    (À remplacer plus tard par matching vectoriel / IA)
    """
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    stagiaire = stagiaires_collection.find_one({"_id": oid})
    if not stagiaire:
        raise HTTPException(status_code=404, detail="Stagiaire non trouvé")

    skills = stagiaire.get("competences", [])
    if not skills:
        # si pas de compétences renseignées, retourner les dernières offres
        docs = offres_collection.find().sort("createdAt", -1).limit(top)
        return [mongo_to_offre(d) for d in docs]

    docs = offres_collection.find({"competences": {"$in": skills}}).sort("createdAt", -1).limit(top)
    return [mongo_to_offre(d) for d in docs]


# ----------------------------------------------------
# 9) CANDIDATURES (stagiaire postule à une offre)
# ----------------------------------------------------

@app.post("/api/stagiaires/candidater")
def candidater(payload: CandidatureCreate):
    try:
        sid = ObjectId(payload.stagiaireId)
        oid = ObjectId(payload.offreId)
    except Exception:
        raise HTTPException(status_code=400, detail="ID stagiaire ou offre invalide")

    stagiaire = stagiaires_collection.find_one({"_id": sid})
    if not stagiaire:
        raise HTTPException(status_code=404, detail="Stagiaire non trouvé")

    offre = offres_collection.find_one({"_id": oid})
    if not offre:
        raise HTTPException(status_code=404, detail="Offre non trouvée")

    # empêcher double candidature
    exists = candidatures_collection.find_one({"stagiaireId": sid, "offreId": oid})
    if exists:
        raise HTTPException(status_code=400, detail="Vous avez déjà postulé à cette offre")

    doc = {
        "stagiaireId": sid,
        "offreId": oid,
        "message": payload.message,
        "status": "envoyée",   # envoyée / retenue / refusée
        "createdAt": datetime.utcnow()
    }
    candidatures_collection.insert_one(doc)

    # incrémenter compteur candidatures sur l'offre (optionnel)
    offres_collection.update_one({"_id": oid}, {"$inc": {"nbCandidatures": 1}})

    return {"status": "ok", "message": "Candidature envoyée"}


# Lister les candidatures d'un stagiaire
@app.get("/api/stagiaires/{id}/candidatures")
def list_candidatures(id: str):
    try:
        sid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID invalide")

    docs = candidatures_collection.find({"stagiaireId": sid}).sort("createdAt", -1)
    results = []
    for c in docs:
        offre = offres_collection.find_one({"_id": c["offreId"]})
        results.append({
            "candidatureId": str(c["_id"]),
            "offreId": str(c["offreId"]),
            "offreTitre": offre.get("titre") if offre else None,
            "entrepriseNom": offre.get("entrepriseNom") if offre else None,
            "message": c.get("message"),
            "status": c.get("status"),
            "createdAt": c.get("createdAt").isoformat()
        })
    return results


# ----------------------------------------------------
# 10) LANCER LE SERVEUR UVICORN
# ----------------------------------------------------
# Tu peux lancer l’API avec :
#  python -m uvicorn main:app --reload
# ou
#  python main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


