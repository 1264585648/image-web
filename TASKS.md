# ProductShot AI 任务开发文档

本文件用于指导 `image-web` 仓库后续开发。目标不是一次性做成完整商业产品，而是按阶段把当前 Demo 打磨成：

```text
可本地运行的工具 → 可给用户试用的 MVP → 可收费产品 → 可规模化平台
```

当前项目已有基础能力：

- 前端工作台：上传、模板选择、生成结果、合规检测、历史结果。
- 后端接口：模板列表、图片上传、图片生成、任务查询、历史查询、删除任务。
- 图片处理：抠图、白底合成、透明 PNG、轻阴影图、高清图、基础合规检测。

当前主要缺口：

- 存储还是本地 `storage/`，不适合线上部署。
- 已有用户登录和任务隔离，但还没有积分系统、套餐系统、真实支付。
- 任务已异步化，但还没有独立队列服务，当前仍使用 FastAPI `BackgroundTasks`。
- 合规检测已做平台规则细分，但 OCR、水印、Logo 一致性仍是接口预留。
- 存储抽象、R2/S3、批量上传和批量生成仍待后续阶段实现。

当前第一期执行状态：

- 平台规则细分已进入实现：模板会绑定 Amazon / Temu / Shopify / Universal / Mobile Commerce 规则集。
- 合规报告已增强为分项报告，并保留旧版 `score`、`checks`、`metrics`、`warnings` 字段。
- OCR、水印、Logo 一致性先走 `qc_status=not_run` 的接口预留，不在第一期接入重依赖或云服务。

---

## 一、开发原则

### 1. 先可用，再商业化

不要先做复杂会员、支付、团队、API Key。先保证用户可以稳定完成：

```text
上传商品图 → 设置模板 → 生成主图 → 查看合规结果 → 下载图片 → 查看历史
```

### 2. 每一步都必须可验收

每个任务完成后，至少满足：

- 本地能启动。
- 页面能操作。
- 接口能返回正确结果。
- 错误场景有提示。
- README 或本任务文档有必要更新。

### 3. 不做隐藏失败

图片生成、抠图、上传、下载、合规检测失败时，必须给用户可理解的错误提示，不能只在后端日志里报错。

### 4. 保持当前轻量结构

短期继续使用当前 `frontend/` 静态页面和 FastAPI 后端，不要立刻迁移 React / Next.js。等 MVP 稳定后再工程化前端。

---

# 阶段 0：环境和基线确认

## Task 0.1：确认项目可本地启动

### 目标

确保开发前有稳定的本地运行基线。

### 要做什么

1. 在仓库根目录启动后端。
2. 打开前端页面。
3. 测试健康检查接口。
4. 上传一张测试商品图。
5. 生成一张主图。

### 涉及文件

- `README.md`
- `backend/app/main.py`
- `backend/app/api/routes.py`
- `frontend/index.html`
- `frontend/app.js`

### 验收方式

执行：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Windows 可使用：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

浏览器访问：

```text
http://localhost:8000/
```

接口检查：

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/templates
```

验收标准：

- `/api/health` 返回 `ok=true`。
- 页面能打开。
- 模板能加载。
- 图片能上传。
- 点击生成后能得到至少一张结果图。
- `storage/uploads` 和 `storage/outputs` 下能看到文件。

---

# 阶段 1：补齐可用 MVP

目标：把当前 Demo 修成一个可给真实用户试用的工具。

---

## Task 1.1：上传前端校验和本地预览

### 目标

用户选择图片后，前端立即提示图片是否符合要求，并显示本地预览，减少无效上传。

### 要做什么

1. 在 `frontend/app.js` 增加上传前校验。
2. 校验文件类型：只允许 JPG、PNG、WebP。
3. 校验文件大小：默认不超过后端 `MAX_UPLOAD_MB`，前端先按 20MB 限制。
4. 选择文件后先用 `URL.createObjectURL(file)` 显示本地预览。
5. 上传成功后再替换为后端返回的 `public_url`。
6. 上传失败时保留错误提示，不清空用户已选择的文件名。

### 涉及文件

- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`

### 验收方式

手动测试：

