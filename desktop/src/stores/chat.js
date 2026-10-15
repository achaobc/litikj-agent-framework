import { defineStore } from 'pinia';
import { api } from '../api/client';
import { useAgentStore } from './agent';
import { useSystemStore } from './system';

const STORAGE_KEY = 'liti_agent_sessions_v3';
const LEGACY_STORAGE_KEY = 'liti_agent_conversations_v2';

export const useChatStore = defineStore('chat', {
  state: () => ({
    // 数据模型: { [agentName]: Array<{ id, title, createdAt, updatedAt, messages: [] }> }
    sessions: {},
    // 记录各智能体当前选中的会话 ID: { [agentName]: string }
    currentSessionId: {},
    sending: false
  }),

  getters: {
    // 当前智能体的所有会话列表 (按更新时间倒序)
    currentAgentSessions: (state) => {
      const agentStore = useAgentStore();
      const agent = agentStore.currentAgent;
      if (!agent) return [];
      const list = state.sessions[agent.name] || [];
      return [...list].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0));
    },

    // 当前智能体当前选中的会话对象
    currentSession: (state) => {
      const agentStore = useAgentStore();
      const agent = agentStore.currentAgent;
      if (!agent) return null;
      const list = state.sessions[agent.name] || [];
      const activeId = state.currentSessionId[agent.name];
      if (activeId) {
        const found = list.find(s => s.id === activeId);
        if (found) return found;
      }
      return list[0] || null;
    },

    // 当前会话的消息流
    currentMessages: (state) => {
      const agentStore = useAgentStore();
      const agent = agentStore.currentAgent;
      if (!agent) return [];
      const list = state.sessions[agent.name] || [];
      const activeId = state.currentSessionId[agent.name];
      const sess = (activeId ? list.find(s => s.id === activeId) : null) || list[0];
      return sess ? (sess.messages || []) : [];
    },

    // 当前会话的标题
    currentSessionTitle: (state) => {
      const agentStore = useAgentStore();
      const agent = agentStore.currentAgent;
      if (!agent) return '新会话';
      const list = state.sessions[agent.name] || [];
      const activeId = state.currentSessionId[agent.name];
      const sess = (activeId ? list.find(s => s.id === activeId) : null) || list[0];
      return sess?.title || '新会话';
    }
  },

  actions: {
    initStorage() {
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          this.sessions = parsed.sessions || {};
          this.currentSessionId = parsed.currentSessionId || {};
          return;
        }

        // 平滑迁移旧版 localStorage 数据 (v2 扁平结构: { [agentName]: [messages] })
        const legacyRaw = localStorage.getItem(LEGACY_STORAGE_KEY);
        if (legacyRaw) {
          const legacyData = JSON.parse(legacyRaw);
          const migratedSessions = {};
          const migratedActive = {};

          Object.keys(legacyData).forEach(agentName => {
            const msgs = legacyData[agentName] || [];
            if (msgs.length > 0) {
              const sessId = 'sess_migrated_' + Date.now();
              const firstUserMsg = msgs.find(m => m.role === 'user');
              const title = firstUserMsg ? firstUserMsg.content.slice(0, 18) : '历史归档会话';
              migratedSessions[agentName] = [
                {
                  id: sessId,
                  title: title,
                  createdAt: new Date().toLocaleString(),
                  updatedAt: Date.now(),
                  messages: msgs
                }
              ];
              migratedActive[agentName] = sessId;
            }
          });

          this.sessions = migratedSessions;
          this.currentSessionId = migratedActive;
          this.saveStorage();
          console.log('✅ 成功将旧版对话记录迁移至 v3 多会话模型');
        }
      } catch (e) {
        console.warn('读取本地对话会话池失败:', e);
        this.sessions = {};
        this.currentSessionId = {};
      }
    },

    saveStorage() {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
          sessions: this.sessions,
          currentSessionId: this.currentSessionId
        }));
      } catch (e) {
        console.warn('持久化对话会话池失败:', e);
      }
    },

    // 保证当前智能体拥有至少一个活跃的会话对象
    ensureActiveSession(agentName) {
      if (!agentName) return null;
      if (!this.sessions[agentName]) {
        this.sessions[agentName] = [];
      }

      const activeId = this.currentSessionId[agentName];
      let sess = this.sessions[agentName].find(s => s.id === activeId);

      if (!sess) {
        if (this.sessions[agentName].length > 0) {
          sess = this.sessions[agentName][0];
          this.currentSessionId[agentName] = sess.id;
        } else {
          sess = this.createNewSession(agentName, false);
        }
      }
      return sess;
    },

    // 注入系统/事件投递消息 (例如投递箱感知、自动化后台任务推送)
    appendSystemEventMessage(agentName, content) {
      if (!content) return;
      const targetAgent = agentName || 'omni_sentinel';
      const sess = this.ensureActiveSession(targetAgent);
      if (!sess) return;
      if (!sess.messages) sess.messages = [];
      sess.messages.push({
        id: 'msg_evt_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4),
        role: 'assistant',
        content: content,
        timestamp: new Date().toLocaleTimeString(),
        isEvent: true
      });
      sess.updatedAt = Date.now();
      this.saveStorage();
    },

    // 兼容快捷方法：向当前活跃会话安全追加消息
    addMessage(msg = {}) {
      const agentStore = useAgentStore();
      const targetAgent = agentStore.currentAgent?.name || 'omni_sentinel';
      const sess = this.ensureActiveSession(targetAgent);
      if (!sess) return;
      if (!sess.messages) sess.messages = [];
      sess.messages.push({
        id: 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4),
        role: msg.role || 'system',
        content: msg.content || '',
        timestamp: new Date().toLocaleTimeString(),
        ...msg
      });
      sess.updatedAt = Date.now();
      this.saveStorage();
    },

    // 创建全新会话 (核心逻辑)
    createNewSession(targetAgentName, showToast = true) {
      const agentStore = useAgentStore();
      const systemStore = useSystemStore();
      const agent = targetAgentName
        ? (agentStore.agents.find(a => a.name === targetAgentName) || { name: targetAgentName, display_name: targetAgentName })
        : agentStore.currentAgent;

      if (!agent) {
        if (showToast) systemStore.showToast('请先选择目标智能体');
        return null;
      }

      const agentName = agent.name;
      if (!this.sessions[agentName]) {
        this.sessions[agentName] = [];
      }

      // 如果当前智能体的活跃会话已经是全新的空白会话（没有发过消息），直接复用，避免产生大量空白无用会话
      const activeId = this.currentSessionId[agentName];
      const currentActive = activeId
        ? this.sessions[agentName].find(s => s.id === activeId)
        : (this.sessions[agentName][0] || null);
      if (currentActive && (!currentActive.messages || currentActive.messages.length === 0)) {
        if (showToast) {
          systemStore.showToast(`已在当前全新会话视界`);
        }
        this.currentSessionId[agentName] = currentActive.id;
        return currentActive;
      }

      const newSessId = 'sess_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
      const newSession = {
        id: newSessId,
        title: '新会话',
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        updatedAt: Date.now(),
        messages: []
      };

      // 放入会话池首部
      this.sessions[agentName].unshift(newSession);
      this.currentSessionId[agentName] = newSessId;
      this.saveStorage();

      if (showToast) {
        systemStore.showToast(`已为【${agent.display_name || agent.name}】开启新会话`);
      }
      return newSession;
    },

    // 切换至指定历史会话
    switchSession(sessionId) {
      const agentStore = useAgentStore();
      const agent = agentStore.currentAgent;
      if (!agent) return;
      const list = this.sessions[agent.name] || [];
      const found = list.find(s => s.id === sessionId);
      if (found) {
        this.currentSessionId[agent.name] = sessionId;
        this.saveStorage();
        useSystemStore().showToast(`已切换至: ${found.title}`);
      }
    },

    // 删除单个历史会话
    deleteSession(sessionId) {
      const agentStore = useAgentStore();
      const agent = agentStore.currentAgent;
      if (!agent) return;
      const list = this.sessions[agent.name] || [];
      const idx = list.findIndex(s => s.id === sessionId);
      if (idx !== -1) {
        list.splice(idx, 1);
        // 如果删除的是当前处于激活状态的会话，自动切换到下一个或自动新建
        if (this.currentSessionId[agent.name] === sessionId) {
          if (list.length > 0) {
            this.currentSessionId[agent.name] = list[0].id;
          } else {
            this.createNewSession(agent.name, false);
          }
        }
        this.saveStorage();
        useSystemStore().showToast('已删除会话记录');
      }
    },

    // 发送消息
    async sendMessage(prompt) {
      if (!prompt || !prompt.trim() || this.sending) return;
      const agentStore = useAgentStore();
      const systemStore = useSystemStore();
      const agent = agentStore.currentAgent;
      if (!agent) {
        alert('请先在左侧选择要对话的智能体');
        return;
      }

      const agentName = agent.name;
      const sess = this.ensureActiveSession(agentName);
      if (!sess) return;

      const userText = prompt.trim();

      // 如果当前标题为初始的“新会话”，且这是第一条提问，自动提取作为标题
      if ((!sess.title || sess.title === '新会话') && sess.messages.length === 0) {
        sess.title = userText.length > 20 ? userText.slice(0, 20) + '...' : userText;
      }

      // 插入用户消息
      sess.messages.push({
        role: 'user',
        content: userText,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      });
      sess.updatedAt = Date.now();
      this.saveStorage();

      this.sending = true;
      try {
        // 构建上下文历史 (最近 10 轮)
        const historyPayload = sess.messages
          .slice(-10)
          .map(m => ({ role: m.role, content: m.content }));

        const res = await api.sendChat(agentName, userText, historyPayload);
        const reply = res.reply || res.response || res.content || '智能体未返回有效内容';

        // 插入助理回复
        sess.messages.push({
          role: 'assistant',
          content: reply,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        });
        sess.updatedAt = Date.now();
        this.saveStorage();

        // 触发算力与审批断点刷新
        systemStore.fetchQuota();
        systemStore.fetchSuspendedWorkflows();
      } catch (err) {
        const errorMsg = err.message || '未知通信异常';
        sess.messages.push({
          role: 'assistant',
          content: `⚠️ **智能体响应异常**: ${errorMsg}`,
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        });
        sess.updatedAt = Date.now();
        this.saveStorage();

        if (errorMsg.includes('QUOTA') || errorMsg.includes('算力') || errorMsg.includes('额度')) {
          systemStore.openModal('quotaExhausted');
        }
      } finally {
        this.sending = false;
      }
    },

    // 清空当前活跃会话
    clearCurrentConversation() {
      const agentStore = useAgentStore();
      const agent = agentStore.currentAgent;
      if (!agent) return;
      const sess = this.currentSession;
      if (!sess) return;

      if (confirm(`确认清空当前会话【${sess.title}】的对话历史吗？`)) {
        sess.messages = [];
        sess.title = '新会话';
        sess.updatedAt = Date.now();
        this.saveStorage();
        useSystemStore().showToast('当前会话已重置');
      }
    },

    // 清空当前智能体的所有历史会话
    clearAllSessionsForCurrentAgent() {
      const agentStore = useAgentStore();
      const agent = agentStore.currentAgent;
      if (!agent) return;

      if (confirm(`确认清空智能体【${agent.display_name || agent.name}】的全部历史会话吗？`)) {
        this.sessions[agent.name] = [];
        this.createNewSession(agent.name, false);
        this.saveStorage();
        useSystemStore().showToast('全部历史会话已清空');
      }
    },

    // 彻底出厂重置：清空全系统所有智能体会话记录与本地存储
    resetAllConversationsAndStorage() {
      this.sessions = {};
      this.currentSessionId = {};
      try {
        localStorage.removeItem(STORAGE_KEY);
        localStorage.removeItem(LEGACY_STORAGE_KEY);
      } catch (e) {
        // ignore
      }
      const agentStore = useAgentStore();
      if (agentStore.currentAgent) {
        this.createNewSession(agentStore.currentAgent.name, false);
      }
      useSystemStore().showToast('已彻底清空所有智能体会话缓存');
    },

    // 导出当前会话为 Markdown
    exportMarkdown() {
      const agentStore = useAgentStore();
      const agent = agentStore.currentAgent;
      if (!agent) return;
      const msgs = this.currentMessages;
      if (msgs.length === 0) {
        alert('当前没有可导出的对话内容');
        return;
      }

      const sess = this.currentSession;
      const title = sess?.title || '会话记录';

      let md = `# 与智能体【${agent.display_name || agent.name}】的会话: ${title}\n\n`;
      md += `*导出时间: ${new Date().toLocaleString()}*\n\n---\n\n`;

      msgs.forEach(m => {
        const sender = m.role === 'user' ? '用户' : `${agent.display_name || agent.name}`;
        md += `### 👤 ${sender} (${m.time || ''})\n\n${m.content}\n\n---\n\n`;
      });

      const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chat_${agent.name}_${Date.now()}.md`;
      a.click();
      URL.revokeObjectURL(url);
    }
  }
});
