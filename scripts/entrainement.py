import os
from pathlib import Path

import joblib
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import URL, create_engine
from xgboost import XGBRegressor

matplotlib.use("Agg")

DOSSIER_PROJET = Path(__file__).resolve().parent.parent
DOSSIER_MODELES = DOSSIER_PROJET / "modeles"
DOSSIER_GRAPHIQUES = DOSSIER_PROJET / "graphiques"
DOSSIER_MODELES.mkdir(exist_ok=True)
DOSSIER_GRAPHIQUES.mkdir(exist_ok=True)

ANNEE_DEBUT = 2010
DERNIERE_ANNEE_ENTRAINEMENT = 2024

# ---------------------------------------------------------------
# 1) Lire les agressions dans PostgreSQL
# ---------------------------------------------------------------
load_dotenv(DOSSIER_PROJET / ".env")
base = create_engine(URL.create(
    "postgresql+psycopg2", username="postgres", password=os.getenv("PG_MOT_DE_PASSE"),
    host="localhost", port=5432, database="safezone",
))
agressions = pd.read_sql("""
    SELECT c.nom AS commune, a.date_faits
    FROM agressions a JOIN communes c ON c.id_commune = a.id_commune
""", base)
agressions["date_faits"] = pd.to_datetime(agressions["date_faits"])
agressions = agressions[agressions["date_faits"].dt.year >= ANNEE_DEBUT]
agressions["periode"] = agressions["date_faits"].dt.to_period("Q")
print(f"Agressions utilisées : {len(agressions)}")

# On s'arrête au dernier trimestre TERMINÉ (le trimestre en cours est incomplet)
dernier_trimestre_termine = pd.Timestamp.today().to_period("Q") - 1
agressions = agressions[agressions["periode"] <= dernier_trimestre_termine]

# ---------------------------------------------------------------
# 2) Tableau complet commune × trimestre (0 quand il n'y a rien eu)
# ---------------------------------------------------------------
communes = sorted(pd.read_sql("SELECT nom FROM communes", base)["nom"])
periodes = pd.period_range(f"{ANNEE_DEBUT}Q1", dernier_trimestre_termine, freq="Q")
grille = pd.MultiIndex.from_product([communes, periodes], names=["commune", "periode"])

tableau = (agressions.groupby(["commune", "periode"]).size()
           .reindex(grille, fill_value=0)
           .rename("nombre").reset_index())
print(f"Cases commune × trimestre : {len(tableau)} — vides : {(tableau['nombre'] == 0).mean():.0%}")

# ---------------------------------------------------------------
# 3) Informations pour prédire (seulement le PASSÉ, jamais le trimestre à prédire)
# ---------------------------------------------------------------
tableau = tableau.sort_values(["commune", "periode"])
passe = tableau.groupby("commune")["nombre"]

tableau["trimestre_precedent"] = passe.shift(1)
tableau["il_y_a_2_trimestres"] = passe.shift(2)
tableau["il_y_a_1_an"] = passe.shift(4)
tableau["moyenne_4_derniers"] = passe.transform(lambda s: s.shift(1).rolling(4).mean())
tableau["moyenne_historique"] = passe.transform(lambda s: s.shift(1).expanding().mean())

# Combien d'agressions dans TOUT Abidjan le trimestre d'avant :
# ça mesure aussi combien la presse parlait d'agressions à ce moment-là.
total_abidjan = tableau.groupby("periode")["nombre"].sum().shift(1).rename("total_abidjan_precedent")
tableau = tableau.merge(total_abidjan, on="periode")

tableau["annee"] = tableau["periode"].dt.year
tableau["trimestre"] = tableau["periode"].dt.quarter
tableau["commune_code"] = tableau["commune"].map({nom: i for i, nom in enumerate(communes)})

COLONNES = ["commune_code", "trimestre", "trimestre_precedent", "il_y_a_2_trimestres",
            "il_y_a_1_an", "moyenne_4_derniers", "moyenne_historique", "total_abidjan_precedent"]
tableau = tableau.dropna(subset=COLONNES)

# ---------------------------------------------------------------
# 4) Séparer : entraînement (2010-2024) / test (2025-2026)
# ---------------------------------------------------------------
entrainement = tableau[tableau["annee"] <= DERNIERE_ANNEE_ENTRAINEMENT]
test = tableau[tableau["annee"] > DERNIERE_ANNEE_ENTRAINEMENT]
print(f"Entraînement : {len(entrainement)} cases | Test : {len(test)} cases\n")


