import argparse
import re
import sys
import time
import unicodedata
import urllib.robotparser
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

# config.py peut être dans le même dossier que ce script, ou dans le dossier au-dessus
DOSSIER_SCRIPT = Path(__file__).resolve().parent
sys.path.append(str(DOSSIER_SCRIPT))
sys.path.append(str(DOSSIER_SCRIPT.parent))
import config  # noqa: E402

COLONNES = [
    "id_article", "source", "adresse", "titre", "date_publication", "journal",
    "texte", "communes_citees", "date_collecte",
]


# ---------------------------------------------------------------
# 1) Outils
# ---------------------------------------------------------------
session = requests.Session()
session.headers.update({"User-Agent": config.IDENTITE_NAVIGATEUR})

_cache_robots = {}


def autorise_par_robots(adresse: str) -> bool:
    """Vérifie dans le fichier robots.txt du site qu'on a le droit de lire cette page."""
    morceaux = urlparse(adresse)
    site = f"{morceaux.scheme}://{morceaux.netloc}"
    if site not in _cache_robots:
        lecteur_robots = urllib.robotparser.RobotFileParser()
        lecteur_robots.set_url(site + "/robots.txt")
        try:
            lecteur_robots.read()
        except Exception:
            lecteur_robots = None
        _cache_robots[site] = lecteur_robots
    lecteur_robots = _cache_robots[site]
    if lecteur_robots is None:
        return True
    return lecteur_robots.can_fetch(config.IDENTITE_NAVIGATEUR, adresse)


def telecharger(adresse: str) -> BeautifulSoup | None:
    """Télécharge une page et la transforme en objet BeautifulSoup. Renvoie None en cas d'échec."""
    if not autorise_par_robots(adresse):
        print(f"  [refusé par robots.txt] {adresse}")
        return None
    try:
        reponse = session.get(adresse, timeout=20)
        reponse.raise_for_status()
    except requests.RequestException as erreur:
        print(f"  [erreur] {adresse} : {erreur}")
        return None
    finally:
        time.sleep(config.PAUSE_SECONDES)
    return BeautifulSoup(reponse.text, "html.parser")


