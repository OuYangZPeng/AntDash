/// Backend emits naive UTC ISO timestamps (no offset). Mark them as UTC so
/// countdowns against DateTime.now() are correct regardless of device timezone.
DateTime parseServerTime(String s) {
  final hasTz = s.endsWith('Z') || RegExp(r'[+-]\d\d:?\d\d$').hasMatch(s);
  return DateTime.parse(hasTz ? s : '${s}Z');
}

class UserProfile {
  final String id;
  final String role;
  final String? phone;
  final String? name;
  final bool verified;
  final double reputationScore;
  final double onTimeRate;
  final int balanceCents;
  final int rescueCount;

  UserProfile({
    required this.id,
    required this.role,
    this.phone,
    this.name,
    required this.verified,
    required this.reputationScore,
    required this.onTimeRate,
    required this.balanceCents,
    this.rescueCount = 0,
  });

  factory UserProfile.fromJson(Map<String, dynamic> j) => UserProfile(
        id: j['id'] as String,
        role: j['role'] as String,
        phone: j['phone'] as String?,
        name: j['name'] as String?,
        verified: j['verified'] as bool,
        reputationScore: (j['reputation_score'] as num).toDouble(),
        onTimeRate: (j['on_time_rate'] as num).toDouble(),
        balanceCents: j['balance_cents'] as int,
        rescueCount: (j['rescue_count'] as int?) ?? 0,
      );
}

class OrderItem {
  final String id;
  final String platform;
  final String externalId;
  final String communityName;
  final String address;
  final int riderIncomeCents;
  final String status;
  final DateTime slaDeadline;
  final int floor;
  final bool hasElevator;
  final String category;
  final bool proofUploaded;
  final DateTime? gateDropoffAt;
  final int gateDiscountCents;
  final int? riderChargeCents; // 本单骑手扣款(仅骑手视角返回)

  OrderItem({
    required this.id,
    required this.platform,
    required this.externalId,
    required this.communityName,
    required this.address,
    required this.riderIncomeCents,
    required this.status,
    required this.slaDeadline,
    this.floor = 1,
    this.hasElevator = true,
    this.category = 'normal',
    this.proofUploaded = false,
    this.gateDropoffAt,
    this.gateDiscountCents = 0,
    this.riderChargeCents,
  });

  factory OrderItem.fromJson(Map<String, dynamic> j) => OrderItem(
        id: j['id'] as String,
        platform: j['platform'] as String,
        externalId: j['external_id'] as String,
        communityName: j['community_name'] as String,
        address: j['address'] as String,
        riderIncomeCents: j['rider_income_cents'] as int,
        status: j['status'] as String,
        slaDeadline: parseServerTime(j['sla_deadline'] as String),
        floor: (j['floor'] as int?) ?? 1,
        hasElevator: (j['has_elevator'] as bool?) ?? true,
        category: (j['category'] as String?) ?? 'normal',
        proofUploaded: (j['proof_uploaded'] as bool?) ?? false,
        gateDropoffAt: j['gate_dropoff_at'] == null
            ? null
            : parseServerTime(j['gate_dropoff_at'] as String),
        gateDiscountCents: (j['gate_discount_cents'] as int?) ?? 0,
        riderChargeCents: j['rider_charge_cents'] as int?,
      );

  bool get droppedAtGate => gateDropoffAt != null;

  String get platformLabel => switch (platform) {
        'meituan' => '美团',
        'shangou' => '闪购',
        'jd' => '京东',
        _ => platform,
      };

  String? get categoryLabel => switch (category) {
        'fresh' => '生鲜',
        'fragile' => '易碎',
        _ => null,
      };

  String? get floorLabel {
    if (floor <= 1) return null;
    return hasElevator ? '$floor楼·有梯' : '$floor楼·无梯';
  }
}

