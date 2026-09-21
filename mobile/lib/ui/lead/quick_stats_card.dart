import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../theme.dart';
import '../widgets/common.dart';

/// The web page's right-hand sidebar: the handful of figures somebody wants
/// before they pick up the phone.
class QuickStatsCard extends StatelessWidget {
  const QuickStatsCard({super.key, required this.lead});

  final Lead lead;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final score = lead.leadScore;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SectionHeader(
          title: 'Quick stats',
          icon: Icons.insights_outlined,
        ),
        AppCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const FieldLabel('Lead score'),
              Row(
                children: [
                  Expanded(
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(999),
                      child: LinearProgressIndicator(
                        value: score / 100,
                        minHeight: 8,
                        backgroundColor: scheme.surfaceContainerHighest,
                        valueColor: const AlwaysStoppedAnimation(Brand.amber),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    '$score',
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 18),
              Row(
                children: [
                  Expanded(
                    child: _Stat(
                      label: 'Days in pipeline',
                      value: '${lead.daysInPipeline}',
                      big: true,
                    ),
                  ),
                  Expanded(
                    child: _Stat(
                      label: 'Deal value',
                      value: lead.value > 0 ? money(lead.value) : '—',
                      big: true,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              _Stat(
                label: 'Tele caller',
                value: lead.teleCallerName.isNotEmpty
                    ? lead.teleCallerName
                    : (lead.assignedToName.isNotEmpty
                          ? lead.assignedToName
                          : 'Unassigned'),
                color: Brand.info,
              ),
              const SizedBox(height: 14),
              _Stat(
                label: 'BDE',
                value: lead.bdeName.isEmpty ? 'Not assigned' : lead.bdeName,
                color: lead.bdeName.isEmpty ? null : const Color(0xFF3B82F6),
              ),
              if (lead.installationLocation.isNotEmpty) ...[
                const SizedBox(height: 14),
                _Stat(
                  label: 'Installation location',
                  value: lead.installationLocation,
                ),
              ],
              const SizedBox(height: 14),
              _Stat(
                label: 'Documentation',
                value: !lead.pushedToDocumentation
                    ? 'Not pushed'
                    : (lead.documentationStaffName.isNotEmpty
                          ? 'Staff: ${lead.documentationStaffName}'
                          : 'Pushed — unassigned'),
                color: lead.pushedToDocumentation ? Brand.amber : null,
              ),
              if (lead.productName.isNotEmpty) ...[
                const SizedBox(height: 14),
                _Stat(label: 'Product', value: lead.productName),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({
    required this.label,
    required this.value,
    this.color,
    this.big = false,
  });

  final String label;
  final String value;
  final Color? color;
  final bool big;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        FieldLabel(label),
        Text(
          value,
          style: TextStyle(
            fontSize: big ? 18 : 13.5,
            fontWeight: big ? FontWeight.w800 : FontWeight.w700,
            color: color ?? scheme.onSurface,
          ),
        ),
      ],
    );
  }
}
