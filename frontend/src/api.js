export const ROLE_NAME = { manager: "Project manager", developer: "Developer", newcomer: "New team member" };

const KEY = "knowflow-session";

export function loadSession() {
  try {
    return JSON.parse(localStorage.getItem(KEY));
  } catch {
    return null;
  }
}

export function saveSession(session) {
  try {
    if (session) localStorage.setItem(KEY, JSON.stringify(session));
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode: stay signed in for this tab only */
  }
}

let token = loadSession()?.token || null;
export const setToken = (t) => (token = t);

export async function api(path, { method = "GET", body, form, text } = {}) {
  const headers = {};
  if (token) headers.Authorization = "Bearer " + token;
  if (body) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch("/api" + path, { method, headers, body: form || (body ? JSON.stringify(body) : undefined) });
  } catch {
    throw new Error("The server did not answer. It may be waking up; try again in a few seconds.");
  }
  if (!res.ok) {
    let detail = "Request failed (" + res.status + ").";
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* keep the default message */
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return text ? res.text() : res.json();
}
