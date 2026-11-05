import hashlib
import hmac
import math
import os
import re
import secrets
import time
import socket
import sys
import unicodedata
from pathlib import Path
from typing import Literal

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import URL, create_engine, text

# ---------------------------------------------------------------
# 1) Connexion à la base de données
# ---------------------------------------------------------------
DOSSIER_PROJET = Path(__file__).resolve().parent.parent
sys.path.append(str(DOSSIER_PROJET))
import config  # noqa: E402

load_dotenv(DOSSIER_PROJET / ".env")
# En ligne (sur Render), l'adresse complète de la base est donnée par la variable DATABASE_URL
# (ex. « postgresql://...neon.tech/safezone »). Sur cet ordinateur, elle n'existe pas : on prend la base locale.
adresse_en_ligne = os.getenv("DATABASE_URL")
if adresse_en_ligne:
    base = create_engine(adresse_en_ligne.replace("postgresql://", "postgresql+psycopg2://", 1))
else:
    base = create_engine(URL.create(
        "postgresql+psycopg2",
        username="postgres",
        password=os.getenv("PG_MOT_DE_PASSE"),
        host="localhost", port=5432,
        database="safezone",
    ))


def lire(requete: str, **parametres) -> list[dict]:
    """Exécute une requête SQL et renvoie une liste de dictionnaires (facile à mettre en JSON).
    Exemple : lire("SELECT nom FROM communes") -> [{"nom": "Abobo"}, {"nom": "Adjamé"}, ...]"""
    with base.connect() as connexion:
        lignes = connexion.execute(text(requete), parametres).mappings().all()
    return [dict(ligne) for ligne in lignes]


def ecrire(requete: str, **parametres) -> None:
    """Exécute une requête SQL qui MODIFIE la base (INSERT, UPDATE...) et enregistre le changement."""
    with base.begin() as connexion:
        connexion.execute(text(requete), parametres)


# ---------------------------------------------------------------
# 2) Création de l'API
# ---------------------------------------------------------------
app = FastAPI(
    title="SafeZone Abidjan — API",
    description="Risque d'agression par commune et par quartier à Abidjan, "
                "à partir des faits divers de la presse.",
    version="2.0",
)
# Autorise le site web (ouvert dans le navigateur) à appeler l'API depuis n'importe quelle adresse
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------
# 3) Petites fonctions utiles
# ---------------------------------------------------------------
def simplifier(mot: str) -> str:
    """'Port Bouët' -> 'port-bouet' : pour comparer des noms sans accents, majuscules ni espaces."""
    mot = unicodedata.normalize("NFD", mot.lower().strip())
    sans_accents = "".join(c for c in mot if unicodedata.category(c) != "Mn")
    return sans_accents.replace(" ", "-")


def trouver_commune(nom: str) -> str:
    """Retrouve le vrai nom d'une commune ('port bouet' -> 'Port-Bouët'), sinon renvoie une erreur 404."""
    for commune in lire("SELECT nom FROM communes"):
        if simplifier(commune["nom"]) == simplifier(nom):
            return commune["nom"]
    raise HTTPException(status_code=404, detail=f"Commune inconnue : {nom}")


def contient(texte: str, mot: str) -> bool:
    """Le mot est-il dans le texte, en entier ? ('sable' est dans 'zone-sable', pas dans 'responsable')"""
    return re.search(rf"(?<![a-z0-9]){re.escape(mot)}(?![a-z0-9])", texte) is not None


# ---------------------------------------------------------------
# 4) Les communes
# ---------------------------------------------------------------
@app.get("/etat")
def accueil():
    """Pour vérifier que l'API répond."""
    return {"message": "API SafeZone Abidjan en marche. Documentation : /docs"}


@app.get("/communes")
def liste_des_communes():
    """Les 13 communes, leur position, le nombre d'agressions et la prévision du modèle."""
    return lire("""
        SELECT c.nom, c.latitude::float, c.longitude::float,
               COUNT(a.id_agression)        AS total_agressions,
               p.periode, p.agressions_prevues::float, p.niveau_risque
        FROM communes c
        LEFT JOIN agressions a  ON a.id_commune = c.id_commune
        LEFT JOIN predictions p ON p.commune = c.nom
        GROUP BY c.nom, c.latitude, c.longitude, p.periode, p.agressions_prevues, p.niveau_risque
        ORDER BY p.agressions_prevues DESC NULLS LAST
    """)


@app.get("/communes/{nom}")
def fiche_commune(nom: str):
    """Tout sur une commune : prévision, types d'agression, heures, années, quartiers, derniers faits."""
    nom = trouver_commune(nom)
    # Le début de requête commun : « les agressions de cette commune »
    de_la_commune = "FROM agressions a JOIN communes c ON c.id_commune = a.id_commune WHERE c.nom = :nom"
    prevision = lire("SELECT periode, agressions_prevues::float, niveau_risque "
                     "FROM predictions WHERE commune = :nom", nom=nom)
    return {
        "commune": nom,
        "prevision": prevision[0] if prevision else None,
        "total_agressions": lire(f"SELECT COUNT(*) AS n {de_la_commune}", nom=nom)[0]["n"],
        "par_type": lire(f"SELECT type_agression, COUNT(*) AS nombre {de_la_commune} "
                         "GROUP BY 1 ORDER BY 2 DESC", nom=nom),
        "par_tranche_horaire": lire(f"SELECT tranche_horaire, COUNT(*) AS nombre {de_la_commune} "
                                    "AND tranche_horaire <> 'inconnue' GROUP BY 1 ORDER BY 2 DESC", nom=nom),
        "par_annee": lire(f"SELECT EXTRACT(YEAR FROM date_faits)::int AS annee, COUNT(*) AS nombre "
                          f"{de_la_commune} GROUP BY 1 ORDER BY 1", nom=nom),
        "quartiers_cites": [{"quartier": q["quartier"], "nombre": q["nombre"]}
                            for q in chercher_quartiers(commune=nom, limite=5)],
        "dernieres_agressions": dernieres_agressions(commune=nom, limite=5),
    }


