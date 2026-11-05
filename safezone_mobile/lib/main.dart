import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'assistant.dart';
import 'carte.dart';
import 'compte.dart';
import 'connexion.dart';
import 'historique.dart';
import 'profil.dart';
import 'theme.dart';

void main() {
  runApp(const SafeZoneApp());
}

/// L'application : son nom, ses couleurs, sa police et son premier écran
class SafeZoneApp extends StatelessWidget {
  const SafeZoneApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SafeZone Abidjan',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: orange, primary: orange, surface: Colors.white),
        scaffoldBackgroundColor: fond,
        textTheme: GoogleFonts.publicSansTextTheme(),
      ),
      home: const EcranDemarrage(),
    );
  }
}

/// Le tout premier écran : on regarde si un compte est gardé en mémoire sur le téléphone.
///   - oui : on ouvre directement l'appli (pas besoin de se reconnecter)
///   - non : on montre l'écran de connexion
class EcranDemarrage extends StatefulWidget {
  const EcranDemarrage({super.key});

  @override
  State<EcranDemarrage> createState() => _EcranDemarrageState();
}

class _EcranDemarrageState extends State<EcranDemarrage> {
  final verification = retrouverCompte();

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Compte?>(
      future: verification,
      builder: (context, etat) {
        // Pendant la vérification (une fraction de seconde) : le logo sur fond bleu nuit
        if (etat.connectionState != ConnectionState.done) {
          return const Scaffold(
            backgroundColor: bleuNuit,
            body: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
              Bouclier(taille: 48),
              SizedBox(height: 12),
              Logo(taille: 28),
            ])),
          );
        }
        // Vérification finie : connecté -> l'appli ; pas connecté -> l'écran de connexion
        return etat.data != null ? const EcranPrincipal() : const EcranConnexion();
      },
    );
  }
}

/// L'écran principal avec la barre du bas : Mon risque, Assistant, Historique, Profil
class EcranPrincipal extends StatefulWidget {
  const EcranPrincipal({super.key});

  @override
  State<EcranPrincipal> createState() => _EcranPrincipalState();
}

class _EcranPrincipalState extends State<EcranPrincipal> {
  int onglet = 0;
  // Une « clé » pour pouvoir envoyer une question à l'assistant depuis l'écran du risque
  final cleAssistant = GlobalKey<EcranAssistantState>();
  // Augmente à chaque ouverture de l'onglet Historique : l'écran est recréé et recharge les dernières recherches
  int ouverturesHistorique = 0;

  /// Le bouton « Demander conseil à l'assistant » : on va sur l'onglet Assistant et on pose la question
  void ouvrirAssistant(String question) {
    setState(() => onglet = 1);
    cleAssistant.currentState?.poserQuestion(question);
  }

  @override
  Widget build(BuildContext context) {
    final ecrans = <Widget>[
      EcranCarte(demanderAssistant: ouvrirAssistant),
      EcranAssistant(key: cleAssistant, retour: () => setState(() => onglet = 0)),
      EcranHistorique(key: ValueKey(ouverturesHistorique)),
      const EcranProfil(),
    ];
    return Scaffold(
      // IndexedStack garde chaque écran en mémoire (la conversation n'est pas perdue)
      body: IndexedStack(index: onglet, children: ecrans),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: bordure))),
        child: SafeArea(
          top: false,
          child: Row(children: [
            boutonOnglet(0, Icons.shield_outlined, 'Mon risque'),
            boutonOnglet(1, Icons.chat_bubble_outline, 'Assistant'),
            boutonOnglet(2, Icons.schedule, 'Historique'),
            boutonOnglet(3, Icons.person_outline, 'Profil'),
          ]),
        ),
      ),
    );
  }

  /// Un bouton de la barre du bas : orange quand il est actif, gris sinon
  Widget boutonOnglet(int numero, IconData icone, String texte) {
    final actif = numero == onglet;
    final couleur = actif ? orange : grisTexte;
    return Expanded(
      child: InkWell(
        onTap: () => setState(() {
          onglet = numero;
          if (numero == 2) ouverturesHistorique++;
        }),
        child: SizedBox(
          height: 60,
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(icone, color: couleur),
            const SizedBox(height: 2),
            Text(texte,
                style: TextStyle(
                    color: couleur, fontSize: 12, fontWeight: actif ? FontWeight.w700 : FontWeight.w600)),
          ]),
        ),
      ),
    );
  }
}