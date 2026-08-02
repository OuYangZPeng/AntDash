# API 约定

基础地址:`http://127.0.0.1:8080`,交互式文档:`/docs`(Swagger UI)。
认证:除登录与订单接入外,均需 `Authorization: Bearer <token>` 头。金额单位统一为**分**。

## 认证 / 实名

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/login/phone` | 手机号登录 `{phone, otp, role}`,mock OTP 任意 ≥4 位 |
| POST | `/auth/login/wechat` | 微信登录 `{code, role}` |
| POST | `/auth/login/alipay` | 支付宝登录 `{code, role}` |
| POST | `/auth/real-name` | 实名认证 `{name, id_card}`(需登录) |
| GET | `/auth/me` | 当前用户信息(含信誉分、准时率、余额) |

登录返回:`{token, user_id, role, verified}`。`role` 可为 `anter` / `rider` / `admin`。

## 订单接入 / 撮合

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/orders/ingest?limit=N` | 从各平台适配器拉取订单并触发撮合 |
| POST | `/orders/match` | 手动触发撮合 |
| GET | `/bundles?status=` | 聚合单列表(可按状态过滤) |
| GET | `/bundles/{id}` | 单个聚合单详情(含订单明细) |

聚合单状态:`open` → `ready` → `at_gate` → `accepted` → `delivered` → `settled`。

## 派单 / 配送

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/dispatch/bundles/{id}/at-gate` | 骑手送到小区门口 |
| GET | `/dispatch/offers` | 可接聚合单(需实名) |
| POST | `/dispatch/bundles/{id}/accept` | Anter 接单(接单后必须履约) |
| POST | `/dispatch/bundles/{id}/deliver?complaint=false` | Anter 送达 → 结算 + 回写平台 + 信誉更新 |
| POST | `/dispatch/bundles/{id}/abandon` | 甩单(触发信誉惩罚) |

## 拍照凭证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/proof/bundles/{id}/gate` | 骑手门口拍照(multipart `file`) |
| POST | `/proof/bundles/{id}/delivery` | Anter 送达拍照(multipart `file`) |

## 钱包 / 支付

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/wallet/balance` | 余额 |
| GET | `/wallet/ledger` | 收支明细(只读账本) |
| GET | `/wallet/methods` | 已绑定支付方式 |
| POST | `/wallet/methods` | 绑定支付方式 `{kind, credential, display}`,kind ∈ wechat/alipay/bank_card |
| POST | `/wallet/withdraw` | 提现(沙箱) |

## 管理 / 配置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/config` | 查看 X / Y / 时间窗等参数 |
| PATCH | `/admin/config` | 运行时调整 `{errand_fee_pct_X, platform_fee_pct_Y, match_window_base_minutes, match_max_bundle_size}` |
| GET | `/admin/split-preview?total_income_cents=` | 分账试算 |
