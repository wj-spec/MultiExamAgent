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

  /** 显示打字指示 */
  function showTyping() {
    isWaitingResponse = true;
    sendBtnEl.disabled = true;

    typingRowEl = document.createElement('div');
    typingRowEl.className = 'message-row assistant';
    typingRowEl.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-bubble">
        <div class="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>
    `;
    messageListEl.appendChild(typingRowEl);
    scrollToBottom();
  }

  /** 移除打字指示，替换为实际回复 */
  function showAssistantMessage(content, resultData) {
    isWaitingResponse = false;
    sendBtnEl.disabled = false;

    // 移除打字指示
    if (typingRowEl) {
      typingRowEl.remove();
      typingRowEl = null;
    }

    const row = document.createElement('div');
    row.className = 'message-row assistant';

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = '🤖';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    // Markdown 渲染
    bubble.innerHTML = renderMarkdown(content);

    // 代码高亮后处理
    if (typeof hljs !== 'undefined') {
      bubble.querySelectorAll('pre code').forEach(hljs.highlightElement);
    }

    // 操作工具栏
    const actions = buildMsgActions(content, resultData);

    row.appendChild(avatar);
    row.appendChild(bubble);
    row.appendChild(actions);

    messageListEl.appendChild(row);
    scrollToBottom();
    return row;
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
          onSendMessage(lastUserMessage);
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
  };
})();
