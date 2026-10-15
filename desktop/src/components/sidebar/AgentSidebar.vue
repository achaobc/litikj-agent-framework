<template>
  <aside class="w-[260px] min-w-[260px] max-w-[260px] bg-[#f9f9fb] border-r border-[#ebecef] flex flex-col justify-between shrink-0 select-none overflow-hidden">
    <div class="flex-1 flex flex-col overflow-hidden min-w-0">
      <!-- + New Conversation 胶囊按钮 -->
      <div class="p-3.5 pb-2">
        <button
          @click="startNewChat"
          class="w-full py-2.5 px-3.5 bg-white hover:bg-slate-50 active:bg-slate-100 text-slate-800 text-[13.5px] font-medium rounded-full border border-slate-200/90 shadow-2xs flex items-center justify-center space-x-2 transition cursor-pointer whitespace-nowrap overflow-hidden"
        >
          <span class="text-lg font-light text-slate-500 leading-none shrink-0">+</span>
          <span class="truncate">新建会话 (New Chat)</span>
        </button>
      </div>

      <!-- 全局系统能力入口：技能卡带 & 协同流水线 -->
      <div class="px-3 pb-2 space-y-1">
        <button
          @click="systemStore.openModal('skillsHub')"
          class="w-full py-2 px-3 rounded-xl bg-white hover:bg-indigo-50/60 active:bg-indigo-100/50 border border-slate-200/80 hover:border-indigo-200 text-slate-700 hover:text-indigo-900 transition flex items-center justify-between text-[13px] font-medium cursor-pointer shadow-2xs group"
          title="管理全局已装载技能卡带与官方云端市场"
        >
          <div class="flex items-center space-x-2.5 min-w-0">
            <span class="text-base group-hover:scale-110 transition-transform">🧩</span>
            <span class="truncate font-medium text-[13px]">技能卡带 (Skills)</span>
          </div>
          <span class="text-[11px] font-mono px-1.5 py-0.2 rounded-md bg-indigo-50 text-indigo-700 font-semibold border border-indigo-100">
            {{ agentStore.skills.length }}
          </span>
        </button>

        <button
          @click="systemStore.openModal('workflow')"
          class="w-full py-2 px-3 rounded-xl bg-white hover:bg-purple-50/60 active:bg-purple-100/50 border border-slate-200/80 hover:border-purple-200 text-slate-700 hover:text-purple-900 transition flex items-center justify-between text-[13px] font-medium cursor-pointer shadow-2xs group"
          title="运行多智能体协同流水线"
        >
          <div class="flex items-center space-x-2.5 min-w-0">
            <span class="text-base group-hover:scale-110 transition-transform">🔄</span>
            <span class="truncate font-medium text-[13px]">协同流水线</span>
          </div>
          <span class="text-[10px] font-mono px-1.5 py-0.2 rounded-md bg-purple-50 text-purple-700 font-semibold border border-purple-100">
            FLOW
          </span>
        </button>
      </div>

      <!-- 智能体员工库分类标题 + 招聘触发 -->
      <div class="px-3.5 pt-2 pb-1.5 flex items-center justify-between text-[11.5px] font-semibold tracking-wider text-slate-400 uppercase">
        <div class="flex items-center space-x-1.5">
          <span>智能体员工库 (AGENTS)</span>
          <span class="bg-slate-200/70 text-slate-600 px-1.5 py-0.2 rounded font-mono text-[10.5px]">
            {{ agentStore.agents.length }}
          </span>
        </div>
        <button
          @click="systemStore.openModal('recruit')"
          class="text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 px-2 py-0.5 rounded-md text-[11.5px] font-medium transition flex items-center space-x-1 cursor-pointer"
          title="招募新数字化员工"
        >
          <span>➕ 招聘</span>
        </button>
      </div>

      <!-- 智能体列表容器 (全高度撑满，滚动顺滑) -->
      <div class="flex-1 overflow-y-auto px-2 space-y-1">
        <div v-if="agentStore.loading" class="text-[13px] text-slate-400 p-6 text-center space-y-2">
          <div class="text-xl animate-spin">⏳</div>
          <div>正在唤醒 AI 微内核底座...</div>
        </div>
        <div v-else-if="agentStore.agents.length === 0" class="text-[13px] text-slate-400 p-6 text-center space-y-2.5">
          <div class="text-xl">🔌</div>
          <div>微内核连接待建立</div>
          <button
            @click="agentStore.fetchAgents(6, 400)"
            class="px-3 py-1 bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg text-[12px] font-medium transition cursor-pointer"
          >
            重试连接 🔄
          </button>
        </div>
        <div
          v-for="agent in agentStore.agents"
          :key="agent.name"
          @click="handleSelectAgent(agent)"
          class="p-2.5 rounded-xl cursor-pointer transition flex items-center space-x-3 text-[13px] group border"
          :class="agentStore.currentAgent?.name === agent.name
            ? 'bg-white border-slate-200 shadow-2xs text-slate-800 font-medium'
            : 'hover:bg-slate-200/50 border-transparent text-slate-600'"
        >
          <!-- 智能体头像与动态状态角标 -->
          <div class="relative w-8.5 h-8.5 rounded-xl bg-slate-100 flex items-center justify-center text-lg shrink-0 border border-slate-200/60 group-hover:scale-105 transition-transform">
            <span>{{ agent.icon || '🤖' }}</span>
            <span
              v-if="getAgentReadiness(agent.name).state === 'INSTALLING_DEPENDENCIES'"
              class="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-amber-500 border-2 border-white animate-pulse"
              title="⏳ 正在装备运行环境"
            ></span>
            <span
              v-else-if="getAgentReadiness(agent.name).state === 'ACTION_REQUIRED'"
              class="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-amber-500 border-2 border-white"
              title="⚠️ 需扫码授权登录"
            ></span>
            <span
              v-else
              class="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-500 border-2 border-white"
              title="🟢 在岗待命"
            ></span>
          </div>

          <div class="min-w-0 flex-1">
            <div class="flex items-center justify-between">
              <div class="flex items-center space-x-1.5 min-w-0 truncate">
                <span class="truncate font-semibold text-slate-800 text-[13.5px]">
                  {{ agent.display_name || agent.name }}
                </span>
                <span v-if="agent.version" class="text-[9.5px] px-1 py-0.2 rounded font-mono font-normal bg-slate-100 text-slate-500 border border-slate-200/60 shrink-0">
                  v{{ agent.version }}
                </span>
              </div>

              <!-- 动态微徽章 (⏳ 准备中 ➔ 🟢 在岗待命) -->
              <div class="flex items-center shrink-0 ml-1">
                <span
                  v-if="getAgentReadiness(agent.name).state === 'INSTALLING_DEPENDENCIES'"
                  class="text-[9.5px] px-1.5 py-0.2 rounded-full font-medium bg-amber-50 text-amber-700 border border-amber-200 flex items-center space-x-0.5 animate-pulse"
                  :title="`正在自愈: ${getAgentReadiness(agent.name).current_item || '环境装备中'}`"
                >
                  <span>⏳ 准备中</span>
                </span>
                <span
                  v-else-if="getAgentReadiness(agent.name).state === 'ACTION_REQUIRED'"
                  class="text-[9.5px] px-1.5 py-0.2 rounded-full font-medium bg-amber-50 text-amber-700 border border-amber-200 flex items-center space-x-0.5"
                  title="需要扫码授权或登录凭据"
                >
                  <span>🔑 待授权</span>
                </span>
                <span
                  v-else
                  class="text-[9.5px] px-1.5 py-0.2 rounded-full font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center space-x-0.5"
                  title="100% 完备在岗"
                >
                  <span>🟢 在岗</span>
                </span>
              </div>
            </div>
            <p class="text-[11.5px] text-slate-400 truncate mt-0.5">
              {{ agent.description || '暂无职责说明' }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- 左下角常驻：⚙️ 系统设置入口 -->
    <div class="p-3 border-t border-[#ebecef] bg-[#f9f9fb]">
      <button
        @click="systemStore.openModal('settings')"
        class="w-full flex items-center justify-between px-3 py-2 rounded-xl text-slate-700 hover:bg-slate-200/60 active:bg-slate-200 transition group cursor-pointer"
      >
        <div class="flex items-center space-x-2 min-w-0">
          <span class="text-base group-hover:rotate-45 transition-transform duration-300 shrink-0">⚙️</span>
          <span class="text-[13.5px] font-medium text-slate-800 truncate">系统设置</span>
        </div>

        <!-- 右侧单一自适应状态徽章 (彻底解决 260px 宽度拥挤与截断残留) -->
        <div class="shrink-0 flex items-center pl-2">
          <!-- 场景 1: 已激活官方商业中枢 -->
          <span
            v-if="systemStore.isLicensed"
            class="text-[11px] px-2 py-0.5 rounded-full font-medium bg-emerald-50 text-emerald-700 border border-emerald-200/80 flex items-center space-x-1"
            title="官方 AI 商业授权已激活"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            <span>已激活</span>
          </span>

          <!-- 场景 2: 自定义 Key / 本地离线私有模式 -->
          <span
            v-else-if="systemStore.isCustomMode"
            class="text-[11px] px-2 py-0.5 rounded-full font-medium bg-sky-50 text-sky-700 border border-sky-200/80 flex items-center space-x-1"
            title="当前运行于自定义 API Key / 本地私有模式"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-sky-500"></span>
            <span>自定义</span>
          </span>

          <!-- 场景 3: 未激活状态 (极简灰底胶囊，无歧义，引导去设置) -->
          <span
            v-else
            class="text-[11px] px-2 py-0.5 rounded-full font-medium bg-slate-200 text-slate-600 group-hover:bg-slate-300 transition"
            title="尚未配置模型 Key 或商业授权，点击前往设置"
          >
            未激活
          </span>
        </div>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue';
import { useSystemStore } from '../../stores/system';
import { useAgentStore } from '../../stores/agent';
import { useChatStore } from '../../stores/chat';

const systemStore = useSystemStore();
const agentStore = useAgentStore();
const chatStore = useChatStore();

let readinessTimer = null;

onMounted(() => {
  readinessTimer = setInterval(() => {
    const hasPending = agentStore.agents.some(a => {
      const st = agentStore.getAgentReadiness(a.name)?.state;
      return st === 'INSTALLING_DEPENDENCIES' || st === 'ACTION_REQUIRED';
    });
    if (hasPending) {
      for (const a of agentStore.agents) {
        const st = agentStore.getAgentReadiness(a.name)?.state;
        if (st === 'INSTALLING_DEPENDENCIES' || st === 'ACTION_REQUIRED') {
          agentStore.fetchAgentReadiness(a.name);
        }
      }
    }
  }, 2500);
});

onUnmounted(() => {
  if (readinessTimer) clearInterval(readinessTimer);
});

function getAgentReadiness(agentName) {
  return agentStore.getAgentReadiness(agentName);
}

function startNewChat() {
  chatStore.createNewSession();
}

function handleSelectAgent(agent) {
  agentStore.selectAgent(agent);
  chatStore.ensureActiveSession(agent.name);
}
</script>
