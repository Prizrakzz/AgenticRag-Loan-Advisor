'use client'

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useAuth } from './AuthContext'
import { API_URL, apiHeaders } from '../lib/config'

interface Message {
  id: string
  text: string
  isUser: boolean
  timestamp: string
  decision?: string
  snippets?: string[]
}

interface Conversation {
  id: string
  title: string
  lastMessage: string
  timestamp: string
  messages: Message[]
}

interface ChatContextType {
  conversations: Conversation[]
  currentConversation: Conversation | null
  isLoading: boolean
  error: string | null
  sendMessage: (clientId: string, text: string) => Promise<void>
  loadConversations: () => Promise<void>
  setCurrentConversation: (conversation: Conversation | null) => void
  clearError: () => void
}

const ChatContext = createContext<ChatContextType | undefined>(undefined)

export function ChatProvider({ children }: { children: ReactNode }) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { user } = useAuth()

  const loadConversations = async () => {
    if (!user) return

    // Get token from localStorage for API calls (not for auth state)
    const token = localStorage.getItem('token')
    if (!token) return

    try {
      setIsLoading(true)
      setError(null)
      
      // Stub the conversation list for now since backend doesn't have this endpoint
      // In the future, this would call: GET ${API_URL}/v1/chat/list
      
      // Return empty array for now
      setConversations([])
      
      // Create a default conversation if none exists
      if (conversations.length === 0) {
        const defaultConversation: Conversation = {
          id: 'default',
          title: 'Loan Consultation',
          lastMessage: 'Welcome! Ask me about loans, applications, or your account.',
          timestamp: new Date().toISOString(),
          messages: [
            {
              id: 'welcome',
              text: 'Hello! I\'m your loan advisor. I can help you with loan applications, check your eligibility, or answer questions about your existing loans. What would you like to know?',
              isUser: false,
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            }
          ]
        }
        setConversations([defaultConversation])
        setCurrentConversation(defaultConversation)
      }

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversations')
    } finally {
      setIsLoading(false)
    }
  }

  const sendMessage = async (clientId: string, text: string) => {
    if (!user || !text.trim()) return

    // Get token from localStorage for API calls (not for auth state)
    const token = localStorage.getItem('token')
    if (!token) return

    try {
      setIsLoading(true)
      setError(null)

      // Call the loan decision endpoint
      const response = await fetch(`${API_URL.replace(/\/$/, '')}/v1/decision`, {
        method: 'POST',
        headers: apiHeaders(token),
        body: JSON.stringify({
          client_id: Number(clientId),
          question: text,
          autonomous: true
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `Server error: ${response.status}`)
      }

      const result = await response.json()
      
      // Create user message
      const userMessage: Message = {
        id: Date.now().toString(),
        text: text,
        isUser: true,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }

      // Create bot response message from loan decision result
      const botText = result.explanation || result.answer || result.message || result.decision || 'No answer returned.'
      
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: botText,
        isUser: false,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        decision: result.decision,
        snippets: result.snippets
      }

      // Update current conversation with new messages
      if (currentConversation) {
        const updatedConversation = {
          ...currentConversation,
          messages: [...currentConversation.messages, userMessage, botMessage],
          lastMessage: botMessage.text,
          timestamp: new Date().toISOString()
        }
        
        setCurrentConversation(updatedConversation)
        
        // Update conversations list
        setConversations(prev => 
          prev.map(conv => 
            conv.id === currentConversation.id ? updatedConversation : conv
          )
        )
      } else {
        // Create new conversation if none exists
        const newConversation: Conversation = {
          id: Date.now().toString(),
          title: text.substring(0, 30) + (text.length > 30 ? '...' : ''),
          lastMessage: botMessage.text,
          timestamp: new Date().toISOString(),
          messages: [userMessage, botMessage]
        }
        
        setCurrentConversation(newConversation)
        setConversations([newConversation])
      }

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send message')
      
      // Still add the user message even if the API call failed
      if (currentConversation) {
        const userMessage: Message = {
          id: Date.now().toString(),
          text: text,
          isUser: true,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
        
        const updatedConversation = {
          ...currentConversation,
          messages: [...currentConversation.messages, userMessage],
          lastMessage: text,
          timestamp: new Date().toISOString()
        }
        
        setCurrentConversation(updatedConversation)
        setConversations(prev => 
          prev.map(conv => 
            conv.id === currentConversation.id ? updatedConversation : conv
          )
        )
      }
    } finally {
      setIsLoading(false)
    }
  }

  const clearError = () => setError(null)

  // Load conversations when user changes
  useEffect(() => {
    if (user?.token) {
      loadConversations()
    } else {
      setConversations([])
      setCurrentConversation(null)
    }
  }, [user?.token])

  return (
    <ChatContext.Provider value={{
      conversations,
      currentConversation,
      isLoading,
      error,
      sendMessage,
      loadConversations,
      setCurrentConversation,
      clearError
    }}>
      {children}
    </ChatContext.Provider>
  )
}

export function useChat() {
  const context = useContext(ChatContext)
  if (context === undefined) {
    throw new Error('useChat must be used within a ChatProvider')
  }
  return context
} 