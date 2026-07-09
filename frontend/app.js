const API_BASE = window.PRODUCTSHOT_API_BASE || '';
const MAX_UPLOAD_MB = 20;
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;
const ALLOWED_UPLOAD_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const ALLOWED_UPLOAD_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'webp']);
const MIN_OUTPUT_SIZE = 512;
const MAX_OUTPUT_SIZE = 4096;
const OUTPUT_FORMATS = new Set(['png', 'jpg', 'webp']);

const state = {
  templates: [],
  selectedTemplateId: 'amazon-white-main',
  sourceImage: null,
  selectedSize: { width: 1600, height: 1600 },
  background: 'white',
  customBackgroundColor: '#F7F9FC',
  customBackgroundActive: false,
  outputFormat: 'png',
  lastTask: null,
  historyTasks: [],
  localPreviewUrl: null,
  customSizeActive: false,
};

const templateIllustrations = {
  'amazon-white-main': '<div class="bottle"></div>',
  'temu-white-main': '<div class="kettle"></div>',
  'shopify-main': '<div class="bag"></div>',
  'transparent-png': '<div class="bottle"></div>',
  'soft-shadow-packshot': '<div class="shoe"></div>',
  'mobile-cover-4x5': '<div class="mugs"><i></i><i></i><i></i><i></i></div>',
};

const assetLabels = {
  'amazon-white-main': '白底主图',
  'temu-white-main': 'Temu 主图',
  'shopify-main': 'Shopify 主图',
  'transparent-png': '透明 PNG',
  'soft-shadow-packshot': '轻阴影图',
  'mobile-cover-4x5': '移动端 4:5',
  'hd-2000px': '2000px 高清图',
};

const assetOrder = ['amazon-white-main', 'temu-white-main', 'shopify-main', 'mobile-cover-4x5', 'transparent-png', 'soft-shadow-packshot', 'hd-2000px'];

const fallbackTemplates = [
  { id: 'amazon-white-main', name: 'Amazon 白底主图', width: 2000, height: 2000, background: 'white', product_fill_ratio: 0.85, shadow_enabled: false },
  { id: 'temu-white-main', name: 'Temu 跨境主图', width: 1600, height: 1600, background: 'white', product_fill_ratio: 0.82, shadow_enabled: false },
  { id: 'shopify-main', name: 'Shopify 独立站主图', width: 1600, height: 1600, background: 'white', product_fill_ratio: 0.78, shadow_enabled: true },
  { id: 'transparent-png', name: '透明 PNG', width: 2000, height: 2000, background: 'transparent', product_fill_ratio: 0.86, shadow_enabled: false },
  { id: 'soft-shadow-packshot', name: '轻阴影棚拍图', width: 2000, height: 2000, background: 'white', product_fill_ratio: 0.78, shadow_enabled: true },
  { id: 'mobile-cover-4x5', name: '批量 SKU 图', width: 1600, height: 2000, background: 'white', product_fill_ratio: 0.8, shadow_enabled: true },
];

function $(selector) {
  return document.querySelector(selector);
}

function $all(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function escapeHTML(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function toast(message, type = '') {
  const el = document.createElement('div');
  el.className = `toast ${type}`.trim();
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try {
      const data = await response.json();
      message = data.detail || message;
    } catch (_) {}
    throw new Error(message);
  }
  return response.json();
}

function getTemplateName(template) {
  return escapeHTML(template?.name || assetLabels[template?.id] || template?.id || '模板');
}

function getTemplateDisplayName(templateId) {
  const template = state.templates.find(item => item.id === templateId);
  return template?.name || assetLabels[templateId] || templateId || '未知模板';
}

function getFileExtension(file) {
  return String(file?.name || '').split('.').pop()?.toLowerCase() || '';
}

function formatFileSize(bytes) {
  if (!Number.isFinite(bytes)) return '未知大小';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDateTime(value) {
  if (!value) return '未知时间';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未知时间';
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function normalizeHexColor(value) {
  const color = String(value || '').trim();
  return /^#[0-9a-fA-F]{6}$/.test(color) ? color.toUpperCase() : null;
}

function validateUploadFile(file) {
  if (!file) return { ok: false, message: '请选择一张商品图片。' };
  const extension = getFileExtension(file);
  const typeAllowed = ALLOWED_UPLOAD_TYPES.has(file.type);
  const extensionAllowed = ALLOWED_UPLOAD_EXTENSIONS.has(extension);
  if (!typeAllowed && !extensionAllowed) return { ok: false, message: '仅支持 JPG、PNG、WebP 格式的商品图片。' };
  if (!file.size) return { ok: false, message: '图片文件为空，请重新选择。' };
  if (file.size > MAX_UPLOAD_BYTES) return { ok: false, message: `图片过大，当前 ${formatFileSize(file.size)}，最大支持 ${MAX_UPLOAD_MB}MB。` };
  return { ok: true, message: '' };
}

function clearLocalPreviewUrl() {
  if (state.localPreviewUrl) {
    URL.revokeObjectURL(state.localPreviewUrl);
    state.localPreviewUrl = null;
  }
}

function getImageDimensions(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight });
    image.onerror = () => reject(new Error('无法读取图片内容，请确认文件未损坏。'));
    image.src = url;
  });
}

