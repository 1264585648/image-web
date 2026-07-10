# 06. 交付计划、Sprint 与开发任务

## 1. 总体节奏

建议用 6 个 Sprint 完成首个可商业化版本。每个 Sprint 都必须包含代码、测试样本、前端展示和验收，不要只完成后端接口。

| Sprint | 重点 | 建议周期 | 可见交付 |
|---|---|---:|---|
| 0 | 基线与测试框架 | 2–3 天 | 固定样本、现状指标、回归脚本 |
| 1 | 原图预检与 Mask | 4–6 天 | 上传后先看到原图问题 |
| 2 | JSON 规则引擎 | 4–6 天 | 支持平台、图片角色和规则版本 |
| 3 | 首批 20 条规则 | 7–10 天 | Amazon/Google 基础检测可用 |
| 4 | 选择性自动修复与复检 | 6–8 天 | 修复前后对比闭环 |
| 5 | OCR 与高频覆盖元素 | 7–12 天 | 文字、价格、折扣、水印初检 |
| 6 | 批量、反馈和商业化 | 7–12 天 | 批量处理、套餐、真实审核反馈 |

周期仅用于任务拆分，不作为固定发布日期承诺。

## 2. Sprint 0：基线与测试框架

### 目标

先记录当前算法表现，避免重构后无法判断是否退化。

### 任务

- [ ] 建立 `tests/fixtures/compliance/` 目录；
- [ ] 创建 `manifest.jsonl`；
- [ ] 准备至少 30 张第一批基线图片；
- [ ] 保存当前 `compliance.py` 输出快照；
- [ ] 增加检测耗时统计；
- [ ] 增加规则报告 JSON 快照测试；
- [ ] 定义 `pass/review/fail/error` 状态；
- [ ] 定义 `blocker/warning/quality/info` 严重度。

### 验收

- 能一条命令运行全部基线测试；
- 能看到每张图当前命中的问题和耗时；
- 后续改动导致报告变化时，测试会显式提示。

## 3. Sprint 1：原图预检与 Mask

### 目标

解决“生成后自证合规”和抠图失败误判。

### 后端任务

- [ ] 新增 `POST /api/compliance/analyze`；
- [ ] 新增 `ComplianceAnalysis` 数据模型；
- [ ] 保存原图文件元数据；
- [ ] 分割结果返回 `success/low_confidence/failed`；
- [ ] 持久化主体 Mask；
- [ ] 计算 Mask bbox、面积、矩形度和边缘接触；
- [ ] `rembg` 异常不再静默标记为成功；
- [ ] 原图报告和生成图报告分开。

### 前端任务

- [ ] 上传完成后自动执行预检；
- [ ] 显示分析进度；
- [ ] 显示原图分数、状态和问题列表；
- [ ] 支持显示/隐藏 Mask；
- [ ] 低置信度显示“需要确认”。

### 测试任务

- [ ] 透明 PNG；
- [ ] 普通杂乱背景；
- [ ] 主体与背景颜色接近；
- [ ] 抠图失败回退场景；
- [ ] 整张矩形被当作主体的场景；
- [ ] 多个孤立前景碎片。

### 验收

- 抠图失败时背景规则不能返回通过；
- 原图不经过居中和白底处理即可获得报告；
- Mask 可查看、可复用；
- 分割低置信度能传递到最终状态。

## 4. Sprint 2：规则引擎

### 目标

把固定阈值从 Python 代码中抽离。

### 任务

- [ ] 建立 `backend/app/compliance/`；
- [ ] 定义规则 JSON Schema；
- [ ] 实现规则加载与缓存；
- [ ] 实现平台、站点、图片角色、类目匹配；
- [ ] 实现规则覆盖优先级；
- [ ] 实现检测器注册表；
- [ ] 实现严重度、置信度和最终状态聚合；
- [ ] 报告保存规则 ID、规则版本和规则集版本；
- [ ] 为 Universal、Amazon、Google Merchant 建立初始规则文件；
- [ ] 保留旧 `/api/generate` 兼容性。

