---
name: wechat-content-fetcher
description: Use when exporting WeChat article links from Tencent IMA knowledge-base folders into a static website for NotebookLM or other crawlers.
---

# wechat-content-fetcher

将腾讯 IMA 指定文件夹中的微信公众号条目同步为静态站点。

## 能力边界

- 从 IMA 知识库文件夹读取公众号文章条目
- 为每篇文章生成单独 HTML 页面
- 按文件夹生成目录页
- 比较状态文件，增量更新目录和文章页
- 输出适合 GitHub Pages 或独立静态站点部署的目录

## 当前执行方式

先使用 `fixture` 模式验证整条链路：

```bash
python run_fetcher.py --config config.example.json --mode fixture
```

站点会输出到 `site_output/`。

## 真实 IMA 接入说明

真实模式将依赖腾讯 IMA OpenAPI：

- `search_knowledge_base`
- `get_knowledge_list`
- `search_knowledge`
- `get_media_info`

本机当前已检测到 `~/.config/ima/client_id` 和 `~/.config/ima/api_key`，但实际请求返回：

```json
{"code":200002,"msg":"skill auth failed","data":{}}
```

这表示当前凭证未通过该 skill 通道授权校验。在权限确认前，使用 `fixture` 模式验证本地生成逻辑。

## 微信内容抓取方法

公众号正文抓取复用 `qiaomu-anything-to-notebooklm` 同源方案：

- 使用 `url-md md <weixin_url>` 获取 frontmatter + Markdown
- 解析 `title`、`author`、`publish_time`、`cover_url`
- 渲染为独立 HTML 页面

## 发布

生成后的 `site_output/` 可以部署到：

- GitHub Pages
- 任意静态站点托管
