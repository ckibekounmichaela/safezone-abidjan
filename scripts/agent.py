import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI

DOSSIER_SCRIPT = Path(__file__).resolve().parent
sys.path.append(str(DOSSIER_SCRIPT))
sys.path.append(str(DOSSIER_SCRIPT.parent))
import api  # noqa: E402
import config  # noqa: E402

load_dotenv(config.DOSSIER_PROJET / ".env")


# ---------------------------------------------------------------
# 1) Les outils de l'agent
#    Le texte entre """ """ est TRÈS important : c'est ce que l'IA lit
#    pour savoir à quoi sert l'outil et quand l'utiliser.
# ---------------------------------------------------------------
def sans_erreur(fonction, **parametres):
    """Appelle une fonction de l'API. Si elle renvoie une erreur (lieu inconnu...),
    on donne le message à l'IA au lieu de faire planter le programme."""
    try:
        return fonction(**parametres)
    except HTTPException as erreur:
        return {"erreur": erreur.detail}


@tool
def risque_d_un_lieu(lieu: str, heure: int, commune: str = "", deplacement: str = "", eclairage: str = "") -> dict:
    """Score de risque d'agression (0 à 100) d'un lieu d'Abidjan à une heure précise (0 à 23).
    Le lieu peut être une commune (Cocody, Yopougon...) ou un quartier (Angré, Selmer, Niangon, PK18...).
    Indiquer la commune seulement si on la connaît (utile si le quartier existe dans plusieurs communes).
    deplacement (si la personne le dit) : "pied", "moto", "taxi" (taxi, woro-woro, gbaka), "voiture" ou "bus".
    eclairage (si la personne le dit) : "eclairee" ou "sombre".
    Pour un TRAJET, appeler cet outil deux fois : une fois pour le départ, une fois pour l'arrivée."""
    return sans_erreur(api.risque_d_un_lieu, lieu=lieu, heure=heure, commune=commune or None,
                       deplacement=deplacement, eclairage=eclairage)


@tool
def meilleur_moment(lieu: str, commune: str = "") -> dict:
    """Le risque d'un lieu (commune ou quartier) aux 4 moments de la journée : matin, après-midi,
    soir et nuit. Sert à conseiller le moment le plus calme pour y aller, et celui à éviter."""
    return sans_erreur(api.risque_sur_la_journee, lieu=lieu, commune=commune or None)


@tool
def faits_du_quartier(quartier: str, commune: str = "") -> dict:
    """Ce qui s'est passé concrètement dans un quartier : nombre d'agressions rapportées,
    types d'agression les plus fréquents, armes utilisées, moments de la journée,
    et les derniers faits divers (date, titre, lien vers l'article).
    Sert à donner des conseils adaptés (ex. surtout des vols de téléphone -> cacher son téléphone)."""
    return sans_erreur(api.faits_du_quartier, quartier=quartier, commune=commune or None)


@tool
def quartiers_les_plus_calmes(commune: str, heure: int) -> dict:
    """Les quartiers d'une commune classés du plus calme au plus risqué, à une heure précise (0 à 23).
    Sert à proposer une autre destination ou un autre point de rendez-vous plus sûr."""
    return sans_erreur(api.classement_des_quartiers, commune=commune, heure=heure)


@tool
def evolution_par_annee(commune: str) -> dict:
    """Le nombre d'agressions rapportées par la presse dans une commune, année par année.
    Sert à répondre à « est-ce que ça devient plus dangereux ? »."""
    fiche = sans_erreur(api.fiche_commune, nom=commune)
    if "erreur" in fiche:
        return fiche
    return {"commune": fiche["commune"], "par_annee": fiche["par_annee"]}


@tool
def fiche_d_une_commune(commune: str) -> dict:
    """Tout sur une commune : prévision du modèle pour le trimestre, nombre total d'agressions,
    types d'agression, moments de la journée, quartiers les plus cités et derniers faits."""
    return sans_erreur(api.fiche_commune, nom=commune)


@tool
def classement_des_communes() -> list:
    """Classe les 13 communes d'Abidjan de la plus risquée à la moins risquée,
    selon la prévision du modèle de machine learning pour le trimestre."""
    return api.liste_des_communes()


@tool
def dernieres_agressions(commune: str = "", nombre: int = 5) -> list:
    """Les agressions les plus récentes rapportées par la presse (date, lieu, type, titre,
    lien vers l'article). Laisser commune vide pour tout Abidjan."""
    return sans_erreur(api.dernieres_agressions, commune=commune or None, limite=min(nombre, 20))


@tool
def statistiques_generales() -> dict:
    """Chiffres globaux sur les agressions à Abidjan : total, période couverte, répartition
    par commune, par moment de la journée, par type d'agression et par arme."""
    return api.statistiques()


# La liste des outils donnés à l'agent
OUTILS = [risque_d_un_lieu, meilleur_moment, faits_du_quartier, quartiers_les_plus_calmes,
          evolution_par_annee, fiche_d_une_commune, classement_des_communes,
          dernieres_agressions, statistiques_generales]


