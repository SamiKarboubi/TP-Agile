export function passwordRules(password) {
  const length = Array.from(password).length
  return [
    { valid: length >= 8, message: `Au moins 8 caractères (${length} actuellement).` },
    { valid: length <= 128, message: 'Au maximum 128 caractères.' },
    { valid: /\p{Lu}/u.test(password), message: 'Au moins une lettre majuscule.' },
    { valid: /[0-9]/.test(password), message: 'Au moins un chiffre.' },
    { valid: /[^\p{L}\p{N}\s]/u.test(password), message: 'Au moins un caractère spécial (un espace ne compte pas).' },
  ]
}
