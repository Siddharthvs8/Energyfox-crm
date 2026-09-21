import 'package:energyfox_mobile/api/api_client.dart';
import 'package:energyfox_mobile/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('shows the sign-in screen when no session is stored',
      (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(
      EnergyFoxApp(api: ApiClient(baseUrl: 'https://example.test')),
    );
    await tester.pumpAndSettle();

    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);

    // The server is fixed in the build. Nobody signing in on a phone knows an
    // API address, and being asked for one is how they get stuck on the first
    // screen.
    expect(find.text('CRM server'), findsNothing);
    expect(find.textContaining('Server settings'), findsNothing);
  });

  testWidgets('points at the production CRM, whatever was stored before',
      (WidgetTester tester) async {
    // A build that has moved servers must not keep talking to the old one
    // because somebody signed in before the move.
    SharedPreferences.setMockInitialValues({'ef_api_base': 'https://old.test'});
    final api = ApiClient(baseUrl: 'https://placeholder.test');
    await api.loadSession();

    expect(api.baseUrl, ApiClient.kProductionBase);
  });
}
