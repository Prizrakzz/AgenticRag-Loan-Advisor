'use client'

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { API_URL, apiHeaders } from '../lib/config'

interface User {
  id: string
  customerId: string
  name: string
  token: string
}

interface AuthContextType {
  user: User | null
  login: (customerId: string, password: string) => Promise<boolean>
  logout: () => void
  isAuthenticated: boolean
  isLoading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(false) // Changed from true to false

  // Removed auto-login on mount - users must explicitly login each session
  // Token is kept in localStorage only for API headers, not for auto-authentication

  const login = async (customerId: string, password: string): Promise<boolean> => {
    try {
      setIsLoading(true)
      
      const requestPayload = { user_id: customerId, password }
      
      const response = await fetch(`${API_URL}/v1/auth/login`, {
        method: 'POST',
        headers: apiHeaders(),
        body: JSON.stringify(requestPayload)
      })

      if (!response.ok) {
        const errorText = await response.text()
        const errorData = JSON.parse(errorText || '{}')
        throw new Error(errorData.detail || 'Login failed')
      }

      const responseData = await response.json()
      
      const { access_token } = responseData
      
      const userData: User = {
        id: customerId,
        customerId,
        name: 'Valued Customer',
        token: access_token
      }

      // Store in localStorage
      localStorage.setItem('token', access_token)
      localStorage.setItem('user', JSON.stringify({
        id: customerId,
        customerId,
        name: 'Valued Customer'
      }))

      setUser(userData)
      return true
    } catch (error) {
      return false
    } finally {
      setIsLoading(false)
    }
  }

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setUser(null)
  }

  const isAuthenticated = !!user?.token

  return (
    <AuthContext.Provider value={{ user, login, logout, isAuthenticated, isLoading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
} 