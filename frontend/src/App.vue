<template>
  <a-layout class="layout">
    <a-layout-header class="header">
      <div class="logo">
        <div class="logo-icon-wrapper">
          <img v-if="logoReady" src="@/assets/logo.png" alt="MinerPick" class="logo-img" @error="logoReady = false" />
          <BuildOutlined v-else class="fallback-logo" />
        </div>
        <span class="logo-text">{{ t('app.title') }}</span>
      </div>
      <div class="header-right">
        <a-space>
          <a-button type="text" style="color: white" href="https://github.com/0mao0/MinerPick" target="_blank">
            <template #icon><GithubOutlined /></template>
            {{ t('app.github') }}
          </a-button>
          <a-button type="text" style="color: white" @click="showSettings = true">
            <template #icon><SettingOutlined /></template>
            {{ t('app.settings') }}
          </a-button>
          <a-dropdown>
            <a-button type="text" style="color: white">
              <template #icon><GlobalOutlined /></template>
              {{ locale === 'zh' ? '中文' : 'English' }}
            </a-button>
            <template #overlay>
              <a-menu @click="handleLocaleChange">
                <a-menu-item key="zh">中文</a-menu-item>
                <a-menu-item key="en">English</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </a-space>
      </div>
    </a-layout-header>
    
    <a-layout-content class="content">
      <div class="viewer-container">
        <!-- Left: PDF Viewer Panel -->
        <div class="side-panel pdf-panel" :style="{ width: leftWidth + '%' }">
          <div class="panel-header">
            <div class="header-left">
              <FilePdfOutlined /> <span>{{ t('app.original_pdf') }}</span>
            </div>
            
            <div v-if="pdfUrl" class="header-toolbar">
              <a-space>
                <a-button type="text" size="small" :disabled="currentPage <= 1" @click="currentPage--">
                  <template #icon><LeftOutlined /></template>
                </a-button>
                <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
                <a-button type="text" size="small" :disabled="currentPage >= totalPages" @click="currentPage++">
                  <template #icon><RightOutlined /></template>
                </a-button>
                <a-divider type="vertical" />
                <a-button type="text" size="small" @click="pdfScale = Math.min(3, pdfScale + 0.1)">
                  <template #icon><PlusOutlined /></template>
                </a-button>
                <a-button type="text" size="small" @click="pdfScale = Math.max(0.5, pdfScale - 0.1)">
                  <template #icon><MinusOutlined /></template>
                </a-button>
                <a-divider type="vertical" />
                <a-tooltip :title="isRawVisible ? t('app.hide_raw') : t('app.show_raw')">
                  <a-button 
                    type="text" 
                    size="small" 
                    @click="isRawVisible = !isRawVisible"
                    :class="{ 'btn-active-blue': isRawVisible }"
                  >
                    <template #icon>
                      <EyeOutlined v-if="isRawVisible" :style="{ color: '#1890ff' }" />
                      <EyeInvisibleOutlined v-else />
                    </template>
                  </a-button>
                </a-tooltip>
                <a-tooltip :title="isHighlightAll ? t('app.hide_modified') : t('app.show_modified')">
                  <a-button 
                    type="text" 
                    size="small" 
                    @click="isHighlightAll = !isHighlightAll"
                    :class="{ 'btn-active-red': isHighlightAll }"
                  >
                    <template #icon>
                      <EyeOutlined v-if="isHighlightAll" :style="{ color: '#ff4d4f' }" />
                      <EyeInvisibleOutlined v-else />
                    </template>
                  </a-button>
                </a-tooltip>
              </a-space>
            </div>

            <a-upload
              v-if="pdfUrl"
              name="file"
              :multiple="false"
              :action="`${apiBaseUrl}/api/upload`"
              @change="handleUploadChange"
              :showUploadList="false"
            >
              <a-button type="link" size="small">{{ t('app.upload') }}</a-button>
            </a-upload>
          </div>

          <div class="panel-body">
            <!-- Initial state: Drag & Drop upload area -->
            <div v-show="!pdfUrl" class="upload-area">
              <a-upload-dragger
                name="file"
                :multiple="false"
                :action="`${apiBaseUrl}/api/upload`"
                @change="handleUploadChange"
                :showUploadList="false"
                accept=".pdf"
              >
                <p class="ant-upload-drag-icon"><inbox-outlined /></p>
                <p class="ant-upload-text">{{ t('app.upload_hint') }}</p>
                <p class="ant-upload-hint">{{ t('app.upload_hint_sub') }}</p>
              </a-upload-dragger>
            </div>

            <!-- Document view: PDF renderer -->
            <PdfViewer 
              v-if="pdfUrl"
              :key="pdfUrl"
              v-model:currentPage="currentPage"
              v-model:totalPages="totalPages"
              v-model:scale="pdfScale"
              :url="pdfUrl" 
              :highlights="currentHighlights" 
              :preferredY="preferredY"
              :is-highlight-all="isHighlightAll"
              :is-raw-visible="isRawVisible"
              :content-list="contentList"
              :raw-content-list="rawContentList"
            />
          </div>
        </div>

        <!-- Draggable resizer bar -->
        <div 
          class="resizer" 
          :class="{ 'resizing': isResizing }"
          @mousedown="startResizing"
        ></div>

        <!-- Right: Markdown Content Panel -->
        <div class="side-panel md-panel" :style="{ width: (100 - leftWidth) + '%' }">
          <div class="panel-header tabs-header">
            <a-tabs v-model:activeKey="activeTab" centered class="header-tabs">
              <a-tab-pane key="full" :tab="mdContent ? `${t('tabs.full_conversion')} (${mdLengthK}k)` : t('tabs.full_conversion')" />
              <a-tab-pane key="main" :tab="t('tabs.main_content')" />
              <a-tab-pane key="ai" :tab="t('tabs.ai_extraction')" />
            </a-tabs>
          </div>
          
          <div class="panel-body">
            <MarkdownViewer 
              v-if="activeTab === 'full'"
              :task-id="taskId"
              :pending-file="pendingFile"
              :loading="isProcessing"
              :loading-text="uploadStatusText"
              :is-uploading="isUploading"
              v-model:md-content="mdContent"
              :content-list="contentList"
              :content-tables="contentTables"
              :is-highlight-all="isHighlightAll"
              :is-raw-visible="isRawVisible"
              v-model:provider="selectedProvider"
              @convert="startConversion"
              @element-click="handleElementClick"
              @toggle-highlight-all="isHighlightAll = !isHighlightAll"
              @toggle-raw-visible="isRawVisible = !isRawVisible"
            />
            <div v-else-if="activeTab === 'main'" class="main-extract-wrapper">
              <div v-if="!mdContent" class="empty-state">
                <a-empty :description="t('viewer.upload_hint')" />
              </div>
              <div v-else class="main-extract-scroll">
                <div class="main-extract-config" v-if="!mainExtractCollapsed">
                  <a-form layout="vertical">
                    <a-form-item :label="t('extract.prompt')">
                      <a-textarea
                        v-model:value="mainExtractPrompt"
                        :auto-size="{ minRows: 3, maxRows: 8 }"
                      />
                    </a-form-item>
                    <a-form-item :label="t('extract.regex')">
                      <a-input v-model:value="mainExtractRegex" />
                    </a-form-item>
                    <a-form-item :label="t('extract.flags')">
                      <a-input v-model:value="mainExtractFlags" />
                    </a-form-item>
                  </a-form>
                  <a-space>
                    <a-button type="primary" :loading="isMainExtracting" @click="runMainExtraction">
                      {{ t('extract.run') }}
                    </a-button>
                    <a-button @click="resetMainExtraction">
                      {{ t('extract.reset') }}
                    </a-button>
                  </a-space>
                </div>

                <div class="main-extract-collapsed" v-else>
                  <a-space>
                    <a-button type="link" @click="mainExtractCollapsed = false">
                      {{ t('extract.edit_prompt') }}
                    </a-button>
                    <span class="main-extract-summary">
                      {{ t('extract.found', { count: mainExtractResults.length }) }}
                    </span>
                  </a-space>
                </div>

                <div class="main-extract-results">
                  <a-list
                    :data-source="mainExtractResults"
                    :locale="{ emptyText: t('extract.empty') }"
                    size="small"
                    bordered
                  >
                    <template #renderItem="{ item }">
                      <a-list-item class="extract-item" @click="handleExtractItemClick(item)">
                        <a-space style="width: 100%" align="center" :wrap="false">
                          <span class="extract-item-text">{{ item.text }}</span>
                          <span class="extract-item-meta">
                            <template v-if="typeof item.page_idx === 'number' && item.bbox">
                              p{{ item.page_idx + 1 }}
                            </template>
                            <template v-else>
                              {{ t('extract.unmapped') }}
                            </template>
                          </span>
                        </a-space>
                      </a-list-item>
                    </template>
                  </a-list>
                </div>
              </div>
            </div>
            <div v-else class="empty-state">
              <a-empty :description="t('messages.ai_feature_dev')" />
            </div>
          </div>
        </div>
        
        <!-- Global overlay to capture mouse events during resizing -->
        <div v-if="isResizing" class="resizing-overlay"></div>
      </div>
    </a-layout-content>

    <!-- Settings Modal: API Configurations -->
    <a-modal
      v-model:open="showSettings"
      :title="t('settings.title')"
      @ok="saveSettings"
      :ok-text="t('settings.save')"
      :cancel-text="t('settings.reset')"
      @cancel="resetSettings"
    >
      <a-form layout="vertical">
        <a-form-item :label="t('settings.mineru_api_url')">
          <a-input 
            v-model:value="mineruApiUrl" 
            :placeholder="t('settings.mineru_api_url_placeholder')" 
          />
        </a-form-item>
        <a-form-item :label="t('settings.mineru_api_key')">
          <a-input 
            v-model:value="mineruApiKey" 
            type="password"
            :placeholder="serverConfig?.has_mineru_api_key ? t('settings.using_server_key') : t('settings.mineru_api_key_placeholder')" 
          />
          <div v-if="!mineruApiKey && serverConfig?.has_mineru_api_key" style="margin-top: 4px; font-size: 12px; color: #52c41a;">
            <span role="img" aria-label="check-circle" class="anticon anticon-check-circle">
              <svg focusable="false" data-icon="check-circle" width="1em" height="1em" fill="currentColor" aria-hidden="true" viewBox="64 64 896 896"><path d="M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm193.5 301.7l-210.6 292a31.8 31.8 0 01-51.7 0L318.5 484.9c-3.8-5.3 0-12.7 6.5-12.7h46.9c10.2 0 19.9 4.9 25.9 13.3l71.2 98.8 157.2-218c6-8.3 15.6-13.3 25.9-13.3H699c6.5 0 10.3 7.4 6.5 12.7z"></path></svg>
            </span>
            {{ t('settings.server_key_active') }}
          </div>
        </a-form-item>
        <p style="color: #666; font-size: 12px;">{{ t('settings.save_hint') }}</p>
      </a-form>
    </a-modal>
  </a-layout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import axios from 'axios';
