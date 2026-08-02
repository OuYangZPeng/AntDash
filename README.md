# 蚂蚁闪达 (AntDash)

聚合外卖末端配送平台 MVP。将 **美团 / 闪购 / 京东** 的订单实时接入,通过**撮合引擎**把同小区订单聚合成团;外卖骑手送到小区门口拍照后,聚合单派发给附近专职 **Anter**;Anter 送达并拍照回写各平台,推动订单状态更新。平台前期只做转发,从跑腿费中抽取维护费。

> 本仓库是**可运行的原型 / MVP**。所有外部依赖(平台订单 API、微信/支付宝/银行卡支付、实名认证)都通过**可插拔适配器**实现,当前使用 mock / 沙箱数据。拿到企业资质后,只需替换适配器实现即可对接真实系统,核心业务逻辑无需改动。详见 [docs/INTEGRATION.md](docs/INTEGRATION.md)。

## 目录结构

```
AntDash/
├── backend/          FastAPI 后端 (撮合/信誉/分账引擎 + API)
│   ├── app/
│   │   ├── adapters/ 平台/支付/实名 适配器 (抽象接口 + mock)
│   │   ├── services/ matching / reputation / ledger / dispatch / proof / auth
│   │   ├── api/      路由
│   │   ├── models.py 数据模型 (SQLModel)
│   │   └── config.py 业务参数 (X / Y / 时间窗 T 等)
│   ├── tests/        单元测试 + 端到端流程测试
│   ├── demo.py       一键演示完整业务流程 (无需起服务)
│   ├── seed.py       造演示数据
│   └── run.sh        一键启动服务
├── app/              Flutter 跨平台 App (iOS / Android)
│   └── lib/          登录 / 接单大厅 / 订单详情 / 钱包 / 我的
└── docs/             算法说明 / API 约定 / 真实接入指引
```

## 快速开始

### 后端

```bash
cd backend
bash run.sh          # 建 venv、装依赖、造数据、启动服务 (http://127.0.0.1:8080)
```

API 文档: http://127.0.0.1:8080/docs

跑测试与演示:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q          # 单元 + 端到端测试
python demo.py               # 叙事化演示完整业务流程
```

随机造单 · 聚合算法压测(需后端已启动,须用 venv 里的解释器):

```bash
cd backend
source .venv/bin/activate                                   # 或用 .venv/bin/python 直接调用
python gen_orders.py                                        # 20 单 / 1 轮 / 5 小区
python gen_orders.py --count 30 --rounds 3 --interval 1 --communities 2 --seed 7
```

> macOS 上命令是 `python3` 而非 `python`;且本工具依赖 `httpx`,请用项目 `.venv`(`source .venv/bin/activate` 后 `python`,或直接 `.venv/bin/python gen_orders.py ...`),勿用系统 `python3`。

`--communities` 越小订单越集中、聚合越密;`--rounds/--interval` 模拟订单流。工具会打印**聚合率、平均/最大团单数、各小区与各状态分布**等指标,用于验证撮合算法。生成的订单同时会出现在 App 里(可观察每单的超时倒计时)。

### Flutter App

需要本地安装 Flutter SDK (`flutter --version`)。首次运行需生成平台脚手架:

```bash
cd app
flutter create .             # 生成 android/ios/web 等平台目录 (只需一次)
flutter pub get
flutter run                  # 连接后端,默认 http://127.0.0.1:8080
```

> Android 模拟器请把 `lib/api/api_client.dart` 的 `baseUrl` 改为 `http://10.0.2.2:8080`。
> 演示账号:手机号 `13800000001`,验证码任意 4 位以上;实名身份证输入任意 18 位合法格式。

## iOS 打包指南

本项目依赖均为纯 Dart 包(`http` / `provider` / `intl` / `cupertino_icons`),**不含原生插件,无需 CocoaPods**。Xcode 工程(`app/ios/Runner.xcworkspace`)在 `flutter create` 时已生成。

### 0. 准备 Xcode 工具链(仅首次)

必须安装**完整版 Xcode**(App Store),仅 Command Line Tools 无法 archive。安装后把工具链指向 Xcode 并接受许可:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
xcodebuild -version          # 验证:应输出 Xcode 版本号而非报错
```

### 1. 在模拟器上运行 / 构建(免签名)

```bash
cd app
# 构建模拟器包 (debug)
flutter build ios --simulator --debug        # 产物: build/ios/iphonesimulator/Runner.app

