import { useEffect, useRef, useState } from 'react'
import './App.css'

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

function MovieCard({ movie }) {
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
  const endRef = useRef(null)
  const textRef = useRef(null)

  useEffect(() => {
    fetch('/api/config')
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data) => setMaxLength(data.max_user_message_length))
      .catch(() => setMaxLength(DEFAULT_MAX_LENGTH))
  }, [])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation, loading])

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
        body: JSON.stringify({ message: trimmed }),
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
        <span className="header-edition">VOTRE SÉLECTION CINÉMA</span>
      </header>

      <section className="conversation" aria-live="polite" aria-label="Conversation">
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
                  {item.movies.map((movie) => <MovieCard movie={movie} key={movie.id} />)}
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

      <footer className="composer-wrap">
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
      </footer>
    </main>
  )
}

export default App
