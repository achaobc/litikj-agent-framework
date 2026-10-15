<template>
  <div
    v-if="systemStore.modals.recruit"
    class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-2xl max-h-[85vh] overflow-hidden animate-scale-up flex flex-col">
      <!-- 弹窗顶栏 -->
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-indigo-50/70 shrink-0">
        <div class="flex items-center space-x-2.5">
          <span class="text-2xl p-1 bg-white rounded-lg border border-indigo-100 shadow-2xs">💼</span>
          <div>
            <h3 class="font-bold text-slate-800 text-[15.5px]">数字化员工招募中枢 (Agent Hub & Recruitment)</h3>
            <p class="text-[11.5px] text-indigo-700 mt-0.5">云端名企直招 · 商业智能体开箱即用 · 支持自主拓岗</p>
          </div>
        </div>
        <button
          @click="systemStore.closeModal('recruit')"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer"
        >
          &times;
        </button>
      </div>

      <!-- Tab 切换栏 -->
      <div class="px-6 pt-3 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 text-[13.5px] font-medium shrink-0">
        <div class="flex space-x-6">
          <button
            @click="switchTab('market')"
            class="pb-2.5 border-b-2 flex items-center space-x-1.5 cursor-pointer"
            :class="activeTab === 'market' ? 'border-indigo-600 text-indigo-800 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
          >
            <span>🌟 云端名企招募库</span>
            <span v-if="marketList.length > 0" class="px-2 py-0.2 rounded-full text-[11px] bg-indigo-100 text-indigo-800 font-mono">
              {{ marketList.length }}
            </span>
          </button>
          <button
            @click="switchTab('custom')"
            class="pb-2.5 border-b-2 flex items-center space-x-1.5 cursor-pointer"
            :class="activeTab === 'custom' ? 'border-indigo-600 text-indigo-800 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
          >
            <span>🛠️ 快速自建岗位工坊</span>
          </button>
        </div>
        <button
          v-if="activeTab === 'market'"
          @click="fetchMarketAgents"
          class="text-[12px] text-indigo-600 hover:underline flex items-center space-x-1 pb-2 cursor-pointer"
        >
          <span>🔄</span>
          <span>刷新</span>
        </button>
      </div>

      <!-- 内容主体 -->
      <div class="p-6 overflow-y-auto flex-1 space-y-3">
        <!-- ================= Tab 1: 云端名企招募库 ================= -->
        <template v-if="activeTab === 'market'">
          <!-- 身份与鉴权横幅 -->
          <div class="p-3 rounded-xl bg-gradient-to-r from-indigo-50/90 to-purple-50/70 border border-indigo-100/80 text-[12.5px] text-indigo-900 flex items-center justify-between shadow-2xs">
            <div class="flex items-center space-x-2">
              <span class="font-medium">👑 授权身份:</span>
              <span class="font-bold px-2 py-0.5 rounded-full text-[11px] bg-white border border-indigo-200 text-indigo-800 shadow-2xs">
                {{ currentUserRoleName }}
              </span>
              <span class="text-slate-400 text-[11px] hidden sm:inline">· 官方验证标准 · 一键招募入职即用</span>
            </div>
            <button
              @click="openSettingsForActivation"
              class="text-[12px] text-indigo-600 hover:text-indigo-800 font-semibold underline cursor-pointer"
            >
              {{ isUserActivated ? '卡密管理 ⚙️' : '激活卡密 ➔' }}
            </button>
          </div>

          <!-- 加载中 -->
          <div v-if="loading" class="text-center text-slate-400 p-8 text-[13px]">
            正在载入名企数字化员工库...
          </div>

          <!-- 空列表 -->
          <div v-else-if="marketList.length === 0" class="text-center text-slate-400 p-8 text-[13px] bg-slate-50 rounded-xl">
            暂无云端智能体数据
          </div>

          <!-- 员工卡片列表 -->
          <div
            v-else
            v-for="item in marketList"
            :key="item.id"
            class="p-4 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 transition space-y-2.5 shadow-2xs"
          >
            <div class="flex items-start justify-between">
              <div class="flex items-start space-x-3 min-w-0 pr-3">
                <span class="text-3xl p-2 bg-slate-50 rounded-xl border border-slate-100 shrink-0 select-none">
                  {{ item.icon || '🤖' }}
                </span>
                <div class="min-w-0">
                  <div class="font-bold text-slate-800 text-[14.5px] flex items-center space-x-2 flex-wrap gap-y-1">
                    <span>{{ item.display_name || item.name }}</span>
                    <span class="text-[11px] px-2 py-0.2 rounded-full font-mono bg-slate-100 text-slate-600" title="云端上架最新版本">
                      云端 v{{ item.version || '1.0.0' }}
                    </span>
                    <span v-if="isAgentInstalled(item.id)" class="text-[11px] px-2 py-0.2 rounded-full font-mono bg-emerald-50 text-emerald-700 border border-emerald-200" title="本地正在运行版本">
                      本地 v{{ getLocalVersion(item.id) || '1.0.0' }}
                    </span>
                    <span v-if="item.category" class="text-[11px] px-2 py-0.2 rounded-full font-mono bg-indigo-50 text-indigo-700 border border-indigo-200">
                      {{ item.category }}
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
                    {{ item.description || '官方认证数字化岗位专家' }}
                  </p>

                  <!-- 挂载技能或特长标签 -->
                  <div class="mt-2 flex items-center space-x-1.5 flex-wrap gap-y-1">
                    <span class="text-[11px] text-slate-400 font-medium">预置能力:</span>
                    <template v-if="item.skills && item.skills.length > 0">
                      <span
                        v-for="sk in item.skills"
                        :key="sk"
                        class="text-[10.5px] px-1.5 py-0.2 bg-slate-100 text-slate-600 rounded font-mono border border-slate-200"
                      >
                        ⚡ {{ sk }}
                      </span>
                    </template>
                    <span v-else class="text-[11px] text-slate-400 italic">
                      纯文本深思推理与交互专家
                    </span>
                  </div>
                </div>
              </div>

              <!-- 右侧操作按钮组 -->
              <div class="flex items-center space-x-2 shrink-0 pt-0.5">
                <!-- 已在职状态 -->
                <template v-if="isAgentInstalled(item.id)">
                  <!-- 发现新版本：提供一键更新按钮 -->
                  <template v-if="isAgentUpdateAvailable(item)">
                    <button
                      @click="updateAgent(item)"
                      :disabled="updatingId === item.id"
                      class="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 active:bg-amber-700 text-white rounded-lg text-[12px] font-semibold transition cursor-pointer disabled:opacity-50 shadow-2xs flex items-center space-x-1"
                      :title="`本地 v${getLocalVersion(item.id)}，云端最新 v${item.version}`"
                    >
                      <span>{{ updatingId === item.id ? '更新中...' : `🔄 一键更新 (v${item.version})` }}</span>
                    </button>
                  </template>
                  <!-- 已是最新版本 -->
                  <template v-else>
                    <span class="px-2.5 py-1.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-lg text-[12px] font-medium flex items-center space-x-1">
                      <span>已在岗 (v{{ getLocalVersion(item.id) || item.version }}) ✓</span>
                    </span>
                  </template>
                  <button
                    v-if="item.id !== 'omni_sentinel'"
                    @click="dismissAgent(item)"
                    :disabled="dismissingId === item.id || updatingId === item.id"
                    class="px-2 py-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg text-[12px] transition cursor-pointer disabled:opacity-50"
                    title="解雇/辞退该数字化员工"
                  >
                    <span>{{ dismissingId === item.id ? '处理中...' : '🗑️' }}</span>
                  </button>
                </template>

                <!-- 未在职且已获得商业授权 -->
                <template v-else-if="item.is_authorized !== false">
                  <button
                    @click="recruitAgent(item)"
                    :disabled="recruitingId === item.id"
                    class="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-[12px] font-semibold transition cursor-pointer disabled:opacity-85 shadow-2xs flex items-center space-x-1"
                  >
                    <span v-if="recruitingId === item.id" class="flex items-center space-x-1.5">
                      <span class="animate-spin text-[11px]">⏳</span>
                      <span>{{ recruitingStatusText(item.id) }}</span>
                    </span>
                    <span v-else>📥 立即入职</span>
                  </button>
                </template>

                <!-- 未在职且无权限 (带锁) -->
                <template v-else>
                  <button
                    @click="handleLockedAgent(item)"
                    class="px-3 py-1.5 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 rounded-lg text-[12px] font-medium transition cursor-pointer flex items-center space-x-1"
                    title="需要年度会员即可招募"
                  >
                    <span>🔒</span>
                    <span>需年度会员</span>
                  </button>
                </template>
              </div>
            </div>
          </div>
        </template>

        <!-- ================= Tab 2: 快速自建岗位工坊 ================= -->
        <template v-else-if="activeTab === 'custom'">
          <div class="p-3 bg-indigo-50/50 rounded-xl border border-indigo-100 text-[12px] text-indigo-700">
            💡 <strong>自主拓岗说明</strong>：您可以为一人公司量身定制全新的数字化员工，设定岗位职责与人设提示词，系统将自动生成对应代码插槽与热重载。
          </div>

          <div class="space-y-4 pt-1">
            <div class="grid grid-cols-2 gap-3.5">
              <div>
                <label class="block text-[12px] font-semibold text-slate-700 mb-1">岗位代号 (ID) *</label>
                <input
                  type="text"
                  v-model="customForm.id"
                  placeholder="如 xiaohongshu_writer"
                  class="w-full text-[13px] p-2 rounded-lg border border-slate-300 font-mono outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label class="block text-[12px] font-semibold text-slate-700 mb-1">岗位名称 (中文) *</label>
                <input
                  type="text"
                  v-model="customForm.name"
                  placeholder="如 小红书文案专员"
                  class="w-full text-[13px] p-2 rounded-lg border border-slate-300 outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3.5">
              <div>
                <label class="block text-[12px] font-semibold text-slate-700 mb-1">形象 Emoji</label>
                <input
                  type="text"
                  v-model="customForm.icon"
                  class="w-16 text-center text-xl p-1.5 rounded-lg border border-slate-300 outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label class="block text-[12px] font-semibold text-slate-700 mb-1">职责简述</label>
                <input
                  type="text"
                  v-model="customForm.desc"
                  placeholder="专注引流文案自动化创作"
                  class="w-full text-[13px] p-2 rounded-lg border border-slate-300 outline-none focus:border-indigo-500"
                />
              </div>
            </div>

            <div>
              <label class="block text-[12px] font-semibold text-slate-700 mb-1">人设业务准则 (System Prompt)</label>
              <textarea
                v-model="customForm.prompt"
                rows="4"
                placeholder="你是一名专业的业务专员，精通各大平台算法推荐机制..."
                class="w-full text-[12.5px] p-2.5 rounded-lg border border-slate-300 outline-none resize-none leading-relaxed focus:border-indigo-500"
              ></textarea>
            </div>
          </div>
        </template>
      </div>

      <!-- 弹窗底栏 -->
      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between shrink-0">
        <button
          @click="systemStore.closeModal('recruit')"
          class="px-4 py-2 text-[13px] text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-lg transition font-medium cursor-pointer"
        >
          关闭
        </button>

        <div v-if="activeTab === 'custom'">
          <button
            @click="submitCustomRecruit"
            :disabled="submittingCustom"
            class="px-6 py-2 text-[13px] text-white bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 rounded-lg transition font-semibold shadow-xs flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
          >
            <span>{{ submittingCustom ? '办理中...' : '🎉 办理自建入职' }}</span>
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

