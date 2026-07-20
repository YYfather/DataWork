<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'

const props = defineProps<{
  open: boolean
  report: any | null
  loading?: boolean
  confirmLabel?: string
  priorRunCount?: number
}>()

const emit = defineEmits<{ close: []; confirm: []; locate: [field: string] }>()

const errors = computed(() => (props.report?.issues ?? []).filter((item: any) => item.severity === 'error'))
const warnings = computed(() => (props.report?.issues ?? []).filter((item: any) => item.severity === 'warning'))
const canConfirm = computed(() => Boolean(props.report?.ready && !props.loading))
const correctionLabel = computed(() => {
  const method = props.report?.batch_summary?.p_adjust || props.report?.selections?.cross_model_p_adjust || props.report?.selections?.combination_p_adjust || 'holm'
  return method === 'fdr_bh' ? 'FDR-BH' : method === 'none' ? '不校正' : method === 'bonferroni' ? 'Bonferroni' : 'Holm'
})
const effectiveConfirmLabel = computed(() => {
  if (props.loading) return '正在检查…'
  const count = Number(props.report?.batch_summary?.group_count || 0)
  if (count > 1) return `确认并运行 ${count} 个模型`
  if ((props.priorRunCount || 0) > 0) return '确认创建新的独立运行'
  return props.confirmLabel || '确认并开始分析'
})

function onKeydown(event: KeyboardEvent) { if (event.key === 'Escape' && props.open) emit('close') }
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

function labelForField(field?: string) {
  const labels: Record<string, string> = {
    method: '统计方法',
    dependent_variables: '因变量',
    fixed_factors: '分类/固定因素',
    covariates: '连续自变量/协变量',
    random_factors: '随机分组因素',
    random_slopes: '随机斜率',
    emm_factors: '估计边际均值因素',
    method_parameters: '高级参数',
    subject_id: '受试者/样本 ID',
    repeated_factor: '重复/时间因素',
    expected_proportions: '期望比例',
    split_by: '批量拆分',
    cross_model_p_adjust: '跨模型多重校正',
    columns: '数据列',
  }
  return labels[field ?? ''] ?? '分析计划'
}
</script>

