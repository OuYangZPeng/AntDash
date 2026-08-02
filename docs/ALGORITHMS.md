# 核心算法说明

所有参数集中在 [`backend/app/config.py`](../backend/app/config.py),可运行时通过 `PATCH /admin/config` 调整。纯算法函数与数据库解耦,便于单元测试(见 `backend/tests/`)。

## 1. 撮合引擎 (Matching)

代码:[`backend/app/services/matching.py`](../backend/app/services/matching.py)

### 分组
- 订单按**小区 ID** (`community_id`) 分组。真实环境中由收货地址 geocode → geohash + 小区聚类得到;mock 环境使用固定小区集合。

### 动态时间窗 T
一个聚合单在 `open` 状态下等待同小区订单加入,直到 **T 分钟**到期或达到聚合上限 `N_max`:

```
T = clamp( T_base * (target_bundle_size / max(arrival_rate, ε)),  T_min,  T_max )
```

- `arrival_rate` = 最近 10 分钟订单到达速率(单/分钟)。
- 订单稀疏 → T 增大(多等,凑更多单降低单均成本)。
- 订单密集或时效紧张 → T 减小(尽快成团保证时效)。
- 默认:`T_base=10min`,`T_min=3min`,`T_max=25min`,`target=4`,`N_max=6`。

### 成团打分
候选分组打分(越高越优先成团):

```
score = w1·同小区 + w2·地理邻近 + w3·时效余量 + w4·聚合效率
```

- **同小区**:同一小区为 1,否则 0(权重最高 0.40)。
- **地理邻近**:`1 / (1 + 平均两两距离km)`。
- **时效余量**:对最紧订单剩余 SLA 分钟做 sigmoid(10 分钟为中点)。
- **聚合效率**:`min(size, N_max) / target`,越接近目标规模越高。

### 成团条件
`order_count ≥ N_max` **或** 当前时间 ≥ `window_deadline` 时,聚合单从 `open` → `ready`。

## 2. Anter 信誉 / 派单频率引擎 (Reputation)

代码:[`backend/app/services/reputation.py`](../backend/app/services/reputation.py)

**原则:奖励准时履约,惩罚甩单 / 超时 / 投诉。** 信誉分驱动派单优先级与频率。

### 信誉分 S ∈ [0,100],初始 60

| 事件 | Δ 分 |
|---|---|
| 准时送达 on_time | +3 |
| 提前送达 early | +1 |
| 超时 late | −5 |
| 接单后甩单 abandon | **−15** |
| 被投诉 complaint | −10 |

### 准时率 (EWMA)
```
on_time_rate = α · 本次结果 + (1-α) · 历史        (α = 0.3)
```
准时/提前记 1,超时/甩单记 0,投诉不直接影响准时率。

### 派单权重
```
dispatch_weight = base · sigmoid( (S - 50) / 10 )
```
接单大厅按权重降序排序;权重高者优先、更频繁获得聚合单。

### 冷却与恢复
- `S < 35` 进入**冷却期**(默认 15 分钟),期间不参与派单。
- 空闲且守约时,信誉分以 `0.05 分/分钟`向初始值 60 **缓慢回升**(不超过初始值)。

## 3. 动态定价引擎 (Pricing)

代码:[`backend/app/services/pricing.py`](../backend/app/services/pricing.py)

对标美团派单定价:**确定性基础包(effort)+ 规模因子 + 波动系数(时段/天气/供需)**,再受上下限保护。C 端不可见价格,骑手承担确定性成本,平台用补贴池承担波动溢价。

### 3.1 基础包(单均,确定性)
```
pkg_i = 起步价 + 距离费(门口→门,来自 MapAdapter) + 楼层费(无电梯每层) + 重量/大件费 + 时效紧张费 + 品类费(生鲜/易碎)
P_base = round( Σ pkg_i × (1 − aggregation_discount_ratio) )      (仅 N≥2;固定折扣,默认 5%)
```
- 成团价与子单数**非线性**:聚合单价固定比各子单基础包之和便宜 5%;省下的 5%(`Σpkg − P_base`)投入当天**应急奖金池**(`EmergencyPoolEntry`,用于救援奖金等紧急激励)。单个订单(N=1)不打折。
- 撮合侧约束:一个聚合单仅同/相邻楼栋、最多 5 单(见第 1 节)。

