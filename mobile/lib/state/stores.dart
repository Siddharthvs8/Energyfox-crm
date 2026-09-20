import 'dart:async';

import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import 'nav.dart';

/// The three states every list screen can be in, kept in one place so the
/// screens can all render loading, error and empty the same way.
enum LoadState { idle, loading, ready, failed }

class DashboardStore extends ChangeNotifier {
  DashboardStore(this.api);

  final ApiClient api;

  LoadState state = LoadState.idle;
  DashboardStats? stats;
  String? error;

  Future<void> load({bool force = false}) async {
    if (state == LoadState.loading) return;
    if (stats != null && !force) return;
    state = LoadState.loading;
    if (force) error = null;
    notifyListeners();
    try {
      final body = await api.get('/api/dashboard-stats/');
      stats = DashboardStats.fromJson((body as Map).cast<String, dynamic>());
      error = null;
      state = LoadState.ready;
    } on ApiException catch (e) {
      error = e.message;
      state = stats == null ? LoadState.failed : LoadState.ready;
    }
    notifyListeners();
  }
}

/// The lead book: one page at a time, filtered server-side on status and
/// ownership, searched client-side over what has been pulled down.
class LeadStore extends ChangeNotifier {
  LeadStore(this.api);

  final ApiClient api;

  LoadState state = LoadState.idle;
  List<Lead> leads = [];
  String? error;
  int total = 0;

  String query = '';
  String? statusFilter;
  bool mineOnly = false;
  bool _hasNext = false;
  bool loadingMore = false;
  int _page = 1;
  int _requestId = 0;

  bool get hasMore => _hasNext;

  List<Lead> get visible {
    final q = query.trim().toLowerCase();
    if (q.isEmpty) return leads;
    return leads.where((l) => l.haystack.contains(q)).toList();
  }

  void search(String value) {
    query = value;
    notifyListeners();
  }

  Future<void> setStatus(String? value) {
    statusFilter = value;
    return load(force: true);
  }

  Future<void> setMineOnly(bool value) {
    mineOnly = value;
    return load(force: true);
  }

  Future<void> load({bool force = false}) async {
    if (leads.isNotEmpty && !force && state == LoadState.ready) return;
    final token = ++_requestId;
    _page = 1;
    state = LoadState.loading;
    if (force) error = null;
    notifyListeners();
    try {
      final page = await _fetch(1);
      if (token != _requestId) return;
      leads = page.items.map(Lead.new).toList();
      total = page.count;
      _hasNext = page.hasNext;
      error = null;
      state = LoadState.ready;
    } on ApiException catch (e) {
      if (token != _requestId) return;
      error = e.message;
      state = leads.isEmpty ? LoadState.failed : LoadState.ready;
    }
    notifyListeners();
  }

  Future<void> loadMore() async {
    if (loadingMore || !_hasNext || state == LoadState.loading) return;
    loadingMore = true;
    notifyListeners();
    final token = _requestId;
    try {
      final page = await _fetch(_page + 1);
      if (token != _requestId) return;
      _page += 1;
      leads = [...leads, ...page.items.map(Lead.new)];
      _hasNext = page.hasNext;
    } on ApiException catch (e) {
      error = e.message;
    } finally {
      loadingMore = false;
      notifyListeners();
    }
  }

  Future<Page<Map<String, dynamic>>> _fetch(int page) async {
    final body = await api.get('/api/leads/', {
      'page': page,
      'status': statusFilter,
      'assigned_to_me': mineOnly ? 'true' : null,
      'ordering': '-created_at',
    });
    return Page.from(body);
  }

  /// Slot an updated lead back into the list in place, so a detail-screen edit
  /// shows up without re-fetching the page behind it.
  void upsert(Lead lead) {
    final i = leads.indexWhere((l) => l.id == lead.id);
    if (i >= 0) {
      leads[i] = lead;
    } else {
      leads.insert(0, lead);
      total += 1;
    }
    notifyListeners();
  }

  void remove(int id) {
    leads.removeWhere((l) => l.id == id);
    total = total > 0 ? total - 1 : 0;
    notifyListeners();
  }
}