<template>
  <div v-if="open" class="modal-backdrop preflight-backdrop" @click.self="emit('close')">
    <section class="preflight-dialog" role="dialog" aria-modal="true" aria-label="分析前检查">
      <header class="preflight-head">
        <div>
          <p class="eyebrow">PREFLIGHT CHECK</p>
          <h2>分析前检查</h2>
          <p>确认当前数据、统计方法和变量角色完整后再开始计算。</p>
        </div>
        <button class="icon-button floating-close" @click="emit('close')" aria-label="关闭">×</button>
      </header>

      <div v-if="loading" class="preflight-loading" role="status" aria-live="polite">
        <div class="inline-spinner" aria-hidden="true"></div>
        <div><strong>正在检查当前数据与分析计划</strong><p>正在逐项验证变量角色、样本结构、方法参数和每个批量子任务。</p></div>
      </div>

      <template v-else-if="report">
        <div :class="report.ready ? 'preflight-status ready' : 'preflight-status blocked'">
          <strong>{{ report.ready ? '检查通过，可以开始分析' : `还缺少 ${errors.length} 项必要设置` }}</strong>
          <span v-if="report.batch_summary?.enabled">
            将按 {{ report.batch_summary.dimensions?.join(' × ') || '批量任务' }} 展开为
            {{ report.batch_summary.group_count }} 个任务，并合并为一个结果表。
          </span>
          <span v-else>当前将执行一次完整分析，不进行批次拆分。</span>
        </div>

        <section class="preflight-section multi-run-alert" v-if="report.batch_summary?.enabled && report.batch_summary.group_count > 1">
          <h3>多模型运行确认</h3>
          <p v-if="correctionLabel === '不校正'">本次操作会在同一个执行批次内运行 <strong>{{ report.batch_summary.group_count }}</strong> 个模型。已明确选择 <strong>不校正</strong>：每个模型直接使用原始 p 值判断，判断 p 不会被修改。</p>
          <p v-else>本次操作会在同一个执行批次内运行 <strong>{{ report.batch_summary.group_count }}</strong> 个模型。它们共同构成一个预先可见的检验集合，主要/总体检验将使用 <strong>{{ correctionLabel }}</strong> 做跨模型校正。</p>
          <small v-if="correctionLabel === '不校正'">组合模型、多因变量和数据拆分均保留原始结果；随着检验次数增加，至少一次假阳性的整体风险会累积。</small>
          <small v-else>组合模型、多因变量和数据拆分都遵循同一规则；原始 p 值仍会保留，正式结论优先采用跨模型校正后的 p 值。</small>
        </section>

        <section class="preflight-section repeat-run-alert" v-if="(priorRunCount || 0) > 0">
          <h3>重复运行提醒</h3>
          <p>当前数据/计划此前已经完成 <strong>{{ priorRunCount }}</strong> 次运行。继续操作会创建一条新的独立运行记录，不会覆盖历史结果。</p>
          <small>历史运行不会被自动拼接成同一个校正家族。若反复更换参数并挑选显著结果，整体误报风险仍会升高；应预先定义比较范围，或在一次批量执行中统一校正。</small>
        </section>

        <section class="preflight-section">
          <h3>当前选择</h3>
          <div class="preflight-selection-grid">
            <div><span>统计方法</span><strong>{{ report.method?.label_zh || '未选择' }}</strong></div>
            <div><span>因变量/分析变量</span><strong>{{ report.selections?.dependent_variables?.join('、') || '未选择或不需要' }}</strong></div>
            <div><span>分类因素</span><strong>{{ report.selections?.fixed_factors?.join(' × ') || '未选择或不需要' }}</strong></div>
            <div><span>连续自变量</span><strong>{{ report.selections?.covariates?.join('、') || '未选择或不需要' }}</strong></div>
            <div><span>随机分组</span><strong>{{ report.selections?.random_factors?.join('、') || '未选择或不需要' }}</strong></div>
            <div><span>对象 ID</span><strong>{{ report.selections?.subject_id || '未选择或不需要' }}</strong></div>
            <div><span>重复/时间</span><strong>{{ report.selections?.repeated_factor || '未选择或不需要' }}</strong></div>
            <div><span>批量拆分</span><strong>{{ report.selections?.split_by?.join('、') || '不拆分' }}</strong><small v-if="report.selections?.split_rules?.length">{{ report.selections.split_rules.length }} 条自定义分组规则</small></div>
          </div>
        </section>

        <section class="preflight-section design-review-section" v-if="report.design_review">
          <div class="design-review-head">
            <div>
              <p class="eyebrow">STATISTICAL DESIGN REVIEW</p>
              <h3>智能统计设计审查</h3>
            </div>
            <span :class="`design-review-badge ${report.design_review.status}`">{{ report.design_review.status === 'ready' ? '结构匹配' : report.design_review.status === 'attention' ? '需要复核' : '阻止运行' }}</span>
          </div>
          <strong>{{ report.design_review.headline }}</strong>
          <p>{{ report.design_review.summary }}</p>
          <div class="design-review-metrics" v-if="report.design_review.metrics?.length">
            <div v-for="metric in report.design_review.metrics" :key="metric.label" :class="`review-metric ${metric.status || 'info'}`">
              <span>{{ metric.label }}</span><strong>{{ metric.value }}</strong>
            </div>
          </div>
          <div class="design-review-columns">
            <article v-if="report.design_review.strengths?.length"><h4>当前优势</h4><ul><li v-for="item in report.design_review.strengths" :key="item">{{ item }}</li></ul></article>
            <article v-if="report.design_review.risks?.length"><h4>设计风险</h4><ul><li v-for="item in report.design_review.risks" :key="item">{{ item }}</li></ul></article>
            <article v-if="report.design_review.actions?.length"><h4>建议动作</h4><ul><li v-for="item in report.design_review.actions" :key="item">{{ item }}</li></ul></article>
          </div>
        </section>

        <section class="preflight-section" v-if="errors.length">
          <h3>必须补充</h3>
          <article class="preflight-issue error" v-for="item in errors" :key="`${item.code}-${item.field}-${item.message}`">
            <div><strong>{{ labelForField(item.field) }}</strong><p>{{ item.message }}</p></div>
            <button v-if="item.code !== 'correction_setting_mismatch'" class="choice active" @click="emit('locate', item.field || '')">去补充</button>
          </article>
        </section>

        <section class="preflight-section" v-if="warnings.length">
          <h3>运行提醒</h3>
          <article class="preflight-issue warning" v-for="item in warnings" :key="`${item.code}-${item.field}-${item.message}`">
            <div><strong>{{ labelForField(item.field) }}</strong><p>{{ item.message }}</p></div>
          </article>
        </section>

        <section class="preflight-section" v-if="report.batch_summary?.enabled">
          <h3>批量执行概览</h3>
          <div class="batch-check-summary">
            <div><span>批次数</span><strong>{{ report.batch_summary.group_count }}</strong></div>
            <div><span>可直接运行</span><strong>{{ report.batch_summary.ready_group_count }}</strong></div>
            <div><span>可能失败</span><strong>{{ report.batch_summary.problem_group_count }}</strong></div>
            <div><span>完整案例</span><strong>{{ report.data_summary?.complete_rows_for_plan }}</strong></div>
          </div>
          <details v-if="report.batch_summary.groups?.length">
            <summary>查看各批次检查结果</summary>
            <div class="table-wrap">
              <table>
                <thead><tr><th>批次</th><th>有效行</th><th>状态</th><th>说明</th></tr></thead>
                <tbody>
                  <tr v-for="(group, index) in report.batch_summary.groups" :key="index">
                    <td>{{ Object.entries(group.key).map(([key, value]) => `${key}=${value}`).join('；') }}</td>
                    <td>{{ group.rows }}</td>
                    <td>{{ group.ready ? '可运行' : '需注意' }}</td>
                    <td><span v-if="group.reasons?.length">{{ group.reasons.join('；') }}</span><span v-else-if="group.warnings?.length">{{ group.warnings.join('；') }}</span><span v-else>—</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </details>
        </section>
      </template>

      <footer class="preflight-actions">
        <button class="choice" :disabled="loading" @click="emit('close')">返回修改</button>
        <button class="primary" :disabled="!canConfirm" :aria-busy="loading" @click="emit('confirm')">
          {{ effectiveConfirmLabel }}
        </button>
      </footer>
    </section>
  </div>
</template>