# ---------------------------------------------------------------
# 5) Le concours : 3 algorithmes apprennent sur les mêmes exemples
# ---------------------------------------------------------------
def creer_modeles() -> dict:
    """Les 3 candidats. Chacun est « vierge » : il n'a encore rien appris."""
    return {
        # 1) Une seule formule (on met d'abord les colonnes à la même échelle)
        "Régression de Poisson": make_pipeline(StandardScaler(), PoissonRegressor(alpha=0.01, max_iter=1000)),
        # 2) 300 arbres de décision qui votent (on fait la moyenne)
        "Random Forest": RandomForestRegressor(n_estimators=300, max_depth=6, min_samples_leaf=3,
                                               random_state=42),
        # 3) des arbres construits l'un après l'autre, chacun corrige les erreurs du précédent
        "XGBoost": XGBRegressor(objective="count:poisson", n_estimators=300, max_depth=3,
                                learning_rate=0.05, subsample=0.8, random_state=42),
    }


reel = test["nombre"]


def score(nom: str, prediction) -> dict:
    """Les erreurs d'une méthode : MAE = erreur moyenne, RMSE = punit plus les grosses erreurs."""
    return {"méthode": nom,
            "MAE": mean_absolute_error(reel, prediction),
            "RMSE": np.sqrt(mean_squared_error(reel, prediction))}


# La méthode simple sert de référence : un bon modèle doit faire MIEUX qu'elle.
resultats = [score("Méthode simple (moyenne récente)", test["moyenne_4_derniers"])]
predictions = {}
modeles = creer_modeles()
for nom, candidat in modeles.items():
    candidat.fit(entrainement[COLONNES], entrainement["nombre"])
    predictions[nom] = candidat.predict(test[COLONNES])
    resultats.append(score(nom, predictions[nom]))

resultats = pd.DataFrame(resultats)
print("Le concours — erreur sur 2025-2026 (plus c'est petit, mieux c'est) :")
print(resultats.round(3).to_string(index=False))

# Le gagnant = l'algorithme qui a la plus petite erreur moyenne (MAE)
candidats = resultats.iloc[1:]
nom_gagnant = candidats.loc[candidats["MAE"].idxmin(), "méthode"]
modele = modeles[nom_gagnant]
prediction_gagnant = predictions[nom_gagnant]
gain = 1 - candidats["MAE"].min() / resultats.loc[0, "MAE"]
print(f"\nGagnant : {nom_gagnant}. Il se trompe {abs(gain):.0%} "
      f"{'moins' if gain > 0 else 'plus'} que la méthode simple.")

# Graphique du concours (le gagnant en bleu foncé)
ordre = resultats.sort_values("MAE", ascending=False)
couleurs = ["#184f95" if m == nom_gagnant else "#86b6ef" for m in ordre["méthode"]]
figure, axe = plt.subplots(figsize=(9, 3.6))
barres = axe.barh(ordre["méthode"], ordre["MAE"], color=couleurs, height=0.6)
axe.bar_label(barres, fmt="%.2f", padding=4, color="#52514e")
axe.set_title("Erreur moyenne sur 2025-2026 (plus c'est court, mieux c'est)", loc="left", fontsize=13)
axe.xaxis.set_visible(False)
axe.spines[["top", "right", "bottom"]].set_visible(False)
figure.tight_layout()
figure.savefig(DOSSIER_GRAPHIQUES / "9_comparaison.png", dpi=150)
plt.close(figure)

# Le modèle classe-t-il bien les communes ? (sur toute la période de test)
classement = test.assign(prediction=prediction_gagnant).groupby("commune")[["nombre", "prediction"]].sum()
top3_reel = set(classement["nombre"].nlargest(3).index)
top3_predit = set(classement["prediction"].nlargest(3).index)
print(f"Les 3 communes les plus touchées en vrai : {', '.join(sorted(top3_reel))}")
print(f"Les 3 communes prédites les plus à risque : {', '.join(sorted(top3_predit))}")
print(f"Communes en commun : {len(top3_reel & top3_predit)} sur 3")