- 上传 `.txt` 文件，前端直接提示格式不支持，不请求后端。
- 上传超过 20MB 的图片，前端直接提示文件过大。
- 上传正常 JPG / PNG / WebP，选择后立刻显示预览。
- 上传成功后显示文件名、尺寸、类型。
- 上传失败时页面不崩溃，有 toast 和状态文字。

完成标准：

- 不合法文件不会触发 `/api/upload`。
- 合法文件会触发 `/api/upload`。
- 上传状态文案清晰。

---

## Task 1.2：自定义尺寸弹窗

### 目标

补齐当前“自定义尺寸”入口，让用户可以输入宽高生成主图。

### 要做什么

1. 点击“自定义”按钮时打开弹窗或内联表单。
2. 用户可输入宽度和高度。
3. 宽高限制与后端保持一致：512 到 4096。
4. 输入非法值时前端提示。
5. 点击确认后更新 `state.selectedSize`。
6. 自定义尺寸按钮显示当前尺寸，例如 `1200 × 1600`。
7. 生成请求使用用户输入的尺寸。

### 涉及文件

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`

### 验收方式

手动测试：

- 点击“自定义”不再只弹出“入口已预留”。
- 输入 `1200 × 1600` 后，生成接口 payload 中 width=1200，height=1600。
- 输入 `200 × 200` 时提示尺寸不能小于 512。
- 输入 `5000 × 5000` 时提示尺寸不能大于 4096。
- 生成结果图尺寸与输入一致。

接口验收：

- 打开浏览器 Network，确认 `/api/generate` 请求体里的 `width`、`height` 正确。

---

## Task 1.3：自定义背景色选择器

### 目标

补齐当前“自定义颜色”入口，不再写死 `#F7F9FC`。

### 要做什么

1. 给“自定义颜色”增加颜色选择器。
2. 用户选择颜色后更新 `state.background`。
3. 页面展示当前颜色值。
4. 生成请求里的 `background` 使用用户选择的 hex 值。
5. 透明背景和纯白背景仍保持原有逻辑。

### 涉及文件

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `backend/app/services/image_pipeline.py`

### 验收方式

手动测试：

- 选择纯白，生成白底图。
- 选择透明，生成透明 PNG。
- 选择浅灰，生成浅灰底图。
- 选择自定义颜色，例如 `#F2EFEA`，生成对应背景色图片。

完成标准：

- `/api/generate` 请求体中 `background` 是用户选择的颜色。
- 输出图片背景颜色肉眼可见正确。
- 非法颜色不会导致前端崩溃。

---

## Task 1.4：输出格式选择

### 目标

允许用户选择 PNG、JPG、WebP 三种输出格式。

### 要做什么

1. 在设置面板增加输出格式选择。
2. 可选：PNG、JPG、WebP。
3. 透明背景时默认使用 PNG，并提示 JPG 不支持透明背景。
4. 生成请求里的 `output_format` 不再写死为 `png`。
5. 下载文件扩展名与格式一致。

### 涉及文件

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `backend/app/api/routes.py`
- `backend/app/services/image_pipeline.py`

### 验收方式

手动测试：

- 选择 PNG，输出 `.png`。
- 选择 JPG，输出 `.jpg`，背景不透明。
- 选择 WebP，输出 `.webp`。
- 透明背景下选择 JPG 时，前端提示需要切换 PNG，或者自动切换为 PNG。

完成标准：

- Network 中 `output_format` 与用户选择一致。
- `storage/outputs` 文件扩展名正确。
- 下载后的文件能正常打开。

---

## Task 1.5：下载全部结果为 ZIP

### 目标

用户生成多张结果后，可以一次性下载所有图片。

### 要做什么

1. 后端新增接口：

```text
GET /api/tasks/{task_id}/download.zip
```

2. 根据任务 ID 找到所有 assets。
3. 把图片打包成 zip。
4. 文件名使用可读名称，例如：

```text
amazon-white-main-2000x2000.png
transparent-png-2000x2000.png
soft-shadow-packshot-2000x2000.png
```

5. 前端在生成结果区域增加“下载全部”按钮。
6. 没有结果时不显示或禁用按钮。

### 涉及文件