# ---------------------------------------------------------------
# 5) Les quartiers
# ---------------------------------------------------------------
# La liste de référence (config.QUARTIERS), mise à plat :
# [{"quartier": "Angré", "commune": "Cocody", "variantes": ["angre", "djorobite", "bessikoi"]}, ...]
REFERENTIEL = []
for commune, quartiers in config.QUARTIERS.items():
    for nom, variantes in quartiers.items():
        REFERENTIEL.append({
            "quartier": nom,
            "commune": commune,
            "variantes": [simplifier(v) for v in [nom, *variantes]],
        })


def quartier_de_reference(texte: str, commune: str):
    """Le quartier de la liste de référence cité dans un texte, ou None.
    Exemple : ('Angré château', 'Cocody') -> le quartier Angré."""
    texte = simplifier(texte)
    for q in REFERENTIEL:
        if q["commune"] == commune:
            for variante in q["variantes"]:
                if contient(texte, variante):
                    return q
    return None


def compter_quartiers(commune: str | None = None) -> list[dict]:
    """Tous les quartiers connus et leur nombre d'agressions :
      - les quartiers de la liste de référence (même ceux qui n'ont aucune agression) ;
      - les quartiers cités dans les articles mais absents de la liste (écrits comme dans l'article).
    « Angré château » ou « Angré Djorobité 1 » comptent pour Angré."""
    # 1) On part de la liste de référence, avec 0 agression pour chaque quartier
    comptes = {}
    for q in REFERENTIEL:
        if commune is None or q["commune"] == commune:
            comptes[(q["commune"], q["quartier"])] = {
                "quartier": q["quartier"], "commune": q["commune"],
                "nombre": 0, "reference": True, "variantes": q["variantes"],
            }

    # 2) On lit les quartiers écrits dans les agressions (avec leur nombre)
    filtre = "AND c.nom = :commune" if commune else ""
    cites = lire(f"""
        SELECT a.quartier, c.nom AS commune, COUNT(*) AS nombre
        FROM agressions a JOIN communes c ON c.id_commune = a.id_commune
        WHERE a.quartier IS NOT NULL AND a.quartier <> '' {filtre}
        GROUP BY a.quartier, c.nom
    """, commune=commune)

    # 3) Chaque quartier écrit dans un article est rangé dans le bon quartier de la liste
    for cite in cites:
        reference = quartier_de_reference(cite["quartier"], cite["commune"])
        if reference:
            cle = (cite["commune"], reference["quartier"])
        else:
            cle = (cite["commune"], simplifier(cite["quartier"]))
            if cle not in comptes:
                comptes[cle] = {"quartier": cite["quartier"], "commune": cite["commune"], "nombre": 0,
                                "reference": False, "variantes": [simplifier(cite["quartier"])]}
        comptes[cle]["nombre"] += cite["nombre"]
    return list(comptes.values())


@app.get("/quartiers")
def chercher_quartiers(recherche: str = "", commune: str | None = None, limite: int = Query(10, ge=1, le=50)):
    """Chercher un quartier (ex. recherche=angre -> Angré, Cocody, et son nombre d'agressions).
    La recherche ignore les accents et les majuscules.
    Sans recherche : les quartiers les plus cités (ceux qui ont au moins une agression)."""
    quartiers = compter_quartiers(trouver_commune(commune) if commune else None)
    mot = simplifier(recherche)

    if mot:
        trouves = []
        for q in quartiers:
            if any(mot in variante for variante in q["variantes"]):
                exact = mot == simplifier(q["quartier"]) or mot in q["variantes"]
                trouves.append((0 if exact else 1, q))
        trouves.sort(key=lambda t: (t[0], not t[1]["reference"], -t[1]["nombre"]))
        quartiers = [q for _, q in trouves]
    else:
        quartiers = [q for q in quartiers if q["nombre"] > 0]
        quartiers.sort(key=lambda q: -q["nombre"])

    # On ne renvoie que les informations utiles (pas les variantes)
    return [{"quartier": q["quartier"], "commune": q["commune"], "nombre": q["nombre"],
             "reference": q["reference"]} for q in quartiers[:limite]]


@app.get("/quartiers/tous")
def tous_les_quartiers():
    """Les quartiers de la liste de référence, pour les listes déroulantes « Quartier »."""
    return [{"quartier": q["quartier"], "commune": q["commune"]} for q in REFERENTIEL]


def trouver_quartier(quartier: str, commune: str | None = None) -> dict:
    """Retrouve un quartier ('angre' -> Angré, Cocody). Erreur 404 s'il est inconnu,
    erreur 400 s'il existe dans plusieurs communes (ex. Belleville) et que la commune n'est pas donnée."""
    if len(simplifier(quartier)) < 2:
        raise HTTPException(status_code=404, detail="Indiquez une commune ou un quartier.")
    trouves = chercher_quartiers(recherche=quartier, commune=commune, limite=50)
    exacts = [q for q in trouves if simplifier(q["quartier"]) == simplifier(quartier)]
    if not exacts:
        exacts = trouves[:1]
    if not exacts:
        raise HTTPException(status_code=404, detail=f"Quartier inconnu : {quartier}.")
    communes = {q["commune"] for q in exacts}
    if len(communes) > 1:
        raise HTTPException(status_code=400, detail=(
            f"« {quartier} » existe dans plusieurs communes ({', '.join(sorted(communes))}) : "
            f"précisez la commune."))
    return exacts[0]


