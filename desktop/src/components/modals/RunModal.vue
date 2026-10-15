<template>
  <div
    v-if="systemStore.modals.runModal"
    class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-lg overflow-hidden animate-scale-up flex flex-col">
      <!-- 模态顶栏 -->
      <div class="px-6 py-4.5 border-b border-slate-100 flex items-center justify-between bg-slate-50/70 shrink-0">
        <div class="flex items-center space-x-2">
          <span class="text-xl">⚡</span>
          <h3 class="font-bold text-slate-800 text-[15px]">智能体单任务调度与仿真</h3>
        </div>
        <button
          @click="systemStore.closeModal('runModal')"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer"
        >
          &times;
        </button>
      </div>

      <div class="p-6 space-y-4 overflow-y-auto">
        <!-- 目标智能体选择 -->
        <div>
          <label class="block text-[13px] font-semibold text-slate-700 mb-1">目标执行智能体 (Agent)</label>
          <select
            v-model="selectedAgent"
            class="w-full text-[13px] p-2.5 rounded-xl border border-slate-300 outline-none bg-white font-medium text-slate-700 focus:border-sky-500 focus:ring-1 focus:ring-sky-200"
          >
            <option
              v-for="ag in agentStore.agents"
              :key="ag.name"
              :value="ag.name"
            >
              {{ ag.icon || '🤖' }} {{ ag.display_name || ag.name }} ({{ ag.category || '岗位' }})
            </option>
          </select>
        </div>

        <!-- 任务主题 -->
        <div>
          <label class="block text-[13px] font-semibold text-slate-700 mb-1">任务主题 / 命题名称 (Topic)</label>
          <input
            type="text"
            v-model="topic"
            placeholder="例如: 哨兵系统底座健康巡检与全链路测试"
            class="w-full text-[13px] p-2.5 rounded-xl border border-slate-300 focus:border-sky-500 focus:ring-1 focus:ring-sky-200 outline-none"
          />
        </div>

        <!-- 快捷指令预设胶囊 -->
        <div v-if="currentAgentActions.length > 0" class="flex items-center space-x-2 text-[12px] text-slate-500">
          <span class="shrink-0">快捷动作:</span>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="(act, aIdx) in currentAgentActions"
              :key="aIdx"
              type="button"
              @click="topic = act.command || act.label"
              class="px-2 py-0.5 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-700 font-mono text-[11px] cursor-pointer transition"
            >
              {{ act.icon || '⚡' }} {{ act.label || act.command }}
            </button>
          </div>
        </div>

        <!-- 本地挂载文件路径 -->
        <div>
          <label class="block text-[13px] font-semibold text-slate-700 mb-1">本地挂载文件路径 (File Path, 可选)</label>
          <input
            type="text"
            v-model="filePath"
            placeholder="留空则自动使用沙箱默认虚拟数据进行全流程仿真"
            class="w-full text-[12.5px] p-2.5 rounded-xl border border-slate-300 focus:border-sky-500 focus:ring-1 focus:ring-sky-200 outline-none font-mono"
          />
        </div>

        <!-- 仿真策略配置面板 -->
        <div class="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2.5">
          <label class="flex items-center space-x-2 text-[13px] text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              v-model="dryRun"
              class="rounded text-sky-600 focus:ring-sky-500 w-4 h-4"
            />
            <span class="font-semibold">开启 Dry-Run 仿真测试模式 (推荐)</span>
          </label>
          <p class="text-[11.5px] text-slate-500 pl-6 leading-normal">
            执行前置安全门禁审查与策略演算，不向外部公域正式提交真实载荷。
          </p>

          <label class="flex items-center space-x-2 text-[13px] text-slate-700 cursor-pointer pt-1">
            <input
              type="checkbox"
              v-model="onlySelf"
              class="rounded text-sky-600 focus:ring-sky-500 w-4 h-4"
            />
            <span>强制开启【仅自己可见】(is_only_self 保护锁)</span>
          </label>
        </div>
      </div>

      <!-- 弹窗底栏 -->
      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end space-x-2.5 shrink-0">
        <button
          @click="systemStore.closeModal('runModal')"
          class="px-4 py-2 text-[13px] text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-lg transition font-medium cursor-pointer"
        >
          取消
        </button>
        <button
          @click="submitRun"
          :disabled="submitting || !selectedAgent"
          class="px-5 py-2 text-[13px] text-white bg-sky-600 hover:bg-sky-700 rounded-lg transition font-semibold flex items-center space-x-1.5 shadow-xs cursor-pointer disabled:opacity-50"
        >
          <span>{{ submitting ? '调度执行中...' : '立即调度执行' }}</span>
          <span>⚡</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { useSystemStore } from '../../stores/system';
