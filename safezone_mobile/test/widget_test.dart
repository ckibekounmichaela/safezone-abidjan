import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:safezone_mobile/connexion.dart';

void main() {
  testWidgets("L'écran de connexion vérifie les champs et passe à « Créer un compte »", (tester) async {
    await tester.pumpWidget(const MaterialApp(home: EcranConnexion()));

    // Au départ : onglet « Se connecter », pas de champ « Votre nom »
    expect(find.text('Votre nom'), findsNothing);

    // Clic sur le bouton orange sans rien remplir -> message d'erreur (sans appeler l'API)
    await tester.tap(find.widgetWithText(FilledButton, 'Se connecter'));
    await tester.pump();
    expect(find.text("L'adresse e-mail n'est pas valide."), findsOneWidget);

    // Onglet « Créer un compte » -> le champ « Votre nom » apparaît
    await tester.tap(find.text('Créer un compte'));
    await tester.pump();
    expect(find.text('Votre nom'), findsOneWidget);
    expect(find.text('Créer mon compte'), findsOneWidget);
  });
}
