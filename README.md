# ProductShot AI

中文副标题：**AI 商品主图工厂**

这是一个面向电商卖家、独立站卖家、Temu / Amazon / Shopify 商家的 AI 商品主图生成工具。

当前仓库同时包含：

- 后端 MVP：普通商品照片 → 平台合规白底主图
- 高保真前端原型：桌面端首页、桌面端工作台、手机端首页、手机端工作台
- 设计资产：统一视觉方向 SVG，可作为 PRD / 前端实现参考

## 高保真前端原型

已新增：

- `index.html`：可直接打开的高保真静态原型
- `assets/mockups/productshot-ai-ui-direction.svg`：四端界面方向资产
- `assets/README.md`：设计资产说明

本地预览：

```bash
python -m http.server 3000
```

打开：

```text
http://localhost:3000
```

页面包含：

1. 桌面端首页 Landing Page
2. 桌面端工作台 Dashboard
3. 手机端首页 Mobile Landing
4. 手机端工作台 Mobile Dashboard

设计原则：

- 高级、干净、专业、可信赖
- 白色 / 浅灰 / 深蓝 / 科技蓝为主
- 绿色表示合规通过，橙色表示警告
- 圆角卡片、柔和阴影、强电商工具属性
- 适合后续拆成 React / Vue / Next.js 组件

---

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
