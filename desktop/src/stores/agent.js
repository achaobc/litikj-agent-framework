import { defineStore } from 'pinia';
import { api, initAuthToken } from '../api/client';
import { useSystemStore } from './system';

export const useAgentStore = defineStore('agent', {
  state: () => ({
    agents: [],
    currentAgent: null,
    skills: [],
    loading: false,
    agentReadinessMap: {} // { [agentName]: { state, progress, current_item, items, action_guide, message } }
  }),

  getters: {
    currentAgentSkills: (state) => {
      if (!state.currentAgent) return [];
      const agentSkillIds = state.currentAgent.skills || [];
      return agentSkillIds.map(sid => {
        const matched = state.skills.find(s => s.name === sid || s.id === sid);
        if (matched) return matched;
        return {
          id: sid,
          name: sid,
          display_name: sid,
          icon: '🧩',
          category: '业务技能',
          description: `智能体绑定的底层原子能力 (${sid})`,
          inputs: []
        };
      });
    },
    currentAgentReadiness: (state) => {
      if (!state.currentAgent) return { state: 'READY', progress: 100 };
      const name = state.currentAgent.name || state.currentAgent.id;
      return state.agentReadinessMap[name] || state.currentAgent.readiness || { state: 'READY', progress: 100 };
    }
  },

  actions: {
    getAgentReadiness(agentName) {
      if (!agentName) return { state: 'READY', progress: 100 };
      return this.agentReadinessMap[agentName] || { state: 'READY', progress: 100 };
    },

    async fetchAgentReadiness(agentName) {
      if (!agentName) return null;
      try {
        const res = await api.getAgentReadiness(agentName);
        if (res && res.readiness) {
          this.agentReadinessMap[agentName] = res.readiness;
          // 同步刷新 currentAgent 上的 readiness
          if (this.currentAgent && (this.currentAgent.name === agentName || this.currentAgent.id === agentName)) {
            this.currentAgent.readiness = res.readiness;
          }
          return res.readiness;
        }
      } catch (e) {
        console.warn(`[AgentStore] 获取 ${agentName} 就绪度失败:`, e);
      }
      return null;
    },

    async healAgent(agentName) {
      if (!agentName) return null;
      try {
        const res = await api.healAgent(agentName);
        if (res && res.readiness) {
          this.agentReadinessMap[agentName] = res.readiness;
          if (this.currentAgent && (this.currentAgent.name === agentName || this.currentAgent.id === agentName)) {
            this.currentAgent.readiness = res.readiness;
          }
          return res.readiness;
        }
      } catch (e) {
        console.error(`[AgentStore] 自愈 ${agentName} 异常:`, e);
      }
      return null;
    },

    async fetchSkills() {
      try {
        await initAuthToken();
        const res = await api.getSkills();
        if (res && Array.isArray(res.skills)) {
          this.skills = res.skills;
        }
      } catch (e) {
        console.error('Failed to fetch skills:', e);
      }
    },

    async fetchAgents(retries = 8, delayMs = 500) {
      this.loading = true;
      await initAuthToken();
      await this.fetchSkills();
      for (let attempt = 1; attempt <= retries; attempt++) {
        try {
          const res = await api.getAgents();
          if (res && Array.isArray(res.agents) && res.agents.length > 0) {
            this.agents = res.agents;
            // 缓存就绪状态
            for (const ag of this.agents) {
              if (ag.readiness) {
                this.agentReadinessMap[ag.name] = ag.readiness;
              }
            }
            if (!this.currentAgent && this.agents.length > 0) {
              // 默认选中第一个智能体
              this.currentAgent = this.agents[0];
            } else if (this.currentAgent) {
              // 刷新当前智能体对象引用
              const matched = this.agents.find(a => a.name === this.currentAgent.name);
              if (matched) this.currentAgent = matched;
            }
            this.loading = false;
            return;
          }
        } catch (e) {
          console.warn(`[AgentStore] fetchAgents attempt ${attempt} error:`, e.message || e);
          // 微内核服务可能仍在启动握手过程中，等待后重试
          if (attempt < retries) {
            await new Promise(r => setTimeout(r, delayMs));
          }
        }
      }
      this.loading = false;
    },

    selectAgent(agent) {
      this.currentAgent = agent;
      if (agent && agent.name) {
        this.fetchAgentReadiness(agent.name);
      }
    },

    async reloadAgents() {
      const systemStore = useSystemStore();
      try {
        const res = await api.reloadAgents();
        await this.fetchAgents(3, 300);
        systemStore.showToast(`已重新扫描插槽 (${res.count || this.agents.length} 个智能体)`);
      } catch (e) {
        alert('刷新智能体插槽异常: ' + e.message);
      }
    }
  }
});
