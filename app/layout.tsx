import React from 'react'
import './globals.css'
import { AuthProvider } from './context/AuthContext'
import { ChatProvider } from './context/ChatContext'
import { autoClearFromLocation } from './lib/clearState'

export const metadata = {
  title: 'Arab Bank - AI Loan Advisor',
  description: 'Your trusted AI-powered loan advisor',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Client-side effect to optionally clear persisted state
  if (typeof window !== 'undefined') {
    autoClearFromLocation()
  }
  return (
    <html lang="en">
      <body className="antialiased font-sans">
        <AuthProvider>
          <ChatProvider>
            {children}
          </ChatProvider>
        </AuthProvider>
      </body>
    </html>
  )
} 