import { useI18n } from 'vue-i18n';
import { message } from 'ant-design-vue';
import { 
  InboxOutlined, 
  FilePdfOutlined,
  LeftOutlined,
  RightOutlined,
  PlusOutlined,
  MinusOutlined,
  GithubOutlined,
  GlobalOutlined,
  SettingOutlined,
  BuildOutlined,
  EyeOutlined,
  EyeInvisibleOutlined
} from '@ant-design/icons-vue';
import PdfViewer from './components/PdfViewer.vue';
import MarkdownViewer from './components/MarkdownViewer.vue';
import { useResizer } from './composables/useResizer';
import { useConversion } from './composables/useConversion';

// Internationalization setup
const { t, locale } = useI18n();
const logoReady = ref(true);

const handleLocaleChange = ({ key }: { key: string }) => {
  locale.value = key;
};

// Panel resizing logic
const { leftWidth, isResizing, startResizing } = useResizer(50);

// API Configuration logic (LocalStorage persistence)
const showSettings = ref(false);
const mineruApiUrl = ref('');
const mineruApiKey = ref('');
const serverConfig = ref<{
  mineru_api_url: string;
  has_mineru_api_key: boolean;
  mineru_api_key_masked: string;
} | null>(null);

onMounted(async () => {
  // 1. Load from local storage first
  mineruApiUrl.value = localStorage.getItem('mineru_api_url') || '';
  mineruApiKey.value = localStorage.getItem('mineru_api_key') || '';
  
  // 2. Fetch server defaults
  try {
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '';
    const res = await axios.get(`${apiBaseUrl}/api/config`);
    serverConfig.value = res.data;
    
    // 3. If local storage is empty, pre-fill with server defaults (logic as requested)
    if (!mineruApiUrl.value && serverConfig.value?.mineru_api_url) {
      mineruApiUrl.value = serverConfig.value.mineru_api_url;
      localStorage.setItem('mineru_api_url', mineruApiUrl.value);
    }
    
    // Note: We don't fill the MASKED key into the real API key field 
    // to avoid saving asterisks as the actual key.
    // But if local is empty and server has one, we can show a placeholder or "Server Default"
    if (!mineruApiKey.value && serverConfig.value?.has_mineru_api_key) {
      // We don't save the masked key to localStorage, 
      // instead we let the conversion logic know to use the server key if local is empty.
    }
  } catch (err) {
    console.error('Failed to fetch server config:', err);
  }
});

