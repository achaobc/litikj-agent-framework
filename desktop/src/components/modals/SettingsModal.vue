<template>
  <div
    v-if="systemStore.modals.settings"
    class="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center select-none p-4"
  >
    <div class="bg-[#f4f5f8] rounded-2xl shadow-2xl border border-slate-200/90 w-full max-w-4xl overflow-hidden animate-scale-up flex flex-col max-h-[88vh]">
      <!-- 模态顶栏 (Clash Verge 风格：通透简约) -->
      <div class="px-6 py-3.5 bg-white border-b border-slate-200/80 flex items-center justify-between shrink-0">
        <div class="flex items-center space-x-2.5">
          <span class="text-xl">⚙️</span>
          <div>
            <h3 class="font-bold text-slate-800 text-[15.5px] leading-tight">系统设置</h3>
            <p class="text-[11px] text-slate-400 mt-0.5">基础系统 · 商业授权 · 模型引擎 · 自动化底座</p>
          </div>
        </div>
        <button
          @click="systemStore.closeModal('settings')"
          class="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition cursor-pointer text-xl leading-none"
        >
          &times;
        </button>
      </div>

      <!-- 模态内容主体：现代双列卡片瀑布流 (2-Column Card Grid) -->
      <div class="p-5 overflow-y-auto flex-1">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
          
          <!-- ================= 卡片 1: 💻 基础系统与设备 ================= -->
          <div class="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-2xs space-y-3">
            <div class="flex items-center justify-between pb-2.5 border-b border-slate-100">
              <span class="text-[13.5px] font-bold text-slate-800 flex items-center space-x-1.5">
                <span>💻</span>
                <span>基础系统与设备</span>
              </span>
              <span class="text-[11px] text-slate-400 font-mono">{{ displayDeviceName }}</span>
            </div>

            <div class="space-y-1">
              <!-- 条目 1: 开机自启 -->
              <div class="flex items-center justify-between py-2 border-b border-slate-50">
                <div>
                  <div class="text-[12.5px] font-medium text-slate-700">开机静默自启</div>
                  <div class="text-[11px] text-slate-400">系统开机时静默常驻托盘守护</div>
                </div>
                <ToggleSwitch
                  v-model="autostartChecked"
                  @change="handleAutostartChange"
                />
              </div>

              <!-- 条目 2: 硬件唯一指纹 -->
              <div class="flex items-center justify-between py-2 border-b border-slate-50">
                <div>
                  <div class="text-[12.5px] font-medium text-slate-700">硬件唯一指纹</div>
                  <div class="text-[11px] text-slate-400">一机一码授权保护，100% 物理隔离</div>
                </div>
                <div class="flex items-center space-x-1.5">
                  <span
                    class="font-mono text-[11px] px-2 py-1 bg-slate-100 text-slate-700 rounded-md select-all border border-slate-200/60 max-w-[145px] truncate"
                    :title="deviceFingerprint || '正在连接微内核...'"
                  >
                    {{ deviceFingerprint || '正在连接微内核...' }}
                  </span>
                  <button
                    @click="copyFingerprint"
                    :disabled="!deviceFingerprint"
                    class="px-2 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-md text-[11px] font-medium transition cursor-pointer shrink-0 disabled:opacity-40"
                  >
                    {{ copiedFingerprint ? '✅' : '复制' }}
                  </button>
                  <button
                    @click="loadCurrentSettings"
                    title="重新获取系统状态"
                    class="p-1 text-slate-400 hover:text-slate-600 transition cursor-pointer text-xs"
                  >
                    🔄
                  </button>
                </div>
              </div>

              <!-- 条目 3: 微内核体检 -->
              <div class="flex items-center justify-between py-2">
                <div>
                  <div class="text-[12.5px] font-medium text-slate-700">底座微内核体检</div>
                  <div class="text-[11px] text-slate-400">评估守护进程与底座负载指标</div>
                </div>
                <button
                  @click="runDiagnosis"
                  :disabled="diagnosing"
                  class="px-2.5 py-1 bg-sky-50 hover:bg-sky-100 text-sky-700 border border-sky-200/80 rounded-lg text-[11.5px] font-medium transition cursor-pointer disabled:opacity-50"
                >
                  {{ diagnosing ? '体检中...' : '即刻体检 ⚡' }}
                </button>
              </div>

              <!-- 体检结果折叠卡片 -->
              <div v-if="diagnosisResult" class="p-2.5 bg-slate-50 rounded-xl border border-slate-200 text-[11px] space-y-1 font-mono text-slate-600 mt-1">
                <div class="flex items-center justify-between font-bold text-slate-700 pb-1 border-b border-slate-200">
                  <span>🩺 体检完成 ({{ diagnosisResult.agent_count || 0 }} 智能体就绪)</span>
                  <span class="px-1.5 py-0.2 rounded text-[10px]" :class="diagnosisResult.licensed ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'">
                    {{ diagnosisResult.licensed ? '已授权' : '审计就绪' }}
                  </span>
                </div>
                <div>• 🧩 装载技能: <strong>{{ diagnosisResult.skills_count || 0 }}</strong> 项</div>
                <div>• 🚀 自启状态: {{ diagnosisResult.autostart ? '已注册' : '未开启' }}</div>
              </div>
            </div>
          </div>

          <!-- ================= 卡片 2: 👑 商业授权与算力 ================= -->
          <div class="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-2xs space-y-3">
            <div class="flex items-center justify-between pb-2.5 border-b border-slate-100">
              <span class="text-[13.5px] font-bold text-slate-800 flex items-center space-x-1.5">
                <span>👑</span>
                <span>商业授权与算力</span>
              </span>
              <a href="https://www.litikj.com" target="_blank" class="text-[11.5px] text-sky-600 hover:underline">
                学员官网 ↗
              </a>
            </div>

            <div class="space-y-1">
              <!-- 条目 1: 当前授权模式 -->
              <div class="flex items-center justify-between py-2 border-b border-slate-50">
                <div>
                  <div class="text-[12.5px] font-medium text-slate-700">授权模式</div>
                  <div class="text-[11px] text-slate-400">官方中枢 / 极客私有 Key</div>
                </div>
                <div>
                  <span
                    v-if="systemStore.isLicensed"
                    class="text-[11px] px-2 py-0.5 rounded-full font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center space-x-1"
                  >
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                    <span>已激活官方授权</span>
                  </span>
                  <span
                    v-else-if="systemStore.isCustomMode"
                    class="text-[11px] px-2 py-0.5 rounded-full font-medium bg-sky-50 text-sky-700 border border-sky-200 flex items-center space-x-1"
                  >
                    <span class="w-1.5 h-1.5 rounded-full bg-sky-500"></span>
                    <span>自定义 Key 模式</span>
                  </span>
                  <span
                    v-else
                    class="text-[11px] px-2 py-0.5 rounded-full font-medium bg-slate-100 text-slate-500 border border-slate-200"
                  >
                    未激活
                  </span>
                </div>
              </div>

              <!-- 条目 2: 激活码输入与绑定 -->
              <div class="py-2 border-b border-slate-50">
                <div class="flex items-center justify-between mb-1.5">
                  <div class="text-[12.5px] font-medium text-slate-700">专属激活卡密 (License Key)</div>
                </div>
                <div class="flex items-center space-x-2">
                  <input
                    type="text"
                    v-model="licenseKey"
                    placeholder="粘贴专属激活卡密 (如 VIP-XXXX-XXXX...)"
                    class="flex-1 text-[12px] px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono outline-none focus:bg-white focus:border-sky-500 transition"
                  />
                  <button
                    @click="saveLicenseOnly"
                    :disabled="saving || !licenseKey.trim()"
                    class="px-3 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-[11.5px] font-medium transition cursor-pointer disabled:opacity-40 shrink-0"
                  >
                    {{ saving ? '激活中' : '绑定' }}
                  </button>
                </div>
              </div>

              <!-- 条目 3: 云端算力余量 -->
              <div class="flex items-center justify-between py-2">
                <div>
                  <div class="text-[12.5px] font-medium text-slate-700">Token 算力池余量</div>
                  <div class="text-[11px] text-slate-400">官方算力池防刷硬隔离</div>
                </div>
                <div class="flex items-center space-x-2">
                  <span class="text-[12px] font-bold text-slate-700 font-mono">{{ systemStore.quotaPercent }}%</span>
                  <div class="w-16 h-2 bg-slate-100 rounded-full overflow-hidden border border-slate-200">
                    <div
                      class="h-full bg-emerald-500 rounded-full transition-all duration-300"
                      :style="{ width: systemStore.quotaPercent + '%' }"
                    ></div>
                  </div>
                  <button
                    @click="refreshQuota"
                    :disabled="refreshingQuota"
                    class="text-slate-400 hover:text-slate-600 transition cursor-pointer text-xs"
                    title="刷新算力余量"
                  >
                    🔄
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- ================= 卡片 3: 🌐 大模型推理引擎 ================= -->
          <div class="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-2xs space-y-3">
            <div class="flex items-center justify-between pb-2.5 border-b border-slate-100">
              <span class="text-[13.5px] font-bold text-slate-800 flex items-center space-x-1.5">
                <span>🌐</span>
                <span>大模型推理引擎</span>
              </span>
              <button
                @click="testConnection"
                :disabled="testingConn"
                class="px-2 py-0.8 rounded-md bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 text-[11px] font-semibold transition cursor-pointer disabled:opacity-50"
              >
                {{ testingConn ? '测速中...' : '⚡ 连通测试' }}
              </button>
            </div>

            <div class="space-y-2">
              <!-- 条目 1: 服务商选择 -->
              <div class="flex items-center justify-between py-1 border-b border-slate-50">
                <span class="text-[12.5px] font-medium text-slate-700">服务商 (Provider)</span>
                <select
                  v-model="selectedProvider"
                  @change="handleProviderChange"
                  class="text-[12px] py-1 px-2.5 bg-slate-50 border border-slate-200 rounded-lg outline-none font-medium text-slate-700 focus:bg-white focus:border-sky-500 cursor-pointer max-w-[200px]"
                >
                  <option value="cloud">官方云端中枢 (卡密免配)</option>
                  <option value="deepseek">🐳 DeepSeek (官方接口)</option>
                  <option value="ollama">🦙 Ollama 本地私有离线</option>
                  <option value="moonshot">🌙 Moonshot / Kimi</option>
                  <option value="openai">🧠 OpenAI (GPT-4o 兼容)</option>
                  <option value="qwen">☁️ 通义千问 (DashScope)</option>
                  <option value="custom">⚙️ 自定义兼容协议</option>
                </select>
              </div>

              <!-- 自定义 API 展开字段 (当非官方云端模式时) -->
              <template v-if="selectedProvider !== 'cloud'">
                <!-- 条目 2: Base URL -->
                <div class="flex items-center justify-between py-1 border-b border-slate-50">
                  <span class="text-[12.5px] font-medium text-slate-700">接口地址 (URL)</span>
                  <input
                    type="text"
                    v-model="customBaseUrl"
                    :placeholder="defaultUrlPlaceholder"
                    class="w-[210px] text-[11.5px] px-2 py-1 bg-slate-50 border border-slate-200 rounded-lg font-mono outline-none focus:bg-white focus:border-sky-500 transition"
                  />
                </div>

                <!-- 条目 3: Model Name -->
                <div class="flex items-center justify-between py-1 border-b border-slate-50">
                  <div class="flex items-center space-x-1">
                    <span class="text-[12.5px] font-medium text-slate-700">模型名称 (Model)</span>
                    <button
                      v-if="selectedProvider === 'ollama'"
                      @click="detectOllamaModels"
                      class="text-[10px] text-sky-600 hover:underline cursor-pointer"
                    >
                      刷新
                    </button>
                  </div>
                  <input
                    type="text"
                    v-model="customModel"
                    list="ollama-models-list"
                    :placeholder="defaultModelPlaceholder"
                    class="w-[210px] text-[11.5px] px-2 py-1 bg-slate-50 border border-slate-200 rounded-lg font-mono outline-none focus:bg-white focus:border-sky-500 transition"
                  />
                  <datalist id="ollama-models-list">
                    <option v-for="m in ollamaModels" :key="m" :value="m" />
                  </datalist>
                </div>

                <!-- 条目 4: API Key -->
                <div class="flex items-center justify-between py-1 border-b border-slate-50">
                  <span class="text-[12.5px] font-medium text-slate-700">
                    API 密钥 <span class="text-[10.5px] text-slate-400 font-normal">({{ selectedProvider === 'ollama' ? '可留空' : '私有' }})</span>
                  </span>
                  <div class="relative w-[210px]">
                    <input
                      :type="showKey ? 'text' : 'password'"
                      v-model="customApiKey"
                      placeholder="sk-..."
                      class="w-full text-[11.5px] px-2 py-1 pr-6 bg-slate-50 border border-slate-200 rounded-lg font-mono outline-none focus:bg-white focus:border-sky-500 transition"
                    />
                    <button
                      type="button"
                      @click="showKey = !showKey"
                      class="absolute right-1.5 top-1 text-slate-400 hover:text-slate-600 text-[10px] cursor-pointer"
                    >
                      {{ showKey ? '🙈' : '👁️' }}
                    </button>
                  </div>
                </div>
              </template>

              <!-- 官方云端模式免配指引提示 -->
              <div
                v-else
                class="p-3 bg-sky-50/80 rounded-xl border border-sky-100/90 text-sky-900 space-y-1"
              >
                <div class="flex items-center space-x-1.5 font-bold text-[12px] text-sky-800">
                  <span>🛡️</span>
                  <span>官方云端中枢 · 免配 API Key</span>
                </div>
                <p class="text-[11px] text-sky-600/90 leading-relaxed">
                  系统直连官方算力集群。凭借上方的【专属激活卡密】自动鉴权，学员完全无需自备或配置任何 API Key。
                </p>
              </div>

              <!-- 连通性测试即时反馈行 -->
              <div
                v-if="testResult"
                class="px-2.5 py-1.5 rounded-lg text-[11px] font-mono flex flex-col space-y-1"
                :class="testResult.success ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-rose-50 text-rose-800 border border-rose-200'"
              >
                <div class="flex items-center justify-between">
                  <span>{{ testResult.success ? '🟢 引擎连通成功' : '🔴 连通探测失败' }}</span>
                  <span v-if="testResult.latency_ms" class="font-bold">{{ testResult.latency_ms }}ms</span>
                </div>
                <div v-if="testResult.message" class="text-[10px] opacity-80 break-all font-sans">
                  {{ testResult.message }}
                </div>
              </div>
            </div>
          </div>

          <!-- ================= 卡片 4: ⚙️ 自动化与底座环境 ================= -->
          <div class="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-2xs space-y-3">
            <div class="flex items-center justify-between pb-2.5 border-b border-slate-100">
              <span class="text-[13.5px] font-bold text-slate-800 flex items-center space-x-1.5">
                <span>⚙️</span>
                <span>自动化与底座环境</span>
              </span>
              <span class="text-[11px] text-slate-400 font-mono">Tauri 2.0 Engine</span>
            </div>

            <div class="space-y-1">
              <!-- 条目 1: 投递箱监听 -->
              <div class="flex items-center justify-between py-2 border-b border-slate-50">
                <div>
                  <div class="text-[12.5px] font-medium text-slate-700">投递箱实时监听</div>
                  <div class="text-[11px] text-slate-400">检测 drop_box/videos 自动触发流水线</div>
                </div>
                <ToggleSwitch v-model="watcherEnabled" />
              </div>

              <!-- 条目 2: 快速直达协议 -->
              <div class="flex items-center justify-between py-2 border-b border-slate-50">
                <div>
                  <div class="text-[12.5px] font-medium text-slate-700">快速直达协议 [EXEC]</div>
                  <div class="text-[11px] text-slate-400">0-Token 极速直达硬规则响应</div>
                </div>
                <ToggleSwitch v-model="fastPathEnabled" />
              </div>

              <!-- 条目 3: 日志级别 -->
              <div class="flex items-center justify-between py-2 border-b border-slate-50">
                <div>
                  <div class="text-[12.5px] font-medium text-slate-700">微内核日志级别</div>
                  <div class="text-[11px] text-slate-400">底座日志记录粒度</div>
                </div>
                <select
                  v-model="logLevel"
                  class="text-[11.5px] py-1 px-2.5 bg-slate-50 border border-slate-200 rounded-lg outline-none font-medium text-slate-700 focus:bg-white focus:border-sky-500 cursor-pointer"
                >
                  <option value="INFO">INFO (推荐)</option>
                  <option value="DEBUG">DEBUG (调试)</option>
                  <option value="WARNING">WARNING (告警)</option>
                </select>
              </div>

              <!-- 条目 4: 固件版本与远程更新 -->
              <div class="flex items-center justify-between py-2">
                <div>
                  <div class="text-[12.5px] font-medium text-slate-700 flex items-center space-x-1.5">
                    <span>底座固件版本</span>
                    <span
                      v-if="systemStore.hasUpdate"
                      class="text-[10px] px-1.5 py-0.2 rounded font-semibold bg-amber-100 text-amber-800 animate-pulse"
                    >
                      发现新补丁
                    </span>
                  </div>
                  <div class="text-[11px] text-slate-400">Single Source of Truth 基准</div>
                </div>
                <div class="flex items-center space-x-2">
                  <span class="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                    v{{ systemStore.systemInfo?.version || '2.5.0' }}
                  </span>
                  <button
                    v-if="systemStore.hasUpdate"
                    @click="systemStore.applyHotfixUpdate()"
                    :disabled="systemStore.applyingUpdate"
                    class="px-2.5 py-1 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-[11px] font-semibold transition cursor-pointer disabled:opacity-50 flex items-center space-x-1 shrink-0 shadow-2xs"
                  >
                    <span>{{ systemStore.applyingUpdate ? '更新中...' : '立即热升级 ⚡' }}</span>
                  </button>
                  <button
                    v-else
                    @click="systemStore.checkForUpdates(false)"
                    :disabled="systemStore.checkingUpdate"
                    class="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-[11px] font-medium transition cursor-pointer disabled:opacity-50 shrink-0"
                  >
                    {{ systemStore.checkingUpdate ? '检查中...' : '检查更新' }}
                  </button>
                </div>
              </div>

              <!-- 条目 5: 缓存重置与出厂清理 -->
              <div class="flex items-center justify-between py-2 border-t border-slate-50 mt-1">
                <div>
                  <div class="text-[12.5px] font-medium text-slate-700">缓存与历史记录重置</div>
                  <div class="text-[11px] text-slate-400">清空所有对话会话缓存与产物文件夹 (恢复纯净开箱态)</div>
                </div>
                <button
                  type="button"
                  @click="triggerFactoryReset"
                  :disabled="clearingStorage"
                  class="px-2.5 py-1 bg-rose-50 hover:bg-rose-100 active:bg-rose-200 text-rose-700 border border-rose-200 rounded-lg text-[11px] font-medium transition cursor-pointer disabled:opacity-50 shrink-0 flex items-center space-x-1"
                >
                  <span>🧹</span>
                  <span>{{ clearingStorage ? '清理中...' : '一键恢复纯净态' }}</span>
                </button>
              </div>

              <!-- 当检测到新版本增量补丁时，呈现的高级折叠卡片 -->
              <div
                v-if="systemStore.updateInfo?.has_update"
                class="p-2.5 bg-gradient-to-br from-amber-50/70 to-orange-50/50 rounded-xl border border-amber-200 text-[11px] space-y-1.5 text-slate-700 mt-1"
              >
                <div class="flex items-center justify-between font-bold text-amber-900 pb-1 border-b border-amber-200/60">
                  <span class="flex items-center space-x-1">
                    <span>🎉</span>
                    <span>{{ systemStore.updateInfo.title || '立体空间增量热补丁就绪' }}</span>
                  </span>
                  <span class="font-mono text-[10.5px] bg-amber-200/80 px-1.5 py-0.2 rounded text-amber-950 font-semibold">
                    ~{{ systemStore.updateInfo.file_size_kb || 128 }} KB
                  </span>
                </div>
                <div class="space-y-0.5 text-[11px] text-slate-600">
                  <div
                    v-for="(note, nIdx) in (systemStore.updateInfo.release_notes || [])"
                    :key="nIdx"
                  >
                    • {{ note }}
                  </div>
                </div>
                <div class="pt-1 flex items-center justify-between text-[10.5px] text-amber-800/80">
                  <span>💡 增量热补丁注入，保护区 100% 隔离，无需重装</span>
                  <button
                    @click="systemStore.applyHotfixUpdate()"
                    :disabled="systemStore.applyingUpdate"
                    class="text-amber-800 font-bold hover:underline cursor-pointer"
                  >
                    {{ systemStore.applyingUpdate ? '正在安装...' : '一键注入生效 ➔' }}
                  </button>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>

      <!-- 模态底栏 -->
      <div class="px-6 py-3 bg-white border-t border-slate-200/80 flex items-center justify-between shrink-0">
        <span class="text-[11.5px] text-slate-400 font-mono">
          Litikj Agent OS v{{ systemStore.systemInfo?.version || '2.5.0' }} · Zero-Config Runtime
        </span>
        <div class="flex items-center space-x-2">
          <button
            @click="systemStore.closeModal('settings')"
            class="px-4 py-1.5 text-[12.5px] text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-xl transition font-medium cursor-pointer"
          >
            关闭
          </button>
          <button
            @click="saveAllSettings"
            :disabled="saving"
            class="px-4.5 py-1.5 text-[12.5px] text-white bg-sky-600 hover:bg-sky-700 rounded-xl transition font-medium shadow-xs flex items-center space-x-1 cursor-pointer disabled:opacity-50"
          >
            <span>{{ saving ? '保存中...' : '保存配置' }}</span>
            <span>✨</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue';
