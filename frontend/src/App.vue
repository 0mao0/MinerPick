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
              :content-list="contentList"
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
              v-model:provider="selectedProvider"
              @convert="startConversion"
              @element-click="handleElementClick"
              @toggle-highlight-all="isHighlightAll = !isHighlightAll"
            />
            <div v-else class="empty-state">
              <a-empty :description="activeTab === 'main' ? t('messages.main_content_dev') : t('messages.ai_feature_dev')" />
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
          <a-input-password 
            v-model:value="mineruApiKey" 
            :placeholder="t('settings.mineru_api_key_placeholder')" 
          />
        </a-form-item>
        <p style="color: #666; font-size: 12px;">{{ t('settings.save_hint') }}</p>
      </a-form>
    </a-modal>
  </a-layout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
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
  BuildOutlined
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

onMounted(() => {
  mineruApiUrl.value = localStorage.getItem('mineru_api_url') || '';
  mineruApiKey.value = localStorage.getItem('mineru_api_key') || '';
});

const saveSettings = () => {
  localStorage.setItem('mineru_api_url', mineruApiUrl.value);
  localStorage.setItem('mineru_api_key', mineruApiKey.value);
  message.success(t('settings.save_success'));
  showSettings.value = false;
};

const resetSettings = () => {
  mineruApiUrl.value = '';
  mineruApiKey.value = '';
  localStorage.removeItem('mineru_api_url');
  localStorage.removeItem('mineru_api_key');
};

const {
  taskId,
  pdfUrl,
  mdContent,
  contentList,
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

const isHighlightAll = ref(true); // Default to highlight all enabled
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