const activeTab = ref('market');
const loading = ref(false);
const marketList = ref([]);
const recruitingId = ref(null);
const updatingId = ref(null);
const dismissingId = ref(null);
const submittingCustom = ref(false);

const customForm = ref({
  id: '',
  name: '',
  icon: '📕',
  desc: '',
  prompt: ''
});

const currentUserRoleName = computed(() => {
  if (marketList.value.length > 0 && marketList.value[0].user_role_name) {
    return marketList.value[0].user_role_name;
  }
  return '未激活 (访客)';
});

const isUserActivated = computed(() => {
  if (marketList.value.length > 0) {
    const role = marketList.value[0].user_role;
    return role && role !== 'guest';
  }
  return false;
});

function getInstalledAgent(agentId) {
  return agentStore.agents.find(a => (a.name === agentId || a.id === agentId));
}

function getLocalVersion(agentId) {
  const ag = getInstalledAgent(agentId);
  return ag ? (ag.version || '1.0.0') : null;
}

function isAgentInstalled(agentId) {
  return !!getInstalledAgent(agentId);
}

function parseVersion(v) {
  if (!v) return [0];
  return String(v).split('.').map(p => {
    const digits = p.replace(/\D/g, '');
    return digits ? parseInt(digits, 10) : 0;
  });
}

