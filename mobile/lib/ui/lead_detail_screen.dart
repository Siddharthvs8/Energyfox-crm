import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../state/auth.dart';
import '../state/stores.dart';
import '../theme.dart';
import 'lead/attachments_card.dart';
import 'lead/calls_card.dart';
import 'lead/lead_actions.dart';
import 'lead/notes_card.dart';
import 'lead/quick_stats_card.dart';
import 'lead/quotations_card.dart';
import 'lead/site_visit_screen.dart';
import 'lead/tasks_card.dart';
import 'lead/whatsapp_card.dart';
import 'lead_form_screen.dart';
import 'task_editor.dart';
import 'widgets/common.dart';

class LeadDetailScreen extends StatefulWidget {
  const LeadDetailScreen({super.key, required this.leadId, this.seed});

  final int leadId;
  final Lead? seed;

  @override
  State<LeadDetailScreen> createState() => _LeadDetailScreenState();
}

class _LeadDetailScreenState extends State<LeadDetailScreen> {
  // The sections own their own data, so a change made in one of them reloads
  // that one rather than the whole page. These are how the page reaches them
  // when an action elsewhere — placing a call, say — affects what they show.
  final _callsKey = GlobalKey<CallHistoryCardState>();
  final _tasksKey = GlobalKey<RelatedTasksCardState>();

  Lead? _lead;
  List<ActivityEntry> _timeline = const [];
  String? _error;
  bool _loading = true;
  bool _calling = false;

  @override
  void initState() {
    super.initState();
    _lead = widget.seed;
    _load();
  }

