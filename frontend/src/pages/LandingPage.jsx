import "../styles/LandingPage.css";

function LandingPage() {
  return (
    <main className="capilearn-page">
      <h1 className="capilearn-slide-title">Landing Page</h1>

      <section className="capilearn-card">
        <header className="capilearn-nav">
          <div className="capilearn-brand">
            <div className="capilearn-brand-icon">♧</div>
            <span className="capilearn-brand-name">Capilearn</span>
          </div>

          <nav className="capilearn-links">
            <a href="#features">Features</a>
            <a href="#how-it-works">How it works</a>
          </nav>

          <button className="capilearn-login">Log in</button>
        </header>

        <section className="capilearn-hero">
          <div className="capilearn-hero-inner">
            <div className="capilearn-badge">
              <span>✣</span>
              <span>Learn. Understand. Grow.</span>
            </div>

            <h2 className="capilearn-headline">
              Learn smarter with your
              <span>chill AI study buddy</span>
            </h2>

            <p className="capilearn-subtitle">
              Get personalized explanations, track your learning streaks, and grow your
              confidence one step at a time.
            </p>

            <div className="capilearn-actions">
              <button className="capilearn-primary">Get started free</button>
              <button className="capilearn-secondary">See how it works</button>
            </div>

            <div className="capilearn-feature-row" id="features">
              <div className="capilearn-feature">
                <span className="capilearn-feature-icon">◔</span>
                <span>Track daily streaks</span>
              </div>

              <div className="capilearn-feature">
                <span className="capilearn-feature-icon">▣</span>
                <span>Chat-based learning</span>
              </div>

              <div className="capilearn-feature">
                <span className="capilearn-feature-icon">◎</span>
                <span>One step at a time</span>
              </div>
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}

export default LandingPage;