function compareVersions(v1, v2) {
  const p1 = parseVersion(v1);
  const p2 = parseVersion(v2);
  const len = Math.max(p1.length, p2.length);
  for (let i = 0; i < len; i++) {
    const n1 = p1[i] || 0;
    const n2 = p2[i] || 0;
    if (n1 > n2) return 1;
    if (n1 < n2) return -1;
  }
  return 0;
}

function isAgentUpdateAvailable(item) {
  if (!isAgentInstalled(item.id)) return false;
  if (item.has_update) return true;
  const localVer = getLocalVersion(item.id);
  if (!localVer || !item.version) return false;
  return compareVersions(item.version, localVer) > 0;
}

function getRoleBadgeClass(role) {
  if (role === 'annual' || role === 'member' || role === 'vip') {
    return 'bg-amber-50 text-amber-800 border-amber-200';
  }
  return 'bg-emerald-50 text-emerald-700 border-emerald-200';
}

async function fetchMarketAgents() {
  loading.value = true;
  try {
    const res = await api.getMarketAgents();
    marketList.value = res.agents || [];
  } catch (err) {
    console.warn('获取智能体市场数据失败:', err);
  } finally {
    loading.value = false;
  }
}

function switchTab(tab) {
  activeTab.value = tab;
  if (tab === 'market' && marketList.value.length === 0) {
    fetchMarketAgents();
  }
}