- `backend/app/api/routes.py`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`

### 验收方式

接口测试：

```bash
curl -L "http://localhost:8000/api/tasks/{task_id}/download.zip" -o result.zip
```

手动测试：

- 生成成功后点击“下载全部”。
- 浏览器下载 zip。
- 解压后包含所有生成结果。
- 图片文件名清晰，不是纯 UUID。

完成标准：

- 成功任务可以下载 zip。
- 不存在的 task_id 返回 404。
- 没有 assets 的任务返回明确错误。

---

## Task 1.6：历史记录完整列表

### 目标

当前历史只加载最近一次，需要做成完整历史列表，方便用户找回生成结果。

### 要做什么

1. 前端增加历史列表区域或抽屉。
2. 调用 `GET /api/history?limit=30`。
3. 每条历史展示：生成时间、模板、状态、合规分、缩略图。
4. 点击历史项后恢复预览和结果列表。
5. 失败任务也要展示失败原因。
6. 增加刷新按钮。

### 涉及文件

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `backend/app/api/routes.py`

### 验收方式

手动测试：

- 连续生成 3 次。
- 刷新页面后能看到历史列表。
- 点击任一历史项，右侧预览和结果图切换到对应任务。
- 失败任务展示失败状态和原因。

完成标准：

- 历史不是只显示最近 1 条。
- 页面刷新后历史仍存在。
- 历史项能恢复对应 assets。

---

## Task 1.7：删除历史和文件清理

### 目标

用户可以删除不需要的生成任务，同时后端清理输出文件。

### 要做什么

1. 前端历史项增加删除按钮。
2. 删除前二次确认。
3. 调用已有接口：

```text
DELETE /api/tasks/{task_id}
```

4. 删除成功后刷新历史列表。
5. 如果正在预览被删除的任务，清空预览。
6. 后端删除 task 时同时删除 assets 文件。
7. 可选：如果 source image 没有其他任务引用，后续再考虑删除原图。

### 涉及文件

- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`
- `backend/app/api/routes.py`

### 验收方式

手动测试：

- 删除一条历史记录。
- 页面列表中该记录消失。
- 刷新页面后仍然消失。
- `storage/outputs` 中对应图片文件被删除。
- 删除不存在的 task_id 返回 404。

完成标准：

- 删除动作不会误删其他任务。
- 删除失败有明确提示。

---

## Task 1.8：生成失败提示优化

### 目标

用户看到的是可理解的失败原因，而不是底层异常。

### 要做什么

1. 后端捕获常见失败场景。
2. 把异常映射成用户友好错误：
   - 图片无法读取。
   - 图片太小。
   - 抠图失败。
   - 输出格式不支持。
   - 存储写入失败。
   - 模板不存在。
3. 前端展示 `error_message`。
4. 前端给出下一步建议，例如“换一张更清晰、背景更干净的商品图”。

### 涉及文件

- `backend/app/api/routes.py`
- `backend/app/services/image_pipeline.py`
- `frontend/app.js`

### 验收方式

手动测试：

- 上传损坏图片，看到明确提示。
- 传不存在的 `source_image_id`，接口返回 404。
- 传错误的 `template_id`，接口返回 400。
- 生成失败时任务状态为 `failed`。
- 前端不崩溃，按钮恢复可点击。

完成标准：

- 用户不直接看到 Python traceback。
- 失败任务能进入历史记录。
- 失败原因能在历史中看到。

---

# 阶段 2：任务异步化和生产化基础

目标：解决接口阻塞问题，为批量生成和线上部署打基础。

---

## Task 2.1：生成接口改为任务模式

### 目标

`POST /api/generate` 不再同步等图片全部生成完，而是创建任务后立即返回 task_id。

### 要做什么

1. `POST /api/generate` 创建任务，状态为 `queued`。
2. 返回任务信息，不阻塞等待生成完成。
3. 后端增加任务执行函数，例如 `run_generation_task(task_id)`。
4. 本阶段可以先用 FastAPI `BackgroundTasks` 实现，不急着引入 Celery。
5. 前端拿到 task_id 后轮询：

```text
GET /api/tasks/{task_id}
```

6. 状态流转：

