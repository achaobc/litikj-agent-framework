<template>
  <div
    ref="scrollContainer"
    class="flex-1 overflow-y-auto px-4 md:px-8 py-6 bg-white select-text scroll-smooth"
  >
    <div class="max-w-3xl mx-auto w-full space-y-6">
      <!-- 1. 环境全自动自愈与依赖准备进度卡 (Zero-Friction Self-Healing) -->
      <div
        v-if="agentStore.currentAgentReadiness.state === 'INSTALLING_DEPENDENCIES'"
        class="bg-gradient-to-r from-amber-50/90 via-indigo-50/70 to-sky-50/70 border border-amber-200/80 rounded-2xl p-4.5 shadow-2xs text-[13px] animate-fade-in select-none space-y-3"
      >
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-2.5 min-w-0">
            <span class="text-xl shrink-0 animate-spin">⏳</span>
            <div>
              <div class="font-bold text-slate-800 text-[14px] flex items-center space-x-2">
                <span>正在为您准备专属数字员工</span>
                <span class="text-[11.5px] px-2 py-0.2 rounded-full font-mono bg-amber-100 text-amber-800 font-semibold border border-amber-300/60">
                  已完成 {{ Math.round(agentStore.currentAgentReadiness.progress || 50) }}%
                </span>
              </div>
              <p class="text-[12px] text-slate-500 mt-0.5">
                当前自愈项目：<span class="font-medium text-slate-700">{{ agentStore.currentAgentReadiness.current_item || '环境装配中' }}</span>
              </p>
            </div>
          </div>
          <button
            @click="agentStore.healAgent(agentStore.currentAgent?.name)"
            class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white rounded-xl text-[12px] font-semibold transition cursor-pointer shadow-2xs shrink-0 flex items-center space-x-1"
          >
            <span>⚡ 一键静默自愈</span>
          </button>
        </div>
        <!-- 进度条 -->
        <div class="w-full bg-slate-200/80 rounded-full h-2 overflow-hidden">
          <div
            class="bg-gradient-to-r from-indigo-500 via-sky-500 to-emerald-500 h-2 rounded-full transition-all duration-500 ease-out"
            :style="{ width: `${Math.max(10, Math.min(100, agentStore.currentAgentReadiness.progress || 50))}%` }"
          ></div>
        </div>
      </div>

      <!-- 2. 需要人工介入/扫码登录优雅引导卡 (ACTION_REQUIRED) -->
      <div
        v-else-if="agentStore.currentAgentReadiness.state === 'ACTION_REQUIRED'"
        class="bg-gradient-to-r from-rose-50/80 via-amber-50/60 to-indigo-50/60 border border-rose-200 rounded-2xl p-4 shadow-2xs text-[12.5px] animate-fade-in select-none flex items-center justify-between"
      >
        <div class="flex items-center space-x-3 min-w-0">
          <span class="text-2xl shrink-0">📱</span>
          <div class="min-w-0">
            <div class="font-bold text-slate-800 text-[13.5px]">
              {{ agentStore.currentAgentReadiness.action_guide?.title || '需要您完成一步授权' }}
            </div>
            <p class="text-slate-600 mt-0.5 truncate">
              {{ agentStore.currentAgentReadiness.action_guide?.message || '请使用对应移动客户端完成扫码授权，完成后将全自动流转就绪。' }}
            </p>
          </div>
        </div>
        <div class="flex items-center space-x-2 shrink-0 ml-3">
          <button
            @click="chatStore.sendMessage(agentStore.currentAgentReadiness.action_guide?.cmd || '[EXEC] login')"
            class="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white rounded-xl font-medium transition cursor-pointer shadow-2xs flex items-center space-x-1"
            title="唤起扫码授权"
          >
            <span>📱 立即扫码</span>
          </button>
        </div>
      </div>

      <!-- 默认欢迎主看板 (Module 3: 2x2 快捷卡片网格) -->
      <div
        v-if="chatStore.currentMessages.length === 0 && !currentAgentActiveTask"
        class="h-full flex flex-col items-center justify-center p-6 mx-auto select-none space-y-6 animate-fade-in"
      >
        <!-- 智能体形象与身份卡 -->
        <div class="text-center space-y-2.5">
          <div class="w-16 h-16 mx-auto rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center text-3xl shadow-2xs">
            {{ agentStore.currentAgent?.icon || '🪐' }}
          </div>
          <div>
            <div class="flex items-center justify-center space-x-2">
              <h3 class="font-bold text-slate-800 text-xl tracking-tight">
                {{ agentStore.currentAgent?.display_name || agentStore.currentAgent?.name || '立体空间智能体系统' }}
              </h3>
              <span class="text-[11px] px-2 py-0.5 rounded-full font-mono bg-sky-50 text-sky-700 border border-sky-200">
                {{ agentStore.currentAgent?.category || '岗位基准' }}
              </span>
            </div>
            <p class="text-[13px] text-slate-500 mt-1 max-w-md mx-auto leading-relaxed">
              {{ agentStore.currentAgent?.description || '专业级多智能体原生交互环境 · 软件归软件，AI归AI' }}
            </p>
          </div>
        </div>

        <!-- 2x2 推荐指令卡片网格 (Module 3 核心) -->
        <div v-if="welcomeCards.length > 0" class="w-full grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
          <div
            v-for="(card, cIdx) in welcomeCards"
            :key="cIdx"
            @click="chatStore.sendMessage(card.prompt)"
            class="p-4 rounded-xl border border-slate-200 hover:border-sky-400 bg-white hover:bg-slate-50/80 transition-all hover:shadow-xs cursor-pointer group flex items-start space-x-3 text-left"
          >
            <span class="text-2xl p-2 rounded-lg bg-slate-50 border border-slate-100 group-hover:scale-110 transition shrink-0">
              {{ card.icon }}
            </span>
            <div class="min-w-0 flex-1">
              <div class="font-semibold text-slate-800 text-[13.5px] group-hover:text-sky-600 transition truncate">
                {{ card.label }}
              </div>
              <div class="text-[11.5px] text-slate-400 mt-0.5 truncate flex items-center space-x-1">
                <span>{{ card.sub }}</span>
                <span class="group-hover:translate-x-0.5 transition inline-block">→</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部操作提示 -->
        <p class="text-[12px] text-slate-400 tracking-wide">
          点击上方卡片快速测试，或在底部胶囊输入框中输入自定义业务指令
        </p>
      </div>

      <!-- 消息流列表 -->
      <div
        v-for="(msg, idx) in chatStore.currentMessages"
        :key="idx"
        class="chat-bubble-row flex flex-col space-y-1.5 animate-fade-in"
        :class="msg.role === 'user' ? 'items-end' : 'items-start'"
      >
        <!-- 用户气泡 (千问风格柔和微胶囊，轻盈淡雅) -->
        <template v-if="msg.role === 'user'">
          <div class="max-w-[85%] bg-[#eff6ff] text-slate-800 px-4.5 py-2.5 rounded-2xl rounded-tr-xs text-[14.5px] leading-relaxed border border-sky-100 shadow-2xs">
            <div class="whitespace-pre-wrap select-text">{{ msg.content }}</div>
          </div>
          <span class="text-[10.5px] text-slate-400 px-1">{{ msg.time || '您' }}</span>
        </template>

        <!-- 助理消息 (千问风格通透无界开放流，告别厚重卡片) -->
        <template v-else>
          <div class="w-full flex flex-col items-start space-y-1.5 py-1">
            <!-- 助理身份微标 -->
            <div class="flex items-center space-x-2 text-[12.5px] font-semibold text-slate-700 select-none pb-0.5">
              <span class="text-base">{{ agentStore.currentAgent?.icon || '🪐' }}</span>
              <span>{{ agentStore.currentAgent?.display_name || agentStore.currentAgent?.name || '智能体' }}</span>
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0" title="在线"></span>
            </div>
            <!-- 通透正文 (无边框、无沉重底色、自然舒展) -->
            <div class="w-full text-slate-800 pr-1">
              <div
                class="markdown-body text-slate-800 select-text leading-relaxed"
                v-html="renderMarkdown(msg.content)"
                @click="handleContainerClick"
              ></div>
            </div>
          </div>
        </template>
      </div>

      <!-- 实时自动化流水线工序阶梯与控制台日志卡片 -->
      <TaskProgressCard
        v-if="currentAgentActiveTask"
        :task="currentAgentActiveTask"
      />

      <!-- 思考/发送中打字机动画提示 -->
      <div
        v-if="chatStore.sending"
        class="flex items-center space-x-2.5 text-[13px] text-slate-500 py-2 animate-pulse select-none"
      >
        <span class="text-base animate-spin">⏳</span>
        <span>智能体正在思考推演与调用底座执行中...</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue';
