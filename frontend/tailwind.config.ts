import type { Config } from "tailwindcss";

const config: Config = {
    content: [
        "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    darkMode: ["class", "class"],
    theme: {
    	extend: {
    		colors: {
    			// ── App backgrounds (landing space palette) ──
    			nav:       '#000000',
    			surface:   '#121426',
    			raised:    '#16171a',
    			overlay:   '#0d0e14',

    			// ── Accents (landing page brand) ──
    			primary:   '#8aa5ff',
    			accent:    '#2934ff',
    			cta:       '#854dff',
    			glow:      '#a3b9ff',

    			// ── Semantic (data / badges only) ──
    			success:   '#34d399',
    			warning:   '#fbbf24',
    			error:     '#f87171',
    			info:      '#60a5fa',

    			// ── Glass tokens ──
    			'glass':                'rgba(18, 20, 38, 0.92)',
    			'glass-hover':          'rgba(22, 23, 38, 0.96)',
    			'glass-border':         'rgba(138, 165, 255, 0.09)',
    			'glass-border-strong':  'rgba(138, 165, 255, 0.18)',

    			// ── Keep HSL-based shadcn-ish tokens so dark: classes still work ──
    			background: 'hsl(var(--background))',
    			foreground: 'hsl(var(--foreground))',
    			card: {
    				DEFAULT: 'hsl(var(--card))',
    				foreground: 'hsl(var(--card-foreground))'
    			},
    			popover: {
    				DEFAULT: 'hsl(var(--popover))',
    				foreground: 'hsl(var(--popover-foreground))'
    			},
    			primaryHsl: {
    				DEFAULT: 'hsl(var(--primary))',
    				foreground: 'hsl(var(--primary-foreground))'
    			},
    			secondary: {
    				DEFAULT: 'hsl(var(--secondary))',
    				foreground: 'hsl(var(--secondary-foreground))'
    			},
    			muted: {
    				DEFAULT: 'hsl(var(--muted))',
    				foreground: 'hsl(var(--muted-foreground))'
    			},
    			accentHsl: {
    				DEFAULT: 'hsl(var(--accent))',
    				foreground: 'hsl(var(--accent-foreground))'
    			},
    			destructive: {
    				DEFAULT: 'hsl(var(--destructive))',
    				foreground: 'hsl(var(--destructive-foreground))'
    			},
    			border: 'hsl(var(--border))',
    			input: 'hsl(var(--input))',
    			ring: 'hsl(var(--ring))',
    		},
    		fontFamily: {
    			sans: [
    				'Inter',
    				'system-ui',
    				'sans-serif'
    			],
    			mono: [
    				'JetBrains Mono',
    				'Menlo',
    				'monospace'
    			]
    		},
    		spacing: {
    			'18': '4.5rem',
    			'22': '5.5rem'
    		},
    		borderRadius: {
    			card: '8px',
    			badge: '4px',
    			modal: '12px',
    			lg: 'var(--radius)',
    			md: 'calc(var(--radius) - 2px)',
    			sm: 'calc(var(--radius) - 4px)'
    		},
    		boxShadow: {
    			glass: '0 8px 40px rgba(0,0,0,0.60)',
    			'glass-lg': '0 24px 80px rgba(0,0,0,0.75)',
    			'glow-blue': '0 0 24px rgba(138, 165, 255, 0.25)',
    			'glow-electric': '0 0 24px rgba(41, 52, 255, 0.30)',
    			'glow-purple': '0 0 24px rgba(133, 77, 255, 0.25)',
    			'glow-green': '0 0 20px rgba(52, 211, 153, 0.18)',
    			'glow-amber': '0 0 20px rgba(251, 191, 36, 0.18)',
    			'glow-red': '0 0 20px rgba(248, 113, 113, 0.18)'
    		},
    		animation: {
    			'pulse-slow': 'pulse 3s ease-in-out infinite',
    			shimmer: 'shimmer 2s linear infinite',
    			'slide-in-right': 'slide-in-right 0.3s cubic-bezier(0.16,1,0.3,1) forwards'
    		},
    		backgroundImage: {
    			'brand-gradient': 'linear-gradient(135deg, #8aa5ff, #2934ff, #854dff)',
    			'blue-gradient': 'linear-gradient(135deg, #031457, #2934ff)',
    			'glass-gradient': 'linear-gradient(135deg, rgba(138,165,255,0.06) 0%, rgba(138,165,255,0.02) 100%)',
    		}
    	}
    },
    plugins: [require("tailwindcss-animate")],
};

export default config;
