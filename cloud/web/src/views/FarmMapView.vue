<template>
  <div class="farm-map-view">
    <div class="map-area">
      <FarmMap ref="farmMapRef">
        <ParcelLayer />
        <SplitPreview />
        <ParcelDrawer :active="drawing" @created="handleParcelCreated" @cancel="drawing = false" />
        <MachineMarker />
      </FarmMap>
      <div class="map-toolbar" v-if="!drawing">
        <el-button type="primary" @click="drawing = true" :icon="Edit">绘制地块</el-button>
      </div>
      <div class="map-toolbar" v-else>
        <el-text type="warning">点击地图添加顶点，双击完成绘制</el-text>
        <el-button @click="drawing = false">取消</el-button>
      </div>
    </div>

    <div class="side-panel">
      <el-card>
        <template #header>
          <div class="panel-header">
            <span>地块列表</span>
            <el-button size="small" text @click="parcelStore.fetchParcels()">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>
        </template>
        <div v-if="parcels.length === 0">
          <EmptyState>暂无地块，使用左侧"绘制地块"按钮创建</EmptyState>
        </div>
        <div v-else v-for="p in parcels" :key="p.id"
             class="parcel-item" :class="{ active: p.id === selectedParcelId }"
             @click="selectParcel(p.id)">
          <div class="parcel-name">{{ p.name }}</div>
          <div class="parcel-meta">{{ formatArea(p.area_ha) }}</div>
        </div>
      </el-card>
      <el-button type="primary" style="margin-top:12px;width:100%"
                 @click="$router.push('/jobs/create')" :disabled="!selectedParcelId">
        新建作业
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Edit, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { storeToRefs } from 'pinia'
import { useParcelStore } from '@/stores/parcelStore'
import { formatArea } from '@/utils/formatters'
import FarmMap from '@/components/map/FarmMap.vue'
import ParcelLayer from '@/components/map/ParcelLayer.vue'
import SplitPreview from '@/components/map/SplitPreview.vue'
import ParcelDrawer from '@/components/map/ParcelDrawer.vue'
import MachineMarker from '@/components/map/MachineMarker.vue'
import EmptyState from '@/components/common/EmptyState.vue'

const parcelStore = useParcelStore()
const { parcels, selectedParcelId } = storeToRefs(parcelStore)
const { selectParcel } = parcelStore

const drawing = ref(false)

async function handleParcelCreated(geojson: unknown) {
  drawing.value = false
  try {
    const name = prompt('地块名称:') || `地块-${Date.now()}`
    await parcelStore.addParcel(name, geojson)
    ElMessage.success('地块已创建')
  } catch (e: unknown) {
    ElMessage.error('创建失败: ' + (e instanceof Error ? e.message : 'unknown'))
  }
}
</script>

<style scoped>
.farm-map-view { display: flex; gap: 16px; height: calc(100vh - 116px); }
.map-area { flex: 1; position: relative; }
.map-toolbar {
  position: absolute; top: 12px; left: 50%; transform: translateX(-50%); z-index: 1000;
  background: rgba(255,255,255,0.95); padding: 8px 16px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  display: flex; align-items: center; gap: 12px;
}
.side-panel { width: 280px; flex-shrink: 0; }
.panel-header { display: flex; justify-content: space-between; align-items: center; }
.parcel-item { padding: 8px 12px; cursor: pointer; border-radius: 4px; margin-bottom: 4px; }
.parcel-item:hover { background: #f0f2f5; }
.parcel-item.active { background: #ecf5ff; border-left: 3px solid #409eff; }
.parcel-name { font-weight: 500; }
.parcel-meta { font-size: 12px; color: #909399; }
</style>
