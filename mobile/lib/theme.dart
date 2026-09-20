import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// EnergyFox brand, sampled straight off LOGO.png: a deep navy field with an
/// amber mark. Everything in the app is tuned around these two.
class Brand {
  static const navy = Color(0xFF191E32);
  static const navyDeep = Color(0xFF10141F);
  static const navySoft = Color(0xFF232A44);
  static const amber = Color(0xFFE09945);
  static const amberSoft = Color(0xFFF3C486);

  static const canvas = Color(0xFFF5F6FA);
  static const ink = Color(0xFF111827);
  static const muted = Color(0xFF6B7280);
  static const line = Color(0xFFE6E8EF);

  static const success = Color(0xFF10B981);
  static const warning = Color(0xFFF59E0B);
  static const danger = Color(0xFFF43F5E);
  static const info = Color(0xFF06B6D4);

  static const gradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF232A44), Color(0xFF141A2C)],
  );
}

/// The six lead statuses the API ships with, coloured the same way the web app
/// colours them so the two never disagree in front of a customer.
const Map<String, Color> kStatusColors = {
  'new': Color(0xFF6366F1),
  'follow_up': Color(0xFFF59E0B),
  'positive': Color(0xFF06B6D4),
  'interested': Color(0xFF84CC16),
  'not_interested': Color(0xFFF43F5E),
  'converted': Color(0xFF10B981),
};

const Map<String, Color> kPriorityColors = {
  'high': Color(0xFFF43F5E),
  'medium': Color(0xFFF59E0B),
  'low': Color(0xFF06B6D4),
};

const Map<String, Color> kTaskStatusColors = {
  'todo': Color(0xFF94A3B8),
  'in_progress': Color(0xFF6366F1),
  'review': Color(0xFFF59E0B),
  'done': Color(0xFF10B981),
};

ThemeData buildTheme(Brightness brightness) {
  final dark = brightness == Brightness.dark;

  final scheme = ColorScheme(
    brightness: brightness,
    primary: dark ? Brand.amber : Brand.navy,
    onPrimary: dark ? Brand.navyDeep : Colors.white,
    primaryContainer: dark ? Brand.navySoft : const Color(0xFFE7EAF3),
    onPrimaryContainer: dark ? Colors.white : Brand.navy,
    secondary: Brand.amber,
    onSecondary: Brand.navyDeep,
    secondaryContainer: dark ? const Color(0xFF3A2E1C) : const Color(0xFFFCEFDC),
    onSecondaryContainer: dark ? Brand.amberSoft : const Color(0xFF7A4E10),
    error: Brand.danger,
    onError: Colors.white,
    errorContainer: dark ? const Color(0xFF45161F) : const Color(0xFFFFE4E8),
    onErrorContainer: dark ? const Color(0xFFFFC9D2) : const Color(0xFF8E1129),
    surface: dark ? const Color(0xFF161B2B) : Colors.white,
    onSurface: dark ? const Color(0xFFE8EAF2) : Brand.ink,
    surfaceContainerLowest: dark ? const Color(0xFF0C1019) : Colors.white,
    surfaceContainerLow: dark ? const Color(0xFF131826) : const Color(0xFFFAFBFD),
    surfaceContainer: dark ? const Color(0xFF181E2E) : const Color(0xFFF2F4F9),
    surfaceContainerHigh: dark ? const Color(0xFF1E2537) : const Color(0xFFECEFF6),
    surfaceContainerHighest: dark ? const Color(0xFF242C41) : const Color(0xFFE6EAF2),
    onSurfaceVariant: dark ? const Color(0xFF9AA3BC) : Brand.muted,
    outline: dark ? const Color(0xFF39415A) : Brand.line,
    outlineVariant: dark ? const Color(0xFF2A3145) : const Color(0xFFEFF1F6),
    inverseSurface: dark ? const Color(0xFFE8EAF2) : Brand.navy,
    onInverseSurface: dark ? Brand.navy : Colors.white,
    shadow: Colors.black,
    scrim: Colors.black,
  );

  final base = ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: dark ? Brand.navyDeep : Brand.canvas,
    fontFamily: 'system-ui',
    splashFactory: InkSparkle.splashFactory,
  );

  return base.copyWith(
    appBarTheme: AppBarTheme(
      backgroundColor: dark ? Brand.navyDeep : Brand.canvas,
      surfaceTintColor: Colors.transparent,
      foregroundColor: scheme.onSurface,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      systemOverlayStyle:
          dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      titleTextStyle: TextStyle(
        color: scheme.onSurface,
        fontSize: 20,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.3,
      ),
    ),
    cardTheme: CardThemeData(
      color: scheme.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: dark ? const Color(0xFF131826) : Colors.white,
      surfaceTintColor: Colors.transparent,
      indicatorColor: dark
          ? Brand.amber.withValues(alpha: 0.18)
          : Brand.navy.withValues(alpha: 0.08),
      height: 66,
      elevation: 0,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
            fontSize: 11.5,
            fontWeight: states.contains(WidgetState.selected)
                ? FontWeight.w700
                : FontWeight.w500,
            color: states.contains(WidgetState.selected)
                ? scheme.primary
                : scheme.onSurfaceVariant,
          )),
      iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
            size: 24,
            color: states.contains(WidgetState.selected)
                ? scheme.primary
                : scheme.onSurfaceVariant,
          )),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: dark ? const Color(0xFF131826) : Colors.white,
      contentPadding:
          const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: scheme.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: scheme.outline),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: Brand.amber, width: 1.6),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: Brand.danger),
      ),
      labelStyle: TextStyle(color: scheme.onSurfaceVariant),
      hintStyle: TextStyle(color: scheme.onSurfaceVariant),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(52),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontSize: 15.5, fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(48),
        side: BorderSide(color: scheme.outline),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        textStyle: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600),
      ),
    ),
    chipTheme: ChipThemeData(
      side: BorderSide(color: scheme.outline),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
      labelStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
    ),
    dividerTheme: DividerThemeData(color: scheme.outlineVariant, space: 1),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: dark ? const Color(0xFF242C41) : Brand.navy,
      contentTextStyle: const TextStyle(color: Colors.white, fontSize: 14),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: CupertinoPageTransitionsBuilder(),
      TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
      TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
      TargetPlatform.windows: CupertinoPageTransitionsBuilder(),
      TargetPlatform.linux: CupertinoPageTransitionsBuilder(),
    }),
  );
}