async function renderLocalUploadPreview(file) {
  clearLocalPreviewUrl();
  const previewUrl = URL.createObjectURL(file);
  state.localPreviewUrl = previewUrl;
  try {
    const dimensions = await getImageDimensions(previewUrl);
    renderUploadedPreview({
      public_url: previewUrl,
      original_filename: file.name || '本地商品图',
      width: dimensions.width,
      height: dimensions.height,
      content_type: `${file.type || '未知类型'} · ${formatFileSize(file.size)}`,
    });
    setPreviewImage(previewUrl, '已选择');
    return dimensions;
  } catch (error) {
    clearLocalPreviewUrl();
    throw error;
  }
}

function renderLandingTemplates() {
  const container = $('#landingTemplates');
  if (!container) return;
  container.innerHTML = state.templates.map(template => `
    <article class="card template-card ${template.id === state.selectedTemplateId ? 'active' : ''}" data-template-card="${escapeHTML(template.id)}">
      <div class="template-thumb ${template.background === 'transparent' ? 'checker-bg' : ''}">${templateIllustrations[template.id] || '<div class="bottle"></div>'}</div>
      <h3>${getTemplateName(template)}</h3>
    </article>
  `).join('');
}

function renderTemplateOptions() {
  const container = $('#templateOptions');
  if (!container) return;
  container.innerHTML = state.templates.map(template => `
    <button type="button" data-template="${escapeHTML(template.id)}" class="${template.id === state.selectedTemplateId ? 'active' : ''}">${getTemplateName(template)}</button>
  `).join('');

  $all('[data-template]').forEach(button => button.addEventListener('click', () => selectTemplate(button.dataset.template)));
  $all('[data-template-card]').forEach(card => {
    card.addEventListener('click', () => {
      selectTemplate(card.dataset.templateCard);
      $('#dashboard')?.scrollIntoView({ behavior: 'smooth' });
    });
  });
}

function findSelectedPresetButton() {
  return $all('#sizeOptions button:not([data-custom])').find(button => {
    return Number(button.dataset.width) === state.selectedSize.width && Number(button.dataset.height) === state.selectedSize.height;
  });
}

function updateCustomSizeButton() {
  const customButton = $('#customSizeBtn');
  if (!customButton) return;
  const presetButton = findSelectedPresetButton();
  customButton.textContent = state.customSizeActive || !presetButton ? `${state.selectedSize.width} × ${state.selectedSize.height}` : '自定义';
}

function setSelectedSize(width, height, options = {}) {
  state.selectedSize = { width, height };
  const presetMatch = $all('#sizeOptions button:not([data-custom])').some(button => Number(button.dataset.width) === width && Number(button.dataset.height) === height);
  state.customSizeActive = Boolean(options.custom) || !presetMatch;
  updateCustomSizeButton();
  syncActiveButtons();
}

function updateCustomColorControls() {
  const colorInput = $('#customColorInput');
  const colorText = $('#customColorText');
  const colorRow = $('#customColorRow');
  const customButton = $('#customColorBtn');
  if (colorInput) colorInput.value = state.customBackgroundColor;
  if (colorText) colorText.textContent = state.customBackgroundColor;
  if (colorRow) colorRow.hidden = !state.customBackgroundActive;
  if (customButton) customButton.textContent = state.customBackgroundActive ? `自定义 ${state.customBackgroundColor}` : '自定义颜色';
}

