import typography from '@tailwindcss/typography'
import tailwindcssAnimate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
          950: '#082f49',
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
          950: '#020617',
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      backgroundColor: {
        'dark': {
          800: '#1e293b',
          900: '#0f172a',
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['Fira Code', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'Liberation Mono', 'Courier New', 'monospace'],
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
      typography: (theme) => ({
        DEFAULT: {
          css: {
            maxWidth: 'none',
            color: theme('colors.foreground.DEFAULT', theme('colors.gray.700')),
            a: {
              color: theme('colors.primary.DEFAULT', theme('colors.primary.500')),
              '&:hover': {
                color: theme('colors.primary.600'),
              },
            },
            img: {
              marginTop: '1.5rem',
              marginBottom: '1.5rem',
              borderRadius: theme('borderRadius.lg'),
            },
            h1: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.900')),
              fontWeight: '700',
              fontSize: theme('fontSize.3xl[0]'),
              marginTop: '1.5rem',
              marginBottom: '1rem',
            },
            h2: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.900')),
              fontWeight: '600',
              fontSize: theme('fontSize.2xl[0]'),
              marginTop: '2rem',
              marginBottom: '1rem',
            },
            h3: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.900')),
              fontWeight: '500',
              fontSize: theme('fontSize.xl[0]'),
              marginTop: '1.5rem',
              marginBottom: '0.75rem',
            },
            code: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.700')),
              backgroundColor: theme('colors.muted.DEFAULT', theme('colors.gray.100')),
              borderRadius: theme('borderRadius.md'),
              padding: '0.25rem 0.5rem',
              fontSize: '0.875rem',
              fontFamily: theme('fontFamily.mono'),
            },
            'code::before': {
              content: '""',
            },
            'code::after': {
              content: '""',
            },
            pre: {
              backgroundColor: theme('colors.muted.DEFAULT', theme('colors.gray.100')),
              borderRadius: theme('borderRadius.md'),
              padding: '1rem',
              overflowX: 'auto',
            },
            'pre code': {
              backgroundColor: 'transparent',
              padding: '0',
            },
            ul: {
              listStyleType: 'disc',
              paddingLeft: '1.5rem',
              marginTop: '1rem',
              marginBottom: '1rem',
            },
            ol: {
              listStyleType: 'decimal',
              paddingLeft: '1.5rem',
              marginTop: '1rem',
              marginBottom: '1rem',
            },
            li: {
              marginTop: '0.5rem',
              marginBottom: '0.5rem',
            },
          },
        },
        dark: {
          css: {
            color: theme('colors.foreground.DEFAULT', theme('colors.gray.300')),
            a: {
              color: theme('colors.primary.DEFAULT', theme('colors.primary.400')),
              '&:hover': {
                color: theme('colors.primary.300'),
              },
            },
            h1: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.100')),
            },
            h2: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.100')),
            },
            h3: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.100')),
            },
            h4: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.100')),
            },
            code: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.300')),
              backgroundColor: theme('colors.muted.DEFAULT', theme('colors.gray.800')),
            },
            pre: {
              backgroundColor: theme('colors.muted.DEFAULT', theme('colors.gray.800')),
            },
            strong: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.300')),
            },
            blockquote: {
              color: theme('colors.foreground.DEFAULT', theme('colors.gray.400')),
            },
          },
        },
      }),
    },
  },
  plugins: [typography, tailwindcssAnimate],
} 