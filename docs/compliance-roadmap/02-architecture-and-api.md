# 02. 合规处理架构、数据模型与 API

## 1. 目标架构

将现有“生成后调用一次固定评分函数”调整为独立的合规处理域。

```text
Source Image
  ├─ 原始文件元数据
  ├─ 主体 Mask
  ├─ 分割状态与置信度
  └─ Pre-check Report
          ↓
      Rule Engine
          ↓
       Fix Plan
          ↓
     Repair Pipeline
          ↓
     Generated Asset
  ├─ 修复操作记录
  └─ Post-check Report
```

建议新增目录：

```text
backend/app/compliance/
├── engine.py              # 规则筛选、执行、聚合与最终状态
├── models.py              # 内部领域对象
├── registry.py            # 检测器和修复器注册
├── scoring.py             # 严重程度、置信度与分数
├── evidence.py            # 证据框、Mask 和调试图层
├── detectors/
│   ├── technical.py
│   ├── background.py
│   ├── composition.py
│   ├── quality.py
│   ├── code_detection.py
│   └── overlay.py
├── fixes/
│   ├── technical.py
│   ├── background.py
│   ├── composition.py
│   └── quality.py
└── rules/
    ├── universal/
    ├── amazon/
    └── google-merchant/
```

现有 `app/services/compliance.py` 可以先作为兼容层，逐步迁移后删除或仅保留旧接口适配。

## 2. 三阶段处理

## 2.1 Pre-check

输入原始上传图，不执行白底、居中或主体缩放。

职责：

- 读取真实文件格式和元数据；
- 修正 EXIF 仅用于分析副本，不覆盖原文件；
- 生成或读取主体 Mask；
- 记录分割成功、失败或低置信度；
- 执行平台规则；
- 输出问题、证据、指标和可修复项。

## 2.2 Repair

根据用户确认的 `fix_plan` 执行修复。

职责：

- 只执行被选择的操作；
- 按依赖顺序执行；
- 保存每一步参数；
- 不允许高风险操作静默执行；
- 保留原图，不做覆盖写入；
- 输出生成资产和修复日志。

建议执行顺序：

```text
方向修正
→ 分割/抠图
→ 边缘修复
→ 背景处理
→ 主体缩放与居中
→ 画布尺寸
→ 亮度、对比度、锐度
→ 文件格式与压缩
```

## 2.3 Post-check

对最终导出文件使用同一平台、图片角色、类目和规则版本重新检测。

职责：

- 判断哪些问题已解决；
- 识别修复产生的新问题；
- 输出仍需确认的问题；
- 生成前后对比；
- 保存最终结果与规则版本。

## 3. API 规划

## 3.1 原图分析

```http
POST /api/compliance/analyze
Content-Type: application/json
```

请求：

```json
{
  "source_image_id": "uuid",
  "platform": "amazon",
  "marketplace": "US",
  "image_role": "main",
  "category": "general"
}
```

响应：

```json
{
  "analysis_id": "uuid",
  "source_image_id": "uuid",
  "context": {
    "platform": "amazon",
    "marketplace": "US",
    "image_role": "main",
    "category": "general",
    "rule_set_version": "amazon-main-2026.07"
  },
  "status": "fail",
  "score": 58,
  "segmentation": {
    "status": "success",
    "confidence": 0.93,
    "mask_url": "/api/compliance/analyses/.../mask"
  },
  "metrics": {},
  "issues": [],
  "fix_plan": []
}
```

## 3.2 执行修复

```http
POST /api/compliance/repair
Content-Type: application/json
```

请求：

```json
{
  "analysis_id": "uuid",
  "selected_fix_ids": [
    "fix-background-white",
    "fix-subject-center",
    "fix-export-size"
  ],
  "output": {
    "width": 2000,
    "height": 2000,
    "format": "jpg"
  }
}
```

响应可以沿用后台任务模式：

```json
{
  "task_id": "uuid",
  "status": "queued"
}
```

## 3.3 查询结果

```http
GET /api/compliance/tasks/{task_id}
```

响应：

```json
{
  "task_id": "uuid",
  "status": "success",
  "progress": 100,
  "asset": {},
  "repair_log": [],
  "pre_check": {},
  "post_check": {},
  "comparison": {
    "resolved_issue_ids": [],
    "remaining_issue_ids": [],
    "new_issue_ids": []
  }
}
```

