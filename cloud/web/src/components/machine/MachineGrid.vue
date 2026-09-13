<template>
  <div class="machine-grid">
    <MachineCard v-for="m in machines" :key="m.id" :machine="m" @confirm="$emit('confirm', $event)" />
  </div>
</template>

<script setup lang="ts">
import type { Machine } from '@/models'
import MachineCard from './MachineCard.vue'

defineProps<{ machines: Machine[] }>()
defineEmits<{ confirm: [id: string] }>()
</script>

<style scoped>
.machine-grid { display: flex; flex-wrap: wrap; gap: 16px; }
</style>
