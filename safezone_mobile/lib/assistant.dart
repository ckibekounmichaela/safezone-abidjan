import 'package:flutter/material.dart';

import 'api.dart';
import 'theme.dart';

/// Un message de la conversation
class Message {
  final String role;
  final String texte;
  final List<String> outils;
  final List<String> consultees;
  final bool erreur;
  Message(this.role, this.texte, {this.outils = const [], this.consultees = const [], this.erreur = false});
}

class EcranAssistant extends StatefulWidget {
  final VoidCallback retour;
  const EcranAssistant({super.key, required this.retour});

  @override
  State<EcranAssistant> createState() => EcranAssistantState();
}

// La classe est « publique » (sans _) pour que la carte puisse lui envoyer une question
class EcranAssistantState extends State<EcranAssistant> {
  final champ = TextEditingController();
  final defilement = ScrollController();
  final messages = <Message>[];
  bool enAttente = false;

  // Les boutons de suggestion : texte du bouton -> question envoyée (une par capacité de l'agent)
  final suggestions = const {
    'Meilleure heure': "À quelle heure c'est le moins risqué d'aller à Angré ?",
    "Faits d'un quartier": "Qu'est-ce qui se passe à Niangon ?",
    'Un trajet': 'Je vais de Yopougon au Plateau vers 22h, c\'est risqué ?',
    'Quartiers calmes': 'Quel quartier de Cocody est le plus calme ce soir ?',
    'Tendance': "Est-ce qu'Abobo devient plus dangereux ?",
  };

  /// Envoie une question à l'agent et ajoute sa réponse à la conversation
  Future<void> poserQuestion(String question) async {
    question = question.trim();
    if (question.isEmpty || enAttente) return;

    // L'historique = les échanges précédents, pour que l'agent suive la conversation
    final historique =
        messages.where((m) => !m.erreur).map((m) => {'role': m.role, 'contenu': m.texte}).toList();

    setState(() {
      messages.add(Message('user', question));
      enAttente = true;
    });
    champ.clear();
    descendre();

    try {
      final resultat = await envoyerApi('/assistant', {'question': question, 'historique': historique});
      setState(() => messages.add(Message('assistant', resultat['reponse'],
          outils: List<String>.from(resultat['outils_utilises']),
          consultees: List<String>.from(resultat['donnees_consultees'] ?? []))));
    } catch (erreur) {
      // l'API ou l'IA ne répond pas : un message en rouge
      setState(() => messages.add(Message('assistant', '$erreur', erreur: true)));
    } finally {
      setState(() => enAttente = false);
      descendre();
    }
  }

