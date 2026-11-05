from pathlib import Path

# ---------------------------------------------------------------
# Dossiers du projet
# ---------------------------------------------------------------
DOSSIER_PROJET = Path(__file__).resolve().parent
DOSSIER_DONNEES = DOSSIER_PROJET / "donnees"
DOSSIER_BRUT = DOSSIER_DONNEES / "brut"
DOSSIER_PROPRE = DOSSIER_DONNEES

FICHIER_ARTICLES = DOSSIER_BRUT / "articles_bruts.csv"

# ---------------------------------------------------------------
# Collecte
# ---------------------------------------------------------------
# On se présente honnêtement au site, et on attend entre deux pages
# pour ne pas le surcharger.
IDENTITE_NAVIGATEUR = "SafeZoneAbidjan/1.0 (projet etudiant Simplon CI - collecte de faits divers)"
PAUSE_SECONDES = 2

# Sources de presse. Pour en ajouter une, copier un bloc et l'adapter.
# Chaque source décrit une rubrique (ou une recherche) à parcourir :
#   "page_liste"     : adresse d'une page de liste ; {page} = 1, 2, 3... et {terme} = mot recherché
#   "termes"         : (facultatif) mots à chercher, une recherche par mot
#   "motif_article"  : forme des adresses d'articles ; le 1er groupe ( ) est le numéro de l'article
#   "prefixe"        : ajouté devant le numéro, pour ne pas confondre deux sites
#   "journal"        : nom du journal si la page ne l'indique pas
#   "filtre_adresse" : True = on ne garde que les liens dont l'adresse contient un mot-clé
#                      (rubrique générale) ; False = on ouvre tous les articles de la liste
MOTIF_ABIDJAN_NET = r"https?://news\.abidjan\.net/articles/(\d+)/([a-z0-9-]+)"
MOTIF_KOACI = r"https?://www\.koaci\.com/(?:index\.php/)?article/\d{4}/\d{2}/\d{2}/cote-divoire/[a-z-]+/[a-z0-9-]+_(\d+)\.html"
MOTIF_FRATMAT = r"https?://www\.fratmat\.info/(?:index\.php/)?article/(\d+)/.+"
MOTIF_CONNECTION = r"https?://connectionivoirienne\.net/(\d{4}/\d{2}/\d{2}/[a-z0-9-]+)/?"
MOTIF_AIP = r"https?://(?:www\.)?aip\.ci/(cote-divoire-aip-[a-z0-9-]+)/?"

# Mots de recherche pour les sites qui ont un moteur de recherche
TERMES_RECHERCHE = [
    "agression", "agressé", "braquage", "braqueurs", "microbes", "machette", "poignardé",
    "couteau", "cambriolage", "gang", "bandits", "vol à main armée", "viol", "enlèvement",
    "enfants en conflit avec la loi", "insécurité Abidjan",
]

# Mots ajoutés le 19/10 : meurtres, vols à l'arraché, attaques... (sous-représentés avant).
# Lancer seulement ces mots :  python scripts/scraping.py --nouveaux-termes --pages 10
TERMES_SUPPLEMENTAIRES = [
    "tué", "meurtre", "assassiné", "homicide", "corps sans vie", "blessé par balle",
    "vol à l'arraché", "arraché", "coupeurs de route", "attaque", "attaqué", "dépouillé",
    "vol de téléphone", "vol de moto", "agresseurs", "violée", "égorgé",
]

