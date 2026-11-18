import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

import { ApiError } from "@/api/client";
import { AppLayout } from "@/components/layout/AppLayout";
import { ToastProvider } from "@/components/ui/toast";
import { ActivityPage } from "@/pages/ActivityPage";
import { CompaniesPage } from "@/pages/CompaniesPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { JobDetailPage } from "@/pages/JobDetailPage";
import { JobsPage } from "@/pages/JobsPage";
import { LlmLabPage } from "@/pages/LlmLabPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { PreferencesPage } from "@/pages/PreferencesPage";
import { ProfilePage } from "@/pages/ProfilePage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      // Don't retry client errors (404, 422 ...) - only transient failures.
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
    },
  },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "jobs", element: <JobsPage /> },
      { path: "jobs/:jobId", element: <JobDetailPage /> },
      { path: "profile", element: <ProfilePage /> },
      { path: "preferences", element: <PreferencesPage /> },
      { path: "companies", element: <CompaniesPage /> },
      { path: "activity", element: <ActivityPage /> },
      { path: "llm-lab", element: <LlmLabPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
