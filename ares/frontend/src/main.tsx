import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

const container = document.getElementById("root")!;
container.innerHTML = ""; // clear the pre-paint boot mark
createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

/* Register the shell service worker so ARES installs to the home screen and
   launches instantly. It caches only static assets — never market data. */
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => {
      /* Registration needs a secure context; the app works regardless. */
    });
  });
}