SOURCES = {
    # ---------- Abidjan.net (reprend de nombreux journaux ivoiriens) ----------
    "faits_divers": {
        "nom": "Abidjan.net — Faits divers et de société (2019 à aujourd'hui)",
        "page_liste": "https://news.abidjan.net/dossier/2181-faits-divers-et-de-societe/articles?page={page}",
        "motif_article": MOTIF_ABIDJAN_NET, "prefixe": "an_", "journal": "Abidjan.net",
        "filtre_adresse": False,
    },
    "faits_divers_2014": {
        "nom": "Abidjan.net — Faits divers 2014-2015",
        "page_liste": "https://news.abidjan.net/dossier/2111-faits-divers-2014/articles?page={page}",
        "motif_article": MOTIF_ABIDJAN_NET, "prefixe": "an_", "journal": "Abidjan.net",
        "filtre_adresse": False,
    },
    "societe": {
        "nom": "Abidjan.net — Société (rubrique générale)",
        "page_liste": "https://news.abidjan.net/articles/societe?page={page}",
        "motif_article": MOTIF_ABIDJAN_NET, "prefixe": "an_", "journal": "Abidjan.net",
        "filtre_adresse": True,
    },
    # ---------- Koaci : on utilise le moteur de recherche du site ----------
    "koaci": {
        "nom": "Koaci — recherche par mots-clés",
        "page_liste": "https://www.koaci.com/recherche?search={terme}&page={page}",
        "termes": [
            "agression", "agresse", "agresseurs", "braquage", "braqueurs", "machette", "microbes",
            "couteau", "poignard", "arme blanche", "vol à main armée", "cambriolage", "cambrioleurs",
            "enfants en conflit avec la loi", "gang", "bandits", "malfrats", "insécurité", "viol",
            "enlèvement", "racket", "vol de moto", "vol",
        ],
        "termes_supplementaires": TERMES_SUPPLEMENTAIRES,
        "motif_article": MOTIF_KOACI, "prefixe": "ko_", "journal": "Koaci",
        "filtre_adresse": False,
    },
    # ---------- Connectionivoirienne (WordPress, articles de 2014 à aujourd'hui) ----------
    "connectionivoirienne": {
        "nom": "Connectionivoirienne — recherche par mots-clés",
        "page_liste": "https://connectionivoirienne.net/page/{page}/?s={terme}",
        "termes": TERMES_RECHERCHE, "termes_supplementaires": TERMES_SUPPLEMENTAIRES,
        "motif_article": MOTIF_CONNECTION, "prefixe": "ci_", "journal": "Connectionivoirienne",
        "filtre_adresse": False,
    },
    # ---------- AIP, Agence ivoirienne de presse (WordPress) ----------
    "aip": {
        "nom": "AIP — recherche par mots-clés",
        "page_liste": "https://www.aip.ci/page/{page}/?s={terme}",
        "termes": TERMES_RECHERCHE, "termes_supplementaires": TERMES_SUPPLEMENTAIRES,
        "motif_article": MOTIF_AIP, "prefixe": "aip_", "journal": "AIP",
        "filtre_adresse": False,
    },
    # ---------- Fraternité Matin : rubriques Police et Gendarmerie ----------
    "fratmat_police": {
        "nom": "Fraternité Matin — Police",
        "page_liste": "https://www.fratmat.info/morearticles/societe/police?pgno={page}",
        "motif_article": MOTIF_FRATMAT, "prefixe": "fm_", "journal": "Fraternité Matin",
        "filtre_adresse": False,
    },
    "fratmat_gendarmerie": {
        "nom": "Fraternité Matin — Gendarmerie",
        "page_liste": "https://www.fratmat.info/morearticles/societe/gendarmerie?pgno={page}",
        "motif_article": MOTIF_FRATMAT, "prefixe": "fm_", "journal": "Fraternité Matin",
        "filtre_adresse": False,
    },
}

# Mots qui indiquent une agression. Ils sont écrits sans accents :
# le script enlève aussi les accents du texte avant de comparer.
# Mots « forts » : un seul suffit pour dire que c'est une agression.
MOTS_FORTS = [
    "agress", "braqu", "vol a main", "vol avec violence", "vol a l'arrache", "arrache",
    "voleur", "voleuse", "vole ", "volee", "voles ", "viol ", "viole ", "violee", "violer", "viols", "attaqu", "poignard",
    "machette", "couteau", "coups de", "taillad", "meurtr", "assassin", "coupeur",
    "homicide", "microbe", "bandit", "cambriol", "racket", "enlev", "gang", "malfrat",
    "egorg", "decapit", "pistolet", "arme a feu", "kalach", "rancon", "detrouss", "depouille par", "depouilles par", "depouillee",
]
# Mots « faibles » : ils comptent seulement si le titre ne parle pas d'accident, d'incendie...
MOTS_FAIBLES = [
    "tue ", "tuee", "tues", "tuer", "bless", "delinquan", "lynch", "bagarre", "corps sans vie",
    "par balle", "abattu", "tuerie", "crime", "criminel", "caid", "suspect", "interpelle",
    "voleu", "vol ", "vols ", "vol d", "arme blanche", "armes blanches",
]
# Titres à écarter même s'ils contiennent un mot faible (accidents, catastrophes, politique...)
MOTS_EXCLUSION = [
    "accident", "collision", "circulation", "incendie", "noyade", "noye", "foudre",
    "orage", "inondation", "effondrement", "crash", "electrocut", "tornade", "camion",
    "election", "electoral", "scrutin", "candidat", "cpi", "proces", "gbagbo", "soro",
]