### 验收

- 修改阈值不需要改检测器代码；
- 同一指标可被不同平台规则复用；
- Amazon 与 Google 可以得到不同判断；
- 规则来源、版本和生效时间可查询；
- blocker 高置信度失败会使整体状态为 fail。

## 5. Sprint 3：首批 20 条确定性规则

### 技术类

- [ ] 文件可读；
- [ ] 扩展名与真实格式；
- [ ] 最小尺寸；
- [ ] 最大文件体积；
- [ ] EXIF 方向。

### 背景与构图

- [ ] 背景白色像素比例；
- [ ] 背景均匀度；
- [ ] 最大异常背景连通区域；
- [ ] 主体居中；
- [ ] bbox 宽高占比；
- [ ] Mask 实际面积；
- [ ] 安全边距与碰边；
- [ ] 疑似裁切。

### 质量类

- [ ] 主体 ROI 模糊；
- [ ] JPEG 压缩块；
- [ ] 过曝与欠曝；
- [ ] Alpha 白边、毛边和残留。

### 覆盖类

- [ ] 二维码；
- [ ] 条形码；
- [ ] 图片边框。

### 前端

- [ ] 问题按严重度分组；
- [ ] 显示指标和简明解释；
- [ ] 显示问题区域框；
- [ ] 提供规则来源入口；
- [ ] 提供“为什么需要确认”的说明。

### 验收

- 100 张首批测试集完成；
- 确定性 blocker Recall ≥ 90%；
- 正常图误报率 < 10%；
- 每条规则都有正、负和边界样本；
- 单张确定性分析 P95 ≤ 3 秒。

## 6. Sprint 4：自动修复与复检闭环

### 目标

由“检测结果”生成可选择的修复计划，而不是统一套用一套生成参数。

### 后端任务

- [ ] 定义 `FixAction` 和风险等级；
- [ ] 根据 issue 生成 `fix_plan`；
- [ ] 新增 `POST /api/compliance/repair`；
- [ ] 支持只执行选中的修复；
- [ ] 保存修复参数和操作日志；
- [ ] 修复后执行相同规则集复检；
- [ ] 计算已解决、仍存在和新增问题；
- [ ] 增加商品真实性保护指标。

### 第一批修复器

- [ ] EXIF 旋转；
- [ ] 格式转换；
- [ ] 文件压缩；
- [ ] 画布尺寸；
- [ ] 主体居中；
- [ ] 主体缩放；
- [ ] 换纯白背景；
- [ ] 移除不需要的 Alpha；
- [ ] 轻度曝光、对比度和锐度调整；
- [ ] 基础 Alpha 边缘修复。

### 前端任务

- [ ] 修复项多选；
- [ ] 标注 Safe、Review、Manual only；
- [ ] 原图/修复图滑块对比；
- [ ] 已解决、仍存在和新增问题列表；
- [ ] 支持撤销单项修复并重新生成；
- [ ] 下载图片和 JSON/PDF 报告。

### 验收

- 用户可以只选择部分修复；
- 修复后不是复用原报告；
- Safe 修复不得明显改变商品颜色、Logo、数量和外形；
- 新增 blocker 时结果不能标记为完成；
- 每次修复可通过日志复现。

## 7. Sprint 5：OCR 与高频违规元素

### 任务顺序

1. PaddleOCR 集成；
2. 文字区域与包装区域初步区分；
3. 价格和货币符号；
4. 折扣百分比；
5. Free Shipping 和 Call to action；
6. URL、邮箱和电话；
7. 水印与重复透明文字；
8. 后期覆盖 Logo；
9. OCR 结果的置信度和人工确认。

### 规则策略

- 包装本体文字不能简单视为违规；
- 背景覆盖文字比商品内部文字风险更高；
- OCR 低置信度输出 review；
- 去文字、去水印默认不自动执行；
- 使用多语言关键词库，并记录语言。

### 验收

- 能展示文字内容和坐标；
- 能区分明显背景覆盖文字与商品包装文字；
- 价格、折扣和运输促销有独立规则；
- OCR 不可用时不影响确定性规则运行。

