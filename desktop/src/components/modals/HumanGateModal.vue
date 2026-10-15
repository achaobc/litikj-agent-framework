<template>
  <div
    v-if="systemStore.modals.humanGate && systemStore.currentGateData"
    class="fixed inset-0 bg-slate-900/50 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-xl overflow-hidden animate-scale-up">
      <div class="px-6 py-4.5 border-b border-slate-100 flex items-center justify-between bg-amber-50/70">
        <div class="flex items-center space-x-2.5">
          <span class="text-xl">⏸️</span>
          <div>
            <h3 class="font-bold text-slate-800 text-[15px]">人机协同审批断点 (Human Gate)</h3>
            <p class="text-[11.5px] text-amber-700 font-mono mt-0.5">
              ID: {{ systemStore.currentGateData.workflow_id }}
            </p>
          </div>
        </div>
        <button
          @click="systemStore.closeModal('humanGate')"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer"
        >
          &times;
        </button>
      </div>

      <div class="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
        <div class="p-3.5 rounded-xl border border-amber-200/80 bg-amber-50/50 text-[13px] text-slate-700 space-y-1">
          <div class="font-semibold text-amber-900 flex items-center space-x-1.5">
            <span>🎯</span>
            <span>{{ gateInfo.gate_name || '任务断点决策' }}</span>
          </div>
          <p class="text-slate-600 leading-relaxed text-[12.5px]">
            {{ gateInfo.description || '流水线已到达人机审批断点，请审定并决策后续闭环：' }}
          </p>
        </div>

        <!-- 候选选项列表 -->
        <div v-if="gateInfo.options && gateInfo.options.length > 0">
          <label class="block text-[13px] font-semibold text-slate-700 mb-2">候选推荐方案 (点击选中)</label>
          <div class="space-y-2">
            <div
              v-for="(opt, idx) in gateInfo.options"
              :key="idx"
              @click="selectedChoice = opt.title || opt"
              class="p-3 rounded-xl border cursor-pointer transition text-[13px]"
              :class="selectedChoice === (opt.title || opt)
                ? 'border-amber-500 bg-amber-50/60 font-semibold text-amber-900'
                : 'border-slate-200 hover:border-slate-300 bg-white text-slate-700'"
            >
              {{ opt.title || opt }}
            </div>
          </div>
        </div>

        <div>
          <label class="block text-[12.5px] font-medium text-slate-600 mb-1">自定义补充方案 (可选)</label>
          <input
            type="text"
            v-model="customChoice"
            placeholder="在此输入自定义主题覆盖备选项..."
            class="w-full text-[13px] p-2.5 rounded-xl border border-slate-300 focus:border-amber-500 outline-none"
          />
        </div>
      </div>

      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
        <span class="text-[12px] text-slate-400 font-mono">断点挂起待决</span>
        <div class="flex space-x-2.5">
          <button
            @click="systemStore.closeModal('humanGate')"
            class="px-4 py-2 text-[13px] text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-lg transition font-medium cursor-pointer"
          >
            稍后决策
          </button>
          <button
            @click="submitResume"
            :disabled="resuming"
            class="px-5 py-2 text-[13px] text-white bg-amber-600 hover:bg-amber-700 active:bg-amber-800 rounded-lg transition font-semibold shadow-xs flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
          >
            <span>{{ resuming ? '提交中...' : '确认采纳并推进闭环 🚀' }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { useSystemStore } from '../../stores/system';
import { api } from '../../api/client';

const systemStore = useSystemStore();
const selectedChoice = ref('');
const customChoice = ref('');
const resuming = ref(false);

const gateInfo = computed(() => {
  return systemStore.currentGateData?.gate_info || {};
});

async function submitResume() {
  const choice = customChoice.value.trim() || selectedChoice.value;
  if (!choice) {
    alert('请选择或输入决策方案');
    return;
  }
  resuming.value = true;
  try {
    await api.resumeHumanGate(systemStore.currentGateData.workflow_id, choice, customChoice.value.trim());
    systemStore.showToast('已确认采纳，流水线继续推进！');
    systemStore.closeModal('humanGate');
    await systemStore.fetchSuspendedWorkflows();
  } catch (err) {
    alert('推进断点失败: ' + err.message);
  } finally {
    resuming.value = false;
  }
}
</script>
