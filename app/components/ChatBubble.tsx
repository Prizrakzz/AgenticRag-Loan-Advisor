'use client'

interface QuickReply {
  label: string
  value: string
}

interface CTA {
  label: string
  url: string
}

interface ChatBubbleProps {
  message: string
  isUser: boolean
  timestamp?: string
  decision?: string
  snippets?: string[]
  quick_replies?: QuickReply[]
  cta?: CTA
  onQuickReply?: (value: string) => void
}

export default function ChatBubble({ 
  message, 
  isUser, 
  timestamp, 
  decision, 
  snippets, 
  quick_replies,
  cta,
  onQuickReply 
}: ChatBubbleProps) {
  
  // Format message with context echo styling
  const formatMessage = (text: string) => {
    // Split by bold markers and italicize "As we discussed" sections
    const parts = text.split(/(\*\*As we discussed:\*\*[^*]+)/g)
    
    return parts.map((part, index) => {
      if (part.startsWith('**As we discussed:**')) {
        const content = part.replace(/\*\*/g, '')
        return (
          <span key={index} className="italic text-gray-600 block mb-2">
            {content}
          </span>
        )
      }
      return part
    })
  }
  
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={isUser ? 'chat-bubble-user' : 'chat-bubble-bot'}>
        <div className="text-sm whitespace-pre-wrap">
          {formatMessage(message)}
        </div>
        
        {/* Show decision if available (for loan responses) */}
        {decision && decision !== message && (
          <div className="mt-2 p-2 bg-blue-50 rounded-lg border-l-4 border-blue-400">
            <p className="text-xs font-semibold text-blue-800">Decision:</p>
            <p className="text-sm text-blue-700">{decision}</p>
          </div>
        )}
        
        {/* Quick Reply Buttons */}
        {!isUser && quick_replies && quick_replies.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {quick_replies.map((reply, index) => (
              <button
                key={index}
                onClick={() => onQuickReply?.(reply.value)}
                className="px-3 py-1 text-xs bg-blue-100 hover:bg-blue-200 text-blue-800 rounded-full border border-blue-300 transition-colors duration-200"
              >
                {reply.label}
              </button>
            ))}
          </div>
        )}
        
        {/* Call-to-Action Button */}
        {!isUser && cta && (
          <div className="mt-3">
            <a
              href={cta.url}
              className="inline-block px-4 py-2 bg-primary text-white text-sm font-medium rounded-lg hover:bg-primary-dark transition-colors duration-200"
            >
              {cta.label}
            </a>
          </div>
        )}
        
        {/* Show snippets if available */}
        {snippets && snippets.length > 0 && (
          <div className="mt-2 space-y-1">
            <p className="text-xs font-semibold text-gray-600">Related Information:</p>
            {snippets.map((snippet, index) => (
              <div key={index} className="p-2 bg-gray-50 rounded text-xs text-gray-700 border-l-2 border-gray-300">
                {snippet}
              </div>
            ))}
          </div>
        )}
        
        {timestamp && (
          <p className="text-xs opacity-70 mt-2">{timestamp}</p>
        )}
      </div>
    </div>
  )
} 