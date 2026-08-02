import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../api/api_client.dart';
import '../api/models.dart';

class AppState extends ChangeNotifier {
  final ApiClient api;
  AppState(this.api);

  UserProfile? user;
  String? role;
  String? city; // IP-derived, non-tamperable
  bool get isLoggedIn => api.authenticated;
  bool get isVerified => user?.verified ?? false;

  // Real-time new-order notifications (bundles within 1km).
  final StreamController<Map<String, dynamic>> _notifications =
      StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get notifications => _notifications.stream;

  WebSocketChannel? _channel;
  StreamSubscription? _wsSub;

  Future<void> loginPhone(String phone, String otp, String role) async {
    final res = await api.loginPhone(phone, otp, role: role);
    _afterLogin(res);
  }

  Future<void> loginOAuth(String provider, String code, String role) async {
    final res = await api.loginOAuth(provider, code, role: role);
    _afterLogin(res);
  }

  void _afterLogin(Map<String, dynamic> res) {
    api.setToken(res['token'] as String);
    role = res['role'] as String;
    notifyListeners();
  }

  Future<void> refreshMe() async {
    user = await api.me();
    role = user?.role;
    notifyListeners();
  }

  Future<void> verifyRealName(String name, String idCard) async {
    user = await api.realName(name, idCard);
    notifyListeners();
  }

  /// Resolve the IP-based city (server-side, cannot be tampered with).
  Future<void> locateCity() async {
    try {
      final res = await api.locate();
      city = res['city'] as String?;
      notifyListeners();
    } catch (_) {
      // non-fatal; city stays null
    }
  }

  /// Connect the notification WebSocket (idempotent). Anters get nearby-order
  /// pushes; reconnects once on drop.
  void connectNotifications() {
    if (_channel != null || !api.authenticated) return;
    try {
      final channel = WebSocketChannel.connect(api.notificationsUri());
      _channel = channel;
      _wsSub = channel.stream.listen(
        (data) {
          try {
            final event = jsonDecode(data as String) as Map<String, dynamic>;
            const kinds = {'new_bundle', 'urgent', 'rescue'};
            if (kinds.contains(event['type'])) {
              _notifications.add(event);
            }
          } catch (_) {}
        },
        onDone: _onWsClosed,
        onError: (_) => _onWsClosed(),
        cancelOnError: true,
      );
    } catch (_) {
      _channel = null;
    }
  }

  void _onWsClosed() {
    _wsSub?.cancel();
    _wsSub = null;
    _channel = null;
  }

  void _disconnectNotifications() {
    _wsSub?.cancel();
    _wsSub = null;
    _channel?.sink.close();
    _channel = null;
  }

  void logout() {
    _disconnectNotifications();
    api.setToken(null);
    user = null;
    role = null;
    city = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _disconnectNotifications();
    _notifications.close();
    super.dispose();
  }
}
