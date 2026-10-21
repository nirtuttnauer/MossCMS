import { useLayoutEffect, useRef } from 'react';

const confirmationMessage = 'Discard unsaved changes? Your saved draft and live content will be kept.';
const pending = new Map<symbol, string>();

export function confirmNavigation() {
  return pending.size === 0 || window.confirm(pending.values().next().value || confirmationMessage);
}

export function useUnsavedChanges(dirty: boolean, prompt = confirmationMessage) {
  const token = useRef(Symbol('editor'));
  useLayoutEffect(() => {
    if (!dirty)
      return;
    const id = token.current;
    pending.set(id, prompt);
    const unload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', unload);
    return () => {
      pending.delete(id);
      window.removeEventListener('beforeunload', unload);
    };
  }, [dirty, prompt]);
  return () => !dirty || window.confirm(prompt);
}
