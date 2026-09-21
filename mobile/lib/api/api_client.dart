import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Anything the API said no to, carried with the status so callers can tell a
/// dead session (401) from a refusal (403) from a bad form (400).
class ApiException implements Exception {
  ApiException(this.statusCode, this.message, {this.fieldErrors});

  final int statusCode;
  final String message;
  final Map<String, String>? fieldErrors;

  bool get isAuth => statusCode == 401;
  bool get isForbidden => statusCode == 403;
  bool get isOffline => statusCode == 0;

  @override
  String toString() => message;
}

/// Talks to the EnergyFox Django API.
///
/// Holds the JWT pair, refreshes the access token once on a 401 and replays the
/// request, and gives up — signalling a logout — only when the refresh itself
/// is rejected.
class ApiClient {
  ApiClient({required this.baseUrl});

  static const kPrefAccess = 'ef_access';
  static const kPrefRefresh = 'ef_refresh';

  String baseUrl;
  String? accessToken;
  String? refreshToken;

  /// Called when the refresh token is dead and the user has to sign in again.
  void Function()? onSessionExpired;

  Future<void>? _refreshing;

  /// The EnergyFox production CRM. There is one server, so the app points at
  /// it and never asks: nobody signing in on a phone knows or should have to
  /// type an API address.
  static const kProductionBase = 'https://crmenergyfox.com';

  /// Overridden only for development:
  ///   flutter run --dart-define=API_BASE=http://10.0.2.2:8000
  static const _compiledBase = String.fromEnvironment('API_BASE');

  /// Where the API lives. The compiled override wins — that is how a developer
  /// points a debug build at a laptop — and everything else, packaged or web,
  /// gets the production server above.
  ///
  /// One exception, and it is a build-time one: a web build served from
  /// localhost is a developer's `flutter run -d chrome`, where Django sits on
  /// :8000 rather than behind the page's own origin.
  static String defaultBaseUrl() {
    if (_compiledBase.isNotEmpty) return normalizeBase(_compiledBase);
    if (kIsWeb) {
      final here = Uri.base;
      if (here.host == 'localhost' || here.host == '127.0.0.1') {
        return 'http://${here.host}:8000';
      }
    }
    return kProductionBase;
  }

  static String normalizeBase(String value) {
    var v = value.trim();
    if (v.isEmpty) return defaultBaseUrl();
    if (!v.startsWith('http://') && !v.startsWith('https://')) v = 'https://$v';
    while (v.endsWith('/')) {
      v = v.substring(0, v.length - 1);
    }
    return v;
  }

  Uri _uri(String path, [Map<String, dynamic>? query]) {
    final cleaned = <String, String>{};
    query?.forEach((k, v) {
      if (v == null) return;
      final s = v.toString();
      if (s.isEmpty) return;
      cleaned[k] = s;
    });
    return Uri.parse('$baseUrl$path')
        .replace(queryParameters: cleaned.isEmpty ? null : cleaned);
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (accessToken != null) 'Authorization': 'Bearer $accessToken',
      };

  // ── Session ───────────────────────────────────────────────────────────────

  Future<void> loadSession() async {
    final prefs = await SharedPreferences.getInstance();
    // The server is fixed, so it is re-derived rather than restored: a build
    // that moves to a new address must not keep talking to the old one because
    // somebody signed in before the move.
    baseUrl = defaultBaseUrl();
    accessToken = prefs.getString(kPrefAccess);
    refreshToken = prefs.getString(kPrefRefresh);
  }

  Future<void> saveSession() async {
    final prefs = await SharedPreferences.getInstance();
    if (accessToken != null) {
      await prefs.setString(kPrefAccess, accessToken!);
    } else {
      await prefs.remove(kPrefAccess);
    }
    if (refreshToken != null) {
      await prefs.setString(kPrefRefresh, refreshToken!);
    } else {
      await prefs.remove(kPrefRefresh);
    }
  }

  Future<void> clearSession() async {
    accessToken = null;
    refreshToken = null;
    await saveSession();
  }

  Future<void> login(String username, String password) async {
    final res = await _raw('POST', '/api/token/',
        body: {'username': username, 'password': password}, authed: false);
    accessToken = res['access'] as String?;
    refreshToken = res['refresh'] as String?;
    await saveSession();
  }

  /// One refresh at a time — three screens loading at once must not fire three
  /// refreshes and race each other into a dead token.
  Future<void> _refreshAccess() {
    return _refreshing ??= () async {
      try {
        if (refreshToken == null) {
          throw ApiException(401, 'Your session has expired. Please sign in again.');
        }
        final res = await _raw('POST', '/api/token/refresh/',
            body: {'refresh': refreshToken}, authed: false);
        accessToken = res['access'] as String?;
        if (res['refresh'] != null) refreshToken = res['refresh'] as String?;
        await saveSession();
      } finally {
        _refreshing = null;
      }
    }();
  }

  // ── Verbs ─────────────────────────────────────────────────────────────────

  Future<dynamic> get(String path, [Map<String, dynamic>? query]) =>
      _request('GET', path, query: query);

  Future<dynamic> post(String path, [Object? body]) =>
      _request('POST', path, body: body);

  Future<dynamic> patch(String path, Object? body) =>
      _request('PATCH', path, body: body);

  Future<dynamic> delete(String path) => _request('DELETE', path);

