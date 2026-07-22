"""
GitHub PR/Issue 本地测试 — 自动安装依赖并生成预览 PNG
用法:
    python test_local.py --url "https://github.com/owner/repo/pull/123" [--token ghp_xxx]
    python test_local.py --repo owner/repo --number 42 [--theme light] [--no-png]
"""
import argparse, asyncio, html as _html_mod, os, re, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ═══════════════════════════════════════════
# 自动安装
# ═══════════════════════════════════════════
def _ensure(im,pn):
    try: __import__(im); return True
    except: pass
    print(f"[AUTO] pip install {pn} …")
    try:
        subprocess.check_call([sys.executable,"-m","pip","install",pn],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120)
        __import__(im); print(f"[AUTO] ✅ {pn}"); return True
    except Exception as e: print(f"[AUTO] ❌ {pn}: {e}"); return False

def _ensure_browser():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p: p.chromium.launch(headless=True).close()
        return True
    except: pass
    print("[AUTO] playwright install chromium …")
    try:
        subprocess.check_call([sys.executable,"-m","playwright","install","chromium"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=300)
        print("[AUTO] ✅ Chromium"); return True
    except Exception as e: print(f"[AUTO] ❌ Chromium: {e}"); return False

_httpx_ok = _ensure("httpx","httpx")
_j2_ok    = _ensure("jinja2","jinja2")
_pw_ok    = _ensure("playwright","playwright") and _ensure_browser()
if not _httpx_ok or not _j2_ok: print("❌ 核心依赖缺失"); sys.exit(1)

# ═══════════════════════════════════════════
# 常量 + Octicon SVG
# ═══════════════════════════════════════════
GITHUB_PR_ISSUE_URL = r"https?://github\.com/([a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?)/([a-zA-Z0-9_.\-]+)/(pull|issues)/(\d+)"
GITHUB_REPO_URL      = r"https?://github\.com/([a-zA-Z0-9](?:[a-zA-Z0-9\-]*[a-zA-Z0-9])?)/([a-zA-Z0-9_.\-]+)/?\s*$"
_SL, _SG = "\x00LT\x00", "\x00GT\x00"
_HTR = re.compile(r"<(/?)([A-Za-z]\w*)([^>]*)>")
MAX_BODY = 8000; MAX_TIMELINE = 20

I_GIT_COMMIT  = '<path d="M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z"/>'
I_TAG         = '<path d="M1 7.775V2.75C1 1.784 1.784 1 2.75 1h5.025c.464 0 .91.184 1.238.513l6.25 6.25a1.75 1.75 0 0 1 0 2.474l-5.026 5.026a1.75 1.75 0 0 1-2.474 0l-6.25-6.25A1.752 1.752 0 0 1 1 7.775Zm1.5 0c0 .066.026.13.073.177l6.25 6.25a.25.25 0 0 0 .354 0l5.025-5.025a.25.25 0 0 0 0-.354l-6.25-6.25a.25.25 0 0 0-.177-.073H2.75a.25.25 0 0 0-.25.25ZM6 5a1 1 0 1 1 0 2 1 1 0 0 1 0-2Z"/>'
I_CROSS_REF   = '<path d="M2.75 3.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h2a.75.75 0 0 1 .75.75v2.19l2.72-2.72a.749.749 0 0 1 .53-.22h4.5a.25.25 0 0 0 .25-.25v-2.5a.75.75 0 0 1 1.5 0v2.5A1.75 1.75 0 0 1 13.25 13H9.06l-2.573 2.573A1.458 1.458 0 0 1 4 14.543V13H2.75A1.75 1.75 0 0 1 1 11.25v-7.5C1 2.784 1.784 2 2.75 2h5.5a.75.75 0 0 1 0 1.5ZM16 1.25v4.146a.25.25 0 0 1-.427.177L14.03 4.03l-3.75 3.75a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734l3.75-3.75-1.543-1.543A.25.25 0 0 1 11.604 1h4.146a.25.25 0 0 1 .25.25Z"/>'
I_EYE         = '<path d="M8 2c1.981 0 3.671.992 4.933 2.078 1.27 1.091 2.187 2.345 2.637 3.023a1.62 1.62 0 0 1 0 1.798c-.45.678-1.367 1.932-2.637 3.023C11.67 13.008 9.981 14 8 14c-1.981 0-3.671-.992-4.933-2.078C1.797 10.83.88 9.576.43 8.898a1.62 1.62 0 0 1 0-1.798c.45-.677 1.367-1.931 2.637-3.022C4.33 2.992 6.019 2 8 2ZM1.679 7.932a.12.12 0 0 0 0 .136c.411.622 1.241 1.75 2.366 2.717C5.176 11.758 6.527 12.5 8 12.5c1.473 0 2.825-.742 3.955-1.715 1.124-.967 1.954-2.096 2.366-2.717a.12.12 0 0 0 0-.136c-.412-.621-1.242-1.75-2.366-2.717C10.824 4.242 9.473 3.5 8 3.5c-1.473 0-2.825.742-3.955 1.715-1.124.967-1.954 2.096-2.366 2.717ZM8 10a2 2 0 1 1-.001-3.999A2 2 0 0 1 8 10Z"/>'
I_CHECK       = '<path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"/>'
I_FORK        = '<path d="M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v.878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 1 3.5 6.25v-.878a2.25 2.25 0 1 1 1.5 0ZM5 3.25a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Zm6.75.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm-3 8.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z"/>'
I_STAR        = '<path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"/>'
I_PULL_REQ    = '<path d="M6.25 1a2.25 2.25 0 0 1 .75 4.372v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 6.25 1Zm0 1.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm2.5 5a.75.75 0 0 1 .75-.75h3.72l-1.22-1.22a.751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018l2.5 2.5a.75.75 0 0 1 0 1.06l-2.5 2.5a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734L13.22 9H9.5a.75.75 0 0 1-.75-.75Zm-3.5 4.75a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm7.5 0a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/>'
I_PULL_CLOSED = '<path d="M3.25 1A2.25 2.25 0 0 1 4 5.372v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.251 2.251 0 0 1 3.25 1Zm9.5 5.5a.75.75 0 0 1 .75.75v3.378a2.251 2.251 0 1 1-1.5 0V7.25a.75.75 0 0 1 .75-.75Zm-2.03-5.273a.75.75 0 0 1 1.06 0l.97.97.97-.97a.748.748 0 0 1 1.265.332.75.75 0 0 1-.205.729l-.97.97.97.97a.751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018l-.97-.97-.97.97a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734l.97-.97-.97-.97a.75.75 0 0 1 0-1.06ZM2.5 3.25a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0ZM3.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm9.5 0a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/>'
I_GIT_MERGE   = '<path d="M8 2a.75.75 0 0 1 .696.471L11 8.226v3.402a2.251 2.251 0 1 1-1.5 0V8.774l-1.745-4.51a2.5 2.5 0 1 1 1.508-.147L11 8.226l1.514-3.45a2.5 2.5 0 1 1 1.425.244L10.944 9.902a.75.75 0 0 1-.944.374.75.75 0 0 1-.444-.69V8.774L7.486 4.106A.75.75 0 0 1 8 2ZM5 2.5a1 1 0 1 0 0 2 1 1 0 0 0 0-2Zm7 0a1 1 0 1 0 0 2 1 1 0 0 0 0-2Zm-7 9.5a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm7 0a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/>'
I_REPO_PUSH   = '<path d="M1.5 2.75a.25.25 0 0 1 .25-.25h12.5a.25.25 0 0 1 .25.25v3a.75.75 0 0 0 1.5 0v-3A1.75 1.75 0 0 0 14.25 1H1.75A1.75 1.75 0 0 0 0 2.75v7.5C0 11.216.784 12 1.75 12H5v1.543a1.458 1.458 0 0 0 2.487 1.03L10.06 12h4.19A1.75 1.75 0 0 0 16 10.25v-3.5a.75.75 0 0 0-1.5 0v3.5a.25.25 0 0 1-.25.25h-4.5a.75.75 0 0 0-.53.22L6.5 13.44v-2.19a.75.75 0 0 0-.75-.75H1.75a.25.25 0 0 1-.25-.25v-7.5Z"/>'

def _p(t): return _HTR.sub(lambda m:f"{_SL}{m.group(1)}{m.group(2)}{m.group(3)}{_SG}",t)
def _r(t): return t.replace(_SL,"<").replace(_SG,">")
def _pts(ts): return datetime.fromisoformat(ts.replace("Z","+00:00"))
def _pu(url):
    m=re.search(GITHUB_PR_ISSUE_URL,url)
    return (m.group(1),m.group(2),int(m.group(4))) if m else None

def _parse_repo(url):
    m=re.match(GITHUB_REPO_URL,url.strip())
    return (m.group(1),m.group(2)) if m else None
def _tc(c):
    try: r,g,b=int(c[0:2],16),int(c[2:4],16),int(c[4:6],16)
    except: return "#fff"
    return "#fff" if (0.299*r+0.587*g+0.114*b)/255<0.5 else "#333"
def _fc(n): return f"{n/1000:.1f}k" if n>=1000 else str(n)
def _rt(dt):
    """GitHub 风格相对时间: just now / 5m ago / 3h ago / 2d ago / on Jun 15"""
    now=datetime.now(timezone.utc); s=(now-dt).total_seconds()
    if s<60: return "just now"
    if s<3600: return f"{int(s/60)}m ago"
    if s<86400: return f"{int(s/3600)}h ago"
    if s<604800: return f"{int(s/86400)}d ago"
    if dt.year==now.year: return f"on {dt.strftime('%b %d')}"
    return f"on {dt.strftime('%b %d, %Y')}"

# ── Markdown → HTML (table / task-list / nested lists) ──
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
        t=re.sub(r'^\[ \] ', '<input type="checkbox" disabled style="margin-right:6px">', t)
        t=re.sub(r'^\[x\] ', '<input type="checkbox" disabled checked style="margin-right:6px">', t)
        t=re.sub(r'!\[([^\]]*)\]\(([^)\s]+(?:\s+"[^"]*")?)\)', r'<img src="\2" alt="\1" style="max-width:100%;border-radius:4px">', t)
        t=re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)', r'<a href="\2">\1</a>', t)
        t=re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
        t=re.sub(r'\*(.+?)\*', r'<em>\1</em>', t)
        t=re.sub(r'~~(.+?)~~', r'<del>\1</del>', t)
        return t
    in_table=False; table_rows=[]
    def _flush_table():
        nonlocal in_table,table_rows
        if not table_rows: return
        html='<table>'
        for ri,row in enumerate(table_rows):
            cells=[c.strip() for c in row.split("|")[1:-1]]
            if all(re.match(r'^:?-{3,}:?$',c) for c in cells): continue  # skip separator
            tag="th" if ri==0 else "td"
            html+="<tr>"+"".join(f"<{tag}>{_pi(c)}</{tag}>" for c in cells)+"</tr>"
        html+="</table>"; O.append(html); table_rows=[]
    i=0
    while i<len(L):
        ln=L[i]
        if ln.strip().startswith("```"):
            if not cb: _fl(); _flush_table(); cb=True; cbl=ln.strip()[3:].strip(); cblines=[]
            else:
                la=f' class="language-{cbl}"' if cbl else ""
                O.append(f"<pre><code{la}>{_html_mod.escape(chr(10).join(cblines))}</code></pre>")
                cb=False; cblines=[]
            i+=1; continue
        if cb: cblines.append(ln); i+=1; continue
        if ln.strip().startswith("|") and ln.strip().endswith("|"):
            if not in_table: _fl(); in_table=True
            table_rows.append(ln); i+=1; continue
        elif in_table: _flush_table(); in_table=False
        if not ln.strip(): _fl(); _flush_table(); i+=1; continue
        hm=re.match(r"^(#{1,4})\s+(.+)$",ln)
        if hm: _fl(); O.append(f"<h{len(hm.group(1))}>{_pi(hm.group(2))}</h{len(hm.group(1))}>"); i+=1; continue
        if re.match(r"^[-*_]{3,}\s*$",ln.strip()): _fl(); O.append("<hr>"); i+=1; continue
        if ln.startswith("> "): _fl(); O.append(f"<blockquote>{_pi(ln[2:])}</blockquote>"); i+=1; continue
        um=re.match(r"^(\s*)[-*+]\s+(.+)$",ln)
        if um:
            if il!="ul": _fl(); il="ul"
            li.append(um.group(2)); i+=1; continue
        om=re.match(r"^(\s*)\d+\.\s+(.+)$",ln)
        if om:
            if il!="ol": _fl(); il="ol"
            li.append(om.group(2)); i+=1; continue
        _fl(); O.append(f"<p>{_pi(ln)}</p>"); i+=1
    _fl(); _flush_table()
    if cb and cblines: O.append(f"<pre><code>{_html_mod.escape(chr(10).join(cblines))}</code></pre>")
    return "\n".join(O)

