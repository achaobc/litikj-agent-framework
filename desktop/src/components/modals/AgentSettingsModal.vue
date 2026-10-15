<template>
  <div
    v-if="systemStore.modals.agentSettings"
    class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-xl max-h-[85vh] overflow-hidden animate-scale-up flex flex-col">
      <!-- 弹窗顶栏 -->
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-amber-50/70 via-indigo-50/50 to-purple-50/50 shrink-0">
        <div class="flex items-center space-x-3 min-w-0">
          <span class="text-2xl p-1.5 bg-white rounded-xl border border-amber-100 shadow-2xs shrink-0">
            {{ agentStore.currentAgent?.icon || '⚙️' }}
          </span>
          <div class="min-w-0">
            <div class="flex items-center space-x-2">
              <h3 class="font-bold text-slate-800 text-[15.5px] truncate">
                {{ agentDisplayName }} · 智能体预置状态与配置
              </h3>
              <span class="text-[11px] font-mono px-2 py-0.2 rounded-full bg-amber-100 text-amber-800 font-semibold shrink-0">
                通用标准面板
              </span>
            </div>
            <p class="text-[11.5px] text-slate-500 mt-0.5 truncate">
              动态绑定出片模式、发布档期、矩阵账号与视觉风格 · 即时落盘
            </p>
          </div>
        </div>
        <button
          @click="closeModal"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer shrink-0 ml-2"
        >
          &times;
        </button>
      </div>

      <!-- 快捷提示横幅 -->
      <div class="px-6 py-2 bg-slate-50 border-b border-slate-100 flex items-center justify-between text-[11.5px] text-slate-600 shrink-0">
        <div class="flex items-center space-x-1.5">
          <span>💡</span>
          <span>修改后将即时同步至本地工作区与运行时，下次任务与出片自动生效。</span>
        </div>
      </div>

      <!-- 加载中状态 -->
      <div v-if="loading" class="p-12 flex flex-col items-center justify-center space-y-3 text-slate-400">
        <span class="animate-spin text-2xl">⏳</span>
        <span class="text-[13px]">正在读取智能体预置配置契约...</span>
      </div>

      <!-- 表单主体 -->
      <div v-else class="p-6 overflow-y-auto space-y-5 flex-1">
        <!-- 错误提示 -->
        <div v-if="loadError" class="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 text-[12px] flex items-center space-x-2">
          <span>⚠️</span>
          <span>{{ loadError }}</span>
        </div>

        <!-- 动态 Schema 渲染表单 -->
        <div v-if="schema && schema.properties" class="space-y-4">
          <div
            v-for="(prop, key) in schema.properties"
            :key="key"
            class="space-y-1.5 pb-3 border-b border-slate-100 last:border-b-0"
          >
            <!-- 字段标头 -->
            <div class="flex items-center justify-between">
              <label class="text-[13px] font-semibold text-slate-800 flex items-center space-x-1.5">
                <span>{{ prop.title || key }}</span>
                <span v-if="prop.description" class="text-[11px] text-slate-400 font-normal">({{ prop.description }})</span>
              </label>
              <span class="text-[10px] font-mono text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">{{ key }}</span>
            </div>

            <!-- 控件类型 1: 下拉单选 (带 enum) -->
            <div v-if="prop.enum" class="relative">
              <select
                v-model="formData[key]"
                class="w-full px-3.5 py-2 bg-slate-50/80 hover:bg-slate-100/70 border border-slate-200 rounded-xl text-[13px] text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 transition cursor-pointer"
              >
                <option
                  v-for="(val, idx) in prop.enum"
                  :key="val"
                  :value="val"
                >
                  {{ (prop.enumNames && prop.enumNames[idx]) ? prop.enumNames[idx] : val }}
                </option>
              </select>
            </div>

            <!-- 控件类型 2: 发布时间 (含有时间标识) -->
            <div v-else-if="key === 'publish_time' || (prop.title && prop.title.includes('时间'))" class="space-y-1.5">
              <div class="flex items-center space-x-2">
                <input
                  type="time"
                  v-model="formData[key]"
                  class="px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-[13px] text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 w-36 font-mono"
                />
                <!-- 快捷黄金时段药丸按钮 -->
                <div class="flex items-center space-x-1.5">
                  <span class="text-[11px] text-slate-400">推荐档期：</span>
                  <button
                    type="button"
                    @click="formData[key] = '19:30'"
                    class="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-[11px] text-slate-600 font-mono transition cursor-pointer"
                  >
                    19:30
                  </button>
                  <button
                    type="button"
                    @click="formData[key] = '20:00'"
                    class="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-[11px] text-slate-600 font-mono transition cursor-pointer"
                  >
                    20:00
                  </button>
                  <button
                    type="button"
                    @click="formData[key] = '21:00'"
                    class="px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-[11px] text-slate-600 font-mono transition cursor-pointer"
                  >
                    21:00
                  </button>
                </div>
              </div>
            </div>

            <!-- 控件类型 3: 开关 (boolean) -->
            <div v-else-if="prop.type === 'boolean'" class="flex items-center space-x-3 pt-1">
              <input
                type="checkbox"
                v-model="formData[key]"
                class="w-4 h-4 text-indigo-600 rounded border-slate-300 focus:ring-indigo-500 cursor-pointer"
              />
              <span class="text-[12.5px] text-slate-600">{{ formData[key] ? '已开启' : '已关闭' }}</span>
            </div>

            <!-- 控件类型 4: 普通文本输入框 -->
            <div v-else>
              <input
                type="text"
                v-model="formData[key]"
                :placeholder="prop.default ? String(prop.default) : '请输入配置值...'"
                class="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-[13px] text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 transition"
              />
            </div>
          </div>
        </div>

        <!-- 空 Schema 时的备选 JSON 编辑 -->
        <div v-else class="text-center py-6 text-slate-400 text-[13px]">
          当前智能体尚未声明可配置属性。
        </div>
      </div>

      <!-- 弹窗底栏 -->
      <div class="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-between shrink-0">
        <button
          type="button"
          @click="resetToDefaults"
          class="text-slate-500 hover:text-slate-700 text-[12.5px] font-medium hover:underline cursor-pointer"
        >
          恢复出厂默认值
        </button>
        <div class="flex items-center space-x-2.5">
          <button
            type="button"
            @click="closeModal"
            class="px-4 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-100 text-slate-600 text-[13px] font-medium transition cursor-pointer"
          >
            取消
          </button>
          <button
            type="button"
            :disabled="saving"
            @click="saveConfig"
            class="px-5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white text-[13px] font-medium shadow-xs transition flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
          >
            <span v-if="saving" class="animate-spin text-xs">⏳</span>
            <span>{{ saving ? '正在保存...' : '保存并应用' }}</span>
          </button>
        </div>
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

