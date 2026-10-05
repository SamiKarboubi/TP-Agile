import { useEffect, useRef, useState } from 'react'
import './App.css'
import { api } from './api'
import { MAX_FAVORITES, useAccount } from './useAccount'
import AccountPanel from './AccountPanel'
import WelcomeSelection from './WelcomeSelection'

const DEFAULT_MAX_LENGTH = 200
const SUGGESTIONS = [
  'Un thriller après 2010, très bien noté',
  'Un film dans le style d’Interstellar',
  'Une comédie française à voir ce soir',
]

function formatRuntime(minutes) {
  if (!minutes) return null
  const hours = Math.floor(minutes / 60)
  const remaining = minutes % 60
  return hours ? `${hours} h ${remaining ? `${remaining} min` : ''}`.trim() : `${minutes} min`
}

function MovieCard({ movie, isFavorite, onToggleFavorite, favoriteLimitReached, disabled }) {
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
              disabled={disabled || (!isFavorite && favoriteLimitReached)}
              onClick={() => onToggleFavorite(movie)}
            ><span aria-hidden="true">{isFavorite ? '♥' : '♡'}</span> {isFavorite ? 'Dans mes favoris' : 'Ajouter aux favoris'}</button>
          </div>
          {offers.length > 0 && <small>Disponibilités : JustWatch via TMDB · Les offres peuvent évoluer.</small>}
        </div>
      </div>
    </article>
  )
}

