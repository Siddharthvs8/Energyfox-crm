import 'package:flutter/material.dart';

import '../theme.dart';

int? _asInt(dynamic v) =>
    v == null ? null : (v is int ? v : int.tryParse(v.toString()));

double _asDouble(dynamic v) {
  if (v == null) return 0;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? 0;
}

String _asString(dynamic v) => v == null ? '' : v.toString();

DateTime? _asDate(dynamic v) {
  if (v == null) return null;
  return DateTime.tryParse(v.toString())?.toLocal();
}

/// The signed-in user, and everyone else who shows up in a picker.
class AppUser {
  AppUser({
    required this.id,
    required this.username,
    required this.firstName,
    required this.lastName,
    required this.email,
    required this.phone,
    required this.role,
    required this.roleLabel,
    required this.avatarUrl,
    required this.branchName,
    required this.readOnly,
    required this.isStaff,
    required this.isManager,
    required this.isGeneralManager,
    required this.permissions,
    required this.b2bAccess,
  });

  final int id;
  final String username;
  final String firstName;
  final String lastName;
  final String email;
  final String phone;
  final String role;
  final String roleLabel;
  final String? avatarUrl;
  final String? branchName;
  final bool readOnly;
  final bool isStaff;
  final bool isManager;
  final bool isGeneralManager;

  /// The module/capability keys a custom user type was granted in Settings →
  /// Roles & Permissions. Empty for a built-in role, whose access comes from the
  /// role rules instead — so an empty list never means "denied", only "ask the
  /// role". See [granted].
  final List<String> permissions;

  /// Which wholesale modules this account reaches: `{'items': 'rw', …}`.
  final Map<String, String> b2bAccess;

  bool get onCustomRole => role == 'custom';

  /// True/false when the user is on a custom role, null when they are not —
  /// the same three-way answer `leads.access.custom_grant` gives the server, and
  /// the difference matters: null means "fall through to the built-in rules".
  bool? granted(String key) => onCustomRole ? permissions.contains(key) : null;

  // ── What this account may actually do ──────────────────────────────────────
  // One gate per thing the UI can offer, each mirroring the function of the
  // same name in `leads/access.py`: a spectator writes nothing, a custom user
  // type is decided by the keys its role was granted, and everyone else falls
  // through to the built-in role rules. Drawing a button the server would
  // refuse is the bug these exist to prevent.

  bool _may(String key, bool Function() builtIn) {
    if (readOnly) return false;
    return granted(key) ?? builtIn();
  }

  /// Leads are sourced and owned by the tele-calling side; a BDE only receives
  /// them as a hand-off for the site visit.
  bool get canAddLeads => _may('leads.add', () => role != 'bde');
  bool get canEditLeads => _may('leads.edit', () => role != 'bde');
  bool get canDeleteLeads => _may('leads.delete', () => role != 'bde');
  bool get canAssignLeads => _may('leads.assign', () => role != 'bde');
  bool get canEditLeadStatus => _may('leads.status', () => role != 'bde');

  /// Anyone signed in may raise a task — the server puts no role gate on the
  /// tasks endpoint, only the spectator's read-only middleware.
  bool get canAddTasks => !readOnly;

  String get name {
    final full = '$firstName $lastName'.trim();
    return full.isEmpty ? username : full;
  }

  String get initials {
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.length == 1) {
      return parts.first.characters.take(2).toString().toUpperCase();
    }
    return (parts.first.characters.first + parts.last.characters.first)
        .toUpperCase();
  }

  factory AppUser.fromJson(Map<String, dynamic> j) => AppUser(
        id: _asInt(j['id']) ?? 0,
        username: _asString(j['username']),
        firstName: _asString(j['first_name']),
        lastName: _asString(j['last_name']),
        email: _asString(j['email']),
        phone: _asString(j['phone']),
        role: _asString(j['role']),
        roleLabel: _asString(j['role_label']),
        avatarUrl: j['avatar_url']?.toString(),
        branchName: j['branch_name']?.toString(),
        readOnly: j['read_only'] == true,
        isStaff: j['is_staff'] == true,
        isManager: j['is_manager'] == true,
        isGeneralManager: j['is_general_manager'] == true,
        permissions: (j['permissions'] as List? ?? const [])
            .map((e) => e.toString())
            .toList(),
        b2bAccess: (j['b2b_access'] as Map? ?? const {})
            .map((k, v) => MapEntry(k.toString(), v.toString())),
      );
}

