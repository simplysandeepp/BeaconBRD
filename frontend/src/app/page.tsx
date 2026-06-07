export default function LandingPage() {
    return (
        <iframe
            src="/landing.html"
            style={{
                position: 'fixed',
                top: 0,
                left: 0,
                width: '100vw',
                height: '100vh',
                border: 'none',
                margin: 0,
                padding: 0,
                zIndex: 9999,
                display: 'block',
            }}
            title="Beacon — AI-Powered BRD Generator"
        />
    );
}