const loading = ref(false);
const saving = ref(false);
const loadError = ref('');
const schema = ref(null);
const formData = ref({});

const currentAgentName = computed(() => {
  return agentStore.currentAgent?.name || 'omni_sentinel';
});

const agentDisplayName = computed(() => {
  return agentStore.currentAgent?.display_name || agentStore.currentAgent?.name || '当前智能体';
});

// 打开弹窗时自动拉取配置
watch(
  () => systemStore.modals.agentSettings,
  async (isOpen) => {
    if (isOpen) {
      await fetchConfig();
    }
  }
);

async function fetchConfig() {
  loading.value = true;
  loadError.value = '';
  try {
    const res = await api.getAgentConfig(currentAgentName.value);
    if (res && res.success) {
      schema.value = res.schema || {};
      const current = res.config || {};
      
      // 初始化表单数据
      const initial = { ...current };
      if (schema.value.properties) {
        for (const [k, prop] of Object.entries(schema.value.properties)) {
          if (initial[k] === undefined && prop.default !== undefined) {
            initial[k] = prop.default;
          }
        }
      }
      formData.value = initial;
    } else {
      loadError.value = res?.error || '获取智能体配置失败';
    }
  } catch (err) {
    loadError.value = err.message || '网络连接或接口异常';
  } finally {
    loading.value = false;
  }
}

function resetToDefaults() {
  if (schema.value && schema.value.properties) {
    for (const [k, prop] of Object.entries(schema.value.properties)) {
      if (prop.default !== undefined) {
        formData.value[k] = prop.default;
      }
    }
  }
}

async function saveConfig() {
  saving.value = true;
  try {
    const res = await api.updateAgentConfig(currentAgentName.value, formData.value);
    if (res && res.success) {
      systemStore.showToast(`✅ 【${agentDisplayName.value}】配置已成功更新并生效！`);
      
      // 在对话流中回显轻量提示 (增加可选链与异常隔离保护，防止未激活会话时误报保存异常)
      try {
        if (chatStore?.currentSession) {
          const changesSummary = Object.entries(formData.value)
            .map(([k, v]) => `${k}=${v}`)
            .slice(0, 3)
            .join(', ');
          const echoMsg = {
            role: 'system',
            content: `⚙️ **[设置面板同步]** 智能体配置已更新：\`${changesSummary}\``
          };
          if (typeof chatStore?.addMessage === 'function') {
            chatStore.addMessage(echoMsg);
          } else if (typeof chatStore?.appendSystemEventMessage === 'function') {
            chatStore.appendSystemEventMessage(currentAgentName.value, echoMsg.content);
          } else {
            chatStore?.addMessage?.(echoMsg);
          }
        }
      } catch {
        // 对话回显属于非关键增强体验，静默容错，避免阻断已成功的配置保存
      }
      
      closeModal();
    } else {
      alert(`保存失败: ${res?.error || '未知错误'}`);
    }
  } catch (err) {
    alert(`保存异常: ${err.message}`);
  } finally {
    saving.value = false;
  }
}

function closeModal() {
  systemStore.closeModal('agentSettings');
}
</script>