@app.get("/quartier/faits")
def faits_du_quartier(quartier: str, commune: str | None = None):
    """Ce qui s'est passé dans un quartier : nombre d'agressions, types, armes, moments, derniers faits.
    Sert à l'agent pour donner des conseils concrets (« ici, ce sont surtout des vols à l'arraché »)."""
    choisi = trouver_quartier(quartier, commune)
    reference = next((q for q in REFERENTIEL if q["quartier"] == choisi["quartier"]
                      and q["commune"] == choisi["commune"]), None)
    variantes = reference["variantes"] if reference else [simplifier(choisi["quartier"])]

    # Toutes les agressions de la commune qui ont un quartier écrit
    agressions = lire("""
        SELECT a.date_faits::text AS date, a.quartier, a.type_agression, a.arme, a.tranche_horaire,
               ar.titre, ar.adresse AS lien_article
        FROM agressions a
        JOIN communes c  ON c.id_commune = a.id_commune
        JOIN articles ar ON ar.id_article = a.id_article
        WHERE c.nom = :commune AND a.quartier IS NOT NULL AND a.quartier <> ''
        ORDER BY a.date_faits DESC
    """, commune=choisi["commune"])
    # On garde seulement celles de CE quartier
    du_quartier = [a for a in agressions
                   if any(contient(simplifier(a["quartier"]), v) for v in variantes)]

    def compter(cle: str) -> dict:
        """Compte les valeurs d'une colonne : {'braquage': 3, 'meurtre': 1}, sans les 'inconnue'."""
        comptes = {}
        for a in du_quartier:
            if a[cle] and a[cle] != "inconnue":
                comptes[a[cle]] = comptes.get(a[cle], 0) + 1
        return dict(sorted(comptes.items(), key=lambda c: -c[1]))

    return {
        "quartier": choisi["quartier"],
        "commune": choisi["commune"],
        "total_agressions": len(du_quartier),
        "par_type": compter("type_agression"),
        "par_arme": compter("arme"),
        "par_moment": compter("tranche_horaire"),
        "derniers_faits": du_quartier[:5],
    }


@app.get("/quartiers/classement")
def classement_des_quartiers(commune: str, heure: int = Query(..., ge=0, le=23)):
    """Les quartiers d'une commune à une heure donnée, du plus calme au plus risqué.
    Sert à l'agent pour proposer une autre destination (« Mermoz est plus calme qu'Angré »)."""
    commune = trouver_commune(commune)
    score_commune = calculer_risque(commune=commune, heure=heure)["score"]
    quartiers = [q for q in compter_quartiers(commune) if q["reference"]]
    moyenne = moyenne_par_quartier(commune)
    classement = []
    for q in quartiers:
        score = min(100, round(score_commune * facteur_quartier(q["nombre"], moyenne)))
        classement.append({"quartier": q["quartier"], "score": score, "niveau": niveau_de(score)})
    classement.sort(key=lambda q: q["score"])
    return {"commune": commune, "heure": heure, "quartiers": classement}


# ---------------------------------------------------------------
# 6) Les agressions et les statistiques
# ---------------------------------------------------------------
@app.get("/agressions")
def dernieres_agressions(commune: str | None = None, limite: int = Query(20, ge=1, le=100)):
    """Les agressions les plus récentes, avec le lien vers l'article de presse."""
    filtre = "WHERE c.nom = :commune" if commune else ""
    return lire(f"""
        SELECT a.date_faits::text AS date, c.nom AS commune, a.quartier, a.type_agression,
               a.arme, a.tranche_horaire, ar.titre, ar.resume, ar.adresse AS lien_article
        FROM agressions a
        JOIN articles ar     ON ar.id_article = a.id_article
        LEFT JOIN communes c ON c.id_commune = a.id_commune
        {filtre}
        ORDER BY a.date_faits DESC
        LIMIT :limite
    """, commune=trouver_commune(commune) if commune else None, limite=limite)


@app.get("/statistiques")
def statistiques():
    """Les chiffres clés pour le tableau de bord."""
    return {
        "total_agressions": lire("SELECT COUNT(*) AS n FROM agressions")[0]["n"],
        "periode": lire("SELECT MIN(EXTRACT(YEAR FROM date_faits))::int AS debut, "
                        "MAX(EXTRACT(YEAR FROM date_faits))::int AS fin FROM agressions")[0],
        "par_commune": lire("SELECT c.nom AS commune, COUNT(*) AS nombre FROM agressions a "
                            "JOIN communes c ON c.id_commune = a.id_commune GROUP BY 1 ORDER BY 2 DESC"),
        "par_tranche_horaire": lire("SELECT tranche_horaire, COUNT(*) AS nombre FROM agressions "
                                    "WHERE tranche_horaire <> 'inconnue' GROUP BY 1 ORDER BY 2 DESC"),
        "par_type": lire("SELECT type_agression, COUNT(*) AS nombre FROM agressions "
                         "GROUP BY 1 ORDER BY 2 DESC"),
        "par_arme": lire("SELECT arme, COUNT(*) AS nombre FROM agressions WHERE arme <> 'inconnue' "
                         "GROUP BY 1 ORDER BY 2 DESC"),
    }


# ---------------------------------------------------------------
# 7) Le calcul du risque
# ---------------------------------------------------------------
DUREES = {"matin": 6, "après-midi": 6, "soir": 4, "nuit": 8}  # en heures
# Lissage : chaque commune est complétée par l'équivalent de 15 agressions réparties comme à Abidjan,
# pour éviter qu'une tranche sans cas connu donne un risque nul.
POIDS_ABIDJAN = 15
HEURE_DE_CHAQUE_MOMENT = {"matin": 9, "après-midi": 15, "soir": 20, "nuit": 23}
MOMENTS = {"matin": "Le matin (6 h – 12 h)", "après-midi": "L'après-midi (12 h – 18 h)",
           "soir": "Le soir (18 h – 22 h)", "nuit": "La nuit (22 h – 6 h)"}
CONSEILS = {
    "élevé": "Évitez de circuler seul(e), restez sur les grands axes éclairés et gardez votre téléphone hors de vue.",
    "moyen": "Restez vigilant(e), surtout dans les zones peu fréquentées.",
    "faible": "Risque faible, mais gardez les précautions habituelles.",
}


def tranche_de(heure: int) -> str:
    """22 -> 'nuit' : le moment de la journée qui contient cette heure."""
    if 6 <= heure < 12:
        return "matin"
    if 12 <= heure < 18:
        return "après-midi"
    if 18 <= heure < 22:
        return "soir"
    return "nuit"


def niveau_de(score: int) -> str:
    """Le niveau d'un score : 50 et plus = élevé, de 20 à 49 = moyen, moins de 20 = faible."""
    if score >= 50:
        return "élevé"
    if score >= 20:
        return "moyen"
    return "faible"


