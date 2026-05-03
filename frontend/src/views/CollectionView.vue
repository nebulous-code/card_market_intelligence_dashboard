<template>
  <div>
    <div class="text-h4 font-weight-bold mb-2">Analyze Your Collection</div>
    <div class="text-body-2 text-medium-emphasis mb-2">
      Upload a list of the cards you own and get a personalized dashboard
      of how they're priced today.
    </div>
    <div class="text-body-2 mb-1">
      Download the template, fill it out in Excel, and upload it back. The
      dashboard updates as soon as the upload validates.
    </div>
    <div class="text-caption text-medium-emphasis mb-6">
      Your collection is stored privately for this session and automatically
      deleted after 24 hours.
      <router-link to="/privacy" class="privacy-link">View privacy policy</router-link>
    </div>

    <v-alert
      v-if="emptyRedirect"
      type="info"
      variant="tonal"
      class="mb-4"
      closable
      @click:close="dismissEmptyBanner"
    >
      <strong>No collection loaded yet</strong> &mdash; upload your collection
      or use the mock collection to get started.
    </v-alert>

    <v-row class="mb-6">
      <v-col cols="12" md="4">
        <v-card class="action-card h-100" :loading="downloading">
          <v-card-text class="d-flex flex-column h-100">
            <v-icon size="40" class="mb-3" color="primary">mdi-file-download</v-icon>
            <div class="text-h6 font-weight-bold mb-1">Download Template</div>
            <div class="text-body-2 text-medium-emphasis mb-4 flex-grow-1">
              A pre-formatted Excel workbook with the current set list as a
              dropdown. Fill in the rows you own and re-upload.
            </div>
            <v-btn color="primary" block @click="onDownloadTemplate" :loading="downloading">
              Download
            </v-btn>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="4">
        <v-card class="action-card h-100" :loading="uploading">
          <v-card-text class="d-flex flex-column h-100">
            <v-icon size="40" class="mb-3" color="primary">mdi-cloud-upload</v-icon>
            <div class="text-h6 font-weight-bold mb-1">Upload Collection</div>
            <div class="text-body-2 text-medium-emphasis mb-4 flex-grow-1">
              Pick the filled-out template from your computer. We'll validate
              it and create your private session.
            </div>
            <input
              ref="fileInput"
              type="file"
              accept=".xlsx"
              class="d-none"
              @change="onFileSelected"
            />
            <v-btn color="primary" block @click="openFilePicker" :loading="uploading">
              Choose file...
            </v-btn>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="4">
        <v-card class="action-card h-100" :loading="loadingMock">
          <v-card-text class="d-flex flex-column h-100">
            <v-icon size="40" class="mb-3" color="primary">mdi-flask</v-icon>
            <div class="text-h6 font-weight-bold mb-1">Use Mock Collection</div>
            <div class="text-body-2 text-medium-emphasis mb-4 flex-grow-1">
              Skip the upload and load a sample collection so you can take the
              dashboard for a spin.
            </div>
            <v-btn color="primary" block @click="onUseMock" :loading="loadingMock">
              Load mock
            </v-btn>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-alert v-if="generalError" type="error" variant="tonal" class="mb-4">
      {{ generalError }}
    </v-alert>

    <v-card v-if="validationFailure" class="error-panel pa-4">
      <div class="text-h6 font-weight-bold mb-2">
        We couldn't process your upload
      </div>
      <div v-if="validationFailure.structural_error" class="text-body-2 mb-2">
        {{ validationFailure.structural_error }}
      </div>
      <div v-else class="text-body-2 mb-2">
        {{ validationFailure.error_rows.length }}
        of {{ validationFailure.total_rows }} rows had errors.
      </div>
      <ul
        v-if="validationFailure.distinct_error_messages?.length"
        class="text-body-2 mb-4 ml-4"
      >
        <li v-for="msg in validationFailure.distinct_error_messages" :key="msg">
          {{ msg }}
        </li>
      </ul>
      <div class="d-flex flex-wrap ga-2">
        <v-btn
          v-if="!validationFailure.structural_error && lastUploadedFile"
          color="primary"
          @click="onDownloadAnnotated"
          :loading="annotating"
        >
          Download Annotated Workbook
        </v-btn>
        <v-btn variant="outlined" @click="resetAndReopenPicker">
          Try Another File
        </v-btn>
      </div>
    </v-card>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  downloadAnnotatedWorkbook,
  downloadCollectionTemplate,
  uploadCollection,
  useMockCollection,
} from '../api/index.js'

const route = useRoute()
const router = useRouter()

const emptyRedirect = computed(() => route.query.empty === '1')

function dismissEmptyBanner() {
  // Drop the ?empty=1 marker so a refresh doesn't re-show the banner.
  const { empty: _omit, ...rest } = route.query
  router.replace({ query: rest })
}

const downloading = ref(false)
const uploading = ref(false)
const loadingMock = ref(false)
const annotating = ref(false)
const generalError = ref('')
const validationFailure = ref(null)
const lastUploadedFile = ref(null)
const fileInput = ref(null)

function clearFeedback() {
  generalError.value = ''
  validationFailure.value = null
}

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

async function onDownloadTemplate() {
  clearFeedback()
  downloading.value = true
  try {
    const blob = await downloadCollectionTemplate()
    const today = new Date().toISOString().slice(0, 10)
    triggerBlobDownload(blob, `card-collection-template-${today}.xlsx`)
  } catch (err) {
    generalError.value = 'Could not download the template. Please try again.'
  } finally {
    downloading.value = false
  }
}

function openFilePicker() {
  clearFeedback()
  fileInput.value?.click()
}

async function onFileSelected(event) {
  const file = event.target.files?.[0]
  if (!file) return
  await submitFile(file)
  // Reset input so picking the same file again still triggers `change`.
  event.target.value = ''
}

async function submitFile(file) {
  clearFeedback()
  lastUploadedFile.value = file
  uploading.value = true
  try {
    await uploadCollection(file)
    router.push('/collection/dashboard')
  } catch (err) {
    handleUploadError(err)
  } finally {
    uploading.value = false
  }
}

function handleUploadError(err) {
  const detail = err?.response?.data?.detail
  if (err?.response?.status === 422 && detail && typeof detail === 'object') {
    validationFailure.value = detail
    return
  }
  generalError.value = 'Could not process the upload. Please try again.'
}

async function onUseMock() {
  clearFeedback()
  loadingMock.value = true
  try {
    await useMockCollection()
    router.push('/collection/dashboard')
  } catch (err) {
    generalError.value = 'Could not load the mock collection.'
  } finally {
    loadingMock.value = false
  }
}

async function onDownloadAnnotated() {
  if (!lastUploadedFile.value) return
  annotating.value = true
  try {
    const blob = await downloadAnnotatedWorkbook(lastUploadedFile.value)
    triggerBlobDownload(blob, 'collection-errors.xlsx')
  } catch (err) {
    generalError.value = 'Could not generate the annotated workbook.'
  } finally {
    annotating.value = false
  }
}

function resetAndReopenPicker() {
  validationFailure.value = null
  lastUploadedFile.value = null
  openFilePicker()
}
</script>

<style scoped>
.action-card {
  transition: border 0.15s ease, box-shadow 0.15s ease;
  border: 1px solid transparent;
}
.action-card:hover {
  border-color: #e8412a;
  box-shadow: 0 4px 16px rgba(232, 65, 42, 0.2) !important;
}
.error-panel {
  border-left: 4px solid #cf6679;
}
.privacy-link {
  color: #e8412a;
  text-decoration: none;
}
.privacy-link:hover {
  text-decoration: underline;
}
</style>