const saveSettings = () => {
  localStorage.setItem('mineru_api_url', mineruApiUrl.value);
  localStorage.setItem('mineru_api_key', mineruApiKey.value);
  message.success(t('settings.save_success'));
  showSettings.value = false;
};

const resetSettings = () => {
  mineruApiUrl.value = serverConfig.value?.mineru_api_url || '';
  mineruApiKey.value = '';
  localStorage.removeItem('mineru_api_url');
  localStorage.removeItem('mineru_api_key');
  message.success(t('settings.reset_success') || 'Settings reset');
};

const {
  taskId,
  pdfUrl,
  mdContent,
  contentList,
  rawContentList,
  contentTables,
  currentHighlights,
  isUploading,
  isProcessing,
  uploadStatusText,
  pendingFile,
  selectedProvider,
  handleUploadChange,
  startConversion,
  apiBaseUrl
} = useConversion();

const isHighlightAll = ref(true); // Default to highlight all enabled (Modified - Red)
const isRawVisible = ref(false); // New: highlight all original content_list blocks (Raw - Blue)
const mdLengthK = computed(() => {
  if (!mdContent.value) return 0;
  // Format content length in KB (1024 bytes per unit)
  return Math.round(mdContent.value.length / 1024);
});

// PDF Viewer component state
const currentPage = ref(1);
const totalPages = ref(0);
const pdfScale = ref(1.0);
const preferredY = ref<number | undefined>(undefined);
const activeTab = ref('full');

