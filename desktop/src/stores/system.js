import { defineStore } from 'pinia';
import { api } from '../api/client';
import { useChatStore } from './chat';
import { useAgentStore } from './agent';

export const useSystemStore = defineStore('system', {
  state: () => ({
    systemInfo: null,
    quota: null,
    watcherStatus: null,
    schedules: [],
    suspendedWorkflows: [],
    currentGateData: null,
    autostart: false,
    activeTask: null, // 全局活跃执行流水线状态流
    dropBoxNotice: null, // 投递箱轻量状态条通知: { fileName, filePath, fileSizeMb, subfolder, targetAgent }
    
    // 全局模态窗可见性控制
    modals: {
      settings: false,
      recruit: false,
      workflow: false,
      humanGate: false,
      watcher: false,
      scheduler: false,
      skillsHub: false,
      skillRunner: false,
      agentSkills: false,
      runModal: false,
      quotaExhausted: false,
      lightbox: false,
      agentSettings: false
    },

    // 任务调度执行器数据
    runModalData: {
      agent: null
    },

    // 灯箱图片数据
    lightboxData: {
      url: '',
      title: '',
      filePath: ''
    },

    // 独立技能运行器数据
    skillRunnerData: {
      skill: null
    },

    // 全局轻量 Toast
    toast: {
      show: false,
      message: ''
    },

    // OTA 远程更新与增量热补丁
    updateInfo: null,
    checkingUpdate: false,
    applyingUpdate: false
  }),

  getters: {
    isLicensed: (state) => {
      const gw = state.systemInfo?.gateway;
      if (gw && gw.is_active && gw.mode === 'cloud') return true;
      return state.systemInfo?.licensed ?? false;
    },
    isCustomMode: (state) => {
      const gw = state.systemInfo?.gateway;
      return gw?.mode === 'custom' && Boolean(gw?.custom_has_key || gw?.is_active);
    },
    licenseMessage: (state) => state.systemInfo?.gateway?.status_msg || (state.systemInfo?.license_message || '检测中...'),
    pendingGateCount: (state) => state.suspendedWorkflows?.length || 0,
    hasUpdate: (state) => Boolean(state.updateInfo?.has_update),
    latestVersion: (state) => state.updateInfo?.latest_version || state.systemInfo?.version || '2.5.0',
    quotaPercent: (state) => {
      const q = state.quota || state.systemInfo?.quota || state.systemInfo?.gateway?.quota;
      if (!q) return '100.0';
      const rem = Number(q.remaining);
      const tot = Number(q.total);
      if (!Number.isFinite(rem) || !Number.isFinite(tot) || tot <= 0) return '100.0';
      return Math.max(0, Math.min(100, (rem / tot) * 100)).toFixed(1);
    }
  },

  actions: {
    async fetchSystemInfo(retries = 6, delayMs = 500) {
      for (let attempt = 1; attempt <= retries; attempt++) {
        try {
          const res = await api.getSystemInfo();
          if (res) {
            this.systemInfo = res;
            if (res.quota && !this.quota) {
              this.quota = res.quota;
            }
            return;
          }
        } catch (e) {
          if (attempt < retries) await new Promise(r => setTimeout(r, delayMs));
        }
      }
    },

    async fetchQuota(retries = 6, delayMs = 500) {
      for (let attempt = 1; attempt <= retries; attempt++) {
        try {
          const res = await api.getQuota();
          if (res) {
            this.quota = res;
            return;
          }
        } catch (e) {
          if (attempt < retries) await new Promise(r => setTimeout(r, delayMs));
        }
      }
    },

    async fetchWatcherStatus() {
      try {
        const res = await api.getWatcherStatus();
        this.watcherStatus = res;
      } catch (e) {
        console.warn('获取投递箱状态失败:', e);
      }
    },

    async pollWatcherEvents() {
      try {
        const res = await api.getWatcherEvents(0, false);
        if (res && res.events && res.events.length > 0) {
          const chatStore = useChatStore();
          const agentStore = useAgentStore();
          const processedIds = [];

          for (const ev of res.events) {
            try {
              const evType = ev.event_type;

              // 1. 步骤状态流变动 (task_step_update)
              if (evType === 'task_step_update') {
                if (!this.activeTask || this.activeTask.taskId !== ev.task_id) {
                  this.activeTask = {
                    taskId: ev.task_id,
                    agentName: ev.agent_name || ev.target_agent,
                    title: ev.title || '自动化生产流水线',
                    current_step: ev.current_step,
                    step_index: ev.step_index || 1,
                    steps: ev.steps || [],
                    logs: this.activeTask?.logs || [],
                    status: 'running'
                  };
                } else {
                  this.activeTask.current_step = ev.current_step;
                  this.activeTask.step_index = ev.step_index || this.activeTask.step_index;
                  this.activeTask.steps = ev.steps || this.activeTask.steps;
                  this.activeTask.status = 'running';
                }
              }

              // 2. 实时控制台行日志 (task_log)
              else if (evType === 'task_log') {
                if (!this.activeTask) {
                  this.activeTask = {
                    taskId: ev.task_id || 'task_' + Date.now(),
                    agentName: ev.agent_name || ev.target_agent,
                    title: ev.title || '自动化生产流水线',
                    current_step: '执行中',
                    step_index: 1,
                    steps: [],
                    logs: [],
                    status: 'running'
                  };
                }
                if (ev.log) {
                  this.activeTask.logs.push(ev.log);
                  if (this.activeTask.logs.length > 60) {
                    this.activeTask.logs.shift();
                  }
                }
              }

              // 3. 任务交付完成 (task_finished)
              else if (evType === 'task_finished') {
                if (this.activeTask && (!ev.task_id || this.activeTask.taskId === ev.task_id)) {
                  this.activeTask.status = ev.status === 'success' ? 'completed' : 'failed';
                  this.activeTask.steps = ev.steps || this.activeTask.steps;
                  this.activeTask.total_elapsed = ev.total_elapsed;
                  // 15 秒后自动关闭，期间支持用户在界面右上角手动关闭
                  const curId = this.activeTask.taskId;
                  setTimeout(() => {
                    if (this.activeTask?.taskId === curId && this.activeTask?.status !== 'running') {
                      this.activeTask = null;
                    }
                  }, 15000);
                }
              }

              // 4.1 文件刚拖入校验中 (file_staged)
              else if (evType === 'file_staged') {
                if (ev.file_name) {
                  this.showToast(`📥 投递箱接入新文件: ${ev.file_name}，正在校验...`);
                }
                // 立刻唤起任务卡片，消除感知延迟
                if (!this.activeTask) {
                  this.activeTask = {
                    taskId: 'stage_' + (ev.id || Date.now()),
                    agentName: ev.target_agent || 'omni_sentinel',
                    title: `投递箱文件感知: ${ev.file_name}`,
                    current_step: '文件写入与完整性校验中...',
                    step_index: 0,
                    steps: [
                      { index: 0, name: '投递箱文件捕获与写入稳定期校验', status: 'running' }
                    ],
                    logs: [
                      { time: new Date().toLocaleTimeString(), level: 'INFO', message: `捕获投递文件: ${ev.file_name} (${ev.file_size_mb || 0} MB)` }
                    ],
                    status: 'running'
                  };
                }
              }

              // 4.2 历史已处理稿件友好提示 (file_already_processed) -> 升级为顶部轻量横幅状态条，禁止刷屏污染对话
              else if (evType === 'file_already_processed') {
                this.dropBoxNotice = {
                  fileName: ev.file_name,
                  filePath: ev.file_path,
                  fileSizeMb: ev.file_size_mb,
                  subfolder: ev.subfolder,
                  targetAgent: ev.target_agent || 'omni_sentinel'
                };
              }

              // 4.3 新稿件感知并就绪通知 (file_detected)
              else if (evType === 'file_detected') {
                if (ev.file_name) {
                  this.showToast(`📥 投递箱检测到新稿件: ${ev.file_name}`);
                }
                if (ev.message) {
                  const targetAgent = ev.target_agent || 'omni_sentinel';
                  chatStore.appendSystemEventMessage(targetAgent, ev.message);
                  if (agentStore.currentAgent?.name !== targetAgent) {
                    const match = agentStore.agents.find(a => a.name === targetAgent);
                    if (match) agentStore.selectAgent(match);
                  }
                }
              }

              // 5. 最终交付结果卡片 (task_completed)
              else if (evType === 'task_completed') {
                if (ev.file_name) {
                  this.showToast(`🎉 稿件【${ev.file_name}】自动化交付完成！`);
                }
                if (ev.message) {
                  const targetAgent = ev.target_agent || 'omni_sentinel';
                  chatStore.appendSystemEventMessage(targetAgent, ev.message);
                  if (agentStore.currentAgent?.name !== targetAgent) {
                    const match = agentStore.agents.find(a => a.name === targetAgent);
                    if (match) agentStore.selectAgent(match);
                  }
                }
              }

              // 6. 岗位待招募引导 (need_recruit)
              else if (evType === 'need_recruit') {
                if (ev.file_name) {
                  this.showToast(`📥 投递箱检测到新稿件: ${ev.file_name}`);
                }
                if (ev.message) {
                  chatStore.appendSystemEventMessage('omni_sentinel', ev.message);
                }
              }

              processedIds.push(ev.id);
            } catch (errItem) {
              console.error('[Watcher] 处理单个投递箱事件异常:', ev, errItem);
              processedIds.push(ev.id);
            }
          }

          if (processedIds.length > 0) {
            try {
              await api.consumeWatcherEvents(processedIds);
            } catch (consumeErr) {
              console.warn('[Watcher] 标记事件已消费失败:', consumeErr);
            }
          }
        }
      } catch (e) {
        console.warn('[Watcher] 轮询投递箱事件异常:', e);
      }
    },

    async fetchSchedules() {
      try {
        const res = await api.getSchedules();
        this.schedules = res.tasks || [];
      } catch (e) {
        console.warn('获取计划任务失败:', e);
      }
    },

    async fetchSuspendedWorkflows() {
      try {
        const res = await api.getSuspendedWorkflows();
        this.suspendedWorkflows = res.workflows || [];
        if (this.suspendedWorkflows.length > 0 && !this.modals.humanGate) {
          this.currentGateData = this.suspendedWorkflows[0];
        }
      } catch (e) {
        console.warn('获取未决人机审批断点失败:', e);
      }
    },

    async checkForUpdates(silent = false, simulate = false) {
      this.checkingUpdate = true;
      try {
        const res = await api.checkUpdate(simulate);
        this.updateInfo = res;
        if (res?.has_update) {
          if (!silent) {
            this.showToast(`发现新补丁 v${res.latest_version}！`);
          }
        } else if (!silent) {
          this.showToast(res?.message || '当前已是最新版本');
        }
        return res;
      } catch (err) {
        if (!silent) {
          this.showToast('检查更新异常: ' + err.message);
        }
      } finally {
        this.checkingUpdate = false;
      }
    },

    async applyHotfixUpdate(patchUrl = '') {
      this.applyingUpdate = true;
      try {
        const targetUrl = patchUrl || this.updateInfo?.download_url || '';
        const targetSha256 = this.updateInfo?.sha256 || '';
        const res = await api.applyUpdate({ patch_url: targetUrl, sha256: targetSha256 });
        await this.fetchSystemInfo(3, 300);
        this.updateInfo = null;
        this.showToast(res.message || '热补丁已生效，系统已平滑升级！');
        return res;
      } catch (err) {
        alert('热补丁升级失败: ' + err.message);
        throw err;
      } finally {
        this.applyingUpdate = false;
      }
    },

    openModal(name, data = null) {
      if (name === 'run' || name === 'runModal') {
        if (data) this.runModalData = data;
        this.modals.runModal = true;
        return;
      } else if (name === 'lightbox' && data) {
        this.lightboxData = data;
      } else if (name === 'skillRunner' && data) {
        this.skillRunnerData = data;
      } else if (name === 'humanGate' && data) {
        this.currentGateData = data;
      }
      this.modals[name] = true;
    },

    closeModal(name) {
      this.modals[name] = false;
    },

    showToast(message) {
      this.toast.message = message;
      this.toast.show = true;
      setTimeout(() => {
        this.toast.show = false;
      }, 2200);
    },

    dismissDropBoxNotice() {
      this.dropBoxNotice = null;
    },

    async rerunDropBoxFile(filePath) {
      const chatStore = useChatStore();
      if (!filePath) return;
      this.dropBoxNotice = null;
      // 触发重置指纹并重跑
      try {
        await api.resetWatcherHistory(filePath);
        chatStore.sendMessage(`[EXEC] run ${filePath}`);
      } catch (e) {
        this.showToast('触发重新执行失败: ' + e.message);
      }
    },

    async archiveDropBoxFile(filePath) {
      if (!filePath) return;
      try {
        const res = await api.archiveWatcherFile(filePath);
        if (res.success) {
          this.dropBoxNotice = null;
          this.showToast('✅ 稿件已成功移至归档目录 (.archive)');
        } else {
          this.showToast('归档失败: ' + (res.error || '未知错误'));
        }
      } catch (e) {
        this.showToast('归档请求异常: ' + e.message);
      }
    }
  }
});
