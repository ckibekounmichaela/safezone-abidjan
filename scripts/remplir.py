import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text

# ---------------------------------------------------------------
# 1) Se connecter à la base (le mot de passe est dans le fichier .env)
# ---------------------------------------------------------------
DOSSIER_PROJET = Path(__file__).resolve().parent.parent
load_dotenv(DOSSIER_PROJET / ".env")
adresse_base = URL.create(
    "postgresql+psycopg2",
    username="postgres",
    password=os.getenv("PG_MOT_DE_PASSE"),
    host="localhost",
    port=5432,
    database="safezone",
)
base = create_engine(adresse_base)

# ---------------------------------------------------------------
# 2) Lire le fichier créé par l'IA (extraction.py)
# ---------------------------------------------------------------
fiches = pd.read_csv(DOSSIER_PROJET / "donnees" / "articles_extraits.csv", dtype=str).fillna("")
fiches = fiches.drop_duplicates(subset="id_article")
print(f"Fiches lues : {len(fiches)}")

# ---------------------------------------------------------------
# 3) Vider les tables (pour pouvoir relancer le script sans doublons)
# ---------------------------------------------------------------
with base.begin() as connexion:
    # Créer les 3 tables si elles n'existent pas encore (sur un nouvel ordinateur, par exemple)
    connexion.execute(text("""
        CREATE TABLE IF NOT EXISTS communes (
            id_commune  SERIAL PRIMARY KEY,                -- numéro donné automatiquement
            nom         VARCHAR NOT NULL UNIQUE,           -- ex. « Abobo » (une seule fois)
            latitude    NUMERIC,                           -- centre de la commune
            longitude   NUMERIC
        );
        CREATE TABLE IF NOT EXISTS articles (
            id_article        VARCHAR PRIMARY KEY,         -- l'identifiant donné au scraping
            source            VARCHAR,                     -- le journal
            titre             TEXT NOT NULL,
            adresse           TEXT,                        -- le lien vers l'article
            date_publication  DATE,
            est_agression     BOOLEAN NOT NULL,            -- la réponse de l'IA
            resume            TEXT
        );
        CREATE TABLE IF NOT EXISTS agressions (
            id_agression     SERIAL PRIMARY KEY,
            id_article       VARCHAR NOT NULL REFERENCES articles (id_article),   -- l'article d'où vient l'agression
            id_commune       INTEGER REFERENCES communes (id_commune),            -- vide si la commune est inconnue
            quartier         VARCHAR,
            type_agression   VARCHAR,
            arme             VARCHAR,
            date_faits       DATE NOT NULL,
            heure            TIME,
            tranche_horaire  VARCHAR,
            nombre_victimes  INTEGER DEFAULT 0,
            deplacement      TEXT,                         -- comment se déplaçait la victime
            eclairage        TEXT                          -- le lieu était-il éclairé
        );
    """))
    # Pour une base créée avant l'ajout du déplacement et de l'éclairage : on ajoute les 2 colonnes
    connexion.execute(text("ALTER TABLE agressions ADD COLUMN IF NOT EXISTS deplacement TEXT"))
    connexion.execute(text("ALTER TABLE agressions ADD COLUMN IF NOT EXISTS eclairage TEXT"))
    # La vue utilisée par eda.py : le nombre d'agressions par commune et par trimestre
    connexion.execute(text("""
        CREATE OR REPLACE VIEW vue_agressions_par_trimestre AS
        SELECT c.nom AS commune,
               EXTRACT(YEAR FROM a.date_faits)::int    AS annee,
               EXTRACT(QUARTER FROM a.date_faits)::int AS trimestre,
               COUNT(*) AS nombre_agressions
        FROM agressions a JOIN communes c ON c.id_commune = a.id_commune
        GROUP BY 1, 2, 3
    """))
    connexion.execute(text("TRUNCATE agressions, articles, communes RESTART IDENTITY"))

# ---------------------------------------------------------------
# 4) Remplir les 3 tables
# ---------------------------------------------------------------
# 4a) Communes : nom + centre approximatif de la commune (latitude, longitude)
communes = pd.DataFrame([
    ("Abobo", 5.418, -4.020), ("Adjamé", 5.367, -4.022), ("Anyama", 5.494, -4.052),
    ("Attécoubé", 5.337, -4.045), ("Bingerville", 5.355, -3.885), ("Cocody", 5.360, -3.980),
    ("Koumassi", 5.297, -3.951), ("Marcory", 5.303, -3.983), ("Plateau", 5.322, -4.017),
    ("Port-Bouët", 5.256, -3.930), ("Songon", 5.310, -4.270), ("Treichville", 5.292, -4.009),
    ("Yopougon", 5.345, -4.083),
], columns=["nom", "latitude", "longitude"])
communes.to_sql("communes", base, if_exists="append", index=False)

# 4b) Articles : on garde seulement les colonnes de la table « articles »
articles = fiches[["id_article", "source", "titre", "adresse", "date_publication", "resume"]].copy()
articles["est_agression"] = fiches["est_agression"] == "True"
articles["date_publication"] = pd.to_datetime(articles["date_publication"], errors="coerce")
articles.to_sql("articles", base, if_exists="append", index=False)

# 4c) Agressions : seulement les articles où l'IA a dit « c'est une agression »
agressions = fiches[fiches["est_agression"] == "True"].copy()

# Date de l'agression ; si l'article ne la donne pas, on prend la date de publication
agressions["date_faits"] = agressions["date_faits"].where(agressions["date_faits"] != "",
                                                          agressions["date_publication"])
agressions["date_faits"] = pd.to_datetime(agressions["date_faits"], errors="coerce")
agressions = agressions.dropna(subset=["date_faits"])

# On remplace le nom de la commune par son numéro (id_commune) ; « inconnue » devient vide
numeros = pd.read_sql("SELECT id_commune, nom FROM communes", base)
agressions = agressions.merge(numeros, left_on="commune", right_on="nom", how="left")

agressions["heure"] = agressions["heure"].replace("", None)
agressions["nombre_victimes"] = pd.to_numeric(agressions["nombre_victimes"], errors="coerce").fillna(0)

colonnes = ["id_article", "id_commune", "quartier", "type_agression", "arme",
            "date_faits", "heure", "tranche_horaire", "nombre_victimes",
            "deplacement", "eclairage"]
agressions[colonnes].to_sql("agressions", base, if_exists="append", index=False)

# ---------------------------------------------------------------
# 5) Vérifier avec une requête SQL : combien d'agressions par commune ?
# ---------------------------------------------------------------
print(f"Communes : {len(communes)} | Articles : {len(articles)} | Agressions : {len(agressions)}\n")
resultat = pd.read_sql("""
    SELECT COALESCE(c.nom, 'inconnue') AS commune, COUNT(*) AS agressions
    FROM agressions a LEFT JOIN communes c ON c.id_commune = a.id_commune
    GROUP BY 1 ORDER BY 2 DESC
""", base)
print(resultat.to_string(index=False))
