import { useEffect, useRef, useState } from 'react'
import './App.css'

const DEFAULT_MAX_LENGTH = 200
const FAVORITES_KEY = 'moviematch:favorites'
const MAX_FAVORITES = 20
const SUGGESTIONS = [
  'Un thriller après 2010, très bien noté',
  'Un film dans le style d’Interstellar',
  'Une comédie française à voir ce soir',
]

function readFavoriteIds() {
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(FAVORITES_KEY) || '[]')
    if (!Array.isArray(saved)) return []
    return [...new Set(saved.filter((id) => Number.isSafeInteger(id) && id > 0))]
      .slice(0, MAX_FAVORITES)
  } catch {
    return []
  }
}

function formatRuntime(minutes) {
  if (!minutes) return null
  const hours = Math.floor(minutes / 60)
  const remaining = minutes % 60
  return hours ? `${hours} h ${remaining ? `${remaining} min` : ''}`.trim() : `${minutes} min`
}

function MovieCard({ movie, isFavorite, onToggleFavorite, favoriteLimitReached }) {
  const offers = [
    ['Abonnement', movie.streaming],
    ['Gratuit', movie.free],
    ['Avec publicité', movie.ads],
    ['Location', movie.rent],
    ['Achat', movie.buy],
  ].filter(([, names]) => names?.length)
  const poster = movie.poster_url ? (
    <img className="poster" src={movie.poster_url} alt={`Affiche de ${movie.title}`} loading="lazy" />
  ) : (
    <div className="poster poster-placeholder" aria-label="Affiche indisponible">CINÉMA</div>
  )

  return (
    <article className="movie-card">
      <div className="poster-frame">
        {poster}
      </div>

      <div className="movie-content">
        <div className="movie-topline">
          <span>SÉLECTION</span>
          {movie.year && <span>{movie.year}</span>}
        </div>
        <div className="movie-heading">
          <div>
            <h3>{movie.title}</h3>
            <p className="metadata">
              {[movie.genres?.slice(0, 2).join(' · '), formatRuntime(movie.runtime)].filter(Boolean).join(' · ')}
            </p>
          </div>
          <div className="ratings" aria-label="Notes du film">
            {movie.imdb_rating != null && <span>IMDb <strong>{movie.imdb_rating}</strong></span>}
            {movie.tmdb_rating != null && <span>TMDB <strong>{movie.tmdb_rating.toFixed(1)}</strong></span>}
          </div>
        </div>

        {movie.director && <p className="credit"><strong>Réalisation</strong> {movie.director}</p>}
        {movie.main_cast?.length > 0 && <p className="credit"><strong>Avec</strong> {movie.main_cast.join(', ')}</p>}
        {movie.overview && <p className="overview">{movie.overview}</p>}

        <div className="availability">
          <div className="availability-heading">
            <span>OÙ VOIR CE FILM</span>
            <span>{movie.watch_region || 'FR'}</span>
          </div>
          {offers.length ? (
            <div className="offer-list">
              {offers.map(([label, names]) => (
                <p className="offer-row" key={label}><span>{label}</span><strong>{names.join(' · ')}</strong></p>
              ))}
            </div>
          ) : <p className="availability-empty">Aucune plateforme renseignée pour ce pays.</p>}
          <div className="movie-actions">
            {movie.trailer_url && <a className="primary-link" href={movie.trailer_url} target="_blank" rel="noopener noreferrer">Voir la bande-annonce <span aria-hidden="true">↗</span></a>}
            <button
              className={`favorite-toggle ${isFavorite ? 'is-favorite' : ''}`}
              type="button"
              aria-pressed={isFavorite}
              aria-label={isFavorite ? `Retirer ${movie.title} des favoris` : `Ajouter ${movie.title} aux favoris`}
              title={!isFavorite && favoriteLimitReached ? 'Limite de 20 favoris atteinte' : undefined}
              disabled={!isFavorite && favoriteLimitReached}
              onClick={() => onToggleFavorite(movie)}
            ><span aria-hidden="true">{isFavorite ? '♥' : '♡'}</span> {isFavorite ? 'Dans mes favoris' : 'Ajouter aux favoris'}</button>
          </div>
          {offers.length > 0 && <small>Disponibilités : JustWatch via TMDB · Les offres peuvent évoluer.</small>}
        </div>
      </div>
    </article>
  )
}

