import '@testing-library/jest-dom/vitest';

// jsdom lacks ResizeObserver, which finch's components use (as in finch's own setup).
class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
}
window.ResizeObserver = ResizeObserver;

// Importing finch's bundle sets up map/plot workers from blob URLs, which jsdom can't make.
window.URL.createObjectURL ??= () => 'blob:mock';
