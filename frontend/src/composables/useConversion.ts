import { ref, onUnmounted } from 'vue';
import axios from 'axios';
import { message } from 'ant-design-vue';
import { useI18n } from 'vue-i18n';

export function useConversion() {
  const { t } = useI18n();
  const taskId = ref('');
  const pdfUrl = ref('');
  const mdContent = ref('');
  const contentList = ref<any[]>([]);
  const contentTables = ref<Record<string, any>>({});
  const currentHighlights = ref<any[]>([]);
  const isUploading = ref(false);
  const isProcessing = ref(false);
  const uploadStatusText = ref('');
  const pendingFile = ref<any>(null);
  const selectedProvider = ref('mineru');
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002';

  const handleUploadChange = async (info: any) => {
    if (info.file.status === 'uploading') {
      isUploading.value = true;
      taskId.value = '';
      pendingFile.value = null;
      mdContent.value = '';
      contentList.value = [];
      currentHighlights.value = [];
      uploadStatusText.value = t('messages.uploading');
      
      if (info.file.originFileObj) {
        // Revoke old blob URL to prevent memory leaks when re-uploading
        if (pdfUrl.value && pdfUrl.value.startsWith('blob:')) {
          URL.revokeObjectURL(pdfUrl.value);
        }
        // Create a local blob URL for immediate preview
        pdfUrl.value = URL.createObjectURL(info.file.originFileObj);
      }
      return;
    }
    
    if (info.file.status === 'done') {
      isUploading.value = false;
      pendingFile.value = info.file.response;
    } else if (info.file.status === 'error') {
      isUploading.value = false;
      message.error(t('messages.upload_failed'));
    }
  };

  const startConversion = async () => {
    if (!pendingFile.value) return;
    
    isProcessing.value = true;
    const providerName = selectedProvider.value === 'mineru' ? 'MinerU AI' : 'PyMuPDF';
    uploadStatusText.value = t('messages.starting_engine', { engine: providerName });
    
    const res = pendingFile.value;
    taskId.value = res.task_id;
    
    // Only update to backend URL if we don't already have a local blob URL.
    // This prevents the PDF preview from flickering/reloading during conversion.
    if (!pdfUrl.value || !pdfUrl.value.startsWith('blob:')) {
      pdfUrl.value = `${apiBaseUrl}${res.pdf_url}`;
    }
    
    try {
      // Timers for updating progress messages during long-running conversion
      const timers: any[] = [];
      timers.push(setTimeout(() => {
        if (isProcessing.value) uploadStatusText.value = t('messages.extracting_layout');
      }, 3000));
      
      timers.push(setTimeout(() => {
        if (isProcessing.value) uploadStatusText.value = t('messages.converting_markdown');
      }, 10000));
      
      const mineruApiUrl = localStorage.getItem('mineru_api_url');
      const mineruApiKey = localStorage.getItem('mineru_api_key');
      
      const convertRes = await axios.post(`${apiBaseUrl}/api/convert`, {
        task_id: res.task_id,
        filename: res.filename,
        provider: selectedProvider.value,
        mineru_api_url: mineruApiUrl || undefined,
        mineru_api_key: mineruApiKey || undefined
      });

      const conversionData = convertRes.data;
      const fetchTasks = [];
      
      if (conversionData.md_url) {
        fetchTasks.push(axios.get(`${apiBaseUrl}${conversionData.md_url}`).then(r => ({ type: 'md', data: r.data })));
      }
      
      if (conversionData.content_list_url) {
        fetchTasks.push(axios.get(`${apiBaseUrl}${conversionData.content_list_url}`).then(r => ({ type: 'list', data: r.data })));
      }

      if (conversionData.content_tables_url) {
        fetchTasks.push(axios.get(`${apiBaseUrl}${conversionData.content_tables_url}`).then(r => ({ type: 'tables', data: r.data })));
      }
      
      const results = await Promise.all(fetchTasks);
      
      timers.forEach(t => clearTimeout(t));

      // Reset values
      mdContent.value = '';
      contentList.value = [];
      contentTables.value = {};

      results.forEach(res => {
        if (res.type === 'md') mdContent.value = res.data;
        else if (res.type === 'list') {
          let data = res.data;
          if (typeof data === 'string') data = JSON.parse(data);
          if (Array.isArray(data)) {
            contentList.value = data;
          } else if (data && typeof data === 'object') {
            contentList.value = data.content_list || data.data || [];
          }
        }
        else if (res.type === 'tables') {
          contentTables.value = res.data || {};
        }
      });
      
      message.success(t('messages.convert_success'));
      // Keep pendingFile to retain the filename for later downloads
      // pendingFile.value = null;
    } catch (err: any) {
      console.error('Conversion error details:', {
        message: err.message,
        response: err.response?.data,
        status: err.response?.status
      });
      const errorMsg = err.response?.data?.detail || err.message || t('messages.convert_failed');
      message.error(t('messages.parse_failed', { error: errorMsg }));
      taskId.value = ''; 
    } finally {
      isProcessing.value = false;
      uploadStatusText.value = '';
    }
  };

  const resetAll = () => {
    if (pdfUrl.value && pdfUrl.value.startsWith('blob:')) {
      URL.revokeObjectURL(pdfUrl.value);
    }
    taskId.value = '';
    pdfUrl.value = '';
    mdContent.value = '';
    contentList.value = [];
    contentTables.value = {};
    pendingFile.value = null;
  };

  onUnmounted(() => {
    if (pdfUrl.value && pdfUrl.value.startsWith('blob:')) {
      URL.revokeObjectURL(pdfUrl.value);
    }
  });

  return {
    taskId,
    pdfUrl,
    mdContent,
    contentList,
    contentTables,
    isUploading,
    isProcessing,
    uploadStatusText,
    pendingFile,
    selectedProvider,
    currentHighlights,
    handleUploadChange,
    startConversion,
    resetAll,
    apiBaseUrl
  };
}
