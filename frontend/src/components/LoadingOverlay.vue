<script setup lang="ts">
defineProps<{ active: boolean; title?: string; detail?: string }>()
</script>

<template>
  <div v-if="active" class="operation-overlay" role="status" aria-live="polite" aria-busy="true">
    <div class="operation-card">
      <div class="operation-spinner" aria-hidden="true"><span></span><span></span><span></span></div>
      <strong>{{ title || '正在处理' }}</strong>
      <p>{{ detail || '请保持当前页面打开，完成后会自动更新。' }}</p>
      <div class="operation-progress"><i></i></div>
    </div>
  </div>
</template>