# --- Le moyen de déplacement et l'éclairage ---
# Ce que l'utilisateur peut choisir (le code court va dans l'adresse, le nom complet est celui des articles)
DEPLACEMENTS = {"pied": "à pied", "moto": "moto", "taxi": "taxi / woro-woro / gbaka",
                "voiture": "voiture", "bus": "bus"}
# Part de chaque moyen dans les déplacements quotidiens à Abidjan.
# Source : enquête ménages-déplacements 2013 du Grand Abidjan (JICA / MCLAU, rapport SDUGA 2015),
# reprise par la Banque mondiale (SSATP, 2018) : 7 150 000 déplacements par jour, dont
#   - 3 720 000 à pied (52 %) ;
#   - 3 430 000 motorisés (48 %) : woro-woro + gbaka 54 % et taxis 6 % de ces trajets (soit 29 % du total),
#     véhicules personnels 345 000 (5 % du total), bus SOTRA environ le reste (14 % du total).
# L'enquête ne sépare pas les voitures et les motos personnelles : on les compte donc ensemble.
PARTS_A_ABIDJAN = {"à pied": 0.52, "taxi / woro-woro / gbaka": 0.29, "bus": 0.14, "véhicule personnel": 0.05}
# Rue sombre : environ 15 % de délits en plus que dans une rue éclairée.
# Source : Welsh et Farrington, revues d'études sur l'éclairage public (2008 : -21 % ; 2022 : -14 %).
FACTEUR_RUE_SOMBRE = 1.15


def groupe_de(deplacement: str) -> str:
    """'voiture' ou 'moto' -> 'véhicule personnel' (comme dans l'enquête) ; sinon le nom ne change pas."""
    if deplacement in ("voiture", "moto"):
        return "véhicule personnel"
    return deplacement


def facteur_deplacement(deplacement: str) -> float:
    """
    De combien on corrige le score selon le moyen de déplacement (entre 0,5 et 1,5).
      facteur = part de ce moyen chez NOS victimes / part de ce moyen dans les déplacements d'Abidjan
    Exemple : si 30 % des victimes étaient en taxi alors que 30 % des trajets se font en taxi,
    le facteur vaut 1 : le taxi n'est ni plus ni moins risqué que la moyenne.
    """
    # Combien de victimes pour chaque moyen (on garde seulement les victimes qui se déplaçaient)
    victimes = {}
    for ligne in lire("SELECT deplacement, COUNT(*) AS n FROM agressions "
                      "WHERE deplacement NOT IN ('sur place', 'inconnu') GROUP BY 1"):
        groupe = groupe_de(ligne["deplacement"])
        victimes[groupe] = victimes.get(groupe, 0) + ligne["n"]
    total = sum(victimes.values())
    groupe = groupe_de(deplacement)
    part_abidjan = PARTS_A_ABIDJAN[groupe]
    # Comme pour les heures, on complète par 15 victimes « moyennes » : il y a peu de cas par moyen
    part_victimes = (victimes.get(groupe, 0) + POIDS_ABIDJAN * part_abidjan) / (total + POIDS_ABIDJAN)
    facteur = part_victimes / part_abidjan
    return min(max(facteur, 0.5), 1.5)


def ajouter_deplacement_et_eclairage(resultat: dict, deplacement: str, eclairage: str) -> dict:
    """Corrige le score selon le moyen de déplacement et l'éclairage (si l'utilisateur les a choisis)."""
    score = resultat["score"]
    if deplacement in DEPLACEMENTS:
        nom = DEPLACEMENTS[deplacement]
        facteur = facteur_deplacement(nom)
        score = score * facteur
        if facteur > 1.1:
            phrase = "plus souvent victime que la moyenne"
        elif facteur < 0.9:
            phrase = "moins souvent victime que la moyenne"
        else:
            phrase = "à peu près autant victime que la moyenne"
        debut = {"à pied": "À pied", "moto": "À moto"}.get(nom, f"En {nom}")
        resultat["a_savoir"].append(f"{debut}, on est {phrase} "
                                    f"(nos articles comparés aux déplacements des Abidjanais).")
        resultat["detail"]["facteur_deplacement"] = round(facteur, 2)
    if eclairage == "sombre" and resultat["tranche_horaire"] in ("soir", "nuit"):
        score = score * FACTEUR_RUE_SOMBRE
        resultat["a_savoir"].append("Rue sombre : les études montrent environ 15 % de délits en plus "
                                    "que dans une rue éclairée.")
        resultat["detail"]["facteur_eclairage"] = FACTEUR_RUE_SOMBRE
    score = min(100, round(score))
    resultat["score"] = score
    resultat["niveau"] = niveau_de(score)
    resultat["conseil"] = CONSEILS[resultat["niveau"]]
    return resultat


