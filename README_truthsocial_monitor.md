# Truth Social 监控 + 飞书推送 + 交易分析

## 1. 你将得到什么
- 每分钟检查一次 Trump Truth Social 最新发言
- 双源抓取：`Truth Social 官方 API` + `archive RSS`（官方异常时自动回退）
- 发现新发言后，自动调用分析模型（按你提供的交易框架 prompt）
- 自动推送到飞书群机器人
- 本地状态文件去重，避免重复推送

主脚本：`truthsocial_monitor.py`

## 2. 快速配置
在项目目录执行：

```bash
cd /Users/freedom33/Documents/New\ project
cp .env.example .env
```

编辑 `.env`，至少填这个：

```env
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
MINIMAX_API_KEY=你的 minimax key
```

可选：
- `ANALYSIS_PROVIDER=minimax`（默认）
- `ANALYSIS_PROVIDER=openai` 时需配置 `OPENAI_API_KEY`
- `ANALYSIS_PROVIDER=none` 则只推送原文，不做分析
- `ANALYSIS_PROMPT_FILE=./analysis_prompt.txt`：使用外部 prompt 文件
- `TRUTH_ACCOUNT_ID`：如果 `lookup` 接口不稳定，可手动填写账号 ID
- `ENABLE_ARCHIVE_FALLBACK=true`：开启 archive 兜底
- `ARCHIVE_RSS_URL=https://trumpstruth.org/feed`：archive 地址

## 3. 先做一次手动测试

```bash
python3 truthsocial_monitor.py --once
```

如果看到 `无新发言`，说明脚本跑通但没有新帖子。
如果有新帖子，会推送到飞书。

## 4. 每分钟运行（推荐 cron）

编辑 crontab：

```bash
crontab -e
```

加入：

```cron
* * * * * cd /Users/freedom33/Documents/New\ project && /usr/bin/python3 truthsocial_monitor.py --once >> /Users/freedom33/Documents/New\ project/outputs/truthsocial_monitor.log 2>&1
```

说明：
- `--once` 模式适合 cron
- 每分钟触发一次
- 日志写入 `outputs/truthsocial_monitor.log`

## 5. 常驻运行（可选）

```bash
./run_truthsocial_monitor.sh
```

这是常驻轮询模式（默认每 60 秒轮询一次）。

## 6. 关键参数说明
- `POLL_SECONDS`：轮询间隔（常驻模式有效）
- `ALERT_ON_STARTUP`：首次启动是否把当前最新帖也推送（默认 `false`）
- `TRUTH_EXCLUDE_REPLIES`：是否过滤回复（默认 `true`）
- `TRUTH_EXCLUDE_REBLOGS`：是否过滤转帖（默认 `true`）
- `STATE_FILE`：去重状态文件（默认 `./outputs/truthsocial_state.json`）
- `ENABLE_ARCHIVE_FALLBACK`：官方源失败时是否启用 archive 回退
- `ARCHIVE_RSS_URL`：archive RSS 源地址

## 7. 故障排查
- 401/403：检查 `FEISHU_WEBHOOK` 或 OpenAI key
- 请求超时：增大 `REQUEST_TIMEOUT`（如 30）
- Truth 接口报错：先在 `.env` 固定 `TRUTH_ACCOUNT_ID`
- 官方源持续超时：确认 `ENABLE_ARCHIVE_FALLBACK=true`，看日志是否已回退 archive
- 想重新全量触发：删除状态文件 `outputs/truthsocial_state.json`

## 8. 接口说明（实现逻辑）
脚本默认使用 Truth Social 的 Mastodon 风格公开接口：
- `GET /api/v1/accounts/lookup?acct=realDonaldTrump`
- `GET /api/v1/accounts/{id}/statuses?...`

并带有 archive 兜底源：
- `https://trumpstruth.org/feed`

如果 Truth Social 后续改接口，只需修改脚本中 `_resolve_account_id` 和 `_fetch_statuses_official` 两个函数。

## 9. GitHub Actions 定时运行（免本机常开）
仓库里已提供 workflow：
- `.github/workflows/truthsocial-monitor.yml`

### 启用步骤
1. 把代码推到 GitHub 仓库。
2. 在仓库 `Settings -> Secrets and variables -> Actions` 添加 Secrets：
   - `FEISHU_WEBHOOK`（必填）
   - `OPENAI_API_KEY`（必填）
   - `TRUTH_ACCOUNT_ID`（可选）
3. 到 `Actions` 页面手动点击一次 `Run workflow` 做首测。

### 定时说明
- 当前 cron 设为 `*/5 * * * *`（每 5 分钟）。
- GitHub Actions 的 schedule 本身有排队抖动，不保证秒级准点。
- 如果你要求严格 1 分钟级实时性，建议改回云主机常驻服务。

### 工作机制
- 每次运行执行 `python3 truthsocial_monitor.py --once`
- 通过 `actions/cache` 持久化 `STATE_FILE`，用于去重，避免重复推送
- 抓取使用双源：官方 API 优先，archive RSS 自动回退
