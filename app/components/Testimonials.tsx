'use client'

import { Star, Quote } from 'lucide-react'

export default function Testimonials() {
  const testimonials = [
    {
      name: "Ahmed Al-Rashid",
      role: "Business Owner",
      company: "Tech Solutions Jordan",
      rating: 5,
      text: "The AI advisor helped me understand Arab Bank's business loan requirements instantly. The process was smooth and the information was exactly what I needed.",
      avatar: "AR"
    },
    {
      name: "Fatima Hassan", 
      role: "First-time Home Buyer",
      company: "Amman, Jordan",
      rating: 5,
      text: "As someone new to loans, the advisor explained everything clearly. I got my housing loan approved faster than I expected thanks to the guidance.",
      avatar: "FH"
    },
    {
      name: "Omar Khalil",
      role: "SME Owner", 
      company: "Khalil Trading",
      rating: 5,
      text: "The policy answers were accurate and saved me multiple branch visits. Arab Bank's digital innovation makes banking so much easier.",
      avatar: "OK"
    }
  ]

  const trustBadges = [
    { name: "Arab Bank", desc: "Official Partner" },
    { name: "Central Bank of Jordan", desc: "Regulated Institution" },
    { name: "ISO 27001", desc: "Security Certified" },
    { name: "PCI DSS", desc: "Payment Security" }
  ]

  return (
    <section className="py-20 bg-arab-navy">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl lg:text-4xl font-bold text-white mb-4">
            Trusted by Thousands
            <span className="block text-arab-gold">Across the MENA Region</span>
          </h2>
          <p className="text-xl text-gray-300 max-w-3xl mx-auto">
            See what our customers say about their experience with Arab Bank's AI loan advisor.
          </p>
        </div>

        {/* Testimonials Grid */}
        <div className="grid md:grid-cols-3 gap-8 mb-16">
          {testimonials.map((testimonial, index) => (
            <div key={index} className="bg-white rounded-xl p-8 shadow-lg relative">
              {/* Quote Icon */}
              <div className="absolute -top-4 left-8">
                <div className="w-8 h-8 bg-arab-gold rounded-full flex items-center justify-center">
                  <Quote size={16} className="text-white" />
                </div>
              </div>
              
              {/* Rating */}
              <div className="flex items-center space-x-1 mb-4 pt-4">
                {[...Array(testimonial.rating)].map((_, i) => (
                  <Star key={i} size={16} className="text-arab-gold fill-current" />
                ))}
              </div>
              
              {/* Testimonial Text */}
              <p className="text-gray-700 mb-6 leading-relaxed">
                "{testimonial.text}"
              </p>
              
              {/* Author */}
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 rounded-full bg-arab-navy flex items-center justify-center">
                  <span className="text-white font-semibold text-sm">{testimonial.avatar}</span>
                </div>
                <div>
                  <p className="font-semibold text-gray-900">{testimonial.name}</p>
                  <p className="text-sm text-gray-600">{testimonial.role}</p>
                  <p className="text-sm text-gray-500">{testimonial.company}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Trust Badges */}
        <div className="border-t border-white/20 pt-12">
          <div className="text-center mb-8">
            <p className="text-lg text-gray-300 font-medium">
              Certified and Trusted by Leading Institutions
            </p>
          </div>
          
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 items-center">
            {trustBadges.map((badge, index) => (
              <div key={index} className="text-center">
                <div className="bg-white/10 rounded-lg p-6 backdrop-blur-sm">
                  <div className="h-8 bg-white/20 rounded mb-3 flex items-center justify-center">
                    <span className="text-white font-semibold text-sm">{badge.name}</span>
                  </div>
                  <p className="text-sm text-gray-300">{badge.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Security Notice */}
        <div className="mt-12 text-center">
          <div className="inline-flex items-center space-x-2 px-4 py-2 bg-white/10 rounded-full backdrop-blur-sm">
            <div className="w-2 h-2 bg-green-400 rounded-full"></div>
            <span className="text-sm text-gray-300">
              Bank-grade security • End-to-end encryption • GDPR compliant
            </span>
          </div>
        </div>
      </div>
    </section>
  )
}
