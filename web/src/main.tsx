import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Claims from "./pages/Claims";
import DecisionDetail from "./pages/DecisionDetail";
import PriorAuth from "./pages/PriorAuth";
import Queues from "./pages/Queues";
import Members from "./pages/Members";
import MemberDetail from "./pages/MemberDetail";
import Rules from "./pages/Rules";
import Models from "./pages/Models";

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 5000, refetchOnWindowFocus: false, retry: 1 } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="claims" element={<Claims />} />
            <Route path="decisions/:id" element={<DecisionDetail />} />
            <Route path="prior-auth" element={<PriorAuth />} />
            <Route path="queues" element={<Queues />} />
            <Route path="members" element={<Members />} />
            <Route path="members/:id" element={<MemberDetail />} />
            <Route path="rules" element={<Rules />} />
            <Route path="models" element={<Models />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