class TaskStore extends ChangeNotifier {
  TaskStore(this.api);

  final ApiClient api;

  LoadState state = LoadState.idle;
  List<TaskItem> tasks = [];
  String? error;
  String query = '';
  bool mineOnly = false;

  List<TaskItem> get visible {
    final q = query.trim().toLowerCase();
    final list = q.isEmpty
        ? tasks
        : tasks
            .where((t) =>
                t.title.toLowerCase().contains(q) ||
                t.description.toLowerCase().contains(q) ||
                t.leadName.toLowerCase().contains(q))
            .toList();
    return list;
  }

  List<TaskItem> byStatus(String status) =>
      visible.where((t) => t.status == status).toList();

  int get openCount => tasks.where((t) => !t.isDone).length;
  int get overdueCount => tasks.where((t) => t.isOverdue).length;

  void search(String value) {
    query = value;
    notifyListeners();
  }

  Future<void> setMineOnly(bool value) {
    mineOnly = value;
    return load(force: true);
  }

  Future<void> load({bool force = false}) async {
    if (tasks.isNotEmpty && !force && state == LoadState.ready) return;
    state = LoadState.loading;
    if (force) error = null;
    notifyListeners();
    try {
      final body = await api.get('/api/tasks/', {
        'all': 'true',
        'assigned_to_me': mineOnly ? 'true' : null,
      });
      tasks = Page.from(body).items.map(TaskItem.new).toList();
      error = null;
      state = LoadState.ready;
    } on ApiException catch (e) {
      error = e.message;
      state = tasks.isEmpty ? LoadState.failed : LoadState.ready;
    }
    notifyListeners();
  }

  /// Flip a task's status, showing the new state immediately and putting the
  /// old one back if the server refuses.
  Future<String?> setStatus(TaskItem task, String status) async {
    final before = Map<String, dynamic>.from(task.raw);
    final i = tasks.indexWhere((t) => t.id == task.id);
    if (i < 0) return null;
    tasks[i] = TaskItem({...task.raw, 'status': status});
    notifyListeners();
    try {
      final body = await api.patch('/api/tasks/${task.id}/', {'status': status});
      if (body is Map) tasks[i] = TaskItem(body.cast<String, dynamic>());
      notifyListeners();
      return null;
    } on ApiException catch (e) {
      tasks[i] = TaskItem(before);
      notifyListeners();
      return e.message;
    }
  }

  void upsert(TaskItem task) {
    final i = tasks.indexWhere((t) => t.id == task.id);
    if (i >= 0) {
      tasks[i] = task;
    } else {
      tasks.insert(0, task);
    }
    notifyListeners();
  }

  void remove(int id) {
    tasks.removeWhere((t) => t.id == id);
    notifyListeners();
  }
}

/// Small lookups (users, products, districts) that several forms need and
/// nobody should fetch twice.
class LookupStore extends ChangeNotifier {
  LookupStore(this.api);

  final ApiClient api;

  List<AppUser> users = [];
  List<Map<String, dynamic>> products = [];
  List<String> districts = [];
  bool _loaded = false;
  Future<void>? _inflight;

  Future<void> ensure() {
    if (_loaded) return Future.value();
    return _inflight ??= _load();
  }

  Future<void> _load() async {
    try {
      final results = await Future.wait([
        api.get('/api/users/', {'all': 'true'}).catchError((_) => <dynamic>[]),
        api.get('/api/products/', {'all': 'true'}).catchError((_) => <dynamic>[]),
        api.get('/api/districts/', {'all': 'true'}).catchError((_) => <dynamic>[]),
      ]);
      users = Page.from(results[0]).items.map(AppUser.fromJson).toList();
      products = Page.from(results[1]).items;
      districts = Page.from(results[2])
          .items
          .map((d) => (d['name'] ?? '').toString())
          .where((n) => n.isNotEmpty)
          .toList();
      _loaded = true;
    } on ApiException {
      // Pickers fall back to free text.
    } finally {
      _inflight = null;
      notifyListeners();
    }
  }
}

