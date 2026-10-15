<template>
  <div
    v-if="systemStore.modals.workflow"
    class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-2xl max-h-[88vh] overflow-hidden animate-scale-up flex flex-col">
      <!-- 弹窗顶栏 -->
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-indigo-50/70 shrink-0">
        <div class="flex items-center space-x-2.5">
          <span class="text-2xl p-1 bg-white rounded-lg border border-indigo-100 shadow-2xs">🔄</span>
          <div>
            <h3 class="font-bold text-slate-800 text-[15.5px]">多智能体接力协同中枢 (Pipeline & Market)</h3>
            <p class="text-[11.5px] text-indigo-700 mt-0.5">全案流水线接力 · 人机把关与并发扇出 · 一键补齐依赖</p>
          </div>
        </div>
        <button
          @click="systemStore.closeModal('workflow')"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer"
        >
          &times;
        </button>
      </div>

      <!-- Tab 切换栏 -->
      <div class="px-6 pt-3 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 text-[13.5px] font-medium shrink-0">
        <div class="flex space-x-6">
          <button
            @click="switchTab('run')"
            class="pb-2.5 border-b-2 flex items-center space-x-1.5 cursor-pointer"
            :class="activeTab === 'run' ? 'border-indigo-600 text-indigo-800 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
          >
            <span>⚡ 协同调度台</span>
            <span class="px-2 py-0.2 rounded-full text-[11px] bg-indigo-100 text-indigo-800 font-mono">
              {{ localWorkflows.length }}
            </span>
          </button>
          <button
            @click="switchTab('market')"
            class="pb-2.5 border-b-2 flex items-center space-x-1.5 cursor-pointer"
            :class="activeTab === 'market' ? 'border-indigo-600 text-indigo-800 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
          >
            <span>☁️ 官方云端市场</span>
            <span v-if="marketWorkflows.length > 0" class="px-2 py-0.2 rounded-full text-[11px] bg-slate-100 text-slate-600 font-mono">
              {{ marketWorkflows.length }}
            </span>
          </button>
        </div>
        <button
          @click="refreshData"
          class="text-[12px] text-indigo-600 hover:underline flex items-center space-x-1 pb-2 cursor-pointer"
        >
          <span>🔄</span>
          <span>刷新</span>
        </button>
      </div>

      <!-- 内容主体 -->
      <div class="p-6 overflow-y-auto flex-1 space-y-4">
        <!-- ================= Tab 1: 协同调度台 ================= -->
        <template v-if="activeTab === 'run'">
          <div v-if="localWorkflows.length === 0" class="text-center text-slate-400 p-8 text-[13px] bg-slate-50 rounded-xl space-y-2">
            <div>暂无本地已装载的工作流</div>
            <p class="text-[12px] text-slate-400">您可以点击上方的「官方云端市场」一键下载装载所需协同流水线</p>
          </div>

          <template v-else>
            <!-- 选择已注册工作流 -->
            <div>
              <label class="block text-[12.5px] font-semibold text-slate-700 mb-1.5">选择执行流水线</label>
              <div class="grid grid-cols-1 gap-2">
                <div
                  v-for="wf in localWorkflows"
                  :key="wf.id || wf.name"
                  @click="selectedWfId = wf.id || wf.name"
                  class="p-3 rounded-xl border transition cursor-pointer flex items-center justify-between"
                  :class="selectedWfId === (wf.id || wf.name) ? 'border-indigo-500 bg-indigo-50/40 shadow-2xs' : 'border-slate-200 hover:border-slate-300 bg-white'"
                >
                  <div class="flex items-center space-x-3 min-w-0 pr-2">
                    <span class="text-2xl p-1.5 bg-slate-50 rounded-lg border border-slate-100 shrink-0">
                      {{ wf.icon || '🔄' }}
                    </span>
                    <div class="min-w-0">
                      <div class="font-bold text-slate-800 text-[13.5px] flex items-center space-x-2">
                        <span>{{ wf.display_name || wf.name || wf.id }}</span>
                        <span class="text-[11px] px-2 py-0.2 rounded-full font-mono bg-indigo-50 text-indigo-700 border border-indigo-200">
                          {{ wf.category || '多智能体协同' }}
                        </span>
                      </div>
                      <p class="text-[12px] text-slate-400 mt-0.5 truncate">
                        {{ wf.description || '多智能体全链路协同调度' }}
                      </p>
                    </div>
                  </div>
                  <div class="shrink-0 text-indigo-600 font-bold text-lg">
                    <span v-if="selectedWfId === (wf.id || wf.name)">✓</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 当前选中工作流的依赖健康状态提示 -->
            <div
              v-if="currentMatchedMarketInfo && !currentMatchedMarketInfo.is_deps_ready"
              class="p-3 bg-amber-50 rounded-xl border border-amber-200 text-[12px] text-amber-900 flex items-center justify-between"
            >
              <div class="space-y-0.5">
                <div class="font-bold flex items-center space-x-1.5 text-amber-800">
                  <span>⚠️ 协同依赖未完全就绪:</span>
                  <span v-if="currentMatchedMarketInfo.missing_agents.length > 0">
                    缺少员工 [{{ currentMatchedMarketInfo.missing_agents.join(', ') }}]
                  </span>
                  <span v-if="currentMatchedMarketInfo.missing_skills.length > 0">
                    缺少技能 [{{ currentMatchedMarketInfo.missing_skills.join(', ') }}]
                  </span>
                </div>
                <p class="text-[11.5px] text-amber-700">推荐在执行前一键补齐所有关联依赖，以获得最佳协同产出</p>
              </div>
              <button
                @click="autoFixDependencies(currentMatchedMarketInfo)"
                :disabled="fixingDepsId === currentMatchedMarketInfo.id"
                class="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-[11.5px] font-semibold transition cursor-pointer shrink-0 disabled:opacity-50"
              >
                <span>{{ fixingDepsId === currentMatchedMarketInfo.id ? '补齐中...' : '⚡ 一键补齐依赖' }}</span>
              </button>
            </div>

            <!-- 任务命题输入 -->
            <div>
              <label class="block text-[12.5px] font-semibold text-slate-700 mb-1">
                初始核心命题 / 任务需求 (Topic / Query) *
              </label>
              <input
                type="text"
                v-model="wfTopic"
                placeholder="例如: 打造高转化自媒体全案或底座健康巡检"
                class="w-full text-[13px] p-2.5 rounded-lg border border-slate-300 focus:border-indigo-500 outline-none"
              />
            </div>

            <!-- 节点图流转预览 -->
            <div class="bg-indigo-50/40 p-4 rounded-xl border border-indigo-100 space-y-2">
              <div class="flex items-center space-x-2 text-[12.5px] font-bold text-indigo-900">
                <span>🔗 预设协同接力链路节点：</span>
              </div>
              <p class="text-[12px] text-indigo-800 font-mono leading-relaxed">
                {{ getPipelineNodesText(selectedWfId) }}
              </p>
              <label class="flex items-center space-x-2 text-[12.5px] text-slate-700 cursor-pointer pt-1">
                <input type="checkbox" v-model="isDryRun" class="rounded text-indigo-600">
                <span class="font-medium">开启全链路 Dry-Run 仿真测试模式 (推荐首测勾选)</span>
              </label>
            </div>
          </template>
        </template>

        <!-- ================= Tab 2: 官方云端市场 ================= -->
        <template v-else-if="activeTab === 'market'">
          <!-- 身份与鉴权横幅 -->
          <div class="p-3 rounded-xl bg-gradient-to-r from-indigo-50/90 to-purple-50/70 border border-indigo-100/80 text-[12.5px] text-indigo-900 flex items-center justify-between shadow-2xs">
            <div class="flex items-center space-x-2">
              <span class="font-medium">👑 授权身份:</span>
              <span class="font-bold px-2 py-0.5 rounded-full text-[11px] bg-white border border-indigo-200 text-indigo-800 shadow-2xs">
                {{ currentUserRoleName }}
              </span>
              <span class="text-slate-400 text-[11px] hidden sm:inline">· 商业工作流卡带 · 依赖拓扑自动感知</span>
            </div>
            <button
              @click="openSettingsForActivation"
              class="text-[12px] text-indigo-600 hover:text-indigo-800 font-semibold underline cursor-pointer"
            >
              {{ isUserActivated ? '卡密管理 ⚙️' : '激活卡密 ➔' }}
            </button>
          </div>

          <div v-if="loading" class="text-center text-slate-400 p-8 text-[13px]">
            正在载入云端工作流市场...
          </div>

          <div v-else-if="marketWorkflows.length === 0" class="text-center text-slate-400 p-8 text-[13px] bg-slate-50 rounded-xl">
            暂无云端工作流卡带
          </div>

          <div
            v-else
            v-for="item in marketWorkflows"
            :key="item.id"
            class="p-4 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 transition space-y-2.5 shadow-2xs"
          >
            <div class="flex items-start justify-between">
              <div class="flex items-start space-x-3 min-w-0 pr-3">
                <span class="text-3xl p-2 bg-slate-50 rounded-xl border border-slate-100 shrink-0 select-none">
                  {{ item.icon || '🔄' }}
                </span>
                <div class="min-w-0">
                  <div class="font-bold text-slate-800 text-[14.5px] flex items-center space-x-2 flex-wrap gap-y-1">
                    <span>{{ item.display_name || item.name }}</span>
                    <span class="text-[11px] px-2 py-0.2 rounded-full font-mono bg-slate-100 text-slate-600">
                      v{{ item.version || '1.0.0' }}
                    </span>
                    <span class="text-[11px] px-2 py-0.2 rounded-full font-mono bg-indigo-50 text-indigo-700 border border-indigo-200">
                      {{ item.category || '多智能体协同' }}
                    </span>
                    <!-- 权限级别徽章 -->
                    <span
                      class="text-[10.5px] px-2 py-0.2 rounded-full font-medium border"
                      :class="getRoleBadgeClass(item.required_role)"
                    >
                      {{ item.required_role_name || item.role_name || '年度会员专享' }}
                    </span>
                  </div>
                  <p class="text-[12.5px] text-slate-500 mt-1 leading-relaxed">
                    {{ item.description || '官方认证多智能体全案协同流水线' }}
                  </p>

                  <!-- 依赖拓扑状态呈现 -->
                  <div class="mt-2 flex items-center space-x-2 flex-wrap gap-y-1">
                    <span class="text-[11px] text-slate-400 font-medium">依赖健康:</span>
                    <span
                      v-if="item.is_deps_ready"
                      class="text-[10.5px] px-2 py-0.2 bg-emerald-50 text-emerald-700 rounded font-semibold border border-emerald-200 flex items-center space-x-1"
                    >
                      <span>✓ 依赖完备 100% Ready</span>
                    </span>
                    <template v-else>
                      <span class="text-[10.5px] px-2 py-0.2 bg-amber-50 text-amber-800 rounded font-medium border border-amber-200">
                        ⚠️ 缺少:
                        <span v-if="item.missing_agents.length > 0">{{ item.missing_agents.length }}名员工</span>
                        <span v-if="item.missing_agents.length > 0 && item.missing_skills.length > 0"> + </span>
                        <span v-if="item.missing_skills.length > 0">{{ item.missing_skills.length }}个技能</span>
                      </span>
                      <button
                        @click="autoFixDependencies(item)"
                        :disabled="fixingDepsId === item.id"
                        class="text-[11px] text-indigo-600 hover:text-indigo-800 font-semibold underline cursor-pointer disabled:opacity-50"
                      >
                        {{ fixingDepsId === item.id ? '补齐中...' : '⚡ 一键补齐依赖' }}
                      </button>
                    </template>
                  </div>
                </div>
              </div>

              <!-- 右侧操作按钮组 -->
              <div class="flex items-center space-x-2 shrink-0 pt-0.5">
                <!-- 已装载状态 -->
                <template v-if="isWorkflowInstalled(item.id)">
                  <span class="px-2.5 py-1.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-lg text-[12px] font-medium">
                    已装载 ✓
                  </span>
                  <button
                    v-if="item.id !== 'system_health_audit'"
                    @click="uninstallWorkflow(item)"
                    :disabled="uninstallingId === item.id"
                    class="px-2 py-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg text-[12px] transition cursor-pointer disabled:opacity-50"
                    title="从本地卸载该工作流"
                  >
                    <span>{{ uninstallingId === item.id ? '处理中...' : '🗑️' }}</span>
                  </button>
                </template>

                <!-- 未装载且有商业权限 -->
                <template v-else-if="item.is_authorized !== false">
                  <button
                    @click="installWorkflow(item)"
                    :disabled="installingId === item.id"
                    class="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-[12px] font-semibold transition cursor-pointer disabled:opacity-50 shadow-2xs flex items-center space-x-1"
                  >
                    <span>{{ installingId === item.id ? '装载中...' : '📥 一键装载' }}</span>
                  </button>
                </template>

                <!-- 未装载且无权限 -->
                <template v-else>
                  <button
                    @click="handleLockedWorkflow(item)"
                    class="px-3 py-1.5 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 rounded-lg text-[12px] font-medium transition cursor-pointer flex items-center space-x-1"
                    title="需要年度会员即可装载"
                  >
                    <span>🔒</span>
                    <span>需年度会员</span>
                  </button>
                </template>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 弹窗底栏 -->
      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between shrink-0">
        <button
          @click="systemStore.closeModal('workflow')"
          class="px-4 py-2 text-[13px] text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-lg transition font-medium cursor-pointer"
        >
          关闭
        </button>

        <div v-if="activeTab === 'run' && localWorkflows.length > 0">
          <button
            @click="submitRunWorkflow"
            :disabled="submittingRun"
            class="px-5 py-2 text-[13px] text-white bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 rounded-lg transition font-semibold shadow-xs flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
          >
            <span>{{ submittingRun ? '全链路调度中...' : '启动全链路接力协同 🚀' }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue';
import { useSystemStore } from '../../stores/system';
import { useAgentStore } from '../../stores/agent';
import { api } from '../../api/client';

const systemStore = useSystemStore();
const agentStore = useAgentStore();

const activeTab = ref('run');
const loading = ref(false);
const localWorkflows = ref([]);
const marketWorkflows = ref([]);

const selectedWfId = ref('media_matrix_pipeline');
const wfTopic = ref('一人公司自媒体全网爆款协同实战');
const isDryRun = ref(true);
const submittingRun = ref(false);

const installingId = ref(null);
const uninstallingId = ref(null);
const fixingDepsId = ref(null);

const currentUserRoleName = computed(() => {
  if (marketWorkflows.value.length > 0 && marketWorkflows.value[0].user_role_name) {
    return marketWorkflows.value[0].user_role_name;
  }
  return '未激活 (访客)';
});

const isUserActivated = computed(() => {
  if (marketWorkflows.value.length > 0) {
    const role = marketWorkflows.value[0].user_role;
    return role && role !== 'guest';
  }
  return false;
});

const currentMatchedMarketInfo = computed(() => {
  return marketWorkflows.value.find(m => m.id === selectedWfId.value) || null;
});

function isWorkflowInstalled(wfId) {
  return localWorkflows.value.some(w => (w.id === wfId || w.name === wfId));
}

function getRoleBadgeClass(role) {
  if (role === 'annual' || role === 'member' || role === 'vip') {
    return 'bg-amber-50 text-amber-800 border-amber-200';
  }
  return 'bg-emerald-50 text-emerald-700 border-emerald-200';
}

function getPipelineNodesText(wfId) {
  return '[omni_sentinel (全维调度哨兵)] ➔ [人机协同审批断点] ➔ [持久化审计报告]';
}

async function fetchLocalWorkflows() {
  try {
    const res = await api.getWorkflows();
    localWorkflows.value = res.workflows || [];
    if (localWorkflows.value.length > 0) {
      if (!selectedWfId.value || !localWorkflows.value.some(w => (w.id === selectedWfId.value || w.name === selectedWfId.value))) {
        selectedWfId.value = localWorkflows.value[0].id || localWorkflows.value[0].name;
      }
    }
  } catch (err) {
    console.warn('获取工作流列表失败:', err);
  }
}

async function fetchMarketWorkflows() {
  loading.value = true;
  try {
    const res = await api.getMarketWorkflows();
    marketWorkflows.value = res.workflows || [];
  } catch (err) {
    console.warn('获取工作流市场数据失败:', err);
  } finally {
    loading.value = false;
  }
}

async function refreshData() {
  if (activeTab.value === 'run') {
    await fetchLocalWorkflows();
    await fetchMarketWorkflows();
  } else {
    await fetchMarketWorkflows();
  }
}

function switchTab(tab) {
  activeTab.value = tab;
  if (tab === 'market' && marketWorkflows.value.length === 0) {
    fetchMarketWorkflows();
  }
}

watch(
  () => systemStore.modals.workflow,
  (val) => {
    if (val) {
      fetchLocalWorkflows();
      fetchMarketWorkflows();
    }
  }
);

onMounted(() => {
  fetchLocalWorkflows();
  fetchMarketWorkflows();
});

async function submitRunWorkflow() {
  if (!wfTopic.value.trim()) {
    alert('请填写初始任务主题');
    return;
  }
  submittingRun.value = true;
  try {
    await api.runWorkflow(selectedWfId.value, wfTopic.value.trim(), isDryRun.value);
    systemStore.closeModal('workflow');
    systemStore.showToast('🚀 已成功启动多智能体全链路协同调度！');
    await systemStore.fetchSuspendedWorkflows();
  } catch (err) {
    alert('启动流水线失败: ' + err.message);
  } finally {
    submittingRun.value = false;
  }
}

async function installWorkflow(item) {
  installingId.value = item.id;
  try {
    await api.installMarketWorkflow(item.id);
    await fetchLocalWorkflows();
    await fetchMarketWorkflows();
    selectedWfId.value = item.id;
    systemStore.showToast(`🎉 协同工作流 [${item.display_name || item.name}] 已成功装载！`);
  } catch (err) {
    alert(err.message || '装载流水线失败');
  } finally {
    installingId.value = null;
  }
}

async function autoFixDependencies(item) {
  fixingDepsId.value = item.id;
  try {
    const res = await api.installMarketWorkflowDeps(item.id);
    await agentStore.fetchAgents();
    await fetchMarketWorkflows();
    systemStore.showToast(res.message || '🎉 关联依赖已全自动补齐就绪！');
  } catch (err) {
    alert('一键补齐依赖失败: ' + err.message);
  } finally {
    fixingDepsId.value = null;
  }
}

async function uninstallWorkflow(item) {
  if (!confirm(`确定要从本地卸载协同工作流 [${item.display_name || item.name}] 吗？`)) {
    return;
  }
  uninstallingId.value = item.id;
  try {
    await api.uninstallMarketWorkflow(item.id);
    await fetchLocalWorkflows();
    await fetchMarketWorkflows();
    if (selectedWfId.value === item.id && localWorkflows.value.length > 0) {
      selectedWfId.value = localWorkflows.value[0].id || localWorkflows.value[0].name;
    }
    systemStore.showToast(`工作流 [${item.display_name || item.name}] 已安全卸载`);
  } catch (err) {
    alert('卸载失败: ' + err.message);
  } finally {
    uninstallingId.value = null;
  }
}

function handleLockedWorkflow(item) {
  if (confirm(`🔒 协同工作流 [${item.display_name || item.name}] 为【年度会员】专享流水线。\n\n您当前为未激活访客身份，是否立即前往【系统设置】填入专属激活卡密升级为年度会员？`)) {
    openSettingsForActivation();
  }
}

function openSettingsForActivation() {
  systemStore.closeModal('workflow');
  systemStore.openModal('settings');
}
</script>
