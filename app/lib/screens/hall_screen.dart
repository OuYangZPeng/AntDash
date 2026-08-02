import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'bundle_detail_screen.dart';
import 'widgets.dart';

class HallScreen extends StatefulWidget {
  const HallScreen({super.key});

  @override
  State<HallScreen> createState() => _HallScreenState();
}

class _HallScreenState extends State<HallScreen> {
  List<Bundle> _bundles = [];
  bool _loading = false;
  String? _error;
  StreamSubscription? _notifSub;

  @override
  void initState() {
    super.initState();
    _load();
    // Auto-refresh when a nearby new-order push arrives.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _notifSub = context.read<AppState>().notifications.listen((_) => _load());
    });
  }

  @override
  void dispose() {
    _notifSub?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await context.read<AppState>().api.offers();
      // Most-urgent (soonest SLA) first.
      list.sort((a, b) {
        final sa = a.soonestSla, sb = b.soonestSla;
        if (sa == null && sb == null) return 0;
        if (sa == null) return 1;
        if (sb == null) return -1;
        return sa.compareTo(sb);
      });
      _bundles = list;
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _ingest() async {
    setState(() => _loading = true);
    try {
      await context.read<AppState>().api.ingest(limit: 10);
      await _load();
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final city = context.watch<AppState>().city;
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Text('接单大厅'),
            if (city != null) ...[
              const SizedBox(width: 8),
              const Icon(Icons.location_on, size: 15, color: AppColors.subtle),
              const SizedBox(width: 2),
              Text(city,
                  style: const TextStyle(
                      fontSize: 13,
                      color: AppColors.subtle,
                      fontWeight: FontWeight.w500)),
            ],
          ],
        ),
        actions: [
          IconButton(
            tooltip: '模拟拉取平台订单',
            onPressed: _loading ? null : _ingest,
            icon: const Icon(Icons.cloud_download_outlined),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading && _bundles.isEmpty
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? ListView(children: [
                    const SizedBox(height: 120),
                    Center(
                        child: Text(_error!,
                            style: const TextStyle(color: AppColors.danger))),
                  ])
                : _bundles.isEmpty
                    ? ListView(children: const [
                        SizedBox(height: 120),
                        EmptyState(
                            icon: Icons.inbox_outlined,
                            message: '暂无可接聚合单,点击右上角拉取订单'),
                      ])
                    : ListView.separated(
                        padding: const EdgeInsets.all(16),
                        itemCount: _bundles.length,
                        separatorBuilder: (_, __) =>
                            const SizedBox(height: 12),
                        itemBuilder: (_, i) => BundleCard(
                          bundle: _bundles[i],
                          onTap: () async {
                            await Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (_) =>
                                    BundleDetailScreen(bundle: _bundles[i]),
                              ),
                            );
                            _load();
                          },
                        ),
                      ),
      ),
    );
  }
}
