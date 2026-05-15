<script setup>
import { computed, nextTick, ref } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { Transformer } from 'markmap-lib'
import { Markmap } from 'markmap-view'

const API_BASE_URL = 'http://127.0.0.1:8000'

const datasetPath = ref('')
const loading = ref(false)
const errorMessage = ref('')
const markdown = ref('')
const validation = ref(null)
const activeTab = ref('meta')
const readerScroll = ref(null)
const readerCompact = ref(false)

const extractTemplate = ref('generic_qa')
const extractViewMode = ref('level12')
const selectedExtractRangeIds = ref([])
const customRegex = ref('(?P<front>^##\\s+.+?)\\n(?P<back>[\\s\\S]*?)(?=^##\\s+|\\Z)')
const previewLoading = ref(false)
const exportLoading = ref(false)
const extractError = ref('')
const previewCards = ref([])
const previewTotal = ref(0)
const exportResult = ref(null)

const mindmapLoading = ref(false)
const mindmapError = ref('')
const mindmapMessage = ref('')
const mindmapHeadingCount = ref(0)
const mindmapSvg = ref(null)
const outlineItems = ref([])
const outlineLoading = ref(false)
const outlineError = ref('')
const selectedOutlineId = ref('')
const outlineViewMode = ref('level12')
const mindmapScale = ref(1)
const mindmapReady = ref(false)
const transformer = new Transformer()
let markmapInstance = null
let readerScrollTimer = null

const tabs = [
  { id: 'qa', label: 'AI 问答 & 溯源' },
  { id: 'mindmap', label: '动态脑图' },
  { id: 'extract', label: '规则抽取 & 制卡' },
  { id: 'meta', label: '数据集元信息' },
]

const templateOptions = [
  { value: 'japanese_vocab', label: '日语词汇模板' },
  { value: 'generic_qa', label: '通用问答模板' },
  { value: 'custom_regex', label: '自定义正则模板' },
]

const outlineViewOptions = [
  { value: 'level1', label: '只看一级标题' },
  { value: 'level12', label: '一级 + 二级标题' },
  { value: 'vocab', label: '只看单词' },
  { value: 'pattern', label: '只看文型/句型' },
  { value: 'examples', label: '只看例文' },
  { value: 'conversation', label: '只看会话' },
  { value: 'grammar', label: '只看文法' },
  { value: 'exercise_a', label: '只看练习A' },
  { value: 'exercise_b', label: '只看练习B' },
  { value: 'exercise_c', label: '只看练习C' },
  { value: 'problem', label: '只看问题' },
]

marked.setOptions({
  gfm: true,
  breaks: false,
})

const renderedMarkdown = computed(() => {
  const html = marked.parse(markdown.value || '')
  const cleanHtml = DOMPurify.sanitize(html, {
    ADD_ATTR: ['target'],
  })
  return addHeadingIds(cleanHtml)
})

const warningSummary = computed(() => {
  if (!validation.value?.warnings?.length) return ''
  return validation.value.warnings.join('；')
})

const canPreview = computed(() => Boolean(markdown.value && !previewLoading.value))
const canExport = computed(() => previewCards.value.length > 0 && !exportLoading.value)

const displayedOutlineItems = computed(() => {
  return filterOutlineItems(outlineViewMode.value)
})

const displayedExtractRangeItems = computed(() => {
  return filterOutlineItems(extractViewMode.value)
})

const currentReaderContext = computed(() => {
  if (!outlineItems.value.length) return null
  const current =
    outlineItems.value.find((item) => item.id === selectedOutlineId.value) ||
    outlineItems.value[0]
  if (!current) return null

  const lesson =
    current.category === 'lesson'
      ? current.title
      : current.parent_title || (current.category === 'intro' ? '引言' : current.level === 1 ? current.title : '-')

  return {
    page: current.page ? `P${current.page}` : 'P-',
    chapter: current.title,
    lesson,
  }
})