// Handle Markdown element click to sync PDF view (highlight & scroll)
const handleElementClick = (data: { page_idx: number; bbox: number[]; clickY: number }) => {
  currentPage.value = data.page_idx + 1;
  currentHighlights.value = [{
    bbox: data.bbox,
    page_idx: data.page_idx
  }];
  preferredY.value = data.clickY;
};

type ExtractResultItem = {
  id: string;
  text: string;
  md_index?: number;
  page_idx?: number;
  bbox?: number[];
};

const mainExtractPrompt = ref('提取章节标题（支持自定义正则）');
const mainExtractRegex = ref('^(#{1,6})\\s+(.+)$');
const mainExtractFlags = ref('gm');
const mainExtractCollapsed = ref(false);
const isMainExtracting = ref(false);
const mainExtractResults = ref<ExtractResultItem[]>([]);

const splitMarkdownBlocks = (input: string) => {
  const src = (input || '').replace(/\r\n/g, '\n').trim();
  if (!src) return [];

  const tableRe = /<table[\s\S]*?<\/table>/gi;
  const blocks: string[] = [];

  let lastEnd = 0;
  let match: RegExpExecArray | null;

  while ((match = tableRe.exec(src)) !== null) {
    const index = match.index;
    const before = src.slice(lastEnd, index);

    if (before.trim()) {
      const subBlocks = before
        .split(/\n{2,}/g)
        .map(s => s.trim())
        .filter(Boolean);
      blocks.push(...subBlocks);
    }

    const tableBlock = match[0];
    if (tableBlock && tableBlock.trim()) {
      blocks.push(tableBlock.trim());
    }
    lastEnd = index + tableBlock.length;
  }

  const tail = src.slice(lastEnd);
  if (tail.trim()) {
    const subBlocks = tail
      .split(/\n{2,}/g)
      .map(s => s.trim())
      .filter(Boolean);
    blocks.push(...subBlocks);
  }

  return blocks;
};

