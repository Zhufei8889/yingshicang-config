#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""影视仓 / TVBox 配置自动更新聚合脚本(零第三方依赖,仅用 Python 标准库)。

流程:
  1. 读取 config/sources.json 里的配置源列表;
  2. 逐个源下载(主地址 -> 备用地址依次回退);
  3. 校验并解析 JSON(自动剔除 // 注释、非法控制字符、尾部逗号);
  4. 每个源单独落盘到 output/{id}.json;
  5. 递归展开多仓订阅(urls 数组),合并所有 sites -> output/单仓聚合.json;
  6. 生成 output/多仓订阅.json、output/status.json、output/shield.json;
  7. 刷新 README 里的状态表(标记块之间)。
"""

import gzip
import json
import os
import re
import ssl
import sys
import datetime
import urllib.request
import urllib.error
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
SOURCES_FILE = os.path.join(CONFIG_DIR, "sources.json")

# GitHub 仓库信息,用于生成多仓订阅里指向本仓库 output 文件的地址。
# 在 GitHub Actions 里会通过 GITHUB_REPOSITORY 环境变量自动传入;
# 本地运行时请改成自己的 "用户名/仓库名",或设置同名环境变量。
REPO = os.environ.get("GITHUB_REPOSITORY", "yourname/yingshicang-config")
RAW_BASE = "https://raw.githubusercontent.com/{}/main/output".format(REPO)

# 简洁 UA:部分接口对完整浏览器 UA 会下发验证页
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36 TVBox/1.0",
    "Accept": "*/*",
}

TIMEOUT = 20       # 单次请求超时(秒)
MAX_DEPTH = 3      # 多仓订阅递归展开的最大深度

# 部分公开接口使用自签名证书,放宽校验以便抓取(仅用于公开配置 JSON,非敏感数据)
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


def _fix_stdout():
    """让 Windows 控制台按 UTF-8 输出,避免中文/特殊字符报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def log(msg):
    print("[{}] {}".format(datetime.datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def to_punycode(url):
    """把 URL 里的中文域名转成 punycode,避免 DNS 解析失败。"""
    try:
        p = urlparse(url)
        if p.hostname and any(ord(c) > 127 for c in p.hostname):
            host = p.hostname.encode("idna").decode("ascii")
            netloc = p.netloc.replace(p.hostname, host, 1)
            return url.replace(p.netloc, netloc, 1)
    except Exception:
        pass
    return url


def decode_bytes(data):
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def strip_comments(text):
    """剔除 // 行注释与 /* */ 块注释,不误伤字符串里的内容。"""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def clean_control_chars(text):
    """移除 JSON 字符串里非法的原始控制字符(保留 \\t \\n \\r)。"""
    return "".join(ch if ch in "\t\n\r" or ord(ch) >= 0x20 else " " for ch in text)


def remove_trailing_commas(text):
    """移除对象/数组结尾多余的逗号,如 {\"a\":1,} 或 [1,2,]。"""
    return re.sub(r",\s*([}\]])", r"\1", text)


def parse_config(text):
    """把文本解析成 dict;失败返回 None。依次尝试:原文/去注释/去尾逗号/去控制字符。"""
    if not text:
        return None
    attempts = [text]
    t = strip_comments(text)
    attempts.append(t)
    t = remove_trailing_commas(t)
    attempts.append(t)
    attempts.append(clean_control_chars(t))
    for s in attempts:
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except Exception:
            continue
    return None


def download(url):
    """下载并返回文本(自动处理 punycode 与 gzip)。"""
    url = to_punycode(url)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=SSL_CONTEXT) as resp:
        data = resp.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return decode_bytes(data)


def load_sources():
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("sources", [])


def save_output(filename, obj):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def collect_site_configs(cfg, depth=0, seen=None):
    """递归收集一个配置里的所有单仓配置(展开多仓订阅的 urls 数组)。"""
    if seen is None:
        seen = set()
    if depth > MAX_DEPTH or not isinstance(cfg, dict):
        return []
    out = []
    if cfg.get("sites"):
        out.append(cfg)
    for u in cfg.get("urls", []):
        url = u.get("url") if isinstance(u, dict) else u
        if not isinstance(url, str) or not url or url in seen:
            continue
        seen.add(url)
        try:
            sub = parse_config(download(url))
            if sub:
                out.extend(collect_site_configs(sub, depth + 1, seen))
        except Exception as e:
            log("    展开子源失败 {}: {}".format(url, e))
    return out


def merge_configs(site_configs):
    """合并多个单仓配置:内容相同的 site 去重,key 冲突但内容不同时重命名,lives/parses 去重。"""
    merged = {"sites": [], "lives": [], "parses": []}
    key_to_sig = {}
    seen_lives = set()
    seen_parses = set()
    for cfg in site_configs:
        for site in cfg.get("sites", []):
            if not isinstance(site, dict):
                continue
            key = site.get("key")
            if not key:
                continue
            sig = json.dumps(site, ensure_ascii=False, sort_keys=True)
            if key in key_to_sig:
                if key_to_sig[key] == sig:
                    continue  # 完全相同的内容,去重
                base = site.get("name") or key
                new_key = "{}_{}".format(base, key)
                n = 1
                while new_key in key_to_sig:
                    n += 1
                    new_key = "{}_{}_{}".format(base, key, n)
                site = dict(site)
                site["key"] = new_key
                key = new_key
            key_to_sig[key] = sig
            merged["sites"].append(site)
        for item in cfg.get("lives", []):
            j = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if j not in seen_lives:
                seen_lives.add(j)
                merged["lives"].append(item)
        for item in cfg.get("parses", []):
            j = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if j not in seen_parses:
                seen_parses.add(j)
                merged["parses"].append(item)
    return merged


def update_readme(results, success):
    """刷新 README 中 <!-- STATUS:START --> 与 <!-- STATUS:END --> 之间的状态表。"""
    readme = os.path.join(BASE_DIR, "README.md")
    if not os.path.exists(readme):
        return
    with open(readme, "r", encoding="utf-8") as f:
        content = f.read()

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = ["| 源 | 状态 | 使用地址 |", "| --- | --- | --- |"]
    for r in results:
        st = "✅ 成功" if r["status"] == "success" else "❌ 失败"
        used = r["used_url"] or r["url"] or "-"
        rows.append("| {} | {} | `{}` |".format(r["name"], st, used))
    table = "\n".join(rows)
    block = (
        "<!-- STATUS:START -->\n"
        "🔄 最近更新:{} · 成功 {}/{} 个源\n\n".format(now, success, len(results))
        + table
        + "\n<!-- STATUS:END -->"
    )

    start = "<!-- STATUS:START -->"
    end = "<!-- STATUS:END -->"
    if start in content and end in content:
        pattern = re.escape(start) + r".*?" + re.escape(end)
        content = re.sub(pattern, lambda m: block, content, flags=re.DOTALL)
    else:
        content += "\n\n" + block + "\n"

    with open(readme, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    _fix_stdout()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    sources = load_sources()
    log("开始更新,共 {} 个配置源".format(len(sources)))

    results = []
    individual = []   # 多仓订阅的 urls
    site_configs = []  # 用于单仓聚合

    for src in sources:
        sid = src.get("id")
        name = src.get("name", sid)
        urls = src.get("urls", [])
        ok, last_err, used_url, cfg = False, "", "", None
        for url in urls:
            try:
                cfg = parse_config(download(url))
                if cfg is None:
                    last_err = "JSON 解析失败"
                    log("  失败 {} ({}) <- {}: {}".format(name, sid, url, last_err))
                    continue
                save_output("{}.json".format(sid), cfg)
                ok, used_url = True, url
                log("  成功 {} ({}) <- {}".format(name, sid, url))
                break
            except Exception as e:
                last_err = str(e)
                log("  失败 {} 地址 {}: {}".format(name, url, e))
                continue

        results.append({
            "id": sid,
            "name": name,
            "status": "success" if ok else "failed",
            "url": urls[0] if urls else "",
            "used_url": used_url,
            "error": "" if ok else last_err,
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") if ok else None,
        })

        if ok and cfg is not None:
            individual.append({"url": "{}/{}.json".format(RAW_BASE, sid), "name": name})
            try:
                site_configs.extend(collect_site_configs(cfg))
            except Exception as e:
                log("  展开 {} 失败: {}".format(name, e))

    # 单仓聚合
    if site_configs:
        merged = merge_configs(site_configs)
        log("单仓聚合:共 {} 个站点".format(len(merged["sites"])))
    else:
        merged = {"sites": [], "lives": [], "parses": []}
    save_output("单仓聚合.json", merged)

    # 多仓订阅
    save_output("多仓订阅.json", {"urls": individual})
    log("多仓订阅:共 {} 个可用源".format(len(individual)))

    # 额外输出 ASCII 文件名的副本,避免部分设备对中文文件名的编码问题
    save_output("config.json", merged)
    save_output("multi.json", {"urls": individual})

    # 状态与徽章
    success = sum(1 for r in results if r["status"] == "success")
    status = {
        "repo": REPO,
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "success": success,
        "failed": len(results) - success,
        "sources": results,
    }
    save_output("status.json", status)
    color = "green" if success == len(results) else ("yellow" if success else "red")
    save_output("shield.json", {
        "schemaVersion": 1,
        "label": "configs",
        "message": "{}/{} ok".format(success, len(results)),
        "color": color,
    })

    update_readme(results, success)
    log("完成:成功 {}/{} 个源".format(success, len(results)))


if __name__ == "__main__":
    main()


