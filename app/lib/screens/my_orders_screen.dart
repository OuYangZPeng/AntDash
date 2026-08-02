import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'bundle_detail_screen.dart';
import 'widgets.dart';

/// A tiny valid 1x1 JPEG stand-in for a captured gate photo.
const List<int> _demoJpeg = [
  0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
  0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xD9
];

class MyOrdersScreen extends StatefulWidget {
  const MyOrdersScreen({super.key});

  @override
  State<MyOrdersScreen> createState() => MyOrdersScreenState();
}

class MyOrdersScreenState extends State<MyOrdersScreen> {
  List<Bundle> _bundles = [];
  List<RiderDelivery> _deliveries = [];
  bool _loading = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    reload();
  }

  bool get _isRider => context.read<AppState>().role == 'rider';

  /// Public so the shell can refresh this tab when it becomes visible.
  Future<void> reload() async {
    if (!mounted) return;
    setState(() => _loading = true);
    try {
      final state = context.read<AppState>();
      final myId = state.user?.id;
      final all = await state.api.bundles();
      _bundles = all
          .where((b) =>
              (b.status == 'accepted' ||
                  b.status == 'delivered' ||
                  b.status == 'settled') &&
              (myId == null || b.anterId == myId))
          .toList();
      if (state.role == 'rider') {
        _deliveries = await state.api.myDeliveries();
      } else {
        _deliveries = [];
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _generateTestOrders() async {
    setState(() => _busy = true);
    try {
      final res = await context.read<AppState>().api.generateForMe(count: 6);
      await reload();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text(
                  '已生成 ${res['generated']} 单配送 · 成团 ${res['bundles_ready']} 个,已推送到接单大厅'),
              backgroundColor: AppColors.success),
        );
      }
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

  Future<void> _dropAtGate(RiderDelivery d) async {
    setState(() => _busy = true);
    try {
      final api = context.read<AppState>().api;
      int discount = 0;
      for (final o in d.orders.where((o) => !o.droppedAtGate)) {
        final res = await api.uploadGateProof(o.id, _demoJpeg);
        discount += (res['discount_cents'] as int?) ?? 0;
      }
      await reload();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text(discount > 0
                  ? '已确认送达门口,提前到达奖励省 ${yuan(discount)} 跑腿费'
                  : '已确认送达小区门口'),
              backgroundColor: AppColors.success),
        );
      }
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

  @override
  Widget build(BuildContext context) {
    final rider = _isRider;
    final empty = _bundles.isEmpty && _deliveries.isEmpty;
    return Scaffold(
      appBar: AppBar(
        title: const Text('我的订单'),
        actions: [
          if (rider)
            IconButton(
              tooltip: '快捷测试:生成配送单并推送',
              onPressed: _busy ? null : _generateTestOrders,
              icon: const Icon(Icons.add_road),
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: reload,
        child: _loading && empty
            ? const Center(child: CircularProgressIndicator())
            : empty
                ? ListView(children: const [
                    SizedBox(height: 120),
                    EmptyState(
                        icon: Icons.local_shipping_outlined,
                        message: '暂无配送中或已完成的订单'),
                  ])
                : ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      if (rider && _deliveries.isNotEmpty) ...[
                        const _SectionTitle('我的配送 · 送到小区门口'),
                        const SizedBox(height: 8),
                        for (final d in _deliveries) ...[
                          _DeliveryCard(
                            delivery: d,
                            busy: _busy,
                            onDrop: () => _dropAtGate(d),
                          ),
                          const SizedBox(height: 12),
                        ],
                        const SizedBox(height: 8),
                      ],
                      _SectionTitle(rider ? '我接的聚合单 (当 Anter)' : '我的聚合单'),
                      const SizedBox(height: 8),
                      if (_bundles.isEmpty)
                        const Padding(
                          padding: EdgeInsets.symmetric(vertical: 24),
                          child: Center(
                              child: Text('还没有接聚合单,去接单大厅接一单吧',
                                  style: TextStyle(color: AppColors.subtle))),
                        ),
                      for (final b in _bundles) ...[
                        BundleCard(
                          bundle: b,
                          onTap: () async {
                            await Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (_) => BundleDetailScreen(bundle: b),
                              ),
                            );
                            reload();
                          },
                        ),
                        const SizedBox(height: 12),
                      ],
                    ],
                  ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  final String text;
  const _SectionTitle(this.text);

  @override
  Widget build(BuildContext context) => Text(text,
      style: const TextStyle(
          fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.ink));
}

class _DeliveryCard extends StatelessWidget {
  final RiderDelivery delivery;
  final bool busy;
  final VoidCallback onDrop;
  const _DeliveryCard(
      {required this.delivery, required this.busy, required this.onDrop});

  @override
  Widget build(BuildContext context) {
    final d = delivery;
    return Card(
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
                  child: Text(d.communityName,
                      style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: AppColors.ink)),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.brand.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(d.bundleStatusLabel,
                      style: const TextStyle(
                          fontSize: 12,
                          color: AppColors.brandDark,
                          fontWeight: FontWeight.w600)),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text('我的订单 ${d.orders.length} 单 · 聚合单共 ${d.orderCount} 单',
                style: const TextStyle(fontSize: 13, color: AppColors.subtle)),
            const SizedBox(height: 6),
            if (!d.allDropped && d.gateDeadline != null)
              CountdownLabel(deadline: d.gateDeadline!, prefix: '距超时 '),
            const SizedBox(height: 12),
            if (d.allDropped)
              Row(children: [
                const Icon(Icons.verified, color: AppColors.success, size: 18),
                const SizedBox(width: 6),
                Text(
                    d.gateDiscountTotal > 0
                        ? '已送到门口 · 提前奖励省 ${yuan(d.gateDiscountTotal)}'
                        : '已送到门口',
                    style: const TextStyle(
                        color: AppColors.success, fontWeight: FontWeight.w600)),
              ])
            else ...[
              const Text('越早送到小区门口,跑腿费越省(给聚合单更多派送时间)',
                  style: TextStyle(fontSize: 12, color: AppColors.subtle)),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: busy ? null : onDrop,
                  icon: const Icon(Icons.camera_alt_outlined),
                  label: const Text('拍照确认送达小区门口'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