function updateFormatControls() {
  $all('#formatOptions button').forEach(button => {
    button.classList.toggle('active', button.dataset.format === state.outputFormat);
  });
  const hint = $('#formatHint');
  if (!hint) return;
  if (state.background === 'transparent') {
    hint.textContent = '透明背景已固定使用 PNG，避免透明区域丢失。';
  } else if (state.outputFormat === 'jpg') {
    hint.textContent = 'JPG 体积更小，但不支持透明背景，适合白底或浅色背景主图。';
  } else if (state.outputFormat === 'webp') {
    hint.textContent = 'WebP 适合网页展示，通常体积更小。';
  } else {
    hint.textContent = 'PNG 适合透明图和高质量主图。';
  }
}

function setOutputFormat(format, options = {}) {
  if (!OUTPUT_FORMATS.has(format)) {
    toast('输出格式仅支持 PNG、JPG、WebP。', 'error');
    return;
  }
  if (state.background === 'transparent' && format !== 'png') {
    state.outputFormat = 'png';
    updateFormatControls();
    if (!options.silent) toast('透明背景需要使用 PNG，已自动切回 PNG。', 'error');
    return;
  }
  state.outputFormat = format;
  updateFormatControls();
}

function enforceOutputFormatForBackground(options = {}) {
  if (state.background === 'transparent' && state.outputFormat !== 'png') {
    state.outputFormat = 'png';
    updateFormatControls();
    if (!options.silent) toast('透明背景需要使用 PNG，已自动切回 PNG。', 'error');
  } else {
    updateFormatControls();
  }
}

function setBackground(background, options = {}) {
  if (background === 'custom') {
    state.customBackgroundActive = true;
    state.background = state.customBackgroundColor;
  } else {
    state.customBackgroundActive = Boolean(options.custom);
    state.background = background;
  }
  updateCustomColorControls();
  syncActiveButtons();
  enforceOutputFormatForBackground(options);
}

function setCustomBackgroundColor(value) {
  const color = normalizeHexColor(value);
  if (!color) {
    toast('请选择有效的 6 位十六进制颜色。', 'error');
    return;
  }
  state.customBackgroundColor = color;
  state.customBackgroundActive = true;
  state.background = color;
  updateCustomColorControls();
  syncActiveButtons();
  enforceOutputFormatForBackground({ silent: true });
}

function updateDownloadAllButton(task = state.lastTask) {
  const button = $('#downloadAllBtn');
  if (!button) return;
  const canDownload = Boolean(task?.id && task.assets?.length);
  button.disabled = !canDownload;
  button.textContent = canDownload ? `下载全部 ${task.assets.length} 张` : '下载全部';
}

function handleDownloadAll() {
  const task = state.lastTask;
  if (!task?.id || !task.assets?.length) {
    toast('当前没有可下载的生成结果。', 'error');
    updateDownloadAllButton(null);
    return;
  }
  window.location.href = `${API_BASE}/api/tasks/${encodeURIComponent(task.id)}/download.zip`;
}

function clearCurrentTaskView(message = '待生成') {
  state.lastTask = null;
  renderResults([]);
  renderCompliance(null, null);
  updateDownloadAllButton(null);
  highlightActiveHistory(null);
  if (state.sourceImage?.public_url) {
    setPreviewImage(state.sourceImage.public_url, '已上传');
  } else {
    setPreviewImage(null, message);
  }
}

