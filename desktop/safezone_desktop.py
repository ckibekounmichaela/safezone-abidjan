import os
import threading
from datetime import datetime
import tkinter as tk
import webbrowser
from tkinter import ttk

import requests
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

try:
    import tkintermapview
except ImportError:
    tkintermapview = None


class RequetesAvecIdentite:
    """tkintermapview télécharge les morceaux de carte avec une identité (« TkinterMapView »)
    que les serveurs d'OpenStreetMap refusent : on la remplace par celle du projet,
    comme pour le scraping (le site sait qui lui parle)."""
    def get(self, adresse, **options):
        options["headers"] = {"User-Agent": "SafeZoneAbidjan-desktop/1.0 (projet etudiant Simplon CI)"}
        return requests.get(adresse, **options)

    def __getattr__(self, nom):
        return getattr(requests, nom)


if tkintermapview:
    tkintermapview.map_widget.requests = RequetesAvecIdentite()

# ---------------------------------------------------------------
# 1) Réglages : adresse de l'API et couleurs de la maquette
# ---------------------------------------------------------------
# 127.0.0.1 plutôt que « localhost » : sous Windows, « localhost » essaie d'abord IPv6
# et perd 2 secondes à chaque appel, car l'API n'écoute qu'en IPv4
ADRESSE_API = os.getenv("SAFEZONE_API", "https://safezone-abidjan.onrender.com")

BLEU_NUIT = "#0E1A2B"
BLEU_NUIT_2 = "#1F3048"
ORANGE = "#C2550F"
OR = "#F2B04C"
FOND = "#F2F4F6"
BLANC = "#FFFFFF"
BORDURE = "#D9DEE4"
GRIS_TEXTE = "#3B4A5C"
BLEU_GRAPHIQUE = "#2a78d6"
# Niveau de risque -> (fond clair, texte foncé, couleur vive pour la carte et la barre)
COULEURS_NIVEAU = {
    "faible": ("#DDF1E6", "#1E5E3F", "#2E8B57"),
    "moyen": ("#FCEBCB", "#7A4A05", "#E0A100"),
    "élevé": ("#F6D5D2", "#8E1D17", "#C0392B"),
}
POLICE = "Segoe UI"


# ---------------------------------------------------------------
# 2) Parler avec l'API
# ---------------------------------------------------------------
def lire_api(chemin: str, **parametres):
    """Demande des données à l'API (GET) et renvoie le JSON.
    Exemple : lire_api("/risque", commune="Cocody", heure=22)"""
    return verifier(requests.get(ADRESSE_API + chemin, params=parametres, timeout=60))


def envoyer_api(chemin: str, donnees: dict):
    """Envoie des données à l'API (POST), par exemple une question à l'assistant."""
    return verifier(requests.post(ADRESSE_API + chemin, json=donnees, timeout=90))


SERVICE_INDISPONIBLE = "Le service ne répond pas. Vérifiez votre connexion Internet et réessayez."


def verifier(reponse: requests.Response):
    """Renvoie le JSON, ou lève une erreur avec un message simple en français."""
    if reponse.status_code == 200:
        return reponse.json()
    try:
        detail = reponse.json().get("detail")
    except ValueError:
        detail = None
    if isinstance(detail, str) and detail != "Not Found":
        raise RuntimeError(detail)
    raise RuntimeError("Les informations saisies ne sont pas valides." if reponse.status_code == 422
                       else SERVICE_INDISPONIBLE)


def message_erreur(erreur: Exception) -> str:
    """Un message clair pour l'utilisateur, selon l'erreur."""
    if isinstance(erreur, requests.RequestException):
        return SERVICE_INDISPONIBLE
    return str(erreur)


def en_arriere_plan(fenetre: tk.Misc, travail, quand_fini, quand_erreur):
    """Fait le travail (appel à l'API) sans figer la fenêtre, puis affiche le résultat.
    Tkinter n'accepte les changements d'affichage que depuis le programme principal :
    on y revient avec fenetre.after()."""
    def executer():
        try:
            resultat = travail()
        except Exception as erreur:
            fenetre.after(0, quand_erreur, erreur)
        else:
            fenetre.after(0, quand_fini, resultat)
    threading.Thread(target=executer, daemon=True).start()


# ---------------------------------------------------------------
# 3) Petits éléments réutilisés
# ---------------------------------------------------------------
def bloc_blanc(parent, **options) -> tk.Frame:
    """Un cadre blanc avec une fine bordure (les « cartes » de la maquette)."""
    return tk.Frame(parent, bg=BLANC, highlightbackground=BORDURE, highlightthickness=1, **options)


def titre(parent, texte, taille=20, fond=FOND) -> tk.Label:
    """Un titre en gras."""
    return tk.Label(parent, text=texte, bg=fond, fg=BLEU_NUIT, font=(POLICE, taille, "bold"), anchor="w")


