<template>
  <div class="viewer-wrapper">
    <div class="md-scroll-area">
      <!-- State 1: Initial upload or waiting for conversion -->
      <div v-if="!taskId" class="empty-state">
        <div v-if="pendingFile" class="convert-prompt">
          <a-button type="primary" size="large" @click="$emit('convert')" :loading="loading">
            <template #icon><FileSyncOutlined /></template>
            {{ t('viewer.start_convert') }}
          </a-button>

          <div class="parser-selector">
            <div class="selector-label">{{ t('viewer.select_engine') }}</div>
            <a-radio-group v-model:value="provider" class="parser-radio-group">
              <a-radio value="mineru">{{ t('viewer.engine_mineru') }}</a-radio>
              <a-radio value="pymupdf" disabled>{{ t('viewer.engine_pymupdf') }}</a-radio>
            </a-radio-group>
          </div>
        </div>
        <a-spin v-else :spinning="isUploading" :tip="loadingText">
          <a-empty :description="emptyDescription || t('viewer.upload_hint')" />
        </a-spin>
      </div>

      <!-- State 2: Processing or displaying Markdown content -->
    <a-spin v-else :spinning="loading" :tip="loadingText" class="md-loading-wrapper">
      <!-- View Mode: Rendered Markdown -->
      <div v-if="mdContent" class="info-panel" ref="containerRef">
        <div
          v-for="(block, index) in mdBlocks"
          :key="index"
          class="md-block md-md"
          :class="{
            'highlight-mapped': isHighlightAll && getBlockStatus(index) === 'mapped' && !isTableBlock(index),
            'md-table-block': isTableBlock(index)
          }"
          :title="t('viewer.dblclick_edit')"
          :style="{ '--edit-hint': `'${t('viewer.dblclick_edit')}'` }"
          @click="handleMdBlockClick(index, $event)"
          @dblclick="handleMdBlockDblClick(index, $event)"
          @mouseenter="handleMouseEnter(index, $event)"
          @mousemove="handleMouseMove"
          @mouseleave="handleMouseLeave"
        >
          <div v-html="renderMarkdown(block)"></div>
        </div>

        <!-- BBox coordinates tooltip on hover -->
        <div v-if="tooltipVisible" class="bbox-tooltip" :style="tooltipStyle">
          {{ tooltipContent }}
        </div>
      </div>
    </a-spin>
  </div>

  <!-- Floating action buttons (Bottom Right: Download, Toggle highlights) -->
    <div v-if="mdContent" class="download-action">
      <a-space direction="vertical">
        <a-tooltip :title="isHighlightAll ? t('viewer.highlight_off') : t('viewer.highlight_all')" placement="left">
          <a-button 
            :type="isHighlightAll ? 'primary' : 'default'" 
            shape="circle" 
            size="large" 
            @click="$emit('toggle-highlight-all')" 
            class="action-btn"
          >
            <template #icon>
              <EyeOutlined v-if="!isHighlightAll" />
              <EyeInvisibleOutlined v-else />
            </template>
          </a-button>
        </a-tooltip>
        
        <a-tooltip :title="t('viewer.download')" placement="left">
          <a-button type="primary" shape="circle" size="large" @click="downloadMd" class="action-btn download-btn">
            <template #icon><DownloadOutlined /></template>
          </a-button>
        </a-tooltip>
      </a-space>
    </div>

    <!-- Quick Block Editor Modal -->
    <a-modal
      v-model:open="isBlockModalVisible"
      :title="editingCellInfo ? t('viewer.edit_cell') : t('viewer.edit_block')"
      @ok="saveBlockEdit"
      :ok-text="t('viewer.save')"
      :cancel-text="t('viewer.cancel')"
      width="600px"
      centered
    >
      <a-textarea
        v-model:value="editingBlockContent"
        :auto-size="{ minRows: 4, maxRows: 12 }"
        class="block-editor-textarea"
      />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive, watch, nextTick, onMounted, onUpdated } from 'vue';
