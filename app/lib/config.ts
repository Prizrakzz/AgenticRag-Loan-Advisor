export const API_URL = process.env.NEXT_PUBLIC_API_URL || '/api'

export const apiHeaders = (token?: string) => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  
  return headers
} 