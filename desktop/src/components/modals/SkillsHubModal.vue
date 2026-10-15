<template>
  <div
    v-if="systemStore.modals.skillsHub"
    class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-2xl max-h-[85vh] overflow-hidden animate-scale-up flex flex-col">
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-indigo-50/70 shrink-0">
        <div class="flex items-center space-x-2.5">
          <span class="text-2xl p-1 bg-white rounded-lg border border-indigo-100 shadow-2xs">🧩</span>
          <div>
            <h3 class="font-bold text-slate-800 text-[15.5px]">技能卡带中枢 (Skills Backpack & Market)</h3>
            <p class="text-[11.5px] text-indigo-700 mt-0.5">极简纯净微内核 · 按需鉴权下载 · 零依赖热插拔</p>
          </div>
        </div>
        <button
          @click="systemStore.closeModal('skillsHub')"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer"
        >
          &times;
        </button>
      </div>

      <!-- Tab 切换 -->
      <div class="px-6 pt-3 border-b border-slate-100 flex items-center justify-between bg-slate-50/40 text-[13.5px] font-medium shrink-0">
        <div class="flex space-x-6">
          <button
            @click="switchTab('loaded')"
            class="pb-2.5 border-b-2 flex items-center space-x-1.5 cursor-pointer"
            :class="activeTab === 'loaded' ? 'border-indigo-600 text-indigo-800 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
          >
            <span>🎒 本地已装载</span>
            <span class="px-2 py-0.2 rounded-full text-[11px] bg-indigo-100 text-indigo-800 font-mono">
              {{ skillsList.length }}
            </span>
          </button>
          <button
            @click="switchTab('market')"
            class="pb-2.5 border-b-2 flex items-center space-x-1.5 cursor-pointer"
            :class="activeTab === 'market' ? 'border-indigo-600 text-indigo-800 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-800'"
          >
            <span>☁️ 官方云端市场</span>
            <span v-if="marketList.length > 0" class="px-2 py-0.2 rounded-full text-[11px] bg-slate-100 text-slate-600 font-mono">
              {{ marketList.length }}
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
      <div class="p-6 overflow-y-auto flex-1 space-y-3">
        <div v-if="loading" class="text-center text-slate-400 p-8 text-[13px]">
          正在载入技能生态...
        </div>

        <!-- Tab 1: 已装载卡带 -->
        <template v-else-if="activeTab === 'loaded'">
          <div v-if="skillsList.length === 0" class="text-center text-slate-400 p-8 text-[13px] bg-slate-50 rounded-xl space-y-2">
            <div>暂无本地业务技能（纯净微内核状态）</div>
            <p class="text-[12px] text-slate-400">您可以点击上方的「官方云端市场」按需一键下载装载所需技能卡带</p>
          </div>

          <div
            v-else
            v-for="skill in skillsList"
            :key="skill.name || skill.id"
            class="p-4 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 transition space-y-2 shadow-2xs flex items-center justify-between"
          >
            <div class="flex items-center space-x-3 min-w-0 pr-3">
              <span class="text-2xl p-2 bg-slate-50 rounded-xl border border-slate-100 shrink-0">
                {{ skill.icon || '🧩' }}
              </span>
              <div class="min-w-0">
                <div class="font-bold text-slate-800 text-[14px] flex items-center space-x-2">
                  <span>{{ skill.display_name || skill.name }}</span>
                  <span class="text-[11px] px-2 py-0.5 rounded-full font-mono bg-indigo-50 text-indigo-700 border border-indigo-200">
                    {{ skill.category || '原生具身' }}
                  </span>
                </div>
                <p class="text-[12px] text-slate-400 mt-0.5 truncate">
                  {{ skill.description || '无详细描述' }}
                </p>
              </div>
            </div>
            <div class="flex items-center space-x-2 shrink-0">
              <button
                @click="runSkill(skill)"
                class="px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 rounded-lg text-[12px] font-medium transition cursor-pointer"
              >
                ⚡ 运行
              </button>
              <button
                @click="uninstallSkill(skill.name || skill.id)"
                class="px-2.5 py-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg text-[12px] transition cursor-pointer"
                title="卸载该技能"
              >
                🗑️
              </button>
            </div>
          </div>
        </template>

        <!-- Tab 2: 官方云端市场 -->
        <template v-else-if="activeTab === 'market'">
          <!-- 身份与鉴权横幅 -->
          <div class="p-3 rounded-xl bg-gradient-to-r from-indigo-50/90 to-purple-50/70 border border-indigo-100/80 text-[12.5px] text-indigo-900 flex items-center justify-between shadow-2xs">
            <div class="flex items-center space-x-2">
              <span class="font-medium">👑 授权身份:</span>
              <span class="font-bold px-2 py-0.5 rounded-full text-[11px] bg-white border border-indigo-200 text-indigo-800 shadow-2xs">
                {{ currentUserRoleName }}
              </span>
              <span class="text-slate-400 text-[11px] hidden sm:inline">· 云端物理隔离 · 按需鉴权下载</span>
            </div>
            <button
              @click="openSettingsForActivation"
              class="text-[12px] text-indigo-600 hover:text-indigo-800 font-semibold underline cursor-pointer"
            >
              {{ isUserActivated ? '卡密管理 ⚙️' : '激活卡密 ➔' }}
            </button>
          </div>

          <div v-if="marketList.length === 0" class="text-center text-slate-400 p-8 text-[13px] bg-slate-50 rounded-xl">
            暂无云端技能
          </div>

          <div
            v-else
            v-for="item in marketList"
            :key="item.id"
            class="p-4 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 transition space-y-2 shadow-2xs flex items-center justify-between"
          >
            <div class="flex items-center space-x-3 min-w-0 pr-3">
              <span class="text-2xl p-2 bg-slate-50 rounded-xl border border-slate-100 shrink-0">
                {{ item.icon || '🧩' }}
              </span>
              <div class="min-w-0">
                <div class="font-bold text-slate-800 text-[14px] flex items-center space-x-2 flex-wrap gap-y-1">
                  <span>{{ item.name }}</span>
                  <span class="text-[11px] px-2 py-0.2 rounded-full font-mono bg-slate-100 text-slate-600">
                    v{{ item.version || '1.0.0' }}
                  </span>
                  
                  <!-- 权限级别徽章 -->
                  <span
                    class="text-[10.5px] px-2 py-0.2 rounded-full font-medium border"
                    :class="getRoleBadgeClass(item.required_role)"
                  >
                    {{ item.required_role_name || item.role_name || '免费公开' }}
                  </span>

                  <span v-if="item.size" class="text-[10.5px] text-slate-400 font-mono">
                    {{ item.size }}
                  </span>
                </div>
                <p class="text-[12px] text-slate-400 mt-1 line-clamp-1">
                  {{ item.description || '官方认证技能卡带' }}
                </p>
              </div>
            </div>

            <!-- 操作按钮组 -->
            <div class="flex items-center space-x-2 shrink-0">
              <!-- 已装载状态 -->
              <template v-if="isSkillInstalled(item.id)">
                <span class="px-2.5 py-1.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-lg text-[12px] font-medium">
                  已装载 ✓
                </span>
                <button
                  @click="uninstallSkill(item.id)"
                  class="px-2 py-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg text-[12px] transition cursor-pointer"
                  title="从本地卸载"
                >
                  🗑️
                </button>
              </template>

              <!-- 未装载且已授权 -->
              <template v-else-if="item.is_authorized !== false">
                <button
                  @click="installSkill(item.id)"
                  :disabled="installingId === item.id"
                  class="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-[12px] font-semibold transition cursor-pointer disabled:opacity-50 shadow-2xs"
                >
                  {{ installingId === item.id ? '装载中...' : '📥 装载' }}
                </button>
              </template>

              <!-- 未装载且无权限 (带锁) -->
              <template v-else>
                <button
                  @click="handleLockedSkill(item)"
                  class="px-3 py-1.5 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 rounded-lg text-[12px] font-medium transition cursor-pointer flex items-center space-x-1"
                  title="需要年度会员即可解锁"
                >
                  <span>🔒</span>
                  <span>需年度会员</span>
                </button>
              </template>
            </div>
          </div>
        </template>
      </div>

      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end">
        <button
          @click="systemStore.closeModal('skillsHub')"
          class="px-4.5 py-2 text-[13px] text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-lg transition font-medium cursor-pointer"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useSystemStore } from '../../stores/system';
