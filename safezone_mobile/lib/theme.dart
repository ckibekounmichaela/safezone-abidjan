import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'api.dart';

// Les couleurs de la maquette (0xFF + le code couleur : FF = opaque)
const Color bleuNuit = Color(0xFF0E1A2B);
const Color bleuNuit2 = Color(0xFF1F3048);
const Color orange = Color(0xFFC2550F);
const Color or = Color(0xFFF2B04C);
const Color fond = Color(0xFFF2F4F6);
const Color fondChat = Color(0xFFF7F8FA);
const Color bordure = Color(0xFFD9DEE4);
const Color bordureChamp = Color(0xFFB8C2CD);
const Color grisTexte = Color(0xFF4A5868);
const Color grisClair = Color(0xFFC9D3DE);

/// Police des titres de la maquette (Bricolage Grotesque). Exemple : Text('Profil', style: titre(20))
TextStyle titre(double taille, {Color couleur = bleuNuit}) =>
    GoogleFonts.bricolageGrotesque(fontSize: taille, fontWeight: FontWeight.w700, color: couleur, height: 1.15);

/// Couleurs d'un niveau : [fond clair, texte foncé, couleur vive (carte et barre de progression)]
List<Color> couleursNiveau(String niveau) {
  switch (niveau) {
    case 'élevé': // rouge
      return const [Color(0xFFF6D5D2), Color(0xFF8E1D17), Color(0xFFC0392B)];
    case 'moyen': // jaune-orangé
      return const [Color(0xFFFCEBCB), Color(0xFF7A4A05), Color(0xFFE0A100)];
    default: // faible : vert
      return const [Color(0xFFDDF1E6), Color(0xFF1E5E3F), Color(0xFF2E8B57)];
  }
}

/// « élevé » -> « Élevé » (majuscule à la première lettre)
String majuscule(String texte) => texte.isEmpty ? texte : texte[0].toUpperCase() + texte.substring(1);

/// Pastille colorée (Faible / Moyen / Élevé), aux bords tout ronds
class Pastille extends StatelessWidget {
  final String niveau;
  final String texte;
  const Pastille(this.niveau, {super.key, this.texte = ''});

  @override
  Widget build(BuildContext context) {
    final couleurs = couleursNiveau(niveau);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
      decoration: BoxDecoration(color: couleurs[0], borderRadius: BorderRadius.circular(99)),
      child: Text(texte.isEmpty ? majuscule(niveau) : texte,
          style: TextStyle(color: couleurs[1], fontWeight: FontWeight.w700, fontSize: 13)),
    );
  }
}

/// L'icône bouclier du logo
class Bouclier extends StatelessWidget {
  final double taille;
  const Bouclier({super.key, this.taille = 22});

  @override
  Widget build(BuildContext context) => Icon(Icons.verified_user_outlined, color: or, size: taille);
}

/// Le logo « SafeZone Abidjan »
class Logo extends StatelessWidget {
  final double taille;
  const Logo({super.key, this.taille = 18});

  @override
  Widget build(BuildContext context) {
    // Text.rich : un texte en plusieurs morceaux de styles différents
    return Text.rich(TextSpan(style: titre(taille, couleur: Colors.white), children: const [
      TextSpan(text: 'SafeZone '),
      TextSpan(text: 'Abidjan', style: TextStyle(color: or)),
    ]));
  }
}

/// Bloc blanc arrondi avec bordure (les « cartes » de la maquette).
/// S'utilise ainsi : Container(decoration: blocBlanc(), child: ...)
BoxDecoration blocBlanc({double rayon = 16}) => BoxDecoration(
      color: Colors.white,
      borderRadius: BorderRadius.circular(rayon),
      border: Border.all(color: bordure),
    );

/// Bouton orange plein largeur (ex. « Calculer le risque », « Se connecter »)
class BoutonOrange extends StatelessWidget {
  final String texte;
  final VoidCallback? onPressed;
  final IconData? icone;
  const BoutonOrange(this.texte, {super.key, this.onPressed, this.icone});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 48,
      child: FilledButton.icon(
        onPressed: onPressed,
        icon: icone == null ? const SizedBox.shrink() : Icon(icone, size: 18),
        label: Text(texte, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
        style: FilledButton.styleFrom(
          backgroundColor: orange,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
    );
  }
}

/// Message affiché quand l'API ne répond pas, avec un bouton « Réessayer » (facultatif)
class MessageErreur extends StatelessWidget {
  final Object erreur;
  final VoidCallback? reessayer;
  const MessageErreur(this.erreur, {super.key, this.reessayer});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.wifi_off, size: 40, color: grisTexte),
        const SizedBox(height: 12),
        Text(erreur is ErreurApi ? '$erreur' : serviceIndisponible, textAlign: TextAlign.center),
        if (reessayer != null) ...[
          const SizedBox(height: 12),
          FilledButton(onPressed: reessayer, child: const Text('Réessayer')),
        ],
      ]),
    );
  }
}