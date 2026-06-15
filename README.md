# astrbot_plugin_github_fetch

AstrBot 插件：自动识别消息中的 GitHub 链接和 `#issue` 编号，截图并返回页面图片。

## 功能

- 🔗 **GitHub 链接自动截图** — 发送包含 GitHub URL 的消息时，自动截图并返回
- 🔢 **#issue 快捷查询** — 发送 `#12345` 时，在配置的默认仓库中查找对应 Issue/PR 并截图
- 🖼️ **支持多种页面** — 仓库首页、Issue、PR、文件、目录、提交、Release 等
- ⚙️ **可视化配置** — 通过 AstrBot WebUI 即可完成所有配置，无需手动编辑文件

## 安装

### 1. 安装插件

将本插件目录放入 AstrBot 的 `data/plugins/` 目录下。

### 2. 安装依赖

```bash
pip install playwright
playwright install chromium
```

> ⚠️ **重要**: `playwright install chromium` 会下载一个独立的 Chromium 浏览器（约 150MB），用于截图。这一步必须执行。

### 3. 重启 AstrBot

重启 AstrBot 后，插件将自动加载。

## 配置

在 AstrBot WebUI 的「插件配置」中找到「GitHub Fetch 截图」即可进行可视化配置。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `github_token` | string | (空) | GitHub Personal Access Token，用于访问私有仓库和提高频率限制 |
| `default_repo` | string | (空) | 默认仓库（格式: `owner/repo`），用于 `#xxxxx` 查询 |
| `enable_url_fetch` | bool | true | 是否启用 GitHub URL 自动截图 |
| `enable_issue_fetch` | bool | true | 是否启用 `#xxxxx` 自动截图 |
| `screenshot_full_page` | bool | true | 是否截取整个页面（false 则仅截取可视区域） |
| `timeout` | int | 30000 | 页面加载超时时间（毫秒） |

## 使用示例

### GitHub URL 截图

在聊天中发送任意 GitHub URL，机器人将自动截图回复：

```
你: https://github.com/AstrBotDevs/AstrBot
Bot: 🔍 正在截图 GitHub 页面...
    [图片: AstrBot 仓库首页截图]
```

支持以下类型的 URL：
- 仓库首页: `https://github.com/owner/repo`
- Issue: `https://github.com/owner/repo/issues/123`
- Pull Request: `https://github.com/owner/repo/pull/123`
- 文件: `https://github.com/owner/repo/blob/main/src/file.py`
- 目录: `https://github.com/owner/repo/tree/main/src`
- 提交: `https://github.com/owner/repo/commit/abc123f`
- Release: `https://github.com/owner/repo/releases/tag/v1.0.0`

### #issue 快捷查询

先配置 `default_repo`（例如 `AstrBotDevs/AstrBot`），然后在聊天中：

```
你: 看下 #6140
Bot: 🔍 正在获取 AstrBotDevs/AstrBot#6140 的截图...
    [图片: Issue #6140 截图]
```

> GitHub 会自动将 PR 内部的编号映射到 Issue 路径，所以 `#xxxxx` 对 Issue 和 PR 均有效。

## 已知限制

- **不支持 GitHub Enterprise** — 仅匹配 `github.com` 域名，企业私有部署暂不支持
- **#issue + URL 共存** — 当消息中同时包含完整 GitHub URL 和 `#xxxxx` 时，仅处理 URL，`#xxxxx` 会被跳过（避免重复截图）
- **每条消息最多 3 个 URL** — 超过限制的 URL 会被忽略
- **首次截图较慢** — Playwright 需要启动浏览器，首次截图可能需要 5~10 秒
- **需要 Chromium** — 依赖 Playwright 的独立 Chromium，约 150MB 磁盘空间

## 故障排除

### 插件加载但截图失败

1. 确认已安装 Playwright: `pip show playwright`
2. 确认已安装 Chromium: `playwright install chromium`
3. 如果在 Docker 中运行，确保容器有足够的内存（建议 ≥ 512MB）

### 截图速度慢

- 可以调小 `timeout` 配置（如 15000 即 15 秒）
- 关闭 `screenshot_full_page` 可以减少截图文件体积和处理时间

### 私有仓库返回 404 截图

- 在配置中填入有效的 `github_token`
- 确保 Token 有对应仓库的访问权限

## 许可

本项目基于原模板仓库的 LICENSE 发布。