async function loadDataset() {
  if (!datasetPath.value.trim()) {
    errorMessage.value = '请输入本地数据集目录的绝对路径。'
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    const { response, data } = await fetchJson(`${API_BASE_URL}/api/dataset/load`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: datasetPath.value.trim() }),
    })
    if (!response.ok) {
      errorMessage.value = formatApiError(data)
      return
    }

    markdown.value = data.markdown
    validation.value = data.validation
    activeTab.value = 'meta'
    resetDerivedResults()
    await generateOutline()
  } catch (error) {
    errorMessage.value = `无法连接后端服务：${formatConnectionError(error)}`
  } finally {
    loading.value = false
  }
}

async function generateOutline() {
  if (!markdown.value) return

  outlineLoading.value = true
  outlineError.value = ''

  try {
    const { response, data } = await fetchJson(`${API_BASE_URL}/api/outline/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        markdown: markdown.value,
        dataset_path: validation.value?.dataset_path,
        json_file: validation.value?.json_file,
      }),
    })
    if (!response.ok) {
      outlineError.value = formatApiError(data)
      return
    }
    outlineItems.value = data.items || []
    mindmapHeadingCount.value = data.heading_count || 0
    if (!selectedOutlineId.value && outlineItems.value.length) {
      selectedOutlineId.value = outlineItems.value[0].id
    }
  } catch (error) {
    outlineError.value = `目录整理失败：${error.message}`
  } finally {
    outlineLoading.value = false
  }
}

function switchTab(tabId) {
  activeTab.value = tabId
  if (tabId === 'mindmap' || tabId === 'extract') {
    readerCompact.value = true
  }
}

function activeFocusLabel() {
  return activeTab.value === 'extract' ? '规则抽取&制卡专注' : '脑图专注'
}

function filterOutlineItems(mode) {
  if (mode === 'level1') {
    return outlineItems.value.filter((item) => item.level === 1)
  }
  if (mode === 'level12') {
    return outlineItems.value.filter((item) => item.level <= 2)
  }
  return outlineItems.value.filter((item) => item.category === mode)
}

async function previewExtract() {
  if (!markdown.value) {
    extractError.value = '请先加载数据集。'
    return
  }

  previewLoading.value = true
  extractError.value = ''
  exportResult.value = null

  try {
    const { response, data } = await fetchJson(`${API_BASE_URL}/api/extract/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildExtractPayload({ limit: 30 })),
    })
    if (!response.ok) {
      extractError.value = formatApiError(data)
      return
    }
    previewCards.value = data.cards
    previewTotal.value = data.total
  } catch (error) {
    extractError.value = `抽取失败：${error.message}`
  } finally {
    previewLoading.value = false
  }
}

