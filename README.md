# 设备资产管理系统

公司内部设备台账 · 扫码借还。全中文、自托管。需求见 [设备资产管理系统-PRD.md](设备资产管理系统-PRD.md)。

技术栈:FastAPI + SQLite(WAL) + Vue3 / Element Plus,前端构建产物由后端同域托管,Caddy 反代自动签发 HTTPS。

---

## 当前进度

MVP(PRD 阶段一)后端与前端已完成:

- 登录鉴权、首次登录强制改密、登录失败锁定
- 分类管理、采购公司管理(含查看公司名下设备)、资产编号自动生成、二维码生成与批量导出
- 设备台账:搜索、筛选、分页、增删改(软删除)
- 借出 / 归还、流转历史、逾期列表、我的设备
- 盘库(滚动盘点):连续扫码批量盘、差异挂起与处理、超期未盘清单、盘库概览
- 设备复制(同型号批量录入)、序列号扫码录入(一维码 / 二维码 / DataMatrix)
- 移动扫码页(取景框 + 手动输入兜底 + 连续扫码)
- Docker Compose 部署

**尚未验证的两件事(PRD 迭代 0),上线前必须做:**

1. **标签打样实测**——用真标签机打 3 张 12mm 标签,分别用低端安卓机和旧 iPhone 扫,**必须用本系统的扫码页扫,不能只用微信验证**(微信支持 Micro QR 等更多码制,会给出假的通过)。

   二维码是标准 QR version 1,21×21 模块,加上四周各 4 模块静默区共 29 模块宽。12mm 标签实际可打印宽度只有 9~10mm,算下来每模块约 **0.31mm**;而 203dpi 标签机一个点是 0.125mm,一个模块只占 2.5 个点——**非整数倍会让模块边缘参差,是扫不动的主要原因**。排版时优先把模块尺寸凑成点距的整数倍(0.375mm = 3 点),宁可让码占满整个标签高度。

   实测不理想时的调整顺序见下方「二维码的三个参数」与「如果 12mm 实在打不好」。
2. **真机摄像头验证**——iOS 需分别验证 Safari 普通标签页与「添加到主屏幕」standalone 模式下的 `getUserMedia`。这是整个项目唯一可能做不成的技术点。

阶段二尚未开始:概览看板、Excel 导入导出、设备照片、内置标签打印、盘点、操作日志页面。

---

## 本地开发

需要 Python 3.12+ 与 Node 20+。

**后端**

```bash
cd backend
py -3.12 -m venv .venv                     # Windows;Linux/macOS 用 python3.12
./.venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

首次启动会自动建表,并创建初始管理员 `admin` / `admin12345`(可用 `SNIPE_INITIAL_ADMIN_PASSWORD` 覆盖)以及 5 个默认分类。首次登录会被要求改密。

接口文档:http://127.0.0.1:8000/docs

**前端**

```bash
cd frontend
npm install
npm run dev
```

Vite 把 `/api` 代理到 `127.0.0.1:8000`,与生产同域,不需要处理 CORS。

**测试**

```bash
cd backend
./.venv/Scripts/python.exe -m pytest tests -q
```

### 用手机调试扫码页

摄像头需要**安全上下文**:`localhost` 算安全,但手机通过局域网 IP(`http://192.168.x.x:5173`)访问**不算**,`getUserMedia` 会直接失败。三个办法:

- 用 Chrome 的 `chrome://flags/#unsafely-treat-insecure-origin-as-secure` 把该 IP 加进白名单(仅安卓 Chrome)
- 用 `cloudflared tunnel --url http://localhost:5173` 之类的临时隧道拿一个 HTTPS 地址
- 直接部署到测试环境走 Caddy 的 HTTPS

页面在摄像头不可用时会给出中文提示并引导用手动输入编号,不会白屏。

---

## 部署

先准备环境变量:

```bash
cp .env.example .env
# 至少要填 SNIPE_SECRET_KEY(openssl rand -base64 48)和 SNIPE_INITIAL_ADMIN_PASSWORD
```

### 情况一:服务器上已有 Nginx / 宝塔面板(推荐)

```bash
docker compose up -d --build
```

只起应用容器,监听 `127.0.0.1:8000`,不碰 80/443。再用宿主机上的 Nginx(或宝塔的反向代理)转发过去、签证书。详见 [docs/宝塔部署.md](docs/宝塔部署.md)。

### 情况二:独立服务器,80/443 空着

叠加 Caddy,自动申请并续期证书:

```bash
# .env 里补上 SITE_ADDRESS=assets.example.com
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
```

域名需先解析到这台服务器,且 80/443 可从公网访问。

### 反代必须转发的头

容器跑在反代后面。**`X-Forwarded-For` 一定要转发**——否则 `request.client.host` 拿到的是反代自己的地址,登录失败的 IP 限流会把全公司算成同一个来源。容器启动命令里已经带了 `--proxy-headers --forwarded-allow-ips=*`,反代那边配好即可。

