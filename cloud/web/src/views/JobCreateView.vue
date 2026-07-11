<template>
  <div class="job-create">
    <h3>新建作业</h3>
    <el-steps :active="activeStep" finish-status="success" align-center style="margin-bottom:24px">
      <el-step title="选择操作" />
      <el-step title="分割 & 分配" />
      <el-step title="确认下发" />
    </el-steps>

    <!-- Step 1 -->
    <div v-if="activeStep === 0">
      <el-form label-position="top">
        <el-form-item label="地块">
          <el-select v-model="form.parcelId" placeholder="选择地块" style="width:100%">
            <el-option v-for="p in parcels" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="操作步骤">
          <div v-for="(step, i) in form.steps" :key="i" class="step-row">
            <el-select v-model="step.operation_type" style="width:160px">
              <el-option label="旋耕" value="tillage" />
              <el-option label="播种" value="seeding" />
              <el-option label="喷洒" value="spraying" />
            </el-select>
            <el-select v-model="step.preset_yaml" style="width:200px">
              <el-option label="tillage_operation" value="tillage_operation" />
              <el-option label="planning_with_real_rtk" value="planning_with_real_rtk" />
              <el-option label="trajectory_playback" value="trajectory_playback" />
            </el-select>
            <el-select v-model="step.planning_mode" style="width:170px"
                       @change="onPlanningModeChange(step)">
              <el-option label="边侧规划" value="edge" />
              <el-option label="云端规划" value="cloud" />
              <el-option label="云端优先" value="cloud_preferred" />
            </el-select>
            <el-button type="danger" :icon="Delete" circle size="small"
                       @click="removeStep(i)" :disabled="form.steps.length <= 1" />
            <div v-if="step.operation_type === 'tillage'" class="operation-params">
              <el-input-number v-model="step.operation_config.implement_width_m" :min="0.5" :max="20" :step="0.1" />
              <span>幅宽 m</span>
              <el-input-number v-model="step.operation_config.overlap_ratio" :min="0" :max="0.8" :step="0.01" />
              <span>重叠率</span>
              <el-input-number v-model="step.operation_config.work_min_turn_radius_m" :min="0.5" :max="30" :step="0.5" />
              <span>作业转弯半径 m</span>
            </div>
          </div>
          <el-button @click="addStep">+ 添加步骤</el-button>
        </el-form-item>
      </el-form>
      <el-button type="primary" @click="activeStep = 1" :disabled="!form.parcelId">下一步</el-button>
    </div>

    <!-- Step 2 -->
    <div v-if="activeStep === 1">
      <el-form label-position="top">
        <el-form-item label="分割模式">
          <el-radio-group v-model="form.splitMode">
            <el-radio label="strip">条带分割</el-radio>
            <el-radio label="checkerboard">网格分割</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="份数">
          <el-input-number v-model="form.splitCount" :min="1" :max="8" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handlePreviewSplit" :loading="previewLoading">
            预览分割
          </el-button>
        </el-form-item>
        <el-form-item v-if="previewSplits.length" label="步骤级机器分配">
          <div class="assignment-grid">
            <section v-for="(step, stepIndex) in form.steps" :key="stepIndex" class="assignment-step">
              <h4>Step {{ stepIndex + 1 }} · {{ step.operation_type }}</h4>
              <div v-for="sp in previewSplits" :key="sp.index" class="assignment-row">
                <span>{{ sp.name }} ({{ sp.area_ha?.toFixed(2) }} ha)</span>
                <el-select v-model="form.stepMachineAssignments[String(stepIndex)][String(sp.index)]"
                           placeholder="选择机器" style="width:180px">
                  <el-option v-for="m in availableMachines" :key="m.id" :label="m.name" :value="m.id" />
                </el-select>
              </div>
            </section>
          </div>
        </el-form-item>
      </el-form>
      <el-divider />
      <el-text type="info">提示：在农场地图页面可看到分割预览效果</el-text>
      <div class="step-actions">
        <el-button @click="activeStep = 0">上一步</el-button>
        <el-button type="primary" @click="activeStep = 2" :disabled="form.splitCount < 1">下一步</el-button>
      </div>
    </div>

    <!-- Step 3 -->
    <div v-if="activeStep === 2">
      <el-descriptions border :column="2">
        <el-descriptions-item label="地块">{{ selectedParcel?.name }}</el-descriptions-item>
        <el-descriptions-item label="分割">{{ form.splitMode }} ×{{ form.splitCount }}</el-descriptions-item>
        <el-descriptions-item label="步骤数">{{ form.steps.length }}</el-descriptions-item>
        <el-descriptions-item label="机器数">{{ assignedMachineCount }}</el-descriptions-item>
        <el-descriptions-item v-for="(s, i) in form.steps" :key="i"
                              :label="`Step ${i + 1}`">
          {{ s.operation_type }} — {{ s.preset_yaml }}
          <span v-if="s.depends_on != null">(依赖 Step {{ s.depends_on + 1 }})</span>
        </el-descriptions-item>
      </el-descriptions>
      <div class="step-actions">
        <el-button @click="activeStep = 1">上一步</el-button>
        <el-button type="success" @click="handleConfirm" :loading="submitting">确认并下发</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Delete } from '@element-plus/icons-vue'