### 3.2 波动系数与最终价
```
M_full = M_time(时段) × M_weather(天气) × M_surge(小区供需)
P = clamp( round(P_base × M_full),  下限,  上限 )
下限 = round(total_income × price_floor_pct_of_income%)   # 保底,默认对齐 X=20%
上限 = price_cap_per_order_cents × N                       # 单均封顶,防 surge 失控
```

- **时段** `M_time`:午高峰 11–13、晚高峰 17–20 → `price_peak_multiplier`(默认 1.2);深夜 22–06 → `price_latenight_multiplier`(1.15);按 CN 本地时 (UTC+8)。
- **天气** `M_weather`:由 `WeatherAdapter` 给出 `clear/rain/heavy_rain/snow/extreme`,查表(小雨 1.15 … 暴雪 1.5)。
- **供需 surge** `M_surge = clamp(1 + k·(demand/supply − 1), 1, surge_max)`,详见 3.4。

### 3.3 出资拆账(谁付这笔钱)
```
骑手扣款  rider_charge = min( P_base × M_time^rider,  P )   # 确定性 + 封顶高峰(price_rider_peak_cap≤1.1)
平台补贴  subsidy      = P − rider_charge                    # 平台承担 surge×天气 波动溢价
平台维护费 platform_fee = round(P × Y%)
Anter 实收 anter_net    = P − platform_fee
平台净     = platform_fee − subsidy                          # 平峰为正(赚维护费),高峰为负(补贴换运力)
```

- `rider_bears_surge / rider_bears_weather`(默认 `false`):控制是否把 surge/天气也转嫁给骑手。
- **可见性**:骑手看 `rider_charge`(本单扣款);Anter 看 `anter_net` + 完整构成;C 端无价格接口。
- 骑手扣款按各订单基础包占比分摊到每单(`rider_charge_cents`),不丢分。

### 3.4 按小区的供需 surge(分层回退)
```
demand_c = 该小区 ready+at_gate 待接聚合单数
supply_c = 服务该小区、非冷却的可用 Anter 数(User.service_community_ids 为空=服务所有小区)
若 demand_c + supply_c < surge_min_samples:  回退到全局 demand/supply(样本太小防抖动)
```

### 3.5 快照冻结与审计
- 成团(`open→ready`)时由 `run_matching` 调 `compute_bundle_quote` 计算并**快照冻结**到 `Bundle`(`quoted_price_cents/rider_charge_cents/subsidy_cents/各系数/pricing_breakdown`)与只读表 `PriceQuote`;`accept` 后价格锁定,保证 Anter 看到即拿到。
- 总开关 `pricing_enabled`;关闭时回退到旧的 `total × X%` 静态分账。
- 干跑预览:`GET /admin/price-preview`。

## 4. 分账引擎 (Ledger)

代码:[`backend/app/services/ledger.py`](../backend/app/services/ledger.py)

动态定价下,跑腿费即冻结的聚合单价 `P`,分账仍按 Y% 抽取:
```
errand_fee   = P (= quoted_price_cents)      # 跑腿费总额
platform_fee = round(errand_fee × Y%)        # 平台维护费
anter_net    = errand_fee − platform_fee     # Anter 实收
```

- 全部以**分 (cents)** 为单位,`round()` 取整,保证 `platform_fee + anter_net == errand_fee`(不丢分)。
- 结算 (`deliver_bundle`) 生成**只读账本** `LedgerEntry`:`errand_fee_debit`(按各订单 `rider_charge` 从骑手账户扣)+ `platform_subsidy`(平台补贴)+ `platform_fee` + `anter_credit`。资金守恒:`Σrider_charge + subsidy = P = platform_fee + anter_net`。
- 关闭动态定价时回退:`errand_fee = round(total_income × X%)`,跑腿费按各订单收入占比从骑手扣除(见 `split_from_errand_fee` / `compute_split`)。

### 静态回退示例(与原规格一致)
4 单共 40 元 (`total=4000` 分),X=20%,Y=10%:
- errand_fee = 4000 × 20% = **800 分 (8 元)**
- platform_fee = 800 × 10% = **80 分 (0.8 元)**
- anter_net = 800 − 80 = **720 分 (7.2 元)**

## 5. 实时通知与 IP 定位 (Realtime / Geo)