/// A lead status as the workspace defines it — the six built-ins plus whatever
/// custom ones the admin has added, so the app never shows a status the CRM
/// does not know.
class LeadStatus {
  LeadStatus({required this.value, required this.label, required this.color});

  final String value;
  final String label;
  final Color color;

  factory LeadStatus.fromJson(Map<String, dynamic> j) {
    final raw = _asString(j['color']).replaceAll('#', '');
    final parsed = int.tryParse(raw, radix: 16);
    return LeadStatus(
      value: _asString(j['value']),
      label: _asString(j['label']),
      color: parsed != null && raw.length == 6
          ? Color(0xFF000000 | parsed)
          : kStatusColors[_asString(j['value'])] ?? Brand.muted,
    );
  }

  static const fallback = [
    {'value': 'new', 'label': 'New'},
    {'value': 'follow_up', 'label': 'Follow up'},
    {'value': 'positive', 'label': 'Positive'},
    {'value': 'interested', 'label': 'Interested'},
    {'value': 'not_interested', 'label': 'Not Interested'},
    {'value': 'converted', 'label': 'Converted'},
  ];
}

class Lead {
  Lead(this.raw);

  final Map<String, dynamic> raw;

  int get id => _asInt(raw['id']) ?? 0;
  String get firstName => _asString(raw['first_name']);
  String get lastName => _asString(raw['last_name']);
  String get name => '$firstName $lastName'.trim();
  String get phone => _asString(raw['phone']);
  String get email => _asString(raw['email']);
  String get company => _asString(raw['company']);
  String get district => _asString(raw['district']);
  String get installationLocation => _asString(raw['installation_location']);
  String get status => _asString(raw['status']);
  String get source => _asString(raw['source']);
  String get notes => _asString(raw['notes']);
  double get value => _asDouble(raw['value']);
  DateTime? get createdAt => _asDate(raw['created_at']);
  DateTime? get statusChangedAt => _asDate(raw['status_changed_at']);
  bool get isLost => raw['is_lost'] == true;
  bool get isArchived => raw['is_archived'] == true;
  String get assignedToName => _asString(raw['assigned_to_name']);
  int? get assignedToId => _asInt(raw['assigned_to']);
  String get bdeName => _asString(raw['bde_name']);
  String get teleCallerName => _asString(raw['tele_caller_name']);
  String get pipelineStageLabel => _asString(raw['pipeline_stage_label']);
  String get dealClassification => _asString(raw['deal_classification']);
  int? get productId => _asInt(raw['product']);
  String get productName {
    final p = raw['product_details'];
    return p is Map ? _asString(p['name']) : '';
  }

  String get initials {
    final n = name.trim();
    if (n.isEmpty) return '?';
    final parts = n.split(RegExp(r'\s+'));
    if (parts.length == 1) {
      return parts.first.characters.take(2).toString().toUpperCase();
    }
    return (parts.first.characters.first + parts.last.characters.first)
        .toUpperCase();
  }

  /// What the search box matches against.
  String get haystack => [
        name,
        phone,
        email,
        company,
        district,
        assignedToName,
        installationLocation,
      ].join(' ').toLowerCase();
}

class TaskItem {
  TaskItem(this.raw);

  final Map<String, dynamic> raw;

  int get id => _asInt(raw['id']) ?? 0;
  String get title => _asString(raw['title']);
  String get description => _asString(raw['description']);
  String get status => _asString(raw['status']);
  String get priority => _asString(raw['priority']);
  int? get assigneeId => _asInt(raw['assignee']);
  DateTime? get dueDate => _asDate(raw['due_date']);
  int? get leadId => _asInt(raw['lead']);
  bool get isDone => status == 'done';

  String get assigneeName {
    final a = raw['assignee_details'];
    if (a is Map) {
      final full = '${_asString(a['first_name'])} ${_asString(a['last_name'])}'.trim();
      return full.isEmpty ? _asString(a['username']) : full;
    }
    return '';
  }

  String get leadName {
    final l = raw['lead_details'];
    if (l is Map) {
      return '${_asString(l['first_name'])} ${_asString(l['last_name'])}'.trim();
    }
    return '';
  }

