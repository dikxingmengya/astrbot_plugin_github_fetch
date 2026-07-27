# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] — 2026-07

### Added

- **全新架构**: Playwright 网页截图 → GitHub REST API + Jinja2 模板渲染
  - 数据获取: httpx 异步调用 GitHub REST API
  - 模板渲染: Jinja2 内联模板，模仿 GitHub 网页端布局
  - HTML→PNG: Playwright `page.setContent()` 本地渲染，零外部网络请求
- **自动安装依赖**: 启动时检测缺失的 pip 包并自动 `pip install`，包括 `playwright install chromium`
- **PR/Issue 预览卡片**: 状态 badge + Markdown body + GitHub Timeline（commits/labels/reviews/cross-references）
- **仓库主页卡片**: 文件列表 + README + 语言柱状图 + Contributors + Releases
- **Release 页面卡片**: 版本信息 + Release Notes + Assets 列表 + 按 release 区间统计的 Contributors
- **GitHub Octicon SVG**: 全部使用 GitHub 官方 16px Octicon 路径，状态图标包括 open/closed/merged 三色
- **HTML 标签透传**: Markdown 中嵌入的 `<details>` / `<summary>` / `<table>` / `<kbd>` 等标签原样保留
- **Markdown 增强**: 支持表格、task-list (`- [ ]`)、嵌套列表、代码块
- **分辨率设置**: 支持 1x/2x/3x 渲染，使用 `device_scale_factor` 提高输出清晰度
- **Token 文件支持**: test_local.py 支持 `--token-file`、环境变量 `GITHUB_TOKEN`、默认文件 `token.txt`
- **标签合并**: 同一用户连续添加多个 label 的事件自动合并
- **GitHub 风格时间格式**: 一周内显示相对时间，超过显示 `on Jun 15`
- **文本降级**: 无 Chromium 时自动降级为 Markdown 文本摘要
- **本地测试脚本** (`test_local.py`): 支持 PR/Issue/仓库主页/Release 四种场景

### Changed

- **数据源**: 从 Playwright 截取 GitHub 页面 → 调用 GitHub REST API
- **渲染方式**: 从截图 DOM 元素 → Jinja2 模板自主渲染 HTML
- **插件类名**: `GitHubFetchPlugin`，注册名 `astrbot_plugin_github_fetch`
- **配置项精简**: 移除 `screenshot_full_page`、`proxy_enabled`、`proxy_preset`、`proxy_url`

### Removed

- Playwright 反检测 JS hack（不再需要绕过 Cloudflare）
- Chromium 特权参数中的 `--disable-blink-features` 等
- `requirements.txt`（改为自动安装）
- `pyppeteer` 支持（统一使用 Playwright）

---

## [1.0.0] — 2026-06

### Added

- 初始 Playwright 截图方案
- Cloudflare 反拦截功能
- GitHub 代理配置
- 基础 URL 解析和页面截图功能
