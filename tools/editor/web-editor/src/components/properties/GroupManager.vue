<template>
  <div class="group-manager">
    <div class="manager-header">
      <h3>节点分组</h3>
      <el-button
        type="primary"
        size="small"
        icon="Plus"
        @click="showCreateDialog = true"
      >
        新建分组
      </el-button>
    </div>

    <!-- 分组列表 -->
    <div class="groups-list">
      <div
        v-for="group in groupStore.allGroups"
        :key="group.id"
        class="group-item"
        :class="{ selected: groupStore.selectedGroupId === group.id }"
        @click="groupStore.selectGroup(group.id)"
      >
        <div class="group-header">
          <div class="group-info">
            <div
              class="group-color"
              :style="{ backgroundColor: group.color }"
            ></div>
            <span class="group-name">{{ group.name }}</span>
            <el-tag size="small">{{ group.nodeIds.length }} 节点</el-tag>
          </div>
          <div class="group-actions">
            <el-button
              size="small"
              icon="Edit"
              @click.stop="handleEditGroup(group)"
            />
            <el-button
              size="small"
              type="danger"
              icon="Delete"
              @click.stop="handleDeleteGroup(group.id)"
            />
          </div>
        </div>

        <div v-if="group.description" class="group-description">
          {{ group.description }}
        </div>

        <!-- 分组中的节点 -->
        <div v-if="group.nodeIds.length > 0" class="group-nodes">
          <div
            v-for="nodeId in group.nodeIds"
            :key="nodeId"
            class="group-node"
          >
            <span>{{ getNodeDisplayName(nodeId) }}</span>
            <el-button
              size="small"
              icon="Close"
              @click.stop="groupStore.removeNodeFromGroup(group.id, nodeId)"
            />
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="groupStore.allGroups.length === 0" class="empty-state">
        <p>还没有创建任何分组</p>
        <p class="hint">分组可以帮助你组织复杂的节点流程</p>
      </div>
    </div>

    <!-- 创建/编辑分组对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      :title="editingGroup ? '编辑分组' : '新建分组'"
      width="500px"
    >
      <el-form :model="formData" label-width="80px">
        <el-form-item label="分组名称">
          <el-input
            v-model="formData.name"
            placeholder="请输入分组名称"
            maxlength="50"
          />
        </el-form-item>

        <el-form-item label="描述">
          <el-input
            v-model="formData.description"
            type="textarea"
            :rows="3"
            placeholder="可选：输入分组描述"
            maxlength="200"
          />
        </el-form-item>

        <el-form-item label="颜色">
          <div class="color-picker">
            <div
              v-for="colorOption in GROUP_COLORS"
              :key="colorOption.value"
              class="color-option"
              :class="{ selected: formData.color === colorOption.value }"
              :style="{
                backgroundColor: colorOption.value,
                borderColor: colorOption.border,
              }"
              @click="formData.color = colorOption.value"
            >
              <el-icon v-if="formData.color === colorOption.value">
                <Check />
              </el-icon>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleSaveGroup">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useGroupStore } from '@/stores/group'
import { useGraphStore } from '@/stores/graph'
import { GROUP_COLORS } from '@/models/Group'
import type { NodeGroup } from '@/models/Group'
import { ElMessage, ElMessageBox } from 'element-plus'

const groupStore = useGroupStore()
const graphStore = useGraphStore()

const showCreateDialog = ref(false)
const editingGroup = ref<NodeGroup | null>(null)

const formData = reactive({
  name: '',
  description: '',
  color: GROUP_COLORS[0].value,
})

function getNodeDisplayName(nodeId: string): string {
  const node = graphStore.getNode(nodeId)
  return node ? `${node.package} (${node.id})` : nodeId
}

function handleEditGroup(group: NodeGroup) {
  editingGroup.value = group
  formData.name = group.name
  formData.description = group.description || ''
  formData.color = group.color
  showCreateDialog.value = true
}

function handleDeleteGroup(groupId: string) {
  ElMessageBox.confirm('确定要删除这个分组吗？', '删除分组', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(() => {
      groupStore.deleteGroup(groupId)
      ElMessage.success('分组已删除')
    })
    .catch(() => {
      // 用户取消
    })
}

function handleSaveGroup() {
  if (!formData.name.trim()) {
    ElMessage.warning('请输入分组名称')
    return
  }

  if (editingGroup.value) {
    // 编辑现有分组
    groupStore.updateGroup(editingGroup.value.id, {
      name: formData.name,
      description: formData.description,
      color: formData.color,
    })
    ElMessage.success('分组已更新')
  } else {
    // 创建新分组
    groupStore.createGroup(formData.name, formData.color)
    if (formData.description) {
      const groups = groupStore.allGroups
      const newGroup = groups[groups.length - 1]
      groupStore.updateGroup(newGroup.id, { description: formData.description })
    }
    ElMessage.success('分组已创建')
  }

  // 重置表单
  formData.name = ''
  formData.description = ''
  formData.color = GROUP_COLORS[0].value
  editingGroup.value = null
  showCreateDialog.value = false
}
</script>

<style scoped>
.group-manager {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  background-color: #fafafa;
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.manager-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.groups-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group-item {
  background-color: white;
  border-radius: 8px;
  padding: 12px;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.group-item:hover {
  border-color: #409eff;
}

.group-item.selected {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
}

.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.group-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.group-color {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 2px solid #ddd;
}

.group-name {
  font-weight: 600;
  font-size: 14px;
}

.group-actions {
  display: flex;
  gap: 4px;
}

.group-description {
  font-size: 12px;
  color: #666;
  margin-bottom: 8px;
  padding-left: 32px;
}

.group-nodes {
  padding-left: 32px;
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.group-node {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  background-color: #f5f5f5;
  border-radius: 4px;
  font-size: 12px;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #999;
}

.empty-state p {
  margin: 8px 0;
}

.empty-state .hint {
  font-size: 12px;
}

.color-picker {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.color-option {
  width: 60px;
  height: 60px;
  border-radius: 8px;
  border: 3px solid;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.color-option:hover {
  transform: scale(1.1);
}

.color-option.selected {
  border-width: 4px;
}

.color-option i {
  font-size: 24px;
  color: #333;
}
</style>
