# Task 2.1：生成接口任务模式完成记录

## 本次完成范围

- `/api/generate` 从同步生成改为任务模式：接口先创建 `queued` 任务并立即返回。
- 使用 FastAPI `BackgroundTasks` 在后台执行图片生成，不再阻塞当前请求。
- 后台任务使用独立 `SessionLocal()` 数据库 session，避免复用请求生命周期内的 session。
- 状态流转改为：

```text
queued → processing → success / failed
```

- 前端新增 `frontend/async-polling.js`，拦截生成按钮，提交生成任务后轮询：

```text
GET /api/tasks/{task_id}
```

- 页面会根据任务状态展示“排队中 / 生成中 / 已生成 / 生成失败”，最终自动刷新历史和结果区。

## 涉及文件

- `backend/app/api/routes.py`
- `frontend/async-polling.js`
- `frontend/index.html`

## 验收建议

1. 启动后端并打开页面。
2. 上传一张正常商品图。
3. 点击“生成主图”。
4. Network 中确认：
   - `POST /api/generate` 很快返回，状态为 `queued`。
   - 前端随后轮询 `/api/tasks/{task_id}`。
   - 状态从 `queued` 或 `processing` 变成 `success`。
5. 成功后结果区自动展示图片，历史列表自动刷新。
6. 失败场景下任务进入 `failed`，页面展示 `error_message`。

## 说明

当前实现仍是单进程后台任务，适合 MVP 阶段。线上多实例、批量生成或长任务较多时，建议后续升级为 Celery / RQ / Dramatiq / Arq 等真正的队列系统。

## 下一步建议

- Task 2.2：增加任务进度字段，例如 `progress`、`current_step`，让前端显示更细的生成进度。
- Task 2.3：增加任务重试能力，失败任务可以一键重新排队。
- Task 2.4：为批量 SKU 生成预留批次任务表。
