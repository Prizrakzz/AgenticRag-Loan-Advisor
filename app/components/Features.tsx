'use client'

import { useState } from 'react'
import { ChevronLeft, ChevronRight, Play, Shield, BarChart3, FileCheck } from 'lucide-react'

export default function Features() {
  const [currentSlide, setCurrentSlide] = useState(0)

  const features = [
    {
      title: "Policy Retrieval & Verification",
      description: "Advanced RAG system instantly retrieves relevant policy information from Arab Bank's comprehensive loan documentation, ensuring every response is accurate and up-to-date.",
      highlights: [
        "Real-time policy lookup",
        "Source verification badges",
        "Multi-language support"
      ],
      icon: <FileCheck size={48} className="text-white" />
    },
    {
      title: "Intelligent Eligibility Assessment",
      description: "AI-powered evaluation engine combines rule-based validation with machine learning to provide personalized loan eligibility decisions in seconds.",
      highlights: [
        "99.7% accuracy rate",
        "Instant decision feedback",
        "Detailed explanation of requirements"
      ],
      icon: <BarChart3 size={48} className="text-white" />
    },
    {
      title: "Complete Audit Trail",
      description: "Every interaction is logged and traceable, providing full transparency for compliance and customer service follow-up.",
      highlights: [
        "Full conversation history",
        "Decision reasoning logs",
        "Compliance reporting"
      ],
      icon: <Shield size={48} className="text-white" />
    }
  ]

  const nextSlide = () => {
    setCurrentSlide((prev) => (prev + 1) % features.length)
  }

  const prevSlide = () => {
    setCurrentSlide((prev) => (prev - 1 + features.length) % features.length)
  }

  return (
    <section className="py-20 bg-gradient-to-br from-gray-50 to-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl lg:text-4xl font-bold text-gray-900 mb-4">
            Powerful Features Built for
            <span className="block text-arab-green">Modern Banking</span>
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            Explore the advanced capabilities that make our AI loan advisor 
            the most trusted and comprehensive solution in the market.
          </p>
        </div>

        {/* Feature Carousel */}
        <div className="relative">
          <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
            <div className="grid lg:grid-cols-2 gap-0">
              {/* Content Side */}
              <div className="p-8 lg:p-12 flex flex-col justify-center">
                <div className="mb-6">
                  <div className="flex items-center space-x-2 mb-4">
                    <div className="w-2 h-2 bg-arab-gold rounded-full"></div>
                    <span className="text-sm font-medium text-arab-navy">
                      Feature {currentSlide + 1} of {features.length}
                    </span>
                  </div>
                  
                  <h3 className="text-2xl lg:text-3xl font-bold text-gray-900 mb-4">
                    {features[currentSlide].title}
                  </h3>
                  
                  <p className="text-lg text-gray-600 leading-relaxed mb-6">
                    {features[currentSlide].description}
                  </p>
                </div>

                {/* Highlights */}
                <div className="space-y-3 mb-8">
                  {features[currentSlide].highlights.map((highlight, index) => (
                    <div key={index} className="flex items-center space-x-3">
                      <div className="w-5 h-5 bg-arab-green/20 rounded-full flex items-center justify-center">
                        <div className="w-2 h-2 bg-arab-green rounded-full"></div>
                      </div>
                      <span className="text-gray-700">{highlight}</span>
                    </div>
                  ))}
                </div>

                {/* Navigation Controls */}
                <div className="flex items-center justify-between">
                  <div className="flex space-x-2">
                    <button
                      onClick={prevSlide}
                      className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                      <ChevronLeft size={20} />
                    </button>
                    <button
                      onClick={nextSlide}
                      className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                      <ChevronRight size={20} />
                    </button>
                  </div>
                  
                  <div className="flex space-x-2">
                    {features.map((_, index) => (
                      <button
                        key={index}
                        onClick={() => setCurrentSlide(index)}
                        className={`w-2 h-2 rounded-full transition-colors ${
                          index === currentSlide ? 'bg-arab-navy' : 'bg-gray-300'
                        }`}
                      />
                    ))}
                  </div>
                </div>
              </div>

              {/* Visual Side */}
              <div className="bg-gradient-to-br from-arab-navy to-arab-green p-8 lg:p-12 flex items-center justify-center relative overflow-hidden">
                {/* Background Pattern */}
                <div className="absolute inset-0 opacity-10">
                  <div className="absolute top-1/4 left-1/4 w-32 h-32 bg-white rounded-full blur-xl"></div>
                  <div className="absolute bottom-1/4 right-1/4 w-24 h-24 bg-arab-gold rounded-full blur-xl"></div>
                </div>
                
                {/* Feature Icon */}
                <div className="relative text-center">
                  <div className="w-32 h-32 bg-white/20 rounded-2xl flex items-center justify-center mb-6 backdrop-blur-sm mx-auto">
                    {features[currentSlide].icon}
                  </div>
                  
                  <div>
                    <p className="text-white/90 text-lg font-medium mb-4">
                      Experience the Power
                    </p>
                    <span className="inline-flex items-center justify-center px-6 py-3 border-2 border-white text-white rounded-lg font-medium pointer-events-none opacity-75">
                      <Play size={16} className="mr-2" />
                      Watch Demo
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="mt-16 grid grid-cols-2 lg:grid-cols-4 gap-8">
          <div className="text-center">
            <div className="text-2xl font-bold text-arab-navy mb-1">99.7%</div>
            <div className="text-gray-600 text-sm">Policy Accuracy</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-arab-navy mb-1">&lt; 2s</div>
            <div className="text-gray-600 text-sm">Response Time</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-arab-navy mb-1">24/7</div>
            <div className="text-gray-600 text-sm">Availability</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-arab-navy mb-1">50K+</div>
            <div className="text-gray-600 text-sm">Applications</div>
          </div>
        </div>
      </div>
    </section>
  )
}
