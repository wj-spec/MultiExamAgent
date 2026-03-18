/**
 * panel.js — 右侧 Agent 状态面板管理
 * 职责：显示/隐藏面板、更新步骤进度、展示任务参数、展示结果+下载
 */

const Panel = (() => {
  // DOM 节点
  let panelEl, stepListEl, paramsSectionEl, paramsContentEl;
  let resultSectionEl, resultSummaryEl, downloadBtnEl;
  let panelTitleTextEl, panelStatusDotEl, panelCloseBtn;

  // 当前结果 Markdown（用于下载）
  let currentMarkdown = '';
  let currentTopic = '试题';

  // 步骤数据 {name -> {el, status, detail, elapsed}}
  const steps = {};

  function init() {
    panelEl = document.getElementById('agent-panel');
    stepListEl = document.getElementById('step-list');
    paramsSectionEl = document.getElementById('params-section');
    paramsContentEl = document.getElementById('params-content');
    resultSectionEl = document.getElementById('result-section');
    resultSummaryEl = document.getElementById('result-summary');
    downloadBtnEl = document.getElementById('download-btn');
    panelTitleTextEl = document.getElementById('panel-title-text');
    panelStatusDotEl = document.getElementById('panel-status-dot');
    panelCloseBtn = document.getElementById('panel-close');

    panelCloseBtn.addEventListener('click', hide);
    downloadBtnEl.addEventListener('click', downloadMarkdown);
  }

  /** 显示面板（开始任务时调用） */
  function show() {
    panelEl.classList.remove('hidden');
  }

  /** 隐藏面板 */
  function hide() {
    panelEl.classList.add('hidden');
  }

  /** 重置面板（新任务开始时调用） */
  function reset() {
    // 清空步骤
    Object.keys(steps).forEach(k => delete steps[k]);
    stepListEl.innerHTML = '';

    // 隐藏参数+结果区域
    paramsSectionEl.classList.add('hidden');
    resultSectionEl.classList.add('hidden');
    paramsContentEl.innerHTML = '';
    resultSummaryEl.innerHTML = '';

    // 重置标题
    panelTitleTextEl.textContent = 'Agent 运行中...';
    panelStatusDotEl.className = 'panel-dot running';

    currentMarkdown = '';
    currentTopic = '试题';
  }

  /**
   * 更新步骤状态
   * @param {string} stepName  步骤名称（如 "🧠 意图路由"）
   * @param {string} status    "running" | "done" | "error"
   * @param {string} detail    详细信息
   * @param {string|null} elapsed  耗时字符串 "1.2s"
   */
  function updateStep(stepName, status, detail, elapsed) {
    // 若步骤不存在，创建
    if (!steps[stepName]) {
      const row = document.createElement('div');
      row.className = 'step-item';
      row.innerHTML = `
        <div class="step-icon pending">○</div>
        <div class="step-body">
          <div class="step-name">${escapeHtml(stepName)}</div>
          <div class="step-detail">等待中...</div>
        </div>
      `;
      stepListEl.appendChild(row);
      steps[stepName] = {
        el: row,
        iconEl: row.querySelector('.step-icon'),
        detailEl: row.querySelector('.step-detail'),
        status: 'pending'
      };
    }

    const s = steps[stepName];
    const { iconEl, detailEl } = s;
    s.status = status;

    // 更新图标
    iconEl.className = `step-icon ${status}`;
    if (status === 'running') iconEl.textContent = '●';
    else if (status === 'done') iconEl.textContent = '✓';
    else if (status === 'error') iconEl.textContent = '✕';

    // 更新详情
    if (detail) detailEl.textContent = detail;

    // 追加耗时标签
    if (elapsed && status === 'done') {
      // 移除旧耗时
      const oldBadge = s.el.querySelector('.step-elapsed');
      if (oldBadge) oldBadge.remove();

      const badge = document.createElement('span');
      badge.className = 'step-elapsed';
      badge.textContent = elapsed;
      s.el.querySelector('.step-body').appendChild(badge);
    }

    // 自动滚动到最新步骤
    s.el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  /** 展示任务参数 */
  function showParams(params) {
    if (!params || Object.keys(params).length === 0) return;

    paramsSectionEl.classList.remove('hidden');
    paramsContentEl.innerHTML = '';

    const labelMap = {
      topic: '知识点',
      question_type: '题型',
      difficulty: '难度',
      count: '题目数量',
      additional_requirements: '附加要求',
    };

    const difficultyMap = { easy: '简单', medium: '中等', hard: '困难' };
    const typeMap = {
      choice: '选择题',
      fill_blank: '填空题',
      essay: '解答题',
      mixed: '综合',
    };

    Object.entries(params).forEach(([k, v]) => {
      if (!v && v !== 0) return;
      const label = labelMap[k] || k;
      let display = v;
      if (k === 'difficulty' && difficultyMap[v]) display = difficultyMap[v];
      if (k === 'question_type' && typeMap[v]) display = typeMap[v];

      const row = document.createElement('div');
      row.className = 'param-row';
      row.innerHTML = `
        <span class="param-key">${escapeHtml(label)}</span>
        <span class="param-val">${escapeHtml(String(display))}</span>
      `;
      paramsContentEl.appendChild(row);
    });
  }

  /**
   * 展示最终结果卡片
   * @param {string} markdown        格式化后的 Markdown 结果
   * @param {number} questionCount   题目数量
   * @param {string} topic           知识点
   * @param {string} questionType    题型
   * @param {string} difficulty      难度
   */
  function showResult(markdown, questionCount, topic, questionType, difficulty) {
    currentMarkdown = markdown;
    currentTopic = topic || '试题';

    resultSectionEl.classList.remove('hidden');

    // 更新面板状态
    panelTitleTextEl.textContent = '任务完成';
    panelStatusDotEl.className = 'panel-dot done';

    const diffMap = { easy: '简单', medium: '中等', hard: '困难' };
    const typeMap = { choice: '选择题', fill_blank: '填空题', essay: '解答题', mixed: '综合' };

    resultSummaryEl.innerHTML = `
      <div style="color: var(--green); font-weight: 700; font-size: 13px; margin-bottom: 8px;">
        ✓ 已生成 ${questionCount} 道试题
      </div>
      <div style="display:flex;flex-direction:column;gap:4px">
        ${topic ? `<div>📚 知识点：${escapeHtml(topic)}</div>` : ''}
        ${questionType ? `<div>📝 题型：${escapeHtml(typeMap[questionType] || questionType)}</div>` : ''}
        ${difficulty ? `<div>📊 难度：${escapeHtml(diffMap[difficulty] || difficulty)}</div>` : ''}
      </div>
    `;

    downloadBtnEl.classList.remove('success');
    downloadBtnEl.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" y1="15" x2="12" y2="3"/>
      </svg>
      下载 Markdown 文件
    `;
  }

  /** 标记任务完成（所有步骤已结束，但无具体结果） */
  function markDone() {
    panelTitleTextEl.textContent = '任务完成';
    panelStatusDotEl.className = 'panel-dot done';
  }

  /** 下载 Markdown 文件 */
  function downloadMarkdown() {
    if (!currentMarkdown) return;
    const blob = new Blob([currentMarkdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const now = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-');
    a.href = url;
    a.download = `${currentTopic}_${now}.md`;
    a.click();
    URL.revokeObjectURL(url);

    downloadBtnEl.classList.add('success');
    downloadBtnEl.innerHTML = `✓ 已下载`;
    setTimeout(() => {
      downloadBtnEl.classList.remove('success');
      downloadBtnEl.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>
        下载 Markdown 文件
      `;
    }, 2000);
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /** 通过缓存的 resultData 对象重新展示结果面板（外部调用） */
  function showResultData(resultData) {
    if (!resultData) return;
    // 重置面板标题/状态，只保留结果区
    panelTitleTextEl.textContent = '任务完成';
    panelStatusDotEl.className = 'panel-dot done';
    showResult(
      resultData.markdown,
      resultData.question_count,
      resultData.topic,
      resultData.question_type,
      resultData.difficulty
    );
  }

  return { init, show, hide, reset, updateStep, showParams, showResult, showResultData, markDone };
})();