async function deleteHistoryTask(taskId, event) {
  event?.stopPropagation();
  const task = state.historyTasks.find(item => item.id === taskId);
  if (!task) {
    toast('没有找到这条历史记录，请刷新列表。', 'error');
    return;
  }
  const templateName = getTemplateDisplayName(task.template_id);
  const ok = window.confirm(`确定删除这条历史记录吗？\n\n${templateName}\n${formatDateTime(task.created_at)}\n\n删除后会同时清理对应生成图片。`);
  if (!ok) return;

  try {
    await api(`/api/tasks/${encodeURIComponent(taskId)}`, { method: 'DELETE' });
    toast('历史记录已删除', 'success');
    state.historyTasks = state.historyTasks.filter(item => item.id !== taskId);
    const deletedCurrent = state.lastTask?.id === taskId;
    if (deletedCurrent) {
      const nextTask = state.historyTasks.find(item => item.assets?.length) || state.historyTasks[0];
      if (nextTask) {
        state.lastTask = nextTask;
        renderTask(nextTask);
      } else {
        clearCurrentTaskView('待生成');
      }
    }
    renderHistoryList(state.historyTasks);
    if (state.lastTask?.id) highlightActiveHistory(state.lastTask.id);
    await loadHistory({ keepCurrent: Boolean(state.lastTask?.id) });
  } catch (error) {
    toast(`删除失败：${error.message}`, 'error');
  }
}

function selectTemplate(templateId) {
  state.selectedTemplateId = templateId;
  const template = state.templates.find(item => item.id === templateId);
  if (template) {
    state.selectedSize = { width: template.width, height: template.height };
    state.customSizeActive = false;
    state.customBackgroundActive = false;
    state.background = template.background || 'white';
    $('#ratioRange').value = Math.round((template.product_fill_ratio || 0.85) * 100);
    $('#ratioText').textContent = `${$('#ratioRange').value}%`;
    $('#addShadow').checked = Boolean(template.shadow_enabled);
  }
  renderLandingTemplates();
  renderTemplateOptions();
  updateCustomSizeButton();
  updateCustomColorControls();
  syncActiveButtons();
  enforceOutputFormatForBackground({ silent: true });
}

function syncActiveButtons() {
  const presetButton = findSelectedPresetButton();
  $all('#sizeOptions button').forEach(button => {
    if (button.dataset.custom) {
      button.classList.toggle('active', state.customSizeActive || !presetButton);
      return;
    }
    const width = Number(button.dataset.width);
    const height = Number(button.dataset.height);
    button.classList.toggle('active', !state.customSizeActive && width === state.selectedSize.width && height === state.selectedSize.height);
  });

  $all('#backgroundOptions button').forEach(button => {
    if (button.dataset.bg === 'custom') {
      button.classList.toggle('active', state.customBackgroundActive);
      return;
    }
    button.classList.toggle('active', !state.customBackgroundActive && button.dataset.bg === state.background);
  });
  updateFormatControls();
}

function setPreviewImage(url, status = '已生成') {
  const img = $('#resultImage');
  const demo = $('#demoProduct');
  const badge = $('#generatedBadge');
  if (!img || !demo || !badge) return;
  if (url) {
    img.src = url;
    img.hidden = false;
    demo.hidden = true;
    badge.textContent = status;
    badge.className = 'generated-badge success';
  } else {
    img.hidden = true;
    demo.hidden = false;
    badge.textContent = status;
    badge.className = 'generated-badge';
  }
}

function renderUploadedPreview(source) {
  const container = $('#uploadedPreview');
  if (!container || !source) return;
  const sizeText = Number.isFinite(source.width) && Number.isFinite(source.height) ? `${source.width} × ${source.height}` : '尺寸读取中';
  const detailText = [sizeText, source.content_type].filter(Boolean).join(' · ');
  container.innerHTML = `
    <img src="${escapeHTML(source.public_url)}" alt="上传的原始商品图" />
    <p><b>${escapeHTML(source.original_filename)}</b><small>${escapeHTML(detailText)}</small></p>
  `;
}

function openCustomSizeModal() {
  const modal = $('#customSizeModal');
  const widthInput = $('#customWidthInput');
  const heightInput = $('#customHeightInput');
  const error = $('#customSizeError');
  if (!modal || !widthInput || !heightInput) return;
  widthInput.value = state.selectedSize.width;
  heightInput.value = state.selectedSize.height;
  if (error) error.textContent = '';
  modal.hidden = false;
  setTimeout(() => widthInput.focus(), 0);
}

function closeCustomSizeModal() {
  const modal = $('#customSizeModal');
  const error = $('#customSizeError');
  if (error) error.textContent = '';
  if (modal) modal.hidden = true;
}

