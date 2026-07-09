const ASYNC_POLL_INTERVAL_MS = 1200;
const ASYNC_POLL_TIMEOUT_MS = 120000;
const TERMINAL_TASK_STATUSES = new Set(['success', 'failed']);

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function getGenerateButtons() {
  return [$('#generateBtn'), $('#mobileGenerateBtn')].filter(Boolean);
}

function setGenerateBusy(isBusy, text = '生成中...') {
  getGenerateButtons().forEach(button => {
    button.disabled = isBusy;
    button.textContent = isBusy ? text : '✦ 生成主图';
  });
}

function setGenerationBadge(text, className = '') {
  const badge = $('#generatedBadge');
  if (!badge) return;
  badge.textContent = text;
  badge.className = `generated-badge ${className}`.trim();
}

function getTaskStatusText(status) {
  if (status === 'queued') return '排队中';
  if (status === 'processing') return '生成中';
  if (status === 'success') return '已生成';
  if (status === 'failed') return '生成失败';
  return status || '生成中';
}

function getTaskProgressText(task) {
  const statusText = getTaskStatusText(task?.status);
  const progress = Number.isFinite(task?.progress) ? Math.max(0, Math.min(100, Math.round(task.progress))) : null;
  const step = task?.current_step || statusText;
  if (task?.status === 'success') return '已生成';
  if (task?.status === 'failed') return '生成失败';
  return progress === null ? step : `${step} ${progress}%`;
}

function syncTaskProgressUI(task) {
  const terminal = TERMINAL_TASK_STATUSES.has(task?.status);
  const badgeClass = task?.status === 'failed' ? 'error' : (task?.status === 'success' ? 'success' : '');
  const progressText = getTaskProgressText(task);
  setGenerationBadge(progressText, badgeClass);
  setGenerateBusy(!terminal, task?.status === 'queued' ? '排队中...' : `生成中 ${Math.max(0, Math.min(100, Math.round(task?.progress || 0)))}%`);
}

function getGeneratePayloadWithUiOptions() {
  const payload = buildGeneratePayload();
  const sharpness = $('#sharpness');
  payload.sharpen = sharpness ? Boolean(sharpness.checked) : true;
  return payload;
}

async function pollGenerationTask(taskId) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < ASYNC_POLL_TIMEOUT_MS) {
    const task = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
    state.lastTask = task;
    renderTask(task);
    updateDownloadAllButton(task);
    syncTaskProgressUI(task);

    if (TERMINAL_TASK_STATUSES.has(task.status)) {
      return task;
    }

    await sleep(ASYNC_POLL_INTERVAL_MS);
  }

  throw new Error('生成时间较长，请稍后点击「刷新历史」查看结果。');
}

async function runQueuedTaskFlow(task, successMessagePrefix = '主图生成完成') {
  state.lastTask = task;
  renderTask(task);
  syncTaskProgressUI(task);
  await loadHistory({ keepCurrent: true });

  const finalTask = TERMINAL_TASK_STATUSES.has(task.status) ? task : await pollGenerationTask(task.id);
  state.lastTask = finalTask;
  renderTask(finalTask);
  syncTaskProgressUI(finalTask);
  await loadHistory({ keepCurrent: true });

  if (finalTask.status === 'success') {
    toast(`${successMessagePrefix}，共 ${finalTask.assets?.length || 0} 个结果`, 'success');
  } else {
    const message = finalTask.error_message || '生成失败，请换一张更清晰的商品图重试';
    setGenerationBadge('生成失败', 'error');
    toast(message, 'error');
  }
  return finalTask;
}

async function generateImageWithPolling() {
  if (!state.sourceImage) {
    toast('请先上传一张商品图', 'error');
    $('#dashboard')?.scrollIntoView({ behavior: 'smooth' });
    return;
  }

  setGenerateBusy(true, '排队中...');
  updateDownloadAllButton(null);
  setGenerationBadge('排队中');

  try {
    const task = await api('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(getGeneratePayloadWithUiOptions()),
    });
    await runQueuedTaskFlow(task, '主图生成完成');
  } catch (error) {
    setGenerationBadge('生成失败', 'error');
    updateDownloadAllButton(null);
    toast(error.message || '生成失败，请稍后重试', 'error');
  } finally {
    setGenerateBusy(false);
  }
}

