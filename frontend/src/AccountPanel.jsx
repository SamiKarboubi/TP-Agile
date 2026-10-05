import { useState } from 'react'
import { passwordRules } from './passwordRules'

const USERNAME_PATTERN = /^[A-Za-z0-9_.\-]{3,32}$/v

export default function AccountPanel({ account, onDone }) {
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirmation, setPasswordConfirmation] = useState('')
  const signup = mode === 'signup'
  const rules = passwordRules(password)
  const confirmationMismatch = signup && passwordConfirmation !== ''
    && passwordConfirmation !== password
  const canSubmit = account.ready && !account.busy
    && (signup
      ? USERNAME_PATTERN.test(username) && rules.every((rule) => rule.valid)
        && passwordConfirmation === password
      : username.trim() !== '' && password !== '')

  async function submit(event) {
    event.preventDefault()
    if (!canSubmit) return
    const success = await account.authenticate(mode, username, password)
    setPassword('')
    setPasswordConfirmation('')
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
            <button type="button" aria-pressed={!signup} disabled={account.busy} onClick={() => { setMode('login'); setPassword(''); setPasswordConfirmation('') }}>Connexion</button>
            <button type="button" aria-pressed={signup} disabled={account.busy} onClick={() => { setMode('signup'); setPassword(''); setPasswordConfirmation('') }}>Créer un compte</button>
          </div>
          <p>Les favoris de cet onglet seront ajoutés à votre compte {signup ? 'à sa création' : 'à la connexion'}.</p>
          <form className="account-form" onSubmit={submit}>
            <label htmlFor="username">Nom d’utilisateur</label>
            <input id="username" name="username" autoComplete="username" value={username}
              onChange={(event) => setUsername(event.target.value)} required minLength={signup ? 3 : undefined} maxLength={32}
              pattern={signup ? USERNAME_PATTERN.source : undefined} aria-describedby="username-help" disabled={account.busy || !account.ready} />
            <small id="username-help">3 à 32 caractères : lettres sans accent, chiffres, point, tiret ou _.</small>
            <label htmlFor="password">Mot de passe</label>
            <input id="password" name="password" type="password" autoComplete={signup ? 'new-password' : 'current-password'}
              value={password} onChange={(event) => setPassword(event.target.value)} required
              minLength={signup ? 8 : undefined} maxLength={128}
              aria-invalid={signup && password !== '' && !rules.every((rule) => rule.valid)}
              aria-describedby={signup ? 'password-help' : undefined}
              disabled={account.busy || !account.ready} />
            {signup && <ul id="password-help" className="password-rules" aria-live="polite">
              {rules.map((rule, index) => <li key={index}
                className={password ? rule.valid ? 'rule-valid' : 'rule-missing' : undefined}>
                <span aria-hidden="true">{password && rule.valid ? '✓' : '○'}</span> {rule.message}
              </li>)}
            </ul>}
            {signup && <>
              <label htmlFor="password-confirmation">Confirmer le mot de passe</label>
              <input id="password-confirmation" name="password-confirmation" type="password"
                autoComplete="new-password" value={passwordConfirmation}
                onChange={(event) => setPasswordConfirmation(event.target.value)}
                required minLength={8} maxLength={128}
                aria-invalid={confirmationMismatch}
                aria-describedby="password-confirmation-help"
                disabled={account.busy || !account.ready} />
              <small id="password-confirmation-help" className={confirmationMismatch ? 'error' : undefined} aria-live="polite">
                {confirmationMismatch ? 'Les mots de passe ne correspondent pas.' : 'Ressaisissez le même mot de passe.'}
              </small>
            </>}
            <button className="account-primary" type="submit" disabled={!canSubmit}>
              {account.busy ? 'Un instant…' : signup ? 'Créer mon compte' : 'Se connecter'}
            </button>
          </form>
        </>
      )}
    </section>
  )
}
