type ToastType = 'success' | 'error';

let showToastFn: ((message: string, type: ToastType) => void) | null = null;

export function registerToastHandler(handler: (message: string, type: ToastType) => void) {
  showToastFn = handler;
}

export function unregisterToastHandler() {
  showToastFn = null;
}

export function showToast(message: string, type: ToastType = 'success') {
  showToastFn?.(message, type);
}
