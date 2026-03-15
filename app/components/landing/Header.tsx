'use client'

import { useState } from 'react'
import { Menu, X, ChevronDown } from 'lucide-react'
import Button from '../Button'

export default function Header() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)

  return (
    <header className="bg-white shadow-sm border-b border-gray-100 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo */}
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="text-2xl font-bold text-arab-navy">
                Arab Bank
                <span className="text-sm font-normal text-arab-green block leading-none">
                  Loan Advisor
                </span>
              </div>
            </div>
          </div>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex space-x-8">
            <a href="#home" className="text-gray-700 hover:text-arab-navy transition-colors">
              Home
            </a>
            <a href="#policy-qa" className="text-gray-700 hover:text-arab-navy transition-colors">
              Policy Q&A
            </a>
            <a href="#apply" className="text-gray-700 hover:text-arab-navy transition-colors">
              Apply Now
            </a>
            <a href="#about" className="text-gray-700 hover:text-arab-navy transition-colors">
              About
            </a>
          </nav>

          {/* Desktop CTA */}
          <div className="hidden md:flex items-center space-x-4">
            <Button
              variant="outline"
              className="border-arab-navy text-arab-navy hover:bg-arab-navy hover:text-white"
              onClick={() => window.location.href = '/login'}
            >
              Login
            </Button>
            <Button 
              className="bg-arab-gold hover:bg-arab-gold-dark text-white"
              onClick={() => window.location.href = '/chat'}
            >
              Get Started
            </Button>
          </div>

          {/* Mobile menu button */}
          <div className="md:hidden">
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="text-gray-700 hover:text-arab-navy"
            >
              {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {isMobileMenuOpen && (
          <div className="md:hidden border-t border-gray-100 py-4">
            <div className="flex flex-col space-y-4">
              <a href="#home" className="text-gray-700 hover:text-arab-navy">
                Home
              </a>
              <a href="#policy-qa" className="text-gray-700 hover:text-arab-navy">
                Policy Q&A
              </a>
              <a href="#apply" className="text-gray-700 hover:text-arab-navy">
                Apply Now
              </a>
              <a href="#about" className="text-gray-700 hover:text-arab-navy">
                About
              </a>
              <div className="pt-4 border-t border-gray-100 space-y-2">
                <Button
                  variant="outline"
                  className="w-full border-arab-navy text-arab-navy"
                >
                  Login
                </Button>
                <Button className="w-full bg-arab-gold hover:bg-arab-gold-dark text-white">
                  Get Started
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </header>
  )
}
