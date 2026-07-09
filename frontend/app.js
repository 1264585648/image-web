const API_BASE = window.PRODUCTSHOT_API_BASE || '';

const state = {
  templates: [],
  selectedTemplateId: 'amazon-white-main',
  sourceImage: null,
  selectedSize: { width: 1600, height: 1600 },
  background: 'white',
  lastTask: null,
};

const templateIllustrations = {
  'amazon-white-main': '<div class="bottle"></div>',
  'temu-white-main': '<div class="kettle"></div>',
  'shopify-main': '<div class="bag"></div>',
  'transparent-png': '<div class="bottle"></div>',
  'soft-shadow-packshot': '<div class="shoe"></div>',
  'mobile-cover-4x5': '<div class="mugs"><i></i><i></i><i></i><i></i></div>',
};

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

function renderLandingTemplates() {
  const container = $('#landingTemplates');
  if (!container) return;
  container.innerHTML = state.templates.map(template => `
    <article class="card template-card ${template.id === state.selectedTemplateId ? 'active' : ''}" data-template-card="${template.id}">
      <div class="template-thumb ${template.background === 'transparent' ? 'checker-bg' : ''}">${templateIllustrations[template.id] || '<div class="bottle"></div>'}</div>
      <h3>${template.name}</h3>
    </article>
  `).join('');
}

function renderTemplateOptions() {
  const container = $('#templateOptions');
  if (!container) return;
  container.innerHTML = state.templates.map(template => `
    <button type="button" data-template="${template.id}" class="${template.id === state.selectedTemplateId ? 'active' : ''}">${template.name}</button>
  `).join('');

  $all('[data-template]').forEach(button => {
    button.addEventListener('click', () => {
      selectTemplate(button.dataset.template);
    });
  });

  $all('[data-template-card]').forEach(card => {
    card.addEventListener('click', () => {
      selectTemplate(card.dataset.templateCard);
      $('#dashboard')?.scrollIntoView({ behavior: 'smooth' });
    });
  });
}

function selectTemplate(templateId) {
  state.selectedTemplateId = templateId;
  const template = state.templates.find(item => item.id === templateId);
  if (template) {
    state.selectedSize = { width: template.width, height: template.height };
    state.background = template.background || 'white';
    $('#ratioRange').value = Math.round((template.product_fill_ratio || 0.85) * 100);
    $('#ratioText').textContent = `${$('#ratioRange').value}%`;
    $('#addShadow').checked = Boolean(template.shadow_enabled);
  }
  renderLandingTemplates();
  renderTemplateOptions();
  syncActiveButtons();
}

function syncActiveButtons() {
  $all('#sizeOptions button').forEach(button => {
    const width = Number(button.dataset.width);
    const height = Number(button.dataset.height);
    button.classList.toggle('active', width === state.selectedSize.width && height === state.selectedSize.height);
  });
  $all('#backgroundOptions button').forEach(button => {
    button.classList.toggle('active', button.dataset.bg === state.background);
  });
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
  if (!container) return;
  if (!source) return;
  container.innerHTML = `
    <img src="${source.public_url}" alt="上传的原始商品图" />
    <p><b>${source.original_filename}</b><small>${source.width} × ${source.height} · ${source.content_type}</small></p>
  `;
}

async function handleUpload(file) {
  if (!file) return;
  const status = $('#uploadStatus');
  const form = new FormData();
  form.append('file', file);
  status.textContent = '正在上传图片...';
  try {
    const source = await api('/api/upload', { method: 'POST', body: form });
    state.sourceImage = source;
    renderUploadedPreview(source);
    setPreviewImage(source.public_url, '已上传');
    status.textContent = '上传完成，可以生成主图。';
    toast('图片上传成功', 'success');
  } catch (error) {
    status.textContent = error.message;
    toast(error.message, 'error');
  }
}

function buildGeneratePayload() {
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
    output_format: 'png',
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
    if (task.status === 'success') {
      toast('主图生成完成', 'success');
    } else {
      const message = task.error_message || '生成失败，请换一张更清晰的商品图重试';
      $('#generatedBadge').className = 'generated-badge error';
      $('#generatedBadge').textContent = '生成失败';
      toast(message, 'error');
    }
  } catch (error) {
    $('#generatedBadge').className = 'generated-badge error';
    $('#generatedBadge').textContent = '生成失败';
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
    mobileButton.disabled = false;
    button.textContent = '✦ 生成主图';
    mobileButton.textContent = '✦ 生成主图';
  }
}

