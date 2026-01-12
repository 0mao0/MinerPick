<template>
  <div class="pdf-viewer">
    <!-- Loading overlay -->
    <div v-if="loading" class="loading-overlay">
      <a-spin :tip="t('viewer.loading_pdf')" />
    </div>
    
    <div class="pdf-content-area" ref="scrollContainerRef" @scroll="handleScroll">
      <div v-if="url && totalPages > 0" class="pdf-pages-list">
        <div 
          v-for="pageNo in totalPages" 
          :key="pageNo"
          :ref="el => pageRefs[pageNo] = el"
          class="pdf-page-container"
          :data-page-number="pageNo"
          :style="getPageContainerStyle(pageNo)"
        >
          <canvas :ref="el => canvasRefs[pageNo] = el"></canvas>
          
          <!-- Annotation/Highlight layer -->
          <div class="annotation-layer">
            <div 
              v-for="(hl, index) in getPageHighlights(pageNo)" 
              :key="index"
              class="highlight-rect highlight-animate"
              :style="hl.style"
            ></div>
          </div>

          <!-- Page loading placeholder -->
          <div v-if="!renderedPages.has(pageNo)" class="page-placeholder">
            {{ t('viewer.page', { page: pageNo }) }}
          </div>
        </div>
      </div>
      
      <!-- Empty state placeholder -->
      <div v-else-if="!loading" class="empty-placeholder">
        <a-empty :description="t('viewer.no_pdf')" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, shallowRef, nextTick, onBeforeUnmount, reactive } from 'vue';
import { useI18n } from 'vue-i18n';
import * as pdfjsLib from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.mjs?url';

const { t } = useI18n();

// Set PDF.js worker path
pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorker;

interface Highlight {
  page_idx: number;
  bbox: [number, number, number, number];
}

interface Props {
  url: string;
  highlights?: Highlight[];
  preferredY?: number;
  isHighlightAll?: boolean;
  contentList?: any[];
}

const props = withDefaults(defineProps<Props>(), {
  highlights: () => [],
  preferredY: 0,
  isHighlightAll: false,
  contentList: () => []
});

// Use defineModel for two-way binding with parent components
const currentPage = defineModel<number>('currentPage', { default: 1 });
const totalPages = defineModel<number>('totalPages', { default: 0 });
const scale = defineModel<number>('scale', { default: 1.0 });

// DOM Element References
const scrollContainerRef = ref<HTMLElement | null>(null);
const pageRefs = reactive<Record<number, any>>({});
const canvasRefs = reactive<Record<number, any>>({});

// Component State
const loading = ref(false);
const pdfDoc = shallowRef<any>(null);
const pageViewports = reactive<Record<number, any>>({});
const renderedPages = ref(new Set<number>());
const renderTasks: Record<number, any> = {};
const isScrollingManually = ref(false);
const isUpdatingFromScroll = ref(false);

/**
 * Get style for each page container based on viewport
 */
const getPageContainerStyle = (pageNo: number) => {
  const vp = pageViewports[pageNo];
  if (!vp) return { minHeight: '800px', width: '600px' };
  return {
    width: `${vp.width}px`,
    height: `${vp.height}px`
  };
};

/**
 * Calculate highlight positions for a specific page
 */
const getPageHighlights = (pageNo: number) => {
  const vp = pageViewports[pageNo];
  if (!vp) return [];

  const pageIdx = pageNo - 1;
  // Only show the currently selected highlights (triggered by clicking Markdown blocks)
  // Removed isHighlightAll impact on the left PDF preview
  const pageHighlights = props.highlights ? props.highlights.filter(h => h.page_idx === pageIdx) : [];

  return pageHighlights.map(hl => {
    const [x1, y1, x2, y2] = hl.bbox;
    const left = (x1 * vp.width) / 1000;
    const top = (y1 * vp.height) / 1000;
    const right = (x2 * vp.width) / 1000;
    const bottom = (y2 * vp.height) / 1000;

    return {
      style: {
        left: `${left}px`,
        top: `${top}px`,
        width: `${right - left}px`,
        height: `${bottom - top}px`
      }
    };
  });
};

/**
 * Load and initialize the PDF document
 */
