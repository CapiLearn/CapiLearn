import { Link } from "react-router-dom";
import "../styles/LandingPage.css";
import landingBackground from "../assets/capilearn-landing-background-v2.png";

function LandingPage() {
  return (
    <main
      className="capilearn-page"
      style={{
        backgroundImage: `linear-gradient(rgba(246, 243, 228, 0.08), rgba(246, 243, 228, 0.08)), url(${landingBackground})`,
      }}
    >

      <section
        className="capilearn-card"
        style={{
          backgroundImage: `linear-gradient(rgba(246, 243, 228, 0.08), rgba(246, 243, 228, 0.08)), url(${landingBackground})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
        }}
      >
        <header className="capilearn-nav">
          <button className="capilearn-login">Log in</button>
        </header>

        <section className="capilearn-hero">
          <div className="capilearn-hero-inner">
            <h2 className="capilearn-headline">
              Learn smarter with your
              <span>AI study partner</span>
            </h2>

            <p className="capilearn-subtitle">
              Ask course questions, get guided explanations, and keep your progress visible
              as you study.
            </p>

            <div className="capilearn-actions">
              <Link className="capilearn-primary link-button" to="/workspace">
                Get Started
              </Link>
            </div>

            <div className="capilearn-feature-row">
              <div className="capilearn-feature">
                <span className="capilearn-feature-icon">◔</span>
                <span>Keep study momentum visible</span>
              </div>

              <div className="capilearn-feature">
                <span className="capilearn-feature-icon">▣</span>
                <span>Ask questions in natural language</span>
              </div>

              <div className="capilearn-feature">
                <span className="capilearn-feature-icon">◎</span>
                <span>Work through guided explanations</span>
              </div>
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}

export default LandingPage;