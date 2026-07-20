<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ plots: any[] }>()

function numeric(values: unknown[]) {
  return values.every(value => typeof value === 'number' && Number.isFinite(value))
}

function points(plot: any, series: any) {
  const xs = Array.isArray(series?.x) ? series.x : []
  const ys = Array.isArray(series?.y) ? series.y.map(Number) : []
  if (!xs.length || !ys.length) return []
  const width = 520
  const height = 250
  const pad = 34
  const numericX = numeric(xs)
  const xNumbers = numericX ? xs.map(Number) : xs.map((_: unknown, index: number) => index)
  const xMin = Math.min(...xNumbers)
  const xMax = Math.max(...xNumbers)
  const yMin = Math.min(...ys)
  const yMax = Math.max(...ys)
  const xScale = (value: number) => pad + ((value - xMin) / (xMax - xMin || 1)) * (width - pad * 2)
  const yScale = (value: number) => height - pad - ((value - yMin) / (yMax - yMin || 1)) * (height - pad * 2)
  return ys.map((value: number, index: number) => ({
    x: xScale(xNumbers[index]),
    y: yScale(value),
    label: String(xs[index]),
    value,
  }))
}

function polyline(plot: any, series: any) {
  return points(plot, series).map((point: { x: number; y: number }) => `${point.x},${point.y}`).join(' ')
}

const available = computed(() => (props.plots ?? []).filter(plot => Array.isArray(plot.series) && plot.series.length))
</script>

<template>
  <section class="diagnostic-section" v-if="available.length">
    <div class="diagnostic-heading"><h3>模型诊断图</h3><span>用于检查模型假设，不替代统计检验。</span></div>
    <div class="diagnostic-grid">
      <article class="diagnostic-card" v-for="(plot, index) in available" :key="`${plot.title}-${index}`">
        <div><strong>{{ plot.title }}</strong><small>{{ plot.x_label }} × {{ plot.y_label }}</small></div>
        <svg viewBox="0 0 520 250" role="img" :aria-label="plot.title">
          <line x1="34" y1="216" x2="486" y2="216" class="axis" />
          <line x1="34" y1="24" x2="34" y2="216" class="axis" />
          <g v-for="(series, seriesIndex) in plot.series" :key="`${series.name}-${seriesIndex}`">
            <polyline v-if="plot.kind === 'line'" :points="polyline(plot, series)" class="plot-line" />
            <circle v-for="(point, pointIndex) in points(plot, series)" :key="pointIndex" :cx="point.x" :cy="point.y" r="3.8" class="plot-point">
              <title>{{ series.name }} {{ point.label }}: {{ point.value }}</title>
            </circle>
          </g>
        </svg>
        <p v-for="note in plot.notes ?? []" :key="note">{{ note }}</p>
      </article>
    </div>
  </section>
</template>

<style scoped>
.diagnostic-section { margin-top: 22px; }
.diagnostic-heading { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 12px; }
.diagnostic-heading h3 { margin: 0; }
.diagnostic-heading span { color: #68707d; font-size: 13px; }
.diagnostic-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
.diagnostic-card { border: 1px solid #dfe4ea; border-radius: 14px; padding: 14px; background: #fff; overflow: hidden; }
.diagnostic-card > div { display: flex; justify-content: space-between; gap: 10px; }
.diagnostic-card small { color: #6d7480; }
.diagnostic-card svg { width: 100%; height: auto; margin-top: 8px; background: #fafbfc; border-radius: 10px; }
.axis { stroke: #8a929e; stroke-width: 1; }
.plot-line { fill: none; stroke: currentColor; stroke-width: 2; }
.plot-point { fill: currentColor; opacity: .82; }
.diagnostic-card p { color: #68707d; font-size: 12px; margin: 6px 0 0; }
</style>