  /// A file upload. Separate from [_request] because a multipart body cannot be
  /// replayed from the same stream, so the token is refreshed *before* the
  /// request rather than after a 401 — there is nothing left to retry with.
  Future<dynamic> upload(
    String path, {
    required String field,
    required String filename,
    required List<int> bytes,
    Map<String, String> fields = const {},
  }) async {
    if (accessToken == null && refreshToken != null) await _refreshAccess();
    var res = await _sendMultipart(path, field, filename, bytes, fields);
    if (res.statusCode == 401 && refreshToken != null) {
      try {
        await _refreshAccess();
      } on ApiException {
        await clearSession();
        onSessionExpired?.call();
        rethrow;
      }
      res = await _sendMultipart(path, field, filename, bytes, fields);
    }
    return _decode(res);
  }

  Future<http.Response> _sendMultipart(String path, String field,
      String filename, List<int> bytes, Map<String, String> fields) async {
    final req = http.MultipartRequest('POST', _uri(path))
      ..fields.addAll(fields)
      ..files.add(http.MultipartFile.fromBytes(field, bytes, filename: filename));
    if (accessToken != null) {
      req.headers['Authorization'] = 'Bearer $accessToken';
    }
    try {
      final streamed = await req.send().timeout(const Duration(minutes: 3));
      return await http.Response.fromStream(streamed);
    } on TimeoutException {
      throw ApiException(0, 'The upload took too long. Try a smaller file.');
    } catch (_) {
      throw ApiException(0, "Can't reach the server. Check your connection.");
    }
  }

  Future<dynamic> _request(String method, String path,
      {Map<String, dynamic>? query, Object? body}) async {
    try {
      return await _raw(method, path, query: query, body: body);
    } on ApiException catch (e) {
      if (!e.isAuth || refreshToken == null) rethrow;
      try {
        await _refreshAccess();
      } on ApiException {
        await clearSession();
        onSessionExpired?.call();
        rethrow;
      }
      return _raw(method, path, query: query, body: body);
    }
  }

  Future<dynamic> _raw(String method, String path,
      {Map<String, dynamic>? query, Object? body, bool authed = true}) async {
    final uri = _uri(path, query);
    final headers = authed ? _headers : {'Content-Type': 'application/json'};
    final payload = body == null ? null : jsonEncode(body);

    late http.Response res;
    try {
      switch (method) {
        case 'POST':
          res = await http
              .post(uri, headers: headers, body: payload)
              .timeout(const Duration(seconds: 30));
        case 'PATCH':
          res = await http
              .patch(uri, headers: headers, body: payload)
              .timeout(const Duration(seconds: 30));
        case 'DELETE':
          res = await http
              .delete(uri, headers: headers)
              .timeout(const Duration(seconds: 30));
        default:
          res = await http
              .get(uri, headers: headers)
              .timeout(const Duration(seconds: 30));
      }
    } on TimeoutException {
      throw ApiException(0, 'The server took too long to answer.');
    } catch (_) {
      throw ApiException(0, "Can't reach the server. Check your connection.");
    }

    return _decode(res);
  }

  dynamic _decode(http.Response res) {
    if (res.statusCode == 204 || res.bodyBytes.isEmpty) return null;

    dynamic decoded;
    try {
      decoded = jsonDecode(utf8.decode(res.bodyBytes));
    } catch (_) {
      decoded = null;
    }

    if (res.statusCode >= 200 && res.statusCode < 300) return decoded;

    throw ApiException(
      res.statusCode,
      _messageFrom(decoded, res.statusCode),
      fieldErrors: _fieldErrorsFrom(decoded),
    );
  }

  String _messageFrom(dynamic decoded, int status) {
    if (decoded is Map) {
      for (final key in ['detail', 'error', 'message', 'non_field_errors']) {
        final v = decoded[key];
        if (v is String && v.isNotEmpty) return v;
        if (v is List && v.isNotEmpty) return v.first.toString();
      }
      final first = decoded.entries.firstOrNull;
      if (first != null) {
        final v = first.value;
        final text = v is List && v.isNotEmpty ? v.first.toString() : v.toString();
        return '${_humanField(first.key.toString())}: $text';
      }
    }
    if (status == 401) return 'Your session has expired. Please sign in again.';
    if (status == 403) return 'You do not have permission to do that.';
    if (status == 404) return 'That record no longer exists.';
    if (status == 429) return 'Too many requests — try again in a minute.';
    if (status >= 500) return 'The server hit an error. Try again shortly.';
    return 'Something went wrong (HTTP $status).';
  }

  Map<String, String>? _fieldErrorsFrom(dynamic decoded) {
    if (decoded is! Map) return null;
    final out = <String, String>{};
    decoded.forEach((k, v) {
      if (v is List && v.isNotEmpty) out[k.toString()] = v.first.toString();
      if (v is String) out[k.toString()] = v;
    });
    return out.isEmpty ? null : out;
  }

  String _humanField(String key) {
    final words = key.replaceAll('_', ' ');
    return words.isEmpty ? key : words[0].toUpperCase() + words.substring(1);
  }

  /// Media paths come back relative in local development and absolute from S3.
  String? absoluteMedia(String? url) {
    if (url == null || url.isEmpty) return null;
    if (url.startsWith('http')) return url;
    return '$baseUrl${url.startsWith('/') ? '' : '/'}$url';
  }
}

extension _FirstOrNull<T> on Iterable<T> {
  T? get firstOrNull => isEmpty ? null : first;
}
