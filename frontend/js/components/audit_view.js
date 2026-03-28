/**
 * audit_view.js
 * 
 * 审题文档批注视图 - 实现设计文档中的「文档批注视图」模式
 * 
 * 核心功能：
 * 1. 主区域（原稿视图）：渲染试卷内容，Agent发现问题时高亮/画线
 * 2. 侧边栏（审查Timeline & 报告单）：动态生成审查流，最终汇总为可交互报告
 * 3. 逐题扫描视觉效果
 * 4. 点击报告项联动滚动到原试卷对应位置
 */

const AuditView = (() => {
  'use strict';

  // ==================== 状态 ====================
  let _currentExamContent = '';
  let _issues = [];           // 检测到的问题列表
  let _scanProgress = 0;      // 扫描进度 (0-100)
  let _isScanning = false;    // 是否正在扫描
  let _containerEl = null;
  let _originalEl = null;     // 原稿视图容器
  let _timelineEl = null;     // 审查时间线容器
  let _reportEl = null;       // 报告汇总容器

  // ==================== 初始化 ====================

  /**
   * 初始化审题视图
   * @param {string} containerId - 容器元素ID
   * @param {string} examContent - 待审试题内容
   */
  function init(containerId, examContent = '') {
    _containerEl = document.getElementById(containerId);
    if (!_containerEl) {
      console.warn('[AuditView] 容器元素不存在:', containerId);
      return;
    }

    _currentExamContent = examContent;
    _issues = [];
    _scanProgress = 0;

    _renderLayout();
    _bindEvents();
  }

  // ==================== 布局渲染 ====================

  function _renderLayout() {
    _containerEl.innerHTML = `
      <div class="audit-workspace">
        <!-- 左侧：原稿视图 -->
        <div class="audit-original-panel">
          <div class="audit-panel-header">
            <div class="audit-panel-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
              </svg>
              <span>原稿视图</span>
            </div>
            <div class="audit-scan-indicator" id="audit-scan-indicator" style="display: none;">
              <div class="scan-line"></div>
              <span class="scan-text">正在扫描...</span>
            </div>
          </div>
          <div class="audit-original-content" id="audit-original-content">
            <div class="audit-empty-state">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity: 0.3; margin-bottom: 12px;">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
              <p>等待上传或粘贴试题内容...</p>
            </div>
          </div>
        </div>

        <!-- 右侧：审查时间线 & 报告 -->
        <div class="audit-timeline-panel">
          <div class="audit-panel-header">
            <div class="audit-panel-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <polyline points="14 2 14 8 20 8"></polyline>
                <line x1="16" y1="13" x2="8" y2="13"></line>
                <line x1="16" y1="17" x2="8" y2="17"></line>
              </svg>
              <span>审查报告</span>
            </div>
            <div class="audit-stats" id="audit-stats" style="display: none;">
              <span class="stat-item stat-error"><span class="stat-count" id="stat-error-count">0</span> 错误</span>
              <span class="stat-item stat-warning"><span class="stat-count" id="stat-warning-count">0</span> 警告</span>
              <span class="stat-item stat-info"><span class="stat-count" id="stat-info-count">0</span> 建议</span>
            </div>
          </div>
          
          <!-- 审查时间线 -->
          <div class="audit-timeline" id="audit-timeline">
            <div class="audit-timeline-empty">
              <p>审查结果将在此显示...</p>
            </div>
          </div>

          <!-- 汇总报告 -->
          <div class="audit-report-summary" id="audit-report-summary" style="display: none;">
            <div class="report-summary-header">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                <polyline points="22 4 12 14.01 9 11.01"></polyline>
              </svg>
              <span>审查完成</span>
            </div>
            <div class="report-summary-content" id="report-summary-content"></div>
            <div class="report-actions">
              <button class="report-btn report-btn-primary" id="audit-download-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                  <polyline points="7 10 12 15 17 10"></polyline>
                  <line x1="12" y1="15" x2="12" y2="3"></line>
                </svg>
                下载报告
              </button>
            </div>
          </div>
        </div>
      </div>
    `;

    _originalEl = document.getElementById('audit-original-content');
    _timelineEl = document.getElementById('audit-timeline');
    _reportEl = document.getElementById('audit-report-summary');
  }

  // ==================== 事件绑定 ====================

  function _bindEvents() {
    // 下载报告按钮
    document.getElementById('audit-download-btn')?.addEventListener('click', _handleDownloadReport);
  }

  // ==================== 核心方法 ====================

  /**
   * 渲染审题结果
   * @param {string} markdown - Markdown 格式的审题报告
   * @param {string} containerId - 容器ID
   */
  function render(markdown, containerId) {
    init(containerId);

    if (!markdown) return;

    // 解析 Markdown 内容，提取问题和建议
    const parsedResult = _parseAuditMarkdown(markdown);

    // 渲染原稿视图
    _renderOriginalContent(_currentExamContent || parsedResult.examContent);

    // 渲染问题列表
    if (parsedResult.issues.length > 0) {
      _issues = parsedResult.issues;
      _renderIssues();
      _highlightIssues();
      _updateStats();
    }

    // 渲染汇总报告
    _renderSummaryReport(markdown, parsedResult);
  }

  /**
   * 设置试题内容
   * @param {string} content - 试题内容
   */
  function setExamContent(content) {
    _currentExamContent = content;
    if (_originalEl) {
      _renderOriginalContent(content);
    }
  }

  /**
   * 开始扫描动画
   */
  function startScanAnimation() {
    _isScanning = true;
    _scanProgress = 0;
    const indicator = document.getElementById('audit-scan-indicator');
    if (indicator) {
      indicator.style.display = 'flex';
    }
    _animateScanLine();
  }

  /**
   * 停止扫描动画
   */
  function stopScanAnimation() {
    _isScanning = false;
    const indicator = document.getElementById('audit-scan-indicator');
    if (indicator) {
      indicator.style.display = 'none';
    }
  }

  /**
   * 添加审查时间线项
   * @param {Object} item - 时间线项
   * @param {string} item.type - 类型: error | warning | info | success
   * @param {string} item.title - 标题
   * @param {string} item.detail - 详情
   * @param {number} item.questionIndex - 相关题目索引（用于联动滚动）
   */
  function addTimelineItem(item) {
    if (!_timelineEl) return;

    // 移除空状态提示
    const emptyEl = _timelineEl.querySelector('.audit-timeline-empty');
    if (emptyEl) emptyEl.remove();

    const itemEl = document.createElement('div');
    itemEl.className = `audit-timeline-item audit-item-${item.type || 'info'}`;
    itemEl.dataset.questionIndex = item.questionIndex || '';

    const icon = _getItemIcon(item.type);

    itemEl.innerHTML = `
      <div class="timeline-item-icon">${icon}</div>
      <div class="timeline-item-content">
        <div class="timeline-item-title">${item.title}</div>
        ${item.detail ? `<div class="timeline-item-detail">${item.detail}</div>` : ''}
        ${item.source ? `<div class="timeline-item-source">来源: ${item.source}</div>` : ''}
      </div>
      <div class="timeline-item-time">${new Date().toLocaleTimeString()}</div>
    `;

    // 点击联动滚动到原稿对应位置
    if (item.questionIndex !== undefined) {
      itemEl.addEventListener('click', () => _scrollToQuestion(item.questionIndex));
      itemEl.style.cursor = 'pointer';
    }

    _timelineEl.appendChild(itemEl);
    _timelineEl.scrollTop = _timelineEl.scrollHeight;

    // 更新统计
    if (item.type) {
      _issues.push(item);
      _updateStats();
    }
  }

  // ==================== 内部方法 ====================

  function _renderOriginalContent(content) {
    if (!_originalEl) return;

    if (!content) {
      _originalEl.innerHTML = `
        <div class="audit-empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity: 0.3; margin-bottom: 12px;">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <p>等待上传或粘贴试题内容...</p>
        </div>
      `;
      return;
    }

    // 解析并渲染试题内容，添加题目编号
    const questions = _parseQuestions(content);
    if (questions.length > 0) {
      let html = '<div class="exam-questions">';
      questions.forEach((q, idx) => {
        html += `
          <div class="exam-question" id="exam-question-${idx}" data-index="${idx}">
            <div class="question-number">第 ${idx + 1} 题</div>
            <div class="question-content">${window.marked ? marked.parse(q) : q}</div>
          </div>
        `;
      });
      html += '</div>';
      _originalEl.innerHTML = html;
    } else {
      // 直接渲染 Markdown
      _originalEl.innerHTML = window.marked ? marked.parse(content) : content;
    }

    // 代码高亮
    if (window.hljs) {
      _originalEl.querySelectorAll('pre code').forEach(block => hljs.highlightElement(block));
    }
  }

  function _parseQuestions(content) {
    // 简单的题目分割逻辑（可根据实际格式调整）
    const patterns = [
      /(?:^|\n)(?:第[一二三四五六七八九十\d]+[题道]|[\d]+[\.、．]|[（(][\d]+[)）])/g,
      /(?:Question\s*\d+|Q\d+)/gi
    ];

    for (const pattern of patterns) {
      const matches = [...content.matchAll(pattern)];
      if (matches.length > 1) {
        const questions = [];
        let lastIndex = 0;
        matches.forEach((match, idx) => {
          if (idx > 0) {
            questions.push(content.substring(lastIndex, match.index).trim());
          }
          lastIndex = match.index;
        });
        questions.push(content.substring(lastIndex).trim());
        return questions.filter(q => q.length > 10);
      }
    }

    return [];
  }

  function _parseAuditMarkdown(markdown) {
    const result = {
      examContent: '',
      issues: [],
      summary: ''
    };

    // 解析问题类型
    const errorPatterns = [
      { pattern: /错误[：:]\s*([^\n]+)/g, type: 'error' },
      { pattern: /警告[：:]\s*([^\n]+)/g, type: 'warning' },
      { pattern: /建议[：:]\s*([^\n]+)/g, type: 'info' },
      { pattern: /科学性错误[：:]\s*([^\n]+)/g, type: 'error' },
      { pattern: /格式错误[：:]\s*([^\n]+)/g, type: 'warning' },
      { pattern: /难度[^\n]*过高|过低/g, type: 'warning' },
      { pattern: /第\s*(\d+)\s*题/g, type: 'reference' }
    ];

    // 提取问题
    const lines = markdown.split('\n');
    let currentIssue = null;

    lines.forEach(line => {
      for (const { pattern, type } of errorPatterns) {
        const matches = [...line.matchAll(pattern)];
        matches.forEach(match => {
          if (type !== 'reference') {
            result.issues.push({
              type,
              title: match[1] || match[0],
              detail: line,
              questionIndex: _extractQuestionNumber(line)
            });
          }
        });
      }
    });

    return result;
  }

  function _extractQuestionNumber(text) {
    const match = text.match(/第\s*(\d+)\s*题/);
    return match ? parseInt(match[1]) - 1 : undefined;
  }

  function _renderIssues() {
    if (!_timelineEl) return;

    // 清空并渲染所有问题
    _timelineEl.innerHTML = '';

    _issues.forEach((issue, idx) => {
      addTimelineItem(issue);
    });
  }

  function _highlightIssues() {
    if (!_originalEl) return;

    // 高亮有问题的题目
    _issues.forEach(issue => {
      if (issue.questionIndex !== undefined) {
        const questionEl = document.getElementById(`exam-question-${issue.questionIndex}`);
        if (questionEl) {
          questionEl.classList.add(`has-${issue.type || 'warning'}`);

          // 添加问题标记
          const marker = document.createElement('div');
          marker.className = 'issue-marker';
          marker.innerHTML = `
            <span class="issue-type issue-type-${issue.type || 'warning'}">
              ${issue.type === 'error' ? '错误' : issue.type === 'warning' ? '警告' : '建议'}
            </span>
            <span class="issue-title">${issue.title}</span>
          `;
          questionEl.appendChild(marker);
        }
      }
    });
  }

  function _updateStats() {
    const statsEl = document.getElementById('audit-stats');
    if (!statsEl) return;

    const errorCount = _issues.filter(i => i.type === 'error').length;
    const warningCount = _issues.filter(i => i.type === 'warning').length;
    const infoCount = _issues.filter(i => i.type === 'info').length;

    document.getElementById('stat-error-count').textContent = errorCount;
    document.getElementById('stat-warning-count').textContent = warningCount;
    document.getElementById('stat-info-count').textContent = infoCount;

    statsEl.style.display = 'flex';
  }

  function _renderSummaryReport(markdown, parsedResult) {
    if (!_reportEl) return;

    const errorCount = _issues.filter(i => i.type === 'error').length;
    const warningCount = _issues.filter(i => i.type === 'warning').length;
    const infoCount = _issues.filter(i => i.type === 'info').length;

    const summaryContent = document.getElementById('report-summary-content');
    if (summaryContent) {
      summaryContent.innerHTML = `
        <div class="summary-stats">
          <div class="summary-stat">
            <span class="stat-number stat-error">${errorCount}</span>
            <span class="stat-label">科学性错误</span>
          </div>
          <div class="summary-stat">
            <span class="stat-number stat-warning">${warningCount}</span>
            <span class="stat-label">格式问题</span>
          </div>
          <div class="summary-stat">
            <span class="stat-number stat-info">${infoCount}</span>
            <span class="stat-label">优化建议</span>
          </div>
        </div>
        <div class="summary-grade">
          ${errorCount === 0 && warningCount === 0
          ? '<span class="grade-pass">✓ 试卷质量良好</span>'
          : '<span class="grade-issues">⚠ 发现问题需要修正</span>'}
        </div>
      `;
    }

    _reportEl.style.display = 'block';
  }

  function _scrollToQuestion(index) {
    const questionEl = document.getElementById(`exam-question-${index}`);
    if (questionEl && _originalEl) {
      questionEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      questionEl.classList.add('highlight-flash');
      setTimeout(() => questionEl.classList.remove('highlight-flash'), 2000);
    }
  }

  function _animateScanLine() {
    if (!_isScanning) return;

    const scanLine = document.querySelector('.scan-line');
    if (scanLine && _originalEl) {
      const height = _originalEl.scrollHeight;
      const progress = (_scanProgress % 100) / 100;
      scanLine.style.top = `${progress * height}px`;
    }

    _scanProgress += 2;
    requestAnimationFrame(_animateScanLine);
  }

  function _getItemIcon(type) {
    const icons = {
      error: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="15" y1="9" x2="9" y2="15"></line>
        <line x1="9" y1="9" x2="15" y2="15"></line>
      </svg>`,
      warning: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
        <line x1="12" y1="9" x2="12" y2="13"></line>
        <line x1="12" y1="17" x2="12.01" y2="17"></line>
      </svg>`,
      info: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>`,
      success: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
        <polyline points="22 4 12 14.01 9 11.01"></polyline>
      </svg>`
    };
    return icons[type] || icons.info;
  }

  function _handleDownloadReport() {
    // 生成报告内容
    const reportContent = _generateReportContent();

    // 创建下载
    const blob = new Blob([reportContent], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `审题报告_${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function _generateReportContent() {
    const errorCount = _issues.filter(i => i.type === 'error').length;
    const warningCount = _issues.filter(i => i.type === 'warning').length;
    const infoCount = _issues.filter(i => i.type === 'info').length;

    let content = `# 审题质检报告\n\n`;
    content += `**生成时间**: ${new Date().toLocaleString()}\n\n`;
    content += `---\n\n`;
    content += `## 统计概览\n\n`;
    content += `- 🔴 科学性错误: ${errorCount} 处\n`;
    content += `- 🟡 格式问题: ${warningCount} 处\n`;
    content += `- 🔵 优化建议: ${infoCount} 处\n\n`;

    if (_issues.length > 0) {
      content += `---\n\n`;
      content += `## 问题详情\n\n`;
      _issues.forEach((issue, idx) => {
        const typeIcon = { error: '🔴', warning: '🟡', info: '🔵' }[issue.type] || '📝';
        content += `### ${typeIcon} ${issue.title}\n\n`;
        if (issue.detail) content += `${issue.detail}\n\n`;
        if (issue.questionIndex !== undefined) content += `*位置: 第 ${issue.questionIndex + 1} 题*\n\n`;
      });
    }

    return content;
  }

  // ==================== 公共 API ====================

  return {
    init,
    render,
    setExamContent,
    addTimelineItem,
    startScanAnimation,
    stopScanAnimation
  };
})();

// 导出全局
window.AuditView = AuditView;
