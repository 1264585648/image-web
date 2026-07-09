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
      body: JSON.stringify(buildGeneratePayload()),
    });

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
      toast(`主图生成完成，共 ${finalTask.assets?.length || 0} 个结果`, 'success');
    } else {
      const message = finalTask.error_message || '生成失败，请换一张更清晰的商品图重试';
      setGenerationBadge('生成失败', 'error');
      toast(message, 'error');
    }
  } catch (error) {
    setGenerationBadge('生成失败', 'error');
    updateDownloadAllButton(null);
    toast(error.message || '生成失败，请稍后重试', 'error');
  } finally {
    setGenerateBusy(false);
  }
}

function installAsyncGenerateInterceptor() {
  document.addEventListener('click', event => {
    const trigger = event.target.closest('#generateBtn, #mobileGenerateBtn, [data-regenerate]');
    if (!trigger) return;

    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    generateImageWithPolling();
  }, true);
}

installAsyncGenerateInterceptor();