  ApiClient get _api => context.read<ApiClient>();

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final results = await Future.wait([
        _api.get('/api/leads/${widget.leadId}/'),
        _api
            .get('/api/leads/${widget.leadId}/activity-timeline/')
            .catchError((_) => <String, dynamic>{}),
      ]);
      if (!mounted) return;
      final lead = Lead((results[0] as Map).cast<String, dynamic>());
      final tl = results[1];
      setState(() {
        _lead = lead;
        _timeline = tl is Map
            ? ((tl['entries'] as List? ?? [])
                .whereType<Map>()
                .map((e) => ActivityEntry.fromJson(e.cast<String, dynamic>()))
                .toList())
            : const [];
        _error = null;
        _loading = false;
      });
      if (mounted) context.read<LeadStore>().upsert(lead);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  Future<void> _openUrl(String url) async {
    final uri = Uri.parse(url);
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      showToast(context, 'Nothing on this device can open that.', error: true);
    }
  }

  String _waNumber(String phone) {
    var digits = phone.replaceAll(RegExp(r'\D'), '');
    if (digits.length == 10) digits = '91$digits';
    return digits;
  }

  /// Click-to-call through the CRM, so the call is recorded and logged against
  /// the lead rather than being a private call off someone's handset.
  Future<void> _callViaCrm() async {
    final lead = _lead;
    if (lead == null || _calling) return;
    setState(() => _calling = true);
    try {
      await _api.post('/api/calls/initiate/', {'lead_id': lead.id});
      if (!mounted) return;
      showToast(context, 'Calling — your phone will ring first.');
      // The log takes a moment to land: the card is refreshed, and the user
      // can pull it again from its own Refresh if the dialler is slow.
      _callsKey.currentState?.reload();
    } on ApiException catch (e) {
      if (!mounted) return;
      showToast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _calling = false);
    }
  }

  Future<void> _changeStatus() async {
    final lead = _lead;
    if (lead == null) return;
    final auth = context.read<AuthController>();
    final statuses = auth.statuses.isEmpty
        ? LeadStatus.fallback
            .map((e) => LeadStatus.fromJson(Map<String, dynamic>.from(e)))
            .toList()
        : auth.statuses;

    final picked = await showModalBottomSheet<String>(
      context: context,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 4, 20, 10),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('Move this lead to',
                    style: TextStyle(
                        fontSize: 17, fontWeight: FontWeight.w800)),
              ),
            ),
            for (final s in statuses)
              ListTile(
                onTap: () => Navigator.pop(context, s.value),
                leading: Container(
                  width: 34,
                  height: 34,
                  decoration: BoxDecoration(
                    color: s.color.withValues(alpha: 0.14),
                    borderRadius: BorderRadius.circular(11),
                  ),
                  child: Icon(Icons.flag_rounded, size: 17, color: s.color),
                ),
                title: Text(s.label,
                    style: const TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w600)),
                trailing: lead.status == s.value
                    ? const Icon(Icons.check_rounded, size: 20)
                    : null,
              ),
            const SizedBox(height: 10),
          ],
        ),
      ),
    );

    if (picked == null || picked == lead.status) return;
    try {
      final body =
          await _api.patch('/api/leads/${lead.id}/', {'status': picked});
      if (!mounted) return;
      final updated = Lead((body as Map).cast<String, dynamic>());
      setState(() => _lead = updated);
      context.read<LeadStore>().upsert(updated);
      context.read<DashboardStore>().load(force: true);
      HapticFeedback.mediumImpact();
      showToast(context, 'Moved to ${auth.statusFor(picked).label}.');
      _load();
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    }
  }

  Future<void> _edit() async {
    final lead = _lead;
    if (lead == null) return;
    final updated = await Navigator.of(context).push<Lead>(
      MaterialPageRoute(builder: (_) => LeadFormScreen(lead: lead)),
    );
    if (updated != null && mounted) {
      setState(() => _lead = updated);
      _load();
    }
  }

  Future<void> _openSiteVisit() async {
    final lead = _lead;
    if (lead == null) return;
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => SiteVisitScreen(lead: lead)),
    );
    // The site visit settles the deal value and the completion flag, both of
    // which this page shows, so it re-reads the lead when something moved.
    if (changed == true) _load();
  }

  Future<void> _assign({required bool documentation}) async {
    final lead = _lead;
    if (lead == null) return;
    final updated =
        await openAssignSheet(context, lead: lead, documentation: documentation);
    if (updated != null && mounted) {
      setState(() => _lead = updated);
      _load();
    }
  }

  Future<void> _setProduct() async {
    final lead = _lead;
    if (lead == null) return;
    if (await openProductSheet(context, lead) && mounted) _load();
  }

  Future<void> _push() async {
    final lead = _lead;
    if (lead == null) return;
    final updated = await pushToDocumentation(context, lead);
    if (updated != null && mounted) {
      setState(() => _lead = updated);
      _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    final lead = _lead;
    final auth = context.watch<AuthController>();

    if (lead == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Lead')),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : ErrorView(message: _error ?? 'Lead not found.', onRetry: _load),
      );
    }

    final status = auth.statusFor(lead.status);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: _load,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(
              parent: BouncingScrollPhysics()),
          slivers: [
            SliverAppBar(
              pinned: true,
              expandedHeight: 232,
              backgroundColor: Brand.navy,
              foregroundColor: Colors.white,
              systemOverlayStyle: SystemUiOverlayStyle.light,
              actions: [
                // The lead record belongs to the tele-calling side: a BDE
                // reports through the site visit and a spectator writes
                // nothing, so neither is offered a form the server would
                // refuse. Mirrors can_edit_leads().
                if (auth.canEditLeads)
                  IconButton(
                    onPressed: _edit,
                    icon: const Icon(Icons.edit_outlined),
                    tooltip: 'Edit lead',
                  ),
              ],
              flexibleSpace: FlexibleSpaceBar(
                collapseMode: CollapseMode.parallax,
                titlePadding: const EdgeInsets.only(left: 56, bottom: 15, right: 56),
                title: Text(
                  lead.name.isEmpty ? 'Unnamed lead' : lead.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 16.5,
                      fontWeight: FontWeight.w700,
                      color: Colors.white),
                ),
                background: _HeroHeader(lead: lead, status: status),
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
              sliver: SliverList.list(children: [
                _ActionBar(
                  lead: lead,
                  calling: _calling,
                  readOnly: auth.readOnly,
                  onCallViaCrm: _callViaCrm,
                  onDial: () => _openUrl('tel:${lead.phone}'),
                  onWhatsApp: () =>
                      _openUrl('https://wa.me/${_waNumber(lead.phone)}'),
                  onEmail: () => _openUrl('mailto:${lead.email}'),
                ),
                const SizedBox(height: 18),
                // Two different permissions, so two separate decisions: a BDE
                // may raise a task on a lead they are handling but may not move
                // its status — that belongs to the tele caller.
                if (auth.canEditLeadStatus || auth.canAddTasks)
                  Row(
                    children: [
                      if (auth.canEditLeadStatus)
                        Expanded(
                          child: FilledButton.icon(
                            onPressed: _changeStatus,
                            icon: const Icon(Icons.flag_rounded, size: 18),
                            label: const Text('Change status'),
                            style: FilledButton.styleFrom(
                              minimumSize: const Size.fromHeight(48),
                              backgroundColor: status.color,
                              foregroundColor: Colors.white,
                            ),
                          ),
                        ),
                      if (auth.canEditLeadStatus && auth.canAddTasks)
                        const SizedBox(width: 10),
                      if (auth.canAddTasks)
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: () async {
                              final created =
                                  await openTaskEditor(context, lead: lead);
                              if (created != null) {
                                _tasksKey.currentState?.reload();
                                _load();
                              }
                            },
                            icon: const Icon(Icons.add_task_rounded, size: 18),
                            label: const Text('Add task'),
                            style: OutlinedButton.styleFrom(
                                minimumSize: const Size.fromHeight(48)),
                          ),
                        ),
                    ],
                  ),

                // The hand-offs the web page keeps in its header. Each one is
                // drawn only when the server said this account may do it to
                // this lead — see LeadSerializer's can_* fields.
                if (lead.canEditSiteVisit ||
                    lead.canAssignBde ||
                    (lead.canAssignDocumentation && lead.pushedToDocumentation))
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: [
                        if (lead.canEditSiteVisit)
                          OutlinedButton.icon(
                            onPressed: _setProduct,
                            icon: const Icon(Icons.inventory_2_outlined,
                                size: 17),
                            label: Text(lead.productId == null
                                ? 'Add product'
                                : 'Edit product'),
                          ),
                        if (lead.canAssignBde)
                          OutlinedButton.icon(
                            onPressed: () => _assign(documentation: false),
                            icon: const Icon(Icons.directions_car_outlined,
                                size: 17),
                            label: Text(lead.bdeId == null
                                ? 'Assign BDE'
                                : 'Reassign BDE'),
                          ),
                        if (lead.canAssignDocumentation &&
                            lead.pushedToDocumentation)
                          OutlinedButton.icon(
                            onPressed: () => _assign(documentation: true),
                            icon: const Icon(Icons.folder_shared_outlined,
                                size: 17),
                            label: Text(lead.documentationStaffId == null
                                ? 'Assign documentation'
                                : 'Reassign documentation'),
                          ),
                      ],
                    ),
                  ),

                // The BDE's own screen. Prominent rather than buried: on a
                // phone this is the reason the app is open at all.
                if (lead.canEditSiteVisit || lead.siteVisitComplete) ...[
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: _openSiteVisit,
                    icon: const Icon(Icons.assignment_outlined, size: 19),
                    label: Text(lead.siteVisitComplete
                        ? 'Site visit — complete'
                        : 'Site visit details'),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(50),
                      backgroundColor:
                          lead.siteVisitComplete ? Brand.success : Brand.amber,
                      foregroundColor: lead.siteVisitComplete
                          ? Colors.white
                          : Brand.navyDeep,
                    ),
                  ),
                ],

                const SizedBox(height: 22),
                const SectionHeader(
                    title: 'Contact information', icon: Icons.badge_outlined),
                _DetailsCard(lead: lead),

                const SizedBox(height: 22),
                QuickStatsCard(lead: lead),

                const SizedBox(height: 22),
                NotesCard(
                  leadId: lead.id,
                  readOnly: auth.readOnly,
                  onChanged: _load,
                ),

                const SizedBox(height: 22),
                WhatsAppCard(leadId: lead.id, readOnly: auth.readOnly),

                const SizedBox(height: 22),
                RelatedTasksCard(
                    key: _tasksKey, lead: lead, canAddTasks: auth.canAddTasks),

                const SizedBox(height: 22),
                CallHistoryCard(
                    key: _callsKey,
                    leadId: lead.id,
                    readOnly: auth.readOnly),

                const SizedBox(height: 22),
                QuotationsCard(
                  leadId: lead.id,
                  readOnly: auth.readOnly,
                  customerEmail: lead.email,
                ),

                const SizedBox(height: 22),
                AttachmentsCard(
                  leadId: lead.id,
                  readOnly: auth.readOnly,
                  invoiceUrl: lead.invoiceUrl,
                ),

                const SizedBox(height: 22),
                SectionHeader(
                  title: 'Activity timeline',
                  icon: Icons.history_rounded,
                  action: _timeline.length > 6
                      ? TextButton(
                          onPressed: () => Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => _TimelineScreen(
                                  name: lead.name, entries: _timeline),
                            ),
                          ),
                          child: Text('All ${_timeline.length}'),
                        )
                      : null,
                ),
                _TimelineCard(
                    entries: _timeline.take(6).toList(), loading: _loading),

                // The hand-off that follows the site visit above.
                if (lead.canEditSiteVisit && !lead.pushedToDocumentation) ...[
                  const SizedBox(height: 22),
                  AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text('Push to documentation',
                            style: TextStyle(
                                fontSize: 14.5, fontWeight: FontWeight.w800)),
                        const SizedBox(height: 4),
                        Text(
                          lead.siteVisitComplete
                              ? 'Site visit is complete — hand this lead over '
                                  'to the documentation team.'
                              : 'Mark the site visit complete first.',
                          style: TextStyle(
                            fontSize: 12.5,
                            height: 1.4,
                            color: Theme.of(context)
                                .colorScheme
                                .onSurfaceVariant,
                          ),
                        ),
                        const SizedBox(height: 14),
                        FilledButton.icon(
                          onPressed: lead.siteVisitComplete ? _push : null,
                          icon: const Icon(Icons.outbox_rounded, size: 18),
                          label: const Text('Push to documentation'),
                          style: FilledButton.styleFrom(
                              minimumSize: const Size.fromHeight(48)),
                        ),
                      ],
                    ),
                  ),
                ],
              ]),
            ),
          ],
        ),
      ),
    );
  }
}

