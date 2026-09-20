import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'api/api_client.dart';
import 'state/auth.dart';
import 'state/stores.dart';
import 'theme.dart';
import 'ui/login_screen.dart';
import 'ui/shell.dart';
import 'ui/widgets/common.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final api = ApiClient(baseUrl: ApiClient.defaultBaseUrl());
  runApp(EnergyFoxApp(api: api));
}

class EnergyFoxApp extends StatelessWidget {
  const EnergyFoxApp({super.key, required this.api});

  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider<ApiClient>.value(value: api),
        ChangeNotifierProvider(create: (_) => AuthController(api)..bootstrap()),
        ChangeNotifierProvider(create: (_) => DashboardStore(api)),
        ChangeNotifierProvider(create: (_) => LeadStore(api)),
        ChangeNotifierProvider(create: (_) => TaskStore(api)),
        ChangeNotifierProvider(create: (_) => LookupStore(api)),
        ChangeNotifierProvider(create: (_) => CallStore(api)),
        // The drawer's badges and the bell, both polled while signed in.
        ChangeNotifierProvider(create: (_) => ModuleCountStore(api)),
        ChangeNotifierProvider(create: (_) => NotificationStore(api)),
      ],
      child: Consumer<AuthController>(
        builder: (context, auth, _) => MaterialApp(
          title: 'EnergyFox CRM',
          debugShowCheckedModeBanner: false,
          theme: buildTheme(Brightness.light),
          darkTheme: buildTheme(Brightness.dark),
          themeMode: auth.themeMode,
          scrollBehavior: const _AppScrollBehavior(),
          home: const _AuthGate(),
        ),
      ),
    );
  }
}

/// Touch dragging on the web build too — a phone-shaped app people scroll with
/// a thumb, not a scroll wheel.
class _AppScrollBehavior extends MaterialScrollBehavior {
  const _AppScrollBehavior();

  @override
  Set<PointerDeviceKind> get dragDevices => PointerDeviceKind.values.toSet();
}

class _AuthGate extends StatelessWidget {
  const _AuthGate();

  @override
  Widget build(BuildContext context) {
    final stage = context.select<AuthController, AuthStage>((a) => a.stage);
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 280),
      child: switch (stage) {
        AuthStage.starting => const _SplashScreen(),
        AuthStage.signedOut => const LoginScreen(),
        AuthStage.signedIn => const AppShell(),
      },
    );
  }
}

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Brand.navy,
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            BrandMark(size: 76, radius: 22),
            SizedBox(height: 26),
            SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(
                  strokeWidth: 2.4, color: Brand.amber),
            ),
          ],
        ),
      ),
    );
  }
}
