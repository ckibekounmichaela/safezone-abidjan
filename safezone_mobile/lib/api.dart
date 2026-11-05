import 'dart:convert';

import 'package:http/http.dart' as http;

// API en ligne par défaut ; en local : --dart-define=API=http://10.0.2.2:8000 (émulateur)
const String adresseApi = String.fromEnvironment('API', defaultValue: 'https://safezone-abidjan.onrender.com');

const serviceIndisponible = 'Le service ne répond pas. Vérifiez votre connexion Internet et réessayez.';

/// Erreur affichable telle quelle à l'utilisateur (message en français).
class ErreurApi implements Exception {
  final String message;
  const ErreurApi(this.message);

  @override
  String toString() => message;
}

/// Envoie la demande ; les erreurs réseau et techniques deviennent un message simple.
Future<dynamic> appelerApi(http.BaseRequest demande, Duration delai) async {
  final http.Response reponse;
  try {
    reponse = await http.Response.fromStream(await demande.send().timeout(delai));
  } catch (_) {
    throw const ErreurApi(serviceIndisponible);
  }
  final contenu = jsonDecode(utf8.decode(reponse.bodyBytes));
  if (reponse.statusCode != 200) {
    final detail = contenu is Map ? contenu['detail'] : null;
    if (detail is String && detail != 'Not Found') throw ErreurApi(detail);
    throw ErreurApi(reponse.statusCode == 422 ? 'Les informations saisies ne sont pas valides.' : serviceIndisponible);
  }
  return contenu;
}

/// Demande des données à l'API (GET). jeton : le badge de connexion, si l'adresse en a besoin.
Future<dynamic> lireApi(String chemin, {String? jeton}) {
  final demande = http.Request('GET', Uri.parse('$adresseApi$chemin'));
  if (jeton != null) demande.headers['Authorization'] = 'Bearer $jeton';
  return appelerApi(demande, const Duration(seconds: 60));
}

/// Envoie des données à l'API. methode : 'POST' (par défaut), 'PUT' ou 'DELETE'.
Future<dynamic> envoyerApi(String chemin, Map<String, dynamic> donnees,
    {String methode = 'POST', String? jeton}) {
  final demande = http.Request(methode, Uri.parse('$adresseApi$chemin'));
  demande.headers['Content-Type'] = 'application/json';
  if (jeton != null) demande.headers['Authorization'] = 'Bearer $jeton';
  demande.body = jsonEncode(donnees);
  return appelerApi(demande, const Duration(seconds: 90));
}