const contentByMdIndex = computed(() => {
  const map = new Map<number, any>();
  for (const item of contentList.value || []) {
    if (item && typeof item.md_index === 'number') {
      map.set(item.md_index, item);
    }
  }
  return map;
});

const normalizeFlags = (flags: string) => {
  const raw = (flags || '').trim();
  const set = new Set<string>();
  for (const ch of raw) set.add(ch);
  set.add('g');
  set.add('m');
  return Array.from(set).join('');
};

const runMainExtraction = () => {
  if (!mdContent.value) {
    message.warning(t('viewer.upload_hint'));
    return;
  }

  isMainExtracting.value = true;
  try {
    const flags = normalizeFlags(mainExtractFlags.value);
    const re = new RegExp(mainExtractRegex.value, flags);
    const blocks = splitMarkdownBlocks(mdContent.value);

    const results: ExtractResultItem[] = [];
    const seen = new Set<string>();

    blocks.forEach((block, mdIndex) => {
      for (const m of block.matchAll(re)) {
        const text = (m[2] || m[1] || m[0] || '').toString().trim();
        if (!text) continue;
        const key = `${mdIndex}:${text}`;
        if (seen.has(key)) continue;
        seen.add(key);

        const mapped = contentByMdIndex.value.get(mdIndex);
        results.push({
          id: `${mdIndex}-${results.length}`,
          text,
          md_index: mdIndex,
          page_idx: mapped?.page_idx,
          bbox: mapped?.bbox
        });
      }
    });

    mainExtractResults.value = results;
    mainExtractCollapsed.value = true;
  } catch (e: any) {
    message.error(t('extract.invalid_regex'));
  } finally {
    isMainExtracting.value = false;
  }
};

const resetMainExtraction = () => {
  mainExtractResults.value = [];
  mainExtractCollapsed.value = false;
};

const handleExtractItemClick = (item: ExtractResultItem) => {
  if (typeof item.page_idx !== 'number' || !item.bbox) return;
  handleElementClick({
    page_idx: item.page_idx,
    bbox: item.bbox,
    clickY: 0
  });
};
</script>

<style>
html, body, #app {
  width: 100vw;
  height: 100vh;
  margin: 0;
  padding: 0;
  overflow: hidden;
}