function renderTask(task) {
  const asset = task.assets?.[0];
  if (asset?.public_url) {
    setPreviewImage(asset.public_url, '已生成');
  }
  renderResults(task.assets || []);
  renderCompliance(asset?.compliance, task.compliance_score);
}

function renderResults(assets) {
  const grid = $('#resultGrid');
  if (!grid) return;
  if (!assets.length) {
    grid.innerHTML = `<div class="empty-state">还没有生成结果。上传商品图后点击「生成主图」。</div>`;
    return;
  }

  const labels = ['白底主图', '透明 PNG', '轻阴影图', '2000px 高清图'];
  const first = assets[0];
  const cards = labels.map((label, index) => ({
    label,
    asset: first,
    suffix: index === 0 ? '推荐' : index === 3 ? '高清' : '',
  }));

  grid.innerHTML = cards.map(item => `
    <article class="card result-card">
      <b>${item.label} ${item.suffix ? `<span class="pass-pill success">${item.suffix}</span>` : ''}</b>
      ${item.asset?.public_url ? `<img src="${item.asset.public_url}" alt="${item.label}" />` : '<div class="result-demo"><div class="bottle"></div></div>'}
      <div class="result-actions">
        ${item.asset?.public_url ? `<a href="${item.asset.public_url}" download>下载</a>` : '<button type="button">下载</button>'}
        <button type="button" data-regenerate="true">重新生成</button>
        <button type="button" data-report="true">查看合规报告</button>
      </div>
    </article>
  `).join('');

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
  const rows = [
    { ok: checks.background_ok, text: '背景接近纯白' },
    { ok: checks.centered, text: '商品居中' },
    { ok: checks.fill_ratio_ok, text: `商品占比 ${formatRatio(metrics.fill_ratio)}` },
    { ok: checks.size_ok, text: '尺寸符合要求' },
  ];

  list.innerHTML = [
    ...rows.map(row => `<li class="${row.ok ? 'pass' : 'warn'}">${row.text}</li>`),
    ...warnings.map(warn => `<li class="warn">${warn}</li>`),
  ].join('');

  if (score >= 85) {
    pill.textContent = '合规通过';
    pill.className = 'pass-pill success';
  } else {
    pill.textContent = '需要确认';
    pill.className = 'pass-pill warning';
  }
}

function formatRatio(value) {
  if (typeof value !== 'number') return '86%';
  if (value <= 1) return `${Math.round(value * 100)}%`;
  return `${Math.round(value)}%`;
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

async function loadHistory() {
  try {
    const history = await api('/api/history?limit=1');
    const last = history.tasks?.[0];
    if (last?.assets?.length) {
      state.lastTask = last;
      renderTask(last);
    } else {
      renderResults([]);
    }
  } catch (_) {
    renderResults([]);
  }
}

function bindEvents() {
  $all('[data-scroll]').forEach(button => {
    button.addEventListener('click', () => {
      const target = button.dataset.scroll;
      document.getElementById(target)?.scrollIntoView({ behavior: 'smooth' });
    });
  });

  $('#fileInput')?.addEventListener('change', event => handleUpload(event.target.files?.[0]));

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
        toast('自定义尺寸入口已预留，可在下一版接入弹窗', 'error');
        return;
      }
      state.selectedSize = { width: Number(button.dataset.width), height: Number(button.dataset.height) };
      syncActiveButtons();
    });
  });

  $all('#backgroundOptions button').forEach(button => {
    button.addEventListener('click', () => {
      state.background = button.dataset.bg;
      syncActiveButtons();
    });
  });

  $('#generateBtn')?.addEventListener('click', generateImage);
  $('#mobileGenerateBtn')?.addEventListener('click', generateImage);
  $('#refreshHistoryBtn')?.addEventListener('click', loadHistory);

  $all('#previewTabs button').forEach(button => {
    button.addEventListener('click', () => {
      $all('#previewTabs button').forEach(item => item.classList.remove('active'));
      button.classList.add('active');
      if (button.dataset.tab === 'original' && state.sourceImage) {
        setPreviewImage(state.sourceImage.public_url, '原图');
      } else if (button.dataset.tab === 'white' && state.lastTask?.assets?.[0]) {
        setPreviewImage(state.lastTask.assets[0].public_url, '已生成');
      } else if (button.dataset.tab === 'compliance') {
        $('#complianceCard')?.scrollIntoView({ behavior: 'smooth' });
      }
    });
  });
}

async function init() {
  bindEvents();
  await loadTemplates();
  await loadHistory();
}

init();
