/**
 * panel.js — 内联思考模块挂载与数据更新支持 (Scheme A)
 * 职责：更新步骤进度、展示作战室辩论气泡
 */

const Panel = (() => {
  // 步骤数据缓存 {stepId -> {...}} 
  const steps = {};

  // 当前结果上下文（兼容保留，可做其他图谱展示使用）
  let currentTopic = '试题';

  function init() {
    // 之前用于绑定固定 DOM，现在废除全局面板，由 chat.js 动态生成内联过程块。
    // 保留 init 空函数给 app.js 初始化调用。
  }

  /** 获取当前活跃的内部 DOM 元素 */
  function getActiveEl(selector) {
    if (typeof Chat !== 'undefined' && Chat.getActiveThoughtContainer) {
      const container = Chat.getActiveThoughtContainer();
      if (container) return container.querySelector(selector);
    }
    // 回退尝试
    return document.querySelector(selector);
  }

  /** 显示面板（兼容调用，实质可能不再需要如果内联容器已渲染） */
  function show() { }

  /** 隐藏面板（兼容调用） */
  function hide() { }

  /** 重置状态（新任务开始时调用） */
  function reset() {
    Object.keys(steps).forEach(k => delete steps[k]);
    const stepListEl = getActiveEl('.step-list');
    if (stepListEl) stepListEl.innerHTML = '';

    const debateBubblesEl = getActiveEl('.debate-bubbles');
    if (debateBubblesEl) debateBubblesEl.innerHTML = '';
    
    currentTopic = '试题';
  }

  function _getStepId(stepName, stepId) {
     return stepId || stepName;
  }

  /**
   * 更新或创建步骤状态
   */
  function updateStep(stepName, status, detail, elapsed, stepId = null, parentId = null) {
    const sId = _getStepId(stepName, stepId);
    
    const stepListEl = getActiveEl('.step-list');
    if (!stepListEl) return; // 没有容器则跳过

    if (!steps[sId]) {
      const row = document.createElement('div');
      row.className = parentId ? 'step-item child-step' : 'step-item';
      // 样式调整以匹配紧凑气泡
      row.style.padding = '4px 0';
      row.innerHTML = `
        <div class="step-icon pending" style="width:16px; height:16px; font-size:9px;">○</div>
        <div class="step-body" style="font-size:11px;">
          <div class="step-name" style="font-size:11px; font-weight:600;">${escapeHtml(stepName)}</div>
          <div class="step-detail" style="font-size:10px;">等待中...</div>
          <div class="step-children-container hidden" style="margin-top:4px;"></div>
        </div>
      `;

      steps[sId] = {
        id: sId,
        name: stepName,
        el: row,
        nameEl: row.querySelector('.step-name'),
        iconEl: row.querySelector('.step-icon'),
        detailEl: row.querySelector('.step-detail'),
        childrenContainerEl: row.querySelector('.step-children-container'),
        status: 'pending',
        parentId: parentId,
        children: []
      };

      const toggleFn = (e) => {
        const s = steps[sId];
        if (s.children.length > 0) {
          s.childrenContainerEl.classList.toggle('hidden');
          s.nameEl.style.opacity = s.childrenContainerEl.classList.contains('hidden') ? '0.8' : '1';
        }
      };
      
      steps[sId].nameEl.style.cursor = 'pointer';
      steps[sId].detailEl.style.cursor = 'pointer';
      steps[sId].nameEl.addEventListener('click', toggleFn);
      steps[sId].detailEl.addEventListener('click', toggleFn);

      if (parentId && steps[parentId]) {
        const parent = steps[parentId];
        parent.children.push(sId);
        parent.childrenContainerEl.classList.remove('hidden');
        parent.childrenContainerEl.appendChild(row);
      } else {
        stepListEl.appendChild(row);
      }
    }

    const s = steps[sId];
    s.status = status;

    s.iconEl.className = `step-icon ${status}`;
    if (status === 'running') {
        s.iconEl.innerHTML = '<span class="spinner-border text-brand spinner-border-sm" style="width: 10px; height: 10px; border-width: 1.5px;"></span>';
        s.iconEl.style.color = 'var(--brand)';
        s.iconEl.style.borderColor = 'var(--brand)';
        s.iconEl.style.background = 'rgba(124, 124, 248, 0.15)';
    }
    else if (status === 'done') {
        s.iconEl.textContent = '✓';
        s.iconEl.style.color = 'var(--green)';
        s.iconEl.style.borderColor = 'var(--green)';
        s.iconEl.style.background = 'rgba(16, 185, 129, 0.12)';
        s.iconEl.innerHTML = '✓'; // Reset contents
    }
    else if (status === 'error') {
        s.iconEl.textContent = '✕';
        s.iconEl.style.color = 'var(--red)';
        s.iconEl.style.borderColor = 'var(--red)';
        s.iconEl.style.background = 'rgba(239, 68, 68, 0.12)';
        s.iconEl.innerHTML = '✕';
    }
    else {
        s.iconEl.textContent = '○';
        s.iconEl.style.color = 'var(--text-muted)';
        s.iconEl.style.borderColor = 'var(--border-medium)';
        s.iconEl.style.background = 'transparent';
        s.iconEl.innerHTML = '○';
    }

    if (detail) s.detailEl.textContent = detail;

    if (status === 'done' && s.children.length > 0) {
      s.childrenContainerEl.classList.add('hidden');
      s.nameEl.style.opacity = '0.8';
      if (!s.nameEl.textContent.includes('点击展开')) {
         s.nameEl.innerHTML = `${escapeHtml(s.name)} <span style="font-size:9px;color:var(--text-muted);font-weight:normal">(点击展开)</span>`;
      }
    }

    if (elapsed && status === 'done') {
      const oldBadge = s.el.querySelector('.step-elapsed');
      if (oldBadge) oldBadge.remove();
      const badge = document.createElement('span');
      badge.className = 'step-elapsed';
      badge.textContent = elapsed;
      s.el.querySelector('.step-body').appendChild(badge);
    }
    
    // 避免大范围滚动影响聊天区
    const container = typeof Chat !== 'undefined' ? Chat.getActiveThoughtContainer() : null;
    if (container) {
       container.scrollTop = container.scrollHeight;
    }
  }

  function showParams(params) { }
  function showResult(markdown, count, topic, type, diff) { }
  function markDone() { }

  /** 添加作战室聊天气泡 */
  function addDebateBubble(role, avatar, content) {
    const warRoomSectionEl = getActiveEl('.war-room-section');
    const debateBubblesEl = getActiveEl('.debate-bubbles');
    
    if (warRoomSectionEl) warRoomSectionEl.classList.remove('hidden');
    if (!debateBubblesEl) return;

    let isLeft = role !== 'creator';
    let label = isLeft ? role : '制卷人 (Creator)';
    if (role === 'domain_expert') label = '学科专家';
    if (role === 'format_examiner') label = '格式审查员';
    if (role === 'meta_reviewer') label = '组长 (Meta)';

    const wrap = document.createElement('div');
    wrap.style.display = 'flex';
    wrap.style.gap = '8px';
    wrap.style.marginBottom = '8px';
    wrap.style.alignItems = 'flex-start';
    wrap.style.animation = 'slideUpFade 0.3s ease-out forwards';
    wrap.style.flexDirection = isLeft ? 'row' : 'row-reverse';

    const avatarEl = document.createElement('div');
    avatarEl.style.width = '20px';
    avatarEl.style.height = '20px';
    avatarEl.style.borderRadius = '50%';
    avatarEl.style.background = isLeft ? 'var(--bg-card)' : 'var(--brand-gradient)';
    avatarEl.style.border = isLeft ? '1px solid var(--border)' : 'none';
    avatarEl.style.display = 'flex';
    avatarEl.style.alignItems = 'center';
    avatarEl.style.justifyContent = 'center';
    avatarEl.style.fontSize = '10px';
    avatarEl.style.flexShrink = '0';
    avatarEl.innerHTML = avatar || (isLeft ? '🧐' : '🤖');

    const bubbleEl = document.createElement('div');
    bubbleEl.style.background = isLeft ? 'var(--bg-card)' : 'rgba(124,124,248,0.1)';
    bubbleEl.style.border = isLeft ? '1px solid var(--border)' : '1px solid rgba(124,124,248,0.2)';
    bubbleEl.style.padding = '4px 8px';
    bubbleEl.style.borderRadius = isLeft ? '0 8px 8px 8px' : '8px 0 8px 8px';
    bubbleEl.style.maxWidth = '90%';
    bubbleEl.style.fontSize = '10px';
    bubbleEl.style.color = 'var(--text-primary)';
    bubbleEl.style.lineHeight = '1.4';

    const nameEl = document.createElement('div');
    nameEl.style.fontSize = '9px';
    nameEl.style.color = 'var(--text-muted)';
    nameEl.style.marginBottom = '2px';
    nameEl.style.textAlign = isLeft ? 'left' : 'right';
    nameEl.textContent = label;

    const contentEl = document.createElement('div');
    contentEl.textContent = content;

    bubbleEl.appendChild(nameEl);
    bubbleEl.appendChild(contentEl);
    wrap.appendChild(avatarEl);
    wrap.appendChild(bubbleEl);

    debateBubblesEl.appendChild(wrap);
    debateBubblesEl.scrollTop = debateBubblesEl.scrollHeight;
  }

  function escapeHtml(str) {
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  return {
    init,
    show,
    hide,
    reset,
    updateStep,
    markDone,
    showParams,
    showResult,
    addDebateBubble
  };
})();