def texte(parent, contenu="", fond=BLANC, couleur=GRIS_TEXTE, taille=10, **options) -> tk.Label:
    """Un texte simple, aligné à gauche."""
    return tk.Label(parent, text=contenu, bg=fond, fg=couleur, font=(POLICE, taille), anchor="w",
                    justify="left", **options)


def pastille(parent, niveau: str, fond=BLANC) -> tk.Label:
    """Pastille colorée « Risque élevé »."""
    fond_pastille, couleur, _ = COULEURS_NIVEAU.get(niveau, COULEURS_NIVEAU["moyen"])
    return tk.Label(parent, text=f"  Risque {niveau}  ", bg=fond_pastille, fg=couleur,
                    font=(POLICE, 10, "bold"))


def vider(cadre: tk.Misc):
    """Enlève tout ce qu'il y a dans un cadre (avant de le remplir à nouveau)."""
    for enfant in cadre.winfo_children():
        enfant.destroy()


# ---------------------------------------------------------------
# 4) Écran « Tableau de bord »
# ---------------------------------------------------------------
class TableauDeBord(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=FOND)
        titre(self, "Tableau de bord").pack(fill="x")
        texte(self, "Les agressions rapportées par la presse à Abidjan.", fond=FOND).pack(fill="x", pady=(0, 12))
        self.contenu = tk.Frame(self, bg=FOND)
        self.contenu.pack(fill="both", expand=True)
        self.charger()

    def charger(self):
        """Demande les statistiques et le risque de ce soir à l'API."""
        vider(self.contenu)
        texte(self.contenu, "Chargement…", fond=FOND).pack(anchor="w")
        en_arriere_plan(self, lambda: (lire_api("/statistiques"), lire_api("/risque/toutes", heure=20)),
                        self.afficher, self.erreur)

    def erreur(self, erreur):
        """L'API ne répond pas : message + bouton « Réessayer »."""
        vider(self.contenu)
        texte(self.contenu, message_erreur(erreur), fond=FOND, couleur="#8E1D17").pack(anchor="w")
        ttk.Button(self.contenu, text="Réessayer", command=self.charger).pack(anchor="w", pady=8)

    def afficher(self, resultats):
        stats, risques = resultats
        vider(self.contenu)

        # 4a) Les 4 chiffres clés, côte à côte
        heure_connue = sum(t["nombre"] for t in stats["par_tranche_horaire"])
        nuit = 0
        for t in stats["par_tranche_horaire"]:
            if t["tranche_horaire"] == "nuit":
                nuit = t["nombre"]
        premiere = stats["par_commune"][0]
        chiffres = [
            (stats["total_agressions"], "agressions rapportées"),
            (f"{stats['periode']['debut']}–{stats['periode']['fin']}", "période couverte"),
            (f"{round(100 * nuit / max(heure_connue, 1))} %", "la nuit (heure connue)"),
            (premiere["commune"], f"commune la plus touchée ({premiere['nombre']})"),
        ]
        ligne = tk.Frame(self.contenu, bg=FOND)
        ligne.pack(fill="x")
        for colonne, (valeur, libelle) in enumerate(chiffres):
            carte = bloc_blanc(ligne, padx=16, pady=12)
            carte.grid(row=0, column=colonne, sticky="nsew", padx=(0 if colonne == 0 else 10, 0))
            ligne.columnconfigure(colonne, weight=1)
            tk.Label(carte, text=valeur, bg=BLANC, fg=ORANGE, font=(POLICE, 20, "bold")).pack(anchor="w")
            texte(carte, libelle).pack(anchor="w")

        # 4b) En bas : deux graphiques (à gauche) + le classement des communes ce soir (à droite)
        bas = tk.Frame(self.contenu, bg=FOND)
        bas.pack(fill="both", expand=True, pady=(12, 0))
        bas.columnconfigure(0, weight=3)
        bas.columnconfigure(1, weight=2)
        bas.rowconfigure(0, weight=1)

        graphiques = bloc_blanc(bas, padx=8, pady=8)
        graphiques.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        figure = Figure(figsize=(6.4, 3.6), dpi=90, facecolor=BLANC)
        # Graphique 1 : par commune (barres horizontales, la plus touchée en haut)
        communes = stats["par_commune"][::-1]
        axe = figure.add_subplot(1, 2, 1)
        barres = axe.barh([c["commune"] for c in communes], [c["nombre"] for c in communes],
                          color=BLEU_GRAPHIQUE, height=0.6)
        axe.bar_label(barres, padding=3, fontsize=8, color=GRIS_TEXTE)
        axe.set_title("Par commune", loc="left", fontsize=11)
        # Graphique 2 : par moment de la journée (barres verticales)
        ordre = ["matin", "après-midi", "soir", "nuit"]
        par_tranche = {t["tranche_horaire"]: t["nombre"] for t in stats["par_tranche_horaire"]}
        axe2 = figure.add_subplot(1, 2, 2)
        barres2 = axe2.bar(ordre, [par_tranche.get(t, 0) for t in ordre], color=BLEU_GRAPHIQUE, width=0.6)
        axe2.bar_label(barres2, padding=3, fontsize=8, color=GRIS_TEXTE)
        axe2.set_title(f"Par moment ({heure_connue} cas, heure connue)", loc="left", fontsize=11)
        for a in (axe, axe2):
            a.spines[["top", "right"]].set_visible(False)
            a.tick_params(labelsize=8, colors=GRIS_TEXTE)
        axe.xaxis.set_visible(False)
        axe2.yaxis.set_visible(False)
        figure.tight_layout()
        FigureCanvasTkAgg(figure, master=graphiques).get_tk_widget().pack(fill="both", expand=True)

        # Le classement des 13 communes à 20 h
        classement = bloc_blanc(bas, padx=16, pady=12)
        classement.grid(row=0, column=1, sticky="nsew")
        tk.Label(classement, text="Risque ce soir (20 h)", bg=BLANC, fg=BLEU_NUIT,
                 font=(POLICE, 13, "bold")).pack(anchor="w", pady=(0, 8))
        for r in risques:
            rangee = tk.Frame(classement, bg=BLANC)
            rangee.pack(fill="x", pady=2)
            texte(rangee, r["commune"], couleur=BLEU_NUIT, taille=10).pack(side="left")
            texte(rangee, f"{r['score']}/100").pack(side="right")
            pastille(rangee, r["niveau"]).pack(side="right", padx=8)


