# 04. 检测器与自动修复实现规划

## 1. 总体原则

检测器负责提供事实，规则负责解释事实，修复器负责执行明确操作。

```text
Detector → metrics + evidence + confidence
Rule     → pass / fail / unknown + severity
Fixer    → output image + operation log
```

不要让单个检测器同时承担平台规则、打分和修图逻辑。

## 2. 主体分割与 Mask

## 2.1 当前问题

抠图失败时不能继续把整张原图当成可靠主体。

## 2.2 输出结构

```json
{
  "status": "success|low_confidence|failed",
  "confidence": 0.93,
  "mask_path": "...",
  "bbox": [120, 90, 1820, 1910],
  "foreground_area_ratio": 0.47,
  "touches_edge": false,
  "rectangularity": 0.64
}
```

## 2.3 低置信度启发式

以下情况降低置信度：

- Mask 几乎覆盖整张画布；
- Mask 外轮廓接近完整矩形；
- 主体与背景颜色差异过小；
- 前景存在大量孤立连通区域；
- Alpha 通道只有极少层级，边缘异常生硬；
- Mask 面积过小或过大；
- 重复运行结果差异明显。

第一版无法获得模型原生置信度时，可以用这些指标生成工程置信度。

## 3. 文件技术检测器

## 3.1 文件可读性

检查：

- Pillow 是否可解码；
- 文件是否截断；
- 像素尺寸是否合法；
- 解码后是否为空图。

## 3.2 真实格式

通过文件头和解码格式判断真实格式，不只依赖扩展名或 MIME。

输出：

```json
{
  "extension": "jpg",
  "declared_mime": "image/jpeg",
  "detected_format": "PNG",
  "matches": false
}
```

## 3.3 尺寸和文件体积

检测器只输出真实值，平台规则决定阈值。

## 3.4 EXIF 方向

记录：

- 原始 Orientation；
- 是否需要旋转；
- 修正后的宽高；
- 是否已在导出时移除异常方向标记。

## 4. 背景检测器

建议组合以下指标：

- 背景像素平均 RGB；
- RGB 每通道达到白色阈值的像素比例；
- 背景亮度和色彩方差；
- 最大非白连通区域占比；
- 所有非白连通区域总占比；
- 四角色差；
- 是否存在明显渐变；
- 是否存在原图矩形边界；
- 主体周围的白边或彩色光晕。

背景区域应使用主体 Mask 的反集，并在主体周围保留安全缓冲区，避免把商品本身颜色计入背景。

输出示例：

```json
{
  "white_pixel_ratio": 0.972,
  "background_rgb_mean": [251.2, 249.8, 249.1],
  "background_std": 7.4,
  "largest_nonwhite_component_ratio": 0.006,
  "corner_delta_e_max": 4.1,
  "gradient_score": 0.18
}
```

## 5. 构图检测器

必须同时输出：

- `bbox_width_ratio`
- `bbox_height_ratio`
- `bbox_area_ratio`
- `mask_area_ratio`
- `convex_hull_ratio`
- `center_offset_x`
- `center_offset_y`
- `margin_left`
- `margin_right`
- `margin_top`
- `margin_bottom`
- `touches_edge`

对于细长商品，不允许只使用最长边占比。

## 5.1 裁切风险

第一版使用组合启发式：

- Mask 是否接触边缘；
- 接触边缘的长度比例；
- 边缘处轮廓是否仍有明显延伸趋势；
- 主体边界是否在多处被画布截断；
- 原图是否本身紧贴边缘。

高置信度碰边可直接失败；复杂裁切输出 `unknown`，不要强行判断完整性。

## 6. 图片质量检测器

## 6.1 模糊

只在主体 ROI 内分析，组合：

- Laplacian variance；
- Tenengrad；
- 高频能量；
- 主体缩放归一化后的指标。

不同品类差异较大，第一版阈值应通过测试集校准。

## 6.2 曝光

输出：

