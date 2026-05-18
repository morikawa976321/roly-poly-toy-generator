/**
 * React アプリのエントリポイント。
 *
 * 役割: DOM #root への React 18 マウント。
 * 働き: BrowserRouter で App を包み、index.css を読み込む。
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