# 或直接运行到模拟器
open -a Simulator                             # 启动模拟器
flutter devices                               # 确认设备 id
flutter run -d "<simulator-id>"
```

> 模拟器与本机共享网络,直接用 `http://127.0.0.1:8080` 即可连到后端。

### 2. App 品牌配置(Bundle ID / 名称 / 图标 / 启动屏)

本仓库已完成以下品牌化配置,可直接复用或按需修改:

| 项目 | 值 | 位置 |
| --- | --- | --- |
| Bundle Identifier | `com.antdash.app` | `app/ios/Runner.xcodeproj/project.pbxproj`(`PRODUCT_BUNDLE_IDENTIFIER`) |
| 显示名称 | 蚂蚁闪达 | `app/ios/Runner/Info.plist`(`CFBundleDisplayName`) |
| App 图标 | 橙底白闪电 | `app/ios/Runner/Assets.xcassets/AppIcon.appiconset/` |
| 启动屏 | 橙色背景 + 居中 Logo | `app/ios/Runner/Base.lproj/LaunchScreen.storyboard` + `LaunchImage.imageset/` |
| 开发团队 | 自动签名 | `project.pbxproj`(`DEVELOPMENT_TEAM` / `CODE_SIGN_STYLE = Automatic`) |

**改 Bundle ID / 名称**:直接改上表对应文件即可(或在 Xcode GUI 里改)。

**换 App 图标**:准备一张 1024×1024 母图,用 `sips` 生成全部尺寸(母图需**无透明通道**,否则 App Store 校验会报错):

```bash
M=path/to/icon_1024.png
D=app/ios/Runner/Assets.xcassets/AppIcon.appiconset
for s in "20x20@1x:20" "20x20@2x:40" "20x20@3x:60" "29x29@1x:29" "29x29@2x:58" \
         "29x29@3x:87" "40x40@1x:40" "40x40@2x:80" "40x40@3x:120" "60x60@2x:120" \
         "60x60@3x:180" "76x76@1x:76" "76x76@2x:152" "83.5x83.5@2x:167" "1024x1024@1x:1024"; do
  name=${s%:*}; px=${s#*:}
  sips -z $px $px "$M" --out "$D/Icon-App-$name.png"
done
```

> `flutter build ipa` 若提示 *App icon is set to the default placeholder icon*,说明图标仍是默认模板,警告消失即表示替换成功。

**换启动屏**:替换 `LaunchImage.imageset/` 里的三张 PNG,并在 `LaunchScreen.storyboard` 里改 `backgroundColor`(本项目用品牌橙 `#F07D19` = rgb 240,125,25)。

### 3. 打 Release IPA 包(真机分发)

先配置签名(只需一次):打开 `app/ios/Runner.xcworkspace` → 选中 `Runner` target → **Signing & Capabilities** → 勾选 *Automatically manage signing* → 选择你的 **Team**(免费 Apple ID 即可)。

根据账号类型选择导出方式:

```bash
cd app

# A. 免费 / 个人 Apple ID —— 只能用 development 导出
flutter build ipa --export-method development

# B. 付费开发者账号 —— 可导出 App Store / Ad-Hoc 包
flutter build ipa                             # 默认 app-store
flutter build ipa --export-method ad-hoc      # Ad-Hoc 分发
```

产物:

- Archive: `app/build/ios/archive/Runner.xcarchive`
- IPA: `app/build/ios/ipa/antdash.ipa`

> ⚠️ 免费个人账号**无法**创建 "iOS App Store" / "iOS Distribution" 描述文件,直接 `flutter build ipa` 会报
> `Team ... does not have permission to create "iOS App Store" provisioning profiles`,
> 此时改用 `--export-method development` 即可成功。

### 4. 安装到真机

免费个人账号首次给某个 Bundle ID 打包时,团队里可能**没有已注册的设备**,会报
`Your team has no devices ...` / `No profiles for '...' were found`。连上真机后用下面命令**自动注册设备并生成描述文件**(只需一次):

```bash
cd app/ios
xcodebuild -workspace Runner.xcworkspace -scheme Runner -configuration Release \
  -destination 'id=<device-udid>' \
  -allowProvisioningUpdates -allowProvisioningDeviceRegistration build
```

`<device-udid>` 可通过 `flutter devices` 或 `xcrun xctrace list devices` 获取。注册成功后即可正常构建安装:

```bash
cd app
flutter build ios --release                   # 产物: build/ios/iphoneos/Runner.app
flutter install -d <device-udid>              # 或 flutter run --release -d <device-udid>
# 或用 Xcode: open ios/Runner.xcworkspace 选中真机点 Run
```

首次在设备上打开,需到 **设置 → 通用 → VPN 与设备管理** 里信任你的开发者证书。

> 注意:免费账号签发的描述文件**有效期仅 7 天**,过期后需重新构建安装;正式上架请使用付费开发者账号并替换为自有 Bundle ID / 图标。

## Android 打包指南

需要本地安装 **Android SDK**(Android Studio 或 command-line tools)。本项目已用如下方式在 macOS 上配置(仅首次):

```bash
brew install --cask android-studio            # GUI / 模拟器(可选)
brew install --cask android-commandlinetools  # 命令行构建必需,提供 sdkmanager

export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"   # 复用 Android Studio 自带 JDK 21
yes | sdkmanager --sdk_root="$ANDROID_HOME" --licenses
sdkmanager --sdk_root="$ANDROID_HOME" "platform-tools" "platforms;android-36" "build-tools;36.0.0"

# 让 flutter 记住 SDK / JDK 位置(持久化,后续无需再设环境变量)
flutter config --android-sdk "$ANDROID_HOME"
flutter config --jdk-dir "$JAVA_HOME"
flutter doctor                                 # 应看到 [✓] Android toolchain
```

> 首次 `flutter build apk` 时 Gradle 会自动补装 NDK、CMake 等组件。

### 品牌配置

本仓库已完成以下配置:

| 项目 | 值 | 位置 |
| --- | --- | --- |
| Application ID | `com.antdash.app` | `app/android/app/build.gradle.kts`(`applicationId` / `namespace`) |
| App 名称 | 蚂蚁闪达 | `app/android/app/src/main/AndroidManifest.xml`(`android:label`) |
| 启动 Activity | `com.antdash.app.MainActivity` | `app/android/app/src/main/kotlin/com/antdash/app/MainActivity.kt` |
| App 图标 | 橙底白闪电 | `app/android/app/src/main/res/mipmap-*/ic_launcher.png` |

> 改包名时,`applicationId`、`namespace`、`MainActivity.kt` 的 `package` 声明及其目录路径需保持一致。

换图标(从 1024 母图生成各密度):

```bash
M=path/to/icon_1024.png
R=app/android/app/src/main/res
sips -z 48 48   "$M" --out "$R/mipmap-mdpi/ic_launcher.png"
sips -z 72 72   "$M" --out "$R/mipmap-hdpi/ic_launcher.png"
sips -z 96 96   "$M" --out "$R/mipmap-xhdpi/ic_launcher.png"
sips -z 144 144 "$M" --out "$R/mipmap-xxhdpi/ic_launcher.png"
sips -z 192 192 "$M" --out "$R/mipmap-xxxhdpi/ic_launcher.png"
```

### 构建与运行

```bash
cd app
flutter build apk --release          # 产物: build/app/outputs/flutter-apk/app-release.apk
flutter build appbundle --release    # 上架 Google Play 用的 .aab
flutter install                      # 安装到已连接的 Android 设备/模拟器
flutter run                          # 调试运行
```

> Android 模拟器请把 `lib/api/api_client.dart` 的 `baseUrl` 改为 `http://10.0.2.2:8080` 才能连到本机后端。
> release 版当前用 debug 签名(见 `build.gradle.kts` 的 `signingConfig`),正式发布 Google Play 需配置自己的 keystore 签名。

## 核心业务流程

```mermaid
sequenceDiagram
  participant P as 平台(美团/闪购/京东)
  participant I as 订单接入
  participant M as 撮合+定价引擎
  participant R as 外卖骑手
  participant N as 通知(1km)
  participant A as Anter/骑手
  participant L as 分账引擎
  P->>I: 实时订单(含楼层/重量/品类/SLA)
  I->>M: 按小区聚合(动态时间窗 T)+ 成团打分
  M->>M: 成团即冻结动态定价 P(基础包×系数,含 floor/cap)
  R->>M: 送到小区门口 + 逐单拍照(越早到→跑腿费折扣↑)
  M->>N: 成团/临期 → 推送 1km 内 Anter(与骑手)
  N->>A: 新单/加急/救援 弹窗(按信誉分排序)
  A->>A: 接单(必须履约;骑手也可当 Anter 救援)
  A->>L: 逐单拍照送达
  L->>P: 回写订单状态
  L->>A: 结算 = P×(1-Y%) + 救援奖金
  Note over M,N: 后台巡检未接单:临期加急费↑、扩圈重推、<15min 派骑手救援
```

