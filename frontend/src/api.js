export async function api(path, { method = 'GET', body, userId, signal } = {}) {
  const headers = {}
  if (method !== 'GET') headers['X-MovieMatch-Request'] = '1'
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (userId) headers['X-MovieMatch-User'] = userId
  const response = await fetch(`/api${path}`, {
    method, headers, signal, credentials: 'same-origin', cache: 'no-store',
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  })
  const data = response.status === 204 ? null : await response.json().catch(() => ({}))
  if (!response.ok) {
    const validationMessage = Array.isArray(data?.detail)
      ? data.detail.map((item) => item.msg?.replace(/^Value error, /, '')).filter(Boolean).join(' ')
      : ''
    const error = new Error(typeof data?.detail === 'string'
      ? data.detail : validationMessage || 'La demande a échoué. Vérifiez les informations saisies.')
    error.status = response.status
    throw error
  }
  return data
}