## 8. Sprint 6：批量、反馈与商业化

### 批量处理

- [ ] 多图上传；
- [ ] 批量选择平台和图片角色；
- [ ] 后台任务队列；
- [ ] 批量结果表；
- [ ] 按问题筛选；
- [ ] 批量应用 Safe 修复；
- [ ] ZIP 下载；
- [ ] CSV 合规报告。

### 反馈闭环

- [ ] 审核通过/失败反馈；
- [ ] 失败原因和截图；
- [ ] 规则版本关联；
- [ ] 误报/漏报统计；
- [ ] 用户授权的数据改进选项；
- [ ] 管理端反馈列表。

### 商业化

建议第一版：

- 免费：每天 3 张预检；
- 单次包：50 张检测与 Safe 修复；
- 月度套餐：300 张；
- 高级套餐：批量、报告、多平台；
- 后续：API Key 和团队账号。

### 验收

- 批量任务失败不会丢失全部结果；
- 每张图独立记录规则版本；
- 计费按成功进入分析的图片或明确规则执行；
- 免费限制不能绕过；
- 用户可删除数据和反馈。

## 9. 建议 GitHub Issues

按以下标题创建任务：

### Epic A：检测可信化

1. `feat: add source image pre-compliance analysis API`
2. `fix: prevent silent segmentation fallback from passing compliance`
3. `feat: persist subject masks and segmentation confidence`
4. `refactor: split pre-check and post-check reports`
5. `test: add compliance fixture manifest and baseline reports`

### Epic B：规则引擎

6. `feat: introduce JSON-based compliance rule engine`
7. `feat: support platform role category and marketplace rule filters`
8. `feat: add rule severity confidence and unknown status`
9. `feat: persist rule IDs and rule-set version in reports`
10. `refactor: replace fixed compliance penalties with rule aggregation`

### Epic C：检测器

11. `feat: add background uniformity and artifact detector`
12. `feat: add mask-based subject area margin and centering metrics`
13. `feat: detect edge contact and cropping risk`
14. `feat: add subject-only blur exposure and compression checks`
15. `feat: detect alpha edge residue and isolated fragments`
16. `feat: detect QR codes barcodes and image borders`

### Epic D：自动修复

17. `feat: generate issue-based selective fix plans`
18. `feat: add safe technical and composition fixers`
19. `feat: run post-fix compliance reanalysis`
20. `feat: add repair authenticity guardrails`
21. `feat: add before-after comparison and issue overlays`
22. `feat: export compliance report with generated assets`

### Epic E：扩展与商业化

23. `feat: add OCR and promotional text rules`
24. `feat: add batch compliance jobs and ZIP export`
25. `feat: collect real platform review feedback`
26. `feat: add usage quota and compliance billing events`

## 10. 优先级

### P0：没有这些不能称为合规产品

- 原图预检；
- 抠图失败显式状态；
- Mask；
- 平台规则引擎；
- 首批 20 条规则；
- 修复后复检；
- 测试集和误报漏报指标。

### P1：形成明显产品价值

- OCR 和促销词；
- 问题区域可视化；
- 选择性修复；
- 前后对比；
- PDF/CSV 报告；
- 批量处理。

### P2：形成长期壁垒

- 类目规则；
- 商品与标题一致性；
- 颜色、数量和套装；
- 图片组级检查；
- 真实审核反馈校准；
- 规则管理后台；
- API 与平台插件。

## 11. 首个发布门槛

达到以下条件后再把首页核心卖点改成“主图合规检查与自动修复”：

- Amazon 主图和 Google Merchant 通用规则可选择；
- 原图和修复图报告独立；
- 抠图低置信度不会被误判为通过；
- 首批 20 条规则通过测试；
- 支持至少 8 项 Safe 修复；
- 修复结果可复检和对比；
- 有规则来源与版本；
- 有实际平台审核反馈入口；
- 产品页面明确说明不保证平台审核结果。