const loadPdf = async () => {
  if (!props.url) {
    pdfDoc.value = null;
    totalPages.value = 0;
    renderedPages.value.clear();
    return;
  }

  // Cancel existing rendering tasks before loading new document
  Object.values(renderTasks).forEach((task: any) => task.cancel());
  renderedPages.value = new Set();

  loading.value = true;
  try {
    let source: any = props.url;
    if (props.url.startsWith('blob:')) {
      const response = await fetch(props.url);
      const arrayBuffer = await response.arrayBuffer();
      source = { data: new Uint8Array(arrayBuffer) };
    }
    
    const loadingTask = pdfjsLib.getDocument(source);
    pdfDoc.value = await loadingTask.promise;
    totalPages.value = pdfDoc.value.numPages;
    
    // Pre-calculate viewports for all pages to handle placeholder sizing
    for (let i = 1; i <= totalPages.value; i++) {
      const page = await pdfDoc.value.getPage(i);
      pageViewports[i] = page.getViewport({ scale: scale.value });
    }

    await nextTick();
    // Initial render of visible pages
    updateVisiblePages();
    
    // Scroll to initial page if specified
    if (currentPage.value > 1) {
      scrollToPage(currentPage.value);
    }
  } catch (error) {
    console.error('PdfViewer: Error loading PDF:', error);
  } finally {
    loading.value = false;
  }
};

/**
 * Render a single page onto its canvas
 */
const renderPage = async (pageNo: number) => {
  if (!pdfDoc.value || renderedPages.value.has(pageNo)) return;
  
  const canvas = canvasRefs[pageNo];
  if (!canvas) return;

  try {
    const page = await pdfDoc.value.getPage(pageNo);
    const vp = page.getViewport({ scale: scale.value });
    pageViewports[pageNo] = vp;

    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) return;

    if (renderTasks[pageNo]) {
      renderTasks[pageNo].cancel();
    }

    canvas.height = vp.height;
    canvas.width = vp.width;
    context.setTransform(1, 0, 0, 1, 0, 0);

    const renderTask = page.render({
      canvasContext: context,
      viewport: vp
    });
    
    renderTasks[pageNo] = renderTask;
    await renderTask.promise;
    delete renderTasks[pageNo];
    renderedPages.value.add(pageNo);
    // Force reactive update of rendered pages set
    renderedPages.value = new Set(renderedPages.value);
  } catch (error: any) {
    if (error.name !== 'RenderingCancelledException') {
      console.error(`PdfViewer: Error rendering page ${pageNo}:`, error);
    }
  }
};

/**
 * Smoothly scroll the container to a specific page
 */
const scrollToPage = async (pageNo: number) => {
  isScrollingManually.value = true;
  await nextTick();
  const el = pageRefs[pageNo];
  if (el && scrollContainerRef.value) {
    el.scrollIntoView({ behavior: 'smooth' });
    // Render target page and its immediate neighbors for better UX
    renderPage(pageNo);
    if (pageNo > 1) renderPage(pageNo - 1);
    if (pageNo < totalPages.value) renderPage(pageNo + 1);
  }
  setTimeout(() => {
    isScrollingManually.value = false;
  }, 1000);
};

/**
 * Sync current page number based on scroll position
 */
const handleScroll = () => {
  if (isScrollingManually.value) return;
  updateVisiblePages();
};

/**
 * Detect which pages are visible and update the active page
 */
const updateVisiblePages = () => {
  const container = scrollContainerRef.value;
  if (!container) return;

  const containerRect = container.getBoundingClientRect();
  let maxVisibleHeight = 0;
  let currentActivePage = currentPage.value;

  for (let i = 1; i <= totalPages.value; i++) {
    const el = pageRefs[i];
    if (!el) continue;

    const rect = el.getBoundingClientRect();
    const visibleTop = Math.max(rect.top, containerRect.top);
    const visibleBottom = Math.min(rect.bottom, containerRect.bottom);
    const visibleHeight = Math.max(0, visibleBottom - visibleTop);

    if (visibleHeight > 0) {
      // Trigger lazy loading for visible pages
      renderPage(i);
      
      // Track page with maximum visible area as the active one
      if (visibleHeight > maxVisibleHeight) {
        maxVisibleHeight = visibleHeight;
        currentActivePage = i;
      }
    }
  }

  if (currentActivePage !== currentPage.value) {
    isUpdatingFromScroll.value = true;
    currentPage.value = currentActivePage;
    nextTick(() => {
      isUpdatingFromScroll.value = false;
    });
  }
};