import { marked } from 'marked';

// 配置 GFM 与换行规则：强制单换行自动转为 <br>，彻底消除内容挤在一行的排版异常
marked.use({
  gfm: true,
  breaks: true
});
import { useAgentStore } from '../../stores/agent';
import { useChatStore } from '../../stores/chat';
import { useSystemStore } from '../../stores/system';
import { api } from '../../api/client';
import TaskProgressCard from './TaskProgressCard.vue';

const agentStore = useAgentStore();
const chatStore = useChatStore();
const systemStore = useSystemStore();

const scrollContainer = ref(null);

// 计算当前智能体是否挂载有活跃的执行中任务 (全局任务对所有视界可见，保证直观反馈)
const currentAgentActiveTask = computed(() => {
  return systemStore.activeTask;
});

// 2x2 欢迎引导卡片计算属性 (Module 3)
const welcomeCards = computed(() => {
  const ag = agentStore.currentAgent;
  if (!ag) return [];
  const list = [];

  // 1. 优先载入已声明的确定性 actions (如 [EXEC] ...)
  if (Array.isArray(ag.actions)) {
    ag.actions.forEach(act => {
      list.push({
        icon: act.icon || '⚡',
        label: act.label || act.command,
        prompt: act.command,
        sub: '0-Token 快速通道'
      });
    });
  }

  // 2. 补齐 quick_chips
  const chips = Array.isArray(ag.quick_chips) ? ag.quick_chips : [];
  chips.forEach(chip => {
    if (!list.some(item => item.prompt === chip)) {
      const isFast = chip.includes('[EXEC]');
      const cleanLabel = chip
        .replace(/^[\p{Emoji}\s]+/u, '')
        .replace(/\(.*?\)/g, '')
        .trim();
      list.push({
        icon: chip.slice(0, 2).trim() || '💡',
        label: cleanLabel || chip,
        prompt: chip,
        sub: isFast ? '0-Token 极速直达' : '大模型深度创作'
      });
    }
  });

  const loginIdx = list.findIndex(item => item.prompt && item.prompt.includes('login'));
  if (loginIdx > 0) {
    const [loginCard] = list.splice(loginIdx, 1);
    list.unshift(loginCard);
  }

  return list.slice(0, 4);
});