import { api } from '../../api/client';

const systemStore = useSystemStore();
const activeTab = ref('loaded');
const loading = ref(false);
const skillsList = ref([]);
const marketList = ref([]);
const installingId = ref(null);

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

onMounted(async () => {
  await fetchSkills();
});

async function switchTab(tab) {
  activeTab.value = tab;
  if (tab === 'market' && marketList.value.length === 0) {
    await fetchMarket();
  }
}

async function refreshData() {
  if (activeTab.value === 'loaded') {
    await fetchSkills();
  } else {
    await fetchMarket();
  }
}

async function fetchSkills() {
  loading.value = true;
  try {
    const res = await api.getSkills();
    skillsList.value = res.skills || [];
  } catch (err) {
    console.warn('获取技能失败:', err);
  } finally {
    loading.value = false;
  }
}

async function fetchMarket() {
  loading.value = true;
  try {
    const res = await api.getMarketSkills();
    marketList.value = res.market || res.market_skills || [];
  } catch (err) {
    console.warn('获取市场技能失败:', err);
  } finally {
    loading.value = false;
  }
}

function isSkillInstalled(skillId) {
  return skillsList.value.some(s => (s.name === skillId || s.id === skillId));
}

function getRoleBadgeClass(role) {
  if (role === 'annual' || role === 'member' || role === 'vip') {
    return 'bg-amber-50 text-amber-800 border-amber-200';
  }
  return 'bg-slate-50 text-slate-600 border-slate-200';
}

async function installSkill(skillId) {
  installingId.value = skillId;
  try {
    await api.installMarketSkill(skillId);
    await fetchSkills();
    await fetchMarket();
    systemStore.showToast('🎉 技能装载成功，已即刻在本地激活就绪！');
  } catch (err) {
    alert(err.message || '装载失败');
  } finally {
    installingId.value = null;
  }
}

async function uninstallSkill(skillId) {
  if (!confirm(`确定要从本地卸载技能 [${skillId}] 吗？`)) {
    return;
  }
  try {
    await api.uninstallMarketSkill(skillId);
    await fetchSkills();
    await fetchMarket();
    systemStore.showToast('技能已安全从本地卸载');
  } catch (err) {
    alert('卸载失败: ' + err.message);
  }
}

function handleLockedSkill(item) {
  if (confirm(`🔒 技能 [${item.name}] 为【年度会员】专享权益。\n\n您当前为未激活访客身份，是否立即前往【系统设置】填入专属激活卡密升级为年度会员？`)) {
    openSettingsForActivation();
  }
}

function openSettingsForActivation() {
  systemStore.closeModal('skillsHub');
  systemStore.openModal('settings');
}

function runSkill(skill) {
  systemStore.closeModal('skillsHub');
  systemStore.openModal('skillRunner', { skill });
}
</script>
