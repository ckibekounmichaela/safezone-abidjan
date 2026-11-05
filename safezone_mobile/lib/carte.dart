import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import 'api.dart';
import 'compte.dart';
import 'theme.dart';

class EcranCarte extends StatefulWidget {
  final void Function(String question) demanderAssistant;
  const EcranCarte({super.key, required this.demanderAssistant});

  @override
  State<EcranCarte> createState() => _EcranCarteState();
}

class _EcranCarteState extends State<EcranCarte> {
  final controleurCarte = MapController();
  final int maintenant = DateTime.now().hour;

  // ---------- Les listes, chargées depuis l'API au démarrage ----------
  Map<String, LatLng> positions = {};
  Map<String, List<String>> quartiersParCommune = {};
  bool chargement = true;
  Object? erreurChargement;

  // ---------- Les choix de l'utilisateur ----------
  String? commune;
  String? quartier;
  late int heure = maintenant;
  String deplacement = '';
  String eclairage = '';

  // Texte affiché dans les listes -> code envoyé à l'API
  static const deplacements = {
    '': 'Je ne sais pas encore',
    'pied': 'À pied',
    'moto': 'À moto',
    'taxi': 'Taxi / woro-woro / gbaka',
    'voiture': 'En voiture',
    'bus': 'En bus',
  };
  static const eclairages = {'': 'Je ne sais pas', 'eclairee': 'Oui, éclairée', 'sombre': 'Non, sombre'};

  // ---------- Le résultat du calcul ----------
  Map<String, dynamic>? risque;
  List<dynamic> toutesLesCommunes = [];
  bool calculEnCours = false;
  String? erreurCalcul;
  LatLng? maPosition;
  bool localisationEnCours = false;

  @override
  void initState() {
    super.initState();
    chargerListes();
  }

  /// Au démarrage : les communes (avec leur position) et les quartiers de chaque commune
  Future<void> chargerListes() async {
    setState(() {
      chargement = true;
      erreurChargement = null;
    });
    try {
      final communes = await lireApi('/communes') as List<dynamic>;
      final quartiers = await lireApi('/quartiers/tous') as List<dynamic>;
      positions = {
        for (final c in communes)
          c['nom']: LatLng((c['latitude'] as num).toDouble(), (c['longitude'] as num).toDouble()),
      };
      quartiersParCommune = {};
      for (final q in quartiers) {
        quartiersParCommune.putIfAbsent(q['commune'], () => []).add(q['quartier']);
      }
      for (final liste in quartiersParCommune.values) {
        liste.sort();
      }
      setState(() {
        commune = (positions.keys.toList()..sort()).first;
        chargement = false;
      });
    } catch (e) {
      setState(() {
        erreurChargement = e;
        chargement = false;
      });
    }
  }

  /// Le bouton « Calculer le risque » : on demande le score à l'API
  Future<void> calculer() async {
    if (commune == null) return;
    setState(() {
      calculEnCours = true;
      erreurCalcul = null;
    });
    try {
      // L'adresse à demander : celle du quartier, ou celle de la commune entière
      final nomCommune = Uri.encodeComponent(commune!);
      final adresse = quartier == null
          ? '/risque?commune=$nomCommune&heure=$heure'
          : '/risque/quartier?quartier=${Uri.encodeComponent(quartier!)}&commune=$nomCommune&heure=$heure';
      // + comment on se déplace et l'éclairage de la rue
      final resultat = await lireApi('$adresse&deplacement=$deplacement&eclairage=$eclairage');
      final toutes = await lireApi('/risque/toutes?heure=$heure') as List<dynamic>;
      setState(() {
        risque = resultat;
        toutesLesCommunes = toutes;
      });
      deplacerCarte(positions[commune]!, 12);
      enregistrerDansHistorique(resultat);
    } catch (e) {
      setState(() => erreurCalcul = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => calculEnCours = false);
    }
  }

  /// Si l'utilisateur est connecté, on garde ce calcul dans son historique (onglet « Historique »).
  /// Sans compte, on ne garde rien. Si l'enregistrement échoue, ce n'est pas grave : le score reste affiché.
  Future<void> enregistrerDansHistorique(Map<String, dynamic> resultat) async {
    final compte = compteConnecte;
    if (compte == null) return;
    try {
      await envoyerApi(
          '/recherches',
          {
            'commune': resultat['commune'],
            'quartier': resultat['quartier'],
            'heure': resultat['heure'],
            'deplacement': deplacement,
            'eclairage': eclairage,
            'score': resultat['score'],
            'niveau': resultat['niveau'],
          },
          jeton: compte.jeton);
    } catch (_) {}
  }

