'use client'

import { useState } from 'react'
import { Sparkles, FileText, CreditCard } from 'lucide-react'
import ChatBubble from './ChatBubble'

interface QuickReply {
  label: string
  value: string
}

interface CTA {
  label: string
  url: string
}

interface ChatMessage {
  type: 'user' | 'bot'
  message: string
  timestamp: string
  verified?: boolean
  quick_replies?: QuickReply[]
  cta?: CTA
}

export default function ChatDemo() {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      type: 'bot',
      message: "Hello! I'm your Arab Bank loan advisor. I can help you with loan eligibility, policy questions, and application guidance. What would you like to know?",
      timestamp: "Just now",
      quick_replies: [
        { label: "Auto Loans", value: "tell me about auto loans" },
        { label: "Home Loans", value: "tell me about home loans" },
        { label: "Business Loans", value: "tell me about business loans" }
      ]
    }
  ])

  const examplePrompts = [
    {
      icon: <CreditCard className="w-5 h-5" />,
      text: "What are your personal loan interest rates?",
      category: "Rates & Terms",
      response: "I understand you're interested in a Personal Loan—let's get you the details you need.\n\nOur current personal loan rates start from 8.5% APR for qualified customers. Based on Arab Bank policy, rates vary from 8.5% to 12.9% depending on your credit profile and loan amount.\n\n**Typical Requirements:**\n• Valid photo ID\n• Proof of income (pay stubs or tax returns)\n• Employment verification\n• Bank statements (2-3 months)\n• Credit score of 600+ (preferred)",
      quick_replies: [
        { label: "Check My Eligibility", value: "am I eligible for a personal loan" },
        { label: "Calculate Payment", value: "help me calculate loan payments" },
        { label: "Apply Now", value: "I want to apply for a personal loan" }
      ],
      cta: { label: "Start Personal Loan Application", url: "/apply?product=personal" }
    },
    {
      icon: <FileText className="w-5 h-5" />,
      text: "Am I eligible for a 50,000 JOD housing loan?",
      category: "Eligibility", 
      response: "I understand you're interested in a Home Loan—let's get you the details you need.\n\nFor a 50,000 JOD housing loan, you'll need: minimum 3,000 JOD monthly income, 20% down payment, debt-to-income ratio below 40%, and valid employment history of 2+ years.\n\n**Typical Requirements:**\n• Credit score of 620+ (varies by program)\n• Proof of income (2 years tax returns, pay stubs)\n• Employment verification\n• Down payment (3-20% depending on loan type)\n• Home appraisal\n• Property inspection\n• Homeowner's insurance",
      quick_replies: [
        { label: "Pre-qualification", value: "can I get pre-qualified" },
        { label: "Document List", value: "what documents do I need" },
        { label: "Timeline", value: "how long does approval take" }
      ],
      cta: { label: "Start Home Loan Application", url: "/apply?product=home" }
    },
    {
      icon: <Sparkles className="w-5 h-5" />,
      text: "What loans do you offer?",
      category: "General Inquiry",
      response: "Thank you for reaching out to Arab Bank. I'm here to assist you with your loan inquiry.\n\nJust to confirm, are you looking for information about a specific type of loan—is that correct? I can help you explore your options.",
      quick_replies: [
        { label: "Auto Loan", value: "car loan" },
        { label: "Home Loan", value: "home mortgage" },
        { label: "Commercial Loan", value: "business loan" },
        { label: "Personal Loan", value: "personal loan" },
        { label: "Refinancing", value: "refinance options" }
      ]
    }
  ]

  const handlePromptClick = (prompt: typeof examplePrompts[0]) => {
    const newUserMessage: ChatMessage = {
      type: 'user',
      message: prompt.text,
      timestamp: "Just now"
    }
    
    setChatMessages(prev => [...prev, newUserMessage])
    
    setTimeout(() => {
      const newBotMessage: ChatMessage = {
        type: 'bot',
        message: prompt.response,
        timestamp: "Just now",
        verified: true,
        quick_replies: prompt.quick_replies,
        cta: prompt.cta
      }
      
      setChatMessages(prev => [...prev, newBotMessage])
    }, 800)
  }

  const handleQuickReply = (value: string) => {
    const newUserMessage: ChatMessage = {
      type: 'user',
      message: value,
      timestamp: "Just now"
    }
    
    setChatMessages(prev => [...prev, newUserMessage])
    
    // Simulate a response
    setTimeout(() => {
      const response = `I understand you're asking about "${value}". Let me help you with that specific information.`
      
      const newBotMessage: ChatMessage = {
        type: 'bot',
        message: response,
        timestamp: "Just now",
        verified: true
      }
      
      setChatMessages(prev => [...prev, newBotMessage])
    }, 600)
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
                Interactive AI Demo
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
            
            {/* Example Prompts - Clickable for demo */}
            <div className="space-y-4 mb-8">
              <h3 className="font-semibold text-gray-900 mb-4">Try these examples:</h3>
              {examplePrompts.map((prompt, index) => (
                <button
                  key={index}
                  onClick={() => handlePromptClick(prompt)}
                  className="w-full text-left p-4 rounded-lg border border-gray-200 hover:border-arab-navy hover:bg-arab-navy/5 transition-all duration-200 group cursor-pointer"
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
                <ChatBubble
                  key={index}
                  message={msg.message}
                  isUser={msg.type === 'user'}
                  timestamp={msg.timestamp}
                  quick_replies={msg.quick_replies}
                  cta={msg.cta}
                  onQuickReply={handleQuickReply}
                />
              ))}
            </div>
            
            {/* Chat Input - Non-functional for demo */}
            <div className="flex space-x-2">
              <div className="flex-1 relative">
                <input
                  type="text"
                  placeholder="Ask about loans, policies, or eligibility..."
                  className="w-full px-4 py-3 rounded-lg border border-gray-200 text-sm pointer-events-none opacity-75"
                  disabled
                />
              </div>
              <span className="inline-flex items-center justify-center px-4 py-3 bg-arab-navy/75 text-white rounded-lg pointer-events-none">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </span>
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
