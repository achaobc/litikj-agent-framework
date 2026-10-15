<template>
  <div class="h-screen w-screen flex flex-col overflow-hidden bg-white text-slate-800 antialiased select-none font-sans">
    <!-- 主体工作区 (左侧浅灰侧边栏 + 右侧主看板) -->
    <div class="flex-1 flex overflow-hidden min-h-0">
      <AgentSidebar />
      <main class="flex-1 bg-white flex flex-col justify-between overflow-hidden relative">
        <ChatHeader />
        
        <!-- 投递箱轻量状态横幅 (全局置顶常驻，清爽浅蓝底色 + 明确蓝色边框，轻盈且醒目) -->
        <div
          v-if="systemStore.dropBoxNotice"
          class="mx-4 md:mx-8 mt-2.5 px-4 py-2.5 bg-gradient-to-r from-blue-50/95 via-sky-50/90 to-blue-50/80 border border-blue-300/90 rounded-2xl shadow-[0_2px_12px_rgba(59,130,246,0.08)] flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-scale-up select-none shrink-0 z-10"
        >
          <div class="flex items-center space-x-3 min-w-0">
            <div class="w-8 h-8 rounded-xl bg-blue-100/80 border border-blue-200/90 flex items-center justify-center text-base shrink-0 shadow-2xs">
              📦
            </div>
            <div class="min-w-0">
              <div class="text-[13px] font-semibold text-blue-950 flex items-center space-x-2 truncate">
                <span class="truncate">{{ systemStore.dropBoxNotice.fileName }}</span>
                <span class="text-[11px] font-medium text-blue-700 bg-blue-100/90 px-1.5 py-0.2 rounded font-mono shrink-0">
                  {{ systemStore.dropBoxNotice.fileSizeMb || 0 }} MB
                </span>
                <span class="text-[11px] font-normal text-blue-700 bg-blue-100/70 border border-blue-200/80 px-1.5 py-0.2 rounded-full shrink-0">
                  投递箱已有记录
                </span>
              </div>
              <div class="text-[11.5px] text-blue-700/85 truncate mt-0.5">
                当前视频仍驻留在投递箱中 · 可点击右侧快捷按钮重新制作或一键归档
              </div>
            </div>
          </div>

          <!-- 快捷 0-Token 交互药丸动作群 -->
          <div class="flex items-center space-x-2 shrink-0 self-end sm:self-center">
            <!-- 重新制作按钮 -->
            <button
              type="button"
              @click="systemStore.rerunDropBoxFile(systemStore.dropBoxNotice.filePath)"
              title="重置指纹并重新执行生产流水线"
              class="px-2.5 py-1 rounded-lg bg-white/90 hover:bg-white text-blue-900 border border-blue-200 hover:border-blue-300 text-[11.5px] font-medium transition cursor-pointer flex items-center space-x-1 shadow-2xs hover:scale-102 active:scale-98"
            >
              <span>🔄</span>
              <span>重新制作</span>
            </button>

            <!-- 查看投递箱 -->
            <button
              type="button"
              @click="api.openPath(systemStore.dropBoxNotice.filePath, 'open_dir')"
              title="在 Windows 资源管理器中打开该文件所在文件夹"
              class="px-2.5 py-1 rounded-lg bg-white/90 hover:bg-white text-slate-700 border border-blue-200 hover:border-blue-300 text-[11.5px] font-medium transition cursor-pointer flex items-center space-x-1 shadow-2xs hover:scale-102 active:scale-98"
            >
              <span>📂</span>
              <span>打开位置</span>
            </button>

            <!-- 一键移入归档 -->
            <button
              type="button"
              @click="systemStore.archiveDropBoxFile(systemStore.dropBoxNotice.filePath)"
              title="将该视频移至 .archive 目录，清空投递箱"
              class="px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white border border-blue-600 text-[11.5px] font-medium transition cursor-pointer flex items-center space-x-1 shadow-2xs hover:scale-102 active:scale-98"
            >
              <span>🧹</span>
              <span>移入归档</span>
            </button>

            <!-- 关闭提示 -->
            <button
              type="button"
              @click="systemStore.dismissDropBoxNotice()"
              title="暂时关闭此提醒"
              class="p-1 rounded-lg hover:bg-blue-100/70 text-blue-400 hover:text-blue-700 transition cursor-pointer text-xs"
            >
              ✕
            </button>
          </div>
        </div>

        <ChatMessages />
        <FloatingInput />
      </main>
    </div>

    <!-- 底部 26px 极简微状态栏 -->
    <StatusBar />

    <!-- 全局模态窗口集 -->
    <SettingsModal />
    <RecruitModal />
    <HumanGateModal />
    <WatcherModal />
    <SchedulerModal />
    <ImageLightboxModal />
    <QuotaExhaustedModal />
    <SkillsHubModal />
    <WorkflowModal />
    <RunModal />
    <SkillRunnerModal />
    <AgentSkillsModal />
    <AgentSettingsModal />

    <!-- 全局轻量 Toast 提示 -->
    <div
      v-if="systemStore.toast.show"
      class="fixed bottom-12 right-6 bg-slate-900 text-white text-[12.5px] px-3.5 py-2 rounded-xl shadow-lg transition-opacity duration-300 pointer-events-none z-50 flex items-center space-x-2 animate-fade-in"
    >
      <span>✨</span>
      <span>{{ systemStore.toast.message }}</span>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue';