```text
queued → processing → success / failed
```

### 涉及文件

- `backend/app/api/routes.py`
- `backend/app/models.py`
- `frontend/app.js`

### 验收方式

接口测试：

- 调用 `/api/generate` 后立即返回 task。
- 初始状态为 `queued` 或 `processing`。
- 轮询 `/api/tasks/{task_id}`，最终变成 `success` 或 `failed`。

前端测试：

- 点击生成后按钮进入生成中。
- 页面显示进度状态。
- 生成完成后自动展示结果。
- 失败后展示失败原因。

完成标准：

- 生成长图时接口不长时间卡住。
- 前端不需要刷新页面即可看到最终结果。

---

## Task 2.2：前端任务轮询

### 目标

让用户明确知道任务正在排队、处理中、已完成或失败。

### 要做什么

1. 新增 `pollTask(taskId)`。
2. 每 1-2 秒请求一次 `/api/tasks/{task_id}`。
3. 最多轮询一定次数，例如 120 次。
4. 成功后停止轮询并渲染结果。
5. 失败后停止轮询并显示失败原因。
6. 超时后提示用户刷新历史查看。

### 涉及文件

- `frontend/app.js`
- `frontend/index.html`
- `frontend/styles.css`

### 验收方式

手动测试：

- 点击生成后显示“排队中 / 生成中”。
- 成功后自动变成“已生成”。
- 失败后显示“生成失败”。
- 多次点击不会产生重复轮询。

完成标准：

- 不需要手动刷新页面。
- 不会出现多个轮询定时器互相干扰。

---

## Task 2.3：抽象 StorageService

### 目标

把本地文件存储逻辑抽象出来，为后续接入 Cloudflare R2 / S3 做准备。

### 要做什么

1. 新增 `backend/app/services/storage.py`。
2. 定义统一接口：

```python
class StorageService:
    def save_upload(...): ...
    def save_output(...): ...
    def delete(...): ...
    def public_url(...): ...
```

3. 先实现 `LocalStorageService`。
4. 替换 routes.py 中直接拼接 `settings.storage_path` 的逻辑。
5. 保持现有本地行为不变。

### 涉及文件

- `backend/app/services/storage.py`
- `backend/app/api/routes.py`
- `backend/app/config.py`

### 验收方式

本地测试：

- 上传图片仍然保存到 `storage/uploads`。
- 输出图片仍然保存到 `storage/outputs`。
- `public_url` 仍然可以在浏览器打开。
- 删除任务仍然能删除输出文件。

完成标准：

- routes.py 不再散落大量文件路径拼接。
- 后续接 R2 时只需要新增一个 storage 实现。

---

## Task 2.4：接入 Cloudflare R2 / S3 存储

### 目标

让线上部署不依赖本地磁盘，生成图可以稳定访问和下载。

### 要做什么

1. 增加环境变量：

```env
STORAGE_DRIVER=local
R2_ENDPOINT_URL=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=
R2_PUBLIC_BASE_URL=
```

2. 实现 `R2StorageService`。
3. 使用 boto3 或兼容 S3 的 SDK 上传文件。
4. 上传原图和输出图到 R2。
5. 返回公开访问 URL 或签名 URL。
6. 保留本地存储作为开发默认值。

### 涉及文件

- `backend/app/config.py`
- `backend/app/services/storage.py`
- `backend/requirements.txt`
- `backend/.env.example`
- `README.md`

### 验收方式

本地 local 模式：

- 不配置 R2 时，项目仍能按原方式运行。

R2 模式：

- 配置 R2 环境变量。
- 上传图片后，文件出现在 R2 bucket。
- 生成结果图出现在 R2 bucket。
- 前端展示的图片 URL 可以打开。
- 删除任务时，R2 中对应文件被删除或标记清理。

完成标准：

- 本地和 R2 两种模式都能运行。
- 环境变量缺失时有明确报错。

---

# 阶段 3：合规检测增强

目标：让工具从“图片处理”升级为“电商主图合规助手”。

---

## Task 3.1：合规报告详情页 / 详情弹窗

### 目标

当前页面只展示简单分数和几条检查项，需要展示更完整的合规报告。

