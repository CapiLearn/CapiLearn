import { SignIn, SignUp } from "@clerk/react";
import "../styles/AuthPage.css";
import capiCoffeeIcon from "../assets/capi_coffee_icon.png";

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
        <img
          src={capiCoffeeIcon}
          alt=""
          className="auth-brand-mark"
          aria-hidden="true"
        />
        <p className="auth-kicker">CapiLearn</p>
        <h1>{title}</h1>
        <p>{description}</p>
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