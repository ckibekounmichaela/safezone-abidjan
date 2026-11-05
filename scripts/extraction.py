import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

DOSSIER_SCRIPT = Path(__file__).resolve().parent
sys.path.append(str(DOSSIER_SCRIPT))
sys.path.append(str(DOSSIER_SCRIPT.parent))
import config  # noqa: E402

FICHIER_PROPRE = config.DOSSIER_PROPRE / "articles_propres.csv"
FICHIER_EXTRAIT = config.DOSSIER_PROPRE / "articles_extraits.csv"
FICHIER_ECHANTILLON = config.DOSSIER_PROPRE / "echantillon_a_verifier.csv"

LONGUEUR_TEXTE = 3000
PAUSE_SECONDES = 1
ESSAIS_MAXIMUM = 4

COLONNES_FICHE = [
    "est_agression", "type_agression", "arme", "commune", "quartier",
    "date_faits", "heure", "tranche_horaire", "nombre_victimes", "deplacement", "eclairage", "resume",
]

# Les consignes envoyées à l'IA avec chaque article (les {...} sont remplacés par les listes de config.py)
CONSIGNES = f"""Tu es un assistant qui analyse des faits divers de la presse ivoirienne.
On te donne un article. Tu réponds UNIQUEMENT avec un objet JSON, sans texte autour.

Champs à remplir :
- "est_agression" : true si l'article raconte une agression précise (une personne attaquée,
  volée avec violence, blessée, tuée, violée, enlevée...) survenue dans le District d'Abidjan.
  false si c'est un accident, un débat, une statistique, une déclaration, un procès sans récit
  d'agression, ou si cela se passe hors du District d'Abidjan.
- "type_agression" : un seul choix parmi {config.TYPES_AGRESSION}
- "arme" : un seul choix parmi {config.ARMES}
- "commune" : une seule commune parmi {list(config.COMMUNES)} ou "inconnue".
  Si seul un quartier est cité, déduis la commune (ex. Angré, Riviera -> Cocody ;
  Selmer, Niangon -> Yopougon ; PK18 -> Abobo ; Vridi -> Port-Bouët).
- "quartier" : le quartier cité (ex. "Riviera 2", "Abobo-Gare"), sinon "".
- "date_faits" : date de l'agression au format AAAA-MM-JJ si on peut la connaître
  (aide-toi de la date de publication pour « hier », « samedi dernier »...), sinon "".
- "heure" : heure de l'agression au format HH:MM si elle est donnée, sinon "".
- "tranche_horaire" : un seul choix parmi {config.TRANCHES_HORAIRES}
  (matin 6h-12h, après-midi 12h-18h, soir 18h-22h, nuit 22h-6h).
- "nombre_victimes" : nombre entier (0 si inconnu).
- "deplacement" : comment se déplaçait la VICTIME, un seul choix parmi {config.DEPLACEMENTS}.
  « sur place » = elle ne se déplaçait pas (chez elle, dans son commerce, à son travail...).
  « moto » : conducteur ou passager (y compris moto-taxi). « inconnu » si l'article ne le dit pas.
- "eclairage" : le lieu était-il éclairé ? un seul choix parmi {config.ECLAIRAGES}.
  « sombre » seulement si l'article parle d'obscurité, de rue non éclairée, de coupure de courant ;
  « éclairé » seulement si l'article le dit ; sinon « inconnu ».
- "resume" : une phrase de 25 mots maximum.

Si "est_agression" est false, remplis quand même les autres champs du mieux possible."""


# ---------------------------------------------------------------
# 1) Connexion à l'IA
# ---------------------------------------------------------------
def connecter_ia() -> tuple[OpenAI, str]:
    """Lit la clé dans le fichier .env et prépare la connexion à l'IA choisie dans config.py."""
    load_dotenv(config.DOSSIER_PROJET / ".env")
    reglages = config.FOURNISSEURS_IA.get(config.FOURNISSEUR_IA)
    if reglages is None:
        sys.exit(f"FOURNISSEUR_IA inconnu dans config.py : {config.FOURNISSEUR_IA}")
    cle = os.getenv(reglages["nom_cle"])
    if not cle:
        sys.exit(f"Clé introuvable. Crée le fichier {config.DOSSIER_PROJET / '.env'} avec la ligne :\n"
                 f"  {reglages['nom_cle']}=ta_cle")
    client = OpenAI(api_key=cle, base_url=reglages["adresse"])
    return client, reglages["modele"]