class _HeroHeader extends StatelessWidget {
  const _HeroHeader({required this.lead, required this.status});

  final Lead lead;
  final LeadStatus status;

  @override
  Widget build(BuildContext context) {
    final place = [lead.company, lead.district]
        .where((s) => s.isNotEmpty)
        .join(' · ');

    return Container(
      decoration: const BoxDecoration(gradient: Brand.gradient),
      padding: const EdgeInsets.fromLTRB(20, 96, 20, 54),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InitialsAvatar(
              text: lead.initials, size: 58, color: Brand.amber),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  lead.name.isEmpty ? 'Unnamed lead' : lead.name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 21,
                    fontWeight: FontWeight.w800,
                    letterSpacing: -0.4,
                  ),
                ),
                if (place.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    place,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13,
                      color: Colors.white.withValues(alpha: 0.6),
                    ),
                  ),
                ],
                const SizedBox(height: 11),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    StatusPill(
                        label: status.label, color: status.color, solid: true),
                    if (lead.value > 0)
                      StatusPill(
                          label: moneyShort(lead.value),
                          color: Brand.amber,
                          dense: false),
                    if (lead.isLost)
                      const StatusPill(
                          label: 'Lost', color: Brand.danger, solid: true),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ActionBar extends StatelessWidget {
  const _ActionBar({
    required this.lead,
    required this.calling,
    required this.readOnly,
    required this.onCallViaCrm,
    required this.onDial,
    required this.onWhatsApp,
    required this.onEmail,
  });

  final Lead lead;
  final bool calling;
  final bool readOnly;
  final VoidCallback onCallViaCrm;
  final VoidCallback onDial;
  final VoidCallback onWhatsApp;
  final VoidCallback onEmail;

  @override
  Widget build(BuildContext context) {
    final hasPhone = lead.phone.isNotEmpty;
    return Row(
      children: [
        Expanded(
          child: _ActionButton(
            icon: calling ? Icons.hourglass_top_rounded : Icons.phone_in_talk_rounded,
            label: 'CRM call',
            color: Brand.success,
            enabled: hasPhone && !calling && !readOnly,
            onTap: onCallViaCrm,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _ActionButton(
            icon: Icons.call_rounded,
            label: 'Dial',
            color: const Color(0xFF6366F1),
            enabled: hasPhone,
            onTap: onDial,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _ActionButton(
            icon: Icons.chat_rounded,
            label: 'WhatsApp',
            color: const Color(0xFF25D366),
            enabled: hasPhone,
            onTap: onWhatsApp,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _ActionButton(
            icon: Icons.mail_outline_rounded,
            label: 'Email',
            color: Brand.info,
            enabled: lead.email.isNotEmpty,
            onTap: onEmail,
          ),
        ),
      ],
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.enabled,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final Color color;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Opacity(
      opacity: enabled ? 1 : 0.4,
      child: AppCard(
        onTap: enabled
            ? () {
                HapticFeedback.lightImpact();
                onTap();
              }
            : null,
        padding: const EdgeInsets.symmetric(vertical: 13),
        child: Column(
          children: [
            Icon(icon, size: 21, color: color),
            const SizedBox(height: 6),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w700,
                color: scheme.onSurface,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DetailsCard extends StatelessWidget {
  const _DetailsCard({required this.lead});

  final Lead lead;

  @override
  Widget build(BuildContext context) {
    final rows = <({String label, String value, IconData icon, bool copy})>[
      if (lead.phone.isNotEmpty)
        (label: 'Phone', value: lead.phone, icon: Icons.call_rounded, copy: true),
      if (lead.email.isNotEmpty)
        (label: 'Email', value: lead.email, icon: Icons.mail_outline_rounded, copy: true),
      if (lead.company.isNotEmpty)
        (label: 'Location', value: lead.company, icon: Icons.place_outlined, copy: false),
      if (lead.district.isNotEmpty)
        (label: 'District', value: lead.district, icon: Icons.map_outlined, copy: false),
      if (lead.installationLocation.isNotEmpty)
        (label: 'Install site', value: lead.installationLocation, icon: Icons.solar_power_outlined, copy: false),
      if (lead.productName.isNotEmpty)
        (label: 'Product', value: lead.productName, icon: Icons.inventory_2_outlined, copy: false),
      if (lead.value > 0)
        (label: 'Deal value', value: money(lead.value), icon: Icons.currency_rupee_rounded, copy: false),
      if (lead.assignedToName.isNotEmpty)
        (label: 'Owner', value: lead.assignedToName, icon: Icons.person_outline_rounded, copy: false),
      if (lead.teleCallerName.isNotEmpty)
        (label: 'Tele caller', value: lead.teleCallerName, icon: Icons.headset_mic_outlined, copy: false),
      if (lead.bdeName.isNotEmpty)
        (label: 'BDE', value: lead.bdeName, icon: Icons.directions_car_outlined, copy: false),
      if (lead.pipelineStageLabel.isNotEmpty)
        (label: 'Stage', value: lead.pipelineStageLabel, icon: Icons.account_tree_outlined, copy: false),
      if (lead.source.isNotEmpty)
        (label: 'Source', value: titleize(lead.source), icon: Icons.input_rounded, copy: false),
      (label: 'Created', value: dateLabel(lead.createdAt), icon: Icons.event_outlined, copy: false),
    ];

    final scheme = Theme.of(context).colorScheme;

    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Column(
        children: [
          for (var i = 0; i < rows.length; i++) ...[
            if (i > 0) Divider(color: scheme.outlineVariant, height: 1),
            InkWell(
              onTap: rows[i].copy
                  ? () {
                      Clipboard.setData(ClipboardData(text: rows[i].value));
                      showToast(context, '${rows[i].label} copied.');
                    }
                  : null,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 13),
                child: Row(
                  children: [
                    Icon(rows[i].icon, size: 17, color: scheme.onSurfaceVariant),
                    const SizedBox(width: 12),
                    Text(
                      rows[i].label,
                      style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: scheme.onSurfaceVariant),
                    ),
                    const Spacer(),
                    Flexible(
                      child: Text(
                        rows[i].value,
                        textAlign: TextAlign.right,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 13.5, fontWeight: FontWeight.w700),
                      ),
                    ),
                    if (rows[i].copy) ...[
                      const SizedBox(width: 6),
                      Icon(Icons.copy_rounded,
                          size: 13, color: scheme.onSurfaceVariant),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _TimelineCard extends StatelessWidget {
  const _TimelineCard({required this.entries, required this.loading});

  final List<ActivityEntry> entries;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    if (entries.isEmpty) {
      return AppCard(
        child: SizedBox(
          height: 66,
          child: Center(
            child: loading
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2.2))
                : const Text('Nothing recorded against this lead yet.'),
          ),
        ),
      );
    }
    return AppCard(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: _TimelineList(entries: entries),
    );
  }
}

class _TimelineList extends StatelessWidget {
  const _TimelineList({required this.entries});

  final List<ActivityEntry> entries;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      children: [
        for (var i = 0; i < entries.length; i++)
          IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Column(
                  children: [
                    Container(
                      width: 10,
                      height: 10,
                      margin: const EdgeInsets.only(top: 4),
                      decoration: BoxDecoration(
                        color: entries[i].auto ? scheme.outline : Brand.amber,
                        shape: BoxShape.circle,
                      ),
                    ),
                    if (i != entries.length - 1)
                      Expanded(
                        child: Container(
                          width: 1.5,
                          margin: const EdgeInsets.symmetric(vertical: 3),
                          color: scheme.outlineVariant,
                        ),
                      ),
                  ],
                ),
                const SizedBox(width: 13),
                Expanded(
                  child: Padding(
                    padding: EdgeInsets.only(
                        bottom: i == entries.length - 1 ? 0 : 18),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          entries[i].description,
                          style: const TextStyle(fontSize: 13.5, height: 1.4),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          [
                            if (entries[i].actor.isNotEmpty) entries[i].actor,
                            dateTimeLabel(entries[i].timestamp),
                          ].join(' · '),
                          style: TextStyle(
                              fontSize: 11.5, color: scheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _TimelineScreen extends StatelessWidget {
  const _TimelineScreen({required this.name, required this.entries});

  final String name;
  final List<ActivityEntry> entries;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(name.isEmpty ? 'Timeline' : name)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [
          AppCard(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
            child: _TimelineList(entries: entries),
          ),
        ],
      ),
    );
  }
}
