import { useState, useSyncExternalStore } from "react";

import {
  cancelBetaCredentials,
  getBetaAuthPromptSnapshot,
  submitBetaCredentials,
  subscribeToBetaAuthPrompt,
} from "../services/apiClient";
import "../styles/BetaAuthDialog.css";

// TEMP BETA AUTH SHIM: Remove when Clerk authentication is wired end-to-end.
function BetaAuthDialog() {
  const promptState = useSyncExternalStore(
    subscribeToBetaAuthPrompt,
    getBetaAuthPromptSnapshot
  );
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (!promptState.isOpen) {
    return null;
  }

  function handleSubmit(event) {
    event.preventDefault();
    const submittedUsername = username;
    const submittedPassword = password;

    setUsername("");
    setPassword("");
    submitBetaCredentials(submittedUsername, submittedPassword);
  }

  function handleCancel() {
    setUsername("");
    setPassword("");
    cancelBetaCredentials();
  }

  return (
    <div
      className="beta-auth-overlay"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          handleCancel();
        }
      }}
    >
      <section
        aria-labelledby="beta-auth-title"
        aria-modal="true"
        className="beta-auth-dialog"
        role="dialog"
      >
        <h2 id="beta-auth-title">Beta access required</h2>
        <p>Enter the temporary CapiLearn beta credentials to continue.</p>

        <form autoComplete="off" onSubmit={handleSubmit}>
          <label htmlFor="beta-auth-username">Username</label>
          <input
            autoComplete="off"
            autoFocus
            id="beta-auth-username"
            onChange={(event) => setUsername(event.target.value)}
            required
            type="text"
            value={username}
          />

          <label htmlFor="beta-auth-password">Password</label>
          <input
            autoComplete="off"
            id="beta-auth-password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />

          <div className="beta-auth-actions">
            <button type="button" onClick={handleCancel}>
              Cancel
            </button>
            <button type="submit">Continue</button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default BetaAuthDialog;
