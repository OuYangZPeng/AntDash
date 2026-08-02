import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:antdash/config.dart';
import 'models.dart';

class ApiException implements Exception {
  final int status;
  final String message;
  ApiException(this.status, this.message);
  @override
  String toString() => 'ApiException($status): $message';
}

class ApiClient {
  /// Backend endpoint. Defaults to [AppConfig.baseUrl].
  /// Use 10.0.2.2 for the Android emulator, 127.0.0.1 elsewhere.
  String baseUrl;
  String? _token;

  ApiClient({this.baseUrl = AppConfig.baseUrl});

  /// HTTP client with an explicit connection timeout so DNS / network failures
  /// surface as a clear message instead of a low-level errno.
  final http.Client _client = http.Client();

  void setToken(String? token) => _token = token;
  bool get authenticated => _token != null;
  String? get token => _token;

  /// ws(s):// URL for the real-time notification socket (carries the token).
  Uri notificationsUri() {
    final ws = baseUrl.replaceFirst('http', 'ws');
    return Uri.parse('$ws/ws/notifications?token=${_token ?? ''}');
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  dynamic _decode(http.Response r) {
    if (r.statusCode >= 200 && r.statusCode < 300) {
      if (r.body.isEmpty) return null;
      return jsonDecode(utf8.decode(r.bodyBytes));
    }
    String detail = r.body;
    try {
      final j = jsonDecode(utf8.decode(r.bodyBytes));
      detail = (j['detail'] ?? r.body).toString();
    } catch (_) {}
    throw ApiException(r.statusCode, detail);
  }

  Future<dynamic> _get(String path) async {
    final resp = await _client
        .get(_uri(path), headers: _headers)
        .timeout(const Duration(seconds: 10),
            onTimeout: () => throw ApiException(
                0, '连接超时：无法访问 $baseUrl，请检查网络/DNS'));
    return _decode(resp);
  }

  Future<dynamic> _post(String path, [Map<String, dynamic>? body]) async {
    final resp = await _client
        .post(_uri(path),
            headers: _headers, body: body == null ? null : jsonEncode(body))
        .timeout(const Duration(seconds: 10),
            onTimeout: () => throw ApiException(
                0, '连接超时：无法访问 $baseUrl，请检查网络/DNS'));
    return _decode(resp);
  }

  // --- auth ---
  Future<Map<String, dynamic>> loginPhone(String phone, String otp,
      {String role = 'anter'}) async {
    final j = await _post('/auth/login/phone',
        {'phone': phone, 'otp': otp, 'role': role});
    return Map<String, dynamic>.from(j);
  }

  Future<Map<String, dynamic>> loginOAuth(String provider, String code,
      {String role = 'anter'}) async {
    final j = await _post('/auth/login/$provider', {'code': code, 'role': role});
    return Map<String, dynamic>.from(j);
  }

  Future<UserProfile> realName(String name, String idCard) async {
    final j = await _post('/auth/real-name', {'name': name, 'id_card': idCard});
    return UserProfile.fromJson(Map<String, dynamic>.from(j));
  }

  Future<UserProfile> me() async =>
      UserProfile.fromJson(Map<String, dynamic>.from(await _get('/auth/me')));

  // --- geo (IP-derived, non-tamperable) ---
  Future<Map<String, dynamic>> locate() async =>
      Map<String, dynamic>.from(await _get('/geo/locate'));

  // --- orders / bundles ---
  Future<Map<String, dynamic>> ingest({int limit = 10}) async =>
      Map<String, dynamic>.from(await _post('/orders/ingest?limit=$limit'));

  Future<List<Bundle>> bundles({String? status}) async {
    final path = status == null ? '/bundles' : '/bundles?status=$status';
    final list = await _get(path) as List;
    return list
        .map((e) => Bundle.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  /// Test helper: generate delivery orders for the current rider, matched &
  /// pushed to the hall. Returns {generated, bundles_ready, ...}.
  Future<Map<String, dynamic>> generateForMe({int count = 6, int communities = 1}) async =>
      Map<String, dynamic>.from(await _post(
          '/orders/generate-for-me?count=$count&communities=$communities'));

  /// Rider's first-leg orders grouped by bundle.
  Future<List<RiderDelivery>> myDeliveries() async {
    final list = await _get('/orders/mine') as List;
    return list
        .map((e) => RiderDelivery.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  // --- dispatch ---
  Future<List<Bundle>> offers() async {
    final list = await _get('/dispatch/offers') as List;
    return list
        .map((e) => Bundle.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<Bundle> markAtGate(String bundleId) async => Bundle.fromJson(
      Map<String, dynamic>.from(await _post('/dispatch/bundles/$bundleId/at-gate')));

  Future<Bundle> accept(String bundleId) async => Bundle.fromJson(
      Map<String, dynamic>.from(await _post('/dispatch/bundles/$bundleId/accept')));

  Future<Bundle> deliver(String bundleId) async => Bundle.fromJson(
      Map<String, dynamic>.from(await _post('/dispatch/bundles/$bundleId/deliver')));

  Future<Bundle> getBundle(String bundleId) async => Bundle.fromJson(
      Map<String, dynamic>.from(await _get('/bundles/$bundleId')));

  // --- proof (multipart) ---
  Future<void> uploadProof(String bundleId, String kind, List<int> bytes) async {
    final req = http.MultipartRequest(
        'POST', _uri('/proof/bundles/$bundleId/$kind'));
    if (_token != null) req.headers['Authorization'] = 'Bearer $_token';
    req.files.add(http.MultipartFile.fromBytes('file', bytes,
        filename: 'proof.jpg'));
    final resp = await http.Response.fromStream(await req.send())
        .timeout(const Duration(seconds: 20),
            onTimeout: () => throw ApiException(0, '上传超时'));
    _decode(resp);
  }

  /// Upload a delivery photo for a single sub-order. Returns {all_uploaded, remaining}.
  Future<Map<String, dynamic>> uploadOrderProof(
      String orderId, List<int> bytes) async {
    final req = http.MultipartRequest('POST', _uri('/proof/orders/$orderId/delivery'));
    if (_token != null) req.headers['Authorization'] = 'Bearer $_token';
    req.files.add(http.MultipartFile.fromBytes('file', bytes, filename: 'proof.jpg'));
    final resp = await http.Response.fromStream(await req.send());
    return Map<String, dynamic>.from(_decode(resp));
  }

  /// Rider confirms + photographs dropping an order at the community gate.
  /// Returns {discount_cents, all_dropped, ...}.
  Future<Map<String, dynamic>> uploadGateProof(
      String orderId, List<int> bytes) async {
    final req = http.MultipartRequest('POST', _uri('/proof/orders/$orderId/gate'));
    if (_token != null) req.headers['Authorization'] = 'Bearer $_token';
    req.files.add(http.MultipartFile.fromBytes('file', bytes, filename: 'gate.jpg'));
    final resp = await http.Response.fromStream(await req.send());
    return Map<String, dynamic>.from(_decode(resp));
  }

  // --- wallet ---
  Future<int> balance() async {
    final j = await _get('/wallet/balance');
    return j['balance_cents'] as int;
  }

  Future<List<LedgerRow>> ledger() async {
    final list = await _get('/wallet/ledger') as List;
    return list
        .map((e) => LedgerRow.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<PaymentMethod>> paymentMethods() async {
    final list = await _get('/wallet/methods') as List;
    return list
        .map((e) => PaymentMethod.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<PaymentMethod> bindPayment(
      String kind, String credential, String display) async {
    final j = await _post('/wallet/methods',
        {'kind': kind, 'credential': credential, 'display': display});
    return PaymentMethod.fromJson(Map<String, dynamic>.from(j));
  }

  Future<int> withdraw() async {
    final j = await _post('/wallet/withdraw');
    return j['withdrawn_cents'] as int;
  }
}
