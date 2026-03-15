// Utility to clear frontend persisted state (token, user, conversations) when invoked.
export function clearPersistedState() {
  try {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
  } catch (e) {
    // localStorage may be unavailable in some browsers
  }
}

// Auto-clear only via explicit user action (removed ?clear=1 URL param for security)
export function autoClearFromLocation() {
  // Intentionally disabled — clearing state via URL parameter is a logout-via-link vulnerability.
  // Use clearPersistedState() programmatically when needed.
}
