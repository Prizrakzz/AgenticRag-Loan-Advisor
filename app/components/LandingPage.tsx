'use client'

import Header from './landing/Header'
import Hero from './landing/Hero'
import ValueProps from './landing/ValueProps'
import ChatDemo from './landing/ChatDemo'
import Features from './landing/Features'
import Testimonials from './landing/Testimonials'
import Footer from './landing/Footer'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white">
      <Header />
      <main>
        <Hero />
        <ValueProps />
        <ChatDemo />
        <Features />
        <Testimonials />
      </main>
      <Footer />
    </div>
  )
}