async function exportCsv() {
  if (!canExport.value) return

  exportLoading.value = true
  extractError.value = ''

  try {
    const { response, data } = await fetchJson(`${API_BASE_URL}/api/anki/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildExtractPayload()),
    })
    if (!response.ok) {
      extractError.value = formatApiError(data)
      return
    }
    exportResult.value = data
  } catch (error) {
    extractError.value = `导出失败：${error.message}`
  } finally {
    exportLoading.value = false
  }
}

async function generateMindmap() {
  if (!markdown.value) {
    mindmapError.value = '请先加载数据集。'
    return
  }

  mindmapLoading.value = true
  mindmapError.value = ''
  mindmapMessage.value = ''

  try {
    if (!outlineItems.value.length) {
      await generateOutline()
    }

    const items = displayedOutlineItems.value
    mindmapHeadingCount.value = items.length
    if (items.length < 2) {
      clearMindmap()
      mindmapMessage.value = '当前筛选下标题较少，暂不适合生成脑图。'
      return
    }

    await nextTick()
    renderMindmap(outlineItemsToMindmapMarkdown(items))
    mindmapMessage.value = '已根据当前筛选的章节目录生成脑图。'
  } catch (error) {
    mindmapError.value = `生成脑图失败：${error.message}`
  } finally {
    mindmapLoading.value = false
  }
}

function buildExtractPayload(extra = {}) {
  return {
    markdown: markdown.value,
    template: extractTemplate.value,
    custom_regex: extractTemplate.value === 'custom_regex' ? customRegex.value : null,
    ranges: selectedExtractRanges(),
    ...extra,
  }
}

function selectedExtractRanges() {
  if (!selectedExtractRangeIds.value.length) return null
  const selectedItems = outlineItems.value.filter((item) => selectedExtractRangeIds.value.includes(item.id))
  return selectedItems.map((item) => ({
    start: item.start_line,
    end: item.end_line,
  }))
}

function renderMindmap(outline) {
  if (!mindmapSvg.value) return
  clearMindmap()
  const { root } = transformer.transform(outline)
  markmapInstance = Markmap.create(
    mindmapSvg.value,
    {
      autoFit: false,
      pan: true,
      zoom: true,
      duration: 250,
      maxWidth: 360,
      paddingX: 12,
    },
    root,
  )
  mindmapScale.value = 1
  mindmapReady.value = true
  markmapInstance.fit()
}

function zoomMindmap(delta) {
  if (!markmapInstance) return
  mindmapScale.value = Math.max(0.35, Math.min(3, mindmapScale.value + delta))
  markmapInstance.rescale(mindmapScale.value)
}

function fitMindmap() {
  if (!markmapInstance) return
  mindmapScale.value = 1
  markmapInstance.fit()
}

function clearMindmap() {
  if (mindmapSvg.value) {
    mindmapSvg.value.innerHTML = ''
  }
  markmapInstance = null
  mindmapReady.value = false
}

function resetDerivedResults() {
  previewCards.value = []
  previewTotal.value = 0
  exportResult.value = null
  extractError.value = ''
  mindmapError.value = ''
  mindmapMessage.value = ''
  mindmapHeadingCount.value = 0
  outlineItems.value = []
  outlineError.value = ''
  selectedOutlineId.value = ''
  outlineViewMode.value = 'level12'
  extractViewMode.value = 'level12'
  selectedExtractRangeIds.value = []
  clearMindmap()
}

function formatOutlineDisplayTitle(item) {
  if (isCategoryOnlyMode(outlineViewMode.value) && item.parent_title) {
    if (['vocab', 'pattern', 'examples', 'conversation', 'exercise_a', 'exercise_b', 'exercise_c', 'problem'].includes(item.category)) {
      return `${item.category_label} · ${item.parent_title}`
    }
    return `${item.title} · ${item.parent_title}`
  }
  return item.title
}

function formatExtractRangeDisplayTitle(item) {
  if (isCategoryOnlyMode(extractViewMode.value) && item.parent_title) {
    if (['vocab', 'pattern', 'examples', 'conversation', 'exercise_a', 'exercise_b', 'exercise_c', 'problem'].includes(item.category)) {
      return `${item.category_label} · ${item.parent_title}`
    }
    return `${item.title} · ${item.parent_title}`
  }
  return item.title
}

function outlineItemClass(item) {
  if (item.level === 1) return 'font-semibold text-slate-900'
  if (item.category !== 'other') return 'text-slate-700'
  return 'text-slate-600'
}

function outlineItemPadding(item) {
  if (outlineViewMode.value !== 'level1' && outlineViewMode.value !== 'level12') return 8
  return 8 + Math.min(item.level - 1, 4) * 14
}

function extractRangeItemPadding(item) {
  if (isCategoryOnlyMode(extractViewMode.value)) return 8
  return 8 + Math.min(item.level - 1, 4) * 14
}

function isCategoryOnlyMode(mode) {
  return mode !== 'level1' && mode !== 'level12'
}

function toggleExtractRange(item) {
  const current = new Set(selectedExtractRangeIds.value)
  if (current.has(item.id)) {
    current.delete(item.id)
  } else {
    current.add(item.id)
  }
  selectedExtractRangeIds.value = Array.from(current)
  previewCards.value = []
  previewTotal.value = 0
  exportResult.value = null
}

function selectAllDisplayedExtractRanges() {
  selectedExtractRangeIds.value = displayedExtractRangeItems.value.map((item) => item.id)
  previewCards.value = []
  previewTotal.value = 0
  exportResult.value = null
}

function clearExtractRanges() {
  selectedExtractRangeIds.value = []
  previewCards.value = []
  previewTotal.value = 0
  exportResult.value = null
}

function outlineItemsToMindmapMarkdown(items) {
  if (!items.length) return ''
  const categoryOnly = outlineViewMode.value !== 'level1' && outlineViewMode.value !== 'level12'
  if (categoryOnly) {
    const lines = []
    let currentParent = ''
    for (const item of items) {
      const parent = item.parent_title || '未分组'
      if (parent !== currentParent) {
        currentParent = parent
        lines.push(`# ${parent}`)
      }
      lines.push(`## ${item.title}${item.page ? ` P${item.page}` : ''}`)
    }
    return lines.join('\n')
  }

  const minLevel = Math.min(...items.map((item) => item.level))
  return items
    .map((item) => {
      const level = Math.max(1, Math.min(6, item.level - minLevel + 1))
      return `${'#'.repeat(level)} ${item.title}${item.page ? ` P${item.page}` : ''}`
    })
    .join('\n')
}

