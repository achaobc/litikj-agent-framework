<template>
  <div
    v-if="systemStore.modals.agentSkills"
    class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-2xl max-h-[85vh] overflow-hidden animate-scale-up flex flex-col">
      <!-- 弹窗顶栏 -->
      <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-indigo-50/80 to-purple-50/60 shrink-0">
        <div class="flex items-center space-x-3 min-w-0">
          <span class="text-2xl p-1.5 bg-white rounded-xl border border-indigo-100 shadow-2xs shrink-0">
            {{ agentStore.currentAgent?.icon || '🤖' }}
          </span>
          <div class="min-w-0">
            <div class="flex items-center space-x-2">
              <h3 class="font-bold text-slate-800 text-[15.5px] truncate">
                {{ agentStore.currentAgent?.display_name || agentStore.currentAgent?.name }} · 专属技能卡带
              </h3>
              <span class="text-[11px] font-mono px-2 py-0.2 rounded-full bg-indigo-100 text-indigo-800 font-semibold shrink-0">
                {{ agentStore.currentAgentSkills.length }} 项技能
              </span>
            </div>
            <p class="text-[11.5px] text-slate-500 mt-0.5 truncate">
              当前数字化员工所绑定的专属具身能力 · 独立参数配置与执行调试
            </p>
          </div>
        </div>
        <button
          @click="systemStore.closeModal('agentSkills')"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer shrink-0 ml-2"
        >
          &times;
        </button>
      </div>

      <!-- 快捷提示横幅 -->
      <div class="px-6 py-2.5 bg-slate-50/70 border-b border-slate-100 flex items-center justify-between text-[12px] text-slate-600 shrink-0">
        <div class="flex items-center space-x-1.5">
          <span>💡</span>
          <span>每个技能均可独立运行调试，参数配置已自动保存在本地。</span>
        </div>
        <button
          @click="openGlobalSkillsHub"
          class="text-indigo-600 hover:text-indigo-800 font-medium hover:underline flex items-center space-x-1 cursor-pointer"
        >
          <span>背包与市场 ➔</span>
        </button>
      </div>

      <!-- 技能列表主体 -->
      <div class="p-6 overflow-y-auto space-y-4 flex-1">
        <!-- 空状态 -->
        <div
          v-if="agentStore.currentAgentSkills.length === 0"
          class="text-center py-12 px-6 bg-slate-50 rounded-2xl border border-slate-200/80 space-y-3"
        >
          <span class="text-3xl">🧩</span>
          <div class="text-[14px] font-semibold text-slate-700">当前智能体暂未装载专属技能卡带</div>
          <p class="text-[12px] text-slate-400 max-w-sm mx-auto">
            您可以前往左侧边栏的「技能卡带」中枢，按需招募并装载官方或自定义业务技能。
          </p>
          <button
            @click="openGlobalSkillsHub"
            class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-[12.5px] font-medium rounded-xl transition cursor-pointer shadow-2xs"
          >
            前往技能卡带中枢
          </button>
        </div>

        <!-- 专属技能卡片列表 -->
        <div
          v-else
          v-for="skill in agentStore.currentAgentSkills"
          :key="skill.id || skill.name"
          class="p-4 rounded-xl border border-slate-200 hover:border-indigo-200 bg-white shadow-2xs transition space-y-3"
        >
          <!-- 技能卡片头部信息 -->
          <div class="flex items-start justify-between">
            <div class="flex items-center space-x-3 min-w-0 pr-3">
              <span class="text-2xl p-2 bg-slate-50 rounded-xl border border-slate-100 shrink-0">
                {{ skill.icon || '🧩' }}
              </span>
              <div class="min-w-0">
                <div class="flex items-center space-x-2">
                  <span class="font-bold text-slate-800 text-[14.5px] truncate">
                    {{ skill.display_name || skill.name }}
                  </span>
                  <span class="text-[11px] px-2 py-0.2 rounded-full font-mono bg-indigo-50 text-indigo-700 border border-indigo-200 font-medium">
                    {{ skill.category || '业务技能' }}
                  </span>
                  <span class="text-[10px] px-1.5 py-0.2 rounded font-mono bg-slate-100 text-slate-500">
                    v{{ skill.version || '1.0.0' }}
                  </span>
                </div>
                <p class="text-[12px] text-slate-500 mt-1 line-clamp-2 leading-relaxed">
                  {{ skill.description || '智能体绑定的底层原子能力，可免对话直接调用底层确定性执行逻辑。' }}
                </p>
              </div>
            </div>

            <!-- 右侧快捷运行按钮 -->
            <button
              @click="handleRunSkill(skill)"
              class="px-3.5 py-1.5 bg-emerald-50 hover:bg-emerald-100 active:bg-emerald-200 text-emerald-700 border border-emerald-200 rounded-lg text-[12.5px] font-medium transition cursor-pointer shrink-0 flex items-center space-x-1 shadow-2xs"
              title="独立运行与调试此技能"
            >
              <span>⚡</span>
              <span>独立调试运行</span>
            </button>
          </div>

          <!-- 专属参数配置快速预览 -->
          <div class="p-3 bg-slate-50/80 rounded-lg border border-slate-100 text-[12px] space-y-1.5">
            <div class="flex items-center justify-between text-slate-600 font-medium">
              <span class="flex items-center space-x-1">
                <span>⚙️</span>
                <span>专属参数状态:</span>
              </span>
              <span class="text-[11px] text-emerald-600 font-semibold flex items-center space-x-1">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                <span>已就绪 (Ready)</span>
              </span>
            </div>
            <p class="text-[11.5px] text-slate-400">
              此技能与当前智能体「{{ agentStore.currentAgent?.display_name }}」深度融合，对话中亦可直接通过自然语言调度。
            </p>
          </div>
        </div>
      </div>

      <!-- 弹窗底栏 -->
      <div class="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-between shrink-0">
        <span class="text-[11.5px] text-slate-400">
          共 {{ agentStore.currentAgentSkills.length }} 个专属业务技能绑定中
        </span>
        <button
          @click="systemStore.closeModal('agentSkills')"
          class="px-4 py-2 text-[13px] text-slate-700 hover:text-slate-900 bg-white border border-slate-200 hover:border-slate-300 rounded-lg transition font-medium cursor-pointer shadow-2xs"
        >
          完成
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useSystemStore } from '../../stores/system';
import { useAgentStore } from '../../stores/agent';

const systemStore = useSystemStore();
const agentStore = useAgentStore();

function openGlobalSkillsHub() {
  systemStore.closeModal('agentSkills');
  systemStore.openModal('skillsHub');
}

function handleRunSkill(skill) {
  systemStore.skillRunnerData = { skill };
  systemStore.closeModal('agentSkills');
  systemStore.openModal('skillRunner');
}
</script>