function parseOutputSize(value, label) {
  const number = Number(value);
  if (!Number.isInteger(number)) return { ok: false, message: `${label}必须是整数。` };
  if (number < MIN_OUTPUT_SIZE || number > MAX_OUTPUT_SIZE) return { ok: false, message: `${label}必须在 ${MIN_OUTPUT_SIZE} 到 ${MAX_OUTPUT_SIZE} 像素之间。` };
  return { ok: true, value: number };
}

function applyCustomSize() {
  const widthInput = $('#customWidthInput');
  const heightInput = $('#customHeightInput');
  const error = $('#customSizeError');
  if (!widthInput || !heightInput) return;
  const width = parseOutputSize(widthInput.value, '宽度');
  const height = parseOutputSize(heightInput.value, '高度');
  const message = !width.ok ? width.message : (!height.ok ? height.message : '');
  if (message) {
    if (error) error.textContent = message;
    toast(message, 'error');
    return;
  }
  setSelectedSize(width.value, height.value, { custom: true });
  closeCustomSizeModal();
  toast(`已使用自定义尺寸 ${width.value} × ${height.value}`, 'success');
}

async function handleUpload(file) {
  if (!file) return;
  const status = $('#uploadStatus');
  const validation = validateUploadFile(file);
  if (!validation.ok) {
    if (status) status.textContent = validation.message;
    toast(validation.message, 'error');
    return;
  }

  state.sourceImage = null;
  if (status) status.textContent = '已选择图片，正在生成本地预览...';
  try {
    await renderLocalUploadPreview(file);
  } catch (error) {
    const message = error.message || '无法读取图片内容，请重新选择一张商品图。';
    if (status) status.textContent = message;
    toast(message, 'error');
    return;
  }

  const form = new FormData();
  form.append('file', file);
  if (status) status.textContent = '本地预览已生成，正在上传图片...';
  try {
    const source = await api('/api/upload', { method: 'POST', body: form });
    state.sourceImage = source;
    renderUploadedPreview(source);
    setPreviewImage(source.public_url, '已上传');
    clearLocalPreviewUrl();
    if (status) status.textContent = '上传完成，可以生成主图。';
    toast('图片上传成功', 'success');
  } catch (error) {
    const message = `上传失败：${error.message}`;
    if (status) status.textContent = `${message}。本地预览已保留，请检查网络或稍后重试。`;
    toast(message, 'error');
  }
}

function buildGeneratePayload() {
  enforceOutputFormatForBackground({ silent: true });
  return {
    source_image_id: state.sourceImage.id,
    template_id: state.selectedTemplateId,
    width: state.selectedSize.width,
    height: state.selectedSize.height,
    product_fill_ratio: Number($('#ratioRange').value) / 100,
    background: state.background,
    add_shadow: $('#addShadow').checked,
    auto_enhance: $('#autoEnhance').checked,
    edge_repair: $('#edgeRepair').checked,
    output_format: state.outputFormat,
  };
}

async function generateImage() {
  if (!state.sourceImage) {
    toast('请先上传一张商品图', 'error');
    $('#dashboard')?.scrollIntoView({ behavior: 'smooth' });
    return;
  }
  const button = $('#generateBtn');
  const mobileButton = $('#mobileGenerateBtn');
  button.disabled = true;
  mobileButton.disabled = true;
  updateDownloadAllButton(null);
  button.textContent = '生成中...';
  mobileButton.textContent = '生成中...';
  $('#generatedBadge').textContent = '生成中';
  try {
    const task = await api('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildGeneratePayload()),
    });
    state.lastTask = task;
    renderTask(task);
    await loadHistory({ keepCurrent: true });
    if (task.status === 'success') {
      toast(`主图生成完成，共 ${task.assets?.length || 0} 个结果`, 'success');
    } else {
      const message = task.error_message || '生成失败，请换一张更清晰的商品图重试';
      $('#generatedBadge').className = 'generated-badge error';
      $('#generatedBadge').textContent = '生成失败';
      toast(message, 'error');
    }
  } catch (error) {
    $('#generatedBadge').className = 'generated-badge error';
    $('#generatedBadge').textContent = '生成失败';
    updateDownloadAllButton(null);
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
    mobileButton.disabled = false;
    button.textContent = '✦ 生成主图';
    mobileButton.textContent = '✦ 生成主图';
  }
}