function addHeadingIds(html) {
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')
  doc.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach((heading, index) => {
    heading.id = `heading-${index}`
    heading.classList.add('scroll-mt-6')
  })
  return doc.body.innerHTML
}

async function scrollToOutlineItem(item) {
  selectedOutlineId.value = item.id
  await nextTick()
  const target = document.getElementById(item.id)
  const container = readerScroll.value
  if (!target || !container) return
  container.scrollTo({
    top: target.offsetTop - 16,
    behavior: 'smooth',
  })
}

function syncOutlineFromReader() {
  if (!outlineItems.value.length || readerScrollTimer) return
  readerScrollTimer = window.setTimeout(() => {
    readerScrollTimer = null
    const container = readerScroll.value
    if (!container) return
    let current = outlineItems.value[0]
    for (const item of outlineItems.value) {
      const target = document.getElementById(item.id)
      if (!target) continue
      if (target.offsetTop <= container.scrollTop + 96) {
        current = item
      } else {
        break
      }
    }
    if (current) selectedOutlineId.value = current.id
  }, 120)
}

async function fetchJson(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    })
    const text = await response.text()
    const data = text ? JSON.parse(text) : {}
    return { response, data }
  } finally {
    window.clearTimeout(timeoutId)
  }
}

function formatApiError(data) {
  if (typeof data?.detail === 'string') return data.detail
  const detail = data?.detail
  const errors = detail?.errors || []
  const warnings = detail?.warnings || []
  return [...errors, ...warnings].join('；') || '请求失败，请检查输入。'
}

function formatConnectionError(error) {
  if (error.name === 'AbortError') {
    return `请求超时。请确认 FastAPI 后端已在 ${API_BASE_URL} 正常运行。`
  }
  return `${error.message}。请确认 FastAPI 后端已在 http://127.0.0.1:8000 启动。`
}
</script>

