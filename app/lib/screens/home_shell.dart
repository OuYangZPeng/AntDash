import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';
import 'hall_screen.dart';
import 'my_orders_screen.dart';
import 'wallet_screen.dart';
import 'profile_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;
  StreamSubscription? _notifSub;
  bool _dialogOpen = false;

  final _ordersKey = GlobalKey<MyOrdersScreenState>();

  late final List<Widget> _pages = [
    const HallScreen(),
    MyOrdersScreen(key: _ordersKey),
    const WalletScreen(),
    const ProfileScreen(),
  ];

  void _onTab(int i) {
    setState(() => _index = i);
    // Refresh "我的订单" whenever it becomes visible (e.g. after accepting).
    if (i == 1) _ordersKey.currentState?.reload();
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final state = context.read<AppState>();
      state.locateCity();
      state.connectNotifications();
      _notifSub = state.notifications.listen(_onNewBundle);
    });
  }

  @override
  void dispose() {
    _notifSub?.cancel();
    super.dispose();
  }

  void _onNewBundle(Map<String, dynamic> event) {
    if (!mounted || _dialogOpen) return;
    _dialogOpen = true;
    final type = event['type'] as String?;
    final community = event['community_name'] ?? '附近小区';
    final count = event['order_count'] ?? 0;
    final net = event['anter_net_cents'] as int?;
    final dist = (event['distance_km'] as num?)?.toDouble();
    final urgencyFee = event['urgency_fee_cents'] as int?;
    final remaining = event['remaining_minutes'] as int?;
    final isRescue = type == 'rescue';
    final isUrgent = type == 'urgent' || isRescue;

    final title = isRescue ? '急单救援 · 抢单有奖' : (isUrgent ? '附近急单(加急费)' : '附近新订单');
    final accent = isUrgent ? AppColors.danger : AppColors.brand;
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        icon: Icon(isUrgent ? Icons.local_fire_department : Icons.notifications_active,
            color: accent, size: 36),
        title: Text(title),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('$community · $count 单',
                style: const TextStyle(
                    fontSize: 16, fontWeight: FontWeight.w700, color: AppColors.ink)),
            const SizedBox(height: 6),
            Text([
              if (net != null) '预计实收 ${yuan(net)}',
              if (dist != null) '距你 ${dist.toStringAsFixed(2)} km',
              if (remaining != null) '剩 $remaining 分钟',
            ].join(' · '), style: const TextStyle(color: AppColors.subtle)),
            if (urgencyFee != null && urgencyFee > 0) ...[
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: AppColors.danger.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text('含加急费 +${yuan(urgencyFee)}',
                    style: const TextStyle(
                        color: AppColors.danger, fontWeight: FontWeight.w700)),
              ),
            ],
            if (isRescue) ...[
              const SizedBox(height: 8),
              const Text('外卖骑手也可接单救援,送达额外奖励 + 优先派单',
                  style: TextStyle(fontSize: 12, color: AppColors.subtle),
                  textAlign: TextAlign.center),
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('忽略'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(ctx);
              setState(() => _index = 0);
            },
            child: const Text('去接单'),
          ),
        ],
      ),
    ).whenComplete(() => _dialogOpen = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: _onTab,
        destinations: const [
          NavigationDestination(
              icon: Icon(Icons.list_alt_outlined),
              selectedIcon: Icon(Icons.list_alt),
              label: '接单大厅'),
          NavigationDestination(
              icon: Icon(Icons.local_shipping_outlined),
              selectedIcon: Icon(Icons.local_shipping),
              label: '我的订单'),
          NavigationDestination(
              icon: Icon(Icons.account_balance_wallet_outlined),
              selectedIcon: Icon(Icons.account_balance_wallet),
              label: '钱包'),
          NavigationDestination(
              icon: Icon(Icons.person_outline),
              selectedIcon: Icon(Icons.person),
              label: '我的'),
        ],
      ),
    );
  }
}
