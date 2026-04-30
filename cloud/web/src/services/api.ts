const BASE = '/api/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  const body = await res.json()
  return body.data ?? body
}

export async function get<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'GET' })
}

export async function post<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: data ? JSON.stringify(data) : undefined })
}

export async function put<T>(path: string, data: unknown): Promise<T> {
  return request<T>(path, { method: 'PUT', body: JSON.stringify(data) })
}

export async function del(path: string): Promise<void> {
  await fetch(`${BASE}${path}`, { method: 'DELETE' })
}
