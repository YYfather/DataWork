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
        <span class="release-notice-version">V1.7 · 多元批量计算提示</span>
      </div>

      <div class="release-notice-heading">
        <span class="release-notice-mark" aria-hidden="true">!</span>
        <div>
          <h2 id="release-notice-title">V1.7 因变量组合会生成多个独立 MANOVA 模型</h2>
          <p id="release-notice-description">
            专业模式可按无序组合批量计算联合因变量；执行前请核对组合范围、任务总数与跨模型校正。
          </p>
        </div>
      </div>

      <ul>
        <li><code>Y1 + Y2</code> 与 <code>Y2 + Y1</code> 只生成一次；同一因变量可以进入不同组合。</li>
        <li>任务总数等于因变量任务、因素模型和实际拆分组的乘积；超过 200 强警告，超过 1000 阻止执行。</li>
        <li>默认使用 Holm 跨模型校正；每个组合仍保留独立的总体检验、单变量跟进、事后比较和诊断。</li>
        <li>用于正式研究结论前，请在预检中确认组合成员、完整案例、设计矩阵与失败任务。</li>
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
