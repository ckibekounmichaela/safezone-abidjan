# SafeZone Abidjan

**Savoir avant de sortir.** SafeZone Abidjan estime le risque d'agression dans une commune ou un quartier d'Abidjan,
à une heure donnée, selon la façon de se déplacer (à pied, moto, taxi, voiture, bus) et l'éclairage de la rue.

Les données viennent des faits divers publiés dans la presse depuis 2010 (Abidjan.net, Koaci, Connectionivoirienne, AIP).
Une IA lit chaque article, un modèle XGBoost prévoit les agressions par commune, et une API sert trois applications
(web, mobile, desktop) avec un assistant IA.

Projet de soutenance Développeur Data IA — Simplon Côte d'Ivoire.

## En ligne

- Site web : https://safezone-abidjan.onrender.com
- API et documentation : https://safezone-abidjan.onrender.com/docs
- Hébergement : Render (API + site), Neon (PostgreSQL). La première visite après une période d'inactivité peut prendre
  environ une minute (offre gratuite de Render).
- L'APK Android et l'application desktop utilisent cette API en ligne par défaut.

## Ce qu'il y a dans le dossier

```
soutenance/
├── config.py               réglages communs : sources, communes, 161 quartiers, listes de réponses autorisées
├── requirements.txt        les bibliothèques Python à installer
├── .env                    clé DeepSeek et mot de passe PostgreSQL (à créer, ne jamais partager)
├── scripts/
│   ├── scraping.py         1. collecte des articles
│   ├── nettoyage.py        2. doublons, articles hors sujet
│   ├── extraction.py       3. l'IA remplit une fiche par article (type, commune, quartier, heure, déplacement, éclairage...)
│   ├── remplir.py          4. crée les tables PostgreSQL et les remplit
│   ├── eda.py              5. graphiques et chiffres clés (dossier graphiques/)
│   ├── entrainement.py     6. concours de 3 modèles, XGBoost gagnant (dossier modeles/)
│   ├── api.py              l'API FastAPI : calcul du risque, comptes, assistant, site web
│   ├── agent.py            l'agent IA (LangChain + DeepSeek, 9 outils)
│   └── tests.py            les tests automatiques
├── donnees/                les fichiers CSV de chaque étape
├── graphiques/             les graphiques et la carte
├── modeles/                le modèle entraîné et ses prévisions
├── web/                    le site (HTML, CSS, JavaScript, carte Leaflet)
├── desktop/                l'application desktop (Python, Tkinter)
└── safezone_mobile/        l'application mobile (Flutter)
```

## Installation (une seule fois)

1. Installer **Python 3.12 ou plus**, **PostgreSQL** (avec pgAdmin) et, pour le mobile, **Flutter** et Android Studio.
2. Installer les bibliothèques Python, depuis le dossier `soutenance` :
   ```
   pip install -r requirements.txt
   ```
3. Dans pgAdmin, créer une base vide nommée **safezone** (utilisateur `postgres`, sur cet ordinateur, port 5432).
4. Créer le fichier `.env` dans le dossier `soutenance` (une ligne par réglage, sans espace ni guillemets) :
   ```
   DEEPSEEK_API_KEY=votre_cle_deepseek
   PG_MOT_DE_PASSE=votre_mot_de_passe_postgres
   ```
5. Remplir la base et entraîner le modèle (les fichiers de `donnees/` sont déjà prêts) :
   ```
   python scripts/remplir.py
   python scripts/eda.py
   python scripts/entrainement.py
   ```

Pour refaire toute la collecte : `scraping.py`, puis `nettoyage.py`, puis `extraction.py` (environ 1 h 30 en tout), puis l'étape 5.

**Données publiées sur GitHub** : le texte complet des articles (`donnees/brut/articles_bruts.csv` et
`donnees/articles_propres.csv`) n'est **pas** publié, pour respecter les droits des journaux et la vie privée des
personnes citées. Le dépôt contient les fiches extraites par l'IA (`donnees/articles_extraits.csv` : type, commune,
quartier, heure, déplacement, résumé court et lien vers l'article d'origine), qui suffisent pour remplir la base,
analyser et entraîner le modèle. `scraping.py` puis `nettoyage.py` recréent les textes complets si besoin.

## Lancer les applications

| Application | Commande (depuis `soutenance`) | Où la voir |
| --- | --- | --- |
| API + site web (local) | `python scripts/api.py` | http://127.0.0.1:8000 (site) et http://127.0.0.1:8000/docs (API) |
| Desktop | `python desktop/safezone_desktop.py`, ou double-clic sur `desktop/SafeZone Abidjan.exe` | une fenêtre s'ouvre |
| Mobile | `cd safezone_mobile` puis `flutter run` | émulateur ou téléphone branché |
| Agent seul | `python scripts/agent.py` | discussion dans le terminal |

Le desktop et le mobile utilisent l'API en ligne. Pour utiliser l'API locale :
`set SAFEZONE_API=http://127.0.0.1:8000` (desktop) ou `flutter run --dart-define=API=http://10.0.2.2:8000` (émulateur).

**APK Android** : `cd safezone_mobile` puis `flutter build apk --release` crée
`safezone_mobile/build/app/outputs/flutter-apk/app-release.apk`, installable sur n'importe quel téléphone Android.

**Appli desktop en `.exe`** (sans installer Python sur l'ordinateur qui l'utilise) :
```
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name "SafeZone Abidjan" --collect-data tkintermapview --distpath desktop desktop/safezone_desktop.py
```

## Comptes et historique

Sur le site (page « Mon compte ») et sur l'appli mobile (onglet « Profil »), on peut créer un compte, se connecter,
changer son nom, se déconnecter et supprimer son compte. Une personne connectée retrouve ses calculs de risque
dans « Mes recherches » (site) ou « Historique » (mobile), et peut les effacer.
Protections : mot de passe et badge de connexion gardés en empreinte, badge valable 30 jours,
compte bloqué 15 minutes après 10 mots de passe faux, 20 questions par heure à l'assistant.

## Tests

```
python scripts/tests.py            # 39 tests : risque, comptes, historique, protections, assistant (gratuit)
python scripts/tests.py --agent    # en plus, 4 scénarios posés au vrai agent IA (quelques centimes DeepSeek)
cd safezone_mobile && flutter test # test de l'écran de connexion mobile
```

## Comment le score est calculé

**Score = score de la zone et de l'heure × facteur déplacement × facteur éclairage** (de 0 à 100)

- **Zone et heure** : prévision XGBoost de la commune ÷ plus forte prévision d'Abidjan × part des agressions à cette heure
  (comparée au moment le plus risqué) × 100. Un quartier corrige ce score de 0,5 à 1,5.
- **Déplacement** : part de ce moyen chez nos victimes ÷ part de ce moyen dans les trajets à Abidjan
  (enquête ménages-déplacements 2013, JICA / MCLAU), entre 0,5 et 1,5.
- **Rue sombre** : × 1,15 le soir et la nuit (études de Welsh et Farrington sur l'éclairage public).
- **Niveau** : faible sous 20, moyen de 20 à 49, élevé à partir de 50.

## Limites

Le score repose sur les agressions **rapportées par la presse** : c'est une estimation pour comparer des lieux et des
heures, pas une certitude. L'heure n'est connue que dans 53 % des articles et le quartier dans 63 %.

**À refaire chaque trimestre** : les prévisions du modèle portent sur un trimestre (aujourd'hui le 4e trimestre 2026).
Au début du trimestre suivant (janvier 2027), relancer `python scripts/entrainement.py` pour les mettre à jour.