_SM={"open":("Open","State--open",I_PULL_REQ,"3fb950"),"closed":("Closed","State--closed",I_PULL_CLOSED,"f85149"),"merged":("Merged","State--merged",I_GIT_MERGE,"a371f7")}
def _si(state,merged=False):
    return _SM["merged"] if merged else _SM.get(state,("Unknown","",'<circle cx="8" cy="8" r="3"/>',"6e7681"))

_ED={
    "committed":("committed","commit"),"labeled":("added","tag"),"unlabeled":("removed","tag"),
    "cross-referenced":("mentioned","xref"),"referenced":("referenced in","xref"),
    "merged":("merged","merged_badge"),"closed":("closed","closed_badge"),"reopened":("reopened","check"),
    "reviewed":("reviewed","eye"),"commented":("commented","eye"),
    "head_ref_force_pushed":("force-pushed","push"),
    "review_requested":("requested a review","eye"),
    "review_request_removed":("removed review request","eye"),
    "ready_for_review":("marked ready for review","eye"),"renamed":("renamed","commit"),
    "assigned":("self-assigned this","tag"),"unassigned":("removed their assignment","tag"),
    "locked":("locked","check"),"unlocked":("unlocked","check"),
}

def _process_timeline(raw):
    tl=[]
    for ev in raw[:MAX_TIMELINE]:
        if not isinstance(ev,dict): continue
        et=ev.get("event",""); info=_ED.get(et)
        if not info: continue
        action,badge=info; cts=ev.get("created_at") or ev.get("submitted_at") or ""
        if not cts: continue
        ao=(ev.get("actor") or ev.get("author") or ev.get("committer") or ev.get("assignee") or ev.get("user") or {})
        if not isinstance(ao,dict): ao={}
        al=ao.get("login","unknown"); aa=ao.get("avatar_url","")
        bot=al.endswith("[bot]")or"bot"in al.lower()or al=="github-actions"
        it={"_badge":badge,"_type":"generic","actor":al,"avatar":aa,"action":action,
            "time":_rt(_pts(cts)),"is_bot":bot}
        if et=="committed":
            it["_type"]="commit"; sha=ev.get("sha",""); it["sha"]=sha[:7] if sha else ""
            it["cmt_url"]=ev.get("html_url",""); m=(ev.get("commit",{}) or {}).get("message","")
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
            if src: it["rf_title"]=src.get("title",""); it["rf_state"]=src.get("state","")
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
    # merge consecutive same-actor label events
    merged=[]
    for it in tl:
        if it["_type"]=="label" and merged and merged[-1]["_type"]=="label" and merged[-1]["actor"]==it["actor"]:
            merged[-1].setdefault("lbs",[]).extend(it.get("lbs",[]))
        else: merged.append(it)
    for it in merged:
        if it["_type"]=="label" and len(it.get("lbs",[]))>1: it["action"]="added"
    has_merged=any(e.get("action")=="merged" for e in merged)
    if has_merged: merged=[e for e in merged if e.get("action")!="closed"]
    return merged

