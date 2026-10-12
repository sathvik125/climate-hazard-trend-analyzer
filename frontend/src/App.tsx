import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Dashboard } from "./components/Dashboard";

export default function App() {
  const [queryClient] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  );
}