function getPrimaryAsset(task) {
  const assets = task?.assets || [];
  return assets.find(asset => asset.output_type === state.selectedTemplateId) || assets[0];
}

function getHistoryThumbnailAsset(task) {
  const assets = task?.assets || [];
  return assets.find(asset => asset.output_type === task.template_id) || assets[0];
}

function renderTask(task) {
  const asset = getPrimaryAsset(task);
  if (asset?.public_url) {
    setPreviewImage(asset.public_url, '已生成');
  } else {
    setPreviewImage(null, task?.status === 'failed' ? '生成失败' : '暂无结果');
    if (task?.status === 'failed') $('#generatedBadge').className = 'generated-badge error';
  }
  renderResults(task.assets || []);
  renderCompliance(asset?.compliance, task.compliance_score);
  updateDownloadAllButton(task);
  highlightActiveHistory(task?.id);
}

function sortedAssets(assets) {
  return [...assets].sort((a, b) => {
    const ai = assetOrder.indexOf(a.output_type);
    const bi = assetOrder.indexOf(b.output_type);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });
}

function renderResults(assets) {
  const grid = $('#resultGrid');
  if (!grid) return;
  if (!assets.length) {
    grid.innerHTML = `<div class="empty-state">还没有生成结果。上传商品图后点击「生成主图」。</div>`;
    return;
  }
  grid.innerHTML = sortedAssets(assets).map(asset => {
    const label = assetLabels[asset.output_type] || asset.output_type;
    const badge = asset.output_type === state.selectedTemplateId ? '<span class="pass-pill success">当前模板</span>' : '';
    return `
      <article class="card result-card">
        <b>${escapeHTML(label)} ${badge}</b>
        <img src="${escapeHTML(asset.public_url)}" alt="${escapeHTML(label)}" />
        <small>${escapeHTML(asset.width)} × ${escapeHTML(asset.height)}</small>
        <div class="result-actions">
          <a href="${escapeHTML(asset.public_url)}" download>下载</a>
          <button type="button" data-regenerate="true">重新生成</button>
          <button type="button" data-report="true">查看合规报告</button>
        </div>
      </article>`;
  }).join('');
  $all('[data-regenerate]').forEach(button => button.addEventListener('click', generateImage));
  $all('[data-report]').forEach(button => button.addEventListener('click', () => $('#complianceCard')?.scrollIntoView({ behavior: 'smooth' })));
}

function renderCompliance(compliance, fallbackScore) {
  const scoreText = $('#scoreText');
  const list = $('#complianceList');
  const pill = $('#complianceCard .pass-pill');
  const score = compliance?.score ?? fallbackScore;
  scoreText.textContent = typeof score === 'number' ? Math.round(score) : '--';
  if (!compliance) {
    list.innerHTML = '<li>暂无合规报告</li>';
    pill.textContent = '待检测';
    pill.className = 'pass-pill';
    return;
  }
  const checks = compliance.checks || {};
  const metrics = compliance.metrics || {};
  const warnings = compliance.warnings || [];
  const fillRatio = metrics.product_fill_ratio ?? metrics.fill_ratio;
  const rows = [
    { ok: checks.background_ok, text: '背景接近纯白' },
    { ok: checks.centered, text: '商品居中' },
    { ok: checks.fill_ratio_ok, text: `商品占比 ${formatRatio(fillRatio)}` },
    { ok: checks.size_ok, text: '尺寸符合要求' },
  ];
  list.innerHTML = [
    ...rows.map(row => `<li class="${row.ok ? 'pass' : 'warn'}">${escapeHTML(row.text)}</li>`),
    ...warnings.map(warn => `<li class="warn">${escapeHTML(warn)}</li>`),
  ].join('');
  if (typeof score === 'number' && score >= 85) {
    pill.textContent = '合规通过';
    pill.className = 'pass-pill success';
  } else {
    pill.textContent = '需要确认';
    pill.className = 'pass-pill warning';
  }
}

function formatRatio(value) {
  if (typeof value !== 'number') return '—';
  if (value <= 1) return `${Math.round(value * 100)}%`;
  return `${Math.round(value)}%`;
}

