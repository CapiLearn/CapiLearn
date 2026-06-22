import { useState } from "react";
import { useClerk } from "@clerk/react";
import { useNavigate } from "react-router-dom";

function LogoutButton({ className }) {
  const { signOut } = useClerk();
  const navigate = useNavigate();
  const [isSigningOut, setIsSigningOut] = useState(false);

  async function handleLogout() {
    setIsSigningOut(true);

    try {
      await signOut();
      navigate("/", { replace: true });
    } catch {
      setIsSigningOut(false);
    }
  }

  return (
    <button
      className={className}
      type="button"
      disabled={isSigningOut}
      onClick={handleLogout}
    >
      {isSigningOut ? "Signing out..." : "Log out"}
    </button>
  );
}

export default LogoutButton;