# ---------------------------------------------------------------
# 5) Écran « Calculer mon risque » : où allez-vous, à quelle heure ? -> score
#    1. choisir la commune, puis le quartier (rien à taper)
#    2. choisir l'heure à laquelle on y sera
#    3. cliquer sur « Calculer le risque »
# ---------------------------------------------------------------
class CalculRisque(tk.Frame):
    def __init__(self, parent, demander_assistant):
        super().__init__(parent, bg=FOND)
        self.demander_assistant = demander_assistant
        self.demande = 0
        self.positions = {}
        self.quartiers_par_commune = {}

        titre(self, "Calculer mon risque").pack(fill="x")
        texte(self, "Choisissez où vous allez, à quelle heure et comment, puis cliquez sur « Calculer le risque ».",
              fond=FOND).pack(fill="x", pady=(0, 10))

        # 5a) Le formulaire : commune, quartier, heure, déplacement, éclairage, bouton
        formulaire = bloc_blanc(self, padx=16, pady=12)
        formulaire.pack(fill="x")
        self.commune = tk.StringVar()
        self.quartier = tk.StringVar(value="Toute la commune")
        self.heure = tk.StringVar()
        maintenant = datetime.now().hour
        # Texte affiché -> heure : {"Maintenant (21 h)": 21, "0 h": 0, "1 h": 1, ... "23 h": 23}
        self.heures = {f"Maintenant ({maintenant} h)": maintenant}
        for h in range(24):
            self.heures[f"{h} h"] = h

        # Les 5 listes déroulantes, côte à côte (titre au-dessus, liste en dessous)
        self.liste_commune = self.liste_deroulante(formulaire, 0, "1. Où allez-vous ? (commune)", self.commune, 16)
        self.liste_quartier = self.liste_deroulante(formulaire, 1, "2. Quartier", self.quartier, 20)
        self.liste_heure = self.liste_deroulante(formulaire, 2, "3. À quelle heure ?", self.heure, 15)
        self.liste_heure["values"] = list(self.heures)
        self.heure.set(f"Maintenant ({maintenant} h)")
        self.liste_commune.bind("<<ComboboxSelected>>", lambda _: self.remplir_quartiers())

        # 4. Comment on se déplace et 5. l'éclairage : texte affiché -> code envoyé à l'API ("" = pas choisi)
        self.deplacements = {"Je ne sais pas encore": "", "À pied": "pied", "À moto": "moto",
                             "Taxi / woro-woro / gbaka": "taxi", "En voiture": "voiture", "En bus": "bus"}
        self.eclairages = {"Je ne sais pas": "", "Oui, éclairée": "eclairee", "Non, sombre": "sombre"}
        self.deplacement = tk.StringVar(value="Je ne sais pas encore")
        self.eclairage = tk.StringVar(value="Je ne sais pas")
        liste = self.liste_deroulante(formulaire, 3, "4. Comment vous déplacez-vous ?", self.deplacement, 22)
        liste["values"] = list(self.deplacements)
        liste = self.liste_deroulante(formulaire, 4, "5. La rue est-elle éclairée ?", self.eclairage, 15)
        liste["values"] = list(self.eclairages)

        # Le bouton orange (désactivé tant que les listes ne sont pas chargées)
        self.bouton = tk.Button(formulaire, text="Calculer le risque", bg=ORANGE, fg=BLANC,
                                activebackground="#8F3D08", activeforeground=BLANC, disabledforeground="#F3C9AE",
                                relief="flat", font=(POLICE, 12, "bold"), padx=22, pady=6, cursor="hand2",
                                command=self.calculer, state="disabled")
        self.bouton.grid(row=1, column=5, sticky="w")
        self.message = texte(formulaire, "Chargement des communes et quartiers…")
        self.message.grid(row=2, column=0, columnspan=6, sticky="w", pady=(8, 0))

        # 5b) Le résultat (à gauche) et la carte (à droite)
        bas = tk.Frame(self, bg=FOND)
        bas.pack(fill="both", expand=True, pady=(10, 0))
        bas.columnconfigure(0, weight=2, uniform="bas")
        bas.columnconfigure(1, weight=3, uniform="bas")
        bas.rowconfigure(0, weight=1)
        self.resultat = bloc_blanc(bas, padx=16, pady=12)
        self.resultat.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.largeur_texte = tk.IntVar(value=360)
        self.resultat.bind("<Configure>", lambda e: self.largeur_texte.set(max(e.width - 40, 200)))
        texte(self.resultat, "Le résultat s'affichera ici.").pack(anchor="w")
        cadre_carte = bloc_blanc(bas)
        cadre_carte.grid(row=0, column=1, sticky="nsew")
        if tkintermapview:
            self.carte = tkintermapview.TkinterMapView(cadre_carte, corner_radius=0)
            self.carte.pack(fill="both", expand=True)
            self.carte.set_position(5.345, -4.02)
            self.carte.set_zoom(11)
        else:
            self.carte = None
            texte(cadre_carte, "Carte indisponible : pip install tkintermapview", padx=16, pady=16).pack()

        self.charger_listes()

    def liste_deroulante(self, parent, colonne: int, libelle: str, variable, largeur: int) -> ttk.Combobox:
        """Un titre en gras et, en dessous, une liste déroulante où on ne peut pas taper."""
        tk.Label(parent, text=libelle, bg=BLANC, fg=BLEU_NUIT, font=(POLICE, 10, "bold")).grid(
            row=0, column=colonne, sticky="w", padx=(0, 14))
        liste = ttk.Combobox(parent, textvariable=variable, state="readonly", width=largeur, font=(POLICE, 11))
        liste.grid(row=1, column=colonne, sticky="w", padx=(0, 14), ipady=3)
        return liste

    # ----- Chargement des listes -----
    def charger_listes(self):
        """Demande les communes et les quartiers à l'API."""
        en_arriere_plan(self, lambda: (lire_api("/communes"), lire_api("/quartiers/tous")),
                        self.listes_recues, self.erreur_listes)

    def erreur_listes(self, erreur):
        """L'API ne répond pas : message + bouton « Réessayer »."""
        self.message.config(text=message_erreur(erreur), fg="#8E1D17")
        vider(self.resultat)
        tk.Button(self.resultat, text="Réessayer", relief="flat", bg=BORDURE, padx=10,
                  command=self.charger_listes).pack(anchor="w", pady=8)

    def listes_recues(self, resultats):
        """Les listes sont arrivées : on remplit les choix et on active le bouton."""
        communes, quartiers = resultats
        self.positions = {c["nom"]: (c["latitude"], c["longitude"]) for c in communes}
        self.quartiers_par_commune.clear()
        for q in quartiers:
            self.quartiers_par_commune.setdefault(q["commune"], []).append(q["quartier"])
        self.liste_commune["values"] = sorted(self.positions)
        self.commune.set(sorted(self.positions)[0])
        self.remplir_quartiers()
        self.bouton.config(state="normal")
        self.message.config(text="13 communes et leurs quartiers chargés.", fg=GRIS_TEXTE)

    def remplir_quartiers(self, quartier: str | None = None):
        """Une commune est choisie : la 2e liste propose ses quartiers."""
        quartiers = sorted(self.quartiers_par_commune.get(self.commune.get(), []))
        self.liste_quartier["values"] = ["Toute la commune", *quartiers]
        self.quartier.set(quartier or "Toute la commune")

    def choisir(self, commune: str, quartier: str | None = None, heure: int | None = None):
        """Remplir le formulaire depuis le code (ou un clic sur la carte), puis calculer."""
        self.commune.set(commune)
        self.remplir_quartiers(quartier)
        if heure is not None:
            self.heure.set(f"{heure} h")
        self.calculer()

    # ----- Le calcul -----
    def calculer(self):
        """Le clic sur « Calculer le risque » : on demande le score à l'API."""
        commune, quartier = self.commune.get(), self.quartier.get()
        heure = self.heures[self.heure.get()]
        deplacement = self.deplacements[self.deplacement.get()]
        eclairage = self.eclairages[self.eclairage.get()]
        if not commune:
            return
        vider(self.resultat)
        texte(self.resultat, "Calcul du risque…").pack(anchor="w")
        self.bouton.config(state="disabled", text="Calcul…")

        def travail():
            if quartier == "Toute la commune":
                risque = lire_api("/risque", commune=commune, heure=heure,
                                  deplacement=deplacement, eclairage=eclairage)
            else:
                risque = lire_api("/risque/quartier", quartier=quartier, commune=commune, heure=heure,
                                  deplacement=deplacement, eclairage=eclairage)
            return risque, lire_api("/risque/toutes", heure=heure)

        # Si l'utilisateur relance un calcul avant la réponse, seule la DERNIÈRE réponse est affichée
        self.demande += 1
        numero = self.demande
        en_arriere_plan(self, travail, lambda resultat: self.reponse_recue(numero, resultat), self.erreur)

    def reponse_recue(self, numero: int, resultat):
        """On affiche la réponse seulement si c'est celle du dernier calcul demandé."""
        if numero == self.demande:
            self.afficher(resultat)

    def erreur(self, erreur):
        """Le calcul a échoué : on affiche le message en rouge."""
        self.bouton.config(state="normal", text="Calculer le risque")
        vider(self.resultat)
        texte(self.resultat, message_erreur(erreur), couleur="#8E1D17",
              wraplength=self.largeur_texte.get()).pack(anchor="w")

    def afficher(self, resultats):
        """Le résultat : seulement ce qui est utile à l'utilisateur
        (le lieu et l'heure, le niveau avec sa barre de progression, le conseil, 2 phrases « À savoir »)."""
        risque, toutes = resultats
        self.bouton.config(state="normal", text="Calculer le risque")
        self.dessiner_carte(toutes, risque["commune"])
        vider(self.resultat)
        largeur = self.largeur_texte.get()
        niveau = risque["niveau"]
        fond_niveau, couleur_niveau, couleur_vive = COULEURS_NIVEAU[niveau]

        # Le lieu et l'heure
        lieu = risque.get("quartier") or risque["commune"]
        tk.Label(self.resultat, text=lieu, bg=BLANC, fg=BLEU_NUIT, font=(POLICE, 18, "bold")).pack(anchor="w")
        sous_titre = f"à {risque['heure']} h"
        if risque.get("quartier"):
            sous_titre = f"{risque['commune']} · " + sous_titre
        texte(self.resultat, sous_titre).pack(anchor="w")

        # Le bandeau de la couleur du niveau : « Risque élevé   78/100 » + la barre de progression
        bandeau = tk.Frame(self.resultat, bg=fond_niveau, padx=12, pady=10)
        bandeau.pack(fill="x", pady=10)
        ligne = tk.Frame(bandeau, bg=fond_niveau)
        ligne.pack(fill="x")
        tk.Label(ligne, text=f"Risque {niveau}", bg=fond_niveau, fg=couleur_niveau,
                 font=(POLICE, 16, "bold")).pack(side="left")
        tk.Label(ligne, text=f"{risque['score']}/100", bg=fond_niveau, fg=couleur_niveau,
                 font=(POLICE, 16, "bold")).pack(side="right")
        # Un style de barre par niveau : remplie de la couleur vive du niveau, sur un fond blanc
        style = f"{niveau}.Horizontal.TProgressbar"
        ttk.Style().configure(style, background=couleur_vive, troughcolor=BLANC, bordercolor=fond_niveau,
                              lightcolor=couleur_vive, darkcolor=couleur_vive, thickness=12)
        ttk.Progressbar(bandeau, style=style, maximum=100, value=risque["score"]).pack(fill="x", pady=(8, 2))
        # Sous la barre : Faible au début, Moyen à 20 %, Élevé à 50 % (les seuils des niveaux)
        legende = tk.Frame(bandeau, bg=fond_niveau, height=18)
        legende.pack(fill="x")
        for mot, place in (("Faible", 0.0), ("Moyen", 0.2), ("Élevé", 0.5)):
            tk.Label(legende, text=mot, bg=fond_niveau, fg=couleur_niveau,
                     font=(POLICE, 8, "bold")).place(relx=place, y=0)

        # Le conseil, bien visible
        tk.Label(self.resultat, text=risque["conseil"], bg=BLANC, fg=BLEU_NUIT, font=(POLICE, 11, "bold"),
                 wraplength=largeur, justify="left", anchor="w").pack(anchor="w")

        # À savoir : 2 phrases simples écrites par l'API
        tk.Label(self.resultat, text="À savoir", bg=BLANC, fg=BLEU_NUIT,
                 font=(POLICE, 11, "bold")).pack(anchor="w", pady=(12, 2))
        for phrase in risque["a_savoir"]:
            texte(self.resultat, f"•  {phrase}", wraplength=largeur).pack(anchor="w", pady=1)

        # Le bouton qui ouvre l'assistant avec une question toute prête
        question = f"Est-ce risqué d'aller à {lieu}"
        if risque.get("quartier"):
            question += f" ({risque['commune']})"
        question += f" vers {risque['heure']}h ?"
        tk.Button(self.resultat, text="Demander conseil à l'assistant", bg=BLEU_NUIT, fg=BLANC,
                  activebackground=BLEU_NUIT_2, activeforeground=BLANC, relief="flat", font=(POLICE, 10, "bold"),
                  padx=12, pady=5, cursor="hand2",
                  command=lambda: self.demander_assistant(question)).pack(anchor="w", pady=(10, 0))
        texte(self.resultat, risque["attention"], taille=8, wraplength=largeur).pack(anchor="w", pady=(8, 0))

    def dessiner_carte(self, toutes, commune_choisie):
        """Un repère par commune, de la couleur de son niveau à l'heure choisie. Clic = calculer pour cette commune."""
        if not self.carte:
            return
        self.carte.delete_all_marker()
        for r in toutes:
            latitude, longitude = self.positions[r["commune"]]
            couleur = COULEURS_NIVEAU[r["niveau"]][2]
            self.carte.set_marker(
                latitude, longitude, text=f"{r['commune']} {r['score']}",
                marker_color_circle=BLANC if r["commune"] == commune_choisie else couleur,
                marker_color_outside=couleur, font=(POLICE, 9, "bold"), text_color=BLEU_NUIT,
                command=lambda marqueur, nom=r["commune"]: self.choisir(nom))
        self.carte.set_position(*self.positions[commune_choisie])
        self.carte.set_zoom(12)


