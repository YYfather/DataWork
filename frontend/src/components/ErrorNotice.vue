<script setup lang="ts">
defineProps<{ title?: string; message: string; hints?: string[]; retryLabel?: string }>()
const emit = defineEmits<{ retry: []; dismiss: [] }>()
</script>

<template>
  <section v-if="message" class="error-notice" role="alert">
    <div class="error-notice-icon">!</div>
    <div class="error-notice-body">
      <strong>{{ title || '操作未完成' }}</strong>
      <p>{{ message }}</p>
      <ul v-if="hints?.length"><li v-for="item in hints" :key="item">{{ item }}</li></ul>
      <div class="error-notice-actions">
        <button v-if="retryLabel" class="choice active" @click="emit('retry')">{{ retryLabel }}</button>
        <button class="choice" @click="emit('dismiss')">关闭提示</button>
      </div>
    </div>
  </section>
</template>
