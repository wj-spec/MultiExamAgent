/**
 * skills_panel.js — 技能管理面板
 *
 * 提供浮层式面板，展示已注册技能列表，支持启用/禁用开关。
 */

const SkillsPanel = (() => {
    /* ---- 分类图标映射 ---- */
    const CATEGORY_ICON = {
        validation: '🔍',
        generation: '✨',
        analysis: '📊',
    };

    const CATEGORY_LABEL = {
        validation: '验证',
        generation: '生成',
        analysis: '分析',
    };

    /* ---- DOM 创建 ---- */
    let overlay = null;

    function _createOverlay() {
        if (overlay) return overlay;

        overlay = document.createElement('div');
        overlay.className = 'skills-overlay';
        overlay.innerHTML = `
      <div class="skills-modal">
        <div class="skills-modal-header">
          <div class="skills-modal-title">
            <span class="skills-modal-icon">🔧</span>
            <span>技能管理</span>
          </div>
          <button class="skills-modal-close" id="skills-close">&times;</button>
        </div>
        <p class="skills-modal-desc">管理 Agent 的可插拔技能模块。启用技能后，Agent 在执行对应任务时将自动调用技能工具。</p>
        <div class="skills-list" id="skills-list">
          <div class="skills-loading">加载中…</div>
        </div>
        <div class="skills-footer">
          <div class="skills-mcp-status" id="skills-mcp-status"></div>
        </div>
      </div>
    `;
        document.body.appendChild(overlay);

        // 关闭事件
        overlay.querySelector('#skills-close').addEventListener('click', hide);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) hide();
        });

        return overlay;
    }

    /* ---- 渲染技能卡片 ---- */
    function _renderSkills(skills) {
        const list = document.getElementById('skills-list');
        if (!skills || skills.length === 0) {
            list.innerHTML = '<div class="skills-empty">暂无已注册技能</div>';
            return;
        }

        list.innerHTML = skills.map(skill => `
      <div class="skill-card ${skill.enabled ? 'skill-card--active' : ''}" data-id="${skill.id}">
        <div class="skill-card-header">
          <div class="skill-card-info">
            <span class="skill-card-icon">${CATEGORY_ICON[skill.category] || '🔧'}</span>
            <div>
              <div class="skill-card-name">${skill.name}</div>
              <div class="skill-card-meta">
                <span class="skill-card-tag">${CATEGORY_LABEL[skill.category] || skill.category}</span>
                <span class="skill-card-version">v${skill.version || '1.0.0'}</span>
              </div>
            </div>
          </div>
          <label class="skill-toggle">
            <input type="checkbox" ${skill.enabled ? 'checked' : ''} data-skill-id="${skill.id}">
            <span class="skill-toggle-slider"></span>
          </label>
        </div>
        <div class="skill-card-desc">${skill.description}</div>
        <div class="skill-card-bindings">
          绑定节点: ${(skill.bind_to || []).map(n => `<span class="skill-bind-tag">${n}</span>`).join(' ')}
        </div>
      </div>
    `).join('');

        // 开关事件
        list.querySelectorAll('input[data-skill-id]').forEach(input => {
            input.addEventListener('change', async (e) => {
                const id = e.target.dataset.skillId;
                const enable = e.target.checked;
                const card = e.target.closest('.skill-card');
                try {
                    const url = `/api/skills/${id}/${enable ? 'enable' : 'disable'}`;
                    const res = await fetch(url, { method: 'POST' });
                    if (!res.ok) throw new Error('API 错误');
                    card.classList.toggle('skill-card--active', enable);
                } catch (err) {
                    console.error('技能切换失败:', err);
                    e.target.checked = !enable; // 回滚
                }
            });
        });
    }

    /* ---- MCP 状态 ---- */
    async function _loadMCPStatus() {
        const el = document.getElementById('skills-mcp-status');
        try {
            const res = await fetch('/api/mcp/status');
            const data = await res.json();
            const servers = Object.values(data.servers || {});
            el.innerHTML = `
        <span class="mcp-status-dot ${data.initialized ? 'mcp-ok' : ''}"></span>
        MCP: ${servers.length} 个服务已注册
      `;
        } catch {
            el.innerHTML = `<span class="mcp-status-dot"></span> MCP: 未连接`;
        }
    }

    /* ---- 公开接口 ---- */
    async function show() {
        _createOverlay();
        overlay.classList.add('visible');

        // 加载技能列表
        try {
            const res = await fetch('/api/skills');
            const data = await res.json();
            _renderSkills(data.skills || []);
        } catch (err) {
            document.getElementById('skills-list').innerHTML =
                `<div class="skills-empty">加载失败: ${err.message}</div>`;
        }

        _loadMCPStatus();
    }

    function hide() {
        if (overlay) overlay.classList.remove('visible');
    }

    /* ---- 初始化侧边栏按钮绑定 ---- */
    function init() {
        const btn = document.getElementById('btn-skills');
        if (btn) btn.addEventListener('click', show);
    }

    return { init, show, hide };
})();

// 页面加载后初始化
document.addEventListener('DOMContentLoaded', () => SkillsPanel.init());
