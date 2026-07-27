# GitHub Fetch 预览卡片

自动识别 AstrBot 消息中的 GitHub Issue/PR 链接及 `#issue` 编号，通过 REST API + Jinja2 渲染生成类 GitHub 时间线预览卡片图片。

## 特性

- **零 DOM 依赖** — 使用 GitHub REST API (`httpx`) 获取数据，不访问 `github.com` 页面
- **类 GitHub 时间线** — 模仿 GitHub 网页端的 Timeline 布局，包含 commit、label、cross-reference、review 等事件节点
- **Octicon SVG 图标** — 使用 GitHub 官方 Octicon 路径，与官方 UI 视觉一致
- **双主题** — 深色模式（GitHub Dark）和浅色模式
- **仓库信息栏** — 展示 ⭐ Star / Fork 数量
- **Markdown + HTML** — 完整渲染 PR body，支持 `<details>`/`<summary>`/`<table>`/`<kbd>` 等标签
- **自动安装依赖** — 启动时检测缺失的 pip 包并自动 `pip install`，包括 `playwright install chromium`
- **文本降级** — 无 Chromium 时自动输出 Markdown 文本摘要
- **内存缓存** — TTL 可配，避免短时间重复 API 请求
- **GitHub Token** — 可选配置，提升速率限制（匿名 60 req/h → 认证 5000 req/h）

## 效果预览

```
📦  MaaAssistantArknights/MaaAssistantArknights   ⭐ 14.2k   fork 3.1k
┌─────────────────────────────────────────────────────────┐
│ [pull-request icon] Open    #17302                      │
│ feat(roguelike): add optional tutorial overlay...       │
│                                                         │
│ ## Summary                                              │
│ - Add an Auto Roguelike advanced setting...             │
│                                                         │
│ ── Timeline ─────────────────────────────────────────── │
│ [commit] feat(roguelike): add optional...    967e5f6    │
│ [tag]    github-actions Bot added labels    2 weeks ago │
│ [ref]    crazysmile-PhD mentioned #16798               │
│          fix(roguelike): 教學遮罩  [Closed]             │
│ [eye]    sourcery-ai Bot reviewed           2 weeks ago │
│          ┌──────────────────────────────────┐           │
│          │ Hey - I've reviewed your changes │           │
│          └──────────────────────────────────┘           │
│                                                         │
│ [avatar] crazysmile-PhD  created 2026-07-08             │
└─────────────────────────────────────────────────────────┘
```

## 安装

### 自动安装（推荐）

插件启动时自动安装所有缺失依赖，无需手动操作。

### 手动安装

```bash
pip install httpx jinja2 playwright cachetools
playwright install chromium
```

## 配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `github_token` | string | - | GitHub Personal Access Token（可选，提高速率限制） |
| `default_repo` | string | - | 默认仓库 `owner/repo`，处理 `#12345` 引用时使用 |
| `enable_url_fetch` | bool | true | 是否响应 GitHub URL |
| `enable_issue_fetch` | bool | true | 是否响应 `#xxxxx` 引用 |
| `theme` | string | dark | 渲染主题 `dark` / `light` |
| `cache_ttl` | int | 300 | API 缓存有效期（秒），0 禁用 |
| `timeout` | int | 30000 | API 请求超时（毫秒） |

## 使用

### 触发方式

| 触发 | 示例 | 说明 |
|------|------|------|
| PR URL | `https://github.com/microsoft/vscode/pull/204590` | 自动识别并渲染 PR 卡片 |
| Issue URL | `https://github.com/torvalds/linux/issues/1234` | 自动识别并渲染 Issue 卡片 |
| `#number` 引用 | `#42` | 需配置 `default_repo`，自动拼接为完整 URL |

### 本地测试 (test_local.py)

#### Token 配置

按优先级依次尝试：`--token` > `--token-file` > 环境变量 `GITHUB_TOKEN` > 默认文件 `./token.txt` > `~/.github_token.txt`

