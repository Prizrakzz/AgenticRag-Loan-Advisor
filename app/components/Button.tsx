'use client'

interface ButtonProps {
  children: React.ReactNode
  onClick?: () => void
  type?: 'button' | 'submit' | 'reset'
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  className?: string
  disabled?: boolean
}

export default function Button({ 
  children, 
  onClick, 
  type = 'button',
  variant = 'primary',
  size = 'md',
  className = '',
  disabled = false
}: ButtonProps) {
  const getVariantClasses = () => {
    switch (variant) {
      case 'primary':
        return 'bg-arab-navy text-white hover:bg-arab-navy/90 shadow-md hover:shadow-lg'
      case 'secondary':
        return 'bg-arab-green text-white hover:bg-arab-green/90 shadow-md hover:shadow-lg'
      case 'outline':
        return 'border-2 border-current bg-transparent hover:bg-current hover:text-white'
      case 'ghost':
        return 'bg-transparent hover:bg-gray-100'
      default:
        return 'bg-arab-navy text-white hover:bg-arab-navy/90'
    }
  }

  const getSizeClasses = () => {
    switch (size) {
      case 'sm':
        return 'px-3 py-1.5 text-sm'
      case 'lg':
        return 'px-8 py-4 text-lg'
      default:
        return 'px-6 py-2.5 text-base'
    }
  }
  
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`
        ${getVariantClasses()} 
        ${getSizeClasses()}
        rounded-lg font-medium transition-all duration-200 
        flex items-center justify-center
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'hover:scale-105 active:scale-95'} 
        ${className}
      `}
    >
      {children}
    </button>
  )
} 