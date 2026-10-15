<template>
  <div id="status-bar" class="h-6.5 bg-[#f9f9fb] border-t border-[#ebecef] px-3.5 flex items-center justify-between text-[11.5px] text-slate-500 shrink-0 select-none">
    <!-- 左侧微状态群 -->
    <div class="flex items-center space-x-3 shrink-0">
      <!-- 智能体实时执行流脉冲呼吸指示器 -->
      <div
        v-if="systemStore.activeTask"
        class="flex items-center space-x-1.5 px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200/80 font-medium shadow-2xs"
      >
        <span class="relative flex h-2 w-2">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2 w-2 bg-sky-500"></span>
        </span>
        <span class="font-bold tracking-tight">⚡ [{{ systemStore.activeTask.title }}]</span>
        <span class="text-slate-500 font-mono text-[10.5px]">({{ systemStore.activeTask.current_step || '处理中...' }})</span>
      </div>

      <!-- 待审批人机决策断点 -->
      <button
        v-if="systemStore.pendingGateCount > 0"
        @click="systemStore.openModal('humanGate')"
        class="status-bar-btn text-amber-800 bg-amber-50 hover:bg-amber-100 border border-amber-200/80 font-medium"
        title="点击处理未决的人机审批决策"
      >
        <span class="animate-pulse shrink-0">⏸️</span>
        <span>{{ systemStore.pendingGateCount }} 个待决策审批</span>
      </button>

      <!-- 投递箱监听守护状态 -->
      <button
        @click="systemStore.openModal('watcher')"
        class="status-bar-btn hover:text-slate-800"
        title="点击查看投递箱守护状态"
      >
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 shrink-0"></span>
        <span>投递箱: 监听中</span>
      </button>

      <!-- 计划任务守护状态徽章 -->
      <button
        @click="systemStore.openModal('scheduler')"
        class="status-bar-btn hover:text-slate-800"
        title="点击打开定时启动与计划任务中枢"
      >
        <span class="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0"></span>
        <span>计划任务: 守护中</span>
      </button>
    </div>

    <!-- 右侧微状态群 -->
    <div class="flex items-center space-x-3 shrink-0">
      <!-- 发现新补丁提示徽章 -->
      <button
        v-if="systemStore.hasUpdate"
        @click="systemStore.openModal('settings')"
        class="status-bar-btn text-amber-800 bg-amber-50 hover:bg-amber-100 border border-amber-200/80 font-medium animate-pulse"
        title="发现立体空间增量热补丁，点击查看与一键升级"
      >
        <span class="shrink-0 text-[10.5px]">⚡</span>
        <span>新补丁 v{{ systemStore.latestVersion }}</span>
      </button>

      <!-- 授权快捷状态徽章 -->
      <button
        @click="systemStore.openModal('settings')"
        class="status-bar-btn hover:text-slate-800"
        title="点击查看或激活商业授权"
      >
        <span
          class="w-1.5 h-1.5 rounded-full shrink-0"
          :class="systemStore.isLicensed ? 'bg-emerald-500' : 'bg-amber-400'"
        ></span>
        <span>{{ systemStore.isLicensed ? '商业授权正常' : '检查授权中...' }}</span>
      </button>

      <!-- 重新扫描插槽 -->
      <button
        @click="agentStore.reloadAgents()"
        title="重新扫描智能体目录"
        class="status-bar-btn hover:text-slate-800"
      >
        <span class="shrink-0 text-[10.5px]">🔄</span>
        <span>刷新插槽</span>
      </button>

      <span class="text-slate-300">|</span>
      <span class="text-[11px] text-slate-400 font-mono">
        v{{ systemStore.systemInfo?.version || '2.5.0' }} · Liti Space
      </span>
    </div>
  </div>
</template>

<script setup>
import { useSystemStore } from '../../stores/system';
import { useAgentStore } from '../../stores/agent';

const systemStore = useSystemStore();
const agentStore = useAgentStore();
</script>