.layout {
  height: 100vh;
  width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.header {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  padding: 0 24px !important;
  background: #001529 !important;
  width: 100% !important;
  height: 64px !important;
  line-height: 64px !important;
}

/* Fix for potential pseudo-elements interfering with flex layout */
.header::before,
.header::after {
  display: none !important;
}

.logo {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  color: white;
  flex-shrink: 0;
  height: 100%;
  margin-right: auto; /* Ensure it stays left */
}

.header-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  margin-left: auto !important; /* Ensure it stays right */
}

.logo-icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
}

.logo-img {
  height: 100%;
  width: auto;
  border-radius: 4px;
}

.fallback-logo {
  font-size: 24px;
  color: #1890ff;
}

.logo-text {
  font-size: 20px;
  font-weight: bold;
  letter-spacing: 0.5px;
}

.content {
  height: calc(100vh - 64px);
  padding: 0;
  overflow: hidden;
  background: #f0f2f5;
}

.viewer-container {
  display: flex;
  height: 100%;
  width: 100%;
  padding: 16px;
  position: relative;
}

.resizer {
  width: 8px;
  cursor: col-resize;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  z-index: 10;
  position: relative;
  margin: 0 -4px;
}

.resizer::after {
  content: "";
  width: 2px;
  height: 40px;
  background: #d9d9d9;
  border-radius: 2px;
  transition: all 0.2s;
}

.resizer:hover::after,
.resizing::after {
  background: #1890ff;
  width: 4px;
  height: 100%;
}

.resizing-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  cursor: col-resize;
}

.panel-header {
  height: 48px;
  padding: 0 16px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
  flex: 0 0 auto;
  background: #fafafa;
}

.tabs-header {
  padding: 0 !important;
  justify-content: center !important;
}

.header-tabs {
  width: 100%;
}

:deep(.header-tabs .ant-tabs-nav) {
  margin: 0 !important;
}

:deep(.header-tabs .ant-tabs-nav::before) {
  border-bottom: none !important;
}

:deep(.header-tabs .ant-tabs-tab) {
  padding: 12px 16px !important;
}

.panel-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.main-extract-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.main-extract-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.main-extract-config {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 16px;
}

.main-extract-collapsed {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.main-extract-summary {
  color: #666;
  font-size: 13px;
}

.main-extract-results {
  margin-top: 12px;
}

.extract-item {
  cursor: pointer;
}

.extract-item-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.extract-item-meta {
  color: #999;
  font-size: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-toolbar {
  display: flex;
  align-items: center;
  background: #f0f0f0;
  padding: 2px 8px;
  border-radius: 4px;
}

.page-info {
  font-size: 13px;
  min-width: 45px;
  text-align: center;
}

.btn-active-blue {
  color: #1890ff !important;
  background-color: rgba(24, 144, 255, 0.1) !important;
}

.btn-active-red {
  color: #ff4d4f !important;
  background-color: rgba(255, 77, 79, 0.1) !important;
}

.upload-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: center;
  padding: 16px;
}

.upload-area :deep(.ant-upload) {
  width: 100% !important;
}

.upload-area :deep(.ant-upload-drag) {
  width: 100% !important;
  height: 500px !important;
  display: flex;
  align-items: center;
  justify-content: center;
}

.upload-area :deep(.ant-upload-btn) {
  display: flex !important;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100% !important;
  height: 100% !important;
}

:deep(.ant-upload-drag-icon .anticon) {
  font-size: 64px !important;
}

:deep(.ant-upload-text) {
  font-size: 24px !important;
  margin-top: 16px !important;
  color: #1890ff !important;
  font-weight: 500;
}

:deep(.ant-upload-hint) {
  font-size: 16px !important;
  margin-top: 8px !important;
}

.side-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  overflow: hidden;
  transition: width 0.05s linear;
}

.pdf-viewer-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* Global scrollbar styling */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>