import { useSystemStore } from '../../stores/system';
import { useAgentStore } from '../../stores/agent';
import { useChatStore } from '../../stores/chat';
import { api, initAuthToken } from '../../api/client';

import AgentSidebar from '../sidebar/AgentSidebar.vue';
import ChatHeader from '../chat/ChatHeader.vue';
import ChatMessages from '../chat/ChatMessages.vue';
import FloatingInput from '../chat/FloatingInput.vue';
import StatusBar from '../statusbar/StatusBar.vue';

import SettingsModal from '../modals/SettingsModal.vue';
import RecruitModal from '../modals/RecruitModal.vue';
import HumanGateModal from '../modals/HumanGateModal.vue';
import WatcherModal from '../modals/WatcherModal.vue';
import SchedulerModal from '../modals/SchedulerModal.vue';
import ImageLightboxModal from '../modals/ImageLightboxModal.vue';
import QuotaExhaustedModal from '../modals/QuotaExhaustedModal.vue';
import SkillsHubModal from '../modals/SkillsHubModal.vue';
import WorkflowModal from '../modals/WorkflowModal.vue';
import RunModal from '../modals/RunModal.vue';
import SkillRunnerModal from '../modals/SkillRunnerModal.vue';
import AgentSkillsModal from '../modals/AgentSkillsModal.vue';
import AgentSettingsModal from '../modals/AgentSettingsModal.vue';

const systemStore = useSystemStore();
const agentStore = useAgentStore();
const chatStore = useChatStore();

let watcherPollTimer = null;

onMounted(async () => {
  await initAuthToken();
  chatStore.initStorage();
  await agentStore.fetchAgents();
  await systemStore.fetchSystemInfo();
  await systemStore.fetchQuota();
  await systemStore.fetchWatcherStatus();
  await systemStore.fetchSchedules();
  await systemStore.fetchSuspendedWorkflows();
  systemStore.checkForUpdates(true); // 开机静默后台轮询新补丁

  // 启动通用投递箱事件守护轮询 (每 1.5 秒静默感知新文件拖入与处理进度)
  watcherPollTimer = setInterval(() => {
    systemStore.pollWatcherEvents();
  }, 1500);
});

onUnmounted(() => {
  if (watcherPollTimer) {
    clearInterval(watcherPollTimer);
    watcherPollTimer = null;
  }
});
</script>