def simplifier(texte: str) -> str:
    """Met en minuscules, enlève les accents et remplace les tirets par des espaces.
    Exemple : 'Insécurité à Port-Bouët' -> ' insecurite a port bouet '."""
    texte = unicodedata.normalize("NFD", texte.lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return " " + texte.replace("-", " ").replace("’", "'") + " "


LONGUEUR_DEBUT = 800


def parle_d_agression(texte: str, titre: str = "") -> bool:
    """Vrai si l'article raconte une agression. La décision se fait sur le TITRE,
    car le texte d'un article politique contient souvent « violence » ou « insécurité ».
    - un mot fort dans le titre (braquage, machette, viol...) suffit ;
    - un mot faible (tué, blessé, suspect...) compte si le titre ne parle pas
      d'accident, d'incendie, d'élection, de procès... ;
    - les brèves internationales de l'AIP (« /Inter/ ») sont écartées.
    Si le titre est vide, on regarde le début du texte."""
    titre_simple = simplifier(titre or texte[:150])
    if "/inter" in titre_simple.replace(" ", ""):
        return False
    if any(mot in titre_simple for mot in config.MOTS_FORTS):
        return True
    if any(mot in titre_simple for mot in config.MOTS_EXCLUSION):
        return False
    return any(mot in titre_simple for mot in config.MOTS_FAIBLES)


def communes_citees(texte: str) -> str:
    """Renvoie les communes d'Abidjan citées dans le texte, séparées par ';' (ex. 'Abobo;Cocody')."""
    texte = simplifier(texte)
    trouvees = [nom for nom, variantes in config.COMMUNES.items()
                if any(simplifier(variante).strip() in texte for variante in variantes)]
    return ";".join(trouvees)


def se_passe_a_abidjan(texte: str) -> bool:
    """Vrai si le titre ou le début de l'article cite Abidjan ou une de ses communes."""
    debut = texte[:LONGUEUR_DEBUT]
    return config.MOT_ABIDJAN in simplifier(debut) or communes_citees(debut) != ""


def date_valide(annee, mois, jour) -> str | None:
    """'2026', '04', '15' -> '2026-04-15', ou None si la date n'existe pas (ex. 31 février)."""
    try:
        return date(int(annee), int(mois), int(jour)).isoformat()
    except (ValueError, TypeError):
        return None


def lire_date(page_html: BeautifulSoup, adresse: str = "") -> str | None:
    """Cherche la date de publication, de la méthode la plus fiable à la moins fiable.
    Renvoie une date au format AAAA-MM-JJ, ou None."""
    # 1) Balises prévues pour ça (presque tous les sites récents)
    for attributs in ({"property": "article:published_time"}, {"itemprop": "datePublished"},
                      {"name": "date"}, {"name": "pubdate"}):
        meta = page_html.find("meta", attrs=attributs)
        if meta and meta.get("content"):
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", meta["content"])
            if m and date_valide(*m.groups()):
                return date_valide(*m.groups())
    balise_time = page_html.find("time", attrs={"datetime": True})
    if balise_time:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", balise_time["datetime"])
        if m and date_valide(*m.groups()):
            return date_valide(*m.groups())
    for script in page_html.find_all("script", type="application/ld+json"):
        m = re.search(r'"datePublished"\s*:\s*"(\d{4})-(\d{2})-(\d{2})', script.string or "")
        if m and date_valide(*m.groups()):
            return date_valide(*m.groups())

    texte = page_html.get_text(" ", strip=True)
    # 2) Abidjan.net : "Publié le samedi 29 mars 2014" — Koaci : "Koaci.com - lundi 15 avril 2026"
    m = re.search(r"(?:Publié le|Koaci\.com\s*-)\s+\w+\s+(\d{1,2})\s+([a-zéû]+)\s+(\d{4})", texte, re.IGNORECASE)
    if m and config.MOIS.get(m.group(2).lower()):
        return date_valide(m.group(3), config.MOIS[m.group(2).lower()], m.group(1))
    # 3) Date écrite dans l'adresse : /2026/04/15/
    m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", adresse)
    if m and date_valide(*m.groups()):
        return date_valide(*m.groups())
    # 4) Fraternité Matin : "27/12/19" ou "27/12/2019" près du début de la page
    m = re.search(r"\b(\d{2})/(\d{2})/(\d{2}|\d{4})\b", texte[:3000])
    if m:
        jour, mois, annee = m.groups()
        annee = int(annee) + 2000 if len(annee) == 2 else int(annee)
        return date_valide(annee, mois, jour)
    return None


# ---------------------------------------------------------------
# 2) Lecture d'une page de liste et d'un article
# ---------------------------------------------------------------
def liens_articles(page_html: BeautifulSoup, source: dict, adresse_page: str) -> list[tuple[str, str]]:
    """Renvoie la liste (identifiant, adresse) des articles trouvés sur une page de liste."""
    motif = re.compile(source["motif_article"])
    deja_trouves, resultat = set(), []
    for lien in page_html.find_all("a", href=True):
        adresse = urljoin(adresse_page, lien["href"]).split("?")[0].split("#")[0]
        correspondance = motif.fullmatch(adresse)
        if correspondance:
            identifiant = source.get("prefixe", "") + correspondance.group(1)
            if identifiant not in deja_trouves:
                deja_trouves.add(identifiant)
                resultat.append((identifiant, adresse))
    return resultat


A_EXCLURE = ("PUBLICITÉ", "PUBLICITE", "©", "Titrologie", "A voir également", "À voir également",
             "Télécharger l'application", "Abidjan.net partout", "Lire aussi", "Commentaires")


def nettoyer_lignes(lignes: list[str]) -> list[str]:
    """Garde les lignes assez longues qui ne sont ni des publicités ni des menus."""
    gardees = []
    for ligne in lignes:
        ligne = " ".join(ligne.split())
        if len(ligne) >= 40 and not any(x in ligne for x in A_EXCLURE) and ligne not in gardees:
            gardees.append(ligne)
    return gardees


def extraire_texte(page_html: BeautifulSoup) -> str:
    """Cherche le texte de l'article à plusieurs endroits, du plus précis au plus large.
    Abidjan.net n'a pas la même mise en page pour les anciens et les nouveaux articles."""
    page_html = BeautifulSoup(str(page_html), "html.parser")
    for balise in page_html(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        balise.decompose()

    # 1) Les paragraphes <p> dans la balise <article>
    article = page_html.find("article")
    if article:
        lignes = nettoyer_lignes([p.get_text(" ", strip=True) for p in article.find_all("p")])
        if sum(len(l) for l in lignes) >= 200:
            return "\n".join(lignes)

    # 2) Le bloc de la page qui contient le plus de texte (hors liens) :
    #    c'est presque toujours le corps de l'article, même sans balises <p>.
    meilleur_bloc, meilleur_score = None, 0
    for bloc in page_html.find_all(["div", "section", "td"]):
        texte_bloc = bloc.get_text(" ", strip=True)
        texte_liens = sum(len(a.get_text(" ", strip=True)) for a in bloc.find_all("a"))
        nb_sous_blocs = len(bloc.find_all(["div", "section"]))
        score = len(texte_bloc) - 2 * texte_liens - 30 * nb_sous_blocs
        if score > meilleur_score:
            meilleur_bloc, meilleur_score = bloc, score
    if meilleur_bloc is not None:
        # Les mots en lien ou en gras (souvent le nom de la commune !) doivent rester
        # dans leur phrase : on enlève la balise et on garde son texte.
        for balise in meilleur_bloc.find_all(["a", "strong", "b", "em", "i", "span", "font"]):
            balise.unwrap()
        meilleur_bloc.smooth()
        lignes = nettoyer_lignes(meilleur_bloc.get_text("\n", strip=True).split("\n"))
        if sum(len(l) for l in lignes) >= 200:
            return "\n".join(lignes)

    # 3) Tous les <p> de la page
    lignes = nettoyer_lignes([p.get_text(" ", strip=True) for p in page_html.find_all("p")])
    if lignes:
        return "\n".join(lignes)

    # 4) Dernier recours : le résumé donné dans les balises meta
    for attribut, valeur in (("property", "og:description"), ("name", "description")):
        meta = page_html.find("meta", attrs={attribut: valeur})
        if meta and meta.get("content") and len(meta["content"]) >= 40:
            return meta["content"].strip()
    return ""


# Ce que les sites ajoutent à la fin des titres (« ... - Abidjan.net News ») : on l'enlève
SUFFIXES_TITRE = r"\s*[-|–]\s*(Abidjan\.net News|Abidjan\.net|Fraternit[ée] Matin|Fratmat(\.info)?|Koaci(\.com)?|Connectionivoirienne(\.net)?|Connection Ivoirienne|AIP|Agence Ivoirienne de Presse)\s*$"


def lire_article(page_html: BeautifulSoup, adresse: str = "", journal_par_defaut: str = "") -> dict:
    """Extrait le titre, la date, le journal et le texte d'une page d'article."""
    # Titre : la balise og:title est la plus fiable
    balise_titre = page_html.find("meta", property="og:title")
    if balise_titre and balise_titre.get("content"):
        titre = balise_titre["content"]
    else:
        titre = page_html.title.get_text() if page_html.title else ""
    titre = re.sub(SUFFIXES_TITRE, "", titre.strip(), flags=re.IGNORECASE).strip()

    date_publication = lire_date(page_html, adresse)

    # Journal d'origine. Sur Abidjan.net : un lien vers /source/<numéro>-<nom-du-journal>
    journal = ""
    lien_journal = page_html.find("a", href=re.compile(r"/source/\d+-"))
    if lien_journal:
        logo = lien_journal.find("img")
        journal = (lien_journal.get_text(strip=True) or (logo.get("alt", "") if logo else "")).strip()
        if not journal:
            journal = lien_journal["href"].rstrip("/").split("-", 1)[-1].replace("-", " ").title()
    journal = journal or journal_par_defaut

    texte = extraire_texte(page_html)

    return {"titre": titre, "date_publication": date_publication, "journal": journal, "texte": texte}


def source_d_une_adresse(adresse: str) -> dict:
    """Retrouve la source (et donc le journal par défaut) à partir du nom du site."""
    for source in config.SOURCES.values():
        if urlparse(source["page_liste"]).netloc == urlparse(adresse).netloc:
            return source
    return {}


# ---------------------------------------------------------------
# 3) Programme principal
# ---------------------------------------------------------------
FICHIER_VUS = config.DOSSIER_DONNEES / "articles_vus.csv"


def charger_articles_vus() -> set:
    """Numéros des articles déjà ouverts (gardés ou écartés), pour ne pas les rouvrir."""
    if FICHIER_VUS.exists():
        return set(pd.read_csv(FICHIER_VUS, dtype=str)["id_article"])
    return set()


def memoriser_vus(lignes: list[dict]) -> None:
    """Ajoute des articles ouverts au fichier des articles vus."""
    if not lignes:
        return
    tableau = pd.DataFrame(lignes)
    tableau.to_csv(FICHIER_VUS, mode="a", header=not FICHIER_VUS.exists(), index=False, encoding="utf-8")


def enregistrer(lignes: list[dict]) -> None:
    """Ajoute des articles gardés à la fin du fichier brut."""
    if not lignes:
        return
    tableau = pd.DataFrame(lignes, columns=COLONNES)
    tableau.to_csv(config.FICHIER_ARTICLES, mode="a", header=not config.FICHIER_ARTICLES.exists(),
                   index=False, encoding="utf-8")


def charger_articles_existants() -> pd.DataFrame:
    """Les articles déjà dans le fichier brut (ou un tableau vide)."""
    if config.FICHIER_ARTICLES.exists():
        return pd.read_csv(config.FICHIER_ARTICLES, dtype={"id_article": str})
    return pd.DataFrame(columns=COLONNES)


def tester_un_article(adresse: str) -> None:
    """Affiche ce que le script comprend d'un seul article, pour vérifier l'extraction."""
    page = telecharger(adresse)
    if page is None:
        return
    infos = lire_article(page, adresse, source_d_une_adresse(adresse).get("journal", ""))
    contenu = infos["titre"] + " " + infos["texte"]
    print(f"Titre    : {infos['titre']}")
    print(f"Date     : {infos['date_publication']}")
    print(f"Journal  : {infos['journal']}")
    print(f"Communes : {communes_citees(contenu[:LONGUEUR_DEBUT]) or '(aucune)'}")
    print(f"Agression ? {'oui' if parle_d_agression(infos['texte'], infos['titre']) else 'non'}"
          f" | À Abidjan ? {'oui' if se_passe_a_abidjan(contenu) else 'non'}")
    print(f"Texte ({len(infos['texte'])} caractères) :\n{infos['texte'][:1500]}")


def collecter(nom_source: str, nombre_pages: int, afficher_details: bool = False,
              nouveaux_termes: bool = False) -> None:
    """Parcourt les pages d'une source et enregistre les articles d'agression à Abidjan."""
    source = config.SOURCES[nom_source]
    config.DOSSIER_BRUT.mkdir(parents=True, exist_ok=True)

    existants = charger_articles_existants()
    deja_vus = set(existants["id_article"].astype(str)) | charger_articles_vus()
    vus_cette_fois = []
    nb_enregistres = 0
    nouveaux = []
    compteur = {"texte vide": 0, "pas une agression": 0, "hors Abidjan": 0}

    print(f"\n=== Source : {source['nom']} — jusqu'à {nombre_pages} page(s) ===")
    # Une liste de pages par mot recherché (ou une seule liste si la source n'a pas de mots)
    termes = source.get("termes", [None])
    if nouveaux_termes:
        termes = source.get("termes_supplementaires", [])
        if not termes:
            print(f"\n{source['nom']} : pas de recherche par mots-clés, rubrique sautée.")
            return
    pages_a_lire = [(terme, numero) for terme in termes for numero in range(1, nombre_pages + 1)]
    terme_termine = set()
    page_precedente = {}
    for terme, numero in pages_a_lire:
        if terme in terme_termine:
            continue
        adresse_page = source["page_liste"].format(page=numero, terme=terme or "")
        print(f"\nPage {numero}{' — recherche « ' + terme + ' »' if terme else ''} : {adresse_page}")
        page = telecharger(adresse_page)
        if page is None:
            continue

        candidats = liens_articles(page, source, adresse_page)
        if not candidats:
            print("  Aucun lien d'article sur cette page : fin de la liste.")
            terme_termine.add(terme)
            continue
        identifiants = {ident for ident, _ in candidats}
        if identifiants == page_precedente.get(terme):
            print("  Même contenu que la page précédente : dernière page atteinte.")
            terme_termine.add(terme)
            continue
        page_precedente[terme] = identifiants
        candidats = [(ident, adr) for ident, adr in candidats if ident not in deja_vus]
        # Premier filtre (rubrique générale seulement) : le titre est écrit dans l'adresse
        if source.get("filtre_adresse"):
            candidats = [(ident, adr) for ident, adr in candidats
                         if parle_d_agression("", adr.rsplit("/", 1)[-1])]
        print(f"  {len(candidats)} article(s) à ouvrir")

        for id_article, adresse in candidats:
            article_html = telecharger(adresse)
            if article_html is None:
                continue
            infos = lire_article(article_html, adresse, source.get("journal", ""))
            contenu = infos["titre"] + " " + infos["texte"]
            if afficher_details:
                print(f"\n  [détail] {adresse}\n  Titre : {infos['titre']}\n  Date : {infos['date_publication']} | Journal : {infos['journal']}\n  Texte ({len(infos['texte'])} caractères) : {infos['texte'][:300]}...\n")
            # Deuxième filtre, sur le vrai titre et le vrai texte
            if not infos["texte"]:
                print(f"  - écarté (texte introuvable) : {infos['titre'][:60]}")
                compteur["texte vide"] += 1
                deja_vus.add(id_article)
                vus_cette_fois.append({"id_article": id_article, "resultat": "texte vide"})
                continue
            if not parle_d_agression(infos["texte"], infos["titre"]):
                print(f"  - écarté (pas une agression) : {infos['titre'][:60]}")
                compteur["pas une agression"] += 1
                deja_vus.add(id_article)
                vus_cette_fois.append({"id_article": id_article, "resultat": "pas une agression"})
                continue
            if not se_passe_a_abidjan(contenu):
                print(f"  - écarté (hors Abidjan) : {infos['titre'][:60]}")
                compteur["hors Abidjan"] += 1
                deja_vus.add(id_article)
                vus_cette_fois.append({"id_article": id_article, "resultat": "hors Abidjan"})
                continue
            ligne = {
                "id_article": id_article,
                "source": nom_source,
                "adresse": adresse,
                **infos,
                "communes_citees": communes_citees(contenu[:LONGUEUR_DEBUT]),
                "date_collecte": datetime.now().isoformat(timespec="seconds"),
            }
            nouveaux.append(ligne)
            deja_vus.add(id_article)
            vus_cette_fois.append({"id_article": id_article, "resultat": "gardé"})
            print(f"  + gardé : {infos['date_publication']} | {infos['titre'][:60]}")

        # Enregistrement après chaque page : un arrêt (Ctrl + C) ne fait perdre que la page en cours
        nouveaux_page = nouveaux[nb_enregistres:]
        enregistrer(nouveaux_page)
        nb_enregistres += len(nouveaux_page)
        memoriser_vus(vus_cette_fois)
        vus_cette_fois.clear()

    print(f"\nTerminé pour {source['nom']} : {len(nouveaux)} article(s) gardé(s).")
    print(f"Écartés : {compteur}")
    print(f"Total dans le fichier : {len(existants) + len(nouveaux)} — {config.FICHIER_ARTICLES}")


if __name__ == "__main__":
    # Les options possibles après le nom du script
    analyseur = argparse.ArgumentParser(description="Collecte des faits divers d'agression à Abidjan")
    analyseur.add_argument("--source", default="toutes", choices=["toutes", *config.SOURCES],
                           help="rubrique à parcourir (par défaut : toutes)")
    analyseur.add_argument("--pages", type=int, default=3,
                           help="nombre maximum de pages à parcourir par rubrique")
    analyseur.add_argument("--details", action="store_true",
                           help="affiche le titre, la date et le début du texte de chaque article")
    analyseur.add_argument("--nouveaux-termes", action="store_true",
                           help="cherche seulement les mots de TERMES_SUPPLEMENTAIRES (config.py)")
    analyseur.add_argument("--tester", metavar="ADRESSE",
                           help="teste l'extraction sur un seul article, sans rien enregistrer")
    arguments = analyseur.parse_args()
    if arguments.tester:
        tester_un_article(arguments.tester)
    else:
        rubriques = list(config.SOURCES) if arguments.source == "toutes" else [arguments.source]
        for rubrique in rubriques:
            collecter(rubrique, arguments.pages, arguments.details, arguments.nouveaux_termes)
