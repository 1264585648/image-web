# ProductShot AI Frontend

这是 ProductShot AI 的高保真前端工作台，已接入后端 API。

## 已接入接口

- `GET /api/templates`：加载主图模板
- `POST /api/upload`：上传商品原图
- `POST /api/generate`：生成主图
- `GET /api/history?limit=1`：加载最近一次生成结果

## 推荐运行方式

在仓库根目录启动后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd ..
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

然后访问：

```text
http://localhost:8000/
```

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