/// The badges on the drawer: how much work is still waiting on this user in
/// each module.
///
/// Same endpoint, same numbers and the same "already seen" rule as the web
/// app's sidebar — a module this account cannot open simply isn't in the
/// answer, so a count is never shown for a door that would not open.
class ModuleCountStore extends ChangeNotifier {
  ModuleCountStore(this.api);

  final ApiClient api;

  Map<String, int> counts = const {};
  Timer? _timer;

  int operator [](String key) => counts[key] ?? 0;

  /// Everything waiting on this user, for the one dot on the hamburger.
  int get total => counts.entries
      .where((e) => e.key != 'leads') // their own book is not a queue
      .fold(0, (sum, e) => sum + e.value);

  Future<void> load() async {
    try {
      final body = await api.get('/api/leads/module-counts/');
      if (body is Map && body['counts'] is Map) {
        counts = (body['counts'] as Map)
            .map((k, v) => MapEntry(k.toString(), (v as num?)?.toInt() ?? 0));
        notifyListeners();
      }
    } on ApiException {
      // Keep the badges we have; the next tick tries again.
    }
  }

  /// Polled rather than pushed, like the web app's sidebar — a minute is soon
  /// enough for a badge and cheap enough for a phone on mobile data.
  void start() {
    if (_timer != null) return;
    load();
    _timer = Timer.periodic(const Duration(minutes: 1), (_) => load());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    counts = const {};
    notifyListeners();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

/// The bell: what the AI manager and the pipeline have to tell this user.
class NotificationStore extends ChangeNotifier {
  NotificationStore(this.api);

  final ApiClient api;

  List<Map<String, dynamic>> items = const [];
  int unread = 0;
  LoadState state = LoadState.idle;
  String? error;
  Timer? _timer;

  Future<void> load() async {
    if (state == LoadState.loading) return;
    state = LoadState.loading;
    notifyListeners();
    try {
      final results = await Future.wait([
        api.get('/api/ai-manager/notifications/', {'limit': 20}),
        api.get('/api/ai-manager/notifications/unread_count/'),
      ]);
      items = Page.from(results[0]).items;
      final count = results[1];
      unread = count is Map ? ((count['count'] as num?)?.toInt() ?? 0) : 0;
      error = null;
      state = LoadState.ready;
    } on ApiException catch (e) {
      error = e.message;
      state = items.isEmpty ? LoadState.failed : LoadState.ready;
    }
    notifyListeners();
  }

  /// Just the count, for the badge — the list itself is only fetched when the
  /// sheet is opened.
  Future<void> refreshCount() async {
    try {
      final body = await api.get('/api/ai-manager/notifications/unread_count/');
      if (body is Map) {
        unread = (body['count'] as num?)?.toInt() ?? 0;
        notifyListeners();
      }
    } on ApiException {
      // Leave the badge as it was.
    }
  }

  Future<void> markAllRead() async {
    if (unread == 0) return;
    unread = 0;
    items = [
      for (final n in items) {...n, 'is_read': true},
    ];
    notifyListeners();
    try {
      await api.post('/api/ai-manager/notifications/mark_read/', const {});
    } on ApiException {
      await refreshCount();
    }
  }

  void start() {
    if (_timer != null) return;
    refreshCount();
    _timer = Timer.periodic(const Duration(minutes: 1), (_) => refreshCount());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    items = const [];
    unread = 0;
    notifyListeners();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}

/// One work queue — Documentation, Accounts, Purchase, any of them.
///
/// Every queue endpoint answers with the same customer core plus its own
/// module's fields, so one store (and one screen) lists any of them; what
/// differs between them is described by the module's [QueueSource].
class QueueStore extends ChangeNotifier {
  QueueStore(this.api, this.source);

  final ApiClient api;
  final QueueSource source;

  LoadState state = LoadState.idle;
  List<Map<String, dynamic>> rows = const [];
  String? error;
  String query = '';

  List<Map<String, dynamic>> get visible {
    final q = query.trim().toLowerCase();
    if (q.isEmpty) return rows;
    return rows.where((r) => _haystack(r).contains(q)).toList();
  }

  static String _haystack(Map<String, dynamic> r) => r.entries
      .where((e) => e.value is String || e.value is num)
      .map((e) => e.value.toString())
      .join(' ')
      .toLowerCase();

  void search(String value) {
    query = value;
    notifyListeners();
  }

  /// How many the server says there are — the same as [rows] for a queue that
  /// answers in one go, larger while a paged one is still being scrolled in.
  int total = 0;
  bool loadingMore = false;
  bool _hasNext = false;
  int _page = 1;

  bool get hasMore => _hasNext;

  Future<void> load({bool force = false}) async {
    if (rows.isNotEmpty && !force && state == LoadState.ready) return;
    state = LoadState.loading;
    _page = 1;
    if (force) error = null;
    notifyListeners();
    try {
      final page = await _fetch(1);
      rows = page.items;
      total = page.count;
      _hasNext = page.hasNext;
      error = null;
      state = LoadState.ready;
    } on ApiException catch (e) {
      error = e.message;
      state = rows.isEmpty ? LoadState.failed : LoadState.ready;
    }
    notifyListeners();
  }

  Future<void> loadMore() async {
    if (loadingMore || !_hasNext || state == LoadState.loading) return;
    loadingMore = true;
    notifyListeners();
    try {
      final page = await _fetch(_page + 1);
      _page += 1;
      rows = [...rows, ...page.items];
      _hasNext = page.hasNext;
    } on ApiException catch (e) {
      error = e.message;
    } finally {
      loadingMore = false;
      notifyListeners();
    }
  }

  Future<Page<Map<String, dynamic>>> _fetch(int page) async {
    final body = await api.get(source.path, {
      ...?source.query,
      'page': page,
      // A work queue is asked for in one go — it is a day's work, not a book.
      // The lead list is the exception, and asking it for every converted
      // customer at once is a download nobody on a phone asked for; the page
      // number above carries those. Endpoints that don't honour `all` simply
      // page like any other, which is why both are sent.
      if (!source.paged) 'all': 'true',
    });
    final list =
        source.rootKey != null && body is Map ? body[source.rootKey!] : body;
    return Page.from(list);
  }
}

/// The call log: every call placed through the CRM, newest first.
///
/// Who appears in it is the server's business — an agent sees their own calls,
/// a branch manager their branch's, the admin tier everybody's — so the app
/// asks for the list and shows what comes back.
class CallStore extends ChangeNotifier {
  CallStore(this.api);

  final ApiClient api;

  LoadState state = LoadState.idle;
  List<Map<String, dynamic>> calls = const [];
  String? error;
  int total = 0;
  String? direction;
  bool loadingMore = false;
  bool _hasNext = false;
  int _page = 1;
  int _requestId = 0;

  bool get hasMore => _hasNext;

  Future<void> setDirection(String? value) {
    direction = value;
    return load(force: true);
  }

  Future<void> load({bool force = false}) async {
    if (calls.isNotEmpty && !force && state == LoadState.ready) return;
    final token = ++_requestId;
    _page = 1;
    state = LoadState.loading;
    if (force) error = null;
    notifyListeners();
    try {
      final page = await _fetch(1);
      if (token != _requestId) return;
      calls = page.items;
      total = page.count;
      _hasNext = page.hasNext;
      error = null;
      state = LoadState.ready;
    } on ApiException catch (e) {
      if (token != _requestId) return;
      error = e.message;
      state = calls.isEmpty ? LoadState.failed : LoadState.ready;
    }
    notifyListeners();
  }

  Future<void> loadMore() async {
    if (loadingMore || !_hasNext || state == LoadState.loading) return;
    loadingMore = true;
    notifyListeners();
    final token = _requestId;
    try {
      final page = await _fetch(_page + 1);
      if (token != _requestId) return;
      _page += 1;
      calls = [...calls, ...page.items];
      _hasNext = page.hasNext;
    } on ApiException catch (e) {
      error = e.message;
    } finally {
      loadingMore = false;
      notifyListeners();
    }
  }

  Future<Page<Map<String, dynamic>>> _fetch(int page) async {
    final body = await api.get('/api/calls/', {
      'page': page,
      'direction': direction,
    });
    return Page.from(body);
  }
}