watch(
  () => systemStore.modals.recruit,
  (val) => {
    if (val && marketList.value.length === 0) {
      fetchMarketAgents();
    }
  }
);

onMounted(() => {
  if (systemStore.modals.recruit) {
    fetchMarketAgents();
  }
});

const recruitingMap = ref({});

function recruitingStatusText(agentId) {
  const r = recruitingMap.value[agentId];
  if (!r) return '办理中...';
  return `岗位准备中 (${r.percent}%)`;
}

async function recruitAgent(item) {
  recruitingId.value = item.id;
  recruitingMap.value[item.id] = { percent: 25, text: '正在下载卡带...' };
  try {
    const res = await api.recruitMarketAgent(item.id);
    recruitingMap.value[item.id] = { percent: 65, text: '正在全自动静默自愈环境...' };

    await agentStore.fetchAgents();
    await fetchMarketAgents();

    // 检查并静默自愈环境
    let readiness = await agentStore.fetchAgentReadiness(item.id);
    if (readiness && readiness.state === 'INSTALLING_DEPENDENCIES') {
      recruitingMap.value[item.id] = { percent: 85, text: '正在装备底层模型与目录...' };
      readiness = await agentStore.healAgent(item.id);
    }

    recruitingMap.value[item.id] = { percent: 100, text: '100% 完备就绪' };

    // 选中新招募员工
    const newly = agentStore.agents.find(a => (a.name === item.id || a.id === item.id));
    if (newly) {
      agentStore.selectAgent(newly);
    }

    if (readiness && readiness.state === 'ACTION_REQUIRED') {
      systemStore.showToast(`🎉 数字化员工 [${item.display_name || item.name}] 环境已齐备，需完成扫码授权！`);
    } else {
      systemStore.showToast(`🎉 数字化员工 [${item.display_name || item.name}] 环境已 100% 完备，已在岗待命！`);
    }
  } catch (err) {
    systemStore.showToast(`⚠️ 入职提醒: ${err.message || '环境自愈需进一步检查'}`);
  } finally {
    setTimeout(() => {
      delete recruitingMap.value[item.id];
      recruitingId.value = null;
    }, 1000);
  }
}