async function retryFailedTaskWithPolling(taskId) {
  setGenerateBusy(true, '重新排队中...');
  updateDownloadAllButton(null);
  setGenerationBadge('重新排队中');

  try {
    const task = await api(`/api/tasks/${encodeURIComponent(taskId)}/retry`, {
      method: 'POST',
    });
    toast('已重新排队生成', 'success');
    await runQueuedTaskFlow(task, '重试生成完成');
  } catch (error) {
    setGenerationBadge('重试失败', 'error');
    updateDownloadAllButton(state.lastTask || null);
    toast(error.message || '重试失败，请重新上传图片后生成', 'error');
  } finally {
    setGenerateBusy(false);
  }
}

function injectRetryButtonsForFailedTasks(tasks = []) {
  const failedTaskIds = new Set((tasks || []).filter(task => task.status === 'failed').map(task => task.id));
  if (!failedTaskIds.size) return;

  $all('[data-history-task]').forEach(item => {
    const taskId = item.dataset.historyTask;
    if (!failedTaskIds.has(taskId) || item.querySelector('[data-retry-task]')) return;

    const meta = item.querySelector('.history-meta') || item;
    const button = document.createElement('button');
    button.className = 'ghost-btn';
    button.type = 'button';
    button.dataset.retryTask = taskId;
    button.textContent = '重试';
    button.style.cssText = 'height:30px;padding:0 10px;border-radius:9px;color:#2563eb';
    const deleteButton = meta.querySelector('[data-delete-task]');
    meta.insertBefore(button, deleteButton || null);
  });
}

function patchHistoryRetryButtons() {
  if (window.__asyncRetryHistoryPatched || typeof window.renderHistoryList !== 'function') return;
  window.__asyncRetryHistoryPatched = true;
  const originalRenderHistoryList = window.renderHistoryList;
  window.renderHistoryList = function patchedRenderHistoryList(tasks) {
    originalRenderHistoryList(tasks);
    injectRetryButtonsForFailedTasks(tasks);
  };
}

function getTaskPrimaryAsset(task) {
  const assets = task?.assets || [];
  const templateId = task?.template_id || state.selectedTemplateId;
  return assets.find(asset => asset.output_type === templateId) || assets[0];
}