import { useSystemStore } from '../../stores/system';
import { useChatStore } from '../../stores/chat';
import { api } from '../../api/client';
import ToggleSwitch from '../common/ToggleSwitch.vue';

const systemStore = useSystemStore();
const chatStore = useChatStore();
const clearingStorage = ref(false);

// 基础信息 (通过 computed 响应式穿透 Pinia 全局状态树，确保后台一就绪前端立即秒出)
const deviceName = ref('');
const displayDeviceName = computed(() => {
  return deviceName.value || systemStore.systemInfo?.device?.name || 'Windows PC';
});

const localFingerprint = ref('');
const deviceFingerprint = computed(() => {
  return localFingerprint.value || systemStore.systemInfo?.device?.fingerprint || '';
});
const copiedFingerprint = ref(false);
const licenseKey = ref('');
const autostartChecked = ref(false);

// 自动化与环境配置
const watcherEnabled = ref(true);
const fastPathEnabled = ref(true);
const logLevel = ref('INFO');

// 大模型服务商与配置
const selectedProvider = ref('cloud');
const customBaseUrl = ref('');
const customModel = ref('');
const customApiKey = ref('');
const showKey = ref(false);

// 连通性测试与 Ollama 检测
const testingConn = ref(false);
const testResult = ref(null);
const ollamaAvailable = ref(false);
const ollamaModels = ref(['qwen2.5:7b', 'deepseek-r1:7b', 'llama3.1:8b']);

