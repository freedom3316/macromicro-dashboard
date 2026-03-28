#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None


DEFAULT_ANALYSIS_PROMPT = """你现在是我的地缘政治与宏观事件交易分析助手。

我会给你一条 Donald Trump 在 Truth Social 上的原文发言。你的任务不是泛泛总结，而是把这条内容转换成“可交易的信息框架”，服务于短线与波段交易决策。

请严格按以下步骤输出：

【1. 原文核心摘要】
- 用 1-3 句话提炼这条发言的核心内容
- 不要复述废话，只提炼最重要的政策、地缘政治、外交、军事、关税、制裁、能源、央行、财政、选举、监管相关信息

【2. 信息属性判断】
判断这条发言更像以下哪一类，可多选，并给出理由：
- 情绪宣示
- 谈判施压
- 政策预告
- 正式政策信号
- 风险升级信号
- 风险缓和信号
- 舆论测试/试探性放话
- 对市场有直接交易意义的信息
同时给出一个：
- 市场影响强度评分：1-10
- 可信度评分：1-10
- 可交易性评分：1-10

【3. 对市场的第一层影响】
基于这条发言，分析未来：
- 几分钟内
- 当日内
- 未来 1-3 天
市场最可能先交易什么逻辑

优先分析这些资产类别：
- 原油（WTI、Brent）
- 天然气
- 黄金 / 白银
- 美元指数
- 美债收益率
- 股指期货（标普、纳指、道指）
- 国防军工
- 航运
- 航空
- 大型科技股
- 中东、能源、军工、避险相关 ETF 或个股

要求：
- 区分“第一反应”和“后续修正”
- 区分“情绪驱动”与“基本面驱动”
- 区分“直接受益资产”和“间接受影响资产”

【4. 可交易映射】
请把这条发言映射成交易语言：
- 利多什么
- 利空什么
- 哪些资产最敏感
- 哪些资产可能是假动作、容易冲高回落/冲低反弹
- 哪些品种更适合做事件驱动短线
- 哪些品种更适合做波段跟踪

输出时按下面格式：
- 直接利多：
- 直接利空：
- 二阶受益：
- 二阶受损：
- 最敏感观察标的：
- 最可能先动的资产：
- 最可能后动的资产：

【5. 情景推演】
给出 3 个情景：
- 基准情景（概率最高）
- 乐观情景
- 风险升级情景

每个情景都要写：
- 触发条件
- 市场会怎么理解
- 哪些资产会怎么走
- 哪些价格/事件会验证这个情景
- 哪些信息会让这个情景失效

【6. 交易员视角的重点】
请站在事件驱动交易员视角，回答：
- 这条发言属于“值得追”的信息，还是“只适合观察”的噪音？
- 当前更适合追涨杀跌，还是等二次确认？
- 最值得盯的后续催化剂是什么？
- 接下来最该监控的官方源、新闻源、人物回应、市场指标有哪些？

【7. 输出要求】
请用简洁、专业、交易员能直接使用的语言输出，避免空泛评论。
不要写政治正确套话，不要写与交易无关的背景科普。
如果这条发言本身缺乏实质信息，要明确指出“交易价值有限”。
如果存在歧义，请明确列出不确定性，而不是强行下结论。"""


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def get_text(self) -> str:
        return "".join(self.parts)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and (key not in os.environ or not str(os.environ.get(key, "")).strip()):
            os.environ[key] = value


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def json_request(url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None, body: Optional[Dict[str, Any]] = None, timeout: int = 20) -> Any:
    req_headers = {"User-Agent": "truthsocial-monitor/1.0"}
    if headers:
        req_headers.update(headers)

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    request = Request(url=url, method=method, headers=req_headers, data=data)
    try:
        with urlopen(request, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            return json.loads(content)
    except Exception:
        cmd = ["curl", "-sS", "-L", "--max-time", str(timeout), "-X", method]
        for k, v in req_headers.items():
            cmd += ["-H", f"{k}: {v}"]
        if body is not None:
            cmd += ["-d", json.dumps(body, ensure_ascii=False)]
        cmd.append(url)
        out = subprocess.check_output(cmd, text=True)
        return json.loads(out)


def http_get_text(url: str, timeout: int = 20, headers: Optional[Dict[str, str]] = None) -> str:
    req_headers = {"User-Agent": "truthsocial-monitor/1.0"}
    if headers:
        req_headers.update(headers)
    request = Request(url=url, method="GET", headers=req_headers)
    try:
        with urlopen(request, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        cmd = ["curl", "-sS", "-L", "--max-time", str(timeout)]
        for k, v in req_headers.items():
            cmd += ["-H", f"{k}: {v}"]
        cmd.append(url)
        return subprocess.check_output(cmd, text=True)


def strip_html(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    text = unescape(parser.get_text())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_urls(value: str) -> str:
    text = re.sub(r"https?://\S+", "", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def now_str(tz_name: str) -> str:
    if ZoneInfo is None:
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    tz = ZoneInfo(tz_name)
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")


def extract_output_text(resp: Dict[str, Any]) -> str:
    if isinstance(resp.get("output_text"), str) and resp["output_text"].strip():
        return resp["output_text"].strip()
    chunks: List[str] = []
    for item in resp.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(x.strip() for x in chunks if x.strip()).strip()


@dataclass
class Config:
    base_url: str
    account_handle: str
    account_id: Optional[str]
    exclude_replies: bool
    exclude_reblogs: bool
    poll_seconds: int
    state_file: Path
    feishu_webhook: str
    timezone: str
    alert_on_startup: bool
    openai_api_key: str
    analysis_model: str
    analysis_prompt: str
    request_timeout: int
    archive_rss_url: str
    enable_archive_fallback: bool
    analysis_provider: str
    minimax_api_key: str
    minimax_base_url: str
    minimax_model: str
    backfill_max_send: int


class TruthSocialMonitor:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state = self._load_state()

    def _log(self, msg: str) -> None:
        print(f"[{now_str(self.cfg.timezone)}] {msg}", flush=True)

    def _load_state(self) -> Dict[str, Any]:
        if not self.cfg.state_file.exists():
            return {}
        try:
            return json.loads(self.cfg.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self) -> None:
        self.cfg.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.state_file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _resolve_account_id(self) -> str:
        if self.cfg.account_id:
            return self.cfg.account_id
        url = f"{self.cfg.base_url}/api/v1/accounts/lookup?acct={quote(self.cfg.account_handle)}"
        data = json_request(url, timeout=self.cfg.request_timeout)
        account_id = str(data.get("id", "")).strip()
        if not account_id:
            raise RuntimeError("无法通过 accounts/lookup 获取账号ID，请手动设置 TRUTH_ACCOUNT_ID")
        self.state["account_id"] = account_id
        self._save_state()
        return account_id

    def _fetch_statuses_official(self) -> List[Dict[str, Any]]:
        account_id = self.state.get("account_id") or self._resolve_account_id()
        limit = 40
        max_pages = 8
        max_id: Optional[str] = None
        all_items: List[Dict[str, Any]] = []
        last_id = str(self.state.get("last_status_id", "")).strip()

        for _ in range(max_pages):
            url = (
                f"{self.cfg.base_url}/api/v1/accounts/{account_id}/statuses"
                f"?limit={limit}&exclude_replies={'true' if self.cfg.exclude_replies else 'false'}"
                f"&exclude_reblogs={'true' if self.cfg.exclude_reblogs else 'false'}"
            )
            if max_id:
                url += f"&max_id={quote(max_id)}"

            page = json_request(url, timeout=self.cfg.request_timeout)
            if not isinstance(page, list):
                raise RuntimeError("状态接口返回异常，不是列表")
            if not page:
                break

            all_items.extend(page)
            if last_id and any(str(x.get("id", "")) == last_id for x in page):
                break

            max_id = str(page[-1].get("id", "")).strip()
            if not max_id:
                break

        return all_items

    def _fetch_statuses_archive(self) -> List[Dict[str, Any]]:
        xml_text = http_get_text(self.cfg.archive_rss_url, timeout=self.cfg.request_timeout)
        root = ET.fromstring(xml_text)
        ns = {"truth": "https://truthsocial.com/ns"}
        out: List[Dict[str, Any]] = []
        for item in root.findall("./channel/item"):
            raw_id = (
                item.findtext("guid")
                or item.findtext("link")
                or item.findtext("title")
                or ""
            )
            original_id = item.findtext("truth:originalId", default="", namespaces=ns).strip()
            original_url = item.findtext("truth:originalUrl", default="", namespaces=ns).strip()
            desc = item.findtext("description") or item.findtext("title") or ""
            clean_desc = strip_html(desc)
            pub_date = item.findtext("pubDate") or ""
            if not pub_date:
                continue

            dt = parsedate_to_datetime(pub_date)
            iso_time = dt.astimezone().isoformat()
            out.append(
                {
                    "id": original_id or raw_id,
                    "created_at": iso_time,
                    "url": original_url or item.findtext("link") or "",
                    "content": clean_desc,
                }
            )
        if not out:
            raise RuntimeError("archive RSS 未返回有效条目")
        return out

    def _fetch_statuses_dual_source(self) -> (List[Dict[str, Any]], str):
        official_statuses: List[Dict[str, Any]] = []
        archive_statuses: List[Dict[str, Any]] = []
        official_err = ""
        archive_err = ""

        try:
            official_statuses = self._fetch_statuses_official()
        except Exception as e:
            official_err = str(e)

        if self.cfg.enable_archive_fallback:
            try:
                archive_statuses = self._fetch_statuses_archive()
            except Exception as e:
                archive_err = str(e)

        if official_statuses:
            if archive_statuses:
                o_latest = sorted(official_statuses, key=lambda x: parse_dt(x["created_at"]))[-1]
                a_latest = sorted(archive_statuses, key=lambda x: parse_dt(x["created_at"]))[-1]
                if str(o_latest.get("id", "")) != str(a_latest.get("id", "")):
                    self._log(
                        f"双源最新ID不一致 official={o_latest.get('id')} archive={a_latest.get('id')}"
                    )
            return official_statuses, "official"

        if archive_statuses:
            self._log(f"官方源失败，已回退 archive。错误: {official_err or 'unknown'}")
            return archive_statuses, "archive"

        raise RuntimeError(
            f"双源均失败。official_err={official_err or 'n/a'}; archive_err={archive_err or 'n/a'}"
        )

    def _new_statuses(self, statuses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not statuses:
            return []

        statuses_sorted = sorted(statuses, key=lambda x: parse_dt(x["created_at"]))
        last_id = str(self.state.get("last_status_id", "")).strip()

        if not last_id:
            latest = statuses_sorted[-1]
            self.state["last_status_id"] = str(latest.get("id", ""))
            self.state["last_created_at"] = latest.get("created_at", "")
            self._save_state()
            if self.cfg.alert_on_startup:
                return [latest]
            return []

        result: List[Dict[str, Any]] = []
        for s in statuses_sorted:
            sid = str(s.get("id", ""))
            if sid and sid != last_id:
                result.append(s)

        # keep only statuses newer than last seen timestamp when ids are unknown/missing
        last_created_at = self.state.get("last_created_at")
        if last_created_at:
            try:
                floor = parse_dt(last_created_at)
                result = [x for x in result if parse_dt(x["created_at"]) > floor]
            except Exception:
                pass

        return result

    def _analyze(self, status_text: str) -> str:
        provider = self.cfg.analysis_provider.lower().strip()
        if provider == "minimax":
            return self._analyze_with_minimax(status_text)
        if provider == "openai":
            return self._analyze_with_openai(status_text)
        return ""

    def _analyze_with_openai(self, status_text: str) -> str:
        if not self.cfg.openai_api_key:
            return "未配置 OPENAI_API_KEY，已跳过分析。"

        url = "https://api.openai.com/v1/responses"
        body = {
            "model": self.cfg.analysis_model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": "你是专业的事件驱动交易分析助手，输出要简洁、结构化、可执行。"}]},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"{self.cfg.analysis_prompt}\n\nTrump Truth 原文如下：\n{status_text}",
                        }
                    ],
                },
            ],
        }
        headers = {"Authorization": f"Bearer {self.cfg.openai_api_key}"}
        resp = json_request(url, method="POST", headers=headers, body=body, timeout=max(self.cfg.request_timeout, 30))
        result = extract_output_text(resp)
        return result or "分析结果为空。"

    def _analyze_with_minimax(self, status_text: str) -> str:
        if not self.cfg.minimax_api_key:
            return "未配置 MINIMAX_API_KEY，已跳过分析。"

        url = f"{self.cfg.minimax_base_url.rstrip('/')}/chat/completions"
        body = {
            "model": self.cfg.minimax_model,
            "messages": [
                {"role": "system", "content": "你是专业的事件驱动交易分析助手，输出要简洁、结构化、可执行。"},
                {"role": "user", "content": f"{self.cfg.analysis_prompt}\n\nTrump Truth 原文如下：\n{status_text}"},
            ],
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self.cfg.minimax_api_key}"}
        try:
            resp = json_request(
                url,
                method="POST",
                headers=headers,
                body=body,
                timeout=max(self.cfg.request_timeout, 30),
            )
        except Exception as e:
            return f"MiniMax 调用失败: {e}"
        try:
            content = resp["choices"][0]["message"]["content"]
            if isinstance(content, str):
                text = content.strip()
                if text:
                    return text
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"].strip())
                merged = "\n".join(x for x in parts if x).strip()
                if merged:
                    return merged
        except Exception:
            pass
        return "MiniMax 分析返回为空。"

    def _push_feishu(self, text: str) -> None:
        if not self.cfg.feishu_webhook:
            self._log("未配置 FEISHU_WEBHOOK，跳过推送")
            return
        body = {"msg_type": "text", "content": {"text": text[:3900]}}
        json_request(self.cfg.feishu_webhook, method="POST", body=body, timeout=self.cfg.request_timeout)

    def process_once(self) -> None:
        statuses, source = self._fetch_statuses_dual_source()
        new_items = self._new_statuses(statuses)
        if not new_items:
            self._log("无新发言")
            return

        if self.cfg.backfill_max_send > 0 and len(new_items) > self.cfg.backfill_max_send:
            dropped = len(new_items) - self.cfg.backfill_max_send
            self._log(f"积压 {len(new_items)} 条，仅补发最近 {self.cfg.backfill_max_send} 条，跳过 {dropped} 条")
            new_items = new_items[-self.cfg.backfill_max_send :]

        for s in new_items:
            sid = str(s.get("id", ""))
            created = s.get("created_at", "")
            url = s.get("url") or f"{self.cfg.base_url}/@{self.cfg.account_handle}/{sid}"
            raw = strip_html(s.get("content", ""))
            raw_plain = strip_urls(raw)
            if not raw_plain:
                raw_plain = raw or "[原文为空或仅媒体内容]"

            self._log(f"发现新发言 id={sid} created_at={created}")
            analysis = self._analyze(raw_plain)

            message = f"时间: {created}\n原文: {raw_plain}"
            if analysis.strip():
                message = f"{message}\n\n{analysis.strip()}"
            self._push_feishu(message)

            self.state["last_status_id"] = sid
            self.state["last_created_at"] = created
            self._save_state()

    def run_forever(self) -> None:
        self._log(f"启动监控，轮询间隔 {self.cfg.poll_seconds}s")
        while True:
            try:
                self.process_once()
            except HTTPError as e:
                self._log(f"HTTPError: {e.code} {e.reason}")
            except URLError as e:
                self._log(f"URLError: {e.reason}")
            except Exception as e:
                self._log(f"异常: {e}")
            time.sleep(self.cfg.poll_seconds)


def load_config() -> Config:
    load_env_file(Path(".env"))

    prompt_path = os.getenv("ANALYSIS_PROMPT_FILE", "")
    prompt = os.getenv("ANALYSIS_PROMPT", "").strip()
    if prompt_path:
        p = Path(prompt_path)
        if p.exists():
            prompt = p.read_text(encoding="utf-8").strip()
    if not prompt:
        prompt = DEFAULT_ANALYSIS_PROMPT

    return Config(
        base_url=os.getenv("TRUTH_BASE_URL", "https://truthsocial.com").rstrip("/"),
        account_handle=os.getenv("TRUTH_ACCOUNT_HANDLE", "realDonaldTrump").lstrip("@"),
        account_id=os.getenv("TRUTH_ACCOUNT_ID") or None,
        exclude_replies=env_bool("TRUTH_EXCLUDE_REPLIES", True),
        exclude_reblogs=env_bool("TRUTH_EXCLUDE_REBLOGS", True),
        poll_seconds=int(os.getenv("POLL_SECONDS", "60")),
        state_file=Path(os.getenv("STATE_FILE", "./outputs/truthsocial_state.json")),
        feishu_webhook=os.getenv("FEISHU_WEBHOOK", ""),
        timezone=os.getenv("TIMEZONE", "Asia/Shanghai"),
        alert_on_startup=env_bool("ALERT_ON_STARTUP", False),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        analysis_model=os.getenv("ANALYSIS_MODEL", "gpt-5-mini"),
        analysis_prompt=prompt,
        request_timeout=int(os.getenv("REQUEST_TIMEOUT", "20")),
        archive_rss_url=os.getenv("ARCHIVE_RSS_URL", "https://trumpstruth.org/feed"),
        enable_archive_fallback=env_bool("ENABLE_ARCHIVE_FALLBACK", True),
        analysis_provider=os.getenv("ANALYSIS_PROVIDER", "minimax"),
        minimax_api_key=os.getenv("MINIMAX_API_KEY", ""),
        minimax_base_url=os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1"),
        minimax_model=os.getenv("MINIMAX_MODEL", "MiniMax-M2.7"),
        backfill_max_send=int(os.getenv("BACKFILL_MAX_SEND", "10")),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor Trump Truth Social and push Feishu alerts with analysis")
    parser.add_argument("--once", action="store_true", help="run one polling cycle and exit")
    args = parser.parse_args()

    cfg = load_config()
    monitor = TruthSocialMonitor(cfg)

    if args.once:
        monitor.process_once()
        return 0

    monitor.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