- 主体高光溢出比例；
- 主体暗部剪切比例；
- 主体平均亮度；
- 动态范围；
- 各通道剪切情况。

## 6.3 JPEG 压缩失真

检查 8×8 block 边界差异和高频异常。该项优先作为 `quality`，不要在阈值未校准前作为 blocker。

## 6.4 抠图边缘

检查：

- Mask 边缘内外颜色差；
- 半透明像素带宽；
- 亮色背景遗留形成的白边；
- 孤立前景碎片；
- 孔洞和断裂；
- 平滑后是否损失细节。

## 7. 二维码、条形码与边框

### 二维码

优先使用 OpenCV `QRCodeDetector`，返回检测框和解码结果。无法解码但具有二维码结构时，也应返回疑似结果。

### 条形码

可选 ZXing 或 pyzbar。要区分：

- 商品包装本身的条形码；
- 后期覆盖在背景上的条形码。

第一版无法可靠区分时，输出 `review`，不要全部当 blocker。

### 边框

检查：

- 四边是否存在连续高对比色带；
- 边框宽度是否一致；
- 四边颜色是否一致；
- 边框内侧是否形成封闭矩形。

## 8. 第二批视觉能力

第二批再接入：

- PaddleOCR：文字和坐标；
- 关键词规则：价格、折扣、运费、Call to action；
- YOLO：人物、多目标、手部、道具；
- Logo 检测：区分包装印刷与后期覆盖；
- CLIP/SigLIP：图片与标题初步一致性；
- pHash + Embedding：图片组重复检测；
- 云内容审核：成人、暴力、武器等。

## 9. 自动修复分级

## 9.1 Safe：可默认勾选

- EXIF 方向修正；
- 文件格式转换；
- 画布尺寸调整；
- 文件压缩；
- 主体居中；
- 主体按安全范围缩放；
- 换纯白背景；
- 移除不需要的 Alpha；
- 轻度曝光、对比度和锐度优化。

## 9.2 Review：执行前后都需确认

- 重新抠图；
- 白边和毛边修复；
- 去背景杂点；
- 删除二维码、文字、水印或 Logo；
- 局部重绘；
- 补全疑似被裁切区域；
- 删除多余道具。

这些操作必须提供前后对比，默认不自动提交为最终结果。

## 9.3 Manual only：只报警

- 商品与标题不一致；
- 商品颜色不一致；
- 商品数量或套装不一致；
- 疑似侵权；
- 成人、暴力等敏感内容；
- 商品本身标签、包装或品牌信息错误；
- 真实性相关问题。

## 10. 修复器接口

```python
class Fixer(Protocol):
    name: str
    risk: str

    def apply(
        self,
        image: Image.Image,
        mask: Image.Image | None,
        parameters: dict,
    ) -> FixResult:
        ...
```

`FixResult`：

```python
class FixResult:
    image: Image.Image
    mask: Image.Image | None
    changed_regions: list[EvidenceRegion]
    log: dict
    warnings: list[str]
```

## 11. 商品真实性保护

所有修复必须遵守：

- 不修改商品主要颜色；
- 不修改商品 Logo 和包装文字；
- 不改变商品数量；
- 不改变商品外形和关键细节；
- 不自动添加原图不存在的配件；
- 对生成式补全标记操作类型；
- 保存原图和每一步操作记录。

可增加修复前后保护指标：

- 主体区域感知哈希差异；
- 主体 Embedding 相似度；
- 主色差异；
- Logo/OCR 区域变化；
- Mask 轮廓差异。

超出阈值时，修复结果自动进入 `review`，不能直接标记为完成。

## 12. 前端展示

每个问题卡片展示：

- 标题；
- 严重级别；
- 置信度；
- 检测证据；
- 规则来源入口；
- 建议动作；
- 是否可自动修复；
- 修复风险。

结果页至少支持：

- 原图与修复图滑块对比；
- Mask 显示；
- 问题框开关；
- 已解决、仍存在和新增问题分组；
- 撤销单个修复；
- 下载图片和报告。
