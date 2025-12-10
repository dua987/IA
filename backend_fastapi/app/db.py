# app/db.py
# Gestion de la connexion MongoDB

from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "affectation_db"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# Collection des offres
offres_collection = db["offres"]
