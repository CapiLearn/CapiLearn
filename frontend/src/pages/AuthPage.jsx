import { SignIn, SignUp } from "@clerk/react";
import capiMascot from "../assets/capi-instructor.svg";
import "../styles/AuthPage.css";
import pomMascot from "../assets/pom.svg";

const clerkAppearance = {
  elements: {
    rootBox: "auth-clerk-root",
    cardBox: "auth-clerk-card",
  },
};

function AuthPage({ mode, title, description }) {
  const isSignUp = mode === "sign-up";

  const ClerkAuthComponent = isSignUp ? SignUp : SignIn;

  return (
    <main className="auth-page">
      <section className="auth-hero-panel">
        <div className="auth-brand-mark">♧</div>
        <p className="auth-kicker">CapiLearn</p>
        <h1>{title}</h1>
        <p>{description}</p>

          <div className="auth-mascot-showcase" aria-hidden="true">
            <img src={capiMascot} alt="" className="auth-mascot auth-mascot-capi" />
            <img src={pomMascot} alt="" className="auth-mascot auth-mascot-pom" />
          </div>
      </section>

      <section className="auth-card-shell">
        <ClerkAuthComponent
          routing="path"
          path={isSignUp ? "/sign-up" : "/sign-in"}
          signInUrl="/sign-in"
          signUpUrl="/sign-up"
          appearance={clerkAppearance}
        />
      </section>
    </main>
  );
}

export default AuthPage;