/**
 * Scroll the view to focus on the first highlight
 */
const scrollToHighlight = async () => {
  if (!props.highlights || props.highlights.length === 0) return;
  
  const hl = props.highlights[0];
  if (!hl) return;
  const pageNo = hl.page_idx + 1;
  
  isScrollingManually.value = true;
  await renderPage(pageNo);
  await nextTick();
  
  const el = pageRefs[pageNo];
  const container = scrollContainerRef.value;
  if (!el || !container) {
    isScrollingManually.value = false;
    return;
  }

  const vp = pageViewports[pageNo];
  const [, y1, , y2] = hl.bbox;
  const highlightTop = (y1 * vp.height) / 1000;
  const highlightHeight = ((y2 - y1) * vp.height) / 1000;

  const offsetTop = el.offsetTop;
  const viewHeight = container.clientHeight;
  
  let targetScrollTop;
  if (props.preferredY && props.preferredY > 0) {
    targetScrollTop = offsetTop + highlightTop - props.preferredY;
  } else {
    targetScrollTop = offsetTop + highlightTop - (viewHeight / 2) + (highlightHeight / 2);
  }

  container.scrollTo({
    top: Math.max(0, targetScrollTop),
    behavior: 'smooth'
  });

  setTimeout(() => {
    isScrollingManually.value = false;
  }, 1000);
};

// Watch for PDF URL changes
watch(() => props.url, loadPdf);

// Watch for external page changes (e.g., from toolbar)
watch(currentPage, (newVal) => {
  if (!isScrollingManually.value && !isUpdatingFromScroll.value) {
    scrollToPage(newVal);
  }
});

// Watch for zoom level changes and re-calculate viewports
watch(scale, async () => {
  renderedPages.value = new Set();
  loading.value = true;
  for (let i = 1; i <= totalPages.value; i++) {
    const page = await pdfDoc.value.getPage(i);
    pageViewports[i] = page.getViewport({ scale: scale.value });
  }
  loading.value = false;
  await nextTick();
  updateVisiblePages();
});

// Watch for new highlights and scroll to them
watch(() => props.highlights, (newHls) => {
  if (newHls && newHls.length > 0) {
    scrollToHighlight();
  }
}, { deep: true });

onMounted(loadPdf);

onBeforeUnmount(() => {
  Object.values(renderTasks).forEach((task: any) => task.cancel());
});

// Expose methods for parent component access
defineExpose({
  scrollToPage,
  loadPdf
});
</script>

<style scoped>
.pdf-viewer {
  position: relative;
  width: 100%;
  height: 100%;
  background: #525659;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(82, 86, 89, 0.7);
  z-index: 100;
}

.pdf-content-area {
  flex: 1;
  overflow: auto;
  padding: 20px;
  scroll-behavior: smooth;
}

.pdf-pages-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  position: relative;
}

.pdf-page-container {
  position: relative;
  box-shadow: 0 0 10px rgba(0,0,0,0.5);
  background: white;
  flex-shrink: 0;
}

.annotation-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.highlight-rect {
  position: absolute;
  background-color: rgba(255, 255, 0, 0.35);
  border: 2px solid #ff6b35;
  z-index: 10;
  border-radius: 2px;
  box-shadow: 0 0 8px rgba(255, 107, 53, 0.4);
}

.highlight-animate {
  animation: highlight-fade-in 0.3s ease-out forwards;
}

@keyframes highlight-fade-in {
  from { opacity: 0; transform: scale(0.98); }
  to { opacity: 1; transform: scale(1); }
}

.page-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #ccc;
  background: #f9f9f9;
}

.empty-placeholder {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}

/* Custom scrollbar styling */
.pdf-content-area::-webkit-scrollbar {
  width: 12px;
}
.pdf-content-area::-webkit-scrollbar-track {
  background: #525659;
}
.pdf-content-area::-webkit-scrollbar-thumb {
  background: #888;
  border: 3px solid #525659;
  border-radius: 6px;
}
.pdf-content-area::-webkit-scrollbar-thumb:hover {
  background: #aaa;
}
</style>
