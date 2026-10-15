<template>
  <footer class="px-4 md:px-6 pb-2 pt-1 bg-gradient-to-t from-white via-white/95 to-transparent shrink-0 flex flex-col items-center select-none z-20">
    <div class="w-full max-w-3xl relative">
      <!-- 悬浮大圆角胶囊卡片 (千问风格一体化输入卡片) -->
      <div
        class="floating-input-card bg-white rounded-2xl md:rounded-3xl border border-slate-200/90 shadow-[0_4px_24px_rgba(0,0,0,0.06)] focus-within:border-slate-400 focus-within:ring-4 focus-within:ring-slate-100 transition-all p-3 flex flex-col justify-between"
      >
        <!-- 核心输入文本域 (自适应高度) -->
        <textarea
          ref="textareaRef"
          v-model="inputPrompt"
          @keydown="handleKeyDown"
          @input="adjustTextareaHeight"
          rows="1"
          :placeholder="inputPlaceholder"
          class="w-full text-[14.5px] leading-relaxed text-slate-800 outline-none resize-none bg-transparent placeholder-slate-400 min-h-[38px] max-h-36 px-1.5 py-0.5"
        ></textarea>

        <!-- 卡片内嵌底栏：左侧轻量能力入口矩阵 + 右侧圆形向上箭头发送圆钮 (千问同款) -->
        <div class="flex items-center justify-between pt-1.5 border-t border-slate-100/80 mt-1">
          <!-- 左侧轻量工具栏 -->
          <div class="flex items-center space-x-1" ref="quickMenuRef">
            <!-- 常用指令下拉弹出菜单 -->
            <div class="relative">
              <button
                type="button"
                @click="chipsMenuOpen = !chipsMenuOpen"
                title="常用指令与业务提示词"
                class="px-2.5 py-1 rounded-lg hover:bg-slate-100 active:bg-slate-200 text-[12px] font-medium flex items-center space-x-1 text-slate-600 transition cursor-pointer"
              >
                <span>💡</span>
                <span class="hidden sm:inline">常用指令</span>
                <span class="text-[9px] text-slate-400 transform" :class="chipsMenuOpen ? 'rotate-180' : ''">▼</span>
              </button>

              <!-- 快捷指令弹出浮层 (宽度适度拓宽至 300px，单行整洁省略，悬停查看完整提示) -->
              <div
                v-if="chipsMenuOpen"
                class="absolute left-0 bottom-10 w-75 sm:w-80 max-h-72 overflow-y-auto bg-white rounded-xl shadow-xl border border-slate-200 p-1.5 z-50 text-[12.5px] animate-scale-up space-y-0.5"
              >
                <div class="text-[11px] font-semibold text-slate-400 px-2.5 py-1.5 border-b border-slate-100/80 mb-1">
                  常用功能与指令
                </div>
                <button
                  v-for="(item, idx) in formattedQuickChips"
                  :key="idx"
                  type="button"
                  @click="selectChip(item)"
                  :title="item.tooltip"
                  class="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-slate-50 text-slate-700 transition cursor-pointer truncate block"
                >
                  <span class="truncate">{{ item.label }}</span>
                </button>
              </div>
            </div>
          </div>

          <!-- 右侧极简圆形向上箭头发送按钮 (千问同款 ↑) -->
          <button
            type="button"
            @click="submitMessage"
            :disabled="!inputPrompt.trim() || chatStore.sending"
            :title="chatStore.sending ? '正在思考执行中...' : '发送指令 (Enter)'"
            :class="inputPrompt.trim() && !chatStore.sending
              ? 'bg-slate-900 hover:bg-slate-800 text-white cursor-pointer hover:scale-105 active:scale-95 shadow-xs'
              : 'bg-slate-100 text-slate-300 cursor-not-allowed'"
            class="w-8 h-8 rounded-full flex items-center justify-center transition-all shrink-0"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 10l7-7m0 0l7 7m-7-7v18"></path>
            </svg>
          </button>
        </div>
      </div>

      <!-- 千问同款微型单行免责声明 (极简浅灰，不占垂直空间) -->
      <p class="text-center text-[11px] text-slate-400 mt-1.5 tracking-tight">
        内容由 AI 生成，请注意甄别重要商业决策 · Enter 发送，Shift+Enter 换行
      </p>
    </div>
  </footer>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue';
import { useAgentStore } from '../../stores/agent';
import { useChatStore } from '../../stores/chat';

const agentStore = useAgentStore();
const chatStore = useChatStore();

const inputPrompt = ref('');
const textareaRef = ref(null);
const chipsMenuOpen = ref(false);
const quickMenuRef = ref(null);

const inputPlaceholder = computed(() => {
  if (agentStore.currentAgentReadiness?.state === 'INSTALLING_DEPENDENCIES') {
    return `正在为 ${agentStore.currentAgent?.display_name || '智能体'} 装备运行环境 (${Math.round(agentStore.currentAgentReadiness.progress || 50)}%)...`;
  }
  return `向 ${agentStore.currentAgent?.display_name || '智能体'} 提问，或输入业务指令...`;
});

const formattedQuickChips = computed(() => {
  const rawChips = agentStore.currentAgent?.quick_chips;
  let list = [];
  if (Array.isArray(rawChips)) {
    list = rawChips;
  } else if (typeof rawChips === 'string') {
    list = rawChips.split(',').map(s => s.trim()).filter(Boolean);
  } else {
    list = ['梳理业务现状', '检查底座环境', '生成审计报表'];
  }

  return list.map(item => {
    const raw = String(item).trim();
    // 匹配 [EXEC] 或其他命令后带括号说明的场景，如 "⚡ [EXEC] status (0-Token 状态自检)"
    const match = raw.match(/^(?:[\p{Emoji}\u200d\s]*)(.+?)\s*[(（]([^()（）]+)[)）]\s*$/u);
    if (match) {
      const commandPart = match[1].trim();
      const descPart = match[2].trim();
      return {
        label: descPart,              // 弹窗中仅展示功能说明
        command: commandPart,         // 输入框中仅填入纯指令（如 [EXEC] status）
        tooltip: `${descPart}：${commandPart}` // 鼠标悬停提示完整信息
      };
    }

    // 普通自然语言指令，过滤开头的 Emoji 与特殊前缀符号
    const cleanLabel = raw.replace(/^[\p{Emoji}\u200d\s*•·✨⚡🎬🔄🚀📦📝📊🤖💡]+/u, '').trim();
    return {
      label: cleanLabel || raw,
      command: cleanLabel || raw,
      tooltip: cleanLabel || raw
    };
  });
});

function adjustTextareaHeight() {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = `${Math.min(el.scrollHeight, 144)}px`;
}

function selectChip(item) {
  // 仅填入纯净命令内容
  inputPrompt.value = item.command;
  chipsMenuOpen.value = false;
  nextTick(() => {
    adjustTextareaHeight();
    if (textareaRef.value) textareaRef.value.focus();
  });
}

function handleKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    submitMessage();
  }
}

function submitMessage() {
  if (!inputPrompt.value.trim() || chatStore.sending) return;
  const msg = inputPrompt.value;
  inputPrompt.value = '';
  chipsMenuOpen.value = false;
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto';
  }
  chatStore.sendMessage(msg);
}

function handleClickOutside(e) {
  if (quickMenuRef.value && !quickMenuRef.value.contains(e.target)) {
    chipsMenuOpen.value = false;
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});
</script>
