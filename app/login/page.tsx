'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../context/AuthContext'
import Button from '../components/Button'
import Input from '../components/Input'

export default function LoginPage() {
  const [customerId, setCustomerId] = useState('')
  const [password, setPassword] = useState('')
  const [isLoggingIn, setIsLoggingIn] = useState(false)
  const [error, setError] = useState('')
  
  const { login, isAuthenticated, isLoading } = useAuth()
  const router = useRouter()

  // Removed auto-redirect logic - users must login each session

  const handleSubmit = async (e: any) => {
    e.preventDefault()
    if (isLoggingIn || !customerId || !password) return

    setIsLoggingIn(true)
    setError('')

    try {
      const success = await login(customerId, password)
      if (success) {
        router.push('/chat')
      } else {
        setError('Invalid customer ID or password. Please check your credentials.')
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Login failed. Please check your connection and try again.'
      setError(errorMessage)
    } finally {
      setIsLoggingIn(false)
    }
  }

  // Show loading spinner if checking authentication
  if (isLoading) {
    return (
      <div className="min-h-screen bg-secondary flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-4 border-primary border-t-transparent rounded-full mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-secondary flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="mx-auto w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mb-4">
            <span className="text-white font-bold text-xl">AB</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Arab Bank</h1>
          <p className="text-gray-600 mt-2">Digital Banking Assistant</p>
        </div>

        {/* Login Form */}
        <div className="card">
          <h2 className="text-xl font-semibold text-gray-900 mb-6 text-center">
            Sign In to Your Account
          </h2>
          
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Customer ID"
              type="text"
              value={customerId}
              onChange={setCustomerId}
              placeholder="Enter your customer ID (e.g., 101)"
              required
            />
            
            <Input
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              placeholder="Enter your password"
              required
            />

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-2xl text-sm">
                {error}
              </div>
            )}

            <Button
              type="submit"
              disabled={isLoggingIn || !customerId || !password}
              className="w-full"
            >
              {isLoggingIn ? (
                <div className="flex items-center justify-center space-x-2">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>Signing In...</span>
                </div>
              ) : (
                'Sign In'
              )}
            </Button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-sm text-gray-600">
              Need help? Contact{' '}
              <span className="text-primary font-medium">Customer Service</span>
            </p>

          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-xs text-gray-500">
          <p>© 2024 Arab Bank. All rights reserved.</p>
          <p className="mt-1">Secured by advanced encryption</p>
        </div>
      </div>
    </div>
  )
} 