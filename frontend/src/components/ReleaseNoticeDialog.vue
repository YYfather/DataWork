<script setup lang="ts">
defineProps<{ open: boolean }>()

const emit = defineEmits<{ acknowledge: [] }>()
</script>

<template>
  <div v-if="open" class="release-notice-backdrop">
    <section
      class="release-notice-card"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="release-notice-title"
      aria-describedby="release-notice-description"
    >
      <div class="release-notice-topline">
        <span class="release-notice-kicker">功能公告</span>
        <span class="release-notice-version">V1.5 · 测试修补阶段</span>
      </div>

      <div class="release-notice-heading">
        <span class="release-notice-mark" aria-hidden="true">!</span>
        <div>
          <h2 id="release-notice-title">V1.5 配对列仍在测试修补阶段</h2>
          <p id="release-notice-description">
            请谨慎使用。处理—对照配对、配对派生列与联合因变量工作流仍在持续校验和修补。
          </p>
        </div>
      </div>

      <ul>
        <li>执行前请在审核窗口确认有效配对数、未匹配或未映射记录，以及最终拆分任务。</li>
        <li>用于正式研究结论前，请保留原始数据，并与人工检查或 R/Python 参考结果交叉复核。</li>
        <li>如果审核数量或分组关系异常，请停止分析并反馈，不要直接采用计算结果。</li>
      </ul>

      <div class="release-notice-actions">
        <small>此公告在每次打开 DataWork 时显示一次。</small>
        <button type="button" class="primary" autofocus @click="emit('acknowledge')">
          我已了解，谨慎使用
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.release-notice-backdrop {
  position: fixed;
  inset: 0;
  z-index: 110;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(18, 34, 26, 0.62);
  backdrop-filter: blur(6px);
}

.release-notice-card {
  width: min(620px, 100%);
  padding: 26px;
  border: 1px solid #d9c88d;
  border-radius: 22px;
  background: #fffdf5;
  box-shadow: 0 32px 100px rgba(10, 28, 18, 0.36);
}

.release-notice-topline,
.release-notice-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.release-notice-kicker {
  color: #80631a;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

.release-notice-version {
  padding: 5px 10px;
  border-radius: 999px;
  background: #f4e8b9;
  color: #6c5315;
  font-size: 12px;
  font-weight: 800;
}

.release-notice-heading {
  display: grid;
  grid-template-columns: 48px 1fr;
  gap: 14px;
  align-items: start;
  margin-top: 20px;
}

.release-notice-mark {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 15px;
  background: #e9b93f;
  color: #2e260f;
  font-size: 26px;
  font-weight: 900;
}

h2 {
  margin: 0;
  color: #25382e;
}

p {
  margin: 8px 0 0;
  color: #5a685f;
  line-height: 1.65;
}

ul {
  display: grid;
  gap: 10px;
  margin: 22px 0;
  padding: 18px 18px 18px 38px;
  border-radius: 16px;
  background: #faf4dc;
  color: #4d594f;
  line-height: 1.6;
}

.release-notice-actions small {
  color: #7b827e;
}

@media (max-width: 620px) {
  .release-notice-backdrop { padding: 14px; }
  .release-notice-card { padding: 20px; }
  .release-notice-topline,
  .release-notice-actions { align-items: stretch; flex-direction: column; }
  .release-notice-heading { grid-template-columns: 40px 1fr; }
  .release-notice-mark { width: 40px; height: 40px; border-radius: 12px; }
  .release-notice-actions button { width: 100%; }
}
</style>
