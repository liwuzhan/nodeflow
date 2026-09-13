<template>
  <div class="settings">
    <h3>系统设置</h3>

    <el-card style="margin-bottom:16px">
      <template #header><span>MQTT Broker</span></template>
      <el-form label-width="120px" :model="mqttForm">
        <el-form-item label="Broker 地址">
          <el-input :model-value="mqttForm.host" disabled />
        </el-form-item>
        <el-form-item label="端口">
          <el-input :model-value="mqttForm.port" disabled />
        </el-form-item>
        <el-form-item label="Cloud Client ID">
          <el-input :model-value="mqttForm.clientId" disabled />
        </el-form-item>
      </el-form>
      <el-text type="info" size="small">
        通过环境变量 <code>NF_CLOUD_MQTT_BROKER</code> / <code>NF_CLOUD_MQTT_PORT</code> 配置。
        机器端通过 <code>NF_MQTT_BROKER</code> 指定 broker 地址。
      </el-text>
    </el-card>

    <el-card style="margin-bottom:16px">
      <template #header><span>注册新机器</span></template>
      <el-form label-width="100px" :model="machineForm">
        <el-form-item label="机器 ID">
          <el-input v-model="machineForm.id" placeholder="如 tractor-02" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="machineForm.name" placeholder="如 2号拖拉机" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="machineForm.machine_type">
            <el-option label="拖拉机" value="tractor" />
            <el-option label="收割机" value="harvester" />
            <el-option label="喷雾机" value="sprayer" />
          </el-select>
        </el-form-item>
        <el-form-item label="幅宽(m)">
          <el-input-number v-model="machineForm.implement_width_m" :min="0.5" :max="20" :step="0.5" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleRegister" :loading="registering">注册</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <template #header>
        <div class="section-header">
          <span>农场 ENU 参考系</span>
          <el-tag :type="frame.ready ? 'success' : 'warning'">
            {{ frame.ready ? `已配置 · v${frame.revision}` : '未配置' }}
          </el-tag>
        </div>
      </template>
      <el-form label-width="120px" :model="frameForm">
        <el-form-item label="参考系 ID">
          <el-input v-model="frameForm.frame_id" placeholder="如 farm-base-01" />
        </el-form-item>
        <el-form-item label="经度">
          <el-input-number v-model="frameForm.ref_lon" :precision="8" :step="0.000001" :min="-180" :max="180" />
        </el-form-item>
        <el-form-item label="纬度">
          <el-input-number v-model="frameForm.ref_lat" :precision="8" :step="0.000001" :min="-90" :max="90" />
        </el-form-item>
        <el-form-item label="高程(m)">
          <el-input-number v-model="frameForm.ref_alt" :precision="3" :step="0.01" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingFrame" @click="handleSaveFrame">保存固定站坐标</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref as vRef } from 'vue'
import { ElMessage } from 'element-plus'
import { createMachine } from '@/services/machineApi'
import { useMachineStore } from '@/stores/machineStore'
import {
  getCoordinateFrame, updateCoordinateFrame, type CoordinateFrame,
} from '@/services/settingsApi'

const machineStore = useMachineStore()
const registering = vRef(false)

const mqttForm = reactive({
  host: 'localhost',
  port: 1883,
  clientId: 'nodeflow-cloud',
})

const machineForm = reactive({
  id: '',
  name: '',
  machine_type: 'tractor' as string,
  implement_width_m: 2.0,
})

const savingFrame = vRef(false)
const frame = reactive<CoordinateFrame>({
  ready: false,
  type: 'ENU',
  frame_id: null,
  origin_source: null,
  ref_lon: null,
  ref_lat: null,
  ref_alt: null,
  revision: null,
  updated_at: null,
})
const frameForm = reactive({
  frame_id: 'farm-base',
  ref_lon: null as number | null,
  ref_lat: null as number | null,
  ref_alt: null as number | null,
})

function applyFrame(value: CoordinateFrame) {
  Object.assign(frame, value)
  if (value.frame_id) frameForm.frame_id = value.frame_id
  frameForm.ref_lon = value.ref_lon
  frameForm.ref_lat = value.ref_lat
  frameForm.ref_alt = value.ref_alt
}

async function handleSaveFrame() {
  if (frameForm.ref_lon == null || frameForm.ref_lat == null || !frameForm.frame_id.trim()) {
    ElMessage.warning('请填写固定站参考系 ID、经度和纬度')
    return
  }
  savingFrame.value = true
  try {
    applyFrame(await updateCoordinateFrame({
      frame_id: frameForm.frame_id.trim(),
      origin_source: 'rtk_base_manual',
      ref_lon: frameForm.ref_lon,
      ref_lat: frameForm.ref_lat,
      ref_alt: frameForm.ref_alt,
    }))
    ElMessage.success('农场参考系已保存')
  } catch (e: unknown) {
    ElMessage.error('保存失败: ' + (e instanceof Error ? e.message : 'unknown'))
  } finally {
    savingFrame.value = false
  }
}

async function handleRegister() {
  if (!machineForm.id || !machineForm.name) {
    ElMessage.warning('请填写机器 ID 和名称')
    return
  }
  registering.value = true
  try {
    await createMachine({
      id: machineForm.id,
      name: machineForm.name,
      machine_type: machineForm.machine_type,
      implement_width_m: machineForm.implement_width_m,
    })
    ElMessage.success('机器已注册')
    machineForm.id = ''
    machineForm.name = ''
    await machineStore.fetchMachines()
  } catch (e: unknown) {
    ElMessage.error('注册失败: ' + (e instanceof Error ? e.message : 'unknown'))
  } finally {
    registering.value = false
  }
}

onMounted(async () => {
  try {
    applyFrame(await getCoordinateFrame())
  } catch (e: unknown) {
    ElMessage.error('参考系加载失败: ' + (e instanceof Error ? e.message : 'unknown'))
  }
})
</script>

<style scoped>
.section-header { display: flex; align-items: center; justify-content: space-between; }
</style>