function MovieApp({ account }) {
  const { favoriteIds, user, ready, busy, identityVersion } = account
  const [message, setMessage] = useState('')
  const [maxLength, setMaxLength] = useState(DEFAULT_MAX_LENGTH)
  const [conversation, setConversation] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [view, setView] = useState('discover')
  const [favoriteMovies, setFavoriteMovies] = useState({})
  const [favoritesError, setFavoritesError] = useState('')
  const [favoritesRetry, setFavoritesRetry] = useState(0)
  const endRef = useRef(null)
  const textRef = useRef(null)
  const favoritesLoading = view === 'favorites' && ready && !favoritesError
    && favoriteIds.some((id) => !favoriteMovies[id])

  useEffect(() => {
    fetch('/api/config')
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data) => setMaxLength(data.max_user_message_length))
      .catch(() => setMaxLength(DEFAULT_MAX_LENGTH))
  }, [])

  useEffect(() => {
    if (view === 'discover') endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation, loading, view])

  useEffect(() => {
    if (view !== 'discover') window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [view])

  useEffect(() => {
    if (view !== 'favorites' || !ready) return
    const missing = favoriteIds.filter((id) => !favoriteMovies[id])
    if (!missing.length) return
    const controller = new AbortController()
    api('/movies/lookup', { method: 'POST', body: { ids: missing }, signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return
        if (!Array.isArray(data.movies) || data.movies.length !== missing.length
          || missing.some((id) => !data.movies.some((movie) => movie.id === id))) {
          throw new Error('Certaines fiches de films sont indisponibles.')
        }
        setFavoriteMovies((current) => ({
          ...current,
          ...Object.fromEntries(data.movies.map((movie) => [movie.id, movie])),
        }))
        setFavoritesError('')
      })
      .catch((requestError) => {
        if (!controller.signal.aborted) setFavoritesError(requestError.message || 'Impossible de charger les favoris.')
      })
    return () => controller.abort()
  }, [view, favoriteIds, favoriteMovies, favoritesRetry, ready])

  function showFavorites() {
    setFavoritesError('')
    setView('favorites')
    account.refresh()
  }

  async function toggleFavorite(movie) {
    const version = identityVersion.current
    setFavoritesError('')
    const success = await account.toggleFavorite(movie.id)
    if (success && version === identityVersion.current) {
      setFavoriteMovies((movies) => ({ ...movies, [movie.id]: movie }))
    }
  }

  async function submit(event) {
    event?.preventDefault()
    const trimmed = message.trim()
    if (!trimmed || loading || !ready || busy) return
    if (trimmed.length > maxLength) {
      setError(`Votre message dépasse la limite de ${maxLength} caractères.`)
      return
    }

    setConversation((items) => [...items, { role: 'user', text: trimmed }])
    setMessage('')
    setError('')
    setLoading(true)
    const version = identityVersion.current

    try {
      const data = await api('/recommendations', {
        method: 'POST',
        userId: user?.id,
        body: { message: trimmed, favorite_ids: user ? [] : favoriteIds },
      })
      if (version !== identityVersion.current) return
      setConversation((items) => [
        ...items,
        { role: 'assistant', text: data.message, movies: data.movies ?? [] },
      ])
    } catch (requestError) {
      if (requestError.status === 401) await account.refresh()
      if (version !== identityVersion.current) return
      setConversation((items) => [...items, {
        role: 'assistant',
        text: requestError.message || 'Le service est temporairement indisponible.',
      }])
    } finally {
      if (version === identityVersion.current) setLoading(false)
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
      <div>
      <header className="app-header">
        <div className="brand-mark" aria-hidden="true">M<span>.</span></div>
        <div className="brand-copy">
          <h1>MovieMatch</h1>
          <p>LE BON FILM, AU BON MOMENT</p>
        </div>
        <nav className="view-nav" aria-label="Navigation principale">
          <button type="button" className={view === 'discover' ? 'active' : ''} aria-current={view === 'discover' ? 'page' : undefined} onClick={() => setView('discover')}>Découvrir</button>
          <button type="button" className={view === 'favorites' ? 'active' : ''} aria-current={view === 'favorites' ? 'page' : undefined} onClick={showFavorites}>Favoris <span>{favoriteIds.length}</span></button>
          <button type="button" className={view === 'account' ? 'active' : ''} aria-current={view === 'account' ? 'page' : undefined} onClick={() => setView('account')}>{user ? user.username : 'Mon compte'}</button>
        </nav>
      </header>
      {!ready && !account.accountError && <p className="account-status" role="status">Vérification de la connexion…</p>}
      {account.accountNotice && <p className="account-status" role="status">{account.accountNotice}</p>}
      {account.accountError && <div className="account-status" role="alert">
        <p className="error">{account.accountError}</p>
        {!ready && <button type="button" onClick={account.refresh}>Réessayer</button>}
      </div>}
      </div>

      {view === 'account' && <AccountPanel account={account} onDone={() => setView('discover')} />}

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
                      disabled={!ready || busy}
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
            <p>{favoriteIds.length} film{favoriteIds.length > 1 ? 's' : ''} enregistré{favoriteIds.length > 1 ? 's' : ''} {user ? `pour ${user.username}.` : 'dans cet onglet. La liste disparaît à la fin de la session.'}</p>
            {!user && <button className="account-invite" type="button" onClick={() => setView('account')}>Créer un compte pour retrouver ma sélection ↗</button>}
          </div>
          {!user && account.storageError && <p className="error" role="alert">Le navigateur bloque le stockage de session : les favoris risquent de disparaître après actualisation.</p>}
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
                <button type="button" onClick={() => { setFavoritesError(''); setFavoritesRetry((value) => value + 1) }}>Réessayer</button>
              </div>}
              <div className="movie-list">
                {favoriteIds.map((id) => favoriteMovies[id] && (
                  <MovieCard
                    movie={favoriteMovies[id]}
                    key={id}
                    isFavorite
                    onToggleFavorite={toggleFavorite}
                    favoriteLimitReached={false}
                    disabled={!ready || busy}
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
            disabled={loading || !ready || busy}
          />
          <button type="submit" disabled={loading || !ready || busy || !message.trim() || message.trim().length > maxLength}>
            <span>Rechercher</span><span aria-hidden="true">↗</span>
          </button>
        </form>
        <div className="composer-note"><span>Entrée pour rechercher · Maj + Entrée pour une nouvelle ligne</span><span className={message.length > maxLength ? 'over-limit' : ''}>{message.length} / {maxLength}</span></div>
      </footer>}
    </main>
  )
}

function App() {
  const account = useAccount()
  const [showWelcome, setShowWelcome] = useState(() => {
    try { return window.sessionStorage.getItem('moviematch:welcome-dismissed') !== '1' }
    catch { return true }
  })
  function continueToSite() {
    try { window.sessionStorage.setItem('moviematch:welcome-dismissed', '1') }
    catch { /* Dismissal still works when browser storage is unavailable. */ }
    setShowWelcome(false)
  }
  if (showWelcome) return <WelcomeSelection account={account} onContinue={continueToSite} />
  // Reset the conversation and movie cache whenever the connected account changes.
  return <MovieApp key={account.user?.id || 'guest'} account={account} />
}

export default App
