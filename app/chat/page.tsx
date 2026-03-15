'use client'

import { useState, useRef, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '../context/AuthContext'
import { useChat } from '../context/ChatContext'
import Button from '../components/Button'
import ChatBubble from '../components/ChatBubble'
import { LogOut, Send, MessageSquare, User, AlertCircle, RefreshCw, RotateCcw } from 'lucide-react'

export default function ChatPage() {
  const [inputMessage, setInputMessage] = useState('')
  const [lastFailedMessage, setLastFailedMessage] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  const { user, logout } = useAuth()
  const { 
    conversations, 
    currentConversation, 
    isLoading, 
    error, 
    sendMessage, 
    loadConversations,
    setCurrentConversation,
    clearError 
  } = useChat()
  const router = useRouter()

  useEffect(() => {
    if (!user) {
      router.push('/login')
    }
  }, [user, router])

  useEffect(() => {
    scrollToBottom()
  }, [currentConversation?.messages])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  const handleSendMessage = async (messageText?: string) => {
    const textToSend = messageText || inputMessage
    if (!textToSend.trim() || !user?.id) return

    if (!messageText) {
      setInputMessage('')
    }
    setLastFailedMessage('')
    clearError()

    try {
      await sendMessage(user.id, textToSend)
    } catch (err) {
      setLastFailedMessage(textToSend)
    }
  }

  const handleRetryMessage = () => {
    if (lastFailedMessage) {
      handleSendMessage(lastFailedMessage)
    }
  }

  const handleLogout = () => {
    logout()
    router.push('/login')
  }

  const handleKeyPress = (e: any) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const handleConversationClick = (conversation: any) => {
    setCurrentConversation(conversation)
    clearError()
    setLastFailedMessage('')
  }

  const handleRetry = () => {
    clearError()
    loadConversations()
  }

  if (!user) {
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
    <div className="h-screen bg-secondary flex overflow-hidden">
      {/* Sidebar */}
      <div className="w-80 bg-white border-r border-gray-200 flex flex-col h-full">
        {/* Header */}
        <div className="p-6 border-b border-gray-200 flex-shrink-0">
          <div className="flex items-center space-x-3 mb-4">
            <div className="w-10 h-10 bg-primary rounded-2xl flex items-center justify-center">
              <User className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-900">{user.name}</h3>
              <p className="text-sm text-gray-600">ID: {user.customerId}</p>
            </div>
          </div>
          <Button
            onClick={handleLogout}
            variant="secondary"
            className="w-full flex items-center justify-center space-x-2"
          >
            <LogOut className="w-4 h-4" />
            <span>Logout</span>
          </Button>
        </div>

        {/* Conversations */}
        <div className="flex-1 overflow-y-auto p-4 min-h-0">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-sm font-medium text-gray-700 uppercase tracking-wide">
              Loan Consultations
            </h4>
            <Button
              onClick={handleRetry}
              variant="secondary"
              className="px-2 py-1 text-xs"
              disabled={isLoading}
            >
              <RefreshCw className={`w-3 h-3 ${isLoading ? 'animate-spin' : ''}`} />
            </Button>
          </div>

          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded-2xl text-sm flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              <div className="flex-1">
                <p>{error}</p>
                <button 
                  onClick={handleRetry}
                  className="text-red-800 underline text-xs mt-1"
                >
                  Try again
                </button>
              </div>
            </div>
          )}

          {isLoading && conversations.length === 0 ? (
            <div className="text-center py-8">
              <div className="animate-pulse space-y-2">
                <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                <div className="h-4 bg-gray-200 rounded w-2/3"></div>
              </div>
            </div>
          ) : conversations.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <MessageSquare className="w-12 h-12 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No conversations yet</p>
              <p className="text-xs">Start asking about loans below</p>
            </div>
          ) : (
            <div className="space-y-2">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => handleConversationClick(conv)}
                  className={`p-3 rounded-2xl border cursor-pointer transition-colors ${
                    currentConversation?.id === conv.id
                      ? 'border-primary bg-blue-50'
                      : 'border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-start space-x-3">
                    <MessageSquare className="w-4 h-4 text-primary mt-1 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {conv.title}
                      </p>
                      <p className="text-xs text-gray-600 truncate">
                        {conv.lastMessage}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {new Date(conv.timestamp).toLocaleString()}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col h-full">
        {/* Chat Header */}
        <div className="bg-white border-b border-gray-200 p-6 flex-shrink-0">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 bg-primary rounded-2xl flex items-center justify-center">
              <span className="text-white font-bold text-sm">AB</span>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Loan Advisor</h2>
              <p className="text-sm text-gray-600">
                {currentConversation ? currentConversation.title : 'Ask about loans, applications, and eligibility'}
              </p>
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 min-h-0">
          {currentConversation?.messages.length === 0 || !currentConversation ? (
            <div className="text-center py-12">
              <div className="w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mx-auto mb-4">
                <span className="text-white font-bold text-xl">💰</span>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                Welcome to Arab Bank Loan Advisor
              </h3>
              <p className="text-gray-600 max-w-md mx-auto">
                I'm here to help you with loan applications, check your eligibility, 
                review existing loans, and answer any loan-related questions you may have.
              </p>
              <div className="mt-6 grid grid-cols-1 gap-2 max-w-sm mx-auto">
                <button 
                  onClick={() => handleSendMessage("What are my current loans?")}
                  className="text-left p-2 bg-blue-50 hover:bg-blue-100 rounded-lg text-sm text-blue-700 transition-colors"
                >
                  💳 What are my current loans?
                </button>
                <button 
                  onClick={() => handleSendMessage("Am I eligible for a new loan?")}
                  className="text-left p-2 bg-blue-50 hover:bg-blue-100 rounded-lg text-sm text-blue-700 transition-colors"
                >
                  ✅ Am I eligible for a new loan?
                </button>
                <button 
                  onClick={() => handleSendMessage("What loan types do you offer?")}
                  className="text-left p-2 bg-blue-50 hover:bg-blue-100 rounded-lg text-sm text-blue-700 transition-colors"
                >
                  📋 What loan types do you offer?
                </button>
              </div>
            </div>
          ) : (
            currentConversation.messages.map((message) => (
              <ChatBubble
                key={message.id}
                message={message.text}
                isUser={message.isUser}
                timestamp={message.timestamp}
                decision={message.decision}
                snippets={message.snippets}
              />
            ))
          )}
          
          {isLoading && currentConversation && (
            <div className="flex justify-start">
              <div className="bg-white text-gray-800 rounded-2xl rounded-bl-md p-4 max-w-xs shadow-md border border-gray-100">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                </div>
                <p className="text-xs text-gray-600 mt-2">Analyzing your request...</p>
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        {/* Message Input - Fixed at bottom */}
        <div className="bg-white border-t border-gray-200 p-6 flex-shrink-0">
          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-2xl text-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <div>
                    <p>Failed to send message: {error}</p>
                    {lastFailedMessage && (
                      <p className="text-xs mt-1 text-gray-600">Message: "{lastFailedMessage}"</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  {lastFailedMessage && (
                    <Button
                      onClick={handleRetryMessage}
                      variant="secondary"
                      className="text-xs px-2 py-1 flex items-center space-x-1"
                    >
                      <RotateCcw className="w-3 h-3" />
                      <span>Retry</span>
                    </Button>
                  )}
                  <button 
                    onClick={clearError}
                    className="text-red-800 underline text-xs"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            </div>
          )}
          
          <div className="flex space-x-4">
            <textarea
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask about loans, applications, eligibility..."
              className="flex-1 resize-none input-field min-h-[44px] max-h-32"
              rows={1}
              disabled={isLoading}
            />
            <Button
              onClick={() => handleSendMessage()}
              disabled={!inputMessage.trim() || isLoading}
              className="flex items-center space-x-2"
            >
              <Send className="w-4 h-4" />
              <span>Send</span>
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
} 