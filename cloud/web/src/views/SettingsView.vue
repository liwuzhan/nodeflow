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
      <template #header><span>农场参考点</span></template>
      <el-form label-width="120px">
        <el-form-item label="经度">
          <el-input :model-value="farmRef.lon" disabled />
        </el-form-item>
        <el-form-item label="纬度">
          <el-input :model-value="farmRef.lat" disabled />
        </el-form-item>
      </el-form>
      <el-text type="info" size="small">参考点用于 GPS ↔ ENU 坐标转换，在创建地块时设置</el-text>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref as vRef } from 'vue'
import { ElMessage } from 'element-plus'
import { createMachine } from '@/services/machineApi'
import { useMachineStore } from '@/stores/machineStore'

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

const farmRef = { lon: 120.037328, lat: 28.91685 }

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
</script>