// 状态标志
const saving = ref(false);
const refreshingQuota = ref(false);
const diagnosing = ref(false);
const diagnosisResult = ref(null);

// 预设地址与模型映射
const providerPresets = {
  cloud: { url: '', model: '' },
  ollama: { url: 'http://localhost:11434/v1', model: 'qwen2.5:7b' },
  deepseek: { url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  moonshot: { url: 'https://api.moonshot.cn/v1', model: 'moonshot-v1-8k' },
  openai: { url: 'https://api.openai.com/v1', model: 'gpt-4o' },
  qwen: { url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'qwen-plus' },
  custom: { url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' }
};

const defaultUrlPlaceholder = computed(() => {
  return providerPresets[selectedProvider.value]?.url || 'https://api.deepseek.com/v1';
});

const defaultModelPlaceholder = computed(() => {
  return providerPresets[selectedProvider.value]?.model || 'deepseek-chat';
});

// 数据统一同步函数
function applySystemData(sys) {
  if (!sys) return;
  if (sys.device) {
    if (sys.device.name) deviceName.value = sys.device.name;
    if (sys.device.fingerprint) localFingerprint.value = sys.device.fingerprint;
  }
  licenseKey.value = sys.gateway?.license_masked ? '' : (sys.license_key || '');

  const gw = sys.gateway || {};
  if (gw.mode === 'custom') {
    selectedProvider.value = gw.custom_provider || 'custom';
    customBaseUrl.value = gw.custom_base_url || '';
    customModel.value = gw.custom_model || '';
  } else {
    selectedProvider.value = 'cloud';
  }

  if (sys.watcher) {
    watcherEnabled.value = sys.watcher.enabled !== false;
  }
  if (sys.fast_path) {
    fastPathEnabled.value = sys.fast_path.enabled !== false;
  }
  if (sys.system?.log_level) {
    logLevel.value = sys.system.log_level;
  }
}

// 响应式监听 1：Pinia 全局状态树更新即刻自动同步
watch(
  () => systemStore.systemInfo,
  (newVal) => {
    if (newVal) applySystemData(newVal);
  },
  { immediate: true, deep: true }
);

// 响应式监听 2：每次用户点击左下角【系统设置】打开弹窗时，强制执行最新拉取与重试
watch(
  () => systemStore.modals.settings,
  async (isOpen) => {
    if (isOpen) {
      await loadCurrentSettings();
    }
  }
);

onMounted(async () => {
  await loadCurrentSettings();
});

async function loadCurrentSettings() {
  // 1. 优先从已有 Store 瞬间回填（0ms 秒开）
  if (systemStore.systemInfo) {
    applySystemData(systemStore.systemInfo);
  }

  // 2. 发起带自动重试的微内核状态同步（多轮等待后台就绪）
  try {
    await systemStore.fetchSystemInfo(5, 400);
    if (systemStore.systemInfo) {
      applySystemData(systemStore.systemInfo);
    }
    const auto = await api.getAutostart();
    if (auto) autostartChecked.value = auto.enabled || false;
  } catch (e) {
    console.warn('读取设置失败:', e);
  }
}

function handleProviderChange() {
  testResult.value = null;
  const p = selectedProvider.value;
  if (p === 'cloud') {
    customBaseUrl.value = '';
    customModel.value = '';
  } else {
    const preset = providerPresets[p];
    if (preset) {
      if (!customBaseUrl.value || Object.values(providerPresets).some(x => x.url === customBaseUrl.value)) {
        customBaseUrl.value = preset.url;
      }
      if (!customModel.value || Object.values(providerPresets).some(x => x.model === customModel.value)) {
        customModel.value = preset.model;
      }
    }
    if (p === 'ollama') {
      detectOllamaModels();
    }
  }
}

async function detectOllamaModels() {
  try {
    const res = await api.detectOllama();
    ollamaAvailable.value = res.available;
    if (res.models && res.models.length > 0) {
      ollamaModels.value = res.models;
      if (!customModel.value) {
        customModel.value = res.models[0];
      }
      systemStore.showToast(`🦙 检测到 ${res.models.length} 个 Ollama 本地模型`);
    }
  } catch {}
}

async function testConnection() {
  testingConn.value = true;
  testResult.value = null;
  try {
    const mode = selectedProvider.value === 'cloud' ? 'cloud' : (selectedProvider.value === 'ollama' ? 'ollama' : 'custom');
    const res = await api.testLlmConnection({
      mode,
      base_url: customBaseUrl.value || defaultUrlPlaceholder.value,
      api_key: customApiKey.value,
      model: customModel.value || defaultModelPlaceholder.value
    });
    testResult.value = res;
    if (res.success) {
      systemStore.showToast(`连通成功！延时 ${res.latency_ms || 0}ms`);
    }
  } catch (err) {
    testResult.value = {
      success: false,
      message: err.message || '网络连接超时或接口无法访问'
    };
  } finally {
    testingConn.value = false;
  }
}

async function saveLicenseOnly() {
  if (!licenseKey.value.trim()) return;
  saving.value = true;
  try {
    const res = await api.saveSettings({ license_key: licenseKey.value.trim(), mode: 'cloud' });
    selectedProvider.value = 'cloud';
    await systemStore.fetchSystemInfo();
    await systemStore.fetchQuota();
    if (res.valid) {
      systemStore.showToast(res.message || '🎉 商业授权已成功联网激活！');
    } else {
      systemStore.showToast(res.message || '卡密已保存，正在校验中...');
    }
  } catch (err) {
    alert('激活异常: ' + err.message);
  } finally {
    saving.value = false;
  }
}

async function saveAllSettings() {
  saving.value = true;
  try {
    const payload = {};
    if (licenseKey.value.trim()) {
      payload.license_key = licenseKey.value.trim();
    }
    if (selectedProvider.value === 'cloud') {
      payload.mode = 'cloud';
    } else {
      payload.mode = 'custom';
      payload.custom_provider = selectedProvider.value;
      payload.custom_base_url = customBaseUrl.value || defaultUrlPlaceholder.value;
      payload.custom_model = customModel.value || defaultModelPlaceholder.value;
      if (customApiKey.value.trim()) {
        payload.custom_api_key = customApiKey.value.trim();
      }
    }

    const res = await api.saveSettings(payload);
    await systemStore.fetchSystemInfo();
    await systemStore.fetchQuota();
    systemStore.showToast(res.message || '配置已成功更新并热重载！');
    systemStore.closeModal('settings');
  } catch (err) {
    alert('保存设置失败: ' + err.message);
  } finally {
    saving.value = false;
  }
}

async function refreshQuota() {
  refreshingQuota.value = true;
  try {
    await api.refreshQuota();
    await systemStore.fetchQuota();
    systemStore.showToast('算力余量已同步');
  } catch (err) {
    systemStore.showToast('刷新失败: ' + err.message);
  } finally {
    refreshingQuota.value = false;
  }
}

async function handleAutostartChange() {
  try {
    await api.setAutostart(autostartChecked.value);
    systemStore.showToast(autostartChecked.value ? '已开启开机自启守护' : '已关闭开机自启');
  } catch (err) {
    alert('设置开机自启异常: ' + err.message);
  }
}

async function runDiagnosis() {
  diagnosing.value = true;
  try {
    const res = await api.runDiagnosis();
    diagnosisResult.value = res;
    if (res?.device_fingerprint) {
      localFingerprint.value = res.device_fingerprint;
    }
    if (res?.device_name) {
      deviceName.value = res.device_name;
    }
    systemStore.showToast('微内核体检完成，各项指标正常！');
  } catch (err) {
    alert('体检失败: ' + err.message);
  } finally {
    diagnosing.value = false;
  }
}

function copyFingerprint() {
  if (!deviceFingerprint.value) return;
  navigator.clipboard.writeText(deviceFingerprint.value);
  copiedFingerprint.value = true;
  systemStore.showToast('设备指纹已复制到剪贴板');
  setTimeout(() => {
    copiedFingerprint.value = false;
  }, 2000);
}

async function triggerFactoryReset() {
  if (confirm('确认清空全系统所有智能体的对话历史，并清空本地产物目录吗？该操作将恢复为初次开箱纯净态。')) {
    clearingStorage.value = true;
    try {
      chatStore.resetAllConversationsAndStorage();
      await api.clearWorkspaceOutputs();
      systemStore.showToast('工作区产物与历史记录已彻底清空');
    } catch (e) {
      systemStore.showToast('清理产物异常: ' + e.message);
    } finally {
      clearingStorage.value = false;
    }
  }
}
</script>