async function updateAgent(item) {
  updatingId.value = item.id;
  try {
    await api.recruitMarketAgent(item.id);
    await agentStore.fetchAgents();
    await fetchMarketAgents();

    // 刷新当前选中的智能体引用
    const updated = agentStore.agents.find(a => (a.name === item.id || a.id === item.id));
    if (updated && agentStore.currentAgent && (agentStore.currentAgent.name === item.id || agentStore.currentAgent.id === item.id)) {
      agentStore.selectAgent(updated);
    }

    systemStore.showToast(`🚀 数字化员工 [${item.display_name || item.name}] 已成功升级至 v${item.version}！`);
  } catch (err) {
    alert('升级更新失败: ' + (err.message || err));
  } finally {
    updatingId.value = null;
  }
}

async function dismissAgent(item) {
  if (!confirm(`确定要为数字化员工 [${item.display_name || item.name}] 办理离职吗？\n（离职后随时可在招募市场重新招募入职）`)) {
    return;
  }
  dismissingId.value = item.id;
  try {
    await api.dismissMarketAgent(item.id);
    await agentStore.fetchAgents();
    await fetchMarketAgents();

    // 若当前选中的正是被解雇员工，自动重定向到基准哨兵或首个智能体
    if (agentStore.currentAgent && (agentStore.currentAgent.name === item.id || agentStore.currentAgent.id === item.id)) {
      if (agentStore.agents.length > 0) {
        agentStore.selectAgent(agentStore.agents[0]);
      }
    }

    systemStore.showToast(`数字化员工 [${item.display_name || item.name}] 已安全办理离职归档`);
  } catch (err) {
    alert('离职办理失败: ' + err.message);
  } finally {
    dismissingId.value = null;
  }
}

function handleLockedAgent(item) {
  if (confirm(`🔒 数字化员工 [${item.display_name || item.name}] 为【年度会员】专享岗位。\n\n您当前为未激活访客身份，是否立即前往【系统设置】填入专属激活卡密升级为年度会员？`)) {
    openSettingsForActivation();
  }
}

function openSettingsForActivation() {
  systemStore.closeModal('recruit');
  systemStore.openModal('settings');
}

async function submitCustomRecruit() {
  if (!customForm.value.id || !customForm.value.name) {
    alert('请填写岗位代号与岗位名称');
    return;
  }
  submittingCustom.value = true;
  try {
    await api.recruitAgent({
      id: customForm.value.id.trim(),
      display_name: customForm.value.name.trim(),
      icon: customForm.value.icon.trim() || '🤖',
      description: customForm.value.desc.trim(),
      prompt: customForm.value.prompt.trim()
    });
    await agentStore.fetchAgents();
    systemStore.closeModal('recruit');
    systemStore.showToast(`🎉 自建数字化员工 [${customForm.value.name}] 已成功上岗！`);

    const newly = agentStore.agents.find(a => a.name === customForm.value.id.trim());
    if (newly) {
      agentStore.selectAgent(newly);
    }

    customForm.value = { id: '', name: '', icon: '📕', desc: '', prompt: '' };
  } catch (err) {
    alert('自建招聘失败: ' + err.message);
  } finally {
    submittingCustom.value = false;
  }
}
</script>
