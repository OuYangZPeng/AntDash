import 'dart:async';

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme.dart';

/// Formats a remaining duration precise to the second (adds hours when needed).
String formatRemaining(Duration d) {
  if (d.isNegative || d == Duration.zero) return '已超时';
  final h = d.inHours;
  final m = d.inMinutes % 60;
  final s = d.inSeconds % 60;
  final ss = s.toString().padLeft(2, '0');
  if (h > 0) {
    final mm = m.toString().padLeft(2, '0');
    return '$h时$mm分$ss秒';
  }
  return '$m分$ss秒';
}

class BundleCard extends StatelessWidget {
  final Bundle bundle;
  final VoidCallback? onTap;
  final Widget? trailing;
  const BundleCard({super.key, required this.bundle, this.onTap, this.trailing});

  @override
  Widget build(BuildContext context) {
    final expiring = bundle.isExpiringSoon();
    // For accepted bundles count down to delivery SLA; otherwise to the soonest
    // order timeout (the order that will breach first).
    final DateTime? countdownDeadline = bundle.status == 'accepted'
        ? bundle.deliveryDeadline
        : (bundle.status == 'at_gate' || bundle.status == 'ready')
            ? bundle.soonestSla
            : null;
    return Card(
      shape: expiring
          ? RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: const BorderSide(color: AppColors.danger, width: 1.5),
            )
          : null,
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.location_on, color: AppColors.brand, size: 20),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(bundle.communityName,
                        style: const TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w700,
                            color: AppColors.ink)),
                  ),
                  if (expiring) ...[
                    const _ExpirePill(),
                    const SizedBox(width: 6),
                  ],
                  _StatusPill(label: bundle.statusLabel),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  _Metric(
                      label: '聚合单数', value: '${bundle.orderCount} 单'),
                  _Metric(label: '订单总额', value: yuan(bundle.totalIncomeCents)),
                  _Metric(
                      label: '我的实收',
                      value: yuan(bundle.anterNetCents > 0
                          ? bundle.anterNetCents
                          : bundle.estimatedAnterNet),
                      highlight: true),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  const Icon(Icons.receipt_long,
                      size: 15, color: AppColors.subtle),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      bundle.hasDynamicPrice
                          ? '跑腿费 ${yuan(bundle.quotedPriceCents!)} · 平台 ${bundle.yRate.toStringAsFixed(0)}%'
                          : '跑腿费 ${yuan((bundle.totalIncomeCents * bundle.xRate / 100).round())} · 抽成 ${bundle.xRate.toStringAsFixed(0)}% · 平台 ${bundle.yRate.toStringAsFixed(0)}%',
                      style: const TextStyle(
                          fontSize: 12, color: AppColors.subtle),
                    ),
                  ),
                  if (countdownDeadline != null)
                    CountdownLabel(prefix: '超时 ', deadline: countdownDeadline),
                ],
              ),
              if (bundle.hasUrgencyFee || bundle.priceTags.isNotEmpty) ...[
                const SizedBox(height: 8),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    if (bundle.hasUrgencyFee)
                      _PriceTag(
                          text: '加急 +${yuan(bundle.urgencyFeeCents)}',
                          danger: true),
                    for (final t in bundle.priceTags) _PriceTag(text: t),
                  ],
                ),
              ],
              if (trailing != null) ...[
                const SizedBox(height: 14),
                trailing!,
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  final String label;
  final String value;
  final bool highlight;
  const _Metric(
      {required this.label, required this.value, this.highlight = false});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: const TextStyle(fontSize: 12, color: AppColors.subtle)),
          const SizedBox(height: 4),
          Text(value,
              style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: highlight ? AppColors.brand : AppColors.ink)),
        ],
      ),
    );
  }
}

class _ExpirePill extends StatelessWidget {
  const _ExpirePill();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.danger.withOpacity(0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: const [
          Icon(Icons.warning_amber_rounded, size: 13, color: AppColors.danger),
          SizedBox(width: 3),
          Text('即将超时',
              style: TextStyle(
                  fontSize: 11,
                  color: AppColors.danger,
                  fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

class _PriceTag extends StatelessWidget {
  final String text;
  final bool danger;
  const _PriceTag({required this.text, this.danger = false});

  @override
  Widget build(BuildContext context) {
    final color = danger ? AppColors.danger : AppColors.brandDark;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: (danger ? AppColors.danger : AppColors.brand).withOpacity(0.12),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(text,
          style: TextStyle(
              fontSize: 11, color: color, fontWeight: FontWeight.w600)),
    );
  }
}

class _StatusPill extends StatelessWidget {
  final String label;
  const _StatusPill({required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.brand.withOpacity(0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(label,
          style: const TextStyle(
              fontSize: 12,
              color: AppColors.brandDark,
              fontWeight: FontWeight.w600)),
    );
  }
}

/// Live, second-by-second countdown to [deadline]. Turns red near/after expiry.
class CountdownLabel extends StatefulWidget {
  final DateTime deadline;
  final String? prefix;
  final double fontSize;
  final double warnSeconds; // go red/orange when remaining <= this
  const CountdownLabel({
    super.key,
    required this.deadline,
    this.prefix,
    this.fontSize = 12,
    this.warnSeconds = 300,
  });

  @override
  State<CountdownLabel> createState() => _CountdownLabelState();
}

class _CountdownLabelState extends State<CountdownLabel> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final remaining = widget.deadline.difference(DateTime.now());
    final over = remaining.isNegative || remaining == Duration.zero;
    final warn = !over && remaining.inSeconds <= widget.warnSeconds;
    final color = over
        ? AppColors.danger
        : warn
            ? AppColors.brand
            : AppColors.success;
    final text = '${widget.prefix ?? ''}${formatRemaining(remaining)}';
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(over ? Icons.timer_off_outlined : Icons.timer_outlined,
            size: widget.fontSize + 3, color: color),
        const SizedBox(width: 4),
        Text(text,
            style: TextStyle(
                fontSize: widget.fontSize,
                color: color,
                fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class EmptyState extends StatelessWidget {
  final IconData icon;
  final String message;
  const EmptyState({super.key, required this.icon, required this.message});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 56, color: AppColors.subtle.withOpacity(0.5)),
          const SizedBox(height: 12),
          Text(message, style: const TextStyle(color: AppColors.subtle)),
        ],
      ),
    );
  }
}
