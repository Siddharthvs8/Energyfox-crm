import 'package:energyfox_mobile/api/models.dart';
import 'package:energyfox_mobile/state/nav.dart';
import 'package:flutter_test/flutter_test.dart';

/// A user as `/api/users/me/` describes one.
AppUser user({
  String role = 'tele_caller',
  bool isStaff = false,
  bool isManager = false,
  bool isGeneralManager = false,
  bool readOnly = false,
  List<String> permissions = const [],
}) =>
    AppUser.fromJson({
      'id': 1,
      'username': 'someone',
      'role': role,
      'is_staff': isStaff,
      'is_manager': isManager,
      'is_general_manager': isGeneralManager,
      'read_only': readOnly,
      'permissions': permissions,
    });

Set<String> keys(AppUser? u) => visibleModules(u).map((m) => m.key).toSet();

void main() {
  group('who may create', () {
    test('a BDE receives leads rather than sourcing them', () {
      final bde = user(role: 'bde');
      expect(bde.canAddLeads, isFalse);
      expect(bde.canEditLeads, isFalse);
      expect(bde.canEditLeadStatus, isFalse);
      // They still work the leads handed to them, and tasks are open to all.
      expect(bde.canAddTasks, isTrue);
    });

    test('a tele caller owns the lead book', () {
      final caller = user(role: 'tele_caller');
      expect(caller.canAddLeads, isTrue);
      expect(caller.canEditLeadStatus, isTrue);
    });

    test('a spectator writes nothing at all', () {
      final watcher = user(role: 'admin', isStaff: true, readOnly: true);
      expect(watcher.canAddLeads, isFalse);
      expect(watcher.canAddTasks, isFalse);
      expect(watcher.canEditLeads, isFalse);
    });

    test('a custom user type is decided by the keys it was granted', () {
      final withAdd = user(role: 'custom', permissions: ['leads', 'leads.add']);
      expect(withAdd.canAddLeads, isTrue);
      expect(withAdd.canEditLeads, isFalse, reason: 'leads.edit not granted');

      // A custom role that happens not to be a BDE still gets nothing it was
      // not given — the permission list is the whole answer for these accounts.
      final viewer = user(role: 'custom', permissions: ['leads']);
      expect(viewer.canAddLeads, isFalse);
    });
  });

  group('which modules the drawer shows', () {
    test('an admin sees the whole house', () {
      final admin = keys(user(role: 'admin', isStaff: true));
      expect(admin, containsAll(<String>[
        'dashboard', 'leads', 'calls', 'tasks', 'accounts', 'purchase',
        'project', 'liasoning', 'settings', 'activity-log',
      ]));
    });

    test('the documentation team get their own queue and nothing else', () {
      final doc = keys(user(role: 'documentation_staff'));
      expect(doc, {'documentation', 'documentation-stage2', 'warranty'});
    });

    test('accounts staff get the money queues', () {
      final accounts = keys(user(role: 'accounts_staff'));
      expect(accounts, {
        'accounts',
        'accounts/partially-paid',
        'accounts/fully-paid',
        'accounts/completed',
      });
    });

    test('a BDE gets the field modules, not the fulfilment ones', () {
      final bde = keys(user(role: 'bde'));
      expect(bde, containsAll(<String>['dashboard', 'leads', 'calls', 'tasks',
        'feasibility', 'closed-deals']));
      expect(bde, isNot(contains('accounts')));
      expect(bde, isNot(contains('settings')));
    });

    test('a custom user type gets exactly its granted modules', () {
      final custom = keys(user(
          role: 'custom', permissions: ['dashboard', 'leads', 'accounts']));
      expect(custom, {'dashboard', 'leads', 'accounts'});
    });

    test('a spectator watches every module an admin can open', () {
      final watcher = keys(user(role: 'spectator', readOnly: true));
      expect(watcher, containsAll(<String>[
        'leads', 'accounts', 'project', 'company-performance', 'closed-deals',
      ]));
      // …but not the audit trail, which is not a watching brief.
      expect(watcher, isNot(contains('activity-log')));
    });

    test('the bottom bar only carries tabs the account may open', () {
      final tabs = tabModules(user(role: 'documentation_staff'));
      expect(tabs, isEmpty, reason: 'the doc team have no field tabs');

      final caller = tabModules(user(role: 'tele_caller')).map((m) => m.key);
      expect(caller, ['dashboard', 'leads', 'calls', 'tasks']);
    });
  });
}