@app.get("/risque")
def calculer_risque(commune: str, heure: int = Query(..., ge=0, le=23, description="heure de 0 à 23"),
                    deplacement: Literal["", "pied", "moto", "taxi", "voiture", "bus"] = "",
                    eclairage: Literal["", "eclairee", "sombre"] = ""):
    """
    Calcule un score de risque de 0 à 100 pour une commune à une heure donnée.
      1. Risque de la commune  = prévision du modèle / plus forte prévision d'Abidjan   (entre 0 et 1)
      2. Risque de l'heure     = ce moment de la journée comparé au moment le plus risqué   (entre 0 et 1)
      3. Score = risque de la commune × risque de l'heure × 100
      4. Si l'utilisateur les donne : × facteur déplacement × facteur éclairage (voir plus haut)
    """
    nom = trouver_commune(commune)
    tranche = tranche_de(heure)

    # 1) Risque de la commune : la prévision du modèle XGBoost (étape 6)
    previsions = {p["commune"]: p["agressions_prevues"]
                  for p in lire("SELECT commune, agressions_prevues::float FROM predictions")}
    if not previsions:
        raise HTTPException(status_code=503, detail="Pas de prévisions : lance d'abord entrainement.py")
    risque_commune = previsions.get(nom, 0) / max(previsions.values())

    # 2) Risque de l'heure : à quels moments ont lieu les agressions de la commune ?
    #    On complète par tout Abidjan : sinon une commune sans agression connue le soir
    #    (ex. Marcory) aurait un score de 0 le soir, comme s'il n'y avait aucun risque.
    commune_n = {l["tranche_horaire"]: l["n"] for l in lire(
        """SELECT tranche_horaire, COUNT(*) AS n FROM agressions a
           JOIN communes c ON c.id_commune = a.id_commune
           WHERE c.nom = :nom AND tranche_horaire <> 'inconnue' GROUP BY 1""", nom=nom)}
    abidjan_n = {l["tranche_horaire"]: l["n"] for l in lire(
        "SELECT tranche_horaire, COUNT(*) AS n FROM agressions "
        "WHERE tranche_horaire <> 'inconnue' GROUP BY 1")}
    total_commune = sum(commune_n.values())
    total_abidjan = sum(abidjan_n.values()) or 1
    part = {}
    for t in DUREES:
        part_abidjan = abidjan_n.get(t, 0) / total_abidjan
        part[t] = (commune_n.get(t, 0) + POIDS_ABIDJAN * part_abidjan) / (total_commune + POIDS_ABIDJAN)
    # Une tranche de 8 h a « naturellement » plus d'agressions qu'une tranche de 4 h : on divise par sa durée
    intensite = {t: part[t] / (DUREES[t] / 24) for t in DUREES}
    risque_heure = intensite[tranche] / max(intensite.values())

    # 3) Le score final, de 0 à 100
    score = round(100 * risque_commune * risque_heure)
    niveau = niveau_de(score)

    # 4) Deux phrases simples pour l'utilisateur (les applications les affichent telles quelles)
    if risque_commune >= 0.7:
        phrase_lieu = f"{nom} fait partie des communes les plus touchées d'Abidjan."
    elif risque_commune >= 0.3:
        phrase_lieu = f"{nom} est moyennement touchée par les agressions."
    else:
        phrase_lieu = f"{nom} fait partie des communes les moins touchées d'Abidjan."
    if risque_heure >= 0.8:
        phrase_heure = f"{MOMENTS[tranche]} est l'un des moments les plus risqués de la journée."
    elif risque_heure >= 0.4:
        phrase_heure = f"{MOMENTS[tranche]} est un moment où il faut rester vigilant."
    else:
        phrase_heure = f"{MOMENTS[tranche]} est un moment plutôt calme de la journée."

    resultat = {
        "commune": nom,
        "heure": heure,
        "tranche_horaire": tranche,
        "score": score,
        "niveau": niveau,
        "conseil": CONSEILS[niveau],
        "a_savoir": [phrase_lieu, phrase_heure],
        "detail": {
            "risque_commune": round(risque_commune, 2),
            "agressions_prevues_trimestre": round(previsions.get(nom) or 0, 2),
            "risque_heure": round(risque_heure, 2),
            "part_des_agressions_dans_cette_tranche": round(part[tranche], 2),
            "heures_calculees_sur": f"{nom} ({total_commune} agressions à l'heure connue), complété par tout Abidjan",
        },
        "attention": "Estimation faite à partir des faits divers de la presse : ce n'est pas une certitude.",
    }
    return ajouter_deplacement_et_eclairage(resultat, deplacement, eclairage)


def moyenne_par_quartier(commune: str) -> float:
    """Le nombre moyen d'agressions par quartier connu de la commune."""
    quartiers = compter_quartiers(commune)
    return sum(q["nombre"] for q in quartiers) / len(quartiers)


def facteur_quartier(agressions_du_quartier: int, moyenne: float) -> float:
    """De combien on corrige le score de la commune pour un quartier (entre 0,5 et 1,5).
    Plus de 1 = quartier plus cité que la moyenne ; moins de 1 = moins cité.
    Le « + 1 » et la racine carrée adoucissent les écarts, car il y a peu de cas par quartier."""
    facteur = math.sqrt((agressions_du_quartier + 1) / (moyenne + 1))
    return min(max(facteur, 0.5), 1.5)


@app.get("/risque/quartier")
def risque_quartier(quartier: str, heure: int = Query(..., ge=0, le=23, description="heure de 0 à 23"),
                    commune: str | None = None,
                    deplacement: Literal["", "pied", "moto", "taxi", "voiture", "bus"] = "",
                    eclairage: Literal["", "eclairee", "sombre"] = ""):
    """
    Score de risque (0 à 100) d'un quartier à une heure donnée.
      1. On part du score de sa commune à cette heure (voir /risque)
      2. On le multiplie par le facteur du quartier (entre 0,5 et 1,5, voir facteur_quartier)
      3. Puis par les facteurs déplacement et éclairage, si l'utilisateur les a choisis
      4. Le score ne dépasse jamais 100
    """
    choisi = trouver_quartier(quartier, commune)
    resultat = calculer_risque(commune=choisi["commune"], heure=heure)
    moyenne = moyenne_par_quartier(choisi["commune"])
    facteur = facteur_quartier(choisi["nombre"], moyenne)
    score = min(100, round(resultat["score"] * facteur))
    niveau = niveau_de(score)

    # La phrase sur le lieu parle maintenant du quartier (la phrase sur l'heure ne change pas)
    if facteur > 1.05:
        comparaison = "plus souvent cité dans les faits divers que"
    elif facteur < 0.95:
        comparaison = "moins souvent cité dans les faits divers que"
    else:
        comparaison = "cité dans les faits divers autant que"
    resultat["a_savoir"][0] = f"{choisi['quartier']} est {comparaison} les autres quartiers de {choisi['commune']}."

    resultat["quartier"] = choisi["quartier"]
    resultat["score_commune"] = resultat["score"]
    resultat["niveau_commune"] = resultat["niveau"]
    resultat["score"] = score
    resultat["niveau"] = niveau
    resultat["conseil"] = CONSEILS[niveau]
    resultat["detail"]["agressions_dans_le_quartier"] = choisi["nombre"]
    resultat["detail"]["moyenne_par_quartier_de_la_commune"] = round(moyenne, 1)
    resultat["detail"]["facteur_quartier"] = round(facteur, 2)
    return ajouter_deplacement_et_eclairage(resultat, deplacement, eclairage)


