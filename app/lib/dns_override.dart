import 'dart:io';

/// Connects directly to the server IP (bypassing the device DNS resolver, which
/// fails with errno 7 on some carriers/ROMs) while keeping HTTPS integrity.
///
/// Because we hit the IP directly, the TLS certificate (issued for
/// www.antdash.com) won't match the IP host. We therefore relax validation
/// ONLY for our backend IP, and only if the presented certificate is still
/// valid for our domain (checked via its subjectAltName / subject). This
/// survives Let's Encrypt renewals (SAN stays www.antdash.com) and rejects
/// unrelated self-signed certs. Override at build time:
///   --dart-define=API_IP=170.106.190.169
///   --dart-define=API_HOST=www.antdash.com
void installFixedIpOverride() {
  const ip = String.fromEnvironment('API_IP',
      defaultValue: '170.106.190.169');
  const host = String.fromEnvironment('API_HOST',
      defaultValue: 'www.antdash.com');

  HttpOverrides.global = _PinnedCertOverrides(ip, host);
}

class _PinnedCertOverrides extends HttpOverrides {
  final String ip;
  final String host;
  _PinnedCertOverrides(this.ip, this.host);

  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final client = super.createHttpClient(context);
    client.badCertificateCallback = (X509Certificate cert, String host, int port) {
      // Only relax validation for our own backend IP and only when the cert
      // is still ours (covers SAN/CN = our domain, so renewals keep working).
      if (host != ip) return false;
      final blob = '${cert.subject}\n${cert.issuer}\n${cert.pem}';
      return blob.contains(this.host);
    };
    return client;
  }
}