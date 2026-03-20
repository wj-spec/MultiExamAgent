/**
 * chat.js - 对话消息渲染与发送
 * 职责：渲染欢迎卡片、渲染消息气泡（Markdown支持）、自动滚动
 */

const Chat = (() => {
  let messageListEl, welcomeScreenEl, chatInputEl, sendBtnEl;
  let onSendMessage = null;  // 发送消息的回调 (content) => void
  let onShowResult = null;   // 查看结果回调 (resultData) => void
  let isWaitingResponse = false;
  let typingRowEl = null;
  let lastUserMessage = '';  // 最后一条用户消息 (用于重新生成)

  // 翻页重生成支持
  let isRegenerating = false;
  let currentAssistantRow = null; 
  // 维护当前正在操作的 AI 气泡的数据版本 { versions: [], currentIndex: 0 }
  // 实际数据结构我们可以挂载在 DOM 上，或者全局维护


  // marked.js 配置
  const markedInstance = typeof marked !== 'undefined' ? marked : null;
  if (markedInstance) {
    markedInstance.setOptions({
      highlight: (code, lang) => {
        if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
          return hljs.highlight(code, { language: lang }).value;
        }
        return typeof hljs !== 'undefined' ? hljs.highlightAuto(code).value : code;
      },
      breaks: true,
      gfm: true,
    });
  }

  // 初始化 Mermaid (如果存在)
  if (typeof mermaid !== 'undefined') {
    mermaid.initialize({ startOnLoad: false, theme: 'default' });
  }

  function init(sendCallback, showResultCallback) {
    messageListEl = document.getElementById('message-list');
    welcomeScreenEl = document.getElementById('welcome-screen');
    chatInputEl = document.getElementById('chat-input');
    sendBtnEl = document.getElementById('send-btn');
    onSendMessage = sendCallback;
    onShowResult = showResultCallback || null;

    // 发送按钮
    sendBtnEl.addEventListener('click', handleSend);

    // Enter 发送，Shift+Enter 换行
    chatInputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });

    // 自适应高度
    chatInputEl.addEventListener('input', () => {
      chatInputEl.style.height = 'auto';
      chatInputEl.style.height = Math.min(chatInputEl.scrollHeight, 180) + 'px';
    });

    // 示例卡片点击
    document.addEventListener('click', (e) => {
      const btn = e.target.closest('.example-card-btn') || e.target.closest('.example-card');
      if (!btn) return;
      const card = btn.closest('.example-card');
      if (!card) return;
      const prompt = card.dataset.prompt;
      if (prompt) {
        chatInputEl.value = prompt;
        chatInputEl.style.height = 'auto';
        chatInputEl.style.height = Math.min(chatInputEl.scrollHeight, 180) + 'px';
        chatInputEl.focus();
      }
    });

    // 文件上传
    const fileInput = document.getElementById('file-upload');
    if (fileInput) {
      fileInput.addEventListener('change', handleFileUpload);
    }
  }

  /** 处理发送 */
  function handleSend() {
    if (isWaitingResponse) return;
    const content = chatInputEl.value.trim();
    if (!content) return;

    chatInputEl.value = '';
    chatInputEl.style.height = 'auto';

    if (onSendMessage) onSendMessage(content);
  }

  /** 隐藏欢迎页，进入对话模式 */
  function hideWelcome() {
    if (welcomeScreenEl && !welcomeScreenEl.classList.contains('hidden')) {
      welcomeScreenEl.classList.add('hidden');
    }
  }

  /** 显示欢迎页 */
  function showWelcome() {
    // 清除所有消息气泡（移除除欢迎页外的内容）
    const rows = messageListEl.querySelectorAll('.message-row');
    rows.forEach(r => r.remove());
    if (welcomeScreenEl) welcomeScreenEl.classList.remove('hidden');
  }

  /** 渲染用户消息 */
  function appendUserMessage(content) {
    hideWelcome();
    lastUserMessage = content;
    const row = document.createElement('div');
    row.className = 'message-row user';
    row.innerHTML = `
      <div class="message-avatar">👤</div>
      <div class="message-bubble">${escapeHtml(content)}</div>
    `;
    messageListEl.appendChild(row);
    scrollToBottom();
    return row;
  }

  /** 标记是否处于重生成状态 */
  function setRegenerating(state) {
    isRegenerating = state;
  }

  /** 显示打字指示 (内联思考块) */
  function showTyping(isRegen = false) {
    isWaitingResponse = true;
    sendBtnEl.disabled = true;

    const thoughtHtml = `
      <div class="inline-thought-process">
        <div class="thinking-header" style="display:flex; gap:8px; align-items:center; user-select:none; font-size:12px; color:var(--text-secondary); background:rgba(255,255,255,0.02); padding:8px 12px; border-radius:6px; border:var(--glass-border);">
          <div class="thinking-status" style="display:flex; align-items:center; gap:8px;">
             <span class="spinner-border spinner-border-sm text-brand" style="width:12px; height:12px; border-width:2px;"></span>
             <span class="thinking-text">🤖 深入思考中 · 检索知识...</span>
          </div>
          <span class="chevron" style="margin-left:auto; transition:transform 0.3s; transform:rotate(180deg);">▼</span>
        </div>
        <div class="thinking-body" style="margin-top:8px; border-top:1px solid var(--border); padding-top:8px; display:flex; flex-direction:column; gap:10px;">
          <!-- 执行步骤 -->
          <div class="panel-section" style="padding:0; border:none;">
            <div class="panel-section-title" style="font-size:10px; margin-bottom:6px;">执行步骤</div>
            <div class="step-list"></div>
          </div>
          <!-- 专家组审核 -->
          <div class="war-room-section hidden panel-section" style="padding:0; border:none;">
            <div class="panel-section-title" style="display:flex; align-items:center; gap:6px; font-size:10px; margin-bottom:6px;">
               ⚔️ 专家组审核
               <span class="debate-status-dot" style="width:6px; height:6px; background:var(--brand); border-radius:50%; box-shadow:0 0 4px var(--brand); animation:pulse 1.5s infinite;"></span>
            </div>
            <div class="debate-container debate-bubbles"></div>
          </div>
        </div>
      </div>
    `;

    if (isRegen && currentAssistantRow) {
      const bubble = currentAssistantRow.querySelector('.message-bubble');
      if (bubble) {
        bubble.innerHTML = thoughtHtml;
        const actions = currentAssistantRow.querySelector('.msg-actions-container');
        if (actions) actions.style.display = 'none'; 
        bindThoughtProcessEvents(bubble.querySelector('.inline-thought-process'));
      }
    } else {
      typingRowEl = document.createElement('div');
      typingRowEl.className = 'message-row assistant';
      typingRowEl.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-bubble">${thoughtHtml}</div>
      `;
      messageListEl.appendChild(typingRowEl);
      bindThoughtProcessEvents(typingRowEl.querySelector('.inline-thought-process'));
    }
    scrollToBottom();
  }

  function bindThoughtProcessEvents(container) {
    if (!container) return;
    const header = container.querySelector('.thinking-header');
    const body = container.querySelector('.thinking-body');
    const chevron = container.querySelector('.chevron');
    if (header && body && chevron) {
      header.style.cursor = 'pointer';
      // 移除旧的监听器防止重复绑定
      header.replaceWith(header.cloneNode(true));
      const newHeader = container.querySelector('.thinking-header');
      newHeader.addEventListener('click', () => {
        body.classList.toggle('hidden');
        newHeader.querySelector('.chevron').style.transform = body.classList.contains('hidden') ? 'rotate(0deg)' : 'rotate(180deg)';
      });
    }
  }

  /** 获取当前活跃的思考块 DOM，供 panel.js 渲染使用 */
  function getActiveThoughtContainer() {
    if (isRegenerating && currentAssistantRow) {
      return currentAssistantRow.querySelector('.inline-thought-process');
    }
    if (typingRowEl) {
      return typingRowEl.querySelector('.inline-thought-process');
    }
    return null;
  }

  /** 移除打字指示，替换为实际回复 (支持多版本) */
  function showAssistantMessage(content, resultData) {
    isWaitingResponse = false;
    sendBtnEl.disabled = false;

    // 捕获旧的思维链路 DOM 并克隆
    let oldThoughtDOM = null;
    if (isRegenerating && currentAssistantRow) {
      const activeBubble = currentAssistantRow.querySelector('.message-bubble');
      const processEl = activeBubble?.querySelector('.inline-thought-process');
      if (processEl) oldThoughtDOM = processEl.cloneNode(true);
    } else if (typingRowEl) {
      const processEl = typingRowEl.querySelector('.inline-thought-process');
      if (processEl) oldThoughtDOM = processEl.cloneNode(true);
    }

    // 清理克隆过来的 DOM 的动画和状态，将其收起
    if (oldThoughtDOM) {
       const spinner = oldThoughtDOM.querySelector('.spinner-border');
       if (spinner) spinner.remove();
       const title = oldThoughtDOM.querySelector('.thinking-text');
       if (title) title.textContent = '🤖 思考过程记录 (\u5df2\u5b8c\u6210)';
       const dot = oldThoughtDOM.querySelector('.debate-status-dot');
       if (dot) dot.style.animation = 'none';

       // 默认折叠它
       const body = oldThoughtDOM.querySelector('.thinking-body');
       if (body) body.classList.add('hidden');
       const chevron = oldThoughtDOM.querySelector('.chevron');
       if (chevron) chevron.style.transform = 'rotate(0deg)';
       
       // 重新绑定克隆节点的点击事件
       bindThoughtProcessEvents(oldThoughtDOM);
    }

    // 移除独立的打字指示容器
    if (typingRowEl) {
      typingRowEl.remove();
      typingRowEl = null;
    }

    let row = null;
    let bubbleInfo = null;

    if (isRegenerating && currentAssistantRow) {
      row = currentAssistantRow;
      bubbleInfo = row.__bubbleInfo;
      bubbleInfo.versions.push({ content, resultData, thoughtDOM: oldThoughtDOM });
      bubbleInfo.currentIndex = bubbleInfo.versions.length - 1;
      isRegenerating = false;
    } else {
      row = document.createElement('div');
      row.className = 'message-row assistant';
      
      const avatar = document.createElement('div');
      avatar.className = 'message-avatar';
      avatar.textContent = '🤖';
      
      const bubble = document.createElement('div');
      bubble.className = 'message-bubble';
      
      const actionsContainer = document.createElement('div');
      actionsContainer.className = 'msg-actions-container';

      row.appendChild(avatar);
      row.appendChild(bubble);
      row.appendChild(actionsContainer);

      messageListEl.appendChild(row);

      bubbleInfo = {
        versions: [{ content, resultData, thoughtDOM: oldThoughtDOM }],
        currentIndex: 0
      };
      row.__bubbleInfo = bubbleInfo;
      currentAssistantRow = row;
    }

    renderBubbleVersion(row, bubbleInfo);
    
    scrollToBottom();
    return row;
  }

  /** 渲染特定版本的 AI 回复 */
  function renderBubbleVersion(row, bubbleInfo) {
    const { versions, currentIndex } = bubbleInfo;
    const { content, resultData, thoughtDOM } = versions[currentIndex];
    
    const bubble = row.querySelector('.message-bubble');
    const actionsContainer = row.querySelector('.msg-actions-container');

    // ---- 渲染主体内容 ----
    bubble.innerHTML = '';
    
    // 如果存在思考过程 DOM，附加在上方
    if (thoughtDOM) {
      bubble.appendChild(thoughtDOM);
    }
    
    // 渲染 Markdown 正文
    const contentDiv = document.createElement('div');
    contentDiv.className = 'markdown-body';
    contentDiv.style.marginTop = thoughtDOM ? '12px' : '0';
    contentDiv.innerHTML = renderMarkdown(content);
    bubble.appendChild(contentDiv);

    // 代码高亮
    if (typeof hljs !== 'undefined') {
      contentDiv.querySelectorAll('pre code').forEach(hljs.highlightElement);
    }

    // 渲染图谱
    if (typeof mermaid !== 'undefined' && resultData?.knowledge_topology) {
      renderMermaidInBubble(contentDiv, resultData);
    }

    // ---- 渲染顶部翻页器 (如果有多个版本) ----
    if (versions.length > 1) {
      const pagination = document.createElement('div');
      pagination.className = 'message-pagination';
      
      const prevBtn = document.createElement('button');
      prevBtn.className = 'page-btn page-prev';
      prevBtn.textContent = '◀';
      prevBtn.disabled = currentIndex === 0;
      prevBtn.onclick = () => {
        bubbleInfo.currentIndex--;
        renderBubbleVersion(row, bubbleInfo);
      };

      const dot = document.createElement('span');
      dot.className = 'page-indicator';
      dot.textContent = `${currentIndex + 1} / ${versions.length}`;

      const nextBtn = document.createElement('button');
      nextBtn.className = 'page-btn page-next';
      nextBtn.textContent = '▶';
      nextBtn.disabled = currentIndex === versions.length - 1;
      nextBtn.onclick = () => {
        bubbleInfo.currentIndex++;
        renderBubbleVersion(row, bubbleInfo);
      };

      pagination.appendChild(prevBtn);
      pagination.appendChild(dot);
      pagination.appendChild(nextBtn);
      
      // 插入到 bubble 最开头
      bubble.insertBefore(pagination, bubble.firstChild);
    }

    // ---- 渲染底部操作栏 ----
    const newActions = buildMsgActions(content, resultData);
    actionsContainer.innerHTML = ''; // 清空
    actionsContainer.appendChild(newActions);
  }

  /** 渲染错误消息 */
  function showErrorMessage(content) {
    isWaitingResponse = false;
    sendBtnEl.disabled = false;

    if (typingRowEl) {
      typingRowEl.remove();
      typingRowEl = null;
    }

    const row = document.createElement('div');
    row.className = 'message-row assistant';
    row.innerHTML = `
      <div class="message-avatar">⚠️</div>
      <div class="message-bubble" style="border-color:rgba(239,68,68,0.3);background:rgba(239,68,68,0.05)">
        <strong style="color:var(--red)">出错了</strong><br>${escapeHtml(content)}
      </div>
    `;
    messageListEl.appendChild(row);
    scrollToBottom();
  }

  /** 清空对话，恢复欢迎页（切换对话时调用） */
  function clearMessages() {
    showWelcome();
  }

  /** 从历史记录恢复消息 */
  function restoreMessages(messages) {
    showWelcome();
    if (!messages || messages.length === 0) return;
    hideWelcome();
    messages.forEach(m => {
      if (m.role === 'user') {
        appendUserMessage(m.content);
      } else if (m.role === 'assistant') {
        // 直接插入已有消息（不需要 typing 动画）
        const row = document.createElement('div');
        row.className = 'message-row assistant';
        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        bubble.innerHTML = renderMarkdown(m.content);
        if (typeof hljs !== 'undefined') {
          bubble.querySelectorAll('pre code').forEach(hljs.highlightElement);
        }
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = '🤖';
        const actions = buildMsgActions(m.content, null);
        row.appendChild(avatar);
        row.appendChild(bubble);
        row.appendChild(actions);
        messageListEl.appendChild(row);
      }
    });
    scrollToBottom();
  }

  /** 文件上传处理 */
  async function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      const data = await res.json();
      appendUserMessage(`[已上传文件: ${file.name}]`);
      showAssistantMessage(data.message || `文件 ${file.name} 已上传到知识库。`);
    } catch (err) {
      showErrorMessage('文件上传失败，请重试。');
    }
    e.target.value = '';
  }

  // ---- 消息操作工具栏 ----

  /**
   * 构建消息操作工具栏
   * @param {string} rawMarkdown  原始 Markdown 内容
   * @param {object|null} resultData  任务结果数据（有则显示查看结果按钮）
   */
  function buildMsgActions(rawMarkdown, resultData) {
    const bar = document.createElement('div');
    bar.className = 'msg-actions';

    // 复制纯文本
    const btnText = createActionBtn(
      `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg> 复制文本`,
      '复制纯文本',
      () => {
        const bubble = bar.parentElement && bar.parentElement.querySelector('.message-bubble');
        const text = bubble ? bubble.innerText : rawMarkdown;
        navigator.clipboard.writeText(text).then(() => flashBtn(btnText, '✓ 已复制'));
      }
    );

    // 复制 Markdown
    const btnMd = createActionBtn(
      `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> 复制 MD`,
      '复制原始 Markdown',
      () => {
        navigator.clipboard.writeText(rawMarkdown).then(() => flashBtn(btnMd, '✓ 已复制'));
      }
    );

    // 重新生成
    const btnRegen = createActionBtn(
      `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg> 重新生成`,
      '重新生成回复',
      () => {
        if (lastUserMessage && onSendMessage && !isWaitingResponse) {
          onSendMessage(lastUserMessage, true);
        }
      }
    );

    bar.appendChild(btnText);
    bar.appendChild(btnMd);
    bar.appendChild(btnRegen);

    // 查看结果按钮（可选，仅命题任务完成时出现）
    if (resultData && onShowResult) {
      const btnResult = createActionBtn(
        `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9h6M9 12h6M9 15h4"/></svg> 查看结果`,
        '查看任务结果',
        () => onShowResult(resultData),
        'result-btn'
      );
      bar.appendChild(btnResult);
    }

    return bar;
  }

  /** 创建操作按钮辅助函数 */
  function createActionBtn(html, title, onClick, extraClass) {
    const btn = document.createElement('button');
    btn.className = 'msg-action-btn' + (extraClass ? ' ' + extraClass : '');
    btn.title = title;
    btn.innerHTML = html;
    btn.addEventListener('click', onClick);
    return btn;
  }

  /** 短暂修改按钮文本后恢复 */
  function flashBtn(btn, text) {
    const orig = btn.innerHTML;
    btn.innerHTML = text;
    btn.disabled = true;
    setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 1500);
  }

  /** 为最后一条 AI 消息附加结果按钮（外部调用） */
  function attachResultToLastMessage(resultData) {
    if (!onShowResult) return;
    const rows = messageListEl.querySelectorAll('.message-row.assistant');
    if (!rows || rows.length === 0) return;
    const lastRow = rows[rows.length - 1];
    const bar = lastRow.querySelector('.msg-actions');
    if (!bar || bar.querySelector('.result-btn')) return;

    const btnResult = createActionBtn(
      `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9h6M9 12h6M9 15h4"/></svg> 查看结果`,
      '查看任务结果',
      () => onShowResult(resultData),
      'result-btn'
    );
    bar.appendChild(btnResult);
  }

  /**
   * 将带有 ```mermaid 的代码块渲染成 SVG 图像
   */
  async function renderMermaidInBubble(bubbleEl, resultData) {
    if (typeof mermaid === 'undefined') return;

    // 先检查传入的 resultData 中是否有直接带知识拓扑
    let topologyCode = resultData?.knowledge_topology || null;

    // 如果 markdown 中本身混入了 mermaid 代码块
    const mermaidNodes = bubbleEl.querySelectorAll('code.language-mermaid');
    
    // 如果没有自带节点且传了拓扑数据，我们手动给它加一个
    if (mermaidNodes.length === 0 && topologyCode) {
        // 尝试解析纯代码部分
        const match = topologyCode.match(/```mermaid[\s\S]*?\n([\s\S]+?)```/);
        if (match) {
            topologyCode = match[1];
        } else {
            topologyCode = topologyCode.replace(/```mermaid/g, '').replace(/```/g, '');
        }

        const container = document.createElement('div');
        container.className = 'mermaid-chart-container';
        container.innerHTML = `
            <div class="mermaid-title">🧠 GraphRAG 知识溯源</div>
            <div class="mermaid-content"></div>
        `;
        bubbleEl.appendChild(container);
        
        try {
            const id = 'mermaid-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
            const { svg } = await mermaid.render(id, topologyCode);
            container.querySelector('.mermaid-content').innerHTML = svg;
        } catch (err) {
            console.error('Mermaid render error:', err);
            container.innerHTML = '<div style="color:red;font-size:12px;">图表渲染失败</div>';
        }
        return;
    }

    // 处理 markdown 原本解析到的所有 mermaid 代码块
    for (const codeEl of Array.from(mermaidNodes)) {
      const preEl = codeEl.parentElement;
      if (!preEl) continue;
      const codeText = codeEl.textContent;
      
      const container = document.createElement('div');
      container.className = 'mermaid-chart-container';
      
      try {
        const id = 'mermaid-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
        const { svg } = await mermaid.render(id, codeText);
        container.innerHTML = svg;
        preEl.replaceWith(container);
      } catch (err) {
        console.error('Mermaid render error:', err);
        container.innerHTML = '<div style="color:red;font-size:12px;">图表渲染失败</div>';
        preEl.replaceWith(container);
      }
    }
  }

  // ---- 工具函数 ----

  function renderMarkdown(content) {
    if (!content) return '';
    if (markedInstance) {
      try {
        const rawHtml = markedInstance.parse(content);
        return typeof DOMPurify !== 'undefined'
          ? DOMPurify.sanitize(rawHtml)
          : rawHtml;
      } catch {
        return escapeHtml(content);
      }
    }
    return escapeHtml(content).replace(/\n/g, '<br>');
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function scrollToBottom() {
    messageListEl.scrollTo({ top: messageListEl.scrollHeight, behavior: 'smooth' });
  }

  return {
    init,
    appendUserMessage,
    showTyping,
    showAssistantMessage,
    showErrorMessage,
    clearMessages,
    restoreMessages,
    scrollToBottom,
    attachResultToLastMessage,
    setRegenerating,
    getActiveThoughtContainer,
  };
})();
