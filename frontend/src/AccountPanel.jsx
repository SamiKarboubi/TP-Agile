import { useState } from 'react'

export default function AccountPanel({ account, onDone }) {
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const signup = mode === 'signup'

  async function submit(event) {
    event.preventDefault()
    const success = await account.authenticate(mode, username, password)
    setPassword('')
    if (success) onDone()
  }

  return (
    <section className="account-panel" aria-label="Mon compte">
      <span className="eyebrow">VOTRE COIN CINÉMA</span>
      <h2>{account.user ? <>Bonjour, <em>{account.user.username}.</em></>
        : signup ? <>Votre prochaine <em>sélection.</em></> : <>Heureux de vous <em>retrouver.</em></>}</h2>
      {account.user ? (
        <>
          <p>Vos favoris sont associés à votre compte.</p>
          <button className="account-primary" disabled={account.busy || !account.ready} onClick={account.logout}>Se déconnecter</button>
        </>
      ) : (
        <>
          <div className="account-tabs">
            <button type="button" aria-pressed={!signup} disabled={account.busy} onClick={() => { setMode('login'); setPassword('') }}>Connexion</button>
            <button type="button" aria-pressed={signup} disabled={account.busy} onClick={() => { setMode('signup'); setPassword('') }}>Créer un compte</button>
          </div>
          <p>{signup ? 'Les favoris de cet onglet seront ajoutés à votre nouveau compte.' : 'Retrouvez votre sélection en vous connectant.'}</p>
          <form className="account-form" onSubmit={submit}>
            <label htmlFor="username">Nom d’utilisateur</label>
            <input id="username" name="username" autoComplete="username" value={username}
              onChange={(event) => setUsername(event.target.value)} required minLength={3} maxLength={32}
              pattern="[A-Za-z0-9_.\-]+" aria-describedby="username-help" disabled={account.busy || !account.ready} />
            <small id="username-help">3 à 32 caractères : lettres sans accent, chiffres, point, tiret ou _.</small>
            <label htmlFor="password">Mot de passe</label>
            <input id="password" name="password" type="password" autoComplete={signup ? 'new-password' : 'current-password'}
              value={password} onChange={(event) => setPassword(event.target.value)} required
              minLength={signup ? 12 : 1} maxLength={128} disabled={account.busy || !account.ready} />
            {signup && <small>Au moins 12 caractères. Les espaces sont acceptés.</small>}
            <button className="account-primary" type="submit" disabled={account.busy || !account.ready}>
              {account.busy ? 'Un instant…' : signup ? 'Créer mon compte' : 'Se connecter'}
            </button>
          </form>
        </>
      )}
    </section>
  )
}
