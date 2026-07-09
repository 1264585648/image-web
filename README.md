# ProductShot AI Backend

AI 商品主图工厂后端 MVP。当前版本聚焦「普通商品照片 → 平台合规白底主图」，提供上传、模板、生成、合规检测、历史记录和静态文件访问。

## 已实现能力

- 图片上传：JPG / PNG / WebP
- 商品抠图：优先使用 `rembg`，没有可用模型时会降级为普通合成，方便本地调试
- 主图模板：Amazon 白底、Temu 主图、Shopify 主图、透明 PNG、轻阴影棚拍、移动端 4:5
- 图片合成：自动居中、自动缩放、纯白/透明/浅灰背景、自然阴影、补光和轻微锐化
- 合规检测：尺寸、纯白背景、商品居中、商品占比、清晰度
- 历史记录：查看生成任务和结果图
- 本地存储：上传图和生成图存到 `storage/`

## 本地启动

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

打开：

- 健康检查：`http://localhost:8000/api/health`
- API 文档：`http://localhost:8000/docs`

## Docker 启动

```bash
docker compose up --build
```

## API 示例

### 1. 上传商品图

```bash
curl -X POST "http://localhost:8000/api/upload" \
  -F "file=@./demo-product.png"
```

返回 `source_image_id` 后，用它生成主图。

### 2. 查看模板

```bash
curl "http://localhost:8000/api/templates"
```

### 3. 生成白底主图

```bash
curl -X POST "http://localhost:8000/api/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "source_image_id": "替换为上传返回的 id",
    "template_id": "amazon-white-main",
    "width": 2000,
    "height": 2000,
    "product_fill_ratio": 0.85,
    "background": "white",
    "add_shadow": false,
    "auto_enhance": true,
    "edge_repair": true,
    "output_format": "png"
  }'
```

### 4. 查看历史

```bash
curl "http://localhost:8000/api/history?limit=20"
```

## 前端对接建议

工作台可以按这个流程接入：

```text
上传商品图 /api/upload
→ 获取模板 /api/templates
→ 用户选择模板和尺寸
→ 调用 /api/generate
→ 展示 assets[0].public_url
→ 展示 assets[0].compliance
```

生成结果里的 `compliance` 可直接渲染成合规检测卡：

- `score`：合规分
- `checks.background_ok`：背景是否合格
- `checks.centered`：商品是否居中
- `checks.fill_ratio_ok`：商品占比是否合格
- `checks.size_ok`：尺寸是否合格
- `warnings`：需要用户确认的问题

## 后续开发路线

### P1：生产化

- 接入 Cloudflare R2 / S3，替代本地存储
- 增加用户系统、项目表、积分扣费表
- 接入 Redis + BullMQ / Celery，把生成改成异步任务
- 增加批量上传和批量导出 zip

### P2：高级 AI 能力

- 接入 OpenAI Image / Gemini Image 做局部瑕疵修复
- 商品细节一致性检测，避免模型改错 Logo、颜色、数量
- OCR 检测文字和水印
- 多平台规则配置后台

### P3：商业化

- Stripe / Lemon Squeezy / Paddle 支付
- 套餐和积分包
- 团队账号
- API Key 对外开放