def demander_fiche(client: OpenAI, modele: str, article: pd.Series) -> dict:
    """Envoie un article à l'IA et renvoie sa réponse sous forme de dictionnaire ({} en cas d'échec)."""
    message = (f"Date de publication : {article['date_publication'] or 'inconnue'}\n"
               f"Titre : {article['titre']}\n\n"
               f"Texte :\n{article['texte'][:LONGUEUR_TEXTE]}")
    for essai in range(1, ESSAIS_MAXIMUM + 1):
        try:
            reponse = client.chat.completions.create(
                model=modele,
                messages=[{"role": "system", "content": CONSIGNES},
                          {"role": "user", "content": message}],
                response_format={"type": "json_object"},
                temperature=0,
            )
            return json.loads(reponse.choices[0].message.content)
        except json.JSONDecodeError:
            print(f"    réponse illisible (essai {essai})")
        except Exception as erreur:
            attente = 10 * essai
            print(f"    erreur : {str(erreur)[:120]} — nouvel essai dans {attente} s")
            if "401" in str(erreur) or "402" in str(erreur):
                sys.exit("Clé refusée ou compte sans crédit : vérifie ta clé et ton solde.")
            time.sleep(attente)
    return {}


# ---------------------------------------------------------------
# 2) Vérification de la réponse de l'IA
# ---------------------------------------------------------------
def choisir(valeur, autorises: list, defaut: str) -> str:
    """Garde la valeur si elle fait partie des choix autorisés (sans tenir compte des majuscules),
    sinon renvoie la valeur par défaut. Exemple : choisir('Braquage', [...], 'autre') -> 'braquage'."""
    valeur = str(valeur or "").strip().lower()
    for choix in autorises:
        if valeur == choix.lower():
            return choix
    return defaut


def verifier_fiche(fiche: dict) -> dict:
    """Corrige ou vide les champs mal remplis par l'IA (on ne lui fait jamais confiance à 100 %)."""
    resultat = {}
    # Oui / non : on accepte true, 1 ou oui
    resultat["est_agression"] = str(fiche.get("est_agression", "")).lower() in ("true", "1", "oui")
    # Choix dans une liste fermée (sinon valeur par défaut)
    resultat["type_agression"] = choisir(fiche.get("type_agression"), config.TYPES_AGRESSION, "autre")
    resultat["arme"] = choisir(fiche.get("arme"), config.ARMES, "inconnue")
    resultat["commune"] = choisir(fiche.get("commune"), list(config.COMMUNES), "inconnue")
    resultat["quartier"] = str(fiche.get("quartier") or "").strip()

    # Date : on la garde seulement si elle a la forme AAAA-MM-JJ
    date_faits = str(fiche.get("date_faits") or "").strip()
    resultat["date_faits"] = date_faits if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_faits) else ""

    # Heure : '22h', '22:30' ou '7' deviennent '22:00', '22:30', '07:00'
    heure = str(fiche.get("heure") or "").strip().replace("h", ":")
    morceaux = re.fullmatch(r"(\d{1,2}):?(\d{2})?", heure)
    if morceaux and int(morceaux.group(1)) < 24:
        resultat["heure"] = f"{int(morceaux.group(1)):02d}:{morceaux.group(2) or '00'}"
    else:
        resultat["heure"] = ""

    tranche = choisir(fiche.get("tranche_horaire"), config.TRANCHES_HORAIRES, "inconnue")
    if resultat["heure"]:
        h = int(resultat["heure"][:2])
        # matin 6-12 h, après-midi 12-18 h, soir 18-22 h, sinon nuit
        tranche = "matin" if 6 <= h < 12 else "après-midi" if 12 <= h < 18 else "soir" if 18 <= h < 22 else "nuit"
    resultat["tranche_horaire"] = tranche

    try:
        resultat["nombre_victimes"] = max(0, int(fiche.get("nombre_victimes") or 0))
    except (TypeError, ValueError):
        resultat["nombre_victimes"] = 0
    # Déplacement de la victime et éclairage du lieu (choix dans une liste fermée, sinon « inconnu »)
    resultat["deplacement"] = choisir(fiche.get("deplacement"), config.DEPLACEMENTS, "inconnu")
    resultat["eclairage"] = choisir(fiche.get("eclairage"), config.ECLAIRAGES, "inconnu")
    resultat["resume"] = str(fiche.get("resume") or "").strip()
    return resultat


# ---------------------------------------------------------------
# 3) Programme principal
# ---------------------------------------------------------------
def deja_traites() -> set:
    """Les numéros des articles déjà lus par l'IA (pour ne pas payer deux fois)."""
    if FICHIER_EXTRAIT.exists():
        return set(pd.read_csv(FICHIER_EXTRAIT, dtype=str)["id_article"])
    return set()


def retirer_fiches_en_trop(ids_gardes: set) -> None:
    """Supprime les fiches des articles que le nettoyage a retirés depuis
    (par exemple « la dépouille de... » qui n'est pas une agression)."""
    if not FICHIER_EXTRAIT.exists():
        return
    fiches = pd.read_csv(FICHIER_EXTRAIT, dtype=str).fillna("")
    en_trop = ~fiches["id_article"].isin(ids_gardes)
    if en_trop.any():
        fiches[~en_trop].to_csv(FICHIER_EXTRAIT, index=False, encoding="utf-8")
        print(f"{en_trop.sum()} fiches retirées (articles écartés par le nettoyage)")


