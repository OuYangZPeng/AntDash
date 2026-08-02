import 'package:flutter_test/flutter_test.dart';
import 'package:antdash/api/models.dart';

void main() {
  test('Bundle parses and computes anter net fallback', () {
    final b = Bundle.fromJson({
      'id': 'b1',
      'community_name': '万科城市花园',
      'status': 'at_gate',
      'order_count': 4,
      'total_income_cents': 4000,
      'errand_fee_cents': 0,
      'platform_fee_cents': 0,
      'anter_net_cents': 0,
      'x_rate': 20.0,
      'y_rate': 10.0,
      'window_deadline': '2026-07-15T00:00:00',
      'delivery_deadline': null,
      'orders': [],
    });
    // 4000 * 20% * (1 - 10%) = 720
    expect(b.estimatedAnterNet, 720);
    expect(b.statusLabel, '可接单');
  });

  test('yuan formats cents', () {
    expect(yuan(4000), '¥40.00');
    expect(yuan(721), '¥7.21');
  });
}
