import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'widgets.dart';

/// A tiny valid 1x1 JPEG used as a stand-in for a captured photo so the
/// proof-upload flow is demonstrable on any platform without camera setup.
/// In production replace with image_picker + real camera capture.
const List<int> _demoJpeg = [
  0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
  0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xD9
];

class BundleDetailScreen extends StatefulWidget {
  final Bundle bundle;
  const BundleDetailScreen({super.key, required this.bundle});

  @override
  State<BundleDetailScreen> createState() => _BundleDetailScreenState();
}

class _BundleDetailScreenState extends State<BundleDetailScreen> {
  late Bundle _bundle;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _bundle = widget.bundle;
  }

  AppState get _state => context.read<AppState>();

  Future<void> _guard(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString()), backgroundColor: AppColors.danger),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _accept() => _guard(() async {
        _bundle = await _state.api.accept(_bundle.id);
        setState(() {});
      });

  Future<void> _uploadOrderProof(OrderItem order) => _guard(() async {
        final res = await _state.api.uploadOrderProof(order.id, _demoJpeg);
        _bundle = await _state.api.getBundle(_bundle.id);
        setState(() {});
        if (mounted) {
          final remaining = res['remaining'] as int? ?? 0;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text(remaining == 0
                    ? '全部子单已拍照,可确认送达'
                    : '已上传,还剩 $remaining 单待拍照'),
                backgroundColor: AppColors.success),
          );
        }
      });

  Future<void> _deliver() => _guard(() async {
        _bundle = await _state.api.deliver(_bundle.id);
        await _state.refreshMe();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text('送达成功,已结算 ${yuan(_bundle.anterNetCents)}'),
                backgroundColor: AppColors.success),
          );
        }
        setState(() {});
      });

  @override
  Widget build(BuildContext context) {
    final b = _bundle;
    // Sub-orders sorted by urgency: soonest SLA first.
    final orders = [...b.orders]
      ..sort((x, y) => x.slaDeadline.compareTo(y.slaDeadline));
    final accepted = b.status == 'accepted';
    final uploaded = orders.where((o) => o.proofUploaded).length;
    return Scaffold(
      appBar: AppBar(title: Text(b.communityName)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          BundleCard(bundle: b),
          const SizedBox(height: 20),
          Row(
            children: [
              const Text('订单明细 (按超时紧急度排序)',
                  style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: AppColors.ink)),
              const Spacer(),
              if (accepted)
                Text('$uploaded/${orders.length} 已拍照',
                    style: const TextStyle(
                        fontSize: 12, color: AppColors.subtle)),
            ],
          ),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                for (int i = 0; i < orders.length; i++) ...[
                  if (i > 0) const Divider(height: 1),
                  _OrderTile(
                    order: orders[i],
                    rank: i + 1,
                    accepted: accepted,
                    busy: _busy,
                    onUpload: () => _uploadOrderProof(orders[i]),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 20),
          _SplitBreakdown(bundle: b, role: _state.role),
          const SizedBox(height: 24),
          _actionButton(b, uploaded, orders.length),
        ],
      ),
    );
  }

  Widget _actionButton(Bundle b, int uploaded, int total) {
    if (_busy) {
      return const Center(child: CircularProgressIndicator());
    }
    switch (b.status) {
      case 'at_gate':
        return ElevatedButton.icon(
          onPressed: _accept,
          icon: const Icon(Icons.check_circle_outline),
          label: const Text('立即接单'),
        );
      case 'accepted':
        final allDone = uploaded >= total && total > 0;
        return Column(
          children: [
            if (!allDone)
              const Padding(
                padding: EdgeInsets.only(bottom: 8),
                child: Text('请先为每个子单拍照上传,再确认送达',
                    style: TextStyle(fontSize: 12, color: AppColors.subtle)),
              ),
            ElevatedButton.icon(
              onPressed: allDone ? _deliver : null,
              icon: const Icon(Icons.verified_outlined),
              label: Text(allDone ? '确认送达' : '确认送达 ($uploaded/$total)'),
            ),
          ],
        );
      case 'settled':
      case 'delivered':
        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppColors.success.withOpacity(0.1),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Row(children: const [
            Icon(Icons.verified, color: AppColors.success),
            SizedBox(width: 8),
            Text('订单已完成并结算', style: TextStyle(color: AppColors.success)),
          ]),
        );
      default:
        return const SizedBox.shrink();
    }
  }
}