def enregistrer(ligne: dict) -> None:
    """Ajoute une fiche à la fin du fichier (on ne perd rien si le script s'arrête)."""
    tableau = pd.DataFrame([ligne])
    tableau.to_csv(FICHIER_EXTRAIT, mode="a", header=not FICHIER_EXTRAIT.exists(),
                   index=False, encoding="utf-8")


def extraire(limite: int | None) -> None:
    """Fait lire par l'IA tous les articles pas encore traités (ou seulement « limite » articles)."""
    if not FICHIER_PROPRE.exists():
        sys.exit(f"Fichier introuvable : {FICHIER_PROPRE}\nLance d'abord nettoyage.py.")
    articles = pd.read_csv(FICHIER_PROPRE, dtype=str).fillna("")
    retirer_fiches_en_trop(set(articles["id_article"]))
    vus = deja_traites()
    a_faire = articles[~articles["id_article"].isin(vus)]
    if limite:
        a_faire = a_faire.head(limite)

    client, modele = connecter_ia()
    print(f"IA utilisée : {config.FOURNISSEUR_IA} ({modele})")
    print(f"Articles : {len(articles)} au total, {len(vus)} déjà traités, {len(a_faire)} à traiter\n")

    for numero, (_, article) in enumerate(a_faire.iterrows(), start=1):
        print(f"[{numero}/{len(a_faire)}] {article['titre'][:80]}")
        fiche = demander_fiche(client, modele, article)
        if not fiche:
            print("    abandonné (pas de réponse), il sera retenté au prochain lancement")
            continue
        fiche = verifier_fiche(fiche)
        print(f"    -> {'AGRESSION' if fiche['est_agression'] else 'pas une agression'} | "
              f"{fiche['type_agression']} | {fiche['commune']} {fiche['quartier']} | {fiche['tranche_horaire']}")
        enregistrer({
            "id_article": article["id_article"], "source": article["source"],
            "titre": article["titre"], "date_publication": article["date_publication"],
            "adresse": article["adresse"], **fiche,
        })
        time.sleep(PAUSE_SECONDES)

    afficher_bilan()


def afficher_bilan() -> None:
    """Combien d'agressions confirmées, et leur répartition par type, commune, moment et arme."""
    if not FICHIER_EXTRAIT.exists():
        return
    fiches = pd.read_csv(FICHIER_EXTRAIT, dtype=str).fillna("")
    agressions = fiches[fiches["est_agression"] == "True"]
    print(f"\n===== BILAN =====\nFiches : {len(fiches)} — agressions confirmées : {len(agressions)}")
    for colonne in ("type_agression", "commune", "tranche_horaire", "arme", "deplacement", "eclairage"):
        if colonne not in agressions:
            continue
        print(f"\nPar {colonne.replace('_', ' ')} :")
        for valeur, nombre in Counter(agressions[colonne]).most_common():
            print(f"  {valeur:28} {'#' * min(nombre, 50)} {nombre}")
    print(f"\nFichier : {FICHIER_EXTRAIT}")


def creer_echantillon(taille: int = 50) -> None:
    """Tire 50 fiches au hasard pour les vérifier à la main (contrôle qualité pour le jury)."""
    if not FICHIER_EXTRAIT.exists():
        sys.exit("Lance d'abord l'extraction.")
    fiches = pd.read_csv(FICHIER_EXTRAIT, dtype=str).fillna("")
    echantillon = fiches.sample(min(taille, len(fiches)), random_state=42)
    for colonne in ("agression_correcte", "commune_correcte", "tranche_correcte"):
        echantillon[colonne] = ""
    echantillon.to_csv(FICHIER_ECHANTILLON, index=False, encoding="utf-8-sig")
    print(f"Échantillon créé : {FICHIER_ECHANTILLON}\n"
          "Ouvre-le dans Excel, lis chaque article (colonne adresse) et écris oui/non dans les 3 dernières colonnes.")


if __name__ == "__main__":
    # Les options possibles après le nom du script
    parametres = argparse.ArgumentParser(description="Lecture des articles par l'IA")
    parametres.add_argument("--limite", type=int, help="nombre d'articles à traiter (pour tester)")
    parametres.add_argument("--echantillon", action="store_true", help="créer le fichier de vérification")
    parametres.add_argument("--bilan", action="store_true", help="afficher seulement le bilan")
    options = parametres.parse_args()
    if options.echantillon:
        creer_echantillon()
    elif options.bilan:
        afficher_bilan()
    else:
        extraire(options.limite)