function getStatusMeta(status) {
  if (status === 'success') return { text: '成功', className: 'success' };
  if (status === 'failed') return { text: '失败', className: 'failed' };
  if (status === 'processing') return { text: '处理中', className: '' };
  if (status === 'queued') return { text: '排队中', className: '' };
  return { text: status || '未知', className: '' };
}

function renderHistoryList(tasks) {
  const list = $('#historyList');
  if (!list) return;
  state.historyTasks = tasks || [];
  if (!state.historyTasks.length) {
    list.innerHTML = '<div class="history-empty">暂无历史记录</div>';
    return;
  }

  list.innerHTML = state.historyTasks.map(task => {
    const asset = getHistoryThumbnailAsset(task);
    const status = getStatusMeta(task.status);
    const score = typeof task.compliance_score === 'number' ? `${Math.round(task.compliance_score)}分` : '未评分';
    const thumb = asset?.public_url
      ? `<img src="${escapeHTML(asset.public_url)}" alt="历史结果缩略图" />`
      : '<span>无图</span>';
    const error = task.status === 'failed' && task.error_message
      ? `<small class="history-error">${escapeHTML(task.error_message)}</small>`
      : '';
    return `
      <div class="history-item ${task.id === state.lastTask?.id ? 'active' : ''}" role="button" tabindex="0" data-history-task="${escapeHTML(task.id)}">
        <span class="history-thumb">${thumb}</span>
        <span class="history-main">
          <b>${escapeHTML(getTemplateDisplayName(task.template_id))}</b>
          <small>${escapeHTML(formatDateTime(task.created_at))} · ${escapeHTML(task.assets?.length || 0)} 张结果</small>
          ${error}
        </span>
        <span class="history-meta">
          <span class="status-pill ${status.className}">${escapeHTML(status.text)}</span>
          <span class="history-score">${escapeHTML(score)}</span>
          <button class="ghost-btn" type="button" data-delete-task="${escapeHTML(task.id)}" style="height:30px;padding:0 10px;border-radius:9px;color:#f97316">删除</button>
        </span>
      </div>`;
  }).join('');

  $all('[data-history-task]').forEach(item => {
    item.addEventListener('click', () => selectHistoryTask(item.dataset.historyTask));
    item.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        selectHistoryTask(item.dataset.historyTask);
      }
    });
  });
  $all('[data-delete-task]').forEach(button => {
    button.addEventListener('click', event => deleteHistoryTask(button.dataset.deleteTask, event));
  });
}

function highlightActiveHistory(taskId) {
  $all('[data-history-task]').forEach(item => {
    item.classList.toggle('active', Boolean(taskId) && item.dataset.historyTask === taskId);
  });
}

function selectHistoryTask(taskId) {
  const task = state.historyTasks.find(item => item.id === taskId);
  if (!task) {
    toast('没有找到这条历史记录，请刷新列表。', 'error');
    return;
  }
  state.lastTask = task;
  renderTask(task);
  $('#resultGrid')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  if (task.status === 'failed') {
    toast(task.error_message || '这条历史任务生成失败。', 'error');
  }
}

async function loadTemplates() {
  try {
    state.templates = await api('/api/templates');
  } catch (_) {
    state.templates = fallbackTemplates;
    toast('模板接口暂不可用，已使用本地模板预览', 'error');
  }
  renderLandingTemplates();
  renderTemplateOptions();
  selectTemplate(state.selectedTemplateId);
}

async function loadHistory(options = {}) {
  try {
    const history = await api('/api/history?limit=30');
    const tasks = history.tasks || [];
    renderHistoryList(tasks);

    if (options.keepCurrent && state.lastTask?.id) {
      const refreshedCurrent = tasks.find(task => task.id === state.lastTask.id);
      if (refreshedCurrent) {
        state.lastTask = refreshedCurrent;
        highlightActiveHistory(state.lastTask.id);
        updateDownloadAllButton(state.lastTask);
        return;
      }
      const fallbackTask = tasks.find(task => task.assets?.length) || tasks[0];
      if (fallbackTask) {
        state.lastTask = fallbackTask;
        renderTask(fallbackTask);
      } else {
        clearCurrentTaskView('待生成');
      }
      return;
    }

    const last = tasks.find(task => task.assets?.length) || tasks[0];
    if (last) {
      state.lastTask = last;
      renderTask(last);
    } else {
      clearCurrentTaskView('待生成');
    }
  } catch (_) {
    state.historyTasks = [];
    renderHistoryList([]);
    clearCurrentTaskView('待生成');
  }
}

