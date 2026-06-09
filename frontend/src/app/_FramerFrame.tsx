"use client";

import { useEffect, useRef } from "react";

/**
 * FramerFrame — renders the Framer landing page inside a full-viewport iframe.
 *
 * This component is dynamically imported with `ssr: false` from page.tsx
 * to prevent hydration mismatches when the Next.js app is embedded in an
 * iframe on the Framer hosting page.
 *
 * On load, it injects <base target="_top"> into the iframe's <head> so that
 * all links (Login, Register, etc.) navigate the top-level window instead of
 * navigating inside the iframe. This also ensures Slack/Gmail OAuth flows
 * escape the iframe and are not blocked by X-Frame-Options.
 */
export default function FramerFrame() {
    const iframeRef = useRef<HTMLIFrameElement>(null);

    useEffect(() => {
        const iframe = iframeRef.current;
        if (!iframe) return;

        const injectBaseTarget = () => {
            try {
                const doc = iframe.contentDocument || iframe.contentWindow?.document;
                if (!doc) return;

                // Remove any existing <base> to avoid duplicates on re-inject
                const existing = doc.querySelector("base");
                if (existing) existing.remove();

                // Inject <base target="_top"> so ALL links (Login, Register, etc.)
                // navigate the top-level window instead of inside the iframe.
                // This also ensures Slack/Gmail OAuth flows escape the iframe
                // and are not blocked by X-Frame-Options: sameorigin.
                const base = doc.createElement("base");
                base.setAttribute("target", "_top");
                doc.head.prepend(base);
            } catch {
                // Cross-origin restriction — landing.html is same-origin so this
                // should not happen, but guard silently just in case.
            }
        };

        // landing.html is a static file; its DOM is ready almost immediately.
        iframe.addEventListener("load", injectBaseTarget);

        // In case the iframe is already cached and loaded before the listener fires
        if (iframe.contentDocument?.readyState === "complete") {
            injectBaseTarget();
        }

        return () => iframe.removeEventListener("load", injectBaseTarget);
    }, []);

    return (
        <iframe
            ref={iframeRef}
            src="/landing.html"
            style={{
                position: "fixed",
                top: 0,
                left: 0,
                width: "100vw",
                height: "100vh",
                border: "none",
                margin: 0,
                padding: 0,
                zIndex: 9999,
                display: "block",
            }}
            title="Beacon — AI-Powered BRD Generator"
        />
    );
}