function scrollToBottom() {
  nextTick(() => {
    if (scrollContainer.value) {
      scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight;
    }
  });
}

watch(
  () => chatStore.currentMessages.length,
  () => scrollToBottom()
);

watch(
  () => chatStore.sending,
  () => scrollToBottom()
);

onMounted(() => {
  scrollToBottom();
});

function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function sanitizeHtml(html) {
  if (!html) return '';
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    // 🛡️ 严格拦截脚本、嵌入框架、内联 SVG 脚本、数学标记与危险对象 (SEC-VULN-04 / R2-VULN-06)
    const dangerousEls = doc.querySelectorAll('script, iframe, object, embed, link, base, meta, form, svg script, math');
    dangerousEls.forEach(el => el.remove());

    // 🛡️ 剥离所有元素上的内联事件 (如 onclick, onerror) 和危险伪协议
    const allNodes = doc.querySelectorAll('*');
    allNodes.forEach(node => {
      const attrs = Array.from(node.attributes);
      for (const attr of attrs) {
        const name = attr.name.toLowerCase();
        // 去除控制字符与空白后再做协议前缀嗅探
        const cleanVal = attr.value.replace(/[\x00-\x20\s]+/g, '').toLowerCase();
        if (
          name.startsWith('on') ||
          cleanVal.startsWith('javascript:') ||
          cleanVal.startsWith('vbscript:') ||
          cleanVal.startsWith('data:text/html') ||
          cleanVal.startsWith('data:image/svg+xml')
        ) {
          node.removeAttribute(attr.name);
        }
      }
    });

    return doc.body.innerHTML;
  } catch {
    return escapeHtml(html);
  }
}

