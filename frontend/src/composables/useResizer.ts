import { ref, onUnmounted } from 'vue';

export function useResizer(initialWidth = 50) {
  const leftWidth = ref(initialWidth);
  const isResizing = ref(false);

  const startResizing = () => {
    isResizing.value = true;
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', stopResizing);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!isResizing.value) return;
    
    const container = document.querySelector('.viewer-container');
    if (container) {
      const rect = container.getBoundingClientRect();
      const newWidth = ((e.clientX - rect.left) / rect.width) * 100;
      
      // Limit resizing range between 20% and 80% to maintain usability
      if (newWidth > 20 && newWidth < 80) {
        leftWidth.value = newWidth;
      }
    }
  };

  const stopResizing = () => {
    isResizing.value = false;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', stopResizing);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };

  onUnmounted(() => {
    stopResizing();
  });

  return {
    leftWidth,
    isResizing,
    startResizing
  };
}
