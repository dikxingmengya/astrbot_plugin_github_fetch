# GitHub Fetch 预览卡片 — AstrBot 插件
# 架构: GitHub REST API (httpx) → Jinja2 渲染 HTML → Playwright HTML→PNG
# 自动安装缺失依赖: pip install httpx jinja2 playwright cachetools
#                                   playwright install chromium

import asyncio, html as _html_mod, os, re, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig

# ═══════════════════════════════════════════════════════════════════════════
# 自动安装依赖
# ═══════════════════════════════════════════════════════════════════════════
_REQUIRED = [
    ("httpx",      "httpx",      False),
    ("jinja2",     "jinja2",     False),
    ("playwright", "playwright", True),
    ("cachetools", "cachetools", False),
]

def _ensure_pkg(import_name: str, pip_name: str) -> bool:
    try: __import__(import_name); return True
    except ImportError: pass
    logger.info(f"[GitHubFetch] pip install {pip_name} …")
    try:
        subprocess.check_call([sys.executable,"-m","pip","install",pip_name],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120)
        __import__(import_name); logger.info(f"[GitHubFetch] ✅ {pip_name}"); return True
    except Exception as e: logger.warning(f"[GitHubFetch] ❌ {pip_name}: {e}"); return False

def _ensure_browser() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p: p.chromium.launch(headless=True).close()
        return True
    except Exception: pass
    logger.info("[GitHubFetch] playwright install chromium (may take minutes) …")
    try:
        subprocess.check_call([sys.executable,"-m","playwright","install","chromium"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=300)
        logger.info("[GitHubFetch] ✅ Chromium"); return True
    except Exception as e: logger.warning(f"[GitHubFetch] ❌ Chromium: {e}"); return False

# 模块级状态（initialize 填充）
_httpx_ok = _jinja2_ok = _pw_ok = _ct_ok = False

# ═══════════════════════════════════════════════════════════════════════════
# 常量 — 匹配 GitHub 精确值
# ═══════════════════════════════════════════════════════════════════════════
GITHUB_PR_ISSUE_URL = r"https?://github\.com/([a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?)/([a-zA-Z0-9_.\-]+)/(pull|issues)/(\d+)"
GITHUB_REPO_URL      = r"https?://github\.com/([a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?)/([a-zA-Z0-9_.\-]+)/?\s*$"
GITHUB_ANY_URL_PATTERN = r"https?://github\.com/[a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?/[a-zA-Z0-9_.\-]+(?:/[^\s]*)?"
ISSUE_REF_PATTERN = r"(?<!\w)#(\d{1,7})\b"
MAX_URLS = 3; CLEANUP_DELAY = 120; MAX_BODY = 8000; MAX_TIMELINE = 20

# ── HTML 标签保护 ──
_SL, _SG = "\x00LT\x00", "\x00GT\x00"
_HTR = re.compile(r"<(/?)([A-Za-z]\w*)([^>]*)>")
def _p(t): return _HTR.sub(lambda m:f"{_SL}{m.group(1)}{m.group(2)}{m.group(3)}{_SG}",t)
def _r(t): return t.replace(_SL,"<").replace(_SG,">")

# ── Octicon SVG (GitHub 官方路径, 16px viewBox) ──
I_GIT_COMMIT   = '<path d="M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z"/>'
I_TAG          = '<path d="M1 7.775V2.75C1 1.784 1.784 1 2.75 1h5.025c.464 0 .91.184 1.238.513l6.25 6.25a1.75 1.75 0 0 1 0 2.474l-5.026 5.026a1.75 1.75 0 0 1-2.474 0l-6.25-6.25A1.752 1.752 0 0 1 1 7.775Zm1.5 0c0 .066.026.13.073.177l6.25 6.25a.25.25 0 0 0 .354 0l5.025-5.025a.25.25 0 0 0 0-.354l-6.25-6.25a.25.25 0 0 0-.177-.073H2.75a.25.25 0 0 0-.25.25ZM6 5a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z"/>'
I_CROSS_REF    = '<path d="M2.75 3.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h2a.75.75 0 0 1 .75.75v2.19l2.72-2.72a.749.749 0 0 1 .53-.22h4.5a.25.25 0 0 0 .25-.25v-2.5a.75.75 0 0 1 1.5 0v2.5A1.75 1.75 0 0 1 13.25 13H9.06l-2.573 2.573A1.458 1.458 0 0 1 4 14.543V13H2.75A1.75 1.75 0 0 1 1 11.25v-7.5C1 2.784 1.784 2 2.75 2h5.5a.75.75 0 0 1 0 1.5ZM16 1.25v4.146a.25.25 0 0 1-.427.177L14.03 4.03l-3.75 3.75a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734l3.75-3.75-1.543-1.543A.25.25 0 0 1 11.604 1h4.146a.25.25 0 0 1 .25.25Z"/>'
I_EYE          = '<path d="M8 2c1.981 0 3.671.992 4.933 2.078 1.27 1.091 2.187 2.345 2.637 3.023a1.62 1.62 0 0 1 0 1.798c-.45.678-1.367 1.932-2.637 3.023C11.67 13.008 9.981 14 8 14c-1.981 0-3.671-.992-4.933-2.078C1.797 10.83.88 9.576.43 8.898a1.62 1.62 0 0 1 0-1.798c.45-.677 1.367-1.931 2.637-3.022C4.33 2.992 6.019 2 8 2ZM1.679 7.932a.12.12 0 0 0 0 .136c.411.622 1.241 1.75 2.366 2.717C5.176 11.758 6.527 12.5 8 12.5c1.473 0 2.825-.742 3.955-1.715 1.124-.967 1.954-2.096 2.366-2.717a.12.12 0 0 0 0-.136c-.412-.621-1.242-1.75-2.366-2.717C10.824 4.242 9.473 3.5 8 3.5c-1.473 0-2.825.742-3.955 1.715-1.124.967-1.954 2.096-2.366 2.717ZM8 10a2 2 0 1 1-.001-3.999A2 2 0 0 1 8 10Z"/>'
I_CHECK        = '<path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"/>'
I_FORK         = '<path d="M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v.878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 1 3.5 6.25v-.878a2.25 2.25 0 1 1 1.5 0ZM5 3.25a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Zm6.75.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm-3 8.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z"/>'
I_STAR         = '<path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"/>'
I_PULL_REQ     = '<path d="M6.25 1a2.25 2.25 0 0 1 .75 4.372v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 6.25 1Zm0 1.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm2.5 5a.75.75 0 0 1 .75-.75h3.72l-1.22-1.22a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018l2.5 2.5a.75.75 0 0 1 0 1.06l-2.5 2.5a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734L13.22 9H9.5a.75.75 0 0 1-.75-.75Zm-3.5 4.75a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm7.5 0a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/>'
I_PULL_CLOSED  = '<path d="M3.25 1A2.25 2.25 0 0 1 4 5.372v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.251 2.251 0 0 1 3.25 1Zm9.5 5.5a.75.75 0 0 1 .75.75v3.378a2.251 2.251 0 1 1-1.5 0V7.25a.75.75 0 0 1 .75-.75Zm-2.03-5.273a.75.75 0 0 1 1.06 0l.97.97.97-.97a.748.748 0 0 1 1.265.332.75.75 0 0 1-.205.729l-.97.97.97.97a.751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018l-.97-.97-.97.97a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734l.97-.97-.97-.97a.75.75 0 0 1 0-1.06ZM2.5 3.25a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0ZM3.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm9.5 0a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/>'
I_GIT_MERGE    = '<path d="M8 2a.75.75 0 0 1 .696.471L11 8.226v3.402a2.251 2.251 0 1 1-1.5 0V8.774l-1.745-4.51a2.5 2.5 0 1 1 1.508-.147L11 8.226l1.514-3.45a2.5 2.5 0 1 1 1.425.244L10.944 9.902a.75.75 0 0 1-.944.374.75.75 0 0 1-.444-.69V8.774L7.486 4.106A.75.75 0 0 1 8 2ZM5 2.5a1 1 0 1 0 0 2 1 1 0 0 0 0-2Zm7 0a1 1 0 1 0 0 2 1 1 0 0 0 0-2Zm-7 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm7 0a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/>'
I_REPO_PUSH    = '<path d="M1.5 2.75a.25.25 0 0 1 .25-.25h12.5a.25.25 0 0 1 .25.25v3a.75.75 0 0 0 1.5 0v-3A1.75 1.75 0 0 0 14.25 1H1.75A1.75 1.75 0 0 0 0 2.75v7.5C0 11.216.784 12 1.75 12H5v1.543a1.458 1.458 0 0 0 2.487 1.03L10.06 12h4.19A1.75 1.75 0 0 0 16 10.25v-3.5a.75.75 0 0 0-1.5 0v3.5a.25.25 0 0 1-.25.25h-4.5a.75.75 0 0 0-.53.22L6.5 13.44v-2.19a.75.75 0 0 0-.75-.75H1.75a.25.25 0 0 1-.25-.25v-7.5Z"/>'

# ═══════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════
def _pts(ts): return datetime.fromisoformat(ts.replace("Z","+00:00"))
def _rt(dt):
    """GitHub 风格相对时间: just now / 5m ago / 3h ago / 2d ago / on Jun 15 / on Jun 15, 2025"""
    now=datetime.now(timezone.utc)
    s=(now-dt).total_seconds()
    if s<60: return "just now"
    if s<3600: return f"{int(s/60)}m ago"
    if s<86400: return f"{int(s/3600)}h ago"
    if s<604800: return f"{int(s/86400)}d ago"
    # 超过一周: GitHub 风格 "on Jun 15" 或 "on Jun 15, 2025"
    if dt.year==now.year:
        return f"on {dt.strftime('%b %d')}"
    return f"on {dt.strftime('%b %d, %Y')}"
def _tc(c):
    try: r,g,b=int(c[0:2],16),int(c[2:4],16),int(c[4:6],16)
    except: return "#fff"
    return "#fff" if (0.299*r+0.587*g+0.114*b)/255<0.5 else "#333"
def _fc(n): return f"{n/1000:.1f}k" if n>=1000 else str(n)
def _pu(url):
    m=re.search(GITHUB_PR_ISSUE_URL,url)
    return (m.group(1),m.group(2),int(m.group(4))) if m else None

def _parse_repo(url):
    m=re.match(GITHUB_REPO_URL,url.strip())
    return (m.group(1),m.group(2)) if m else None

# ── 增强 Markdown → HTML（支持 table / task-list / 嵌套列表 / details） ──
def _md2html(text):
    if not text: return ""
    if len(text)>MAX_BODY: text=text[:MAX_BODY]+"\n\n> ⚠️ *truncated…*"
    L=text.split("\n"); O=[]; cb=False; cbl=""; cblines=[]; il=None; li=[]
    def _fl():
        nonlocal il,li
        if il and li: O.append(f"<{il}>"); [O.append(f"<li>{_pi(x)}</li>") for x in li]; O.append(f"</{il}>"); li=[]; il=None
    def _pi(t):
        ss=[]
        def _s(m): ss.append(m.group(1)); return f"\x00ICODE{len(ss)-1}\x00"
        t=re.sub(r"`([^`]+?)`",_s,t)
        t=_p(t); t=_html_mod.escape(t); t=_r(t)
        for i,s in enumerate(ss): t=t.replace(f"\x00ICODE{i}\x00",f"<code>{_html_mod.escape(s)}</code>")
        # task-list checkbox
        t=re.sub(r'^\[ \] ', '<input type="checkbox" disabled style="margin-right:6px">', t)
        t=re.sub(r'^\[x\] ', '<input type="checkbox" disabled checked style="margin-right:6px">', t)
        t=re.sub(r'!\[([^\]]*)\]\(([^)\s]+(?:\s+"[^"]*")?)\)', r'<img src="\2" alt="\1" style="max-width:100%;border-radius:4px">', t)
        t=re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'<a href="\2">\1</a>', t)
        t=re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
        t=re.sub(r'\*(.+?)\*', r'<em>\1</em>', t)
        t=re.sub(r'~~(.+?)~~', r'<del>\1</del>', t)
        return t
    # parse markdown table rows
    in_table=False; table_rows=[]
    def _flush_table():
        nonlocal in_table,table_rows
        if not table_rows: return
        html='<table>'
        for ri,row in enumerate(table_rows):
            cells=[c.strip() for c in row.split("|")[1:-1]]
            tag="th" if ri==0 else "td"
            html+="<tr>"+"".join(f"<{tag}>{_pi(c)}</{tag}>" for c in cells)+"</tr>"
        html+="</table>"; O.append(html); table_rows=[]
    i=0
    while i<len(L):
        ln=L[i]
        # code fence
        if ln.strip().startswith("```"):
            if not cb: _fl(); _flush_table(); cb=True; cbl=ln.strip()[3:].strip(); cblines=[]
            else:
                la=f' class="language-{cbl}"' if cbl else ""
                O.append(f"<pre><code{la}>{_html_mod.escape(chr(10).join(cblines))}</code></pre>")
                cb=False; cblines=[]
            i+=1; continue
        if cb: cblines.append(ln); i+=1; continue
        # table row detection
        if ln.strip().startswith("|") and ln.strip().endswith("|"):
            if "---" in ln and "|" in ln:  # separator row
                table_rows.append(ln); i+=1; continue
            if not in_table: _fl(); in_table=True
            table_rows.append(ln)
            i+=1; continue
        elif in_table: _flush_table(); in_table=False
        # blank line
        if not ln.strip(): _fl(); _flush_table(); i+=1; continue
        # heading
        hm=re.match(r"^(#{1,4})\s+(.+)$",ln)
        if hm: _fl(); O.append(f"<h{len(hm.group(1))}>{_pi(hm.group(2))}</h{len(hm.group(1))}>"); i+=1; continue
        # hr
        if re.match(r"^[-*_]{3,}\s*$",ln.strip()): _fl(); O.append("<hr>"); i+=1; continue
        # blockquote
        if ln.startswith("> "): _fl(); O.append(f"<blockquote>{_pi(ln[2:])}</blockquote>"); i+=1; continue
        # nested list — count leading spaces
        um=re.match(r"^(\s*)[-*+]\s+(.+)$",ln)
        if um:
            indent=len(um.group(1))
            if il!="ul" or indent>0: _fl(); il="ul"
            prefix="  "*(indent//2) if indent>0 else ""
            li.append(prefix+um.group(2)); i+=1; continue
        om=re.match(r"^(\s*)\d+\.\s+(.+)$",ln)
        if om:
            if il!="ol": _fl(); il="ol"
            li.append(om.group(2)); i+=1; continue
        _fl(); O.append(f"<p>{_pi(ln)}</p>"); i+=1
    _fl(); _flush_table()
    if cb and cblines: O.append(f"<pre><code>{_html_mod.escape(chr(10).join(cblines))}</code></pre>")
    return "\n".join(O)

# ═══════════════════════════════════════════════════════════════════════════
# TTL 缓存
# ═══════════════════════════════════════════════════════════════════════════
class _TC:
    def __init__(s,ms=256,ttl=300): s._c={}; s._m=ms; s._ttl=ttl
    def _ev(s):
        n=time.time()
        for k in [k for k,(_,ts) in s._c.items() if n-ts>s._ttl]: del s._c[k]
    def __getitem__(s,k):
        s._ev(); v,ts=s._c[k]
        if time.time()-ts>s._ttl: del s._c[k]; raise KeyError(k)
        return v
    def __setitem__(s,k,v):
        s._ev()
        while len(s._c)>=s._m and s._c: del s._c[min(s._c.items(),key=lambda x:x[1][1])[0]]
        s._c[k]=(v,time.time())
    def get(s,k):
        try: return s[k]
        except KeyError: return None
    def clear(s): s._c.clear()

# ═══════════════════════════════════════════════════════════════════════════
# Jinja2 模板 — 严格模仿 GitHub TimelineItem 结构
# ═══════════════════════════════════════════════════════════════════════════
_T = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=800">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;font-size:14px;line-height:1.5;color:{{tc}};background:{{bg}};padding:16px;width:800px;-webkit-font-smoothing:antialiased}
  a{color:{{lk}};text-decoration:none}a:hover{text-decoration:underline}

  .repo-bar{display:flex;align-items:center;gap:10px;background:{{cbg}};border:1px solid {{bc}};border-radius:6px 6px 0 0;padding:12px 20px}
  .repo-bar svg.rb-icon{width:16px;height:16px;flex-shrink:0;fill:{{mu}}}
  .repo-bar .rb-name{font-weight:600;font-size:14px;color:{{lk}};flex:1}
  .repo-bar .rb-stat{display:flex;align-items:center;gap:4px;font-size:12px;color:{{mu}}}
  .repo-bar .rb-stat svg{width:14px;height:14px;fill:{{mu}}}

  .card{background:{{cbg}};border:1px solid {{bc}};border-top:none;border-radius:0 0 6px 6px;padding:20px 24px 16px}
  .card.no-repo{border-radius:6px;border-top:1px solid {{bc}}}

  /* header */
  .State{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:2em;font-size:12px;font-weight:600;line-height:20px;color:#fff}
  .State svg{width:14px;height:14px;fill:#fff}
  .State--open{background:#3fb950}.State--closed{background:#f85149}.State--merged{background:#a371f7}
  .header{margin-bottom:16px}
  .header-row{display:flex;align-items:center;gap:8px;margin-bottom:8px}
  .pr-num{color:{{mu}};font-size:14px}
  .title{font-size:22px;font-weight:600;line-height:1.35;word-wrap:break-word}
  .title a{color:{{tc}}}

  /* body markdown */
  .body{font-size:15px;line-height:1.6;margin:16px 0;padding-top:16px;border-top:1px solid {{bc}};word-wrap:break-word;overflow-wrap:break-word}
  .body>:first-child{margin-top:0}
  .body h1,.body h2,.body h3,.body h4{margin:20px 0 8px;font-weight:600}
  .body h1{font-size:1.5em;padding-bottom:7px;border-bottom:1px solid {{bc}}}
  .body h2{font-size:1.35em;padding-bottom:5px;border-bottom:1px solid {{bc}}}
  .body h3{font-size:1.15em}.body h4{font-size:1em}
  .body p{margin:0 0 10px}.body p:last-child{margin-bottom:0}
  .body ul,.body ol{padding-left:24px;margin:0 0 10px}
  .body li{margin:2px 0}
  .body ul ul,.body ol ol,.body ul ol,.body ol ul{margin:4px 0 4px 0}
  .body code{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;background:{{cbg2}};padding:2px 5px;border-radius:4px;font-size:.85em;color:{{ico}}}
  .body pre{background:{{cbg2}};border-radius:6px;padding:14px;overflow-x:auto;margin:0 0 10px;line-height:1.5}
  .body pre code{background:none;padding:0;color:{{tc}};font-size:.82em}
  .body blockquote{border-left:3px solid {{st}};padding:2px 14px;margin:0 0 10px;color:{{mu}}}
  .body img{max-width:100%;height:auto;border-radius:4px;margin:6px 0}
  .body hr{border:none;border-top:1px solid {{bc}};margin:20px 0}
  .body details{border:1px solid {{bc}};border-radius:6px;padding:10px 16px;margin:8px 0}
  .body details[open]>summary{margin-bottom:8px}
  .body summary{font-weight:600;cursor:pointer;color:{{lk}}}
  /* markdown table */
  .body table{border-collapse:collapse;width:100%;margin:10px 0;font-size:.92em;display:block;overflow-x:auto;max-width:100%}
  .body th,.body td{border:1px solid {{bc}};padding:8px 12px;text-align:left;word-break:break-word;white-space:normal}
  .body th{background:{{cbg2}};font-weight:600}
  .body tr:nth-child(even){background:{{cbg2}}33}
  .body input[type=checkbox]{vertical-align:middle;accent-color:{{lk}}}
  .body kbd{display:inline-block;padding:1px 5px;font:11px ui-monospace,monospace;border:1px solid {{bc}};border-radius:3px;background:{{cbg2}};box-shadow:inset 0 -1px 0 {{bc}}}

  /* ── Timeline ── */
  .tl-section{margin:20px 0;padding-top:16px;border-top:1px solid {{bc}}}
  .tl-hdr{font-size:13px;font-weight:600;color:{{mu}};margin-bottom:12px;display:flex;align-items:center;gap:6px}
  .tl-hdr svg{fill:{{mu}};width:16px;height:16px}

  .TimelineItem{position:relative;display:flex;gap:12px;padding:0 0 12px 0}
  .TimelineItem:last-child{padding-bottom:0}
  .TimelineItem::before{content:'';position:absolute;left:14px;top:28px;bottom:0;width:2px;background:{{bc}}}
  .TimelineItem:last-child::before{display:none}
  .TimelineItem--condensed{padding:0 0 4px 0}
  .TimelineItem--condensed .TimelineItem-badge{padding:0}

  .TimelineItem-badge{position:relative;z-index:1;width:30px;height:30px;flex-shrink:0;display:flex;align-items:center;justify-content:center}
  .TimelineItem-badge svg{width:16px;height:16px;fill:{{mu}}}
  .TimelineItem--condensed .TimelineItem-badge svg{width:12px;height:12px}

  .TimelineItem-body{flex:1;min-width:0;padding-top:4px}
  .TimelineItem--condensed .TimelineItem-body{padding-top:6px}

  /* commit row */
  .tl-cmt{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
  .tl-avatar-stack{display:flex;flex-shrink:0;margin-right:2px}
  .tl-avatar-stack img{width:20px;height:20px;border-radius:50%;object-fit:cover;border:2px solid {{cbg}};margin-right:-6px}
  .tl-avatar-stack img:last-child{margin-right:0}
  .tl-cmt-msg{font-family:ui-monospace,SFMono-Regular,monospace;font-size:13px;min-width:0;flex:1}
  .tl-cmt-msg a{color:{{tc}};font-weight:600}
  .tl-cmt-sha{font-family:ui-monospace,SFMono-Regular,monospace;font-size:11px;flex-shrink:0;margin-left:auto}
  .tl-cmt-sha a{color:{{mu}}}
  /* label row */
  .tl-lbl{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:13px;line-height:20px}
  .tl-lbl-tag{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;line-height:18px}
  /* cross-ref card */
  .tl-xref{margin-top:6px;background:{{cbg2}};border:1px solid {{bc}};border-radius:6px;padding:10px 14px;display:flex;align-items:center;gap:10px}
  .tl-xref .tl-xref-title{font-size:14px;font-weight:600;flex:1;min-width:0}
  .tl-xref .tl-xref-title a{color:{{tc}}}
  .tl-xref .tl-xref-num{color:{{mu}};font-weight:400}
  /* state badge */
  .State--sm{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:2em;font-size:11px;font-weight:600;flex-shrink:0}
  .State--sm svg{width:14px;height:14px}
  /* review box */
  .tl-review{margin-top:6px;background:{{cbg2}};border:1px solid {{bc}};border-radius:8px;padding:14px 18px}
  .tl-review-body{font-size:14px;line-height:1.55;color:{{tc}}}
  .tl-review-body p{margin:0 0 6px}.tl-review-body p:last-child{margin-bottom:0}
  /* badges */
  .Label-bot{display:inline-block;padding:0 6px;border-radius:2em;font-size:10px;font-weight:600;color:{{mu}};border:1px solid {{bc}};line-height:18px;margin-left:3px}
  .tl-time{color:{{mu}};font-size:12px;white-space:nowrap}
  .actor{font-weight:600;color:{{tc}}}

  /* footer */
  .footer{display:flex;align-items:center;gap:10px;margin-top:16px;padding-top:14px;border-top:1px solid {{bc}};flex-wrap:wrap}
  .footer-l{display:flex;align-items:center;gap:8px}
  .ft-avatar{width:26px;height:26px;border-radius:50%;object-fit:cover;flex-shrink:0}
  .ft-name{font-weight:600;font-size:14px}.ft-time{color:{{mu}};font-size:12px}
  .ft-labels{display:flex;gap:5px;flex-wrap:wrap;margin-left:auto}
  .ft-label{display:inline-block;padding:2px 8px;border-radius:2em;font-size:11px;font-weight:600;line-height:18px}
</style></head>
<body>
{% if repo %}
<div class="repo-bar">
  <svg class="rb-icon" viewBox="0 0 16 16">{{I_FORK}}</svg>
  <a class="rb-name" href="https://github.com/{{repo.fn}}">{{repo.fn}}</a>
  <span class="rb-stat"><svg viewBox="0 0 16 16">{{I_STAR}}</svg> {{repo.st}}</span>
  <span class="rb-stat"><svg viewBox="0 0 16 16">{{I_FORK}}</svg> {{repo.fk}}</span>
</div>
{% endif %}
<div class="card{% if not repo %} no-repo{% endif %}">
  <div class="header">
    <div class="header-row">
      <span class="State {{st_class}}"><svg viewBox="0 0 16 16">{{st_svg}}</svg> {{st_text}}</span>
      <span class="pr-num">#{{num}}</span>
    </div>
    <div class="title"><a href="{{url}}">{{title}}</a></div>
  </div>
  {% if body %}<div class="body">{{body|safe}}</div>{% endif %}

  {% if timeline %}
  <div class="tl-section">
    <div class="tl-hdr"><svg viewBox="0 0 16 16"><path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM1.5 8a6.5 6.5 0 0 1 7.25-6.46.75.75 0 0 0 .25 1.48A5.001 5.001 0 0 0 3 8c0 2.76 2.24 5 5 5a4.998 4.998 0 0 0 4.9-4 .75.75 0 0 1 1.48.2A6.501 6.501 0 0 1 1.5 8Zm1.78-2.22a.75.75 0 0 1 1.06 0L7.5 8.94l2.97-2.97a.75.75 0 0 1 1.06 1.06L8.22 10.28a.75.75 0 0 1-1.06 0l-3.5-3.5a.75.75 0 0 1 0-1.06Z"/></svg> Timeline</div>
    {% for it in timeline %}
    <div class="TimelineItem{% if it._type=='commit' %} TimelineItem--condensed{% endif %}">
      <div class="TimelineItem-badge">
        {% if it._badge == 'commit' %}<svg viewBox="0 0 16 16">{{I_GIT_COMMIT}}</svg>
        {% elif it._badge == 'tag' %}<svg viewBox="0 0 16 16">{{I_TAG}}</svg>
        {% elif it._badge == 'xref' %}<svg viewBox="0 0 16 16">{{I_CROSS_REF}}</svg>
        {% elif it._badge == 'eye' %}<svg viewBox="0 0 16 16">{{I_EYE}}</svg>
        {% elif it._badge == 'check' %}<svg viewBox="0 0 16 16">{{I_CHECK}}</svg>
        {% elif it._badge == 'push' %}<svg viewBox="0 0 16 16">{{I_REPO_PUSH}}</svg>
        {% elif it._badge == 'closed_badge' %}<span style="width:30px;height:30px;border-radius:50%;background:#f85149;display:flex;align-items:center;justify-content:center"><svg viewBox="0 0 16 16" style="fill:#fff;width:14px;height:14px">{{I_PULL_CLOSED}}</svg></span>
        {% elif it._badge == 'merged_badge' %}<span style="width:30px;height:30px;border-radius:50%;background:#a371f7;display:flex;align-items:center;justify-content:center"><svg viewBox="0 0 16 16" style="fill:#fff;width:14px;height:14px">{{I_GIT_MERGE}}</svg></span>
        {% else %}<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="3" fill="{{mu}}"/></svg>{% endif %}
      </div>
      <div class="TimelineItem-body">
        {% if it._type == 'commit' %}
          <div class="tl-cmt">
            {% if it.avatar %}<div class="tl-avatar-stack"><img src="{{it.avatar}}" alt="" width="20" height="20"></div>{% endif %}
            <span class="tl-cmt-msg"><a href="{{it.cmt_url or '#'}}">{{it.msg or it.sha}}</a></span>
            <span class="tl-cmt-sha"><a href="{{it.cmt_url or '#'}}">{{it.sha}}</a></span>
          </div>
        {% elif it._type == 'label' %}
          <div class="tl-lbl">
            {% if it.avatar %}<img src="{{it.avatar}}" width="20" height="20" style="border-radius:50%;object-fit:cover">{% endif %}
            <span class="actor">{{it.actor}}</span>
            {% if it.is_bot %}<span class="Label-bot">Bot</span>{% endif %}
            <span style="color:{{mu}}">{{it.action}}</span>
            {% for lb in it.lbs %}
              <span class="tl-lbl-tag" style="background:#{{lb.color}}33;color:#{{lb.color}};border:1px solid #{{lb.color}}55">{{lb.name}}</span>
            {% endfor %}
            <span style="color:{{mu}}">labels</span>
            <span class="tl-time">{{it.time}}</span>
          </div>
        {% elif it._type == 'reference' %}
          <div style="font-size:13px;line-height:20px">
            {% if it.avatar %}<img src="{{it.avatar}}" width="20" height="20" style="border-radius:50%;object-fit:cover;vertical-align:middle;margin-right:4px">{% endif %}
            <span class="actor">{{it.actor}}</span> <span style="color:{{mu}}">{{it.action}}</span>
            <span class="tl-time" style="margin-left:4px">{{it.time}}</span>
          </div>
          {% if it.rf_title %}
          <div class="tl-xref">
            <span class="tl-xref-title"><a href="{{it.rf_url or '#'}}">{{it.rf_title}}</a> <span class="tl-xref-num">#{{it.rf_num}}</span></span>
            {% if it.rf_state %}
            <span class="State--sm" style="{% if it.rf_state=='closed' %}background:#f8514933;color:#f85149{% elif it.rf_state=='open' %}background:#3fb95033;color:#3fb950{% elif it.rf_state=='merged' %}background:#a371f733;color:#a371f7{% else %}background:{{cbg2}};color:{{mu}}{% endif %}">
              <svg viewBox="0 0 16 16" fill="currentColor">{{I_PULL_CLOSED}}</svg> {{it.rf_state|capitalize}}
            </span>
            {% endif %}
          </div>
          {% endif %}
        {% elif it._type == 'review' %}
          <div style="font-size:13px;line-height:20px">
            {% if it.avatar %}<img src="{{it.avatar}}" width="20" height="20" style="border-radius:50%;object-fit:cover;vertical-align:middle;margin-right:4px">{% endif %}
            <span class="actor">{{it.actor}}</span>
            {% if it.is_bot %}<span class="Label-bot">Bot</span>{% endif %}
            <span style="color:{{mu}}">{{it.action}}</span>
            <span class="tl-time" style="margin-left:4px">{{it.time}}</span>
          </div>
          {% if it.rv_body %}<div class="tl-review"><div class="tl-review-body">{{it.rv_body|safe}}</div></div>{% endif %}
        {% else %}
          <div style="font-size:13px;line-height:20px">
            {% if it.avatar %}<img src="{{it.avatar}}" width="20" height="20" style="border-radius:50%;object-fit:cover;vertical-align:middle;margin-right:4px">{% endif %}
            <span class="actor">{{it.actor}}</span> <span style="color:{{mu}}">{{it.action}}</span>
            {% if it.msg %}<span class="tl-cmt-sha" style="margin-left:4px">{{it.msg}}</span>{% endif %}
            <span class="tl-time" style="margin-left:4px">{{it.time}}</span>
          </div>
        {% endif %}
      </div>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <div class="footer">
    <div class="footer-l">
      <img class="ft-avatar" src="{{av}}" alt="" width="26" height="26">
      <div><span class="ft-name">{{author}}</span><br><span class="ft-time">created {{ca}}</span></div>
    </div>
    {% if labels %}
    <div class="ft-labels">{% for lb in labels %}<span class="ft-label" style="background:#{{lb.color}};color:{{lb.tc}}">{{lb.name}}</span>{% endfor %}</div>
    {% endif %}
  </div>
</div>
</body></html>"""

_REPO_T = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=800">
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;font-size:14px;line-height:1.5;color:{{tc}};background:{{bg}};padding:0;width:800px;-webkit-font-smoothing:antialiased}
  a{color:{{lk}};text-decoration:none}a:hover{text-decoration:underline}

  /* header bar — GitHub 风格: owner / repo-name  +  Public badge */
  .gh-header{background:{{cbg}};border-bottom:1px solid {{bc}};padding:12px 24px;display:flex;align-items:center;gap:8px}
  .gh-header .owner{font-size:14px;color:{{mu}}}
  .gh-header .sep{color:{{mu}};font-size:14px}
  .gh-header .repo{font-size:18px;font-weight:600;color:{{lk}}}
  .gh-badge{font-size:10px;font-weight:600;color:{{mu}};border:1px solid {{bc}};border-radius:2em;padding:1px 8px;line-height:16px;margin-left:4px}

  /* action bar — star/fork 按钮行 */
  .action-bar{background:{{cbg}};border-bottom:1px solid {{bc}};padding:8px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  .act-btn{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border:1px solid {{bc}};border-radius:6px;font-size:11px;font-weight:600;color:{{tc}};background:{{cbg2}};cursor:default;line-height:18px}
  .act-btn svg{width:14px;height:14px;fill:{{mu}}}
  .act-count{background:{{cbg}};margin-left:-5px;border-radius:0 6px 6px 0}

  /* tab bar */
  .tab-bar{background:{{cbg}};border-bottom:1px solid {{bc}};padding:0 24px;display:flex;gap:0}
  .tab{font-size:13px;color:{{mu}};padding:8px 14px;cursor:default;border-bottom:2px solid transparent}
  .tab.active{color:{{tc}};font-weight:600;border-bottom-color:#f78166}
  .tab .count{font-size:11px;background:{{bc}};border-radius:2em;padding:0 6px;margin-left:4px;color:{{tc}};font-weight:400}

  /* main: 文件列表 + README */
  .main-body{padding:0 24px 16px}

  /* branch selector row */
  .branch-bar{display:flex;align-items:center;gap:8px;padding:12px 0;font-size:13px}
  .branch-btn{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border:1px solid {{bc}};border-radius:6px;font-size:12px;color:{{tc}};background:{{cbg2}};cursor:default}
  .branch-btn svg{width:12px;height:12px;fill:{{mu}}}

  /* file table — 严格匹配 GitHub table 样式 */
  .file-table{background:{{cbg}};border:1px solid {{bc}};border-radius:6px;overflow:hidden;margin-bottom:16px}
  .file-row{display:flex;align-items:center;gap:8px;padding:6px 12px;border-bottom:1px solid {{bc}};font-size:13px}
  .file-row:last-child{border-bottom:none}
  .file-row:nth-child(even){background:{{bc}}11}
  .file-icon{width:16px;text-align:center;flex-shrink:0;font-size:12px}
  .file-icon svg{width:14px;height:14px;fill:{{mu}}}
  .file-name{flex:1;min-width:0;word-break:break-word;color:{{tc}};font-weight:600}
  .file-name a{color:{{tc}}}
  .file-msg{color:{{mu}};font-size:11px;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:none}
  .file-time{color:{{mu}};font-size:11px;white-space:nowrap}

  /* about sidebar */
  .about-box{background:{{cbg}};border:1px solid {{bc}};border-radius:6px;padding:14px 16px;margin-bottom:12px}
  .about-title{font-size:13px;font-weight:600;margin-bottom:8px;color:{{tc}}}
  .about-desc{font-size:13px;color:{{tc}};line-height:1.5;margin-bottom:8px}
  .about-topics{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
  .about-topic{display:inline-block;padding:2px 8px;border-radius:2em;font-size:11px;font-weight:500;color:{{lk}};background:{{lk}}1a}
  .about-stat{display:flex;align-items:center;gap:4px;font-size:12px;color:{{tc}};padding:2px 0}
  .about-stat svg{width:14px;height:14px;fill:{{mu}}

  /* languages bar */
  .lang-bar-wrap{margin-bottom:12px}
  .lang-bar{display:flex;border-radius:4px;overflow:hidden;height:8px;margin-bottom:8px}
  .lang-list{font-size:11px}
  .lang-item{display:flex;align-items:center;gap:4px;margin-bottom:2px}
  .lang-dot{width:8px;height:8px;border-radius:2px;flex-shrink:0}
  .lang-name{color:{{tc}}}.lang-pct{color:{{mu}};margin-left:auto}

  /* contributors */
  .contrib-row{display:flex;align-items:center;gap:6px;padding:3px 0;font-size:12px}
  .contrib-avatar{width:20px;height:20px;border-radius:50%;object-fit:cover}
  .contrib-name{color:{{tc}};font-weight:600;flex:1}
  .contrib-commits{color:{{mu}};font-size:11px}

  /* releases */
  .rel-item{padding:3px 0;font-size:12px;display:flex;align-items:center;gap:6px}
  .rel-tag{font-family:ui-monospace,monospace;font-size:11px;color:{{lk}};font-weight:600}
  .rel-latest{font-size:9px;color:#fff;background:#3fb950;padding:0 4px;border-radius:2em}
  .rel-date{color:{{mu}};margin-left:auto;font-size:11px}

  /* README */
  .readme-box{background:{{cbg}};border:1px solid {{bc}};border-radius:6px;padding:24px 28px;margin-bottom:12px}
  .readme-title{font-size:14px;font-weight:600;color:{{tc}};margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid {{bc}}}
  .readme-body{font-size:14px;line-height:1.6;color:{{tc}}}
  .readme-body h1,.readme-body h2,.readme-body h3{margin:16px 0 8px;font-weight:600}
  .readme-body h1{font-size:1.5em;padding-bottom:6px;border-bottom:1px solid {{bc}}}
  .readme-body h2{font-size:1.3em;padding-bottom:4px;border-bottom:1px solid {{bc}}}
  .readme-body p{margin:0 0 10px}.readme-body code{font-family:ui-monospace,monospace;background:{{cbg2}};padding:2px 5px;border-radius:3px;font-size:.85em;color:{{ico}}}
  .readme-body pre{background:{{cbg2}};border-radius:4px;padding:12px;overflow-x:auto;font-size:.85em;margin:0 0 10px}
  .readme-body table{border-collapse:collapse;width:100%;margin:8px 0;display:block;overflow-x:auto;max-width:100%}
  .readme-body td,.readme-body th{border:1px solid {{bc}};padding:6px 10px;text-align:left;word-break:break-word}
  .readme-body th{background:{{cbg2}};font-weight:600}
  .readme-body img{max-width:100%}
  .readme-body ul,.readme-body ol{padding-left:20px;margin:0 0 10px}
</style></head>
<body>
<!-- header -->
<div class="gh-header">
  <svg width="20" height="20" viewBox="0 0 16 16" fill="{{mu}}">{{I_FORK}}</svg>
  <span class="owner"><a href="https://github.com/{{name.split('/')[0]}}" style="color:{{mu}}">{{name.split('/')[0]}}</a></span>
  <span class="sep">/</span>
  <a class="repo" href="{{url}}">{{name.split('/')[1]}}</a>
  <span class="gh-badge">Public</span>
</div>

<!-- action bar -->
<div class="action-bar">
  <span class="act-btn"><svg viewBox="0 0 16 16">{{I_STAR}}</svg> Star</span><span class="act-btn act-count">{{stars}}</span>
  <span class="act-btn"><svg viewBox="0 0 16 16">{{I_FORK}}</svg> Fork</span><span class="act-btn act-count">{{forks}}</span>
  <span style="font-size:12px;color:{{mu}};margin-left:4px">{{watchers}} watching · {{issues}} issues</span>
</div>

<!-- tab bar -->
<div class="tab-bar">
  <span class="tab active">Code</span>
  <span class="tab">Issues{% if issues %}<span class="count">{{issues}}</span>{% endif %}</span>
  <span class="tab">Pull requests</span>
  <span class="tab">Actions</span>
</div>

<div class="main-body">
<!-- branch selector + file count -->
{% if files %}
<div class="branch-bar">
  <span class="branch-btn"><svg viewBox="0 0 16 16"><path d="M9.5 3.25a2.25 2.25 0 1 1 3 2.122V6A2.5 2.5 0 0 1 10 8.5H6a1 1 0 0 0-1 1v1.128a2.251 2.251 0 1 1-1.5 0V9.5A2.5 2.5 0 0 1 6 7h4a1 1 0 0 0 1-1v-.628A2.25 2.25 0 0 1 9.5 3.25Zm-6 0a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Zm8.25-.75a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5ZM4.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/></svg> {{branch}}</span>
  <span style="font-size:12px;color:{{mu}}">{{files|length}} files</span>
</div>

<div class="file-table">
{% for f in files %}
<div class="file-row">
  <span class="file-icon">{% if f.type=='dir' %}<svg viewBox="0 0 16 16"><path d="M1.75 1A1.75 1.75 0 0 0 0 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0 0 16 13.25v-8.5A1.75 1.75 0 0 0 14.25 3H7.5a.25.25 0 0 1-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1H1.75Z"/></svg>{% else %}<svg viewBox="0 0 16 16"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16H3.75A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"/></svg>{% endif %}</span>
  <span class="file-name">{% if f.type=='dir' %}<a href="#">{{f.name}}</a>{% else %}{{f.name}}{% endif %}</span>
  <span class="file-time">{% if f.type=='file' and f.size>0 %}{% if f.size>1024 %}{{ (f.size/1024)|round|int }} KB{% else %}{{f.size}} B{% endif %}{% endif %}</span>
</div>
{% endfor %}
</div>
{% endif %}

<!-- README -->
{% if readme %}
<div class="readme-box">
  <div class="readme-title">📄 README.md</div>
  <div class="readme-body">{{readme|safe}}</div>
</div>
{% endif %}
</div>

<!-- sidebar sections -->
<div style="padding:0 24px 16px;display:flex;gap:12px;flex-wrap:wrap">
  <!-- About -->
  <div class="about-box" style="flex:1;min-width:200px">
    <div class="about-title">About</div>
    {% if desc %}<div class="about-desc">{{desc}}</div>{% endif %}
    {% if topics %}<div class="about-topics">{% for t in topics %}<span class="about-topic">{{t}}</span>{% endfor %}</div>{% endif %}
    <div class="about-stat"><svg viewBox="0 0 16 16">{{I_STAR}}</svg> <strong>{{stars}}</strong> stars</div>
    <div class="about-stat"><svg viewBox="0 0 16 16">{{I_FORK}}</svg> <strong>{{forks}}</strong> forks</div>
    <div class="about-stat"><span style="width:14px;text-align:center">👁</span> <strong>{{watchers}}</strong> watching</div>
  </div>

  <!-- Languages -->
  {% if langs %}
  <div class="about-box" style="flex:1;min-width:200px">
    <div class="about-title">Languages</div>
    <div class="lang-bar">{% for l in langs %}<div style="width:{{l.pct}}%;height:8px;background:hsl({{(loop.index0*60+200)%360}},60%,55%)"></div>{% endfor %}</div>
    <div class="lang-list">{% for l in langs %}<div class="lang-item"><span class="lang-dot" style="background:hsl({{(loop.index0*60+200)%360}},60%,55%)"></span><span class="lang-name">{{l.name}}</span><span class="lang-pct">{{l.pct}}%</span></div>{% endfor %}</div>
  </div>
  {% endif %}

  <!-- Releases -->
  {% if rels %}
  <div class="about-box" style="flex:1;min-width:150px">
    <div class="about-title">Releases</div>
    {% for r in rels %}<div class="rel-item"><span class="rel-tag">{{r.tag}}</span>{% if loop.first and not r.prerelease %}<span class="rel-latest">Latest</span>{% endif %}<span class="rel-date">{{r.date}}</span></div>{% endfor %}
  </div>
  {% endif %}

  <!-- Contributors -->
  {% if contribs %}
  <div class="about-box" style="flex:1;min-width:150px">
    <div class="about-title">Contributors</div>
    {% for c in contribs %}<div class="contrib-row"><img class="contrib-avatar" src="{{c.avatar}}" alt="" width="20" height="20"><span class="contrib-name">{{c.login}}</span><span class="contrib-commits">{{c.commits}}</span></div>{% endfor %}
  </div>
  {% endif %}
</div>
</body></html>"""

# ═══════════════════════════════════════════════════════════════════════════
# 配色
# ═══════════════════════════════════════════════════════════════════════════
def _tv(th,sc):
    if th=="light": return {"bg":"#fff","cbg":"#f6f8fa","bc":"#d0d7de","tc":"#1f2328","mu":"#656d76","lk":"#0969da","cbg2":"#afb8c133","ico":"#d1242f","st":sc}
    return {"bg":"#0d1117","cbg":"#161b22","bc":"#30363d","tc":"#c9d1d9","mu":"#8b949e","lk":"#58a6ff","cbg2":"#1c2128","ico":"#ff7b72","st":sc}

_SM={"open":("Open","State--open",I_PULL_REQ,"3fb950"),"closed":("Closed","State--closed",I_PULL_CLOSED,"f85149"),"merged":("Merged","State--merged",I_GIT_MERGE,"a371f7")}
def _si(state,merged=False):
    if merged: return _SM["merged"]
    return _SM.get(state,("Unknown","",'<circle cx="8" cy="8" r="3"/>',"6e7681"))

# ═══════════════════════════════════════════════════════════════════════════
# Timeline 事件处理
# ═══════════════════════════════════════════════════════════════════════════
_ED={
    "committed":              ("committed","commit"),
    "labeled":                ("added","tag"),
    "unlabeled":              ("removed","tag"),
    "cross-referenced":       ("mentioned","xref"),
    "referenced":             ("referenced in","xref"),
    "merged":                 ("merged","merged_badge"),
    "closed":                 ("closed","closed_badge"),
    "reopened":               ("reopened","check"),
    "reviewed":               ("reviewed","eye"),
    "commented":              ("commented","eye"),
    "head_ref_force_pushed":  ("force-pushed","push"),
    "review_requested":       ("requested a review","eye"),
    "review_request_removed": ("removed review request","eye"),
    "ready_for_review":       ("marked ready for review","eye"),
    "renamed":                ("renamed","commit"),
    "assigned":               ("self-assigned this","tag"),
    "unassigned":             ("removed their assignment","tag"),
    "locked":                 ("locked","check"),
    "unlocked":               ("unlocked","check"),
}

def _process_timeline(raw):
    tl=[]
    for ev in raw[:MAX_TIMELINE]:
        if not isinstance(ev,dict): continue
        et=ev.get("event",""); info=_ED.get(et)
        if not info: continue
        action,badge=info
        cts=ev.get("created_at") or ev.get("submitted_at") or ""
        if not cts: continue
        ao=(ev.get("actor") or ev.get("author") or ev.get("committer") or ev.get("assignee") or ev.get("user") or {})
        if not isinstance(ao,dict): ao={}
        al=ao.get("login","unknown"); aa=ao.get("avatar_url","")
        bot=al.endswith("[bot]") or "bot" in al.lower() or al=="github-actions"
        it={"_badge":badge,"_type":"generic","actor":al,"avatar":aa,"action":action,
            "time":_rt(_pts(cts)),"is_bot":bot}

        if et=="committed":
            it["_type"]="commit"; sha=ev.get("sha",""); it["sha"]=sha[:7] if sha else ""
            it["cmt_url"]=ev.get("html_url","")
            m=(ev.get("commit",{}) or {}).get("message","")
            if m: it["msg"]=m.split("\n")[0][:140]
        elif et=="head_ref_force_pushed":
            it["_type"]="generic"; it["_badge"]="push"
            after=ev.get("after",""); before=ev.get("before","")
            ref=ev.get("ref","").replace("refs/heads/","")
            it["action"]=f"force-pushed {ref}" if ref else "force-pushed"
            it["msg"]=f"{before[:7]} → {after[:7]}" if (before and after) else ""
            it["sha"]=after[:7] if after else ""
        elif et in("labeled","unlabeled"):
            it["_type"]="label"; lb=ev.get("label") or {}
            if lb: it["lbs"]=[{"name":lb.get("name",""),"color":lb.get("color","ffffff")}]
        elif et in("cross-referenced","referenced"):
            it["_type"]="reference"; src=(ev.get("source") or {}).get("issue") or {}
            if src:
                it["rf_title"]=src.get("title",""); it["rf_state"]=src.get("state","")
                it["rf_num"]=src.get("number",0); it["rf_url"]=src.get("html_url","")
        elif et=="reviewed":
            it["_type"]="review"; st=ev.get("state","commented")
            it["action"]={"approved":"approved","changes_requested":"requested changes"}.get(st,"reviewed")
            body=(ev.get("body") or "")[:400]
            if body: it["rv_body"]=_md2html(body)
        elif et=="commented":
            it["_type"]="review"; it["action"]="commented"
            body=(ev.get("body") or "")[:400]
            if body: it["rv_body"]=_md2html(body)
        elif et in("review_requested","review_request_removed"):
            reviewer=(ev.get("requested_reviewer") or ev.get("requested_team") or {})
            rv_login=reviewer.get("login") or reviewer.get("slug","")
            if rv_login and rv_login!=al:
                it["action"]=f"requested a review from @{rv_login}" if et=="review_requested" else f"removed review request for @{rv_login}"
            it["_badge"]="eye"
        elif et=="assigned":
            assignee=(ev.get("assignee") or {})
            an=assignee.get("login","")
            it["action"]="self-assigned this" if an==al else f"assigned @{an}" if an else "was assigned"
        tl.append(it)

    # ── 合并连续的同人 label 事件 ──
    merged=[]
    for it in tl:
        if it["_type"]=="label" and merged and merged[-1]["_type"]=="label" and merged[-1]["actor"]==it["actor"]:
            merged[-1].setdefault("lbs",[]).extend(it.get("lbs",[]))
        else:
            merged.append(it)
    for it in merged:
        if it["_type"]=="label" and len(it.get("lbs",[]))>1:
            it["action"]="added"
    # ── 如果有 merged 事件，过滤掉 closed（merged 已隐含 close） ──
    has_merged=any(e.get("action")=="merged" for e in merged)
    if has_merged:
        merged=[e for e in merged if e.get("action")!="closed"]
    return merged

# ═══════════════════════════════════════════════════════════════════════════
# 插件主类
# ═══════════════════════════════════════════════════════════════════════════
@register("astrbot_plugin_github_fetch","Drest","GitHub Issue/PR 预览卡片。REST API + Jinja2 渲染 → PNG。","2.0.0")
class GitHubFetchPlugin(Star):
    def __init__(self, context, config):
        super().__init__(context); self.config=config; self._cln=[]; self._hc=None
        ttl=max(int(config.get("cache_ttl",300)),0)
        self._cache=None
        if ttl>0:
            try: from cachetools import TTLCache; self._cache=TTLCache(256,ttl)
            except: self._cache=_TC(256,ttl)

    async def initialize(self):
        global _httpx_ok,_jinja2_ok,_pw_ok,_ct_ok
        for iname,pname,br in _REQUIRED:
            if iname=="playwright": _pw_ok=_ensure_pkg(iname,pname) and _ensure_browser()
            elif iname=="httpx": _httpx_ok=_ensure_pkg(iname,pname)
            elif iname=="jinja2": _jinja2_ok=_ensure_pkg(iname,pname)
            elif iname=="cachetools": _ct_ok=_ensure_pkg(iname,pname)
        if _httpx_ok: import httpx
        if _jinja2_ok: from jinja2 import Template
        parts=[]
        if _httpx_ok:
            to=max(float(self.config.get("timeout",15000))/1000.,1.)
            self._hc=httpx.AsyncClient(timeout=httpx.Timeout(to),headers={"Accept":"application/vnd.github+json"})
            parts.append(f"httpx({to}s)")
        else: parts.append("httpx ❌")
        if _jinja2_ok: self._tpl=Template(_T); parts.append("Jinja2")
        else: self._tpl=None; parts.append("Jinja2 ❌")
        parts.append(f"PNG={'pw' if _pw_ok else 'text'}")
        parts.append(f"Cache={'on' if self._cache else 'off'}")
        logger.info("[GitHubFetch] "+" | ".join(parts))

    async def terminate(self):
        if self._hc: await self._hc.aclose(); self._hc=None
        for t in self._cln: t.cancel()
        self._cln.clear()
        if self._cache and hasattr(self._cache,"clear"): self._cache.clear()

    def _ah(self)->dict:
        h={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"astrbot-gh-fetch"}
        tok=(self.config.get("github_token","") or "").strip()
        if tok: h["Authorization"]=f"Bearer {tok}"
        return h

    async def _cached(self,key,factory):
        if self._cache:
            try: return self._cache[key]
            except KeyError: pass
        r=await factory()
        if self._cache and r is not None: self._cache[key]=r
        return r

    async def _repo(self,o,r):
        """PR/Issue 流程用的精简仓库信息"""
        async def _do():
            resp=await self._hc.get(f"https://api.github.com/repos/{o}/{r}",headers=self._ah())
            if resp.status_code!=200: return None
            d=resp.json()
            return {"fn":d.get("full_name",f"{o}/{r}"),"st":_fc(d.get("stargazers_count",0)),"fk":_fc(d.get("forks_count",0))}
        return await self._cached(f"repo:{o}/{r}",_do)

    async def _repo_full(self,o,r):
        """获取仓库综合信息（并发请求 contents/readme/languages/contributors/releases）"""
        async def _do():
            h=self._ah()
            # 基础信息
            rp=await self._hc.get(f"https://api.github.com/repos/{o}/{r}",headers=h)
            if rp.status_code!=200: return None
            d=rp.json()

            # 并发获取所有子资源
            tasks={
                "contents":     self._hc.get(f"https://api.github.com/repos/{o}/{r}/contents",headers=h),
                "readme":       self._hc.get(f"https://api.github.com/repos/{o}/{r}/readme",headers=h),
                "languages":    self._hc.get(f"https://api.github.com/repos/{o}/{r}/languages",headers=h),
                "contributors": self._hc.get(f"https://api.github.com/repos/{o}/{r}/contributors",headers=h,params={"per_page":5}),
                "releases":     self._hc.get(f"https://api.github.com/repos/{o}/{r}/releases",headers=h,params={"per_page":3}),
            }
            results={}
            for k,t in tasks.items():
                try: resp=await t; results[k]=resp
                except: pass

            # 文件列表
            files=[]
            if "contents" in results and results["contents"].status_code==200:
                for f in results["contents"].json()[:15]:
                    files.append({"name":f.get("name",""),"type":f.get("type","file"),"size":f.get("size",0)})

            # README
            readme_html=""
            if "readme" in results and results["readme"].status_code==200:
                import base64
                try:
                    rd=results["readme"].json()
                    content=base64.b64decode(rd.get("content","")).decode("utf-8","replace")
                    readme_html=_md2html(content[:3000])
                except: pass

            # Languages
            langs=[]
            if "languages" in results and results["languages"].status_code==200:
                ld=results["languages"].json()
                total=sum(ld.values()) or 1
                langs=sorted([{"name":k,"pct":round(v/total*100,1),"bytes":v} for k,v in ld.items()],key=lambda x:-x["pct"])[:6]

            # Contributors
            contribs=[]
            if "contributors" in results and results["contributors"].status_code==200:
                for c in results["contributors"].json()[:5]:
                    contribs.append({"login":c.get("login",""),"avatar":c.get("avatar_url",""),"commits":c.get("contributions",0)})

            # Releases
            rels=[]
            if "releases" in results and results["releases"].status_code==200:
                for rl in results["releases"].json()[:3]:
                    rels.append({"tag":rl.get("tag_name",""),"name":rl.get("name",""),"prerelease":rl.get("prerelease",False),
                                 "published":_pts(rl["published_at"]) if rl.get("published_at") else None})

            return {"fn":d.get("full_name",f"{o}/{r}"),"st":_fc(d.get("stargazers_count",0)),"fk":_fc(d.get("forks_count",0)),
                    "desc":(d.get("description") or "")[:200],"lang":d.get("language") or "",
                    "license":(d.get("license") or {}).get("spdx_id",""),"topics":(d.get("topics") or [])[:8],
                    "issues":d.get("open_issues_count",0),"watchers":_fc(d.get("subscribers_count",0)),
                    "default_branch":d.get("default_branch","main"),
                    "updated_at":_pts(d["updated_at"]) if d.get("updated_at") else None,
                    "files":files,"readme":readme_html,"langs":langs,"contribs":contribs,"rels":rels}
        return await self._cached(f"repo_full:{o}/{r}",_do)

    async def _tl(self,o,r,n):
        async def _do():
            resp=await self._hc.get(f"https://api.github.com/repos/{o}/{r}/issues/{n}/timeline",headers=self._ah(),params={"per_page":60})
            if resp.status_code!=200: return []
            try: return _process_timeline(resp.json())
            except Exception as e: logger.warning(f"[GitHubFetch] tl: {e}"); return []
        return await self._cached(f"tl:{o}/{r}#{n}",_do)

    async def _commits_api(self,o,r,n):
        """获取 PR 的 commit 列表，转为 timeline 条目，与 API timeline 合并。"""
        async def _do():
            resp=await self._hc.get(f"https://api.github.com/repos/{o}/{r}/pulls/{n}/commits",headers=self._ah(),params={"per_page":40})
            if resp.status_code!=200: return []
            commits=[]
            for c in resp.json():
                sha=c.get("sha",""); cmt=c.get("commit",{}) or {}
                author=c.get("author") or {}
                dt_str=cmt.get("committer",{}).get("date","") or cmt.get("author",{}).get("date","")
                commits.append({
                    "_badge":"commit","_type":"commit","actor":author.get("login","unknown"),
                    "avatar":author.get("avatar_url",""),"action":"committed","time":_rt(_pts(dt_str)) if dt_str else "",
                    "sha":sha[:7] if sha else "","cmt_url":c.get("html_url",""),
                    "msg":cmt.get("message","").split("\n")[0][:140],"is_bot":False,
                    "_ts":_pts(dt_str) if dt_str else None,
                })
            return commits
        return await self._cached(f"cmts:{o}/{r}#{n}",_do)

    def _merge_timeline(self, tl_events, commits):
        """将 PR commits 按时间插入 timeline 事件列表的正确位置。"""
        # 过滤掉 timeline 中已有的 commit 事件（避免重复）
        non_commit = [e for e in tl_events if e.get("_type")!="commit"]
        # 合并 + 按时间排序
        combined = non_commit + commits
        def _sort_key(e):
            t=e.get("time","")
            # 用 time 字段做粗略排序：较新事件在前（列表末尾）
            # 使用 reverse alphabetical 作为近似时间排序
            return t
        # 由于我们没有精确的时间戳，保持 timeline 原有顺序，在末尾追加 commits
        # 更好的方案：将 commit 插入到 force-push 之前
        result = list(non_commit)
        if commits:
            # 找到 force-push 事件位置，将 commits 插入在它之前
            push_idx = None
            for i,e in enumerate(result):
                if e.get("_badge")=="push" or e.get("action","").startswith("force-pushed"):
                    push_idx = i; break
            if push_idx is not None:
                for c in reversed(commits):
                    result.insert(push_idx, c)
            else:
                # 没有 force-push，追加到 review_requested/assigned 之后、closed 之前
                close_idx = None
                for i,e in enumerate(result):
                    if e.get("action","") in ("closed","merged","reopened"):
                        close_idx = i; break
                if close_idx is not None:
                    for c in reversed(commits):
                        result.insert(close_idx, c)
                else:
                    result.extend(commits)
        return result

    async def _issue(self,o,r,n):
        if not _httpx_ok or self._hc is None: raise RuntimeError("httpx not installed")
        ck=f"{o}/{r}#{n}"
        if self._cache:
            try: return self._cache[ck]
            except KeyError: pass
        h=self._ah(); resp=await self._hc.get(f"https://api.github.com/repos/{o}/{r}/issues/{n}",headers=h)
        if resp.status_code==404: return None
        if resp.status_code in(403,429): raise RuntimeError(f"rate limit ({resp.status_code})")
        if resp.status_code>=400: raise RuntimeError(f"API {resp.status_code}")
        d=resp.json(); is_pr="pull_request" in d
        rt=asyncio.create_task(self._repo(o,r)); tt=asyncio.create_task(self._tl(o,r,n))
        ct=asyncio.create_task(self._commits_api(o,r,n)) if is_pr else None
        pt=None
        if is_pr:
            pr=d.get("pull_request"); pu=pr.get("url") if isinstance(pr,dict) else None
            if pu: pt=asyncio.create_task(self._hc.get(pu,headers=h))
        repo=await rt; tl_events=await tt; commits=await ct if ct else []
        tl = self._merge_timeline(tl_events, commits)
        ma,gs=None,None
        pr=d.get("pull_request")
        if isinstance(pr,dict) and pr.get("merged_at"): ma=_pts(pr["merged_at"])
        if pt:
            pr_r=await pt
            if pr_r.status_code==200:
                pd=pr_r.json()
                if not ma and pd.get("merged_at"): ma=_pts(pd["merged_at"])
                gs={"c":pd.get("commits",0),"a":pd.get("additions",0),"d":pd.get("deletions",0),"f":pd.get("changed_files",0)}
        result={"title":d.get("title",""),"body":d.get("body") or "","state":d.get("state","unknown"),
                "author":d["user"]["login"] if d.get("user") else "unknown",
                "av":d["user"]["avatar_url"] if d.get("user") else "",
                "labels":[{"name":lb["name"],"color":lb["color"],"tc":_tc(lb.get("color","ffffff"))}
                          for lb in(d.get("labels") or[])],
                "ca":_pts(d["created_at"]),"url":d.get("html_url",""),"num":d.get("number",n),
                "is_pr":is_pr,"ma":ma,"repo":repo,"tl":tl,"gs":gs}
        if self._cache: self._cache[ck]=result
        return result

    def _html(self,d):
        if not _jinja2_ok or self._tpl is None: raise RuntimeError("jinja2 not installed")
        th=(self.config.get("theme","dark") or "dark").strip()
        merged=d.get("ma") is not None
        st_text,st_class,st_svg,st_hex=_si(d["state"],merged)
        v=_tv(th,f"#{st_hex}")
        return self._tpl.render(
            bg=v["bg"],cbg=v["cbg"],bc=v["bc"],tc=v["tc"],mu=v["mu"],lk=v["lk"],
            cbg2=v["cbg2"],ico=v["ico"],st=v["st"],st_text=st_text,st_class=st_class,st_svg=st_svg,
            num=d["num"],title=d["title"],url=d["url"],author=d["author"],av=d["av"],
            ca=d["ca"].strftime("%Y-%m-%d %H:%M UTC"),labels=d.get("labels",[]),
            body=_md2html(d.get("body") or ""),repo=d.get("repo"),timeline=d.get("tl",[]),
            I_FORK=I_FORK,I_STAR=I_STAR,I_GIT_COMMIT=I_GIT_COMMIT,I_TAG=I_TAG,
            I_CROSS_REF=I_CROSS_REF,I_EYE=I_EYE,I_CHECK=I_CHECK,I_PULL_CLOSED=I_PULL_CLOSED,
            I_REPO_PUSH=I_REPO_PUSH,I_GIT_MERGE=I_GIT_MERGE,I_PULL_REQ=I_PULL_REQ,
        )

    def _html_repo(self, d):
        """渲染仓库主页卡片"""
        if not _jinja2_ok: raise RuntimeError("jinja2 not installed")
        from jinja2 import Template
        tpl = Template(_REPO_T)
        th = (self.config.get("theme", "dark") or "dark").strip()
        v = _tv(th, "#3fb950")
        updated = d.get("updated_at")
        rels_formatted = []
        for r in d.get("rels", []):
            pub = r.get("published")
            rels_formatted.append({**r, "date": pub.strftime("%b %d, %Y") if pub else ""})
        return tpl.render(
            bg=v["bg"], cbg=v["cbg"], bc=v["bc"], tc=v["tc"], mu=v["mu"], lk=v["lk"],
            cbg2=v["cbg2"], ico=v["ico"],
            name=d["fn"], desc=d.get("desc", ""), url=f"https://github.com/{d['fn']}",
            stars=d.get("st", "0"), forks=d.get("fk", "0"), watchers=d.get("watchers", "0"),
            issues=str(d.get("issues", 0)), topics=d.get("topics", []),
            branch=d.get("default_branch", "main"),
            readme=d.get("readme", ""), files=d.get("files", []),
            langs=d.get("langs", []), contribs=d.get("contribs", []),
            rels=rels_formatted,
            I_FORK=I_FORK, I_STAR=I_STAR,
        )

    async def _proc_repo(self, o, r):
        try:
            d = await self._repo_full(o, r)
        except Exception as e:
            return (None, None, f"❌ {o}/{r}\n{type(e).__name__}: {e}")
        if d is None:
            return (None, None, f"❌ repo not found: {o}/{r}")
        try:
            h = self._html_repo(d)
        except:
            return (None, f"📦 **{d['fn']}**\n{d.get('desc','')}\n⭐ {d['st']}  🍴 {d['fk']}", None)
        try:
            p = await self._png(h)
            return (p, None, None)
        except:
            return (None, f"📦 **{d['fn']}**\n{d.get('desc','')}\n⭐ {d['st']}  🍴 {d['fk']}", None)

    async def _png(self,html):
        if not _pw_ok: raise RuntimeError("playwright not available")
        fp=str(Path(tempfile.gettempdir())/f"ghc_{abs(hash(html))}_{int(time.time()*1000)}.png")
        from playwright.async_api import async_playwright as _pw2
        async with _pw2() as p:
            browser = await p.chromium.launch(headless=True, args=[
                "--disable-gpu","--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"])
            try:
                pg=await browser.new_page(viewport={"width":800,"height":600})
                await pg.set_content(html,wait_until="networkidle"); await pg.wait_for_timeout(500)
                await pg.screenshot(path=fp,full_page=True)
            finally: await browser.close()
        return fp

    def _txt(self,d):
        merged=d.get("ma") is not None; st_text,*_=_si(d["state"],merged)
        lbs=" | "+" ".join(f"`{n['name']}`" for n in d.get("labels",[])) if d.get("labels") else ""
        body=(d.get("body") or "")[:200]
        if len(d.get("body") or "")>200: body+="…"
        ln=[f"### {st_text} — #{d['num']} {d['title']}","",
            f"**Author**: [{d['author']}](https://github.com/{d['author']})",
            f"**Time**: {_rt(d['ca'])}{lbs}",f"**Link**: {d['url']}"]
        if d.get("repo"): ln.insert(2,f"**Repo**: {d['repo']['fn']} ⭐{d['repo']['st']} 🍴{d['repo']['fk']}")
        if d.get("gs"): gs=d["gs"]; ln.append(f"**Commits**: {gs['c']} +{gs['a']} -{gs['d']} ({gs['f']} files)")
        if body.strip(): ln.append(f"\n> {body}")
        return "\n".join(ln)

    def _cln(self,fp):
        async def _rm():
            await asyncio.sleep(CLEANUP_DELAY)
            try:
                if os.path.exists(fp): os.remove(fp)
            except OSError: pass
        t=asyncio.create_task(_rm()); self._cln.append(t)
        self._cln=[x for x in self._cln if not x.done()]

    async def _proc(self,o,r,n):
        try: d=await self._issue(o,r,n)
        except Exception as e: return (None,None,f"❌ {o}/{r}#{n}\n{type(e).__name__}: {e}")
        if d is None: return (None,None,f"❌ not found: {o}/{r}#{n}")
        try: h=self._html(d)
        except: return (None,self._txt(d),None)
        try: p=await self._png(h); return (p,None,None)
        except: return (None,self._txt(d),None)

    @filter.regex(GITHUB_ANY_URL_PATTERN)
    async def on_url(self,ev):
        if not self.config.get("enable_url_fetch",True): return
        urls=re.findall(GITHUB_ANY_URL_PATTERN,ev.message_str or "")
        if not urls: return
        prs,repos,oth=[],[],[]
        for u in urls[:MAX_URLS]:
            p=_pu(u)
            if p: prs.append((u,*p)); continue
            rp=_parse_repo(u)
            if rp: repos.append((u,*rp)); continue
            oth.append(u)
        # PR/Issue URLs
        for u,o,r,n in prs:
            png,txt,err=await self._proc(o,r,n)
            if err: yield ev.plain_result(err)
            elif png: yield ev.image_result(png); self._cln(png)
            elif txt: yield ev.plain_result(txt)
        # 仓库主页 URLs
        for u,o,r in repos:
            png,txt,err=await self._proc_repo(o,r)
            if err: yield ev.plain_result(err)
            elif png: yield ev.image_result(png); self._cln(png)
            elif txt: yield ev.plain_result(txt)
        for u in oth: yield ev.plain_result(f"💡 unsupported:\n{u}")

    @filter.regex(ISSUE_REF_PATTERN)
    async def on_ref(self,ev):
        if not self.config.get("enable_issue_fetch",True): return
        dr=(self.config.get("default_repo","") or "").strip()
        if not dr: return
        if re.search(GITHUB_PR_ISSUE_URL,ev.message_str or ""): return
        if "/" not in dr or dr.count("/")!=1: yield ev.plain_result(f"❌ bad repo: '{dr}'"); return
        o,r=dr.split("/"); seen=set()
        for n in re.findall(ISSUE_REF_PATTERN,ev.message_str or ""):
            if n in seen: continue
            seen.add(n)
            png,txt,err=await self._proc(o,r,int(n))
            if err: yield ev.plain_result(err)
            elif png: yield ev.image_result(png); self._cln(png)
            elif txt: yield ev.plain_result(txt)