@app.get("/risque/lieu")
def risque_d_un_lieu(lieu: str, heure: int = Query(..., ge=0, le=23), commune: str | None = None,
                     deplacement: Literal["", "pied", "moto", "taxi", "voiture", "bus"] = "",
                     eclairage: Literal["", "eclairee", "sombre"] = ""):
    """Le risque d'un lieu, que ce soit une commune (« Cocody ») ou un quartier (« Angré »)."""
    for c in lire("SELECT nom FROM communes"):
        if simplifier(c["nom"]) == simplifier(lieu):
            return calculer_risque(commune=c["nom"], heure=heure, deplacement=deplacement, eclairage=eclairage)
    return risque_quartier(quartier=lieu, heure=heure, commune=commune,
                           deplacement=deplacement, eclairage=eclairage)


@app.get("/risque/journee")
def risque_sur_la_journee(lieu: str, commune: str | None = None):
    """Le risque d'un lieu aux 4 moments de la journée, pour trouver le meilleur moment pour y aller."""
    moments = []
    for tranche, heure in HEURE_DE_CHAQUE_MOMENT.items():
        risque = risque_d_un_lieu(lieu=lieu, heure=heure, commune=commune)
        moments.append({"moment": MOMENTS[tranche], "score": risque["score"], "niveau": risque["niveau"]})
    plus_calme = min(moments, key=lambda m: m["score"])
    plus_risque = max(moments, key=lambda m: m["score"])
    return {"lieu": lieu, "moments": moments,
            "moment_le_plus_calme": plus_calme["moment"], "moment_le_plus_risque": plus_risque["moment"]}


@app.get("/risque/toutes")
def risque_toutes_les_communes(heure: int = Query(..., ge=0, le=23)):
    """Le score de risque des 13 communes à une heure donnée (pour colorier la carte)."""
    resultats = [calculer_risque(commune=c["nom"], heure=heure) for c in lire("SELECT nom FROM communes")]
    return sorted(resultats, key=lambda r: r["score"], reverse=True)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance entre deux points GPS, en kilomètres (formule de Haversine)."""
    rayon_terre = 6371
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * rayon_terre * math.asin(math.sqrt(a))


@app.get("/risque/position")
def risque_selon_position(latitude: float, longitude: float, heure: int = Query(..., ge=0, le=23)):
    """Risque à l'endroit où se trouve l'utilisateur (position GPS du téléphone ou du navigateur) :
    on prend la commune dont le centre est le plus proche."""
    communes = lire("SELECT nom, latitude::float, longitude::float FROM communes")
    for c in communes:
        c["distance_km"] = distance_km(latitude, longitude, c["latitude"], c["longitude"])
    plus_proche = min(communes, key=lambda c: c["distance_km"])
    if plus_proche["distance_km"] > 25:
        raise HTTPException(status_code=404, detail=(
            f"Vous semblez être hors du District d'Abidjan "
            f"({plus_proche['distance_km']:.0f} km de {plus_proche['nom']})."))
    resultat = calculer_risque(commune=plus_proche["nom"], heure=heure)
    resultat["distance_km"] = round(plus_proche["distance_km"], 1)
    return resultat


# ---------------------------------------------------------------
# 8) Assistant IA (agent.py) — limites de coût : taille de la question, historique, débit
# ---------------------------------------------------------------
LONGUEUR_MAX_QUESTION = 500
MESSAGES_GARDES = 10
QUESTIONS_PAR_HEURE = 20

# Horodatage des dernières demandes par clé (IP ou compte), en mémoire.
ESSAIS: dict[str, list[float]] = {}


def essais_recents(cle: str, secondes: int) -> list[float]:
    """Les demandes de cette personne faites pendant les « secondes » dernières secondes."""
    maintenant = time.time()
    ESSAIS[cle] = [moment for moment in ESSAIS.get(cle, []) if maintenant - moment < secondes]
    return ESSAIS[cle]


def adresse_ip(requete: Request) -> str:
    """L'adresse Internet de la personne. En ligne, Render la met dans l'en-tête « X-Forwarded-For »."""
    transmise = requete.headers.get("x-forwarded-for", "")
    return transmise.split(",")[0].strip() or (requete.client.host if requete.client else "inconnue")


class Message(BaseModel):
    """Un message de la conversation."""
    role: Literal["user", "assistant"]
    contenu: str = Field(max_length=4000)


class Question(BaseModel):
    """Ce que les applications envoient à POST /assistant."""
    question: str = Field(min_length=2, max_length=LONGUEUR_MAX_QUESTION)
    historique: list[Message] = []


@app.post("/assistant")
def assistant(demande: Question, requete: Request):
    """Pose une question à l'agent IA. Exemple de corps :
    {"question": "Est-ce que je peux aller à Yopougon ce soir ?", "historique": []}"""
    from agent import demander
    recentes = essais_recents("assistant:" + adresse_ip(requete), 3600)
    if len(recentes) >= QUESTIONS_PAR_HEURE:
        raise HTTPException(status_code=429, detail="Vous avez posé beaucoup de questions. Réessayez dans une heure.")
    recentes.append(time.time())
    derniers = demande.historique[-MESSAGES_GARDES:]
    try:
        return demander(demande.question, [m.model_dump() for m in derniers])
    except Exception as erreur:
        print("Erreur de l'assistant :", erreur)
        raise HTTPException(status_code=503, detail="L'assistant ne répond pas pour le moment. Réessayez plus tard.")


# ---------------------------------------------------------------
# 9) Comptes utilisateurs
#    Mots de passe : PBKDF2-SHA256 salé. Jetons : stockés en SHA-256, valables 30 jours.
#    Connexion bloquée 15 min après 10 échecs sur un même compte.
# ---------------------------------------------------------------
JOURS_DE_CONNEXION = 30
ESSAIS_DE_CONNEXION = 10
LONGUEURS_MAX = {"nom": 100, "email": 254, "mot_de_passe": 128}

ecrire("""
    CREATE TABLE IF NOT EXISTS utilisateurs (
        id_utilisateur SERIAL PRIMARY KEY,
        nom            TEXT NOT NULL,
        email          TEXT NOT NULL UNIQUE,
        mot_de_passe   TEXT NOT NULL,             -- "sel$empreinte"
        jeton          TEXT,                      -- empreinte du jeton (NULL = déconnecté)
        date_creation  TIMESTAMP DEFAULT NOW()
    )
