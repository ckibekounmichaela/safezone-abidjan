// Adresse de l'API. Si le site est servi par l'API (http://localhost:8000/site/),
// on utilise la même adresse ("") ; si on ouvre le fichier directement, on vise l'API sur cet ordinateur.
// (127.0.0.1 plutôt que « localhost » : sous Windows, « localhost » peut perdre 2 secondes à chaque appel)
const API = location.protocol.startsWith("http") ? "" : "http://127.0.0.1:8000";

// Demande des données à l'API (GET) et renvoie le JSON. Exemple : await lireApi("/communes")
// jeton : le badge de connexion, seulement pour les adresses qui en ont besoin (ex. "/recherches")
const SERVICE_INDISPONIBLE = "Le service ne répond pas. Vérifiez votre connexion Internet et réessayez.";

// Appelle l'API ; les erreurs réseau et techniques deviennent un message simple en français.
async function appelerApi(chemin, options) {
  let reponse;
  try {
    reponse = await fetch(API + chemin, options);
  } catch (erreur) {
    throw new Error(SERVICE_INDISPONIBLE);
  }
  if (!reponse.ok) {
    const erreur = await reponse.json().catch(() => ({}));
    const detail = typeof erreur.detail === "string" && erreur.detail !== "Not Found" ? erreur.detail : null;
    if (detail) throw new Error(detail);
    throw new Error(reponse.status === 422 ? "Les informations saisies ne sont pas valides." : SERVICE_INDISPONIBLE);
  }
  return reponse.json();
}

async function lireApi(chemin, jeton = null) {
  const entetes = jeton ? { "Authorization": "Bearer " + jeton } : {};
  return appelerApi(chemin, { headers: entetes });
}

// Envoie des données à l'API et renvoie le JSON. Exemple : la question pour l'assistant
// methode : "POST" (envoyer, par défaut), "PUT" (modifier) ou "DELETE" (supprimer)
// jeton : le badge de connexion, pour les adresses qui en ont besoin (ex. "/comptes/moi")
async function envoyerApi(chemin, donnees, methode = "POST", jeton = null) {
  const entetes = { "Content-Type": "application/json" };
  if (jeton) entetes["Authorization"] = "Bearer " + jeton;
  return appelerApi(chemin, { method: methode, headers: entetes, body: JSON.stringify(donnees) });
}

// ---------- Le compte de l'utilisateur, gardé dans le navigateur (localStorage) ----------
// Après la connexion, on garde le nom, l'e-mail et le badge : en revenant sur le site, on est encore connecté.

// Le compte connecté : { nom, email, jeton }, ou null pour un invité
function monCompte() {
  const jeton = localStorage.getItem("jeton");
  if (!jeton) return null;
  return { nom: localStorage.getItem("nom"), email: localStorage.getItem("email"), jeton };
}

// Après l'inscription ou la connexion : on garde le compte dans le navigateur
function seSouvenir(compte) {
  localStorage.setItem("nom", compte.nom);
  localStorage.setItem("email", compte.email);
  localStorage.setItem("jeton", compte.jeton);
}

// Après la déconnexion ou la suppression du compte : on efface tout
function oublier() {
  ["nom", "email", "jeton"].forEach(cle => localStorage.removeItem(cle));
}

// Protège le texte venant de la base avant de l'insérer dans la page
// (évite qu'un titre d'article contenant du HTML casse la page)
function proteger(texte) {
  const div = document.createElement("div");
  div.textContent = texte ?? "";
  return div.innerHTML;
}

// "élevé" -> classe CSS "eleve" (les classes CSS n'aiment pas les accents)
function classeNiveau(niveau) {
  return { "faible": "faible", "moyen": "moyen", "élevé": "eleve" }[niveau] || "moyen";
}

// Pastille colorée : <span class="pastille eleve">Risque élevé</span>
function pastille(niveau, prefixe = "Risque") {
  return `<span class="pastille ${classeNiveau(niveau)}">${prefixe} ${proteger(niveau)}</span>`;
}

// Message affiché quand l'API ne répond pas
function messageApiArretee(erreur) {
  return `<p class="message-erreur">${proteger(erreur.message)}</p>`;
}

// Date "2026-03-14" -> "14/03/2026"
function dateFr(date) {
  if (!date) return "";
  const [annee, mois, jour] = date.split("-");
  return `${jour}/${mois}/${annee}`;
}

// Les deux listes déroulantes « Commune » puis « Quartier » (rien à taper, pas de faute d'orthographe) :
// choisir une commune remplit la liste avec ses quartiers. Le premier choix « Toute la commune » vaut "".
// Renvoie une fonction pour choisir un lieu depuis le code : choisirLieu("Cocody", "Angré")
async function preparerListesLieu(idCommune, idQuartier) {
  // On demande les communes et les quartiers à l'API, en même temps
  const [communes, quartiers] = await Promise.all([lireApi("/communes"), lireApi("/quartiers/tous")]);
  const ordreFr = (a, b) => a.localeCompare(b, "fr");
  const listeCommunes = document.getElementById(idCommune);
  const listeQuartiers = document.getElementById(idQuartier);
  communes.map(c => c.nom).sort(ordreFr).forEach(nom => listeCommunes.add(new Option(nom, nom)));

  // Remplit la liste des quartiers avec ceux de la commune choisie
  function remplirQuartiers() {
    listeQuartiers.innerHTML = "";
    listeQuartiers.add(new Option("Toute la commune", ""));
    quartiers.filter(q => q.commune === listeCommunes.value)
      .map(q => q.quartier).sort(ordreFr)
      .forEach(nom => listeQuartiers.add(new Option(nom, nom)));
  }
  listeCommunes.addEventListener("change", remplirQuartiers);
  remplirQuartiers();

  // La fonction renvoyée : choisir un lieu depuis le code (ex. quand on arrive depuis l'accueil)
  return function choisirLieu(commune, quartier = null) {
    listeCommunes.value = commune;
    remplirQuartiers();
    listeQuartiers.value = quartier ?? "";
  };
}

// Remplit la liste « À quelle heure ? » : « Maintenant (21 h) », puis 0 h, 1 h ... 23 h
function remplirHeures(idListe) {
  const liste = document.getElementById(idListe);
  const maintenant = new Date().getHours();
  liste.add(new Option(`Maintenant (${maintenant} h)`, maintenant));
  for (let h = 0; h < 24; h++) {
    liste.add(new Option(`${h} h`, h));
  }
}
