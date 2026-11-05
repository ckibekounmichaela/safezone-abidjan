import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

# config.py peut être dans le même dossier que ce script, ou dans le dossier au-dessus
DOSSIER_SCRIPT = Path(__file__).resolve().parent
sys.path.append(str(DOSSIER_SCRIPT))
sys.path.append(str(DOSSIER_SCRIPT.parent))
import config  # noqa: E402

# On réutilise les fonctions de tri du script de collecte, pour avoir exactement les mêmes règles.
fichier_collecte = DOSSIER_SCRIPT / "scraping.py"
if not fichier_collecte.exists():
    sys.exit("Script de collecte introuvable : scraping.py doit être dans le même dossier que nettoyage.py")
specification = importlib.util.spec_from_file_location("collecte", fichier_collecte)
collecte = importlib.util.module_from_spec(specification)
specification.loader.exec_module(collecte)

FICHIER_BRUT = config.DOSSIER_DONNEES / "brut" / "articles_bruts.csv"
FICHIER_PROPRE = config.DOSSIER_PROPRE / "articles_propres.csv"
FICHIER_ECARTES = config.DOSSIER_PROPRE / "articles_ecartes.csv"


def prefixe_du_site(adresse: str) -> str:
    """Retrouve le préfixe ('an_', 'ko_', 'fm_'...) à partir du nom du site dans l'adresse."""
    source = collecte.source_d_une_adresse(adresse)
    return source.get("prefixe", "")


def harmoniser_identifiant(ligne: pd.Series) -> str:
    """Ajoute le préfixe du site aux numéros des anciennes collectes ('519115' -> 'an_519115')."""
    identifiant = str(ligne["id_article"])
    if "_" in identifiant:
        return identifiant
    return prefixe_du_site(ligne["adresse"]) + identifiant


def raison_d_ecart(ligne: pd.Series) -> str:
    """Renvoie '' si l'article est gardé, sinon la raison pour laquelle il est écarté."""
    if len(ligne["texte"]) < 40:
        return "texte vide"
    if not collecte.parle_d_agression(ligne["texte"], ligne["titre"]):
        return "pas une agression"
    if not collecte.se_passe_a_abidjan(ligne["titre"] + " " + ligne["texte"]):
        return "hors Abidjan"
    return ""


def nettoyer() -> None:
    # Le fichier brut est cherché dans donnees/brut/ (ou directement dans donnees/)
    fichier_brut = FICHIER_BRUT if FICHIER_BRUT.exists() else config.DOSSIER_DONNEES / "articles_bruts.csv"
    if not fichier_brut.exists():
        sys.exit(f"Fichier introuvable : {FICHIER_BRUT}\nLance d'abord la collecte.")

    articles = pd.read_csv(fichier_brut, dtype=str).fillna("")
    print(f"Fichier lu : {fichier_brut}")
    print(f"Articles dans le fichier brut : {len(articles)}")

    # 1) Numéros au même format
    articles["id_article"] = articles.apply(harmoniser_identifiant, axis=1)

    # 2) Doublons
    avant = len(articles)
    articles = articles.drop_duplicates(subset="adresse")
    articles = articles.drop_duplicates(subset=["titre", "date_publication"])
    articles = articles.drop_duplicates(subset="id_article")
    print(f"Doublons supprimés : {avant - len(articles)}")

    # 3) Filtres : on note la raison d'écart de chaque article
    articles["raison_ecart"] = articles.apply(raison_d_ecart, axis=1)
    gardes = articles[articles["raison_ecart"] == ""].drop(columns="raison_ecart").copy()
    ecartes = articles[articles["raison_ecart"] != ""].copy()

    # 4) Communes recalculées sur le titre et le début du texte (là où elles sont le plus fiables)
    gardes["communes_citees"] = gardes.apply(
        lambda l: collecte.communes_citees((l["titre"] + " " + l["texte"])[:collecte.LONGUEUR_DEBUT]), axis=1)
    gardes = gardes.sort_values("date_publication", ascending=False)

    # 5) Enregistrement des deux fichiers
    config.DOSSIER_PROPRE.mkdir(parents=True, exist_ok=True)
    gardes.to_csv(FICHIER_PROPRE, index=False, encoding="utf-8")
    ecartes[["id_article", "source", "titre", "raison_ecart", "adresse"]].to_csv(
        FICHIER_ECARTES, index=False, encoding="utf-8")

    # 6) Bilan affiché dans le terminal
    print(f"\nArticles écartés : {len(ecartes)}")
    for raison, nombre in ecartes["raison_ecart"].value_counts().items():
        print(f"  - {raison} : {nombre}")
    print(f"\nArticles gardés : {len(gardes)}")

    print("\nPar site :")
    for source, nombre in gardes["source"].value_counts().items():
        print(f"  {source:22} {nombre}")

    print("\nPar année :")
    annees = gardes["date_publication"].str[:4].replace("", "inconnue")
    for annee, nombre in annees.value_counts().sort_index().items():
        print(f"  {annee}  {'#' * min(nombre, 60)} {nombre}")

    print("\nPar commune (un article peut citer plusieurs communes) :")
    # 'Abobo;Cocody' est découpé en 'Abobo' et 'Cocody', puis on compte chaque commune
    communes = Counter(c for liste in gardes["communes_citees"] if liste for c in liste.split(";"))
    sans_commune = (gardes["communes_citees"] == "").sum()
    for commune, nombre in communes.most_common():
        print(f"  {commune:12} {'#' * min(nombre, 60)} {nombre}")
    print(f"  (sans commune précise, seulement « Abidjan » : {sans_commune})")

    print(f"\nFichiers créés :\n  {FICHIER_PROPRE}\n  {FICHIER_ECARTES}")


if __name__ == "__main__":
    nettoyer()