# ---------------------------------------------------------------
# 2) Les consignes données à l'IA (son « rôle »)
# ---------------------------------------------------------------
CONSIGNES = """Tu es l'assistant de SafeZone Abidjan. Tu aides les habitants d'Abidjan à se
déplacer plus prudemment, selon le lieu (commune ou quartier) et l'heure.

L'application affiche déjà le score et le niveau de risque. Toi, tu dois apporter PLUS :
1. Le meilleur moment : utilise meilleur_moment pour dire quand y aller et quand éviter.
2. Ce qui se passe concrètement : pour un QUARTIER, utilise faits_du_quartier ; pour une
   COMMUNE, utilise fiche_d_une_commune. Cite le type d'agression le plus fréquent, l'arme la
   plus utilisée et un fait récent (avec sa date). Donne un conseil adapté à ce type d'agression.
3. Un trajet (« de Yopougon au Plateau ») : utilise risque_d_un_lieu pour le départ ET pour
   l'arrivée, donne les DEUX scores, et dis à quel endroit être le plus prudent.
4. Une alternative : si le risque est élevé, utilise quartiers_les_plus_calmes pour proposer
   un quartier plus calme de la même commune (pour un rendez-vous, par exemple).
5. La tendance : si on te demande si ça s'aggrave, utilise evolution_par_annee. Précise que
   plus d'articles ne veut pas forcément dire plus d'agressions (la presse n'en parle pas toujours).

Règles :
- Utilise TOUJOURS tes outils pour les chiffres. N'invente jamais un chiffre ni un fait.
- Si la personne dit comment elle se déplace (à pied, moto, taxi, woro-woro, voiture, bus) ou si la rue
  est sombre, donne-le à risque_d_un_lieu (deplacement, eclairage) et reprends la phrase « À savoir » qui en parle.
- Heures : « ce soir » = 20, « cette nuit » = 23, « maintenant » = l'heure actuelle donnée dans le message.
- Ne te contente pas de répéter le score : donne au moins une information en plus (moment, faits, alternative).
- Réponds en français simple, en phrases courtes : 3 petits paragraphes au maximum (150 mots environ).
- Écris du texte simple, sans mise en forme : pas d'astérisques, pas de titres, pas de tableaux.
- Rappelle quand c'est utile que les données viennent des faits divers de la presse :
  c'est une estimation, pas une certitude.
- Si la question n'a rien à voir avec la sécurité à Abidjan, dis poliment que tu ne peux
  répondre qu'à ce sujet.
- En cas de danger immédiat, rappelle les numéros d'urgence : Police secours 110 ou 111,
  Sapeurs-pompiers 180."""


# ---------------------------------------------------------------
# 3) Création de l'agent : le cerveau (DeepSeek ou Groq) + les outils + les consignes
# ---------------------------------------------------------------
reglages = config.FOURNISSEURS_IA[config.FOURNISSEUR_IA]
cerveau = ChatOpenAI(
    model=reglages["modele"],
    base_url=reglages["adresse"],
    api_key=os.getenv(reglages["nom_cle"]),
    temperature=0.2,
    max_tokens=600,
    timeout=60,
)
agent = create_agent(cerveau, tools=OUTILS, system_prompt=CONSIGNES)


def demander(question: str, historique: list[dict] | None = None) -> dict:
    """Pose une question à l'agent.
    historique : les messages précédents [{"role": "user"/"assistant", "contenu": "..."}]
    Renvoie la réponse et la liste des outils utilisés (utile pour montrer au jury)."""
    maintenant = datetime.now(timezone(timedelta(hours=0)))

    # 1) On remet la conversation dans le format attendu par LangChain
    messages = [{"role": m["role"], "content": m["contenu"]} for m in (historique or [])]
    # 2) On ajoute la nouvelle question, avec la date et l'heure (pour « maintenant », « ce soir »...)
    messages.append({"role": "user", "content":
                     f"(Date et heure actuelles à Abidjan : {maintenant:%d/%m/%Y %H:%M})\n{question}"})

    # 3) L'agent réfléchit, utilise ses outils et répond
    resultat = agent.invoke({"messages": messages})

    # 4) On note les outils qu'il a utilisés
    outils_utilises = []
    for message in resultat["messages"]:
        for appel in getattr(message, "tool_calls", None) or []:
            outils_utilises.append(appel["name"])
    consultees = list(dict.fromkeys(NOMS_LISIBLES.get(nom, nom) for nom in outils_utilises))
    return {"reponse": resultat["messages"][-1].content,
            "outils_utilises": outils_utilises,
            "donnees_consultees": consultees}


NOMS_LISIBLES = {
    "risque_d_un_lieu": "risque du lieu",
    "meilleur_moment": "meilleur moment",
    "faits_du_quartier": "faits du quartier",
    "quartiers_les_plus_calmes": "quartiers plus calmes",
    "evolution_par_annee": "évolution par année",
    "fiche_d_une_commune": "fiche de la commune",
    "classement_des_communes": "classement des communes",
    "dernieres_agressions": "dernières agressions",
    "statistiques_generales": "statistiques",
}


# ---------------------------------------------------------------
# 4) Discuter avec l'agent dans le terminal
# ---------------------------------------------------------------
if __name__ == "__main__":
    print("Assistant SafeZone Abidjan — pose ta question (tape « quitter » pour arrêter)\n")
    historique = []
    while True:
        question = input("Toi : ").strip()
        if question.lower() in ("quitter", "exit", "q"):
            break
        if not question:
            continue
        resultat = demander(question, historique)
        print(f"\n[outils utilisés : {', '.join(resultat['outils_utilises']) or 'aucun'}]")
        print(f"Assistant : {resultat['reponse']}\n")
        historique += [{"role": "user", "contenu": question},
                       {"role": "assistant", "contenu": resultat["reponse"]}]
