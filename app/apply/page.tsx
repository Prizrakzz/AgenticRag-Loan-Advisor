'use client'

import { useSearchParams } from 'next/navigation'
import { Suspense } from 'react'

function ApplicationContent() {
  const searchParams = useSearchParams()
  const product = searchParams.get('product')
  
  const productNames: Record<string, string> = {
    'auto': 'Auto Loan',
    'home': 'Home Loan', 
    'commercial': 'Commercial Loan',
    'personal': 'Personal Loan',
    'realestate': 'Real Estate Loan',
    'refinance': 'Refinancing'
  }
  
  const productName = product ? productNames[product] || 'Loan' : 'Loan'
  
  return (
    <div className="min-h-screen bg-secondary flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        <div className="card text-center">
          <div className="mx-auto w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mb-6">
            <span className="text-white font-bold text-xl">AB</span>
          </div>
          
          <h1 className="text-2xl font-bold text-gray-900 mb-4">
            {productName} Application
          </h1>
          
          <p className="text-gray-600 mb-8">
            Thank you for your interest in our {productName.toLowerCase()}. 
            This application form is coming soon.
          </p>
          
          <div className="space-y-4">
            <div className="bg-green-50 border border-green-200 rounded-2xl p-4">
              <h3 className="font-semibold text-green-800 mb-2">
                What's Next?
              </h3>
              <ul className="text-sm text-green-700 space-y-1">
                <li>• Complete the online application form</li>
                <li>• Upload required documents</li>
                <li>• Get pre-qualification decision</li>
                <li>• Schedule consultation with advisor</li>
              </ul>
            </div>
            
            <a
              href="/chat"
              className="block w-full px-6 py-3 bg-primary text-white font-medium rounded-2xl hover:bg-primary-dark transition-colors duration-200"
            >
              Continue Chatting
            </a>
            
            <a
              href="/"
              className="block w-full px-6 py-3 border border-gray-300 text-gray-700 font-medium rounded-2xl hover:bg-gray-50 transition-colors duration-200"
            >
              Back to Home
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function ApplicationPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-secondary flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-primary border-t-transparent rounded-full"></div>
      </div>
    }>
      <ApplicationContent />
    </Suspense>
  )
}