<template>
  <div class="min-h-screen bg-[#f6f7f9] text-slate-900">
    <header class="border-b border-slate-200 bg-white">
      <div class="mx-auto flex max-w-[1600px] flex-col gap-2 px-4 py-3">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div class="flex min-w-0 flex-1 gap-2">
            <input
              v-model="datasetPath"
              class="h-10 min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
              placeholder="/absolute/path/to/dataset"
              @keyup.enter="loadDataset"
            />
            <button
              class="h-10 shrink-0 rounded-md bg-sky-600 px-4 text-sm font-medium text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-400"
              :disabled="loading"
              @click="loadDataset"
            >
              {{ loading ? '加载中' : '加载目录' }}
            </button>
          </div>

          <div v-if="validation" class="flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <span class="rounded-md bg-slate-100 px-2.5 py-1">MD: {{ validation.markdown_file }}</span>
            <span class="rounded-md bg-slate-100 px-2.5 py-1">图片: {{ validation.image_count }}</span>
            <span
              v-if="validation.warnings?.length"
              class="rounded-md bg-amber-50 px-2.5 py-1 text-amber-800"
            >
              警告 {{ validation.warnings.length }}
            </span>
          </div>
        </div>

        <div v-if="errorMessage" class="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          {{ errorMessage }}
        </div>
      </div>
    </header>

    <main
      class="mx-auto grid max-w-[1800px] gap-4 px-4 py-4 transition-all duration-200"
      :class="
        readerCompact && (activeTab === 'mindmap' || activeTab === 'extract')
          ? 'lg:grid-cols-[minmax(280px,0.85fr)_minmax(760px,2.65fr)]'
          : 'lg:grid-cols-[3fr_2fr]'
      "
    >
      <section class="min-h-[calc(100vh-104px)] overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div class="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <h1 class="text-base font-semibold text-slate-900">Markdown 阅读器</h1>
          <div class="flex min-w-0 flex-1 items-center justify-end gap-2">
            <div
              v-if="currentReaderContext"
              class="min-w-0 rounded-md bg-slate-100 px-2.5 py-1 text-xs text-slate-600"
              :title="`${currentReaderContext.page}｜章节：${currentReaderContext.chapter}｜课时：${currentReaderContext.lesson}`"
            >
              <span class="font-semibold text-slate-800">{{ currentReaderContext.page }}</span>
              <span class="mx-1 text-slate-400">|</span>
              <span class="inline-block max-w-[13rem] truncate align-bottom">章节：{{ currentReaderContext.chapter }}</span>
              <span class="mx-1 text-slate-400">|</span>
              <span class="inline-block max-w-[8rem] truncate align-bottom">课时：{{ currentReaderContext.lesson }}</span>
            </div>
            <button
              v-if="activeTab === 'mindmap' || activeTab === 'extract'"
              class="h-8 shrink-0 rounded-md border border-slate-300 bg-white px-2.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
              @click="readerCompact = !readerCompact"
            >
              {{ readerCompact ? '恢复阅读器' : activeFocusLabel() }}
            </button>
          </div>
        </div>

        <div
          ref="readerScroll"
          class="h-[calc(100vh-160px)] overflow-auto px-5 py-4"
          @scroll="syncOutlineFromReader"
        >
          <article
            v-if="markdown"
            class="markdown-body mx-auto max-w-4xl"
            v-html="renderedMarkdown"
          />
          <div v-else class="flex h-full items-center justify-center text-sm text-slate-500">
            加载数据集后在此阅读 Markdown 内容
          </div>
        </div>
      </section>

      <aside class="min-h-[calc(100vh-104px)] overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div class="flex overflow-x-auto border-b border-slate-200">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            class="shrink-0 border-b-2 px-4 py-3 text-sm font-medium transition"
            :class="
              activeTab === tab.id
                ? 'border-sky-600 text-sky-700'
                : 'border-transparent text-slate-600 hover:bg-slate-50 hover:text-slate-900'
            "
            @click="switchTab(tab.id)"
          >
            {{ tab.label }}
          </button>
        </div>

        <div class="h-[calc(100vh-160px)] overflow-auto p-4">
          <div v-if="activeTab === 'qa'" class="flex h-full items-center justify-center text-sm text-slate-500">
            AI 问答 & 溯源 占位
          </div>

          <div v-else-if="activeTab === 'mindmap'" class="grid h-full min-h-0 gap-4 xl:grid-cols-[minmax(220px,0.42fr)_minmax(320px,0.58fr)]">
            <section class="min-h-0 overflow-hidden rounded-md border border-slate-200">
              <div class="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
                <div>
                  <h2 class="text-sm font-semibold text-slate-900">章节标题整理</h2>
                  <p class="mt-0.5 text-xs text-slate-500">
                    显示 {{ displayedOutlineItems.length }} / {{ outlineItems.length }} 个
                  </p>
                </div>
                <button
                  class="h-8 rounded-md border border-slate-300 bg-white px-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
                  :disabled="!markdown || outlineLoading"
                  @click="generateOutline"
                >
                  {{ outlineLoading ? '整理中' : '重新整理' }}
                </button>
              </div>

              <div class="border-b border-slate-200 px-3 py-2">
                <label class="grid gap-1 text-xs font-medium text-slate-600">
                  <span>显示范围</span>
                  <select
                    v-model="outlineViewMode"
                    class="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm font-normal text-slate-800 outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                  >
                    <option v-for="option in outlineViewOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
              </div>

              <div v-if="outlineError" class="m-3 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
                {{ outlineError }}
              </div>

              <div class="h-[468px] overflow-auto px-2 py-2">
                <button
                  v-for="item in displayedOutlineItems"
                  :key="item.id"
                  class="mb-1 grid w-full grid-cols-[1fr_auto] items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm transition"
                  :class="
                    selectedOutlineId === item.id
                      ? 'bg-sky-50 text-sky-800 ring-1 ring-sky-200'
                      : 'text-slate-700 hover:bg-slate-50'
                  "
                  :style="{ paddingLeft: `${outlineItemPadding(item)}px` }"
                  @click="scrollToOutlineItem(item)"
                >
                  <span class="min-w-0">
                    <span class="block truncate" :class="outlineItemClass(item)">
                      {{ formatOutlineDisplayTitle(item) }}
                    </span>
                    <span v-if="item.level > 1" class="mt-0.5 block truncate text-[11px] text-slate-500">
                      {{ item.category_label }}{{ item.parent_title ? ` / ${item.parent_title}` : '' }}
                    </span>
                  </span>
                  <span class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
                    {{ item.page ? `P${item.page}` : '-' }}
                  </span>
                </button>

                <div v-if="!outlineLoading && outlineItems.length === 0" class="px-3 py-8 text-center text-sm text-slate-500">
                  加载数据集后整理章节标题
                </div>
                <div v-else-if="!outlineLoading && displayedOutlineItems.length === 0" class="px-3 py-8 text-center text-sm text-slate-500">
                  当前筛选下没有标题
                </div>
              </div>
            </section>

            <section class="min-h-0 space-y-3">
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 class="text-sm font-semibold text-slate-900">动态脑图</h2>
                  <p class="mt-1 text-xs text-slate-500">标题数：{{ mindmapHeadingCount }}</p>
                </div>
                <div class="flex flex-wrap gap-2">
                  <button
                    class="h-8 rounded-md border border-slate-300 bg-white px-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
                    :disabled="!mindmapReady"
                    @click="zoomMindmap(0.2)"
                  >
                    放大
                  </button>
                  <button
                    class="h-8 rounded-md border border-slate-300 bg-white px-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
                    :disabled="!mindmapReady"
                    @click="zoomMindmap(-0.2)"
                  >
                    缩小
                  </button>
                  <button
                    class="h-8 rounded-md border border-slate-300 bg-white px-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
                    :disabled="!mindmapReady"
                    @click="fitMindmap"
                  >
                    归正
                  </button>
                  <button
                    class="h-8 rounded-md bg-sky-600 px-3 text-sm font-medium text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-400"
                    :disabled="!markdown || mindmapLoading"
                    @click="generateMindmap"
                  >
                    {{ mindmapLoading ? '生成中' : '生成脑图' }}
                  </button>
                </div>
              </div>

              <div v-if="mindmapError" class="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
                {{ mindmapError }}
              </div>
              <div v-if="mindmapMessage" class="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                {{ mindmapMessage }}
              </div>

              <div class="h-[520px] overflow-hidden rounded-md border border-slate-200 bg-white">
                <svg ref="mindmapSvg" class="mindmap-canvas h-full w-full cursor-grab active:cursor-grabbing" />
                <div v-if="!mindmapMessage && !mindmapError" class="-mt-[520px] flex h-[520px] items-center justify-center text-sm text-slate-500">
                  加载数据集后生成脑图
                </div>
              </div>
            </section>
          </div>

          <div v-else-if="activeTab === 'extract'" class="grid h-full min-h-0 gap-4 xl:grid-cols-[minmax(220px,0.42fr)_minmax(320px,0.58fr)]">
            <section class="min-h-0 overflow-hidden rounded-md border border-slate-200">
              <div class="flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2">
                <div>
                  <h2 class="text-sm font-semibold text-slate-900">章节标题整理</h2>
                  <p class="mt-0.5 text-xs text-slate-500">
                    已选 {{ selectedExtractRangeIds.length }} / 显示 {{ displayedExtractRangeItems.length }} 个
                  </p>
                </div>
                <button
                  class="h-8 rounded-md border border-slate-300 bg-white px-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
                  :disabled="!markdown || outlineLoading"
                  @click="generateOutline"
                >
                  {{ outlineLoading ? '整理中' : '重新整理' }}
                </button>
              </div>

              <div class="border-b border-slate-200 px-3 py-2">
                <label class="grid gap-1 text-xs font-medium text-slate-600">
                  <span>抽卡范围</span>
                  <select
                    v-model="extractViewMode"
                    class="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm font-normal text-slate-800 outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                    @change="clearExtractRanges"
                  >
                    <option v-for="option in outlineViewOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <div class="mt-2 flex flex-wrap gap-2">
                  <button
                    class="h-7 rounded-md border border-slate-300 bg-white px-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
                    :disabled="displayedExtractRangeItems.length === 0"
                    @click="selectAllDisplayedExtractRanges"
                  >
                    全选当前
                  </button>
                  <button
                    class="h-7 rounded-md border border-slate-300 bg-white px-2 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
                    :disabled="selectedExtractRangeIds.length === 0"
                    @click="clearExtractRanges"
                  >
                    清空选择
                  </button>
                </div>
              </div>

              <div v-if="outlineError" class="m-3 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
                {{ outlineError }}
              </div>

              <div class="h-[430px] overflow-auto px-2 py-2">
                <button
                  v-for="item in displayedExtractRangeItems"
                  :key="item.id"
                  class="mb-1 grid w-full grid-cols-[auto_1fr_auto] items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm transition"
                  :class="
                    selectedExtractRangeIds.includes(item.id)
                      ? 'bg-emerald-50 text-emerald-900 ring-1 ring-emerald-200'
                      : 'text-slate-700 hover:bg-slate-50'
                  "
                  :style="{ paddingLeft: `${extractRangeItemPadding(item)}px` }"
                  @click="toggleExtractRange(item)"
                >
                  <span
                    class="mt-0.5 h-4 w-4 rounded border"
                    :class="selectedExtractRangeIds.includes(item.id) ? 'border-emerald-500 bg-emerald-500' : 'border-slate-300 bg-white'"
                  />
                  <span class="min-w-0">
                    <span class="block truncate" :class="outlineItemClass(item)">
                      {{ formatExtractRangeDisplayTitle(item) }}
                    </span>
                    <span v-if="item.level > 1" class="mt-0.5 block truncate text-[11px] text-slate-500">
                      {{ item.category_label }}{{ item.parent_title ? ` / ${item.parent_title}` : '' }}
                    </span>
                  </span>
                  <span class="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">
                    {{ item.page ? `P${item.page}` : '-' }}
                  </span>
                </button>

                <div v-if="!outlineLoading && outlineItems.length === 0" class="px-3 py-8 text-center text-sm text-slate-500">
                  加载数据集后整理章节标题
                </div>
                <div v-else-if="!outlineLoading && displayedExtractRangeItems.length === 0" class="px-3 py-8 text-center text-sm text-slate-500">
                  当前筛选下没有标题
                </div>
              </div>
            </section>

            <section class="min-h-0 space-y-4 overflow-auto pr-1">
              <div class="grid gap-3">
                <label class="grid gap-1 text-sm">
                  <span class="font-medium text-slate-700">模板选择</span>
                  <select
                    v-model="extractTemplate"
                    class="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                    @change="previewCards = []; previewTotal = 0; exportResult = null"
                  >
                    <option v-for="option in templateOptions" :key="option.value" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>

                <label v-if="extractTemplate === 'custom_regex'" class="grid gap-1 text-sm">
                  <span class="font-medium text-slate-700">自定义正则</span>
                  <textarea
                    v-model="customRegex"
                    rows="4"
                    class="resize-y rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-xs outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
                  />
                </label>

                <div class="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
                  {{ selectedExtractRangeIds.length ? `将从 ${selectedExtractRangeIds.length} 个选中范围抽卡` : '未选择范围时默认从全文抽卡' }}
                </div>

                <div class="flex flex-wrap gap-2">
                  <button
                    class="h-9 rounded-md bg-sky-600 px-3 text-sm font-medium text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-400"
                    :disabled="!canPreview"
                    @click="previewExtract"
                  >
                    {{ previewLoading ? '预览中' : '预览抽取' }}
                  </button>
                  <button
                    class="h-9 rounded-md bg-emerald-600 px-3 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-400"
                    :disabled="!canExport"
                    @click="exportCsv"
                  >
                    {{ exportLoading ? '导出中' : '导出 CSV' }}
                  </button>
                </div>
              </div>

              <div v-if="extractError" class="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              {{ extractError }}
              </div>

              <div v-if="exportResult" class="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              已导出 {{ exportResult.total }} 条：
              <a class="font-medium underline" :href="exportResult.download_url" target="_blank">
                {{ exportResult.filename }}
              </a>
              </div>

              <div class="rounded-md border border-slate-200">
              <div class="flex items-center justify-between border-b border-slate-200 px-3 py-2 text-sm">
                <span class="font-medium text-slate-700">预览结果</span>
                <span class="text-slate-500">共 {{ previewTotal }} 条</span>
              </div>
              <div class="overflow-auto">
                <table class="min-w-full divide-y divide-slate-200 text-sm">
                  <thead class="bg-slate-50 text-left text-xs uppercase text-slate-500">
                    <tr>
                      <th class="px-3 py-2 font-semibold">Front</th>
                      <th class="px-3 py-2 font-semibold">Back</th>
                      <th class="px-3 py-2 font-semibold">Image</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    <tr v-for="(card, index) in previewCards" :key="`${card.front}-${index}`">
                      <td class="max-w-[180px] px-3 py-2 align-top font-medium text-slate-900">
                        {{ card.front }}
                      </td>
                      <td class="max-w-[260px] px-3 py-2 align-top text-slate-700">
                        {{ card.back }}
                      </td>
                      <td class="max-w-[180px] break-all px-3 py-2 align-top text-xs text-slate-500">
                        {{ card.image || '-' }}
                      </td>
                    </tr>
                    <tr v-if="previewCards.length === 0">
                      <td colspan="3" class="px-3 py-8 text-center text-slate-500">
                        暂无预览数据
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              </div>
            </section>
          </div>

          <div v-else class="space-y-4">
            <div v-if="errorMessage" class="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
              {{ errorMessage }}
            </div>

            <template v-if="validation">
              <dl class="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-2 text-sm">
                <dt class="text-slate-500">valid</dt>
                <dd class="font-medium" :class="validation.valid ? 'text-emerald-700' : 'text-rose-700'">
                  {{ validation.valid }}
                </dd>
                <dt class="text-slate-500">dataset</dt>
                <dd class="break-all">{{ validation.dataset_name }}</dd>
                <dt class="text-slate-500">path</dt>
                <dd class="break-all">{{ validation.dataset_path }}</dd>
                <dt class="text-slate-500">markdown</dt>
                <dd>{{ validation.markdown_file || '-' }}</dd>
                <dt class="text-slate-500">json</dt>
                <dd>{{ validation.json_file || '-' }}</dd>
                <dt class="text-slate-500">images</dt>
                <dd>{{ validation.image_count }}</dd>
              </dl>

              <div v-if="warningSummary" class="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                {{ warningSummary }}
              </div>

              <pre class="overflow-auto rounded-md bg-slate-950 p-3 text-xs leading-6 text-slate-100">{{ JSON.stringify(validation, null, 2) }}</pre>
            </template>

            <div v-else class="text-sm text-slate-500">
              当前未加载数据集
            </div>
          </div>
        </div>
      </aside>
    </main>
  </div>
</template>
