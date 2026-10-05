import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { authenticateAccount } from './authenticateAccount'

const FAVORITES_KEY = 'moviematch:favorites'
export const MAX_FAVORITES = 20

function readGuestFavorites() {
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(FAVORITES_KEY) || '[]')
    if (!Array.isArray(saved)) return []
    return [...new Set(saved.filter((id) => Number.isSafeInteger(id) && id > 0))]
      .slice(0, MAX_FAVORITES)
  } catch {
    return []
  }
}

export function useAccount() {
  const [favoriteIds, setFavoriteIds] = useState(readGuestFavorites)
  const guestIds = useRef(favoriteIds)
  const userRef = useRef(null)
  const requestVersion = useRef(0)
  const identityVersion = useRef(0)
  const busyRef = useRef(false)
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [accountError, setAccountError] = useState('')
  const [accountNotice, setAccountNotice] = useState('')
  const [storageError, setStorageError] = useState(false)

  const applyAccount = useCallback((data) => {
    if (userRef.current?.id !== data.user?.id) identityVersion.current += 1
    userRef.current = data.user
    setUser(data.user)
    setFavoriteIds(data.user ? data.favorite_ids : guestIds.current)
    setReady(true)
  }, [])

  const refresh = useCallback(() => {
    if (busyRef.current) return Promise.resolve()
    const version = ++requestVersion.current
    return api('/auth/me')
      .then((data) => {
        if (version !== requestVersion.current) return
        applyAccount(data)
        setAccountError('')
      })
      .catch(() => {
        if (version !== requestVersion.current) return
        setReady(false)
        setAccountError('Impossible de vérifier la connexion. Réessayez.')
      })
  }, [applyAccount])

  useEffect(() => {
    refresh()
    window.addEventListener('focus', refresh)
    return () => {
      requestVersion.current += 1
      window.removeEventListener('focus', refresh)
    }
  }, [refresh])

  function saveGuestIds(ids) {
    guestIds.current = ids
    try {
      if (ids.length) window.sessionStorage.setItem(FAVORITES_KEY, JSON.stringify(ids))
      else window.sessionStorage.removeItem(FAVORITES_KEY)
      setStorageError(false)
    } catch {
      setStorageError(true)
    }
  }

  async function authenticate(mode, username, password) {
    if (busyRef.current || !ready) return false
    busyRef.current = true
    setBusy(true)
    requestVersion.current += 1
    setAccountError('')
    setAccountNotice('')
    const visitorIds = [...guestIds.current]
    try {
      const { data, remaining } = await authenticateAccount(mode, username, password, visitorIds)
      // Keep overflow locally; failed authentication never clears visitor favorites.
      saveGuestIds(remaining)
      if (remaining.length) setAccountNotice(`${remaining.length} favori(s) restent dans la session visiteur : votre compte a atteint la limite de 20 favoris. Ils seront accessibles après déconnexion.`)
      applyAccount(data)
      return true
    } catch (error) {
      setAccountError(error.message || 'Impossible de vous connecter.')
      return false
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  async function logout() {
    if (busyRef.current || !ready) return
    busyRef.current = true
    setBusy(true)
    requestVersion.current += 1
    setAccountError('')
    let expired = false
    try {
      await api('/auth/logout', { method: 'POST', userId: userRef.current?.id })
      setAccountNotice('')
      applyAccount({ user: null, favorite_ids: [] })
    } catch (error) {
      expired = error.status === 401
      setAccountError(error.message || 'Impossible de vous déconnecter.')
    } finally {
      busyRef.current = false
      setBusy(false)
    }
    if (expired) await refresh()
  }

  async function toggleFavorite(movieId) {
    if (busyRef.current || !ready) return false
    const removing = favoriteIds.includes(movieId)
    if (!removing && favoriteIds.length >= MAX_FAVORITES) return false
    if (!userRef.current) {
      const ids = removing ? favoriteIds.filter((id) => id !== movieId) : [...favoriteIds, movieId]
      saveGuestIds(ids)
      setFavoriteIds(ids)
      return true
    }
    busyRef.current = true
    setBusy(true)
    requestVersion.current += 1
    setAccountError('')
    let expired = false
    try {
      const data = await api(`/favorites/${movieId}`, {
        method: removing ? 'DELETE' : 'PUT', userId: userRef.current.id,
      })
      setFavoriteIds(data.ids)
      return true
    } catch (error) {
      expired = error.status === 401
      setAccountError(error.message || 'Impossible de modifier les favoris.')
    } finally {
      busyRef.current = false
      setBusy(false)
      if (expired) await refresh()
    }
    return false
  }

  return {
    user, favoriteIds, ready, busy, accountError, accountNotice, storageError,
    identityVersion, refresh, authenticate, logout, toggleFavorite,
  }
}