function bindEvents() {
  $all('[data-scroll]').forEach(button => {
    button.addEventListener('click', () => {
      document.getElementById(button.dataset.scroll)?.scrollIntoView({ behavior: 'smooth' });
    });
  });

  $('#fileInput')?.addEventListener('change', event => {
    handleUpload(event.target.files?.[0]);
    event.target.value = '';
  });

  const dropzone = $('.dropzone');
  dropzone?.addEventListener('dragover', event => {
    event.preventDefault();
    dropzone.classList.add('dragging');
  });
  dropzone?.addEventListener('dragleave', () => dropzone.classList.remove('dragging'));
  dropzone?.addEventListener('drop', event => {
    event.preventDefault();
    dropzone.classList.remove('dragging');
    handleUpload(event.dataTransfer.files?.[0]);
  });

  $('#ratioRange')?.addEventListener('input', event => {
    $('#ratioText').textContent = `${event.target.value}%`;
  });

  $all('#sizeOptions button').forEach(button => {
    button.addEventListener('click', () => {
      if (button.dataset.custom) {
        openCustomSizeModal();
        return;
      }
      setSelectedSize(Number(button.dataset.width), Number(button.dataset.height), { custom: false });
    });
  });

  $('#applyCustomSizeBtn')?.addEventListener('click', applyCustomSize);
  $('#cancelCustomSizeBtn')?.addEventListener('click', closeCustomSizeModal);
  $('#closeCustomSizeBtn')?.addEventListener('click', closeCustomSizeModal);
  $('#customSizeModal')?.addEventListener('click', event => {
    if (event.target.id === 'customSizeModal') closeCustomSizeModal();
  });
  $('#customWidthInput')?.addEventListener('keydown', event => {
    if (event.key === 'Enter') applyCustomSize();
  });
  $('#customHeightInput')?.addEventListener('keydown', event => {
    if (event.key === 'Enter') applyCustomSize();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !$('#customSizeModal')?.hidden) closeCustomSizeModal();
  });

  $all('#backgroundOptions button').forEach(button => {
    button.addEventListener('click', () => {
      setBackground(button.dataset.bg);
    });
  });
  $('#customColorInput')?.addEventListener('input', event => {
    setCustomBackgroundColor(event.target.value);
  });

  $all('#formatOptions button').forEach(button => {
    button.addEventListener('click', () => {
      setOutputFormat(button.dataset.format);
    });
  });

  $('#generateBtn')?.addEventListener('click', generateImage);
  $('#mobileGenerateBtn')?.addEventListener('click', generateImage);
  $('#refreshHistoryBtn')?.addEventListener('click', () => loadHistory({ keepCurrent: true }));
  $('#refreshHistoryListBtn')?.addEventListener('click', () => loadHistory({ keepCurrent: true }));
  $('#downloadAllBtn')?.addEventListener('click', handleDownloadAll);

  $all('#previewTabs button').forEach(button => {
    button.addEventListener('click', () => {
      $all('#previewTabs button').forEach(item => item.classList.remove('active'));
      button.classList.add('active');
      if (button.dataset.tab === 'original' && state.sourceImage) {
        setPreviewImage(state.sourceImage.public_url, '原图');
      } else if (button.dataset.tab === 'original' && state.localPreviewUrl) {
        setPreviewImage(state.localPreviewUrl, '已选择');
      } else if (button.dataset.tab === 'white' && state.lastTask?.assets?.length) {
        setPreviewImage(getPrimaryAsset(state.lastTask).public_url, '已生成');
      } else if (button.dataset.tab === 'compliance') {
        $('#complianceCard')?.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });
}

async function init() {
  bindEvents();
  updateCustomColorControls();
  updateFormatControls();
  updateDownloadAllButton(null);
  await loadTemplates();
  await loadHistory();
}

init();