# ---------------------------------------------------------------
# 6) Écran « Incidents » : les dernières agressions
# ---------------------------------------------------------------
class Incidents(tk.Frame):
    # Les colonnes du tableau : (nom dans l'API, titre affiché, largeur en pixels)
    COLONNES = [("date", "Date", 90), ("commune", "Commune", 100), ("quartier", "Quartier", 140),
                ("type_agression", "Type", 170), ("arme", "Arme", 110), ("tranche_horaire", "Moment", 90),
                ("titre", "Titre de l'article", 420)]

    def __init__(self, parent):
        super().__init__(parent, bg=FOND)
        self.liens = {}
        self.demande = 0
        titre(self, "Incidents récents").pack(fill="x")
        texte(self, "Double-cliquez sur une ligne pour ouvrir l'article de presse.", fond=FOND).pack(fill="x", pady=(0, 12))

        # Les filtres : commune et nombre d'agressions
        filtres = tk.Frame(self, bg=FOND)
        filtres.pack(fill="x", pady=(0, 10))
        self.commune = tk.StringVar(value="Toutes les communes")
        self.nombre = tk.StringVar(value="50")
        texte(filtres, "Commune", fond=FOND, couleur=BLEU_NUIT).grid(row=0, column=0, sticky="w")
        texte(filtres, "Nombre", fond=FOND, couleur=BLEU_NUIT).grid(row=0, column=1, sticky="w", padx=10)
        self.liste_commune = ttk.Combobox(filtres, textvariable=self.commune, state="readonly", width=20)
        self.liste_commune.grid(row=1, column=0)
        liste_nombre = ttk.Combobox(filtres, textvariable=self.nombre, values=["20", "50", "100"],
                                    state="readonly", width=6)
        liste_nombre.grid(row=1, column=1, padx=10)
        for liste in (self.liste_commune, liste_nombre):
            liste.bind("<<ComboboxSelected>>", lambda _: self.charger())
        self.message = texte(filtres, "", fond=FOND)
        self.message.grid(row=1, column=2, padx=10)

        # Le tableau, avec une barre de défilement à droite
        cadre = bloc_blanc(self)
        cadre.pack(fill="both", expand=True)
        self.tableau = ttk.Treeview(cadre, columns=[c[0] for c in self.COLONNES], show="headings")
        for cle, entete, largeur in self.COLONNES:
            self.tableau.heading(cle, text=entete, anchor="w")
            self.tableau.column(cle, width=largeur, anchor="w", stretch=(cle == "titre"))
        defilement = ttk.Scrollbar(cadre, orient="vertical", command=self.tableau.yview)
        self.tableau.configure(yscrollcommand=defilement.set)
        self.tableau.pack(side="left", fill="both", expand=True)
        defilement.pack(side="right", fill="y")
        self.tableau.bind("<Double-1>", self.ouvrir_article)

        en_arriere_plan(self, lambda: lire_api("/communes"), self.communes_recues, self.erreur)

    def communes_recues(self, communes):
        """Remplit la liste des communes, puis charge les agressions."""
        self.liste_commune["values"] = ["Toutes les communes", *sorted(c["nom"] for c in communes)]
        self.charger()

    def charger(self):
        """Demande les agressions à l'API selon les filtres."""
        parametres = {"limite": int(self.nombre.get())}
        if self.commune.get() != "Toutes les communes":
            parametres["commune"] = self.commune.get()
        self.message.config(text="Chargement…", fg=GRIS_TEXTE)
        self.demande += 1
        numero = self.demande
        en_arriere_plan(self, lambda: lire_api("/agressions", **parametres),
                        lambda agressions: self.reponse_recue(numero, agressions), self.erreur)

    def reponse_recue(self, numero: int, agressions):
        if numero == self.demande:
            self.afficher(agressions)

    def erreur(self, erreur):
        self.message.config(text=message_erreur(erreur), fg="#8E1D17")

    def afficher(self, agressions):
        """Remplit le tableau : une ligne par agression."""
        self.tableau.delete(*self.tableau.get_children())
        self.liens.clear()
        for a in agressions:
            valeurs = [a.get(cle) or "—" for cle, _, _ in self.COLONNES]
            ligne = self.tableau.insert("", "end", values=valeurs)
            self.liens[ligne] = a["lien_article"]
        self.message.config(text=f"{len(agressions)} agressions", fg=GRIS_TEXTE)

    def ouvrir_article(self, _evenement):
        """Double-clic : ouvre l'article de la ligne dans le navigateur."""
        ligne = self.tableau.focus()
        if self.liens.get(ligne):
            webbrowser.open(self.liens[ligne])