代码:[`notifications.py`](../backend/app/services/notifications.py)、[`api/ws.py`](../backend/app/api/ws.py)、[`adapters/geo_mock.py`](../backend/app/adapters/geo_mock.py)

### IP 定位(不可篡改)
- `GET /geo/locate`:由**服务端**从请求 IP(`X-Forwarded-For` → `X-Real-IP` → `client.host`)经 `GeoAdapter` 解析出城市 + 经纬度,写入 `User.city/lat/lng`,返回 `editable:false`。客户端无法篡改。
- mock 对回环/内网 IP 回退到默认城市(`上海市`,近演示小区),真实环境替换为高德/百度 IP 定位。

### 1km 新单推送
- Anter 通过 `ws://…/ws/notifications?token=…` 建立 WebSocket;服务端按其 IP 定位坐标登记连接。
- 每当 `run_matching` 成团(`/orders/ingest` `/orders/simulate` `/orders/match`),对每个新聚合单计算小区质心,`NotificationHub.publish_new_bundle` 用 haversine 只推给 **`notify_radius_km`(默认 1km)内**的在线 Anter → App 弹窗提示。
- Hub 通过 `loop.call_soon_threadsafe` 从同步端点安全地投递到事件循环上的各连接队列。

### 即将超时
- App 大厅按最近订单 SLA 升序排列,`≤5 分钟`的聚合单标红「即将超时」并显示**逐秒倒计时**;详情页每一单显示各自的超时倒计时(时间戳按 UTC 解析,避免时区错位)。

## 6. 临期升级与骑手救援 (Escalation / Rescue)

代码:[`services/escalation.py`](../backend/app/services/escalation.py)

后台每 `escalation_sweep_seconds`(默认 20s)巡检**未接单**(`at_gate`)聚合单,以最紧子单剩余 SLA 驱动分级升级:

| 阶段 | 剩余 SLA | 动作 |
|---|---|---|
| 0 | > `urgency_start`(20min) | 正常 |
| 1 | ≤20min | 加急费开始累积,大厅置顶,1km 推送 |
| 2 | ≤ `rescue_threshold`(15min) | **触发骑手救援**:向 1km 内**外卖骑手 + Anter** 推送;加急费↑ |
| 3 | ≤6min | 加急费封顶,推送半径扩至 `escalation_radius_max_km` |
| 4 | 已超时 | 兜底;不因无人接惩罚 Anter |

### 加急费(平台出资,不加骑手)
```
urgency_fee = round(base_price × urgency_fee_max_ratio × frac),  frac = (start − remaining)/start ∈[0,1]
```
- 只对未接单加急,`accept` 时冻结;结算时 `errand_fee = quoted_price + urgency_fee`,加急部分并入 `platform_subsidy`(平台补贴池)。

### 骑手即 Anter + 救援奖励
- **外卖骑手可直接当 Anter**:以 `rider` 角色登录、实名后即可在接单大厅接单/逐单拍照/送达(与 Anter 同流程)。
- 救援(送达曾进入 `<15min` 的聚合单)额外获得:
  - **救援奖金** `rider_rescue_bonus_cents`(奖金池,记 `rescue_bonus` 账目);
  - **信誉加成** `rescue_reputation_bonus` → 抬高 `dispatch_weight` → **优先派单**;
  - `User.rescue_count` 计数。
- 推送经 `NotificationHub` 按角色 + 半径过滤;救援事件 `type=rescue` 触发 App 强弹窗(含加急费/剩余分钟)。

### 骑手视图 + 提前到门口奖励
- `GET /orders/mine`:骑手看到自己的第一段订单**按所属聚合单分组**(社区/聚合单状态/门口超时倒计时)。
- 骑手拍照确认「送达小区门口」:`POST /proof/orders/{id}/gate` → `rider_gate_dropoff` 计算**提前折扣**并入账:
```
折扣 = round(rider_charge × early_gate_discount_ratio_max × min(送达时剩余SLA / slack_ref, 1))
```
  越早到门口(剩余 SLA 越多)折扣越大,直接**减免骑手跑腿费**;减免额由平台补贴吸收(`bundle.subsidy_cents += 折扣`,Anter 收入不变),从而**把"提前到门口的时间"纳入骑手费用动态计算**,并为聚合派送留出更多时间。
- 一个聚合单的所有订单都完成门口送达后自动进入 `at_gate`(可接)。