### 要做什么

1. 点击“查看详细报告”打开弹窗。
2. 展示：
   - 总分。
   - 背景检测。
   - 尺寸检测。
   - 商品占比。
   - 居中偏移。
   - 清晰度。
   - 警告项。
   - 修改建议。
3. 每个检查项用“通过 / 警告 / 失败”标识。
4. 支持复制报告文本。

### 涉及文件

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `backend/app/services/compliance.py`

### 验收方式

手动测试：

- 生成图片后点击“查看详细报告”。
- 能看到完整指标。
- 低分图片有修改建议。
- 没有报告时按钮禁用或提示暂无报告。

完成标准：

- 不是只有一个分数。
- 用户知道下一步怎么改。

---

## Task 3.2：OCR 文字和水印检测

### 目标

检测主图中是否存在文字、水印、促销词等可能影响平台审核的内容。

### 要做什么

1. 接入 OCR 能力。
2. 可选方案：
   - EasyOCR。
   - PaddleOCR。
   - 云服务 OCR。
   - 后续接入多模态模型。
3. 在合规报告中增加：

```json
{
  "text_detected": true,
  "detected_text": ["SALE", "50% OFF"],
  "watermark_suspected": true
}
```

4. 前端展示检测到的文字。
5. 如果检测到明显促销词或水印，扣分并给出警告。

### 涉及文件

- `backend/app/services/compliance.py`
- `backend/requirements.txt`
- `frontend/app.js`

### 验收方式

测试图片：

- 一张无文字商品图。
- 一张带 `SALE` 的商品图。
- 一张带水印的商品图。

完成标准：

- 无文字图片不误报或低误报。
- 有明显文字时报告能提示。
- 前端能展示检测文本。

---

## Task 3.3：平台规则拆分

### 目标

不同平台规则不同，不能所有模板都用同一套检测标准。

### 要做什么

1. 为模板增加平台规则配置。
2. 不同平台可配置：
   - 最小尺寸。
   - 背景要求。
   - 商品占比范围。
   - 是否允许阴影。
   - 是否允许文字。
3. `analyze_image` 根据 template/platform 选择规则。
4. 合规报告显示当前使用的平台规则。

### 涉及文件

- `backend/app/templates.py`
- `backend/app/services/compliance.py`
- `backend/app/schemas.py`
- `frontend/app.js`

### 验收方式

手动测试：

- Amazon 模板强校验白底和文字。
- Shopify 模板允许更宽松的背景。
- 透明 PNG 模板不要求白底。

完成标准：

- 同一张图在不同模板下可能得到不同合规结果。
- 报告中能看到平台规则名称。

---

# 阶段 4：用户、积分和商业化基础

目标：让项目具备收费产品的基本结构。

---

## Task 4.1：用户注册登录

### 目标

每个用户只能看到自己的上传图、生成任务和历史记录。

### 要做什么

1. 新增 users 表。
2. 支持邮箱 + 密码注册。
3. 密码加密存储。
4. 登录后返回 token 或 session。
5. 前端增加登录 / 注册弹窗。
6. 后端接口通过当前用户过滤数据。

### 涉及文件

- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/api/routes.py`
- `backend/app/config.py`
- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`

### 验收方式

手动测试：

- 用户 A 注册并生成图片。
- 用户 B 注册后看不到用户 A 的历史。
- 未登录用户访问生成接口时，根据产品策略：要么拒绝，要么走游客免费次数。

完成标准：

- 历史记录按用户隔离。
- 登录状态刷新后仍可保持。
- 密码不明文保存。

---

## Task 4.2：积分系统

### 目标

控制用户生成次数，为后续收费做准备。

### 要做什么

1. 新增 `credit_ledger` 积分流水表。
2. 用户注册赠送免费积分，例如 5 次。
3. 每次生成成功或创建任务时扣积分。
4. 生成失败时退回积分，或失败不扣积分。
5. 前端显示当前积分。
6. 积分不足时阻止生成，引导升级。

### 涉及文件

- `backend/app/models.py`
- `backend/app/api/routes.py`
- `backend/app/schemas.py`
- `frontend/app.js`
- `frontend/index.html`

### 验收方式

