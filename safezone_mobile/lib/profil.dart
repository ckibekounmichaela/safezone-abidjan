import 'package:flutter/material.dart';

import 'compte.dart';
import 'connexion.dart';
import 'theme.dart';

class EcranProfil extends StatefulWidget {
  const EcranProfil({super.key});

  @override
  State<EcranProfil> createState() => _EcranProfilState();
}

class _EcranProfilState extends State<EcranProfil> {
  /// Revient à l'écran de connexion (après « Se déconnecter » ou « Se connecter »)
  void allerConnexion(BuildContext context) {
    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => const EcranConnexion()));
  }

  /// Affiche un petit message en bas de l'écran
  void message(String texte) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(texte)));

  /// « Modifier mon nom » : une fenêtre avec le nom actuel, l'utilisateur le change et valide
  Future<void> modifierNom() async {
    final champ = TextEditingController(text: compteConnecte!.nom);
    final nouveauNom = await showDialog<String>(
      context: context,
      builder: (fenetre) => AlertDialog(
        title: const Text('Modifier mon nom'),
        content: TextField(controller: champ, autofocus: true, decoration: const InputDecoration(labelText: 'Nom')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(fenetre), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(fenetre, champ.text), child: const Text('Enregistrer')),
        ],
      ),
    );
    if (nouveauNom == null) return;
    try {
      await changerNom(nouveauNom);
      setState(() {});
      message('Nom modifié.');
    } catch (erreur) {
      message(erreur.toString().replaceFirst('Exception: ', ''));
    }
  }

  /// « Supprimer mon compte » : on demande confirmation, car on ne peut pas revenir en arrière
  Future<void> supprimer() async {
    final confirme = await showDialog<bool>(
      context: context,
      builder: (fenetre) => AlertDialog(
        title: const Text('Supprimer mon compte ?'),
        content: const Text('Votre compte sera effacé pour de bon. Vous pourrez toujours utiliser SafeZone sans compte.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(fenetre, false), child: const Text('Annuler')),
          FilledButton(
            onPressed: () => Navigator.pop(fenetre, true),
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFF8E1D17)),
            child: const Text('Supprimer'),
          ),
        ],
      ),
    );
    if (confirme != true) return;
    try {
      await supprimerCompte();
      if (mounted) allerConnexion(context);
    } catch (erreur) {
      message(erreur.toString().replaceFirst('Exception: ', ''));
    }
  }

  @override
  Widget build(BuildContext context) {
    final compte = compteConnecte;

    // Une ligne : une icône orange, un titre en gras et un texte gris
    Widget ligne(IconData icone, String titreLigne, String texte) => Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(icone, color: orange),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(titreLigne, style: const TextStyle(fontWeight: FontWeight.w700)),
                Text(texte, style: const TextStyle(color: grisTexte)),
              ]),
            ),
          ]),
        );

    return Column(children: [
      // ---------- En-tête ----------
      Container(
        width: double.infinity,
        color: bleuNuit,
        child: SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Text('Profil', style: titre(20, couleur: Colors.white)),
          ),
        ),
      ),
      Expanded(
        child: ListView(padding: const EdgeInsets.all(16), children: [
          // ---------- Le compte ----------
          Container(
            padding: const EdgeInsets.all(16),
            decoration: blocBlanc(),
            child: Row(children: [
              CircleAvatar(
                backgroundColor: compte != null ? bleuNuit : fond,
                // l'initiale du nom (A pour Awa), ou une silhouette pour un invité
                child: compte != null && compte.nom.isNotEmpty
                    ? Text(compte.nom[0].toUpperCase(),
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700))
                    : const Icon(Icons.person_outline, color: bleuNuit),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(compte?.nom ?? 'Invité', style: const TextStyle(fontWeight: FontWeight.w700)),
                  Text(compte?.email ?? 'Vous utilisez SafeZone sans compte.',
                      style: const TextStyle(color: grisTexte, fontSize: 13)),
                ]),
              ),
            ]),
          ),
          const SizedBox(height: 8),
          if (compte != null) ...[
            // Connecté : « Modifier mon nom », « Se déconnecter » et « Supprimer mon compte »
            OutlinedButton.icon(
              onPressed: modifierNom,
              icon: const Icon(Icons.edit_outlined),
              label: const Text('Modifier mon nom'),
              style: OutlinedButton.styleFrom(
                foregroundColor: bleuNuit,
                side: const BorderSide(color: bordure),
                minimumSize: const Size.fromHeight(46),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () async {
                await seDeconnecter();
                if (context.mounted) allerConnexion(context);
              },
              icon: const Icon(Icons.logout),
              label: const Text('Se déconnecter'),
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF8E1D17),
                side: const BorderSide(color: bordure),
                minimumSize: const Size.fromHeight(46),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
            ),
            TextButton(
              onPressed: supprimer,
              style: TextButton.styleFrom(foregroundColor: const Color(0xFF8E1D17)),
              child: const Text('Supprimer mon compte'),
            ),
          ] else
            // Invité : bouton « Se connecter ou créer un compte »
            BoutonOrange('Se connecter ou créer un compte', onPressed: () => allerConnexion(context)),
          const SizedBox(height: 16),

          // ---------- Numéros d'urgence ----------
          Container(
            padding: const EdgeInsets.all(16),
            decoration: blocBlanc(),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text("Numéros d'urgence", style: titre(18)),
              const SizedBox(height: 12),
              ligne(Icons.local_police_outlined, 'Police secours', '110 · 111 · 170'),
              ligne(Icons.local_fire_department_outlined, 'Sapeurs-pompiers', '180'),
              ligne(Icons.medical_services_outlined, 'SAMU', '185'),
            ]),
          ),
          const SizedBox(height: 16),

          Container(
            padding: const EdgeInsets.all(16),
            decoration: blocBlanc(),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('À savoir', style: titre(18)),
              const SizedBox(height: 8),
              const Text(
                  "Une estimation, pas une certitude : le risque repose sur les faits rapportés par la presse, "
                  "et beaucoup d'incidents ne sont jamais publiés. "
                  'SafeZone évalue des zones et des horaires, jamais des personnes.',
                  style: TextStyle(color: grisTexte)),
            ]),
          ),
        ]),
      ),
    ]);
  }
}
