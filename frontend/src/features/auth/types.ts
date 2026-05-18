export type AuthMode = 'login' | 'register'

export type AuthUser = {
  id: string
  name: string
  email: string
  role: 'teacher'
  createdAt: string
}

export type AuthErrorCode =
  | 'invalid_credentials'
  | 'email_taken'
  | 'weak_password'
  | 'password_mismatch'
  | 'invalid_email'
  | 'invalid_name'

export class AuthError extends Error {
  code: AuthErrorCode

  constructor(code: AuthErrorCode) {
    super(code)
    this.code = code
  }
}