**备份**:数据都在 `snipe-data` 这个 volume 里(SQLite 单文件)。

```bash
docker compose exec app sh -c 'sqlite3 /data/snipe.db ".backup /data/backup.db"'
docker compose cp app:/data/backup.db ./backup-$(date +%F).db
```

---

## 几个绕不开的设计约定

改代码前值得先看一眼,这些约定散落在各处但彼此关联。

### 二维码里只有资产编号,没有 URL

这是刻意的:**让标签在本系统之外被扫到时读不出任何信息**。用微信或系统相机扫这张标签,只会得到一串 `PC-0001`,无法跳转、无法查询、看不出是什么设备、归谁、在哪。

代价是员工无法用微信扫一扫直接进来,必须先打开本系统再用页面内的扫码器。移动端首页因此直接就是取景框,并把登录态放到 30 天,尽量抵消这个摩擦。

配套的安全边界:

- **二维码是标识符,不是凭证**。标签贴在设备外壳上,拍张照就等于拿到内容,所以绝不能有「扫到码即可免登录查看/借还」的捷径。查详情、借还一律走登录后的接口。
- `by-tag` 接口鉴权 + 每用户 60 次/分钟限流,防止按编号规律枚举全量台账;查不到统一返回 404,不提示编号是否存在。

### 二维码的三个参数都不能随便动

`_make_qr()` 里的三个参数各自挡着一个坑:

- **`micro=False`** —— 编号只有 7 个字符,segno 默认会挑 **Micro QR**(15×15),而 ZXing 和浏览器 `BarcodeDetector` **都不支持 Micro QR**,标签打出来我们自己的扫码页反而读不出来。
- **`error="h"`** —— 30% 纠错。version 1 在 H 级下能装 10 个字母数字字符,而编号最长就是 10 个,所以码的尺寸一格没变,抗磨损却从 15% 提到 30%,等于白拿。设备标签会蹭脏、磨损、被手指盖住一角。
- **`border=4`** —— QR 规范要求的静默区。留白不够时扫码器找不到定位图形。在已经接近打印极限的 12mm 标签上,这是最不该省的地方。

配套约束:**资产编号最长 10 个字符**,所以分类前缀限长 5 位(`CategoryCreate.tag_prefix`)。多一个字符就跳到 version 2(25×25),模块从 0.31mm 缩到 0.27mm,12mm 标签会明显更难扫。

### 前端是两个独立入口

| 入口 | 文件 | 路由 | UI 库 | 首屏 |
|---|---|---|---|---|
| 桌面后台 | `index.html` → `src/main.js` | `/admin/*`、`/login` | Element Plus | ~1.4 MB |
| 手机端 | `m.html` → `src/mobile/main.js` | `/m/*` | Vant | ~340 KB |

后端 `spa_fallback` 按路径分发:`/m` 与 `/m/*` 给 `m.html`,其余给 `index.html`。
两个入口各自打包,手机用户不会白下载一整套桌面组件;将来手机端要套 App 壳或
重写成小程序,只动这一半。

**共享的东西只能是 UI 无关的**:`api.js`、`format.js`、`store.js`、`QrScanner.vue`。
`api.js` 里的 `toast()` 因此不能直接 `import { ElMessage }` —— 那会把整个
Element Plus 拖进手机端的包(实测多下载 1 MB)。改成各入口用
`setErrorNotifier()` 注入,和 `setUnauthorizedHandler()` 一个套路。

两个入口之间跳转必须整页跳(`window.location`),前端路由跳不过去。

### 后台在手机上走卡片,不是硬压表格

管理员会拿手机开后台(移动端菜单里就有入口)。`el-table` 在窄屏下基本没法用 ——
尤其 `fixed="right"` 的操作列会盖住整张表,只剩一列按钮可见。所以:

- 台账窄屏时**换成卡片列表**(`useNarrow()` 判断),筛选项收进底部抽屉
- 其余后台表格窄屏时**去掉 `fixed`**,让它正常横向滚动而不是叠在内容上
- 顶部导航窄屏时隐藏标题、菜单横向滚动

没有引入第二套 UI 库。移动端 `/m/*` 那几页本来就是移动优先的简单布局,
再塞一套 Vant 只会让包体翻倍、两种设计语言并存。

### 两个扫码器,码制范围是故意不同的

`QrScanner` 有个 `formats` 参数:

- **扫资产标签**(移动首页、盘库)只认 `qr_code`。标签是我们自己印的,限定单一
  码制能少很多误读 —— 设备上往往还贴着厂商的条码,放开了容易扫错东西。
- **录序列号**(`ScanInput`)放开一维码、二维码和 DataMatrix。厂商贴的 SN 码制
  五花八门,限定了就等于不能用。