class _OrderTile extends StatelessWidget {
  final OrderItem order;
  final int rank;
  final bool accepted;
  final bool busy;
  final VoidCallback onUpload;
  const _OrderTile({
    required this.order,
    required this.rank,
    required this.accepted,
    required this.busy,
    required this.onUpload,
  });

  @override
  Widget build(BuildContext context) {
    final badges = <String>[
      if (order.floorLabel != null) order.floorLabel!,
      if (order.categoryLabel != null) order.categoryLabel!,
    ];
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: AppColors.brand.withOpacity(0.12),
        child: Text('$rank',
            style: const TextStyle(
                color: AppColors.brandDark, fontWeight: FontWeight.bold)),
      ),
      title: Text('${order.platformLabel} · ${yuan(order.riderIncomeCents)}'),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(order.address, maxLines: 1, overflow: TextOverflow.ellipsis),
          const SizedBox(height: 4),
          // 距离超时的实时倒计时(精确到秒)
          CountdownLabel(deadline: order.slaDeadline, prefix: '超时倒计时 '),
          if (badges.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Wrap(
                spacing: 6,
                children: [for (final t in badges) _MiniChip(text: t)],
              ),
            ),
        ],
      ),
      trailing: _trailing(),
    );
  }

  Widget? _trailing() {
    // While delivering: each sub-order has its own photo-upload button.
    if (accepted) {
      if (order.proofUploaded) {
        return const Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle, color: AppColors.success, size: 22),
            SizedBox(height: 2),
            Text('已拍照',
                style: TextStyle(fontSize: 11, color: AppColors.success)),
          ],
        );
      }
      return OutlinedButton.icon(
        onPressed: busy ? null : onUpload,
        icon: const Icon(Icons.camera_alt_outlined, size: 16),
        label: const Text('拍照'),
        style: OutlinedButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 10),
          visualDensity: VisualDensity.compact,
        ),
      );
    }
    // Rider-scoped: backend returns this order's deduction for the rider only.
    if (order.riderChargeCents != null) {
      return Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          const Text('本单扣款',
              style: TextStyle(fontSize: 11, color: AppColors.subtle)),
          Text('-${yuan(order.riderChargeCents!)}',
              style: const TextStyle(
                  color: AppColors.danger, fontWeight: FontWeight.w700)),
        ],
      );
    }
    return null;
  }
}

class _MiniChip extends StatelessWidget {
  final String text;
  const _MiniChip({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: AppColors.subtle.withOpacity(0.12),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(text,
          style: const TextStyle(fontSize: 11, color: AppColors.subtle)),
    );
  }
}

/// Split breakdown, role-scoped:
/// - rider: shows only "本单扣款" total (anter economics hidden by backend).
/// - anter/admin: full dynamic-pricing breakdown (base + surge/weather + net).
class _SplitBreakdown extends StatelessWidget {
  final Bundle bundle;
  final String? role;
  const _SplitBreakdown({required this.bundle, this.role});

  @override
  Widget build(BuildContext context) {
    if (role == 'rider') return _riderView();
    if (bundle.hasDynamicPrice) return _dynamicAnterView();
    return _legacyView();
  }