# ═══════════════════════════════════════════
# Template
# ═══════════════════════════════════════════
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

  .State{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:2em;font-size:12px;font-weight:600;line-height:20px;color:#fff}
  .State svg{width:14px;height:14px;fill:#fff}
  .State--open{background:#3fb950}.State--closed{background:#f85149}.State--merged{background:#a371f7}
  .header{margin-bottom:16px}
  .header-row{display:flex;align-items:center;gap:8px;margin-bottom:8px}
  .pr-num{color:{{mu}};font-size:14px}
  .title{font-size:22px;font-weight:600;line-height:1.35;word-wrap:break-word}
  .title a{color:{{tc}}}

  .body{font-size:15px;line-height:1.6;margin:16px 0;padding-top:16px;border-top:1px solid {{bc}};word-wrap:break-word;overflow-wrap:break-word}
  .body>:first-child{margin-top:0}
  .body h1,.body h2,.body h3,.body h4{margin:20px 0 8px;font-weight:600}
  .body h1{font-size:1.5em;padding-bottom:7px;border-bottom:1px solid {{bc}}}
  .body h2{font-size:1.35em;padding-bottom:5px;border-bottom:1px solid {{bc}}}
  .body h3{font-size:1.15em}.body h4{font-size:1em}
  .body p{margin:0 0 10px}.body p:last-child{margin-bottom:0}
  .body ul,.body ol{padding-left:24px;margin:0 0 10px}
  .body li{margin:2px 0}
  .body code{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;background:{{cbg2}};padding:2px 5px;border-radius:4px;font-size:.85em;color:{{ico}}}
  .body pre{background:{{cbg2}};border-radius:6px;padding:14px;overflow-x:auto;margin:0 0 10px;line-height:1.5}
  .body pre code{background:none;padding:0;color:{{tc}};font-size:.82em}
  .body blockquote{border-left:3px solid {{st}};padding:2px 14px;margin:0 0 10px;color:{{mu}}}
  .body img{max-width:100%;height:auto;border-radius:4px;margin:6px 0}
  .body hr{border:none;border-top:1px solid {{bc}};margin:20px 0}
  .body details{border:1px solid {{bc}};border-radius:6px;padding:10px 16px;margin:8px 0}
  .body summary{font-weight:600;cursor:pointer;color:{{lk}}}
  .body table{border-collapse:collapse;width:100%;margin:10px 0;font-size:.92em;display:block;overflow-x:auto;max-width:100%}
  .body th,.body td{border:1px solid {{bc}};padding:8px 12px;text-align:left;word-break:break-word;white-space:normal}
  .body th{background:{{cbg2}};font-weight:600}
  .body tr:nth-child(even){background:{{cbg2}}33}
  .body input[type=checkbox]{vertical-align:middle;accent-color:{{lk}}}
  .body kbd{display:inline-block;padding:1px 5px;font:11px ui-monospace,monospace;border:1px solid {{bc}};border-radius:3px;background:{{cbg2}};box-shadow:inset 0 -1px 0 {{bc}}}

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
  .tl-cmt{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
  .tl-avatar-stack{display:flex;flex-shrink:0;margin-right:2px}
  .tl-avatar-stack img{width:20px;height:20px;border-radius:50%;object-fit:cover;border:2px solid {{cbg}};margin-right:-6px}
  .tl-avatar-stack img:last-child{margin-right:0}
  .tl-cmt-msg{font-family:ui-monospace,SFMono-Regular,monospace;font-size:13px;min-width:0;flex:1}
  .tl-cmt-msg a{color:{{tc}};font-weight:600}
  .tl-cmt-sha{font-family:ui-monospace,SFMono-Regular,monospace;font-size:11px;flex-shrink:0;margin-left:auto}
  .tl-cmt-sha a{color:{{mu}}}
  .tl-lbl{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:13px;line-height:20px}
  .tl-lbl-tag{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;line-height:18px}
  .tl-xref{margin-top:6px;background:{{cbg2}};border:1px solid {{bc}};border-radius:6px;padding:10px 14px;display:flex;align-items:center;gap:10px}
  .tl-xref .tl-xref-title{font-size:14px;font-weight:600;flex:1;min-width:0}
  .tl-xref .tl-xref-title a{color:{{tc}}}
  .tl-xref .tl-xref-num{color:{{mu}};font-weight:400}
  .State--sm{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:2em;font-size:11px;font-weight:600;flex-shrink:0}
  .State--sm svg{width:14px;height:14px}
  .tl-review{margin-top:6px;background:{{cbg2}};border:1px solid {{bc}};border-radius:8px;padding:14px 18px}
  .tl-review-body{font-size:14px;line-height:1.55;color:{{tc}}}
  .tl-review-body p{margin:0 0 6px}.tl-review-body p:last-child{margin-bottom:0}
  .Label-bot{display:inline-block;padding:0 6px;border-radius:2em;font-size:10px;font-weight:600;color:{{mu}};border:1px solid {{bc}};line-height:18px;margin-left:3px}
  .tl-time{color:{{mu}};font-size:12px;white-space:nowrap}
  .actor{font-weight:600;color:{{tc}}}

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
            {% for lb in it.lbs %}<span class="tl-lbl-tag" style="background:#{{lb.color}}33;color:#{{lb.color}};border:1px solid #{{lb.color}}55">{{lb.name}}</span>{% endfor %}
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
    {% if labels %}<div class="ft-labels">{% for lb in labels %}<span class="ft-label" style="background:#{{lb.color}};color:{{lb.tc}}">{{lb.name}}</span>{% endfor %}</div>{% endif %}
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
  .gh-header{background:{{cbg}};border-bottom:1px solid {{bc}};padding:12px 24px;display:flex;align-items:center;gap:8px}
  .gh-header .owner{font-size:14px;color:{{mu}}}.gh-header .sep{color:{{mu}};font-size:14px}
  .gh-header .repo{font-size:18px;font-weight:600;color:{{lk}}}
  .gh-badge{font-size:10px;font-weight:600;color:{{mu}};border:1px solid {{bc}};border-radius:2em;padding:1px 8px;line-height:16px;margin-left:4px}
  .action-bar{background:{{cbg}};border-bottom:1px solid {{bc}};padding:8px 24px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  .act-btn{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border:1px solid {{bc}};border-radius:6px;font-size:11px;font-weight:600;color:{{tc}};background:{{cbg2}};cursor:default;line-height:18px}
  .act-btn svg{width:14px;height:14px;fill:{{mu}}}.act-count{background:{{cbg}};margin-left:-5px;border-radius:0 6px 6px 0}
  .tab-bar{background:{{cbg}};border-bottom:1px solid {{bc}};padding:0 24px;display:flex;gap:0}
  .tab{font-size:13px;color:{{mu}};padding:8px 14px;cursor:default;border-bottom:2px solid transparent}
  .tab.active{color:{{tc}};font-weight:600;border-bottom-color:#f78166}
  .tab .count{font-size:11px;background:{{bc}};border-radius:2em;padding:0 6px;margin-left:4px;color:{{tc}};font-weight:400}
  .main-body{padding:0 24px 16px}
  .branch-bar{display:flex;align-items:center;gap:8px;padding:12px 0;font-size:13px}
  .branch-btn{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border:1px solid {{bc}};border-radius:6px;font-size:12px;color:{{tc}};background:{{cbg2}};cursor:default}
  .branch-btn svg{width:12px;height:12px;fill:{{mu}}}
  .file-table{background:{{cbg}};border:1px solid {{bc}};border-radius:6px;overflow:hidden;margin-bottom:16px}
  .file-row{display:flex;align-items:center;gap:8px;padding:6px 12px;border-bottom:1px solid {{bc}};font-size:13px}
  .file-row:last-child{border-bottom:none}.file-row:nth-child(even){background:{{bc}}11}
  .file-icon{width:16px;text-align:center;flex-shrink:0;font-size:12px}
  .file-icon svg{width:14px;height:14px;fill:{{mu}}}
  .file-name{flex:1;min-width:0;word-break:break-word;color:{{tc}};font-weight:600}
  .file-time{color:{{mu}};font-size:11px;white-space:nowrap}
  .about-box{background:{{cbg}};border:1px solid {{bc}};border-radius:6px;padding:14px 16px;margin-bottom:12px}
  .about-title{font-size:13px;font-weight:600;margin-bottom:8px;color:{{tc}}}
  .about-desc{font-size:13px;color:{{tc}};line-height:1.5;margin-bottom:8px}
  .about-topics{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
  .about-topic{display:inline-block;padding:2px 8px;border-radius:2em;font-size:11px;font-weight:500;color:{{lk}};background:{{lk}}1a}
  .about-stat{display:flex;align-items:center;gap:4px;font-size:12px;color:{{tc}};padding:2px 0}
  .about-stat svg{width:14px;height:14px;fill:{{mu}}}
  .lang-bar{display:flex;border-radius:4px;overflow:hidden;height:8px;margin-bottom:8px}
  .lang-item{display:flex;align-items:center;gap:4px;margin-bottom:2px;font-size:11px}
  .lang-dot{width:8px;height:8px;border-radius:2px;flex-shrink:0}.lang-name{color:{{tc}}}.lang-pct{color:{{mu}};margin-left:auto}
  .contrib-row{display:flex;align-items:center;gap:6px;padding:3px 0;font-size:12px}
  .contrib-avatar{width:20px;height:20px;border-radius:50%;object-fit:cover}
  .contrib-name{color:{{tc}};font-weight:600;flex:1}.contrib-commits{color:{{mu}};font-size:11px}
  .rel-item{padding:3px 0;font-size:12px;display:flex;align-items:center;gap:6px}
  .rel-tag{font-family:ui-monospace,monospace;font-size:11px;color:{{lk}};font-weight:600}
  .rel-latest{font-size:9px;color:#fff;background:#3fb950;padding:0 4px;border-radius:2em}
  .rel-date{color:{{mu}};margin-left:auto;font-size:11px}
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
<div class="gh-header">
  <svg width="20" height="20" viewBox="0 0 16 16" fill="{{mu}}">{{I_FORK}}</svg>
  <span class="owner"><a href="https://github.com/{{name.split('/')[0]}}" style="color:{{mu}}">{{name.split('/')[0]}}</a></span><span class="sep">/</span>
  <a class="repo" href="{{url}}">{{name.split('/')[1]}}</a><span class="gh-badge">Public</span>
</div>
<div class="action-bar">
  <span class="act-btn"><svg viewBox="0 0 16 16">{{I_STAR}}</svg> Star</span><span class="act-btn act-count">{{stars}}</span>
  <span class="act-btn"><svg viewBox="0 0 16 16">{{I_FORK}}</svg> Fork</span><span class="act-btn act-count">{{forks}}</span>
  <span style="font-size:12px;color:{{mu}};margin-left:4px">{{watchers}} watching · {{issues}} issues</span>
</div>
<div class="tab-bar">
  <span class="tab active">Code</span>
  <span class="tab">Issues{% if issues %}<span class="count">{{issues}}</span>{% endif %}</span>
  <span class="tab">Pull requests</span><span class="tab">Actions</span>
</div>
<div class="main-body">
{% if files %}
<div class="branch-bar"><span class="branch-btn"><svg viewBox="0 0 16 16"><path d="M9.5 3.25a2.25 2.25 0 1 1 3 2.122V6A2.5 2.5 0 0 1 10 8.5H6a1 1 0 0 0-1 1v1.128a2.251 2.251 0 1 1-1.5 0V9.5A2.5 2.5 0 0 1 6 7h4a1 1 0 0 0 1-1v-.628A2.25 2.25 0 0 1 9.5 3.25Zm-6 0a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Zm8.25-.75a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5ZM4.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/></svg> {{branch}}</span><span style="font-size:12px;color:{{mu}}">{{files|length}} files</span></div>
<div class="file-table">
{% for f in files %}<div class="file-row"><span class="file-icon">{% if f.type=='dir' %}<svg viewBox="0 0 16 16"><path d="M1.75 1A1.75 1.75 0 0 0 0 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0 0 16 13.25v-8.5A1.75 1.75 0 0 0 14.25 3H7.5a.25.25 0 0 1-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1H1.75Z"/></svg>{% else %}<svg viewBox="0 0 16 16"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16H3.75A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"/></svg>{% endif %}</span><span class="file-name">{{f.name}}</span><span class="file-time">{% if f.type=='file' and f.size>0 %}{% if f.size>1024 %}{{ (f.size/1024)|round|int }} KB{% else %}{{f.size}} B{% endif %}{% endif %}</span></div>{% endfor %}
</div>
{% endif %}
{% if readme %}<div class="readme-box"><div class="readme-title">📄 README.md</div><div class="readme-body">{{readme|safe}}</div></div>{% endif %}
</div>
<div style="padding:0 24px 16px;display:flex;gap:12px;flex-wrap:wrap">
  <div class="about-box" style="flex:1;min-width:200px"><div class="about-title">About</div>{% if desc %}<div class="about-desc">{{desc}}</div>{% endif %}{% if topics %}<div class="about-topics">{% for t in topics %}<span class="about-topic">{{t}}</span>{% endfor %}</div>{% endif %}<div class="about-stat"><svg viewBox="0 0 16 16">{{I_STAR}}</svg> <strong>{{stars}}</strong> stars</div><div class="about-stat"><svg viewBox="0 0 16 16">{{I_FORK}}</svg> <strong>{{forks}}</strong> forks</div><div class="about-stat"><span style="width:14px;text-align:center">&#x1f441;</span> <strong>{{watchers}}</strong> watching</div></div>
  {% if langs %}<div class="about-box" style="flex:1;min-width:200px"><div class="about-title">Languages</div><div class="lang-bar">{% for l in langs %}<div style="width:{{l.pct}}%;height:8px;background:hsl({{(loop.index0*60+200)%360}},60%,55%)"></div>{% endfor %}</div>{% for l in langs %}<div class="lang-item"><span class="lang-dot" style="background:hsl({{(loop.index0*60+200)%360}},60%,55%)"></span><span class="lang-name">{{l.name}}</span><span class="lang-pct">{{l.pct}}%</span></div>{% endfor %}</div>{% endif %}
  {% if rels %}<div class="about-box" style="flex:1;min-width:150px"><div class="about-title">Releases</div>{% for r in rels %}<div class="rel-item"><span class="rel-tag">{{r.tag}}</span>{% if loop.first and not r.prerelease %}<span class="rel-latest">Latest</span>{% endif %}<span class="rel-date">{{r.date}}</span></div>{% endfor %}</div>{% endif %}
  {% if contribs %}<div class="about-box" style="flex:1;min-width:150px"><div class="about-title">Contributors</div>{% for c in contribs %}<div class="contrib-row"><img class="contrib-avatar" src="{{c.avatar}}" alt="" width="20" height="20"><span class="contrib-name">{{c.login}}</span><span class="contrib-commits">{{c.commits}}</span></div>{% endfor %}</div>{% endif %}
</div>
</body></html>"""

def _tv(th,sc):
    if th=="light": return {"bg":"#fff","cbg":"#f6f8fa","bc":"#d0d7de","tc":"#1f2328","mu":"#656d76","lk":"#0969da","cbg2":"#afb8c133","ico":"#d1242f","st":sc}
    return {"bg":"#0d1117","cbg":"#161b22","bc":"#30363d","tc":"#c9d1d9","mu":"#8b949e","lk":"#58a6ff","cbg2":"#1c2128","ico":"#ff7b72","st":sc}

# ═══════════════════════════════════════════
# API + Render
# ═══════════════════════════════════════════
def _ah(tok):
    h={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"test"}
    if tok: h["Authorization"]=f"Bearer {tok}"
    return h

async def _repo(cl,o,r,tok):
    """PR/Issue 精简 repo 信息"""
    rp=await cl.get(f"https://api.github.com/repos/{o}/{r}",headers=_ah(tok))
    print(f"[API] repo {rp.status_code}")
    if rp.status_code!=200: return None
    d=rp.json()
    return {"fn":d.get("full_name",f"{o}/{r}"),"st":_fc(d.get("stargazers_count",0)),"fk":_fc(d.get("forks_count",0))}

async def _repo_full(cl,o,r,tok):
    """仓库卡片综合信息"""
    h=_ah(tok)
    rp=await cl.get(f"https://api.github.com/repos/{o}/{r}",headers=h)
    print(f"[API] repo {rp.status_code}")
    if rp.status_code!=200: return None
    d=rp.json()
    # 并发请求
    tasks={
        "contents":     cl.get(f"https://api.github.com/repos/{o}/{r}/contents",headers=h),
        "readme":       cl.get(f"https://api.github.com/repos/{o}/{r}/readme",headers=h),
        "languages":    cl.get(f"https://api.github.com/repos/{o}/{r}/languages",headers=h),
        "contributors": cl.get(f"https://api.github.com/repos/{o}/{r}/contributors",headers=h,params={"per_page":5}),
        "releases":     cl.get(f"https://api.github.com/repos/{o}/{r}/releases",headers=h,params={"per_page":3}),
    }
    results={}
    for k,t in tasks.items():
        try: resp=await t; results[k]=resp; print(f"[API] {k} {resp.status_code}")
        except: pass
    files=[]
    if "contents" in results and results["contents"].status_code==200:
        for f in results["contents"].json()[:15]:
            files.append({"name":f.get("name",""),"type":f.get("type","file"),"size":f.get("size",0)})
    readme_html=""
    if "readme" in results and results["readme"].status_code==200:
        import base64
        try:
            rd=results["readme"].json(); content=base64.b64decode(rd.get("content","")).decode("utf-8","replace")
            readme_html=_md2html(content[:3000])
        except: pass
    langs=[]
    if "languages" in results and results["languages"].status_code==200:
        ld=results["languages"].json(); total=sum(ld.values()) or 1
        langs=sorted([{"name":k,"pct":round(v/total*100,1),"bytes":v} for k,v in ld.items()],key=lambda x:-x["pct"])[:6]
    contribs=[]
    if "contributors" in results and results["contributors"].status_code==200:
        for c in results["contributors"].json()[:5]:
            contribs.append({"login":c.get("login",""),"avatar":c.get("avatar_url",""),"commits":c.get("contributions",0)})
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

async def _tl_api(cl,o,r,n,tok):
    rp=await cl.get(f"https://api.github.com/repos/{o}/{r}/issues/{n}/timeline",headers=_ah(tok),params={"per_page":60})
    n_ev=len(rp.json()) if rp.status_code==200 else 0
    print(f"[API] timeline {rp.status_code} ({n_ev} events)")
    if rp.status_code!=200: return []
    try: return _process_timeline(rp.json())
    except Exception as e: print(f"[WARN] tl: {e}"); import traceback; traceback.print_exc(); return []

async def _commits_api(cl,o,r,n,tok):
    """获取 PR commit 列表并转为 timeline 条目"""
    rp=await cl.get(f"https://api.github.com/repos/{o}/{r}/pulls/{n}/commits",headers=_ah(tok),params={"per_page":40})
    print(f"[API] commits {rp.status_code} ({len(rp.json()) if rp.status_code==200 else 0} commits)")
    if rp.status_code!=200: return []
    commits=[]
    for c in rp.json():
        sha=c.get("sha",""); cmt=c.get("commit",{}) or {}
        author=c.get("author") or {}
        dt_str=cmt.get("committer",{}).get("date","") or cmt.get("author",{}).get("date","")
        commits.append({
            "_badge":"commit","_type":"commit","actor":author.get("login","unknown"),
            "avatar":author.get("avatar_url",""),"action":"committed",
            "time":_rt(_pts(dt_str)) if dt_str else "","is_bot":False,
            "sha":sha[:7] if sha else "","cmt_url":c.get("html_url",""),
            "msg":cmt.get("message","").split("\n")[0][:140],
        })
    return commits

def _merge(tl_events, commits):
    non_commit=[e for e in tl_events if e.get("_type")!="commit"]
    result=list(non_commit)
    if commits:
        # 找到 force-push 或 closed 事件作为插入锚点
        anchor=None
        for i,e in enumerate(result):
            if e.get("_badge")=="push" or e.get("action","").startswith("force-pushed"):
                anchor=("push",i); break
        if not anchor:
            for i,e in enumerate(result):
                if e.get("action","") in("closed","merged","reopened"):
                    anchor=("close",i); break
        if anchor:
            _,idx=anchor
            for c in reversed(commits): result.insert(idx,c)
        else:
            result.extend(commits)
    return result

async def _issue(cl,o,r,n,tok):
    rp=await cl.get(f"https://api.github.com/repos/{o}/{r}/issues/{n}",headers=_ah(tok))
    print(f"[API] issue  {rp.status_code}")
    if rp.status_code==404: return None
    if rp.status_code in(403,429): raise RuntimeError(f"rate limit ({rp.status_code})")
    if rp.status_code>=400: raise RuntimeError(f"API {rp.status_code}: {rp.text[:200]}")
    d=rp.json(); is_pr="pull_request" in d
    rt=asyncio.create_task(_repo(cl,o,r,tok))
    tt=asyncio.create_task(_tl_api(cl,o,r,n,tok))
    ct=asyncio.create_task(_commits_api(cl,o,r,n,tok)) if is_pr else None
    pt=None
    if is_pr:
        pr=d.get("pull_request"); pu=pr.get("url") if isinstance(pr,dict) else None
        if pu: pt=asyncio.create_task(cl.get(pu,headers=_ah(tok)))
    repo=await rt; tl_events=await tt; commits=await ct if ct else []
    tl=_merge(tl_events, commits)
    ma,gs=None,None
    pr=d.get("pull_request")
    if isinstance(pr,dict) and pr.get("merged_at"): ma=_pts(pr["merged_at"])
    if pt:
        pr_r=await pt
        if pr_r.status_code==200:
            pd=pr_r.json()
            if not ma and pd.get("merged_at"): ma=_pts(pd["merged_at"])
            gs={"c":pd.get("commits",0),"a":pd.get("additions",0),"d":pd.get("deletions",0),"f":pd.get("changed_files",0)}
    return {"title":d.get("title",""),"body":d.get("body") or "","state":d.get("state","unknown"),
            "author":d["user"]["login"] if d.get("user") else "unknown",
            "av":d["user"]["avatar_url"] if d.get("user") else "",
            "labels":[{"name":lb["name"],"color":lb["color"],"tc":_tc(lb.get("color","ffffff"))} for lb in(d.get("labels") or[])],
            "ca":_pts(d["created_at"]),"url":d.get("html_url",""),"num":d.get("number",n),
            "is_pr":is_pr,"ma":ma,"repo":repo,"tl":tl,"gs":gs}

def _html(d,th):
    from jinja2 import Template
    tpl=Template(_T)
    merged=d.get("ma") is not None
    st_text,st_class,st_svg,st_hex=_si(d["state"],merged)
    v=_tv(th,f"#{st_hex}")
    return tpl.render(
        bg=v["bg"],cbg=v["cbg"],bc=v["bc"],tc=v["tc"],mu=v["mu"],lk=v["lk"],
        cbg2=v["cbg2"],ico=v["ico"],st=v["st"],st_text=st_text,st_class=st_class,st_svg=st_svg,
        num=d["num"],title=d["title"],url=d["url"],author=d["author"],av=d["av"],
        ca=d["ca"].strftime("%Y-%m-%d %H:%M UTC"),labels=d.get("labels",[]),
        body=_md2html(d.get("body") or ""),repo=d.get("repo"),timeline=d.get("tl",[]),
        I_FORK=I_FORK,I_STAR=I_STAR,I_GIT_COMMIT=I_GIT_COMMIT,I_TAG=I_TAG,
        I_CROSS_REF=I_CROSS_REF,I_EYE=I_EYE,I_CHECK=I_CHECK,I_PULL_CLOSED=I_PULL_CLOSED,
        I_REPO_PUSH=I_REPO_PUSH,I_GIT_MERGE=I_GIT_MERGE,I_PULL_REQ=I_PULL_REQ,
    )

def _html_repo(d, th):
    from jinja2 import Template
    tpl = Template(_REPO_T)
    v = _tv(th, "#3fb950")
    rels_fmt = []
    for r in d.get("rels", []):
        pub = r.get("published")
        rels_fmt.append({**r, "date": pub.strftime("%b %d, %Y") if pub else ""})
    return tpl.render(
        bg=v["bg"], cbg=v["cbg"], bc=v["bc"], tc=v["tc"], mu=v["mu"], lk=v["lk"],
        name=d["fn"], desc=d.get("desc", ""), url=f"https://github.com/{d['fn']}",
        stars=d.get("st", "0"), forks=d.get("fk", "0"), watchers=d.get("watchers", "0"),
        issues=str(d.get("issues", 0)), topics=d.get("topics", []),
        branch=d.get("default_branch", "main"),
        readme=d.get("readme", ""), files=d.get("files", []),
        langs=d.get("langs", []), contribs=d.get("contribs", []),
        rels=rels_fmt,
        I_FORK=I_FORK, I_STAR=I_STAR,
    )

async def _png(html,out):
    from playwright.async_api import async_playwright as _pw2
    print(f"[PNG] rendering…")
    async with _pw2() as p:
        b=await p.chromium.launch(headless=True,args=["--disable-gpu","--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"])
        try:
            pg=await b.new_page(viewport={"width":800,"height":600})
            await pg.set_content(html,wait_until="networkidle"); await pg.wait_for_timeout(500)
            await pg.screenshot(path=out,full_page=True)
            print(f"[PNG] ✅ {out} ({os.path.getsize(out)/1024:.1f} KB)")
        finally: await b.close()

def _summary(d):
    merged=d.get("ma") is not None; st_text,*_=_si(d["state"],merged)
    print(); print("="*60)
    if d.get("repo"): r=d["repo"]; print(f"  📦 {r['fn']}  ⭐ {r['st']}  fork {r['fk']}")
    print(f"  {st_text}  #{d['num']} — {d['title']}")
    print(f"  Author: {d['author']}  |  {'PR' if d['is_pr'] else 'Issue'}")
    print(f"  Created: {d['ca'].strftime('%Y-%m-%d %H:%M UTC')}")
    if merged: print(f"  Merged: {d['ma'].strftime('%Y-%m-%d %H:%M UTC')}")
    if d.get("labels"): print(f"  Labels: {', '.join(lb['name'] for lb in d['labels'])}")
    if d.get("gs"): gs=d["gs"]; print(f"  +{gs['a']} -{gs['d']}  {gs['c']}c  {gs['f']}f")
    if d.get("tl"): print(f"  Timeline: {len(d['tl'])} events")
    print(f"  URL: {d['url']}")
    body=d.get("body") or ""
    if body: print(f"  Preview: {body[:120].replace(chr(10),' ')}{'…' if len(body)>120 else ''}")
    print("="*60); print()

# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════
def parse_args():
    p=argparse.ArgumentParser(description="GitHub PR/Issue 本地测试",formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例: %(prog)s --url https://github.com/owner/repo/pull/1 --token ghp_xxx")
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--url","-u",type=str,help="GitHub PR/Issue URL")
    g.add_argument("--repo","-r",type=str,help="owner/repo")
    p.add_argument("--number","-n",type=int,help="PR/Issue 编号")
    p.add_argument("--token","-t",type=str,default="",help="GitHub Token")
    p.add_argument("--theme",type=str,choices=["dark","light"],default="dark")
    p.add_argument("--output","-o",type=str,default="",help="输出 PNG")
    p.add_argument("--timeout",type=float,default=15.0)
    p.add_argument("--no-png",action="store_true",help="跳过 PNG")
    return p.parse_args()

async def main():
    args=parse_args()
    is_repo=False; is_pr=False
    if args.url:
        pr=_pu(args.url)
        if pr: o,r,n=pr; is_pr=True
        else:
            rp=_parse_repo(args.url)
            if rp: o,r=rp; is_repo=True
            else: print(f"❌ parse fail: {args.url}"); sys.exit(1)
    elif args.repo:
        if "/" not in args.repo or args.repo.count("/")!=1: print(f"❌ bad: {args.repo}"); sys.exit(1)
        o,r=args.repo.split("/")
        if args.number: n=args.number; is_pr=True
        else: is_repo=True
    else: print("❌ --repo or --url required"); sys.exit(1)
    if is_repo:
        print(f"\n🎯 Repo: {o}/{r}  theme={args.theme}  token={'yes' if args.token else 'no'}\n")
        if not args.no_png and not _pw_ok:
            print("❌ playwright/chromium missing. Run: playwright install chromium"); sys.exit(1)
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(args.timeout)) as cl:
            try: d=await _repo_full(cl,o,r,args.token)
            except Exception as e: print(f"\n❌ {e}"); import traceback; traceback.print_exc(); sys.exit(1)
        if d is None: print(f"\n❌ not found"); sys.exit(1)
        print(f"\n{'='*60}")
        print(f"  📦 {d['fn']}")
        if d.get("desc"): print(f"  {d['desc']}")
        print(f"  ⭐ {d['st']}  🍴 {d['fk']}  👁 {d['watchers']}  📌 {d['issues']}")
        if d.get("topics"): print(f"  Topics: {', '.join(d['topics'])}")
        print(f"  🔤 {d.get('lang','')}  📄 {d.get('license','')}  🌿 {d.get('default_branch','')}")
        print(f"{'='*60}\n")
        h=_html_repo(d,args.theme)
        hp=Path(f"{o}_{r}_repo_debug.html"); hp.write_text(h,encoding="utf-8"); print(f"[HTML] {hp}")
        if not args.no_png:
            out=args.output or f"{o}_{r}_repo_{int(time.time())}.png"
            try: await _png(h,out); print(f"\n✅ {Path(out).resolve()}")
            except Exception as e: print(f"\n❌ PNG: {e}"); sys.exit(1)
        else: print(f"\n✅ → {hp.resolve()}")
    else:
        print(f"\n🎯 {o}/{r}#{n}  theme={args.theme}  token={'yes' if args.token else 'no'}\n")
        if not args.no_png and not _pw_ok:
            print("❌ playwright/chromium missing. Run: playwright install chromium")
            print("   or use --no-png"); sys.exit(1)
        import httpx
        async with httpx.AsyncClient(timeout=httpx.Timeout(args.timeout)) as cl:
            try: d=await _issue(cl,o,r,n,args.token)
            except Exception as e: print(f"\n❌ {e}"); import traceback; traceback.print_exc(); sys.exit(1)
        if d is None: print(f"\n❌ not found"); sys.exit(1)
        _summary(d)
        h=_html(d,args.theme)
        hp=Path(f"{o}_{r}_#{n}_debug.html"); hp.write_text(h,encoding="utf-8"); print(f"[HTML] {hp}")
        if not args.no_png:
            out=args.output or f"{o}_{r}_#{n}_{int(time.time())}.png"
            try: await _png(h,out); print(f"\n✅ {Path(out).resolve()}")
            except Exception as e: print(f"\n❌ PNG: {e}"); sys.exit(1)
        else: print(f"\n✅ → {hp.resolve()}")

if __name__=="__main__": asyncio.run(main())
