import { useState } from "react";
import { useClerk, useSignIn } from "@clerk/react";
import { isClerkAPIResponseError } from "@clerk/react/errors";
import { useNavigate } from "react-router-dom";

import { API_BASE_URL, handleApiResponse } from "../services/apiClient";

function DemoAdminLoginButton() {
  const clerk = useClerk();
  const { fetchStatus, signIn } = useSignIn();
  const navigate = useNavigate();
  const [isPending, setIsPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const isDisabled = isPending || fetchStatus === "fetching";

  async function handleClick() {
    if (isDisabled) {
      return;
    }

    if (!clerk.loaded) {
      setErrorMessage("Admin login is still loading. Please try again.");
      return;
    }

    setIsPending(true);
    setErrorMessage("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/auth/demo-admin/sign-in-token`,
        {
          method: "POST",
        }
      );
      const payload = await handleApiResponse(
        response,
        "Unable to start demo admin login."
      );

      if (!payload?.token) {
        throw new Error("Demo admin login did not return a sign-in token.");
      }

      const ticketResult = await signIn.ticket({ ticket: payload.token });
      if (ticketResult.error) {
        throw new Error(ticketResult.error.message || "Admin login failed.");
      }

      if (signIn.status !== "complete") {
        throw new Error("Admin login needs additional verification.");
      }

      let didNavigate = false;
      const finalizeResult = await signIn.finalize({
        navigate: async ({ session, decorateUrl }) => {
          if (session?.currentTask) {
            return;
          }

          const url = decorateUrl("/");
          didNavigate = true;
          if (url.startsWith("http")) {
            window.location.href = url;
            return;
          }

          navigate(url, { replace: true });
        },
      });

      if (finalizeResult.error) {
        throw new Error(finalizeResult.error.message || "Admin login failed.");
      }

      if (!didNavigate) {
        navigate("/", { replace: true });
      }
    } catch (error) {
      setErrorMessage(errorMessageFrom(error));
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div className="capilearn-demo-admin-login">
      <button
        type="button"
        className="capilearn-secondary"
        onClick={handleClick}
        disabled={isDisabled}
      >
        {isPending ? "Logging in..." : "Admin Login"}
      </button>
      {errorMessage ? (
        <p className="capilearn-action-error" role="alert">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}

function errorMessageFrom(error) {
  if (isClerkAPIResponseError(error)) {
    return error.errors[0]?.message || "Admin login failed.";
  }

  if (error instanceof Error) {
    return error.message || "Admin login failed.";
  }

  return "Admin login failed. Please try again.";
}

export default DemoAdminLoginButton;