import { useI18n } from 'vue-i18n';
import { FileSyncOutlined, DownloadOutlined, EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons-vue';
import MarkdownIt from 'markdown-it';

interface Props {
  taskId: string;
  pendingFile: any;
  loading: boolean;
  loadingText: string;
  isUploading: boolean;
  contentList: any[];
  contentTables?: Record<string, any>;
  emptyDescription?: string;
  isHighlightAll?: boolean;
}

const props = defineProps<Props>();
const mdContent = defineModel<string>('mdContent', { default: '' });
const provider = defineModel<string>('provider', { default: 'mineru' });
const containerRef = ref<HTMLElement | null>(null);
const { t } = useI18n();

const emit = defineEmits<{
  (e: 'convert'): void;
  (e: 'element-click', data: any): void;
  (e: 'toggle-highlight-all'): void;
}>();

// Block editing state
const isBlockModalVisible = ref(false);
const editingBlockIndex = ref(-1);
const editingBlockContent = ref('');
const editingCellInfo = ref<{ r: number, c: number, originalText: string } | null>(null);

// Reset state when modal closes
watch(isBlockModalVisible, (val) => {
  if (!val) {
    editingBlockIndex.value = -1;
    editingCellInfo.value = null;
  }
});

// Tooltip state for bounding box information
const tooltipVisible = ref(false);
const tooltipContent = ref('');
const tooltipStyle = reactive({
  top: '0px',
  left: '0px'
});
let hoverTimer: any = null;

// Markdown-it configuration
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
});

const handleMouseEnter = (index: number, event: MouseEvent) => {
  if (hoverTimer) clearTimeout(hoverTimer);
  
  // Start timer for 500ms delay (reduced from 1000ms)
  hoverTimer = setTimeout(() => {
    updateTooltip(index, event);
  }, 500);
};

const handleMouseMove = (event: MouseEvent) => {
  // If we're moving, we need to reset the timer to ensure it only shows after 500ms of being STILL
  if (hoverTimer) clearTimeout(hoverTimer);
  
  // Hide tooltip while moving to ensure it only appears when still
  tooltipVisible.value = false;

  const target = event.currentTarget as HTMLElement;
  const blocks = Array.from(containerRef.value?.querySelectorAll('.md-block') || []);
  const index = blocks.indexOf(target);
  
  if (index !== -1) {
    hoverTimer = setTimeout(() => {
      updateTooltip(index, event);
    }, 500);
  }
};

const updateTooltip = (index: number, event: MouseEvent) => {
  const target = event.target as HTMLElement;
  const cell = target.closest('td, th') as HTMLTableCellElement;
  
  // Prioritize displaying table cell bbox if available
  if (cell && cell.dataset.bbox) {
    try {
      const bbox = JSON.parse(cell.dataset.bbox || '[]');
      if (bbox && bbox.length === 4) {
        tooltipContent.value = `cell bbox: [${bbox.map((n: number) => Math.round(n)).join(', ')}]`;
        tooltipStyle.left = `${event.clientX + 15}px`;
        tooltipStyle.top = `${event.clientY + 15}px`;
        tooltipVisible.value = true;
        return;
      }
    } catch (e) {
      // ignore
    }
  }

  const item = contentByMdIndex.value.get(index);
  if (!item || !item.bbox) {
    tooltipVisible.value = false;
    return;
  }

  const bbox = item.bbox;
  tooltipContent.value = `bbox: [${bbox.map((n: number) => Math.round(n)).join(', ')}]`;
  tooltipStyle.left = `${event.clientX + 15}px`;
  tooltipStyle.top = `${event.clientY + 15}px`;
  tooltipVisible.value = true;
};

const handleMouseLeave = () => {
  if (hoverTimer) clearTimeout(hoverTimer);
  tooltipVisible.value = false;
};

