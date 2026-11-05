import os
from pathlib import Path

import folium
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from dotenv import load_dotenv
from matplotlib.colors import LinearSegmentedColormap
from sqlalchemy import URL, create_engine

matplotlib.use("Agg")

# ---------------------------------------------------------------
# 1) Connexion à la base et dossier des graphiques
# ---------------------------------------------------------------
DOSSIER_PROJET = Path(__file__).resolve().parent.parent
DOSSIER_GRAPHIQUES = DOSSIER_PROJET / "graphiques"
DOSSIER_GRAPHIQUES.mkdir(exist_ok=True)

load_dotenv(DOSSIER_PROJET / ".env")
base = create_engine(URL.create(
    "postgresql+psycopg2", username="postgres", password=os.getenv("PG_MOT_DE_PASSE"),
    host="localhost", port=5432, database="safezone",
))

# ---------------------------------------------------------------
# 2) Lire les agressions (avec le nom de la commune)
# ---------------------------------------------------------------
agressions = pd.read_sql("""
    SELECT a.*, c.nom AS commune, c.latitude, c.longitude
    FROM agressions a
    LEFT JOIN communes c ON c.id_commune = a.id_commune
""", base)
agressions["annee"] = pd.to_datetime(agressions["date_faits"]).dt.year
print(f"Agressions lues : {len(agressions)}")

# ---------------------------------------------------------------
# 3) Style commun à tous les graphiques
# ---------------------------------------------------------------
BLEU = "#2a78d6"
TEXTE = "#52514e"
plt.rcParams.update({
    "font.size": 11, "axes.edgecolor": "#d9d8d4", "axes.labelcolor": TEXTE,
    "xtick.color": TEXTE, "ytick.color": TEXTE, "axes.spines.top": False,
    "axes.spines.right": False, "figure.facecolor": "white",
})


def barres_horizontales(comptage: pd.Series, titre: str, fichier: str) -> None:
    """Barres horizontales triées (la plus grande en haut), avec le nombre au bout."""
    comptage = comptage.sort_values()
    figure, axe = plt.subplots(figsize=(8, 0.45 * len(comptage) + 1.2))
    barres = axe.barh(comptage.index, comptage.values, color=BLEU, height=0.6)
    axe.bar_label(barres, padding=4, color=TEXTE, fontsize=10)
    axe.set_title(titre, loc="left", fontsize=13, color="#0b0b0b")
    axe.xaxis.set_visible(False)
    axe.spines["bottom"].set_visible(False)
    figure.tight_layout()
    figure.savefig(DOSSIER_GRAPHIQUES / fichier, dpi=150)
    plt.close(figure)
    print(f"  créé : {fichier}")


# ---------------------------------------------------------------
# 4) Les graphiques
# ---------------------------------------------------------------
print("Création des graphiques :")

# 4a) Par commune (on met de côté les communes inconnues)
avec_commune = agressions.dropna(subset=["commune"])
barres_horizontales(avec_commune["commune"].value_counts(),
                    "Nombre d'agressions par commune", "1_communes.png")

# 4b) Par année (barres verticales : le temps se lit de gauche à droite)
par_annee = agressions["annee"].value_counts().sort_index()
figure, axe = plt.subplots(figsize=(9, 4))
axe.bar(par_annee.index.astype(str), par_annee.values, color=BLEU, width=0.6)
axe.set_title("Nombre d'agressions par année", loc="left", fontsize=13, color="#0b0b0b")
axe.grid(axis="y", color="#ecebe8")
axe.set_axisbelow(True)
plt.xticks(rotation=45)
figure.tight_layout()
figure.savefig(DOSSIER_GRAPHIQUES / "2_annees.png", dpi=150)
plt.close(figure)
print("  créé : 2_annees.png")

# 4c) Tranches horaires (seulement les agressions où l'heure est connue)
heure_connue = agressions[agressions["tranche_horaire"] != "inconnue"]
ordre = ["matin", "après-midi", "soir", "nuit"]
tranches = heure_connue["tranche_horaire"].value_counts().reindex(ordre, fill_value=0)
barres_horizontales(tranches, f"Quand ont lieu les agressions ? ({len(heure_connue)} cas où l'heure est connue)",
                    "3_tranches.png")

# 4d) Types d'agression et 4e) armes
barres_horizontales(agressions["type_agression"].value_counts(), "Types d'agression", "4_types.png")
armes = agressions[agressions["arme"] != "inconnue"]["arme"].value_counts()
barres_horizontales(armes, "Armes utilisées (quand l'article le précise)", "5_armes.png")

# 4f) Tableau de chaleur commune × année : plus la case est foncée, plus il y a d'agressions
tableau = pd.crosstab(avec_commune["commune"], avec_commune["annee"])
tableau = tableau.loc[tableau.sum(axis=1).sort_values(ascending=False).index]
bleus = LinearSegmentedColormap.from_list("bleus", ["#ffffff", "#cde2fb", "#5598e7", "#1c5cab", "#0d366b"])
figure, axe = plt.subplots(figsize=(12, 6))
image = axe.imshow(tableau.values, cmap=bleus, aspect="auto")
axe.set_xticks(range(len(tableau.columns)), tableau.columns, rotation=45)
axe.set_yticks(range(len(tableau.index)), tableau.index)
for ligne in range(tableau.shape[0]):
    for colonne in range(tableau.shape[1]):
        valeur = tableau.iat[ligne, colonne]
        if valeur > 0:
            couleur = "white" if valeur > tableau.values.max() / 2 else "#0b0b0b"
            axe.text(colonne, ligne, valeur, ha="center", va="center", fontsize=8, color=couleur)
