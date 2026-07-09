# Task 2.2：任务进度字段完成记录

## 本次完成范围

- `generation_tasks` 增加任务进度字段：
  - `progress`：0 到 100 的整数进度。
  - `current_step`：当前生成阶段说明。
- `TaskOut` 响应模型增加 `progress` 和 `current_step`，历史、任务查询和生成接口都会返回。
- `/api/generate` 创建任务时初始化：

```text
status=queued
progress=0
current_step=已创建任务，等待生成
```

- 后台生成任务会持续更新进度：

```text
8%   正在读取原图
20%  正在抠图和增强
35%+ 正在合成主图结果（n/m）
100% 生成完成
```

- 失败时任务状态会变为 `failed`，并写入：

```text
current_step=生成失败
error_message=用户可理解的失败原因
```

- 前端轮询脚本会展示 `current_step + progress%`，生成按钮也会显示当前百分比。

## 涉及文件

- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/database.py`
- `backend/app/api/routes.py`
- `frontend/async-polling.js`

## 兼容性处理

本地 SQLite 旧库不会因为 `create_all()` 自动新增字段，所以 `init_db()` 里增加了轻量列补齐逻辑：

```text
ALTER TABLE generation_tasks ADD COLUMN progress INTEGER NOT NULL DEFAULT 0
ALTER TABLE generation_tasks ADD COLUMN current_step VARCHAR(120)
```

该逻辑只对 SQLite 生效，适合当前 MVP 阶段。

## 验收建议

1. 使用旧的本地 SQLite 数据库启动后端，确认不会报 `no such column: generation_tasks.progress`。
2. 调用 `/api/generate`，确认立即返回：
   - `status=queued`
   - `progress=0`
   - `current_step=已创建任务，等待生成`
3. 轮询 `/api/tasks/{task_id}`，确认进度逐步变化。
4. 生成完成后返回：
   - `status=success`
   - `progress=100`
   - `current_step=生成完成`
5. 前端生成按钮和预览角标能展示当前进度。

## 下一步建议

- Task 2.3：失败任务一键重试。
- Task 2.4：批量 SKU 生成的批次任务设计。