""")
ecrire("ALTER TABLE utilisateurs ADD COLUMN IF NOT EXISTS date_jeton TIMESTAMP")


def empreinte(mot_de_passe: str, sel: str) -> str:
    """Calcule l'empreinte d'un mot de passe. Le « sel » est un code au hasard propre à chaque compte :
    deux personnes qui ont le même mot de passe n'ont donc pas la même empreinte."""
    resultat = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel.encode(), 200_000)
    return resultat.hex()


def verifier_mot_de_passe(mot_de_passe: str, enregistre: str) -> bool:
    """Le mot de passe tapé correspond-il à ce qui est enregistré (« sel$empreinte ») ?"""
    sel, empreinte_enregistree = enregistre.split("$")
    return hmac.compare_digest(empreinte(mot_de_passe, sel), empreinte_enregistree)


def empreinte_jeton(jeton: str) -> str:
    """L'empreinte d'un jeton (SHA-256). Le jeton est déjà long et au hasard : pas besoin de sel."""
    return hashlib.sha256(jeton.encode()).hexdigest()


def nouveau_jeton(email: str) -> str:
    """Crée un nouveau badge de connexion pour ce compte. La base garde son empreinte, l'application le badge."""
    jeton = secrets.token_hex(32)
    ecrire("UPDATE utilisateurs SET jeton = :empreinte, date_jeton = NOW() WHERE email = :email",
           empreinte=empreinte_jeton(jeton), email=email)
    return jeton


def verifier_longueurs(**champs: str) -> None:
    """Refuse un nom, un e-mail ou un mot de passe trop long (erreur 400 avec un message clair)."""
    for nom_du_champ, valeur in champs.items():
        if len(valeur) > LONGUEURS_MAX[nom_du_champ]:
            raise HTTPException(status_code=400, detail=(
                f"Trop long : {LONGUEURS_MAX[nom_du_champ]} caractères au plus ({nom_du_champ.replace('_', ' ')})."))


class Inscription(BaseModel):
    """Ce que l'application envoie pour créer un compte."""
    nom: str
    email: str
    mot_de_passe: str


class Connexion(BaseModel):
    """Ce que l'application envoie pour se connecter."""
    email: str
    mot_de_passe: str


class Deconnexion(BaseModel):
    """Ce que l'application envoie pour se déconnecter."""
    jeton: str