class Bundle {
  final String id;
  final String communityName;
  final String status;
  final String? anterId;
  final int orderCount;
  final int totalIncomeCents;
  final int errandFeeCents;
  final int platformFeeCents;
  final int anterNetCents;
  final double xRate;
  final double yRate;
  final DateTime windowDeadline;
  final DateTime? deliveryDeadline;
  final List<OrderItem> orders;
  // --- dynamic pricing (nullable: absent for rider view / legacy) ---
  final int? basePriceCents;
  final int? quotedPriceCents;
  final int? riderChargeCents;
  final int? subsidyCents;
  final double? surgeMultiplier;
  final double? timeMultiplier;
  final double? weatherMultiplier;
  final String? weatherCondition;
  final int urgencyFeeCents;
  final int escalationStage;
  final bool rescue;

  Bundle({
    required this.id,
    required this.communityName,
    required this.status,
    this.anterId,
    required this.orderCount,
    required this.totalIncomeCents,
    required this.errandFeeCents,
    required this.platformFeeCents,
    required this.anterNetCents,
    required this.xRate,
    required this.yRate,
    required this.windowDeadline,
    this.deliveryDeadline,
    required this.orders,
    this.basePriceCents,
    this.quotedPriceCents,
    this.riderChargeCents,
    this.subsidyCents,
    this.surgeMultiplier,
    this.timeMultiplier,
    this.weatherMultiplier,
    this.weatherCondition,
    this.urgencyFeeCents = 0,
    this.escalationStage = 0,
    this.rescue = false,
  });

  factory Bundle.fromJson(Map<String, dynamic> j) => Bundle(
        id: j['id'] as String,
        communityName: j['community_name'] as String,
        status: j['status'] as String,
        anterId: j['anter_id'] as String?,
        orderCount: j['order_count'] as int,
        totalIncomeCents: j['total_income_cents'] as int,
        errandFeeCents: j['errand_fee_cents'] as int,
        platformFeeCents: j['platform_fee_cents'] as int,
        anterNetCents: j['anter_net_cents'] as int,
        xRate: (j['x_rate'] as num).toDouble(),
        yRate: (j['y_rate'] as num).toDouble(),
        windowDeadline: parseServerTime(j['window_deadline'] as String),
        deliveryDeadline: j['delivery_deadline'] == null
            ? null
            : parseServerTime(j['delivery_deadline'] as String),
        orders: ((j['orders'] as List?) ?? [])
            .map((e) => OrderItem.fromJson(e as Map<String, dynamic>))
            .toList(),
        basePriceCents: j['base_price_cents'] as int?,
        quotedPriceCents: j['quoted_price_cents'] as int?,
        riderChargeCents: j['rider_charge_cents'] as int?,
        subsidyCents: j['subsidy_cents'] as int?,
        surgeMultiplier: (j['surge_multiplier'] as num?)?.toDouble(),
        timeMultiplier: (j['time_multiplier'] as num?)?.toDouble(),
        weatherMultiplier: (j['weather_multiplier'] as num?)?.toDouble(),
        weatherCondition: j['weather_condition'] as String?,
        urgencyFeeCents: (j['urgency_fee_cents'] as int?) ?? 0,
        escalationStage: (j['escalation_stage'] as int?) ?? 0,
        rescue: (j['rescue'] as bool?) ?? false,
      );

  bool get hasUrgencyFee => urgencyFeeCents > 0;

  /// Whether a frozen dynamic-pricing snapshot is available (Anter/admin view).
  bool get hasDynamicPrice =>
      quotedPriceCents != null && quotedPriceCents! > 0;

  /// Earliest SLA deadline across the bundle's orders (the one that times out first).
  DateTime? get soonestSla {
    if (orders.isEmpty) return null;
    return orders
        .map((o) => o.slaDeadline)
        .reduce((a, b) => a.isBefore(b) ? a : b);
  }

  /// True when the soonest order is within [threshold] of timing out.
  bool isExpiringSoon({Duration threshold = const Duration(minutes: 5)}) {
    final s = soonestSla;
    if (s == null) return false;
    final left = s.difference(DateTime.now());
    return !left.isNegative && left <= threshold;
  }

  /// Anter net income = total * X% * (1 - Y%). Kept for display fallback.
  int get estimatedAnterNet =>
      (totalIncomeCents * xRate / 100 * (1 - yRate / 100)).round();

  String? get weatherLabel => switch (weatherCondition) {
        'rain' => '雨',
        'heavy_rain' => '大雨',
        'snow' => '雪',
        'extreme' => '极端天气',
        _ => null, // 'clear' or null -> no badge
      };

