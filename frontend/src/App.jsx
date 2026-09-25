import { useEffect, useRef, useState } from 'react'
import './App.css'

const DEFAULT_MAX_LENGTH = 200

function formatRuntime(minutes) {
  if (!minutes) return null
  const hours = Math.floor(minutes / 60)
  const remaining = minutes % 60
  return hours ? `${hours} h ${remaining ? `${remaining} min` : ''}`.trim() : `${minutes} min`
}

function MovieCard({ movie }) {
  return (
    <article className="movie-card">
      {movie.poster_url ? (
        <img className="poster" src={movie.poster_url} alt={`Affiche de ${movie.title}`} />
      ) : (
        <div className="poster poster-placeholder" aria-label="Affiche indisponible">
          <span>🎬</span>
          Affiche indisponible
        </div>
      )}

      <div className="movie-content">
        <div className="movie-heading">
          <div>
            <h3>{movie.title}</h3>
            <p className="metadata">
              {[movie.year, movie.genres?.slice(0, 2).join(' · '), formatRuntime(movie.runtime)]
                .filter(Boolean)
                .join(' · ')}
            </p>
          </div>
          <div className="ratings" aria-label="Notes du film">
            {movie.imdb_rating != null && <span className="imdb">IMDb {movie.imdb_rating}</span>}
            {movie.tmdb_rating != null && <span>TMDB {movie.tmdb_rating.toFixed(1)}</span>}
          </div>
        </div>

        {movie.director && (
          <p className="credit"><strong>Réalisation :</strong> {movie.director}</p>
        )}
        {movie.main_cast?.length > 0 && (
          <p className="credit"><strong>Avec :</strong> {movie.main_cast.join(', ')}</p>
        )}
        {movie.overview && <p className="overview">{movie.overview}</p>}
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
      setError(requestError.message || 'Le service est temporairement indisponible.')
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
        <div className="brand-mark" aria-hidden="true">M</div>
        <div>
          <h1>Movie Recommendation</h1>
          <p>Décrivez le film que vous avez envie de voir.</p>
        </div>
      </header>

      <section className="conversation" aria-live="polite">
        {conversation.length === 0 && (
          <div className="welcome">
            <span aria-hidden="true">✦</span>
            <h2>Une envie de cinéma ?</h2>
            <p>Essayez « Un thriller après 2010 avec une note IMDb supérieure à 7.5 ».</p>
          </div>
        )}

        {conversation.map((item, index) => (
          <div className={`message ${item.role}`} key={`${item.role}-${index}`}>
            <div className="message-label">{item.role === 'user' ? 'Vous' : 'Assistant'}</div>
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
            <div className="message-label">Assistant</div>
            <div className="message-body loading"><span /><span /><span /></div>
          </div>
        )}
        <div ref={endRef} />
      </section>

      <footer className="composer-wrap">
        {error && <p className="error" role="alert">{error}</p>}
        <form className="composer" onSubmit={submit}>
          <textarea
            aria-label="Votre recherche de film"
            placeholder="Écrivez votre recherche…"
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
          <button type="submit" disabled={loading || !message.trim() || message.length > maxLength}>
            <span className="sr-only">Envoyer</span>
            <span aria-hidden="true">➤</span>
          </button>
        </form>
        <div className={`counter ${message.length > maxLength ? 'over-limit' : ''}`}>
          {message.length} / {maxLength}
        </div>
      </footer>
    </main>
  )
}

export default App
