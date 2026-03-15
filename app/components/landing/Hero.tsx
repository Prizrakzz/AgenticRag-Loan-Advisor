'use client'

import { ArrowRight, Shield, Zap, Clock } from 'lucide-react'
import Button from '../Button'

export default function Hero() {
  return (
    <section className="relative bg-gradient-to-br from-arab-navy via-arab-navy/95 to-arab-green overflow-hidden">
      {/* Background Pattern */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-arab-gold rounded-full blur-3xl"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-white rounded-full blur-3xl"></div>
      </div>
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 lg:py-32">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Left Column - Content */}
          <div className="text-white">
            <div className="mb-6">
              <span className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-arab-gold/20 text-arab-gold border border-arab-gold/30">
                <Shield size={14} className="mr-2" />
                Powered by Arab Bank Policy
              </span>
            </div>
            
            <h1 className="text-4xl lg:text-6xl font-bold mb-6 leading-tight">
              Your Personalized
              <span className="block text-arab-gold">Loan Advisor</span>
            </h1>
            
            <p className="text-xl lg:text-2xl mb-8 text-gray-100 leading-relaxed">
              Get instant, accurate loan guidance backed by Arab Bank's comprehensive policy database and advanced AI technology.
            </p>
            
            {/* Value Props */}
            <div className="grid sm:grid-cols-3 gap-4 mb-8">
              <div className="flex items-center space-x-2">
                <Zap size={20} className="text-arab-gold flex-shrink-0" />
                <span className="text-sm">Instant Answers</span>
              </div>
              <div className="flex items-center space-x-2">
                <Shield size={20} className="text-arab-gold flex-shrink-0" />
                <span className="text-sm">Policy Grounded</span>
              </div>
              <div className="flex items-center space-x-2">
                <Clock size={20} className="text-arab-gold flex-shrink-0" />
                <span className="text-sm">24/7 Available</span>
              </div>
            </div>
            
            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row gap-4">
              <Button 
                size="lg"
                className="bg-arab-gold hover:bg-arab-gold-dark text-arab-navy font-semibold group"
                onClick={() => window.location.href = '/chat'}
              >
                Start Consultation
                <ArrowRight size={20} className="ml-2 group-hover:translate-x-1 transition-transform" />
              </Button>
              <Button 
                variant="outline"
                size="lg"
                className="border-white text-white hover:bg-white hover:text-arab-navy"
              >
                View Demo
              </Button>
            </div>
          </div>
          
          {/* Right Column - Chat Preview */}
          <div className="lg:pl-8">
            <div className="bg-white rounded-2xl shadow-2xl p-6 max-w-md mx-auto">
              <div className="flex items-center space-x-3 mb-4 pb-4 border-b border-gray-100">
                <div className="w-10 h-10 bg-arab-green rounded-full flex items-center justify-center">
                  <span className="text-white font-semibold text-sm">AB</span>
                </div>
                <div>
                  <p className="font-semibold text-gray-900">Arab Bank Advisor</p>
                  <p className="text-sm text-gray-500">Online now</p>
                </div>
              </div>
              
              {/* Sample Chat Messages */}
              <div className="space-y-4">
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-lg px-4 py-2 max-w-xs">
                    <p className="text-sm text-gray-800">
                      Hello! I can help you with loan eligibility, policy questions, and application guidance. What would you like to know?
                    </p>
                  </div>
                </div>
                
                <div className="flex justify-end">
                  <div className="bg-arab-navy text-white rounded-lg px-4 py-2 max-w-xs">
                    <p className="text-sm">
                      What are the requirements for a 50,000 JOD housing loan?
                    </p>
                  </div>
                </div>
                
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-lg px-4 py-2 max-w-xs">
                    <p className="text-sm text-gray-800">
                      Based on Arab Bank policy, for a 50,000 JOD housing loan you'll need...
                    </p>
                    <div className="mt-2 p-2 bg-arab-green/10 rounded border-l-2 border-arab-green">
                      <p className="text-xs text-arab-green font-semibold">✓ Policy Verified</p>
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Typing Indicator */}
              <div className="flex justify-start mt-4">
                <div className="bg-gray-100 rounded-lg px-4 py-2 flex items-center space-x-1">
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
