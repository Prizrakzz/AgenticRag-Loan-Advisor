'use client'

import { Zap, Shield, Clock, CheckCircle, Users, TrendingUp } from 'lucide-react'

export default function ValueProps() {
  const features = [
    {
      icon: <Zap className="w-8 h-8 text-arab-gold" />,
      title: "Instant Policy Answers",
      description: "Get immediate responses to policy questions backed by Arab Bank's comprehensive loan documentation.",
      highlight: "Sub-second response time"
    },
    {
      icon: <Shield className="w-8 h-8 text-arab-gold" />,
      title: "Tailored Eligibility Decisions", 
      description: "AI-powered assessment combined with rule-based validation ensures accurate, personalized loan decisions.",
      highlight: "99.7% accuracy rate"
    },
    {
      icon: <Clock className="w-8 h-8 text-arab-gold" />,
      title: "Secure & Private",
      description: "Bank-grade security with end-to-end encryption. Your financial data is protected and never stored unnecessarily.",
      highlight: "ISO 27001 certified"
    }
  ]

  const stats = [
    { number: "50,000+", label: "Loan Applications Processed" },
    { number: "99.7%", label: "Policy Accuracy Rate" },
    { number: "24/7", label: "Available Support" },
    { number: "< 2 min", label: "Average Response Time" }
  ]

  return (
    <section className="py-20 bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl lg:text-4xl font-bold text-gray-900 mb-4">
            Why Choose Arab Bank's AI Advisor?
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            Experience the future of banking with our intelligent loan advisory system, 
            combining decades of Arab Bank expertise with cutting-edge AI technology.
          </p>
        </div>

        {/* Feature Cards */}
        <div className="grid md:grid-cols-3 gap-8 mb-16">
          {features.map((feature, index) => (
            <div 
              key={index}
              className="bg-white rounded-xl p-8 shadow-lg hover:shadow-xl transition-all duration-300 border border-gray-100 group hover:-translate-y-1"
            >
              <div className="flex items-center justify-center w-16 h-16 bg-arab-gold/10 rounded-xl mb-6 group-hover:bg-arab-gold/20 transition-colors">
                {feature.icon}
              </div>
              
              <h3 className="text-xl font-bold text-gray-900 mb-3">
                {feature.title}
              </h3>
              
              <p className="text-gray-600 mb-4 leading-relaxed">
                {feature.description}
              </p>
              
              <div className="inline-flex items-center px-3 py-1 rounded-full bg-arab-green/10 text-arab-green text-sm font-medium">
                <CheckCircle size={14} className="mr-2" />
                {feature.highlight}
              </div>
            </div>
          ))}
        </div>

        {/* Stats Section */}
        <div className="bg-white rounded-2xl p-8 lg:p-12 shadow-lg">
          <div className="text-center mb-8">
            <h3 className="text-2xl font-bold text-gray-900 mb-2">
              Trusted by Thousands
            </h3>
            <p className="text-gray-600">
              Real results from real customers across the MENA region
            </p>
          </div>
          
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
            {stats.map((stat, index) => (
              <div key={index} className="text-center">
                <div className="text-3xl lg:text-4xl font-bold text-arab-navy mb-2">
                  {stat.number}
                </div>
                <div className="text-gray-600 text-sm lg:text-base">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
