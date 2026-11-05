import 'package:flutter/material.dart';

import 'api.dart';
import 'compte.dart';
import 'connexion.dart';
import 'theme.dart';

class EcranHistorique extends StatefulWidget {
  const EcranHistorique({super.key});

  @override
  State<EcranHistorique> createState() => _EcranHistoriqueState();
}

class _EcranHistoriqueState extends State<EcranHistorique> {
  late Future<List<dynamic>> recherches;

  // Les codes envoyés à l'API -> le texte affiché
  static const deplacements = {
    'pied': 'à pied',
    'moto': 'à moto',
    'taxi': 'en taxi / woro-woro / gbaka',
    'voiture': 'en voiture',
    'bus': 'en bus',
  };

  @override
  void initState() {
    super.initState();
    recherches = charger();
  }

  /// Demande à l'API les dernières recherches de l'utilisateur connecté (liste vide pour un invité)
  Future<List<dynamic>> charger() async {
    final compte = compteConnecte;
    if (compte == null) return [];
    return await lireApi('/recherches', jeton: compte.jeton) as List<dynamic>;
  }

  /// Recharge la liste (après un effacement, ou en tirant l'écran vers le bas)
  /// Les accolades { } sont importantes : setState ne doit rien renvoyer (pas de « => »), sinon Flutter refuse.
  void recharger() => setState(() {
        recherches = charger();
      });

  /// Efface une recherche (glissée vers la gauche), ou toutes si numero est null
  Future<void> effacer(int? numero) async {
    final chemin = numero == null ? '/recherches' : '/recherches/$numero';
    try {
      await envoyerApi(chemin, {}, methode: 'DELETE', jeton: compteConnecte!.jeton);
    } catch (erreur) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(erreur.toString().replaceFirst('Exception: ', ''))));
      }
    }
    recharger();
  }

  /// « Tout effacer » : on demande d'abord confirmation
  Future<void> toutEffacer() async {
    final confirme = await showDialog<bool>(
      context: context,
      builder: (fenetre) => AlertDialog(
        title: const Text("Effacer l'historique ?"),
        content: const Text('Toutes vos recherches seront effacées.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(fenetre, false), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(fenetre, true), child: const Text('Effacer')),
        ],
      ),
    );
    if (confirme == true) await effacer(null);
  }

  @override
  Widget build(BuildContext context) {
    final connecte = compteConnecte != null;
    return Column(children: [
      // ---------- En-tête bleu nuit, avec « Tout effacer » pour un utilisateur connecté ----------
      Container(
        width: double.infinity,
        color: bleuNuit,
        child: SafeArea(
          bottom: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
            child: Row(children: [
              Expanded(child: Text('Mes recherches', style: titre(20, couleur: Colors.white))),
              if (connecte)
                TextButton(
                  onPressed: toutEffacer,
                  style: TextButton.styleFrom(foregroundColor: Colors.white),
                  child: const Text('Tout effacer'),
                ),
            ]),
          ),
        ),
      ),
      Expanded(child: connecte ? liste() : invite()),
    ]);
  }

  /// Pour un invité : pourquoi il n'y a pas d'historique, et un bouton pour se connecter
  Widget invite() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.schedule, size: 48, color: grisTexte),
          const SizedBox(height: 12),
          const Text(
            'Connectez-vous pour garder vos recherches et les retrouver sur tous vos appareils.',
            textAlign: TextAlign.center,
            style: TextStyle(color: grisTexte, fontSize: 15),
          ),
          const SizedBox(height: 16),
          BoutonOrange('Se connecter ou créer un compte',
              onPressed: () => Navigator.of(context)
                  .pushReplacement(MaterialPageRoute(builder: (_) => const EcranConnexion()))),
        ]),
      ),
    );
  }

  /// Pour un utilisateur connecté : la liste de ses recherches, la plus récente en haut
  Widget liste() {
    return FutureBuilder<List<dynamic>>(
      future: recherches,
      builder: (context, etat) {
        if (etat.hasError) return Center(child: MessageErreur(etat.error!, reessayer: recharger));
        if (!etat.hasData) return const Center(child: CircularProgressIndicator());
        final liste = etat.data!;
        if (liste.isEmpty) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text('Aucune recherche pour le moment.\nCalculez un risque dans « Mon risque ».',
                  textAlign: TextAlign.center, style: TextStyle(color: grisTexte, fontSize: 15)),
            ),
          );
        }
        return RefreshIndicator(
          onRefresh: () async => recharger(),
          child: ListView.builder(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
            itemCount: liste.length + 1,
            itemBuilder: (context, i) {
              if (i == 0) {
                return const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text('Glissez une recherche vers la gauche pour l’effacer.',
                      style: TextStyle(color: grisTexte, fontSize: 13)),
                );
              }
              final r = liste[i - 1];
              // « Angré (Cocody) » ou « Cocody »
              final lieu = r['quartier'] != null ? '${r['quartier']} (${r['commune']})' : r['commune'];
              // « à 21 h · à pied · rue sombre » (on n'écrit que ce qui a été choisi)
              final details = [
                'à ${r['heure']} h',
                if (deplacements[r['deplacement']] != null) deplacements[r['deplacement']]!,
                if (r['eclairage'] == 'sombre') 'rue sombre',
                if (r['eclairage'] == 'eclairee') 'rue éclairée',
              ].join(' · ');
              return Dismissible(
                key: ValueKey(r['id_recherche']),
                direction: DismissDirection.endToStart,
                background: Container(
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: 20),
                  margin: const EdgeInsets.only(bottom: 10),
                  decoration: BoxDecoration(color: const Color(0xFF8E1D17), borderRadius: BorderRadius.circular(16)),
                  child: const Icon(Icons.delete_outline, color: Colors.white),
                ),
                onDismissed: (_) {
                  setState(() => liste.remove(r));
                  effacer(r['id_recherche']);
                },
                child: Container(
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.all(14),
                  decoration: blocBlanc(),
                  child: Row(children: [
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(lieu, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                        const SizedBox(height: 2),
                        Text(details, style: const TextStyle(color: Color(0xFF2B3A4D))),
                        const SizedBox(height: 2),
                        Text('Calculé le ${r['date']}', style: const TextStyle(fontSize: 12, color: grisTexte)),
                      ]),
                    ),
                    const SizedBox(width: 8),
                    // À droite : le niveau et le score, de la couleur du niveau
                    Pastille(r['niveau'], texte: '${r['niveau']} · ${r['score']}'),
                  ]),
                ),
              );
            },
          ),
        );
      },
    );
  }
}
