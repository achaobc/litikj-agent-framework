<template>
  <div
    v-if="systemStore.modals.watcher"
    class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-lg overflow-hidden animate-scale-up">
      <div class="px-6 py-4.5 border-b border-slate-100 flex items-center justify-between bg-emerald-50/60">
        <div class="flex items-center space-x-2">
          <span class="text-xl">📁</span>
          <h3 class="font-bold text-slate-800 text-[15px]">投递箱监听守护中枢 (Watcher Daemon)</h3>
        </div>
        <button
          @click="systemStore.closeModal('watcher')"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer"
        >
          &times;
        </button>
      </div>

      <div class="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
        <div class="p-3.5 rounded-xl border border-emerald-200 bg-emerald-50/50 space-y-1.5">
          <div class="flex items-center justify-between text-[13px]">
            <span class="font-semibold text-emerald-900">守护引擎状态</span>
            <span class="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800">
              {{ systemStore.watcherStatus?.is_running ? '监听中 🟢' : '已就绪' }}
            </span>
          </div>
          <p class="text-[12px] text-emerald-700 leading-relaxed">
            无需打开软件，录制好视频后只需拖入指定文件夹，微内核在 2.0 秒写入防抖后自动触发全链路闭环！
          </p>
        </div>

        <div>
          <h4 class="text-[13px] font-semibold text-slate-700 mb-2">当前挂载的投递规则清单</h4>
          <div v-if="rules.length === 0" class="text-[12px] text-slate-400 p-3 bg-slate-50 rounded-xl text-center">
            暂无挂载规则
          </div>
          <div v-else class="space-y-2">
            <div
              v-for="(rule, idx) in rules"
              :key="idx"
              class="p-3 bg-slate-50 rounded-xl border border-slate-200 text-[12.5px] space-y-1"
            >
              <div class="font-semibold text-slate-800 flex items-center justify-between">
                <span>{{ rule.name || rule.rule_id }}</span>
                <span class="text-[11px] font-mono text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
                  {{ rule.match_pattern || '*.*' }}
                </span>
              </div>
              <div class="text-[11.5px] text-slate-500 font-mono flex items-center justify-between">
                <span class="truncate">监听路径: {{ rule.watch_dir }}</span>
                <button
                  @click="openDir(rule.watch_dir)"
                  class="text-[11px] text-emerald-600 hover:text-emerald-800 font-sans font-medium px-2 py-0.5 bg-emerald-50 hover:bg-emerald-100 rounded transition cursor-pointer shrink-0 ml-2"
                >
                  打开文件夹 📂
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="p-3 bg-slate-50 rounded-xl border border-slate-100 space-y-1 text-[12px] text-slate-500 font-mono">
          <div>• 轮询扫描周期: 2.0s</div>
          <div>• 写入防抖稳定时间: 2.0s (防止大视频传输中途被误读)</div>
          <div>• 状态指纹防重放: 已启用 (重启不重复触发)</div>
        </div>
      </div>

      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end">
        <button
          @click="systemStore.closeModal('watcher')"
          class="px-4.5 py-2 text-[13px] text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-lg transition font-medium cursor-pointer"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue';
import { useSystemStore } from '../../stores/system';
import { api } from '../../api/client';

const systemStore = useSystemStore();

onMounted(() => {
  systemStore.fetchWatcherStatus();
});

const rules = computed(() => {
  return systemStore.watcherStatus?.rules || [];
});

const openDir = (dir) => {
  if (dir) {
    api.openPath(dir, 'open_dir');
  }
};
</script>
