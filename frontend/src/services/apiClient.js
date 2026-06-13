/**
 * Shared base URL for backend API calls.
 */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8001";

// TEMP BETA AUTH SHIM: Remove when Clerk authentication is wired end-to-end.
let betaAuthorizationHeader = null;
let pendingCredentialRequest = null;
let betaAuthPromptSnapshot = { isOpen: false };
const betaAuthPromptListeners = new Set();

function notifyBetaAuthPromptListeners() {
  betaAuthPromptListeners.forEach((listener) => listener());
}

function setBetaAuthPromptSnapshot(snapshot) {
  betaAuthPromptSnapshot = snapshot;
  notifyBetaAuthPromptListeners();
}

function encodeBasicCredentials(username, password) {
  const credentialBytes = new TextEncoder().encode(`${username}:${password}`);
  let binaryCredentials = "";

  credentialBytes.forEach((byte) => {
    binaryCredentials += String.fromCharCode(byte);
  });

  return `Basic ${btoa(binaryCredentials)}`;
}

function requestBetaCredentials() {
  if (pendingCredentialRequest) {
    return pendingCredentialRequest;
  }

  pendingCredentialRequest = new Promise((resolve) => {
    setBetaAuthPromptSnapshot({
      isOpen: true,
      resolve,
    });
  }).finally(() => {
    pendingCredentialRequest = null;
  });

  return pendingCredentialRequest;
}

function withAuthorizationHeader(options, authorizationHeader) {
  const headers = new Headers(options.headers);

  if (authorizationHeader) {
    headers.set("Authorization", authorizationHeader);
  }

  return {
    ...options,
    headers,
  };
}

/**
 * TEMP BETA AUTH SHIM: Remove when Clerk authentication is wired end-to-end.
 * Retries one unauthorized API request with page-session Basic credentials.
 *
 * @param {RequestInfo|URL} input - Fetch resource.
 * @param {RequestInit} options - Fetch options.
 * @returns {Promise<Response>} Fetch response.
 */
export async function apiFetch(input, options = {}) {
  const response = await fetch(
    input,
    withAuthorizationHeader(options, betaAuthorizationHeader)
  );

  if (response.status !== 401) {
    return response;
  }

  betaAuthorizationHeader = null;

  const credentials = await requestBetaCredentials();

  if (!credentials) {
    return response;
  }

  const authorizationHeader = encodeBasicCredentials(
    credentials.username,
    credentials.password
  );
  betaAuthorizationHeader = authorizationHeader;

  const retryResponse = await fetch(
    input,
    withAuthorizationHeader(options, authorizationHeader)
  );

  if (retryResponse.status === 401) {
    betaAuthorizationHeader = null;
  }

  return retryResponse;
}

// TEMP BETA AUTH SHIM: Remove when Clerk authentication is wired end-to-end.
export function subscribeToBetaAuthPrompt(listener) {
  betaAuthPromptListeners.add(listener);
  return () => betaAuthPromptListeners.delete(listener);
}

// TEMP BETA AUTH SHIM: Remove when Clerk authentication is wired end-to-end.
export function getBetaAuthPromptSnapshot() {
  return betaAuthPromptSnapshot;
}

// TEMP BETA AUTH SHIM: Remove when Clerk authentication is wired end-to-end.
export function submitBetaCredentials(username, password) {
  const resolve = betaAuthPromptSnapshot.resolve;
  setBetaAuthPromptSnapshot({ isOpen: false });
  resolve?.({ username, password });
}

// TEMP BETA AUTH SHIM: Remove when Clerk authentication is wired end-to-end.
export function cancelBetaCredentials() {
  const resolve = betaAuthPromptSnapshot.resolve;
  setBetaAuthPromptSnapshot({ isOpen: false });
  resolve?.(null);
}

/**
 * Parses a fetch response and throws a readable error for failed API calls.
 *
 * The backend usually returns errors in this shape:
 * {
 *   code: string,
 *   message: string,
 *   details: object | null
 * }
 *
 * @param {Response} response - Fetch API response object.
 * @param {string} fallbackMessage - Message to use when the API does not return one.
 * @returns {Promise<Object|null>} Parsed JSON response body, or null for 204 responses.
 * @throws {Error} When the response status is not successful.
 */
export async function handleApiResponse(
  response,
  fallbackMessage = "Request failed."
) {
  if (!response.ok) {
    let errorMessage = fallbackMessage;
    let errorCode;
    let errorDetails;

    try {
      const errorData = await response.json();

      errorMessage = errorData?.message || fallbackMessage;
      errorCode = errorData?.code;
      errorDetails = errorData?.details;
    } catch {
      // Keep the fallback message when the response body is not valid JSON.
    }

    const error = new Error(errorMessage);
    error.code = errorCode;
    error.details = errorDetails;

    throw error;
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}
