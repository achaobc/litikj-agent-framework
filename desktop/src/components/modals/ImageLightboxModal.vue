<template>
  <div
    v-if="systemStore.modals.lightbox"
    @click="systemStore.closeModal('lightbox')"
    class="fixed inset-0 bg-slate-950/85 backdrop-blur-md z-60 flex items-center justify-center cursor-zoom-out select-none"
  >
    <div class="relative max-w-[90vw] max-h-[90vh] flex flex-col items-center animate-scale-up" @click.stop>
      <button
        @click="systemStore.closeModal('lightbox')"
        class="absolute -top-12 right-0 text-white/80 hover:text-white text-3xl font-bold transition cursor-pointer leading-none"
      >
        &times;
      </button>
      <img
        :src="systemStore.lightboxData.url"
        :alt="systemStore.lightboxData.title"
        class="max-w-[85vw] max-h-[80vh] object-contain rounded-2xl shadow-2xl border border-white/20 select-none"
      />
      <div class="mt-3 flex items-center space-x-3 text-[12px] text-white/90 font-mono bg-slate-900/90 px-4 py-1.5 rounded-full border border-white/10 backdrop-blur-xs">
        <span>{{ systemStore.lightboxData.title }}</span>
        <span class="text-white/30">|</span>
        <button
          @click="openFile"
          class="text-sky-400 hover:text-sky-300 font-sans cursor-pointer transition"
        >
          📂 打开原图
        </button>
        <span class="text-white/30">|</span>
        <button
          @click="openDir"
          class="text-emerald-400 hover:text-emerald-300 font-sans cursor-pointer transition"
        >
          📁 所在目录
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useSystemStore } from '../../stores/system';
import { api } from '../../api/client';

const systemStore = useSystemStore();

function openFile() {
  if (systemStore.lightboxData.filePath) {
    api.openPath(systemStore.lightboxData.filePath, 'open_file');
  }
}

function openDir() {
  if (systemStore.lightboxData.filePath) {
    api.openPath(systemStore.lightboxData.filePath, 'open_dir');
  }
}
</script>
