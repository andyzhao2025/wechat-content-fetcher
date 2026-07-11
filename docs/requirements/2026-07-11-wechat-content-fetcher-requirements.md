# wechat-content-fetcher 需求文档

**日期**: 2026-07-11  
**项目**: `wechat-content-fetcher`

## 1. 背景

用户需要将腾讯 IMA 知识库中指定目录下收藏的微信公众号文章，稳定导出为可长期托管的静态网页资源，并进一步组织为适合 NotebookLM 读取的网页入口和 bundle 页面。系统需要支持日常增量同步、配额受限下的跨天续跑，以及 GitHub Pages 等静态站点发布。

该能力最终需要作为 OpenClaw 中的一个可调用 skill 部署，后续运行环境以树莓派上的 OpenClaw 为主。

## 2. 目标

构建一个可部署、可重复执行、可恢复的内容抓取与发布链路，使用户可以：

1. 从 IMA 指定知识库目录读取公众号文章条目
2. 为每篇文章生成独立 HTML 页面
3. 为目录生成索引页和 NotebookLM bundle 页面
4. 将生成结果发布到 GitHub Pages 或独立静态站点
5. 在 IMA API 配额限制下分多天逐步补齐全量内容
6. 通过 OpenClaw 的定时任务实现自动同步

## 3. 适用范围

### 3.1 包含

- IMA 目录元数据读取
- 微信公众号正文抓取
- 单篇文章页面生成
- 目录索引页面生成
- NotebookLM bundle 页面生成
- GitHub Pages 发布产物构建
- 增量同步、断点续跑、月度审计
- OpenClaw skill 形式运行

### 3.2 不包含

- 向 IMA 写回内容
- 在 GitHub Actions 中直接访问 IMA
- NotebookLM 平台本身的自动导入
- 多用户权限系统

## 4. 角色

- **最终用户**：通过微信/OpenClaw 触发同步、查看结果、通知手动改动
- **OpenClaw 定时任务**：每天自动执行同步
- **IMA OpenAPI**：提供知识库目录和文章链接元数据
- **微信公众号内容抓取器**：基于 `url-md` 获取正文
- **GitHub Pages**：托管静态页面输出

## 5. 功能需求

### 5.1 IMA 目录读取

系统必须支持：

- 指定 `knowledge_base_id + folder_id` 作为同步目标
- 递归读取目标目录下文章条目
- 从 IMA 返回结果中提取微信公众号文章链接
- 识别文章新增、删除、分组变化和标题变化

### 5.2 文章抓取与渲染

系统必须支持：

- 使用文章链接抓取正文
- 将每篇文章渲染为独立 HTML 页面
- 为页面分配稳定文件名
- 镜像必要图片资源到本地输出目录

### 5.3 索引与 Bundle

系统必须支持：

- 为每个目标目录生成 `index.html`
- 为整个站点生成根索引页
- 生成 NotebookLM 可读的 bundle 页面
- 输出 `manifest.json` 与 `notebooklm-urls.txt`

### 5.4 增量同步

系统必须支持三类同步原因：

- `scheduled_daily`
- `manual`
- `monthly_audit`

行为要求：

- `scheduled_daily` 在指纹未变化且无待处理 backlog 时可跳过
- `manual` 可强制重跑
- `monthly_audit` 可全量重建

### 5.5 配额受限与跨天续跑

系统必须支持：

- IMA API 配额耗尽时不崩溃退出
- 将本轮未完成文章记录到 `pending_article_ids`
- 下一次 `scheduled_daily` 同步时优先处理 backlog
- 当 backlog 未清空时，新发现文章不得插队抓取
- backlog 清空后，再处理新增文章

### 5.6 发布

系统必须支持：

- 构建 GitHub Pages 发布目录 `site_output/_pages/`
- 在配额耗尽且没有新增页面时跳过发布
- 避免把空目录或不完整结果推送到 GitHub Pages

### 5.7 OpenClaw 集成

系统必须支持：

- 作为 OpenClaw skill 安装到 `workspace/skills/wechat-content-fetcher`
- 通过本地命令确定性执行，不依赖自然语言临时拼装 shell 流程
- 可由 OpenClaw cron 定时调用

## 6. 非功能需求

### 6.1 稳定性

- 同步命令必须支持多次重复执行
- 同步中断后必须可从状态文件恢复
- 配额耗尽必须返回可识别的 `partial` 状态

### 6.2 可观测性

- 必须保存每次运行的 run log
- 必须记录：
  - 开始/结束时间
  - 同步原因
  - 运行状态
  - 配额耗尽情况
  - backlog 状态

### 6.3 可迁移性

- 必须可从 Git 仓库直接部署
- 运行依赖必须尽量简单：
  - Python 3.10+
  - Node.js
  - `url-md`
- 必须支持部署到树莓派 Linux 环境

### 6.4 安全性

- IMA 凭证只保存在本地环境
- 凭证不得写入 Git 仓库
- GitHub Pages 发布流程不得暴露 IMA API key

## 7. 外部依赖

- 腾讯 IMA OpenAPI
- `ima-skill/ima_api.cjs`
- `url-md`
- Python 包：
  - `markdown`
  - `PyYAML`
- GitHub 仓库与 Pages

## 8. 输入输出

### 8.1 输入

- IMA 凭证：`client_id`、`api_key`
- 目标配置：知识库 ID、目录 ID、目录名称
- 同步原因：`scheduled_daily` / `manual` / `monthly_audit`

### 8.2 输出

- 单篇文章 HTML
- 目录索引页
- 站点根索引页
- NotebookLM bundle 页面
- `site_output/_pages/`
- 本地状态文件和运行日志

## 9. 运行方式

典型命令：

```bash
python run_fetcher.py --config config.ima.json --mode ima --reason scheduled_daily --ima-script ~/.openclaw-ima/workspace/skills/ima-skill/ima_api.cjs
python run_fetcher.py --config config.ima.json --mode pages
```

## 10. 验收标准

当以下条件同时满足时，视为需求达成：

1. 能从 IMA 目标目录读取到公众号文章列表
2. 能为文章生成独立 HTML 和目录索引
3. 能生成 NotebookLM bundle 页面
4. 在 IMA 配额耗尽时返回 `partial` 而非异常退出
5. 后续定时任务能继续清理 backlog，直到目录补齐
6. 发布过程不会因不完整同步而破坏 GitHub Pages
7. 树莓派上的 OpenClaw 可以通过 Git 仓库安装并执行该 skill
