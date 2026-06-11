/**
 * Shared base URL for backend API calls.
 */
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:8001";

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
