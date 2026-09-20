import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../state/auth.dart';
import '../state/stores.dart';
import 'widgets/common.dart';

/// Create a lead, or edit one. The same form both ways — the CRM's own lead
/// form has far more on it, but these are the fields a phone is used for.
class LeadFormScreen extends StatefulWidget {
  const LeadFormScreen({super.key, this.lead});

  final Lead? lead;

  bool get isEdit => lead != null;

  @override
  State<LeadFormScreen> createState() => _LeadFormScreenState();
}

class _LeadFormScreenState extends State<LeadFormScreen> {
  final _form = GlobalKey<FormState>();
  late final _firstName = TextEditingController(text: widget.lead?.firstName);
  late final _lastName = TextEditingController(text: widget.lead?.lastName);
  late final _phone = TextEditingController(text: widget.lead?.phone);
  late final _email = TextEditingController(text: widget.lead?.email);
  late final _company = TextEditingController(text: widget.lead?.company);
  late final _install =
      TextEditingController(text: widget.lead?.installationLocation);
  late final _value = TextEditingController(
      text: (widget.lead?.value ?? 0) > 0
          ? widget.lead!.value.toStringAsFixed(0)
          : '');
  late final _notes = TextEditingController(text: widget.lead?.notes);

  late String _status = widget.lead?.status ?? 'new';
  late String? _district =
      (widget.lead?.district.isNotEmpty ?? false) ? widget.lead!.district : null;
  late int? _productId = widget.lead?.productId;
  late int? _assigneeId = widget.lead?.assignedToId;

