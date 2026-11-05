import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';

/// Un compte : le nom, l'e-mail et le jeton de connexion
class Compte {
  final String nom;
  final String email;
  final String jeton;
  const Compte(this.nom, this.email, this.jeton);
}

/// Le compte connecté, utilisable partout dans l'appli (null = invité, sans compte)
Compte? compteConnecte;

/// Après l'inscription ou la connexion : on garde le compte en mémoire sur le téléphone
Future<void> seSouvenir(Map<String, dynamic> reponseApi) async {
  final memoire = await SharedPreferences.getInstance();
  await memoire.setString('nom', reponseApi['nom']);
  await memoire.setString('email', reponseApi['email']);
  await memoire.setString('jeton', reponseApi['jeton']);
  compteConnecte = Compte(reponseApi['nom'], reponseApi['email'], reponseApi['jeton']);
}

/// Au démarrage de l'appli : y a-t-il un compte en mémoire, et son jeton est-il toujours valable ?
Future<Compte?> retrouverCompte() async {
  final memoire = await SharedPreferences.getInstance();
  final jeton = memoire.getString('jeton');
  if (jeton == null) return null;

  // Le compte gardé en mémoire (utilisé si l'API ne répond pas, par exemple sans internet)
  compteConnecte = Compte(memoire.getString('nom') ?? '', memoire.getString('email') ?? '', jeton);
  try {
    final moi = await lireApi('/comptes/moi', jeton: jeton);
    compteConnecte = Compte(moi['nom'], moi['email'], jeton);
  } catch (erreur) {
    if (erreur.toString().contains('pas connecté')) {
      await oublier();
    }
  }
  return compteConnecte;
}

/// Se déconnecter : on prévient l'API (le badge ne marchera plus), puis on vide la mémoire
Future<void> seDeconnecter() async {
  final jeton = compteConnecte?.jeton;
  if (jeton != null) {
    try {
      await envoyerApi('/comptes/deconnexion', {'jeton': jeton});
    } catch (_) {}
  }
  await oublier();
}

/// Modifier mon nom : l'API le change dans la base, puis on le change sur le téléphone
Future<void> changerNom(String nouveauNom) async {
  final compte = compteConnecte!;
  final reponse = await envoyerApi('/comptes/moi', {'nom': nouveauNom}, methode: 'PUT', jeton: compte.jeton);
  final memoire = await SharedPreferences.getInstance();
  await memoire.setString('nom', reponse['nom']);
  compteConnecte = Compte(reponse['nom'], compte.email, compte.jeton);
}

/// Supprimer mon compte : l'API l'efface de la base, puis on vide la mémoire du téléphone
Future<void> supprimerCompte() async {
  await envoyerApi('/comptes/moi', {}, methode: 'DELETE', jeton: compteConnecte!.jeton);
  await oublier();
}

/// Efface le compte de la mémoire du téléphone
Future<void> oublier() async {
  final memoire = await SharedPreferences.getInstance();
  await memoire.remove('nom');
  await memoire.remove('email');
  await memoire.remove('jeton');
  compteConnecte = null;
}
