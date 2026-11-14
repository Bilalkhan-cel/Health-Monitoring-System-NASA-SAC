// fetch wrapper: JSON in and out, CSRF header on writes, login redirect on 401.

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content ?? '';
}

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export async function api(path, { method = 'GET', body, signal, raw = false } = {}) {
  const headers = { Accept: 'application/json' };
  const init = { method, headers, credentials: 'same-origin', signal };
  if (method !== 'GET' && method !== 'HEAD') headers['X-CSRFToken'] = csrfToken();
  if (body instanceof FormData || body instanceof Blob) {
    init.body = body;
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  if (raw) return response;
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (response.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    throw new ApiError('Your session ended. Log in again.', 401, data);
  }
  if (!response.ok) {
    const message = data?.message || 'Something went wrong. Try again in a moment.';
    throw new ApiError(message, response.status, data);
  }
  return data;
}

export function emitDataUpdated(detail = {}) {
  window.dispatchEvent(new CustomEvent('astro:data-updated', { detail }));
}