# Graphique : ce qui compte le plus pour le modèle
if hasattr(modele, "feature_importances_"):
    poids = modele.feature_importances_
else:
    poids = np.abs(modele[-1].coef_)
importance = pd.Series(poids, index=COLONNES).sort_values()
figure, axe = plt.subplots(figsize=(8, 4))
axe.barh(importance.index, importance.values, color="#2a78d6", height=0.6)
axe.set_title(f"Ce qui compte le plus pour le modèle ({nom_gagnant})", loc="left", fontsize=13)
axe.spines[["top", "right"]].set_visible(False)
figure.tight_layout()
figure.savefig(DOSSIER_GRAPHIQUES / "7_importance.png", dpi=150)
plt.close(figure)

# Graphique : réel contre prédit, par commune, sur la période de test
classement = classement.sort_values("nombre")
figure, axe = plt.subplots(figsize=(8, 6))
positions = np.arange(len(classement))
axe.barh(positions + 0.2, classement["nombre"], height=0.4, color="#2a78d6", label="réel")
axe.barh(positions - 0.2, classement["prediction"], height=0.4, color="#eb6834", label="prédit")
axe.set_yticks(positions, classement.index)
axe.set_title("Test 2025-2026 : agressions réelles et prédites par commune", loc="left", fontsize=13)
axe.legend(frameon=False, loc="lower right")
axe.spines[["top", "right"]].set_visible(False)
figure.tight_layout()
figure.savefig(DOSSIER_GRAPHIQUES / "8_reel_predit.png", dpi=150)
plt.close(figure)

# ---------------------------------------------------------------
# 6) Réentraîner le GAGNANT sur TOUT et prédire le prochain trimestre
# ---------------------------------------------------------------
modele_final = creer_modeles()[nom_gagnant]
modele_final.fit(tableau[COLONNES], tableau["nombre"])

prochain = dernier_trimestre_termine + 1
complet = (agressions.groupby(["commune", "periode"]).size()
           .reindex(grille, fill_value=0).unstack("commune"))
lignes = []
for nom in communes:
    serie = complet[nom]
    lignes.append({
        "commune": nom,
        "commune_code": communes.index(nom),
        "trimestre": prochain.quarter,
        "trimestre_precedent": serie.iloc[-1],
        "il_y_a_2_trimestres": serie.iloc[-2],
        "il_y_a_1_an": serie.iloc[-4],
        "moyenne_4_derniers": serie.iloc[-4:].mean(),
        "moyenne_historique": serie.mean(),
        "total_abidjan_precedent": complet.iloc[-1].sum(),
    })
futur = pd.DataFrame(lignes)
futur["agressions_prevues"] = modele_final.predict(futur[COLONNES]).round(2)

# Niveau de risque : on compare chaque commune à la moyenne d'Abidjan
#   élevé  = plus de 1,5 fois la moyenne
#   faible = moins de la moitié de la moyenne
#   moyen  = entre les deux
moyenne = futur["agressions_prevues"].mean()
futur["niveau_risque"] = np.select(
    [futur["agressions_prevues"] > 1.5 * moyenne, futur["agressions_prevues"] < 0.5 * moyenne],
    ["élevé", "faible"], default="moyen")
futur["periode"] = str(prochain)
futur = futur.sort_values("agressions_prevues", ascending=False)

print(f"\nPrévisions pour {prochain} :")
print(futur[["commune", "agressions_prevues", "niveau_risque"]].to_string(index=False))

# ---------------------------------------------------------------
# 7) Enregistrer
# ---------------------------------------------------------------
joblib.dump({"modele": modele_final, "nom": nom_gagnant, "colonnes": COLONNES, "communes": communes},
            DOSSIER_MODELES / "modele_risque.joblib")
futur[["commune", "periode", "agressions_prevues", "niveau_risque"]].to_csv(
    DOSSIER_MODELES / "predictions.csv", index=False, encoding="utf-8")
futur[["commune", "periode", "agressions_prevues", "niveau_risque"]].to_sql(
    "predictions", base, if_exists="replace", index=False)
resultats.to_csv(DOSSIER_MODELES / "evaluation.csv", index=False, encoding="utf-8")

print(f"\nEnregistré : modeles/modele_risque.joblib, modeles/predictions.csv, "
      f"table « predictions » dans PostgreSQL, graphiques 7, 8 et 9.")
