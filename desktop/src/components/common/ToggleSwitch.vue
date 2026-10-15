<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    @click="toggle"
    class="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none disabled:cursor-not-allowed disabled:opacity-40"
    :class="modelValue ? 'bg-sky-500' : 'bg-slate-300'"
  >
    <span
      class="pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-xs ring-0 transition duration-200 ease-in-out"
      :class="modelValue ? 'translate-x-4' : 'translate-x-0'"
    />
  </button>
</template>

<script setup>
const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['update:modelValue', 'change']);

function toggle() {
  if (props.disabled) return;
  const newVal = !props.modelValue;
  emit('update:modelValue', newVal);
  emit('change', newVal);
}
</script>