import { useAgentStore } from '../../stores/agent';
import { useChatStore } from '../../stores/chat';
import { api } from '../../api/client';

const systemStore = useSystemStore();
const agentStore = useAgentStore();
const chatStore = useChatStore();

const selectedAgent = ref('');
const topic = ref('系统底座健康度诊断');
const filePath = ref('');
const dryRun = ref(true);
const onlySelf = ref(false);
const submitting = ref(false);

watch(
  () => systemStore.modals.runModal,
  (open) => {
    if (open) {
      selectedAgent.value = agentStore.currentAgent?.name || (agentStore.agents[0]?.name ?? '');
      topic.value = '系统底座健康度综合诊断与策略仿真';
    }
  }
);

const currentAgentActions = computed(() => {
  const ag = agentStore.agents.find(a => a.name === selectedAgent.value);
  return ag?.actions || [];
});

async function submitRun() {
  if (!selectedAgent.value) return;
  submitting.value = true;
  const currentAgentName = selectedAgent.value;
  const currentTopic = topic.value.trim() || '系统底座任务调度执行';

  try {
    // 1. 关闭弹窗
    systemStore.closeModal('runModal');

    // 2. 插入用户触发记录
    if (!chatStore.conversations[currentAgentName]) {
      chatStore.conversations[currentAgentName] = [];
    }
    chatStore.conversations[currentAgentName].push({
      role: 'user',
      content: `⚡ **提交单任务调度执行**\n• **目标岗位**: \`${currentAgentName}\`\n• **任务主题**: ${currentTopic}\n• **仿真模式**: ${dryRun.value ? '🟢 Dry-Run 开启' : '🔴 真实提交'}${filePath.value ? `\n• **挂载路径**: \`${filePath.value}\`` : ''}`,
      time: new Date().toLocaleTimeString()
    });
    chatStore.saveStorage();

    // 3. 调用底座微内核任务分发
    const res = await api.runAgentTask({
      agent_name: currentAgentName,
      payload: {
        topic: currentTopic,
        video_path: filePath.value.trim(),
        file_path: filePath.value.trim(),
        dry_run: dryRun.value,
        is_only_self: onlySelf.value
      }
    });

    // 4. 组装格式化执行报告 Markdown
    let replyMarkdown = `### 🚀 任务调度执行报告\n\n`;
    replyMarkdown += `* **执行状态**: ${res.success ? '✅ 执行完成 (Completed)' : '❌ 执行受阻 (Blocked)'}\n`;
    replyMarkdown += `* **微内核反馈**: ${res.message || '调度闭环完成'}\n\n`;

    if (res.guard_reports && res.guard_reports.length > 0) {
      replyMarkdown += `#### 🛡️ 前置商业门禁审查摘要\n`;
      res.guard_reports.forEach(gr => {
        const errorInfo = gr.errors && gr.errors.length ? gr.errors.join('; ') : '无告警';
        replyMarkdown += `- **${gr.name}**: ${gr.passed ? '✅ 通过' : '❌ 拦截'} (${errorInfo})\n`;
      });
      replyMarkdown += `\n`;
    }

    if (res.data) {
      replyMarkdown += `#### 📦 任务产出载荷数据\n\`\`\`json\n${JSON.stringify(res.data, null, 2)}\n\`\`\`\n`;
    }

    // 5. 插入助理回复
    chatStore.conversations[currentAgentName].push({
      role: 'assistant',
      content: replyMarkdown,
      time: new Date().toLocaleTimeString()
    });
    chatStore.saveStorage();
    systemStore.showToast(`任务【${currentTopic}】执行完成`);
  } catch (err) {
    chatStore.conversations[currentAgentName].push({
      role: 'assistant',
      content: `❌ **任务调度异常**: ${err.message || '底层分发失败'}`,
      time: new Date().toLocaleTimeString()
    });
    chatStore.saveStorage();
    alert('任务调度执行失败: ' + err.message);
  } finally {
    submitting.value = false;
  }
}
</script>
