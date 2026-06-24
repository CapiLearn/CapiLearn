import { API_BASE_URL, handleApiResponse } from "./apiClient";

function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
  };
}

export async function recordLoginActivity(token) {
  const response = await fetch(`${API_BASE_URL}/api/activity/login`, {
    method: "POST",
    headers: authHeaders(token),
  });

  return handleApiResponse(response, "Unable to record login activity.");
}

export async function getActivityCalendar(token, { fromDate, toDate }) {
  const params = new URLSearchParams({ fromDate, toDate });

  const response = await fetch(`${API_BASE_URL}/api/activity/calendar?${params}`, {
    method: "GET",
    headers: authHeaders(token),
  });

  return handleApiResponse(response, "Unable to load activity calendar.");
}