## 3.4 用户审核反馈

```http
POST /api/compliance/feedback
```

请求：

```json
{
  "asset_id": "uuid",
  "platform": "amazon",
  "marketplace": "US",
  "actual_result": "rejected",
  "rejection_reason": "平台提示文字",
  "notes": "背景被识别为非纯白"
}
```

## 4. 领域对象

## 4.1 ComplianceContext

```python
class ComplianceContext:
    platform: str
    marketplace: str | None
    image_role: str
    category: str
    rule_set_version: str
```

## 4.2 ComplianceIssue

```python
class ComplianceIssue:
    id: str
    rule_id: str
    severity: str
    status: str
    title: str
    description: str
    confidence: float
    metrics: dict
    evidence: list
    auto_fix: str | None
    requires_confirmation: bool
```

建议 `status` 取值：

- `failed`
- `warning`
- `passed`
- `unknown`
- `not_applicable`

其中 `unknown` 很重要：模型或分割置信度不足时，不能强行判定通过或失败。

## 4.3 EvidenceRegion

```python
class EvidenceRegion:
    type: str            # bbox, polygon, mask, full_image
    coordinates: list
    label: str
    confidence: float
    preview_url: str | None
```

所有能够定位的问题尽量返回证据区域，例如：

- 背景异常色块；
- 商品碰边位置；
- 二维码位置；
- 边框范围；
- 抠图白边区域。

## 4.4 FixAction

```python
class FixAction:
    id: str
    issue_id: str
    action: str
    risk: str
    selected_by_default: bool
    parameters: dict
    requires_confirmation: bool
```

风险分级：

- `safe`
- `review`
- `manual_only`

## 5. 数据库调整

建议新增表，而不是将所有信息继续塞进 `compliance_json`。

### compliance_analyses

- `id`
- `user_id`
- `source_image_id`
- `platform`
- `marketplace`
- `image_role`
- `category`
- `rule_set_version`
- `status`
- `score`
- `segmentation_status`
- `segmentation_confidence`
- `mask_path`
- `metrics_json`
- `issues_json`
- `fix_plan_json`
- `created_at`

### compliance_repair_runs

- `id`
- `analysis_id`
- `generation_task_id`
- `selected_fixes_json`
- `repair_log_json`
- `post_check_json`
- `created_at`

### compliance_feedback

- `id`
- `user_id`
- `asset_id`
- `platform`
- `marketplace`
- `category`
- `rule_set_version`
- `predicted_status`
- `actual_result`
- `rejection_reason`
- `notes`
- `created_at`

MVP 可先使用 JSON 字段，等数据稳定后再将 issue 和 evidence 拆表。

## 6. 检测器接口

```python
class Detector(Protocol):
    name: str

    def analyze(
        self,
        image: Image.Image,
        mask: Image.Image | None,
        context: ComplianceContext,
        rule: ComplianceRule,
    ) -> DetectorResult:
        ...
```

要求：

- 检测器不直接决定最终总分；
- 检测器只输出指标、状态、置信度和证据；
- 规则引擎根据规则严重程度和阈值聚合；
- 相同底层指标应缓存，避免多条规则重复计算。

## 7. 缓存与性能

建议一次分析创建 `ImageAnalysisCache`：

```text
normalized_rgb
normalized_rgba
mask
subject_bbox
subject_roi
background_mask
connected_components
histogram
edge_map
laplacian_map
qr_results
barcode_results
```

性能目标：

- 首批确定性规则单张分析 P95 不超过 3 秒；
- 不含 OCR 和大型视觉模型；
- 同一图片、同一规则版本允许复用分析结果；
- 修复后复检必须重新计算受影响指标，不能直接复制原结果。

## 8. 兼容现有接口

现有 `/api/generate` 暂时保持可用。

迁移阶段：

1. `/api/generate` 继续提供原功能；
2. 新增 `/api/compliance/*`；
3. 新前端流程优先使用合规接口；
4. 生成资产仍可保留简化版 `compliance` 字段；
5. 稳定后将旧固定评分替换为新 Post-check 摘要。