订单/聚合单状态机:`ingested →(撮合)matched →(成团+定价)ready →(骑手到门口)at_gate →(接单)accepted →(拍照送达)delivered →(结算)settled`。

以下所有参数均在 [`backend/app/config.py`](backend/app/config.py),可运行时 `PATCH /admin/config` 动态调整;纯算法函数与 DB 解耦,见 `backend/tests/`。完整说明见 [docs/ALGORITHMS.md](docs/ALGORITHMS.md)。

### 1. 撮合:动态时间窗 T

同小区订单在 `open` 状态累积,直到 T 到期或达聚合上限:

```
T = clamp( T_base × (target / max(arrival_rate, ε)),  T_min,  T_max )
```
- `arrival_rate` = 最近 10 分钟订单到达速率(单/分钟);订单稀疏→T 增大(多凑单),密集→T 减小(保时效)。
- **楼栋聚合约束**:一个聚合单只聚合**同一或相邻楼栋**(楼栋号差 ≤ `building_adjacency`,默认 1)的订单,**最多 5 单**(`match_max_bundle_size_adjacent`);超出则另起新团。
- 默认:`T_base=10min, T_min=3, T_max=25, target=4, 楼栋上限=5`。

### 2. 成团打分(越高越优先成团)

```
score = w1·同小区 + w2·地理邻近 + w3·时效余量 + w4·聚合效率
        地理邻近 = 1 / (1 + 平均两两距离km)
        时效余量 = sigmoid( (最紧订单剩余分钟 − 10) / 5 )
        聚合效率 = min(size, N_max) / target        (上限 1)
```
- 默认权重:`w1=0.40, w2=0.25, w3=0.20, w4=0.15`。

### 3. 动态定价(成团时冻结)

对标美团:**确定性基础包 + 规模因子 + 波动系数**,再受上下限保护。

```
单均基础包 pkg_i = 起步价 + 距离费 + 楼层费(无电梯) + 重量费 + 时效紧张费 + 品类费(生鲜/易碎)
    距离费 = round( max(0, 门口→门距离m − 免距离半径) / 100 × 每百米费 )
    楼层费 = min(楼层−1, 封顶层数) × 每层费          (仅无电梯)
    重量费 = round( max(0, 重量g − 免重量g) / 1000 × 每kg费 )

聚合单基础包 P_base = round( Σ pkg_i × (1 − 聚合折扣) )      (仅 N≥2 生效;与单数非线性,固定省 5%)
    聚合折扣省下的 5%(Σpkg_i − P_base)→ 投入当天**应急奖金池**(用于救援等紧急激励;GET /admin/pool 查询)

波动系数 M_full = M_时段 × M_天气 × M_供需
    M_供需 surge = clamp( 1 + k·(demand/supply − 1),  1,  surge_max )   (按小区,样本稀疏回退全局)

聚合单价 P = clamp( round(P_base × M_full),  下限,  上限 )
    下限 = round(订单总额 × X%_floor)          (保底,默认对齐 X=20%)
    上限 = 单均封顶 × N
```
- 默认:`起步价 2.5元, 免距离 80m, 0.5元/100m, 无电梯 0.6元/层(封顶8层), 免重 3kg 后 1元/kg, 生鲜+1元, 易碎+1.5元, 时效紧张(≤15min)+1.5元`。
- 时段:午 11–13 / 晚 17–20 高峰 `×1.2`,深夜 22–06 `×1.15`;天气:雨 `×1.15`、大雨 `×1.3`、雪 `×1.5`、极端 `×1.25`;`surge: k=0.6, max=1.8`;单均封顶 15 元。

### 4. 出资拆账(谁付这笔钱)

C 端不可见价格;骑手只付确定性成本,平台补贴池承担波动溢价:

```
骑手扣款 rider_charge = min( P_base × M_时段^rider,  P )   (M_时段^rider 封顶 1.1;surge/天气默认不转嫁)
平台补贴 subsidy      = P − rider_charge
平台维护费 platform_fee = round(P × Y%)
Anter 实收  anter_net   = P − platform_fee
平台净       = platform_fee − subsidy               (平峰赚维护费,高峰补贴换运力)
```
- 骑手扣款按各订单基础包占比分摊到每单(不丢分);`rider_bears_surge / rider_bears_weather` 可切换是否转嫁(默认 false)。

### 5. 信誉分 / 派单频率

```
信誉分 S ∈ [0,100],初始 60;  on_time +3 · early +1 · late −5 · abandon −15 · complaint −10 · rescue +5
准时率(EWMA) = α·本次结果 + (1−α)·历史            (α=0.3;准时/提前记 1,超时/甩单记 0)
派单权重 dispatch_weight = base · sigmoid( (S − 50) / 10 )
```
- `S < 35` 进入冷却(默认 15min 不派单);空闲守约时以 `0.05 分/分钟`向 60 缓慢回升。接单大厅按权重降序排序(信誉越高越优先)。

### 6. 临期升级 + 加急费(后台每 20s 巡检未接单)

以最紧子单剩余 SLA 分级:`>20min` 正常 → `≤20` 加急 → `≤15` 触发救援 → `≤6` 封顶 → 已超时兜底。

```
加急费 urgency_fee = round( P_base × urgency_max_ratio × frac )
    frac = clamp( (urgency_start − remaining) / urgency_start,  0,  1 )
推送半径 = min( notify_radius + step×(stage−1),  radius_max )     (1→2→3 km)
```
- 加急费只对未接单累积、`accept` 时冻结;结算并入平台补贴。默认:`urgency_start=20min, urgency_max_ratio=0.6, radius_max=3km`。

### 7. 骑手救援(< 15 分钟未接单)

- 向 **1km 内的外卖骑手 + Anter** 推送 `rescue` 事件(App 强弹窗);**外卖骑手可直接当 Anter** 接单救援。
- 救援(送达曾进入救援态的单)奖励:**救援奖金** `rider_rescue_bonus`(默认 3 元,奖金池出资)+ **信誉 +5**(→ 优先派单)+ `rescue_count` 计数。

### 8. 骑手提前到门口奖励(纳入费用动态计算)

骑手越早把订单送到小区门口(留给聚合派送的时间越多),跑腿费减免越多:

```
早到折扣 discount = round( rider_charge × early_ratio_max × min( 送达时剩余SLA / slack_ref, 1 ) )
rider_charge −= discount ;  bundle.subsidy += discount        (平台吸收,Anter 收入不变)
```
- 默认:`early_ratio_max=0.3(最高抵 30%), slack_ref=30min`。一个聚合单所有订单都送到门口后自动进入 `at_gate`(可接)。

### 9. 分账结算(送达时,逐单拍照后)

```
有效跑腿费 errand_fee = P + urgency_fee
platform_fee = round(errand_fee × Y%)
anter_net    = errand_fee − platform_fee + rescue_bonus
```
- **资金守恒**:`Σ rider_charge + subsidy(含加急费) + rescue_bonus = errand_fee + rescue_bonus = platform_fee + anter_net`。
- 全部以**分(cents)** 计、`round()` 取整,保证 `platform_fee + anter_net == errand_fee`(不丢分);结算生成**只读账本** `LedgerEntry`(`errand_fee_debit / platform_subsidy / rescue_bonus / platform_fee / anter_credit`),不可篡改、可对账。

### 收入示例

**静态回退**(关闭动态定价,`pricing_enabled=false`):4 单共 40 元,X=20%,Y=10%
→ 跑腿费 `4000×20%=800` 分(8 元)、平台费 `800×10%=80` 分(0.8 元)、**Anter 到手 720 分(7.2 元)**。

**动态定价**(晚高峰 ×1.2 + 雨 ×1.15 + 运力紧张 surge 1.3):基础包 ≈11.4 元 → 聚合单价 `P≈20.45 元`
→ 骑手扣款 ≈12.54 元(仅确定性 + 封顶高峰)、平台补贴 ≈7.91 元、平台费 ≈2.05 元、**Anter 实收 ≈18.41 元**;若为救援单再 +3 元奖金。

详见 [docs/ALGORITHMS.md](docs/ALGORITHMS.md) 与 [docs/API.md](docs/API.md)。商业侧的 2B 转型方案见 [docs/PIVOT_2B.md](docs/PIVOT_2B.md)。