  /// Short multiplier tags like ['高峰×1.2', '雨×1.15', '运力×1.3'] for chips.
  List<String> get priceTags {
    final tags = <String>[];
    if ((timeMultiplier ?? 1) > 1.001) {
      tags.add('高峰×${timeMultiplier!.toStringAsFixed(2)}');
    }
    if ((weatherMultiplier ?? 1) > 1.001 && weatherLabel != null) {
      tags.add('${weatherLabel!}×${weatherMultiplier!.toStringAsFixed(2)}');
    }
    if ((surgeMultiplier ?? 1) > 1.001) {
      tags.add('运力×${surgeMultiplier!.toStringAsFixed(2)}');
    }
    return tags;
  }

  String get statusLabel => switch (status) {
        'open' => '撮合中',
        'ready' => '待到门口',
        'at_gate' => '可接单',
        'accepted' => '配送中',
        'delivered' => '已送达',
        'settled' => '已结算',
        'expired' => '已过期',
        _ => status,
      };
}

class PaymentMethod {
  final String id;
  final String kind;
  final String display;
  final bool isDefault;

  PaymentMethod({
    required this.id,
    required this.kind,
    required this.display,
    required this.isDefault,
  });

  factory PaymentMethod.fromJson(Map<String, dynamic> j) => PaymentMethod(
        id: j['id'] as String,
        kind: j['kind'] as String,
        display: j['display'] as String,
        isDefault: j['is_default'] as bool,
      );

  String get kindLabel => switch (kind) {
        'wechat' => '微信',
        'alipay' => '支付宝',
        'bank_card' => '银行卡',
        _ => kind,
      };
}

class LedgerRow {
  final String type;
  final int amountCents;
  final String memo;
  final DateTime createdAt;

  LedgerRow({
    required this.type,
    required this.amountCents,
    required this.memo,
    required this.createdAt,
  });

  factory LedgerRow.fromJson(Map<String, dynamic> j) => LedgerRow(
        type: j['type'] as String,
        amountCents: j['amount_cents'] as int,
        memo: (j['memo'] ?? '') as String,
        createdAt: DateTime.parse(j['created_at'] as String),
      );

  String get typeLabel => switch (type) {
        'anter_credit' => '跑腿收入',
        'errand_fee_debit' => '跑腿费扣款',
        'platform_fee' => '平台服务费',
        'platform_subsidy' => '平台补贴',
        _ => type,
      };
}

/// A rider's first-leg orders grouped by the aggregate bundle they joined.
class RiderDelivery {
  final String? bundleId;
  final String communityName;
  final String bundleStatus;
  final int orderCount;
  final DateTime? gateDeadline;
  final List<OrderItem> orders;

  RiderDelivery({
    required this.bundleId,
    required this.communityName,
    required this.bundleStatus,
    required this.orderCount,
    required this.gateDeadline,
    required this.orders,
  });

  factory RiderDelivery.fromJson(Map<String, dynamic> j) => RiderDelivery(
        bundleId: j['bundle_id'] as String?,
        communityName: j['community_name'] as String,
        bundleStatus: (j['bundle_status'] ?? 'open') as String,
        orderCount: (j['order_count'] as int?) ?? 0,
        gateDeadline: j['gate_deadline'] == null
            ? null
            : parseServerTime(j['gate_deadline'] as String),
        orders: ((j['my_orders'] as List?) ?? [])
            .map((e) => OrderItem.fromJson(Map<String, dynamic>.from(e)))
            .toList(),
      );

  bool get allDropped => orders.every((o) => o.droppedAtGate);
  int get gateDiscountTotal =>
      orders.fold(0, (s, o) => s + o.gateDiscountCents);

  String get bundleStatusLabel => switch (bundleStatus) {
        'open' => '撮合中',
        'ready' => '待到门口',
        'at_gate' => '已到门口·待接',
        'accepted' => '配送中',
        'delivered' => '已送达',
        'settled' => '已结算',
        _ => bundleStatus,
      };
}

String yuan(int cents) => '¥${(cents / 100).toStringAsFixed(2)}';