function renderMarkdown(text) {
  if (!text) return '';
  let cleanText = text;

  // 1. 抽取 :::skill-artifact 卡片
  const artifactRegex = /:::skill-artifact\s*\n([\s\S]*?)\n:::/g;
  const artifacts = [];
  cleanText = cleanText.replace(artifactRegex, (match, jsonStr) => {
    try {
      const data = JSON.parse(jsonStr.trim());
      artifacts.push(data);
      return `\n\n__ARTIFACT_PLACEHOLDER_${artifacts.length - 1}__\n\n`;
    } catch {
      return match;
    }
  });

  // 2. 深度思考链手风琴
  const thinkRegex = /<think>([\s\S]*?)<\/think>/gi;
  cleanText = cleanText.replace(thinkRegex, (match, thinkContent) => {
    const escaped = escapeHtml(thinkContent.trim());
    return `\n\n<div class="tool-accordion thinking-accordion not-prose"><div class="tool-accordion-header"><div class="flex items-center space-x-2"><span>💭</span><span class="font-medium">深度思考推理过程 (Thinking Process)</span></div><span class="tool-accordion-arrow">▼</span></div><div class="tool-accordion-body whitespace-pre-wrap">${escaped}</div></div>\n\n`;
  });

  // 3. 底座工具调用日志手风琴
  const toolCallRegex = /:::tool-call\s*\n([\s\S]*?)\n:::/g;
  cleanText = cleanText.replace(toolCallRegex, (match, logContent) => {
    const escaped = escapeHtml(logContent.trim());
    return `\n\n<div class="tool-accordion not-prose"><div class="tool-accordion-header"><div class="flex items-center space-x-2"><span>⚡</span><span class="font-medium">底座工具执行与调试日志</span></div><span class="tool-accordion-arrow">▼</span></div><div class="tool-accordion-body font-mono text-[11.5px] bg-slate-900 text-slate-100 p-3 rounded-lg overflow-x-auto whitespace-pre-wrap">${escaped}</div></div>\n\n`;
  });

  let rendered = marked.parse(cleanText, { gfm: true, breaks: true });

  // 4. 替换 Artifact 卡片
  artifacts.forEach((art, idx) => {
    const cardHtml = buildArtifactCardHtml(art);
    rendered = rendered.replace(`<p>__ARTIFACT_PLACEHOLDER_${idx}__</p>`, cardHtml);
    rendered = rendered.replace(`__ARTIFACT_PLACEHOLDER_${idx}__`, cardHtml);
  });

  // 5. 增强代码块：注入优雅暗黑顶栏与一键复制按钮 (Module 6)
  rendered = rendered.replace(/<pre><code(?:\s+class="language-([^"]*)")?>([\s\S]*?)<\/code><\/pre>/gi, (match, lang, codeContent) => {
    const language = lang || 'python';
    return `
      <div class="code-block-wrapper my-4 rounded-xl border border-slate-750 bg-slate-900 overflow-hidden not-prose shadow-sm">
        <div class="flex items-center justify-between px-4 py-2 bg-slate-950/80 border-b border-slate-800 text-[12px] font-mono text-slate-400 select-none">
          <div class="flex items-center space-x-2">
            <span class="w-2.5 h-2.5 rounded-full bg-slate-700"></span>
            <span class="font-semibold text-slate-300 uppercase">${language}</span>
          </div>
          <button type="button" class="copy-code-btn px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 active:scale-95 text-slate-200 transition cursor-pointer flex items-center space-x-1 text-[11.5px]" data-action="copy_code">
            <span>📋</span>
            <span>复制</span>
          </button>
        </div>
        <pre class="p-4 text-[13px] font-mono text-slate-100 overflow-x-auto leading-relaxed whitespace-pre m-0"><code>${codeContent}</code></pre>
      </div>
    `;
  });

  // 6. 智能药丸：将 `[EXEC] config` 转换为一键直达可点击的设置面板按钮
  rendered = rendered.replace(
    /<code>\[EXEC\] config<\/code>/g,
    '<button type="button" class="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200/80 text-[12px] font-medium transition cursor-pointer shadow-2xs my-0.5" data-action="open_agent_settings"><span>⚙️</span><span>打开智能体设置面板</span></button>'
  );

  // 7. 智能自愈药丸：将 `[EXEC] heal` 或 `[EXEC] setup` 转换为一键静默自愈按钮
  rendered = rendered.replace(
    /(?:<code>|`)(?:\[EXEC\]\s+)?(?:heal|setup\s+whisper|setup\s+netdisk|setup)(?:<\/code>|`)/gi,
    '<button type="button" class="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 text-[12.5px] font-medium transition cursor-pointer shadow-2xs my-1 select-none" data-action="run_fast_heal"><span>⚡</span><span>一键全自动环境静默自愈</span></button>'
  );

  return sanitizeHtml(rendered);
}

