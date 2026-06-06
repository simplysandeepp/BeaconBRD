/* ─── COMMENTED OUT ───
   The original Next.js landing page (Beacon custom React component) has been
   disabled. The main landing page is now the static HTML file at:
   /public/landing.html  (originally from frontend/beacon/)

   To restore: uncomment the original code below and remove the redirect.

   Original file was a "use client" component with:
   - Lamp beam hero effect
   - Floating terminal/signal/BRD cards
   - Pipeline architecture visualization
   - Feature cards, tech stack, footer
   - All using framer-motion, lucide-react, next/link

[Full original code preserved in git history]

import Link from 'next/link';
import { ArrowRight, Zap, Shield, Check, FileText, GitBranch,
    Search, Database, Filter, Brain, Download, ChevronRight,
    Github, Mail, ExternalLink } from 'lucide-react';
import { motion, useScroll, useTransform } from 'framer-motion';
import { useRef, useState, useCallback, useEffect } from 'react';
import { LampContainer } from '@/components/ui/lamp';
// ... (full original component code preserved in git history)
*/

import { redirect } from 'next/navigation';

export default function HomePage() {
    redirect('/landing.html');
}