  /// « Utiliser ma position » : le GPS trouve la commune où l'on est, puis on calcule pour MAINTENANT
  Future<void> utiliserMaPosition() async {
    void message(String texte) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(texte)));

    setState(() => localisationEnCours = true);
    try {
      // 1) Le GPS est-il allumé ? L'utilisateur nous autorise-t-il à l'utiliser ?
      if (!await Geolocator.isLocationServiceEnabled()) {
        message('Activez la localisation (GPS) du téléphone.');
        return;
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
        message('Autorisation de localisation refusée.');
        return;
      }

      // 2) La position GPS -> l'API trouve la commune la plus proche
      final position = await Geolocator.getCurrentPosition();
      final ici = await lireApi('/risque/position?latitude=${position.latitude}'
          '&longitude=${position.longitude}&heure=$maintenant');

      // 3) On remplit les 3 choix, puis on calcule comme si on avait appuyé sur le bouton
      setState(() {
        maPosition = LatLng(position.latitude, position.longitude);
        commune = ici['commune'];
        quartier = null;
        heure = maintenant;
      });
      await calculer();
    } catch (e) {
      message(e is ErreurApi ? '$e' : 'Position introuvable. Vérifiez que la localisation du téléphone est activée.');
    } finally {
      if (mounted) setState(() => localisationEnCours = false);
    }
  }

  /// Déplace la carte (sans planter si elle n'est pas encore affichée)
  void deplacerCarte(LatLng position, double zoom) {
    try {
      controleurCarte.move(position, zoom);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      // ---------- En-tête bleu nuit ----------
      Container(
        color: bleuNuit,
        child: const SafeArea(
          bottom: false,
          child: Padding(
            padding: EdgeInsets.fromLTRB(16, 14, 16, 14),
            child: Row(children: [Bouclier(), SizedBox(width: 8), Logo()]),
          ),
        ),
      ),

      // ---------- Contenu ----------
      Expanded(
        child: chargement
            ? const Center(child: CircularProgressIndicator())
            : erreurChargement != null
                ? Center(child: MessageErreur(erreurChargement!, reessayer: chargerListes))
                : ListView(padding: const EdgeInsets.all(16), children: [
                    Text('Calculer mon risque', style: titre(24)),
                    const SizedBox(height: 4),
                    const Text('Choisissez où vous allez, à quelle heure et comment, puis appuyez sur « Calculer le risque ».',
                        style: TextStyle(color: grisTexte, fontSize: 14)),
                    const SizedBox(height: 12),
                    formulaire(),
                    const SizedBox(height: 12),
                    if (erreurCalcul != null)
                      Text(erreurCalcul!, style: const TextStyle(color: Color(0xFF8E1D17))),
                    if (risque != null) ...[resultat(), const SizedBox(height: 12)],
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: blocBlanc(),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: SizedBox(height: 300, child: carte()),
                      ),
                    ),
                  ]),
      ),
    ]);
  }

  /// Les 5 listes, le bouton « Calculer le risque » et « Utiliser ma position »
  Widget formulaire() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: blocBlanc(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // 1. La commune (quand elle change, on revient à « Toute la commune »)
        listeDeroulante<String?>(
          '1. Où allez-vous ? (commune)',
          commune,
          [for (final nom in positions.keys.toList()..sort()) DropdownMenuItem<String?>(value: nom, child: Text(nom))],
          (nom) => setState(() {
            commune = nom;
            quartier = null;
          }),
        ),
        // 2. Le quartier : seulement ceux de la commune choisie
        listeDeroulante<String?>(
          '2. Quartier',
          quartier,
          [
            const DropdownMenuItem(value: null, child: Text('Toute la commune')),
            for (final nom in quartiersParCommune[commune] ?? <String>[])
              DropdownMenuItem(value: nom, child: Text(nom, overflow: TextOverflow.ellipsis)),
          ],
          (nom) => setState(() => quartier = nom),
        ),
        // 3. L'heure : de 0 h à 23 h, l'heure actuelle est marquée « (maintenant) »
        listeDeroulante<int>(
          '3. À quelle heure ?',
          heure,
          [
            for (var h = 0; h < 24; h++)
              DropdownMenuItem(value: h, child: Text(h == maintenant ? '$h h (maintenant)' : '$h h')),
          ],
          (h) => setState(() => heure = h!),
        ),
        // 4. Comment on se déplace
        listeDeroulante<String>(
          '4. Comment vous déplacez-vous ?',
          deplacement,
          [for (final choix in deplacements.entries) DropdownMenuItem(value: choix.key, child: Text(choix.value))],
          (code) => setState(() => deplacement = code!),
        ),
        // 5. L'éclairage de la rue
        listeDeroulante<String>(
          '5. La rue est-elle éclairée ?',
          eclairage,
          [for (final choix in eclairages.entries) DropdownMenuItem(value: choix.key, child: Text(choix.value))],
          (code) => setState(() => eclairage = code!),
        ),
        const SizedBox(height: 4),
        BoutonOrange(
          calculEnCours ? 'Calcul…' : 'Calculer le risque',
          icone: Icons.shield_outlined,
          onPressed: calculEnCours ? null : calculer,
        ),
        const SizedBox(height: 4),
        TextButton.icon(
          onPressed: localisationEnCours ? null : utiliserMaPosition,
          icon: const Icon(Icons.my_location),
          label: const Text('Utiliser ma position'),
          style: TextButton.styleFrom(foregroundColor: bleuNuit),
        ),
      ]),
    );
  }

  /// Une liste déroulante avec son titre au-dessus
  Widget listeDeroulante<T>(String titreListe, T valeur, List<DropdownMenuItem<T>> choix, void Function(T?) quandChoisi) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(titreListe, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: bleuNuit)),
        const SizedBox(height: 4),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: bordureChamp),
          ),
          child: DropdownButton<T>(
            value: valeur,
            items: choix,
            onChanged: quandChoisi,
            isExpanded: true,
            underline: const SizedBox(),
          ),
        ),
      ]),
    );
  }

  /// Le résultat : seulement ce qui est utile à l'utilisateur
  /// (le lieu et l'heure, le niveau avec sa barre de progression, le conseil, 2 phrases « À savoir »)
  Widget resultat() {
    final r = risque!;
    final lieu = r['quartier'] ?? r['commune'];
    final couleurs = couleursNiveau(r['niveau']);
    final score = (r['score'] as num).toDouble();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: blocBlanc(),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(lieu, style: titre(24)),
        Text(
          '${r['quartier'] != null ? '${r['commune']} · ' : ''}à ${r['heure']} h',
          style: const TextStyle(color: grisTexte, fontSize: 14),
        ),
        // Le bandeau de la couleur du niveau : « Risque élevé   78/100 » + la barre de progression
        Container(
          width: double.infinity,
          margin: const EdgeInsets.symmetric(vertical: 12),
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
          decoration: BoxDecoration(color: couleurs[0], borderRadius: BorderRadius.circular(12)),
          child: Column(children: [
            Row(children: [
              Expanded(child: Text('Risque ${r['niveau']}', style: titre(22, couleur: couleurs[1]))),
              Text('${r['score']}/100', style: titre(22, couleur: couleurs[1])),
            ]),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(99),
              child: LinearProgressIndicator(
                value: score / 100,
                minHeight: 12,
                color: couleurs[2],
                backgroundColor: Colors.white,
              ),
            ),
            const SizedBox(height: 4),
            // Sous la barre : « moyen » commence à 20, « élevé » à 50
            Row(children: [
              Expanded(flex: 20, child: Text('Faible', style: TextStyle(fontSize: 12, color: couleurs[1]))),
              Expanded(flex: 30, child: Text('Moyen', style: TextStyle(fontSize: 12, color: couleurs[1]))),
              Expanded(flex: 50, child: Text('Élevé', style: TextStyle(fontSize: 12, color: couleurs[1]))),
            ]),
          ]),
        ),
        // Le conseil, bien visible
        Text(r['conseil'], style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
        const SizedBox(height: 12),
        // À savoir : 2 phrases simples écrites par l'API
        const Text('À savoir', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
        const SizedBox(height: 4),
        for (final phrase in r['a_savoir'])
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text('•  $phrase', style: const TextStyle(fontSize: 14, color: Color(0xFF2B3A4D))),
          ),
        const SizedBox(height: 10),
        SizedBox(
          width: double.infinity,
          height: 46,
          child: FilledButton.icon(
            onPressed: () => widget.demanderAssistant('Est-ce risqué d\'aller à $lieu'
                '${r['quartier'] != null ? ' (${r['commune']})' : ''} vers ${r['heure']}h ?'),
            icon: const Icon(Icons.chat_bubble_outline, size: 18),
            label: const Text("Demander conseil à l'assistant", style: TextStyle(fontWeight: FontWeight.w700)),
            style: FilledButton.styleFrom(
              backgroundColor: bleuNuit,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Text(r['attention'], style: const TextStyle(fontSize: 12, color: grisTexte)),
      ]),
    );
  }

  /// La carte d'Abidjan : après un calcul, un rond par commune, de la couleur de son niveau
  Widget carte() {
    return FlutterMap(
      mapController: controleurCarte,
      options: const MapOptions(initialCenter: LatLng(5.345, -4.02), initialZoom: 10.5),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'ci.simplon.safezone',
        ),
        MarkerLayer(markers: [
          for (final r in toutesLesCommunes)
            if (positions[r['commune']] != null)
              Marker(
                point: positions[r['commune']]!,
                width: 22 + (r['score'] as num) / 4,
                height: 22 + (r['score'] as num) / 4,
                child: Container(
                  decoration: BoxDecoration(
                    color: couleursNiveau(r['niveau'])[2].withAlpha(120),
                    shape: BoxShape.circle,
                    // contour foncé et épais = la commune choisie
                    border: Border.all(
                      color: r['commune'] == risque?['commune'] ? bleuNuit : couleursNiveau(r['niveau'])[2],
                      width: r['commune'] == risque?['commune'] ? 3 : 2,
                    ),
                  ),
                ),
              ),
        ]),
        // Le point bleu : la position de l'utilisateur
        if (maPosition != null)
          MarkerLayer(markers: [
            Marker(
              point: maPosition!,
              width: 22,
              height: 22,
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF2A78D6),
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white, width: 3),
                ),
              ),
            ),
          ]),
      ],
    );
  }
}
