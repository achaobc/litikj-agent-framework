<template>
  <div
    v-if="systemStore.modals.quotaExhausted"
    class="fixed inset-0 bg-slate-900/50 backdrop-blur-xs z-50 flex items-center justify-center select-none"
  >
    <div class="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-lg overflow-hidden animate-scale-up">
      <div class="px-6 py-4.5 border-b border-rose-100 flex items-center justify-between bg-rose-50/70">
        <div class="flex items-center space-x-2.5">
          <span class="text-2xl">⚡</span>
          <div>
            <h3 class="font-bold text-slate-800 text-[15px]">官方体验算力已耗尽 (Token Quota Notice)</h3>
            <p class="text-[11.5px] text-rose-700 font-mono mt-0.5">多轨保护体系生效 · 系统核心功能 100% 永久可用</p>
          </div>
        </div>
        <button
          @click="systemStore.closeModal('quotaExhausted')"
          class="text-slate-400 hover:text-slate-600 text-2xl font-bold leading-none cursor-pointer"
        >
          &times;
        </button>
      </div>

      <div class="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
        <div class="p-3.5 rounded-xl border border-rose-200/80 bg-rose-50/50 text-[13px] text-slate-700 space-y-1">
          <div class="font-semibold text-rose-900 flex items-center space-x-1.5">
            <span>🛡️</span>
            <span>保护性安全熔断</span>
          </div>
          <p class="text-slate-600 leading-relaxed text-[12.5px]">
            您的官方免费体验额度已达上限。您可以选择以下任一方式无缝继续使用：
          </p>
        </div>

        <div class="space-y-2.5">
          <!-- 方案 1: 增购加油包 -->
          <a
            href="https://shop1822790922.v.weidian.com/item.html?itemID=7869615291"
            target="_blank"
            class="p-3.5 rounded-xl border border-slate-200 hover:border-sky-400 bg-white transition hover:shadow-2xs cursor-pointer group flex items-center justify-between block"
          >
            <div class="flex items-center space-x-3">
              <span class="text-2xl">🛒</span>
              <div>
                <div class="text-[13.5px] font-bold text-slate-800 group-hover:text-sky-600 transition">
                  方案 A：订购官方算力加油包
                </div>
                <p class="text-[12px] text-slate-400 mt-0.5">官方专线直连，免配置开箱即用</p>
              </div>
            </div>
            <span class="text-sky-600 font-semibold text-[13px] shrink-0">即充即用 →</span>
          </a>

          <!-- 方案 2: 本地私有 Ollama (0元) -->
          <div
            @click="switchToSettings"
            class="p-3.5 rounded-xl border border-slate-200 hover:border-indigo-400 bg-white transition hover:shadow-2xs cursor-pointer group flex items-center justify-between"
          >
            <div class="flex items-center space-x-3">
              <span class="text-2xl">🦙</span>
              <div>
                <div class="text-[13.5px] font-bold text-slate-800 group-hover:text-indigo-600 transition">
                  方案 B：0元切换本地 Ollama (推荐)
                </div>
                <p class="text-[12px] text-slate-400 mt-0.5">电脑本地运行 Qwen / DeepSeek-R1，纯离线隐私安全</p>
              </div>
            </div>
            <span class="text-indigo-600 font-semibold text-[13px] shrink-0">去配置 →</span>
          </div>
        </div>
      </div>

      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end">
        <button
          @click="systemStore.closeModal('quotaExhausted')"
          class="px-5 py-2 text-[13px] text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-lg transition font-medium cursor-pointer"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useSystemStore } from '../../stores/system';

const systemStore = useSystemStore();

function switchToSettings() {
  systemStore.closeModal('quotaExhausted');
  systemStore.openModal('settings');
}
</script>