  Widget _card(String title, List<Widget> children, {List<String> tags = const []}) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Text(title,
                    style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: AppColors.ink)),
                const Spacer(),
                for (final t in tags)
                  Padding(
                    padding: const EdgeInsets.only(left: 6),
                    child: _SurgeChip(text: t),
                  ),
              ],
            ),
            const SizedBox(height: 6),
            ...children,
          ],
        ),
      ),
    );
  }

  static Widget _row(String k, String v,
      {bool bold = false, Color? valueColor, bool indent = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Padding(
            padding: EdgeInsets.only(left: indent ? 14 : 0),
            child: Text(k,
                style: TextStyle(
                    color: bold ? AppColors.ink : AppColors.subtle,
                    fontWeight: bold ? FontWeight.w700 : FontWeight.normal)),
          ),
          Text(v,
              style: TextStyle(
                  color: valueColor ?? (bold ? AppColors.brand : AppColors.ink),
                  fontWeight: FontWeight.w600,
                  fontSize: bold ? 18 : 14)),
        ],
      ),
    );
  }

  Widget _riderView() {
    final total = bundle.riderChargeCents ??
        bundle.orders.fold<int>(0, (s, o) => s + (o.riderChargeCents ?? 0));
    return _card('本单跑腿费扣款', [
      _row('聚合单', '${bundle.communityName} · ${bundle.orderCount} 单'),
      const Divider(),
      _row('本次扣款合计', '-${yuan(total)}',
          bold: true, valueColor: AppColors.danger),
      const Padding(
        padding: EdgeInsets.only(top: 6),
        child: Text('高峰 / 恶劣天气的运力溢价由平台补贴承担,不额外向你收取。',
            style: TextStyle(fontSize: 12, color: AppColors.subtle)),
      ),
    ]);
  }

  Widget _dynamicAnterView() {
    final base = bundle.basePriceCents ?? 0;
    final quoted = bundle.quotedPriceCents ?? bundle.errandFeeCents;
    return _card('动态定价 · 我的收入', tags: bundle.priceTags, [
      _row('订单总额 (骑手收入)', yuan(bundle.totalIncomeCents)),
      _row('基础包 (距离/楼层/重量)', yuan(base)),
      _row('聚合单价 (跑腿费)', yuan(quoted)),
      _row('· 骑手扣款', yuan(bundle.riderChargeCents ?? 0), indent: true),
      _row('· 平台补贴 (高峰/天气)', yuan(bundle.subsidyCents ?? 0),
          indent: true, valueColor: AppColors.success),
      if (bundle.hasUrgencyFee)
        _row('· 加急费 (临期·平台补贴)', '+${yuan(bundle.urgencyFeeCents)}',
            indent: true, valueColor: AppColors.danger),
      _row('平台服务费 = 跑腿费 × ${bundle.yRate.toStringAsFixed(0)}%',
          '-${yuan(bundle.platformFeeCents)}'),
      const Divider(),
      _row('Anter 实际到手', yuan(bundle.anterNetCents), bold: true),
      if (bundle.rescue)
        const Padding(
          padding: EdgeInsets.only(top: 6),
          child: Text('救援急单:送达后额外发放救援奖金,并提升信誉(优先派单)',
              style: TextStyle(fontSize: 12, color: AppColors.danger)),
        ),
    ]);
  }

  Widget _legacyView() {
    final errand = (bundle.totalIncomeCents * bundle.xRate / 100).round();
    final platform = (errand * bundle.yRate / 100).round();
    final net = errand - platform;
    return _card('分账明细', [
      _row('订单总额 (骑手收入)', yuan(bundle.totalIncomeCents)),
      _row('跑腿费 = 总额 × ${bundle.xRate.toStringAsFixed(0)}%', yuan(errand)),
      _row('平台服务费 = 跑腿费 × ${bundle.yRate.toStringAsFixed(0)}%',
          '-${yuan(platform)}'),
      const Divider(),
      _row('Anter 实际到手', yuan(net), bold: true),
    ]);
  }
}

class _SurgeChip extends StatelessWidget {
  final String text;
  const _SurgeChip({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.brand.withOpacity(0.12),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(text,
          style: const TextStyle(
              fontSize: 11,
              color: AppColors.brandDark,
              fontWeight: FontWeight.w600)),
    );
  }
}
