# PhD Advisor Agent

持续发现和复核美国高校机器学习、深度学习、统计学习方向 PhD 导师的开源 Agent。它保存每条结论的来源链接，不把“可能招生”冒充为“确认招生”，默认不发送邮件。

## 能力

- 导入带排名年份和来源的学校、CS/Statistics 院系清单；
- 从院系目录自动发现教师主页；
- 提取姓名、职称、邮箱、研究文本和招生线索；
- 通过规范化姓名和学校去重；
- 保存网页版本并检测内容变化；
- 失败指数退避、超时、并发、页面大小和最大重试限制；
- 规则初筛 + 可选 OpenAI 模型证据核验；
- 单次模型调用数和估算费用上限；
- 人工审核队列、匹配评分、CSV 和周报；
- 本地管理界面、Docker、Render Blueprint 和 GitHub Actions。

## 数据限制

US News 排名会更新且完整榜单可能受许可限制。仓库不会伪造或内置未经核验的“前100”。请把你合法取得的榜单填入 `input/schools.csv`，并保留 `ranking_source` 和 `ranking_year`。只有提供真实院系 URL 的学校可在无搜索 API 的情况下被扫描。

格式：

```csv
rank,school,department,department_url,website,ranking_source,ranking_year
1,Example University,Computer Science,https://example.edu/cs/faculty,example.edu,US News,2026
```

## 本地运行

Windows + Codex 用户可双击 `start_dashboard.bat`。命令行方式：

```powershell
python agent.py init
python agent.py run
python agent.py export
python agent.py serve
```

界面默认位于 `http://127.0.0.1:8765/`。

## 持续运行

本地每周循环：

```powershell
python agent.py scheduler
```

Docker：

```powershell
docker compose up -d --build
```

GitHub Actions 每周一运行一次并上传结果。云端可使用 `render.yaml` 创建带持久磁盘的 Web 服务；同一进程内的后台线程每周扫描，确保界面和扫描器共享数据库。多实例部署时应将 SQLite 替换为 PostgreSQL。

## 模型核验与搜索

复制 `.env.example` 为 `.env`。`OPENAI_API_KEY` 缺失时，系统仍会运行，但疑似招生记录进入人工审核队列。`SEARCH_API_KEY` 缺失时，仅扫描 `schools.csv` 中给出的院系 URL。

任何密钥都不得提交到 Git。模型只接收公开教师主页中的相关文本。默认限制：每次最多20次模型核验，估算费用不超过1美元。

## 安全与合规

- 遵守目标网站条款、robots.txt 和合理访问频率；
- 只抓公开学术页面，不绕过登录、验证码或访问控制；
- 招生状态必须附证据和复核时间；
- 邮件只生成草稿，发送必须人工确认；
- 不根据敏感个人属性筛选导师；
- 学校排名仅作用户指定的范围过滤，不代表项目背书。

## 测试

```powershell
python -m unittest discover -s tests -v
```

MIT License