  /// Descend en bas de la conversation (après l'affichage du nouveau message)
  void descendre() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (defilement.hasClients) {
        defilement.animateTo(defilement.position.maxScrollExtent,
            duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
      }
    });
  }

  /// Trouve le niveau de risque cité dans la réponse (pour afficher la pastille de la maquette).
  /// Seulement si l'agent a calculé un risque (outil risque_d_un_lieu).
  String? niveauDansReponse(Message m) {
    if (!m.outils.contains('risque_d_un_lieu')) return null;
    final texte = m.texte.toLowerCase();
    String? premier;
    var position = texte.length;
    for (final niveau in ['élevé', 'moyen', 'faible']) {
      final i = texte.indexOf(niveau);
      if (i >= 0 && i < position) {
        position = i;
        premier = niveau;
      }
    }
    return premier;
  }

  /// Si l'agent écrit **gras**, un morceau sur deux (entre les **) est affiché en gras
  Widget texteAvecGras(String texte, Color couleur) {
    final morceaux = texte.split('**');
    return Text.rich(TextSpan(style: TextStyle(color: couleur, height: 1.45, fontSize: 15), children: [
      for (var i = 0; i < morceaux.length; i++)
        TextSpan(text: morceaux[i], style: i.isOdd ? const TextStyle(fontWeight: FontWeight.w700) : null),
    ]));
  }

  /// Une bulle : à droite en bleu nuit pour mes messages, à gauche en blanc pour l'agent
  Widget bulle(Message m) {
    final deMoi = m.role == 'user';
    final niveau = deMoi ? null : niveauDansReponse(m);
    return Align(
      alignment: deMoi ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: 14),
        padding: EdgeInsets.all(deMoi ? 12 : 14),
        // largeur maximale : 82 % de l'écran pour moi, 92 % pour l'agent
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * (deMoi ? 0.82 : 0.92)),
        decoration: BoxDecoration(
          // bleu nuit pour moi, rouge clair pour une erreur, blanc pour l'agent
          color: deMoi ? bleuNuit : (m.erreur ? const Color(0xFFF6D5D2) : Colors.white),
          border: deMoi ? null : Border.all(color: bordure),
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(deMoi ? 16 : 4),
            bottomRight: Radius.circular(deMoi ? 4 : 16),
          ),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (niveau != null) ...[
            Pastille(niveau, texte: 'Risque $niveau'),
            const SizedBox(height: 10),
          ],
          texteAvecGras(m.texte, deMoi ? Colors.white : bleuNuit),
          if (m.consultees.isNotEmpty) ...[
            const Divider(height: 20, color: bordure),
            Text('Données consultées : ${m.consultees.join(', ')}',
                style: const TextStyle(fontSize: 12, color: grisTexte)),
          ],
        ]),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: fondChat,
      child: Column(children: [
        // ---------- En-tête : retour, bouclier, « Garde » ----------
        Container(
          color: bleuNuit,
          child: SafeArea(
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(8, 10, 16, 10),
              child: Row(children: [
                IconButton(
                  tooltip: 'Retour à la carte',
                  onPressed: widget.retour,
                  icon: const Icon(Icons.chevron_left, color: Colors.white, size: 28),
                ),
                Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(color: bleuNuit2, borderRadius: BorderRadius.circular(10)),
                  child: const Bouclier(taille: 20),
                ),
                const SizedBox(width: 10),
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Garde', style: titre(18, couleur: Colors.white)),
                  const Text('Assistant sécurité', style: TextStyle(color: grisClair, fontSize: 12)),
                ]),
              ]),
            ),
          ),
        ),

        // ---------- La conversation (Expanded : prend toute la place disponible) ----------
        Expanded(
          child: ListView(
            controller: defilement,
            padding: const EdgeInsets.all(16),
            children: [
              // le message d'accueil (toujours en premier)
              bulle(Message('assistant',
                  'Bonjour, je suis Garde. Demandez-moi par exemple à quelle heure aller quelque part, '
                  'ce qui se passe dans un quartier, ou si un trajet est risqué.')),
              ...messages.map(bulle),
              if (enAttente)
                const Padding(
                  padding: EdgeInsets.only(bottom: 12),
                  child: Text('Garde réfléchit…', style: TextStyle(fontStyle: FontStyle.italic, color: grisTexte)),
                ),
              const Center(
                child: Text('Estimation statistique, pas une garantie.',
                    style: TextStyle(fontSize: 12, color: grisTexte)),
              ),
            ],
          ),
        ),

        // ---------- Suggestions + zone de saisie (en bas de l'écran) ----------
        Container(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: bordure))),
          child: Column(children: [
            // Les boutons de suggestion, qui défilent de gauche à droite
            SizedBox(
              height: 40,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: suggestions.entries
                    .map((s) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: OutlinedButton(
                            onPressed: () => poserQuestion(s.value),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: bleuNuit,
                              side: const BorderSide(color: bordureChamp),
                              shape: const StadiumBorder(),
                            ),
                            child: Text(s.key, style: const TextStyle(fontSize: 13)),
                          ),
                        ))
                    .toList(),
              ),
            ),
            const SizedBox(height: 10),
            // Le champ de texte et le bouton « Envoyer »
            Row(children: [
              Expanded(
                child: TextField(
                  controller: champ,
                  maxLength: 500,
                  textInputAction: TextInputAction.send,
                  onSubmitted: poserQuestion,
                  decoration: InputDecoration(
                    hintText: 'Un lieu, une heure…',
                    filled: true,
                    fillColor: Colors.white,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 14),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
                    enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                        borderSide: const BorderSide(color: bordureChamp)),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                width: 48,
                height: 48,
                child: IconButton.filled(
                  tooltip: 'Envoyer',
                  onPressed: enAttente ? null : () => poserQuestion(champ.text),
                  style: IconButton.styleFrom(
                    backgroundColor: orange,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  ),
                  icon: const Icon(Icons.send, color: Colors.white, size: 20),
                ),
              ),
            ]),
          ]),
        ),
      ]),
    );
  }
}