const mdBlocks = computed(() => {
  const src = (mdContent.value || '').replace(/\r\n/g, '\n').trim();
  if (!src) return [];
  
  // Regex to find HTML tables
  const tableRe = /<table[\s\S]*?<\/table>/gi;
  const blocks: string[] = [];

  let lastEnd = 0;
  let match;
  
  // Reset regex lastIndex just in case, though matchAll handles it
  while ((match = tableRe.exec(src)) !== null) {
    const index = match.index;
    const before = src.slice(lastEnd, index);
    
    if (before.trim()) {
      // Split non-table content by double newlines, but be careful not to split other potential blocks
      const subBlocks = before.split(/\n{2,}/g)
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
    const subBlocks = tail.split(/\n{2,}/g)
      .map(s => s.trim())
      .filter(Boolean);
    blocks.push(...subBlocks);
  }

  return blocks;
});

const contentByMdIndex = computed(() => {
  const map = new Map<number, any>();
  for (const item of props.contentList || []) {
    if (item && typeof item.md_index === 'number') {
      map.set(item.md_index, item);
    }
  }
  return map;
});

const renderMarkdown = (text: string) => {
  return md.render(text || '');
};

const getBlockStatus = (index: number) => {
  const item = contentByMdIndex.value.get(index);
  if (item && item.bbox && item.page_idx !== undefined) {
    return 'mapped';
  }
  return 'unmapped';
};

const isTableBlock = (index: number) => {
  const block = mdBlocks.value[index];
  return block && block.trim().toLowerCase().startsWith('<table');
};

/**
 * Handle block clicks to sync the PDF viewer position and highlights
 */
const handleMdBlockClick = (mdIndex: number, event: MouseEvent) => {
  const item = contentByMdIndex.value.get(mdIndex);
  if (!item) return;

  let targetBbox = item.bbox;

  if (item.type === 'table' && props.contentTables && props.contentTables[item.id]) {
    const target = event.target as HTMLElement;
    const cell = target.closest('td, th') as HTMLTableCellElement;
    const table = target.closest('table') as HTMLTableElement;

    if (cell && table) {
      // Calculate logical row/column indices, accounting for merged cells (rowspan/colspan)
      let logicalRow = -1;
      let logicalCol = -1;
      
      const matrix: number[][] = [];
      const rows = table.rows;
      
      for (let r = 0; r < rows.length; r++) {
        if (!matrix[r]) matrix[r] = [];
        const currentRow = rows[r];
        if (!currentRow) continue;
        
        const rowCells = currentRow.cells;
        let cIndex = 0; // Track actual cell index within the current row
        
        for (let c = 0; ; c++) {
          // Skip cells already occupied by a rowspan from above
          const currentRowMatrix = matrix[r];
          while (currentRowMatrix && currentRowMatrix[c] === 1) c++;
          
          if (cIndex >= rowCells.length) break;
          
          const currentCell = rowCells[cIndex];
          if (!currentCell) break;
          
          // Identify the clicked cell in our logical matrix
          if (currentCell === cell) {
            logicalRow = r;
            logicalCol = c;
            break;
          }
          
          // Mark the space occupied by the current cell in the matrix
          const rowSpan = currentCell.rowSpan || 1;
          const colSpan = currentCell.colSpan || 1;
          
          for (let rs = 0; rs < rowSpan; rs++) {
            for (let cs = 0; cs < colSpan; cs++) {
              if (!matrix[r + rs]) matrix[r + rs] = [];
              const targetRow = matrix[r + rs];
              if (targetRow) {
                targetRow[c + cs] = 1;
              }
            }
          }
          
          cIndex++;
        }
        if (logicalRow !== -1) break;
      }

      if (logicalRow !== -1 && logicalCol !== -1) {
        const tableData = props.contentTables[item.id];
        const cellData = tableData.cells.find((c: any) =>
          (c.r === logicalRow && c.c === logicalCol) || (c.row === logicalRow && c.col === logicalCol)
        );

        if (cellData) {
          if (cellData.bbox) targetBbox = cellData.bbox;
          // Use cell-specific page_idx for multi-page tables
          if (typeof cellData.page_idx === 'number') {
            item.page_idx = cellData.page_idx;
          }
        }
      }
    }
  }

  if (!targetBbox || typeof item.page_idx !== 'number') return;

  const scrollArea = (event.currentTarget as HTMLElement).closest('.md-scroll-area');
  const visualY = event.clientY - (scrollArea?.getBoundingClientRect().top || 0);

  emit('element-click', {
    page_idx: item.page_idx,
    bbox: targetBbox,
    clickY: visualY
  });
};

/**
 * Handle double click to open the block editor
 */
const handleMdBlockDblClick = (mdIndex: number, event: MouseEvent) => {
  const block = mdBlocks.value[mdIndex];
  if (block === undefined) return;

  editingBlockIndex.value = mdIndex;
  editingCellInfo.value = null; // Reset cell info

  const target = event.target as HTMLElement;
  const cell = target.closest('td, th') as HTMLTableCellElement;
  const table = target.closest('table') as HTMLTableElement;

  if (cell && table) {
    // If double-clicking a cell, let's try to edit just the cell content for simplicity
    // Calculate logical row/col to identify the cell later during save
    let logicalRow = -1;
    let logicalCol = -1;
    const matrix: number[][] = [];
    const rows = table.rows;
    
    for (let r = 0; r < rows.length; r++) {
      if (!matrix[r]) matrix[r] = [];
      const currentRow = rows[r];
      if (!currentRow) continue;
      
      const rowCells = currentRow.cells;
      let cIndex = 0;
      for (let c = 0; ; c++) {
        const rowMatrix = matrix[r];
        if (rowMatrix) {
          while (rowMatrix[c] === 1) c++;
        }
        
        if (cIndex >= rowCells.length) break;
        const currentCell = rowCells[cIndex];
        if (!currentCell) {
          cIndex++;
          continue;
        }
        
        if (currentCell === cell) {
          logicalRow = r;
          logicalCol = c;
          break;
        }
        const rowSpan = currentCell.rowSpan || 1;
        const colSpan = currentCell.colSpan || 1;
        for (let rs = 0; rs < rowSpan; rs++) {
          for (let cs = 0; cs < colSpan; cs++) {
            if (!matrix[r + rs]) matrix[r + rs] = [];
            const targetRow = matrix[r + rs];
            if (targetRow) {
              targetRow[c + cs] = 1;
            }
          }
        }
        cIndex++;
      }
      if (logicalRow !== -1) break;
    }

    if (logicalRow !== -1 && logicalCol !== -1) {
      editingCellInfo.value = { 
        r: logicalRow, 
        c: logicalCol, 
        originalText: cell.innerHTML.trim() 
      };
      editingBlockContent.value = cell.innerHTML.trim();
    } else {
      editingBlockContent.value = block;
    }
  } else {
    editingBlockContent.value = block;
  }
  
  isBlockModalVisible.value = true;
};

/**
 * Save the edited content of a single block back to the main content
 */
const saveBlockEdit = () => {
  if (editingBlockIndex.value === -1) return;

  const newBlocks = [...mdBlocks.value];
  const originalBlock = newBlocks[editingBlockIndex.value] || '';

  if (editingCellInfo.value) {
    // We are editing a single cell. We need to parse the block as HTML, 
    // find the cell by row/col, update it, and convert back to string.
    const parser = new DOMParser();
    const doc = parser.parseFromString(originalBlock, 'text/html');
    const table = doc.querySelector('table');
    if (table) {
      const matrix: number[][] = [];
      const rows = table.rows;
      let cellFound = false;

      for (let r = 0; r < rows.length; r++) {
        if (!matrix[r]) matrix[r] = [];
        const currentRow = rows[r];
        if (!currentRow) continue;
        
        const rowCells = currentRow.cells;
        let cIndex = 0;
        for (let c = 0; ; c++) {
          const rowMatrix = matrix[r];
          if (rowMatrix) {
            while (rowMatrix[c] === 1) c++;
          }
          
          if (cIndex >= rowCells.length) break;
          const currentCell = rowCells[cIndex];
          if (!currentCell) {
            cIndex++;
            continue;
          }
          
          if (r === editingCellInfo.value.r && c === editingCellInfo.value.c) {
            currentCell.innerHTML = editingBlockContent.value;
            cellFound = true;
            break;
          }

          const rowSpan = currentCell.rowSpan || 1;
          const colSpan = currentCell.colSpan || 1;
          for (let rs = 0; rs < rowSpan; rs++) {
            for (let cs = 0; cs < colSpan; cs++) {
              if (!matrix[r + rs]) matrix[r + rs] = [];
              const targetRow = matrix[r + rs];
              if (targetRow) {
                targetRow[c + cs] = 1;
              }
            }
          }
          cIndex++;
        }
        if (cellFound) break;
      }
      
      if (cellFound) {
        newBlocks[editingBlockIndex.value] = table.outerHTML;
      }
    }
  } else {
    // Normal block edit
    newBlocks[editingBlockIndex.value] = editingBlockContent.value;
  }
  
  // Join blocks back together.
  mdContent.value = newBlocks.join('\n\n');
  isBlockModalVisible.value = false;
  editingBlockIndex.value = -1;
  editingCellInfo.value = null;
};

/**
 * Update highlight status and bbox data for all table cells in DOM
 */
const updateTableHighlights = () => {
  if (!containerRef.value) return;

  const blocks = containerRef.value.querySelectorAll('.md-block');
  blocks.forEach((block, index) => {
    const item = contentByMdIndex.value.get(index);
    if (!item || item.type !== 'table' || !props.contentTables || !props.contentTables[item.id]) return;

    const table = block.querySelector('table') as HTMLTableElement;
    if (!table) return;

    const tableData = props.contentTables[item.id];
    const matrix: HTMLTableCellElement[][] = [];
    const rows = table.rows;

    // Construct a matrix of DOM elements to resolve rowspan/colspan layouts
    for (let r = 0; r < rows.length; r++) {
      if (!matrix[r]) matrix[r] = [];
      const currentRow = rows[r];
      if (!currentRow) continue;
      
      const rowCells = currentRow.cells;
      let cIndex = 0;

      for (let c = 0; ; c++) {
        const currentRowMatrix = matrix[r];
        if (currentRowMatrix && currentRowMatrix[c]) {
          c++;
          continue;
        }

        if (cIndex >= rowCells.length) break;
        
        const cell = rowCells[cIndex];
        if (!cell) break;
        
        const rowSpan = cell.rowSpan || 1;
        const colSpan = cell.colSpan || 1;

        for (let rs = 0; rs < rowSpan; rs++) {
          const matrixRowIdx = r + rs;
          if (!matrix[matrixRowIdx]) matrix[matrixRowIdx] = [];
          const matrixRow = matrix[matrixRowIdx];
          
          for (let cs = 0; cs < colSpan; cs++) {
            if (matrixRow) {
              matrixRow[c + cs] = cell;
            }
          }
        }
        cIndex++;
      }
    }

    // Apply highlights and bind bbox data to dataset attributes
    if (tableData.cells) {
      tableData.cells.forEach((cellData: any) => {
        const r = cellData.r !== undefined ? cellData.r : cellData.row;
        const c = cellData.c !== undefined ? cellData.c : cellData.col;
        
        const rowData = matrix[r];
        if (rowData && rowData[c]) {
          const domCell = rowData[c];
          
          // Store bbox coordinates in data-bbox attribute for tooltip access
          if (cellData.bbox) {
            domCell.dataset.bbox = JSON.stringify(cellData.bbox);
          }

          // Toggle highlight CSS class based on global state
          if (props.isHighlightAll && cellData.bbox) {
            domCell.classList.add('cell-highlight');
          } else {
            domCell.classList.remove('cell-highlight');
          }
        }
      });
    }
  });
};

// Re-calculate table highlights when content or state changes
watch([() => props.isHighlightAll, () => mdContent.value], () => {
  nextTick(updateTableHighlights);
});

onMounted(() => {
  nextTick(updateTableHighlights);
});

onUpdated(() => {
  nextTick(updateTableHighlights);
});

/**
 * Trigger a browser download for the Markdown content
 */
const downloadMd = () => {
  if (!mdContent.value) return;
  
  // Derive base filename from original PDF name
  let baseName = 'content';
  if (props.pendingFile && props.pendingFile.filename) {
    baseName = props.pendingFile.filename.replace(/\.[^/.]+$/, "");
  }
  
  const blob = new Blob([mdContent.value], { type: 'text/markdown;charset=utf-8' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${baseName}.md`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};
</script>

<style scoped>
/* Main container for the viewer */
.viewer-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

/* Scrollable container for Markdown content */
.md-scroll-area {
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.download-action {
  position: absolute;
  bottom: 32px;
  right: 32px;
  z-index: 100;
}

.action-btn {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transition: all 0.3s ease;
}

.save-btn, .save-btn:hover, .save-btn:focus {
  background: #1890ff !important;
  color: white !important;
}

.md-md {
  padding: 8px 16px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.action-btn:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
}

.highlight-mapped {
  background-color: rgba(255, 0, 0, 0.1); /* Light red background */
  border: 1px solid red; /* Solid red border */
  transition: all 0.3s ease;
}

.bbox-tooltip {
  position: fixed;
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  pointer-events: none;
  z-index: 1000;
  white-space: nowrap;
}

/* Spinner/Loading overlay wrapper */
.convert-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}

.parser-selector {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  background: #f9f9f9;
  padding: 16px 20px;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
  width: 100%;
  max-width: 300px;
}

.parser-radio-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.selector-label {
  font-size: 13px;
  color: #8c8c8c;
  margin-bottom: 4px;
}

.md-loading-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  min-height: 0;
  height: 100%;
}

/* Spinner container fix - Only force 100% height when loading */
.md-loading-wrapper.ant-spin-spinning :deep(.ant-spin-nested-loading),
.md-loading-wrapper.ant-spin-spinning :deep(.ant-spin-container) {
  flex: 1 !important;
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
  min-height: 0 !important;
}

:deep(.ant-spin-nested-loading) {
  display: flex !important;
  flex-direction: column !important;
  flex: 1 !important;
}

:deep(.ant-spin-container) {
  display: flex !important;
  flex-direction: column !important;
  flex: 1 !important;
}

/* Center the Ant Design spinner */
:deep(.ant-spin) {
  max-height: none !important;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

:deep(.ant-spin-dot) {
  position: static !important;
  margin: 0 !important;
}

:deep(.ant-spin-text) {
  position: static !important;
  padding-top: 0 !important;
  text-shadow: none !important;
}

/* Main content area styling */
.info-panel {
  position: relative;
  padding: 24px;
  line-height: 1.8;
  font-size: 15px;
  color: #2c3e50;
  background: #fff;
}

:deep(.cell-highlight) {
  background-color: rgba(255, 0, 0, 0.1) !important;
  border: 1px solid red !important;
  transition: all 0.3s ease;
}

.md-block {
  margin-bottom: 4px;
  border-radius: 4px;
}

.md-block:hover {
  background-color: rgba(0, 123, 255, 0.05);
  box-shadow: 0 0 0 1px rgba(0, 123, 255, 0.1);
}

/* Tooltip hint for double click at the top-right of the block or cell */
.md-block:not(.md-table-block):hover::after,
:deep(td:hover::after),
:deep(th:hover::after) {
  content: var(--edit-hint);
  position: absolute;
  top: 2px;
  right: 6px;
  font-size: 10px;
  color: #1890ff;
  opacity: 0.8;
  pointer-events: none;
  z-index: 10;
  background: rgba(255, 255, 255, 0.7);
  padding: 0 2px;
  border-radius: 2px;
}

:deep(td), :deep(th) {
  position: relative;
}

/* For Chinese locale, we can use a dynamic approach or just keep it English as a common dev indicator, */
.md-block:active {
  background-color: rgba(0, 123, 255, 0.1);
}

.md-heading {
  margin-top: 1.2em;
  margin-bottom: 0.6em;
  font-weight: 600;
  color: #1a1a1a;
  text-align: left;
}

h1.md-heading { font-size: 1.6em; border-bottom: 1px solid #eee; padding-bottom: 0.3em; }
h2.md-heading { font-size: 1.4em; }
h3.md-heading { font-size: 1.2em; }
h4.md-heading { font-size: 1.1em; }

p {
  margin-bottom: 0;
  white-space: pre-wrap;
  text-align: left;
}

/* Table and Image styles within Markdown */
.table-wrapper {
  overflow-x: auto;
  margin: 1em 0;
}

:deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 16px 0;
  font-size: 13px;
}

:deep(th), :deep(td) {
  border: 1px solid #dfe2e5;
  padding: 8px 12px;
  text-align: left;
}

:deep(tr:nth-child(even)) {
  background-color: #f8f9fa;
}

:deep(th) {
  background-color: #f1f3f5;
  font-weight: 600;
}

.image-wrapper {
  margin: 16px 0;
  text-align: center;
}

.image-wrapper img {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.image-wrapper .caption {
  margin-top: 8px;
  font-size: 13px;
  color: #666;
  font-style: italic;
}

/* Empty state styles */
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.convert-prompt {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.convert-prompt .hint-text {
  color: #8c8c8c;
  font-size: 14px;
}

.fallback-content {
  color: #666;
}

/* Custom scrollbar styling for Markdown area */
.md-scroll-area::-webkit-scrollbar {
  width: 8px;
}
.md-scroll-area::-webkit-scrollbar-track {
  background: #f1f1f1;
}
.md-scroll-area::-webkit-scrollbar-thumb {
  background: #ccc;
  border-radius: 4px;
}
.md-scroll-area::-webkit-scrollbar-thumb:hover {
  background: #bbb;
}
</style>
