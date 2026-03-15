'use client'

import { useRouter } from 'next/navigation'
import HomeHero from './components/HomeHero'
import ValueProps from './components/ValueProps'
import ChatDemo from './components/ChatDemo'
import Features from './components/Features'
import Testimonials from './components/Testimonials'
import Footer from './components/Footer'

export default function HomePage() {
  const router = useRouter()

  const handleLoginClick = () => {
    router.push('/login')
  }

  return (
    <div className="min-h-screen bg-white">
      <HomeHero onLoginClick={handleLoginClick} />
      <ValueProps />
      <ChatDemo />
      <Features />
      <Testimonials />
      <Footer />
    </div>
  )
} 