# Mot qui suffit à dire que l'article se passe à Abidjan (en plus des communes).
MOT_ABIDJAN = "abidjan"

# Les 13 communes du District d'Abidjan (avec et sans accents).
COMMUNES = {
    "Abobo": ["abobo"],
    "Adjamé": ["adjamé", "adjame"],
    "Anyama": ["anyama"],
    "Attécoubé": ["attécoubé", "attecoube"],
    "Bingerville": ["bingerville"],
    "Cocody": ["cocody"],
    "Koumassi": ["koumassi"],
    "Marcory": ["marcory"],
    "Plateau": ["plateau"],
    "Port-Bouët": ["port-bouët", "port-bouet", "port bouet"],
    "Songon": ["songon"],
    "Treichville": ["treichville"],
    "Yopougon": ["yopougon", "yop "],
}

MOIS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}

# ---------------------------------------------------------------
# Étape 3 : lecture des articles par l'IA (extraction_ia.py)
# ---------------------------------------------------------------
# Choisir l'IA ici : "deepseek" ou "groq". Rien d'autre à changer.
FOURNISSEUR_IA = "deepseek"

# Les deux IA parlent le même « langage » que OpenAI : seule l'adresse change.
# La clé n'est JAMAIS écrite ici : elle est dans le fichier .env (voir README).
FOURNISSEURS_IA = {
    "deepseek": {"adresse": "https://api.deepseek.com", "modele": "deepseek-chat",
                 "nom_cle": "DEEPSEEK_API_KEY"},
    "groq": {"adresse": "https://api.groq.com/openai/v1", "modele": "llama-3.3-70b-versatile",
             "nom_cle": "GROQ_API_KEY"},
}