function App() {
  const [message, setMessage] = useState('')
  const [maxLength, setMaxLength] = useState(DEFAULT_MAX_LENGTH)
  const [conversation, setConversation] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [view, setView] = useState('discover')
  const [favoriteIds, setFavoriteIds] = useState(readFavoriteIds)
  const [favoriteMovies, setFavoriteMovies] = useState({})
  const [favoritesLoading, setFavoritesLoading] = useState(false)
  const [favoritesError, setFavoritesError] = useState('')
  const [storageError, setStorageError] = useState(false)
  const endRef = useRef(null)
  const textRef = useRef(null)

  useEffect(() => {
    fetch('/api/config')
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data) => setMaxLength(data.max_user_message_length))
      .catch(() => setMaxLength(DEFAULT_MAX_LENGTH))
  }, [])

  useEffect(() => {
    if (view === 'discover') endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation, loading, view])

  function saveFavoriteIds(ids) {
    setFavoriteIds(ids)
    try {
      window.sessionStorage.setItem(FAVORITES_KEY, JSON.stringify(ids))
      setStorageError(false)
    } catch {
      setStorageError(true)
    }
  }

  async function showFavorites() {
    setView('favorites')
    const missing = favoriteIds.filter((id) => !favoriteMovies[id])
    if (!missing.length || favoritesLoading) return

    setFavoritesLoading(true)
    setFavoritesError('')
    try {
      const response = await fetch('/api/movies/lookup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: missing }),
      })
      if (!response.ok) throw new Error('Impossible de retrouver vos films favoris.')
      const data = await response.json()
      if (!Array.isArray(data.movies) || data.movies.length !== missing.length
        || missing.some((id) => !data.movies.some((movie) => movie.id === id))) {
        throw new Error('Certaines fiches de films sont indisponibles.')
      }
      setFavoriteMovies((current) => ({
        ...current,
        ...Object.fromEntries(data.movies.map((movie) => [movie.id, movie])),
      }))
    } catch (requestError) {
      setFavoritesError(requestError.message || 'Impossible de charger les favoris.')
    } finally {
      setFavoritesLoading(false)
    }
  }

  function toggleFavorite(movie) {
    setFavoritesError('')
    if (favoriteIds.includes(movie.id)) {
      saveFavoriteIds(favoriteIds.filter((id) => id !== movie.id))
      return
    }
    if (favoriteIds.length >= MAX_FAVORITES) return
    setFavoriteMovies((movies) => ({ ...movies, [movie.id]: movie }))
    saveFavoriteIds([...favoriteIds, movie.id])
  }

  async function submit(event) {
    event?.preventDefault()
    const trimmed = message.trim()
    if (!trimmed || loading) return
    if (trimmed.length > maxLength) {
      setError(`Votre message dépasse la limite de ${maxLength} caractères.`)
      return
    }

    setConversation((items) => [...items, { role: 'user', text: trimmed }])
    setMessage('')
    setError('')
    setLoading(true)

    try {
      const response = await fetch('/api/recommendations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed, favorite_ids: favoriteIds }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'La recherche a échoué.')
      }
      setConversation((items) => [
        ...items,
        { role: 'assistant', text: data.message, movies: data.movies ?? [] },
      ])
    } catch (requestError) {
      setConversation((items) => [...items, {
        role: 'assistant',
        text: requestError.message || 'Le service est temporairement indisponible.',
      }])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div className="brand-mark" aria-hidden="true">M<span>.</span></div>
        <div className="brand-copy">
          <h1>MovieMatch</h1>
          <p>LE BON FILM, AU BON MOMENT</p>
        </div>
        <nav className="view-nav" aria-label="Navigation principale">
          <button type="button" className={view === 'discover' ? 'active' : ''} aria-current={view === 'discover' ? 'page' : undefined} onClick={() => setView('discover')}>Découvrir</button>
          <button type="button" className={view === 'favorites' ? 'active' : ''} aria-current={view === 'favorites' ? 'page' : undefined} onClick={showFavorites}>Favoris <span>{favoriteIds.length}</span></button>
        </nav>
      </header>

      <section className="conversation" aria-live="polite" aria-label="Conversation" hidden={view !== 'discover'}>
        {conversation.length === 0 && (
          <div className="welcome">
            <span className="eyebrow">LE FILM DE CE SOIR COMMENCE ICI</span>
            <h2>Qu’est-ce qu’on <em>regarde ?</em></h2>
            <p>Une ambiance, un acteur, une envie précise : racontez-nous ce que vous cherchez.</p>
            <div className="suggestions" aria-label="Idées de recherche">
              {SUGGESTIONS.map((suggestion) => (
                <button key={suggestion} type="button" onClick={() => {
                  setMessage(suggestion)
                  textRef.current?.focus()
                }}>{suggestion} <span aria-hidden="true">↗</span></button>
              ))}
            </div>
            <div className="welcome-line"><span>01 / DÉCRIVEZ</span><span>02 / DÉCOUVREZ</span><span>03 / REGARDEZ</span></div>
          </div>
        )}

        {conversation.map((item, index) => (
          <div className={`message ${item.role}`} key={`${item.role}-${index}`}>
            <div className="message-label">{item.role === 'user' ? 'VOUS' : 'MOVIEMATCH'}</div>
            <div className="message-body">
              <p>{item.text}</p>
              {item.movies?.length > 0 && (
                <div className="movie-list">
                  {item.movies.map((movie) => (
                    <MovieCard
                      movie={movie}
                      key={movie.id}
                      isFavorite={favoriteIds.includes(movie.id)}
                      onToggleFavorite={toggleFavorite}
                      favoriteLimitReached={favoriteIds.length >= MAX_FAVORITES}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="message assistant">
            <div className="message-label">MOVIEMATCH</div>
            <div className="message-body loading" role="status" aria-label="Recherche en cours"><span /><span /><span /></div>
          </div>
        )}
        <div ref={endRef} />
      </section>

      {view === 'favorites' && (
        <section className="favorites-panel" aria-label="Mes favoris">
          <div className="favorites-intro">
            <span className="eyebrow">MA SÉLECTION</span>
            <h2>Mes <em>favoris.</em></h2>
            <p>{favoriteIds.length} film{favoriteIds.length > 1 ? 's' : ''} enregistré{favoriteIds.length > 1 ? 's' : ''} dans cet onglet. La liste disparaît à la fin de la session.</p>
          </div>
          {storageError && <p className="error" role="alert">Le navigateur bloque le stockage de session : les favoris risquent de disparaître après actualisation.</p>}
          {favoriteIds.length === 0 ? (
            <div className="favorites-empty">
              <p>Votre sélection est encore vide.</p>
              <button type="button" onClick={() => setView('discover')}>Découvrir des films ↗</button>
            </div>
          ) : (
            <>
              {favoritesLoading && <p className="favorites-status" role="status">Chargement des fiches…</p>}
              {favoritesError && <div className="favorites-status" role="alert">
                <p>{favoritesError}</p>
                <button type="button" onClick={showFavorites}>Réessayer</button>
              </div>}
              <div className="movie-list">
                {favoriteIds.map((id) => favoriteMovies[id] && (
                  <MovieCard
                    movie={favoriteMovies[id]}
                    key={id}
                    isFavorite
                    onToggleFavorite={toggleFavorite}
                    favoriteLimitReached={false}
                  />
                ))}
              </div>
            </>
          )}
        </section>
      )}

      {view === 'discover' && <footer className="composer-wrap">
        {error && <p className="error" role="alert">{error}</p>}
        <form className="composer" onSubmit={submit}>
          <textarea
            ref={textRef}
            aria-label="Votre recherche de film"
            placeholder="Décrivez le film que vous avez envie de voir…"
            value={message}
            onChange={(event) => {
              setMessage(event.target.value)
              setError('')
            }}
            onKeyDown={handleKeyDown}
            rows="2"
            maxLength={maxLength + 1}
            disabled={loading}
          />
          <button type="submit" disabled={loading || !message.trim() || message.trim().length > maxLength}>
            <span>Rechercher</span><span aria-hidden="true">↗</span>
          </button>
        </form>
        <div className="composer-note"><span>Entrée pour rechercher · Maj + Entrée pour une nouvelle ligne</span><span className={message.length > maxLength ? 'over-limit' : ''}>{message.length} / {maxLength}</span></div>
      </footer>}
    </main>
  )
}

export default App
