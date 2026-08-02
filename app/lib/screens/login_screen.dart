import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../theme.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _phone = TextEditingController(text: '13800000001');
  final _otp = TextEditingController(text: '1234');
  String _role = 'anter';
  bool _busy = false;
  String? _error;

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      if (mounted) await context.read<AppState>().refreshMe();
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = context.read<AppState>();
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: ListView(
            children: [
              const SizedBox(height: 56),
              Center(
                child: Container(
                  width: 72,
                  height: 72,
                  decoration: BoxDecoration(
                    color: AppColors.brand,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Icon(Icons.bolt, color: Colors.white, size: 40),
                ),
              ),
              const SizedBox(height: 16),
              const Center(
                child: Text('蚂蚁闪达',
                    style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.bold,
                        color: AppColors.ink)),
              ),
              const SizedBox(height: 4),
              const Center(
                child: Text('聚合外卖 · 末端闪达',
                    style: TextStyle(color: AppColors.subtle)),
              ),
              const SizedBox(height: 40),
              _RoleSelector(
                role: _role,
                onChanged: (r) => setState(() => _role = r),
              ),
              const SizedBox(height: 20),
              TextField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: '手机号',
                  prefixIcon: Icon(Icons.phone_iphone),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _otp,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: '验证码',
                  prefixIcon: Icon(Icons.password),
                  helperText: '演示环境:任意 4 位以上验证码',
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!, style: const TextStyle(color: AppColors.danger)),
              ],
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: _busy
                    ? null
                    : () => _run(() =>
                        state.loginPhone(_phone.text, _otp.text, _role)),
                child: _busy
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Text('手机号登录'),
              ),
              const SizedBox(height: 24),
              Row(children: const [
                Expanded(child: Divider()),
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: 12),
                  child: Text('第三方登录',
                      style: TextStyle(color: AppColors.subtle)),
                ),
                Expanded(child: Divider()),
              ]),
              const SizedBox(height: 20),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _OAuthButton(
                    icon: Icons.wechat,
                    color: const Color(0xFF07C160),
                    label: '微信',
                    onTap: _busy
                        ? null
                        : () => _run(() => state.loginOAuth(
                            'wechat', 'demo-wx-code', _role)),
                  ),
                  const SizedBox(width: 32),
                  _OAuthButton(
                    icon: Icons.account_balance_wallet,
                    color: const Color(0xFF1677FF),
                    label: '支付宝',
                    onTap: _busy
                        ? null
                        : () => _run(() => state.loginOAuth(
                            'alipay', 'demo-ali-code', _role)),
                  ),
                ],
              ),
              const SizedBox(height: 24),
              const Center(
                child: Text('登录即代表同意《用户协议》与《隐私政策》',
                    style: TextStyle(color: AppColors.subtle, fontSize: 12)),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _RoleSelector extends StatelessWidget {
  final String role;
  final ValueChanged<String> onChanged;
  const _RoleSelector({required this.role, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    Widget chip(String value, String label, IconData icon) {
      final selected = role == value;
      return Expanded(
        child: GestureDetector(
          onTap: () => onChanged(value),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            padding: const EdgeInsets.symmetric(vertical: 14),
            decoration: BoxDecoration(
              color: selected ? AppColors.brand.withOpacity(0.12) : Colors.white,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                  color: selected ? AppColors.brand : const Color(0xFFE6E8EC),
                  width: selected ? 1.5 : 1),
            ),
            child: Column(
              children: [
                Icon(icon,
                    color: selected ? AppColors.brand : AppColors.subtle),
                const SizedBox(height: 6),
                Text(label,
                    style: TextStyle(
                        color: selected ? AppColors.brand : AppColors.subtle,
                        fontWeight: FontWeight.w600)),
              ],
            ),
          ),
        ),
      );
    }

    return Row(children: [
      chip('anter', 'Anter 跑腿员', Icons.directions_run),
      const SizedBox(width: 12),
      chip('rider', '外卖骑手', Icons.delivery_dining),
    ]);
  }
}

class _OAuthButton extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String label;
  final VoidCallback? onTap;
  const _OAuthButton(
      {required this.icon,
      required this.color,
      required this.label,
      this.onTap});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(28),
          child: Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: const Color(0xFFE6E8EC)),
            ),
            child: Icon(icon, color: color, size: 30),
          ),
        ),
        const SizedBox(height: 8),
        Text(label, style: const TextStyle(color: AppColors.subtle)),
      ],
    );
  }
}
