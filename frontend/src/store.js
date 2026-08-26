import { reactive } from 'vue'

export const session = reactive({
  user: null,
  loaded: false,
})

export function isAdmin() {
  return session.user && session.user.role === 'admin'
}

export function displayName(user) {
  if (!user) return ''
  return user.real_name || user.username
}