手动测试：

- 新用户注册后有免费积分。
- 生成一次后积分减少。
- 积分为 0 时不能生成。
- 失败任务按规则退回或不扣。
- 积分流水可查询。

完成标准：

- 积分不是前端假数据。
- 刷新页面后积分仍正确。

---

## Task 4.3：套餐页真实化

### 目标

当前页面上的免费版、专业版、商家版只是静态展示，需要和后端套餐数据对齐。

### 要做什么

1. 后端增加套餐配置。
2. 前端从接口加载套餐。
3. 显示：套餐名、价格、生成次数、能力限制。
4. 当前用户显示当前套餐。
5. 升级按钮先跳到占位弹窗，后续接支付。

### 涉及文件

- `backend/app/api/routes.py`
- `backend/app/schemas.py`
- `frontend/index.html`
- `frontend/app.js`

### 验收方式

- 套餐信息来自后端接口，不是写死 HTML。
- 修改后端套餐配置后，前端展示变化。
- 当前套餐能正确显示。

完成标准：

- 为支付接入做好数据结构准备。

---

# 阶段 5：批量处理能力

目标：面向 Temu / Amazon / Shopify 卖家，支持多 SKU 批量处理。

---

## Task 5.1：批量上传队列

### 目标

用户可以一次上传多张商品图。

### 要做什么

1. 文件选择支持 multiple。
2. 前端显示上传队列。
3. 每张图片有独立状态：等待上传、上传中、上传成功、上传失败。
4. 上传成功后保存 source_image_id。
5. 失败项可以重试。

### 涉及文件

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `backend/app/api/routes.py`

### 验收方式

- 一次选择 5 张图片。
- 5 张图片分别上传。
- 失败的单张可以重试。
- 上传成功的图片能进入批量生成。

完成标准：

- 单张上传能力不受影响。
- 批量上传状态清晰。

---

## Task 5.2：批量生成

### 目标

对多个 source_image 使用同一模板批量生成主图。

### 要做什么

1. 新增批量生成接口：

```text
POST /api/batch-generate
```

2. 请求包含多个 `source_image_id` 和统一生成参数。
3. 后端为每张图创建一个 task。
4. 前端展示批量任务进度。
5. 支持批量下载 zip。

### 涉及文件

- `backend/app/api/routes.py`
- `backend/app/models.py`
- `backend/app/schemas.py`
- `frontend/app.js`

### 验收方式

- 上传 3 张图。
- 点击批量生成。
- 生成 3 组结果。
- 单张失败不影响其他图片。
- 可以一键下载全部结果。

完成标准：

- 批量任务具备独立状态。
- 不因为一张失败导致整批失败。

---

# 阶段 6：前端工程化

目标：当前静态前端功能稳定后，再迁移到更适合长期维护的结构。

---

## Task 6.1：迁移到 Vite + React + TypeScript

### 目标

将当前 `frontend/` 拆成组件化工程，提高后续维护效率。

### 前置条件

必须先完成阶段 1 和阶段 2 的主要任务。否则不要提前迁移。

### 要做什么

1. 新建 Vite React TypeScript 项目。
2. 拆分组件：

```text
UploadPanel
TemplateSelector
PreviewCanvas
SettingsPanel
ResultGrid
ComplianceCard
HistoryPanel
PricingSection
LoginModal
```

3. 抽离 API client。
4. 保持现有 UI 风格。
5. FastAPI 继续托管构建后的静态文件，或前后端分离部署。

### 涉及文件

- `frontend/`
- `backend/app/main.py`
- `README.md`

### 验收方式

- `npm install` 成功。
- `npm run dev` 能打开页面。
- `npm run build` 成功。
- 后端能托管构建后的静态文件，或 README 说明前后端分别启动。
- 原有上传、生成、下载、历史、合规检测功能不丢失。

完成标准：

- 功能不倒退。
- 组件边界清晰。
- API 调用集中管理。

---

# 推荐执行顺序

不要同时开太多任务。建议按下面顺序执行：

