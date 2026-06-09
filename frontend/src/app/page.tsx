import dynamic from "next/dynamic";

/**
 * Landing page — renders the Framer-exported landing.html inside a
 * full-viewport iframe.  All links inside the iframe are retargeted to
 * `_top` (see _FramerFrame) so navigation escapes the iframe.
 *
 * The iframe component is dynamically imported with `ssr: false` to
 * prevent hydration mismatches when the app is embedded in an iframe.
 */
const FramerFrame = dynamic(() => import("./_FramerFrame"), { ssr: false });

export default function LandingPage() {
    return <FramerFrame />;
}