  bool _saving = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<LookupStore>().ensure();
    });
  }

  @override
  void dispose() {
    for (final c in [
      _firstName,
      _lastName,
      _phone,
      _email,
      _company,
      _install,
      _value,
      _notes,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_form.currentState?.validate() ?? false)) return;
    FocusScope.of(context).unfocus();
    setState(() => _saving = true);

    final payload = <String, dynamic>{
      'first_name': _firstName.text.trim(),
      'last_name': _lastName.text.trim(),
      'phone': _phone.text.trim(),
      'email': _email.text.trim(),
      'company': _company.text.trim(),
      'installation_location': _install.text.trim(),
      'district': _district ?? '',
      'status': _status,
      'value': _value.text.trim().isEmpty ? '0' : _value.text.trim(),
      'notes': _notes.text.trim(),
      'product': _productId,
      'assigned_to': _assigneeId,
    };

    final api = context.read<ApiClient>();
    try {
      final body = widget.isEdit
          ? await api.patch('/api/leads/${widget.lead!.id}/', payload)
          : await api.post('/api/leads/', payload);
      if (!mounted) return;
      final lead = Lead((body as Map).cast<String, dynamic>());
      context.read<LeadStore>().upsert(lead);
      context.read<DashboardStore>().load(force: true);
      HapticFeedback.mediumImpact();
      showToast(context, widget.isEdit ? 'Lead updated.' : 'Lead created.');
      Navigator.of(context).pop(lead);
    } on ApiException catch (e) {
      if (mounted) showToast(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final lookups = context.watch<LookupStore>();
    final auth = context.watch<AuthController>();
    final statuses = auth.statuses.isEmpty
        ? LeadStatus.fallback
            .map((e) => LeadStatus.fromJson(Map<String, dynamic>.from(e)))
            .toList()
        : auth.statuses;

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.isEdit ? 'Edit lead' : 'New lead'),
        actions: [
          TextButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    width: 17,
                    height: 17,
                    child: CircularProgressIndicator(strokeWidth: 2.2))
                : const Text('Save'),
          ),
          const SizedBox(width: 6),
        ],
      ),
      body: Form(
        key: _form,
        child: ListView(
          padding: EdgeInsets.fromLTRB(
              16, 10, 16, 32 + MediaQuery.of(context).viewInsets.bottom),
          children: [
            const SectionHeader(
                title: 'Who', icon: Icons.person_outline_rounded),
            AppCard(
              child: Column(
                children: [
                  TextFormField(
                    controller: _firstName,
                    textCapitalization: TextCapitalization.words,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(labelText: 'First name *'),
                    validator: (v) => (v == null || v.trim().isEmpty)
                        ? 'A name is required'
                        : null,
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _lastName,
                    textCapitalization: TextCapitalization.words,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(labelText: 'Last name'),
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _phone,
                    keyboardType: TextInputType.phone,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(
                      labelText: 'Phone',
                      prefixIcon: Icon(Icons.call_rounded, size: 19),
                    ),
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      prefixIcon: Icon(Icons.mail_outline_rounded, size: 19),
                    ),
                    validator: (v) {
                      final value = v?.trim() ?? '';
                      if (value.isEmpty) return null;
                      return RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
                              .hasMatch(value)
                          ? null
                          : 'That email does not look right';
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            const SectionHeader(title: 'Where', icon: Icons.place_outlined),
            AppCard(
              child: Column(
                children: [
                  TextFormField(
                    controller: _company,
                    textCapitalization: TextCapitalization.words,
                    decoration:
                        const InputDecoration(labelText: 'Place / locality'),
                  ),
                  const SizedBox(height: 14),
                  DropdownButtonFormField<String?>(
                    initialValue: lookups.districts.contains(_district)
                        ? _district
                        : null,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'District'),
                    items: [
                      const DropdownMenuItem<String?>(
                          value: null, child: Text('Not set')),
                      for (final d in lookups.districts)
                        DropdownMenuItem<String?>(value: d, child: Text(d)),
                    ],
                    onChanged: (v) => setState(() => _district = v),
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _install,
                    textCapitalization: TextCapitalization.sentences,
                    decoration: const InputDecoration(
                        labelText: 'Installation site',
                        helperText: 'Where the system goes up'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            const SectionHeader(
                title: 'The deal', icon: Icons.handshake_outlined),
            AppCard(
              child: Column(
                children: [
                  DropdownButtonFormField<String>(
                    initialValue: _status,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Status'),
                    items: [
                      for (final s in statuses)
                        DropdownMenuItem(
                          value: s.value,
                          child: Row(
                            children: [
                              Container(
                                width: 9,
                                height: 9,
                                decoration: BoxDecoration(
                                    color: s.color, shape: BoxShape.circle),
                              ),
                              const SizedBox(width: 9),
                              Text(s.label),
                            ],
                          ),
                        ),
                    ],
                    onChanged: (v) => setState(() => _status = v ?? 'new'),
                  ),
                  const SizedBox(height: 14),
                  DropdownButtonFormField<int?>(
                    initialValue: lookups.products
                            .any((p) => p['id'] == _productId)
                        ? _productId
                        : null,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Product'),
                    items: [
                      const DropdownMenuItem<int?>(
                          value: null, child: Text('Not set')),
                      for (final p in lookups.products)
                        DropdownMenuItem<int?>(
                          value: p['id'] as int?,
                          child: Text((p['name'] ?? '').toString(),
                              overflow: TextOverflow.ellipsis),
                        ),
                    ],
                    onChanged: (v) => setState(() => _productId = v),
                  ),
                  const SizedBox(height: 14),
                  TextFormField(
                    controller: _value,
                    keyboardType:
                        const TextInputType.numberWithOptions(decimal: true),
                    decoration: const InputDecoration(
                      labelText: 'Deal value',
                      prefixText: '₹ ',
                    ),
                    validator: (v) {
                      final value = v?.trim() ?? '';
                      if (value.isEmpty) return null;
                      return double.tryParse(value) == null
                          ? 'Numbers only'
                          : null;
                    },
                  ),
                  const SizedBox(height: 14),
                  DropdownButtonFormField<int?>(
                    initialValue: lookups.users.any((u) => u.id == _assigneeId)
                        ? _assigneeId
                        : null,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Assign to'),
                    items: [
                      const DropdownMenuItem<int?>(
                          value: null, child: Text('Unassigned')),
                      for (final u in lookups.users)
                        DropdownMenuItem<int?>(
                          value: u.id,
                          child: Text(
                            u.roleLabel.isEmpty
                                ? u.name
                                : '${u.name} · ${u.roleLabel}',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                    onChanged: (v) => setState(() => _assigneeId = v),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            const SectionHeader(
                title: 'Notes', icon: Icons.sticky_note_2_outlined),
            AppCard(
              child: TextFormField(
                controller: _notes,
                maxLines: 5,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(
                  hintText: 'What did they say? What did you promise?',
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  filled: false,
                  contentPadding: EdgeInsets.zero,
                ),
              ),
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: _saving ? null : _save,
              icon: const Icon(Icons.check_rounded, size: 19),
              label: Text(widget.isEdit ? 'Save changes' : 'Create lead'),
            ),
          ],
        ),
      ),
    );
  }
}