```text
1. Task 0.1  本地基线确认
2. Task 1.1  上传校验和本地预览
3. Task 1.2  自定义尺寸弹窗
4. Task 1.3  自定义背景色
5. Task 1.4  输出格式选择
6. Task 1.5  下载全部 zip
7. Task 1.6  历史记录完整列表
8. Task 1.7  删除历史和文件清理
9. Task 1.8  生成失败提示优化
10. Task 2.1  生成接口任务化
11. Task 2.2  前端任务轮询
12. Task 2.3  抽象 StorageService
13. Task 2.4  接入 R2 / S3
14. Task 3.1  合规报告详情
15. Task 3.2  OCR 文字和水印检测
16. Task 3.3  平台规则拆分
17. Task 4.1  用户注册登录
18. Task 4.2  积分系统
19. Task 4.3  套餐页真实化
20. Task 5.1  批量上传队列
21. Task 5.2  批量生成
22. Task 6.1  前端工程化
```

---

# 每次提交前的通用验收清单

每完成一个任务，都必须检查：

```text
[ ] 后端能启动
[ ] 前端能打开
[ ] /api/health 正常
[ ] 原有上传功能未破坏
[ ] 原有生成功能未破坏
[ ] 新功能有正常场景测试
[ ] 新功能有失败场景测试
[ ] 页面没有明显 JS 报错
[ ] 后端没有明显 traceback
[ ] README 或 TASKS.md 已按需更新
```

建议本地执行：

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

然后访问：

```text
http://localhost:8000/
http://localhost:8000/api/health
http://localhost:8000/docs
```

---

# 给 Codex / 开发模型的执行提示词

如果要让 Codex 按任务执行，可以使用下面模板：

```text
你正在开发 GitHub 仓库 1264585648/image-web。
请阅读 README.md 和 TASKS.md。
当前只实现 TASKS.md 中的【Task X.X：任务名称】。

要求：
1. 不要一次性实现多个阶段。
2. 保持现有前端风格，不要大规模重构。
3. 保持现有 API 兼容，除非任务明确要求修改。
4. 完成后说明改了哪些文件。
5. 给出本地验收步骤。
6. 如果发现现有代码问题，可以顺手修小 bug，但不要引入无关功能。
7. 所有错误提示要让普通用户看得懂。
8. 不要提交密钥、真实账号、真实支付配置。

当前任务：
【把这里替换成 Task X.X 的完整内容】
```

---

# 暂不建议做的事情

下面这些功能可以后置，不要在 MVP 阶段提前做：

- 完整管理后台。
- 团队协作。
- API Key 开放平台。
- 多语言系统。
- 复杂模板编辑器。
- AI 场景图生成。
- 支付订阅自动续费。
- Next.js 全量重构。
- 移动端 App。

这些不是不重要，而是会拖慢当前 MVP 验证。

---

# 阶段完成定义

## MVP 完成定义

完成以下任务即可认为 MVP 可试用：

- Task 1.1 上传校验和本地预览
- Task 1.2 自定义尺寸弹窗
- Task 1.3 自定义背景色
- Task 1.4 输出格式选择
- Task 1.5 下载全部 zip
- Task 1.6 历史记录完整列表
- Task 1.7 删除历史和文件清理
- Task 1.8 生成失败提示优化

MVP 验收标准：

```text
用户可以上传商品图，选择模板、尺寸、背景和格式，生成多张主图，查看合规检测，下载单张或全部结果，并能在历史记录中找回或删除生成结果。
```

## 可上线试用完成定义

完成以下任务即可考虑部署给小范围用户试用：

- MVP 全部任务
- Task 2.1 生成接口任务化
- Task 2.2 前端任务轮询
- Task 2.3 抽象 StorageService
- Task 2.4 接入 R2 / S3

可上线试用验收标准：

```text
用户生成图片时接口不会长时间阻塞，任务状态可追踪，文件存储不依赖本地磁盘，线上刷新页面后仍可访问历史结果。
```

## 可收费完成定义

完成以下任务即可考虑接入真实支付：

- 可上线试用全部任务
- Task 4.1 用户注册登录
- Task 4.2 积分系统
- Task 4.3 套餐页真实化

可收费验收标准：

```text
用户身份、生成次数、积分余额、套餐权益都由后端控制，不再是前端假数据。
```
