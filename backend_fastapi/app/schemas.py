# app/schemas.py
from pydantic import BaseModel
from typing import List, Optional


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
