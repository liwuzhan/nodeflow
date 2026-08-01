<template>
  <g
    class="custom-edge"
    :class="{ selected: isSelected, invalid: !isValid }"
    @click.stop="handleClick"
  >
    <!-- 主连接线 -->
    <path
      :d="edgePath"
      :stroke="edgeColor"
      :stroke-width="isSelected ? 3 : 2"
      fill="none"
      class="edge-path"
    />

    <!-- 箭头 -->
    <polygon
      :points="arrowPoints"
      :fill="edgeColor"
      class="edge-arrow"
    />

    <!-- 删除按钮（选中时显示） -->
    <g v-if="isSelected" :transform="`translate(${midPoint.x - 12}, ${midPoint.y - 12})`">
      <circle cx="12" cy="12" r="12" fill="white" stroke="#409eff" :stroke-width="2" class="delete-bg" />
      <g @click.stop="handleDelete" class="delete-icon">
        <line x1="8" y1="8" x2="16" y2="16" stroke="#f56c6c" :stroke-width="2" />
        <line x1="16" y1="8" x2="8" y2="16" stroke="#f56c6c" :stroke-width="2" />
      </g>
      <title>点击删除连线</title>
    </g>

    <!-- 类型标签（悬停时显示） -->
    <g v-if="showLabel" :transform="`translate(${midPoint.x}, ${midPoint.y - 25})`">
      <rect
        x="-40"
        y="-10"
        width="80"
        height="20"
        fill="white"
        stroke="#e0e0e0"
        rx="4"
      />
      <text
        x="0"
        y="4"
        text-anchor="middle"
        font-size="11"
        :fill="isValid ? '#67c23a' : '#f56c6c'"
      >
        {{ edgeTypeLabel }}
      </text>
    </g>
  </g>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { getCompatibilityColor, areTypesCompatible } from '@/services/typeChecker'

interface Props {
  edgeId: string
  fromNodeId: string
  fromPort: string
  fromPortType: string
  fromX: number
  fromY: number
  toNodeId: string
  toPort: string
  toPortType: string
  toX: number
  toY: number
  isSelected: boolean
}

interface Emits {
  (e: 'select'): void
  (e: 'delete'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const showLabel = ref(false)

// 检查类型兼容性
const isValid = computed(() =>
  areTypesCompatible(props.fromPortType, props.toPortType)
)

// 边的颜色
const edgeColor = computed(() => getCompatibilityColor(isValid.value))

// 边的类型标签
const edgeTypeLabel = computed(() => {
  if (props.fromPortType === props.toPortType) {
    return props.fromPortType
  }
  return `${props.fromPortType} → ${props.toPortType}`
})

// 计算中点坐标
const midPoint = computed(() => ({
  x: (props.fromX + props.toX) / 2,
  y: (props.fromY + props.toY) / 2,
}))

// 计算边的路径（使用贝塞尔曲线）
const edgePath = computed(() => {
  const dx = props.toX - props.fromX
  const dy = props.toY - props.fromY
  const distance = Math.sqrt(dx * dx + dy * dy)

  // 控制点偏移量（根据距离调整）
  const offset = Math.min(distance * 0.3, 100)

  const cp1x = props.fromX + offset
  const cp1y = props.fromY
  const cp2x = props.toX - offset
  const cp2y = props.toY

  const path = `M ${props.fromX} ${props.fromY} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${props.toX} ${props.toY}`

  console.log(`Edge ${props.edgeId}: from(${props.fromX}, ${props.fromY}) to(${props.toX}, ${props.toY}) path=${path}`)

  return path
})

// 计算箭头点坐标
const arrowPoints = computed(() => {
  const dx = props.toX - props.fromX
  const dy = props.toY - props.fromY
  const angle = Math.atan2(dy, dx)

  const arrowLength = 10

  // 箭头尖端
  const tipX = props.toX
  const tipY = props.toY

  // 箭头两侧点
  const angle1 = angle + (3 * Math.PI) / 4
  const angle2 = angle - (3 * Math.PI) / 4

  const p1x = tipX + arrowLength * Math.cos(angle1)
  const p1y = tipY + arrowLength * Math.sin(angle1)

  const p2x = tipX + arrowLength * Math.cos(angle2)
  const p2y = tipY + arrowLength * Math.sin(angle2)

  return `${tipX},${tipY} ${p1x},${p1y} ${p2x},${p2y}`
})

function handleClick() {
  emit('select')
}

function handleDelete() {
  emit('delete')
}
</script>

<style scoped>
.custom-edge {
  cursor: pointer;
}

.edge-path {
  transition: stroke-width 0.2s, stroke 0.2s;
}

.edge-path:hover {
  stroke-width: 4 !important;
}

.custom-edge.selected .edge-path {
  stroke-dasharray: 5, 3;
  animation: dash 0.5s linear infinite;
}

@keyframes dash {
  to {
    stroke-dashoffset: -8;
  }
}

.custom-edge.invalid .edge-path {
  stroke-dasharray: 3, 3;
}

.edge-arrow {
  transition: fill 0.2s;
}

.delete-icon {
  cursor: pointer;
  pointer-events: all;
}

.delete-icon:hover line {
  stroke: #ff0000;
  stroke-width: 3;
}

.delete-bg {
  pointer-events: all;
  cursor: pointer;
}

.delete-bg:hover {
  fill: #fff5f5;
  stroke: #f56c6c;
}
</style>
