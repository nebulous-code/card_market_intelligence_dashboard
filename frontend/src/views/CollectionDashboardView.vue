<template>
  <div>
    <div class="text-h4 font-weight-bold mb-2">Your Collection</div>

    <v-skeleton-loader v-if="loading" type="paragraph" />

    <template v-else-if="session">
      <v-alert type="success" variant="tonal" class="mb-4">
        Your collection has been loaded. The dashboard is coming in the next update.
      </v-alert>
      <div class="text-body-1">
        Loaded <strong>{{ session.card_count }}</strong>
        {{ session.card_count === 1 ? 'card' : 'cards' }}
        across <strong>{{ session.set_count }}</strong>
        {{ session.set_count === 1 ? 'set' : 'sets' }}.
      </div>
      <div class="mt-6">
        <v-btn color="primary" variant="outlined" :to="'/collection'">
          Upload a different collection
        </v-btn>
      </div>
    </template>

    <template v-else>
      <v-alert type="info" variant="tonal" class="mb-4">
        No collection is loaded for this session.
      </v-alert>
      <v-btn color="primary" :to="'/collection'">Upload your collection</v-btn>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { getCollectionSession } from '../api/index.js'

const loading = ref(true)
const session = ref(null)

onMounted(async () => {
  try {
    session.value = await getCollectionSession()
  } catch {
    session.value = null
  } finally {
    loading.value = false
  }
})
</script>
