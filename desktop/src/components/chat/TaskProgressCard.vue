<template>
  <div
    v-if="task"
    class="w-full my-3 p-4.5 rounded-2xl border border-sky-200/80 bg-gradient-to-b from-sky-50/50 to-white shadow-xs select-none transition-all duration-300"
  >
    <!-- 卡片顶栏 -->
    <div class="flex items-center justify-between pb-3 border-b border-sky-100">
      <div class="flex items-center space-x-2.5 min-w-0">
        <div class="w-8 h-8 rounded-xl bg-sky-100 border border-sky-200 flex items-center justify-center text-lg shrink-0">
          ⚡
        </div>
        <div class="min-w-0">
          <div class="flex items-center space-x-2">
            <h4 class="font-bold text-slate-800 text-[14px] truncate tracking-tight">
              {{ task.title || '自动化流水线正在执行' }}
            </h4>
            <span
              class="text-[10.5px] px-2 py-0.5 rounded-full font-mono font-medium shrink-0"
              :class="statusBadgeClass"
            >
              {{ statusText }}
            </span>
          </div>
          <p class="text-[11.5px] text-slate-500 mt-0.5 truncate font-mono">
            阶段: {{ task.current_step || '初始化中...' }}
          </p>
        </div>
      </div>

      <!-- 耗时与关闭按钮 -->
      <div class="flex items-center space-x-2.5 shrink-0">
        <span v-if="task.total_elapsed" class="text-[11px] text-slate-400 font-mono">
          总耗时 {{ task.total_elapsed }}s
        </span>
        <button
          @click="closeTask"
          class="w-6 h-6 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 flex items-center justify-center transition cursor-pointer text-xs"
          title="关闭面板"
        >
          ✕
        </button>
      </div>
    </div>

    <!-- 动态进度条 -->
    <div class="w-full bg-slate-100 h-1.5 rounded-full mt-3 overflow-hidden">
      <div
        class="h-full bg-gradient-to-r from-sky-500 to-indigo-500 rounded-full transition-all duration-500"
        :style="{ width: progressPercent + '%' }"
      ></div>
    </div>

    <!-- 步骤阶梯器 (Steps Stepper) -->
    <div class="mt-4 space-y-2">
      <div
        v-for="(st, idx) in task.steps"
        :key="idx"
        class="flex items-center justify-between p-2 rounded-xl text-[12.5px] transition-all"
        :class="st.status === 'running' ? 'bg-sky-50/80 border border-sky-200/60 font-medium text-sky-900' : 'text-slate-600 hover:bg-slate-50'"
      >
        <div class="flex items-center space-x-2.5 min-w-0">
          <!-- 步骤状态图标 -->
          <div class="w-5 h-5 rounded-full flex items-center justify-center shrink-0">
            <span v-if="st.status === 'completed'" class="text-emerald-500 font-bold text-sm">✔</span>
            <span v-else-if="st.status === 'running'" class="inline-block w-3.5 h-3.5 border-2 border-sky-500 border-t-transparent rounded-full animate-spin"></span>
            <span v-else-if="st.status === 'failed'" class="text-rose-500 font-bold text-sm">✘</span>
            <span v-else class="w-2 h-2 rounded-full bg-slate-300"></span>
          </div>
          <span class="truncate">{{ st.name }}</span>
        </div>

        <!-- 步骤耗时/状态备注 -->
        <div class="text-[11px] font-mono shrink-0">
          <span v-if="st.status === 'completed'" class="text-emerald-600">
            耗时 {{ st.elapsed || '0.1' }}s
          </span>
          <span v-else-if="st.status === 'running'" class="text-sky-600 font-medium animate-pulse">
            处理中...
          </span>
          <span v-else-if="st.status === 'failed'" class="text-rose-600">
            失败: {{ st.error || '中断' }}
          </span>
          <span v-else class="text-slate-400">
            等待中
          </span>
        </div>
      </div>
    </div>

    <!-- 控制台控制与折叠终端日志 -->
    <div class="mt-3.5 pt-2.5 border-t border-slate-100">
      <button
        @click="showLogs = !showLogs"
        class="text-[11.5px] text-slate-500 hover:text-sky-600 flex items-center space-x-1.5 transition select-none cursor-pointer"
      >
        <span>{{ showLogs ? '▼ 收起控制台底层输出' : '▶ 展开实时控制台日志 (Console Logs)' }}</span>
        <span v-if="task.logs?.length" class="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.2 rounded-full font-mono">
          {{ task.logs.length }} 行
        </span>
      </button>

      <!-- 黑色微终端视窗 -->
      <div
        v-if="showLogs"
        ref="logTerminal"
        class="mt-2.5 p-3 rounded-xl bg-slate-900 text-slate-200 font-mono text-[11px] leading-relaxed max-h-48 overflow-y-auto select-text shadow-inner scroll-smooth"
      >
        <div v-if="!task.logs || task.logs.length === 0" class="text-slate-500 italic">
          [终端就绪] 等待任务工序标准输出...
        </div>
        <div
          v-for="(log, lIdx) in task.logs"
          :key="lIdx"
          class="flex items-start space-x-2 py-0.5"
        >
          <span class="text-slate-500 shrink-0">[{{ log.time }}]</span>
          <span
            :class="{
              'text-rose-400 font-bold': log.level === 'WARN' || log.level === 'ERROR',
              'text-sky-300': log.level === 'INFO',
              'text-slate-300': !log.level
            }"
            class="break-all"
          >
            {{ log.message }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue';
import { useSystemStore } from '../../stores/system';

const systemStore = useSystemStore();

const closeTask = () => {
  systemStore.activeTask = null;
};

const props = defineProps({
  task: {
    type: Object,
    default: null
  }
});

const showLogs = ref(false);
const logTerminal = ref(null);

const statusText = computed(() => {
  if (!props.task) return '';
  if (props.task.status === 'completed') return '已完成';
  if (props.task.status === 'failed') return '执行失败';
  return '运行中';
});

const statusBadgeClass = computed(() => {
  if (!props.task) return '';
  if (props.task.status === 'completed') return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
  if (props.task.status === 'failed') return 'bg-rose-50 text-rose-700 border border-rose-200';
  return 'bg-sky-50 text-sky-700 border border-sky-200 animate-pulse';
});

const progressPercent = computed(() => {
  if (!props.task || !props.task.steps || props.task.steps.length === 0) return 20;
  if (props.task.status === 'completed') return 100;
  const completedCount = props.task.steps.filter(s => s.status === 'completed').length;
  const total = props.task.steps.length;
  const base = Math.round((completedCount / total) * 100);
  // 若有正在执行的步骤，微加 10%
  const running = props.task.steps.some(s => s.status === 'running');
  return Math.min(95, Math.max(15, base + (running ? 15 : 0)));
});

// 监听日志追加自动滚屏
watch(() => props.task?.logs?.length, () => {
  if (showLogs.value && logTerminal.value) {
    nextTick(() => {
      logTerminal.value.scrollTop = logTerminal.value.scrollHeight;
    });
  }
});
</script>
