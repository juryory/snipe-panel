# 设备资产管理系统

公司内部设备台账 · 扫码借还。全中文、自托管。需求见 [设备资产管理系统-PRD.md](设备资产管理系统-PRD.md)。

技术栈:FastAPI + SQLite(WAL) + Vue3 / Element Plus,前端构建产物由后端同域托管,Caddy 反代自动签发 HTTPS。

---

## 当前进度

MVP(PRD 阶段一)后端与前端已完成:

- 登录鉴权、首次登录强制改密、登录失败锁定
- 分类管理、资产编号自动生成、二维码生成与批量导出
- 设备台账:搜索、筛选、分页、增删改(软删除)
- 借出 / 归还、流转历史、逾期列表、我的设备
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

```bash
cp .env.example .env
# 填 SITE_ADDRESS、SNIPE_SECRET_KEY(openssl rand -base64 48)、初始管理员密码
docker compose up -d --build
```

Caddy 会为 `SITE_ADDRESS` 自动申请并续期证书。域名需先解析到这台服务器,且 80/443 端口可从公网访问。

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
