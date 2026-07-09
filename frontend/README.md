# ProductShot AI Frontend

这是 ProductShot AI 的高保真前端工作台，已接入后端 API。

## 已接入接口

- `GET /api/templates`：加载主图模板
- `POST /api/upload`：上传商品原图
- `POST /api/generate`：生成主图，并渲染返回的多个 `assets`
- `GET /api/history?limit=1`：加载最近一次生成结果

## 已优化交互

- 生成结果不再用前端假卡片重复展示同一张图，而是按后端真实 `assets` 渲染。
- 合规评分兼容后端 `metrics.product_fill_ratio` 字段，商品占比展示更准确。
- 动态模板、文件名、告警内容做了 HTML 转义，降低页面注入风险。
- 上传、生成、历史加载均保留错误提示和空状态。

## 推荐运行方式

在仓库根目录执行：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

然后访问：

```text
http://localhost:8000/
```

> 说明：虽然命令在 `backend/` 目录里执行，后端会自动向上查找仓库根目录下的 `frontend/`，并把它挂载到 `/`。

也可以继续使用 Docker：

```bash
docker compose up --build
```

访问：

```text
http://localhost:8000/
```

## 页面结构

- Landing Page：首页转化页
- Dashboard：真实接入上传、生成、合规检测和历史结果
- Mobile：CSS 响应式适配，底部固定生成按钮

## 说明

当前前端为无构建静态页面，便于快速部署和直接由 FastAPI 托管。后续如果要工程化，可以迁移到：

- React / Next.js
- Vue / Nuxt
- Vite + TypeScript

组件拆分建议：

- `UploadPanel`
- `TemplateSelector`
- `PreviewCanvas`
- `SettingsPanel`
- `ResultGrid`
- `ComplianceCard`
- `MobileActionBar`
