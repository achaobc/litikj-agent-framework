<template>
  <div
    v-if="systemStore.modals.skillRunner"
    class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-lg max-h-[90vh] overflow-hidden animate-scale-up flex flex-col">
      <!-- 弹窗顶栏 -->
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-emerald-50/70 shrink-0">
        <div class="flex items-center space-x-2.5 min-w-0">
          <span class="text-2xl p-1 bg-white rounded-lg border border-emerald-100 shadow-2xs shrink-0">
            {{ currentSkill?.icon || '▶️' }}
          </span>
          <div class="min-w-0">
            <div class="flex items-center space-x-2">
              <h3 class="font-bold text-slate-800 text-[15.5px] truncate">
                {{ currentSkill?.display_name || currentSkill?.name || '技能独立运行控制台' }}
              </h3>
              <span class="text-[11px] font-mono px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 shrink-0">
                {{ skillOriginBadge }}
              </span>
            </div>
            <p class="text-[11.5px] text-slate-500 mt-0.5 truncate">
              {{ currentSkill?.description || '免对话直接调用底层确定性执行逻辑' }}
            </p>
          </div>
        </div>
        <button
          @click="systemStore.closeModal('skillRunner')"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer shrink-0 ml-2"
        >
          &times;
        </button>
      </div>

      <div class="p-6 overflow-y-auto space-y-4 flex-1">
        <!-- 动态参数配置容器 -->
        <div>
          <div class="text-[12px] font-semibold text-slate-700 mb-2 flex items-center space-x-1.5">
            <span>📝</span>
            <span>输入参数配置 (Inputs):</span>
          </div>

          <!-- 当有定制 inputs 声明时 -->
          <div v-if="skillInputs.length > 0" class="space-y-3 p-3.5 rounded-xl bg-slate-50 border border-slate-200/90 text-[13px]">
            <div
              v-for="input in skillInputs"
              :key="input.name"
            >
              <label class="block text-[12px] font-semibold text-slate-700 mb-1">
                <span>{{ input.name }}</span>
                <span class="text-[11px] font-normal text-slate-400 ml-1">({{ input.desc || '参数说明' }})</span>
              </label>
              <textarea
                v-if="input.isTextarea"
                v-model="formParams[input.name]"
                rows="3"
                :placeholder="input.placeholder || '每行一条或用换行分隔...'"
                class="w-full text-[12.5px] p-2 rounded-lg border border-slate-300 outline-none resize-none font-sans leading-relaxed focus:border-emerald-500 bg-white"
              ></textarea>
              <input
                v-else
                type="text"
                v-model="formParams[input.name]"
                :placeholder="input.placeholder || '请输入参数...'"
                class="w-full text-[13px] p-2 rounded-lg border border-slate-300 outline-none focus:border-emerald-500 bg-white font-sans"
              />
            </div>
          </div>

          <!-- 无特殊参数时默认提示 -->
          <div v-else class="text-center py-6 px-4 bg-slate-50 rounded-xl border border-slate-200/80 space-y-1">
            <span class="text-2xl">⚡</span>
            <div class="text-[13px] font-medium text-slate-700">该技能无需特殊输入参数</div>
            <div class="text-[11.5px] text-slate-400">点击下方「🚀 立即执行」将直接调用底层原生业务脚本并生成产物。</div>
          </div>
        </div>

        <!-- 执行结果与产物卡片 -->
        <div v-if="executionResult" class="space-y-2 pt-2 border-t border-slate-100">
          <div class="text-[12px] font-semibold text-slate-700 flex items-center justify-between">
            <span class="flex items-center space-x-1.5" :class="executionResult.success ? 'text-emerald-700' : 'text-rose-700'">
              <span>{{ executionResult.success ? '✨' : '❌' }}</span>
              <span>执行产物与反馈:</span>
            </span>
            <span class="text-[11px] font-mono text-slate-400">耗时: {{ executionElapsed }}ms</span>
          </div>

          <!-- JSON 结果展示 -->
          <div class="p-3.5 rounded-xl bg-slate-900 text-slate-100 text-[12px] font-mono overflow-x-auto max-h-48 leading-relaxed">
            <pre class="m-0"><code>{{ JSON.stringify(executionResult.result || executionResult, null, 2) }}</code></pre>
          </div>

          <!-- 成果文件快捷操作栏 -->
          <div
            v-if="artifactFilePath"
            class="flex items-center justify-between p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-[12px] text-emerald-800"
          >
            <div class="flex items-center space-x-2 truncate pr-2">
              <span>🖼️</span>
              <span class="truncate font-mono">{{ artifactFileName }}</span>
            </div>
            <div class="flex space-x-2 shrink-0">
              <button
                @click="api.openPath(artifactFilePath, 'open_file')"
                class="px-2.5 py-1 bg-white hover:bg-emerald-100 border border-emerald-300 rounded text-emerald-900 text-[11px] font-medium transition cursor-pointer"
              >
                📂 打开原图
              </button>
              <button
                @click="api.openOutputs()"
                class="px-2.5 py-1 bg-white hover:bg-emerald-100 border border-emerald-300 rounded text-emerald-900 text-[11px] font-medium transition cursor-pointer"
              >
                📁 产物目录
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 弹窗底栏 -->
      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between shrink-0">
        <button
          @click="systemStore.closeModal('skillRunner')"
          class="px-4 py-2 text-[13px] text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-lg transition font-medium cursor-pointer"
        >
          关闭
        </button>
        <button
          @click="executeSkill"
          :disabled="running"
          class="px-6 py-2 text-[13px] text-white bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 rounded-lg transition font-semibold shadow-xs flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
        >
          <span>{{ running ? '执行中...' : '🚀 立即执行' }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue';
import { useSystemStore } from '../../stores/system';
import { api } from '../../api/client';

const systemStore = useSystemStore();

const formParams = ref({});
const running = ref(false);
const executionResult = ref(null);
const executionElapsed = ref(0);

const currentSkill = computed(() => {
  return systemStore.skillRunnerData?.skill || null;
});

const skillOriginBadge = computed(() => {
  const origin = currentSkill.value?.origin;
  if (origin === 'official') return '👑 官方认证';
  if (origin === 'community') return '🌐 第三方社区';
  return '🛠️ 本地开发';
});

// 计算输入参数规范
const skillInputs = computed(() => {
  const s = currentSkill.value;
  if (!s) return [];

  if (s.inputs && Array.isArray(s.inputs) && s.inputs.length > 0) {
    return s.inputs.map(i => ({
      name: i.name,
      desc: i.desc || '参数说明',
      isTextarea: i.name.includes('highlights') || i.name.includes('list') || i.name.includes('text'),
      placeholder: i.placeholder || ''
    }));
  }

  return [];
});

watch(
  () => systemStore.modals.skillRunner,
  (open) => {
    if (open) {
      executionResult.value = null;
      executionElapsed.value = 0;
      formParams.value = {};
      skillInputs.value.forEach(inp => {
        formParams.value[inp.name] = inp.default || '';
      });
    }
  }
);

const artifactFilePath = computed(() => {
  if (!executionResult.value) return '';
  const r = executionResult.value.result || executionResult.value;
  return r?.poster_path || r?.file_path || r?.path || '';
});

const artifactFileName = computed(() => {
  const p = artifactFilePath.value;
  if (!p) return '';
  const parts = p.split(/[\\/]/);
  return parts[parts.length - 1];
});

async function executeSkill() {
  if (!currentSkill.value) return;
  running.value = true;
  executionResult.value = null;
  const startTime = Date.now();

  try {
    const payload = {};
    Object.keys(formParams.value).forEach(k => {
      const val = formParams.value[k];
      if (typeof val === 'string' && (k.includes('highlights') || k.includes('list'))) {
        payload[k] = val.split('\n').map(s => s.trim()).filter(Boolean);
      } else {
        payload[k] = val;
      }
    });

    const res = await api.runSkill(currentSkill.value.name || currentSkill.value.id, payload);
    executionElapsed.value = Date.now() - startTime;
    executionResult.value = res;
    systemStore.showToast(`技能【${currentSkill.value.display_name || currentSkill.value.name}】执行完成！`);
  } catch (err) {
    executionElapsed.value = Date.now() - startTime;
    executionResult.value = {
      success: false,
      error: err.message || '执行异常'
    };
    alert('技能执行失败: ' + err.message);
  } finally {
    running.value = false;
  }
}
</script>
