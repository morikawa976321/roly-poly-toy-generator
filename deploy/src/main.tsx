/**
 * deploy SPA のエントリポイント。
 *
 * 役割: Vite バンドルの DOM マウント。
 * 働き: #root に App を StrictMode で render する。
 */

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
