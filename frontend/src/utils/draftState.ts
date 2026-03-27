export function loadDraftValue(
  key: string,
  fallback = '',
  storage: Pick<Storage, 'getItem'> | undefined = typeof window !== 'undefined'
    ? window.localStorage
    : undefined
): string {
  if (!storage) return fallback;
  try {
    const value = storage.getItem(key);
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

export function saveDraftValue(
  key: string,
  value: string,
  storage: Pick<Storage, 'setItem'> | undefined = typeof window !== 'undefined'
    ? window.localStorage
    : undefined
): void {
  if (!storage) return;
  try {
    storage.setItem(key, value);
  } catch {
    // Best-effort only. Draft persistence should never block UI.
  }
}

export function clearDraftValue(
  key: string,
  storage: Pick<Storage, 'removeItem'> | undefined = typeof window !== 'undefined'
    ? window.localStorage
    : undefined
): void {
  if (!storage) return;
  try {
    storage.removeItem(key);
  } catch {
    // Ignore storage failures.
  }
}
