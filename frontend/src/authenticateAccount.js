import { api } from './api.js'

export async function authenticateAccount(mode, username, password, visitorIds) {
  const data = await api(`/auth/${mode}`, {
    method: 'POST', body: { username, password, favorite_ids: visitorIds },
  })
  return { data, remaining: visitorIds.filter((id) => !data.favorite_ids.includes(id)) }
}
