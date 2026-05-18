import { useMemo, useState, type FormEvent } from 'react'

import type { Locale } from '../../shared/types/scientific-kb'
import { AuthError, type AuthErrorCode, type AuthMode } from './types'

const authCopy = {
  ru: {
    product: 'Научная база',
    subtitle: 'Войдите, чтобы работать с материалами, поиском и 3D-графом знаний.',
    login: 'Вход',
    register: 'Регистрация',
    name: 'Имя',
    email: 'Email',
    password: 'Пароль',
    confirmPassword: 'Повторите пароль',
    loginAction: 'Войти',
    registerAction: 'Создать аккаунт',
    switchToLogin: 'Уже есть аккаунт',
    switchToRegister: 'Создать аккаунт',
    passwordHint: 'Минимум 8 символов, буквы и цифры.',
    loading: 'Проверяем...',
    lang: 'EN',
    errors: {
      invalid_credentials: 'Неверный email или пароль.',
      email_taken: 'Пользователь с таким email уже зарегистрирован.',
      weak_password: 'Пароль должен содержать минимум 8 символов, буквы и цифры.',
      password_mismatch: 'Пароли не совпадают.',
      invalid_email: 'Введите корректный email.',
      invalid_name: 'Имя должно быть не короче 2 символов.',
    },
  },
  en: {
    product: 'Scientific Base',
    subtitle: 'Sign in to work with materials, search and the 3D knowledge graph.',
    login: 'Sign In',
    register: 'Register',
    name: 'Name',
    email: 'Email',
    password: 'Password',
    confirmPassword: 'Confirm password',
    loginAction: 'Sign in',
    registerAction: 'Create account',
    switchToLogin: 'I already have an account',
    switchToRegister: 'Create an account',
    passwordHint: 'At least 8 characters with letters and numbers.',
    loading: 'Checking...',
    lang: 'RU',
    errors: {
      invalid_credentials: 'Wrong email or password.',
      email_taken: 'This email is already registered.',
      weak_password: 'Password must include at least 8 characters, letters and numbers.',
      password_mismatch: 'Passwords do not match.',
      invalid_email: 'Enter a valid email.',
      invalid_name: 'Name must be at least 2 characters.',
    },
  },
} as const

type AuthPageProps = {
  locale: Locale
  busy: boolean
  onLocaleChange: (locale: Locale) => void
  onLogin: (input: { email: string; password: string }) => Promise<void>
  onRegister: (input: { name: string; email: string; password: string; confirmPassword: string }) => Promise<void>
}

export function AuthPage({ locale, busy, onLocaleChange, onLogin, onRegister }: AuthPageProps) {
  const t = authCopy[locale]
  const [mode, setMode] = useState<AuthMode>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')

  const canSubmit = useMemo(() => {
    if (mode === 'register' && !name.trim()) return false
    return Boolean(email.trim() && password)
  }, [email, mode, name, password])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    try {
      if (mode === 'login') {
        await onLogin({ email, password })
      } else {
        await onRegister({ name, email, password, confirmPassword })
      }
    } catch (err) {
      setError(authErrorMessage(err, t.errors))
    }
  }

  function switchMode(nextMode: AuthMode) {
    setMode(nextMode)
    setError('')
    setPassword('')
    setConfirmPassword('')
  }

  return (
    <main className="auth-shell">
      <section className="auth-hero">
        <button className="brand auth-brand" aria-label={t.product}>KB</button>
        <h1>{t.product}</h1>
        <p>{t.subtitle}</p>
      </section>

      <section className="auth-card">
        <div className="auth-card-top">
          <div className="auth-tabs" role="tablist" aria-label={t.product}>
            <button className={mode === 'login' ? 'active' : ''} type="button" onClick={() => switchMode('login')}>
              {t.login}
            </button>
            <button className={mode === 'register' ? 'active' : ''} type="button" onClick={() => switchMode('register')}>
              {t.register}
            </button>
          </div>
          <button className="chip auth-lang" type="button" onClick={() => onLocaleChange(locale === 'ru' ? 'en' : 'ru')}>
            {t.lang}
          </button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          {mode === 'register' && (
            <label>
              <span>{t.name}</span>
              <input className="input" autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} />
            </label>
          )}
          <label>
            <span>{t.email}</span>
            <input className="input" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label>
            <span>{t.password}</span>
            <input className="input" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          {mode === 'register' && (
            <label>
              <span>{t.confirmPassword}</span>
              <input className="input" type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
            </label>
          )}
          {mode === 'register' && <small>{t.passwordHint}</small>}
          {error && <div className="auth-error" role="alert">{error}</div>}
          <button className="button primary full" disabled={busy || !canSubmit} type="submit">
            {busy ? t.loading : mode === 'login' ? t.loginAction : t.registerAction}
          </button>
        </form>

        <button className="auth-switch" type="button" onClick={() => switchMode(mode === 'login' ? 'register' : 'login')}>
          {mode === 'login' ? t.switchToRegister : t.switchToLogin}
        </button>
      </section>
    </main>
  )
}

function authErrorMessage(err: unknown, messages: Record<AuthErrorCode, string>) {
  if (err instanceof AuthError) return messages[err.code]
  return String(err)
}
