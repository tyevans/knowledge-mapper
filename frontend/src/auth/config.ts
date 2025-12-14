/**
 * OIDC Configuration for Keycloak
 */

export const OIDC_CONFIG = {
  authority: import.meta.env.VITE_OIDC_AUTHORITY || 'http://keycloak.localtest.me:8080/realms/knowledge-mapper-dev',
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID || 'knowledge-mapper-frontend',
  redirect_uri: import.meta.env.VITE_OIDC_REDIRECT_URI || 'http://localhost:5173/auth/callback',
  post_logout_redirect_uri: import.meta.env.VITE_OIDC_POST_LOGOUT_REDIRECT_URI || 'http://localhost:5173',
  response_type: 'code',
  scope: 'openid profile email',
  automaticSilentRenew: true,
  silentRequestTimeoutInSeconds: 10,
} as const