function buildArtifactCardHtml(art) {
  const isImage = art.is_image && art.preview_url;
  const fileName = escapeHtml(art.file_name || '成果文件');
  const filePath = escapeHtml(art.file_path || '');
  const previewUrl = escapeHtml(art.preview_url || '');
  const toolName = escapeHtml(art.tool_name || art.tool || '能力卡带');
  const icon = art.icon || '🎨';
  const success = art.success !== false;
  const elapsed = art.elapsed_ms || 1;

  const imageHtml = isImage ? `
    <div class="artifact-image-container group cursor-pointer" data-action="lightbox" data-url="${previewUrl}" data-title="${fileName}" data-path="${filePath}">
      <img src="${previewUrl}" alt="${fileName}" loading="lazy" class="w-full max-h-80 object-cover rounded-xl" />
      <div class="artifact-image-overlay">
        <span class="font-medium">🔍 点击高清全屏放大预览</span>
      </div>
    </div>
  ` : '';

  const actionsHtml = filePath ? `
    <div class="artifact-card-actions">
      <button type="button" class="artifact-action-btn primary" data-action="open_file" data-path="${filePath}">
        <span>📂</span>
        <span>打开原图 / 文件</span>
      </button>
      <button type="button" class="artifact-action-btn" data-action="open_dir" data-path="${filePath}">
        <span>📁</span>
        <span>打开所在文件夹</span>
      </button>
    </div>
  ` : '';

  return `
    <div class="skill-artifact-card not-prose">
      <div class="artifact-card-header">
        <div class="flex items-center space-x-2">
          <span class="text-xl">${icon}</span>
          <div class="font-bold text-[13.5px] text-slate-800 flex items-center space-x-2">
            <span>${toolName}</span>
            <span class="text-[11px] px-2 py-0.5 rounded-full ${success ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'} font-semibold">
              ${success ? '✅ 具身执行成功' : '❌ 执行异常'}
            </span>
          </div>
        </div>
        <div class="text-[11.5px] text-slate-400 font-mono">⚡ 耗时 ${elapsed}ms</div>
      </div>
      <div class="artifact-card-body space-y-3">
        ${imageHtml}
        ${filePath ? `<div class="text-[11.5px] text-slate-400 font-mono truncate"><span>📂 本地物理路径:</span> <span class="text-slate-600 truncate">${filePath}</span></div>` : ''}
      </div>
      ${actionsHtml}
    </div>
  `;
}

function handleContainerClick(e) {
  // 1. 深度思考与工具日志折叠面板切换 (事件委托解耦，彻底避免内联 onclick XSS 风险 SEC-VULN-04)
  const accordionHeader = e.target.closest('.tool-accordion-header');
  if (accordionHeader && accordionHeader.parentElement) {
    accordionHeader.parentElement.classList.toggle('open');
    return;
  }

  const target = e.target.closest('[data-action]');
  if (!target) return;
  const action = target.getAttribute('data-action');
  const path = target.getAttribute('data-path');
  const url = target.getAttribute('data-url');
  const title = target.getAttribute('data-title');

  if (action === 'open_agent_settings') {
    systemStore.openModal('agentSettings');
  } else if (action === 'run_fast_heal') {
    if (agentStore.currentAgent) {
      systemStore.showToast('正在为您启动全自动环境静默自愈...');
      agentStore.healAgent(agentStore.currentAgent.name);
    }
  } else if (action === 'run_fast_exec') {
    const cmd = target.getAttribute('data-cmd');
    if (cmd) {
      chatStore.sendMessage(cmd);
    }
  } else if (action === 'lightbox') {
    systemStore.openModal('lightbox', { url, title, filePath: path });
  } else if (action === 'open_file') {
    api.openPath(path, 'open_file');
  } else if (action === 'open_dir') {
    api.openPath(path, 'open_dir');
  } else if (action === 'copy_code') {
    const wrapper = target.closest('.code-block-wrapper');
    if (!wrapper) return;
    const codeEl = wrapper.querySelector('code');
    if (!codeEl) return;
    const codeText = codeEl.innerText || codeEl.textContent;
    navigator.clipboard.writeText(codeText);
    const originalHtml = target.innerHTML;
    target.innerHTML = '<span>✅</span><span>已复制</span>';
    target.classList.add('text-emerald-400', 'bg-slate-700');
    systemStore.showToast('代码已复制到剪贴板');
    setTimeout(() => {
      target.innerHTML = originalHtml;
      target.classList.remove('text-emerald-400', 'bg-slate-700');
    }, 1800);
  }
}
</script>