原生 `BarcodeDetector` **只在它支持全部所需码制时才启用**,少一种就整体回退
ZXing —— 支持一半的话,漏掉的那种扫不出来,用户只会以为功能是坏的。ZXing 多码制
路径开了 `TRY_HARDER`,DataMatrix 和小尺寸一维码不开基本扫不出来。

### 盘库记的是观察值,写不写回台账是另一回事

盘库接口**永远提交成功** —— 现场盘库的人不该因为权限或状态冲突卡在半路。
是否写回台账分情况:管理员盘出的差异当场写回;普通用户盘出的差异挂起,进
「待处理差异」等管理员采纳或忽略。

`location_at_check` / `status_at_check` 这两个**台账快照必须存**。差异不能靠
「观察值 vs 当前台账」来判断 —— 台账后来又被改过的话就对不上了。

「最后盘库时间」和「是否有差异」都是派生的,不在 `assets` 上冗余字段,理由与
「借出」一样:两处存一份数据迟早打架。

还有一条既有规则要守住:借出中的设备不允许改状态,所以即便是管理员,盘库时的
状态差异也只挂起,等归还后再处理 —— 位置仍可当场修正。

### 分类和采购公司都不能在「名下还有设备」时删除

判断必须把**软删除的设备也算进去**。软删除只是给 `deleted_at` 打了时间戳,行还在、
外键也还指着,只数在册设备的话这里会放行,然后在 `DELETE` 时撞上 SQLite 的
`FOREIGN KEY constraint failed`。所以两处删除接口都分别统计在册和已删除台数,
任一非零就拒绝,并在提示里说清是哪种。

### 改了外键之后别直接读关系

Session 是 `expire_on_commit=False`(为了让 `checkout()` 提交后还能序列化返回值),
代价是提交后对象上**已加载的关系不会失效**。所以 `update_asset` 改完
`category_id` / `company_id` 后显式 `db.expire(asset)` 再重新查——否则 `joinedload`
会命中 identity map 里的旧对象,把改动前的分类名和采购公司返回给前端。

### 「借出」不是设备状态

`assets.status` 只有 **在库 / 维修 / 报废** 三个值。是否借出由「存在 `checked_in_at` 为空的借还记录」派生,不冗余存字段——否则一定会出现「状态显示在库,但有条借出记录没关」的脏数据。

并发靠数据库硬约束:`checkout_records` 上有唯一部分索引 `uq_active_checkout_per_asset`,同一设备至多一条未归还记录。借出走「插入 + 捕获唯一冲突」,**不做「先查后写」**,所以两个人同时扫同一台相机点借出,必定只有一个成功。

### 长期责任人 ≠ 借用人

两种流转模式在实际使用中差别很大:

- `assets.owner_user_id` = **长期责任人**(员工的笔记本,一发三年),管理员手工指定,**借还流程不会修改它**
- **当前借用人**(相机镜头,按次借还)从最新未归还记录派生,不存字段

「我的设备」两者都算。

### 资产编号一经生成永不变更

标签已经贴在实物上了。改分类不改编号,分类前缀只在生成时用一次;分类的 `tag_prefix` 创建后也不允许改。流水号靠 `UPDATE seq = seq + 1` 原子推进,插入包在 SAVEPOINT 里,撞车了就推进到下一个号重试(存量设备手工占号的情况会走到这条路径)。

### 时间一律存朴素 UTC

SQLite 的 DATETIME 列不保存时区偏移,写入带时区的 datetime 会被静默丢弃,读回来是朴素时间,再和带时区的 `now()` 比较就抛 `TypeError`。所以全库存朴素 UTC,出口处由 `schemas.UtcDatetime` 补上时区再序列化——否则前端 `new Date("2026-08-26T10:00:00")` 会按浏览器本地时区解析,时间全错。

### 认证

JWT 放 **httpOnly + SameSite=Lax Cookie**,不放 localStorage:同域部署 + SameSite=Lax 已能防跨站 CSRF,同时 XSS 也偷不走 token。前端因此完全不接触 token,只要 `credentials: 'same-origin'`。

登录防爆破的主防线是**账号级锁定**(连续失败 5 次锁 15 分钟),IP 限流只是辅助——全公司共用一个出口 IP,那个值不能设太紧。

---

## 已知取舍

- **限流是进程内的**(`app/ratelimit.py`),单进程部署够用。若要多 worker 或横向扩容,换成 Redis。
- **@zxing/browser 打包后约 1MB**,只在不支持 `BarcodeDetector` 的浏览器(主要是 iOS Safari)按需动态加载。安卓 Chrome 走原生 API,不会下载这个包。
- **建表用 `create_all`**,还没接 Alembic。表结构稳定前先这样,首次正式部署前应补上迁移。
- **没有设备照片上传**,PRD 已把照片移到阶段二。
