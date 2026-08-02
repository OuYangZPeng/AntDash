/// Centralized app configuration.
///
/// Switch [baseUrl] per environment. The value is used by [ApiClient] as the
/// default backend endpoint.
class AppConfig {
  /// Base URL of the AntDash backend API.
  ///
  /// Defaults to the server IP (with HTTPS) to bypass the device DNS resolver,
  /// which fails with errno 7 on some carriers/ROMs even though the domain
  /// resolves in the browser. The certificate is pinned in dns_override.dart,
  /// so HTTPS integrity is preserved. Override at build time:
  ///   flutter build apk --release --dart-define=BASE_URL=https://www.antdash.com
  ///
  /// Environments:
  /// - Local (physical device / iOS simulator):  http://127.0.0.1:8080
  /// - Android emulator:                          http://10.0.2.2:8080
  /// - Production (Tencent Cloud, IP, cert-pinned): https://170.106.190.169
  static const String baseUrl = String.fromEnvironment(
    'BASE_URL',
    defaultValue: 'https://170.106.190.169',
  );
}