# ---------------------------------------------------------------
# 7) Écran « Assistant » : discuter avec l'agent IA (bloc 5)
# ---------------------------------------------------------------
class Assistant(tk.Frame):
    # Les boutons d'exemple : (texte du bouton, question envoyée) — une par capacité de l'agent
    EXEMPLES = [("Meilleure heure", "À quelle heure c'est le moins risqué d'aller à Angré ?"),
                ("Faits d'un quartier", "Qu'est-ce qui se passe à Niangon ?"),
                ("Un trajet", "Je vais de Yopougon au Plateau vers 22h, c'est risqué ?"),
                ("Quartiers calmes", "Quel quartier de Cocody est le plus calme ce soir ?"),
                ("Tendance", "Est-ce qu'Abobo devient plus dangereux ?")]

    def __init__(self, parent):
        super().__init__(parent, bg=FOND)
        self.historique = []
        titre(self, "Assistant").pack(fill="x")
        texte(self, "Posez votre question sur la sécurité à Abidjan. L'assistant utilise les données de SafeZone.",
              fond=FOND).pack(fill="x", pady=(0, 12))

        # La zone de discussion (on ne peut pas écrire dedans : state="disabled")
        cadre = bloc_blanc(self)
        cadre.pack(fill="both", expand=True)
        self.discussion = tk.Text(cadre, wrap="word", bg="#F7F8FA", fg=BLEU_NUIT, font=(POLICE, 10),
                                  relief="flat", padx=14, pady=12, state="disabled")
        self.discussion.pack(fill="both", expand=True)
        # Des styles de texte : le nom de celui qui parle, et la liste des outils
        self.discussion.tag_configure("utilisateur", foreground=ORANGE, font=(POLICE, 10, "bold"), spacing1=10)
        self.discussion.tag_configure("assistant", foreground=BLEU_NUIT, font=(POLICE, 10, "bold"), spacing1=10)
        self.discussion.tag_configure("outils", foreground="#7A8696", font=(POLICE, 8, "italic"))
        self.ecrire("Assistant", "Bonjour ! Demandez-moi par exemple à quelle heure aller quelque part, "
                                 "ce qui se passe dans un quartier, ou si un trajet est risqué.")

        # Les boutons d'exemple
        exemples = tk.Frame(self, bg=FOND)
        exemples.pack(fill="x", pady=(10, 0))
        for nom, question in self.EXEMPLES:
            ttk.Button(exemples, text=nom, command=lambda q=question: self.poser(q)).pack(side="left", padx=(0, 6))

        # Le champ de saisie et le bouton « Envoyer »
        saisie = tk.Frame(self, bg=FOND)
        saisie.pack(fill="x", pady=(10, 0))
        self.question = ttk.Entry(saisie, font=(POLICE, 11))
        self.question.pack(side="left", fill="x", expand=True, ipady=4)
        self.question.bind("<Return>", lambda _: self.poser(self.question.get()))
        self.bouton = tk.Button(saisie, text="Envoyer", bg=ORANGE, fg=BLANC, relief="flat", padx=16,
                                font=(POLICE, 10, "bold"), cursor="hand2",
                                command=lambda: self.poser(self.question.get()))
        self.bouton.pack(side="left", padx=(8, 0), fill="y")

    def ecrire(self, qui: str, message: str, consultees: list | None = None):
        """Ajoute un message à la discussion (qui parle, le texte, puis les données consultées)."""
        self.discussion.config(state="normal")
        self.discussion.insert("end", f"{qui}\n", "utilisateur" if qui == "Vous" else "assistant")
        self.discussion.insert("end", message.replace("**", "") + "\n")
        if consultees:
            self.discussion.insert("end", f"Données consultées : {', '.join(consultees)}\n", "outils")
        self.discussion.config(state="disabled")
        self.discussion.see("end")

    def poser(self, question: str):
        """Envoie une question à l'agent (en arrière-plan)."""
        question = question.strip()
        if not question or str(self.bouton["state"]) == "disabled":
            return
        if len(question) > 500:
            self.ecrire("Assistant", "Votre question est trop longue (500 caractères au plus). Raccourcissez-la.")
            return
        self.question.delete(0, "end")
        self.ecrire("Vous", question)
        self.ecrire("Assistant", "… je réfléchis (cela peut prendre quelques secondes)")
        self.bouton.config(state="disabled")
        historique = list(self.historique)
        en_arriere_plan(self, lambda: envoyer_api("/assistant", {"question": question, "historique": historique}),
                        lambda resultat: self.reponse(question, resultat), self.erreur)

    def effacer_attente(self):
        """Enlève le message « je réfléchis » (les 2 dernières lignes)."""
        self.discussion.config(state="normal")
        self.discussion.delete("end-3l", "end-1c")
        self.discussion.config(state="disabled")
        self.bouton.config(state="normal")

    def reponse(self, question, resultat):
        """L'agent a répondu : on affiche la réponse et on la garde dans l'historique."""
        self.effacer_attente()
        self.ecrire("Assistant", resultat["reponse"], resultat.get("donnees_consultees"))
        self.historique += [{"role": "user", "contenu": question},
                            {"role": "assistant", "contenu": resultat["reponse"]}]

    def erreur(self, erreur):
        self.effacer_attente()
        self.ecrire("Assistant", f"Désolé, je ne peux pas répondre : {message_erreur(erreur)}")