# Réponses autorisées : si l'IA invente autre chose, on remplace par "inconnu".
TYPES_AGRESSION = [
    "braquage", "vol à l'arraché", "vol avec violence", "cambriolage", "agression à l'arme blanche",
    "agression par balle", "coups et blessures", "meurtre", "viol", "enlèvement", "racket", "autre",
]
ARMES = ["aucune", "arme blanche", "arme à feu", "objet contondant", "autre", "inconnue"]
TRANCHES_HORAIRES = ["matin", "après-midi", "soir", "nuit", "inconnue"]
# Comment se déplaçait la victime (« sur place » = chez elle, dans son commerce, à son travail...)
DEPLACEMENTS = ["à pied", "moto", "taxi / woro-woro / gbaka", "voiture", "bus", "sur place", "inconnu"]
# Le lieu de l'agression était-il éclairé ? (seulement si l'article le dit)
ECLAIRAGES = ["sombre", "éclairé", "inconnu"]
# ---------------------------------------------------------------
# Étape 7 (bloc 3) : les quartiers de chaque commune (recherche « Où allez-vous ? »)
# ---------------------------------------------------------------
# Pour chaque commune : nom du quartier -> autres façons de l'écrire dans la presse.
# Le nom lui-même est toujours reconnu ; les accents, majuscules et tirets sont ignorés.
# Les variantes servent aussi à regrouper les agressions : « Angré château » et
# « Angré Djorobité 1 » comptent toutes pour Angré.
# L'ordre compte : le premier quartier reconnu dans le texte l'emporte
# (« Riviera Palmeraie » est donc placé avant « Riviera »).
QUARTIERS = {
    "Abobo": {
        "Abobo-Gare": [], "Abobo Baoulé": [], "N'Dotré": ["ndotre"], "Avocatier": [],
        "PK18": ["pk 18"], "Belleville": ["belle ville"], "Akeikoi": [], "Samaké": ["samanke"],
        "Anokoua-Kouté": ["anokoua"], "Kennedy": [], "Sagbé": [], "Clouetcha": [],
        "Abobo-Plaque": ["plaque"], "Abobo-Té": [], "Agbekoi": [], "Sogefiha": ["sogefia"],
        "Kobakro": [], "Ayébi": [], "Colombie": [], "Abobo Sud": [], "Habitat": [],
        "Biabou": [], "Derrière-Rails": [], "Bocabo": [], "Dokui": [],
    },
    "Adjamé": {
        "Williamsville": ["williams ville"], "220 Logements": [], "Liberté": [], "Bracodi": [],
        "Bromakoté": ["bromacote"], "Paillet": [], "Mirador": [], "Adjamé Village": ["ebrie"],
        "Marie-Thérèse": [], "Fraternité": [], "Habitat Extension": [], "Gare routière": [],
        "Black Market": [],
    },
    "Anyama": {
        "Ébimpé": [], "Belleville": ["belle ville"], "Akoupé-Zeudji": ["akoupe"], "Thomasset": [],
        "Anyama centre": [], "Sylla": [], "Ahoué": [], "Attinguié": [],
    },
    "Attécoubé": {
        "Locodjro": ["lokodjro"], "Abobo-Doumé": [], "Santé": [], "Boribana": [], "Mossikro": [],
        "Banco": [], "Agban Village": ["agban"], "Jérusalem": [], "Sébroko": [],
        "Attécoubé centre": [], "Gbebouto": [],
    },
    "Bingerville": {
        "Bingerville centre": [], "Akandjé": [], "Santai": [], "Gbagba": [],
        "Adjamé-Bingerville": [], "Feh Kessé": [], "Achokoi": [],
    },
    "Cocody": {
        "Angré": ["djorobite", "bessikoi"], "Riviera Palmeraie": ["palmeraie"], "Riviera": [],
        "Deux-Plateaux": ["2 plateaux", "ii plateaux", "7e tranche", "vallon", "vallons", "sococe"],
        "Danga": [], "Blockhauss": ["blockhaus"], "Cocody centre": [], "Ambassades": [],
        "Mermoz": [], "Saint-Jean": [], "Akouédo": [], "Abatta": [], "Bonoumin": [],
        "Attoban": [], "Faya": [], "Anono": [], "M'Pouto": ["mpouto"], "M'Badon": ["mbadon"],
        "Gobelet": [], "Campus universitaire": ["campus", "universite", "cite universitaire"],
        "Lycée technique": [], "Cocody Village": [],
    },
    "Koumassi": {
        "Remblais": ["remblai"], "Grand Carrefour": [], "Campement": [], "Divo": [], "Sicogi": [],
        "Soleil": [], "Prodomo": [], "Inchallah": ["inch allah"], "Zoé Bruno": [],
        "Sogefiha": ["sogefia"],
    },
    "Marcory": {
        "Zone 4": ["zone iv"], "Biétry": [], "Anoumabo": [], "Marcory Résidentiel": ["residentiel"],
        "Sicogi": [], "Champroux": [], "Hibiscus": [], "Aliodan": [], "Gnanzoua": [],
        "Konan Raphaël": [],
    },
    "Plateau": {
        "Plateau centre": [], "Cité administrative": [], "Indénié": [],
    },
    "Port-Bouët": {
        "Vridi": [], "Gonzagueville": [], "Derrière Wharf": ["derriere warf", "wharf", "warf"],
        "Jean Folly": [], "Adjouffou": [], "Anani": [], "Aéroport": [], "Phare": [],
        "Abattoir": [], "Port-Bouët centre": [],
    },
    "Songon": {
        "Songon centre": [], "Kassemblé": [], "Songon-Agban": [], "Songon-Dagbé": ["dagbe"],
        "Songon-Té": [], "M'Brathé": ["mbrathe"],
    },
    "Treichville": {
        "Arras": [], "Biafra": [], "Gare de Bassam": [], "Zone portuaire": [],
        "Treichville centre": [],
    },
    "Yopougon": {
        "Selmer": [], "Niangon": ["lokoa", "lokoua"], "Siporex": [], "Andokoi": [], "Sicogi": [],
        "Wassakara": [], "Lavage": [], "Micao": [], "Azito": [], "Toits-Rouges": ["toit rouge"],
        "Port-Bouët 2": [], "Bel Air": [], "Kouté": [], "Gesco": [], "Maroc": [], "Koweït": [],
        "Ananeraie": ["ananerais"], "Doukouré": [], "Bagnon": [], "Sideci": [],
        "Nouveau Quartier": [], "Ficgayo": [], "Sable": [], "Béago": [], "Camp militaire": [],
        "Gouro": [], "Mamie Adjoua": [], "Zone industrielle": [], "Millionnaire": [],
        "Yao Séhi": [], "Académie de la mer": ["academie des mers"],
    },
}