  String get leadPhone {
    final l = raw['lead_details'];
    return l is Map ? _asString(l['phone']) : '';
  }

  bool get isOverdue {
    final d = dueDate;
    if (d == null || isDone) return false;
    final today = DateTime.now();
    return d.isBefore(DateTime(today.year, today.month, today.day));
  }

  bool get isDueToday {
    final d = dueDate;
    if (d == null) return false;
    final now = DateTime.now();
    return d.year == now.year && d.month == now.month && d.day == now.day;
  }

  static const statuses = [
    ('todo', 'To Do'),
    ('in_progress', 'In Progress'),
    ('review', 'In Review'),
    ('done', 'Done'),
  ];

  static String labelFor(String value) =>
      statuses.firstWhere((s) => s.$1 == value, orElse: () => (value, value)).$2;
}

class ActivityEntry {
  ActivityEntry({
    required this.id,
    required this.type,
    required this.description,
    required this.actor,
    required this.timestamp,
    required this.auto,
  });

  final int id;
  final String type;
  final String description;
  final String actor;
  final DateTime? timestamp;
  final bool auto;

  factory ActivityEntry.fromJson(Map<String, dynamic> j) => ActivityEntry(
        id: _asInt(j['id']) ?? 0,
        type: _asString(j['type']),
        description: _asString(j['description']),
        actor: _asString(j['actor'] ?? j['user']),
        timestamp: _asDate(j['timestamp']),
        auto: j['auto_generated'] == true,
      );
}

class DashboardStats {
  DashboardStats({
    required this.totalLeads,
    required this.newToday,
    required this.pipelineValue,
    required this.totalRevenue,
    required this.pipeline,
    required this.revenueOverTime,
    required this.leadsOverTime,
    required this.recentActivities,
    required this.performance,
  });

  final int totalLeads;
  final int newToday;
  final double pipelineValue;
  final double totalRevenue;
  final Map<String, int> pipeline;
  final List<({String label, double value})> revenueOverTime;
  final List<({String label, double value})> leadsOverTime;
  final List<ActivityEntry> recentActivities;
  final List<Map<String, dynamic>> performance;

  int get converted => pipeline['converted'] ?? 0;

  factory DashboardStats.fromJson(Map<String, dynamic> j) {
    List<({String label, double value})> series(dynamic list, String key) {
      if (list is! List) return const [];
      return list
          .whereType<Map>()
          .map((e) => (
                label: _asString(e['name']),
                value: _asDouble(e[key]),
              ))
          .toList();
    }

    final pipelineRaw = j['pipeline'];
    return DashboardStats(
      totalLeads: _asInt(j['total_leads']) ?? 0,
      newToday: _asInt(j['new_today']) ?? 0,
      pipelineValue: _asDouble(j['pipeline_value']),
      totalRevenue: _asDouble(j['total_revenue']),
      pipeline: pipelineRaw is Map
          ? pipelineRaw.map((k, v) => MapEntry(k.toString(), _asInt(v) ?? 0))
          : <String, int>{},
      revenueOverTime: series(j['revenue_over_time'], 'Revenue'),
      leadsOverTime: series(j['leads_over_time'], 'Leads'),
      recentActivities: (j['recent_activities'] as List? ?? [])
          .whereType<Map>()
          .map((e) => ActivityEntry.fromJson(e.cast<String, dynamic>()))
          .toList(),
      performance: (j['performance_stats'] as List? ?? [])
          .whereType<Map>()
          .map((e) => e.cast<String, dynamic>())
          .toList(),
    );
  }
}

/// A DRF page: `{count, next, previous, results}`, or a bare list when the
/// endpoint was asked for everything at once.
class Page<T> {
  Page({required this.items, required this.count, required this.hasNext});

  final List<T> items;
  final int count;
  final bool hasNext;

  static Page<Map<String, dynamic>> from(dynamic body) {
    if (body is List) {
      final items = body.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList();
      return Page(items: items, count: items.length, hasNext: false);
    }
    if (body is Map) {
      final results = (body['results'] as List? ?? [])
          .whereType<Map>()
          .map((e) => e.cast<String, dynamic>())
          .toList();
      return Page(
        items: results,
        count: _asInt(body['count']) ?? results.length,
        hasNext: body['next'] != null,
      );
    }
    return Page(items: const [], count: 0, hasNext: false);
  }
}