import { storeToRefs } from 'pinia'
import { useParcelStore } from '@/stores/parcelStore'
import { useMachineStore } from '@/stores/machineStore'
import { useJobStore } from '@/stores/jobStore'

const router = useRouter()
const parcelStore = useParcelStore()
const machineStore = useMachineStore()
const jobStore = useJobStore()
const { parcels } = storeToRefs(parcelStore)
const { machines } = storeToRefs(machineStore)

const activeStep = ref(0)
const submitting = ref(false)
const previewLoading = ref(false)
const previewSplits = ref<{ index: number; name: string; area_ha: number }[]>([])

const form = reactive({
  parcelId: '',
  splitMode: 'strip' as string,
  splitCount: 1,
  steps: [
    { operation_type: 'tillage', preset_yaml: 'planning_with_real_rtk', seq_index: 0,
      planning_mode: 'edge', fallback_policy: 'deny',
      operation_config: { planning_strategy: 'contour_spiral', implement_width_m: 3.0,
        overlap_ratio: 0.1, path_inset_m: 1.0, work_min_turn_radius_m: 4.0,
        work_max_curvature_rate_1pm2: 0.08, path_point_spacing: 0.5 } },
  ] as { operation_type: string; preset_yaml: string; seq_index: number; depends_on?: number | null;
         planning_mode: string; fallback_policy: string; operation_config: Record<string, any> }[],
  stepMachineAssignments: { '0': {} } as Record<string, Record<string, string>>,
})

const selectedParcel = computed(() => parcels.value.find(p => p.id === form.parcelId))
const availableMachines = computed(() => machines.value.filter(m => m.status === 'online'))
const assignedMachineCount = computed(() => new Set(
  Object.values(form.stepMachineAssignments).flatMap(assignments => Object.values(assignments))
).size)

function addStep() {
  const idx = form.steps.length
  form.steps.push({ operation_type: 'seeding', preset_yaml: 'planning_with_real_rtk',
                    seq_index: idx, depends_on: idx - 1,
                    planning_mode: 'edge', fallback_policy: 'deny', operation_config: {} })
  form.stepMachineAssignments[String(idx)] = {}
}

function removeStep(i: number) {
  form.steps.splice(i, 1)
  const previous = { ...form.stepMachineAssignments }
  for (const key of Object.keys(form.stepMachineAssignments)) delete form.stepMachineAssignments[key]
  form.steps.forEach((s, j) => {
    s.seq_index = j
    s.depends_on = j > 0 ? j - 1 : null
    form.stepMachineAssignments[String(j)] = previous[String(j < i ? j : j + 1)] || {}
  })
}

function onPlanningModeChange(step: typeof form.steps[number]) {
  if (step.planning_mode === 'edge') {
    step.preset_yaml = 'planning_with_real_rtk'
    step.fallback_policy = 'deny'
  } else {
    step.preset_yaml = 'tillage_operation'
    step.fallback_policy = step.planning_mode === 'cloud_preferred' ? 'allow_edge_replan' : 'deny'
  }
}

async function handlePreviewSplit() {
  if (!form.parcelId) return
  previewLoading.value = true
  try {
    const splits = await parcelStore.fetchSplitPreview(form.parcelId, {
      mode: form.splitMode,
      count: form.splitCount,
    })
    previewSplits.value = splits
  } finally {
    previewLoading.value = false
  }
}

async function handleConfirm() {
  submitting.value = true
  try {
    const job = await jobStore.addJob({
      parcel_id: form.parcelId,
      split_mode: form.splitMode,
      split_count: form.splitCount,
      steps: form.steps.map((s, i) => ({
        operation_type: s.operation_type,
        preset_yaml: s.preset_yaml,
        seq_index: i,
        depends_on: s.depends_on ?? (i > 0 ? i - 1 : null),
        planning_mode: s.planning_mode,
        fallback_policy: s.fallback_policy,
        operation_config: s.operation_config,
        machine_assignments: form.stepMachineAssignments[String(i)] || {},
      })),
      machine_assignments: form.stepMachineAssignments['0'] || {},
    })
    await jobStore.dispatch(job.id)
    router.push(`/jobs/${job.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  if (parcels.value.length === 0) await parcelStore.fetchParcels()
  if (machines.value.length === 0) await machineStore.fetchMachines()
})
</script>

<style scoped>
.step-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.operation-params { display: flex; gap: 6px; align-items: center; width: 100%; font-size: 12px; color: #606266; }
.operation-params :deep(.el-input-number) { width: 130px; }
.assignment-grid { display: grid; gap: 16px; width: 100%; }
.assignment-step { border-left: 3px solid #409eff; padding-left: 12px; }
.assignment-step h4 { margin: 0 0 8px; font-size: 14px; }
.assignment-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 8px; }
.step-actions { margin-top: 24px; display: flex; gap: 12px; }
</style>
