<template>
  <div
    v-if="systemStore.modals.scheduler"
    class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-2xl overflow-hidden animate-scale-up flex flex-col max-h-[85vh]">
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-amber-50/70 shrink-0">
        <div class="flex items-center space-x-2.5">
          <span class="text-xl">⏰</span>
          <div>
            <h3 class="font-bold text-slate-800 text-[15.5px]">定时调度与计划任务中枢 (Scheduler Daemon)</h3>
            <p class="text-[12px] text-amber-700 mt-0.5">每日时刻、固定间隔、倒计时延时与标准 Cron 守护</p>
          </div>
        </div>
        <button
          @click="systemStore.closeModal('scheduler')"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer"
        >
          &times;
        </button>
      </div>

      <!-- 选项卡切换栏 -->
      <div class="px-6 pt-3 border-b border-slate-100 flex space-x-6 bg-slate-50/40 text-[13.5px] font-medium shrink-0">
        <button
          @click="activeTab = 'list'"
          class="pb-2.5 border-b-2 flex items-center space-x-1.5 cursor-pointer"
          :class="activeTab === 'list' ? 'border-amber-600 text-amber-800 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
        >
          <span>📋 计划列表</span>
          <span class="px-2 py-0.2 rounded-full text-[11px] bg-amber-100 text-amber-800 font-mono">
            {{ systemStore.schedules.length }}
          </span>
        </button>
        <button
          @click="activeTab = 'create'"
          class="pb-2.5 border-b-2 flex items-center space-x-1.5 cursor-pointer"
          :class="activeTab === 'create' ? 'border-amber-600 text-amber-800 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
        >
          <span>➕ 新建计划</span>
        </button>
      </div>

      <!-- 主体内容 -->
      <div class="p-6 overflow-y-auto flex-1 space-y-4">
        <!-- 视图 1: 计划列表 -->
        <div v-if="activeTab === 'list'" class="space-y-3">
          <div class="flex items-center justify-between text-[12.5px] text-slate-500 pb-1">
            <span>后台守护线程已就绪 · 到期后在 outputs/ 写入产物</span>
            <button
              @click="systemStore.fetchSchedules"
              class="text-amber-700 hover:underline flex items-center space-x-1 cursor-pointer"
            >
              <span>🔄 刷新列表</span>
            </button>
          </div>

          <div v-if="systemStore.schedules.length === 0" class="p-8 text-center text-slate-400 text-[13px] bg-slate-50 rounded-xl">
            暂无配置定时任务，点击上方“➕ 新建计划”创建
          </div>

          <div
            v-for="task in systemStore.schedules"
            :key="task.task_id || task.id"
            class="p-4 rounded-xl border border-slate-200 bg-white hover:border-amber-300 transition space-y-2 shadow-2xs"
          >
            <div class="flex items-center justify-between">
              <div class="font-bold text-slate-800 text-[14px] flex items-center space-x-2">
                <span>{{ task.name || task.task_id }}</span>
                <span class="text-[11px] px-2 py-0.5 rounded-full font-mono bg-amber-50 text-amber-800 border border-amber-200">
                  {{ task.trigger_type || '定时' }}
                </span>
              </div>
              <button
                @click="deleteTask(task.task_id || task.id)"
                class="text-rose-500 hover:text-rose-700 text-[12px] cursor-pointer"
              >
                🗑️ 删除
              </button>
            </div>
            <div class="text-[12px] text-slate-500 font-mono">
              执行指令: <span class="text-slate-700 font-semibold">{{ task.command }}</span> · 目标智能体: {{ task.agent_name || '默认' }}
            </div>
          </div>
        </div>

        <!-- 视图 2: 新建计划 -->
        <div v-else class="space-y-4">
          <div>
            <label class="block text-[13px] font-semibold text-slate-700 mb-1">计划任务名称</label>
            <input
              type="text"
              v-model="newTask.name"
              placeholder="如 每日晨间系统巡检"
              class="w-full text-[13px] p-2.5 rounded-lg border border-slate-300 focus:border-amber-500 outline-none"
            />
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-[13px] font-semibold text-slate-700 mb-1">执行指令载荷</label>
              <input
                type="text"
                v-model="newTask.command"
                placeholder="如 [EXEC] report"
                class="w-full text-[13px] p-2.5 rounded-lg border border-slate-300 font-mono outline-none focus:border-amber-500"
              />
            </div>
            <div>
              <label class="block text-[13px] font-semibold text-slate-700 mb-1">触发时间 (如 09:00 或 30m)</label>
              <input
                type="text"
                v-model="newTask.timeValue"
                placeholder="09:00"
                class="w-full text-[13px] p-2.5 rounded-lg border border-slate-300 font-mono outline-none focus:border-amber-500"
              />
            </div>
          </div>

          <div class="pt-2 flex justify-end">
            <button
              @click="submitCreateTask"
              class="px-5 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-semibold text-[13px] transition cursor-pointer shadow-xs"
            >
              创建并启动守护 ⏰
            </button>
          </div>
        </div>
      </div>

      <div class="px-6 py-4 bg-slate-50/70 border-t border-slate-100 flex justify-end">
        <button
          @click="systemStore.closeModal('scheduler')"
          class="px-4.5 py-2 text-[13px] text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-lg transition font-medium cursor-pointer"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useSystemStore } from '../../stores/system';
import { api } from '../../api/client';

const systemStore = useSystemStore();
const activeTab = ref('list');

const newTask = ref({
  name: '每日系统健康审计',
  command: '[EXEC] report',
  timeValue: '09:00'
});

onMounted(() => {
  systemStore.fetchSchedules();
});

async function deleteTask(taskId) {
  if (!confirm('确认删除该计划任务吗？')) return;
  try {
    await api.deleteSchedule(taskId);
    await systemStore.fetchSchedules();
    systemStore.showToast('任务已删除');
  } catch (err) {
    alert('删除失败: ' + err.message);
  }
}

async function submitCreateTask() {
  if (!newTask.value.name || !newTask.value.command) {
    alert('请填写完整任务信息');
    return;
  }
  try {
    await api.createSchedule({
      name: newTask.value.name,
      command: newTask.value.command,
      trigger_type: 'daily',
      time_val: newTask.value.timeValue
    });
    await systemStore.fetchSchedules();
    activeTab.value = 'list';
    systemStore.showToast('计划任务已成功创建！');
  } catch (err) {
    alert('创建任务失败: ' + err.message);
  }
}
</script>
