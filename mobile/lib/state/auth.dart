import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api_client.dart';
import '../api/models.dart';

enum AuthStage { starting, signedOut, signedIn }

/// Owns the session: who is signed in, which server we are pointed at, and the
/// workspace's own name and status list, which every other screen reads.
class AuthController extends ChangeNotifier {
  AuthController(this.api) {
    api.onSessionExpired = () {
      _stage = AuthStage.signedOut;
      _user = null;
      notifyListeners();
    };
  }

  static const _kThemeMode = 'ef_theme_mode';

  final ApiClient api;

  AuthStage _stage = AuthStage.starting;
  AppUser? _user;
  String _orgName = 'EnergyFox';
  List<LeadStatus> _statuses = const [];
  bool _busy = false;
  String? _error;
  ThemeMode _themeMode = ThemeMode.system;

  AuthStage get stage => _stage;
  AppUser? get user => _user;
  String get orgName => _orgName;
  List<LeadStatus> get statuses => _statuses;
  bool get busy => _busy;
  String? get error => _error;
  ThemeMode get themeMode => _themeMode;
  String get baseUrl => api.baseUrl;
  bool get readOnly => _user?.readOnly ?? false;

  // What this account may do, as the record itself answers it — see AppUser,
  // which mirrors `leads/access.py` gate for gate. Nobody signed out may do
  // anything.
  bool get canAddLeads => _user?.canAddLeads ?? false;
  bool get canEditLeads => _user?.canEditLeads ?? false;
  bool get canDeleteLeads => _user?.canDeleteLeads ?? false;
  bool get canAssignLeads => _user?.canAssignLeads ?? false;
  bool get canEditLeadStatus => _user?.canEditLeadStatus ?? false;
  bool get canAddTasks => _user?.canAddTasks ?? false;

  LeadStatus statusFor(String value) => _statuses.firstWhere(
        (s) => s.value == value,
        orElse: () => LeadStatus.fromJson({'value': value, 'label': _titleize(value)}),
      );

  static String _titleize(String value) => value
      .split('_')
      .where((w) => w.isNotEmpty)
      .map((w) => w[0].toUpperCase() + w.substring(1))
      .join(' ');

  Future<void> bootstrap() async {
    await api.loadSession();
    final prefs = await SharedPreferences.getInstance();
    _themeMode = ThemeMode.values.firstWhere(
      (m) => m.name == prefs.getString(_kThemeMode),
      orElse: () => ThemeMode.system,
    );
    if (api.accessToken == null) {
      _stage = AuthStage.signedOut;
      notifyListeners();
      return;
    }
    try {
      await _loadIdentity();
      _stage = AuthStage.signedIn;
    } on ApiException catch (e) {
      // Offline with a stored token is not a signed-out user: let them in and
      // let the individual screens report that they cannot reach the server.
      _stage = e.isOffline ? AuthStage.signedIn : AuthStage.signedOut;
    }
    notifyListeners();
  }

  Future<bool> signIn({
    required String username,
    required String password,
  }) async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      await api.login(username.trim(), password);
      await _loadIdentity();
      _stage = AuthStage.signedIn;
      return true;
    } on ApiException catch (e) {
      _error = e.statusCode == 401
          ? 'Wrong username or password.'
          : e.message;
      return false;
    } finally {
      _busy = false;
      notifyListeners();
    }
  }

  Future<void> signOut() async {
    await api.clearSession();
    _user = null;
    _statuses = const [];
    _stage = AuthStage.signedOut;
    notifyListeners();
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    _themeMode = mode;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kThemeMode, mode.name);
    notifyListeners();
  }

  Future<void> refreshIdentity() async {
    try {
      await _loadIdentity();
      notifyListeners();
    } on ApiException {
      // Leave the cached identity in place; the screen shows its own error.
    }
  }

  Future<void> _loadIdentity() async {
    final me = await api.get('/api/users/me/');
    _user = AppUser.fromJson((me as Map).cast<String, dynamic>());
    // Best-effort extras — a workspace that hides these must not block sign-in.
    try {
      final list = await api.get('/api/leads/statuses/');
      if (list is List) {
        _statuses = list
            .whereType<Map>()
            .map((e) => LeadStatus.fromJson(e.cast<String, dynamic>()))
            .toList();
      }
    } on ApiException {
      _statuses = LeadStatus.fallback
          .map((e) => LeadStatus.fromJson(Map<String, dynamic>.from(e)))
          .toList();
    }
    try {
      final org = await api.get('/api/org-settings/');
      if (org is Map && org['name'] != null) {
        _orgName = org['name'].toString();
      }
    } on ApiException {
      // Keep the default name.
    }
  }
}
