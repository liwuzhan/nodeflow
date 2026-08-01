<template>
  <el-dialog
    v-model="visible"
    title="图验证结果"
    width="600px"
    @close="$emit('close')"
  >
    <!-- 验证摘要 -->
    <div class="validation-summary">
      <div v-if="validationResult.valid && validationResult.warnings.length === 0" class="summary-success">
        <el-icon><SuccessFilled /></el-icon>
        <span>图验证通过 ✓</span>
      </div>

      <div v-else class="summary-issues">
        <div v-if="validationResult.errors.length > 0" class="issue-count error-count">
          <el-icon><CircleCloseFilled /></el-icon>
          <span>{{ validationResult.errors.length }} 个错误</span>
        </div>
        <div v-if="validationResult.warnings.length > 0" class="issue-count warning-count">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ validationResult.warnings.length }} 个警告</span>
        </div>
      </div>
    </div>

    <!-- 错误列表 -->
    <div v-if="validationResult.errors.length > 0" class="error-section">
      <h4>
        <el-icon><CircleCloseFilled /></el-icon>
        错误（必须修复）
      </h4>
      <div class="error-list">
        <div v-for="(error, index) in validationResult.errors" :key="`error_${index}`" class="error-item">
          <div class="error-header">
            <span class="error-code">{{ error.code }}</span>
            <span v-if="error.nodeId" class="error-target">节点: {{ error.nodeId }}</span>
            <span v-else-if="error.edgeId" class="error-target">连接: {{ error.edgeId }}</span>
          </div>
          <div class="error-message">{{ error.message }}</div>
        </div>
      </div>
    </div>

    <!-- 警告列表 -->
    <div v-if="validationResult.warnings.length > 0" class="warning-section">
      <h4>
        <el-icon><WarningFilled /></el-icon>
        警告（可选修复）
      </h4>
      <div class="warning-list">
        <div v-for="(warning, index) in validationResult.warnings" :key="`warning_${index}`" class="warning-item">
          <div class="warning-header">
            <span class="warning-code">{{ warning.code }}</span>
            <span v-if="warning.nodeId" class="warning-target">节点: {{ warning.nodeId }}</span>
            <span v-else-if="warning.edgeId" class="warning-target">连接: {{ warning.edgeId }}</span>
          </div>
          <div class="warning-message">{{ warning.message }}</div>
        </div>
      </div>
    </div>

    <!-- 无问题提示 -->
    <div v-if="validationResult.errors.length === 0 && validationResult.warnings.length === 0" class="no-issues">
      <p>图结构完整，没有发现任何问题。</p>
      <p>您可以安心导出为 YAML 配置文件。</p>
    </div>

    <!-- 按钮 -->
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button
        v-if="!validationResult.valid"
        type="primary"
        disabled
      >
        无法继续（有错误）
      </el-button>
      <el-button
        v-else
        type="primary"
        @click="handleExport"
      >
        确认导出
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { ValidationResult } from '@/services/validator'
import { CircleCloseFilled, WarningFilled, SuccessFilled } from '@element-plus/icons-vue'

interface Props {
  modelValue: boolean
  validationResult: ValidationResult
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'close'): void
  (e: 'export'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = ref(props.modelValue)

function handleExport() {
  emit('export')
  visible.value = false
}
</script>

<style scoped>
.validation-summary {
  margin-bottom: 24px;
}

.summary-success {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background-color: #f0f9ff;
  border-left: 4px solid #67c23a;
  border-radius: 4px;
  color: #67c23a;
  font-weight: 600;
}

.summary-success :deep(.el-icon) {
  font-size: 20px;
}

.summary-issues {
  display: flex;
  gap: 12px;
}

.issue-count {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 4px;
  font-weight: 600;
}

.error-count {
  background-color: #fef0f0;
  color: #f56c6c;
}

.error-count :deep(.el-icon) {
  font-size: 18px;
}

.warning-count {
  background-color: #fdf6ec;
  color: #e6a23c;
}

.warning-count :deep(.el-icon) {
  font-size: 18px;
}

.error-section,
.warning-section {
  margin-bottom: 20px;
}

.error-section h4,
.warning-section h4 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.error-section h4 :deep(.el-icon) {
  color: #f56c6c;
  font-size: 18px;
}

.warning-section h4 :deep(.el-icon) {
  color: #e6a23c;
  font-size: 18px;
}

.error-list,
.warning-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.error-item,
.warning-item {
  padding: 10px 12px;
  border-radius: 4px;
  font-size: 12px;
  border-left: 3px solid;
}

.error-item {
  background-color: #fef0f0;
  border-left-color: #f56c6c;
}

.warning-item {
  background-color: #fdf6ec;
  border-left-color: #e6a23c;
}

.error-header,
.warning-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-weight: 500;
}

.error-code {
  color: #f56c6c;
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.warning-code {
  color: #e6a23c;
  font-family: 'Courier New', monospace;
  font-size: 11px;
}

.error-target,
.warning-target {
  color: #999;
  font-size: 11px;
}

.error-message,
.warning-message {
  color: #333;
  line-height: 1.4;
}

.no-issues {
  padding: 20px;
  text-align: center;
  background-color: #f0f9ff;
  border-radius: 4px;
  color: #67c23a;
}

.no-issues p {
  margin: 0;
  line-height: 1.6;
}
</style>
