import { useState } from "react";
import { AuthScreen } from "./AuthScreen.js";
import { Dashboard } from "./Dashboard.js";

function loadToken(): string | null {
  return localStorage.getItem("ta_token");
}

export function App() {
  const [token, setToken] = useState<string | null>(loadToken);

  if (!token) {
    return (
      <AuthScreen
        onAuthenticated={(t) => {
          localStorage.setItem("ta_token", t);
          setToken(t);
        }}
      />
    );
  }

  return (
    <Dashboard
      token={token}
      onLogout={() => {
        localStorage.removeItem("ta_token");
        setToken(null);
      }}
    />
  );
}
