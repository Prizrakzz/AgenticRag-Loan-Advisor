'use client'

import { useState } from 'react'
import { Send, Sparkles, FileText, CreditCard } from 'lucide-react'
import Button from '../Button'

interface ChatMessage {
  type: 'user' | 'bot'
  message: string
  timestamp: string
  verified?: boolean
}

export default function ChatDemo() {
  const [selectedPrompt, setSelectedPrompt] = useState<string | null>(null)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      type: 'bot',
      message: "Hello! I'm your Arab Bank loan advisor. I can help you with loan eligibility, policy questions, and application guidance. What would you like to know?",
      timestamp: "Just now"
    }
  ])

  const examplePrompts = [
    {
      icon: <CreditCard className="w-5 h-5" />,
      text: "What are your personal loan interest rates?",
      category: "Rates & Terms"
    },
    {
      icon: <FileText className="w-5 h-5" />,
      text: "Am I eligible for a 50,000 JOD housing loan?",
      category: "Eligibility"
    },
    {
      icon: <Sparkles className="w-5 h-5" />,
      text: "Explain the collateral requirements for business loans",
      category: "Policy Questions"
    }
  ]

  const handlePromptClick = (prompt: string) => {
    setSelectedPrompt(prompt)
    
    // Add user message
    const newUserMessage: ChatMessage = {
      type: 'user',
      message: prompt,
      timestamp: "Just now"
    }
    
    // Simulate bot response
    setTimeout(() => {
      let botResponse = ""
      if (prompt.includes("interest rates")) {
        botResponse = "Our current personal loan rates start from 8.5% APR for qualified customers. Based on Arab Bank policy, rates vary from 8.5% to 12.9% depending on your credit profile and loan amount."
      } else if (prompt.includes("50,000 JOD")) {
        botResponse = "For a 50,000 JOD housing loan, you'll need: minimum 3,000 JOD monthly income, 20% down payment, debt-to-income ratio below 40%, and valid employment history of 2+ years."
      } else {
        botResponse = "For business loans, Arab Bank requires collateral worth 120-150% of the loan amount. Acceptable collateral includes real estate, time deposits, or bank guarantees from qualifying institutions."
      }
      
      const newBotMessage: ChatMessage = {
        type: 'bot',
        message: botResponse,
        timestamp: "Just now",
        verified: true
      }
      
      setChatMessages(prev => [...prev, newUserMessage, newBotMessage])
    }, 1000)
  }

  return (
    <section className="py-20 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Left Column - Content */}
          <div>
            <div className="mb-6">
              <span className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-arab-navy/10 text-arab-navy border border-arab-navy/20">
                <Sparkles size={14} className="mr-2" />
                Live AI Demo
              </span>
            </div>
            
            <h2 className="text-3xl lg:text-4xl font-bold text-gray-900 mb-6">
              Experience Our AI
              <span className="block text-arab-green">Loan Advisor</span>
            </h2>
            
            <p className="text-xl text-gray-600 mb-8 leading-relaxed">
              Try our interactive demo to see how our AI advisor provides instant, 
              accurate responses backed by Arab Bank's comprehensive policy database.
            </p>
            
            {/* Example Prompts */}
            <div className="space-y-4 mb-8">
              <h3 className="font-semibold text-gray-900 mb-4">Try these examples:</h3>
              {examplePrompts.map((prompt, index) => (
                <button
                  key={index}
                  onClick={() => handlePromptClick(prompt.text)}
                  className="w-full text-left p-4 rounded-lg border border-gray-200 hover:border-arab-navy hover:bg-arab-navy/5 transition-all duration-200 group"
                >
                  <div className="flex items-start space-x-3">
                    <div className="flex-shrink-0 text-arab-navy group-hover:text-arab-green transition-colors">
                      {prompt.icon}
                    </div>
                    <div>
                      <p className="font-medium text-gray-900 group-hover:text-arab-navy">
                        {prompt.text}
                      </p>
                      <p className="text-sm text-gray-500 mt-1">
                        {prompt.category}
                      </p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
            
            <div className="flex items-center space-x-4 text-sm text-gray-500">
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-arab-green rounded-full"></div>
                <span>Policy Grounded</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="w-3 h-3 bg-arab-gold rounded-full"></div>
                <span>Real-time Responses</span>
              </div>
            </div>
          </div>
          
          {/* Right Column - Chat Interface */}
          <div className="bg-gray-50 rounded-2xl p-6 shadow-xl border border-gray-100">
            {/* Chat Header */}
            <div className="flex items-center space-x-3 mb-6 pb-4 border-b border-gray-200">
              <div className="w-10 h-10 bg-arab-green rounded-full flex items-center justify-center">
                <span className="text-white font-semibold text-sm">AB</span>
              </div>
              <div>
                <p className="font-semibold text-gray-900">Arab Bank Advisor</p>
                <div className="flex items-center space-x-1">
                  <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                  <p className="text-sm text-gray-500">Online now</p>
                </div>
              </div>
            </div>
            
            {/* Chat Messages */}
            <div className="h-80 overflow-y-auto mb-4 space-y-4">
              {chatMessages.map((msg, index) => (
                <div key={index} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-xs lg:max-w-sm px-4 py-2 rounded-lg ${
                    msg.type === 'user' 
                      ? 'bg-arab-navy text-white' 
                      : 'bg-white border border-gray-200 text-gray-900'
                  }`}>
                    <p className="text-sm leading-relaxed">{msg.message}</p>
                    {msg.verified && (
                      <div className="mt-2 flex items-center space-x-1">
                        <div className="w-1.5 h-1.5 bg-arab-green rounded-full"></div>
                        <span className="text-xs text-arab-green font-medium">Policy Verified</span>
                      </div>
                    )}
                    <p className="text-xs opacity-70 mt-1">{msg.timestamp}</p>
                  </div>
                </div>
              ))}
            </div>
            
            {/* Chat Input */}
            <div className="flex space-x-2">
              <div className="flex-1 relative">
                <input
                  type="text"
                  placeholder="Ask about loans, policies, or eligibility..."
                  className="w-full px-4 py-3 rounded-lg border border-gray-200 focus:ring-2 focus:ring-arab-navy focus:border-transparent text-sm"
                  disabled
                />
              </div>
              <Button className="bg-arab-navy hover:bg-arab-navy/90 p-3">
                <Send size={18} />
              </Button>
            </div>
            
            <p className="text-xs text-gray-500 mt-2 text-center">
              This is a demo. Click examples above to see responses.
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
