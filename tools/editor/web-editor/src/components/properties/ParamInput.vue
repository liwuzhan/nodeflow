<template>
  <div class="param-input-wrapper">
    <!-- String 类型 -->
    <el-input
      v-if="paramType === 'string'"
      v-model="localValue"
      type="text"
      :placeholder="placeholder"
      @blur="emitChange"
      @keyup.enter="emitChange"
      clearable
    />

    <!-- Integer 类型 -->
    <el-input-number
      v-else-if="paramType === 'int' || paramType === 'integer'"
      v-model="localValue"
      :step="1"
      :min="Number.MIN_SAFE_INTEGER"
      :max="Number.MAX_SAFE_INTEGER"
      @change="emitChange"
    />

    <!-- Float 类型 -->
    <el-input-number
      v-else-if="paramType === 'float' || paramType === 'number'"
      v-model="localValue"
      :step="0.1"
      :precision="2"
      :min="Number.MIN_VALUE"
      :max="Number.MAX_VALUE"
      @change="emitChange"
    />

    <!-- Boolean 类型 -->
    <el-switch
      v-else-if="paramType === 'bool' || paramType === 'boolean'"
      v-model="localValue"
      @change="emitChange"
    />

    <!-- Any 类型（支持多种输入） -->
    <div v-else class="any-type-input">
      <el-select
        v-model="anyTypeValue"
        placeholder="选择类型"
        @change="updateAnyValue"
        style="width: 50%; margin-right: 8px"
      >
        <el-option label="字符串" value="string" />
        <el-option label="数字" value="number" />
        <el-option label="布尔值" value="boolean" />
        <el-option label="JSON" value="json" />
      </el-select>

      <el-input
        v-if="anyTypeValue === 'string' || anyTypeValue === 'json'"
        v-model="anyStringValue"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 4 }"
        :placeholder="anyTypeValue === 'json' ? '{...}' : '输入文本'"
        @blur="emitChange"
      />

      <el-input-number
        v-else-if="anyTypeValue === 'number'"
        v-model="anyNumberValue"
        @change="emitChange"
      />

      <el-switch
        v-else-if="anyTypeValue === 'boolean'"
        v-model="anyBoolValue"
        @change="emitChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

interface Props {
  modelValue: any
  paramType: string
  placeholder?: string
  paramName?: string
}

interface Emits {
  (e: 'update:modelValue', value: any): void
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '输入参数值',
})
const emit = defineEmits<Emits>()

const localValue = ref(props.modelValue)

// Any 类型的特殊处理
const anyTypeValue = ref<'string' | 'number' | 'boolean' | 'json'>('string')
const anyStringValue = ref('')
const anyNumberValue = ref<number>(0)
const anyBoolValue = ref(false)

// 初始化 any 类型的值
watch(
  () => props.modelValue,
  (newVal) => {
    localValue.value = newVal

    if (props.paramType === 'any') {
      if (typeof newVal === 'string') {
        anyTypeValue.value = 'string'
        anyStringValue.value = newVal
      } else if (typeof newVal === 'number') {
        anyTypeValue.value = 'number'
        anyNumberValue.value = newVal
      } else if (typeof newVal === 'boolean') {
        anyTypeValue.value = 'boolean'
        anyBoolValue.value = newVal
      } else if (typeof newVal === 'object') {
        anyTypeValue.value = 'json'
        anyStringValue.value = JSON.stringify(newVal, null, 2)
      } else {
        anyStringValue.value = String(newVal)
      }
    }
  },
  { immediate: true }
)

// 数值类型 watch localValue 变化
watch(
  () => props.modelValue,
  (newVal) => {
    if (
      props.paramType === 'int' ||
      props.paramType === 'integer' ||
      props.paramType === 'float' ||
      props.paramType === 'number'
    ) {
      localValue.value = newVal
    }
  }
)

function emitChange() {
  let value: any = localValue.value

  // 数值类型转换
  if (props.paramType === 'int' || props.paramType === 'integer') {
    value = value === null ? null : Math.floor(Number(value))
  } else if (props.paramType === 'float' || props.paramType === 'number') {
    value = value === null ? null : Number(value)
  }

  emit('update:modelValue', value)
}

function updateAnyValue() {
  let value: any

  if (anyTypeValue.value === 'string') {
    value = anyStringValue.value
  } else if (anyTypeValue.value === 'number') {
    value = anyNumberValue.value
  } else if (anyTypeValue.value === 'boolean') {
    value = anyBoolValue.value
  } else if (anyTypeValue.value === 'json') {
    try {
      value = JSON.parse(anyStringValue.value)
    } catch {
      value = anyStringValue.value
    }
  }

  localValue.value = value
  emit('update:modelValue', value)
}
</script>

<style scoped>
.param-input-wrapper {
  width: 100%;
}

.any-type-input {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.any-type-input > div:first-child {
  display: flex;
  gap: 8px;
}
</style>
