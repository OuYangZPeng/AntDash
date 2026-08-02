import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/app_state.dart';
import '../theme.dart';

class RealNameScreen extends StatefulWidget {
  const RealNameScreen({super.key});

  @override
  State<RealNameScreen> createState() => _RealNameScreenState();
}

class _RealNameScreenState extends State<RealNameScreen> {
  final _name = TextEditingController();
  final _idCard = TextEditingController();
  bool _busy = false;
  String? _error;

  Future<void> _submit() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await context.read<AppState>().verifyRealName(_name.text, _idCard.text);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('实名认证'),
        actions: [
          TextButton(
            onPressed: () => context.read<AppState>().logout(),
            child: const Text('退出'),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24),
        child: ListView(
          children: [
            const SizedBox(height: 16),
            const Text('为保障配送安全,接单前需完成实名认证',
                style: TextStyle(color: AppColors.subtle)),
            const SizedBox(height: 24),
            TextField(
              controller: _name,
              decoration: const InputDecoration(
                labelText: '真实姓名',
                prefixIcon: Icon(Icons.badge_outlined),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _idCard,
              decoration: const InputDecoration(
                labelText: '身份证号',
                prefixIcon: Icon(Icons.credit_card),
                helperText: '演示环境:输入 18 位合法格式即可',
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: AppColors.danger)),
            ],
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: _busy ? null : _submit,
              child: _busy
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white))
                  : const Text('提交认证'),
            ),
          ],
        ),
      ),
    );
  }
}
