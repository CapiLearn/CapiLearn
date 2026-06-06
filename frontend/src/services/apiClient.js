/**
 * Shared base URL for local backend API calls.
 *
 * The Vite frontend runs on localhost:5173 and the FastAPI backend runs on
 * 127.0.0.1:8001 during local development.
 */
export const API_BASE_URL = "http://127.0.0.1:8001";

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
    try {
      const errorData = await response.json();
      throw new Error(errorData.message || fallbackMessage);
    } catch {
      throw new Error(fallbackMessage);
    }
  }

  if (response.status === 204) {
    return null;
  }

  return response.json();
}