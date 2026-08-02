# 接入真实平台 / 支付 / 实名 指引

MVP 通过**适配器模式**隔离所有外部依赖。要对接真实系统,只需为对应抽象接口提供新实现,并在装配处替换 mock,**核心业务逻辑(撮合/信誉/分账)完全不动**。

抽象接口定义:[`backend/app/adapters/base.py`](../backend/app/adapters/base.py)。

## 1. 外卖平台(美团 / 闪购 / 京东)

> 说明:美团、京东等的配送订单接口**不对公众开放**,需企业资质并与平台签订合作/商户协议后申请开放平台权限。

实现 `PlatformAdapter`:

```python
class MeituanPlatformAdapter(PlatformAdapter):
    name = "meituan"
    def fetch_orders(self, limit=20) -> list[ExternalOrder]:
        # 调用美团开放平台订单接口,映射为 ExternalOrder
        ...
    def push_status(self, external_id, status, proof_url=None) -> bool:
        # 回写订单状态 / 上传送达凭证到平台后台
        ...
```

替换点:[`backend/app/adapters/platform_mock.py`](../backend/app/adapters/platform_mock.py) 的 `get_platform_adapters()`,把 `MockPlatformAdapter` 换成真实实现。

需要准备:
- 各平台开放平台的 **AppKey / AppSecret / 商户号**、OAuth 授权、回调/签名校验。
- 订单地址 → 小区聚类:接入 geocoding(高德/腾讯地图)得到经纬度与小区 POI。

## 2. 支付(微信 / 支付宝 / 银行卡)

实现 `PaymentAdapter`(`bind_method` / `charge` / `payout`):

- **微信支付**:JSAPI/APP 下单、企业付款到零钱(分账用商户平台「分账」能力)。
- **支付宝**:App 支付、单笔转账到账。
- **银行卡**:通过持牌支付机构 / 银联代付通道。

替换点:各 API 路由中 `MockPaymentAdapter()`(`backend/app/api/wallet.py`、`backend/app/api/dispatch.py`)。建议改为依赖注入,统一从工厂获取。

需要准备:支付/商户资质、平台备案、资金结算账户、对账文件处理。

## 3. 实名认证 (KYC)

实现 `IdentityAdapter.verify(name, id_card)`,对接公安实名核验 / 三方 KYC(人脸 + 身份证 OCR + 二要素/三要素核验)。

替换点:[`backend/app/services/auth.py`](../backend/app/services/auth.py) 中的 `_identity = MockIdentityAdapter()`。

## 4. 生产化改造清单

- **数据库**:SQLite → PostgreSQL(改 `ANTDASH_DATABASE_URL`),加 Alembic 迁移。
- **配置**:`config.py` 的运行时覆盖当前为进程内内存;生产应落库并支持多实例一致性。
- **撮合触发**:当前为请求触发;生产应由后台任务/消息队列(Celery / APScheduler)按周期与事件驱动。
- **鉴权**:JWT 密钥用环境变量注入,启用刷新令牌与角色权限校验。
- **凭证存储**:图片存对象存储(OSS/S3)而非本地 `media/`。
- **可观测性**:结构化日志、指标、审计(账本已只读,补充操作审计)。
- **安全合规**:身份证/支付敏感信息加密存储,满足等保与个人信息保护要求。

## 环境变量

以 `ANTDASH_` 前缀覆盖 `config.py` 中任意字段,例如:

```bash
export ANTDASH_DATABASE_URL="postgresql+psycopg://user:pass@host/antdash"
export ANTDASH_JWT_SECRET="<32+ 字节随机串>"
export ANTDASH_ERRAND_FEE_PCT_X=20
export ANTDASH_PLATFORM_FEE_PCT_Y=10
```