# ---------------------------------------------------------------
# 8) La fenêtre principale : menu à gauche, écran choisi à droite
# ---------------------------------------------------------------
class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SafeZone Abidjan")
        self.minsize(980, 600)
        self.state("zoomed")
        self.configure(bg=FOND)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", rowheight=26, font=(POLICE, 9))
        style.configure("Treeview.Heading", font=(POLICE, 9, "bold"))

        # Le menu bleu nuit, à gauche
        menu = tk.Frame(self, bg=BLEU_NUIT, width=220)
        menu.pack(side="left", fill="y")
        menu.pack_propagate(False)
        logo = tk.Frame(menu, bg=BLEU_NUIT)
        logo.pack(anchor="w", padx=20, pady=(24, 28))
        tk.Label(logo, text="SafeZone", bg=BLEU_NUIT, fg=BLANC, font=(POLICE, 16, "bold")).pack(side="left")
        tk.Label(logo, text=" Abidjan", bg=BLEU_NUIT, fg=OR, font=(POLICE, 16, "bold")).pack(side="left")

        # La zone de droite, où s'affiche l'écran choisi
        self.zone = tk.Frame(self, bg=FOND, padx=22, pady=14)
        self.zone.pack(side="left", fill="both", expand=True)

        # Chaque écran est créé une seule fois, puis affiché ou caché.
        # Le premier écran est celui dont l'utilisateur a besoin : calculer son risque.
        self.ecrans = {
            "Calculer mon risque": CalculRisque(self.zone, self.demander_assistant),
            "Tableau de bord": TableauDeBord(self.zone),
            "Incidents": Incidents(self.zone),
            "Assistant": Assistant(self.zone),
        }
        self.boutons = {}
        for nom in self.ecrans:
            bouton = tk.Button(menu, text=f"  {nom}", anchor="w", bg=BLEU_NUIT, fg=BLANC, relief="flat",
                               activebackground=BLEU_NUIT_2, activeforeground=BLANC, font=(POLICE, 11),
                               padx=16, pady=10, cursor="hand2", command=lambda n=nom: self.montrer(n))
            bouton.pack(fill="x")
            self.boutons[nom] = bouton
        self.montrer("Calculer mon risque")

    def montrer(self, nom: str):
        """Affiche un écran et cache les autres ; le bouton du menu correspondant est mis en valeur."""
        for autre, ecran in self.ecrans.items():
            ecran.pack_forget()
            actif = autre == nom
            self.boutons[autre].config(bg=BLEU_NUIT_2 if actif else BLEU_NUIT,
                                       font=(POLICE, 11, "bold" if actif else "normal"))
        self.ecrans[nom].pack(fill="both", expand=True)

    def demander_assistant(self, question: str):
        """Le bouton « Demander conseil à l'assistant » du calcul : on change d'écran et on pose la question."""
        self.montrer("Assistant")
        self.ecrans["Assistant"].poser(question)


if __name__ == "__main__":
    Application().mainloop()