@app.post("/comptes/inscription")
def inscription(compte: Inscription):
    """Crée un compte. Renvoie le nom, l'e-mail et le jeton (l'utilisateur est connecté tout de suite)."""
    nom = compte.nom.strip()
    email = compte.email.strip().lower()
    verifier_longueurs(nom=nom, email=email, mot_de_passe=compte.mot_de_passe)
    if len(nom) < 2:
        raise HTTPException(status_code=400, detail="Indiquez votre nom.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="L'adresse e-mail n'est pas valide.")
    if len(compte.mot_de_passe) < 6:
        raise HTTPException(status_code=400, detail="Le mot de passe doit faire au moins 6 caractères.")
    if lire("SELECT 1 FROM utilisateurs WHERE email = :email", email=email):
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet e-mail. Connectez-vous.")
    sel = secrets.token_hex(16)
    ecrire("INSERT INTO utilisateurs (nom, email, mot_de_passe) VALUES (:nom, :email, :mdp)",
           nom=nom, email=email, mdp=f"{sel}${empreinte(compte.mot_de_passe, sel)}")
    return {"nom": nom, "email": email, "jeton": nouveau_jeton(email)}


@app.post("/comptes/connexion")
def connexion(compte: Connexion):
    """Vérifie l'e-mail et le mot de passe. Renvoie le nom, l'e-mail et un nouveau jeton."""
    email = compte.email.strip().lower()
    verifier_longueurs(email=email, mot_de_passe=compte.mot_de_passe)
    rates = essais_recents("connexion:" + email, 15 * 60)
    if len(rates) >= ESSAIS_DE_CONNEXION:
        raise HTTPException(status_code=429, detail="Trop d'essais. Réessayez dans 15 minutes.")
    trouves = lire("SELECT nom, mot_de_passe FROM utilisateurs WHERE email = :email", email=email)
    # Message identique dans les deux cas : on ne révèle pas si l'e-mail existe.
    if not trouves or not verifier_mot_de_passe(compte.mot_de_passe, trouves[0]["mot_de_passe"]):
        rates.append(time.time())
        raise HTTPException(status_code=401, detail="E-mail ou mot de passe incorrect.")
    return {"nom": trouves[0]["nom"], "email": email, "jeton": nouveau_jeton(email)}


def compte_du_jeton(authorization: str) -> dict:
    """Le compte qui correspond au jeton envoyé dans l'en-tête « Authorization: Bearer <jeton> »
    (ou une erreur 401 si le jeton est absent, faux, ou a plus de 30 jours)."""
    jeton = authorization.removeprefix("Bearer ").strip()
    trouves = lire(f"""SELECT id_utilisateur, nom, email FROM utilisateurs
                       WHERE jeton = :empreinte AND date_jeton > NOW() - INTERVAL '{JOURS_DE_CONNEXION} days'""",
                   empreinte=empreinte_jeton(jeton)) if jeton else []
    if not trouves:
        raise HTTPException(status_code=401, detail="Vous n'êtes pas connecté.")
    return trouves[0]


class NouveauNom(BaseModel):
    """Ce que l'application envoie pour changer le nom du compte."""
    nom: str


@app.get("/comptes/moi")
def mon_compte(authorization: str = Header("")):
    """Lire mon compte. Sert à l'application, au démarrage, pour vérifier que l'utilisateur est toujours connecté."""
    compte = compte_du_jeton(authorization)
    return {"nom": compte["nom"], "email": compte["email"]}


@app.put("/comptes/moi")
def modifier_mon_nom(demande: NouveauNom, authorization: str = Header("")):
    """Modifier le nom de mon compte (il faut être connecté)."""
    compte = compte_du_jeton(authorization)
    nom = demande.nom.strip()
    verifier_longueurs(nom=nom)
    if len(nom) < 2:
        raise HTTPException(status_code=400, detail="Indiquez votre nom.")
    ecrire("UPDATE utilisateurs SET nom = :nom WHERE email = :email", nom=nom, email=compte["email"])
    return {"nom": nom, "email": compte["email"]}


@app.delete("/comptes/moi")
def supprimer_mon_compte(authorization: str = Header("")):
    """Supprimer mon compte pour de bon (il faut être connecté). L'application demande d'abord une confirmation."""
    compte = compte_du_jeton(authorization)
    ecrire("DELETE FROM utilisateurs WHERE email = :email", email=compte["email"])
    return {"message": "Votre compte a été supprimé."}


# ---------------------------------------------------------------
# 10) Historique des recherches (utilisateurs connectés)
# ---------------------------------------------------------------
ecrire("""
    CREATE TABLE IF NOT EXISTS recherches (
        id_recherche    SERIAL PRIMARY KEY,
        id_utilisateur  INTEGER NOT NULL REFERENCES utilisateurs (id_utilisateur) ON DELETE CASCADE,
        commune         TEXT NOT NULL,
        quartier        TEXT,
        heure           INTEGER NOT NULL,
        deplacement     TEXT,
        eclairage       TEXT,
        score           INTEGER NOT NULL,
        niveau          TEXT NOT NULL,
        date_recherche  TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'Africa/Abidjan')
    )
""")


class Recherche(BaseModel):
    """Ce que l'application envoie après un calcul de risque."""
    commune: str = Field(max_length=50)
    quartier: str | None = Field(default=None, max_length=100)
    heure: int = Field(ge=0, le=23)
    deplacement: Literal["", "pied", "moto", "taxi", "voiture", "bus"] = ""
    eclairage: Literal["", "eclairee", "sombre"] = ""
    score: int = Field(ge=0, le=100)
    niveau: Literal["faible", "moyen", "élevé"]


@app.post("/recherches")
def enregistrer_recherche(recherche: Recherche, authorization: str = Header("")):
    """Enregistre un calcul de risque dans l'historique de l'utilisateur connecté."""
    compte = compte_du_jeton(authorization)
    ecrire("""INSERT INTO recherches (id_utilisateur, commune, quartier, heure, deplacement, eclairage, score, niveau)
              VALUES (:id, :commune, :quartier, :heure, :deplacement, :eclairage, :score, :niveau)""",
           id=compte["id_utilisateur"], **recherche.model_dump())
    # Conserver uniquement les 50 dernières recherches de l'utilisateur.
    ecrire("""DELETE FROM recherches WHERE id_utilisateur = :id AND id_recherche NOT IN (
                  SELECT id_recherche FROM recherches WHERE id_utilisateur = :id
                  ORDER BY date_recherche DESC LIMIT 50)""", id=compte["id_utilisateur"])
    return {"message": "Recherche enregistrée."}


@app.get("/recherches")
def mes_recherches(authorization: str = Header("")):
    """Les 50 dernières recherches de l'utilisateur connecté, la plus récente en premier."""
    compte = compte_du_jeton(authorization)
    return lire("""SELECT id_recherche, commune, quartier, heure, deplacement, eclairage, score, niveau,
                          TO_CHAR(date_recherche, 'DD/MM/YYYY à HH24:MI') AS date
                   FROM recherches WHERE id_utilisateur = :id
                   ORDER BY date_recherche DESC LIMIT 50""", id=compte["id_utilisateur"])


@app.delete("/recherches/{id_recherche}")
def effacer_une_recherche(id_recherche: int, authorization: str = Header("")):
    """Efface une recherche (seulement si elle appartient à l'utilisateur connecté)."""
    compte = compte_du_jeton(authorization)
    ecrire("DELETE FROM recherches WHERE id_recherche = :n AND id_utilisateur = :id",
           n=id_recherche, id=compte["id_utilisateur"])
    return {"message": "Recherche effacée."}


@app.delete("/recherches")
def effacer_mes_recherches(authorization: str = Header("")):
    """Efface tout l'historique de l'utilisateur connecté."""
    compte = compte_du_jeton(authorization)
    ecrire("DELETE FROM recherches WHERE id_utilisateur = :id", id=compte["id_utilisateur"])
    return {"message": "Historique effacé."}


@app.post("/comptes/deconnexion")
def deconnexion(demande: Deconnexion):
    """Efface le jeton : il ne pourra plus servir."""
    ecrire("UPDATE utilisateurs SET jeton = NULL WHERE jeton = :empreinte", empreinte=empreinte_jeton(demande.jeton))
    return {"message": "Vous êtes déconnecté."}


# ---------------------------------------------------------------
# 11) Le site web (dossier « web ») est servi par l'API : http://localhost:8000/site/
# ---------------------------------------------------------------
DOSSIER_WEB = DOSSIER_PROJET / "web"
if DOSSIER_WEB.exists():
    app.mount("/site", StaticFiles(directory=DOSSIER_WEB, html=True), name="site")


@app.get("/", include_in_schema=False)
def accueil_vers_site():
    """Ouvrir http://localhost:8000 amène directement sur le site."""
    return RedirectResponse("/site/")


# ---------------------------------------------------------------
# 12) Démarrer le serveur
# ---------------------------------------------------------------
if __name__ == "__main__":
    with socket.socket() as test:
        if test.connect_ex(("127.0.0.1", 8000)) == 0:
            print("L'API tourne déjà dans un autre terminal (le port 8000 est occupé).")
            print("Pour la relancer avec le nouveau code : Ctrl + C dans ce terminal-là, puis relancez la commande.")
            sys.exit(1)
    print("API lancée (Ctrl + C pour arrêter) :")
    print("  site web      : http://localhost:8000/site/")
    print("  documentation : http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
