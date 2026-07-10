# 03. 规则引擎与规则库规划

## 1. 设计目标

规则库用于描述“在什么上下文下，使用哪个检测器，以什么阈值判断问题，以及能否自动修复”。

规则不应继续写死在 Python 条件分支中。平台规则、阈值和来源经常变化，必须支持独立版本管理。

## 2. 目录结构

```text
backend/app/compliance/rules/
├── universal/
│   ├── technical.json
│   ├── composition.json
│   ├── quality.json
│   └── overlay.json
├── amazon/
│   ├── main-image.json
│   └── secondary-image.json
├── google-merchant/
│   └── product-image.json
└── schemas/
    └── rule.schema.json
```

## 3. 规则结构

```json
{
  "id": "amazon.main.background.white",
  "enabled": true,
  "platform": "amazon",
  "marketplace": "US",
  "image_role": "main",
  "category": "*",
  "severity": "blocker",
  "title": "主图背景应为纯白色",
  "description": "主体外背景存在明显非白区域。",
  "detector": "background_uniformity",
  "threshold": {
    "white_pixel_ratio_min": 0.985,
    "largest_nonwhite_component_ratio_max": 0.0015
  },
  "confidence_policy": {
    "minimum": 0.8,
    "below_minimum_status": "unknown"
  },
  "auto_fix": "replace_background_white",
  "requires_confirmation": false,
  "effective_from": "2026-07-01",
  "effective_to": null,
  "source": {
    "type": "official",
    "url": "",
    "checked_at": "2026-07-10",
    "notes": "上线前补充并复核官方来源"
  },
  "rule_version": "1.0.0"
}
```

## 4. 规则上下文优先级

规则匹配从通用到具体叠加：

```text
Universal
→ Platform
→ Marketplace
→ Image role
→ Category
```

冲突时优先级：

```text
类目规则 > 图片角色规则 > 站点规则 > 平台规则 > 通用规则
```

必须记录最终生效规则列表，方便复现历史报告。

## 5. 严重程度

| 等级 | 含义 | 最终状态影响 |
|---|---|---|
| blocker | 高概率导致拒绝或明显不满足硬要求 | 高置信度失败时整体 fail |
| warning | 规则存在灰度或可能影响审核 | 整体 review/fail 取决于策略 |
| quality | 不一定违规，但影响图片质量 | 不直接阻断 |
| info | 优化建议 | 不扣分或轻微扣分 |

## 6. 置信度处理

每条规则同时拥有“规则确定性”和“本次检测置信度”。

推荐逻辑：

```text
检测置信度 >= rule.minimum
  → 根据阈值输出 pass / fail

检测置信度 < rule.minimum
  → 输出 unknown，需要人工确认
```

禁止将低置信度结果直接当作通过。

## 7. 最终状态

建议状态：

- `pass`：无 blocker，且无必须确认项；
- `review`：无高置信度 blocker，但存在 unknown 或 warning；
- `fail`：存在高置信度 blocker；
- `error`：图片无法读取或分析流程失败。

分数只用于排序和展示，最终状态不能只依赖分数。

## 8. 首批 20 条规则

### A. 文件技术类

| ID | 规则 | 严重度 | 自动修复 |
|---|---|---|---|
| universal.file.readable | 文件可正常解码 | blocker | 否 |
| universal.file.real-format | 扩展名与实际格式一致 | warning | 转换格式 |
| universal.file.min-dimensions | 最小尺寸达标 | blocker/warning | 放大导出，需提示原始细节不会增加 |
| universal.file.max-size | 文件体积不超限制 | blocker | 压缩 |
| universal.file.orientation | 无异常 EXIF 方向 | warning | 自动旋转 |

### B. 背景与构图类

| ID | 规则 | 严重度 | 自动修复 |
|---|---|---|---|
| main.background.white | 背景接近纯白 | blocker | 换白底 |
| main.background.uniform | 背景颜色均匀 | blocker | 换白底 |
| main.background.no-large-artifact | 无大块背景杂物 | blocker | 重抠图/换背景，需确认 |
| main.subject.centered | 主体居中 | warning | 居中 |
| main.subject.dimension-ratio | 主体宽高占比合理 | warning | 缩放 |
| main.subject.mask-area | 主体真实面积不过小 | warning | 缩放 |
| main.subject.safe-margin | 主体未触碰边缘 | blocker | 缩小与居中 |
| main.subject.not-cropped | 主体无明显裁切 | blocker | 默认只报警 |

### C. 图片质量类

| ID | 规则 | 严重度 | 自动修复 |
|---|---|---|---|
| universal.quality.blur | 主体无明显模糊 | warning | 轻度增强，严重时只报警 |
| universal.quality.jpeg-artifact | 无明显压缩块 | quality | 重编码只能有限改善 |
| universal.quality.exposure | 主体不过曝或欠曝 | warning | 轻度曝光调整 |
| universal.quality.alpha-edge | 无明显白边、毛边和透明残留 | warning | 边缘修复，需复检 |

### D. 覆盖元素类

| ID | 规则 | 严重度 | 自动修复 |
|---|---|---|---|
| main.overlay.no-qr | 主图不含二维码 | blocker | 默认只报警 |
| main.overlay.no-barcode | 主图无非商品本体条形码覆盖 | warning/blocker | 默认只报警 |
| main.overlay.no-border | 图片无明显外边框 | blocker/warning | 裁切或重建画布 |

## 9. 第二批规则

第二批在 OCR 和目标检测稳定后加入：

- 覆盖文字；
- 价格；
- 折扣；
- Free Shipping；
- Call to action；
- 水印；
- 后期覆盖 Logo；
- URL、邮箱和联系电话；
- 人物、人脸和手部；
- 多目标和多余道具；
- 占位图、纯 Logo 图；
- 商品标题与图片一致性；
- 颜色、数量和套装一致性；
- 敏感内容；
- AI 生成图片元数据。

## 10. 规则来源库

没有一个公开数据库能完整覆盖所有电商平台。规则库需组合：

1. 平台官方帮助中心和卖家文档；
2. Google Merchant 等结构化公共商品图片规范；
3. 内容安全服务的审核标签；
4. 平台实际拒绝截图和卖家反馈；
5. 团队人工验证和测试样本。

建议新增来源清单：

```text
docs/compliance-sources/
├── source-registry.csv
└── review-notes/
```

`source-registry.csv` 字段：

```text
platform,marketplace,image_role,category,title,url,source_type,checked_at,effective_from,status,owner,notes
```

规则发布前要求：

- 至少一个官方或高可信来源；
- 记录最近核验日期；
- 无法确认的规则只能标记为 `warning` 或实验规则；
- 来源变更时提升规则集版本。

## 11. 规则版本

建议规则集版本：

```text
amazon-main-2026.07.1
google-merchant-product-2026.07.1
universal-product-image-2026.07.1
```

语义：

- 年月：规则资料核验周期；
- 末位版本：阈值或规则修订次数。

每份报告必须保存实际使用的规则 ID、规则版本和规则集版本。

## 12. 规则管理后台

不作为 MVP 阻塞项，但后续应支持：

- 启用/禁用规则；
- 修改阈值；
- 查看来源；
- 按平台和类目筛选；
- 规则灰度发布；
- 对比新旧规则命中率；
- 回滚规则集；
- 查看误报与漏报反馈。