```bash
# 方式 1: 命令行直接传入
python test_local.py --url "..." --token ghp_xxx

# 方式 2: 从文件读取（推荐，避免 token 出现在 shell 历史中）
echo "ghp_xxx" > token.txt
python test_local.py --url "..." --token-file token.txt

# 方式 3: 环境变量
export GITHUB_TOKEN=ghp_xxx
python test_local.py --url "..."

# 方式 4: 默认文件（自动检测 ./token.txt）
python test_local.py --url "..."
```

> **安全提示**: 建议使用 GitHub Fine-grained Token，仅授予 `public_repo` 只读权限。

#### 参数说明

| 参数 | 简写 | 说明 |
|------|------|------|
| `--url` | `-u` | GitHub 链接（PR/Issue/仓库/Release） |
| `--repo` | `-r` | `owner/repo` 格式，配合 `--number` 或单独使用 |
| `--number` | `-n` | PR/Issue 编号，与 `--repo` 配合 |
| `--token` | `-t` | GitHub Token |
| `--token-file` | `-f` | 从文件读取 Token |
| `--theme` | | `dark` (默认) / `light` |
| `--resolution` | | `1x` / `2x` (默认) / `3x` |
| `--output` | `-o` | 自定义输出 PNG 路径 |
| `--no-png` | | 仅生成调试 HTML，不渲染 PNG |
| `--timeout` | | API 超时秒数（默认 15） |

#### 使用示例

```bash
# PR 预览
python test_local.py -u "https://github.com/microsoft/vscode/pull/204590" -t ghp_xxx

# Issue 预览（通过仓库+编号）
python test_local.py -r AstrBotDevs/AstrBot -n 42

# 仓库主页预览
python test_local.py -u "https://github.com/torvalds/linux" -t ghp_xxx
python test_local.py -r torvalds/linux

# Release 页面预览
python test_local.py -u "https://github.com/astral-sh/uv/releases/tag/0.5.0"

# 浅色主题 + 3x 分辨率
python test_local.py -u "..." --theme light --resolution 3x

# 仅生成 HTML 调试文件（无需 Chromium）
python test_local.py -u "..." --no-png
```

#### 输出文件

每次运行在当前目录生成：

| 文件 | 格式 | 说明 |
|------|------|------|
| `{owner}_{repo}_#{n}_debug.html` | HTML | PR/Issue 调试文件，可直接用浏览器打开 |
| `{owner}_{repo}_#{n}_{ts}.png` | PNG | 渲染后的预览图片 |
| `{owner}_{repo}_repo_debug.html` | HTML | 仓库卡片调试文件 |
| `{owner}_{repo}_repo_{ts}.png` | PNG | 仓库卡片预览图片 |

## 架构

```
消息触发
  │
  ├─ @filter.regex(GITHUB_ANY_URL_PATTERN)  →  on_github_url()
  └─ @filter.regex(ISSUE_REF_PATTERN)       →  on_issue_ref()
        │
        ▼
  fetch_issue_data()
    ├── GET /repos/{owner}/{repo}/issues/{n}     (主数据)
    ├── GET /repos/{owner}/{repo}                (仓库 stats)
    ├── GET /repos/{owner}/{repo}/issues/{n}/timeline  (时间线事件)
    └── GET /repos/{owner}/{repo}/pulls/{n}      (PR 详情)
        │
        ▼
  render_html()
    ├── simple_markdown_to_html()    (body 渲染)
    ├── _process_timeline_events()   (时间线结构化)
    └── Jinja2 Template.render()     (HTML 卡片)
        │
        ▼
  html_to_png()
    └── Playwright page.setContent(html)  (本地渲染，零网络请求)
        │
        ▼
  event.image_result(png_path)       (返回图片)
```

## 依赖

| 包 | 用途 |
|----|------|
| `httpx` | 异步 HTTP 客户端，访问 GitHub REST API |
| `jinja2` | HTML 模板渲染 |
| `playwright` | HTML → PNG 转换 (`page.setContent`, 不加载外部资源) |
| `cachetools` | TTL 内存缓存（可选，有内置回退） |

## 许可

MIT
