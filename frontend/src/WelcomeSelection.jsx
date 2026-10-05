import { useEffect, useState } from 'react'
import { api } from './api'
import { MAX_FAVORITES } from './useAccount'

export default function WelcomeSelection({ account, onContinue }) {
  const [movies, setMovies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    api('/movies/random', { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return
        if (!Array.isArray(data.movies) || data.movies.length !== 5
          || new Set(data.movies.map((movie) => movie.id)).size !== 5) {
          throw new Error('La sélection est temporairement indisponible.')
        }
        setMovies(data.movies)
      })
      .catch((requestError) => {
        if (!controller.signal.aborted) setError(requestError.message)
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [retry])

  return <main className="welcome-selection">
    <header className="welcome-selection-header">
      <span className="welcome-brand">MovieMatch<span>.</span></span>
      <button className="welcome-skip" type="button" onClick={onContinue}>Passer cette étape ↗</button>
    </header>
    <section aria-labelledby="welcome-title">
      <span className="eyebrow">CINQ FILMS, POUR COMMENCER</span>
      <h1 id="welcome-title">Un coup de <em>cœur ?</em></h1>
      <p className="welcome-description">Une sélection au hasard. Gardez les films qui vous tentent : ils aideront MovieMatch à affiner vos prochaines recommandations.</p>
      {loading && <p className="favorites-status" role="status">Préparation de votre sélection…</p>}
      {error && <div className="favorites-status" role="alert"><p>{error}</p>
        <button type="button" onClick={() => { setLoading(true); setError(''); setRetry((value) => value + 1) }}>Réessayer</button>
      </div>}
      {account.accountError && <div role="alert"><p className="error">{account.accountError}</p>
        {!account.ready && <button className="welcome-skip" type="button" onClick={account.refresh}>Vérifier la connexion</button>}
      </div>}
      {account.storageError && <p className="error" role="alert">Le stockage de session est bloqué. Vos favoris visiteurs risquent de disparaître après actualisation.</p>}
      <div className="welcome-movies">
        {movies.map((movie) => {
          const favorite = account.favoriteIds.includes(movie.id)
          const full = account.favoriteIds.length >= MAX_FAVORITES
          return <article className="welcome-movie" key={movie.id}>
            {movie.poster_url
              ? <img src={movie.poster_url} alt={`Affiche de ${movie.title}`} />
              : <div className="welcome-poster-empty" aria-label="Affiche indisponible">MovieMatch</div>}
            <div className="welcome-movie-copy">
              <span className="welcome-year">{movie.year || 'Année non renseignée'}</span>
              <h2>{movie.title}</h2>
              <button className={`favorite-toggle ${favorite ? 'is-favorite' : ''}`}
                type="button" aria-pressed={favorite}
                aria-label={`${favorite ? 'Retirer' : 'Ajouter'} ${movie.title} ${favorite ? 'des' : 'aux'} favoris`}
                disabled={!account.ready || account.busy || (!favorite && full)}
                onClick={() => account.toggleFavorite(movie.id)}>
                <span aria-hidden="true">{favorite ? '♥' : '♡'}</span> {favorite ? 'En favoris' : 'Ajouter'}
              </button>
            </div>
          </article>
        })}
      </div>
      <div className="welcome-continue">
        <p>{account.favoriteIds.length >= MAX_FAVORITES ? 'Limite de 20 favoris atteinte. Vous pouvez en retirer pour faire de la place.'
          : account.user ? 'Vos choix sont enregistrés dans votre compte.' : 'Vos choix restent dans cet onglet. Connectez-vous ensuite pour les conserver dans votre compte.'}</p>
        <button className="account-primary" type="button" onClick={onContinue}>Continuer vers MovieMatch ↗</button>
      </div>
    </section>
  </main>
}
