import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../theme.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    final user = state.user;
    return Scaffold(
      appBar: AppBar(title: const Text('我的')),
      body: RefreshIndicator(
        onRefresh: () => state.refreshMe(),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Row(
                  children: [
                    CircleAvatar(
                      radius: 32,
                      backgroundColor: AppColors.brand.withOpacity(0.15),
                      child: const Icon(Icons.person,
                          size: 36, color: AppColors.brand),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(user?.name ?? '未认证用户',
                              style: const TextStyle(
                                  fontSize: 19, fontWeight: FontWeight.w700)),
                          const SizedBox(height: 4),
                          Text(
                              '${_roleLabel(user?.role)} · ${user?.phone ?? '-'}',
                              style: const TextStyle(color: AppColors.subtle)),
                          const SizedBox(height: 6),
                          if (user?.verified ?? false)
                            Row(children: const [
                              Icon(Icons.verified,
                                  size: 16, color: AppColors.success),
                              SizedBox(width: 4),
                              Text('已实名',
                                  style: TextStyle(
                                      color: AppColors.success, fontSize: 12)),
                            ]),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                _statCard('信誉分',
                    (user?.reputationScore ?? 0).toStringAsFixed(0),
                    Icons.stars_outlined),
                const SizedBox(width: 12),
                _statCard(
                    '准时率',
                    '${((user?.onTimeRate ?? 0) * 100).toStringAsFixed(0)}%',
                    Icons.timelapse),
              ],
            ),
            const SizedBox(height: 16),
            _reputationHint(user?.reputationScore ?? 0),
            const SizedBox(height: 24),
            Card(
              child: Column(children: [
                const ListTile(
                    leading: Icon(Icons.shield_outlined),
                    title: Text('实名认证'),
                    trailing: Text('已完成',
                        style: TextStyle(color: AppColors.success))),
                const Divider(height: 1),
                ListTile(
                    leading: const Icon(Icons.help_outline),
                    title: const Text('帮助与规则'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => showDialog(
                          context: context,
                          builder: (_) => const _RulesDialog(),
                        )),
              ]),
            ),
            const SizedBox(height: 24),
            OutlinedButton(
              onPressed: () => context.read<AppState>().logout(),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(52),
                foregroundColor: AppColors.danger,
                side: const BorderSide(color: AppColors.danger),
              ),
              child: const Text('退出登录'),
            ),
          ],
        ),
      ),
    );
  }

  String _roleLabel(String? role) => switch (role) {
        'anter' => 'Anter 跑腿员',
        'rider' => '外卖骑手',
        'admin' => '管理员',
        _ => '用户',
      };

  Widget _statCard(String label, String value, IconData icon) {
    return Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: AppColors.brand),
              const SizedBox(height: 10),
              Text(value,
                  style: const TextStyle(
                      fontSize: 24, fontWeight: FontWeight.bold)),
              Text(label, style: const TextStyle(color: AppColors.subtle)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _reputationHint(double score) {
    final cooling = score < 35;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cooling
            ? AppColors.danger.withOpacity(0.08)
            : AppColors.success.withOpacity(0.08),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(children: [
        Icon(cooling ? Icons.warning_amber : Icons.trending_up,
            color: cooling ? AppColors.danger : AppColors.success),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            cooling
                ? '信誉分偏低,派单频率已下调。准时履约可逐步恢复。'
                : '信誉良好,优先获得聚合单派发。准时履约将持续加分。',
            style: TextStyle(
                color: cooling ? AppColors.danger : AppColors.success,
                fontSize: 13),
          ),
        ),
      ]),
    );
  }
}

class _RulesDialog extends StatelessWidget {
  const _RulesDialog();

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('接单与信誉规则'),
      content: const SingleChildScrollView(
        child: Text(
          '· 接单后必须履约,无故甩单将大幅扣减信誉分。\n'
          '· 准时/提前送达加分,超时或被投诉扣分。\n'
          '· 信誉分越高,派单越优先、越频繁。\n'
          '· 信誉过低将进入冷却期,减少派单。\n\n'
          '收入规则:\n'
          '· 跑腿费 = 订单总额 × X%\n'
          '· 平台服务费 = 跑腿费 × Y%\n'
          '· 实际到手 = 订单总额 × X% × (1 - Y%)',
        ),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context), child: const Text('知道了')),
      ],
    );
  }
}
