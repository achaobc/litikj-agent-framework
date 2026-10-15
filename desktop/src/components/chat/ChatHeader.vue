<template>
  <header class="h-14 border-b border-[#ebecef] px-6 flex items-center justify-between bg-white shrink-0 z-20 select-none">
    <!-- 左侧：当前智能体身份 + 历史会话切换下拉 -->
    <div class="flex items-center space-x-3 min-w-0 mr-4">
      <div class="w-8 h-8 rounded-xl bg-slate-100 border border-slate-200/80 flex items-center justify-center text-lg shrink-0">
        <span>{{ agentStore.currentAgent?.icon || '🤖' }}</span>
      </div>
      <div class="flex items-center space-x-2 truncate">
        <span class="font-semibold text-slate-800 text-[14.5px] truncate">
          {{ agentStore.currentAgent?.display_name || agentStore.currentAgent?.name || '请选择智能体' }}
        </span>
        <span
          v-if="agentStore.currentAgent?.version"
          class="text-[10px] px-1.5 py-0.2 rounded font-mono font-medium bg-slate-100 text-slate-600 border border-slate-200 shrink-0"
          title="当前运行版本"
        >
          v{{ agentStore.currentAgent.version }}
        </span>
        <!-- 三态就绪状态指示器 -->
        <span
          v-if="agentStore.currentAgentReadiness.state === 'INSTALLING_DEPENDENCIES'"
          class="text-[10px] px-2 py-0.5 rounded-full font-medium bg-amber-50 text-amber-700 border border-amber-200 flex items-center space-x-1 shrink-0 animate-pulse"
          :title="`正在自愈: ${agentStore.currentAgentReadiness.current_item || '环境装备中'}`"
        >
          <span>⏳</span>
          <span>环境准备中 ({{ Math.round(agentStore.currentAgentReadiness.progress || 50) }}%)</span>
        </span>
        <span
          v-else-if="agentStore.currentAgentReadiness.state === 'ACTION_REQUIRED'"
          class="text-[10px] px-2 py-0.5 rounded-full font-medium bg-amber-50 text-amber-700 border border-amber-200 flex items-center space-x-1 shrink-0"
          title="需要扫码授权或登录凭据"
        >
          <span>🔑</span>
          <span>待授权登录</span>
        </span>
        <span
          v-else
          class="text-[10px] px-2 py-0.5 rounded-full font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center space-x-1 shrink-0"
          title="100% 完备在岗"
        >
          <span>🟢</span>
          <span>在岗待命</span>
        </span>
      </div>

      <!-- 历史会话下拉菜单入口 -->
      <div class="relative shrink-0" ref="sessionMenuRef">
        <button
          @click="sessionMenuOpen = !sessionMenuOpen"
          class="flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-slate-100/80 hover:bg-slate-200/70 active:bg-slate-200 text-slate-700 text-[12px] font-medium transition cursor-pointer max-w-[210px] border border-slate-200/60"
          title="切换或管理历史会话"
        >
          <span class="text-slate-400 text-[11px]">💬</span>
          <span class="truncate max-w-[140px]">{{ chatStore.currentSessionTitle }}</span>
          <span class="text-[9px] text-slate-400">▾</span>
        </button>

        <!-- 历史会话下拉弹窗面板 -->
        <div
          v-if="sessionMenuOpen"
          class="absolute left-0 top-8.5 w-76 bg-white rounded-xl shadow-xl border border-slate-200 py-1.5 z-50 text-[12.5px] animate-scale-up"
        >
          <!-- 顶栏：标题与新建按钮 -->
          <div class="px-3.5 py-1.5 border-b border-slate-100 flex items-center justify-between text-slate-500 text-[11.5px] font-semibold">
            <span>历史会话记录 ({{ chatStore.currentAgentSessions.length }})</span>
            <button
              @click="handleCreateNewSession"
              class="text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 px-2 py-0.5 rounded text-[11px] font-medium transition flex items-center space-x-1 cursor-pointer"
            >
              <span>+ 新建会话</span>
            </button>
          </div>

          <!-- 历史会话滚动列表 -->
          <div class="max-h-64 overflow-y-auto py-1 px-1.5 space-y-0.5">
            <div
              v-for="sess in chatStore.currentAgentSessions"
              :key="sess.id"
              @click="handleSwitchSession(sess.id)"
              class="p-2 rounded-lg cursor-pointer transition flex items-center justify-between group border border-transparent"
              :class="chatStore.currentSession?.id === sess.id ? 'bg-indigo-50/70 border-indigo-200/60 text-indigo-700 font-medium' : 'hover:bg-slate-50 text-slate-700'"
            >
              <div class="min-w-0 flex-1 pr-2">
                <div class="truncate text-[12.5px]">{{ sess.title }}</div>
                <div class="text-[10.5px] text-slate-400 flex items-center space-x-2 mt-0.5">
                  <span>{{ sess.createdAt || '刚刚' }}</span>
                  <span>·</span>
                  <span>{{ (sess.messages || []).length }} 条对话</span>
                </div>
              </div>
              <!-- 删除按钮 -->
              <button
                @click.stop="handleDeleteSession(sess.id)"
                class="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-600 p-1 rounded hover:bg-rose-50 transition text-[11px] shrink-0"
                title="删除此会话"
              >
                ✕
              </button>
            </div>
          </div>

          <!-- 底栏：清空该智能体全部历史 -->
          <div class="border-t border-slate-100 pt-1 mt-1 px-2">
            <button
              @click="handleClearAllSessions"
              class="w-full text-center py-1 text-[11px] text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition cursor-pointer"
            >
              清空该智能体全部会话
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧：智能体专属技能 + 高频产物目录 + 优雅更多操作菜单 (···) -->
    <div class="flex items-center space-x-2 shrink-0 relative" ref="menuRef">
      <!-- 智能体预置状态与参数配置入口 -->
      <button
        @click="systemStore.openModal('agentSettings')"
        title="打开当前智能体预置状态与运营参数配置面板"
        class="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-amber-200/90 bg-amber-50/70 hover:bg-amber-100/80 active:bg-amber-200/70 text-amber-900 text-[13px] font-medium transition cursor-pointer shadow-2xs"
      >
        <span>⚙️</span>
        <span>智能体设置</span>
      </button>

      <!-- 智能体专属技能卡带按钮 -->
      <button
        @click="systemStore.openModal('agentSkills')"
        title="查看与配置当前智能体专属业务技能"
        class="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-indigo-200/90 bg-indigo-50/70 hover:bg-indigo-100/80 active:bg-indigo-200/70 text-indigo-800 text-[13px] font-medium transition cursor-pointer shadow-2xs"
      >
        <span>🧩</span>
        <span>技能卡带</span>
        <span class="px-1.5 py-0.2 rounded-full text-[10.5px] font-mono bg-indigo-200/80 text-indigo-900 font-bold ml-0.5">
          {{ (agentStore.currentAgent?.skills || []).length }}
        </span>
      </button>

      <!-- 产物目录 -->
      <button
        @click="api.openOutputs()"
        title="在 Windows 资源管理器中打开产物目录 (workspace/outputs)"
        class="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-slate-200/90 hover:bg-slate-50 active:bg-slate-100 text-slate-700 text-[13px] font-medium transition cursor-pointer"
      >
        <span>📂</span>
        <span>产物目录</span>
      </button>

      <!-- 更多操作下拉按钮 (···) -->
      <div class="relative">
        <button
          @click="menuOpen = !menuOpen"
          title="更多操作与扩展能力"
          class="w-8 h-8 rounded-lg border border-slate-200/90 hover:bg-slate-50 active:bg-slate-100 text-slate-600 flex items-center justify-center transition cursor-pointer text-base font-bold"
        >
          ···
        </button>

        <!-- 更多操作下拉菜单 -->
        <div
          v-if="menuOpen"
          class="absolute right-0 top-9.5 w-56 bg-white rounded-xl shadow-xl border border-slate-200 py-1.5 z-50 text-[13px] animate-scale-up"
        >
          <button
            @click="handleCreateNewSessionFromMenu"
            class="w-full px-3.5 py-2 text-left hover:bg-slate-50 flex items-center space-x-2.5 text-slate-700 cursor-pointer font-medium"
          >
            <span class="text-indigo-600">+</span>
            <span>新建会话 (New Chat)</span>
          </button>
          <button
            @click="openModalAndClose('runModal')"
            class="w-full px-3.5 py-2 text-left hover:bg-slate-50 flex items-center space-x-2.5 text-slate-700 cursor-pointer"
          >
            <span>⚡</span>
            <span>单任务调度与仿真</span>
          </button>
          <div class="my-1 border-t border-slate-100"></div>
          <button
            @click="exportChat"
            class="w-full px-3.5 py-2 text-left hover:bg-slate-50 flex items-center space-x-2.5 text-slate-700 cursor-pointer"
          >
            <span>💾</span>
            <span>导出当前对话 (Markdown)</span>
          </button>
          <button
            @click="clearChat"
            class="w-full px-3.5 py-2 text-left hover:bg-rose-50 text-rose-600 flex items-center space-x-2.5 cursor-pointer"
          >
            <span>🧹</span>
            <span>重置当前会话</span>
          </button>
          <button
            @click="handleFactoryReset"
            class="w-full px-3.5 py-2 text-left hover:bg-rose-50 text-rose-600 flex items-center space-x-2.5 cursor-pointer"
            title="清空所有智能体会话记录并清理本地工作区产物"
          >
            <span>🗑️</span>
            <span>清空全部历史与产物</span>
          </button>
          <div class="my-1 border-t border-slate-100"></div>
          <div class="px-3.5 py-1.5 text-[11px] text-slate-400 flex items-center space-x-1.5">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"></span>
            <span>多会话已自动持久化</span>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { useSystemStore } from '../../stores/system';
