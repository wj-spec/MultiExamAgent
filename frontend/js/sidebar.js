/**
 * sidebar.js — 左侧边栏对话管理
 * 职责：新建对话、加载历史列表、切换对话、删除对话、清除全部历史
 */

const Sidebar = (() => {
  let convListEl;
  let currentConvId = null;
  let onSwitchConversation = null; // 切换对话的回调

  function init(switchCallback) {
    convListEl = document.getElementById('conv-list');
    onSwitchConversation = switchCallback;

    document.getElementById('btn-new-chat').addEventListener('click', newConversation);
    document.getElementById('btn-clear-history').addEventListener('click', clearAllHistory);

    // 折叠按钮
    const toggleBtn = document.getElementById('sidebar-toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', toggleCollapse);
    }

    // 展开按钮（仅折叠时可见）
    const expandBtn = document.getElementById('sidebar-expand-btn');
    if (expandBtn) {
      expandBtn.addEventListener('click', () => {
        setSidebarCollapsed(false);
        localStorage.setItem('sidebar-collapsed', 'false');
      });
    }

    // 折叠时点击 logo icon 展开（永久检查状态）
    const logoIcon = document.querySelector('#sidebar .sidebar-logo-icon');
    if (logoIcon) {
      logoIcon.addEventListener('click', () => {
        const sidebar = document.getElementById('sidebar');
        if (sidebar.classList.contains('collapsed')) {
          setSidebarCollapsed(false);
          localStorage.setItem('sidebar-collapsed', 'false');
        }
      });
    }

    // 恢复折叠状态
    if (localStorage.getItem('sidebar-collapsed') === 'true') {
      setSidebarCollapsed(true);
    }

    // 加载初始历史列表
    loadConversations();
  }

  /** 切换侧边栏折叠状态 */
  function toggleCollapse() {
    const sidebar = document.getElementById('sidebar');
    const isCollapsed = sidebar.classList.contains('collapsed');
    setSidebarCollapsed(!isCollapsed);
    localStorage.setItem('sidebar-collapsed', String(!isCollapsed));
  }

  /** 设置折叠状态 */
  function setSidebarCollapsed(collapsed) {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle');
    const expandBtn = document.getElementById('sidebar-expand-btn');

    if (collapsed) {
      sidebar.classList.add('collapsed');
      if (toggleBtn) toggleBtn.title = '展开侧边栏';
      if (expandBtn) expandBtn.style.display = 'flex';
    } else {
      sidebar.classList.remove('collapsed');
      if (toggleBtn) toggleBtn.title = '折叠侧边栏';
      if (expandBtn) expandBtn.style.display = 'none';
    }
  }


  /** 设置当前活动对话 ID */
  function setCurrentConvId(id) {
    currentConvId = id;
    // 刷新高亮
    document.querySelectorAll('.conv-item').forEach(el => {
      el.classList.toggle('active', el.dataset.id === id);
    });
  }

  /** 新建对话 */
  async function newConversation() {
    if (onSwitchConversation) {
      onSwitchConversation(null); // null = 新建
    }
    // 刷新历史列表（延迟一点，让服务端创建完成）
    setTimeout(loadConversations, 500);
  }

  /** 从服务端加载历史对话列表 */
  async function loadConversations() {
    try {
      const res = await fetch('/api/conversations?limit=20');
      if (!res.ok) return;
      const data = await res.json();
      renderConversations(data.conversations || []);
    } catch (e) {
      console.warn('加载对话列表失败:', e);
    }
  }

  /** 渲染历史列表 */
  function renderConversations(conversations) {
    if (!conversations || conversations.length === 0) {
      convListEl.innerHTML = '<div class="conv-list-empty">暂无历史对话</div>';
      return;
    }

    convListEl.innerHTML = '';
    conversations.forEach(conv => {
      const item = createConvItem(conv);
      convListEl.appendChild(item);
    });

    // 恢复当前高亮
    if (currentConvId) {
      const activeEl = convListEl.querySelector(`[data-id="${currentConvId}"]`);
      if (activeEl) activeEl.classList.add('active');
    }
  }

  /** 创建单条对话条目 */
  function createConvItem(conv) {
    const item = document.createElement('div');
    item.className = 'conv-item';
    item.dataset.id = conv.id;
    if (conv.id === currentConvId) item.classList.add('active');

    // 格式化时间
    const dateStr = formatDate(conv.created_at || conv.updated_at || '');

    // 取标题（优先使用首条用户消息，否则用 ID 前8位）
    const title = getConvTitle(conv);

    item.innerHTML = `
      <div class="conv-item-icon">💬</div>
      <div class="conv-item-body">
        <div class="conv-item-title">${escapeHtml(title)}</div>
        <div class="conv-item-meta">${dateStr}</div>
      </div>
      <button class="conv-item-del" data-id="${escapeHtml(conv.id)}" title="删除">×</button>
    `;

    // 点击加载对话
    item.addEventListener('click', (e) => {
      if (e.target.classList.contains('conv-item-del')) return;
      loadConversation(conv.id);
    });

    // 删除按钮
    item.querySelector('.conv-item-del').addEventListener('click', (e) => {
      e.stopPropagation();
      deleteConversation(conv.id);
    });

    return item;
  }

  /** 加载指定对话 */
  async function loadConversation(convId) {
    if (onSwitchConversation) {
      onSwitchConversation(convId);
    }
    setCurrentConvId(convId);
  }

  /** 删除单条对话 */
  async function deleteConversation(convId) {
    if (!confirm('确认删除这条对话记录？')) return;
    try {
      const res = await fetch(`/api/conversations/${convId}`, { method: 'DELETE' });
      if (res.ok) {
        loadConversations();
        // 如果删除的是当前对话，触发新建
        if (convId === currentConvId && onSwitchConversation) {
          onSwitchConversation(null);
        }
      }
    } catch (e) {
      console.warn('删除对话失败:', e);
    }
  }

  /** 清除全部历史 */
  async function clearAllHistory() {
    if (!confirm('确认清除所有历史对话？此操作不可撤销。')) return;
    try {
      const res = await fetch('/api/conversations', { method: 'DELETE' });
      if (res.ok) {
        convListEl.innerHTML = '<div class="conv-list-empty">暂无历史对话</div>';
        // 触发新建对话
        if (onSwitchConversation) onSwitchConversation(null);
      }
    } catch (e) {
      console.warn('清除历史失败:', e);
    }
  }

  // ---- 工具函数 ----

  function getConvTitle(conv) {
    if (conv.messages && conv.messages.length > 0) {
      const firstUser = conv.messages.find(m => m.role === 'user');
      if (firstUser) {
        return firstUser.content.slice(0, 30) + (firstUser.content.length > 30 ? '...' : '');
      }
    }
    return `对话 ${(conv.id || '').slice(0, 8)}`;
  }

  function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      const now = new Date();
      const diffMs = now - d;
      const diffDays = Math.floor(diffMs / 86400000);
      if (diffDays === 0) {
        return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
      } else if (diffDays === 1) {
        return '昨天';
      } else if (diffDays < 7) {
        return `${diffDays}天前`;
      } else {
        return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
      }
    } catch {
      return '';
    }
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  return { init, setCurrentConvId, loadConversations, newConversation };
})();