axe.set_title("Agressions par commune et par année", loc="left", fontsize=13, color="#0b0b0b")
figure.colorbar(image, ax=axe, label="nombre d'agressions")
figure.tight_layout()
figure.savefig(DOSSIER_GRAPHIQUES / "6_commune_annee.png", dpi=150)
plt.close(figure)
print("  créé : 6_commune_annee.png")

# 4g) Qualité des données : dans quelle part des agressions le quartier est-il connu ?
#     (la presse ne cite pas toujours le quartier : il faut le mesurer avant d'étudier les quartiers)
agressions["quartier_connu"] = agressions["quartier"].fillna("").str.strip() != ""
quartier_connu = (avec_commune.assign(quartier_connu=agressions["quartier_connu"])
                  .groupby("commune")["quartier_connu"].agg(agressions="size", avec_quartier="sum"))
quartier_connu["pourcentage"] = (100 * quartier_connu["avec_quartier"] / quartier_connu["agressions"]).round()
quartier_connu = quartier_connu.sort_values("agressions", ascending=False)
quartier_connu.to_csv(DOSSIER_GRAPHIQUES / "quartier_connu.csv", encoding="utf-8-sig")
print("  créé : quartier_connu.csv")

ordre_graphique = quartier_connu.sort_values("pourcentage")
figure, axe = plt.subplots(figsize=(8, 0.45 * len(ordre_graphique) + 1.4))
barres = axe.barh(ordre_graphique.index, ordre_graphique["pourcentage"], color=BLEU, height=0.6)
axe.bar_label(barres, padding=4, color=TEXTE, fontsize=10,
              labels=[f"{p:.0f} %  ({q}/{n})" for p, q, n in zip(ordre_graphique["pourcentage"],
                      ordre_graphique["avec_quartier"], ordre_graphique["agressions"])],
              bbox={"facecolor": "white", "edgecolor": "none", "pad": 1})
total_quartier = agressions["quartier_connu"].mean()
moyenne_communes = quartier_connu["avec_quartier"].sum() / quartier_connu["agressions"].sum()
axe.axvline(100 * moyenne_communes, color=TEXTE, linestyle="--", linewidth=1, zorder=0)
axe.text(100 * moyenne_communes, len(ordre_graphique) - 0.4, f" moyenne {moyenne_communes:.0%}",
         color=TEXTE, fontsize=9, va="bottom")
axe.set_xlim(0, 115)
axe.set_title("Part des agressions dont le quartier est connu", loc="left", fontsize=13, color="#0b0b0b")
axe.xaxis.set_visible(False)
axe.spines["bottom"].set_visible(False)
figure.tight_layout()
figure.savefig(DOSSIER_GRAPHIQUES / "10_quartier_connu.png", dpi=150)
plt.close(figure)
print("  créé : 10_quartier_connu.png")

# 4h) Carte : un cercle par commune, plus il est grand, plus il y a d'agressions
par_commune = avec_commune.groupby(["commune", "latitude", "longitude"]).size().reset_index(name="nombre")
carte = folium.Map(location=[5.345, -4.02], zoom_start=11)
for _, c in par_commune.iterrows():
    folium.CircleMarker(
        location=[float(c["latitude"]), float(c["longitude"])],
        radius=5 + c["nombre"] ** 0.5 * 2.5,
        color="#1c5cab", fill=True, fill_color=BLEU, fill_opacity=0.55, weight=2,
        tooltip=f"{c['commune']} : {c['nombre']} agressions",
    ).add_to(carte)
carte.save(DOSSIER_GRAPHIQUES / "carte.html")
print("  créé : carte.html")

# ---------------------------------------------------------------
# 5) Chiffres clés (à recopier dans les slides)
# ---------------------------------------------------------------
trimestres = pd.read_sql("SELECT * FROM vue_agressions_par_trimestre", base)
nb_cases = 13 * agressions["annee"].nunique() * 4
cases_vides = 1 - len(trimestres) / nb_cases

premiere = avec_commune["commune"].value_counts()
lignes = [
    "CHIFFRES CLÉS — SafeZone Abidjan",
    f"Agressions analysées : {len(agressions)} (de {agressions['annee'].min()} à {agressions['annee'].max()})",
    f"Commune connue : {len(avec_commune)} ({len(avec_commune) / len(agressions):.0%})",
    f"Heure connue : {len(heure_connue)} ({len(heure_connue) / len(agressions):.0%})",
    f"Quartier connu : {agressions['quartier_connu'].sum()} ({total_quartier:.0%}) — de "
    f"{quartier_connu['pourcentage'].min():.0f} % à {quartier_connu['pourcentage'].max():.0f} % selon la commune",
    f"Communes les plus touchées : " + ", ".join(f"{n} ({v})" for n, v in premiere.head(3).items()),
    f"Part des agressions la nuit (heure connue) : {tranches['nuit'] / max(len(heure_connue), 1):.0%}",
    f"Type le plus fréquent : {agressions['type_agression'].value_counts().index[0]}",
    f"Arme la plus fréquente : {armes.index[0] if len(armes) else 'inconnue'}",
    "",
    "Pour le modèle (commune × trimestre) :",
    f"  cases possibles : {nb_cases}, cases avec au moins une agression : {len(trimestres)}",
    f"  cases sans aucune agression : {cases_vides:.0%}",
]
(DOSSIER_GRAPHIQUES / "resume.txt").write_text("\n".join(lignes), encoding="utf-8")
print("\n" + "\n".join(lignes))
print(f"\nTout est dans : {DOSSIER_GRAPHIQUES}")
