'use client'

import { Facebook, Twitter, Linkedin, Instagram, Mail, Phone, MapPin, ChevronRight } from 'lucide-react'

export default function Footer() {
  const quickLinks = [
    { label: "Home", href: "#home" },
    { label: "Policy Q&A", href: "#policy" },
    { label: "Apply Now", href: "#apply" },
    { label: "About Arab Bank", href: "#about" }
  ]

  const services = [
    { label: "Personal Loans", href: "#personal" },
    { label: "Housing Loans", href: "#housing" },
    { label: "Business Loans", href: "#business" },
    { label: "Credit Cards", href: "#cards" }
  ]

  const support = [
    { label: "Help Center", href: "#help" },
    { label: "Contact Us", href: "#contact" },
    { label: "Privacy Policy", href: "#privacy" },
    { label: "Terms of Service", href: "#terms" }
  ]

  const socialLinks = [
    { icon: <Facebook size={20} />, href: "https://facebook.com/arabbank", label: "Facebook" },
    { icon: <Twitter size={20} />, href: "https://twitter.com/arabbank", label: "Twitter" },
    { icon: <Linkedin size={20} />, href: "https://linkedin.com/company/arab-bank", label: "LinkedIn" },
    { icon: <Instagram size={20} />, href: "https://instagram.com/arabbank", label: "Instagram" }
  ]

  return (
    <footer className="bg-arab-green text-white">
      {/* Main Footer Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="grid lg:grid-cols-4 gap-8">
          {/* Company Info */}
          <div className="lg:col-span-1">
            <div className="mb-6">
              <div className="text-2xl font-bold mb-2">Arab Bank</div>
              <div className="text-lg text-gray-300">Loan Advisor</div>
            </div>
            
            <p className="text-gray-300 mb-6 leading-relaxed">
              Your trusted AI-powered loan advisor, backed by Arab Bank's decades of expertise 
              and commitment to excellence in banking services.
            </p>
            
            {/* Contact Info */}
            <div className="space-y-3">
              <div className="flex items-center space-x-3">
                <Phone size={16} className="text-arab-gold flex-shrink-0" />
                <span className="text-sm">+962 6 560 0000</span>
              </div>
              <div className="flex items-center space-x-3">
                <Mail size={16} className="text-arab-gold flex-shrink-0" />
                <span className="text-sm">advisor@arabbank.jo</span>
              </div>
              <div className="flex items-center space-x-3">
                <MapPin size={16} className="text-arab-gold flex-shrink-0" />
                <span className="text-sm">Amman, Jordan</span>
              </div>
            </div>
          </div>

          {/* Quick Links - Non-functional for CRO */}
          <div>
            <h3 className="font-semibold text-lg mb-4">Quick Links</h3>
            <ul className="space-y-3">
              {quickLinks.map((link, index) => (
                <li key={index}>
                  <span className="text-gray-300 flex items-center pointer-events-none opacity-75">
                    <ChevronRight size={14} className="mr-2 opacity-50" />
                    {link.label}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {/* Services - Non-functional for CRO */}
          <div>
            <h3 className="font-semibold text-lg mb-4">Loan Services</h3>
            <ul className="space-y-3">
              {services.map((service, index) => (
                <li key={index}>
                  <span className="text-gray-300 flex items-center pointer-events-none opacity-75">
                    <ChevronRight size={14} className="mr-2 opacity-50" />
                    {service.label}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          {/* Support & Legal - Non-functional for CRO */}
          <div>
            <h3 className="font-semibold text-lg mb-4">Support & Legal</h3>
            <ul className="space-y-3 mb-6">
              {support.map((item, index) => (
                <li key={index}>
                  <span className="text-gray-300 flex items-center pointer-events-none opacity-75">
                    <ChevronRight size={14} className="mr-2 opacity-50" />
                    {item.label}
                  </span>
                </li>
              ))}
            </ul>

            {/* Social Links - Non-functional for CRO */}
            <div>
              <h4 className="font-medium mb-3">Follow Us</h4>
              <div className="flex space-x-3">
                {socialLinks.map((social, index) => (
                  <span
                    key={index}
                    className="w-10 h-10 bg-white/10 rounded-lg flex items-center justify-center pointer-events-none opacity-75"
                    title={social.label}
                  >
                    {social.icon}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Bar */}
      <div className="border-t border-white/20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex flex-col md:flex-row justify-between items-center">
            <div className="text-sm text-gray-300 mb-4 md:mb-0">
              © 2025 Arab Bank. All rights reserved.
            </div>
            
            <div className="flex items-center space-x-6 text-sm text-gray-300">
              <span className="pointer-events-none opacity-75">Privacy Policy</span>
              <span className="pointer-events-none opacity-75">Terms of Service</span>
              <span className="pointer-events-none opacity-75">Cookie Policy</span>
              <span className="pointer-events-none opacity-75">Accessibility</span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}
