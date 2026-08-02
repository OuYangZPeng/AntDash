import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/app_state.dart';
import '../theme.dart';

class WalletScreen extends StatefulWidget {
  const WalletScreen({super.key});

  @override
  State<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends State<WalletScreen> {
  int _balance = 0;
  List<LedgerRow> _ledger = [];
  List<PaymentMethod> _methods = [];
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final api = context.read<AppState>().api;
      _balance = await api.balance();
      _ledger = await api.ledger();
      _methods = await api.paymentMethods();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _withdraw() async {
    try {
      final cents = await context.read<AppState>().api.withdraw();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text('提现成功 ${yuan(cents)}'),
              backgroundColor: AppColors.success),
        );
      }
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString()), backgroundColor: AppColors.danger),
        );
      }
    }
  }

  Future<void> _bind() async {
    final kind = await showModalBottomSheet<String>(
      context: context,
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('选择支付方式',
                  style: TextStyle(fontWeight: FontWeight.w700)),
            ),
            ListTile(
                leading: const Icon(Icons.wechat, color: Color(0xFF07C160)),
                title: const Text('微信'),
                onTap: () => Navigator.pop(context, 'wechat')),
            ListTile(
                leading: const Icon(Icons.account_balance_wallet,
                    color: Color(0xFF1677FF)),
                title: const Text('支付宝'),
                onTap: () => Navigator.pop(context, 'alipay')),
            ListTile(
                leading: const Icon(Icons.credit_card),
                title: const Text('银行卡'),
                onTap: () => Navigator.pop(context, 'bank_card')),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (kind == null) return;
    try {
      await context
          .read<AppState>()
          .api
          .bindPayment(kind, '6222021234567890888', '');
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString()), backgroundColor: AppColors.danger),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('钱包')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _balanceCard(),
            const SizedBox(height: 20),
            _sectionHeader('支付方式', action: TextButton(
              onPressed: _bind,
              child: const Text('绑定'),
            )),
            if (_methods.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text('尚未绑定支付方式',
                    style: TextStyle(color: AppColors.subtle)),
              )
            else
              ..._methods.map((m) => Card(
                    child: ListTile(
                      leading: Icon(_iconFor(m.kind)),
                      title: Text(m.kindLabel),
                      subtitle: Text(m.display),
                      trailing: m.isDefault
                          ? const Text('默认',
                              style: TextStyle(color: AppColors.brand))
                          : null,
                    ),
                  )),
            const SizedBox(height: 20),
            _sectionHeader('收支明细'),
            if (_loading && _ledger.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_ledger.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text('暂无收支记录',
                    style: TextStyle(color: AppColors.subtle)),
              )
            else
              ..._ledger.map((e) => Card(
                    child: ListTile(
                      title: Text(e.typeLabel),
                      subtitle: Text(
                          '${e.createdAt.toLocal()}'.split('.').first),
                      trailing: Text(
                        (e.amountCents >= 0 ? '+' : '') + yuan(e.amountCents),
                        style: TextStyle(
                            color: e.amountCents >= 0
                                ? AppColors.success
                                : AppColors.danger,
                            fontWeight: FontWeight.w700),
                      ),
                    ),
                  )),
          ],
        ),
      ),
    );
  }

  IconData _iconFor(String kind) => switch (kind) {
        'wechat' => Icons.wechat,
        'alipay' => Icons.account_balance_wallet,
        _ => Icons.credit_card,
      };

  Widget _balanceCard() {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
            colors: [AppColors.brand, AppColors.brandDark]),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('可提现余额',
              style: TextStyle(color: Colors.white70, fontSize: 13)),
          const SizedBox(height: 8),
          Text(yuan(_balance),
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 34,
                  fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(
              onPressed: _withdraw,
              style: OutlinedButton.styleFrom(
                foregroundColor: Colors.white,
                side: const BorderSide(color: Colors.white70),
                minimumSize: const Size.fromHeight(46),
              ),
              child: const Text('提现'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionHeader(String title, {Widget? action}) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(title,
            style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: AppColors.ink)),
        if (action != null) action,
      ],
    );
  }
}