function renderResultsForTask(assets, templateId) {
  const grid = $('#resultGrid');
  if (!grid) return;
  if (!assets?.length) {
    grid.innerHTML = `<div class="empty-state">还没有生成结果。上传商品图后点击「生成主图」。</div>`;
    return;
  }
  grid.innerHTML = sortedAssets(assets).map(asset => {
    const label = assetLabels[asset.output_type] || asset.output_type;
    const badge = asset.output_type === templateId ? '<span class="pass-pill success">当前模板</span>' : '';
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
  $all('[data-report]').forEach(button => button.addEventListener('click', () => $('#complianceCard')?.scrollIntoView({ behavior: 'smooth' })));
}

function renderTaskForTaskTemplate(task) {
  const asset = getTaskPrimaryAsset(task);
  if (asset?.public_url) {
    setPreviewImage(asset.public_url, '已生成');
  } else {
    setPreviewImage(null, task?.status === 'failed' ? '生成失败' : '暂无结果');
    if (task?.status === 'failed') $('#generatedBadge').className = 'generated-badge error';
  }
  renderResultsForTask(task?.assets || [], task?.template_id || state.selectedTemplateId);
  renderCompliance(asset?.compliance, task?.compliance_score);
  updateDownloadAllButton(task);
  highlightActiveHistory(task?.id);
}

function patchTaskRendering() {
  if (window.__taskRenderPatched) return;
  window.__taskRenderPatched = true;
  window.getPrimaryAsset = getTaskPrimaryAsset;
  window.renderTask = renderTaskForTaskTemplate;
}

function showCutoutPreview() {
  const asset = (state.lastTask?.assets || []).find(item => item.output_type === 'transparent-png');
  if (asset?.public_url) {
    setPreviewImage(asset.public_url, '抠图');
    return;
  }
  toast('生成完成后才可以查看抠图结果。', 'error');
}

function installCutoutTabPreview() {
  document.addEventListener('click', event => {
    const button = event.target.closest('#previewTabs button[data-tab="cutout"]');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    $all('#previewTabs button').forEach(item => item.classList.remove('active'));
    button.classList.add('active');
    showCutoutPreview();
  }, true);
}

function safeHTML(value) {
  if (typeof escapeHTML === 'function') return escapeHTML(value);
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function openComplianceDetailModal() {
  const asset = getTaskPrimaryAsset(state.lastTask);
  const compliance = asset?.compliance;
  if (!compliance) {
    toast('暂无详细合规报告，请先生成主图。', 'error');
    return;
  }

  $('#complianceDetailModal')?.remove();
  const checks = compliance.checks || {};
  const metrics = compliance.metrics || {};
  const warnings = compliance.warnings || [];
  const checkRows = Object.entries(checks).map(([key, value]) => `
    <tr><td>${safeHTML(key)}</td><td>${value ? '通过' : '未通过'}</td></tr>
  `).join('');
  const metricRows = Object.entries(metrics).map(([key, value]) => `
    <tr><td>${safeHTML(key)}</td><td>${safeHTML(value)}</td></tr>
  `).join('');
  const warningRows = warnings.length
    ? warnings.map(item => `<li>${safeHTML(item)}</li>`).join('')
    : '<li>暂无警告</li>';

  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.id = 'complianceDetailModal';
  modal.innerHTML = `
    <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="complianceDetailTitle" style="width:min(720px,100%)">
      <div class="modal-head">
        <div>
          <h3 id="complianceDetailTitle">详细合规报告</h3>
          <p>当前模板：${safeHTML(getTemplateDisplayName(state.lastTask?.template_id))}，合规分：${safeHTML(Math.round(compliance.score ?? state.lastTask?.compliance_score ?? 0))}/100</p>
        </div>
        <button class="modal-close" type="button" data-close-compliance-detail aria-label="关闭">×</button>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;max-height:64vh;overflow:auto">
        <section>
          <h4 style="margin:0 0 10px">检查项</h4>
          <table style="width:100%;border-collapse:collapse;font-size:13px">${checkRows}</table>
        </section>
        <section>
          <h4 style="margin:0 0 10px">指标</h4>
          <table style="width:100%;border-collapse:collapse;font-size:13px">${metricRows}</table>
        </section>
        <section style="grid-column:1/-1">
          <h4 style="margin:0 0 10px">警告</h4>
          <ul style="margin:0;padding-left:18px;color:var(--muted);line-height:1.7">${warningRows}</ul>
        </section>
      </div>
      <div class="modal-actions">
        <button class="primary-btn" type="button" data-close-compliance-detail>知道了</button>
      </div>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', event => {
    if (event.target === modal || event.target.closest('[data-close-compliance-detail]')) modal.remove();
  });
}

function installComplianceDetailButton() {
  document.addEventListener('click', event => {
    const button = event.target.closest('#complianceCard .secondary-btn');
    if (!button) return;
    event.preventDefault();
    openComplianceDetailModal();
  });
}

function clarifyStaticProductOptions() {
  const detailLabel = $all('.check-grid label').find(label => label.textContent.includes('保持商品细节不变'));
  if (detailLabel) {
    const input = detailLabel.querySelector('input');
    if (input) {
      input.checked = true;
      input.disabled = true;
    }
    detailLabel.title = '当前处理链路不会生成式重绘商品主体，默认保持商品细节不变。';
    if (!detailLabel.querySelector('[data-option-note]')) {
      const note = document.createElement('small');
      note.dataset.optionNote = 'true';
      note.textContent = '固定开启';
      note.style.cssText = 'margin-left:6px;color:#637087;font-size:12px;font-weight:700';
      detailLabel.appendChild(note);
    }
  }
}

function clarifySaasPlaceholders() {
  const loginButton = document.querySelector('.desktop-nav .ghost-btn[data-scroll="dashboard"]');
  if (loginButton) loginButton.textContent = '进入工作台';

  const credit = $('.credit');
  if (credit) credit.textContent = '演示积分：未接入计费';

  $all('button').forEach(button => {
    if (button.textContent.trim() !== '升级套餐') return;
    button.textContent = '升级套餐（待接入）';
    button.disabled = true;
    button.title = '套餐、积分扣费和支付功能还在后续路线中，当前为生成工作台演示。';
  });
}

function installUiFixes() {
  patchTaskRendering();
  installCutoutTabPreview();
  installComplianceDetailButton();
  clarifyStaticProductOptions();
  clarifySaasPlaceholders();
}

function installAsyncGenerateInterceptor() {
  patchHistoryRetryButtons();

  document.addEventListener('click', event => {
    const retryButton = event.target.closest('[data-retry-task]');
    if (retryButton) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      retryFailedTaskWithPolling(retryButton.dataset.retryTask);
      return;
    }

    const trigger = event.target.closest('#generateBtn, #mobileGenerateBtn, [data-regenerate]');
    if (!trigger) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    generateImageWithPolling();
  }, true);
}

installUiFixes();
installAsyncGenerateInterceptor();
