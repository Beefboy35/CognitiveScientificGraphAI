import { useCallback, useEffect, useState } from 'react'

import type { AuthUser } from '../types'
import {
  bootstrapCurrentUser,
  clearAuthStorage,
  getCurrentUserSync,
  loginUser,
  logoutUser,
  registerUser,
} from './authStore'

type RegisterInput = Parameters<typeof registerUser>[0]
type LoginInput = Parameters<typeof loginUser>[0]

export function useAuthSession() {
  const [user, setUser] = useState<AuthUser | null>(() => getCurrentUserSync())
  const [isReady, setReady] = useState<boolean>(() => getCurrentUserSync() === null && !localStorageHasToken())

  useEffect(() => {
    let cancelled = false
    bootstrapCurrentUser()
      .then((current) => {
        if (cancelled) return
        setUser(current)
      })
      .catch(() => {
        if (cancelled) return
        clearAuthStorage()
        setUser(null)
      })
      .finally(() => {
        if (!cancelled) setReady(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const signIn = useCallback(async (input: LoginInput) => {
    const nextUser = await loginUser(input)
    setUser(nextUser)
    return nextUser
  }, [])

  const signUp = useCallback(async (input: RegisterInput) => {
    const nextUser = await registerUser(input)
    setUser(nextUser)
    return nextUser
  }, [])

  const signOut = useCallback(async () => {
    await logoutUser()
    setUser(null)
  }, [])

  return { user, isReady, signIn, signUp, signOut }
}

function localStorageHasToken(): boolean {
  try {
    return Boolean(localStorage.getItem('kb.auth.access_token'))
  } catch {
    return false
  }
}
