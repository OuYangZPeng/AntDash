import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'api/api_client.dart';
import 'state/app_state.dart';
import 'theme.dart';
import 'screens/login_screen.dart';
import 'screens/real_name_screen.dart';
import 'screens/home_shell.dart';

void main() {
  runApp(const AntDashApp());
}

class AntDashApp extends StatelessWidget {
  const AntDashApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider(
      create: (_) => AppState(ApiClient()),
      child: MaterialApp(
        title: '蚂蚁闪达',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        home: const RootRouter(),
      ),
    );
  }
}

class RootRouter extends StatelessWidget {
  const RootRouter({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppState>();
    if (!state.isLoggedIn) return const LoginScreen();
    if (!state.isVerified) return const RealNameScreen();
    return const HomeShell();
  }
}
