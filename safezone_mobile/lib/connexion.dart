import 'package:flutter/material.dart';

import 'api.dart';
import 'compte.dart';
import 'main.dart';
import 'theme.dart';

class EcranConnexion extends StatefulWidget {
  const EcranConnexion({super.key});

  @override
  State<EcranConnexion> createState() => _EcranConnexionState();
}

class _EcranConnexionState extends State<EcranConnexion> {
  bool creation = false;
  final champNom = TextEditingController();
  final champEmail = TextEditingController();
  final champMotDePasse = TextEditingController();
  bool cacherMotDePasse = true;
  bool enCours = false;
  String? erreur;

  /// Ouvre l'écran principal (pushReplacement : on ne peut pas revenir en arrière vers la connexion)
  void entrer() {
    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const EcranPrincipal()));
  }

  /// Le bouton orange : vérifie les champs, puis demande à l'API de créer le compte ou de connecter
  Future<void> valider() async {
    final nom = champNom.text.trim();
    final email = champEmail.text.trim();
    final motDePasse = champMotDePasse.text;

    // 1) On vérifie d'abord sur le téléphone (réponse immédiate, sans attendre l'API)
    String? probleme;
    if (creation && nom.length < 2) probleme = 'Indiquez votre nom.';
    if (!email.contains('@') || !email.contains('.')) probleme ??= "L'adresse e-mail n'est pas valide.";
    if (motDePasse.length < 6) probleme ??= 'Le mot de passe doit faire au moins 6 caractères.';
    if (probleme != null) {
      setState(() => erreur = probleme);
      return;
    }

    // 2) On envoie à l'API
    setState(() {
      enCours = true;
      erreur = null;
    });
    try {
      final reponse = creation
          ? await envoyerApi('/comptes/inscription', {'nom': nom, 'email': email, 'mot_de_passe': motDePasse})
          : await envoyerApi('/comptes/connexion', {'email': email, 'mot_de_passe': motDePasse});
      await seSouvenir(reponse);
      if (mounted) entrer();
    } catch (e) {
      // ex. « E-mail ou mot de passe incorrect. » ou « Un compte existe déjà avec cet e-mail. »
      setState(() => erreur = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => enCours = false);
    }
  }

  /// Le style commun des champs (fond blanc, bords arrondis)
  InputDecoration styleChamp(String exemple, {Widget? aDroite}) => InputDecoration(
        hintText: exemple,
        filled: true,
        fillColor: Colors.white,
        suffixIcon: aDroite,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: bordureChamp)),
      );

  /// Un titre de champ en gras, au-dessus du champ
  Widget etiquette(String texte) => Padding(
        padding: const EdgeInsets.only(top: 14, bottom: 6),
        child: Text(texte, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
      );

  /// Un onglet (« Se connecter » ou « Créer un compte ») : bleu nuit quand il est choisi
  Widget onglet(String texte, bool pourCreation) {
    final actif = creation == pourCreation;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() {
          creation = pourCreation;
          erreur = null;
        }),
        child: Container(
          height: 44,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: actif ? bleuNuit : Colors.transparent,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(texte,
              style: TextStyle(color: actif ? Colors.white : bleuNuit, fontWeight: FontWeight.w700)),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SingleChildScrollView(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          // ---------- Bandeau bleu nuit arrondi en bas ----------
          Container(
            padding: const EdgeInsets.fromLTRB(24, 64, 24, 32),
            decoration: const BoxDecoration(
              color: bleuNuit,
              borderRadius: BorderRadius.vertical(bottom: Radius.circular(28)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(color: bleuNuit2, borderRadius: BorderRadius.circular(16)),
                child: const Bouclier(taille: 30),
              ),
              const SizedBox(height: 16),
              const Logo(taille: 32),
              const SizedBox(height: 6),
              const Text('Savoir avant de sortir.', style: TextStyle(color: grisClair)),
            ]),
          ),

          // ---------- Le formulaire ----------
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 24, 24, 24),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              // Les deux onglets
              Container(
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: bordure),
                ),
                child: Row(children: [onglet('Se connecter', false), onglet('Créer un compte', true)]),
              ),

              // Le nom : seulement pour créer un compte
              if (creation) ...[
                etiquette('Votre nom'),
                TextField(
                  controller: champNom,
                  textCapitalization: TextCapitalization.words,
                  decoration: styleChamp('ex. Awa Koné'),
                ),
              ],
              etiquette('Adresse e-mail'),
              TextField(
                controller: champEmail,
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                decoration: styleChamp('nom@exemple.com'),
              ),
              etiquette('Mot de passe'),
              TextField(
                controller: champMotDePasse,
                obscureText: cacherMotDePasse,
                onSubmitted: (_) => valider(),
                decoration: styleChamp(
                  creation ? '6 caractères minimum' : 'Votre mot de passe',
                  aDroite: IconButton(
                    tooltip: cacherMotDePasse ? 'Afficher le mot de passe' : 'Cacher le mot de passe',
                    icon: Icon(cacherMotDePasse ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                    onPressed: () => setState(() => cacherMotDePasse = !cacherMotDePasse),
                  ),
                ),
              ),

              // Le message d'erreur, en rouge
              if (erreur != null)
                Container(
                  margin: const EdgeInsets.only(top: 14),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(color: const Color(0xFFF6D5D2), borderRadius: BorderRadius.circular(10)),
                  child: Text(erreur!, style: const TextStyle(color: Color(0xFF8E1D17))),
                ),

              const SizedBox(height: 20),
              BoutonOrange(
                enCours ? 'Patientez…' : (creation ? 'Créer mon compte' : 'Se connecter'),
                onPressed: enCours ? null : valider,
              ),
              const SizedBox(height: 20),
              TextButton(
                onPressed: entrer,
                child: const Text('Continuer sans compte', style: TextStyle(fontWeight: FontWeight.w600)),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}
