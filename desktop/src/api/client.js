// ========================================================
// desktop/src/api/client.js
// 立体空间智能体系统 · 现代化统一 API 客户端
// ========================================================

let baseUrl = 'http://127.0.0.1:8765';
let authToken = '';

export function setBaseUrl(url) {
  baseUrl = url.replace(/\/+$/, '');
}

export function getBaseUrl() {
  return baseUrl;
}

export function setAuthToken(token) {
  authToken = token || '';
}

export function getAuthToken() {
  if (authToken) return authToken;
  if (typeof window !== 'undefined' && window.__LITIKJ_API_TOKEN__) {
    authToken = window.__LITIKJ_API_TOKEN__;
    return authToken;
  }
  return '';
}

export async function initAuthToken() {
  if (authToken) return authToken;
  if (typeof window !== 'undefined' && window.__LITIKJ_API_TOKEN__) {
    authToken = window.__LITIKJ_API_TOKEN__;
    return authToken;
  }
  // 优先通过 Tauri IPC 原生指令通道获取会话私密 Token (安全隔离，无网络暴露面)
  if (typeof window !== 'undefined' && (window.__TAURI_INTERNALS__ || window.__TAURI__)) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      const t = await invoke('get_session_token');
      if (t) {
        authToken = t;
        window.__LITIKJ_API_TOKEN__ = t;
        return authToken;
      }
    } catch (e) {
      console.warn('[client] 获取 Tauri Session Token 失败:', e);
    }
  }
  if (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_LITIKJ_API_TOKEN) {
    authToken = import.meta.env.VITE_LITIKJ_API_TOKEN;
    return authToken;
  }
  return '';
}