import { useAgentStore } from '../../stores/agent';
import { useChatStore } from '../../stores/chat';
import { api } from '../../api/client';

const systemStore = useSystemStore();
const agentStore = useAgentStore();
const chatStore = useChatStore();

const menuOpen = ref(false);
const menuRef = ref(null);

const sessionMenuOpen = ref(false);
const sessionMenuRef = ref(null);

function handleCreateNewSession() {
  sessionMenuOpen.value = false;
  chatStore.createNewSession();
}

function handleCreateNewSessionFromMenu() {
  menuOpen.value = false;
  chatStore.createNewSession();
}

function handleSwitchSession(sessionId) {
  sessionMenuOpen.value = false;
  chatStore.switchSession(sessionId);
}

function handleDeleteSession(sessionId) {
  chatStore.deleteSession(sessionId);
}

function handleClearAllSessions() {
  sessionMenuOpen.value = false;
  chatStore.clearAllSessionsForCurrentAgent();
}

function openModalAndClose(name) {
  menuOpen.value = false;
  systemStore.openModal(name);
}

function exportChat() {
  menuOpen.value = false;
  chatStore.exportMarkdown();
}

function clearChat() {
  menuOpen.value = false;
  chatStore.clearCurrentConversation();
}

async function handleFactoryReset() {
  menuOpen.value = false;
  if (confirm('确认清空所有智能体的全部会话记录，并清理本地产物输出目录吗？')) {
    chatStore.resetAllConversationsAndStorage();
    try {
      await api.clearWorkspaceOutputs();
    } catch (e) {
      console.warn('清理工作区产物失败:', e);
    }
  }
}

function handleClickOutside(e) {
  if (menuRef.value && !menuRef.value.contains(e.target)) {
    menuOpen.value = false;
  }
  if (sessionMenuRef.value && !sessionMenuRef.value.contains(e.target)) {
    sessionMenuOpen.value = false;
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});
</script>
