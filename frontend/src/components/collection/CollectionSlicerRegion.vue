<template>
  <div class="slicer-region d-flex flex-column">
    <div class="d-flex align-center mb-2 px-2 slicer-region-header">
      <v-icon :color="hasActive ? '#F5C842' : undefined" size="20">
        {{ icon }}
      </v-icon>
      <div class="text-subtitle-2 font-weight-bold ml-2 text-uppercase">
        {{ title }}
      </div>
      <v-spacer />
      <v-chip
        v-if="hasActive"
        size="x-small"
        color="#F5C842"
        variant="flat"
        class="font-weight-bold"
      >
        {{ filterSet.size }}
      </v-chip>
    </div>
    <div class="slicer-region-chips px-2">
      <v-chip
        v-for="entry in values"
        :key="entry.value"
        :color="isChipSelected(filterSet, entry.value) ? '#E8412A' : undefined"
        :variant="isChipSelected(filterSet, entry.value) ? 'flat' : 'outlined'"
        size="small"
        class="ma-1 chip-toggle"
        :class="{ 'chip-toggle--selected': isChipSelected(filterSet, entry.value) }"
        @click="emit('toggle', entry.value)"
      >
        {{ entry.label }}
      </v-chip>
    </div>
  </div>
</template>

<script setup>
/**
 * One region inside the slicer panel: header + scrolling chip area.
 *
 * The component emits a single ``toggle`` event with the chip value
 * the user clicked. The parent applies :func:`toggleChipSelection`
 * and writes the resulting Set back into ``filterState`` -- this
 * component is otherwise stateless.
 */

import { computed } from 'vue'
import { isChipSelected } from '../../utils/slicerState.js'

const props = defineProps({
  title: { type: String, required: true },
  icon: { type: String, required: true },
  values: { type: Array, required: true },
  filterSet: { type: Set, required: true },
})
const emit = defineEmits(['toggle'])

const hasActive = computed(() => props.filterSet.size > 0)
</script>

<style scoped>
.slicer-region {
  flex: 1 1 0;
  min-height: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding: 12px 0;
}
.slicer-region:last-child {
  border-bottom: none;
}
.slicer-region-header {
  flex-shrink: 0;
}
.slicer-region-chips {
  overflow-y: auto;
  flex: 1 1 0;
  min-height: 0;
}
.chip-toggle {
  cursor: pointer;
}
.chip-toggle--selected {
  color: #f5edd6 !important;
}
</style>
