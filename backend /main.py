from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
import gridfs
import io

from jose import jwt
from passlib.context import CryptContext

# ================== CONFIG ==================
SECRET_KEY = "SECRET_ULTRA_SECURISE"
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

# ================== DB ==================
client = MongoClient("mongodb://localhost:27017")
db = client["affectation_db"]

stagiaires = db["stagiaires"]
offres = db["offres"]
candidatures = db["candidatures"]
fs = gridfs.GridFS(db)

# ================== APP ==================
app = FastAPI(title="API Interface Stagiaire")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== UTILS ==================
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)

def create_token(data: dict):
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

# ================== MODELS ==================
class Stagiaire(BaseModel):
    nom: str
    email: EmailStr
    ville: Optional[str] = None
    competences: List[str] = []

class Login(BaseModel):
    email: EmailStr
    password: str

class Candidature(BaseModel):
    stagiaireId: str
    offreId: str

class OffreOut(BaseModel):
    id: str
    titre: str
    ville: Optional[str]
    competences: List[str]

# ================== ROUTES ==================

@app.get("/")
def root():
    return {"status": "API OK"}

# ---------- AUTH ----------
@app.post("/api/login")
def login(data: Login):
    user = stagiaires.find_one({"email": data.email})
    if not user or not verify_password(data.password, user["password"]):
        raise HTTPException(401, "Email ou mot de passe incorrect")

    token = create_token({
        "sub": str(user["_id"]),
        "email": user["email"]
    })
    return {"access_token": token, "token_type": "bearer"}

# ---------- STAGIAIRE ----------
@app.post("/api/stagiaires")
def create_stagiaire(s: Stagiaire, password: str):
    sid = stagiaires.insert_one({
        **s.dict(),
        "password": hash_password(password),
        "createdAt": datetime.utcnow()
    }).inserted_id
    return {"id": str(sid)}

# ---------- UPLOAD CV ----------
@app.post("/api/stagiaires/{id}/upload-cv")
async def upload_cv(id: str, file: UploadFile = File(...)):

    stagiaire = stagiaires.find_one({"_id": ObjectId(id)})
    if not stagiaire:
        raise HTTPException(404, "Stagiaire introuvable")

    if file.content_type not in [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]:
        raise HTTPException(400, "Format non autorisé")

    content = await file.read()
    if not content:
        raise HTTPException(400, "Fichier vide")

    cv_id = fs.put(
        content,
        filename=file.filename,
        contentType=file.content_type,
        uploadedAt=datetime.utcnow()
    )

    stagiaires.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"cvId": str(cv_id)}}
    )

    return {"message": "CV uploadé avec succès"}

# ---------- DOWNLOAD CV ----------
@app.get("/api/stagiaires/{id}/cv")
def download_cv(id: str):

    stagiaire = stagiaires.find_one({"_id": ObjectId(id)})
    if not stagiaire or "cvId" not in stagiaire:
        raise HTTPException(404, "CV introuvable")

    cv_file = fs.get(ObjectId(stagiaire["cvId"]))

    return StreamingResponse(
        io.BytesIO(cv_file.read()),
        media_type=cv_file.content_type,
        headers={
            "Content-Disposition": f"attachment; filename={cv_file.filename}"
        }
    )

# ---------- OFFRES ----------
@app.get("/api/offres", response_model=List[OffreOut])
def get_offres():
    return [
        OffreOut(
            id=str(o["_id"]),
            titre=o["titre"],
            ville=o.get("ville"),
            competences=o.get("competences", [])
        )
        for o in offres.find()
    ]

# ---------- CANDIDATURE ----------
@app.post("/api/candidater")
def candidater(c: Candidature):

    if not stagiaires.find_one({"_id": ObjectId(c.stagiaireId)}):
        raise HTTPException(404, "Stagiaire introuvable")

    if not offres.find_one({"_id": ObjectId(c.offreId)}):
        raise HTTPException(404, "Offre introuvable")

    if candidatures.find_one({
        "stagiaireId": c.stagiaireId,
        "offreId": c.offreId
    }):
        raise HTTPException(400, "Déjà postulé")

    candidatures.insert_one({
        "stagiaireId": c.stagiaireId,
        "offreId": c.offreId,
        "date": datetime.utcnow()
    })

    return {"message": "Candidature envoyée"}

# ---------- IA RECOMMANDATIONS ----------
@app.get("/api/recommandations/{stagiaire_id}")
def recommandations(stagiaire_id: str):

    stagiaire = stagiaires.find_one({"_id": ObjectId(stagiaire_id)})
    if not stagiaire:
        raise HTTPException(404, "Stagiaire introuvable")

    skills = set(stagiaire.get("competences", []))
    results = []

    for o in offres.find():
        offer_skills = set(o.get("competences", []))
        score = len(skills.intersection(offer_skills))
        if score > 0:
            results.append({
                "offreId": str(o["_id"]),
                "titre": o["titre"],
                "score": score
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:5]

# ---------- STATISTIQUES ----------
@app.get("/api/stats/stagiaire/{id}")
def stats_stagiaire(id: str):

    total = candidatures.count_documents({"stagiaireId": id})
    par_ville = {}

    for c in candidatures.find({"stagiaireId": id}):
        offre = offres.find_one({"_id": ObjectId(c["offreId"])})
        if offre:
            ville = offre.get("ville", "Inconnue")
            par_ville[ville] = par_ville.get(ville, 0) + 1

    return {
        "total_candidatures": total,
        "par_ville": par_ville
    }

@app.get("/api/stats/global")
def stats_globales():
    return {
        "stagiaires": stagiaires.count_documents({}),
        "offres": offres.count_documents({}),
        "candidatures": candidatures.count_documents({})
    }

# ================== RUN ==================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