async function request(endpoint, options = {}) {
  const url = `${baseUrl}${endpoint}`;
  let token = getAuthToken();
  if (!token && endpoint !== '/api/auth/token' && endpoint !== '/api/health') {
    token = await initAuthToken();
  }
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'X-Agent-OS-Token': token } : {}),
    ...(options.headers || {})
  };

  const response = await fetch(url, {
    ...options,
    headers
  });

  if (!response.ok) {
    const errorText = await response.text();
    let errorJson;
    try {
      errorJson = JSON.parse(errorText);
    } catch {
      // ignore
    }
    const message = errorJson?.error || errorJson?.message || `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(message);
  }

  return response.json();
}

export const api = {
  // 1. 系统配置、商业授权与底座诊断
  getSystemInfo: () => request('/api/system'),
  getQuota: () => request('/api/quota'),
  refreshQuota: () => request('/api/quota/refresh', { method: 'POST' }),
  rechargeQuota: (points = 500000) => request('/api/quota/recharge', { method: 'POST', body: JSON.stringify({ points }) }),
  saveSettings: (payload) => request('/api/system/license', { method: 'POST', body: JSON.stringify(payload) }),
  testLlmConnection: (payload) => request('/api/llm/test-connection', { method: 'POST', body: JSON.stringify(payload) }),
  detectOllama: () => request('/api/llm/detect-ollama'),
  runDiagnosis: () => request('/api/system/diagnose', { method: 'POST' }),
  getAutostart: () => request('/api/autostart'),
  setAutostart: (enabled) => request('/api/autostart', { method: 'POST', body: JSON.stringify({ enabled }) }),
  checkUpdate: (simulate = false) => request(`/api/system/update/check${simulate ? '?simulate=true' : ''}`),
  applyUpdate: (payload = {}) => request('/api/system/update/apply', { method: 'POST', body: JSON.stringify(payload) }),

  // 2. 智能体资产与生命周期
  getAgents: () => request('/api/agents'),
  reloadAgents: () => request('/api/agents/reload', { method: 'POST' }),
  recruitAgent: (payload) => request('/api/agents/create', { method: 'POST', body: JSON.stringify(payload) }),
  deleteAgent: (agentId) => request('/api/agents/delete', { method: 'POST', body: JSON.stringify({ agent_id: agentId }) }),
  getMarketAgents: () => request('/api/market/agents'),
  recruitMarketAgent: (agentId) => request('/api/market/agents/recruit', { method: 'POST', body: JSON.stringify({ agent_id: agentId }) }),
  dismissMarketAgent: (agentId) => request('/api/market/agents/dismiss', { method: 'POST', body: JSON.stringify({ agent_id: agentId }) }),
  getAgentConfig: (agentName) => request(`/api/agent/${encodeURIComponent(agentName)}/config`),
  updateAgentConfig: (agentName, updates) =>
    request(`/api/agent/${encodeURIComponent(agentName)}/config`, {
      method: 'POST',
      body: JSON.stringify({ updates })
    }),
  getAgentReadiness: (agentName) => request(`/api/agent/${encodeURIComponent(agentName)}/readiness`),
  healAgent: (agentName) => request(`/api/agent/${encodeURIComponent(agentName)}/heal`, { method: 'POST' }),

  // 3. 对话与单任务调度执行
  sendChat: (agentName, prompt, history = []) => {
    const messages = [...history];
    if (prompt) {
      messages.push({ role: 'user', content: prompt });
    }
    return request('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ agent_name: agentName, messages })
    });
  },
  runAgentTask: (payload) => request('/api/run', { method: 'POST', body: JSON.stringify(payload) }),

  // 4. 技能卡带背包与云端市场
  getSkills: () => request('/api/skills'),
  getMarketSkills: () => request('/api/market/skills'),
  installMarketSkill: (skillId) => request('/api/market/install', { method: 'POST', body: JSON.stringify({ skill_id: skillId }) }),
  uninstallMarketSkill: (skillId, origin = '') => request('/api/market/uninstall', { method: 'POST', body: JSON.stringify({ skill_id: skillId, origin }) }),
  runSkill: (skillId, params = {}) =>
    request('/api/skills/run', {
      method: 'POST',
      body: JSON.stringify({ skill_id: skillId, params })
    }),

  // 5. 多智能体接力流水线与人机协同审批
  getWorkflows: () => request('/api/workflows'),
  getMarketWorkflows: () => request('/api/market/workflows'),
  installMarketWorkflow: (workflowId) =>
    request('/api/market/workflows/install', { method: 'POST', body: JSON.stringify({ workflow_id: workflowId }) }),
  installMarketWorkflowDeps: (workflowId) =>
    request('/api/market/workflows/install-deps', { method: 'POST', body: JSON.stringify({ workflow_id: workflowId }) }),
  uninstallMarketWorkflow: (workflowId) =>
    request('/api/market/workflows/uninstall', { method: 'POST', body: JSON.stringify({ workflow_id: workflowId }) }),
  getSuspendedWorkflows: () => request('/api/workflow/suspended'),
  runWorkflow: (workflowId, topic, dryRun = true) =>
    request('/api/workflow/run', {
      method: 'POST',
      body: JSON.stringify({ workflow_id: workflowId, topic, dry_run: dryRun })
    }),
  resumeHumanGate: (workflowId, choice, customTopic = '') =>
    request('/api/workflow/resume', {
      method: 'POST',
      body: JSON.stringify({ workflow_id: workflowId, choice, custom_topic: customTopic })
    }),

  // 6. 定时计划任务守护 (Scheduler Daemon)
  getSchedules: (params = '') => request(`/api/schedules${params ? '?' + params : ''}`),
  createSchedule: (payload) => request('/api/schedules', { method: 'POST', body: JSON.stringify(payload) }),
  toggleSchedule: (taskId, enabled) => request('/api/schedules/toggle', { method: 'POST', body: JSON.stringify({ task_id: taskId, enabled }) }),
  runScheduleNow: (taskId) => request('/api/schedules/run_now', { method: 'POST', body: JSON.stringify({ task_id: taskId }) }),
  deleteSchedule: (taskId) => request('/api/schedules/delete', { method: 'POST', body: JSON.stringify({ task_id: taskId }) }),

  // 7. 投递箱监听守护 (Watcher Daemon)
  getWatcherStatus: () => request('/api/watcher/status'),
  getWatcherEvents: (since = 0, autoConsume = true) =>
    request(`/api/watcher/events?since=${since}&auto_consume=${autoConsume ? 1 : 0}`),
  consumeWatcherEvents: (eventIds) =>
    request('/api/watcher/events/consume', { method: 'POST', body: JSON.stringify({ event_ids: eventIds }) }),
  resetWatcherHistory: (filePath = '') =>
    request('/api/watcher/reset', { method: 'POST', body: JSON.stringify({ path: filePath }) }),
  archiveWatcherFile: (filePath) =>
    request('/api/watcher/archive', { method: 'POST', body: JSON.stringify({ path: filePath }) }),

  // 8. 本地文件系统唤起与工作区清理
  openOutputs: () => request('/api/system/open-outputs', { method: 'POST' }).catch(() => {
    window.open(`${baseUrl}/outputs/`, '_blank');
  }),
  openPath: (path, mode = 'open_file') =>
    request('/api/system/open-outputs', { method: 'POST', body: JSON.stringify({ path, action: mode }) }),
  clearWorkspaceOutputs: () => request('/api/system/clear-workspace-outputs', { method: 'POST' }),

  // 9. B站物料包与草稿箱
  getBiliPackages: () => request('/api/bili/packages'),
  uploadBiliDraft: (packageId, chosenTitle = '') =>
    request('/api/bili/upload-draft', { method: 'POST', body: JSON.stringify({ package_id: packageId, chosen_title: chosenTitle }) }),
  openBiliPackageFolder: (bundleDir) =>
    request('/api/bili/open-package', { method: 'POST', body: JSON.stringify({ bundle_dir: bundleDir }) }),

  // 10. 环境自动化装配
  installWhisperEnv: () => request('/api/system/env/install-whisper', { method: 'POST' })
};
